import { useEffect, useState } from "react";
import { X, Route, Play, LoaderCircle, Circle } from "lucide-react";
import { districts, measures, type Choice } from "./data";
import { mobilityExample, type MobilityComparison } from "./mobility";
import { budget, validate } from "./engine";
import { fmt } from "./planner/analysis";
import { money } from "./money";
export function useMobility(plan: Choice[], enabled: boolean) {
  const [data, setData] = useState<MobilityComparison | null>(null),
    [error, setError] = useState("");
  const signature = JSON.stringify(plan);
  useEffect(() => {
    if (!enabled) return;
    setData(null);
    setError("");
    if (validate(plan, true).length) {
      setError("Сначала исправьте конфликты плана.");
      return;
    }
    const worker = new Worker(
      new URL("./mobility.worker.ts", import.meta.url),
      { type: "module" },
    );
    worker.onmessage = (e) => {
      setData(e.data.result ?? null);
      setError(e.data.error ?? "");
    };
    worker.onerror = () => setError("Не удалось рассчитать маршруты.");
    worker.postMessage(JSON.parse(signature));
    return () => worker.terminate();
  }, [signature, enabled]);
  return { data, error };
}
export default function MobilityPanel({
  plan,
  data,
  error,
  after,
  onAfter,
  onClose,
  onExample,
  onReplay,
}: {
  plan: Choice[];
  data: MobilityComparison | null;
  error: string;
  after: boolean;
  onAfter: (v: boolean) => void;
  onClose: () => void;
  onExample: (p: Choice[]) => void;
  onReplay: () => void;
}) {
  const transport = plan.filter((c) =>
    ["M1", "M2", "M3"].includes(c.measureId),
  );
  return (
    <section
      className="analysis-panel glass"
      role="dialog"
      aria-labelledby="mobility-title"
    >
      <header>
        <div>
          <span className="eyebrow">ОДНИ И ТЕ ЖЕ 2 000 ПОЕЗДОК</span>
          <h2 id="mobility-title">
            <Route size={22} /> Мобильность
          </h2>
        </div>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Закрыть мобильность"
        >
          <X />
        </button>
      </header>
      <p>Сравните утренние поездки до и после транспортных мер вашего плана.</p>
      <div className="analysis-segment">
        <button aria-pressed={!after} onClick={() => onAfter(false)}>
          До
        </button>
        <button aria-pressed={after} onClick={() => onAfter(true)}>
          После
        </button>
        <button onClick={onReplay}>
          <Play size={13} /> Час пик
        </button>
      </div>
      {transport.length ? (
        <p className="analysis-summary">
          {transport
            .map((c) => measures.find((m) => m.id === c.measureId)!.name)
            .join(" · ")}
          <br />
          <strong>{money(budget(transport))} у.е.</strong> · транспортная часть
          плана
        </p>
      ) : (
        <div className="analysis-empty">
          <p>В плане нет транспортных мер — результаты совпадают.</p>
          <button className="dark" onClick={() => onExample(mobilityExample)}>
            Пример: автобусные полосы + светофоры
          </button>
        </div>
      )}
      {error ? (
        <p role="alert">{error}</p>
      ) : !data ? (
        <p role="status">
          <LoaderCircle className="spin" size={16} /> Перестраиваем маршруты…
        </p>
      ) : (
        <>
          <div className="mobility-table">
            <div>
              <b>Утренний час пик</b>
              <b>До</b>
              <b>После</b>
            </div>
            {[
              [
                "Средняя поездка, мин",
                data.before.metrics.minutes,
                data.after.metrics.minutes,
              ],
              [
                "90% поездок быстрее, мин",
                data.before.metrics.p90,
                data.after.metrics.p90,
              ],
              [
                "Участки с перегрузкой, км",
                data.before.metrics.congestedKm,
                data.after.metrics.congestedKm,
              ],
              [
                "Доля автомобилей, %",
                data.before.metrics.carShare,
                data.after.metrics.carShare,
              ],
            ].map(([label, b, a]) => (
              <div key={label}>
                <span>{label}</span>
                <span>{fmt(Number(b), 1)}</span>
                <strong>{fmt(Number(a), 1)}</strong>
              </div>
            ))}
          </div>
          <p className="analysis-summary">
            {fmt(data.changedRoutes, 0)} жителей выбрали другой маршрут. Цвет дорог
            показывает модельную нагрузку.
          </p>
          <div className="road-legend">
            <span><Circle size={10} fill="#328365" color="#328365" aria-hidden="true" /> Свободно</span>
            <span><Circle size={10} fill="#c98c00" color="#c98c00" aria-hidden="true" /> Плотно</span>
            <span><Circle size={10} fill="#b8392a" color="#b8392a" aria-hidden="true" /> Перегрузка</span>
          </div>
          <details>
            <summary>Районы · средняя поездка</summary>
            {districts.map((d) => (
              <p key={d.id}>
                {d.name}: {fmt(data.before.districts[d.id].minutes, 1)} →{" "}
                {fmt(data.after.districts[d.id].minutes, 1)} мин
              </p>
            ))}
          </details>
        </>
      )}
      <details className="model-assumptions">
        <summary>Допущения модели</summary>
        <p>
          Улицы OSM; синтетические пары дом–работа в пределах района. Авто 32
          км/ч, автобус 18, пешком 4,5. Начальные доли: 50% / 30% / 20%.
          Нагрузка — относительная, без счётчиков реального трафика.
        </p>
        <p>
          Полосы: автобус 22 км/ч, часть водителей пересаживается, ёмкость для
          авто −25%. Светофоры: задержка на перекрёстке 9 → 3 сек. ЛРТ: условная
          сеть по улицам района, 26 км/ч; не реальная трасса ЛРТ. Два прохода
          назначения маршрутов, без транспортного равновесия. Только утренний
          пик; прогноз не откалиброван.
        </p>
      </details>
    </section>
  );
}
