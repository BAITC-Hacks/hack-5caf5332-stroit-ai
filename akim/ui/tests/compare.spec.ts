import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/health", (route) => route.fulfill({
    json: { configured: false, model: "gpt-6-luna", token: "test" },
  }));
  await page.route("**/api/city", (route) => route.fulfill({ status: 503, json: { error: "Offline test" } }));
  await page.route("https://tile.openstreetmap.org/**", (route) => route.fulfill({ status: 204, body: "" }));
});

test("save a scenario, edit through the district panel and compare results", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "Сравнение проверяется на десктопе");
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const original = "M7.nura,M8.nura,M10.nura,M12,M5.saryarka";
  await page.goto(`/?plan=${original}&step=report`);
  const sheet = page.locator(".sheet");
  await sheet.getByRole("button", { name: "Сохранить как вариант", exact: true }).click();
  await expect(page.locator(".toast")).toHaveText("Сохранён как Вариант A");
  await sheet.getByRole("button", { name: "Варианты (1)", exact: true }).click();
  const variants = page.getByRole("dialog", { name: "Сохранённые варианты" });
  await expect(variants).toContainText("Балл 56,54 · Бюджет 95 у.е.");
  await variants.getByRole("textbox", { name: "Название варианта A" }).fill("Социальный план");
  await variants.getByRole("textbox", { name: "Название варианта A" }).press("Enter");
  await variants.getByRole("button", { name: "Загрузить", exact: true }).click();
  await expect(sheet).toBeHidden();
  await expect(page.locator(".tray-slots li.filled")).toHaveCount(5);

  await page.getByRole("button", { name: "Убрать: Чистое топливо, Сарыарка", exact: true }).click();
  await page.getByRole("button", { name: "Район Нура", exact: true }).click();
  await page.getByRole("button", { name: /Все 14 мер/ }).click();
  await page.locator(".decision-list li", { hasText: "ЛРТ" }).getByRole("button", { name: /Построить/ }).click();
  await page.getByRole("button", { name: /Подвести итог/ }).click();

  const comparison = page.getByRole("table", { name: "Сравнение сценариев", exact: true });
  await expect(comparison).toBeVisible();
  await expect(comparison).toContainText("Социальный план");
  await expect(comparison.getByRole("row", { name: /Балл \(Score\)/ })).toContainText("57,21");
  await expect(comparison.getByRole("row", { name: /Балл \(Score\)/ })).toContainText("56,54");
  await expect(comparison.getByRole("row", { name: /Балл \(Score\)/ })).toContainText("+0,66");
  await expect(page.locator(".comparison-conclusion")).toHaveText("Текущий план лучше на +0,66: сильнее в транспорте Нуры, слабее в экологии Сарыарки.");
  const districts = page.getByRole("table", { name: "Разница по районам и направлениям" });
  await expect(districts.getByRole("row", { name: /^Нура/ })).toContainText("+9,00");
  await expect(districts.getByRole("row", { name: /^Сарыарка/ })).toContainText("−4,38");
  await comparison.scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath("comparison.png"), scale: "css" });

  // The URL restores comparison even without an explicit report step.
  const shared = new URL(page.url());
  expect(shared.searchParams.get("vs")).toBe(original);
  shared.searchParams.delete("step");
  await page.goto(shared.toString());
  await expect(comparison).toBeVisible();
  await expect(page.locator(".comparison-conclusion")).toContainText("лучше на +0,66");
  await sheet.getByRole("button", { name: "Варианты (1)", exact: true }).click();
  await expect(variants.getByRole("textbox", { name: "Название варианта A" })).toHaveValue("Социальный план");
  await variants.getByRole("button", { name: "Сравнить", exact: true }).click();
  await expect(comparison).toContainText("Социальный план");

  await sheet.getByRole("button", { name: "Сравнить с эталоном автопилота", exact: true }).click();
  await expect(comparison).toContainText("Эталон автопилота");
  await expect(page.locator(".comparison-conclusion")).toContainText("показатели районов совпадают");
  for (const name of ["B", "C"]) {
    await sheet.getByRole("button", { name: "Сохранить как вариант", exact: true }).click();
    await expect(page.locator(".toast")).toHaveText(`Сохранён как Вариант ${name}`);
  }
  await expect(sheet.getByRole("button", { name: "Сохранить как вариант", exact: true })).toBeDisabled();
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("sim-astana-variants-v1")!));
  expect(stored).toHaveLength(3);
  expect(stored[0]).toEqual({ id: "A", name: "Социальный план", plan: original });
  expect(errors).toEqual([]);
});
