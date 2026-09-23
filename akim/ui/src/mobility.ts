import streets from "./astana-roads.json" with { type: "json" };
import { districts, type Choice, type DistrictId } from "./data";
import { population, type Point, type Resident } from "./population";
import { toLatLng } from "./geography";
export type TravelMode = "car" | "bus" | "walk";
export interface Trip {
  district: DistrictId;
  route: number[];
  elapsed: number[];
  minutes: number;
  km: number;
  mode: TravelMode;
}
export interface MobilityMetrics {
  minutes: number;
  p90: number;
  km: number;
  carShare: number;
  congestedKm: number;
}
export interface MobilityPhase {
  trips: Trip[];
  metrics: MobilityMetrics;
  districts: Record<DistrictId, MobilityMetrics>;
  segments: { district: DistrictId; a: number; b: number; load: number }[];
}
export interface MobilityComparison {
  before: MobilityPhase;
  after: MobilityPhase;
  changedRoutes: number;
}
export const mobilityExample: Choice[] = [
  { measureId: "M7", districtId: "nura" },
  { measureId: "M8", districtId: "nura" },
  { measureId: "M1", districtId: "saryarka" },
  { measureId: "M2" },
  { measureId: "M12" },
];
export const streetPoint = (id: DistrictId, node: number) =>
  streets[id].points[node] as Point;
