// Deterministic plan analysis for the planner view. Every number here comes from the
// scoring engine; the AI layer may only rephrase these facts, never add new ones.
import {
  directions,
  districts,
  indicators,
  indicatorNames,
  measureById,
  measures,
  synergies,
  type Choice,
  type Direction,
  type DistrictId,
  type Indicator,
} from "../data";
import { baseline, budget, projectEffects, validate, type Projection } from "../engine";
import { BUDGET_LIMIT } from "../money";
import { pollProposal } from "../residents";

export const TARGET_GAIN = 3;
const PRIORITY_GAIN = 1;
const CRITICAL = 40;
const HORIZON = 8;

export const directionOf: Record<Indicator, Direction> = {
  T1: "Транспорт",
  T2: "Транспорт",
  E1: "Экология",
  E2: "Экология",
  S1: "Соцсфера",
  S2: "Соцсфера",
  B1: "Безопасность",
  B2: "Безопасность",
  C1: "Сервисы",
  C2: "Сервисы",
};

export const districtName = (id: DistrictId) =>
  districts.find((d) => d.id === id)!.name;

const locative: Record<DistrictId, string> = {
  esil: "в Есиле",
  almaty: "в районе Алматы",
  saryarka: "в Сарыарке",
  baikonur: "в Байконуре",
  nura: "в Нуре",
};
export const inDistrict = (id: DistrictId) => locative[id];

export const lower = (text: string) => text.toLocaleLowerCase("ru");

export interface Cell {
  district: DistrictId;
  indicator: Indicator;
  value: number;
}

export function criticalCells(projection: Projection): Cell[] {
  return projection.districts.flatMap((row) =>
    indicators
      .filter((k) => row.values[k] < CRITICAL)
      .map((k) => ({ district: row.id, indicator: k, value: row.values[k] })),
  );
}

/** Weakest district share of the score: 30% of the score is the minimum district. */
export function weakestDistrict(projection: Projection) {
  return projection.districts.reduce((a, b) => (a.score < b.score ? a : b));
}

/** Score gain from adding one choice to a draft plan (draft may be incomplete). */
export function previewGain(plan: Choice[], choice: Choice) {
  return projectEffects([...plan, choice]).score - projectEffects(plan).score;
}

/** Why a choice cannot join the plan right now; null when it can. */
export function blockReason(plan: Choice[], choice: Choice): string | null {
  if (plan.some((c) => c.measureId === choice.measureId)) return "Уже в плане";
  if (plan.length >= 5) return "В плане уже 5 решений";
  const errors = validate([...plan, choice], true);
  return errors[0] ?? null;
}

export interface Contribution {
  choice: Choice;
  gain: number;
}

/** Marginal contribution: how much the score drops if this one decision is removed. */
export function contributions(plan: Choice[]): Contribution[] {
  const full = projectEffects(plan).score;
  return plan
    .map((choice) => ({
      choice,
      gain: full - projectEffects(plan.filter((c) => c !== choice)).score,
    }))
    .sort((a, b) => b.gain - a.gain);
}

export interface Goal {
  id: string;
  label: string;
  met: boolean;
  detail: string;
}

export function priorityGain(projection: Projection, direction: Direction) {
  const keys = indicators.filter((k) => directionOf[k] === direction);
  return projection.districts.reduce(
    (sum, row, i) =>
      sum +
      districts[i].population *
        (keys.reduce((s, k) => s + row.delta[k], 0) / keys.length),
    0,
  );
}

export function goals(plan: Choice[], priorities: Direction[]): Goal[] {
  const errors = validate(plan);
  const spent = budget(plan);
  const result = projectEffects(plan);
  const gain = result.score - baseline.score;
  const worse = result.districts.filter(
    (row, i) => row.score < baseline.districts[i].score - 1e-9,
  );
  const before = criticalCells(baseline).length;
  const after = criticalCells(result).length;
  const list: Goal[] = [
    {
      id: "rules",
      label: "Пять решений по правилам",
      met: errors.length === 0,
      detail: errors.length
        ? errors[0]
        : `Бюджет ${fmt(spent, 0)} из ${BUDGET_LIMIT} у.е., конфликтов нет.`,
    },
    {
      id: "gain",
      label: `Балл вырос минимум на ${fmt(TARGET_GAIN, 0)}`,
      met: gain >= TARGET_GAIN,
      detail: `${signed(gain)} к исходным ${fmt(baseline.score)}.`,
    },
    {
      id: "nobody-worse",
      label: "Ни один район не стал хуже",
      met: worse.length === 0,
      detail: worse.length
        ? `Хуже стало: ${worse.map((r) => districtName(r.id)).join(", ")}.`
        : "Все пять районов не ниже исходного уровня.",
    },
    {
      id: "critical",
      label: "Меньше критических показателей",
      met: after < before,
      detail: `Ниже ${CRITICAL}: было ${before}, стало ${after}. Каждый стоит минус 1 балл.`,
    },
  ];
  for (const direction of priorities) {
    const value = priorityGain(result, direction);
    list.push({
      id: `priority-${direction}`,
      label: `Приоритет: ${lower(direction)}`,
      met: value >= PRIORITY_GAIN,
      detail: `В среднем по городу ${signed(value, 1)} к показателям направления, цель +${PRIORITY_GAIN}.`,
    });
  }
  return list;
}

