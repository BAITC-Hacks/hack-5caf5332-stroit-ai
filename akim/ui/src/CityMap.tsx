import { useEffect, useRef, useState } from "react";
import { districts, type DistrictId } from "./data";
import { baseline, type Projection } from "./engine";
import type { Poll } from "./residents";
export function seeded(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function inside(x: number, y: number, points: [number, number][]) {
  let yes = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const [xi, yi] = points[i],
      [xj, yj] = points[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi)
      yes = !yes;
  }
  return yes;
}
const random = seeded(711);
const people = districts.flatMap((d) =>
  Array.from({ length: Math.round(d.population * 2000) }, (_, i) => {
    let x = 0,
      y = 0;
    do {
      x = 220 + random() * 845;
      y = 98 + random() * 612;
    } while (!inside(x, y, d.polygon));
    return {
      x,
      y,
      district: d.id,
      index: i,
      color: [
        "#f1dfb5",
        "#e89a78",
        "#cbe5db",
        "#eee9d9",
        "#dda5b7",
        "#b2cbd6",
        "#eac26c",
      ][Math.floor(random() * 7)],
    };
  }),
);
const districtPaths = districts.map((d) => {
  const p = new Path2D();
  d.polygon.forEach(([x, y], i) => (i ? p.lineTo(x, y) : p.moveTo(x, y)));
  p.closePath();
  return p;
});
const river = new Path2D(
  "M 176 405 C 257 370 269 428 334 414 S 398 462 442 437 S 511 403 551 430 S 662 469 711 433 S 762 381 806 413 S 856 469 920 488 S 1020 473 1100 548",
);
const roadLines = [
  "M250 275 L1000 365",
  "M290 560 L961 576",
  "M370 171 L453 688",
  "M525 158 L510 680",
  "M673 100 L661 413",
  "M846 183 L791 680",
  "M994 309 L928 623",
  "M256 316 L1008 417",
  "M303 637 L900 282",
  "M301 219 L962 625",
];
function buildBase() {
  const canvas = document.createElement("canvas");
  canvas.width = 2400;
  canvas.height = 1700;
  const ctx = canvas.getContext("2d")!;
  ctx.scale(2, 2);
  const rand = seeded(14);
  // A quiet, abstract green belt makes the schematic city read as one land mass.
  ctx.save();
  ctx.shadowColor = "#061f2a77";
  ctx.shadowBlur = 45;
  ctx.shadowOffsetY = 15;
  ctx.fillStyle = "#6f9380";
  ctx.beginPath();
  ctx.moveTo(231, 231);
  ctx.bezierCurveTo(320, 100, 458, 145, 554, 107);
  ctx.bezierCurveTo(684, 23, 753, 108, 885, 159);
  ctx.bezierCurveTo(1047, 182, 1115, 366, 1070, 467);
  ctx.bezierCurveTo(1166, 650, 890, 759, 680, 736);
  ctx.bezierCurveTo(480, 789, 261, 705, 208, 595);
  ctx.bezierCurveTo(120, 477, 234, 354, 231, 231);
  ctx.fill();
  ctx.restore();
  for (let i = 0; i < districts.length; i++) {
    const d = districts[i];
    ctx.fillStyle = d.color;
    ctx.fill(districtPaths[i]);
    ctx.save();
    ctx.clip(districtPaths[i]);
    // Fine streets and individual roofs are fixed in world coordinates.
    ctx.strokeStyle = "#d4d5bd";
    ctx.lineWidth = 3;
    for (let x = 180; x < 1110; x += 21) {
      ctx.beginPath();
      ctx.moveTo(x, 80);
      ctx.lineTo(x + 35, 760);
      ctx.stroke();
    }
    for (let y = 90; y < 760; y += 19) {
      ctx.beginPath();
      ctx.moveTo(170, y);
      ctx.lineTo(1100, y + 35);
      ctx.stroke();
    }
    for (let y = 110; y < 725; y += 10)
      for (let x = 225; x < 1060; x += 11) {
        if (rand() < 0.22) continue;
        const xx = x + rand() * 4,
          yy = y + rand() * 4;
        if (rand() < 0.13) {
          ctx.fillStyle = "#7eab83";
          ctx.beginPath();
          ctx.arc(xx, yy, 3 + rand() * 3, 0, Math.PI * 2);
          ctx.fill();
          continue;
        }
        const w = 3 + rand() * 5,
          h = 3 + rand() * 5;
        ctx.fillStyle = "#6f81795c";
        ctx.fillRect(xx + 2, yy + 2, w, h);
        ctx.fillStyle = [
          "#d6d2ba",
          "#bac7bf",
          "#dfdbca",
          "#96aca5",
          "#e6dbc0",
          "#b0b9a8",
        ][Math.floor(rand() * 6)];
        ctx.fillRect(xx, yy, w, h);
        ctx.fillStyle = "#f2eadb88";
        ctx.fillRect(xx, yy, w, 1);
      }
    ctx.strokeStyle = "#92a588";
    ctx.lineWidth = 16;
    ctx.stroke(new Path2D(roadLines[i]));
    ctx.strokeStyle = "#eee5c8";
    ctx.lineWidth = 7;
    for (const line of roadLines) ctx.stroke(new Path2D(line));
    ctx.strokeStyle = "#f8f3dd";
    ctx.lineWidth = 2;
    for (const line of roadLines) ctx.stroke(new Path2D(line));
    // Pocket parks, tree canopies, and a small sports field.
    for (let p = 0; p < 9; p++) {
      const x = 250 + rand() * 770,
        y = 170 + rand() * 470;
      ctx.fillStyle = "#82a27d";
      ctx.fillRect(x, y, 22 + rand() * 20, 15 + rand() * 18);
      for (let t = 0; t < 7; t++) {
        ctx.fillStyle = t % 2 ? "#638e70" : "#75a17c";
        ctx.beginPath();
        ctx.arc(x + rand() * 30, y + rand() * 20, 3, 0, 7);
        ctx.fill();
      }
    }
    ctx.restore();
  }
  ctx.lineCap = "round";
  ctx.strokeStyle = "#d4d5b5";
  ctx.lineWidth = 24;
  ctx.stroke(river);
  ctx.strokeStyle = "#3a7886";
  ctx.lineWidth = 17;
  ctx.stroke(river);
  ctx.strokeStyle = "#689a9e";
  ctx.lineWidth = 1;
  ctx.stroke(river);
  ctx.save();
  ctx.translate(616, 450);
  ctx.rotate(0.1);
  ctx.fillStyle = "#d9e8df";
  ctx.font = "italic 9px sans-serif";
  ctx.fillText("Есіл / Ишим", 0, 0);
  ctx.restore();
  for (const [x, y] of [
    [337, 417],
    [553, 435],
    [707, 434],
    [907, 483],
  ]) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(-0.4);
    ctx.fillStyle = "#d8d4bc";
    ctx.fillRect(-5, -19, 10, 38);
    ctx.fillStyle = "#f5ead0";
    ctx.fillRect(-1, -19, 2, 38);
    ctx.restore();
  }
  // Stylized Baiterek and Khan Shatyr landmarks, part of the map itself.
  ctx.save();
  ctx.translate(711, 550);
  ctx.fillStyle = "#67827688";
  ctx.beginPath();
  ctx.ellipse(8, 12, 17, 6, -0.3, 0, 7);
  ctx.fill();
  ctx.strokeStyle = "#f6eed2";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(-7, 8);
  ctx.lineTo(-3, -20);
  ctx.moveTo(7, 8);
  ctx.lineTo(3, -20);
  ctx.stroke();
  ctx.fillStyle = "#c8a555";
  ctx.beginPath();
  ctx.arc(0, -23, 8, 0, 7);
  ctx.fill();
  ctx.fillStyle = "#f8da89";
  ctx.beginPath();
  ctx.arc(-2, -26, 3, 0, 7);
  ctx.fill();
  ctx.restore();
  ctx.save();
  ctx.translate(533, 550);
  ctx.fillStyle = "#e6ddc1";
  ctx.beginPath();
  ctx.moveTo(0, -25);
  ctx.lineTo(-17, 6);
  ctx.quadraticCurveTo(0, 17, 21, 6);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = "#a6a48c";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, -25);
  ctx.lineTo(2, 11);
  ctx.stroke();
  ctx.restore();
  return canvas;
}
interface Props {
  selected: DistrictId | null;
  onSelect: (id: DistrictId) => void;
  result: Projection | null;
  after: boolean;
  poll: Poll | null;
  panelOpen: boolean;
}
export default function CityMap({
  selected,
  onSelect,
  result,
  after,
  poll,
  panelOpen,
}: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const born = useRef(performance.now());
  const base = useRef<HTMLCanvasElement | null>(null);
  const [size, setSize] = useState({ w: 1200, h: 850 });
  const [hover, setHover] = useState<DistrictId | null>(null);
  const camera = useRef({ x: 640, y: 410, zoom: 1 });
  const target = useRef(camera.current);
  const sizeRef = useRef(size);
  const snapshot = useRef({ selected, result, after, poll, hover });
  snapshot.current = { selected, result, after, poll, hover };
  const [labels, setLabels] = useState({ scale: 1, tx: 0, ty: 0 });
  useEffect(() => {
    const canvas = ref.current!;
    const resize = new ResizeObserver(([e]) => {
      const next = { w: e.contentRect.width, h: e.contentRect.height };
      sizeRef.current = next;
      setSize(next);
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = next.w * ratio;
      canvas.height = next.h * ratio;
    });
    resize.observe(canvas);
    return () => resize.disconnect();
  }, []);
  useEffect(() => {
    const d = districts.find((d) => d.id === selected);
    const mobile = size.w < 760;
    target.current = {
      x: d ? d.center[0] : 635,
      y: d ? d.center[1] : 410,
      zoom: d ? (mobile ? 1.7 : 2) : 1,
    };
  }, [selected, size.w]);
  useEffect(() => {
    if (!base.current) base.current = buildBase();
    const canvas = ref.current!;
    const ctx = canvas.getContext("2d")!;
    const started = born.current;
    let raf = 0;
    let lastLabels = 0;
    let cancelled = false;
    const reduced = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    let lastPaint = "";
    let lastResult: Projection | null | undefined;
    let lastPoll: Poll | null | undefined;
    const draw = (time: number) => {
      if (cancelled) return;
      const { w, h } = sizeRef.current;
      const mobile = w < 760;
      const t = target.current,
        c = camera.current;
      const ease = reduced ? 1 : 0.12;
      c.x += (t.x - c.x) * ease;
      c.y += (t.y - c.y) * ease;
      c.zoom += (t.zoom - c.zoom) * ease;
      const fit = Math.min(
        w / (mobile ? 1000 : 1350),
        h / (mobile ? 950 : 890),
      );
      const scale = fit * c.zoom;
      const shift = mobile ? 0 : panelOpen ? 155 : 70;
      const tx = w / 2 - c.x * scale + shift;
      const ty = h * (mobile ? 0.4 : 0.5) - c.y * scale;
      const scene = snapshot.current;
      const paintKey = [
        w,
        h,
        tx.toFixed(2),
        ty.toFixed(2),
        scale.toFixed(4),
        scene.selected,
        scene.after,
        scene.hover,
      ].join("|");
      if (
        time - started > 1150 &&
        paintKey === lastPaint &&
        scene.result === lastResult &&
        scene.poll === lastPoll
      ) {
        raf = requestAnimationFrame(draw);
        return;
      }
      lastPaint = paintKey;
      lastResult = scene.result;
      lastPoll = scene.poll;
      const ratio = canvas.width / w;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, w, h);
      ctx.translate(tx, ty);
      ctx.scale(scale, scale);
      ctx.drawImage(base.current!, 0, 0, 1200, 850);
      const s = snapshot.current;
      districts.forEach((d, i) => {
        const isSelected = d.id === s.selected;
        const score =
          s.result?.districts[i].score ?? baseline.districts[i].score;
        if (s.result && s.after) {
          ctx.fillStyle = `rgba(179,234,140,${Math.min(0.5, (score - baseline.districts[i].score) * 0.055)})`;
          ctx.fill(districtPaths[i]);
        }
        ctx.lineWidth = (isSelected ? 2.5 : 1) / scale;
        ctx.strokeStyle = isSelected
          ? "#f1ffba"
          : s.hover === d.id
            ? "#fcf7d4"
            : "#eef2d378";
        ctx.setLineDash(isSelected ? [] : [4 / scale, 5 / scale]);
        ctx.stroke(districtPaths[i]);
        ctx.setLineDash([]);
        if (s.selected && !isSelected) {
          ctx.fillStyle = "#173d5044";
          ctx.fill(districtPaths[i]);
        }
      });
      const reveal = reduced ? 1 : Math.min(1, (time - started) / 1100);
      for (let i = 0; i < people.length; i++) {
        if (((i * 7919) % people.length) / people.length > reveal) continue;
        const p = people[i];
        const districtIndex = districts.findIndex((d) => d.id === p.district);
        const approval = s.poll?.districts[districtIndex];
        const yes = approval ? p.index < approval.yes : false;
        const delta = s.result
          ? s.result.districts[districtIndex].score -
            baseline.districts[districtIndex].score
          : 0;
        const color = approval
          ? yes
            ? "#86c466"
            : "#df7762"
          : s.result && s.after && delta > 0
            ? "#b0d573"
            : p.color;
        ctx.globalAlpha = s.selected && s.selected !== p.district ? 0.48 : 1;
        ctx.fillStyle = "#264a46a0";
        ctx.fillRect(p.x - 1.1, p.y - 2, 2.9, 5.3);
        ctx.fillStyle = color;
        ctx.fillRect(p.x - 0.8, p.y - 0.6, 2.1, 3.1);
        ctx.fillStyle = "#f4dfba";
        ctx.fillRect(p.x - 0.5, p.y - 1.8, 1.4, 1.3);
        if (c.zoom > 1.6) {
          ctx.fillStyle = "#335657";
          ctx.fillRect(p.x - 0.7, p.y + 2.2, 0.6, 0.9);
          ctx.fillRect(p.x + 0.5, p.y + 2.2, 0.6, 0.9);
        }
      }
      ctx.globalAlpha = 1;
      if (time - lastLabels > 30) {
        setLabels((old) =>
          Math.abs(old.scale - scale) < 0.0001 &&
          Math.abs(old.tx - tx) < 0.05 &&
          Math.abs(old.ty - ty) < 0.05
            ? old
            : { scale, tx, ty },
        );
        lastLabels = time;
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
    };
  }, [panelOpen]);
  const hit = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const x = (e.clientX - labels.tx) / labels.scale,
      y = (e.clientY - labels.ty) / labels.scale;
    return districts.find((d) => inside(x, y, d.polygon))?.id ?? null;
  };
  return (
    <div className="city-map">
      <canvas
        ref={ref}
        aria-label="Схематичная карта Астаны с 2000 синтетическими жителями. Выберите район кнопками на карте."
        onPointerMove={(e) => setHover(hit(e))}
        onPointerLeave={() => setHover(null)}
        onClick={(e) => {
          const id = hit(e);
          if (id) onSelect(id);
        }}
        style={{ cursor: hover ? "pointer" : "default" }}
      />
      <div className="map-labels">
        {districts.map((d, i) => {
          const row =
            result && after ? result.districts[i] : baseline.districts[i];
          return (
            <button
              key={d.id}
              className={`district-label ${selected === d.id ? "selected" : ""}`}
              style={{
                left: d.center[0] * labels.scale + labels.tx,
                top: (d.center[1] - 24) * labels.scale + labels.ty,
                opacity: selected && selected !== d.id ? 0.55 : 1,
              }}
              onClick={() => onSelect(d.id)}
              aria-pressed={selected === d.id}
              aria-label={`Район ${d.name}`}
            >
              <span>{d.name}</span>
              <small>
                {row.score.toFixed(1)}
                {result && after && (
                  <b>
                    {" "}
                    +{(row.score - baseline.districts[i].score).toFixed(1)}
                  </b>
                )}
              </small>
            </button>
          );
        })}
      </div>
      {selected &&
        districts
          .find((d) => d.id === selected)!
          .voices.map((voice, i) => (
            <div
              className={`thought thought-${i}`}
              key={voice}
              style={{
                left:
                  (districts.find((d) => d.id === selected)!.center[0] +
                    (i ? 90 : -100)) *
                    labels.scale +
                  labels.tx,
                top:
                  (districts.find((d) => d.id === selected)!.center[1] +
                    (i ? 65 : -65)) *
                    labels.scale +
                  labels.ty,
              }}
            >
              {poll
                ? poll.districts.find((d) => d.id === selected)!.quote
                : voice}
            </div>
          ))}
    </div>
  );
}
