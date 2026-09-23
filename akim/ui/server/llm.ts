import OpenAI from "openai";
import { zodTextFormat } from "openai/helpers/zod";
import { z } from "zod";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import type {
  ResponseInput,
  Tool,
  Response,
} from "openai/resources/responses/responses";
export class PublicError extends Error {
  constructor(
    message: string,
    public status = 502,
  ) {
    super(message);
  }
}
export interface Llm {
  model: string;
  structured<T>(
    name: string,
    schema: z.ZodType<T>,
    system: string,
    payload: unknown,
    signal?: AbortSignal,
  ): Promise<T>;
  tools(
    input: ResponseInput,
    tools: Tool[],
    signal?: AbortSignal,
  ): Promise<Response>;
}
export function createLlm(): Llm {
  const model = process.env.OPENAI_MODEL || "gpt-6-luna";
  const client = new OpenAI({
    apiKey: process.env.OPENAI_API_KEY || "not-configured",
    maxRetries: 0,
    timeout: 45_000,
  });
  return {
    model,
    async structured<T>(
      name: string,
      schema: z.ZodType<T>,
      system: string,
      payload: unknown,
      signal?: AbortSignal,
    ) {
      if (!process.env.OPENAI_API_KEY)
        throw new PublicError(
          "OpenAI не настроен. Добавьте ключ на сервере или выберите локальную модель.",
          503,
        );
      const response = await client.responses.parse(
        {
          model,
          reasoning: { effort: "low" },
          store: false,
          input: [
            { role: "system", content: system },
            { role: "user", content: JSON.stringify(payload) },
          ],
          text: { format: zodTextFormat(schema, name) },
          max_output_tokens: 5500,
        },
        { signal },
      );
      if (!response.output_parsed)
        throw new PublicError(
          "Модель не вернула допустимый структурированный ответ. Попробуйте другой вопрос.",
        );
      return response.output_parsed;
    },
    async tools(input, tools, signal) {
      if (!process.env.OPENAI_API_KEY)
        throw new PublicError("Ключ OpenAI не настроен.", 503);
      return client.responses.create(
        {
          model,
          reasoning: { effort: "low" },
          store: false,
          input,
          tools,
          parallel_tool_calls: false,
          max_output_tokens: 2200,
        },
        { signal },
      );
    },
  };
}
const cacheDir = fileURLToPath(new URL("../.cache/llm/", import.meta.url));
const tasks = new Map<string, Promise<unknown>>();
export async function cached<T>(
  kind: string,
  input: unknown,
  run: () => Promise<T>,
): Promise<{ value: T; hit: boolean }> {
  const hash = createHash("sha256")
    .update(JSON.stringify({ version: 2, kind, input }))
    .digest("hex");
  const path = cacheDir + hash + ".json";
  try {
    const item = JSON.parse(await readFile(path, "utf8")) as {
      value: T;
      time: number;
    };
    if (Date.now() - item.time < 24 * 60 * 60_000)
      return { value: item.value, hit: true };
  } catch {
    /* First request or expired cache. */
  }
  const inProgress = tasks.get(hash) as Promise<T> | undefined;
  if (inProgress) return { value: await inProgress, hit: true };
  const task = run();
  tasks.set(hash, task);
  try {
    const value = await task;
    await mkdir(cacheDir, { recursive: true });
    await writeFile(path, JSON.stringify({ value, time: Date.now() }));
    return { value, hit: false };
  } finally {
    tasks.delete(hash);
  }
}
export function publicMessage(error: unknown) {
  if (error instanceof PublicError) return error.message;
  if (error instanceof OpenAI.APIError) {
    if (error.status === 401)
      return "OpenAI отклонил ключ. Обновите OPENAI_API_KEY на сервере.";
    if (error.status === 429)
      return "OpenAI: лимит запросов или средств исчерпан. Повторите позже или выберите локальную модель.";
  }
  if (error instanceof Error && error.name === "AbortError")
    return "Запрос отменён.";
  return "Сервис AI временно недоступен. Попробуйте снова или явно выберите локальную модель.";
}
