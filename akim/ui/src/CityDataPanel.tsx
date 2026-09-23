import { ExternalLink, RefreshCw, X } from "lucide-react";
import { useServices } from "./services";
import { BUDGET_LIMIT, budgetSource, money } from "./money";
export default function CityDataPanel({ onClose }: { onClose: () => void }) {
  const { city, cityError, refresh } = useServices();
  return (
    <section
      className="panel data-panel glass"
      role="dialog"
      aria-labelledby="data-title"
    >
      <div className="panel-heading">
        <div>
          <div className="eyebrow">ПРОВЕРЯЕМЫЙ КОНТЕКСТ</div>
          <h2 id="data-title">Настоящая Астана</h2>
        </div>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Закрыть данные"
        >
          <X size={19} />
        </button>
      </div>
      <div className="panel-scroll">
        <p className="data-intro">
          Реальные источники помогают жителям и акиму оценить ситуацию. Эффекты
          решений и балл качества жизни остаются сценарной моделью.
        </p>
        <button className="text-button" onClick={refresh}>
          <RefreshCw size={13} />
          Проверить обновления
        </button>
        {cityError && <p className="inline-error">{cityError}</p>}
        {!city && !cityError && <p role="status">Загружаем источники…</p>}
        {city &&
          Object.values(city).map((source) => (
            <article className="source-card" key={source.id}>
              <div className="source-heading">
                <h3>{source.name}</h3>
                <span className={`source-state ${source.status}`}>
                  {source.status === "live"
                    ? "Получено сейчас"
                    : source.status === "cached"
                      ? "Сохранённый снимок"
                      : "Недоступно"}
                </span>
              </div>
              {source.id === "weather" && city.weather.data && (
                <strong>
                  {city.weather.data.temperature} °C{" "}
                  <small>· ветер {city.weather.data.wind} км/ч</small>
                </strong>
              )}
              {source.id === "air" && city.air.data && (
                <strong>
                  AQI {city.air.data.aqi}
                  <small>PM2.5 {city.air.data.pm25} мкг/м³</small>
                </strong>
              )}
              {source.id === "accidents" && city.accidents.data && (
                <strong>
                  {money(city.accidents.data.count)}
                  <small>записей ДТП · {city.accidents.data.year}</small>
                </strong>
              )}
              {source.id === "population" && city.population.data && (
                <strong>
                  {money(city.population.data.total)}
                  <small>человек · {city.population.data.period}</small>
                </strong>
              )}
              {source.id === "boundaries" && city.boundaries.data && (
                <>
                  <strong>
                    {city.boundaries.data.districts.length}
                    <small>районов в реестре</small>
                  </strong>
                  <p>
                    {city.boundaries.data.districts
                      .map((d) => d.name)
                      .join(" · ")}
                  </p>
                </>
              )}
              <p>{source.note}</p>
              {source.error && <p className="negative">{source.error}</p>}
              <small className="source-date">
                {source.observedAt
                  ? `Данные на ${new Date(source.observedAt).toLocaleString("ru-RU")}`
                  : "Дата наблюдения не указана"}
                {source.fetchedAt &&
                  ` · Запрос ${new Date(source.fetchedAt).toLocaleString("ru-RU")}`}
              </small>
              <a href={source.url} target="_blank" rel="noreferrer">
                {source.attribution}
                <ExternalLink size={11} />
              </a>
            </article>
          ))}
        <article className="source-card">
          <h3>Бюджет в миллионах тенге</h3>
          <strong>
            {money(BUDGET_LIMIT)}
            <small>у.е. · общий бюджет задания, одинаковый для всех команд</small>
          </strong>
          <p>
            Лимит выбран для игры. Годовые затраты города по бюджету 2026:{" "}
            {money(budgetSource.operatingCostsMln)} млн ₸. Это не свободный
            остаток для новых проектов.
          </p>
          <p>
            Каждая карточка меры показывает основание цены: исторический
            ориентир или оценка масштаба работ.
          </p>
          <small className="source-date">
            Проверено {budgetSource.verifiedAt}
          </small>
          <a href={budgetSource.url} target="_blank" rel="noreferrer">
            Бюджет Астаны · Әділет <ExternalLink size={11} />
          </a>
        </article>
      </div>
    </section>
  );
}
