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
  assert.equal(poll.cost, 20700);
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
