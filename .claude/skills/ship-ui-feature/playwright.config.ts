import { existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { playwright } from "./scripts/playwright-runtime";

const { defineConfig } = playwright;

const outRoot = process.env.CAPTURE_OUT;
if (!outRoot) {
  throw new Error("CAPTURE_OUT must point at the per-worktree evidence dir (e.g. /tmp/claude/ui-capture/<worktree-basename>)");
}

// Optional logged-in session for auth-gated routes. Durable home-dir path, NOT /tmp (which gets
// reaped, forcing a re-login). Override with CAPTURE_STORAGE_STATE.
const storageState = process.env.CAPTURE_STORAGE_STATE ?? path.join(os.homedir(), ".claude", "stroit-ai-auth", "storageState.json");

// Downsample the recording from the 1440x900 viewport to bound evidence size.
// Override the default 960x600 with CAPTURE_VIDEO_WIDTH / CAPTURE_VIDEO_HEIGHT.
const rawVideoWidth = Number(process.env.CAPTURE_VIDEO_WIDTH);
const rawVideoHeight = Number(process.env.CAPTURE_VIDEO_HEIGHT);
const videoSize = {
  width: Number.isFinite(rawVideoWidth) && rawVideoWidth > 0 ? rawVideoWidth : 960,
  height: Number.isFinite(rawVideoHeight) && rawVideoHeight > 0 ? rawVideoHeight : 600
};

export default defineConfig({
  testDir: path.join(__dirname, "scripts"),
  testMatch: "capture.ts",
  outputDir: path.join(outRoot, "test-results"),
  timeout: 180_000,
  use: {
    baseURL: process.env.CAPTURE_BASE_URL ?? "http://localhost:3000",
    ...(existsSync(storageState) ? { storageState } : {}),
    video: { mode: "on", size: videoSize },
    viewport: { width: 1440, height: 900 }
  }
});
