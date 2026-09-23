import { useEffect, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCheck,
  LoaderCircle,
  Sparkles,
  X,
} from "lucide-react";
import { choiceLabel, type Choice, directions, districts } from "./data";
import {
  advise,
  autopilot,
  budget,
  projectEffects,
  simulate,
  type Alternative,
  type Projection,
} from "./engine";
import { pollProposal } from "./residents";
import { fmt } from "./PlanBuilder";
import { AiModeSwitch, akimApi, useServices } from "./services";
import type { ActivityEvent } from "./city-data";
import type { AkimResult } from "../server/akim";
import type { GoalConstraints } from "../server/schemas";
import { BUDGET_LIMIT, money } from "./money";
interface Props {
  plan: Choice[];
  onChange: (plan: Choice[]) => void;
  onClose: () => void;
  onBuild: () => void;
}
const steps = [
  "Проверка бюджета",
  "Симуляция сценария",
  "Опрос жителей",
  "Сравнение альтернатив",
];
export default function AkimPanel({ plan, onChange, onClose, onBuild }: Props) {
  const services = useServices();
  const [liveResult, setLiveResult] = useState<AkimResult | null>(null);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [mode, setMode] = useState<"advisor" | "autopilot" | "goal">("advisor");
  const [goal, setGoal] = useState("");
  const [constraints, setConstraints] = useState<GoalConstraints>({
    priorities: [],
    protectedDistricts: [],
    minSupportPercent: 0,
    reserveUnits: 0,
    mustInclude: [],
    mustExclude: [],
  });
  const [submittedGoal, setSubmittedGoal] = useState<{
    serviceMode: "live" | "local";
    goal: string;
    constraints: GoalConstraints;
  } | null>(null);
  const [step, setStep] = useState(0);
  const [alternative, setAlternative] = useState<Alternative | null>(null);
  const [proposed, setProposed] = useState<Choice[] | null>(null);
  const [projection, setProjection] = useState<Projection | null>(null);
  const [approval, setApproval] = useState<number | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const current = mode === "goal" ? projectEffects(plan) : simulate(plan).result;
  const blocked = mode === "advisor" && !current;
  const usesApi = services.mode === "live" || mode === "goal";
  const busy = usesApi && attempt > 0 && !liveResult && !error;
  useEffect(() => {
    setStep(0);
    setAlternative(null);
    setProposed(null);
    setProjection(null);
    setApproval(null);
    setDismissed(false);
    setError("");
    setEvents([]);
    setLiveResult(null);
    if (blocked) return;
    if (services.mode === "live" || mode === "goal") {
      if (attempt === 0) return;
      if (mode === "goal" && submittedGoal?.serviceMode !== services.mode) {
        setAttempt(0);
        return;
      }
      const controller = new AbortController();
      akimApi(
        mode,
        plan,
        services.health?.token ?? "",
        (event) => setEvents((old) => [...old, event]),
        controller.signal,
        mode === "goal" && services.mode === "live"
          ? submittedGoal?.goal
          : undefined,
        mode === "goal" && services.mode === "local"
          ? submittedGoal?.constraints
          : undefined,
      )
        .then((answer) => {
          if (controller.signal.aborted) return;
          setLiveResult(answer);
          setProposed(answer.plan);
          setProjection(answer.result);
          setStep(4);
          if (mode === "advisor") {
            const same = (a: Choice, b: Choice) =>
              a.measureId === b.measureId && a.districtId === b.districtId;
            const removed = plan.find(
              (a) => !answer.plan.some((b) => same(a, b)),
            );
            const added = answer.plan.find(
              (a) => !plan.some((b) => same(a, b)),
            );
            if (removed && added)
              setAlternative({
                plan: answer.plan,
                removed,
                added,
                result: answer.result,
                improvement: answer.result.score - (current?.score ?? 0),
              });
          }
        })
        .catch((e) => {
          if (!controller.signal.aborted) setError(e.message);
        });
      return () => controller.abort();
    }
    let next: Choice[] = plan;
    const timers = [
      window.setTimeout(() => {
        budget(plan);
        setStep(1);
      }, 240),
      window.setTimeout(() => {
        simulate(plan);
        setStep(2);
      }, 500),
      window.setTimeout(() => {
        setApproval(
          pollProposal(mode === "autopilot" ? autopilot() : plan, "").approval,
        );
        setStep(3);
      }, 780),
      window.setTimeout(() => {
        if (mode === "advisor") {
          const suggestion = advise(plan);
          setAlternative(suggestion);
          if (suggestion) next = suggestion.plan;
        } else next = autopilot();
        setProposed(next);
        setProjection(simulate(next).result);
        setStep(4);
      }, 1060),
    ];
    return () => timers.forEach(clearTimeout);
  }, [
    plan, mode, blocked, services.mode, services.health?.token,
    attempt, submittedGoal,
  ]);
  const apply = () => {
    if (proposed) {
      onChange(proposed);
      onClose();
    }
  };
  return (
    <section
      className="panel akim-panel glass"
      style={{ zIndex: 9 }}
      role="dialog"
      aria-labelledby="akim-title"
    >
      <div className="panel-heading">
        <div className="akim-heading">
          <span className="akim-avatar">
            <Sparkles size={23} />
          </span>
          <div>
            <div className="eyebrow">ВАШ ГОРОДСКОЙ СОВЕТНИК</div>
            <h2 id="akim-title">AI Аким</h2>
          </div>
        </div>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Закрыть AI Акима"
        >
          <X size={20} />
        </button>
      </div>
      <div className="mode-tabs">
        <button
          aria-pressed={mode === "advisor"}
          className={mode === "advisor" ? "active" : ""}
          onClick={() => {
            setAttempt(0);
            setMode("advisor");
          }}
        >
          Советник
        </button>
        <button
          aria-pressed={mode === "autopilot"}
          className={mode === "autopilot" ? "active" : ""}
          onClick={() => {
            setAttempt(0);
            setMode("autopilot");
          }}
        >
          Автопилот
        </button>
        <button
          aria-pressed={mode === "goal"}
          className={mode === "goal" ? "active" : ""}
          onClick={() => {
            setAttempt(0);
            setMode("goal");
          }}
        >
          Цель
        </button>
      </div>
      <AiModeSwitch />
      <div className="panel-scroll">
        {blocked ? (
          <div className="empty-state">
            <Sparkles size={36} />
            <h3>Сначала — ваши пять решений</h3>
            <p>
              Я проверю готовый план, покажу компромиссы и сравню его с
              конкретной заменой.
            </p>
            <button className="dark wide" onClick={onBuild}>
              Собрать план <ArrowUpRight size={16} />
            </button>
            <p>Или откройте «Автопилот», чтобы посмотреть мой вариант.</p>
          </div>
        ) : (
          <>
            {mode === "goal" && (
              <form
                className="akim-start"
                style={{ display: "grid", gap: 12, fontSize: 12 }}
                onSubmit={(e) => {
                  e.preventDefault();
                  setSubmittedGoal({
                    serviceMode: services.mode,
                    goal: goal.trim(),
                    constraints,
                  });
                  setAttempt((n) => n + 1);
                }}
              >
                {services.mode === "live" ? (
                  <>
                    <label htmlFor="akim-goal">Цель словами</label>
                    <div className="question-field">
                      <textarea
                        id="akim-goal"
                        rows={4}
                        maxLength={300}
                        required
                        disabled={busy}
                        placeholder="Например: экология в приоритете, Есиль не трогать, поддержка не ниже 60%, оставить 10 у.е. в резерве"
                        value={goal}
                        onChange={(e) => setGoal(e.target.value)}
                      />
                    </div>
                  </>
                ) : (
                  <fieldset
                    disabled={busy}
                    style={{ border: 0, padding: 0, margin: 0 }}
                  >
                    <legend>Ограничения цели</legend>
                    <p className="demo-note">
                      Выберите ограничения для локального поиска.
                    </p>
                    <fieldset style={{ border: 0, padding: "8px 0" }}>
                      <legend>Приоритеты</legend>
                      <div
                        style={{ display: "flex", flexWrap: "wrap", gap: "6px 12px" }}
                      >
                        {directions.map((direction) => (
                          <label key={direction}>
                            <input
                              type="checkbox"
                              checked={constraints.priorities.includes(direction)}
                              onChange={(e) =>
                                setConstraints((old) => ({
                                  ...old,
                                  priorities: e.target.checked
                                    ? [...old.priorities, direction]
                                    : old.priorities.filter((d) => d !== direction),
                                }))
                              }
                            />{" "}
                            {direction}
                          </label>
                        ))}
                      </div>
                    </fieldset>
                    <fieldset style={{ border: 0, padding: "8px 0" }}>
                      <legend>Защищённые районы</legend>
                      <div
                        style={{ display: "flex", flexWrap: "wrap", gap: "6px 12px" }}
                      >
                        {districts.map((district) => (
                          <label key={district.id}>
                            <input
                              type="checkbox"
                              checked={constraints.protectedDistricts.includes(district.id)}
                              onChange={(e) =>
                                setConstraints((old) => ({
                                  ...old,
                                  protectedDistricts: e.target.checked
                                    ? [...old.protectedDistricts, district.id]
                                    : old.protectedDistricts.filter((id) => id !== district.id),
                                }))
                              }
                            />{" "}
                            {district.name}
                          </label>
                        ))}
                      </div>
                    </fieldset>
                    <p className="demo-note">
                      Балл защищённого района не должен снижаться относительно
                      исходного состояния города.
                    </p>
                    <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
                      <label style={{ flex: 1, minWidth: 0 }}>
                        Поддержка не ниже, %
                        <input
                          type="number"
                          min={0}
                          max={100}
                          step="any"
                          required
                          style={{ width: "100%" }}
                          value={constraints.minSupportPercent}
                          onChange={(e) =>
                            setConstraints((old) => ({
                              ...old,
                              minSupportPercent: Number(e.target.value),
                            }))
                          }
                        />
                      </label>
                      <label style={{ flex: 1, minWidth: 0 }}>
                        Резерв, у.е.
                        <input
                          type="number"
                          min={0}
                          max={BUDGET_LIMIT}
                          step="any"
                          required
                          style={{ width: "100%" }}
                          value={constraints.reserveUnits}
                          onChange={(e) =>
                            setConstraints((old) => ({
                              ...old,
                              reserveUnits: Number(e.target.value),
                            }))
                          }
                        />
                      </label>
                    </div>
                  </fieldset>
                )}
                <button
                  type="submit"
                  className="dark wide"
                  disabled={
                    busy || !services.health ||
                    (services.mode === "live" && !goal.trim())
                  }
                >
                  Собрать план под цель <Sparkles size={16} />
                </button>
              </form>
            )}
            {mode !== "goal" && services.mode === "live" && attempt === 0 && (
              <div className="akim-start">
                <p>
                  Аким учтёт ваш сценарий, данные города и интересы жителей.
                </p>
                <button
                  className="dark wide"
                  onClick={() => setAttempt((n) => n + 1)}
                >
                  {mode === "advisor"
                    ? "Проверить план с AI"
                    : "Собрать план с AI"}
                  <Sparkles size={16} />
                </button>
              </div>
            )}
            <div className="activity">
              <div className="section-label">ЖУРНАЛ ДЕЙСТВИЙ</div>
              {usesApi ? (
                <>
                  {events.map((event, i) => (
                    <div className="done" key={i}>
                      <Check size={14} />
                      <span>
                        {event.label}
                        <small className="event-detail">{event.detail}</small>
                      </span>
                    </div>
                  ))}
                  {attempt > 0 && !liveResult && !error && (
                    <div className="running">
                      <LoaderCircle size={14} className="spin" />
                      <span>
                        {services.mode === "live"
                          ? "AI принимает решение…"
                          : "Ищем план под ограничения…"}
                      </span>
                    </div>
                  )}
                </>
              ) : (
                steps.map((label, i) => (
                  <div
                    className={step > i ? "done" : step === i ? "running" : ""}
                    key={label}
                  >
                    {step > i ? (
                      <Check size={14} />
                    ) : step === i ? (
                      <LoaderCircle size={14} className="spin" />
                    ) : (
                      <span className="step-dot" />
                    )}
                    <span>{label}</span>
                    {step > i && <small>готово</small>}
                  </div>
                ))
              )}
            </div>
            {error && (
              <div className="inline-error" role="alert">
                {error}
                <button
                  className="text-button"
                  onClick={() => setAttempt((n) => n + 1)}
                >
                  Повторить
                </button>
              </div>
            )}
            {step === 4 && projection && proposed && (
              <div className="akim-answer" aria-live="polite">
                {liveResult?.constraints && (
                  <ul
                    aria-label="Ограничения плана"
                    style={{
                      display: "flex", flexWrap: "wrap", gap: 6,
                      listStyle: "none", padding: 0, margin: "0 0 12px",
                    }}
                  >
                    {[
                      ...liveResult.constraints.priorities.map(
                        (d) => `Приоритет: ${d.toLocaleLowerCase("ru")}`,
                      ),
                      ...liveResult.constraints.protectedDistricts.map(
                        (id) => `Защищён: ${districts.find((d) => d.id === id)?.name ?? id}`,
                      ),
                      `Поддержка ≥ ${money(liveResult.constraints.minSupportPercent)}%`,
                      `Резерв ${money(liveResult.constraints.reserveUnits)} у.е.`,
                      ...liveResult.constraints.mustInclude.map((id) => `Обязательная мера: ${id}`),
                      ...liveResult.constraints.mustExclude.map((id) => `Исключена мера: ${id}`),
                    ].map((label) => (
                      <li
                        key={label}
                        style={{
                          borderRadius: 12, background: "#edf1df",
                          padding: "4px 8px", fontSize: 11,
                        }}
                      >
                        {label}
                      </li>
                    ))}
                  </ul>
                )}
                <div className="eyebrow">
                  {mode === "advisor"
                    ? "РЕЗУЛЬТАТ ПРОВЕРКИ"
                    : mode === "goal"
                      ? "План под цель"
                      : "ПЛАН АВТОПИЛОТА"}
                </div>
                <h3>
                  {liveResult
                    ? liveResult.title
                    : mode === "advisor"
                      ? alternative && alternative.improvement > 0
                        ? "У города есть запас роста."
                        : "Ваш план уже силён."
                      : "Начнём с базовых потребностей."}
                </h3>
                <p>
                  {liveResult
                    ? liveResult.why
                    : mode === "advisor"
                      ? `Поддержка вашего плана в демомодели — ${fmt(approval ?? 0, 1)}%. ${current?.critical === 0 ? "Показателей ниже 40 не осталось." : `Показателей ниже 40: ${current?.critical}.`}`
                      : `План улучшает условия в Нуре и общегородские сервисы. Поддержка в демомодели — ${fmt(approval ?? 0, 1)}%. Поиск сравнивает последовательные замены; это хороший вариант, а не гарантия глобального максимума.`}
                </p>
                <div className="comparison">
                  <div>
                    <small>{mode === "goal" ? "До изменений" : "Ваш план"}</small>
                    <strong>{current ? fmt(current.score) : "—"}</strong>
                    <span>
                      {current
                        ? `${money(budget(plan))} у.е.`
                        : "Ещё не собран"}
                    </span>
                  </div>
                  <ArrowRight size={19} />
                  <div>
                    <small>
                      {mode === "advisor"
                        ? "После замены"
                        : mode === "goal" ? "План под цель" : "Автопилот"}
                    </small>
                    <strong>{fmt(projection.score)}</strong>
                    <span>
                      {money(budget(proposed))} у.е.{" "}
                      {current &&
                        `· ${projection.score - current.score >= 0 ? "+" : ""}${fmt(projection.score - current.score)}`}
                    </span>
                  </div>
                </div>
                {mode === "advisor" && alternative ? (
                  <div className="swap">
                    <div>
                      <small>Убрать</small>
                      <p>{choiceLabel(alternative.removed)}</p>
                    </div>
                    <ArrowRight size={15} />
                    <div>
                      <small>Добавить</small>
                      <p>{choiceLabel(alternative.added)}</p>
                    </div>
                  </div>
                ) : (
                  <ol className="proposed-plan">
                    {proposed.map((c) => (
                      <li key={c.measureId}>
                        <span>{c.measureId}</span>
                        {choiceLabel(c)}
                      </li>
                    ))}
                  </ol>
                )}
                {liveResult && (
                  <div className="live-narrative">
                    <p className="model-caption">
                      {liveResult.model === "local"
                        ? "Локальная модель"
                        : liveResult.model} ·{" "}
                      {liveResult.cached ? "сохранённый ответ" : "новый ответ"}
                    </p>
                    <b>Сильные стороны</b>
                    <p>{liveResult.strengths}</p>
                    <b>Компромиссы</b>
                    <p>{liveResult.risks}</p>
                  </div>
                )}
                <div className="tradeoff">
                  <b>Что меняется по районам</b>
                  {projection.districts.map((d, i) => {
                    const old = current?.districts[i].score;
                    return (
                      <div className="district-comparison" key={d.id}>
                        <span>{districts[i].name}</span>
                        <span>
                          {old !== undefined && `${fmt(old, 1)} → `}
                          {fmt(d.score, 1)}
                          {old !== undefined && (
                            <b
                              className={
                                d.score - old < 0 ? "negative" : "positive"
                              }
                            >
                              {" "}
                              {d.score - old >= 0 ? "+" : ""}
                              {fmt(d.score - old, 1)}
                            </b>
                          )}
                        </span>
                      </div>
                    );
                  })}
                  <p>
                    Выше общий балл не всегда означает улучшение для каждого
                    района. Сравните изменения перед применением.
                  </p>
                </div>
                {dismissed ? (
                  <div className="dismissed">
                    <CheckCheck size={17} />
                    Рекомендация отклонена. Ваш план сохранён.
                  </div>
                ) : (
                  <div className="akim-actions">
                    <button className="dark wide" onClick={apply}>
                      {mode === "advisor"
                        ? "Применить замену"
                        : "Применить план"}
                      <ArrowUpRight size={16} />
                    </button>
                    {mode === "advisor" && (
                      <button
                        className="text-button"
                        onClick={() => setDismissed(true)}
                      >
                        Оставить мой план
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
