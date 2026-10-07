from ortools.sat.python import cp_model
from .knowledge import CROPS, FALLOW_GAIN, FAMILIES, SEASONS
from .schemas import FarmProfile

PLANS = {
    "A_max_profit": {"w_soil": 100,  "risk": 0.1, "floor_abs": 30, "floor_rel": None},
    "B_balanced":   {"w_soil": 1500, "risk": 0.3, "floor_abs": 50, "floor_rel": None},
    "C_soil_recovery": {"w_soil": 5000, "risk": 0.5, "floor_abs": None, "floor_rel": 4},
}


def season_names(start: str, horizon: int) -> list[str]:
    i = SEASONS.index(start)
    return [SEASONS[(i + k) % 3] for k in range(horizon)]


def econ(crop: str, prices: dict) -> tuple[float, float]:
    c = CROPS[crop]
    rev = c["yield_q_per_acre"] * prices.get(crop, c["price_inr_per_q"])
    return rev, rev - c["cost_inr_per_acre"]


def _trajectory(farm: FarmProfile, picks: list[str | None]) -> list[float]:
    soil, out = farm.soil_index, [farm.soil_index]
    for c in picks:
        soil += CROPS[c]["soil_delta"] if c else FALLOW_GAIN
        out.append(round(soil, 1))
    return out


def _summarise(farm, names, picks, prices, key, relaxed):
    seq, total, water, risk = [], 0.0, 0.0, 0.0
    for s, c in enumerate(picks):
        profit = econ(c, prices)[1] * farm.area_acres if c else 0.0
        total += profit
        water += CROPS[c]["water_mm"] if c else 0
        risk += CROPS[c]["risk"] if c else 0
        seq.append({"season_index": s, "season": names[s], "crop": c, "profit_inr": round(profit)})
    traj = _trajectory(farm, picks)
    return {"plan": key, "sequence": seq, "total_profit_inr": round(total),
            "soil_trajectory": traj, "soil_final": traj[-1], "total_water_mm": water,
            "avg_risk": round(risk / max(1, len(picks)), 2), "floor_relaxed": relaxed}


def solve(farm: FarmProfile, horizon: int, prices: dict, key: str, relax=False):
    cfg, names, area = PLANS[key], season_names(farm.next_season, horizon), farm.area_acres
    allowed = [c for c in CROPS if c not in farm.excluded_crops]
    m = cp_model.CpModel()
    x = {(s, c): m.NewBoolVar(f"x_{s}_{c}") for s in range(horizon) for c in allowed
         if names[s] in CROPS[c]["seasons"]}
    for s in range(horizon):
        here = [c for c in allowed if (s, c) in x]
        m.Add(sum(x[s, c] for c in here) <= 1)
        for c in here:
            cr = CROPS[c]
            if cr["water_mm"] > farm.water_mm_per_season or cr["cost_inr_per_acre"] * area > farm.budget_inr_per_season:
                m.Add(x[s, c] == 0)
            if (s + 1, c) in x:
                m.Add(x[s, c] + x[s + 1, c] <= 1)
    for fam, rule in FAMILIES.items():
        k, members = rule["max_consecutive"], [c for c in allowed if CROPS[c]["family"] == fam]
        for s in range(horizon - k):
            terms = [x[t, c] for t in range(s, s + k + 1) for c in members if (t, c) in x]
            if terms:
                m.Add(sum(terms) <= k)
    prev = CROPS.get(farm.previous_crop or "")
    if prev and FAMILIES[prev["family"]]["max_consecutive"] == 1:
        for c in allowed:
            if (0, c) in x and CROPS[c]["family"] == prev["family"]:
                m.Add(x[0, c] == 0)
    start = int(round(farm.soil_index))
    soil = start + FALLOW_GAIN * horizon + sum((CROPS[c]["soil_delta"] - FALLOW_GAIN) * v for (s, c), v in x.items())
    floor = cfg["floor_abs"] if cfg["floor_abs"] is not None else start + cfg["floor_rel"]
    if not relax:
        m.Add(soil >= int(floor))
    profit = 0
    for (s, c), v in x.items():
        rev, prof = econ(c, prices)
        profit += int((prof - cfg["risk"] * CROPS[c]["risk"] * rev) * area) * v
    m.Maximize(profit + int(cfg["w_soil"] * area) * soil)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5
    solver.parameters.random_seed = 7
    if solver.Solve(m) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None if relax else solve(farm, horizon, prices, key, relax=True)
    picks = [next((c for c in allowed if (s, c) in x and solver.Value(x[s, c])), None) for s in range(horizon)]
    return _summarise(farm, names, picks, prices, key, relax)


def generate_plans(farm: FarmProfile, horizon: int, prices: dict) -> list[dict]:
    return [p for k in PLANS if (p := solve(farm, horizon, prices, k))]


def evaluate(farm: FarmProfile, sequence: list[str | None], prices: dict) -> dict:
    names, issues = season_names(farm.next_season, len(sequence)), []
    bad = [c for c in sequence if c is not None and c not in CROPS]
    if bad:
        return {"plan": "custom", "issues": [f"unknown crop {c}" for c in bad]}
    for s, c in enumerate(sequence):
        if c is None:
            continue
        if c not in CROPS:
            issues.append(f"unknown crop {c}")
        elif names[s] not in CROPS[c]["seasons"]:
            issues.append(f"{c} not suited to {names[s]}")
        elif CROPS[c]["water_mm"] > farm.water_mm_per_season:
            issues.append(f"{c} exceeds water availability")
        if s and sequence[s - 1] == c:
            issues.append(f"{c} repeated back-to-back")
    out = _summarise(farm, names, sequence, prices, "custom", False)
    out["issues"] = issues
    return out
