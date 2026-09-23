import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Check, LoaderCircle, X } from "lucide-react";
import { choiceLabel, districts, type Choice, type Direction } from "../data";
import { advise, autopilot, budget, simulate } from "../engine";
import { pollProposal } from "../residents";
import { akimApi, useServices } from "../services";
import type { AkimResult } from "../../server/akim";
import type { ActivityEvent } from "../city-data";
import Matrix from "./Matrix";
import StressTest from "./StressTest";
import ScoreGauge from "./ScoreGauge";
import PixelMayor from "./PixelMayor";
import Comparison, { type ComparisonTarget } from "./Comparison";
import { contributions, explain, fmt, goals, signed } from "./analysis";

interface AiBrief {
  summary: string;
  tradeoff: string;
  nextStep: string;
  evidence: string;
  sources: { name: string; status: "live" | "cached" | "unavailable"; observedAt: string | null }[];
  complaintsUsed: number;
  model: string;
  cached: boolean;
}

export default function Report({
  plan,
  priorities,
  onApply,
  onEdit,
  comparison,
  onCompare,
}: {
  plan: Choice[];
  priorities: Direction[];
  onApply: (plan: Choice[]) => void;
  onEdit: () => void;
  comparison?: ComparisonTarget | null;
  onCompare?: (target: ComparisonTarget) => void;
}) {
  const result = simulate(plan).result!;
  const checklist = goals(plan, priorities);
  const met = checklist.filter((g) => g.met).length;
  const brief = explain(plan, priorities);
  const parts = contributions(plan);
  const maxPart = Math.max(...parts.map((p) => Math.abs(p.gain)), 0.01);
  const poll = useMemo(() => pollProposal(plan, "Мой план"), [plan]);
  const alternative = useMemo(() => advise(plan), [plan]);
  const benchmarkPlan = useMemo(() => autopilot(), []);
  const benchmark = useMemo(() => simulate(benchmarkPlan).result!, [benchmarkPlan]);
  const [localComparison, setLocalComparison] = useState<ComparisonTarget | null>(null);
  const target = comparison === undefined ? localComparison : comparison;

  return (
    <div className="report">
      <header className="report-heading">
        <h1 id="report-title">Итог вашего плана</h1>
        <p className="lead">{met === checklist.length
          ? "Все цели выполнены. Проверьте риски и сравните следующий шаг."
          : `Выполнено ${fmt(met, 0)} из ${fmt(checklist.length, 0)} целей. Начните с того, что осталось нерешённым.`}</p>
      </header>
      <section className="report-hero" aria-labelledby="report-title">
        <div className="report-score">
          <ScoreGauge score={result.score} benchmark={benchmark.score} />
          <p className="report-budget">Потрачено {fmt(budget(plan), 0)} из 100 у.е.</p>
          <p className="report-support"><b>{fmt(poll.approval, 1)}%</b> поддержки модели жителей<br /><small>Синтетическая оценка, не опрос</small></p>
          <button type="button" className="secondary" onClick={onEdit}>Изменить план</button>
        </div>
        <section className="report-goals" aria-labelledby="goals-title">
          <h2 id="goals-title">Цели: {fmt(met, 0)} из {fmt(checklist.length, 0)}</h2>
          <ul className="goal-list">
            {[...checklist].sort((a, b) => Number(a.met)-Number(b.met)).map(g => (
              <li key={g.id} className={g.met ? "met" : "missed"}>
                {g.met ? <Check size={16} aria-hidden="true" /> : <X size={16} aria-hidden="true" />}
                <div><b>{g.label}</b><span>{g.detail}</span></div>
                <span className="visually-hidden">{g.met ? "выполнено" : "не выполнено"}</span>
              </li>
            ))}
          </ul>
        </section>
      <section className="report-next advice" aria-labelledby="advice-title">
        <h2 id="advice-title">Что улучшить</h2>
        <p className="next-priority">{checklist.find(g => !g.met)?.detail ?? brief.risks[0] ?? "Все цели выполнены. Сравните план с альтернативой и проверьте его при ЧП."}</p>
        <AkimAdvice plan={plan} score={result.score} onApply={onApply}>
        {alternative && alternative.improvement > 0.005 ? (
          <div className="swap">
            <p>
              Одна замена даёт <b>{signed(alternative.improvement)}</b> к общему баллу.
              Модель проверила все допустимые замены одного решения.
            </p>
            <div className="swap-row">
              <span className="swap-out">{choiceLabel(alternative.removed)}</span>
              <span aria-hidden="true">заменить на</span>
              <span className="swap-in">{choiceLabel(alternative.added)}</span>
            </div>
            <button type="button" className="primary" onClick={() => onApply(alternative.plan)}>
              Применить замену
            </button>
          </div>
        ) : (
          <p>Ни одна замена одного решения не повышает балл. План устойчив.</p>
        )}
        </AkimAdvice>
        <p className="section-note">
          Для сравнения: лучший план, найденный последовательными заменами,
          даёт {fmt(benchmark.score)}. Это ориентир, а не доказанный максимум.
        </p>
      </section>
      </section>

      <section className="report-section" aria-labelledby="comparison-title">
        <div className="comparison-heading">
          <h2 id="comparison-title">Сравнить сценарии</h2>
          <button type="button" className="secondary" onClick={() => (onCompare ?? setLocalComparison)({ name: "Эталон автопилота", plan: benchmarkPlan })}>
            Сравнить с эталоном автопилота
          </button>
        </div>
        {target ? <Comparison plan={plan} target={target} priorities={priorities} /> : (
          <p className="section-note">Сохраните план как вариант, измените решения и сравните результат. Или выберите эталон автопилота.</p>
        )}
      </section>

      <StressTest plan={plan} />

      <section className="report-section" aria-labelledby="parts-title">
        <h2 id="parts-title">Откуда взялся балл</h2>
        <p className="section-note">
          Сколько балла потеряет план, если убрать решение. Сумма не равна
          приросту: синергии и самый слабый район считаются по всему плану сразу.
        </p>
        <ol className="parts">
          {parts.map((p) => (
            <li key={p.choice.measureId}>
              <span className="part-name">{choiceLabel(p.choice)}</span>
              <span className="part-bar" aria-hidden="true">
                <span
                  className={p.gain < 0 ? "down" : ""}
                  style={{ width: `${(Math.abs(p.gain) / maxPart) * 100}%` }}
                />
              </span>
              <b>{signed(p.gain)}</b>
            </li>
          ))}
        </ol>
      </section>

      <section className="report-section brief" aria-labelledby="brief-title">
        <h2 id="brief-title">Сильные стороны, риски и последствия</h2>
        <div className="brief-columns">
          <BriefList title="Сильные стороны" items={brief.strengths} empty="Заметных улучшений нет." />
          <BriefList title="Риски" items={brief.risks} empty="Серьёзных рисков модель не видит." />
          <BriefList title="Последствия" items={brief.consequences} empty="" />
        </div>
        <AiExplain plan={plan} priorities={priorities} />
      </section>

      <section className="report-section" aria-labelledby="matrix-title">
        <h2 id="matrix-title">Город после плана</h2>
        <Matrix
          projection={result}
          showDelta
          caption="Показатели районов через 8 кварталов; рядом изменение к исходному"
        />
      </section>

      <section className="report-section residents" aria-labelledby="residents-title">
        <h2 id="residents-title">Что скажут жители</h2>
        <p className="section-note">
          Оценка по синтетическим жителям: 2 000 человек, 6 профилей интересов
          в каждом районе. Это модель, не опрос.
        </p>
        <ul className="support">
          {poll.districts.map((d) => {
            const district = districts.find((x) => x.id === d.id)!;
            return (
              <li key={d.id}>
                <span className="support-name">{district.name}</span>
                <span className="support-bar" aria-hidden="true">
                  <span style={{ width: `${d.approval}%` }} className={d.approval < 50 ? "low" : ""} />
                </span>
                <b>{fmt(d.approval, 0)}% за</b>
                <q>{d.quote.replace(/[«»]/g, "")}</q>
              </li>
            );
          })}
        </ul>
        <p className="support-total">
          В среднем по городу: <b>{fmt(poll.approval, 0)}% поддержки</b>.
        </p>
      </section>


    </div>
  );
}

