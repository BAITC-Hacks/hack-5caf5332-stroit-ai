import { Check, Plus } from "lucide-react";
import {
  directions,
  districts,
  indicatorNames,
  measures,
  synergies,
  type Choice,
  type Indicator,
  type Measure,
} from "../data";
import { costs, money } from "../money";
import { blockReason, fmt, previewGain, signed } from "./analysis";

function effectsText(m: Measure) {
  return (Object.entries(m.effects) as [Indicator, number][])
    .map(([k, v]) => `${indicatorNames[k]} ${v > 0 ? "+" : "−"}${Math.abs(v)}`)
    .join(", ");
}

function synergyHint(m: Measure, plan: Choice[]) {
  const pair = synergies.find((s) => s.pair.includes(m.id));
  if (!pair) return null;
  const other = pair.pair[0] === m.id ? pair.pair[1] : pair.pair[0];
  const active = plan.some((c) => c.measureId === other);
  return active
    ? `С ${other} в плане: ${indicatorNames[pair.indicator].toLocaleLowerCase("ru")} +${pair.bonus}`
    : `Синергия с ${other}`;
}

export default function Catalog({
  plan,
  onAdd,
  onRemove,
}: {
  plan: Choice[];
  onAdd: (choice: Choice) => void;
  onRemove: (measureId: string) => void;
}) {
  return (
    <div className="catalog">
      {directions.map((direction) => {
        const used = plan.filter(
          (c) => measures.find((m) => m.id === c.measureId)!.direction === direction,
        ).length;
        return (
          <section key={direction} className="catalog-group" aria-labelledby={`dir-${direction}`}>
            <header>
              <h3 id={`dir-${direction}`}>{direction}</h3>
              <span className={used === 2 ? "cap-full" : ""}>
                {used} из 2
              </span>
            </header>
            <ul>
              {measures
                .filter((m) => m.direction === direction)
                .map((m) => (
                  <MeasureRow
                    key={m.id}
                    measure={m}
                    plan={plan}
                    onAdd={onAdd}
                    onRemove={onRemove}
                  />
                ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function MeasureRow({
  measure: m,
  plan,
  onAdd,
  onRemove,
}: {
  measure: Measure;
  plan: Choice[];
  onAdd: (choice: Choice) => void;
  onRemove: (measureId: string) => void;
}) {
  const chosen = plan.find((c) => c.measureId === m.id);
  const options: Choice[] =
    m.type === "city"
      ? [{ measureId: m.id }]
      : districts.map((d) => ({ measureId: m.id, districtId: d.id }));
  const rated = options.map((choice) => ({
    choice,
    gain: previewGain(plan, choice),
    blocked: blockReason(plan, choice),
  }));
  const best = Math.max(...rated.filter((r) => !r.blocked).map((r) => r.gain));
  const allBlocked = rated.every((r) => r.blocked);
  const effect = Math.round(((8 - m.lag) / 8) * 100);
  const synergy = synergyHint(m, plan);

  return (
    <li className={`measure ${chosen ? "is-chosen" : ""} ${allBlocked && !chosen ? "is-blocked" : ""}`}>
      <div className="measure-head">
        <span className="measure-id">{m.id}</span>
        <h4>{m.name}</h4>
        <span className="measure-cost">
          {money(m.cost)} <small>у.е.</small>
        </span>
      </div>
      <p className="measure-effects">{effectsText(m)}</p>
      <p className="measure-meta">
        {m.type === "city" ? "Весь город" : "Один район"}. Старт через {m.lag} кв.,
        за горизонт {effect}% эффекта.
        {synergy && <span className="measure-synergy"> {synergy}.</span>}
        <span className="measure-ref"> Справочно ~{money(costs[m.id].referenceMln)} млн ₸.</span>
      </p>
      {chosen ? (
        <div className="measure-actions">
          <span className="chosen-label">
            <Check size={15} aria-hidden="true" />
            В плане{chosen.districtId ? `: ${districts.find((d) => d.id === chosen.districtId)!.name}` : ""}
          </span>
          <button type="button" className="link-button" onClick={() => onRemove(m.id)}>
            Убрать
          </button>
        </div>
      ) : allBlocked ? (
        <p className="measure-block">{rated[0].blocked}</p>
      ) : (
        <div className={`measure-actions ${m.type === "district" ? "districts" : ""}`}>
          {rated.map(({ choice, gain, blocked }) => {
            const name = choice.districtId
              ? districts.find((d) => d.id === choice.districtId)!.name
              : "Добавить";
            const isBest = !blocked && gain === best && gain > 0.005;
            return (
              <button
                key={choice.districtId ?? "city"}
                type="button"
                className={`option ${isBest ? "is-best" : ""}`}
                disabled={!!blocked}
                title={blocked ?? `Балл ${signed(gain)}`}
                onClick={() => onAdd(choice)}
                aria-label={`${m.name}${choice.districtId ? `, ${name}` : ""}: балл ${signed(gain)}${blocked ? `. ${blocked}` : ""}`}
              >
                {m.type === "city" && <Plus size={14} aria-hidden="true" />}
                <span>{name}</span>
                <b>{blocked ? "—" : signed(gain)}</b>
              </button>
            );
          })}
        </div>
      )}
      {!chosen && !allBlocked && rated.some((r) => r.blocked) && m.type === "district" && (
        <p className="measure-note">
          Недоступно в части районов: {rated.find((r) => r.blocked)!.blocked}
        </p>
      )}
      {!chosen && !allBlocked && best <= 0.005 && (
        <p className="measure-note">Сейчас не добавляет баллов: {fmt(best)}.</p>
      )}
    </li>
  );
}
