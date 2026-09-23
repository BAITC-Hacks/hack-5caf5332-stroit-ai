// Run: npx tsx scripts/prepare-roads.ts /path/to/overpass-roads.json
// Input: Overpass ways with nodes and geometry; see docs/MAP.md for the query.
import { readFileSync, writeFileSync } from "node:fs";
import { geographicDistricts, districtKato, toWorld } from "../src/geography";
function inside(x: number, y: number, ring: number[][]) {
  let yes = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i],
      [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi)
      yes = !yes;
  }
  return yes;
}
type Way = {
  nodes: number[];
  geometry: { lon: number; lat: number }[];
  tags: { highway: string };
};
const ways: Way[] = JSON.parse(
  readFileSync(process.argv[2], "utf8"),
).elements.filter((w: Way) =>
  ["primary", "secondary", "tertiary"].includes(w.tags.highway),
);
const output: Record<string, { points: number[][]; edges: number[][] }> = {};
for (const [id, kato] of Object.entries(districtKato)) {
  const polygons = geographicDistricts.features
    .filter((f) => f.properties.kato === kato)
    .flatMap((f) => f.geometry.coordinates);
  const positions = new Map<number, number[]>(),
    adj = new Map<number, Set<number>>();
  const contained = new Map<number, boolean>();
  const valid = (node: number, p: { lon: number; lat: number }) => {
    if (!contained.has(node))
      contained.set(
        node,
        polygons.some(
          (poly) =>
            inside(p.lon, p.lat, poly[0]) &&
            !poly.slice(1).some((r) => inside(p.lon, p.lat, r)),
        ),
      );
    return contained.get(node);
  };
  for (const w of ways)
    for (let i = 1; i < w.nodes.length; i++) {
      const a = w.nodes[i - 1],
        b = w.nodes[i],
        p = w.geometry[i - 1],
        q = w.geometry[i];
      if (!valid(a, p) || !valid(b, q)) continue;
      positions.set(a, toWorld(p.lon, p.lat));
      positions.set(b, toWorld(q.lon, q.lat));
      if (!adj.has(a)) adj.set(a, new Set());
      if (!adj.has(b)) adj.set(b, new Set());
      adj.get(a)!.add(b);
      adj.get(b)!.add(a);
    }
  let largest: number[] = [];
  const seen = new Set<number>();
  for (const node of adj.keys()) {
    if (seen.has(node)) continue;
    const queue = [node];
    seen.add(node);
    for (let i = 0; i < queue.length; i++)
      for (const q of adj.get(queue[i])!)
        if (!seen.has(q)) {
          seen.add(q);
          queue.push(q);
        }
    if (queue.length > largest.length) largest = queue;
  }
  const indices = new Map(largest.map((n, i) => [n, i]));
  output[id] = {
    points: largest.map((n) => positions.get(n)!.map((v) => +v.toFixed(5))),
    edges: largest.map((n) => [...adj.get(n)!].map((q) => indices.get(q)!)),
  };
  console.log(id, largest.length, "street vertices");
}
writeFileSync("src/astana-roads.json", JSON.stringify(output));