export interface Brief {
  strengths: string[];
  risks: string[];
  consequences: string[];
}

export function explain(plan: Choice[], priorities: Direction[]): Brief {
  const result = projectEffects(plan);
  const strengths: string[] = [];
  const risks: string[] = [];
  const consequences: string[] = [];

  const gains = result.districts
    .flatMap((row) =>
      indicators.map((k) => ({
        district: row.id,
        indicator: k,
        delta: row.delta[k],
        from: row.values[k] - row.delta[k],
        to: row.values[k],
      })),
    )
    .filter((g) => g.delta > 0.05)
    .sort((a, b) => b.delta - a.delta);
  for (const g of gains.slice(0, 3))
    strengths.push(
      `${indicatorNames[g.indicator]} ${inDistrict(g.district)}: ${fmt(g.from, 0)} → ${fmt(g.to, 0)}.`,
    );

  const fixed = criticalCells(baseline).filter(
    (c) =>
      result.districts.find((r) => r.id === c.district)!.values[c.indicator] >=
      CRITICAL,
  );
  if (fixed.length)
    strengths.push(
      `Выведено из зоны ниже ${CRITICAL}: ${fixed
        .map((c) => `${lower(indicatorNames[c.indicator])} ${inDistrict(c.district)}`)
        .join(", ")}.`,
    );
  for (const s of synergies)
    if (plan.some((c) => c.measureId === s.pair[0]) && plan.some((c) => c.measureId === s.pair[1]))
      strengths.push(
        `Сработала синергия ${s.pair[0]} + ${s.pair[1]}: ${lower(indicatorNames[s.indicator])} +${s.bonus}.`,
      );

  const remaining = criticalCells(result);
  if (remaining.length)
    risks.push(
      `Остаются ниже ${CRITICAL}: ${remaining
        .map((c) => `${lower(indicatorNames[c.indicator])} ${inDistrict(c.district)} (${fmt(c.value, 0)})`)
        .join(", ")}. Каждый такой показатель снимает 1 балл.`,
    );
  const untouched = result.districts.filter((row) =>
    indicators.every((k) => Math.abs(row.delta[k]) < 0.05),
  );
  if (untouched.length)
    risks.push(
      `${untouched.map((r) => districtName(r.id)).join(", ")}: ни одно решение не меняет жизнь района.`,
    );
  for (const row of result.districts)
    for (const k of indicators)
      if (row.delta[k] < -0.05)
        risks.push(
          `${indicatorNames[k]} ${inDistrict(row.id)} падает на ${fmt(-row.delta[k], 1)}.`,
        );
  const slow = plan
    .map((c) => measureById(c.measureId))
    .filter((m) => m.lag >= 4);
  if (slow.length)
    risks.push(
      `Долгий старт: ${slow
        .map((m) => `${lower(m.name)} (${Math.round(((HORIZON - m.lag) / HORIZON) * 100)}% эффекта за 8 кварталов)`)
        .join(", ")}.`,
    );
  if (plan.length === 5) {
    const unhappy = pollProposal(plan, "").districts.filter((d) => d.approval < 50);
    if (unhappy.length)
      risks.push(
        `Поддержка жителей ниже 50%: ${unhappy
          .map((d) => `${districtName(d.id)} (${fmt(d.approval, 0)}%)`)
          .join(", ")}. Главные нужды этих районов план не закрывает.`,
      );
  }
  const left = BUDGET_LIMIT - budget(plan);
  if (plan.length === 5 && left >= 15)
    risks.push(
      `Не потрачено ${fmt(left, 0)} у.е. Остаток не даёт бонуса к баллу.`,
    );

  const weakest = weakestDistrict(result);
  consequences.push(
    `Самый слабый район после плана: ${districtName(weakest.id)} (${fmt(weakest.score, 1)}). От него зависит 30% итогового балла.`,
  );
  const touched = new Set(plan.map((c) => measureById(c.measureId).direction));
  const missing = directions.filter((d) => !touched.has(d));
  if (missing.length)
    consequences.push(
      `Без вложений остаются: ${missing.map(lower).join(", ")}. Эти показатели не изменятся.`,
    );
  for (const direction of priorities) {
    const value = priorityGain(result, direction);
    consequences.push(
      value >= PRIORITY_GAIN
        ? `Заявленный приоритет «${lower(direction)}» подкреплён решениями.`
        : `Заявленный приоритет «${lower(direction)}» почти не получил вложений.`,
    );
  }
  return { strengths, risks, consequences };
}

