import { useMemo } from "react";
import { directions, type Choice, type Direction } from "../data";
import { money } from "../money";
import { comparePlans, districtName, fmt, signed, type ComparisonValue } from "./analysis";

export interface ComparisonTarget {
  name: string;
  plan: Choice[];
  variantId?: string;
}

export default function Comparison({ plan, target, priorities }: {
  plan: Choice[];
  target: ComparisonTarget;
  priorities: Direction[];
}) {
  const comparison = useMemo(() => comparePlans(plan, target.plan, priorities), [plan, target.plan, priorities]);
  const identical = plan.length === target.plan.length && plan.every(choice =>
    target.plan.some(other => other.measureId === choice.measureId && other.districtId === choice.districtId));
  if (identical) return (
    <div className="comparison-empty" role="status">
      <h3>«{target.name}» совпадает с текущим планом</h3>
      <p>Измените меру и подведите итог, чтобы сравнить.</p>
    </div>
  );
  const rows: { label: string; value: ComparisonValue; format: (n: number) => string; neutral?: boolean; digits?: number }[] = [
    { label: "Балл (Score)", value: comparison.metrics.score, format: fmt },
    { label: "Бюджет", value: comparison.metrics.budget, format: (n) => `${money(n)} у.е.`, neutral: true, digits: 0 },
    { label: "Закрытые цели", value: comparison.metrics.goals, format: (n) => `${fmt(n, 0)} из ${fmt(comparison.goalCount, 0)}`, digits: 0 },
    { label: "Поддержка жителей", value: comparison.metrics.support, format: (n) => `${fmt(n)}%` },
    { label: "Минимум по ячейкам", value: comparison.metrics.minimum, format: fmt },
  ];
  return (
    <div className="plan-comparison">
      <h3>Текущий план против «{target.name}»</h3>
      <table className="comparison-table">
        <caption>Сравнение сценариев</caption>
        <thead><tr><th scope="col">Показатель</th><th scope="col">Текущий план</th><th scope="col">{target.name}</th><th scope="col">Разница</th></tr></thead>
        <tbody>
          {rows.map(({ label, value, format, neutral, digits }) => (
            <tr key={label}>
              <th scope="row">{label}</th><td>{format(value.current)}</td><td>{format(value.variant)}</td>
              <td className={neutral ? "" : deltaClass(value.delta)}>{signed(value.delta, digits)}{label === "Поддержка жителей" ? " п.п." : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="comparison-conclusion" role="status">{comparison.conclusion}</p>
      <table className="comparison-table comparison-districts">
        <caption>Разница по районам и направлениям</caption>
        <thead><tr><th scope="col">Район</th><th scope="col">Балл района</th>{directions.map((d) => <th scope="col" key={d}>{d}</th>)}</tr></thead>
        <tbody>
          {comparison.districts.map((row) => (
            <tr key={row.district}>
              <th scope="row">{districtName(row.district)}</th>
              <td className={deltaClass(row.score.delta)}>{signed(row.score.delta)}</td>
              {row.directions.map((d) => <td key={d.direction} className={deltaClass(d.delta)}>{signed(d.delta)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="section-note">Разница = текущий план − вариант. Плюс — текущий лучше, минус — вариант лучше.
        По направлениям: среднее двух показателей. Минимум — наименьшее из 50 значений «район × показатель».
        Меньший бюджет сам по себе не улучшает балл. Поддержка — расчёт модели жителей.</p>
    </div>
  );
}

function deltaClass(delta: number) {
  return delta > 0.005 ? "up" : delta < -0.005 ? "down" : "";
}
