import { districts, indicators, indicatorNames, type Indicator } from "../data";
import { baseline, type Projection } from "../engine";
import { fmt, signed } from "./analysis";

const shortNames: Record<Indicator, string> = {
  T1: "Дороги",
  T2: "Автобусы",
  E1: "Зелень",
  E2: "Воздух",
  S1: "Школы",
  S2: "Клиники",
  B1: "Улицы",
  B2: "На дорогах",
  C1: "ЖКХ",
  C2: "Обращения",
};

const groups = [
  { name: "Транспорт", span: 2 },
  { name: "Экология", span: 2 },
  { name: "Соцсфера", span: 2 },
  { name: "Безопасность", span: 2 },
  { name: "Сервисы", span: 2 },
];

function band(value: number) {
  if (value < 40) return "critical";
  if (value < 50) return "low";
  if (value < 65) return "mid";
  return "high";
}

export default function Matrix({
  projection,
  showDelta,
  caption,
}: {
  projection: Projection;
  showDelta: boolean;
  caption: string;
}) {
  return (
    <div className="matrix-scroll">
      <table className="matrix">
        <caption>{caption}</caption>
        <thead>
          <tr className="matrix-groups">
            <th scope="col" rowSpan={2} className="matrix-corner">
              Район
            </th>
            {groups.map((g) => (
              <th scope="colgroup" colSpan={g.span} key={g.name}>
                {g.name}
              </th>
            ))}
            <th scope="col" rowSpan={2} className="matrix-score-head">
              Балл района
            </th>
          </tr>
          <tr>
            {indicators.map((k) => (
              <th
                scope="col"
                key={k}
                title={indicatorNames[k]}
                className="matrix-ind"
              >
                {shortNames[k]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {projection.districts.map((row, i) => {
            const base = baseline.districts[i];
            const scoreDelta = row.score - base.score;
            return (
              <tr key={row.id}>
                <th scope="row">
                  <span className="matrix-district">{districts[i].name}</span>
                  <small>{Math.round(districts[i].population * 100)}% жителей</small>
                </th>
                {indicators.map((k) => {
                  const delta = row.delta[k];
                  const changed = showDelta && Math.abs(delta) >= 0.05;
                  return (
                    <td
                      key={k}
                      className={`cell band-${band(row.values[k])} ${changed ? "changed" : ""}`}
                      title={`${indicatorNames[k]}, ${districts[i].name}: ${fmt(row.values[k], 1)}`}
                    >
                      <span className="cell-value">{fmt(row.values[k], 0)}</span>
                      {changed && (
                        <span className={`cell-delta ${delta < 0 ? "down" : "up"}`}>
                          {signed(delta, 1)}
                        </span>
                      )}
                    </td>
                  );
                })}
                <td className="matrix-score">
                  <strong>{fmt(row.score, 1)}</strong>
                  {showDelta && Math.abs(scoreDelta) >= 0.05 && (
                    <span className={`cell-delta ${scoreDelta < 0 ? "down" : "up"}`}>
                      {signed(scoreDelta, 1)}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="matrix-legend">
        <span className="swatch band-critical" aria-hidden="true" /> ниже 40, минус 1 балл
        <span className="swatch band-low" aria-hidden="true" /> 40–49
        <span className="swatch band-mid" aria-hidden="true" /> 50–64
        <span className="swatch band-high" aria-hidden="true" /> 65 и выше
      </p>
    </div>
  );
}