// Scenario in the URL: ?plan=M7.nura,M12 — the same link reproduces the same score.
export function encodePlan(plan: Choice[]) {
  return plan.map((c) => (c.districtId ? `${c.measureId}.${c.districtId}` : c.measureId)).join(",");
}

export function decodePlan(value: string | null): Choice[] {
  if (!value) return [];
  const plan: Choice[] = [];
  for (const part of value.split(",").slice(0, 5)) {
    const [measureId, districtId] = part.split(".");
    const measure = measures.find((m) => m.id === measureId);
    if (!measure) continue;
    if (measure.type === "district") {
      if (!districts.some((d) => d.id === districtId)) continue;
      plan.push({ measureId, districtId: districtId as DistrictId });
    } else plan.push({ measureId });
  }
  return validate(plan, true).length ? [] : plan;
}

export function fmt(value: number, digits = 2) {
  return value.toLocaleString("ru-RU", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function signed(value: number, digits = 2) {
  const rounded = Number(value.toFixed(digits));
  return `${rounded > 0 ? "+" : rounded < 0 ? "−" : ""}${fmt(Math.abs(rounded), digits)}`;
}

export interface ComparisonValue {
  current: number;
  variant: number;
  delta: number;
}

/** Deltas are current minus variant. Compare only complete, valid scenarios.
 * Both plans share the same goals; directions are unweighted indicator means.
 */
export function comparePlans(a: Choice[], b: Choice[], priorities: Direction[] = []) {
  for (const plan of [a, b]) {
    const errors = validate(plan);
    if (errors.length) throw new Error(`Нельзя сравнить план: ${errors.join(" ")}`);
  }
  const current = projectEffects(a);
  const variant = projectEffects(b);
  const pair = (x: number, y: number): ComparisonValue => ({
    current: x, variant: y, delta: Math.abs(x - y) < 1e-9 ? 0 : x - y,
  });
  const minimum = (p: Projection) => Math.min(...p.districts.flatMap((r) => indicators.map((k) => r.values[k])));
  const metrics = {
    score: pair(current.score, variant.score),
    budget: pair(budget(a), budget(b)),
    goals: pair(goals(a, priorities).filter((g) => g.met).length, goals(b, priorities).filter((g) => g.met).length),
    support: pair(pollProposal(a, "").approval, pollProposal(b, "").approval),
    minimum: pair(minimum(current), minimum(variant)),
  };
  const rows = current.districts.map((row, i) => ({
    district: row.id,
    score: pair(row.score, variant.districts[i].score),
    directions: directions.map((direction) => {
      const keys = indicators.filter((k) => directionOf[k] === direction);
      return {
        direction,
        ...pair(
          keys.reduce((sum, k) => sum + row.values[k], 0) / keys.length,
          keys.reduce((sum, k) => sum + variant.districts[i].values[k], 0) / keys.length,
        ),
      };
    }),
  }));
  const cells = rows.flatMap((row) => row.directions.map((d) => ({ ...d, district: row.district })));
  // Stable data order breaks ties, so the same plans always produce the same text.
  const strongest = cells.filter((c) => c.delta > 0).sort((x, y) => y.delta - x.delta)[0];
  const weakest = cells.filter((c) => c.delta < 0).sort((x, y) => x.delta - y.delta)[0];
  const where: Record<Direction, string> = {
    Транспорт: "в транспорте", Экология: "в экологии", Соцсфера: "в соцсфере",
    Безопасность: "в безопасности", Сервисы: "в сервисах",
  };
  const districtGenitive: Record<DistrictId, string> = {
    esil: "Есиля", almaty: "района Алматы", saryarka: "Сарыарки", baikonur: "Байконура", nura: "Нуры",
  };
  const details = [
    strongest && `сильнее ${where[strongest.direction]} ${districtGenitive[strongest.district]}`,
    weakest && `слабее ${where[weakest.direction]} ${districtGenitive[weakest.district]}`,
  ].filter(Boolean);
  const delta = metrics.score.delta;
  const lead = Math.abs(delta) < 0.005
    ? "Балл планов одинаков при округлении до сотых"
    : delta > 0
      ? `Текущий план лучше на ${signed(delta)}`
      : `Текущий план хуже на ${fmt(-delta)} (${signed(delta)} к баллу)`;
  const conclusion = `${lead}${details.length ? `: ${details.join(", ")}` : "; показатели районов совпадают"}.`;
  return { metrics, districts: rows, goalCount: goals(a, priorities).length, conclusion };
}
