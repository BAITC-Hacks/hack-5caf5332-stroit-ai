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


test("resident canvas survives all detail levels, double-click and interrupted zooms", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/?plan=M7.nura");
  const canvas = page.locator(".resident-overlay");
  await expect(canvas).toBeVisible();
  await page.waitForFunction(() => !!(document.querySelector(".leaflet-host") as HTMLElement & { simMap?: unknown })?.simMap);
  const setZoom = async (zoom: number) => page.evaluate((value) => {
    const map = (document.querySelector(".leaflet-host") as HTMLElement & { simMap: import("leaflet").Map }).simMap;
    map.setZoom(value, { animate: false });
  }, zoom);
  const visiblePixels = async () => {
    await expect(canvas).toHaveCSS("opacity", "1");
    await expect(canvas).toHaveCSS("pointer-events", "none");
    await expect.poll(() => canvas.evaluate((node: HTMLCanvasElement) => {
      const bytes = node.getContext("2d")!.getImageData(0, 0, node.width, node.height).data;
      let pixels = 0;
      for (let i = 3; i < bytes.length; i += 4) if (bytes[i] > 0) pixels++;
      return pixels;
    })).toBeGreaterThan(20);
  };
  for (const [zoom, detail] of [[11, "cluster"], [13, "sparse"], [15, "full"]] as const) {
    await setZoom(zoom);
    await expect(canvas).toHaveAttribute("data-detail", detail);
    await visiblePixels();
  }
  await page.evaluate(() => {
    const map = (document.querySelector(".leaflet-host") as HTMLElement & { simMap: import("leaflet").Map }).simMap;
    map.setZoom(11, { animate: false });
    map.setZoom(15, { animate: false });
    map.setZoom(13, { animate: false });
    // Also cover an interrupted transition whose final notification is moveend.
    map.fire("zoomstart");
    map.fire("moveend");
  });
  await expect(page.locator(".leaflet-host")).not.toHaveClass(/leaflet-zoom-anim/);
  await visiblePixels();
  await setZoom(13);
  await expect(canvas).toHaveAttribute("data-detail", "sparse");
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect(canvas).toHaveAttribute("data-detail", "full");
  await visiblePixels();
  await setZoom(13);
  await page.locator(".leaflet-host").dblclick({ position: { x: 750, y: 450 } });
  await expect(canvas).toHaveAttribute("data-detail", "full");
  await visiblePixels();
  for (const name of ["Zoom out", "Zoom in", "Zoom out", "Zoom in"]) {
    await page.getByRole("button", { name, exact: true }).click();
  }
  await expect(page.locator(".leaflet-host")).not.toHaveClass(/leaflet-zoom-anim/);
  await visiblePixels();
});
