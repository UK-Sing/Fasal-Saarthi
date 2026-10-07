from .knowledge import SOIL_RULES as R
from .schemas import SoilInput


def _level(v, lo, hi):
    return "low" if v < lo else "high" if v > hi else "medium"


def assess(s: SoilInput) -> dict:
    cls = {k: _level(getattr(s, k), *R["nutrients"][k]) for k in R["nutrients"]}
    cls["ph"] = "good" if 6.5 <= s.ph <= 7.5 else "watch" if 6.0 <= s.ph <= 8.5 else "poor"
    cls["ec"] = "good" if s.ec < 1 else "watch" if s.ec <= 2 else "poor"
    w, sc = R["weights"], R["class_score"]
    index = sum(w[k] * sc[cls[k]] for k in w) / sum(w.values())
    micro = [m for m, t in R["micro_deficient_below"].items()
             if getattr(s, m) is not None and getattr(s, m) < t]
    return {"classes": cls, "soil_index": round(index, 1), "micronutrient_deficiencies": micro}
