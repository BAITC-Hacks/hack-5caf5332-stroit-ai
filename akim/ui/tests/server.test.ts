import { test } from "node:test";
import assert from "node:assert/strict";
import { parsePopulation, parseBoundaries } from "../server/city-data";
import { aggregateOpinions, askResidents } from "../server/polls";
import { validateAdvisor } from "../server/akim";
import { PublicError, publicMessage, type Llm } from "../server/llm";
import { askRequest, akimRequest } from "../server/schemas";
import { districts, samplePlan } from "../src/data";
import type { CityData } from "../src/city-data";
const valid = {
  cohorts: districts.flatMap((d) =>
    Array.from({ length: 6 }, (_, profileId) => ({
      districtId: d.id,
      profileId,
      probability: 0.75,
      quote: "Поддерживаю доступные услуги.",
    })),
  ),
};
test("population parser selects the latest unsorted all-population observation, not a subgroup", () => {
  const parsed = parsePopulation([
    {
      termNames: ["Г.АСТАНА", "Всего", "Всего", "Все группы"],
      periods: [
        { date: "31.12.2025", name: "2025 год", value: "1 528 703" },
        { date: "31.12.2023", name: "2023 год", value: "1430117" },
      ],
    },
    {
      termNames: ["Г.АСТАНА", "Мужчины", "Всего", "Все группы"],
      periods: [{ date: "31.12.2026", name: "2026 год", value: "999" }],
    },
  ]);
  assert.equal(parsed.observedAt, "2025-12-31");
  assert.equal(parsed.data.total, 1528703);
  assert.throws(() => parsePopulation([]));
});
test("district multipart geometry is counted once per KATO; empty responses are unavailable", () => {
  const r = parseBoundaries({
    features: [
      { properties: { kato: "7111", name_ru: "Алматы" } },
      { properties: { kato: "7111", name_ru: "Алматы" } },
      { properties: { kato: "7116", name_ru: "Сарайшык" } },
    ],
  });
  assert.equal(r.data.districts.length, 2);
  assert.equal(r.data.parts, 3);
  assert.throws(() => parseBoundaries({ features: [] }));
});
test("LLM cohort probabilities aggregate to actual resident votes and reject fabricated cohorts", () => {
  const poll = aggregateOpinions(valid, samplePlan, "test", "gpt-6-luna");
  assert.equal(
    poll.districts.reduce((n, r) => n + r.total, 0),
    2000,
  );
  assert.equal(
    poll.approval,
    poll.cohorts!.reduce((n, c) => n + c.yes, 0) / 20,
  );
  assert.equal(poll.cost, 95);
  for (const mutate of [
    (c: typeof valid) => c.cohorts.pop(),
    (c: typeof valid) => (c.cohorts[1] = c.cohorts[0]),
    (c: typeof valid) => (c.cohorts[0].probability = 1.5),
  ]) {
    const c = structuredClone(valid);
    mutate(c);
    assert.throws(() => aggregateOpinions(c, samplePlan, "test", "gpt-6-luna"));
  }
});
test("advisor accepts one replacement regardless of JSON property order and rejects zero or multiple changes", () => {
  const next = samplePlan.map((c) => ({ ...c }));
  next[4] = { districtId: "nura", measureId: "M3" };
  assert.deepEqual(validateAdvisor(samplePlan, next), []);
  assert.ok(validateAdvisor(samplePlan, samplePlan).length);
  next[1] = { measureId: "M8", districtId: "esil" };
  assert.ok(validateAdvisor(samplePlan, next).length);
});
test("API inputs and output errors do not expose provider details", () => {
  assert.equal(
    askRequest.safeParse({ question: "x".repeat(1001), plan: [] }).success,
    false,
  );
  assert.equal(
    akimRequest.safeParse({ mode: "admin", plan: [] }).success,
    false,
  );
  assert.equal(
    askRequest.safeParse({
      question: "x",
      plan: [{ measureId: "M7", districtId: "unknown" }],
    }).success,
    false,
  );
  assert.ok(
    !publicMessage(new Error("private-key-value")).includes(
      "private-key-value",
    ),
  );
  assert.equal(
    publicMessage(new PublicError("Visible validation")),
    "Visible validation",
  );
});
test("invalid current plan is rejected before any paid model call", async () => {
  let calls = 0;
  const llm = {
    model: "fake",
    search: async () => {
      throw Error();
    },
    cache: async (_kind, _input, run) => ({ value: await run(), hit: false }),
    structured: async () => {
      calls++;
      throw Error();
    },
    tools: async () => {
      calls++;
      throw Error();
    },
  } as Llm;
  await assert.rejects(askResidents(llm, "мой план", [], {} as CityData));
  assert.equal(calls, 0);
});

