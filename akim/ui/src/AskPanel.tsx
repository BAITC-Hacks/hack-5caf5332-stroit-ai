import { useServices, AiModeSwitch, askApi } from "./services";
import { money } from "./money";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, LoaderCircle, MessageCircle, Send, X } from "lucide-react";
import { districts, type Choice } from "./data";
import { askCity, examples, type Poll } from "./residents";
import { fmt } from "./PlanBuilder";
interface Props {
  plan: Choice[];
  poll: Poll | null;
  onPoll: (poll: Poll | null) => void;
  onClose: () => void;
  initialQuestion?: string;
}
export default function AskPanel({
  plan,
  poll,
  onPoll,
  onClose,
  initialQuestion = "",
}: Props) {
  const { mode, health } = useServices();
  const abort = useRef<AbortController | null>(null);
  const [question, setQuestion] = useState(initialQuestion);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
      abort.current?.abort();
    },
    [],
  );
  useEffect(() => {
    abort.current?.abort();
    setBusy(false);
    setError(null);
    onPoll(null);
  }, [mode, onPoll]);
  const submit = async (text = question) => {
    if (!text.trim()) return;
    setQuestion(text);
    setError(null);
    setBusy(true);
    onPoll(null);
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    try {
      if (mode === "live") {
        if (!health) throw Error("Сервер AI не подключён.");
        onPoll(await askApi(text, plan, health.token, controller.signal));
      } else {
        await new Promise<void>((resolve) => {
          timer.current = setTimeout(resolve, 500);
        });
        if (controller.signal.aborted) return;
        const response = askCity(text, plan);
        onPoll(response.poll ? { ...response.poll, mode: "local" } : null);
        setError(response.error);
      }
    } catch (e) {
      if (!controller.signal.aborted)
        setError(
          e instanceof Error ? e.message : "Не удалось опросить жителей.",
        );
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  };
  return (
    <section
      className="ask-panel glass"
      role="dialog"
      aria-labelledby="ask-title"
    >
      <div className="ask-heading">
        <span>
          <MessageCircle size={16} />
          <b id="ask-title">Спросить город</b>
        </span>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Закрыть опрос"
        >
          <X size={19} />
        </button>
      </div>
      <AiModeSwitch />
      {busy ? (
        <div className="poll-loading" role="status">
          <LoaderCircle className="spin" size={28} />
          <h3>Слушаем жителей…</h3>
          <p>{question}</p>
          <div className="loading-track">
            <i />
          </div>
          <small>
            {mode === "live"
              ? "OpenAI оценивает интересы 30 профилей по сценарию и данным города"
              : "Считаем изменения и интересы шести профилей в каждом районе"}
          </small>
        </div>
      ) : poll ? (
        <div className="poll-result" aria-live="polite">
          <h3>{poll.title}</h3>
          <div className="approval">
            <strong>
              {fmt(poll.approval, 2)}
              <span>%</span>
            </strong>
            <span>
              поддерживают
              <br />
              предложение
            </span>
          </div>
          <div className="approval-bar">
            <i style={{ width: `${poll.approval}%` }} />
          </div>
          <div className="poll-legend">
            <span>
              <i />
              За {fmt(poll.approval, 2)}%
            </span>
            <span>
              <i />
              Против {fmt(100 - poll.approval, 2)}%
            </span>
          </div>
          {poll.comparison && (
            <div className="comparison-note">
              <b>Сравнение двух отдельных предложений</b>
              <p>
                {poll.primaryLabel || "Школа + поликлиника в Нуре"}:{" "}
                {fmt(poll.approval, 2)}% за · {money(poll.cost)} млн ₸
                <br />
                {poll.comparison.title}: {fmt(poll.comparison.approval, 2)}% за
                · {money(poll.comparison.cost ?? 0)} млн ₸
              </p>
              <small>
                На карте — реакции на первое предложение. Это не голосование
                между двумя вариантами.
              </small>
            </div>
          )}
          <div className="poll-districts">
            {poll.districts.map((d, i) => (
              <div key={d.id}>
                <span>{districts[i].name}</span>
                <div>
                  <i style={{ width: `${d.approval}%` }} />
                </div>
                <strong>{fmt(d.approval, 0)}%</strong>
              </div>
            ))}
          </div>
          <div className="quotes">
            {[...poll.districts]
              .sort((a, b) => b.approval - a.approval)
              .filter((_, i) => i === 0 || i === 4)
              .map((d) => (
                <blockquote key={d.id}>
                  {d.quote}
                  <cite>
                    {districts.find((r) => r.id === d.id)!.name} · синтетический
                    житель
                  </cite>
                </blockquote>
              ))}
          </div>
          <div className="demo-note">
            Синтетические жители ·{" "}
            {poll.mode === "live"
              ? `OpenAI ${poll.model}${poll.cached ? " · из кеша" : ""}`
              : "локальная модель"}{" "}
            · не реальный опрос
          </div>
          <button
            className="dark wide"
            onClick={() => {
              onPoll(null);
              setQuestion("");
            }}
          >
            Задать ещё вопрос <ArrowRight size={16} />
          </button>
        </div>
      ) : (
        <>
          <p className="ask-description">
            Один город. Две тысячи разных взглядов.
            <br />
            Узнайте, как жители встретят ваши решения.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <label className="sr-only" htmlFor="question">
              Вопрос жителям
            </label>
            <div className="question-field">
              <textarea
                id="question"
                placeholder="Что изменится для жителей?"
                rows={2}
                maxLength={1000}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                autoFocus
              />
              <button
                className="send-button"
                type="submit"
                disabled={!question.trim()}
                aria-label="Отправить вопрос"
              >
                <Send size={18} />
              </button>
            </div>
          </form>
          {error && (
            <p className="inline-error" role="alert">
              {error}
            </p>
          )}
          <div className="section-label">ПОПРОБУЙТЕ СПРОСИТЬ</div>
          <div className="example-questions">
            {examples.map((text, i) => (
              <button onClick={() => submit(text)} key={text}>
                <span>{["01", "02", "03"][i]}</span>
                {text}
                <ArrowRight size={14} />
              </button>
            ))}
          </div>
          <div className="demo-note">
            Синтетические жители ·{" "}
            {mode === "live"
              ? "свободные вопросы о мерах города"
              : "3 доступных сценария"}
          </div>
        </>
      )}
    </section>
  );
}
