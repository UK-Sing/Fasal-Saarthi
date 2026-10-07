from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel, create_engine
from .config import settings

MODEL_VERSION = "0.2.0"


def _now():
    return datetime.now(timezone.utc)


class Farm(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    profile: dict = Field(default_factory=dict, sa_column=Column(JSON))


class PlanVersion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    farm_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=_now)
    model_version: str = MODEL_VERSION
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))


class Outcome(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    farm_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=_now)
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))


def _db_url(url: str) -> str:
    # A relative SQLite path resolves against backend/, not the shell's cwd, so the DB never "disappears".
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        rel = url.removeprefix("sqlite:///")
        if rel != ":memory:":
            return "sqlite:///" + str((Path(__file__).resolve().parents[1] / rel).resolve())
    return url


@lru_cache
def get_engine():
    url = _db_url(settings.database_url)
    args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=args, pool_pre_ping=not url.startswith("sqlite"))


def init_db():
    SQLModel.metadata.create_all(get_engine())
