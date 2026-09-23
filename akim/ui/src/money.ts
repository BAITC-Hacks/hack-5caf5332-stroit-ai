// All monetary values are million KZT. These are scoped scenario estimates,
// never presented as awarded procurement contracts or the city's free cash.
export const BUDGET_LIMIT = 50_000;
export const money = (amount: number) =>
  amount.toLocaleString("ru-RU", { maximumFractionDigits: 1 });
export const budgetSource = {
  title: "Бюджет Астаны на 2026 год",
  url: "https://old.adilet.zan.kz/rus/docs/G25AAZ3524M",
  verifiedAt: "2026-09-23",
  operatingCostsMln: 1_286_453.4108,
  note: "В документе затраты указаны в тысячах тенге; здесь переведены в миллионы. Это весь годовой объём затрат, а не доступный инвестиционный остаток.",
};
const schoolSource =
  "https://primeminister.kz/ru/news/asset_recovery/novaya-shkola-na-1200-uchenicheskih-mest-budet-postroena-v-astane-na-sredstva-iz-vozvrashchennyh-aktivov-31773";
const clinicSource =
  "https://www.gov.kz/memleket/entities/astana/documents/details/533548?lang=ru";
export interface CostEstimate {
  amount: number;
  basis: string;
  kind: "estimate" | "benchmark";
  source?: string;
}
export const costs: Record<string, CostEstimate> = {
  M1: {
    amount: 1800,
    kind: "estimate",
    basis:
      "Оценка сценария: выделенный автобусный коридор, разметка и переустройство остановок.",
  },
  M2: {
    amount: 2200,
    kind: "estimate",
    basis: "Оценка сценария: городской пакет адаптивных светофоров.",
  },
  M3: {
    amount: 30000,
    kind: "estimate",
    basis:
      "Оценка ограниченного этапа расширения ЛРТ. Не стоимость всей линии.",
  },
  M4: {
    amount: 1500,
    kind: "estimate",
    basis: "Оценка одного районного парка с благоустройством.",
  },
  M5: {
    amount: 2500,
    kind: "estimate",
    basis:
      "Оценка районной программы подключения частного сектора к чистому топливу.",
  },
  M6: {
    amount: 2000,
    kind: "estimate",
    basis: "Оценка городского пакета озеленения и ветрозащитных полос.",
  },
  M7: {
    amount: 8400,
    kind: "benchmark",
    source: schoolSource,
    basis:
      "Ориентир: 7 000 млн ₸ на школу на 1 200 мест по сообщению Правительства. Детсад и резерв: допущение +1 400 млн ₸. Это оценка комплекса.",
  },
  M8: {
    amount: 7200,
    kind: "benchmark",
    source: clinicSource,
    basis:
      "Исторический ориентир прогноза 2024–2028: 5 поликлиник за 36 000 млн ₸, в среднем 7 200 млн ₸. Не актуальная смета конкретного объекта.",
  },
  M9: {
    amount: 1000,
    kind: "estimate",
    basis: "Оценка районного пакета дворовых спорт-хабов.",
  },
  M10: {
    amount: 1200,
    kind: "estimate",
    basis: "Оценка расширения освещения и камер в одном районе.",
  },
  M11: {
    amount: 1000,
    kind: "estimate",
    basis: "Оценка районного пакета переходов и школьных зон.",
  },
  M12: {
    amount: 1400,
    kind: "estimate",
    basis:
      "Оценка городской платформы обращений с внедрением и эксплуатацией за горизонт сценария.",
  },
  M13: {
    amount: 28000,
    kind: "estimate",
    basis: "Оценка крупного районного этапа модернизации тепло- и водосетей.",
  },
  M14: {
    amount: 1600,
    kind: "estimate",
    basis: "Оценка городского усиления аварийных бригад и оповещения.",
  },
};
