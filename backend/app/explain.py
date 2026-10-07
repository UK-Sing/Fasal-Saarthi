"""Explanations. The LLM only rephrases facts produced by the optimizer/rules."""
import logging
import httpx
from .config import settings

log = logging.getLogger(__name__)
LABEL = {"A_max_profit": "Maximum near-term return", "B_balanced": "Balanced",
         "C_soil_recovery": "Soil recovery"}


def template(plan: dict, farm) -> str:
    seq = ", ".join(f"{s['season']}: {s['crop'] or 'fallow'}" for s in plan["sequence"])
    note = " (soil target could not be met; best achievable plan shown)" if plan["floor_relaxed"] else ""
    return (f"{LABEL[plan['plan']]} plan: {seq}. Expected profit about Rs {plan['total_profit_inr']:,} "
            f"over {len(plan['sequence'])} seasons. Soil index moves {plan['soil_trajectory'][0]} -> "
            f"{plan['soil_final']}{note}. Total crop water need {plan['total_water_mm']:,.0f} mm; "
            f"average crop risk {plan['avg_risk']} (0-1 scale). "
            "Prices and yields are estimates; confirm with your local agronomist.")


def explain(plan: dict, farm) -> dict:
    text = template(plan, farm)
    if settings.llm_base_url and settings.llm_model:
        try:
            r = httpx.post(settings.llm_base_url.rstrip("/") + "/chat/completions", timeout=10,
                headers={"Authorization": f"Bearer {settings.llm_api_key or 'none'}"},
                json={"model": settings.llm_model, "temperature": 0.2, "messages": [
                    {"role": "system", "content": f"Rewrite the farm plan summary in simple language code '{farm.language}' "
                     "for a farmer. Use ONLY the facts and numbers given. Add no crops, doses or advice."},
                    {"role": "user", "content": text}]})
            r.raise_for_status()
            return {"text": r.json()["choices"][0]["message"]["content"].strip(), "source": "llm", "template": text}
        except Exception as e:
            log.warning("LLM explanation failed, using template: %s", e)
    return {"text": text, "source": "template", "template": text}
