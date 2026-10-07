import pytest
from fastapi.testclient import TestClient
from app.config import settings
from app.main import app

SOIL = dict(ph=8.1, ec=0.6, oc=0.42, n=250, p=14, k=150, zn=0.5)
FARM = dict(name="Demo farm (SIMULATED)", state="Haryana", district="Karnal", lat=29.69, lon=76.99,
            area_acres=3, previous_crop="rice", next_season="rabi", soil=SOIL)


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def fid(c):
    return c.post("/farm/profile", json=FARM).json()["farm_id"]


def _first(plans, key="B_balanced"):
    return next(p for p in plans if p["plan"] == key)["sequence"][0]["crop"]


def test_health(c):
    h = c.get("/health").json()
    assert h["ok"] and not h["live_data"] and not h["auth_required"] and "wheat" in h["crops"]


def test_demo_story_end_to_end(c, fid):
    r = c.post("/plan/generate", json={"farm_id": fid})
    assert r.status_code == 200
    base = r.json()
    assert len(base["plans"]) == 3 and base["plan_version_id"]
    assert base["weather"] is None and base["warnings"] == [] and base["price_meta"]["as_of"] is None
    for p in base["plans"]:
        assert p["explanation"]["source"] == "template" and p["explanation"]["text"]
        assert p["next_season_fertilizer"]["crop"] == p["sequence"][0]["crop"]
    crash = c.post("/plan/generate", json={"farm_id": fid, "price_overrides": {"mustard": 4300}}).json()
    assert crash["prices"]["mustard"] == 4300 and crash["price_meta"]["overridden"] == ["mustard"]
    assert [_first(base["plans"], k) for k in ("A_max_profit", "B_balanced")] != \
           [_first(crash["plans"], k) for k in ("A_max_profit", "B_balanced")]
    opts = c.post("/residue/decision", json={"crop": "rice", "area_acres": 3, "equipment_access": True,
                                             "biomass_buyer_km": 12}).json()["options"]
    assert opts[-1]["option"] == "burn"
    out = c.post("/season/outcome", json=dict(farm_id=fid, season="kharif", crop="rice", residue_action="burn")).json()
    assert out["soil_index"] == round(out["soil_index_before"] - 3, 1) and out["next_season"] == "rabi"
    after = c.post("/plan/generate", json={"farm_id": fid}).json()
    assert after["soil_index_start"] == out["soil_index"]
    assert _first(after["plans"]) != _first(base["plans"])
    mem = c.get("/farm/memory", params={"farm_id": fid}).json()
    assert len(mem["plan_versions"]) == 3 and len(mem["outcomes"]) == 1
    assert mem["outcomes"][0]["residue_action"] == "burn" and mem["plan_versions"][0]["summary"][0]["plan"]


def test_profile_update_and_soil(c, fid):
    c.post("/season/outcome", json=dict(farm_id=fid, season="rabi", crop="wheat", residue_action="burn"))
    r = c.post("/farm/profile", json={"farm_id": fid, "name": "renamed", "area_acres": 5})
    prof = r.json()["profile"]
    assert r.json()["farm_id"] == fid and prof["area_acres"] == 5 and prof["name"] == "renamed"
    assert prof["soil_index"] == 44.1 and prof["next_season"] == "zaid" and prof["previous_crop"] == "wheat"
    assert prof["soil"]["n"] == SOIL["n"] and prof["district"] == "Karnal"
    resent = c.post("/farm/profile", json={**FARM, "farm_id": fid, "area_acres": 5}).json()["profile"]
    assert resent["soil_index"] == 44.1  # same soil test re-sent: modelled history kept
    new = c.post("/farm/profile", json={**FARM, "farm_id": fid, "soil": {**SOIL, "oc": 0.9}}).json()["profile"]
    assert new["soil_index"] > 47.1  # new soil test: index recomputed
    assert c.post("/farm/profile", json={**FARM, "farm_id": "does-not-exist"}).status_code == 404
    a = c.post("/soil/assessment", json={"soil": {**SOIL, "oc": 0.9}, "farm_id": fid}).json()
    assert a["classes"]["oc"] == "high" and "zn" in a["micronutrient_deficiencies"]
    assert c.get("/farm/memory", params={"farm_id": fid}).json()["profile"]["soil_index"] == a["soil_index"]


def test_compare_and_fertilizer(c, fid):
    res = c.post("/plan/compare", json={"farm_id": fid, "sequences": [["wheat", "maize", "rice"],
                                                                     ["chickpea", None, "moong"]]}).json()["results"]
    assert res[0]["issues"] and res[1]["issues"] == []
    f = c.post("/fertilizer/recommendation", json={"crop": "wheat", "farm_id": fid}).json()
    assert f["area_acres"] == 3 and f["nutrients_kg_per_ha"]["n"] == 150.0  # N 250 -> low -> 1.25 x 120
    assert f["micronutrients"][0]["nutrient"] == "zn"
    g = c.post("/fertilizer/recommendation", json={"crop": "mustard"}).json()
    assert g["area_acres"] == 1 and g["nutrients_kg_per_ha"] == {"n": 80, "p2o5": 40, "k2o": 40}


@pytest.mark.parametrize("path,body", [
    ("/farm/profile", {**FARM, "previous_crop": "banana"}),
    ("/farm/profile", {**FARM, "area_acres": 0}),
    ("/farm/profile", {**FARM, "soil": {**SOIL, "ph": 20}}),
    ("/farm/profile", {**FARM, "excluded_crops": ["potato"]}),
    ("/residue/decision", {"crop": "banana"}),
    ("/fertilizer/recommendation", {"crop": "banana"}),
])
def test_validation_422(c, path, body):
    assert c.post(path, json=body).status_code == 422


def test_validation_with_farm(c, fid):
    assert c.post("/plan/generate", json={"farm_id": fid, "price_overrides": {"banana": 1}}).status_code == 422
    assert c.post("/plan/generate", json={"farm_id": fid, "price_overrides": {"wheat": 0}}).status_code == 422
    assert c.post("/plan/generate", json={"farm_id": fid, "horizon": 12}).status_code == 422
    assert c.post("/plan/compare", json={"farm_id": fid, "sequences": [["banana"]]}).status_code == 422
    assert c.post("/season/outcome", json={"farm_id": fid, "season": "rabi", "crop": "wheat",
                                           "residue_action": "dump"}).status_code == 422
    assert c.post("/plan/generate", json={"farm_id": "does-not-exist"}).status_code == 404
    assert c.get("/farm/memory", params={"farm_id": "does-not-exist"}).status_code == 404


def test_api_key(c, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "s3cret")
    assert c.get("/health").status_code == 200
    assert c.post("/residue/decision", json={"crop": "rice"}).status_code == 401
    assert c.post("/residue/decision", json={"crop": "rice"}, headers={"X-API-Key": "nope"}).status_code == 401
    assert c.post("/residue/decision", json={"crop": "rice"}, headers={"X-API-Key": "s3cret"}).status_code == 200
    pre = c.options("/plan/generate", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST",
                                                "Access-Control-Request-Headers": "x-api-key,content-type"})
    assert pre.status_code == 200
