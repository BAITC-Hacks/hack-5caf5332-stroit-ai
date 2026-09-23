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
