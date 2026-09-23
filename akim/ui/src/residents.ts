import { BUDGET_LIMIT } from "./money";
import {
  districts,
  indicators,
  indicatorNames,
  type Choice,
  type DistrictId,
  type Indicator,
} from "./data";
import { budget, projectEffects, validate } from "./engine";
export const examples = [
  "Школа и детсад в Нуре?",
  "ЛРТ в Есиле или школа и поликлиника в Нуре?",
  "Что жители думают о моём плане?",
];
interface PollDistrict {
  id: DistrictId;
  approval: number;
  yes: number;
  total: number;
  quote: string;
  reason: Indicator | null;
}
export interface Poll {
  title: string;
  approval: number;
  districts: PollDistrict[];
  comparison?: { title: string; approval: number; cost?: number };
  primaryLabel?: string;
  cost: number;
  mode?: "live" | "local";
  model?: string;
  cached?: boolean;
  cohorts?: {
    districtId: DistrictId;
    profileId: number;
    yes: number;
    total: number;
    probability: number;
    quote: string;
  }[];
}
const profiles: Indicator[][] = [
  ["S1", "S2"],
  ["T1", "B2"],
  ["T2", "E1"],
  ["S2", "C1"],
  ["B1", "C2"],
  ["E2", "E1"],
];
export function pollProposal(plan: Choice[], title: string): Poll {
  const effect = projectEffects(plan);
  const cost = budget(plan);
  const rows: PollDistrict[] = districts.map((d, i) => {
    const delta = effect.districts[i].delta;
    const support = profiles.map((profile) => {
      const concern = indicators.map(
        (k) =>
          1 + (d.needs.includes(k) ? 3 : 0) + (profile.includes(k) ? 4 : 0),
      );
      const gain =
        indicators.reduce((s, k, j) => s + delta[k] * concern[j], 0) /
        concern.reduce((a, b) => a + b, 0);
      return Math.max(
        0.08,
        Math.min(0.94, 0.5 + gain * 0.075 - (cost / BUDGET_LIMIT) * 0.065),
      );
    });
    const total = Math.round(d.population * 2000);
    const yes = Math.round(
      (total * support.reduce((a, b) => a + b, 0)) / support.length,
    );
    const ranked = [...indicators].sort((a, b) => delta[b] - delta[a]);
    const reason = delta[ranked[0]] > 0 ? ranked[0] : null;
    const negative = indicators.find((k) => delta[k] < 0);
    const quote = negative
      ? `«${indicatorNames[negative]} ухудшается. Это меня беспокоит.»`
      : reason
        ? yes / total < 0.5
          ? `«Улучшение есть: ${indicatorNames[reason].toLocaleLowerCase("ru")}. Но общие расходы велики, а главные потребности района остаются.»`
          : `«Вижу улучшение: ${indicatorNames[reason].toLocaleLowerCase("ru")}. Для нашего района это важно.»`
        : "«Расходы общие, а наши главные проблемы пока остаются.»";
    return {
      id: d.id,
      approval: (yes / total) * 100,
      yes,
      total,
      quote,
      reason,
    };
  });
  return {
    title,
    approval: rows.reduce((s, d) => s + d.yes, 0) / 20,
    districts: rows,
    cost,
  };
}
const normalize = (s: string) =>
  s
    .toLocaleLowerCase("ru")
    .replace(/ё/g, "е")
    .replace(/[?!.]/g, "")
    .replace(/\s+/g, " ")
    .trim();
export function askCity(
  question: string,
  plan: Choice[],
): { poll: Poll | null; error: string | null } {
  const q = normalize(question);
  if (q === normalize(examples[0]))
    return {
      poll: pollProposal(
        [{ measureId: "M7", districtId: "nura" }],
        examples[0],
      ),
      error: null,
    };
  if (q === normalize(examples[1])) {
    const social = pollProposal(
      [
        { measureId: "M7", districtId: "nura" },
        { measureId: "M8", districtId: "nura" },
      ],
      "Школа + поликлиника в Нуре",
    );
    const lrt = pollProposal(
      [{ measureId: "M3", districtId: "esil" }],
      "ЛРТ в Есиле",
    );
    return {
      poll: {
        ...social,
        title: examples[1],
        comparison: {
          title: lrt.title,
          approval: lrt.approval,
          cost: lrt.cost,
        },
      },
      error: null,
    };
  }
  if (q === normalize(examples[2]) || q === "мой план") {
    const errors = validate(plan);
    if (errors.length)
      return {
        poll: null,
        error:
          "Сначала соберите допустимый план из 5 решений. Или выберите пример о школе в Нуре.",
      };
    return { poll: pollProposal(plan, examples[2]), error: null };
  }
  return {
    poll: null,
    error:
      "В деморежиме доступны три вопроса ниже и «мой план». Выберите пример — для него есть локальная модель. Для свободных вопросов включите OpenAI.",
  };
}
