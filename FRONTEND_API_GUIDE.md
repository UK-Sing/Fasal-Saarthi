# Fasal Sarthi backend: guide for the frontend

Everything the UI needs to talk to the API. All examples below are real responses captured from the running backend (v0.2.0).

## 1. Connecting

| Item | Value |
| --- | --- |
| Base URL (local) | `http://localhost:8000` (env `NEXT_PUBLIC_API_URL`) |
| Interactive docs | `http://localhost:8000/docs` (Swagger, try every endpoint live) |
| OpenAPI schema | `http://localhost:8000/openapi.json` |
| Content type | JSON in, JSON out |
| Auth | Only if the backend sets `API_KEY`: send header `X-API-Key: <value>` on every call except `/health`. Check `GET /health` → `auth_required`. |
| CORS | `http://localhost:3000` and `http://127.0.0.1:3000` are allowed by default |
| Typed client | `frontend_starter/lib/api.ts` — copy it to `frontend/src/lib/api.ts`. It already wraps every endpoint with the types below. |

Typical latency: plan generation takes ~0.5–2 s (an optimizer runs three times). Show a loading state.

## 2. Core concepts

- **Farm** – one record per field/farm, identified by `farm_id`, an **opaque string** (e.g. `"kS7dbD6u0pMP7G3Dn2gO"`). Never parse it or assume it is numeric. Keep it in client state/localStorage after creating a farm.
- **Seasons** – `"kharif"` (Jun–Oct), `"rabi"` (Nov–Mar), `"zaid"` (Apr–May). They cycle kharif → rabi → zaid → kharif.
- **Crops** – exactly six: `rice`, `wheat`, `maize`, `mustard`, `chickpea`, `moong`. `GET /health` returns the list; populate dropdowns from it. A crop value of `null` in a plan means **fallow** (nothing grown that season).
- **Soil index** – 0–100 health score derived from a Soil Health Card style test. Below ~50 is degraded.
- **Plans** – every generation returns three plans, always in this order:
  - `A_max_profit` – "Maximum near-term return"
  - `B_balanced` – "Balanced" (the one to highlight)
  - `C_soil_recovery` – "Soil recovery"
- **Residue actions** – `happy_seeder`, `incorporate`, `mulch`, `compost`, `biomass_sale`, `burn`. `burn` is always listed, last; never hide it, never shame the farmer.
- **Money** – all amounts are INR, integers unless noted. Prices are ₹ per quintal. Areas are acres.
- **Simulated data** – every planning response carries `data_note`. **Show a "simulated / placeholder data" label** wherever profits or doses appear; the concept doc requires it.

## 3. The farmer journey (which endpoint when)

1. Onboarding form → `POST /farm/profile` (include `soil` if the farmer has a Soil Health Card) → store `farm_id`.
2. Soil screen → `POST /soil/assessment` to show classes and deficiencies (optionally with `farm_id` to save it).
3. Plans screen → `POST /plan/generate` → three plan cards + profit/soil charts + "why" text + next-season fertilizer.
4. "What if prices change?" slider → `POST /plan/generate` again with `price_overrides`.
5. "Compare my usual rotation" → `POST /plan/compare` with the farmer's own sequence.
6. Residue screen → `POST /residue/decision`.
7. Fertilizer screen → `POST /fertilizer/recommendation`.
8. End of season → `POST /season/outcome` (soil index and next season update), then regenerate plans.
9. History / FPO dashboard → `GET /farm/memory`.

The 3-minute demo script is `scripts/demo.py`; the UI should be able to reproduce that story.

## 4. Endpoints

### `GET /health`
No auth. Use it to detect the backend and populate crop lists.
```json
{"ok": true, "version": "0.2.0", "live_data": false, "auth_required": false,
 "database_backend": "firestore", "crops": ["rice","wheat","maize","mustard","chickpea","moong"]}
```

### `POST /farm/profile` — create or update a farm
Request (all fields except `name` and `area_acres` are optional):
```json
{
  "farm_id": null,                 // omit to create; pass an existing id to update
  "name": "Demo farm (SIMULATED)",
  "state": "Haryana", "district": "Karnal",
  "lat": 29.69, "lon": 76.99,      // needed for weather features (live mode only)
  "area_acres": 3,
  "water_mm_per_season": 1300,     // irrigation water available per season, mm
  "budget_inr_per_season": 100000,
  "previous_crop": "rice",         // one of the six crops or null
  "next_season": "rabi",           // the season being planned next
  "soil": {"ph": 8.1, "ec": 0.6, "oc": 0.42, "n": 250, "p": 14, "k": 150, "zn": 0.5},
  "soil_index": 55,                // ignored if soil is given (computed from it)
  "excluded_crops": [],            // crops the farmer refuses to grow
  "language": "en"                 // used for LLM explanations when enabled
}
```
Soil fields: `ph` (0–14), `ec` (dS/m), `oc` (% organic carbon), `n`, `p`, `k` (kg/ha) are required inside `soil`; `s`, `zn`, `fe`, `cu`, `mn`, `b` (ppm) are optional.

