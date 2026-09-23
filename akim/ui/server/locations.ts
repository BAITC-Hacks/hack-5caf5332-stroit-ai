import places from "./astana-places.json" with { type: "json" };
import { districts } from "../src/data";
import { geoCenters } from "../src/geography";
import type { ComplaintLocation } from "../src/complaints";
export const normalizePlace = (s: string) =>
  s
    .toLowerCase()
    .normalize("NFKC")
    .replace(/ё/g, "е")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
const stop = new Set([
  "улица",
  "ул",
  "проспект",
  "пр",
  "переулок",
  "проезд",
  "бульвар",
  "шоссе",
  "набережная",
  "площадь",
  "даңғылы",
  "көшесі",
  "street",
  "avenue",
  "road",
  "имени",
  "им",
  "сакена",
  "сәкен",
]);
// OSM ways can carry different Russian inflections but the same Kazakh name.
// Collapse nearby entries with an identical full alias before offering choices.
type PlaceEntry = { place: (typeof places)[number]; id: number };
const byAlias = new Map<string, PlaceEntry[]>();
const unique: PlaceEntry[] = [];
places.forEach((place, id) => {
  const aliases = [...new Set(place.aliases.map(normalizePlace))];
  const duplicate = aliases
    .flatMap((a) => byAlias.get(a) ?? [])
    .find(
      ({ place: other }) =>
        Math.hypot(
          (place.point[0] - other.point[0]) * 111,
          (place.point[1] - other.point[1]) * 70,
        ) < 2,
    );
  const entry = duplicate ?? { place, id };
  if (duplicate)
    entry.place = {
      ...entry.place,
      aliases: [...new Set([...entry.place.aliases, ...place.aliases])],
    };
  else unique.push(entry);
  for (const alias of aliases) {
    const entries = byAlias.get(alias) ?? [];
    if (!entries.includes(entry)) entries.push(entry);
    byAlias.set(alias, entries);
  }
});
const index = unique.map(({ place: p, id: i }) => ({
  id: `street-${i}`,
  name: p.name,
  point: p.point as [number, number],
  aliases: p.aliases
    .map((a) =>
      normalizePlace(a)
        .split(" ")
        .filter((t) => !stop.has(t)),
    )
    .flatMap((a) => {
      const last = a.at(-1)!;
      return a.length > 1 &&
        last.length >= 6 &&
        !["батыр", "батыра", "даңғылы"].includes(last)
        ? [a, [last]]
        : [a];
    })
    .filter((a) => a.join("").length >= 5),
}));
function wordMatches(a: string, b: string) {
  if (a === b) return true;
  const stem = a.replace(/[аыиуея]$/, "");
  return stem.length >= 6 && b.startsWith(stem) && b.length <= stem.length + 3;
}
export function locationCandidates(text: string): ComplaintLocation[] {
  const normalized = normalizePlace(text),
    words = normalized.split(" "),
    found: ComplaintLocation[] = [];
  for (const p of index)
    if (
      p.aliases.some((a) =>
        a.every((t) => words.some((w) => wordMatches(t, w))),
      )
    )
      found.push({ id: p.id, name: p.name, kind: "street", point: p.point });
  for (const d of districts)
    if (
      new RegExp(
        `(?:район\\p{L}* ${normalizePlace(d.name)}|${normalizePlace(d.name)}\\p{L}* район)`,
        "u",
      ).test(normalized)
    )
      found.push({
        id: `district-${d.id}`,
        name: `Район ${d.name}`,
        kind: "district",
        point: geoCenters[d.id],
      });
  return found.slice(0, 8);
}
