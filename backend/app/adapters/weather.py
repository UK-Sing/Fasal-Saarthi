"""Open-Meteo 7-day forecast summary (no API key). TODO: feed into water constraints."""
import httpx
from ..config import settings


def forecast(lat: float | None, lon: float | None) -> dict | None:
    if not settings.use_live_data or lat is None or lon is None:
        return None
    try:
        r = httpx.get("https://api.open-meteo.com/v1/forecast", timeout=8, params={
            "latitude": lat, "longitude": lon, "forecast_days": 7, "timezone": "auto",
            "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min"})
        d = r.json()["daily"]
        return {"rain_mm_7d": round(sum(v or 0 for v in d["precipitation_sum"]), 1),
                "tmax_c": max(d["temperature_2m_max"]), "tmin_c": min(d["temperature_2m_min"]),
                "source": "open-meteo"}
    except Exception:
        return None