Response:
```json
{"farm_id": "kS7dbD6u0pMP7G3Dn2gO",
 "profile": {"name": "Demo farm (SIMULATED)", "state": "Haryana", "district": "Karnal", "lat": 29.69, "lon": 76.99,
             "area_acres": 3.0, "water_mm_per_season": 1300.0, "budget_inr_per_season": 100000.0,
             "previous_crop": "rice", "next_season": "rabi", "soil_index": 47.1,
             "soil": {"ph": 8.1, "ec": 0.6, "oc": 0.42, "n": 250.0, "p": 14.0, "k": 150.0, "zn": 0.5, "s": null, "fe": null, "cu": null, "mn": null, "b": null},
             "excluded_crops": [], "language": "en"}}
```
**Update semantics:** send `farm_id` plus only the fields you want to change (`name` and `area_acres` are always required by the schema, so resend them). Fields you don't send keep their stored values, including the soil index after a burn and the advanced season. Re-sending the *same* soil test keeps the history; sending a *new* soil test recomputes the index.

### `POST /soil/assessment` — interpret a soil test
Request: `{"soil": {...same soil object...}, "farm_id": "optional"}`. With `farm_id` the test is saved to the farm.
```json
{"classes": {"oc": "low", "n": "low", "p": "medium", "k": "medium", "ph": "watch", "ec": "good"},
 "soil_index": 47.1,
 "micronutrient_deficiencies": ["zn"]}
```
`classes` values: nutrients are `low | medium | high`; `ph` and `ec` are `good | watch | poor`. Good UI: a traffic-light table.

### `POST /plan/generate` — the main screen
Request:
```json
{"farm_id": "kS7dbD6u0pMP7G3Dn2gO",
 "horizon": 6,                              // seasons to plan, 2–9, default 6
 "price_overrides": {"mustard": 4300}}      // optional ₹/quintal scenario prices
```
Response (one plan shown; the array always has three):
```json
{
 "plan_version_id": "XGjaSV9KfsDNbdJRLNKT",
 "plans": [
  {
   "plan": "B_balanced",
   "sequence": [
     {"season_index": 0, "season": "rabi", "crop": "mustard", "profit_inr": 99873, "water_mm": 250, "water_available_mm": 1300},
     {"season_index": 1, "season": "zaid", "crop": "moong",   "profit_inr": 65190, "water_mm": 300, "water_available_mm": 1300},
     "... one entry per season; crop may be null (fallow)"
   ],
   "total_profit_inr": 491571,
   "soil_trajectory": [47.1, 46.1, 50.1, 48.1, 52.1, 50.1, 54.1],   // horizon + 1 points (start first)
   "soil_final": 54.1,
   "total_water_mm": 2150.0,
   "avg_risk": 0.31,                 // 0–1, lower is safer
   "floor_relaxed": false,           // true = soil target could not be met; show a caveat
   "explanation": {"text": "Balanced plan: rabi: mustard, ... confirm with your local agronomist.",
                   "source": "template",            // or "llm" when an LLM is configured
                   "template": "...same text..."},
   "next_season_fertilizer": { "...same object as POST /fertilizer/recommendation, for sequence[0].crop; null if fallow" }
  },
  "... A_max_profit, C_soil_recovery"
 ],
 "prices": {"rice": 2441, "wheat": 2610, "maize": 2410, "mustard": 6613, "chickpea": 5958, "moong": 8780},
 "price_meta": {"source": "config_defaults (Govt MSP, see crops.yaml)", "as_of": null,
                "overridden": ["mustard"]},          // only present when you sent price_overrides
 "weather": null,                                    // or {"rain_mm_7d", "tmax_c", "tmin_c", "warnings": [...], "source"} in live mode
 "water": {"irrigation_mm_per_season": 1300.0, "rain_climatology": null,
           "note": "irrigation water only (live weather off or no lat/lon)"},
 "warnings": [],                                     // weather strings to show as banners
 "soil_index_start": 47.1, "previous_crop": "rice", "next_season": "rabi", "horizon": 6,
 "model_version": "0.2.0",
 "data_note": "SIMULATED / PLACEHOLDER agronomy: ... Default prices are Govt MSP."
}
```
Charting hints: `soil_trajectory` for all three plans on one line chart (x = season index 0..horizon); `sequence[].profit_inr` as stacked bars or a cumulative line; `total_profit_inr` vs `soil_final` as the headline trade-off per card. Each call is stored as a plan version (`plan_version_id`) and appears in `/farm/memory`.

