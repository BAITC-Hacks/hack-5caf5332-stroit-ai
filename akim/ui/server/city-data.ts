import { z } from "zod";
import { memoryStore, type Store } from "./storage";
import type { CityData, SourceRecord } from "../src/city-data";
const weatherSchema = z.object({
  current: z.object({
    time: z.string(),
    temperature_2m: z.number(),
    wind_speed_10m: z.number(),
    weather_code: z.number(),
  }),
});
const airSchema = z.object({
  current: z.object({
    time: z.string(),
    european_aqi: z.number(),
    pm2_5: z.number(),
    pm10: z.number(),
  }),
});
const ua = {
  "User-Agent": "Mozilla/5.0 (Sim Astana; local civic simulation prototype)",
};
export const sourceUrls = {
  weather:
    "https://api.open-meteo.com/v1/forecast?latitude=51.1694&longitude=71.4491&current=temperature_2m,wind_speed_10m,weather_code&timezone=Asia%2FAlmaty",
  air: "https://air-quality-api.open-meteo.com/v1/air-quality?latitude=51.1694&longitude=71.4491&current=pm2_5,pm10,european_aqi&timezone=Asia%2FAlmaty",
  accidents:
    "https://gis.kgp.kz/arcgis/rest/services/KPSSU/DTP/FeatureServer/0/query?where=yr%3D2026&geometry=71.2%2C51.0%2C71.65%2C51.3&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&returnCountOnly=true&f=json",
  population: "https://stat.gov.kz/api/iblock/element/6584/json/file/ru/",
  boundaries:
    "https://map.gov.kz/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature&typeNames=geonode:border_districts&outputFormat=application/json&propertyName=kato,name_ru&CQL_FILTER=" +
    encodeURIComponent("kato LIKE '71%'"),
};
const metadata = {
  weather: {
    name: "Погода в Астане",
    attribution: "Open-Meteo · модель прогноза · CC BY 4.0",
    note: "Температура, ветер и погодный код в одной точке города. Это модель прогноза, не измерение городской станции.",
  },
  air: {
    name: "Качество воздуха",
    attribution: "Open-Meteo / Copernicus CAMS · CC BY 4.0",
    note: "Европейский AQI и PM2.5 по модельной сетке CAMS. Разрешение не позволяет достоверно сравнивать соседние районы.",
  },
  accidents: {
    name: "ДТП в городской рамке",
    attribution: "Комитет по правовой статистике · ArcGIS DTP",
    note: "Записи за 2026 год в рамке 71.2–71.65°E, 51.0–51.3°N. Рамка не равна административной границе; число не является официальным итогом по Астане.",
  },
  population: {
    name: "Население Астаны",
    attribution: "Бюро национальной статистики · таблица 6584",
    note: "Последний период в опубликованном ряду, категория «Всего / Всего / Все группы». Не счётчик населения в реальном времени.",
  },
  boundaries: {
    name: "Районы в геопортале",
    attribution: "map.gov.kz · geonode:border_districts",
    note: "Список уникальных KATO: части одного района объединены. Карта показывает 6 реальных районов, включая Сарайшык. Сценарные показатели рассчитаны для 5 районов исходной модели.",
  },
};
export function parsePopulation(raw: unknown) {
  const rows = z
    .array(
      z.object({
        termNames: z.array(z.string()),
        periods: z.array(
          z.object({
            date: z.string(),
            value: z.union([z.string(), z.number()]),
            name: z.string(),
          }),
        ),
      }),
    )
    .parse(raw);
  const row = rows.find(
    (r) =>
      /^Г\.?\s*(АСТАНА|НУР-СУЛТАН)$/i.test(r.termNames[0]) &&
      r.termNames.slice(1).join("|") === "Всего|Всего|Все группы",
  );
  if (!row) throw Error("Series missing");
  const periods = row.periods
    .map((p) => ({
      ...p,
      iso: p.date.split(".").reverse().join("-"),
      number: Number(String(p.value).replace(/\s/g, "").replace(",", ".")),
    }))
    .filter((p) => Number.isFinite(p.number) && p.number > 0)
    .sort((a, b) => b.iso.localeCompare(a.iso));
  if (!periods.length) throw Error("Empty series");
  return {
    data: { total: periods[0].number, period: periods[0].name },
    observedAt: periods[0].iso,
  };
}
export function parseBoundaries(raw: unknown) {
  const j = z
    .object({
      features: z.array(
        z.object({
          properties: z.object({ kato: z.string(), name_ru: z.string() }),
        }),
      ),
    })
    .parse(raw);
  if (!j.features.length) throw Error("Empty district list");
  return {
    data: {
      districts: [
        ...new Map(
          j.features.map((f) => [
            f.properties.kato,
            { kato: f.properties.kato, name: f.properties.name_ru },
          ]),
        ).values(),
      ],
      parts: j.features.length,
    },
    observedAt: null,
  };
}
function parse(
  id: keyof CityData,
  j: unknown,
): { data: unknown; observedAt: string | null } {
  if (id === "weather") {
    const { current: c } = weatherSchema.parse(j);
    return {
      data: {
        temperature: c.temperature_2m,
        wind: c.wind_speed_10m,
        code: c.weather_code,
      },
      observedAt: c.time + "+05:00",
    };
  }
  if (id === "air") {
    const { current: c } = airSchema.parse(j);
    return {
      data: { aqi: c.european_aqi, pm25: c.pm2_5, pm10: c.pm10 },
      observedAt: c.time + "+05:00",
    };
  }
  if (id === "accidents") {
    const j2 = z.object({ count: z.number().int().nonnegative() }).parse(j);
    return {
      data: { count: j2.count, year: 2026, bounds: [71.2, 51.0, 71.65, 51.3] },
      observedAt: null,
    };
  }
  return id === "population" ? parsePopulation(j) : parseBoundaries(j);
}
export async function getSource(
  id: keyof CityData,
  fetcher: typeof fetch = fetch,
  store: Store = memoryStore(),
): Promise<SourceRecord> {
  const key = "source:" + id;
  const previous = await store.get<SourceRecord>(key);
  const ttl = id === "weather" || id === "air" ? 15 * 60_000 : 24 * 60 * 60_000;
  if (
    previous?.data &&
    previous.fetchedAt &&
    Date.now() - Date.parse(previous.fetchedAt) < ttl
  )
    return { ...previous, status: "cached" };
  try {
    const res = await fetcher(sourceUrls[id], {
      headers: ua,
      signal: AbortSignal.timeout(id === "population" ? 20_000 : 12_000),
    });
    if (!res.ok) throw Error("Upstream unavailable");
    if (res.status === 206) {
      const m = /bytes (\d+)-(\d+)\/(\d+)/.exec(
        res.headers.get("content-range") ?? "",
      );
      if (!m || Number(m[1]) !== 0 || Number(m[2]) + 1 < Number(m[3]))
        throw Error("Partial response");
    }
    const parsed = parse(id, await res.json());
    const record: SourceRecord = {
      id,
      ...metadata[id],
      url: sourceUrls[id],
      status: "live",
      fetchedAt: new Date().toISOString(),
      ...parsed,
    };
    await store.put(key, record, 7 * 86400);
    return record;
  } catch {
    return previous?.data
      ? {
          ...previous,
          status: "cached",
          error: "Источник недоступен; показан сохранённый снимок.",
        }
      : {
          id,
          ...metadata[id],
          url: sourceUrls[id],
          status: "unavailable",
          data: null,
          fetchedAt: null,
          observedAt: null,
          error: "Источник не ответил или вернул неполные данные.",
        };
  }
}
export async function getCityData(
  store: Store = memoryStore(),
): Promise<CityData> {
  const keys = Object.keys(sourceUrls) as (keyof CityData)[];
  const results = await Promise.all(
    keys.map((id) => getSource(id, fetch, store)),
  );
  return Object.fromEntries(
    keys.map((id, i) => [id, results[i]]),
  ) as unknown as CityData;
}
