import { test, expect } from "@playwright/test";
import type { ComplaintCollection, Complaint } from "../src/complaints";
const complaint: Complaint = {
  id: "fixture-a",
  url: "https://www.threads.com/@fixture/post/fixture-a",
  title: "Synthetic UI fixture",
  summary: "Тестовая жалоба: в Астане на Сейфуллина задерживаются автобусы.",
  sourceKind: "threads",
  directions: ["Транспорт"],
  confidence: { Транспорт: 0.95 },
  astanaProbability: 0.95,
  complaintProbability: 0.95,
  decision: "accepted",
  reason: "Synthetic test fixture",
  location: {
    id: "fixture-place",
    name: "улица Сакена Сейфуллина",
    kind: "street",
    point: [51.17157, 71.42732],
  },
};
const collection: ComplaintCollection = {
  posts: [
    complaint,
    {
      ...complaint,
      id: "fixture-b",
      url: "https://www.threads.com/@fixture/post/fixture-b",
      summary: "Тестовая жалоба без места: в Астане перебои воды.",
      directions: ["Сервисы"],
      location: null,
    },
    {
      ...complaint,
      id: "fixture-c",
      decision: "review",
      location: null,
      summary: "Тестовый сомнительный результат",
    },
  ],
  queries: ["Астана пробки"],
  searchedQueries: ["Астана пробки"],
  model: "jev-fixture",
  cached: false,
  fetchedAt: "2026-09-23T10:00:00Z",
  coverage: "Synthetic browser fixture, not real evidence",
};
test.beforeEach(async ({ page }) => {
  await page.route("**/api/health", (r) =>
    r.fulfill({
      json: {
        configured: true,
        jevConfigured: true,
        model: "gpt-6-luna",
        token: "test-token",
      },
    }),
  );
  await page.route("**/api/city", (r) =>
    r.fulfill({ status: 503, json: { error: "fixture" } }),
  );
  await page.route("**/api/complaints", (r) =>
    r.fulfill({ json: { collection: null } }),
  );
});
test("mobility compares the same trips and renders before/after road loads", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByRole("button", { name: "Мобильность", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("нет транспортных мер");
  await expect(page.locator(".mobility-table")).toBeVisible();
  const row = page.locator(".mobility-table>div").nth(1);
  expect(await row.locator("span").nth(1).innerText()).toBe(
    await row.locator("strong").innerText(),
  );
  await page
    .getByRole("button", { name: "Пример: автобусные полосы + светофоры" })
    .click();
  await expect(page.getByRole("dialog")).toContainText("Выделенные полосы");
  await expect(page.locator(".mobility-table")).toBeVisible();
  await expect(
    page.locator(".leaflet-mobility-roads-pane canvas").first(),
  ).toBeAttached();
  await page.getByRole("button", { name: "До", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "До", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "После", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "После", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.screenshot({ path: info.outputPath("mobility.png") });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});
test("complaints ingest, filter, geolocate verified items and preserve results on failure", async ({
  page,
}, info) => {
  await page.route("**/api/complaints/ingest", (r) => {
    expect(r.request().headers()["x-sim-token"]).toBe("test-token");
    expect(r.request().postDataJSON().includePress).toBe(true);
    return r.fulfill({ json: { collection } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Жалобы", exact: true }).click();
  await page.getByRole("button", { name: "Найти жалобы на карте" }).click();
  await expect(page.locator(".complaint-counts")).toContainText("2");
  await expect(page.locator(".complaint-marker")).toHaveCount(1);
  await page
    .getByRole("button", { name: "улица Сакена Сейфуллина", exact: true })
    .click();
  await expect(page.locator(".complaint-popup")).toContainText(
    "приблизительная точка",
  );
  await page.waitForTimeout(350);
  await expect(page.locator(".complaint-popup")).toBeVisible();
  if (info.project.name === "mobile") {
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const box = await page.locator(".leaflet-popup").boundingBox();
    expect(box!.y).toBeGreaterThanOrEqual(190);
  }
  await page.screenshot({ path: info.outputPath("complaints.png") });
  if (!(await page.getByRole("dialog").isVisible()))
    await page.getByRole("button", { name: "Жалобы", exact: true }).click();
  await page.getByLabel("Направление жалоб").selectOption("Сервисы");
  await expect(page.locator(".complaint-marker")).toHaveCount(0);
  await expect(page.locator(".complaint-list")).toContainText(
    "Без подтверждённого места",
  );
  await page.getByLabel("Показать сомнительные результаты").check();
  await expect(page.locator(".complaint-list")).toContainText("сомнительный");
  await expect(page.locator(".complaint-marker")).toHaveCount(0);
  await page.route("**/api/complaints/ingest", (r) =>
    r.fulfill({ status: 502, json: { error: "Jev временно недоступен." } }),
  );
  await page.getByRole("button", { name: "Найти жалобы на карте" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Предыдущий результат сохранён",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
