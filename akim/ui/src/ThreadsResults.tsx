import { ExternalLink, MessageSquare } from "lucide-react";
import type { ThreadsEvidence } from "./threads";
const stances = {
  complaint: "Жалоба",
  support: "Поддержка",
  mixed: "Смешанная позиция",
  unclear: "Позиция неясна",
};
export default function ThreadsResults({
  evidence,
}: {
  evidence: ThreadsEvidence;
}) {
  const specific = evidence.posts.filter((p) => p.scope === "street"),
    complaints = specific.filter((p) => p.stance === "complaint");
  return (
    <section className="threads-results" aria-label="Результаты Threads">
      <div className="threads-title">
        <MessageSquare size={16} />
        <b>Голоса из Threads</b>
        <small>{evidence.cached ? "Сохранённый поиск" : "Новый поиск"}</small>
      </div>
      <p className="threads-topic">{evidence.question}</p>
      <details className="threads-queries">
        <summary>Поисковые запросы · {evidence.queries.length}</summary>
        <ul>
          {evidence.queries.map((q) => (
            <li key={q}>{q}</li>
          ))}
        </ul>
        {evidence.searchedQueries.length > 0 && (
          <>
            <b>Выполнено поиском</b>
            <ul>
              {evidence.searchedQueries.map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ul>
          </>
        )}
      </details>
      <p className="threads-conclusion">
        {evidence.posts.length
          ? `Найдено публикаций: ${evidence.posts.length}. С явной привязкой к улице: ${specific.length}; среди них жалоб: ${complaints.length}.`
          : "Подходящих индексируемых публикаций не найдено. Это не означает, что жители не жалуются."}
      </p>
      {evidence.posts.map((post) => (
        <article className="thread-post" key={post.url}>
          <div>
            <span className={"stance " + post.stance}>
              {stances[post.stance]}
            </span>
            <small>
              {post.scope === "street"
                ? "Указанная улица"
                : post.scope === "city"
                  ? "Астана в целом"
                  : "Место не подтверждено"}
            </small>
          </div>
          <a href={post.url} target="_blank" rel="noreferrer">
            {post.title}
            <ExternalLink size={12} />
          </a>
          <p>{post.summary}</p>
          <small>Пересказ AI · дата публикации не подтверждена</small>
        </article>
      ))}
      <p className="threads-coverage">{evidence.coverage}</p>
      <small>
        {evidence.provider} ·{" "}
        {new Date(evidence.fetchedAt).toLocaleString("ru-RU")}
      </small>
    </section>
  );
}
