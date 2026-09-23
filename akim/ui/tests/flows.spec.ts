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
});

test("explore, build five choices, poll, advisor swap, and autopilot", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /А если акимом/ }),
  ).toBeVisible();
  await expect(page.locator(".score-value")).toContainText("52,56");
  await page.waitForTimeout(1200); // Complete the purposeful resident reveal before visual review.
  await page.screenshot({ path: info.outputPath("01-city.png"), scale: "css" });
  await page.getByRole("button", { name: "Район Нура", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Нура", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".district-stats")).toContainText("49,18");
  await page.getByRole("button", { name: "Весь город", exact: true }).click();
  await page.getByRole("button", { name: /Создать план/ }).click();
  await expect(
    page.getByRole("button", { name: "Добавить M7", exact: true }),
  ).toBeDisabled();
  for (const id of ["M7", "M8", "M10"]) {
    await page
      .getByLabel(`Район для ${id}`, { exact: true })
      .selectOption("nura");
    await page
      .getByRole("button", { name: `Добавить ${id}`, exact: true })
      .click();
  }
  await page.getByRole("button", { name: "Добавить M12", exact: true }).click();
  await page
    .getByLabel("Район для M5", { exact: true })
    .selectOption("saryarka");
  await page.getByRole("button", { name: "Добавить M5", exact: true }).click();
  await expect(page.locator(".budget-line")).toContainText("20 700");
  await expect(page.locator(".plan-result")).toContainText("56,54");
  await expect(
    page.getByRole("button", { name: "Добавить M14", exact: true }),
  ).toBeDisabled();
  await page.locator(".panel-scroll").evaluate((el) => (el.scrollTop = 0));
  await page.screenshot({ path: info.outputPath("02-plan.png"), scale: "css" });
  await page.getByRole("button", { name: "Совет акима", exact: true }).click();
  await expect(page.locator(".akim-answer")).toBeVisible();
  await expect(page.locator(".comparison")).toContainText("57,21");
  await page.screenshot({
    path: info.outputPath("03-advisor.png"),
    scale: "css",
  });
  await page
    .getByRole("button", { name: "Оставить мой план", exact: true })
    .click();
  await expect(page.locator(".dismissed")).toBeVisible();
  await page.getByRole("button", { name: "Закрыть AI Акима" }).click();
  await expect(page.locator(".score-value")).toContainText("56,54");
  await page.getByRole("button", { name: "AI Аким", exact: true }).click();
  await page.getByRole("button", { name: "Применить замену" }).click();
  await expect(page.locator(".score-value")).toContainText("57,21");
  await page
    .getByRole("button", { name: "Спросить город", exact: true })
    .click();
  await page
    .getByRole("button", { name: /Что жители думают о моём плане/ })
    .click();
  await expect(page.locator(".poll-loading")).toContainText("Слушаем жителей");
  await expect(page.locator(".poll-result")).toBeVisible();
  await expect(page.locator(".poll-districts>div")).toHaveCount(5);
  await page.screenshot({ path: info.outputPath("04-poll.png"), scale: "css" });
  await page.getByRole("button", { name: "Закрыть опрос" }).click();
  await page.getByRole("button", { name: "AI Аким", exact: true }).click();
  await page.getByRole("button", { name: "Автопилот", exact: true }).click();
  await expect(page.locator(".proposed-plan>li")).toHaveCount(5);
  await page.screenshot({
    path: info.outputPath("05-autopilot.png"),
    scale: "css",
  });
  await page
    .getByRole("button", { name: "Применить план", exact: true })
    .click();
  await expect(page.locator(".score-value")).toContainText("57,35");
  await page.reload();
  await expect(page.locator(".score-value")).toContainText("57,35");
  expect(errors).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("demo path, real budget block, local conflict, unsupported question and comparison", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: /Попробовать готовый сценарий/ })
    .click();
  await expect(page.locator(".score-value")).toContainText("56,54");
  await page.getByRole("button", { name: /Мой план/ }).click();
  await page.getByRole("button", { name: "Сбросить", exact: true }).click();
  await page.getByLabel("Район для M3", { exact: true }).selectOption("esil");
  await page.getByRole("button", { name: "Добавить M3", exact: true }).click();
  await page.getByLabel("Район для M13", { exact: true }).selectOption("nura");
  await expect(
    page.getByRole("button", { name: "Добавить M13", exact: true }),
  ).toBeDisabled();
  await expect(page.getByTestId("measure-M13")).toContainText(
    "Бюджет превышен на 8 000",
  );
  await page.getByRole("button", { name: "Сбросить", exact: true }).click();
  await page.getByLabel("Район для M4", { exact: true }).selectOption("nura");
  await page.getByRole("button", { name: "Добавить M4", exact: true }).click();
  await page.getByLabel("Район для M7", { exact: true }).selectOption("nura");
  await expect(
    page.getByRole("button", { name: "Добавить M7", exact: true }),
  ).toBeDisabled();
  await expect(page.getByTestId("measure-M7")).toContainText("один участок");
  await page.getByLabel("Район для M7", { exact: true }).selectOption("esil");
  await expect(
    page.getByRole("button", { name: "Добавить M7", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Закрыть план" }).click();
  await page
    .getByRole("button", { name: "Спросить город", exact: true })
    .click();
  await page.getByLabel("Вопрос жителям").fill("Что будет с погодой?");
  await page.getByRole("button", { name: "Отправить вопрос" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "В деморежиме доступны три вопроса",
  );
  await page.getByRole("button", { name: /ЛРТ в Есиле или школа/ }).click();
  await expect(page.locator(".comparison-note")).toContainText(
    "Сравнение двух отдельных предложений",
  );
});

test("keyboard focus, reduced motion, narrow layout and invalid persisted state", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.evaluate(() =>
    localStorage.setItem("sim-astana-plan-v1", '[{"measureId":"invalid"}]'),
  );
  await page.reload();
  await expect(page.locator(".score-value")).toContainText("52,56");
  await page.getByRole("button", { name: "Район Нура", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Нура", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("heading", { name: "Нура", exact: true }),
  ).not.toBeVisible();
  const dock = page.getByRole("button", { name: /Создать план/ });
  await dock.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dock).toBeFocused();
  await page.setViewportSize({ width: 360, height: 640 });
  await dock.click();
  const box = await page.getByRole("dialog").boundingBox();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(360);
  expect(box!.y).toBeGreaterThanOrEqual(80);
  expect(box!.y + box!.height).toBeLessThanOrEqual(550);
});
