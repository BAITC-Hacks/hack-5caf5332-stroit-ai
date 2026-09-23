import { useMemo, useState } from "react";
import { FlaskConical } from "lucide-react";
import { choiceLabel, type Choice } from "../data";
import { money } from "../money";
import { fmt, signed } from "./analysis";
import { stressEvents, stressTest, type StressEventId } from "./stress";

export default function StressTest({ plan }: { plan: Choice[] }) {
  const [open, setOpen] = useState(false);
  const [eventId, setEventId] = useState<StressEventId>("flood");
  const test = useMemo(() => stressTest(plan, eventId), [plan, eventId]);
  return <section className="report-section stress-test" aria-labelledby="stress-title">
    <div className="comparison-heading">
      <div><h2 id="stress-title">Выдержит ли план неожиданность?</h2>
        <p className="section-note">Проверьте запас прочности при ЧП или росте цен.</p></div>
      <button type="button" className="secondary" aria-expanded={open} aria-controls="stress-result" onClick={() => setOpen(v => !v)}>
        <FlaskConical size={16} /> Что если
      </button>
    </div>
    {open && <div id="stress-result">
      <div className="stress-options" role="group" aria-label="Событие стресс-теста">
        {stressEvents.map(event => <button type="button" className="secondary" key={event.id} aria-pressed={eventId === event.id} onClick={() => setEventId(event.id)}>{event.name}</button>)}
      </div>
      <p className="stress-assumptions">{test.event.description}</p>
      <div className="stress-summary" role="status">
        <div><span>Без события</span><strong>{fmt(test.normal.score)}</strong></div>
        <div><span>При событии</span><strong>{test.result ? fmt(test.result.score) : "Не считается"}</strong></div>
        <div><span>Стоимость плана</span><strong>{money(test.cost)} у.е.</strong></div>
      </div>
      {test.result ? <p className="stress-verdict">
        Изменение балла: <b>{signed(test.result.score - test.normal.score)}</b>. Критических показателей: {fmt(test.normal.critical, 0)} → {fmt(test.result.critical, 0)}.
        {" "}Без ваших мер при том же событии: {fmt(test.withoutPlan.score)}. План удерживает {signed(test.result.score - test.withoutPlan.score)} балла.
      </p> : <p className="stress-deficit" role="alert">Не хватает {money(test.deficit)} у.е. Балл не считается: план превышает бюджет. Вернитесь к карте и замените дорогую меру; ни одно решение не отменено автоматически.</p>}
      <table className="comparison-table stress-measures">
        <caption>{test.result ? "Какие решения удерживают балл при событии" : "Какие решения стали дороже"}</caption>
        <thead><tr><th scope="col">Решение</th><th scope="col">{test.result ? "Вклад без события" : "Добавка к цене"}</th><th scope="col">{test.result ? "Вклад при событии" : "Цена при событии"}</th><th scope="col">Вывод</th></tr></thead>
        <tbody>{test.measures.map(row => <tr key={row.choice.measureId}>
          <th scope="row">{choiceLabel(row.choice)}</th>
          <td>{test.result ? signed(row.regular) : `${money(row.extraCost)} у.е.`}</td>
          <td>{row.stressed !== null ? signed(row.stressed) : `${money(row.cost)} у.е.`}</td>
          <td>{row.stressed === null ? "Нужно пересобрать бюджет" : row.stressed < -0.005 ? "Снижает балл" : row.stressed > 0.005 ? "Удерживает балл" : "Не меняет балл"}</td>
        </tr>)}</tbody>
      </table>
      <p className="section-note">Это условный стресс-тест, не прогноз ЧП. Вклад — потеря балла при удалении одной меры, с учётом порога 40 и синергий; вклады не складываются. Дополнительных бонусов защиты нет. Исходный план и его обычный балл сохранены.</p>
    </div>}
  </section>;
}
