// Regenerates README screenshots and the walkthrough GIF in docs/.
// Needs: Vite dev UI on 5178 (`npm run dev:ui -- --port 5178`), API on 8791, ffmpeg.
// Run: npx tsx scripts/readme-media.ts
import { chromium } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const base = process.env.BASE_URL ?? "http://127.0.0.1:5178";
const out = new URL("../docs/", import.meta.url).pathname;
const videoDir = mkdtempSync(join(tmpdir(), "akim-video-"));
const size = { width: 1440, height: 900 };

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: size, recordVideo: { dir: videoDir, size }, locale: "ru-RU" });
const page = await ctx.newPage();
const pause = (ms = 900) => page.waitForTimeout(ms);
const shot = (name: string) => page.screenshot({ path: join(out, name), scale: "css" });
const build = (name: string) =>
  page.locator(".decision-list li", { hasText: name }).getByRole("button", { name: /Построить/ }).click();

await page.goto(base + "/");
await page.getByRole("heading", { name: "Пять решений для города" }).waitFor();
await pause(2500);
await shot("intro.png");
await page.getByRole("button", { name: /Стать акимом/ }).click();
await page.getByRole("heading", { name: /Город сейчас/ }).waitFor();
await pause(2000);
await page.getByRole("button", { name: "Соцсфера", exact: true }).click();
await pause();
await page.getByRole("button", { name: /Начать: район Нура/ }).click();
await pause(2500);
await shot("map.png");
await page.getByRole("button", { name: "Район Нура", exact: true }).click();
await pause();
await page.getByRole("button", { name: /Все 14 мер/ }).click();
await pause();
for (const name of ["Школа и детсад", "Поликлиника", "Освещение и камеры", "Платформа обращений"]) {
  await build(name);
  await pause(1200);
}
await page.locator(".jump").getByRole("button", { name: "Сарыарка" }).click();
await pause();
await page.getByRole("button", { name: /Все 14 мер/ }).click();
await pause();
await build("Чистое топливо");
await page.getByRole("heading", { name: "Все пять решений приняты" }).waitFor();
await pause(2000);
await shot("plan.png");
await page.getByRole("button", { name: /Подвести итог/ }).click();
await page.getByRole("heading", { name: "Итог вашего плана" }).waitFor();
await pause(1500);
// Live AI akim: wait for the brief, but never longer than a minute.
await page.locator(".ai-brief[aria-busy='false']").waitFor({ timeout: 60000 }).catch(() => {});
await pause(2500);
await shot("report.png");
await page.getByRole("button", { name: "Спросить жителей", exact: true }).click();
await page.getByRole("dialog", { name: "Спросить город" }).waitFor();
await pause(2000);
await shot("residents.png");
await page.getByRole("button", { name: "Закрыть опрос" }).click();
await pause();
await page.getByRole("button", { name: "Что если", exact: true }).click();
await pause();
await page.getByRole("button", { name: "Отключение ТЭЦ", exact: true }).click();
await pause(2000);
await shot("stress.png");
await pause(1500);

await ctx.close();
await browser.close();
const webm = join(videoDir, readdirSync(videoDir).find((f) => f.endsWith(".webm"))!);
execFileSync("ffmpeg", [
  "-y", "-i", webm,
  "-vf", "setpts=PTS/2.5,fps=5,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff:max_colors=48[p];[b][p]paletteuse=dither=none:diff_mode=rectangle",
  "-loop", "0", join(out, "walkthrough.gif"),
], { stdio: "inherit" });
console.log("done:", out);
