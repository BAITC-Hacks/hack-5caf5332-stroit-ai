import { readFileSync, writeFileSync } from "node:fs";
const raw = JSON.parse(readFileSync(process.argv[2], "utf8"));
const grouped = new Map<
  string,
  { name: string; aliases: Set<string>; points: [number, number][] }
>();
for (const way of raw.elements) {
  const name = way.tags?.["name:ru"] || way.tags?.name;
  if (!name || !way.geometry) continue;
  const key = (way.tags["name:kk"] || name).toLowerCase().replace(/\s+/g, " ");
  if (!grouped.has(key))
    grouped.set(key, { name, aliases: new Set(), points: [] });
  const g = grouped.get(key)!;
  for (const k of [
    "name",
    "name:ru",
    "name:kk",
    "name:en",
    "alt_name",
    "old_name",
  ])
    if (way.tags[k]) for (const a of way.tags[k].split(";")) g.aliases.add(a);
  g.points.push(
    ...way.geometry.map(
      (p: { lat: number; lon: number }) => [p.lat, p.lon] as [number, number],
    ),
  );
}
const result = [...grouped.values()].map((g) => {
  const mean = g.points.reduce(
    (s, p) => [s[0] + p[0] / g.points.length, s[1] + p[1] / g.points.length],
    [0, 0],
  );
  const center = g.points.reduce((a, b) =>
    Math.hypot(a[0] - mean[0], a[1] - mean[1]) <
    Math.hypot(b[0] - mean[0], b[1] - mean[1])
      ? a
      : b,
  );
  return { name: g.name, aliases: [...g.aliases], point: center };
});
writeFileSync("server/astana-places.json", JSON.stringify(result));
console.log(result.length, "named streets");
