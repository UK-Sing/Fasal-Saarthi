// Typed client for the Fasal Sarthi API. Copied to frontend/src/lib/api.ts by setup.fish.
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`);
  return res.json();
}
const post = <T>(path: string, body: unknown) => call<T>(path, { method: "POST", body: JSON.stringify(body) });

export type SeqItem = { season_index: number; season: string; crop: string | null; profit_inr: number };
export type Plan = {
  plan: "A_max_profit" | "B_balanced" | "C_soil_recovery"; sequence: SeqItem[];
  total_profit_inr: number; soil_trajectory: number[]; soil_final: number;
  total_water_mm: number; avg_risk: number; floor_relaxed: boolean;
  explanation: { text: string; source: "llm" | "template" };
};
export type PlanResponse = { plans: Plan[]; prices: Record<string, number>; soil_index_start: number; data_note: string };

export const api = {
  upsertFarm: (farm: Record<string, unknown>) => post<{ farm_id: number }>("/farm/profile", farm),
  assessSoil: (soil: Record<string, number>, farm_id?: number) => post("/soil/assessment", { soil, farm_id }),
  generatePlans: (farm_id: number, price_overrides: Record<string, number> = {}, horizon = 6) =>
    post<PlanResponse>("/plan/generate", { farm_id, horizon, price_overrides }),
  comparePlans: (farm_id: number, sequences: (string | null)[][]) => post("/plan/compare", { farm_id, sequences }),
  residueDecision: (r: { crop: string; area_acres: number; equipment_access: boolean; biomass_buyer_km?: number }) =>
    post("/residue/decision", r),
  recordOutcome: (o: Record<string, unknown>) => post("/season/outcome", o),
  memory: (farm_id: number) => call(`/farm/memory?farm_id=${farm_id}`),
};
