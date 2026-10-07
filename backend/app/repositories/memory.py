import itertools
from collections.abc import Callable
from datetime import datetime, timezone
from .base import NotFound


def _now():
    return datetime.now(timezone.utc)


class InMemoryRepository:
    def __init__(self):
        self._farms: dict[str, dict] = {}
        self._plans: dict[str, list[dict]] = {}
        self._outcomes: dict[str, list[dict]] = {}
        self._ids = itertools.count(1)

    def create_farm(self, profile: dict) -> str:
        farm_id = str(next(self._ids))
        self._farms[farm_id] = dict(profile)
        self._plans[farm_id] = []
        self._outcomes[farm_id] = []
        return farm_id

    def get_farm(self, farm_id: str) -> dict | None:
        p = self._farms.get(str(farm_id))
        return dict(p) if p is not None else None

    def apply(self, farm_id: str, fn: Callable[[dict], tuple[dict, dict | None]]) -> dict:
        farm_id = str(farm_id)
        if farm_id not in self._farms:
            raise NotFound(farm_id)
        new_profile, outcome = fn(dict(self._farms[farm_id]))
        self._farms[farm_id] = new_profile
        if outcome is not None:
            self._outcomes[farm_id].append({"id": str(next(self._ids)), "created_at": _now(), "payload": outcome})
        return dict(new_profile)

    def save_plan(self, farm_id: str, payload: dict, model_version: str) -> str:
        farm_id = str(farm_id)
        if farm_id not in self._farms:
            raise NotFound(farm_id)
        plan_id = str(next(self._ids))
        self._plans[farm_id].append({"id": plan_id, "created_at": _now(), "model_version": model_version,
                                     "payload": payload})
        return plan_id

    def list_plans(self, farm_id: str) -> list[dict]:
        return [dict(p) for p in self._plans.get(str(farm_id), [])]

    def list_outcomes(self, farm_id: str) -> list[dict]:
        return [dict(o) for o in self._outcomes.get(str(farm_id), [])]
