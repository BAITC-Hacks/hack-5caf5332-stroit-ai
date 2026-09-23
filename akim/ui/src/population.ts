import { districts, type DistrictId, type Indicator } from "./data";
export type Point = [number, number];
export function seeded(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
export function inside(x: number, y: number, points: Point[]) {
  let yes = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const [xi, yi] = points[i],
      [xj, yj] = points[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi)
      yes = !yes;
  }
  return yes;
}
export const profiles: { name: string; needs: Indicator[]; routine: string }[] =
  [
    { name: "Родитель", needs: ["S1", "S2"], routine: "Работа, школа и семья" },
    { name: "Водитель", needs: ["T1", "B2"], routine: "Поездки и работа" },
    { name: "Студент", needs: ["T2", "E1"], routine: "Учёба и прогулки" },
    {
      name: "Пенсионер",
      needs: ["S2", "C1"],
      routine: "Покупки, поликлиника и дом",
    },
    {
      name: "Предприниматель",
      needs: ["B1", "C2"],
      routine: "Работа и дела района",
    },
    {
      name: "Горожанин",
      needs: ["E2", "E1"],
      routine: "Работа и отдых в парке",
    },
  ];
export interface Resident {
  id: number;
  districtId: DistrictId;
  districtIndex: number;
  index: number;
  profileId: number;
  cohortIndex: number;
  name: string;
  age: number;
  sprite: number;
  home: Point;
  work: Point;
  leisure: Point;
  toWork: Point[];
  toLeisure: Point[];
  toHome: Point[];
  offset: number;
}
// Original local implementation inspired by Sim Francisco's separation of seeded
// personas, routine-driven travel and batched opinion inference. Routes are synthetic.
function gridFor(polygon: Point[]) {
  const nodes = new Map<string, Point>();
  for (let x = 230; x <= 1060; x += 16)
    for (let y = 110; y <= 710; y += 16)
      if (inside(x, y, polygon)) nodes.set(`${x},${y}`, [x, y]);
  const neighbors = (p: Point) =>
    [
      [p[0] + 16, p[1]],
      [p[0] - 16, p[1]],
      [p[0], p[1] + 16],
      [p[0], p[1] - 16],
    ].filter(
      (q) =>
        nodes.has(q.join(",")) &&
        [0.25, 0.5, 0.75].every((t) =>
          inside(p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, polygon),
        ),
    ) as Point[];
  let biggest: Point[] = [];
  const seen = new Set<string>();
  for (const p of nodes.values()) {
    if (seen.has(p.join(","))) continue;
    const queue = [p];
    seen.add(p.join(","));
    for (let i = 0; i < queue.length; i++)
      for (const q of neighbors(queue[i]))
        if (!seen.has(q.join(","))) {
          seen.add(q.join(","));
          queue.push(q);
        }
    if (queue.length > biggest.length) biggest = queue;
  }
  return { nodes: biggest, neighbors };
}
function route(
  start: Point,
  end: Point,
  neighbors: (p: Point) => Point[],
): Point[] {
  const queue = [start],
    parents = new Map<string, Point | null>([[start.join(","), null]]);
  for (let i = 0; i < queue.length; i++) {
    const p = queue[i];
    if (p[0] === end[0] && p[1] === end[1]) break;
    for (const q of neighbors(p))
      if (!parents.has(q.join(","))) {
        parents.set(q.join(","), p);
        queue.push(q);
      }
  }
  const path: Point[] = [];
  let cursor: Point | null = end;
  while (cursor) {
    path.push(cursor);
    cursor = parents.get(cursor.join(",")) ?? null;
  }
  return path.reverse();
}
export function generatePopulation(seed = 711): Resident[] {
  const rng = seeded(seed);
  let id = 0;
  const names = [
    "Айдана",
    "Тимур",
    "Алия",
    "Марат",
    "Дана",
    "Арман",
    "Сауле",
    "Руслан",
    "Аружан",
    "Ерлан",
    "Жанна",
    "Алексей",
  ];
  return districts.flatMap((d, districtIndex) => {
    const grid = gridFor(d.polygon);
    const pick = () => grid.nodes[Math.floor(rng() * grid.nodes.length)];
    return Array.from(
      { length: Math.round(d.population * 2000) },
      (_, index) => {
        const home = pick(),
          work = pick(),
          leisure = pick(),
          profileId = index % 6;
        return {
          id: id++,
          districtId: d.id,
          districtIndex,
          index,
          profileId,
          cohortIndex: Math.floor(index / 6),
          name: names[Math.floor(rng() * names.length)],
          age:
            profileId === 2
              ? 18 + Math.floor(rng() * 7)
              : profileId === 3
                ? 62 + Math.floor(rng() * 19)
                : 25 + Math.floor(rng() * 34),
          sprite: Math.floor(rng() * 10),
          home,
          work,
          leisure,
          toWork: route(home, work, grid.neighbors),
          toLeisure: route(work, leisure, grid.neighbors),
          toHome: route(leisure, home, grid.neighbors),
          offset: Math.floor(rng() * 35),
        };
      },
    );
  });
}
export const population = generatePopulation();
export function cohortSize(districtId: DistrictId, profileId: number) {
  return population.filter(
    (p) => p.districtId === districtId && p.profileId === profileId,
  ).length;
}
export function walk(path: Point[], progress: number): Point {
  if (path.length === 1) return path[0];
  const t = Math.max(0, Math.min(1, progress)) * (path.length - 1);
  const a = path[Math.floor(t)],
    b = path[Math.min(path.length - 1, Math.floor(t) + 1)];
  return [a[0] + (b[0] - a[0]) * (t % 1), a[1] + (b[1] - a[1]) * (t % 1)];
}
export function residentState(
  p: Resident,
  minutes: number,
  stayInside = false,
) {
  const t = ((minutes % 1440) + 1440) % 1440;
  const workStart = 460 + p.offset,
    leisureStart = 1020 + p.offset,
    homeStart = 1230 + p.offset;
  const activity =
    p.profileId === 2
      ? "на учёбе"
      : p.profileId === 3
        ? "по делам"
        : "на работе";
  if (t < workStart) return { point: p.home, activity: "дома", moving: false };
  if (t < workStart + 60)
    return {
      point: walk(p.toWork, (t - workStart) / 60),
      activity: "в пути",
      moving: true,
    };
  if (t < leisureStart) return { point: p.work, activity, moving: false };
  if (stayInside) {
    if (t < leisureStart + 45)
      return {
        point: walk(p.toWork, 1 - (t - leisureStart) / 45),
        activity: "домой из-за погоды",
        moving: true,
      };
    return { point: p.home, activity: "дома из-за погоды", moving: false };
  }
  if (t < leisureStart + 45)
    return {
      point: walk(p.toLeisure, (t - leisureStart) / 45),
      activity: "в пути",
      moving: true,
    };
  if (t < homeStart)
    return { point: p.leisure, activity: "гуляет", moving: false };
  if (t < homeStart + 60)
    return {
      point: walk(p.toHome, (t - homeStart) / 60),
      activity: "возвращается домой",
      moving: true,
    };
  return { point: p.home, activity: "дома", moving: false };
}
export function activityCounts(minutes: number, stayInside = false) {
  return population.reduce(
    (acc, p) => {
      const s = residentState(p, minutes, stayInside);
      if (s.moving) acc.moving++;
      else if (s.activity.startsWith("дома")) acc.home++;
      else acc.busy++;
      return acc;
    },
    { moving: 0, home: 0, busy: 0 },
  );
}
