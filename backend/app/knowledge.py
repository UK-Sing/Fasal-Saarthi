from pathlib import Path
import yaml

DATA = Path(__file__).parent / "data"
SEASONS = ["kharif", "rabi", "zaid"]


def _load(name):
    return yaml.safe_load((DATA / name).read_text())


_c = _load("crops.yaml")
CROPS, FAMILIES, FALLOW_GAIN = _c["crops"], _c["families"], _c["fallow_soil_gain"]
_r = _load("residue.yaml")
RESIDUE, SOIL_VALUE = _r["options"], _r["soil_value_inr_per_point"]
SOIL_RULES = _load("soil_rules.yaml")


def next_season(season: str) -> str:
    return SEASONS[(SEASONS.index(season) + 1) % 3]
