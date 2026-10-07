from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from . import explain, planner, residue, soil
from .adapters import market, weather
from .config import settings
from .db import Farm, Outcome, PlanVersion, get_session, init_db
from .knowledge import CROPS, RESIDUE, next_season
from .schemas import (CompareRequest, FarmProfile, FarmUpsert, OutcomeRequest, PlanRequest,
                      ResidueRequest, SoilAssessRequest)


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title="Fasal Sarthi API", version="0.1.0", lifespan=lifespan,
              description="Multi-season farm planning engine. Demo data is simulated/placeholder.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","),
                   allow_methods=["*"], allow_headers=["*"])


def _farm(session: Session, farm_id: int) -> tuple[Farm, FarmProfile]:
    row = session.get(Farm, farm_id)
    if not row:
        raise HTTPException(404, "farm not found")
    return row, FarmProfile(**row.profile)


@app.get("/health")
def health():
    return {"ok": True, "live_data": settings.use_live_data, "crops": list(CROPS)}


@app.post("/farm/profile")
def upsert_farm(body: FarmUpsert, session: Session = Depends(get_session)):
    profile = FarmProfile(**body.model_dump(exclude={"farm_id"}))
    row = session.get(Farm, body.farm_id) if body.farm_id else Farm()
    if body.farm_id and not row:
        raise HTTPException(404, "farm not found")
    if profile.soil:
        profile.soil_index = soil.assess(profile.soil)["soil_index"]
    row.profile = profile.model_dump()
    session.add(row); session.commit(); session.refresh(row)
    return {"farm_id": row.id, "profile": row.profile}


@app.post("/soil/assessment")
def soil_assessment(body: SoilAssessRequest, session: Session = Depends(get_session)):
    result = soil.assess(body.soil)
    if body.farm_id:
        row, profile = _farm(session, body.farm_id)
        profile.soil, profile.soil_index = body.soil, result["soil_index"]
        row.profile = profile.model_dump()
        session.add(row); session.commit()
    return result


def _prices(profile, overrides):
    prices, meta = market.get_prices(profile.state)
    return {**prices, **overrides}, meta


@app.post("/plan/generate")
def generate(body: PlanRequest, session: Session = Depends(get_session)):
    _, profile = _farm(session, body.farm_id)
    prices, meta = _prices(profile, body.price_overrides)
    plans = planner.generate_plans(profile, body.horizon, prices)
    for p in plans:
        p["explanation"] = explain.explain(p, profile)
    payload = {"plans": plans, "prices": prices, "price_meta": meta,
               "weather": weather.forecast(profile.lat, profile.lon), "soil_index_start": profile.soil_index,
               "data_note": "Crop/residue parameters are placeholders pending agronomist validation."}
    session.add(PlanVersion(farm_id=body.farm_id, payload=payload)); session.commit()
    return payload


@app.post("/plan/compare")
def compare(body: CompareRequest, session: Session = Depends(get_session)):
    _, profile = _farm(session, body.farm_id)
    prices, _ = _prices(profile, body.price_overrides)
    return {"results": [planner.evaluate(profile, s, prices) for s in body.sequences]}


@app.post("/residue/decision")
def residue_decision(body: ResidueRequest):
    if body.crop not in CROPS:
        raise HTTPException(400, f"unknown crop; use one of {list(CROPS)}")
    return {"options": residue.decide(body.crop, body.area_acres, body.equipment_access, body.biomass_buyer_km)}


@app.post("/season/outcome")
def record_outcome(body: OutcomeRequest, session: Session = Depends(get_session)):
    row, profile = _farm(session, body.farm_id)
    if body.residue_action:
        if body.residue_action not in RESIDUE:
            raise HTTPException(400, f"residue_action must be one of {list(RESIDUE)}")
        profile.soil_index = max(0, min(100, profile.soil_index + RESIDUE[body.residue_action]["soil_delta"]))
    if body.soil:
        profile.soil, profile.soil_index = body.soil, soil.assess(body.soil)["soil_index"]
    profile.previous_crop, profile.next_season = body.crop, next_season(body.season)
    row.profile = profile.model_dump()
    session.add(row)
    session.add(Outcome(farm_id=body.farm_id, payload=body.model_dump()))
    session.commit()
    return {"farm_id": body.farm_id, "soil_index": profile.soil_index, "next_season": profile.next_season}


@app.get("/farm/memory")
def memory(farm_id: int, session: Session = Depends(get_session)):
    _, profile = _farm(session, farm_id)
    plans = session.exec(select(PlanVersion).where(PlanVersion.farm_id == farm_id)).all()
    outs = session.exec(select(Outcome).where(Outcome.farm_id == farm_id)).all()
    return {"profile": profile, "plan_versions": [{"id": p.id, "created_at": p.created_at,
            "summary": [(q["plan"], q["total_profit_inr"], q["soil_final"]) for q in p.payload["plans"]]} for p in plans],
            "outcomes": [{"created_at": o.created_at, **o.payload} for o in outs]}