const key = (a: number, b: number) => (a < b ? `${a}:${b}` : `${b}:${a}`);
export function distanceKm(a: Point, b: Point) {
  const [lat1, lon1] = toLatLng(a),
    [lat2, lon2] = toLatLng(b),
    rad = Math.PI / 180;
  const h =
    Math.sin(((lat2 - lat1) * rad) / 2) ** 2 +
    Math.cos(lat1 * rad) *
      Math.cos(lat2 * rad) *
      Math.sin(((lon2 - lon1) * rad) / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
}
// All speeds, demand weights, capacities and intervention factors are scenario assumptions.
const models = districts.map((d) => {
  const g = streets[d.id],
    lookup = new Map(g.points.map((p, i) => [p.join(","), i]));
  const lengths = g.edges.map((edges, a) =>
    edges.map((b) => distanceKm(g.points[a] as Point, g.points[b] as Point)),
  );
  return { id: d.id, g, lookup, lengths };
});
class Heap {
  values: [number, number][] = [];
  push(node: number, cost: number) {
    const v: [number, number] = [node, cost];
    let i = this.values.length;
    this.values.push(v);
    while (i) {
      const p = (i - 1) >> 1;
      if (this.values[p][1] <= cost) break;
      this.values[i] = this.values[p];
      i = p;
    }
    this.values[i] = v;
  }
  pop() {
    const top = this.values[0],
      last = this.values.pop()!;
    if (this.values.length) {
      let i = 0;
      for (;;) {
        let c = i * 2 + 1;
        if (c >= this.values.length) break;
        if (
          c + 1 < this.values.length &&
          this.values[c + 1][1] < this.values[c][1]
        )
          c++;
        if (this.values[c][1] >= last[1]) break;
        this.values[i] = this.values[c];
        i = c;
      }
      this.values[i] = last;
    }
    return top;
  }
}
export function shortestRoute(
  start: number,
  end: number,
  edges: number[][],
  weights: number[][],
) {
  const dist = new Float64Array(edges.length).fill(Infinity),
    parent = new Int32Array(edges.length).fill(-1),
    heap = new Heap();
  dist[start] = 0;
  heap.push(start, 0);
  while (heap.values.length) {
    const [n, cost] = heap.pop();
    if (cost !== dist[n]) continue;
    if (n === end) break;
    for (let i = 0; i < edges[n].length; i++) {
      const b = edges[n][i],
        next = cost + weights[n][i];
      if (next < dist[b]) {
        dist[b] = next;
        parent[b] = n;
        heap.push(b, next);
      }
    }
  }
  if (!Number.isFinite(dist[end])) throw Error("No connected mobility route");
  const path = [end];
  while (path[path.length - 1] !== start)
    path.push(parent[path[path.length - 1]]);
  return path.reverse();
}
function modeFor(p: Resident, plan: Choice[]): TravelMode {
  const base = p.id % 10;
  if (base >= 8) return "walk";
  if (base >= 5) return "bus";
  const lrt = plan.some(
    (c) => c.measureId === "M3" && c.districtId === p.districtId,
  );
  const bus = plan.some(
    (c) => c.measureId === "M1" && c.districtId === p.districtId,
  );
  return (lrt && base < 3) || (bus && base === 0) ? "bus" : "car";
}
function metrics(
  trips: Trip[],
  segments: MobilityPhase["segments"],
  id?: DistrictId,
): MobilityMetrics {
  const sorted = trips.map((t) => t.minutes).sort((a, b) => a - b),
    n = trips.length || 1;
  return {
    minutes: trips.reduce((s, t) => s + t.minutes, 0) / n,
    p90: sorted[Math.max(0, Math.ceil(sorted.length * 0.9) - 1)] || 0,
    km: trips.reduce((s, t) => s + t.km, 0) / n,
    carShare: (100 * trips.filter((t) => t.mode === "car").length) / n,
    congestedKm: segments
      .filter((s) => s.load > 1 && (!id || s.district === id))
      .reduce(
        (sum, s) =>
          sum +
          distanceKm(
            streetPoint(s.district, s.a),
            streetPoint(s.district, s.b),
          ),
        0,
      ),
  };
}
function phase(plan: Choice[]): MobilityPhase {
  const trips: Trip[] = new Array(population.length),
    segments: MobilityPhase["segments"] = [];
  for (const model of models) {
    const { g, id, lookup, lengths } = model,
      people = population.filter((p) => p.districtId === id),
      smart = plan.some((c) => c.measureId === "M2"),
      bus = plan.some((c) => c.measureId === "M1" && c.districtId === id),
      lrt = plan.some((c) => c.measureId === "M3" && c.districtId === id);
    const loads = new Map<string, number>();
    let paths: number[][] = [];
    const cost = (
      mode: TravelMode,
      a: number,
      j: number,
      flow: Map<string, number>,
    ) => {
      const b = g.edges[a][j],
        km = lengths[a][j],
        capacity = bus ? 13.5 : 18,
        ratio = (flow.get(key(a, b)) || 0) / capacity;
      const delay = 1 + 0.15 * Math.min(3, ratio) ** 4;
      const junction = g.edges[b].length > 2 ? (smart ? 0.05 : 0.15) : 0;
      if (mode === "walk") return (km / 4.5) * 60;
      if (mode === "bus")
        return (
          (km / (lrt ? 26 : bus ? 22 : 18)) * 60 * (lrt || bus ? 1 : delay) +
          junction * (lrt ? 0.2 : 1)
        );
      return (km / 32) * 60 * delay + junction;
    };
    // Two deterministic assignment passes: free-flow demand, then one reroute using its congestion.
    for (let pass = 0; pass < 2; pass++) {
      const weights = Object.fromEntries(
        (["car", "bus", "walk"] as const).map((m) => [
          m,
          g.edges.map((es, a) => es.map((_, j) => cost(m, a, j, loads))),
        ]),
      ) as Record<TravelMode, number[][]>;
      const next = new Map<string, number>();
      paths = people.map((p) => {
        const mode = modeFor(p, plan),
          route = shortestRoute(
            lookup.get(p.home.join(","))!,
            lookup.get(p.work.join(","))!,
            g.edges,
            weights[mode],
          );
        for (let i = 1; i < route.length; i++) {
          const k = key(route[i - 1], route[i]);
          next.set(
            k,
            (next.get(k) || 0) +
              (mode === "car" ? 1 : mode === "bus" ? 0.08 : 0),
          );
        }
        return route;
      });
      loads.clear();
      for (const [k, v] of next) loads.set(k, v);
    }
    people.forEach((p, i) => {
      const route = paths[i],
        mode = modeFor(p, plan),
        elapsed = [0];
      let km = 0;
      for (let n = 1; n < route.length; n++) {
        const a = route[n - 1],
          j = g.edges[a].indexOf(route[n]);
        km += lengths[a][j];
        elapsed.push(elapsed[n - 1] + cost(mode, a, j, loads));
      }
      const wait = mode === "bus" ? (lrt ? 3 : bus ? 4 : 7) : 0;
      trips[p.id] = {
        district: id,
        route,
        elapsed,
        minutes: elapsed.at(-1)! + wait,
        km,
        mode,
      };
    });
    for (const [k, value] of loads) {
      const [a, b] = k.split(":").map(Number);
      if (value > 0)
        segments.push({ district: id, a, b, load: value / (bus ? 13.5 : 18) });
    }
  }
  return {
    trips,
    segments,
    metrics: metrics(trips, segments),
    districts: Object.fromEntries(
      districts.map((d) => [
        d.id,
        metrics(
          trips.filter((t) => t.district === d.id),
          segments,
          d.id,
        ),
      ]),
    ) as Record<DistrictId, MobilityMetrics>,
  };
}
export function compareMobility(plan: Choice[]): MobilityComparison {
  const relevant = plan.filter((c) => ["M1", "M2", "M3"].includes(c.measureId)),
    before = phase([]),
    after = relevant.length ? phase(relevant) : before;
  return {
    before,
    after,
    changedRoutes: after.trips.filter(
      (t, i) => t.route.join(",") !== before.trips[i].route.join(","),
    ).length,
  };
}
export function mobilityState(resident: Resident, minutes: number, trip: Trip) {
  const t = (((minutes % 1440) + 1440) % 1440) - (460 + resident.offset),
    wait = trip.minutes - trip.elapsed.at(-1)!;
  if (t <= 0) return { point: resident.home, moving: false, activity: "дома" };
  if (t >= trip.minutes)
    return {
      point: resident.work,
      moving: false,
      activity: resident.profileId === 2 ? "на учёбе" : "по делам",
    };
  if (t < wait)
    return {
      point: resident.home,
      moving: false,
      activity: "ожидает транспорт",
    };
  const travel = t - wait;
  let left = 0,
    right = trip.elapsed.length - 1;
  while (left + 1 < right) {
    const mid = (left + right) >> 1;
    if (trip.elapsed[mid] <= travel) left = mid;
    else right = mid;
  }
  const a = streetPoint(trip.district, trip.route[left]),
    b = streetPoint(trip.district, trip.route[right]),
    part =
      (travel - trip.elapsed[left]) /
      (trip.elapsed[right] - trip.elapsed[left] || 1);
  return {
    point: [a[0] + (b[0] - a[0]) * part, a[1] + (b[1] - a[1]) * part] as Point,
    moving: true,
    activity:
      trip.mode === "car"
        ? "едет на автомобиле"
        : trip.mode === "bus"
          ? "едет на транспорте"
          : "идёт пешком",
  };
}
