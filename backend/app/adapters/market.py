"""Mandi prices: data.gov.in Agmarknet resource, with config fallback (demo-safe)."""
import logging
import time
from datetime import datetime, timezone
import httpx
from ..config import settings
from ..knowledge import CROPS

log = logging.getLogger(__name__)
# Verify the resource id on data.gov.in ("Current Daily Price of Various Commodities from Various Markets").
URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
_cache: dict = {}


def get_prices(state: str) -> tuple[dict, dict]:
    base = {c: v["price_inr_per_q"] for c, v in CROPS.items()}
    meta = {"source": "config_defaults (Govt MSP, see crops.yaml)", "as_of": None}
    if not (settings.use_live_data and settings.data_gov_api_key):
        return base, meta
    hit = _cache.get(state)
    if hit and time.time() - hit[0] < hit[3]:
        return dict(hit[1]), dict(hit[2])
    live = {}
    for c, v in CROPS.items():
        try:
            r = httpx.get(URL, timeout=8, params={
                "api-key": settings.data_gov_api_key, "format": "json", "limit": 50,
                "filters[state]": state, "filters[commodity]": v["agmarknet_name"]})
            r.raise_for_status()
            vals = sorted(float(x["modal_price"]) for x in r.json().get("records", []) if x.get("modal_price"))
            if vals:
                live[c] = vals[len(vals) // 2]  # median modal price, INR/quintal
        except Exception as e:  # network/API failure must never break the demo
            log.warning("agmarknet %s failed: %s", c, e)
    if live:
        base.update(live)
        meta = {"source": "data.gov.in/agmarknet (others: config defaults)", "as_of": datetime.now(timezone.utc).isoformat(),
                "live_crops": sorted(live)}
    # success cached 6 h; failure cached 5 min so an outage neither stalls every request nor sticks for hours
    _cache[state] = (time.time(), base, meta, 6 * 3600 if live else 300)
    return dict(base), dict(meta)
