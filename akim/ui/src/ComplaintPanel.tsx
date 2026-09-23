import { useEffect, useRef, useState } from "react";
import { X, MapPin, ExternalLink, LoaderCircle } from "lucide-react";
import { directions, type Direction } from "./data";
import {
  complaintColors,
  type Complaint,
  type ComplaintCollection,
} from "./complaints";
import { complaintApi, useServices } from "./services";
export default function ComplaintPanel({
  collection,
  onCollection,
  filter,
  onFilter,
  onFocus,
  onClose,
}: {
  collection: ComplaintCollection | null;
  onCollection: (c: ComplaintCollection) => void;
  filter: Direction | "";
  onFilter: (d: Direction | "") => void;
  onFocus: (c: Complaint) => void;
  onClose: () => void;
}) {
  const { health } = useServices(),
    [includePress, setIncludePress] = useState(true),
    [keywords, setKeywords] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [showReview, setShowReview] = useState(false),
    abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);
  const ingest = async () => {
    if (!health) return;
    setBusy(true);
    setError("");
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    try {
      onCollection(
        await complaintApi(
          keywords,
          filter || undefined,
          health.token,
          controller.signal,
          includePress,
        ),
      );
    } catch (e) {
      if (!controller.signal.aborted)
        setError(e instanceof Error ? e.message : "Поиск недоступен.");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  };
  const accepted =
      collection?.posts.filter((p) => p.decision === "accepted") ?? [],
    mapped = accepted.filter((p) => p.location),
    review = collection?.posts.filter((p) => p.decision === "review") ?? [];
  const visible = (showReview ? review : accepted).filter(
    (p) => !filter || p.directions.includes(filter) || showReview,
  );
  return (
    <section
      className="analysis-panel complaint-panel glass"
      role="dialog"
      aria-labelledby="complaints-title"
    >
      <header>
        <div>
          <span className="eyebrow">ПУБЛИЧНЫЕ THREADS · JEV</span>
          <h2 id="complaints-title">О чём говорит город</h2>
        </div>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Закрыть жалобы"
        >
          <X />
        </button>
      </header>
      <p>Поиск по Астане, проверка жалоб и привязка к месту из текста.</p>
      <label className="field-label">
        Направление
        <select
          aria-label="Направление жалоб"
          value={filter}
          onChange={(e) => onFilter(e.target.value as Direction | "")}
        >
          <option value="">Все направления</option>
          {directions.map((d) => (
            <option key={d}>{d}</option>
          ))}
        </select>
      </label>
      <label className="field-label">
        Улица или ключевые слова
        <input
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
          maxLength={160}
          placeholder="Сейфуллина, пробки, нет воды…"
        />
      </label>
      <label className="review-toggle">
        <input
          type="checkbox"
          checked={includePress}
          onChange={(e) => setIncludePress(e.target.checked)}
          disabled={busy}
        />{" "}
        Учитывать жалобы из Threads, процитированные СМИ
      </label>
      <button
        className="dark wide"
        onClick={ingest}
        disabled={busy || !health?.configured || !health?.jevConfigured}
      >
        {busy ? (
          <>
            <LoaderCircle size={15} className="spin" /> Поиск и проверка Jev…
          </>
        ) : (
          "Найти жалобы на карте"
        )}
      </button>
      {!health?.jevConfigured && (
        <p className="analysis-summary">Классификатор Jev пока не подключён.</p>
      )}
      {error && (
        <p role="alert" className="analysis-error">
          {error} Предыдущий результат сохранён.
        </p>
      )}
      {collection ? (
        <>
          <div className="complaint-counts">
            <span>
              <b>{accepted.length}</b> подходят
            </span>
            <span>
              <b>{mapped.length}</b> с местом
            </span>
            <span>
              <b>{review.length}</b> на проверку
            </span>
          </div>
          <p className="analysis-summary">
            {collection.cached ? "Сохранённый поиск" : "Последний поиск"} ·{" "}
            {new Date(collection.fetchedAt).toLocaleString("ru-RU")}
          </p>
          <label className="review-toggle">
            <input
              type="checkbox"
              checked={showReview}
              onChange={(e) => setShowReview(e.target.checked)}
            />{" "}
            Показать сомнительные результаты
          </label>
          {!visible.length && (
            <p className="analysis-empty">
              {collection.posts.length
                ? "Нет подходящих публикаций для этого фильтра."
                : "Индексируемых публикаций не найдено. Это не подтверждает отсутствие проблем."}
            </p>
          )}
          <div className="complaint-list">
            {visible.map((p) => (
              <article key={p.id} className="complaint-item">
                <div className="complaint-tags">
                  {p.directions.map((d) => (
                    <span
                      key={d}
                      style={{
                        borderColor: complaintColors[d],
                        color: complaintColors[d],
                      }}
                    >
                      {d}
                    </span>
                  ))}
                </div>
                <p>{p.summary}</p>
                <small>
                  {p.sourceKind === "press"
                    ? "Threads через СМИ"
                    : "Публичный Threads"}{" "}
                  · пересказ · {collection.model}
                </small>
                <small className="complaint-status">
                  Дата публикации и текущий статус проблемы не проверены.
                </small>
                <div className="complaint-actions">
                  <a href={p.url} target="_blank" rel="noreferrer">
                    Источник <ExternalLink size={12} />
                  </a>
                  {p.location ? (
                    <button onClick={() => onFocus(p)}>
                      <MapPin size={13} />
                      {p.location.name}
                    </button>
                  ) : (
                    <span>Без подтверждённого места</span>
                  )}
                </div>
                <details>
                  <summary>Почему подходит / не подходит</summary>
                  <p>{p.reason}</p>
                  <p>
                    Астана: {Math.round(p.astanaProbability * 100)}% · жалоба:{" "}
                    {Math.round(p.complaintProbability * 100)}%
                  </p>
                  {directions.map((d) => (
                    <p key={d}>
                      {d}: {Math.round((p.confidence[d] ?? 0) * 100)}%
                    </p>
                  ))}
                </details>
              </article>
            ))}
          </div>
          <details className="model-assumptions">
            <summary>Запросы и ограничения</summary>
            <ul>
              {collection.searchedQueries.map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ul>
            <p>{collection.coverage}</p>
            <p>
              Исключено Jev:{" "}
              {collection.posts.filter((p) => p.decision === "excluded").length}
              . Неуверенные результаты не попадают на карту.
            </p>
          </details>
        </>
      ) : (
        !busy && (
          <p className="analysis-empty">
            Запустите поиск. На карту попадут подходящие жалобы с подтверждённой
            улицей или районом.
          </p>
        )
      )}
    </section>
  );
}
