from collections.abc import Callable
from sqlmodel import Session, select
from ..db import Farm, Outcome, PlanVersion
from .base import NotFound


class SQLRepository:
    def __init__(self, engine):
        self.engine = engine

    def _farm(self, session: Session, farm_id: str) -> Farm:
        try:
            key = int(farm_id)
        except (TypeError, ValueError):
            raise NotFound(farm_id)
        row = session.get(Farm, key)
        if not row:
            raise NotFound(farm_id)
        return row

    def create_farm(self, profile: dict) -> str:
        with Session(self.engine) as s:
            row = Farm(profile=profile)
            s.add(row)
            s.commit()
            s.refresh(row)
            return str(row.id)

    def get_farm(self, farm_id: str) -> dict | None:
        with Session(self.engine) as s:
            try:
                return dict(self._farm(s, farm_id).profile)
            except NotFound:
                return None

    def apply(self, farm_id: str, fn: Callable[[dict], tuple[dict, dict | None]]) -> dict:
        with Session(self.engine) as s:
            row = self._farm(s, farm_id)
            new_profile, outcome = fn(dict(row.profile))
            row.profile = new_profile
            s.add(row)
            if outcome is not None:
                s.add(Outcome(farm_id=row.id, payload=outcome))
            s.commit()
            return dict(new_profile)

    def save_plan(self, farm_id: str, payload: dict, model_version: str) -> str:
        with Session(self.engine) as s:
            row = self._farm(s, farm_id)
            pv = PlanVersion(farm_id=row.id, payload=payload, model_version=model_version)
            s.add(pv)
            s.commit()
            s.refresh(pv)
            return str(pv.id)

    def list_plans(self, farm_id: str) -> list[dict]:
        try:
            key = int(farm_id)
        except (TypeError, ValueError):
            return []
        with Session(self.engine) as s:
            rows = s.exec(select(PlanVersion).where(PlanVersion.farm_id == key).order_by(PlanVersion.id)).all()
            return [{"id": str(p.id), "created_at": p.created_at, "model_version": p.model_version,
                     "payload": p.payload} for p in rows]

    def list_outcomes(self, farm_id: str) -> list[dict]:
        try:
            key = int(farm_id)
        except (TypeError, ValueError):
            return []
        with Session(self.engine) as s:
            rows = s.exec(select(Outcome).where(Outcome.farm_id == key).order_by(Outcome.id)).all()
            return [{"id": str(o.id), "created_at": o.created_at, "payload": o.payload} for o in rows]
