import { test, expect } from "@playwright/test";
import { districts, samplePlan } from "../src/data";
import { pollProposal } from "../src/residents";
import { advise, simulate } from "../src/engine";
import { population, residentState } from "../src/population";
import { toLatLng } from "../src/geography";
import { encodePlan } from "../src/planner/analysis";
const planUrl = "/?plan=M7.nura,M8.nura,M10.nura,M12,M5.saryarka";
test.use({ reducedMotion: "reduce" });
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
  await page.route("https://tile.openstreetmap.org/**", (r) =>
    r.fulfill({ status: 204, body: "" }),
  );
});
test("city sources and resident details in the turn stage", async ({
  page,
}, info) => {
  await page.goto(planUrl);
  await expect(page.locator(".tray-slots li.filled")).toHaveCount(5);
  await page.getByRole("button", { name: "Данные города", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("16.5");
  await expect(page.getByRole("dialog")).toContainText("1 528 703");
  await expect(page.getByRole("dialog")).toContainText("Сарайшык");
  await page.screenshot({ path: info.outputPath("sources.png") });
  await page.keyboard.press("Escape");

  // Reduced motion keeps residents at 09:00; project their positions at the initial zoom.
  const project = ([lat, lng]: [number, number]) => {
    const sin = Math.sin(lat * Math.PI / 180);
    const scale = 256 * 2 ** 12;
    return [scale * (lng / 360 + 0.5), scale * (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI))];
  };
  const center = project([51.153, 71.427]);
  const bounds = (await page.locator(".leaflet-host").boundingBox())!;
  const positions = population.map((person) => {
    const point = project(toLatLng(residentState(person, 540, false).point));
    return {
      x: bounds.x + point[0] - Math.round(center[0] - bounds.width / 2),
      y: bounds.y + point[1] - Math.round(center[1] - bounds.height / 2),
    };
  });
  const point = await page.evaluate((positions) => positions.find(({ x, y }) => {
    const target = document.elementFromPoint(x, y);
    return target?.closest(".leaflet-host") &&
      !target.closest(".leaflet-marker-icon,.leaflet-control,.leaflet-popup");
  }), positions);
  expect(point).toBeDefined();
  await page.mouse.click(point!.x, point!.y);
  await expect(page.getByLabel("Житель города")).toContainText(/синтетический житель/i);
  await page.screenshot({ path: info.outputPath("resident.png") });
  await page.getByRole("button", { name: "Закрыть жителя" }).click();
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
  await page.goto(`${planUrl}&step=report`);
  await page.getByRole("button", { name: "Спросить жителей", exact: true }).click();
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
      at: "2026-09-23T10:00:00Z",
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
  await page.goto(`${planUrl}&step=report`);
  await page.getByRole("button", { name: "AI-аким", exact: true }).click();
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
    JSON.parse(localStorage.getItem("sim-astana-game-v1")!),
  );
  expect(stored.plan).toBe(encodePlan(samplePlan));
  await page.getByRole("dialog", { name: "AI Аким", exact: true })
    .getByRole("button", { name: "Применить замену", exact: true }).click();
  await expect(page.locator(".tray-score strong")).toContainText("57,21");
  expect(new URL(page.url()).searchParams.get("plan")).toBe(encodePlan(candidate.plan));
  expect(calls).toBe(1);
});

