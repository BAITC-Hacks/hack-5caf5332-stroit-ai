import { mkdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { digest, type Store } from "./storage";
export function localStore(): Store {
  const dir = fileURLToPath(new URL("../.cache/store/", import.meta.url));
  return {
    async get<T>(key: string) {
      try {
        const j = JSON.parse(
          await readFile(dir + (await digest(key)) + ".json", "utf8"),
        );
        return j.expires > Date.now() ? (j.value as T) : null;
      } catch {
        return null;
      }
    },
    async put(key, value, ttl) {
      await mkdir(dir, { recursive: true });
      await writeFile(
        dir + (await digest(key)) + ".json",
        JSON.stringify({ value, expires: Date.now() + ttl * 1000 }),
      );
    },
  };
}
