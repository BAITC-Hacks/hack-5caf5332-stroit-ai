import { ArrowRight, X } from "lucide-react";
import { measureById, type Choice } from "../data";
import { baseline, budget } from "../engine";
import { BUDGET_LIMIT } from "../money";
import { fmt, signed } from "../planner/analysis";
import { shortLabel } from "./labels";

interface Props {
  plan: Choice[];
  score: number;
  errors: string[];
  onRemove: (measureId: string) => void;
  onReport: () => void;
}

/** Bottom tray: five slots, budget and the score against the start. */
export default function Tray({ plan, score, errors, onRemove, onReport }: Props) {
  const spent = budget(plan);
  const gain = score - baseline.score;
  const ready = plan.length === 5 && errors.length === 0;
  const hint =
    plan.length < 5
      ? `Осталось ${5 - plan.length} из 5. Нажмите на район на карте.`
      : errors[0] ?? "Все пять решений приняты.";
  return (
    <div className="tray glass" role="region" aria-label="Ваши решения">
      <div className="tray-score">
        <small>Качество жизни</small>
        <strong>{fmt(score)}</strong>
        <span className={gain > 0.005 ? "up" : gain < -0.005 ? "down" : ""}>
          {Math.abs(gain) > 0.005 ? signed(gain) : `старт ${fmt(baseline.score)}`}
        </span>
      </div>
      <div className="tray-main">
        <ol className="tray-slots">
          {Array.from({ length: 5 }, (_, i) => {
            const c = plan[i];
            return (
              <li key={i} className={c ? "filled" : ""}>
                {c ? (
                  <>
                    <span>{shortLabel(c)}</span>
                    <button type="button" onClick={() => onRemove(c.measureId)} aria-label={`Убрать: ${shortLabel(c)}`}>
                      <X size={13} />
                    </button>
                  </>
                ) : (
                  <span className="empty">{i + 1}</span>
                )}
              </li>
            );
          })}
        </ol>
        <div className="tray-budget">
          <i className="bar" aria-hidden="true">
            {plan.map((c) => (
              <b key={c.measureId} style={{ width: `${(measureById(c.measureId).cost / BUDGET_LIMIT) * 100}%` }} />
            ))}
          </i>
          <span>
            {spent} из {BUDGET_LIMIT} у.е.
          </span>
          <em className={plan.length === 5 && errors.length ? "error" : ""} role="status">
            {hint}
          </em>
        </div>
      </div>
      <button type="button" className="tray-go" disabled={!ready} onClick={onReport}>
        Подвести итог <ArrowRight size={16} />
      </button>
    </div>
  );
}
