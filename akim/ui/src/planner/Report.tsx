import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Link2, LoaderCircle, X } from "lucide-react";
import { choiceLabel, districts, type Choice, type Direction } from "../data";
import { advise, autopilot, budget, simulate } from "../engine";
import { pollProposal } from "../residents";
import { useServices } from "../services";
import Matrix from "./Matrix";
import ScoreGauge from "./ScoreGauge";
import { contributions, explain, fmt, goals, signed } from "./analysis";

interface AiBrief {
  summary: string;
  tradeoff: string;
  nextStep: string;
  model: string;
  cached: boolean;
}

export default function Report({
  plan,
  priorities,
  onApply,
  onEdit,
}: {
  plan: Choice[];
  priorities: Direction[];
  onApply: (plan: Choice[]) => void;
  onEdit: () => void;
}) {
  const result = simulate(plan).result!;
  const checklist = goals(plan, priorities);
  const met = checklist.filter((g) => g.met).length;
  const brief = explain(plan, priorities);
  const parts = contributions(plan);
  const maxPart = Math.max(...parts.map((p) => Math.abs(p.gain)), 0.01);
  const poll = useMemo(() => pollProposal(plan, "Мой план"), [plan]);
  const alternative = useMemo(() => advise(plan), [plan]);
  const benchmark = useMemo(() => simulate(autopilot()).result!, []);
  const [copied, setCopied] = useState(false);

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="report">
      <section className="report-hero" aria-labelledby="report-title">
        <div>
          <h1 id="report-title">Итог вашего плана</h1>
          <p className="lead">
            {met === checklist.length
              ? "Все цели выполнены. Ниже видно, за счёт чего и где остались риски."
              : `Выполнено ${met} из ${checklist.length} целей. Ниже видно, что мешает и как это исправить.`}
          </p>
          <ul className="goal-list">
            {checklist.map((g) => (
              <li key={g.id} className={g.met ? "met" : "missed"}>
                {g.met ? <Check size={16} aria-hidden="true" /> : <X size={16} aria-hidden="true" />}
                <div>
                  <b>{g.label}</b>
                  <span>{g.detail}</span>
                </div>
                <span className="visually-hidden">{g.met ? "выполнено" : "не выполнено"}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="report-score">
          <ScoreGauge score={result.score} benchmark={benchmark.score} />
          <p className="report-budget">
            Потрачено {budget(plan)} из 100 у.е.
          </p>
          <div className="report-actions">
            <button type="button" className="secondary" onClick={onEdit}>
              Изменить план
            </button>
            <button type="button" className="secondary" onClick={copyLink}>
              <Link2 size={15} aria-hidden="true" />
              {copied ? "Ссылка скопирована" : "Ссылка на сценарий"}
            </button>
          </div>
        </div>
      </section>

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

      <section className="report-section advice" aria-labelledby="advice-title">
        <h2 id="advice-title">Совет акима</h2>
        {alternative && alternative.improvement > 0.005 ? (
          <div className="swap">
            <p>
              Одна замена даёт <b>{signed(alternative.improvement)}</b> к баллу.
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
        <p className="section-note">
          Для сравнения: лучший план, найденный последовательными заменами,
          даёт {fmt(benchmark.score)}. Это ориентир, а не доказанный максимум.
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
  const { health } = useServices();
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [answer, setAnswer] = useState<AiBrief | null>(null);
  const [error, setError] = useState("");
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => {
    setState("idle");
    setAnswer(null);
  }, [plan]);

  const run = async () => {
    if (!health) return;
    abort.current?.abort();
    abort.current = new AbortController();
    setState("loading");
    setError("");
    try {
      const response = await fetch("/api/explain", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Sim-Token": health.token },
        body: JSON.stringify({ plan, priorities }),
        signal: abort.current.signal,
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
  };

  if (!health?.configured)
    return (
      <p className="ai-note">
        Разбор выше посчитан моделью по правилам задания. AI-аким добавит к нему
        связный вывод, когда на сервере настроен ключ OpenAI.
      </p>
    );

  return (
    <div className="ai-brief" aria-live="polite">
      {state === "done" && answer ? (
        <>
          <h3>Вывод AI-акима</h3>
          <p>{answer.summary}</p>
          <p>
            <b>Главный компромисс.</b> {answer.tradeoff}
          </p>
          <p>
            <b>Что сделать дальше.</b> {answer.nextStep}
          </p>
          <small>
            Текст {answer.model}{answer.cached ? ", сохранённый ответ" : ""}. Все
            числа посчитаны моделью выше, AI их только пересказывает.
          </small>
        </>
      ) : (
        <button type="button" className="secondary" onClick={run} disabled={state === "loading"}>
          {state === "loading" && <LoaderCircle size={15} className="spin" aria-hidden="true" />}
          {state === "loading" ? "AI-аким читает разбор…" : "Получить вывод AI-акима"}
        </button>
      )}
      {state === "error" && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

