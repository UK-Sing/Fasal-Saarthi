import secrets
from contextlib import asynccontextmanager
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from . import explain, fertilizer, planner, residue, soil
from .adapters import market, weather
from .config import settings
from .db import MODEL_VERSION
from .knowledge import CROPS, RESIDUE, next_season
from .repositories import NotFound, Repository, get_repo
from .schemas import (CompareRequest, FarmProfile, FarmUpsert, FertilizerRequest, OutcomeRequest,
                      PlanRequest, ResidueRequest, SoilAssessRequest)

DATA_NOTE = ("SIMULATED / PLACEHOLDER agronomy: crop yields, costs, water, soil and residue parameters and "
             "fertilizer doses are placeholders pending agronomist validation. Default prices are Govt MSP.")


@asynccontextmanager
async def lifespan(app):
    get_repo()  # builds the configured backend (and creates SQLite tables) once, failing fast on bad config
    yield


app = FastAPI(title="Fasal Sarthi API", version=MODEL_VERSION, lifespan=lifespan,
              description="Multi-season farm planning engine. Demo data is simulated/placeholder.")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                   allow_methods=["*"], allow_headers=["*"])

_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_key(key: str | None = Security(_key_header)):
    if settings.api_key and not secrets.compare_digest((key or "").encode(), settings.api_key.encode()):
        raise HTTPException(401, "missing or invalid X-API-Key")


api = APIRouter(dependencies=[Depends(require_key)])


@app.exception_handler(NotFound)
def _not_found(request: Request, exc: NotFound):
    return JSONResponse(status_code=404, content={"detail": "farm not found"})


def _farm(repo: Repository, farm_id: str) -> FarmProfile:
    profile = repo.get_farm(farm_id)
    if profile is None:
        raise HTTPException(404, "farm not found")
    return FarmProfile(**profile)


@app.get("/health")
def health():
    return {"ok": True, "version": MODEL_VERSION, "live_data": settings.use_live_data,
            "auth_required": bool(settings.api_key), "database_backend": settings.database_backend,
            "crops": list(CROPS)}


@api.post("/farm/profile")
def upsert_farm(body: FarmUpsert, repo: Repository = Depends(get_repo)):
    # Update = merge: fields not sent keep their stored values (e.g. soil index after a burn, next season).
    sent = body.model_dump(exclude={"farm_id"}, exclude_unset=True)

    def merge(stored: dict):
        profile = FarmProfile(**{**stored, **sent})
        new_soil = profile.soil and profile.soil.model_dump() != stored.get("soil")  # re-sending same test keeps history
        if new_soil and "soil_index" not in sent:
            profile.soil_index = soil.assess(profile.soil)["soil_index"]
        return profile.model_dump(mode="json"), None

    if body.farm_id is None:
        profile = FarmProfile(**sent)
        if profile.soil and "soil_index" not in sent:
            profile.soil_index = soil.assess(profile.soil)["soil_index"]
        farm_id = repo.create_farm(profile.model_dump(mode="json"))
        return {"farm_id": farm_id, "profile": repo.get_farm(farm_id)}
    return {"farm_id": body.farm_id, "profile": repo.apply(body.farm_id, merge)}


@api.post("/soil/assessment")
def soil_assessment(body: SoilAssessRequest, repo: Repository = Depends(get_repo)):
    result = soil.assess(body.soil)
    if body.farm_id is not None:
        def fn(stored: dict):
            profile = FarmProfile(**stored)
            profile.soil, profile.soil_index = body.soil, result["soil_index"]
            return profile.model_dump(mode="json"), None
        repo.apply(body.farm_id, fn)
    return result


def _context(profile: FarmProfile, overrides: dict) -> dict:
    """Prices + weather for a farm. Live sources only when USE_LIVE_DATA=true; otherwise deterministic."""
    prices, meta = market.get_prices(profile.state)
    if overrides:
        meta = {**meta, "overridden": sorted(overrides)}
    clim = weather.seasonal_rain(profile.lat, profile.lon)
    return {"prices": {**prices, **overrides}, "price_meta": meta, "climatology": clim,
            "extra_water": clim["effective_rain_mm"] if clim else None}