test("Threads ingestion displays cited evidence, scopes complaints and attaches context to a city question", async ({
  page,
}) => {
  const evidence = {
    question: "Новая дорога у Сейфуллина",
    queries: ["Астана Сейфуллина пробки", "Астана новая дорога"],
    searchedQueries: ["site:threads.com Астана Сейфуллина пробки"],
    location: "Астана, Сейфуллина",
    posts: [
      {
        url: "https://www.threads.com/@fixture/post/test123",
        title: "Тестовая публикация",
        summary: "Синтетическая тестовая жалоба на движение.",
        stance: "complaint",
        scope: "street",
        publishedAt: null,
      },
    ],
    fetchedAt: "2026-09-23T10:00:00Z",
    cached: false,
    provider: "OpenAI web search",
    coverage: "Тестовый набор. Не репрезентативный опрос.",
  };
  await page.route("**/api/threads/ingest", (r) => {
    expect(r.request().postDataJSON().question).toContain("Сейфуллина");
    return r.fulfill({ json: { evidence } });
  });
  await page.route("**/api/ask", (r) => {
    expect(r.request().postDataJSON().useThreads).toBe(true);
    return r.fulfill({
      json: {
        poll: null,
        evidence,
        notice:
          "В каталоге нет отдельной меры новой дороги. Результаты поиска доступны.",
      },
    });
  });
  await page.goto(`${planUrl}&step=report`);
  await page.getByRole("button", { name: "Спросить жителей", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Спросить город" })).toContainText(
    "Синтетические жители отвечают по модели. Публичные посты из Threads добавляют реальные голоса по теме.",
  );
  await page.getByLabel("Вопрос жителям").fill("Новая дорога у Сейфуллина");
  await page
    .getByRole("button", { name: "Найти публичные посты", exact: true })
    .click();
  await expect(page.getByLabel("Результаты Threads")).toContainText(
    "С явной привязкой к улице: 1",
  );
  await expect(
    page.getByRole("link", { name: "Тестовая публикация" }),
  ).toHaveAttribute("href", evidence.posts[0].url);
  await expect(page.getByRole("checkbox", { name: "Учитывать посты в ответе жителей" })).toBeChecked();
  await page.getByRole("button", { name: "Отправить вопрос" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Результаты поиска доступны",
  );
  await expect(page.getByLabel("Результаты Threads")).toContainText(
    "Тестовая публикация",
  );
});
test("empty Threads search is distinct from a provider failure", async ({
  page,
}) => {
  await page.route("**/api/threads/ingest", (r) =>
    r.fulfill({
      json: {
        evidence: {
          question: "Сейфуллина",
          queries: ["Астана Сейфуллина пробки"],
          searchedQueries: [],
          location: "Астана",
          posts: [],
          fetchedAt: "2026-09-23T10:00:00Z",
          cached: false,
          provider: "OpenAI web search",
          coverage: "Неполная индексация.",
        },
      },
    }),
  );
  await page.goto(`${planUrl}&step=report`);
  await page.getByRole("button", { name: "Спросить жителей", exact: true }).click();
  await page
    .getByRole("button", { name: "Найти публичные посты", exact: true })
    .click();
  await expect(page.getByLabel("Результаты Threads")).toContainText(
    "не означает, что жители не жалуются",
  );
  await page.route("**/api/threads/ingest", (r) =>
    r.fulfill({ status: 502, json: { error: "Поиск временно недоступен" } }),
  );
  await page
    .getByRole("button", { name: "Найти публичные посты", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Поиск временно недоступен",
  );
  await expect(page.getByLabel("Результаты Threads")).toHaveCount(0);
});

test("live goal submits text, shows parsed constraints and applies only on request", async ({
  page,
}, info) => {
  const goal = "Экология в приоритете, защитить Есиль, поддержка не ниже 50%, резерв 5 у.е.";
  const constraints = {
    priorities: ["Экология"],
    protectedDistricts: ["esil"],
    minSupportPercent: 50,
    reserveUnits: 5,
    mustInclude: [],
    mustExclude: [],
  };
  let calls = 0;
  await page.route("**/api/akim", async (route) => {
    calls++;
    expect(route.request().headers()["x-sim-token"]).toBe("fixture-token");
    expect(route.request().postDataJSON()).toEqual({ mode: "goal", plan: [], goal });
    const event = {
      label: "Проверка цели",
      detail: "Ограничения проверены локальным расчётом.",
      at: "2026-09-23T10:00:00Z",
    };
    await route.fulfill({
      contentType: "application/x-ndjson",
      body: [
        { type: "activity", event },
        {
          type: "result",
          result: {
            plan: samplePlan,
            result: simulate(samplePlan).result,
            constraints,
            title: "План под экологическую цель",
            strengths: "Чище воздух в Сарыарке.",
            risks: "Резерв ограничивает выбор мер.",
            why: "Учтены приоритет и защита района.",
            model: "gpt-6-luna",
            cached: false,
            events: [event],
          },
        },
      ].map((item) => JSON.stringify(item)).join("\n") + "\n",
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Стать акимом" }).click();
  await page.getByRole("button", { name: "Поручить AI-акиму" }).click();
  await expect(page.locator(".ai-mode-switch")).toContainText("gpt-6-luna");
  await page.getByRole("button", { name: "Цель", exact: true }).click();
  const submit = page.getByRole("button", { name: "Собрать план под цель" });
  await expect(submit).toBeDisabled();
  await expect(page.getByLabel("Цель словами")).toHaveAttribute("maxlength", "300");
  await page.getByLabel("Цель словами").fill(goal);
  expect(calls).toBe(0);
  await submit.click();
  await expect(page.locator(".activity")).toContainText("Ограничения проверены");
  await expect(page.getByLabel("Ограничения плана").locator("li")).toHaveText([
    "Приоритет: экология", "Защищён: Есиль", "Поддержка ≥ 50%", "Резерв 5 у.е.",
  ]);
  await expect(page.locator(".akim-answer")).toContainText("План под экологическую цель");
  await expect(page.locator(".proposed-plan li")).toHaveCount(5);
  await expect(page.locator(".comparison strong")).toHaveText(["52,56", "56,54"]);
  expect(new URL(page.url()).searchParams.has("plan")).toBe(false);
  await page.screenshot({ path: info.outputPath("goal.png") });
  await page.getByRole("button", { name: "Применить план", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "AI Аким", exact: true })).toBeHidden();
  await expect(page.locator(".tray-slots li.filled")).toHaveCount(5);
  await expect(page.locator(".tray-score strong")).toContainText("56,54");
  expect(new URL(page.url()).searchParams.get("plan")).toBe(encodePlan(samplePlan));
  expect(calls).toBe(1);
});

test("goal without a key submits structured constraints and preserves server errors", async ({
  page,
}, info) => {
  await page.route("**/api/health", (route) => route.fulfill({
    json: { configured: false, model: "gpt-6-luna", token: "fixture-token" },
  }));
  let calls = 0;
  await page.route("**/api/akim", async (route) => {
    calls++;
    const body = route.request().postDataJSON();
    expect(body).toEqual({
      mode: "goal",
      plan: [],
      constraints: {
        priorities: ["Экология"], protectedDistricts: ["esil"],
        minSupportPercent: 50, reserveUnits: calls === 1 ? 100 : 5,
        mustInclude: [], mustExclude: [],
      },
    });
    await route.fulfill({
      contentType: "application/x-ndjson",
      body: JSON.stringify(calls === 1 ? {
        type: "error",
        error: "Ограниченный локальный поиск не нашёл допустимый план. Уменьшите резерв.",
      } : {
        type: "result",
        result: {
          plan: samplePlan,
          result: simulate(samplePlan).result,
          constraints: body.constraints,
          title: "План по заданной цели",
          strengths: "Ограничения соблюдены.",
          risks: "Поддержка синтетическая.",
          why: "План проверен локально.",
          model: "local", cached: false, events: [],
        },
      }) + "\n",
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Стать акимом" }).click();
  await page.getByRole("button", { name: "Поручить AI-акиму" }).click();
  await page.getByRole("button", { name: "Цель", exact: true }).click();
  await expect(page.getByLabel("Цель словами")).toHaveCount(0);
  await page.getByRole("checkbox", { name: "Экология", exact: true }).check();
  await page.getByRole("checkbox", { name: "Есиль", exact: true }).check();
  await page.getByLabel("Поддержка не ниже, %").fill("50");
  await page.getByLabel("Резерв, у.е.").fill("100");
  expect(calls).toBe(0);
  await page.getByRole("button", { name: "Собрать план под цель" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Ограниченный локальный поиск не нашёл допустимый план. Уменьшите резерв.",
  );
  await expect(page.locator(".akim-answer")).toHaveCount(0);
  await page.getByLabel("Резерв, у.е.").fill("5");
  expect(calls).toBe(1);
  await page.getByRole("button", { name: "Собрать план под цель" }).click();
  await expect(page.getByLabel("Ограничения плана")).toContainText("Резерв 5 у.е.");
  await expect(page.locator(".akim-answer")).toContainText("План по заданной цели");
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.screenshot({ path: info.outputPath("local-goal.png") });
  expect(calls).toBe(2);
});
