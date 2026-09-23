import { useEffect, useState } from "react";
import "./pixel-mayor.css";

// 16x16 sprite, one char per pixel. Overlays below swap mouth/eyes frames.
const SPRITE = [
  "....kkkkkkkk....",
  "...khhhhhhhhk...",
  "..khhhhhhhhhhk..",
  "..khhsssssshhk..",
  "..kssssssssssk..",
  "..kssessssessk..",
  "..kssssSSssssk..",
  "..ksssmmmmsssk..",
  "...kssssssssk...",
  "....kksssskk....",
  "...kjjwwwwjjk...",
  "..kjjjwttwjjjk..",
  ".kjgjjwttwjjjjk.",
  ".kjjjjJttJjjjjk.",
  ".kjjjjJttJjjjjk.",
  ".kjjjjjJJjjjjjk.",
];
const MOUTH_OPEN: [number, number, string][] = [
  [7, 7, "k"],
  [8, 7, "k"],
  [7, 8, "m"],
  [8, 8, "m"],
];
const EYES_SHUT: [number, number, string][] = [
  [5, 5, "S"],
  [10, 5, "S"],
];
const COLORS: Record<string, string> = {
  k: "#1b1b1f",
  h: "#2b1d14",
  s: "#e2ae80",
  S: "#c2875a",
  e: "#111",
  m: "#8a2f2f",
  w: "#f4f4f4",
  j: "#34466b",
  J: "#243252",
  t: "#c0392b",
  g: "#e8b923",
};

const px = ([x, y, c]: [number, number, string]) => (
  <rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill={COLORS[c]} />
);

// Types `title` then `text` out like a 2D-game dialogue box; the mayor's
// mouth moves while letters are still appearing. Long answers speed up so
// typing never takes much longer than ~1.5s, and a click skips it.
export default function PixelMayor({
  title,
  text,
}: {
  title: string;
  text: string;
}) {
  const full = `${title}\n${text}`;
  const [shown, setShown] = useState(0);
  useEffect(() => {
    setShown(0);
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setShown(full.length);
      return;
    }
    const step = Math.max(1, Math.ceil(full.length / 60));
    const id = setInterval(
      () => setShown((n) => Math.min(full.length, n + step)),
      25,
    );
    return () => clearInterval(id);
  }, [full]);
  const talking = shown < full.length;
  const skip = () => setShown(full.length);

  return (
    <div className={`pixel-mayor${talking ? " talking" : ""}`}>
      <div className="pixel-mayor-layout">
        <div className="pixel-mayor-head">
          <svg
            className="pixel-mayor-sprite"
            viewBox="0 0 16 16"
            shapeRendering="crispEdges"
            aria-hidden="true"
          >
            <g className="bob">
              {SPRITE.flatMap((row, y) =>
                [...row].map((c, x) => (c === "." ? null : px([x, y, c]))),
              )}
              <g className="mouth-open">{MOUTH_OPEN.map(px)}</g>
              <g className="eyes-shut">{EYES_SHUT.map(px)}</g>
            </g>
          </svg>
          <span className="pixel-mayor-name">АКИМ</span>
        </div>
        <div
          className="pixel-mayor-box"
          onClick={talking ? skip : undefined}
          onKeyDown={(e) =>
            talking && (e.key === "Enter" || e.key === " ") && skip()
          }
          tabIndex={talking ? 0 : -1}
        >
          <p aria-live="polite">
            <span className="visually-hidden">
              {title}. {text}
            </span>
            <span aria-hidden="true">
              <b>{title.slice(0, shown)}</b>
              {text.slice(0, Math.max(0, shown - title.length - 1))}
            </span>
            {!talking && (
              <span className="pixel-mayor-next" aria-hidden="true">
                ▼
              </span>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}
