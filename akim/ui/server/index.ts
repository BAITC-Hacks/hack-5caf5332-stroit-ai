import {
  complaintRequest,
  complaintSnapshot,
  ingestComplaints,
} from "./complaints";
import { config } from "dotenv";
import { fileURLToPath } from "node:url";
import { randomBytes, timingSafeEqual } from "node:crypto";
import express from "express";
import { localStore } from "./local-store";
import { getCityData } from "./city-data";
import { createLlm, PublicError, publicMessage } from "./llm";
import { askRequest, akimRequest, explainRequest } from "./schemas";
import { askWithEvidence } from "./ask";
import { ingestThreads } from "./threads";
import { threadsRequest } from "./schemas";
import { explainPlan } from "./explain";
import { runAkim } from "./akim";
config({
  path: fileURLToPath(new URL("../.env", import.meta.url)),
  quiet: true,
});
const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: "16kb" }));
const token = randomBytes(32).toString("hex");
const store = localStore();
const llm = createLlm({
  apiKey: process.env.OPENAI_API_KEY,
  model: process.env.OPENAI_MODEL,
  store,
});
let active = 0;
const hits: number[] = [];
app.get("/api/health", (_req, res) =>
  res.set("Cache-Control", "no-store").json({
    configured: !!process.env.OPENAI_API_KEY,
    model: llm.model,
    jevConfigured: !!process.env.JEV_API_KEY,
    token,
  }),
);
app.get("/api/city", async (_req, res) => {
  try {
    res.json(await getCityData(store));
  } catch {
    res.status(503).json({ error: "Городские источники временно недоступны." });
  }
});
app.get("/api/complaints", async (_req, res) => {
  res
    .set("Cache-Control", "no-store")
    .json({ collection: await store.get(complaintSnapshot) });
});
app.use("/api", (req, res, next) => {
  if (req.method !== "POST") {
    next();
    return;
  }
  const supplied = req.get("X-Sim-Token") || "";
  const origin = req.get("origin");
  const allowed = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:5178",
    "http://localhost:5178",
    `http://127.0.0.1:${process.env.API_PORT || 8791}`,
    `http://localhost:${process.env.API_PORT || 8791}`,
  ];
  if (origin && !allowed.includes(origin)) {
    res.status(403).json({ error: "Недопустимый источник запроса." });
    return;
  }
  if (
    supplied.length !== token.length ||
    !timingSafeEqual(Buffer.from(supplied), Buffer.from(token))
  ) {
    res.status(403).json({ error: "Обновите страницу для нового сеанса." });
    return;
  }
  const now = Date.now();
  while (hits.length && hits[0] < now - 15 * 60_000) hits.shift();
  if (active >= 2 || hits.length >= 30) {
    res
      .status(429)
      .json({ error: "Слишком много AI-запросов. Подождите и повторите." });
    return;
  }
  hits.push(now);
  active++;
  res.once("close", () => {
    active--;
  });
  next();
});
app.post("/api/ask", async (req, res) => {
  const parsed = askRequest.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({
      error: "Укажите вопрос до 1000 символов и допустимые идентификаторы мер.",
    });
    return;
  }
  const abort = new AbortController();
  res.once("close", () => {
    if (!res.writableEnded) abort.abort();
  });
  const signal = AbortSignal.any([abort.signal, AbortSignal.timeout(180_000)]);
  try {
    const context = await getCityData(store);
    const answer = await askWithEvidence(
      llm,
      parsed.data.question,
      parsed.data.plan,
      context,
      parsed.data.useThreads,
      signal,
    );
    res.json(answer);
  } catch (error) {
    if (!res.destroyed)
      res
        .status(error instanceof PublicError ? error.status : 502)
        .json({ error: publicMessage(error) });
  }
});
app.post("/api/complaints/ingest", async (req, res) => {
  const parsed = complaintRequest.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: "Некорректный поиск жалоб." });
    return;
  }
  const abort = new AbortController();
  res.once("close", () => {
    if (!res.writableEnded) abort.abort();
  });
  try {
    const collection = await ingestComplaints(
      llm,
      process.env.JEV_API_KEY,
      store,
      parsed.data,
      AbortSignal.any([abort.signal, AbortSignal.timeout(180000)]),
    );
    if (!res.destroyed) res.json({ collection });
  } catch (e) {
    if (!res.destroyed)
      res
        .status(e instanceof PublicError ? e.status : 502)
        .json({ error: publicMessage(e) });
  }
});
app.post("/api/threads/ingest", async (req, res) => {
  const parsed = threadsRequest.safeParse(req.body);
  if (!parsed.success) {
    res
      .status(400)
      .json({ error: "Укажите решение или вопрос до 1000 символов." });
    return;
  }
  const abort = new AbortController();
  res.once("close", () => {
    if (!res.writableEnded) abort.abort();
  });
  try {
    res.json({
      evidence: await ingestThreads(
        llm,
        parsed.data.question,
        parsed.data.plan,
        AbortSignal.any([abort.signal, AbortSignal.timeout(150000)]),
      ),
    });
  } catch (e) {
    if (!res.destroyed)
      res
        .status(e instanceof PublicError ? e.status : 502)
        .json({ error: publicMessage(e) });
  }
});
app.post("/api/explain", async (req, res) => {
  const parsed = explainRequest.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: "Некорректный план для разбора." });
    return;
  }
  const abort = new AbortController();
  res.once("close", () => {
    if (!res.writableEnded) abort.abort();
  });
  const signal = AbortSignal.any([abort.signal, AbortSignal.timeout(60_000)]);
  try {
    const brief = await explainPlan(
      llm,
      parsed.data.plan,
      parsed.data.priorities,
      signal,
    );
    res.json({ brief });
  } catch (error) {
    if (!res.destroyed)
      res
        .status(error instanceof PublicError ? error.status : 502)
        .json({ error: publicMessage(error) });
  }
});
app.post("/api/akim", async (req, res) => {
  const parsed = akimRequest.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: "Некорректный запрос к акиму." });
    return;
  }
  const abort = new AbortController();
  res.once("close", () => {
    if (!res.writableEnded) abort.abort();
  });
  const signal = AbortSignal.any([abort.signal, AbortSignal.timeout(180_000)]);
  res.set({
    "Content-Type": "application/x-ndjson",
    "Cache-Control": "no-store",
    "X-Accel-Buffering": "no",
  });
  res.flushHeaders();
  const send = (event: unknown) => {
    if (!res.destroyed) res.write(JSON.stringify(event) + "\n");
  };
  try {
    const local = parsed.data.mode === "goal" && !process.env.OPENAI_API_KEY;
    send({
      type: "activity",
      event: {
        label: local ? "Локальная цель" : "Загрузка данных города",
        detail: local ? "Поиск без OpenAI и внешних источников." : "Чтение доступных источников и дат наблюдения.",
        at: new Date().toISOString(),
      },
    });
    const context = local ? null : await getCityData(store);
    const result = await runAkim(
      local ? null : llm,
      parsed.data.mode,
      parsed.data.plan,
      context,
      (event) => send({ type: "activity", event }),
      signal,
      parsed.data,
    );
    send({ type: "result", result });
  } catch (error) {
    send({ type: "error", error: publicMessage(error) });
  } finally {
    res.end();
  }
});
app.use("/api", (_req, res) => {
  res.status(404).json({ error: "Неизвестный API endpoint." });
});
const dist = fileURLToPath(new URL("../dist/", import.meta.url));
app.use(express.static(dist, { dotfiles: "deny" }));
app.get("/", (_req, res) => res.sendFile(dist + "index.html"));
app.use(
  (
    error: unknown,
    _req: express.Request,
    res: express.Response,
    _next: express.NextFunction,
  ) => {
    void error;
    res.status(400).json({ error: "Некорректный запрос." });
  },
);
const port = Number(process.env.API_PORT || 8791),
  host = process.env.API_HOST || "127.0.0.1";
const server = app.listen(port, host, () =>
  console.log(
    `Sim Astana API http://${host}:${port} · OpenAI ${process.env.OPENAI_API_KEY ? "configured" : "not configured"} · ${llm.model}`,
  ),
);

server.on("error", () => {
  console.error(
    "API could not bind its port. Check API_PORT and Vite proxy configuration.",
  );
  process.exitCode = 1;
});