@api.post("/plan/generate")
def generate(body: PlanRequest, repo: Repository = Depends(get_repo)):
    profile = _farm(repo, body.farm_id)
    ctx = _context(profile, body.price_overrides)
    plans = planner.generate_plans(profile, body.horizon, ctx["prices"], ctx["extra_water"])
    for p in plans:
        p["explanation"] = explain.explain(p, profile)
        first = p["sequence"][0]["crop"]
        p["next_season_fertilizer"] = fertilizer.recommend(first, profile.soil, profile.area_acres) if first else None
    fc = weather.forecast(profile.lat, profile.lon)
    payload = {"plans": plans, "prices": ctx["prices"], "price_meta": ctx["price_meta"], "weather": fc,
               "water": {"irrigation_mm_per_season": profile.water_mm_per_season, "rain_climatology": ctx["climatology"],
                         "note": "effective seasonal rain added to irrigation water" if ctx["climatology"]
                         else "irrigation water only (live weather off or no lat/lon)"},
               "warnings": (fc or {}).get("warnings", []), "soil_index_start": profile.soil_index,
               "previous_crop": profile.previous_crop, "next_season": profile.next_season,
               "horizon": body.horizon, "model_version": MODEL_VERSION, "data_note": DATA_NOTE}
    plan_version_id = repo.save_plan(body.farm_id, payload, MODEL_VERSION)
    return {"plan_version_id": plan_version_id, **payload}


@api.post("/plan/compare")
def compare(body: CompareRequest, repo: Repository = Depends(get_repo)):
    profile = _farm(repo, body.farm_id)
    ctx = _context(profile, body.price_overrides)
    return {"results": [planner.evaluate(profile, s, ctx["prices"], ctx["extra_water"]) for s in body.sequences],
            "prices": ctx["prices"], "data_note": DATA_NOTE}


@api.post("/residue/decision")
def residue_decision(body: ResidueRequest):
    return {"options": residue.decide(body.crop, body.area_acres, body.equipment_access, body.biomass_buyer_km),
            "data_note": DATA_NOTE}


@api.post("/fertilizer/recommendation")
def fertilizer_recommendation(body: FertilizerRequest, repo: Repository = Depends(get_repo)):
    profile = _farm(repo, body.farm_id) if body.farm_id is not None else None
    soil_in = body.soil or (profile.soil if profile else None)
    area = body.area_acres or (profile.area_acres if profile else 1.0)
    return fertilizer.recommend(body.crop, soil_in, area)


@api.post("/season/outcome")
def record_outcome(body: OutcomeRequest, repo: Repository = Depends(get_repo)):
    outcome_payload = body.model_dump(mode="json")
    state = {}

    def fn(stored: dict):
        profile = FarmProfile(**stored)
        before = profile.soil_index
        if body.residue_action:
            profile.soil_index = round(max(0, min(100, profile.soil_index + RESIDUE[body.residue_action]["soil_delta"])), 1)
        if body.soil:  # a fresh soil test overrides the modelled estimate
            profile.soil, profile.soil_index = body.soil, soil.assess(body.soil)["soil_index"]
        profile.previous_crop, profile.next_season = body.crop, next_season(body.season)
        state["before"] = before
        payload = {**outcome_payload, "soil_index_before": before, "soil_index_after": profile.soil_index}
        return profile.model_dump(mode="json"), payload

    new_profile = repo.apply(body.farm_id, fn)
    return {"farm_id": body.farm_id, "soil_index_before": state["before"], "soil_index": new_profile["soil_index"],
            "previous_crop": new_profile["previous_crop"], "next_season": new_profile["next_season"]}


@api.get("/farm/memory")
def memory(farm_id: str, repo: Repository = Depends(get_repo)):
    profile = _farm(repo, farm_id)
    plans = repo.list_plans(farm_id)
    outs = repo.list_outcomes(farm_id)
    return {"farm_id": farm_id, "profile": profile,
            "plan_versions": [{"id": p["id"], "created_at": p["created_at"], "model_version": p["model_version"],
                               "soil_index_start": p["payload"].get("soil_index_start"),
                               "summary": [{"plan": q["plan"], "total_profit_inr": q["total_profit_inr"],
                                            "soil_final": q["soil_final"],
                                            "first_crop": q["sequence"][0]["crop"]} for q in p["payload"]["plans"]]}
                              for p in plans],
            "outcomes": [{"id": o["id"], "created_at": o["created_at"], **o["payload"]} for o in outs]}


app.include_router(api)
