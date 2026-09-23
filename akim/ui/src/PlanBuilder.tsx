import { BUDGET_LIMIT, money, costs } from "./money";
import { useState } from "react";
import {
  ArrowUpRight,
  Check,
  ChevronDown,
  Plus,
  RotateCcw,
  Trash2,
  X,
} from "lucide-react";
import {
  districts,
  directions,
  measures,
  measureById,
  indicatorNames,
  indicators,
  samplePlan,
  choiceLabel,
  type Choice,
  type DistrictId,
  type Direction,
  type Indicator,
} from "./data";
import {
  baseline,
  budget,
  simulate,
  validate,
  type Projection,
} from "./engine";
export const fmt = (n: number, d = 2) =>
  n.toLocaleString("ru-RU", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  });
export function Changes({ result }: { result: Projection }) {
  const changes = result.districts
    .flatMap((d, i) =>
      indicators.map((k) => ({
        district: districts[i].name,
        key: k,
        delta: d.delta[k],
        value: d.values[k],
      })),
    )
    .filter((c) => c.delta !== 0)
    .sort((a, b) => b.delta - a.delta);
  const losses = changes.filter((c) => c.delta < 0);
  const weakest = result.districts.reduce((a, b) =>
    a.score < b.score ? a : b,
  );
  return (
    <div className="changes">
      <div className="section-label">Что изменится за 2 года</div>
      {changes.slice(0, 3).map((c) => (
        <div className="change-row" key={c.district + c.key}>
          <span>
            {indicatorNames[c.key]}
            <small>{c.district}</small>
          </span>
          <strong>+{fmt(c.delta)}</strong>
        </div>
      ))}
      <div className="tradeoff">
        <b>Цена выбора</b>
        <p>
          {losses.length
            ? losses
                .map(
                  (c) =>
                    `${c.district}: ${indicatorNames[c.key].toLowerCase()} ${fmt(c.delta)}.`,
                )
                .join(" ")
            : "Прямых ухудшений показателей нет. Но бюджет ограничен: нерешённые потребности остаются."}{" "}
          Самый низкий балл — {districts.find((d) => d.id === weakest.id)!.name}
          : {fmt(weakest.score)}. Критических показателей: {result.critical}.
        </p>
      </div>
    </div>
  );
}
interface Props {
  plan: Choice[];
  onChange: (p: Choice[]) => void;
  selected: DistrictId | null;
  onClose: () => void;
  onAsk: () => void;
  onAdvisor: () => void;
}
export default function PlanBuilder({
  plan,
  onChange,
  selected,
  onClose,
  onAsk,
  onAdvisor,
}: Props) {
  const [targets, setTargets] = useState<Record<string, DistrictId | "">>({});
  const [filter, setFilter] = useState<Direction | "Все">("Все");
  const [showResults, setShowResults] = useState(true);
  const spent = budget(plan),
    { result, errors } = simulate(plan);
  return (
    <section
      className="panel plan-panel glass"
      role="dialog"
      aria-labelledby="plan-title"
    >
      <div className="panel-heading">
        <div>
          <div className="eyebrow">ВАШИ РЕШЕНИЯ · 2 ГОДА</div>
          <h2 id="plan-title">План для города</h2>
        </div>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Закрыть план"
        >
          <X size={20} />
        </button>
      </div>
      <div className="budget-area">
        <div className="budget-line">
          <span>Бюджет</span>
          <strong>
            {money(spent)}
            <span> / {money(BUDGET_LIMIT)} млн ₸</span>
          </strong>
          <small>Осталось {money(BUDGET_LIMIT - spent)}</small>
        </div>
        <div className="budget-track">
          <i
            style={{ width: `${Math.min(100, (spent / BUDGET_LIMIT) * 100)}%` }}
          />
        </div>
        <div className="slots" aria-label={`${plan.length} из 5 решений`}>
          {Array.from({ length: 5 }, (_, i) => {
            const c = plan[i];
            return (
              <button
                key={i}
                disabled={!c}
                className={c ? "filled" : ""}
                title={c ? `Убрать: ${choiceLabel(c)}` : `Решение ${i + 1}`}
                aria-label={
                  c ? `Убрать ${c.measureId}` : `Пустое решение ${i + 1}`
                }
                onClick={() => onChange(plan.filter((_, j) => j !== i))}
              >
                {c ? (
                  <>
                    <span>{c.measureId}</span>
                    <X size={12} />
                  </>
                ) : (
                  <>
                    <Plus size={13} />
                    <span>{i + 1}</span>
                  </>
                )}
              </button>
            );
          })}
        </div>
        <div className="plan-rule">
          <span>{plan.length} из 5 решений</span>
          <span>Не более 2 в одном направлении</span>
        </div>
      </div>
      <div className="panel-scroll">
        {!plan.length && (
          <button
            className="demo-banner"
            onClick={() => onChange(samplePlan.map((c) => ({ ...c })))}
          >
            <span>
              <b>Начните с готового сценария</b>
              <small>
                Школы, здоровье и безопасность · {money(budget(samplePlan))} млн
                ₸
              </small>
            </span>
            <ArrowUpRight size={20} />
          </button>
        )}
        {result && (
          <div className="plan-result">
            <button
              className="result-heading"
              onClick={() => setShowResults(!showResults)}
              aria-expanded={showResults}
            >
              <div>
                <div className="section-label">КАЧЕСТВО ЖИЗНИ АСТАНЫ</div>
                <strong>
                  {fmt(result.score)}{" "}
                  <small>+{fmt(result.score - baseline.score)}</small>
                </strong>
              </div>
              <ChevronDown size={18} />
            </button>
            {showResults && (
              <>
                <Changes result={result} />
                <div className="result-actions">
                  <button onClick={onAsk}>Спросить жителей</button>
                  <button className="dark" onClick={onAdvisor}>
                    Совет акима <ArrowUpRight size={14} />
                  </button>
                </div>
              </>
            )}
          </div>
        )}
        {plan.length === 5 && errors.length > 0 && (
          <p className="inline-error" role="alert">
            {errors.join(" ")}
          </p>
        )}
        <div className="catalog-heading">
          <h3>
            Каталог мер <span>14</span>
          </h3>
          {plan.length > 0 && (
            <button className="text-button" onClick={() => onChange([])}>
              <RotateCcw size={13} />
              Сбросить
            </button>
          )}
        </div>
        <div className="filter-tabs" aria-label="Направления">
          {(["Все", ...directions] as const).map((d) => (
            <button
              key={d}
              className={filter === d ? "active" : ""}
              onClick={() => setFilter(d)}
              aria-pressed={filter === d}
            >
              {d}
            </button>
          ))}
        </div>
        {directions
          .filter((d) => filter === "Все" || filter === d)
          .map((direction) => (
            <div className="measure-group" key={direction}>
              <div className="group-heading">
                <i
                  className={`direction-dot direction-${directions.indexOf(direction)}`}
                />
                {direction}
                <span>
                  {
                    plan.filter(
                      (c) => measureById(c.measureId).direction === direction,
                    ).length
                  }
                  /2
                </span>
              </div>
              {measures
                .filter((m) => m.direction === direction)
                .map((m) => {
                  const chosen = plan.find((c) => c.measureId === m.id);
                  const target = targets[m.id] ?? selected ?? "";
                  const candidate: Choice = {
                    measureId: m.id,
                    ...(m.type === "district" && target
                      ? { districtId: target }
                      : {}),
                  };
                  const blockers = validate([...plan, candidate], true);
                  const reason = blockers[0];
                  return (
                    <article
                      className={`measure-card ${chosen ? "chosen" : ""}`}
                      key={m.id}
                      data-testid={`measure-${m.id}`}
                    >
                      <div className="measure-top">
                        <span className="measure-id">{m.id}</span>
                        <span>
                          {m.type === "city" ? "Весь город" : "Один район"} ·
                          Старт: {m.lag} кв.
                        </span>
                        <strong>
                          {money(m.cost)} <small>млн ₸</small>
                        </strong>
                      </div>
                      <h4>{m.name}</h4>
                      <details className="cost-basis">
                        <summary>
                          {costs[m.id].kind === "benchmark"
                            ? "Цена по ориентиру"
                            : "Оценка стоимости"}
                        </summary>
                        <p>{costs[m.id].basis}</p>
                        {costs[m.id].source && (
                          <a
                            href={costs[m.id].source}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Официальный источник ↗
                          </a>
                        )}
                      </details>
                      <p className="measure-effects">
                        {Object.entries(m.effects)
                          .map(
                            ([key, v]) =>
                              `${indicatorNames[key as Indicator]} ${v > 0 ? "+" : ""}${fmt((v * (8 - m.lag)) / 8)}`,
                          )
                          .join(" · ")}
                      </p>
                      <div className="measure-bottom">
                        {chosen ? (
                          <span className="chosen-label">
                            <Check size={14} />
                            {chosen.districtId
                              ? districts.find(
                                  (d) => d.id === chosen.districtId,
                                )!.name
                              : "Весь город"}
                          </span>
                        ) : m.type === "district" ? (
                          <select
                            aria-label={`Район для ${m.id}`}
                            value={target}
                            onChange={(e) =>
                              setTargets({
                                ...targets,
                                [m.id]: e.target.value as DistrictId,
                              })
                            }
                          >
                            <option value="">Выберите район</option>
                            {districts.map((d) => (
                              <option key={d.id} value={d.id}>
                                {d.name}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <span className="citywide-label">Все 5 районов</span>
                        )}
                        <button
                          className={chosen ? "remove-measure" : "add-measure"}
                          aria-label={
                            chosen ? `Удалить ${m.id}` : `Добавить ${m.id}`
                          }
                          disabled={!chosen && !!reason}
                          title={!chosen ? reason : undefined}
                          onClick={() =>
                            onChange(
                              chosen
                                ? plan.filter((c) => c.measureId !== m.id)
                                : [...plan, candidate],
                            )
                          }
                        >
                          {chosen ? <Trash2 size={15} /> : <Plus size={17} />}
                        </button>
                      </div>
                      {!chosen && reason && (
                        <small className="block-reason">{reason}</small>
                      )}
                    </article>
                  );
                })}
            </div>
          ))}
      </div>
    </section>
  );
}
