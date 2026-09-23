import { type Choice } from "../data";
import { validate } from "../engine";
import { decodePlan, encodePlan } from "../planner/analysis";

export const VARIANTS_STORAGE = "sim-astana-variants-v1";
export const VARIANT_IDS = ["A", "B", "C"] as const;
export interface Variant {
  id: string;
  name: string;
  plan: Choice[];
}

/** Treat browser storage as untrusted; discard broken entries independently. */
export function parseVariants(raw: string | null): Variant[] {
  try {
    const data: unknown = JSON.parse(raw ?? "null");
    if (!Array.isArray(data)) return [];
    const variants: Variant[] = [];
    for (const item of data) {
      if (!item || !VARIANT_IDS.includes(item.id) || variants.some((v) => v.id === item.id)
        || typeof item.name !== "string" || !item.name.trim() || typeof item.plan !== "string") continue;
      const plan = decodePlan(item.plan);
      if (validate(plan).length || encodePlan(plan) !== item.plan) continue;
      variants.push({ id: item.id, name: item.name.trim().slice(0, 60), plan });
    }
    return variants;
  } catch {
    return [];
  }
}

export function serializeVariants(variants: Variant[]) {
  return JSON.stringify(variants.slice(0, 3).map((v) => ({ ...v, plan: encodePlan(v.plan) })));
}
