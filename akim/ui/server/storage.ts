export interface Store {
  get<T>(key: string): Promise<T | null>;
  put(key: string, value: unknown, ttlSeconds: number): Promise<void>;
}
export type Cached = <T>(
  kind: string,
  input: unknown,
  run: () => Promise<T>,
) => Promise<{ value: T; hit: boolean }>;
export function memoryStore(): Store {
  const values = new Map<string, { value: unknown; expires: number }>();
  return {
    async get<T>(key: string) {
      const v = values.get(key);
      return v && v.expires > Date.now() ? (v.value as T) : null;
    },
    async put(key, value, ttl) {
      values.set(key, { value, expires: Date.now() + ttl * 1000 });
    },
  };
}
export async function digest(value: string) {
  return Array.from(
    new Uint8Array(
      await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)),
    ),
  )
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
export function createCache(store: Store): Cached {
  return async <T>(kind: string, input: unknown, run: () => Promise<T>) => {
    const key =
      "llm:" + (await digest(JSON.stringify({ version: 4, kind, input })));
    const hit = await store.get<T>(key);
    if (hit !== null) return { value: hit, hit: true };
    const value = await run();
    await store.put(key, value, 86400);
    return { value, hit: false };
  };
}
