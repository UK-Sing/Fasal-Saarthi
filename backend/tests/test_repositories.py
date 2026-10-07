import pytest
from sqlmodel import SQLModel, create_engine
from app.repositories.base import NotFound
from app.repositories.memory import InMemoryRepository
from app.repositories.sql import SQLRepository

PROFILE = {"name": "Contract farm", "state": "Haryana", "area_acres": 3, "soil_index": 55.0}


def _sql_repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/repo_test.db")
    SQLModel.metadata.create_all(engine)
    return SQLRepository(engine)


@pytest.fixture(params=["memory", "sql"])
def repo(request, tmp_path):
    yield InMemoryRepository() if request.param == "memory" else _sql_repo(tmp_path)


def test_contract(repo):
    assert repo.get_farm("missing") is None
    with pytest.raises(NotFound):
        repo.apply("missing", lambda p: (p, None))
    with pytest.raises(NotFound):
        repo.save_plan("missing", {"x": 1}, "0.0.0")

    fid = repo.create_farm(PROFILE)
    assert isinstance(fid, str)
    assert repo.get_farm(fid)["name"] == "Contract farm"

    # apply merges and writes the outcome atomically
    def fn(current):
        new = {**current, "area_acres": 5}
        return new, {"season": "rabi", "note": "first"}

    new_profile = repo.apply(fid, fn)
    assert new_profile["area_acres"] == 5 and repo.get_farm(fid)["area_acres"] == 5
    outs = repo.list_outcomes(fid)
    assert len(outs) == 1 and outs[0]["payload"]["note"] == "first" and isinstance(outs[0]["id"], str)

    pid1 = repo.save_plan(fid, {"n": 1}, "0.1.0")
    pid2 = repo.save_plan(fid, {"n": 2}, "0.1.0")
    assert isinstance(pid1, str) and isinstance(pid2, str) and pid1 != pid2
    repo.apply(fid, lambda p: (p, {"season": "kharif", "note": "second"}))

    plans = repo.list_plans(fid)
    assert [p["payload"]["n"] for p in plans] == [1, 2]
    assert [p["model_version"] for p in plans] == ["0.1.0", "0.1.0"]
    outs = repo.list_outcomes(fid)
    assert [o["payload"]["note"] for o in outs] == ["first", "second"]
