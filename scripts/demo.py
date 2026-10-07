"""Rehearse the 3-minute demo against a running API:  uv run python ../scripts/demo.py"""
import sys, httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
c = httpx.Client(base_url=BASE, timeout=30)
SOIL = dict(ph=8.1, ec=0.6, oc=0.42, n=250, p=14, k=150)


def show(title, res):
    print(f"\n== {title}")
    for p in res["plans"]:
        seq = " > ".join(s["crop"] or "fallow" for s in p["sequence"])
        print(f"{p['plan']:16} Rs{p['total_profit_inr']:>9,}  soil {p['soil_trajectory'][0]}->{p['soil_final']}  {seq}")


farm = c.post("/farm/profile", json=dict(name="Demo farm (SIMULATED)", state="Haryana", district="Karnal",
              lat=29.69, lon=76.99, area_acres=3, previous_crop="rice", next_season="rabi", soil=SOIL)).json()
fid = farm["farm_id"]
print("soil index:", farm["profile"]["soil_index"])
show("Baseline plans", c.post("/plan/generate", json={"farm_id": fid}).json())
show("Mustard price crash (-35%)", c.post("/plan/generate", json={"farm_id": fid, "price_overrides": {"mustard": 3700}}).json())
print("\n== Residue options after paddy")
for o in c.post("/residue/decision", json={"crop": "rice", "area_acres": 3, "equipment_access": True, "biomass_buyer_km": 12}).json()["options"]:
    print(f"{o['option']:13} feasible={o['feasible']!s:5} net Rs{o['net_inr']:>7,} soil {o['soil_delta']:+}")
print("\n== Farmer burns residue -> re-plan")
print(c.post("/season/outcome", json=dict(farm_id=fid, season="kharif", crop="rice", residue_action="burn")).json())
show("After burning", c.post("/plan/generate", json={"farm_id": fid}).json())
print("\nMemory:", len(c.get("/farm/memory", params={"farm_id": fid}).json()["plan_versions"]), "plan versions stored")
