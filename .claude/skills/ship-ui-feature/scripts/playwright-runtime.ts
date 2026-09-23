import { createRequire } from "node:module";
import path from "node:path";

const toolHome = process.env.PLAYWRIGHT_TOOL_HOME;

if (!toolHome) {
  throw new Error("PLAYWRIGHT_TOOL_HOME is required. Run capture tooling through ensure-playwright.sh.");
}

const requireTool = createRequire(path.join(toolHome, "package.json"));

export function requireCaptureTool<T>(id: string): T {
  return requireTool(id) as T;
}

export const playwright = requireCaptureTool<typeof import("@playwright/test")>("@playwright/test");
