// Typed client for the Fasal Sarthi API. Copied to frontend/src/lib/api.ts by setup.fish.
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
// Only needed if the backend sets API_KEY. NEXT_PUBLIC_ values are visible in the browser (fine for a demo).
const KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (KEY) headers["X-API-Key"] = KEY;
  const res = await fetch(BASE + path, { headers, ...init });
  if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`);
  return res.json();
}
const post = <T>(path: string, body: unknown) => call<T>(path, { method: "POST", body: JSON.stringify(body) });

export type Season = "kharif" | "rabi" | "zaid";
export type Soil = { ph: number; ec: number; oc: number; n: number; p: number; k: number;
  s?: number; zn?: number; fe?: number; cu?: number; mn?: number; b?: number };
export type FarmProfile = {
  name: string; state?: string; district?: string; lat?: number | null; lon?: number | null; area_acres: number;
  water_mm_per_season?: number; budget_inr_per_season?: number; previous_crop?: string | null;
  next_season?: Season; soil_index?: number; soil?: Soil | null; excluded_crops?: string[]; language?: string;
};
export type SoilAssessment = { classes: Record<string, string>; soil_index: number; micronutrient_deficiencies: string[] };

export type FertilizerProduct = { product: "urea" | "dap" | "mop"; label: string; kg_per_acre: number; kg_total: number;
  bags: number; bag_kg: number; indicative_cost_inr: number };
export type Fertilizer = {
  crop: string; area_acres: number; basis: string;
  nutrients_kg_per_ha: { n: number; p2o5: number; k2o: number }; nutrients_kg_per_acre: { n: number; p2o5: number; k2o: number };
  products: FertilizerProduct[];
  micronutrients: { nutrient: string; product: string | null; kg_per_ha: number | null; kg_total: number | null; note?: string }[];
  notes: string[]; indicative_cost_inr: number; requires_expert_review: true; data_note: string;
};

export type SeqItem = { season_index: number; season: Season; crop: string | null; profit_inr: number;
  water_mm: number; water_available_mm: number };
export type Plan = {
  plan: "A_max_profit" | "B_balanced" | "C_soil_recovery"; sequence: SeqItem[];
  total_profit_inr: number; soil_trajectory: number[]; soil_final: number;
  total_water_mm: number; avg_risk: number; floor_relaxed: boolean;
  explanation: { text: string; source: "llm" | "template"; template: string };
  next_season_fertilizer: Fertilizer | null;
};
export type Weather = { rain_mm_7d: number; tmax_c: number; tmin_c: number; warnings: string[]; source: string };
export type PlanResponse = {
  plan_version_id: string; plans: Plan[]; prices: Record<string, number>;
  price_meta: { source: string; as_of: string | null; live_crops?: string[]; overridden?: string[] };
  weather: Weather | null; warnings: string[];
  water: { irrigation_mm_per_season: number; note: string;
    rain_climatology: { mean_rain_mm: Record<Season, number>; effective_rain_mm: Record<Season, number>;
      effective_fraction: number; years: string; source: string } | null };
  soil_index_start: number; previous_crop: string | null; next_season: Season; horizon: number;
  model_version: string; data_note: string;
};
export type CompareResult = Partial<Omit<Plan, "plan" | "explanation" | "next_season_fertilizer">> & { plan: "custom"; issues: string[] };
export type ResidueOption = { option: string; label: string; feasible: boolean; blocked_reason: string | null;
  net_inr: number; soil_delta: number; note: string };
export type OutcomeResponse = { farm_id: string; soil_index_before: number; soil_index: number;
  previous_crop: string; next_season: Season };
export type Memory = {
  farm_id: string; profile: FarmProfile;
  plan_versions: { id: string; created_at: string; model_version: string; soil_index_start: number;
    summary: { plan: Plan["plan"]; total_profit_inr: number; soil_final: number; first_crop: string | null }[] }[];
  outcomes: ({ id: string; created_at: string; season: Season; crop: string; residue_action: string | null;
    yield_q_per_acre: number | null; net_income_inr: number | null; soil_index_before: number; soil_index_after: number })[];
};
export type Health = { ok: boolean; version: string; live_data: boolean; auth_required: boolean;
  database_backend: "firestore" | "sqlite" | "memory"; crops: string[] };

export const api = {
  health: () => call<Health>("/health"),
  upsertFarm: (farm: FarmProfile & { farm_id?: string }) =>
    post<{ farm_id: string; profile: FarmProfile }>("/farm/profile", farm),
  assessSoil: (soil: Soil, farm_id?: string) => post<SoilAssessment>("/soil/assessment", { soil, farm_id }),
  generatePlans: (farm_id: string, price_overrides: Record<string, number> = {}, horizon = 6) =>
    post<PlanResponse>("/plan/generate", { farm_id, horizon, price_overrides }),
  comparePlans: (farm_id: string, sequences: (string | null)[][], price_overrides: Record<string, number> = {}) =>
    post<{ results: CompareResult[]; prices: Record<string, number>; data_note: string }>("/plan/compare",
      { farm_id, sequences, price_overrides }),
  residueDecision: (r: { crop: string; area_acres: number; equipment_access: boolean; biomass_buyer_km?: number }) =>
    post<{ options: ResidueOption[]; data_note: string }>("/residue/decision", r),
  fertilizer: (r: { crop: string; farm_id?: string; soil?: Soil; area_acres?: number }) =>
    post<Fertilizer>("/fertilizer/recommendation", r),
  recordOutcome: (o: { farm_id: string; season: Season; crop: string; yield_q_per_acre?: number;
    net_income_inr?: number; residue_action?: string; soil?: Soil }) => post<OutcomeResponse>("/season/outcome", o),
  memory: (farm_id: string) => call<Memory>(`/farm/memory?farm_id=${farm_id}`),
};
