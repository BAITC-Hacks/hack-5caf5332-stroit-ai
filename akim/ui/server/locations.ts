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
const index = places.map((p, i) => ({
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
