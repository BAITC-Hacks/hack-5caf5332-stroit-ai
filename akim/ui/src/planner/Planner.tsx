import { useEffect, useRef, useState } from "react";
import { ArrowRight, Map, X } from "lucide-react";
import {
  choiceLabel,
  directions,
  indicatorNames,
  measureById,
  samplePlan,
  type Choice,
  type Direction,
} from "../data";
import { baseline, budget, projectEffects, validate } from "../engine";
import { BUDGET_LIMIT, money } from "../money";
import Catalog from "./Catalog";
import Matrix from "./Matrix";
import Report from "./Report";
import ScoreGauge from "./ScoreGauge";
import {
  criticalCells,
  decodePlan,
  districtName,
  encodePlan,
  fmt,
  goals,
  inDistrict,
  lower,
  weakestDistrict,
} from "./analysis";

type Step = "city" | "plan" | "report";
const steps: { id: Step; label: string }[] = [
  { id: "city", label: "Город" },
  { id: "plan", label: "Решения" },
  { id: "report", label: "Итог" },
];

function readUrl() {
  const params = new URLSearchParams(window.location.search);
  const plan = decodePlan(params.get("plan"));
  const priorities = (params.get("focus") ?? "")
    .split(",")
    .filter((d): d is Direction => (directions as readonly string[]).includes(d))
    .slice(0, 2);
  const step: Step =
    params.get("step") === "report" && validate(plan).length === 0
      ? "report"
      : plan.length
        ? "plan"
        : "city";
  return { plan, priorities, step };
}

