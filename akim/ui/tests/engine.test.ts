import { test } from "node:test";
import assert from "node:assert/strict";
import {
  baseline,
  simulate,
  validate,
  projectEffects,
  advise,
  autopilot,
  budget,
} from "../src/engine";
import { samplePlan, weights, districts, type Choice } from "../src/data";
import { askCity, examples, pollProposal } from "../src/residents";
const near = (actual: number, expected: number) =>
  assert.ok(Math.abs(actual - expected) < 1e-8, `${actual} ≠ ${expected}`);
test("baseline reproduces all five district scores and strict critical threshold", () => {
  near(
    Object.values(weights).reduce((a, b) => a + b),
    1,
  );
  near(
    districts.reduce((s, d) => s + d.population, 0),
    1,
  );
  [62.99, 57.06, 54.65, 56.63, 49.18].forEach((score, i) =>
    near(baseline.districts[i].score, score),
  );
  near(baseline.average, 56.8624);
  near(baseline.score, 52.55768);
  assert.equal(baseline.critical, 2);
});
test("sample includes lag and synergy, costs 95 and scores 56.54307", () => {
  const { errors, result } = simulate(samplePlan);
  assert.deepEqual(errors, []);
  assert.ok(result);
  assert.equal(budget(samplePlan), 95);
  near(result.score, 56.54307);
  assert.equal(result.critical, 0);
  const nura = result.districts.find((d) => d.id === "nura")!;
  near(nura.values.S1, 48);
  near(nura.values.S2, 43.75);
  near(nura.values.B1, 67.5);
  near(nura.values.C2, 54.375);
  near(result.districts[2].values.E2, 48.75);
});
test("score is absent for empty, incomplete, too long, unknown, duplicate and over-budget plans", () => {
  const invalid: Choice[][] = [
    [],
    samplePlan.slice(0, 4),
    [...samplePlan, { measureId: "M14" }],
    samplePlan.map((c, i) => (i === 0 ? { measureId: "bad" } : c)),
    samplePlan.map((c, i) => (i === 0 ? samplePlan[1] : c)),
    [
      { measureId: "M3", districtId: "esil" },
      { measureId: "M5", districtId: "saryarka" },
      { measureId: "M7", districtId: "nura" },
      { measureId: "M13", districtId: "almaty" },
      { measureId: "M10", districtId: "nura" },
    ],
  ];
  for (const p of invalid) {
    assert.equal(simulate(p).result, null);
    assert.ok(validate(p).length);
  }
  assert.match(validate(invalid.at(-1)!).join(" "), /Бюджет превышен/);
});
test("district is required only for district measures and must be known", () => {
  assert.match(
    validate([{ measureId: "M7" }], true).join(" "),
    /выберите район/,
  );
  assert.match(
    validate([{ measureId: "M7", districtId: "invalid" as "nura" }], true).join(
      " ",
    ),
    /выберите район/,
  );
  assert.match(
    validate([{ measureId: "M12", districtId: "nura" }], true).join(" "),
    /без района/,
  );
  assert.deepEqual(validate([{ measureId: "M12" }], true), []);
});
test("direction cap permits exactly five measures across three directions", () => {
  const three: Choice[] = [
    { measureId: "M9", districtId: "nura" },
    { measureId: "M7", districtId: "nura" },
    { measureId: "M10", districtId: "nura" },
    { measureId: "M11", districtId: "esil" },
    { measureId: "M12" },
  ];
  assert.deepEqual(validate(three), []);
  assert.ok(simulate(three).result);
  assert.match(
    validate(
      [
        { measureId: "M7", districtId: "nura" },
        { measureId: "M8", districtId: "nura" },
        { measureId: "M9", districtId: "nura" },
      ],
      true,
    ).join(" "),
    /не более 2/,
  );
});
test("BRT and LRT conflict globally; land and utility conflicts are district-local", () => {
  assert.match(
    validate(
      [
        { measureId: "M1", districtId: "almaty" },
        { measureId: "M3", districtId: "esil" },
      ],
      true,
    ).join(" "),
    /M1 и M3/,
  );
  for (const [a, b] of [
    ["M4", "M7"],
    ["M5", "M13"],
  ]) {
    assert.ok(
      validate(
        [
          { measureId: a, districtId: "nura" },
          { measureId: b, districtId: "nura" },
        ],
        true,
      ).length,
    );
    assert.deepEqual(
      validate(
        [
          { measureId: a, districtId: "nura" },
          { measureId: b, districtId: "esil" },
        ],
        true,
      ),
      [],
    );
  }
});
test("all fixed synergies apply at first measure district, without scaling lag", () => {
  const cases = [
    {
      plan: [{ measureId: "M1", districtId: "nura" }, { measureId: "M2" }],
      key: "T1",
      expected: 9.5,
    },
    {
      plan: [{ measureId: "M10", districtId: "nura" }, { measureId: "M12" }],
      key: "B1",
      expected: 12.5,
    },
    {
      plan: [{ measureId: "M5", districtId: "nura" }, { measureId: "M6" }],
      key: "E2",
      expected: 12.25,
    },
  ] as const;
  for (const c of cases) {
    const result = projectEffects([...c.plan]);
    near(result.districts[4].delta[c.key], c.expected);
  }
});
test("measure order does not change scores or resident responses", () => {
  near(
    simulate([...samplePlan].reverse()).result!.score,
    simulate(samplePlan).result!.score,
  );
  assert.deepEqual(
    pollProposal(samplePlan, "test"),
    pollProposal([...samplePlan].reverse(), "test"),
  );
});
test("negative transport effect creates an extra penalty strictly below 40", () => {
  const p = projectEffects([{ measureId: "M11", districtId: "almaty" }]);
  near(p.districts[1].values.T1, 38.25);
  assert.equal(p.critical, 3);
});
test("advisor offers a valid concrete improvement and does not mutate input", () => {
  const input = structuredClone(samplePlan);
  const recommendation = advise(input)!;
  assert.deepEqual(input, samplePlan);
  assert.deepEqual(validate(recommendation.plan), []);
  assert.ok(recommendation.improvement > 0);
  assert.equal(recommendation.removed.measureId, "M5");
  assert.equal(recommendation.added.measureId, "M3");
  near(recommendation.result.score, 57.20556);
  assert.equal(advise([]), null);
});
test("autopilot is deterministic, valid, bounded by budget, and independent from callers", () => {
  const first = autopilot();
  assert.deepEqual(validate(first), []);
  assert.ok(budget(first) <= 100);
  assert.deepEqual(autopilot(), first);
  first[0].measureId = "invalid";
  assert.deepEqual(validate(autopilot()), []);
});
test("poll resolver supports examples, tradeoffs and valid current plan with repeatable output", () => {
  for (const question of examples) {
    const a = askCity(question, samplePlan);
    assert.equal(a.error, null);
    assert.ok(a.poll);
    assert.deepEqual(a, askCity(question, samplePlan));
    assert.equal(
      a.poll.districts.reduce((s, d) => s + d.total, 0),
      2000,
    );
    near(a.poll.approval, a.poll.districts.reduce((s, d) => s + d.yes, 0) / 20);
  }
  assert.ok(askCity(examples[1], samplePlan).poll?.comparison);
  assert.equal(askCity("Will it rain tomorrow?", samplePlan).poll, null);
  assert.ok(askCity(examples[2], []).error);
});
