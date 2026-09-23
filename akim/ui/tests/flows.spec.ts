import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/health", (route) =>
    route.fulfill({
      json: { configured: false, model: "gpt-6-luna", token: "test" },
    }),
  );
  await page.route("**/api/city", (route) =>
    route.fulfill({ status: 503, json: { error: "Offline test" } }),
  );
  await page.route("https://tile.openstreetmap.org/**", (route) =>
    route.fulfill({ status: 204, body: "" }),
  );
});

test("one path: intro, brief, five decisions from the district panel, report, swap", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Пять решений для города" }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Стать акимом/ }).click();
  await expect(
    page.getByRole("heading", { name: /Город сейчас: 52,56/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Соцсфера", exact: true }).click();
  await page.getByRole("button", { name: /Начать: район Нура/ }).click();
  await expect(page.locator(".turn-hint")).toContainText("Нура");
  await page.screenshot({ path: info.outputPath("01-turn.png"), scale: "css" });

  // Three decisions in Nura, straight from the district panel.
  await page.getByRole("button", { name: "Район Нура", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Нура", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Все 14 мер/ }).click();
  for (const name of ["Школа и детсад", "Поликлиника", "Освещение и камеры"]) {
    await page
      .locator(".decision-list li", { hasText: name })
      .getByRole("button", { name: /Построить/ })
      .click();
    await expect(page.locator(".toast")).toContainText(name);
  }
  await expect(page.locator(".tray-slots li.filled")).toHaveCount(3);
  await expect(page.locator(".map-markers li", { hasText: "Школа и детсад" })).toBeVisible();
  await expect(page.locator(".tray-score strong")).toContainText("55,86");

  // A city-wide measure and a district measure elsewhere complete the plan.
  await page
    .locator(".decision-list li", { hasText: "Платформа обращений" })
    .getByRole("button", { name: /Построить/ })
    .click();
  await page.locator(".jump").getByRole("button", { name: "Сарыарка" }).click();
  await expect(
    page.getByRole("heading", { name: "Сарыарка", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Все 14 мер/ }).click();
  await page
    .locator(".decision-list li", { hasText: "Чистое топливо" })
    .getByRole("button", { name: /Построить/ })
    .click();
  await expect(page.locator(".tray-budget span")).toContainText("95 из 100");
  await expect(page.locator(".tray-score strong")).toContainText("56,54");
  await expect(
    page.getByRole("heading", { name: "Все пять решений приняты" }),
  ).toBeVisible();
  await page.screenshot({ path: info.outputPath("02-five.png"), scale: "css" });

  // Report over the map: goals, contributions, brief, residents, advice.
  await page.getByRole("button", { name: /Подвести итог/ }).click();
  await expect(
    page.getByRole("heading", { name: "Итог вашего плана" }),
  ).toBeVisible();
  await expect(page.locator(".goal-list li.met")).toHaveCount(5);
  await expect(page.locator(".parts li").first()).toContainText("+1,45");
  await expect(page.locator(".brief-columns")).toContainText("синергия M10 + M12");
  await expect(page.locator(".support-total")).toContainText("54%");
  await expect(page.locator(".swap")).toContainText("+0,66");
  await expect(page.locator(".ai-note")).toContainText("ключ OpenAI");
  expect(page.url()).toContain("step=report");
  await page.screenshot({ path: info.outputPath("03-report.png"), scale: "css", fullPage: true });

  // Applying the swap changes the plan on the map and the score.
  await page.getByRole("button", { name: "Применить замену", exact: true }).click();
  await expect(page.locator(".tray-score strong")).toContainText("57,21");
  await expect(page.locator(".map-markers li", { hasText: "ЛРТ" })).toBeVisible();

  // The scenario link reproduces the plan after a reload.
  await page.reload();
  await expect(page.locator(".tray-score strong")).toContainText("57,21");
  expect(errors).toEqual([]);
});

test("rules are enforced on the map: budget, direction cap and conflicts", async ({
  page,
}) => {
  await page.goto("/?plan=M3.esil,M13.nura,M5.saryarka");
  await page.getByRole("button", { name: "Район Алматы", exact: true }).click();
  const school = page.locator(".decision-list li", { hasText: "Школа и детсад" });
  await page.getByRole("button", { name: /Все 14 мер/ }).click();
  await expect(school).toContainText("бюджет превышен на 7");
  await expect(school.getByRole("button", { name: /Построить/ })).toBeDisabled();
  await expect(page.locator(".tray-go")).toBeDisabled();
  await expect(page.locator(".tray-budget em")).toContainText("Осталось 2 из 5");
  await page.goto("/?plan=M3.esil");
  await page.getByRole("button", { name: "Район Алматы", exact: true }).click();
  await page.getByRole("button", { name: /Все 14 мер/ }).click();
  const lanes = page.locator(".decision-list li", { hasText: "Автобусные полосы" });
  await expect(lanes).toContainText("M1 и M3");
  await expect(lanes.getByRole("button", { name: /Построить/ })).toBeDisabled();
});

test("ready example, keyboard escape and invalid link fall back safely", async ({
  page,
}) => {
  await page.goto("/?plan=M1.esil,M3.nura");
  await expect(
    page.getByRole("heading", { name: "Пять решений для города" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Посмотреть готовый пример" }).click();
  await expect(
    page.getByRole("heading", { name: "Итог вашего плана" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("heading", { name: "Итог вашего плана" }),
  ).toBeHidden();
  await expect(page.locator(".tray-slots li.filled")).toHaveCount(5);
  await page.getByRole("button", { name: /Как это работает/ }).click();
  await expect(page.getByRole("dialog")).toContainText("70%");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
});
