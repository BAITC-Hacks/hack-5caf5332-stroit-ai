import { measureById, type Choice, type Indicator } from "../data";
import { profiles } from "../population";
import { districtName, inDistrict, signed } from "../planner/analysis";

/** Short names for map markers and the decision tray. */
export const shortNames: Record<string, string> = {
  M1: "Автобусные полосы",
  M2: "Умные светофоры",
  M3: "ЛРТ",
  M4: "Парк",
  M5: "Чистое топливо",
  M6: "Озеленение",
  M7: "Школа и детсад",
  M8: "Поликлиника",
  M9: "Спорт-хабы",
  M10: "Освещение и камеры",
  M11: "Безопасные переходы",
  M12: "Платформа обращений",
  M13: "Сети ЖКХ",
  M14: "Аварийные бригады",
};

export const shortLabel = (c: Choice) =>
  c.districtId ? `${shortNames[c.measureId]}, ${districtName(c.districtId)}` : `${shortNames[c.measureId]}, весь город`;

const pluralNames: Record<string, string> = {
  Родитель: "родители",
  Водитель: "водители",
  Студент: "студенты",
  Пенсионер: "пенсионеры",
  Предприниматель: "предприниматели",
  Горожанин: "горожане",
};

/** One-line reaction shown right after a decision: who is happy, who is not. */
export function reaction(choice: Choice, gain: number) {
  const m = measureById(choice.measureId);
  const effects = m.effects as Partial<Record<Indicator, number>>;
  const happy = profiles
    .filter((p) => p.needs.some((k) => (effects[k] ?? 0) > 0))
    .map((p) => pluralNames[p.name]);
  const upset = profiles
    .filter((p) => p.needs.some((k) => (effects[k] ?? 0) < 0))
    .map((p) => pluralNames[p.name]);
  const where = choice.districtId ? ` ${inDistrict(choice.districtId)}` : " по всему городу";
  const parts = [`${shortNames[m.id]}${where}: ${signed(gain)} к баллу.`];
  if (happy.length) parts.push(`Довольны ${happy.join(", ")}.`);
  if (upset.length) parts.push(`Недовольны ${upset.join(", ")}.`);
  return parts.join(" ");
}
