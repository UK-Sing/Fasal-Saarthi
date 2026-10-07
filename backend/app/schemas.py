from typing import Literal
from pydantic import BaseModel, Field

Season = Literal["kharif", "rabi", "zaid"]


class SoilInput(BaseModel):
    ph: float
    ec: float
    oc: float
    n: float
    p: float
    k: float
    s: float | None = None
    zn: float | None = None
    fe: float | None = None
    cu: float | None = None
    mn: float | None = None
    b: float | None = None


class FarmProfile(BaseModel):
    name: str
    state: str = "Haryana"
    district: str = ""
    lat: float | None = None
    lon: float | None = None
    area_acres: float = Field(gt=0)
    water_mm_per_season: float = 1300
    budget_inr_per_season: float = 100000
    previous_crop: str | None = None
    next_season: Season = "rabi"
    soil_index: float = 55.0
    soil: SoilInput | None = None
    excluded_crops: list[str] = []
    language: str = "en"


class FarmUpsert(FarmProfile):
    farm_id: int | None = None


class SoilAssessRequest(BaseModel):
    soil: SoilInput
    farm_id: int | None = None


class PlanRequest(BaseModel):
    farm_id: int
    horizon: int = Field(6, ge=2, le=9)
    price_overrides: dict[str, float] = {}


class CompareRequest(BaseModel):
    farm_id: int
    sequences: list[list[str | None]]
    price_overrides: dict[str, float] = {}


class ResidueRequest(BaseModel):
    crop: str
    area_acres: float = 1
    equipment_access: bool = False
    biomass_buyer_km: float | None = None


class OutcomeRequest(BaseModel):
    farm_id: int
    season: Season
    crop: str
    yield_q_per_acre: float | None = None
    net_income_inr: float | None = None
    residue_action: str | None = None
    soil: SoilInput | None = None
