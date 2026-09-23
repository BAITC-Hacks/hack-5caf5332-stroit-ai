import { z } from "zod";
import { zodTextFormat } from "openai/helpers/zod";
import { directions } from "../src/data";
import type { ThreadEvidence } from "../src/threads";
import type { ComplaintCollection } from "../src/complaints";
import { classifyComplaints } from "./jev";
import { PublicError, type Llm } from "./llm";
import { evidenceSchema, searchSources, verifiedEvidence } from "./threads";
import type { Store } from "./storage";
export const complaintRequest = z
  .object({
    includePress: z.boolean().default(true),
    keywords: z.string().trim().max(160).default(""),
    direction: z.enum(directions).optional(),
  })
  .strict();
const pressSchema = z.object({
  posts: z.array(
    z.object({
      sourceUrl: z.string(),
      summary: z.string(),
      mentionsThreads: z.boolean(),
    }),
  ),
});
export function verifiedPress(
  raw: unknown,
  sources: { url: string }[],
): ThreadEvidence[] {
  const parsed = pressSchema.parse(raw),
    allowed = new Set(sources.map((s) => s.url)),
    seen = new Set<string>();
  return parsed.posts
    .flatMap((p) => {
      let u: URL;
      try {
        u = new URL(p.sourceUrl);
      } catch {
        return [];
      }
      if (
        !p.mentionsThreads ||
        !allowed.has(p.sourceUrl) ||
        u.protocol !== "https:" ||
        u.username ||
        u.password ||
        ![
          "informburo.kz",
          "tengrinews.kz",
          "newtimes.kz",
          "kz.kursiv.media",
          "astana-web.kz",
        ].includes(u.hostname.replace(/^www\./, "")) ||
        seen.has(p.sourceUrl)
      )
        return [];
      seen.add(p.sourceUrl);
      return [
        {
          url: p.sourceUrl,
          title: `Threads через ${u.hostname}`,
          summary: p.summary.slice(0, 700),
          publishedAt: null,
          sourceKind: "press" as const,
          stance: "unclear" as const,
          scope: "unclear" as const,
        },
      ];
    })
    .slice(0, 8);
}
export const complaintSnapshot = "complaints:latest:v1";
const queriesByDirection = {
  Транспорт: [
    "Астана пробки автобус жалоба",
    "Astana traffic bus problem",
    "Астана Сейфуллина пробки",
  ],
  Экология: [
    "Астана мусор смог жалоба",
    "Астана ағаш қоқыс",
    "Astana pollution park",
  ],
  Соцсфера: [
    "Астана школа поликлиника очередь",
    "Астана балабақша мектеп",
    "Astana school clinic problem",
  ],
  Безопасность: [
    "Астана улица нет освещения переход",
    "Астана қауіпті жол",
    "Astana unsafe crossing",
  ],
  Сервисы: [
    "Астана нет воды отопления жалоба",
    "Астана су жылу жоқ",
    "Astana water heating outage",
  ],
};
export async function ingestComplaints(
  llm: Llm,
  jevKey: string | undefined,
  store: Store,
  request: z.infer<typeof complaintRequest>,
  signal?: AbortSignal,
): Promise<ComplaintCollection> {
  if (!jevKey) throw new PublicError("Jev не настроен на сервере.", 503);
  const queries = [
    ...(request.keywords ? [`Астана ${request.keywords} Threads`] : []),
    ...(request.direction
      ? queriesByDirection[request.direction]
      : directions.map((d) => queriesByDirection[d][0])),
    ...(!request.keywords ? ["Astana city problems complaints"] : []),
  ].slice(0, 6);
  const result = await llm.cache(
    "complaint-map",
    {
      version: 7,
      includePress: request.includePress,
      queries,
      model: llm.model,
      jev: "jev-1.13.0",
      bucket: Math.floor(Date.now() / 1800000),
    },
    async () => {
      const response = await llm.search(
        {
          queries,
          location: "Астана, Казахстан",
          question:
            "Найди публичные публикации об актуальных городских проблемах Астаны. В пересказе сохрани только явно названные в источнике город, улицу и район. Не добавляй место из поискового запроса.",
        },
        zodTextFormat(evidenceSchema, "complaint_evidence"),
        signal,
      );
      const sources = searchSources(response);
      if (!sources.queries.length)
        throw new PublicError("Поиск Threads не выполнился.");
      let posts;
      try {
        posts = verifiedEvidence(
          JSON.parse(response.output_text),
          sources.sources,
        );
      } catch {
        throw new PublicError("Поиск не вернул проверяемые публикации.");
      }
      if (request.includePress && posts.length < 3) {
        const pressQueries = queries.map((q) => q + " Threads");
        const secondary = await llm.search(
          {
            queries: pressQueries,
            location: "Астана",
            question: "Жалобы жителей Астаны из Threads, процитированные в СМИ",
          },
          zodTextFormat(pressSchema, "threads_in_press"),
          signal,
          { press: true },
        );
        const pressSources = searchSources(secondary);
        if (!pressSources.queries.length)
          throw new PublicError("Поиск вторичных источников не выполнился.");
        sources.queries.push(...pressSources.queries);
        try {
          posts.push(
            ...verifiedPress(
              JSON.parse(secondary.output_text),
              pressSources.sources,
            ),
          );
        } catch {
          throw new PublicError("Не удалось проверить вторичные источники.");
        }
      }
      const classified: Awaited<ReturnType<typeof classifyComplaints>> = {
        model: "jev-1.13.0",
        posts: [],
      };
      // One post per state avoids unrelated evidence influencing a decision.
      // Bound concurrency to four requests, preserving the source order.
      for (let i = 0; i < posts.length; i += 4) {
        const batches = await Promise.all(
          posts
            .slice(i, i + 4)
            .map((post) => classifyComplaints(jevKey, [post], signal)),
        );
        for (const batch of batches) {
          classified.model = batch.model;
          classified.posts.push(...batch.posts);
        }
      }
      return {
        posts: classified.posts,
        queries,
        searchedQueries: sources.queries,
        fetchedAt: new Date().toISOString(),
        model: classified.model,
        coverage:
          "Индексируемые публичные Threads; при включённой опции — сообщения СМИ с жалобами из Threads, отмеченные отдельно. Jev классифицирует пересказы найденных источников; полный текст и дата публикации не проверены. Пины обозначают улицу или район, не точный адрес. Карта не показывает распространённость проблемы среди всех жителей.",
      };
    },
  );
  const collection = { ...result.value, cached: result.hit };
  await store.put(complaintSnapshot, collection, 86400);
  return collection;
}