function BriefList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  if (!items.length && !empty) return null;
  return (
    <div>
      <h3>{title}</h3>
      {items.length ? (
        <ul>
          {items.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      ) : (
        <p className="empty">{empty}</p>
      )}
    </div>
  );
}

function AiExplain({ plan, priorities }: { plan: Choice[]; priorities: Direction[] }) {
  const { health, mode } = useServices();
  const [state, setState] = useState<"loading" | "done" | "error">("loading");
  const [answer, setAnswer] = useState<AiBrief | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const token = mode === "live" && health?.configured ? health.token : null;

  // Every plan change on the report fetches a fresh server analysis; the
  // debounce keeps rapid swaps under the 5/min AI rate limit.
  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    setState("loading");
    setError("");
    const timer = setTimeout(async () => {
      try {
        const response = await fetch("/api/explain", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Sim-Token": token },
          body: JSON.stringify({ plan, priorities }),
          signal: controller.signal,
        });
        const body = await response.json();
        if (!response.ok) throw Error(body.error || "Сервер не ответил.");
        setAnswer(body.brief);
        setState("done");
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        setError((e as Error).message);
        setState("error");
      }
    }, 700);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [plan, priorities, token, attempt]);

  if (!token)
    return (
      <p className="ai-note">
        Разбор выше посчитан моделью по правилам задания. AI-аким добавит к нему
        связный вывод, когда на сервере настроен ключ OpenAI.
      </p>
    );

  return (
    <div className="ai-brief" aria-live="polite" aria-busy={state === "loading"}>
      <h3>Вывод AI-акима</h3>
      {state === "loading" && (
        <p className="ai-note">
          <LoaderCircle size={15} className="spin" aria-hidden="true" /> AI-аким
          сверяет план с данными города и жалобами жителей…
        </p>
      )}
      {state === "done" && answer && (
        <>
          <p>{answer.summary}</p>
          <p>
            <b>Главный компромисс.</b> {answer.tradeoff}
          </p>
          <p>
            <b>Что говорят данные города.</b> {answer.evidence}
          </p>
          <p>
            <b>Что сделать дальше.</b> {answer.nextStep}
          </p>
          <small>
            Источники:{" "}
            {answer.sources
              .map((s) => `${s.name} (${s.status === "live" ? "сейчас" : s.status === "cached" ? "снимок" : "недоступен"})`)
              .join(", ")}
            ; жалоб по направлениям плана: {answer.complaintsUsed}. Текст {answer.model}
            {answer.cached ? ", сохранённый ответ" : ""}. Балл посчитан по правилам
            задания, AI его не меняет.
          </small>
        </>
      )}
      {state === "error" && (
        <>
          <p className="inline-error" role="alert">
            {error}
          </p>
          <button type="button" className="secondary" onClick={() => setAttempt((n) => n + 1)}>
            Повторить
          </button>
        </>
      )}
    </div>
  );
}

