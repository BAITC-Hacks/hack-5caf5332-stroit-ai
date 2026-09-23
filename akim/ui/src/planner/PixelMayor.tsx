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
const MOUTH_OPEN: [number, number, string][] = [[7, 7, "k"], [8, 7, "k"], [7, 8, "m"], [8, 8, "m"]];
const EYES_SHUT: [number, number, string][] = [[5, 5, "S"], [10, 5, "S"]];
const COLORS: Record<string, string> = {
  k: "#1b1b1f", h: "#2b1d14", s: "#e2ae80", S: "#c2875a", e: "#111",
  m: "#8a2f2f", w: "#f4f4f4", j: "#34466b", J: "#243252", t: "#c0392b", g: "#e8b923",
};

const px = ([x, y, c]: [number, number, string]) => (
  <rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill={COLORS[c]} />
);

// Types `text` out like a 2D-game dialogue box; the mayor's mouth moves
// while letters are still appearing.
export default function PixelMayor({ text }: { text: string }) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    setShown(0);
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setShown(text.length);
      return;
    }
    const id = setInterval(() => setShown((n) => (n >= text.length ? n : n + 1)), 28);
    return () => clearInterval(id);
  }, [text]);
  const talking = shown < text.length;

  return (
    <div className={`pixel-mayor${talking ? " talking" : ""}`}>
      <svg className="pixel-mayor-sprite" viewBox="0 0 16 16" shapeRendering="crispEdges" aria-hidden="true">
        <g className="bob">
          {SPRITE.flatMap((row, y) => [...row].map((c, x) => (c === "." ? null : px([x, y, c]))))}
          <g className="mouth-open">{MOUTH_OPEN.map(px)}</g>
          <g className="eyes-shut">{EYES_SHUT.map(px)}</g>
        </g>
      </svg>
      <div className="pixel-mayor-box">
        <span className="pixel-mayor-name">АКИМ</span>
        <p aria-live="polite">
          <span className="visually-hidden">{text}</span>
          <span aria-hidden="true">{text.slice(0, shown)}</span>
          {!talking && <span className="pixel-mayor-next" aria-hidden="true">▼</span>}
        </p>
      </div>
    </div>
  );
}
