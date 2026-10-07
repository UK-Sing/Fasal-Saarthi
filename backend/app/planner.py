from ortools.sat.python import cp_model
from .knowledge import CROPS, FALLOW_GAIN, FAMILIES, SEASONS
from .schemas import FarmProfile

# w_soil: objective value (INR per acre) of one soil-index point at the end of the horizon.
# deficit_boost: w_soil is multiplied by (1 + deficit_boost * points below SOIL_TARGET), so a degraded
#   farm (e.g. after residue burning) puts more weight on recovery. Planning policy, not agronomy.
# risk: share of expected revenue x crop risk deducted as a risk penalty.
PLANS = {
    "A_max_profit":    {"w_soil": 100,  "deficit_boost": 0.0, "risk": 0.1, "floor_abs": 30, "floor_rel": None},
    "B_balanced":      {"w_soil": 1000, "deficit_boost": 0.1, "risk": 0.3, "floor_abs": 52, "floor_rel": None},
    "C_soil_recovery": {"w_soil": 8000, "deficit_boost": 0.0, "risk": 0.5, "floor_abs": None, "floor_rel": 4},
}
SOIL_TARGET = 50
SCALE = 10  # soil index handled in tenths inside the integer model


def season_names(start: str, horizon: int) -> list[str]:
    i = SEASONS.index(start)
    return [SEASONS[(i + k) % 3] for k in range(horizon)]


def econ(crop: str, prices: dict) -> tuple[float, float]:
    c = CROPS[crop]
    rev = c["yield_q_per_acre"] * prices.get(crop, c["price_inr_per_q"])
    return rev, rev - c["cost_inr_per_acre"]


def water_available(farm: FarmProfile, season: str, extra_water: dict | None) -> float:
    return farm.water_mm_per_season + (extra_water or {}).get(season, 0)


def _trajectory(farm: FarmProfile, picks: list[str | None]) -> list[float]:
    soil, out = farm.soil_index, [round(farm.soil_index, 1)]
    for c in picks:
        soil = max(0.0, min(100.0, soil + (CROPS[c]["soil_delta"] if c else FALLOW_GAIN)))
        out.append(round(soil, 1))
    return out


def _summarise(farm, names, picks, prices, key, relaxed, extra_water):
    seq, total, water, risk, n = [], 0.0, 0.0, 0.0, 0
    for s, c in enumerate(picks):
        profit = econ(c, prices)[1] * farm.area_acres if c else 0.0
        total += profit
        if c:
            water += CROPS[c]["water_mm"]
            risk += CROPS[c]["risk"]
            n += 1
        seq.append({"season_index": s, "season": names[s], "crop": c, "profit_inr": round(profit),
                    "water_mm": CROPS[c]["water_mm"] if c else 0,
                    "water_available_mm": round(water_available(farm, names[s], extra_water))})
    traj = _trajectory(farm, picks)
    return {"plan": key, "sequence": seq, "total_profit_inr": round(total),
            "soil_trajectory": traj, "soil_final": traj[-1], "total_water_mm": water,
            "avg_risk": round(risk / max(1, n), 2), "floor_relaxed": relaxed}


def _floor(cfg, start: float) -> float:
    f = cfg["floor_abs"] if cfg["floor_abs"] is not None else start + cfg["floor_rel"]
    return min(f, 100)


