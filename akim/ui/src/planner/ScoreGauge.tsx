import { baseline } from "../engine";
import { fmt, signed, TARGET_GAIN } from "./analysis";

const MIN = 48;
const MAX = 62;
const at = (value: number) =>
  `${((Math.min(MAX, Math.max(MIN, value)) - MIN) / (MAX - MIN)) * 100}%`;

/** The score with a ghost baseline and the goal line, so every change is read against the start. */
export default function ScoreGauge({
  score,
  benchmark,
  compact = false,
}: {
  score: number;
  benchmark?: number;
  compact?: boolean;
}) {
  const gain = score - baseline.score;
  const target = baseline.score + TARGET_GAIN;
  return (
    <figure className={`gauge ${compact ? "compact" : ""}`}>
      <figcaption>Astana Quality of Life Score</figcaption>
      <div className="gauge-number">
        <strong>{fmt(score)}</strong>
        {Math.abs(gain) > 0.005 && (
          <span className={gain < 0 ? "down" : "up"}>{signed(gain)}</span>
        )}
      </div>
      <div
        className="gauge-track"
        role="img"
        aria-label={`Балл ${fmt(score)}, исходный ${fmt(baseline.score)}, цель ${fmt(target)}`}
      >
        <span className="gauge-fill" style={{ left: at(baseline.score), width: `calc(${at(score)} - ${at(baseline.score)})` }} />
        <span className="gauge-mark ghost" style={{ left: at(baseline.score) }} />
        <span className="gauge-mark target" style={{ left: at(target) }} />
        {benchmark !== undefined && (
          <span className="gauge-mark bench" style={{ left: at(benchmark) }} />
        )}
        <span className="gauge-dot" style={{ left: at(score) }} />
      </div>
      <p className="gauge-legend">
        <span className="key ghost" /> исходно {fmt(baseline.score)}
        <span className="key target" /> цель {fmt(target)}
        {benchmark !== undefined && (
          <>
            <span className="key bench" /> ориентир {fmt(benchmark)}
          </>
        )}
      </p>
    </figure>
  );
}
