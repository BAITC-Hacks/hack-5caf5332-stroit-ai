import type { Page } from "@playwright/test";
import { existsSync, lstatSync, mkdirSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { playwright, requireCaptureTool } from "./playwright-runtime";

const { test } = playwright;
const sharp = requireCaptureTool<typeof import("sharp")>("sharp");

// Generic capture spec — the per-task interaction lives in the module
// CAPTURE_STEPS points at, so this file never needs editing per feature.
export type CaptureSteps = (page: Page, screenshot: (name: string) => Promise<void>) => Promise<void>;

const MEDIA_DIRNAME = "media";
const LATEST_RUN_POINTER = ".latest-run";
const STALE_EVIDENCE_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

// Override the default longest-side screenshot cap with CAPTURE_MAX_PX.
const rawMaxPx = Number(process.env.CAPTURE_MAX_PX);
const MAX_CAPTURE_PX = Number.isFinite(rawMaxPx) && rawMaxPx > 0 ? rawMaxPx : 2000;

// Downsample screenshot color to bound evidence size: palette (indexed-color) PNGs are lossily
// quantized, typically several times smaller than the lossless full-color encoding while staying
// readable for UI evidence. Override the default quality (1–100) with CAPTURE_PNG_QUALITY.
const rawPngQuality = Number(process.env.CAPTURE_PNG_QUALITY);
const PNG_QUALITY = Number.isFinite(rawPngQuality) && rawPngQuality > 0 && rawPngQuality <= 100 ? rawPngQuality : 80;

// Next's dev server serves build/runtime failures as a 200 page with a full-screen overlay,
// so a naive capture screenshots the red error box and "passes" — posting evidence of a broken
// page. Match the overlay's heading text (pierces the <nextjs-portal> open shadow root); the
// bottom-left dev indicator is a separate toast without these headings, so this won't false-positive.
const ERROR_OVERLAY_TEXT = /Build Error|Unhandled Runtime Error|Failed to compile|Module not found/i;

const assertNotSignInPage = (page: Page): void => {
  if (process.env.CAPTURE_ALLOW_SIGN_IN === "1") return;

  const currentUrl = new URL(page.url());
  if (/^\/(sign-in|login)(?:\/|$)/.test(currentUrl.pathname)) {
    throw new Error(
      `capture landed on a sign-in page (${currentUrl.origin}${currentUrl.pathname}) — provide an authenticated CAPTURE_STORAGE_STATE, then rerun`
    );
  }
};

const assertHealthyPage = async (page: Page): Promise<void> => {
  const overlay = page.getByText(ERROR_OVERLAY_TEXT).first();
  if (await overlay.isVisible().catch(() => false)) {
    const detail = ((await overlay.textContent().catch(() => "")) ?? "").trim().slice(0, 300);
    throw new Error(`Next dev error overlay detected — refusing to capture an error page as evidence: ${detail}`);
  }
};

// Sequential reruns share CAPTURE_OUT, so isolate each run under media/<runId>/.
// post-to-pr.ts reads the run id back from media/.latest-run.
const newRunId = (): string => new Date().toISOString().replace(/[:.]/g, "-");

// Nothing else prunes local evidence now that runs stay on disk (no git push): sweep files older
// than a week across the evidence dirs, dropping emptied run dirs only under media/ (see below).
const sweepStaleEvidence = (outRoot: string): void => {
  const cutoff = Date.now() - STALE_EVIDENCE_MAX_AGE_MS;
  const walk = (dir: string, pruneEmptied: boolean): void => {
    if (!existsSync(dir)) return;
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full, pruneEmptied);
        if (pruneEmptied && readdirSync(full).length === 0) rmSync(full, { recursive: true, force: true });
      } else if (entry.name !== LATEST_RUN_POINTER && lstatSync(full).mtimeMs < cutoff) {
        rmSync(full, { force: true });
      }
    }
  };
  walk(path.join(outRoot, MEDIA_DIRNAME), true);
  // Don't prune dirs under Playwright-owned test-results/ while the test owns them.
  walk(path.join(outRoot, "test-results"), false);
};

test("capture UI evidence", async ({ page }) => {
  const outRoot = process.env.CAPTURE_OUT;
  if (!outRoot) throw new Error("CAPTURE_OUT is required");
  const mediaRoot = path.join(outRoot, MEDIA_DIRNAME);
  sweepStaleEvidence(outRoot);
  mkdirSync(mediaRoot, { recursive: true });

  const runId = newRunId();
  const mediaDir = path.join(mediaRoot, runId);
  mkdirSync(mediaDir, { recursive: true });
  writeFileSync(path.join(mediaRoot, LATEST_RUN_POINTER), runId);

  let shotIndex = 0;
  const screenshot = async (name: string) => {
    shotIndex += 1;
    const file = `${String(shotIndex).padStart(2, "0")}-${name.replace(/[^\w-]+/g, "_")}.png`;
    // Full-page shots can be many thousands of px tall → multi-MB PNGs. Cap the longest side
    // (whole page kept, just downsampled) and recompress with palette quantization to bound
    // on-disk evidence size.
    const raw = await page.screenshot({ fullPage: true });
    const capped = await sharp(raw)
      .resize({ width: MAX_CAPTURE_PX, height: MAX_CAPTURE_PX, fit: "inside", withoutEnlargement: true })
      .png({ compressionLevel: 9, palette: true, quality: PNG_QUALITY })
      .toBuffer();
    writeFileSync(path.join(mediaDir, file), capped);
  };

  // domcontentloaded, not the default "load": a dev route holding an open stream
  // (SSE/long-poll) never fires "load", so the default goto runs to the test timeout.
  const response = await page.goto(process.env.CAPTURE_ROUTE ?? "/", { waitUntil: "domcontentloaded" });
  if (response && response.status() >= 400) {
    throw new Error(`capture route returned HTTP ${response.status()} — refusing to post evidence of an error page`);
  }
  // Dev-mode Next keeps trickling requests; degrade silently rather than fail the capture.
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
  assertNotSignInPage(page);
  await assertHealthyPage(page);

  // Plain-JS .mjs only: the runner's TS transform doesn't reach runtime dynamic imports.
  const stepsPath = process.env.CAPTURE_STEPS;
  if (stepsPath) {
    const { default: steps } = (await import(pathToFileURL(path.resolve(stepsPath)).href)) as { default: CaptureSteps };
    await steps(page, screenshot);
  }

  // A step may navigate or trigger a runtime error — re-check before the closing screenshot.
  assertNotSignInPage(page);
  await assertHealthyPage(page);
  await screenshot("final");
});
