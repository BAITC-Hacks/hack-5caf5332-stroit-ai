import { test, expect } from "@playwright/test";
import { districts, samplePlan } from "../src/data";
import { pollProposal } from "../src/residents";
import { advise } from "../src/engine";
const source = (id: string, data: unknown, note: string) => ({
  id,
  name: id,
  attribution: "Проверяемый источник",
  url: "https://api.open-meteo.com/",
  status: "cached",
  observedAt: "2026-09-23T08:00:00Z",
  fetchedAt: "2026-09-23T08:10:00Z",
  data,
  note,
});
const city = {
  weather: source(
    "weather",
    { temperature: 16.5, wind: 22.2, code: 1 },
    "Модель прогноза",
  ),
  air: source("air", { aqi: 26, pm25: 5.4, pm10: 6 }, "Модельная сетка CAMS"),
  accidents: source(
    "accidents",
    { count: 1537, year: 2026 },
    "Географическая рамка",
  ),
  population: source(
    "population",
    { total: 1528703, period: "2025 год" },
    "Последний опубликованный период",
  ),
  boundaries: source(
    "boundaries",
    {
      districts: [
        ...districts.map((d) => ({ kato: d.id, name: d.name })),
        { kato: "7116", name: "Сарайшык" },
      ],
      parts: 11,
    },
    "Реестр из шести районов",
  ),
};
test.beforeEach(async ({ page }) => {
  await page.route("**/api/health", (r) =>
    r.fulfill({
      json: { configured: true, model: "gpt-6-luna", token: "fixture-token" },
    }),
  );
  await page.route("**/api/city", (r) => r.fulfill({ json: city }));
});
test("city sources, resident details, clock speed and pause", async ({
  page,
}, info) => {
  await page.goto("/");
  await expect(page.locator(".data-toggle")).toContainText("16.5°");
  await page.getByRole("button", { name: "Пауза симуляции" }).click();
  const time = await page.locator(".simulation-controls time").innerText();
  await page.waitForTimeout(250);
  await expect(page.locator(".simulation-controls time")).toHaveText(time);
  await page.getByRole("button", { name: "Познакомиться с жителем" }).click();
  await expect(page.getByLabel("Житель города")).toContainText(
    "СИНТЕТИЧЕСКИЙ ЖИТЕЛЬ",
  );
  await page.screenshot({ path: info.outputPath("resident.png") });
  await page.getByRole("button", { name: "Закрыть жителя" }).click();
  await page.getByLabel("Скорость симуляции").selectOption("120");
  await page.getByRole("button", { name: "Продолжить симуляцию" }).click();
  await expect(page.locator(".simulation-controls time")).not.toHaveText(time);
  await page.getByRole("button", { name: "Открыть реальные данные" }).click();
  await expect(page.getByRole("dialog")).toContainText("1 528 703");
  await expect(page.getByRole("dialog")).toContainText("Сарайшык");
  await page.screenshot({ path: info.outputPath("sources.png") });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
test("live poll carries model identity, validates token and surfaces failure without silent fallback", async ({
  page,
}) => {
  let posted = false;
  await page.route("**/api/ask", async (route) => {
    expect(route.request().headers()["x-sim-token"]).toBe("fixture-token");
    posted = true;
    await route.fulfill({
      json: {
        poll: {
          ...pollProposal(
            [{ measureId: "M7", districtId: "nura" }],
            "Школа и детсад в Нуре?",
          ),
          mode: "live",
          model: "gpt-6-luna",
          cached: false,
        },
      },
    });
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Спросить город", exact: true })
    .click();
  await expect(page.locator(".ai-mode-switch")).toContainText("gpt-6-luna");
  await page.getByRole("button", { name: /Школа и детсад в Нуре/ }).click();
  await expect(page.locator(".poll-result")).toContainText("OpenAI gpt-6-luna");
  expect(posted).toBe(true);
  await page.getByRole("button", { name: "Задать ещё вопрос" }).click();
  await page.route("**/api/ask", (r) =>
    r.fulfill({ status: 502, json: { error: "OpenAI временно недоступен" } }),
  );
  await page.getByRole("button", { name: /Школа и детсад в Нуре/ }).click();
  await expect(page.getByRole("alert")).toContainText(
    "OpenAI временно недоступен",
  );
  await expect(page.locator(".poll-result")).toHaveCount(0);
  await expect(page.locator(".ai-mode-switch")).toContainText("gpt-6-luna");
});
test("live advisor streams actual activity, displays verified result and applies only on user action", async ({
  page,
}, info) => {
  const candidate = advise(samplePlan)!;
  let calls = 0;
  await page.route("**/api/akim", async (route) => {
    calls++;
    expect(route.request().postDataJSON().mode).toBe("advisor");
    const event = {
      label: "Симуляция сценария",
      detail: "Проверка бюджета завершена.",
      at: new Date().toISOString(),
    };
    await route.fulfill({
      contentType: "application/x-ndjson",
      body:
        JSON.stringify({ type: "activity", event }) +
        "\n" +
        JSON.stringify({
          type: "result",
          result: {
            plan: candidate.plan,
            result: candidate.result,
            title: "Улучшим доступность транспорта",
            strengths: "Удобнее поездки.",
            risks: "Озеленение придётся отложить.",
            why: "Сравнение допустимых сценариев.",
            model: "gpt-6-luna",
            cached: false,
            events: [event],
          },
        }) +
        "\n",
    });
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: /Попробовать готовый сценарий/ })
    .click();
  await page.getByRole("button", { name: "AI Аким", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Проверить план с AI" }),
  ).toBeVisible();
  expect(calls).toBe(0);
  await page.getByRole("button", { name: "Проверить план с AI" }).click();
  await expect(page.locator(".activity")).toContainText(
    "Проверка бюджета завершена",
  );
  await expect(page.locator(".akim-answer")).toContainText(
    "Улучшим доступность транспорта",
  );
  await page.screenshot({ path: info.outputPath("luna-advisor.png") });
  const stored = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("sim-astana-plan-v1")!),
  );
  expect(stored).toEqual(samplePlan);
  await page.getByRole("button", { name: "Применить замену" }).click();
  await expect(page.locator(".score-value")).toContainText("57,21");
  expect(calls).toBe(1);
});
