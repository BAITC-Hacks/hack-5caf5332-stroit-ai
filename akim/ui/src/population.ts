import streetGraphs from "./astana-roads.json" with { type: "json" };
import { districts, type DistrictId } from "./data";
type Point = [number, number];
function seeded(seed: number) {
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
export { profiles, cohortSize } from "./profiles";
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
// Fictional journeys on an OSM street snapshot, ignoring access restrictions,
// traffic, one-way rules and travel speeds. These are not navigation directions.
function route(
  start: number,
  end: number,
  graph: { points: number[][]; edges: number[][] },
): Point[] {
  const parents = new Int32Array(graph.points.length).fill(-1);
  const queue = new Int32Array(graph.points.length);
  queue[0] = start;
  parents[start] = start;
  let tail = 1;
  for (let head = 0; head < tail; head++) {
    const node = queue[head];
    if (node === end) break;
    for (const next of graph.edges[node])
      if (parents[next] === -1) {
        parents[next] = node;
        queue[tail++] = next;
      }
  }
  if (parents[end] === -1) throw new Error("Disconnected street graph");
  const result: Point[] = [];
  for (let node = end; ; node = parents[node]) {
    result.push(graph.points[node] as Point);
    if (node === start) break;
  }
  return result.reverse();
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
    const graph = streetGraphs[d.id];
    const pick = () => Math.floor(rng() * graph.points.length);
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
          home: graph.points[home] as Point,
          work: graph.points[work] as Point,
          leisure: graph.points[leisure] as Point,
          toWork: route(home, work, graph),
          toLeisure: route(work, leisure, graph),
          toHome: route(leisure, home, graph),
          offset: Math.floor(rng() * 35),
        };
      },
    );
  });
}
export const population = generatePopulation();
function walk(path: Point[], progress: number): Point {
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
