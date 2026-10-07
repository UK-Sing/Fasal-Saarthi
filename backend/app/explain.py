"""Explanations. The LLM only rephrases facts produced by the optimizer/rules."""
import httpx
from .config import settings

LABEL = {"A_max_profit": "Maximum near-term return", "B_balanced": "Balanced",
         "C_soil_recovery": "Soil recovery"}


def template(plan: dict, farm) -> str:
    seq = ", ".join(f"{s['season']}: {s['crop'] or 'fallow'}" for s in plan["sequence"])
    note = " (soil target had to be relaxed)" if plan["floor_relaxed"] else ""
    return (f"{LABEL[plan['plan']]} plan: {seq}. Expected profit about Rs {plan['total_profit_inr']:,} "
            f"over {len(plan['sequence'])} seasons. Soil index moves {plan['soil_trajectory'][0]} -> "
            f"{plan['soil_final']}{note}. Prices and yields are estimates; confirm with your local agronomist.")


def explain(plan: dict, farm) -> dict:
    text = template(plan, farm)
    if settings.llm_base_url and settings.llm_model:
        try:
            r = httpx.post(settings.llm_base_url.rstrip("/") + "/chat/completions", timeout=20,
                headers={"Authorization": f"Bearer {settings.llm_api_key or 'none'}"},
                json={"model": settings.llm_model, "temperature": 0.2, "messages": [
                    {"role": "system", "content": f"Rewrite the farm plan summary in simple language code '{farm.language}' "
                     "for a farmer. Use ONLY the facts and numbers given. Add no crops, doses or advice."},
                    {"role": "user", "content": text}]})
            return {"text": r.json()["choices"][0]["message"]["content"].strip(), "source": "llm", "template": text}
        except Exception:
            pass
    return {"text": text, "source": "template", "template": text}
