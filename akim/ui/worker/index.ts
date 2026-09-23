import { createLlm, PublicError, publicMessage } from "../server/llm";
import { getCityData } from "../server/city-data";
import { askWithEvidence } from "../server/ask";
import { runAkim } from "../server/akim";
import { ingestThreads } from "../server/threads";
import {
  askRequest,
  akimRequest,
  explainRequest,
  threadsRequest,
} from "../server/schemas";
import { explainPlan } from "../server/explain";
import type { Store } from "../server/storage";
const json = (value: unknown, status = 200) =>
  Response.json(value, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
async function token(secret: string, identity: string, bucket: number) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return Array.from(
    new Uint8Array(
      await crypto.subtle.sign(
        "HMAC",
        key,
        new TextEncoder().encode(identity + ":" + bucket),
      ),
    ),
  )
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
async function authorized(request: Request, env: Env, identity: string) {
  const value = request.headers.get("X-Sim-Token") ?? "";
  const bucket = Math.floor(Date.now() / 3600000);
  if (!/^[a-f0-9]{64}$/.test(value)) return false;
  for (const t of [bucket, bucket - 1]) {
    const expected = await token(env.SESSION_SECRET, identity, t);
    let diff = 0;
    for (let i = 0; i < 64; i++)
      diff |= value.charCodeAt(i) ^ expected.charCodeAt(i);
    if (diff === 0) return true;
  }
  return false;
}
async function readBody(request: Request) {
  if (!request.headers.get("Content-Type")?.includes("application/json"))
    throw new PublicError("Ожидается JSON.", 415);
  const reader = request.body?.getReader();
  if (!reader) throw new PublicError("Пустой запрос.", 400);
  const decoder = new TextDecoder();
  let body = "",
    size = 0;
  for (;;) {
    const part = await reader.read();
    if (part.done) break;
    size += part.value.byteLength;
    if (size > 16384) {
      await reader.cancel();
      throw new PublicError("Запрос слишком большой.", 413);
    }
    body += decoder.decode(part.value, { stream: true });
  }
  try {
    return JSON.parse(body + decoder.decode());
  } catch {
    throw new PublicError("Некорректный JSON.", 400);
  }
}
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(request);
    const store: Store = {
      get: <T>(key: string) => env.CACHE.get<T>(key, "json"),
      async put(key, value, ttl) {
        await env.CACHE.put(key, JSON.stringify(value), {
          expirationTtl: Math.max(60, ttl),
        });
      },
    };
    const identity = request.headers.get("CF-Connecting-IP") ?? "local";
    try {
      if (url.pathname === "/api/health" && request.method === "GET")
        return json({
          configured: !!env.OPENAI_API_KEY,
          model: env.OPENAI_MODEL,
          token: await token(
            env.SESSION_SECRET,
            identity,
            Math.floor(Date.now() / 3600000),
          ),
          threads: true,
        });
      if (url.pathname === "/api/city" && request.method === "GET")
        return json(await getCityData(store));
      if (
        ![
          "/api/ask",
          "/api/akim",
          "/api/explain",
          "/api/threads/ingest",
        ].includes(url.pathname)
      )
        return json({ error: "Неизвестный API endpoint." }, 404);
      if (request.method !== "POST")
        return json({ error: "Ожидается POST." }, 405);
      const origin = request.headers.get("Origin");
      if (origin && origin !== url.origin)
        return json({ error: "Недопустимый источник запроса." }, 403);
      if (!(await authorized(request, env, identity)))
        return json({ error: "Сеанс истёк. Обновите страницу." }, 403);
      if (
        !(await env.AI_LIMIT.limit({ key: identity })).success ||
        !(await env.SERVICE_LIMIT.limit({ key: "ai" })).success
      )
        return json(
          { error: "Лимит AI-запросов. Подождите минуту и повторите." },
          429,
        );
      const body = await readBody(request),
        llm = createLlm({
          apiKey: env.OPENAI_API_KEY,
          model: env.OPENAI_MODEL,
          store,
        });
      const signal = AbortSignal.any([
        request.signal,
        AbortSignal.timeout(180000),
      ]);
      if (url.pathname === "/api/threads/ingest") {
        const parsed = threadsRequest.safeParse(body);
        if (!parsed.success)
          return json(
            { error: "Укажите решение или вопрос до 1000 символов." },
            400,
          );
        return json({
          evidence: await ingestThreads(
            llm,
            parsed.data.question,
            parsed.data.plan,
            signal,
          ),
        });
      }
      if (url.pathname === "/api/explain") {
        const parsed = explainRequest.safeParse(body);
        if (!parsed.success)
          return json({ error: "Некорректный план для разбора." }, 400);
        return json({
          brief: await explainPlan(
            llm,
            parsed.data.plan,
            parsed.data.priorities,
            signal,
          ),
        });
      }
      if (url.pathname === "/api/ask") {
        const parsed = askRequest.safeParse(body);
        if (!parsed.success)
          return json({ error: "Некорректный вопрос или план." }, 400);
        return json(
          await askWithEvidence(
            llm,
            parsed.data.question,
            parsed.data.plan,
            await getCityData(store),
            parsed.data.useThreads,
            signal,
          ),
        );
      }
      const parsed = akimRequest.safeParse(body);
      if (!parsed.success) return json({ error: "Некорректный план." }, 400);
      const stream = new TransformStream(),
        writer = stream.writable.getWriter(),
        encoder = new TextEncoder();
      let queue = Promise.resolve();
      const send = (event: unknown) => {
        queue = queue.then(() =>
          writer.write(encoder.encode(JSON.stringify(event) + "\n")),
        );
      };
      const task = (async () => {
        try {
          send({
            type: "activity",
            event: {
              label: "Загрузка данных города",
              detail: "Читаем датированные источники.",
              at: new Date().toISOString(),
            },
          });
          const result = await runAkim(
            llm,
            parsed.data.mode,
            parsed.data.plan,
            await getCityData(store),
            (event) => send({ type: "activity", event }),
            signal,
          );
          send({ type: "result", result });
        } catch (e) {
          send({ type: "error", error: publicMessage(e) });
        } finally {
          try {
            await queue;
            await writer.close();
          } catch {
            /* Client disconnected. */
          }
        }
      })();
      ctx.waitUntil(task);
      return new Response(stream.readable, {
        headers: {
          "Content-Type": "application/x-ndjson",
          "Cache-Control": "no-store",
        },
      });
    } catch (e) {
      return json(
        { error: publicMessage(e) },
        e instanceof PublicError ? e.status : 502,
      );
    }
  },
} satisfies ExportedHandler<Env>;
