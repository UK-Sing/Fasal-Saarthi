from typing import Literal
from pydantic import BaseModel, Field, field_validator
from .knowledge import CROPS, RESIDUE

Season = Literal["kharif", "rabi", "zaid"]


def _crop(c: str | None) -> str | None:
    if c is not None and c not in CROPS:
        raise ValueError(f"unknown crop '{c}'; use one of {list(CROPS)}")
    return c


def _prices(p: dict[str, float]) -> dict[str, float]:
    for c, v in p.items():
        _crop(c)
        if v <= 0:
            raise ValueError(f"price for '{c}' must be > 0")
    return p


class SoilInput(BaseModel):
    ph: float = Field(ge=0, le=14)
    ec: float = Field(ge=0, description="dS/m")
    oc: float = Field(ge=0, description="organic carbon, %")
    n: float = Field(ge=0, description="available N, kg/ha")
    p: float = Field(ge=0, description="available P, kg/ha")
    k: float = Field(ge=0, description="available K, kg/ha")
    s: float | None = Field(None, ge=0, description="ppm")
    zn: float | None = Field(None, ge=0, description="ppm")
    fe: float | None = Field(None, ge=0, description="ppm")
    cu: float | None = Field(None, ge=0, description="ppm")
    mn: float | None = Field(None, ge=0, description="ppm")
    b: float | None = Field(None, ge=0, description="ppm")


class FarmProfile(BaseModel):
    name: str
    state: str = "Haryana"
    district: str = ""
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    area_acres: float = Field(gt=0)
    water_mm_per_season: float = Field(1300, ge=0, description="irrigation water available per season, mm")
    budget_inr_per_season: float = Field(100000, ge=0)
    previous_crop: str | None = None
    next_season: Season = "rabi"
    soil_index: float = Field(55.0, ge=0, le=100)
    soil: SoilInput | None = None
    excluded_crops: list[str] = []
    language: str = "en"

    _v_prev = field_validator("previous_crop")(_crop)

    @field_validator("excluded_crops")
    @classmethod
    def _v_excl(cls, v):
        return [_crop(c) for c in v]


class FarmUpsert(FarmProfile):
    farm_id: str | None = None


class SoilAssessRequest(BaseModel):
    soil: SoilInput
    farm_id: str | None = None


class PlanRequest(BaseModel):
    farm_id: str
    horizon: int = Field(6, ge=2, le=9)
    price_overrides: dict[str, float] = {}

    _v_prices = field_validator("price_overrides")(_prices)


class CompareRequest(BaseModel):
    farm_id: str
    sequences: list[list[str | None]] = Field(min_length=1)
    price_overrides: dict[str, float] = {}

    _v_prices = field_validator("price_overrides")(_prices)

    @field_validator("sequences")
    @classmethod
    def _v_seq(cls, v):
        for seq in v:
            if not 1 <= len(seq) <= 9:
                raise ValueError("each sequence must have 1-9 seasons")
            for c in seq:
                _crop(c)
        return v


class ResidueRequest(BaseModel):
    crop: str
    area_acres: float = Field(1, gt=0)
    equipment_access: bool = False
    biomass_buyer_km: float | None = Field(None, ge=0)

    _v_crop = field_validator("crop")(_crop)


class FertilizerRequest(BaseModel):
    crop: str
    farm_id: str | None = Field(None, description="use this farm's soil test and area")
    soil: SoilInput | None = Field(None, description="overrides the farm's stored soil test")
    area_acres: float | None = Field(None, gt=0, description="defaults to the farm's area, else 1")

    _v_crop = field_validator("crop")(_crop)


class OutcomeRequest(BaseModel):
    farm_id: str
    season: Season
    crop: str
    yield_q_per_acre: float | None = Field(None, ge=0)
    net_income_inr: float | None = None
    residue_action: str | None = None
    soil: SoilInput | None = None

    _v_crop = field_validator("crop")(_crop)

    @field_validator("residue_action")
    @classmethod
    def _v_res(cls, v):
        if v is not None and v not in RESIDUE:
            raise ValueError(f"residue_action must be one of {list(RESIDUE)}")
        return v
