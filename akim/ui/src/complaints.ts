import type { Direction } from "./data";
export interface ComplaintLocation {
  id: string;
  name: string;
  kind: "street" | "district";
  point: [number, number];
}
export interface Complaint {
  sourceKind: "threads" | "press";
  id: string;
  url: string;
  title: string;
  summary: string;
  directions: Direction[];
  confidence: Record<string, number>;
  astanaProbability: number;
  complaintProbability: number;
  location: ComplaintLocation | null;
  decision: "accepted" | "review" | "excluded";
  reason: string;
}
export interface ComplaintCollection {
  posts: Complaint[];
  queries: string[];
  searchedQueries: string[];
  fetchedAt: string;
  model: string;
  cached: boolean;
  coverage: string;
}
export const complaintColors: Record<Direction, string> = {
  Транспорт: "#ba6435",
  Экология: "#44793e",
  Соцсфера: "#6461a0",
  Безопасность: "#ad4653",
  Сервисы: "#287d88",
};
