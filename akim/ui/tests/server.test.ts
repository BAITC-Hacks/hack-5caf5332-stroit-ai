import { test } from "node:test";
import assert from "node:assert/strict";
import { parsePopulation, parseBoundaries } from "../server/city-data";
import { aggregateOpinions, askResidents } from "../server/polls";
import { validateAdvisor } from "../server/akim";
import { PublicError, publicMessage, type Llm } from "../server/llm";
import { askRequest, akimRequest } from "../server/schemas";
import { districts, samplePlan } from "../src/data";
import { AGENTS } from "../src/profiles";
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
    AGENTS,
  );
  assert.equal(
    poll.approval,
    poll.cohorts!.reduce((n, c) => n + c.yes, 0) * 100 / AGENTS,
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
    tools: async (_input, available, _signal, force) => {
      const round = rounds++;
      assert.equal(available.length, 3);
      assert.equal(force, round === 5 ? "submit_plan" : undefined);
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

type GoalConstraints = import("../server/schemas").GoalConstraints;
type Choice = import("../src/data").Choice;

async function goalFixture(constraints: GoalConstraints, rejected?: Choice[], supported = true) {
  const { validateGoal } = await import("../server/goal");
  const state = { parses: 0, rounds: 0, narratives: 0, feedback: [] as string[], candidate: [] as Choice[] };
  const llm: Llm = {
    model: "goal-fixture",
    search: async () => { throw new Error("Unexpected search"); },
    cache: async (_kind, _input, run) => ({ value: await run(), hit: false }),
    structured: async (name, schema, system, payload) => {
      if (name === "akim_goal") {
        state.parses++;
        assert.equal(typeof (payload as { goal: string }).goal, "string");
        assert.ok(system.includes("baseline"));
        return schema.parse({ supported, constraints });
      }
      assert.equal(name, "akim_explanation");
      state.narratives++;
      assert.deepEqual((payload as { constraints: GoalConstraints }).constraints, constraints);
      assert.ok(system.includes("пожертвовать"));
      return schema.parse({ title: "Цель", strengths: "Резерв сохранён", risks: "Компромисс", why: "Приоритет транспорта" });
    },
    tools: async (input) => {
      const message = input.find((item) => "role" in item && item.role === "user");
      assert.ok(message && "content" in message && typeof message.content === "string");
      state.candidate = JSON.parse(message.content).candidate;
      assert.deepEqual(validateGoal(state.candidate, constraints), []);
      assert.ok(input.some((item) => "role" in item && item.role === "system" &&
        "content" in item && typeof item.content === "string" && item.content.includes(JSON.stringify(constraints))));
      for (const item of input)
        if (item.type === "function_call_output" && item.call_id?.endsWith("submit_plan")) {
          assert.equal(typeof item.output, "string");
          state.feedback.push(item.output as string);
        }
      const round = state.rounds++;
      const plan = round === 0 && rejected ? rejected : state.candidate;
      return {
        output: ["simulate", "ask_residents", "submit_plan"].map((name) => ({
          type: "function_call", name, call_id: `${round}-${name}`,
          arguments: JSON.stringify({ choices: plan.map((choice) => ({ ...choice, districtId: choice.districtId ?? null })) }),
        })),
      } as import("openai/resources/responses/responses").Response;
    },
  };
  return { llm, state };
}

test("goal request requires text or constraints and validates the complete constraint vocabulary", () => {
  assert.ok(akimRequest.safeParse({ mode: "goal", plan: [], goal: "Защитить Нуру" }).success);
  assert.ok(akimRequest.safeParse({ mode: "goal", plan: [], goal: "я".repeat(300) }).success);
  const defaults = akimRequest.parse({ mode: "goal", plan: [], constraints: {} }).constraints!;
  assert.deepEqual(defaults, { priorities: [], protectedDistricts: [], minSupportPercent: 0, reserveUnits: 0, mustInclude: [], mustExclude: [] });
  for (const extra of [{}, { goal: " " }, { goal: "я".repeat(301) }])
    assert.equal(akimRequest.safeParse({ mode: "goal", plan: [], ...extra }).success, false);
  for (const constraints of [
    { priorities: ["Финансы"] }, { protectedDistricts: ["unknown"] },
    { minSupportPercent: -1 }, { minSupportPercent: 101 }, { minSupportPercent: "50" },
    { reserveUnits: -1 }, { reserveUnits: 101 }, { reserveUnits: Infinity },
    { mustInclude: ["M15"] }, { mustExclude: ["M0"] }, { unexpected: true },
  ]) assert.equal(akimRequest.safeParse({ mode: "goal", plan: [], constraints }).success, false);
});

test("goal parses natural language, supplies a feasible candidate and returns a verified explanation", async () => {
  const { runAkim } = await import("../server/akim");
  const { constraintsInput } = await import("../server/schemas");
  const { validateGoal } = await import("../server/goal");
  const { simulate } = await import("../src/engine");
  const constraints = constraintsInput.parse({
    priorities: ["Транспорт"], protectedDistricts: ["nura", "esil"],
    minSupportPercent: 55, reserveUnits: 20, mustInclude: ["M1"], mustExclude: ["M5"],
  });
  const { llm, state } = await goalFixture(constraints);
  const events: import("../src/city-data").ActivityEvent[] = [];
  const result = await runAkim(llm, "goal", [], null, (event) => events.push(event), undefined, {
    goal: "Транспорт с автобусными полосами, без чистого топлива. Защитить Нуру и Есиль, резерв 20, поддержка 55%.",
  });
  assert.equal(state.parses, 1);
  assert.equal(state.rounds, 1);
  assert.equal(state.narratives, 1);
  assert.deepEqual(result.constraints, constraints);
  assert.deepEqual(validateGoal(result.plan, constraints), []);
  assert.deepEqual(result.result, simulate(result.plan).result);
  assert.equal(result.model, "goal-fixture");
  assert.equal(result.cached, false);
  assert.deepEqual(result.events, events);
});

test("goal rejects hard-constraint violations on submit and lets the model retry", async () => {
  const { runAkim } = await import("../server/akim");
  const { constraintsInput } = await import("../server/schemas");
  const { validateGoal } = await import("../server/goal");
  const constraints = constraintsInput.parse({
    priorities: ["Транспорт"], minSupportPercent: 55, reserveUnits: 20,
    mustInclude: ["M1"], mustExclude: ["M5"],
  });
  const { llm, state } = await goalFixture(constraints, samplePlan);
  const result = await runAkim(llm, "goal", samplePlan, null, () => {}, undefined, { constraints });
  assert.equal(state.parses, 0);
  assert.equal(state.rounds, 2);
  const feedback = JSON.parse(state.feedback[0]);
  assert.equal(feedback.accepted, undefined);
  for (const text of ["резерв", "Поддержка локальной модели", "Обязательная мера M1", "Мера M5 запрещена"])
    assert.ok(feedback.errors.some((error: string) => error.includes(text)), text);
  assert.deepEqual(validateGoal(result.plan, constraints), []);
  assert.notDeepEqual(result.plan, samplePlan);
});

test("goal rejects unrelated language before the tool loop with a helpful public 400", async () => {
  const { runAkim } = await import("../server/akim");
  const { constraintsInput } = await import("../server/schemas");
  const { llm, state } = await goalFixture(constraintsInput.parse({}), undefined, false);
  await assert.rejects(runAkim(llm, "goal", [], null, () => {}, undefined, { goal: "Напиши рецепт торта" }),
    (error: unknown) => error instanceof PublicError && error.status === 400 && error.message.includes("городских мер"));
  assert.equal(state.parses, 1);
  assert.equal(state.rounds, 0);
  assert.equal(state.narratives, 0);
});

test("goal protection compares actual district scores with the city baseline", async () => {
  const { validateGoal } = await import("../server/goal");
  const { constraintsInput } = await import("../server/schemas");
  const { measures } = await import("../src/data");
  const { baseline, projectEffects, validate } = await import("../src/engine");
  const plan: Choice[] = [
    { measureId: "M1", districtId: "esil" }, { measureId: "M2" },
    { measureId: "M8", districtId: "nura" }, { measureId: "M9", districtId: "nura" },
    { measureId: "M11", districtId: "nura" },
  ];
  const measure = measures.find((item) => item.id === "M11")!;
  const effects = measure.effects;
  try {
    measure.effects = { T1: -100 };
    assert.deepEqual(validate(plan), []);
    assert.ok(projectEffects(plan).districts.find((row) => row.id === "nura")!.score <
      baseline.districts.find((row) => row.id === "nura")!.score);
    assert.ok(validateGoal(plan, constraintsInput.parse({ protectedDistricts: ["nura"] }))
      .some((error) => error.includes("защищённого района Нура")));
    assert.deepEqual(validateGoal(plan, constraintsInput.parse({ protectedDistricts: ["esil"] })), []);
  } finally {
    measure.effects = effects;
  }
});

test("goal hard checks use exact local approval and units, including threshold boundaries", async () => {
  const { validateGoal } = await import("../server/goal");
  const { constraintsInput } = await import("../server/schemas");
  const { pollProposal } = await import("../src/residents");
  const approval = pollProposal(samplePlan, "").approval;
  assert.deepEqual(validateGoal(samplePlan, constraintsInput.parse({ minSupportPercent: approval, reserveUnits: 5 })), []);
  assert.ok(validateGoal(samplePlan, constraintsInput.parse({ minSupportPercent: approval + 0.01 }))
    .some((error) => error.includes("Поддержка")));
  assert.ok(validateGoal(samplePlan, constraintsInput.parse({ reserveUnits: 5.01 }))
    .some((error) => error.includes("резерв")));
  assert.ok(validateGoal(samplePlan.slice(0, 4), constraintsInput.parse({}))
    .some((error) => error.includes("ровно 5")));
});

test("goal without an OpenAI key runs entirely locally with deterministic constrained results", async () => {
  const { runAkim } = await import("../server/akim");
  const { validateGoal } = await import("../server/goal");
  const { constraintsInput } = await import("../server/schemas");
  const constraints = constraintsInput.parse({
    priorities: ["Соцсфера"], protectedDistricts: districts.map((district) => district.id),
    minSupportPercent: 50, reserveUnits: 20, mustInclude: ["M7"], mustExclude: ["M3"],
  });
  const first = await runAkim(null, "goal", [], null, () => {}, undefined, { constraints });
  const second = await runAkim(null, "goal", [], null, () => {}, undefined, { constraints });
  assert.equal(first.model, "local");
  assert.equal(first.cached, false);
  assert.equal(second.cached, false);
  assert.deepEqual(first.constraints, constraints);
  assert.deepEqual(validateGoal(first.plan, constraints), []);
  assert.deepEqual(first.plan, second.plan);
  assert.ok(first.events.some((event) => event.label === "Локальный поиск завершён"));
});

test("goal never silently relaxes impossible constraints or guesses text without a key", async () => {
  const { runAkim } = await import("../server/akim");
  for (const constraints of [
    { reserveUnits: 100 }, { minSupportPercent: 100 },
    { mustInclude: ["M1" as const, "M3" as const] },
    { mustInclude: ["M7" as const], mustExclude: ["M7" as const] },
  ]) await assert.rejects(runAkim(null, "goal", [], null, () => {}, undefined, { constraints }),
    (error: unknown) => error instanceof PublicError && error.status === 400);
  await assert.rejects(runAkim(null, "goal", [], null, () => {}, undefined, { goal: "Улучшить город" }),
    (error: unknown) => error instanceof PublicError && error.status === 503 && error.message.includes("constraints"));
});

test("goal cache reuses identical constraints but isolates different goals", async () => {
  const { runAkim } = await import("../server/akim");
  const { constraintsInput } = await import("../server/schemas");
  const { createCache, memoryStore } = await import("../server/storage");
  const cache = createCache(memoryStore());
  const firstConstraints = constraintsInput.parse({ reserveUnits: 5 });
  const first = await goalFixture(firstConstraints);
  first.llm.cache = cache;
  await runAkim(first.llm, "goal", [], null, () => {}, undefined, { constraints: firstConstraints });
  const cached = await runAkim(first.llm, "goal", [], null, () => {}, undefined, { constraints: firstConstraints });
  assert.equal(cached.cached, true);
  assert.equal(first.state.rounds, 1);
  const secondConstraints = constraintsInput.parse({ reserveUnits: 20 });
  const second = await goalFixture(secondConstraints);
  second.llm.cache = cache;
  const fresh = await runAkim(second.llm, "goal", [], null, () => {}, undefined, { constraints: secondConstraints });
  assert.equal(fresh.cached, false);
  assert.equal(second.state.rounds, 1);
  assert.deepEqual(fresh.constraints, secondConstraints);
});
