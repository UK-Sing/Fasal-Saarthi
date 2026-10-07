"""Rule-based nutrient recommendation: RDF x soil-test class factor -> fertilizer products.
Doses come only from data/fertilizer.yaml (placeholders pending validation), never from an LLM."""
from .knowledge import FERTILIZER as F
from .schemas import SoilInput
from . import soil as soil_mod

HA_PER_ACRE = 0.404686


def recommend(crop: str, soil: SoilInput | None, area_acres: float) -> dict:
    n, p, k = F["rdf_kg_per_ha"][crop]
    notes, micro, basis = [], [], "general RDF (no soil test supplied)"
    if soil:
        a = soil_mod.assess(soil)
        cls, fac = a["classes"], F["soil_class_factor"]
        if crop not in F["no_n_adjust"]:
            n *= fac[cls["n"]]
        p *= fac[cls["p"]]
        k *= fac[cls["k"]]
        basis = (f"RDF adjusted by soil-test class: N {cls['n']}, P {cls['p']}, K {cls['k']}"
                 + (" (N is a legume starter dose, not adjusted)" if crop in F["no_n_adjust"] else ""))
        for m in a["micronutrient_deficiencies"]:
            if m in F["micronutrients"]:
                r = F["micronutrients"][m]
                micro.append({"nutrient": m, "product": r["product"], "kg_per_ha": r["kg_per_ha"],
                              "kg_total": round(r["kg_per_ha"] * area_acres * HA_PER_ACRE, 1)})
            elif m in F["flag_only"]:
                micro.append({"nutrient": m, "product": None, "kg_per_ha": None, "kg_total": None,
                              "note": "deficient below SHC threshold; dose to be set by agronomist"})
        if cls["oc"] == "low":
            notes.append("Organic carbon is low: add organic matter (FYM/compost, residue retention).")
        if soil.ph > 8.5:
            notes.append("pH above 8.5 (alkaline/sodic risk): get a gypsum-requirement test before amending.")
        elif soil.ph < 5.5:
            notes.append("pH below 5.5 (acidic): get a lime-requirement test before amending.")
        if soil.ec > 2:
            notes.append("EC above 2 dS/m (saline): crop choice and leaching need expert advice.")
    need_ha = {"n": n, "p2o5": p, "k2o": k}
    pr = F["products"]
    # DAP covers P2O5 first; its N is credited; urea tops up N; MOP covers K2O.
    dap = need_ha["p2o5"] / pr["dap"]["p2o5"]
    urea = max(0.0, need_ha["n"] - dap * pr["dap"]["n"]) / pr["urea"]["n"]
    mop = need_ha["k2o"] / pr["mop"]["k2o"]
    ha = area_acres * HA_PER_ACRE
    products, cost = [], 0.0
    for key, kg_ha in (("urea", urea), ("dap", dap), ("mop", mop)):
        total = kg_ha * ha
        bags = total / pr[key]["bag_kg"]
        c = bags * pr[key]["price_inr_per_bag"]
        cost += c
        products.append({"product": key, "label": pr[key]["label"], "kg_per_acre": round(kg_ha * HA_PER_ACRE, 1),
                         "kg_total": round(total, 1), "bags": round(bags, 1), "bag_kg": pr[key]["bag_kg"],
                         "indicative_cost_inr": round(c)})
    return {
        "crop": crop, "area_acres": area_acres, "basis": basis,
        "nutrients_kg_per_ha": {k_: round(v, 1) for k_, v in need_ha.items()},
        "nutrients_kg_per_acre": {k_: round(v * HA_PER_ACRE, 1) for k_, v in need_ha.items()},
        "products": products, "micronutrients": micro, "notes": notes,
        "indicative_cost_inr": round(cost),
        "requires_expert_review": True,
        "data_note": "Doses are general placeholder RDFs pending state package-of-practices / agronomist "
                     "validation. Split N application and timing per local recommendation.",
    }
