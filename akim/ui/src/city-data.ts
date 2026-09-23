export interface SourceRecord<T = unknown> {
  id: string;
  name: string;
  url: string;
  attribution: string;
  status: "live" | "cached" | "unavailable";
  fetchedAt: string | null;
  observedAt: string | null;
  data: T | null;
  note: string;
  error?: string;
}
export interface CityData {
  weather: SourceRecord<{ temperature: number; wind: number; code: number }>;
  air: SourceRecord<{ aqi: number; pm25: number; pm10: number }>;
  accidents: SourceRecord<{ count: number; year: number; bounds: number[] }>;
  population: SourceRecord<{ total: number; period: string }>;
  boundaries: SourceRecord<{
    districts: { kato: string; name: string }[];
    parts: number;
  }>;
}
export interface ServiceHealth {
  jevConfigured?: boolean;
  configured: boolean;
  model: string;
  token: string;
}
export interface ActivityEvent {
  label: string;
  detail: string;
  at: string;
}
