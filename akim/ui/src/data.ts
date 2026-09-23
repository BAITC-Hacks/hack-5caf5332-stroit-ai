import { mainPolygon, geoCenters, toWorld } from "./geography";
import { costs } from "./money";
export const indicators = [
  "T1",
  "T2",
  "E1",
  "E2",
  "S1",
  "S2",
  "B1",
  "B2",
  "C1",
  "C2",
] as const;
export type Indicator = (typeof indicators)[number];
export type Values = Record<Indicator, number>;
export type DistrictId = "esil" | "almaty" | "saryarka" | "baikonur" | "nura";
export const directions = [
  "Транспорт",
  "Экология",
  "Соцсфера",
  "Безопасность",
  "Сервисы",
] as const;
export type Direction = (typeof directions)[number];
export const weights: Values = {
  T1: 0.1,
  T2: 0.1,
  E1: 0.09,
  E2: 0.11,
  S1: 0.11,
  S2: 0.11,
  B1: 0.09,
  B2: 0.09,
  C1: 0.1,
  C2: 0.1,
};
export const indicatorNames: Record<Indicator, string> = {
  T1: "Разгрузка дорог",
  T2: "Общественный транспорт",
  E1: "Озеленение",
  E2: "Качество воздуха",
  S1: "Школы и детсады",
  S2: "Поликлиники",
  B1: "Безопасность улиц",
  B2: "Безопасность на дорогах",
  C1: "Надёжность ЖКХ",
  C2: "Решение обращений",
};
const values = (v: number[]): Values =>
  Object.fromEntries(indicators.map((k, i) => [k, v[i]])) as Values;
export interface District {
  id: DistrictId;
  name: string;
  population: number;
  values: Values;
  needs: Indicator[];
  description: string;
  voices: string[];
  center: [number, number];
  polygon: [number, number][];
  color: string;
}
export const districts: District[] = [
  {
    id: "esil",
    name: "Есиль",
    population: 0.27,
    values: values([45, 62, 68, 72, 48, 55, 78, 60, 75, 70]),
    needs: ["T1", "S1"],
    description:
      "Левый берег, новые кварталы. Мосты перегружены, школам не хватает мест.",
    voices: ["Каждое утро стою на мосту.", "Нужна школа ближе к дому."],
    center: [710, 578],
    polygon: [
      [562, 431],
      [697, 430],
      [768, 397],
      [824, 423],
      [909, 483],
      [984, 496],
      [992, 579],
      [945, 655],
      [868, 694],
      [737, 696],
      [687, 666],
      [608, 670],
      [566, 583],
    ],
    color: "#a7c4a3",
  },
  {
    id: "almaty",
    name: "Алматы",
    population: 0.24,
    values: values([40, 75, 50, 55, 60, 65, 62, 52, 50, 60]),
    needs: ["C1", "T1"],
    description:
      "Обжитый правый берег. Старым сетям нужно обновление, дорогам — разгрузка.",
    voices: [
      "Хотелось бы зимовать без аварий.",
      "Автобус есть, но он тоже стоит в пробке.",
    ],
    center: [851, 330],
    polygon: [
      [752, 213],
      [824, 172],
      [893, 192],
      [915, 231],
      [989, 263],
      [1014, 335],
      [1062, 372],
      [1022, 455],
      [977, 478],
      [913, 463],
      [842, 410],
      [785, 370],
      [741, 391],
      [714, 315],
    ],
    color: "#b9c5aa",
  },
  {
    id: "saryarka",
    name: "Сарыарка",
    population: 0.2,
    values: values([50, 70, 42, 40, 62, 68, 58, 55, 45, 55]),
    needs: ["E2", "E1"],
    description:
      "Старые кварталы и частный сектор. Чистый воздух и зелень — главные запросы.",
    voices: ["Зимой хочется открывать окна.", "Нашей улице нужен сквер."],
    center: [460, 268],
    polygon: [
      [271, 264],
      [307, 194],
      [394, 184],
      [426, 139],
      [520, 157],
      [544, 195],
      [607, 195],
      [623, 252],
      [588, 305],
      [584, 382],
      [522, 399],
      [467, 373],
      [414, 400],
      [341, 362],
      [294, 371],
      [259, 319],
    ],
    color: "#a9bba0",
  },
  {
    id: "baikonur",
    name: "Байконур",
    population: 0.13,
    values: values([52, 68, 55, 50, 58, 60, 52, 58, 55, 58]),
    needs: ["B1", "E2"],
    description:
      "Спокойные жилые кварталы. Больше света во дворах и чище воздух.",
    voices: ["Вечером во дворе темновато.", "Хочется больше зелени рядом."],
    center: [659, 267],
    polygon: [
      [563, 173],
      [584, 114],
      [650, 99],
      [706, 141],
      [758, 158],
      [772, 193],
      [731, 226],
      [697, 318],
      [719, 382],
      [677, 408],
      [602, 402],
      [605, 323],
      [642, 256],
      [623, 181],
    ],
    color: "#c1cab0",
  },
  {
    id: "nura",
    name: "Нура",
    population: 0.16,
    values: values([55, 40, 45, 65, 38, 35, 55, 50, 60, 50]),
    needs: ["S1", "S2", "T2"],
    description:
      "Молодой район, которому ещё предстоит вырасти. Не хватает школ, поликлиник и автобусов.",
    voices: [
      "До поликлиники еду в другой район.",
      "Ребёнок учится во вторую смену.",
    ],
    center: [442, 535],
    polygon: [
      [286, 405],
      [343, 387],
      [406, 423],
      [466, 398],
      [522, 425],
      [544, 448],
      [550, 536],
      [575, 600],
      [577, 674],
      [517, 707],
      [441, 677],
      [395, 696],
      [351, 643],
      [286, 632],
      [254, 561],
      [222, 525],
      [243, 456],
    ],
    color: "#b8c9ad",
  },
];
for (const district of districts) {
  district.polygon = mainPolygon(district.id);
  const [lat, lng] = geoCenters[district.id];
  district.center = toWorld(lng, lat);
}

