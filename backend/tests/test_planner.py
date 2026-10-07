import pytest
from app import fertilizer, planner, residue, soil
from app.knowledge import CROPS, FAMILIES
from app.schemas import FarmProfile, SoilInput

SOIL = SoilInput(ph=8.1, ec=0.6, oc=0.42, n=250, p=14, k=150)


def farm(**kw):
    base = dict(name="demo", area_acres=3, previous_crop="rice", next_season="rabi",
                soil_index=soil.assess(SOIL)["soil_index"])
    return FarmProfile(**{**base, **kw})


def _picks(p):
    return [s["crop"] for s in p["sequence"]]


def test_three_plans_respect_floors():
    f = farm()
    plans = {p["plan"]: p for p in planner.generate_plans(f, 6, {})}
    assert set(plans) == {"A_max_profit", "B_balanced", "C_soil_recovery"}
    assert plans["B_balanced"]["soil_final"] >= planner.PLANS["B_balanced"]["floor_abs"]
    assert plans["C_soil_recovery"]["soil_final"] >= f.soil_index + planner.PLANS["C_soil_recovery"]["floor_rel"]
    assert not any(p["floor_relaxed"] for p in plans.values())
    assert plans["A_max_profit"]["total_profit_inr"] >= plans["B_balanced"]["total_profit_inr"] \
        >= plans["C_soil_recovery"]["total_profit_inr"]
    assert plans["C_soil_recovery"]["soil_final"] >= plans["B_balanced"]["soil_final"] >= plans["A_max_profit"]["soil_final"]


@pytest.mark.parametrize("prev,start", [("rice", "rabi"), ("wheat", "zaid"), ("chickpea", "zaid"), (None, "kharif")])
def test_rotation_rules_hold_for_every_plan(prev, start):
    f = farm(previous_crop=prev, next_season=start)
    names = planner.season_names(start, 6)
    for p in planner.generate_plans(f, 6, {}):
        full = [prev] + _picks(p)
        assert all(a is None or a != b for a, b in zip(full, full[1:])), p
        for s, c in enumerate(_picks(p)):
            assert c is None or names[s] in CROPS[c]["seasons"]
        for fam, rule in FAMILIES.items():
            run = 0
            for c in full:
                run = run + 1 if c and CROPS[c]["family"] == fam else 0
                assert run <= rule["max_consecutive"], (fam, full)
        assert planner.evaluate(f, _picks(p), {})["issues"] == [] or p["plan"] == "A_max_profit"


def test_price_crash_changes_plan():
    base = {p["plan"]: _picks(p) for p in planner.generate_plans(farm(), 6, {})}
    crash = {p["plan"]: _picks(p) for p in planner.generate_plans(farm(), 6, {"mustard": 4300})}
    assert "mustard" in base["A_max_profit"] and base != crash


def test_lower_soil_changes_balanced_plan():
    f = farm()
    before = planner.solve(f, 6, {}, "B_balanced")
    after = planner.solve(farm(soil_index=f.soil_index - 3), 6, {}, "B_balanced")  # burn: soil_delta -3
    assert _picks(before) != _picks(after)
    assert after["soil_final"] >= planner.PLANS["B_balanced"]["floor_abs"]


def test_water_budget_and_exclusions():
    f = farm(water_mm_per_season=100)
    assert all(c is None for p in planner.generate_plans(f, 3, {}) for c in _picks(p))
    rainy = planner.generate_plans(farm(water_mm_per_season=100, next_season="kharif"), 3, {}, {"kharif": 1300})
    assert any(_picks(p)[0] for p in rainy)
    assert all(c is None for p in rainy for c in _picks(p)[1:])
    poor = farm(budget_inr_per_season=30000)  # 3 acres -> only crops costing <= 10000/acre
    for p in planner.generate_plans(poor, 6, {}):
        assert all(c is None or CROPS[c]["cost_inr_per_acre"] * 3 <= 30000 for c in _picks(p))
    excl = farm(excluded_crops=["mustard", "maize"])
    for p in planner.generate_plans(excl, 6, {}):
        assert not {"mustard", "maize"} & set(_picks(p))


def test_soil_trajectory_clamped():
    p = planner.solve(farm(soil_index=99), 6, {}, "C_soil_recovery")
    assert max(p["soil_trajectory"]) <= 100


def test_evaluate_flags_violations():
    f = farm()  # previous rice, starts rabi
    issues = planner.evaluate(f, ["wheat", "maize", "rice"], {})["issues"]
    assert any("consecutive cereal" in i for i in issues)
    issues = planner.evaluate(f, ["rice", "moong", "moong"], {})["issues"]
    assert any("not suited to rabi" in i for i in issues) and any("back-to-back" in i for i in issues)
    assert planner.evaluate(f, ["chickpea", None, "moong"], {})["issues"] == []


def test_soil_and_residue():
    assert 0 < soil.assess(SOIL)["soil_index"] < 100
    opts = residue.decide("rice", 2, True, 10)
    assert opts[0]["option"] != "burn" and opts[-1]["option"] == "burn"
    assert all(o["feasible"] for o in opts)
    no_eq = residue.decide("rice", 2, False, None)
    assert {o["option"] for o in no_eq if not o["feasible"]} == {"happy_seeder", "incorporate", "biomass_sale"}


def test_fertilizer_math():
    low = SoilInput(ph=7, ec=0.5, oc=0.4, n=200, p=14, k=300, zn=0.4, b=0.2)  # N low, P medium, K high
    r = fertilizer.recommend("wheat", low, 1 / fertilizer.HA_PER_ACRE)  # exactly 1 ha
    assert r["nutrients_kg_per_ha"] == {"n": 150.0, "p2o5": 60.0, "k2o": 30.0}
    prod = {p["product"]: p for p in r["products"]}
    assert prod["dap"]["kg_total"] == round(60 / 0.46, 1)
    assert prod["urea"]["kg_total"] == round((150 - 60 / 0.46 * 0.18) / 0.46, 1)
    assert prod["mop"]["kg_total"] == 50.0
    assert [m["nutrient"] for m in r["micronutrients"]] == ["zn", "b"]
    assert r["micronutrients"][0]["kg_total"] == 25.0 and r["micronutrients"][1]["kg_per_ha"] is None
    assert any("Organic carbon" in n for n in r["notes"]) and r["requires_expert_review"]
    legume = fertilizer.recommend("chickpea", low, 1 / fertilizer.HA_PER_ACRE)
    assert legume["nutrients_kg_per_ha"]["n"] == 20.0  # starter N not scaled
    assert fertilizer.recommend("rice", None, 1)["basis"].startswith("general RDF")