export default function Planner() {
  const initial = useRef(readUrl()).current;
  const [step, setStep] = useState<Step>(initial.step);
  const [plan, setPlan] = useState<Choice[]>(initial.plan);
  const [priorities, setPriorities] = useState<Direction[]>(initial.priorities);
  const main = useRef<HTMLElement>(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (plan.length) params.set("plan", encodePlan(plan));
    if (priorities.length) params.set("focus", priorities.join(","));
    if (step === "report") params.set("step", "report");
    const query = params.toString();
    window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
  }, [plan, priorities, step]);

  const go = (next: Step) => {
    setStep(next);
    window.scrollTo({ top: 0 });
    requestAnimationFrame(() => main.current?.focus({ preventScroll: true }));
  };

  const errors = validate(plan);
  const ready = errors.length === 0;
  const projection = projectEffects(plan);

  return (
    <div className="planner">
      <a className="skip-link" href="#planner-main">
        Перейти к содержимому
      </a>
      <header className="topbar">
        <div className="brand">
          <b>Аким на 5 часов</b>
          <span>Астана, синтетические данные задания</span>
        </div>
        <nav aria-label="Шаги">
          <ol className="steps">
            {steps.map((s, i) => {
              const disabled = s.id === "report" && !ready;
              return (
                <li key={s.id}>
                  <button
                    type="button"
                    aria-current={step === s.id ? "step" : undefined}
                    disabled={disabled}
                    onClick={() => go(s.id)}
                  >
                    <span className="step-number">{i + 1}</span>
                    {s.label}
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>
        <a className="map-link" href="/">
          <Map size={15} aria-hidden="true" />
          Карта с жителями
        </a>
      </header>

      <main id="planner-main" ref={main} tabIndex={-1}>
        {step === "city" && (
          <CityStep
            priorities={priorities}
            setPriorities={setPriorities}
            onNext={() => go("plan")}
            onSample={() => {
              setPlan(samplePlan.map((c) => ({ ...c })));
              go("report");
            }}
          />
        )}
        {step === "plan" && (
          <div className="workspace">
            <div className="workspace-main">
              <section aria-labelledby="plan-title">
                <h1 id="plan-title">Пять решений на 100 у.е.</h1>
                <p className="lead">
                  Цифра на кнопке показывает, насколько изменится балл, если
                  добавить решение сейчас. Для районных мер сравните районы: одна
                  и та же школа даёт разный эффект.
                </p>
              </section>
              <Matrix
                projection={projection}
                showDelta
                caption="Город с учётом выбранных решений"
              />
              <Catalog
                plan={plan}
                onAdd={(choice) => setPlan((p) => [...p, choice])}
                onRemove={(id) => setPlan((p) => p.filter((c) => c.measureId !== id))}
              />
            </div>
            <PlanRail
              plan={plan}
              priorities={priorities}
              errors={errors}
              onRemove={(id) => setPlan((p) => p.filter((c) => c.measureId !== id))}
              onClear={() => setPlan([])}
              onReport={() => go("report")}
            />
            <div className="mobile-bar" aria-hidden="true">
              <div>
                <strong>{fmt(projection.score)}</strong>
                <span>
                  {plan.length} из 5, {money(budget(plan))} из {BUDGET_LIMIT} у.е.
                </span>
              </div>
              <button
                type="button"
                className="primary"
                tabIndex={-1}
                disabled={!ready}
                onClick={() => go("report")}
              >
                Итог
                <ArrowRight size={16} />
              </button>
            </div>
          </div>
        )}
        {step === "report" && ready && (
          <Report
            plan={plan}
            priorities={priorities}
            onApply={(next) => {
              setPlan(next);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
            onEdit={() => go("plan")}
          />
        )}
      </main>
    </div>
  );
}

function CityStep({
  priorities,
  setPriorities,
  onNext,
  onSample,
}: {
  priorities: Direction[];
  setPriorities: (p: Direction[]) => void;
  onNext: () => void;
  onSample: () => void;
}) {
  const critical = criticalCells(baseline);
  const weakest = weakestDistrict(baseline);
  const toggle = (d: Direction) =>
    setPriorities(
      priorities.includes(d)
        ? priorities.filter((p) => p !== d)
        : [...priorities, d].slice(-2),
    );
  return (
    <div className="city-step">
      <section className="city-intro" aria-labelledby="city-title">
        <div>
          <h1 id="city-title">Город до ваших решений</h1>
          <p className="lead">
            У всех команд одинаковые данные и бюджет 100 у.е. Нужно принять ровно
            пять решений так, чтобы качество жизни выросло и ни один район не
            остался позади.
          </p>
          <dl className="rules">
            <div>
              <dt>70%</dt>
              <dd>балла даёт средний район с учётом числа жителей</dd>
            </div>
            <div>
              <dt>30%</dt>
              <dd>
                балла даёт самый слабый район. Сейчас это {districtName(weakest.id)},{" "}
                {fmt(weakest.score, 1)}
              </dd>
            </div>
            <div>
              <dt>−1</dt>
              <dd>
                за каждый показатель ниже 40. Сейчас их {critical.length}:{" "}
                {critical
                  .map((c) => `${lower(indicatorNames[c.indicator])} ${inDistrict(c.district)}`)
                  .join(", ")}
              </dd>
            </div>
          </dl>
        </div>
        <ScoreGauge score={baseline.score} />
      </section>

      <Matrix projection={baseline} showDelta={false} caption="Показатели районов сейчас, шкала 0–100" />

      <section className="focus" aria-labelledby="focus-title">
        <h2 id="focus-title">Что для вас главное</h2>
        <p>
          Выберите до двух направлений. В итоге проверим, подкреплены ли они
          решениями, а не только баллом.
        </p>
        <div className="focus-options" role="group" aria-labelledby="focus-title">
          {directions.map((d) => (
            <button
              key={d}
              type="button"
              aria-pressed={priorities.includes(d)}
              onClick={() => toggle(d)}
            >
              {d}
            </button>
          ))}
        </div>
        <div className="city-actions">
          <button type="button" className="primary" onClick={onNext}>
            Выбрать решения
            <ArrowRight size={16} aria-hidden="true" />
          </button>
          <button type="button" className="link-button" onClick={onSample}>
            Посмотреть итог на примере из задания
          </button>
        </div>
      </section>
    </div>
  );
}


function PlanRail({
  plan,
  priorities,
  errors,
  onRemove,
  onClear,
  onReport,
}: {
  plan: Choice[];
  priorities: Direction[];
  errors: string[];
  onRemove: (id: string) => void;
  onClear: () => void;
  onReport: () => void;
}) {
  const spent = budget(plan);
  const projection = projectEffects(plan);
  const checklist = plan.length === 5 ? goals(plan, priorities) : [];
  const hint =
    plan.length < 5
      ? `Осталось выбрать ${5 - plan.length} из 5.`
      : errors[0] ?? "План готов к итогу.";
  return (
    <aside className="rail" aria-label="Ваш план">
      <ScoreGauge score={projection.score} compact />
      <div className="budget">
        <div className="budget-line">
          <span>Бюджет</span>
          <b>
            {money(spent)} <small>из {BUDGET_LIMIT} у.е.</small>
          </b>
        </div>
        <div
          className={`budget-bar ${spent > BUDGET_LIMIT ? "over" : ""}`}
          role="meter"
          aria-valuemin={0}
          aria-valuemax={BUDGET_LIMIT}
          aria-valuenow={spent}
          aria-label="Потрачено из бюджета"
        >
          {plan.map((c) => (
            <span
              key={c.measureId}
              style={{ width: `${(measureById(c.measureId).cost / BUDGET_LIMIT) * 100}%` }}
              title={choiceLabel(c)}
            />
          ))}
        </div>
      </div>
      <ol className="slots">
        {Array.from({ length: 5 }, (_, i) => {
          const c = plan[i];
          return (
            <li key={i} className={c ? "filled" : ""}>
              {c ? (
                <>
                  <span className="slot-id">{c.measureId}</span>
                  <span className="slot-name">{choiceLabel(c)}</span>
                  <button
                    type="button"
                    className="icon-button"
                    onClick={() => onRemove(c.measureId)}
                    aria-label={`Убрать ${choiceLabel(c)}`}
                  >
                    <X size={14} aria-hidden="true" />
                  </button>
                </>
              ) : (
                <span className="slot-empty">Решение {i + 1}</span>
              )}
            </li>
          );
        })}
      </ol>
      {checklist.length > 0 && (
        <ul className="mini-goals" aria-label="Цели">
          {checklist.map((g) => (
            <li key={g.id} className={g.met ? "met" : "missed"}>
              {g.label}
            </li>
          ))}
        </ul>
      )}
      <p className={`rail-hint ${plan.length === 5 && errors.length ? "error" : ""}`} role="status">
        {hint}
      </p>
      <button type="button" className="primary wide" disabled={errors.length > 0} onClick={onReport}>
        Подвести итог
        <ArrowRight size={16} aria-hidden="true" />
      </button>
      {plan.length > 0 && (
        <button type="button" className="link-button" onClick={onClear}>
          Очистить план
        </button>
      )}
    </aside>
  );
}