### `POST /plan/compare` — score the farmer's own rotation
Request: `{"farm_id": "...", "sequences": [["wheat", "maize", "rice"], ["chickpea", null, "moong"]], "price_overrides": {}}`
Each inner list is one sequence starting at the farm's `next_season`; `null` = fallow; 1–9 entries.
```json
{"results": [
  {"plan": "custom",
   "sequence": [{"season_index": 0, "season": "rabi", "crop": "wheat", "profit_inr": 97770, "water_mm": 450, "water_available_mm": 1300}, "..."],
   "total_profit_inr": 259476, "soil_trajectory": [47.1, 45.1, 43.1, 41.1], "soil_final": 41.1,
   "total_water_mm": 2200.0, "avg_risk": 0.2, "floor_relaxed": false,
   "issues": ["more than 2 consecutive cereal season(s) at season 2",
              "final soil index 41.1 below the balanced floor of 52"]}],
 "prices": {"rice": 2441, "...": 0}, "data_note": "..."}
```
`issues` is empty when the sequence breaks no rule. Possible issue texts: wrong season for a crop, exceeds water, exceeds budget, repeated back-to-back, too many consecutive cereal/oilseed/legume seasons, excluded crop, soil below floor. Show them as a checklist next to the numbers.

### `POST /residue/decision` — what to do with crop residue
Request: `{"crop": "rice", "area_acres": 3, "equipment_access": true, "biomass_buyer_km": 12}`
(`biomass_buyer_km` null/omitted = no buyer reachable.)
```json
{"options": [
  {"option": "compost", "label": "Compost on farm", "feasible": true, "blocked_reason": null,
   "net_inr": -2100, "soil_delta": 2, "note": "Needs 6+ weeks and pit space."},
  {"option": "happy_seeder", "label": "Zero-till sowing into residue (Happy Seeder)", "feasible": true,
   "blocked_reason": null, "net_inr": -3600, "soil_delta": 2, "note": "Needs machine access (custom-hiring centre)."},
  "... incorporate, biomass_sale, burn (burn is always last)"],
 "data_note": "..."}
```
Options are pre-sorted: feasible first, then best overall. `net_inr` is for the whole area (negative = costs money). `blocked_reason` explains infeasible ones (e.g. "needs equipment access"). The chosen `option` string is what you send as `residue_action` in `/season/outcome`.

### `POST /fertilizer/recommendation`
Request: `{"crop": "wheat", "farm_id": "..."}` — uses the farm's soil test and area. Alternatives: `{"crop": "wheat", "soil": {...}, "area_acres": 2}` without a farm. With no soil at all you get the general dose.
```json
{"crop": "wheat", "area_acres": 3.0,
 "basis": "RDF adjusted by soil-test class: N low, P medium, K medium",
 "nutrients_kg_per_ha":   {"n": 150.0, "p2o5": 60.0, "k2o": 40.0},
 "nutrients_kg_per_acre": {"n": 60.7,  "p2o5": 24.3, "k2o": 16.2},
 "products": [
   {"product": "urea", "label": "Urea (46% N)",          "kg_per_acre": 111.3, "kg_total": 333.9, "bags": 7.4, "bag_kg": 45, "indicative_cost_inr": 1978},
   {"product": "dap",  "label": "DAP (18% N, 46% P2O5)", "kg_per_acre": 52.8,  "kg_total": 158.4, "bags": 3.2, "bag_kg": 50, "indicative_cost_inr": 4276},
   {"product": "mop",  "label": "MOP (60% K2O)",         "kg_per_acre": 27.0,  "kg_total": 80.9,  "bags": 1.6, "bag_kg": 50, "indicative_cost_inr": 2752}],
 "micronutrients": [{"nutrient": "zn", "product": "Zinc sulphate heptahydrate (21% Zn)", "kg_per_ha": 25, "kg_total": 30.4}],
 "notes": ["Organic carbon is low: add organic matter (FYM/compost, residue retention)."],
 "indicative_cost_inr": 9005,
 "requires_expert_review": true,
 "data_note": "Doses are general placeholder RDFs pending ... validation. Split N application and timing per local recommendation."}
```
Micronutrient entries with `product: null` mean "deficient, ask an agronomist for the dose" (shown with a `note`). Always render `requires_expert_review` as a visible caveat.

