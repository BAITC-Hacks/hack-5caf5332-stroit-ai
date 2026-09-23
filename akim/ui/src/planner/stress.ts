import { type Choice } from "../data";
import { budget, projectEffects, validate, type IndicatorShock } from "../engine";
import { BUDGET_LIMIT } from "../money";

export const stressEvents = [
  {
    id: "flood", name: "Паводок", multiplier: 1,
    description: "Условное подтопление в Нуре и Сарыарке: разгрузка дорог −12, надёжность ЖКХ −14, безопасность движения −8 в каждом районе.",
    shock: { nura: { T1: -12, C1: -14, B2: -8 }, saryarka: { T1: -12, C1: -14, B2: -8 } },
  },
  {
    id: "heat", name: "Отключение ТЭЦ", multiplier: 1,
    description: "Условный сбой теплоснабжения в районах Алматы и Сарыарка: надёжность ЖКХ −20, доступность поликлиник −6, безопасность улиц −6.",
    shock: { almaty: { C1: -20, S2: -6, B1: -6 }, saryarka: { C1: -20, S2: -6, B1: -6 } },
  },
  {
    id: "prices", name: "Рост цен на 20%", multiplier: 1.2,
    description: "Все пять решений дорожают на 20%. Лимит остаётся 100 у.е. При превышении балл не считается. Эффекты профинансированного плана не меняются.",
    shock: {},
  },
] as const satisfies readonly { id: string; name: string; multiplier: number; description: string; shock: IndicatorShock }[];
export type StressEventId = typeof stressEvents[number]["id"];

/** Shock is applied after policy effects and synergies, before clipping and scoring.
 * No invented resilience bonus: marginal contributions use the unchanged engine.
 * Price overspend follows the brief: invalid plans have no score, no auto-scaling.
 */
export function stressTest(plan: Choice[], eventId: StressEventId) {
  const errors = validate(plan);
  if (errors.length) throw new Error(errors.join(" "));
  const event = stressEvents.find(e => e.id === eventId);
  if (!event) throw new Error("Неизвестное событие.");
  const normal = projectEffects(plan);
  const cost = Math.round(budget(plan) * event.multiplier * 100) / 100;
  const deficit = Math.max(0, cost - BUDGET_LIMIT);
  const result = deficit > 0 ? null : projectEffects(plan, event.shock);
  const withoutPlan = projectEffects([], event.shock);
  const measures = plan.map(choice => {
    const rest = plan.filter(c => c.measureId !== choice.measureId);
    const regular = normal.score - projectEffects(rest).score;
    const stressed = result ? result.score - projectEffects(rest, event.shock).score : null;
    return { choice, regular, stressed, extraCost: (event.multiplier - 1) * budget([choice]), cost: budget([choice]) * event.multiplier };
  });
  return { event, normal, result, withoutPlan, cost, deficit, measures };
}
