from collections.abc import Callable
from typing import Protocol


class NotFound(Exception):
    """Raised when a farm id does not exist."""


class Repository(Protocol):
    def create_farm(self, profile: dict) -> str: ...
    def get_farm(self, farm_id: str) -> dict | None: ...  # returns profile dict

    def apply(self, farm_id: str, fn: Callable[[dict], tuple[dict, dict | None]]) -> dict:
        """fn(current_profile) -> (new_profile, outcome_payload | None).
        Atomically writes the farm (+ an outcome doc if payload is not None).
        Returns new_profile. Raises NotFound."""
        ...

    def save_plan(self, farm_id: str, payload: dict, model_version: str) -> str:
        """Raises NotFound if the farm is missing."""
        ...

    # oldest first: [{id: str, created_at: datetime, model_version: str, payload: dict}]
    def list_plans(self, farm_id: str) -> list[dict]: ...
    # oldest first: [{id: str, created_at: datetime, payload: dict}]
    def list_outcomes(self, farm_id: str) -> list[dict]: ...
