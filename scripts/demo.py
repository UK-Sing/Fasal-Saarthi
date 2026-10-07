"""Rehearse the 3-minute demo against a running API:  uv run python ../scripts/demo.py [BASE_URL]
Set API_KEY in the environment if the server requires it."""
import os, sys, httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
c = httpx.Client(base_url=BASE, timeout=60, headers={"X-API-Key": os.environ.get("API_KEY", "")})
SOIL = dict(ph=8.1, ec=0.6, oc=0.42, n=250, p=14, k=150, zn=0.5)


def ok(r):
    r.raise_for_status()
    return r.json()


def show(title, res):
    print(f"\n== {title}")
    for p in res["plans"]:
        seq = " > ".join(s["crop"] or "fallow" for s in p["sequence"])
        print(f"{p['plan']:16} Rs{p['total_profit_inr']:>9,}  soil {p['soil_trajectory'][0]}->{p['soil_final']}  {seq}")
    for w in res.get("warnings", []):
        print("  weather:", w)


print("health:", ok(c.get("/health")))
farm = ok(c.post("/farm/profile", json=dict(name="Demo farm (SIMULATED)", state="Haryana", district="Karnal",
              lat=29.69, lon=76.99, area_acres=3, previous_crop="rice", next_season="rabi", soil=SOIL)))
fid = farm["farm_id"]
print("farm", fid, "soil index:", farm["profile"]["soil_index"])
base = ok(c.post("/plan/generate", json={"farm_id": fid}))
show("Baseline plans", base)
print("  water:", base["water"]["note"])
bal = next(p for p in base["plans"] if p["plan"] == "B_balanced")
print("  why balanced:", bal["explanation"]["text"])
fert = bal["next_season_fertilizer"]
print(f"  fertilizer for {fert['crop']}: N/P/K kg/acre {fert['nutrients_kg_per_acre']}, "
      + ", ".join(f"{p['product']} {p['bags']} bags" for p in fert["products"]))
show("Mustard price crash (MSP 6613 -> 4300, -35%)",
     ok(c.post("/plan/generate", json={"farm_id": fid, "price_overrides": {"mustard": 4300}})))
print("\n== Residue options after paddy")
for o in ok(c.post("/residue/decision", json={"crop": "rice", "area_acres": 3, "equipment_access": True,
                                              "biomass_buyer_km": 12}))["options"]:
    print(f"{o['option']:13} feasible={o['feasible']!s:5} net Rs{o['net_inr']:>7,} soil {o['soil_delta']:+}")
print("\n== Farmer burns residue -> re-plan")
print(ok(c.post("/season/outcome", json=dict(farm_id=fid, season="kharif", crop="rice", residue_action="burn"))))
after = ok(c.post("/plan/generate", json={"farm_id": fid}))
show("After burning", after)
bal = next(p for p in after["plans"] if p["plan"] == "B_balanced")
print("\n== Farmer's own rice-wheat habit vs the new balanced plan (/plan/compare)")
for r in ok(c.post("/plan/compare", json={"farm_id": fid, "sequences": [["wheat", None, "rice", "wheat", None, "rice"],
                                                                        [s["crop"] for s in bal["sequence"]]]}))["results"]:
    print(f"Rs{r['total_profit_inr']:>9,} soil -> {r['soil_final']}  issues: {r['issues'] or 'none'}")
mem = ok(c.get("/farm/memory", params={"farm_id": fid}))
print("\nMemory:", len(mem["plan_versions"]), "plan versions,", len(mem["outcomes"]), "outcome(s) stored")