### `POST /season/outcome` — close a season
Request:
```json
{"farm_id": "...", "season": "kharif", "crop": "rice",
 "yield_q_per_acre": 22, "net_income_inr": 70000,      // optional, stored for history
 "residue_action": "burn",                             // optional; shifts the soil index (burn = -3)
 "soil": {"ph": 7.9, "...": 0}}                        // optional fresh soil test; overrides the modelled index
```
```json
{"farm_id": "kS7dbD6u0pMP7G3Dn2gO", "soil_index_before": 47.1, "soil_index": 44.1,
 "previous_crop": "rice", "next_season": "rabi"}
```
After this, the farm's `previous_crop` and `next_season` have advanced, so call `/plan/generate` again to show the re-plan. In the demo, recording a burn flips the balanced plan's next crop from mustard to chickpea.

### `GET /farm/memory?farm_id=...` — history
```json
{"farm_id": "kS7dbD6u0pMP7G3Dn2gO",
 "profile": {"...same as /farm/profile response.profile..."},
 "plan_versions": [
   {"id": "XGjaSV9KfsDNbdJRLNKT", "created_at": "2026-10-07T17:40:54.671377+00:00", "model_version": "0.2.0",
    "soil_index_start": 47.1,
    "summary": [{"plan": "A_max_profit", "total_profit_inr": 523158, "soil_final": 37.1, "first_crop": "mustard"},
                {"plan": "B_balanced",   "total_profit_inr": 491571, "soil_final": 54.1, "first_crop": "mustard"},
                {"plan": "C_soil_recovery", "total_profit_inr": 322371, "soil_final": 60.1, "first_crop": "chickpea"}]}],
 "outcomes": [
   {"id": "Tc1ZeiP5vSRRjE4VkJyp", "created_at": "2026-10-07T17:40:55.815501+00:00", "farm_id": "kS7dbD6u0pMP7G3Dn2gO",
    "season": "kharif", "crop": "rice", "residue_action": "burn", "yield_q_per_acre": null, "net_income_inr": null,
    "soil": null, "soil_index_before": 47.1, "soil_index_after": 44.1}]}
```
Both lists are oldest-first; `created_at` is ISO-8601 UTC. This is the "farm memory / audit trail" view and the FPO/API interoperability moment of the demo.

## 5. Errors

| Status | When | Body |
| --- | --- | --- |
| 404 | unknown `farm_id` | `{"detail": "farm not found"}` |
| 422 | invalid input (unknown crop, pH > 14, area ≤ 0, price ≤ 0, horizon outside 2–9, bad residue action, …) | FastAPI format: `{"detail": [{"loc": ["body","crop"], "msg": "Value error, unknown crop 'banana'; use one of [...]", "type": "value_error", ...}]}` |
| 401 | `API_KEY` set and header missing/wrong | `{"detail": "missing or invalid X-API-Key"}` |

For 422, `detail[i].loc` tells you which field to highlight; `msg` is safe to show after stripping the `Value error, ` prefix.

## 6. Things to show in the UI (responsible-AI requirements from the concept doc)

- The "simulated data" label on every number (`data_note`).
- The explanation text per plan (`explanation.text`) and whether it came from the template or an LLM (`explanation.source`).
- Uncertainty cues: `avg_risk`, `floor_relaxed`, `price_meta.source`/`as_of` (defaults are MSP floors, not forecasts).
- Human override: always let the user pick any plan or enter their own sequence via `/plan/compare`.
- Fertilizer: `requires_expert_review` and `notes`.
- Residue: all options including burn, with `net_inr` and `soil_delta`, no judgemental copy.

## 7. Running the backend locally

```fish
cd backend
uv run uvicorn app.main:app --reload      # http://localhost:8000/docs
uv run python ../scripts/demo.py          # replays the whole story against the API
```
Data persists in Firestore by default (`DATABASE_BACKEND=firestore` in the root `.env`); if the backend is run offline it uses SQLite (`DATABASE_BACKEND=sqlite`). Either way the API contract above is identical.
