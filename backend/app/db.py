from datetime import datetime, timezone
from sqlalchemy import JSON, Column
from sqlmodel import Field, Session, SQLModel, create_engine
from .config import settings


def _now():
    return datetime.now(timezone.utc)


class Farm(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    profile: dict = Field(default_factory=dict, sa_column=Column(JSON))


class PlanVersion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    farm_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=_now)
    model_version: str = "0.1.0"
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))


class Outcome(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    farm_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=_now)
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))


_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_args)


def init_db():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as s:
        yield s
