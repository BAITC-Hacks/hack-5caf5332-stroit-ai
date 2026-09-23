import { createPortal } from "react-dom";
import { choiceLabel, districts, measureById, type Choice, type Direction } from "../data";
import { baseline, budget, simulate } from "../engine";
import { money } from "../money";
import { pollProposal } from "../residents";
import { explain, fmt, goals, signed } from "./analysis";
import "./memo.css";

export default function LeadershipMemo({ plan, priorities }: { plan: Choice[]; priorities: Direction[] }) {
  const result = simulate(plan).result;
  if (!result) return null;
  const checklist = goals(plan, priorities);
  const brief = explain(plan, priorities);
  const poll = pollProposal(plan, "Мой план");
  return createPortal(<article className="leadership-memo" aria-label="Записка руководству">
    <header><p>Аким на 5 часов / Астана</p><h1>Записка по городскому сценарию</h1>
      <p>Горизонт: 8 кварталов. Синтетическая модель для сравнения решений.</p></header>
    <div className="memo-metrics">
      <div><span>Балл качества жизни</span><strong>{fmt(result.score)}</strong><small>{signed(result.score-baseline.score)} к исходным {fmt(baseline.score)}</small></div>
      <div><span>Бюджет</span><strong>{money(budget(plan))} / 100 у.е.</strong><small>Остаток {money(100-budget(plan))} у.е.</small></div>
      <div><span>Поддержка модели жителей</span><strong>{fmt(poll.approval, 1)}%</strong><small>Не реальный опрос населения</small></div>
    </div>
    <section><h2>Пять решений</h2><table><thead><tr><th>Мера и территория</th><th>Стоимость, у.е.</th></tr></thead>
      <tbody>{plan.map(c => <tr key={c.measureId}><td>{choiceLabel(c)}</td><td>{money(measureById(c.measureId).cost)}</td></tr>)}</tbody></table></section>
    <section><h2>Цели: выполнено {fmt(checklist.filter(g => g.met).length, 0)} из {fmt(checklist.length, 0)}</h2>
      <ul className="memo-goals">{checklist.map(g => <li key={g.id}><b>{g.met ? "Выполнено" : "Не выполнено"}.</b> {g.label}. <span>{g.detail}</span></li>)}</ul></section>
    <div className="memo-columns"><section><h2>Главные улучшения</h2><ul>{brief.strengths.slice(0, 2).map(text => <li key={text}>{text}</li>)}</ul></section>
      <section><h2>Главные риски</h2>{brief.risks.length ? <ul>{brief.risks.slice(0, 3).map(text => <li key={text}>{text}</li>)}</ul> : <p>Дополнительных рисков по правилам модели не выявлено.</p>}</section></div>
    <section><h2>Районы и поддержка жителей</h2><table><thead><tr><th>Район</th><th>Балл после плана</th><th>Изменение</th><th>Поддержка модели</th></tr></thead>
      <tbody>{result.districts.map((d, i) => <tr key={d.id}><td>{districts[i].name}</td><td>{fmt(d.score, 1)}</td><td>{signed(d.score-baseline.districts[i].score, 1)}</td><td>{fmt(poll.districts[i].approval, 1)}%</td></tr>)}</tbody></table></section>
    <footer>Источник расчёта: правила задания, исходные значения и эффекты мер. Поддержка: локальная модель 2 000 синтетических жителей. Реальные городские источники не меняют балл. Стресс-события в эту записку не включены.</footer>
  </article>, document.body);
}