// Runs the server AI akim (advisor mode: simulate, ask residents, submit one
// swap) for the plan; the local exhaustive swap search is the fallback.
function AkimAdvice({
  plan,
  score,
  onApply,
  children,
}: {
  plan: Choice[];
  score: number;
  onApply: (plan: Choice[]) => void;
  children: ReactNode;
}) {
  const { health, mode } = useServices();
  const token = mode === "live" && health?.configured ? health.token : null;
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [answer, setAnswer] = useState<AkimResult | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    setEvents([]);
    setAnswer(null);
    setError("");
    akimApi("advisor", plan, token, (e) => setEvents((old) => [...old, e]), controller.signal)
      .then((result) => !controller.signal.aborted && setAnswer(result))
      .catch((e: Error) => {
        if (e.name !== "AbortError" && !controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [plan, token, attempt]);

  if (!token) return <>{children}</>;

  if (error)
    return (
      <>
        <p className="inline-error" role="alert">
          AI-аким не ответил: {error}{" "}
          <button type="button" className="secondary" onClick={() => setAttempt((n) => n + 1)}>
            Повторить
          </button>
        </p>
        <p className="section-note">Пока показан локальный расчёт замены.</p>
        {children}
      </>
    );

  if (!answer)
    return (
      <div aria-busy="true">
        <PixelMayor
          title={events.length ? events[events.length - 1].label : "Так-так…"}
          text={
            events.length
              ? events[events.length - 1].detail
              : "Проверяю ваш план на данных города."
          }
        />
      </div>
    );

  const same = (a: Choice, b: Choice) =>
    a.measureId === b.measureId && a.districtId === b.districtId;
  const removed = plan.find((a) => !answer.plan.some((b) => same(a, b)));
  const added = answer.plan.find((a) => !plan.some((b) => same(a, b)));
  const improvement = answer.result.score - score;
  return (
    <div className="swap" aria-live="polite">
      <PixelMayor title={answer.title} text={answer.why} />
      {removed && added && (
        <>
          <p>
            {improvement > 0 ? (
              <>
                Замена от AI-акима даёт <b>{signed(improvement)}</b> к общему баллу.
              </>
            ) : (
              <>
                Замена не улучшает балл (<b>{signed(improvement)}</b>).
              </>
            )}
          </p>
          <div className="swap-row">
            <span className="swap-out">{choiceLabel(removed)}</span>
            <span aria-hidden="true">заменить на</span>
            <span className="swap-in">{choiceLabel(added)}</span>
          </div>
        </>
      )}
      <p>
        <b>Сильные стороны.</b> {answer.strengths}
      </p>
      <p>
        <b>Риски.</b> {answer.risks}
      </p>
      {removed && added && (
        <button type="button" className="primary" onClick={() => onApply(answer.plan)}>
          Применить замену
        </button>
      )}
      <small>
        {answer.model}
        {answer.cached ? ", сохранённый ответ" : ""} · {answer.events.length} шагов
        проверки. Балл пересчитан по правилам задания.
      </small>
    </div>
  );
}
