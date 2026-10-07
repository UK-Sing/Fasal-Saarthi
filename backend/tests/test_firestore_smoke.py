import os
import pytest
from app.config import Settings
from app.repositories.base import NotFound
from app.repositories.firestore import FirestoreRepository

pytestmark = pytest.mark.skipif(not os.environ.get("FIREBASE_SMOKE"),
                                reason="set FIREBASE_SMOKE=1 to run against the real Firestore project")

PROFILE = {"name": "SMOKE TEST", "state": "Haryana", "area_acres": 1, "soil_index": 55.0}


@pytest.fixture
def repo():
    yield FirestoreRepository(project_id=Settings().firebase_project_id,
                              credentials_path=Settings().firebase_credentials)


@pytest.fixture
def fid(repo):
    farm_id = repo.create_farm(PROFILE)
    yield farm_id
    repo.delete_farm(farm_id)


def test_smoke_contract(repo, fid):
    assert isinstance(fid, str)
    assert repo.get_farm(fid)["name"] == "SMOKE TEST"
    assert repo.get_farm("does-not-exist") is None
    with pytest.raises(NotFound):
        repo.apply("does-not-exist", lambda p: (p, None))
    with pytest.raises(NotFound):
        repo.save_plan("does-not-exist", {"x": 1}, "0.0.0")

    new_profile = repo.apply(fid, lambda p: ({**p, "area_acres": 5}, {"season": "rabi", "note": "first"}))
    assert new_profile["area_acres"] == 5 and repo.get_farm(fid)["area_acres"] == 5

    pid1 = repo.save_plan(fid, {"n": 1}, "0.1.0")
    pid2 = repo.save_plan(fid, {"n": 2}, "0.1.0")
    assert isinstance(pid1, str) and pid1 != pid2
    repo.apply(fid, lambda p: (p, {"season": "kharif", "note": "second"}))

    assert [p["payload"]["n"] for p in repo.list_plans(fid)] == [1, 2]
    assert [o["payload"]["note"] for o in repo.list_outcomes(fid)] == ["first", "second"]
