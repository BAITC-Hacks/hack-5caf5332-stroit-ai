import type { ThreadsEvidence } from "./threads";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { Choice } from "./data";
import type { Poll } from "./residents";
import type { ActivityEvent, CityData, ServiceHealth } from "./city-data";
import type { AkimResult } from "../server/akim";
interface Services {
  health: ServiceHealth | null;
  mode: "live" | "local";
  setMode: (mode: "live" | "local") => void;
  city: CityData | null;
  cityError: string;
  refresh: () => void;
}
const Context = createContext<Services | null>(null);
export function ServicesProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<ServiceHealth | null>(null),
    [mode, setMode] = useState<"live" | "local">("local"),
    [city, setCity] = useState<CityData | null>(null),
    [cityError, setCityError] = useState("");
  const refresh = () => {
    setCityError("");
    fetch("/api/city")
      .then((r) => {
        if (!r.ok) throw Error();
        return r.json();
      })
      .then(setCity)
      .catch(() =>
        setCityError(
          "Не удалось загрузить источники. Проверьте запуск сервера.",
        ),
      );
  };
  useEffect(() => {
    let cancelled = false;
    fetch("/api/health")
      .then((r) => r.json())
      .then((h: ServiceHealth) => {
        if (!cancelled) {
          setHealth(h);
          if (h.configured) setMode("live");
        }
      })
      .catch(() => {
        if (!cancelled) setHealth(null);
      });
    refresh();
    return () => {
      cancelled = true;
    };
  }, []);
  return (
    <Context.Provider
      value={{ health, mode, setMode, city, cityError, refresh }}
    >
      {children}
    </Context.Provider>
  );
}
export function useServices() {
  const value = useContext(Context);
  if (!value) throw Error("Missing ServicesProvider");
  return value;
}
export function AiModeSwitch() {
  const { health, mode, setMode } = useServices();
  return (
    <div className="ai-mode-switch">
      <span>
        <i className={mode === "live" ? "live-dot" : ""} />
        {mode === "live" ? `OpenAI · ${health?.model}` : "Локальная демомодель"}
      </span>
      <button
        onClick={() => setMode(mode === "live" ? "local" : "live")}
        disabled={mode === "local" && !health?.configured}
      >
        {mode === "live" ? "Локально" : "Включить OpenAI"}
      </button>
    </div>
  );
}
async function post(
  path: string,
  payload: unknown,
  token: string,
  signal: AbortSignal,
) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Sim-Token": token },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ error: "Сервер не ответил." }));
    throw Error(error.error || "Ошибка сервера.");
  }
  return response;
}
export async function askApi(
  question: string,
  plan: Choice[],
  token: string,
  signal: AbortSignal,
  useThreads = false,
): Promise<{ poll: Poll | null; evidence?: ThreadsEvidence; notice?: string }> {
  const response = await post(
    "/api/ask",
    { question, plan, useThreads },
    token,
    signal,
  );
  return response.json();
}
export async function akimApi(
  mode: "advisor" | "autopilot",
  plan: Choice[],
  token: string,
  onEvent: (event: ActivityEvent) => void,
  signal: AbortSignal,
): Promise<AkimResult> {
  const response = await post("/api/akim", { mode, plan }, token, signal);
  if (!response.body) throw Error("Пустой ответ сервера.");
  const reader = response.body.getReader(),
    decoder = new TextDecoder();
  let buffer = "",
    result: AkimResult | undefined;
  const consume = (line: string) => {
    if (!line.trim()) return;
    const item = JSON.parse(line);
    if (item.type === "activity") onEvent(item.event);
    else if (item.type === "result") result = item.result;
    else if (item.type === "error") throw Error(item.error);
  };
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop()!;
      lines.forEach(consume);
    }
    buffer += decoder.decode();
    if (buffer) consume(buffer);
  } finally {
    reader.releaseLock();
  }
  if (!result) throw Error("AI не завершил ответ. Попробуйте снова.");
  return result;
}

export async function ingestApi(
  question: string,
  plan: Choice[],
  token: string,
  signal: AbortSignal,
): Promise<ThreadsEvidence> {
  return (
    await (
      await post("/api/threads/ingest", { question, plan }, token, signal)
    ).json()
  ).evidence;
}