export interface Measure {
  id: string;
  direction: Direction;
  name: string;
  type: "district" | "city";
  cost: number;
  lag: number;
  effects: Partial<Values>;
}
export const measures: Measure[] = [
  {
    id: "M1",
    direction: "Транспорт",
    name: "Выделенные полосы для автобусов",
    type: "district",
    cost: costs.M1.amount,
    lag: 2,
    effects: { T1: 6, T2: 9 },
  },
  {
    id: "M2",
    direction: "Транспорт",
    name: "Умные светофоры",
    type: "city",
    cost: costs.M2.amount,
    lag: 2,
    effects: { T1: 4, B2: 3 },
  },
  {
    id: "M3",
    direction: "Транспорт",
    name: "Линия ЛРТ / расширение",
    type: "district",
    cost: costs.M3.amount,
    lag: 4,
    effects: { T1: 16, T2: 20, E2: 4 },
  },
  {
    id: "M4",
    direction: "Экология",
    name: "Парк / сквер",
    type: "district",
    cost: costs.M4.amount,
    lag: 2,
    effects: { E1: 12, E2: 3, B1: 2 },
  },
  {
    id: "M5",
    direction: "Экология",
    name: "Перевод частного сектора на чистое топливо",
    type: "district",
    cost: costs.M5.amount,
    lag: 3,
    effects: { E2: 14, C1: 4 },
  },
  {
    id: "M6",
    direction: "Экология",
    name: "Городская программа озеленения и ветрозащитных полос",
    type: "city",
    cost: costs.M6.amount,
    lag: 4,
    effects: { E1: 5, E2: 3 },
  },
  {
    id: "M7",
    direction: "Соцсфера",
    name: "Школа + детсад",
    type: "district",
    cost: costs.M7.amount,
    lag: 3,
    effects: { S1: 16 },
  },
  {
    id: "M8",
    direction: "Соцсфера",
    name: "Центр семейного здоровья / поликлиника",
    type: "district",
    cost: costs.M8.amount,
    lag: 3,
    effects: { S2: 14 },
  },
  {
    id: "M9",
    direction: "Соцсфера",
    name: "Дворовые спорт-хабы",
    type: "district",
    cost: costs.M9.amount,
    lag: 1,
    effects: { S1: 3, S2: 3, B1: 3 },
  },
  {
    id: "M10",
    direction: "Безопасность",
    name: "Освещение и камеры",
    type: "district",
    cost: costs.M10.amount,
    lag: 1,
    effects: { B1: 12, B2: 2 },
  },
  {
    id: "M11",
    direction: "Безопасность",
    name: "Безопасные переходы и школьные зоны",
    type: "district",
    cost: costs.M11.amount,
    lag: 1,
    effects: { B2: 12, T1: -2 },
  },
  {
    id: "M12",
    direction: "Сервисы",
    name: "Единая цифровая платформа обращений",
    type: "city",
    cost: costs.M12.amount,
    lag: 1,
    effects: { C2: 5 },
  },
  {
    id: "M13",
    direction: "Сервисы",
    name: "Модернизация тепло- и водосетей",
    type: "district",
    cost: costs.M13.amount,
    lag: 4,
    effects: { C1: 18, E2: 2 },
  },
  {
    id: "M14",
    direction: "Сервисы",
    name: "Аварийные бригады ЖКХ + раннее оповещение",
    type: "city",
    cost: costs.M14.amount,
    lag: 1,
    effects: { C1: 5, C2: 2 },
  },
];
export interface Choice {
  measureId: string;
  districtId?: DistrictId;
}
export const samplePlan: Choice[] = [
  { measureId: "M7", districtId: "nura" },
  { measureId: "M8", districtId: "nura" },
  { measureId: "M10", districtId: "nura" },
  { measureId: "M12" },
  { measureId: "M5", districtId: "saryarka" },
];
export const synergies: {
  pair: [string, string];
  indicator: Indicator;
  bonus: number;
}[] = [
  { pair: ["M1", "M2"], indicator: "T1", bonus: 2 },
  { pair: ["M10", "M12"], indicator: "B1", bonus: 2 },
  { pair: ["M5", "M6"], indicator: "E2", bonus: 2 },
];
export const conflicts = [
  {
    pair: ["M1", "M3"],
    sameDistrict: false,
    reason: "M1 и M3: выберите автобусные полосы или ЛРТ.",
  },
  {
    pair: ["M4", "M7"],
    sameDistrict: true,
    reason: "M4 и M7: парк и школа занимают один участок в этом районе.",
  },
  {
    pair: ["M5", "M13"],
    sameDistrict: true,
    reason: "M5 и M13: программы дублируются в этом районе.",
  },
];
export const measureById = (id: string) => measures.find((m) => m.id === id)!;
export const districtById = (id: DistrictId) =>
  districts.find((d) => d.id === id)!;
export const choiceLabel = (c: Choice) =>
  `${measureById(c.measureId).name} · ${c.districtId ? districtById(c.districtId).name : "Весь город"}`;