test("Threads evidence rejects fabricated URLs, unrelated domains and duplicate posts", async () => {
  const { threadUrl, verifiedEvidence } = await import("../server/threads");
  assert.equal(threadUrl("https://threads.com.evil.example/@a/post/123"), null);
  assert.equal(threadUrl("https://threads.com/@a"), null);
  assert.equal(threadUrl("javascript:alert(1)"), null);
  const source = "https://www.threads.com/@example/post/fixture123";
  const post = {
    url: source,
    summary: "Synthetic fixture about a road.",
    stance: "complaint",
    scope: "street",
  };
  const results = verifiedEvidence(
    {
      posts: [
        post,
        { ...post, url: source + "?utm_source=x" },
        { ...post, url: "https://threads.com/@invented/post/missing" },
      ],
    },
    [{ url: source, title: "Fixture source" }],
  );
  assert.equal(results.length, 1);
  assert.equal(results[0].title, "Fixture source");
  assert.equal(results[0].publishedAt, null);
});
test("source storage reuses valid snapshots and labels stale failures", async () => {
  const { getSource } = await import("../server/city-data");
  const { memoryStore } = await import("../server/storage");
  const store = memoryStore();
  let calls = 0;
  const fetcher: typeof fetch = async () => {
    calls++;
    return Response.json({
      current: {
        time: "2026-09-23T15:00",
        temperature_2m: 17,
        wind_speed_10m: 20,
        weather_code: 1,
      },
    });
  };
  const live = await getSource("weather", fetcher, store);
  assert.equal(live.status, "live");
  const cached = await getSource("weather", fetcher, store);
  assert.equal(cached.status, "cached");
  assert.equal(calls, 1);
  await store.put(
    "source:weather",
    { ...live, fetchedAt: "2020-01-01T00:00:00Z" },
    600,
  );
  const stale = await getSource(
    "weather",
    async () => {
      throw Error("offline");
    },
    store,
  );
  assert.equal(stale.status, "cached");
  assert.ok(stale.error);
  assert.equal(stale.fetchedAt, "2020-01-01T00:00:00Z");
  const unavailable = await getSource(
    "air",
    async () => {
      throw Error("offline");
    },
    store,
  );
  assert.equal(unavailable.status, "unavailable");
  assert.equal(unavailable.data, null);
});

test("advisor closes a prolonged search with a verified, consulted proposal", async () => {
  const { runAkim } = await import("../server/akim");
  const { advise } = await import("../src/engine");
  const candidate = advise(samplePlan)!.plan;
  let rounds = 0;
  const llm: Llm = {
    model: "test-fixture",
    search: async () => {
      throw new Error("Unexpected search");
    },
    cache: async (_kind, _input, run) => ({ value: await run(), hit: false }),
    tools: async (_input, available) => {
      const round = rounds++;
      const names = available.flatMap((t) =>
        t.type === "function" ? [t.name] : [],
      );
      if (round === 5) assert.deepEqual(names, ["submit_plan"]);
      const name =
        round === 0
          ? "simulate"
          : round === 5
            ? "submit_plan"
            : "ask_residents";
      return {
        output: [
          {
            type: "function_call",
            name,
            call_id: `fixture-${round}`,
            arguments: JSON.stringify({
              choices: candidate.map((c) => ({
                ...c,
                districtId: c.districtId ?? null,
              })),
            }),
          },
        ],
      } as import("openai/resources/responses/responses").Response;
    },
    structured: async (_name, schema) =>
      schema.parse({
        title: "Fixture",
        strengths: "Fixture",
        risks: "Fixture",
        why: "Fixture",
      }),
  };
  const result = await runAkim(
    llm,
    "advisor",
    samplePlan,
    {} as CityData,
    () => {},
  );
  assert.equal(rounds, 6);
  assert.deepEqual(result.plan, candidate);
  assert.deepEqual(validateAdvisor(samplePlan, result.plan), []);
});
