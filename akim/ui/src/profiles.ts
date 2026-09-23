import { districts, type DistrictId, type Indicator } from "./data";
export const profiles: { name: string; needs: Indicator[]; routine: string }[] =
  [
    { name: "Родитель", needs: ["S1", "S2"], routine: "Работа, школа и семья" },
    { name: "Водитель", needs: ["T1", "B2"], routine: "Поездки и работа" },
    { name: "Студент", needs: ["T2", "E1"], routine: "Учёба и прогулки" },
    {
      name: "Пенсионер",
      needs: ["S2", "C1"],
      routine: "Покупки, поликлиника и дом",
    },
    {
      name: "Предприниматель",
      needs: ["B1", "C2"],
      routine: "Работа и дела района",
    },
    {
      name: "Горожанин",
      needs: ["E2", "E1"],
      routine: "Работа и отдых в парке",
    },
  ];
export function cohortSize(districtId: DistrictId, profileId: number) {
  const d = districts.find((d) => d.id === districtId)!;
  const total = Math.round(d.population * 2000);
  return Math.floor(total / 6) + (profileId < total % 6 ? 1 : 0);
}
