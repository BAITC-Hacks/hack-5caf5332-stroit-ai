import { test } from "node:test";
import assert from "node:assert/strict";
import { samplePlan, type Choice } from "../src/data";
import { autopilot, baseline, budget, simulate } from "../src/engine";
import { pollProposal } from "../src/residents";
import { parseVariants, serializeVariants } from "../src/game/variants";
import {
  blockReason,
  contributions,
  comparePlans,
  criticalCells,
  decodePlan,
  encodePlan,
  explain,
  goals,
  fmt,
  previewGain,
} from "../src/planner/analysis";

test("budget follows file.md: 100 units, sample costs 95, spec overspend is rejected", () => {
  assert.equal(budget(samplePlan), 95);
  const over: Choice[] = [
    { measureId: "M7", districtId: "nura" },
    { measureId: "M8", districtId: "nura" },
    { measureId: "M5", districtId: "saryarka" },
    { measureId: "M2" },
    { measureId: "M14" },
  ];
  assert.equal(budget(over), 107);
  assert.equal(simulate(over).result, null);
});

test("comparison: file.md example versus autopilot uses exact engine values", () => {
  const best = autopilot();
  const result = comparePlans(samplePlan, best);
  assert.ok(Math.abs(result.metrics.score.current - 56.54307) < 1e-9);
  assert.equal(fmt(result.metrics.score.variant), "57,21");
  assert.ok(Math.abs(result.metrics.score.delta + 0.66249) < 1e-9);
  assert.deepEqual(result.metrics.budget, { current: 95, variant: 100, delta: -5 });
  assert.deepEqual(result.metrics.goals, { current: 4, variant: 4, delta: 0 });
  assert.equal(result.metrics.support.current, pollProposal(samplePlan, "").approval);
  assert.equal(result.metrics.support.variant, pollProposal(best, "").approval);
  // Minimum cell is 40, not the weakest district's composite score.
  assert.deepEqual(result.metrics.minimum, { current: 40, variant: 40, delta: 0 });
  const nura = result.districts.find((d) => d.district === "nura")!;
  assert.equal(nura.directions.find((d) => d.direction === "Транспорт")!.delta, -9);
  assert.match(result.conclusion, /Текущий план хуже на 0,66/);
});

test("comparison: reversing scenarios reverses deltas and generates the tradeoff", () => {
  const best = autopilot();
  const forward = comparePlans(best, samplePlan);
  const reverse = comparePlans(samplePlan, best);
  for (const key of Object.keys(forward.metrics) as (keyof typeof forward.metrics)[]) {
    assert.ok(Math.abs(forward.metrics[key].delta + reverse.metrics[key].delta) < 1e-9);
  }
  assert.equal(forward.conclusion, "Текущий план лучше на +0,66: сильнее в транспорте Нуры, слабее в экологии Сарыарки.");
  assert.deepEqual(comparePlans(best, samplePlan), forward);
});

test("comparison: identical and reordered plans tie without mutating inputs", () => {
  const before = structuredClone(samplePlan);
  const reversed = [...samplePlan].reverse();
  const result = comparePlans(samplePlan, reversed);
  assert.ok(Object.values(result.metrics).every((v) => v.delta === 0));
  assert.ok(result.districts.every((r) => r.score.delta === 0 && r.directions.every((d) => d.delta === 0)));
  assert.match(result.conclusion, /показатели районов совпадают/);
  assert.deepEqual(samplePlan, before);
  assert.deepEqual(reversed, [...before].reverse());
});

test("comparison: invalid and incomplete plans never receive a score", () => {
  assert.throws(() => comparePlans([], samplePlan), /ровно 5/);
  assert.throws(() => comparePlans(samplePlan, [...samplePlan, { measureId: "M14" }]), /Нельзя сравнить план/);
  assert.throws(() => comparePlans([{ measureId: "unknown" }, ...samplePlan.slice(1)], samplePlan), /Неизвестная мера/);
});

test("comparison: both scenarios use the same optional priorities", () => {
  const result = comparePlans(autopilot(), samplePlan, ["Транспорт"]);
  assert.equal(result.goalCount, 5);
  assert.deepEqual(result.metrics.goals, { current: 5, variant: 4, delta: 1 });
});

test("variants: storage round-trips snapshots and rejects corrupt, incomplete and duplicate entries", () => {
  const variants = [{ id: "A", name: "Социальный план", plan: samplePlan }];
  assert.deepEqual(parseVariants(serializeVariants(variants)), variants);
  assert.deepEqual(parseVariants("not json"), []);
  assert.deepEqual(parseVariants('{"id":"A"}'), []);
  const entry = { id: "A", name: "Вариант A", plan: encodePlan(samplePlan) };
  const stored = parseVariants(JSON.stringify([
    null, { ...entry, plan: "M12" }, { ...entry, plan: entry.plan + ",M99" },
    entry, entry, { ...entry, id: "B" }, { ...entry, id: "C" }, { ...entry, id: "D" },
  ]));
  assert.deepEqual(stored.map((v) => v.id), ["A", "B", "C"]);
});

test("baseline has two critical cells, both in Nura", () => {
  const cells = criticalCells(baseline);
  assert.deepEqual(
    cells.map((c) => `${c.district}.${c.indicator}`),
    ["nura.S1", "nura.S2"],
  );
});

test("sample plan meets every goal and explains strengths, risks and consequences", () => {
  const list = goals(samplePlan, []);
  assert.ok(list.every((g) => g.met), JSON.stringify(list));
  const brief = explain(samplePlan, ["Транспорт"]);
  assert.ok(brief.strengths.some((s) => s.includes("M10 + M12")));
  assert.ok(brief.risks.length > 0);
  assert.ok(brief.consequences.some((s) => s.includes("транспорт")));
});

test("contributions and previews are computed by the engine", () => {
  const parts = contributions(samplePlan);
  assert.equal(parts.length, 5);
  assert.equal(parts[0].choice.measureId, "M7");
  assert.ok(previewGain([], { measureId: "M7", districtId: "nura" }) > 0);
  assert.match(blockReason([{ measureId: "M1", districtId: "esil" }], { measureId: "M3", districtId: "esil" })!, /M1 и M3/);
});

test("scenario link round-trips and rejects invalid plans", () => {
  assert.deepEqual(decodePlan(encodePlan(samplePlan)), samplePlan);
  assert.deepEqual(decodePlan("M1.esil,M3.nura"), []);
  assert.deepEqual(decodePlan("M99,M12.nura"), [{ measureId: "M12" }]);
});


test("explanation acknowledges cross-direction effects instead of claiming missing sectors cannot improve", () => {
  const plan = [{ measureId: "M7", districtId: "nura" }, { measureId: "M3", districtId: "nura" }, { measureId: "M2" }, { measureId: "M12" }, { measureId: "M11", districtId: "nura" }] as import("../src/data").Choice[];
  const brief = explain(plan, ["Экология"]);
  assert.ok(brief.consequences.some(text => text.includes("за счёт мер других направлений")));
  assert.ok(!brief.consequences.some(text => text.includes("Эти показатели не изменятся")));
});