def solve(farm: FarmProfile, horizon: int, prices: dict, key: str, extra_water: dict | None = None,
          relax: bool = False) -> dict | None:
    cfg, names, area = PLANS[key], season_names(farm.next_season, horizon), farm.area_acres
    allowed = [c for c in CROPS if c not in farm.excluded_crops]
    m = cp_model.CpModel()
    x = {}
    for s in range(horizon):
        for c in allowed:
            cr = CROPS[c]
            if (names[s] in cr["seasons"] and cr["water_mm"] <= water_available(farm, names[s], extra_water)
                    and cr["cost_inr_per_acre"] * area <= farm.budget_inr_per_season):
                x[s, c] = m.NewBoolVar(f"x_{s}_{c}")
    for s in range(horizon):
        here = [c for c in allowed if (s, c) in x]
        if here:
            m.Add(sum(x[s, c] for c in here) <= 1)
        for c in here:
            if (s + 1, c) in x:
                m.Add(x[s, c] + x[s + 1, c] <= 1)
    prev = farm.previous_crop
    if prev and (0, prev) in x:
        m.Add(x[0, prev] == 0)
    for fam, rule in FAMILIES.items():
        k, members = rule["max_consecutive"], [c for c in allowed if CROPS[c]["family"] == fam]
        for s in range(horizon - k):
            terms = [x[t, c] for t in range(s, s + k + 1) for c in members if (t, c) in x]
            if terms:
                m.Add(sum(terms) <= k)
        if prev and CROPS[prev]["family"] == fam:  # the previous season counts towards the run
            terms = [x[t, c] for t in range(min(k, horizon)) for c in members if (t, c) in x]
            if terms:
                m.Add(sum(terms) <= k - 1)
    start = int(round(farm.soil_index * SCALE))
    soil = start + FALLOW_GAIN * SCALE * horizon + sum(
        (CROPS[c]["soil_delta"] - FALLOW_GAIN) * SCALE * v for (s, c), v in x.items())
    if not relax:
        m.Add(soil >= int(round(_floor(cfg, farm.soil_index) * SCALE)))
    soil_capped = m.NewIntVar(-100 * SCALE, 100 * SCALE, "soil_capped")
    m.Add(soil_capped <= soil)
    profit = 0
    for (s, c), v in x.items():
        rev, prof = econ(c, prices)
        profit += round((prof - cfg["risk"] * CROPS[c]["risk"] * rev) * area) * v
    w_soil = cfg["w_soil"] * (1 + cfg["deficit_boost"] * max(0.0, SOIL_TARGET - farm.soil_index))
    m.Maximize(profit + round(w_soil * area / SCALE) * soil_capped)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5
    solver.parameters.random_seed = 7
    solver.parameters.num_workers = 1  # deterministic results for the demo
    if solver.Solve(m) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None if relax else solve(farm, horizon, prices, key, extra_water, relax=True)
    picks = [next((c for c in allowed if (s, c) in x and solver.Value(x[s, c])), None) for s in range(horizon)]
    return _summarise(farm, names, picks, prices, key, relax, extra_water)


def generate_plans(farm: FarmProfile, horizon: int, prices: dict, extra_water: dict | None = None) -> list[dict]:
    return [p for k in PLANS if (p := solve(farm, horizon, prices, k, extra_water))]


def evaluate(farm: FarmProfile, sequence: list[str | None], prices: dict, extra_water: dict | None = None) -> dict:
    names, issues = season_names(farm.next_season, len(sequence)), []
    bad = [c for c in sequence if c is not None and c not in CROPS]
    if bad:
        return {"plan": "custom", "issues": [f"unknown crop {c}" for c in bad]}
    full = [farm.previous_crop] + list(sequence)
    for s, c in enumerate(sequence):
        if c is None:
            continue
        cr = CROPS[c]
        if c in farm.excluded_crops:
            issues.append(f"{c} is excluded by the farmer")
        if names[s] not in cr["seasons"]:
            issues.append(f"{c} not suited to {names[s]} (season {s + 1})")
        if cr["water_mm"] > water_available(farm, names[s], extra_water):
            issues.append(f"{c} exceeds water availability in season {s + 1}")
        if cr["cost_inr_per_acre"] * farm.area_acres > farm.budget_inr_per_season:
            issues.append(f"{c} exceeds the season budget in season {s + 1}")
        if full[s] == c:
            issues.append(f"{c} repeated back-to-back (season {s + 1})")
    for fam, rule in FAMILIES.items():
        k, run = rule["max_consecutive"], 0
        for i, c in enumerate(full):
            run = run + 1 if c and CROPS[c]["family"] == fam else 0
            if run == k + 1:  # full[0] is the previous crop, so full[i] is season i (1-based)
                issues.append(f"more than {k} consecutive {fam} season(s) at season {i}")
    out = _summarise(farm, names, list(sequence), prices, "custom", False, extra_water)
    soil_floor = PLANS["B_balanced"]["floor_abs"]
    if out["soil_final"] < soil_floor:
        issues.append(f"final soil index {out['soil_final']} below the balanced floor of {soil_floor}")
    out["issues"] = issues
    return out
