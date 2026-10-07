"""Open-Meteo (no API key): 7-day forecast summary + seasonal rainfall climatology for the water constraint.
Only used when USE_LIVE_DATA=true; every failure degrades to None so the demo never breaks."""
import logging
import time
from collections import defaultdict
from datetime import date
import httpx
from ..config import settings
from ..knowledge import EFFECTIVE_RAIN, SEASON_MONTHS

log = logging.getLogger(__name__)
_cache: dict = {}
CLIM_YEARS = 5
FAIL_TTL = 300  # an outage is retried after 5 min instead of stalling every request


def _cached(key, ttl_ok, fetch):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < hit[2]:
        return hit[1]
    val = fetch()
    _cache[key] = (time.time(), val, ttl_ok if val is not None else FAIL_TTL)
    return val


def _warnings(rain7: float, tmax: float, tmin: float) -> list[str]:
    w = []
    if rain7 >= 50:
        w.append(f"Heavy rain forecast ({rain7} mm in 7 days): schedule sowing, spraying and residue work around it.")
    if tmax >= 40:
        w.append(f"Heat forecast (max {tmax} C): watch for heat stress at sowing/flowering.")
    if tmin <= 2:
        w.append(f"Cold forecast (min {tmin} C): frost risk for sensitive crops.")
    return w


def forecast(lat: float | None, lon: float | None) -> dict | None:
    if not settings.use_live_data or lat is None or lon is None:
        return None
    return _cached(("fc", round(lat, 2), round(lon, 2)), 3600, lambda: _forecast(lat, lon))


def _forecast(lat: float, lon: float) -> dict | None:
    try:
        r = httpx.get("https://api.open-meteo.com/v1/forecast", timeout=8, params={
            "latitude": lat, "longitude": lon, "forecast_days": 7, "timezone": "auto",
            "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min"})
        r.raise_for_status()
        d = r.json()["daily"]
        rain7 = round(sum(v or 0 for v in d["precipitation_sum"]), 1)
        tmax = max(v for v in d["temperature_2m_max"] if v is not None)
        tmin = min(v for v in d["temperature_2m_min"] if v is not None)
        return {"rain_mm_7d": rain7, "tmax_c": tmax, "tmin_c": tmin,
                "warnings": _warnings(rain7, tmax, tmin), "source": "open-meteo"}
    except Exception as e:
        log.warning("open-meteo forecast failed: %s", e)
        return None


def seasonal_rain(lat: float | None, lon: float | None) -> dict | None:
    """Mean seasonal rainfall (mm) over the last CLIM_YEARS full years, plus the effective share."""
    if not settings.use_live_data or lat is None or lon is None:
        return None
    return _cached(("clim", round(lat, 2), round(lon, 2)), 30 * 86400, lambda: _seasonal_rain(lat, lon))


def _seasonal_rain(lat: float, lon: float) -> dict | None:
    end_year = date.today().year - 1
    try:
        r = httpx.get("https://archive-api.open-meteo.com/v1/archive", timeout=15, params={
            "latitude": lat, "longitude": lon, "timezone": "auto", "daily": "precipitation_sum",
            "start_date": f"{end_year - CLIM_YEARS + 1}-01-01", "end_date": f"{end_year}-12-31"})
        r.raise_for_status()
        d = r.json()["daily"]
        by_month = defaultdict(float)
        for t, v in zip(d["time"], d["precipitation_sum"]):
            by_month[int(t[5:7])] += v or 0
        mean = {s: round(sum(by_month[m] for m in months) / CLIM_YEARS, 1) for s, months in SEASON_MONTHS.items()}
        return {"mean_rain_mm": mean, "effective_fraction": EFFECTIVE_RAIN,
               "effective_rain_mm": {s: round(v * EFFECTIVE_RAIN, 1) for s, v in mean.items()},
               "years": f"{end_year - CLIM_YEARS + 1}-{end_year}", "source": "open-meteo archive (ERA5)"}
    except Exception as e:
        log.warning("open-meteo archive failed: %s", e)
        return None
