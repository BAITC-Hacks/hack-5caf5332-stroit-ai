import { BUDGET_LIMIT, money } from "./money";
import {
  districts,
  measures,
  indicators,
  weights,
  synergies,
  conflicts,
  samplePlan,
  measureById,
  type Choice,
  type DistrictId,
  type Values,
} from "./data";
export const budget = (plan: Choice[]) =>
  plan.reduce(
    (sum, c) => sum + (measures.find((m) => m.id === c.measureId)?.cost ?? 0),
    0,
  );
export function validate(plan: Choice[], draft = false): string[] {
  const errors: string[] = [];
  if ((!draft && plan.length !== 5) || plan.length > 5)
    errors.push("Нужно ровно 5 решений.");
  if (new Set(plan.map((c) => c.measureId)).size !== plan.length)
    errors.push("Меры не должны повторяться.");
  if (budget(plan) > BUDGET_LIMIT)
    errors.push(
      `Бюджет превышен на ${money(budget(plan) - BUDGET_LIMIT)} у.е.`,
    );
  const counts: Record<string, number> = {};
  for (const c of plan) {
    const m = measures.find((m) => m.id === c.measureId);
    if (!m) {
      errors.push(`Неизвестная мера ${c.measureId}.`);
      continue;
    }
    counts[m.direction] = (counts[m.direction] ?? 0) + 1;
    if (m.type === "district" && !districts.some((d) => d.id === c.districtId))
      errors.push(`${m.id}: выберите район.`);
    if (m.type === "city" && c.districtId !== undefined)
      errors.push(`${m.id}: городская мера применяется без района.`);
  }
  for (const [direction, count] of Object.entries(counts))
    if (count > 2) errors.push(`${direction}: не более 2 мер.`);
  for (const conflict of conflicts) {
    const a = plan.find((c) => c.measureId === conflict.pair[0]);
    const b = plan.find((c) => c.measureId === conflict.pair[1]);
    if (a && b && (!conflict.sameDistrict || a.districtId === b.districtId))
      errors.push(conflict.reason);
  }
  return errors;
}
interface DistrictResult {
  id: DistrictId;
  values: Values;
  delta: Values;
  score: number;
}
export interface Projection {
  districts: DistrictResult[];
  average: number;
  critical: number;
  score: number;
}
// Internal effects calculation also supports individual proposals for the demo poll.
// Public simulate() never assigns a score to an invalid plan.
export function projectEffects(plan: Choice[]): Projection {
  const rows: DistrictResult[] = districts.map((d) => ({
    id: d.id,
    values: { ...d.values },
    delta: { ...d.values },
    score: 0,
  }));
  for (const c of plan) {
    const m = measureById(c.measureId);
    for (const row of rows) {
      if (m.type === "district" && c.districtId !== row.id) continue;
      for (const k of indicators)
        row.values[k] += ((m.effects[k] ?? 0) * (8 - m.lag)) / 8;
    }
  }
  for (const s of synergies) {
    const first = plan.find((c) => c.measureId === s.pair[0]);
    if (first && plan.some((c) => c.measureId === s.pair[1])) {
      const row = rows.find((r) => r.id === first.districtId);
      if (row) row.values[s.indicator] += s.bonus;
    }
  }
  for (const [i, row] of rows.entries())
    for (const k of indicators) {
      row.values[k] = Math.min(100, Math.max(0, row.values[k]));
      row.delta[k] = row.values[k] - districts[i].values[k];
      row.score += weights[k] * row.values[k];
    }
  const average = rows.reduce(
    (s, row, i) => s + row.score * districts[i].population,
    0,
  );
  const critical = rows.reduce(
    (s, row) => s + indicators.filter((k) => row.values[k] < 40).length,
    0,
  );
  return {
    districts: rows,
    average,
    critical,
    score:
      0.7 * average + 0.3 * Math.min(...rows.map((r) => r.score)) - critical,
  };
}
export const baseline = projectEffects([]);
export function simulate(plan: Choice[]) {
  const errors = validate(plan);
  return { errors, result: errors.length ? null : projectEffects(plan) };
}
export const allChoices: Choice[] = measures.flatMap((m) =>
  m.type === "city"
    ? [{ measureId: m.id }]
    : districts.map((d) => ({ measureId: m.id, districtId: d.id })),
);
export interface Alternative {
  plan: Choice[];
  result: Projection;
  removed: Choice;
  added: Choice;
  improvement: number;
}
export function advise(plan: Choice[]): Alternative | null {
  const original = simulate(plan).result;
  if (!original) return null;
  let best: Alternative | null = null;
  for (let i = 0; i < plan.length; i++)
    for (const candidate of allChoices) {
      if (
        candidate.measureId === plan[i].measureId &&
        candidate.districtId === plan[i].districtId
      )
        continue;
      const next = plan.map((c, j) => (j === i ? candidate : c));
      const result = simulate(next).result;
      if (result && (!best || result.score > best.result.score + 1e-9))
        best = {
          plan: next,
          result,
          removed: plan[i],
          added: candidate,
          improvement: result.score - original.score,
        };
    }
  return best;
}
let cachedAutopilot: Choice[] | null = null;
export function autopilot(): Choice[] {
  if (cachedAutopilot) return cachedAutopilot.map((c) => ({ ...c }));
  let plan = samplePlan.map((c) => ({ ...c }));
  for (let step = 0; step < 8; step++) {
    const next = advise(plan);
    if (!next || next.improvement < 1e-9) break;
    plan = next.plan;
  }
  cachedAutopilot = plan;
  return plan.map((c) => ({ ...c }));
}
