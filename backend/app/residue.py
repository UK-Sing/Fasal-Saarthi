from .knowledge import CROPS, RESIDUE, SOIL_VALUE


def decide(crop: str, area: float, equipment: bool, buyer_km: float | None) -> list[dict]:
    kind, rows = CROPS[crop]["residue"], []
    for oid, o in RESIDUE.items():
        if kind not in o["applies_to"]:
            continue
        cost, why = o["cost_inr_per_acre"], None
        if o.get("needs_equipment") and not equipment:
            why = "needs equipment access"
        if oid == "biomass_sale":
            if buyer_km is None:
                why = "no buyer reachable"
            else:
                cost += o["transport_inr_per_acre_per_km"] * buyer_km
        net = o["value_inr_per_acre"] - cost - o.get("penalty_risk_inr_per_acre", 0)
        rows.append({"option": oid, "label": o["label"], "feasible": why is None,
                     "blocked_reason": why, "net_inr": round(net * area),
                     "soil_delta": o["soil_delta"], "note": o["note"],
                     "score": net + SOIL_VALUE * o["soil_delta"]})
    rows.sort(key=lambda r: (r["feasible"], r["score"]), reverse=True)
    for r in rows:
        r.pop("score")
    return rows
