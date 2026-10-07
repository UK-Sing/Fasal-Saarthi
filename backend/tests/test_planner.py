from app import planner, residue, soil
from app.schemas import FarmProfile, SoilInput

SOIL = SoilInput(ph=8.1, ec=0.6, oc=0.42, n=250, p=14, k=150)


def farm(**kw):
    base = dict(name="demo", area_acres=3, previous_crop="rice", next_season="rabi",
                soil_index=soil.assess(SOIL)["soil_index"])
    return FarmProfile(**{**base, **kw})


def test_three_plans_respect_floors():
    f = farm()
    plans = {p["plan"]: p for p in planner.generate_plans(f, 6, {})}
    assert set(plans) == {"A_max_profit", "B_balanced", "C_soil_recovery"}
    assert plans["B_balanced"]["soil_final"] >= 50 or plans["B_balanced"]["floor_relaxed"]
    assert plans["A_max_profit"]["total_profit_inr"] >= plans["C_soil_recovery"]["total_profit_inr"]


def test_no_back_to_back_same_crop_or_wrong_season():
    for p in planner.generate_plans(farm(), 6, {}):
        picks = [s["crop"] for s in p["sequence"]]
        assert all(a is None or a != b for a, b in zip(picks, picks[1:]))


def test_soil_and_residue():
    assert 0 < soil.assess(SOIL)["soil_index"] < 100
    opts = residue.decide("rice", 2, True, 10)
    assert opts[0]["option"] != "burn" and opts[-1]["option"] == "burn"
