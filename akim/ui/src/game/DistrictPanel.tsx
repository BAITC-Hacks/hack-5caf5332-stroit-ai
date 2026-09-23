import { useState } from "react";
import { ChevronDown, MessageCircle, X } from "lucide-react";
import {
  districts,
  indicatorNames,
  indicators,
  measures,
  type Choice,
  type DistrictId,
  type Indicator,
} from "../data";
import { baseline, type Projection } from "../engine";
import { blockReason, fmt, previewGain, signed } from "../planner/analysis";
import { shortNames } from "./labels";

const lowerFirst = (text: string) =>
  /^M\d/.test(text) ? text : text.charAt(0).toLocaleLowerCase("ru") + text.slice(1);

interface Props {
  districtId: DistrictId;
  plan: Choice[];
  projection: Projection;
  onAdd: (choice: Choice) => void;
  onClose: () => void;
  onAsk: () => void;
  onJump: (id: DistrictId) => void;
}

/** The turn panel: what hurts in this district and which decisions help it most. */
export default function DistrictPanel({ districtId, plan, projection, onAdd, onClose, onAsk, onJump }: Props) {
  const index = districts.findIndex((d) => d.id === districtId);
  const district = districts[index];
  const row = projection.districts[index];
  const base = baseline.districts[index];
  const [showAll, setShowAll] = useState(false);

  const options = measures
    .flatMap((m) => {
      const choice: Choice = m.type === "district" ? { measureId: m.id, districtId } : { measureId: m.id };
      const chosen = plan.find((c) => c.measureId === m.id);
      return [{ measure: m, choice, chosen, gain: previewGain(plan, choice), blocked: blockReason(plan, choice) }];
    })
    .sort((a, b) => Number(!!a.blocked) - Number(!!b.blocked) || b.gain - a.gain);
  const visible = showAll ? options : options.filter((o) => !o.blocked).slice(0, 5);
  const full = plan.length >= 5;

  return (
    <section className="side-panel glass" aria-labelledby="district-title">
      <header className="side-head">
        <div>
          <h2 id="district-title">{district.name}</h2>
          <p>
            {Math.round(district.population * 100)}% жителей города. Балл района{" "}
            <b>{fmt(row.score, 1)}</b>
            {Math.abs(row.score - base.score) > 0.05 && (
              <span className="delta up"> {signed(row.score - base.score, 1)}</span>
            )}
          </p>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Закрыть район">
          <X size={18} />
        </button>
      </header>

      <ul className="indicator-list" aria-label="Показатели района">
        {indicators.map((k: Indicator) => {
          const v = row.values[k];
          const d = row.delta[k];
          const need = district.needs.includes(k);
          return (
            <li key={k} className={v < 40 ? "critical" : need ? "need" : ""}>
              <span>{indicatorNames[k]}</span>
              <i className="bar" aria-hidden="true">
                <b style={{ width: `${v}%` }} />
              </i>
              <strong>
                {fmt(v, 0)}
                {Math.abs(d) > 0.05 && <small className={d < 0 ? "down" : "up"}>{signed(d, 1)}</small>}
              </strong>
            </li>
          );
        })}
      </ul>
      <p className="side-note">
        Красное ниже 40, минус 1 балл каждое. Жёлтым отмечено, о чём жители района просят чаще всего.
      </p>

      <blockquote className="side-voice">{district.voices[0]}</blockquote>

      <h3>{full ? "Все пять решений приняты" : "Что здесь построить"}</h3>
      {full ? (
        <p className="side-note">Уберите решение в корзине внизу, чтобы заменить его.</p>
      ) : (
        <ul className="decision-list">
          {visible.map(({ measure, choice, chosen, gain, blocked }) => (
            <li key={measure.id} className={blocked ? "blocked" : ""}>
              <div>
                <b>{shortNames[measure.id]}</b>
                <small>
                  {measure.type === "city" ? "весь город" : "этот район"}, {measure.cost} у.е.
                  {blocked ? ` — ${chosen ? "уже в плане" : lowerFirst(blocked)}` : ""}
                </small>
              </div>
              <button type="button" className="build" disabled={!!blocked} onClick={() => onAdd(choice)}>
                Построить <span>{blocked ? "—" : signed(gain)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {!full && !showAll && options.length > visible.length && (
        <button type="button" className="text-button more" onClick={() => setShowAll(true)}>
          Все 14 мер <ChevronDown size={14} />
        </button>
      )}
      <button type="button" className="text-button" onClick={onAsk}>
        <MessageCircle size={14} /> Что скажут жители?
      </button>
      <nav className="jump" aria-label="Другие районы">
        <span>Другие районы</span>
        {districts
          .filter((d) => d.id !== districtId)
          .map((d) => (
            <button key={d.id} type="button" onClick={() => onJump(d.id)}>
              {d.name}
            </button>
          ))}
      </nav>
    </section>
  );
}
