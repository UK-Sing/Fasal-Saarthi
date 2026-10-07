import os
from collections.abc import Callable
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import firestore
from .base import NotFound


def _now():
    return datetime.now(timezone.utc)


class FirestoreRepository:
    """Layout: farms/{id} = {profile, created_at, updated_at};
    farms/{id}/plans/{auto} = {created_at, model_version, payload};
    farms/{id}/outcomes/{auto} = {created_at, payload}."""

    def __init__(self, project_id: str = "", credentials_path: str = ""):
        if credentials_path:
            os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", credentials_path)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(options={"projectId": project_id} if project_id else None)
        self.db = firestore.client()
        self.farms = self.db.collection("farms")

    def _ref(self, farm_id: str):
        if not farm_id or "/" in farm_id:  # Firestore rejects such paths with ValueError; treat as unknown farm
            raise NotFound(farm_id)
        return self.farms.document(farm_id)

    def create_farm(self, profile: dict) -> str:
        ref = self.farms.document()
        ref.set({"profile": profile, "created_at": _now(), "updated_at": _now()})
        return ref.id

    def get_farm(self, farm_id: str) -> dict | None:
        try:
            snap = self._ref(farm_id).get()
        except NotFound:
            return None
        return dict(snap.get("profile")) if snap.exists else None

    def apply(self, farm_id: str, fn: Callable[[dict], tuple[dict, dict | None]]) -> dict:
        farm_ref = self._ref(farm_id)
        outcome_ref = farm_ref.collection("outcomes").document()

        @firestore.transactional
        def _txn(transaction):
            snap = farm_ref.get(transaction=transaction)
            if not snap.exists:
                raise NotFound(farm_id)
            new_profile, outcome = fn(dict(snap.get("profile")))
            transaction.update(farm_ref, {"profile": new_profile, "updated_at": _now()})
            if outcome is not None:
                transaction.set(outcome_ref, {"created_at": _now(), "payload": outcome})
            return new_profile

        return dict(_txn(self.db.transaction()))

    def save_plan(self, farm_id: str, payload: dict, model_version: str) -> str:
        farm_ref = self._ref(farm_id)
        if not farm_ref.get().exists:
            raise NotFound(farm_id)
        ref = farm_ref.collection("plans").document()
        ref.set({"created_at": _now(), "model_version": model_version, "payload": payload})
        return ref.id

    def list_plans(self, farm_id: str) -> list[dict]:
        docs = self.farms.document(farm_id).collection("plans").order_by("created_at").stream()
        return [{"id": d.id, "created_at": d.get("created_at"), "model_version": d.get("model_version"),
                 "payload": d.get("payload")} for d in docs]

    def list_outcomes(self, farm_id: str) -> list[dict]:
        docs = self.farms.document(farm_id).collection("outcomes").order_by("created_at").stream()
        return [{"id": d.id, "created_at": d.get("created_at"), "payload": d.get("payload")} for d in docs]

    def delete_farm(self, farm_id: str):
        """Test-teardown helper: removes subcollection docs, then the farm."""
        farm_ref = self.farms.document(farm_id)
        for sub in ("plans", "outcomes"):
            for d in farm_ref.collection(sub).stream():
                d.reference.delete()
        farm_ref.delete()
