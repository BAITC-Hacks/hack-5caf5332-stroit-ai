import { test, expect } from "@playwright/test";
const example = "M7.nura,M8.nura,M10.nura,M12,M5.saryarka";
test.beforeEach(async ({ page }) => {
  await page.route("**/api/health", r => r.fulfill({ json: { configured: false, model: "gpt-6-luna", token: "test" } }));
  await page.route("**/api/city", r => r.fulfill({ status: 503, json: { error: "Offline test" } }));
  await page.route("https://tile.openstreetmap.org/**", r => r.fulfill({ status: 204, body: "" }));
});
test("report yields to residents and advisor; helper overlays never cover dialogs", async ({ page }) => {
  await page.goto(`/?plan=${example}&step=report`);
  await page.getByRole("button", { name: "Спросить жителей", exact: true }).click();
  await expect(page.locator(".sheet-backdrop")).toBeHidden();
  await expect(page.getByRole("dialog", { name: "Спросить город" })).toBeVisible();
  await page.getByRole("button", { name: "Закрыть опрос" }).click();
  await expect(page.locator(".sheet-backdrop")).toBeVisible();
  await page.getByRole("button", { name: "AI-аким", exact: true }).click();
  await expect(page.locator(".sheet-backdrop")).toBeHidden();
  await expect(page.getByRole("dialog", { name: "AI Аким" })).toBeVisible();
  await expect(page.locator(".toast")).toBeHidden();
  await expect(page.locator(".turn-hint")).toBeHidden();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Вернуться к карте" }).click();
  await page.getByRole("button", { name: "Данные города", exact: true }).click();
  await expect(page.locator(".turn-hint")).toBeHidden();
  await expect(page.locator(".toast")).toBeHidden();
  await expect(page.getByRole("dialog")).toBeVisible();
});

test("stress events change the projection, preserve the plan and reject inflation overspend", async ({ page }, info) => {
  await page.goto(`/?plan=${example}&step=report`);
  await page.getByRole("button", { name: "Что если", exact: true }).click();
  await expect(page.locator(".stress-summary")).toContainText("56,54");
  await expect(page.locator(".stress-verdict")).toContainText("Критических показателей: 0 → 2");
  await expect(page.locator(".stress-measures tbody tr")).toHaveCount(5);
  await page.getByRole("button", { name: "Отключение ТЭЦ", exact: true }).click();
  await expect(page.locator(".stress-assumptions")).toContainText("Алматы и Сарыарка");
  await page.getByRole("button", { name: "Рост цен на 20%", exact: true }).click();
  await expect(page.locator(".stress-deficit")).toContainText("Не хватает 14 у.е.");
  await expect(page.locator(".stress-summary")).toContainText("Не считается");
  await expect(page.locator(".stress-summary")).toContainText("114 у.е.");
  expect(new URL(page.url()).searchParams.get("plan")).toBe(example);
  await expect(page.locator(".gauge-number strong")).toHaveText("56,54");
  await page.screenshot({ path: info.outputPath("stress.png"), scale: "css" });
});

test("leadership memo invokes print and fits one A4 page with all five decisions", async ({ page }, info) => {
  await page.addInitScript(() => { window.print = () => { document.documentElement.dataset.printCalled = "true"; }; });
  await page.goto(`/?plan=${example}&step=report&focus=Соцсфера,Транспорт`);
  await page.getByRole("button", { name: "Скачать записку", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-print-called", "true");
  await expect(page.locator(".leadership-memo")).toBeHidden();
  await page.emulateMedia({ media: "print" });
  const memo = page.getByRole("article", { name: "Записка руководству" });
  await expect(memo).toBeVisible();
  await expect(page.locator("#root")).toBeHidden();
  await expect(memo.locator("table").first().locator("tbody tr")).toHaveCount(5);
  await expect(memo).toContainText("56,54");
  await expect(memo).toContainText("95 / 100 у.е.");
  await expect(memo).toContainText("Не реальный опрос");
  await expect(memo.locator(".memo-goals li")).toHaveCount(6);
  await page.evaluate(() => document.fonts.ready);
  const pdf = await page.pdf({ path: info.outputPath("memo.pdf"), format: "A4", printBackground: true, preferCSSPageSize: true });
  expect(pdf.toString("latin1").match(/\/Type\s*\/Page\b/g)).toHaveLength(1);
});
