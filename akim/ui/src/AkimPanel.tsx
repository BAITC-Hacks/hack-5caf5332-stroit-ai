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
import { choiceLabel, type Choice, districts } from "./data";
import {
  advise,
  autopilot,
  budget,
  simulate,
  type Alternative,
  type Projection,
} from "./engine";
import { pollProposal } from "./residents";
import { fmt } from "./PlanBuilder";
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
  const [mode, setMode] = useState<"advisor" | "autopilot">("advisor");
  const [step, setStep] = useState(0);
  const [alternative, setAlternative] = useState<Alternative | null>(null);
  const [proposed, setProposed] = useState<Choice[] | null>(null);
  const [projection, setProjection] = useState<Projection | null>(null);
  const [approval, setApproval] = useState<number | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const current = simulate(plan).result;
  const blocked = mode === "advisor" && !current;
  useEffect(() => {
    setStep(0);
    setAlternative(null);
    setProposed(null);
    setProjection(null);
    setApproval(null);
    setDismissed(false);
    if (blocked) return;
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
  }, [plan, mode, blocked]);
  const apply = () => {
    if (proposed) {
      onChange(proposed);
      onClose();
    }
  };
  return (
    <section
      className="panel akim-panel glass"
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
          onClick={() => setMode("advisor")}
        >
          Советник
        </button>
        <button
          aria-pressed={mode === "autopilot"}
          className={mode === "autopilot" ? "active" : ""}
          onClick={() => setMode("autopilot")}
        >
          Автопилот
        </button>
      </div>
      <div className="demo-note">
        <i />
        Деморежим · локальный алгоритм, без LLM
      </div>
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
            <div className="activity">
              <div className="section-label">ЖУРНАЛ ДЕЙСТВИЙ</div>
              {steps.map((label, i) => (
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
              ))}
            </div>
            {step === 4 && projection && proposed && (
              <div className="akim-answer" aria-live="polite">
                <div className="eyebrow">
                  {mode === "advisor"
                    ? "РЕЗУЛЬТАТ ПРОВЕРКИ"
                    : "ПЛАН АВТОПИЛОТА"}
                </div>
                <h3>
                  {mode === "advisor"
                    ? alternative && alternative.improvement > 0
                      ? "У города есть запас роста."
                      : "Ваш план уже силён."
                    : "Начнём с базовых потребностей."}
                </h3>
                <p>
                  {mode === "advisor"
                    ? `Поддержка вашего плана в демомодели — ${fmt(approval ?? 0, 1)}%. ${current?.critical === 0 ? "Показателей ниже 40 не осталось." : `Показателей ниже 40: ${current?.critical}.`}`
                    : `План улучшает условия в Нуре и общегородские сервисы. Поддержка в демомодели — ${fmt(approval ?? 0, 1)}%. Поиск сравнивает последовательные замены; это хороший вариант, а не гарантия глобального максимума.`}
                </p>
                <div className="comparison">
                  <div>
                    <small>{current ? "Ваш план" : "Ваш план"}</small>
                    <strong>{current ? fmt(current.score) : "—"}</strong>
                    <span>
                      {current ? `${budget(plan)} ед.` : "Ещё не собран"}
                    </span>
                  </div>
                  <ArrowRight size={19} />
                  <div>
                    <small>
                      {mode === "advisor" ? "После замены" : "Автопилот"}
                    </small>
                    <strong>{fmt(projection.score)}</strong>
                    <span>
                      {budget(proposed)} ед.{" "}
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
