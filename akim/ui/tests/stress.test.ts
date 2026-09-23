import { test } from "node:test";
import assert from "node:assert/strict";
import { samplePlan, type Choice } from "../src/data";
import { projectEffects, baseline } from "../src/engine";
import { stressTest } from "../src/planner/stress";
const near = (a: number, b: number) => assert.ok(Math.abs(a-b) < 1e-8, `${a} != ${b}`);
test("flood affects only declared cells and recomputes threshold penalties without mutating the plan", () => {
  const input = structuredClone(samplePlan), base = projectEffects(input), t = stressTest(input, "flood");
  assert.deepEqual(input, samplePlan);
  assert.deepEqual(t.normal, base);
  assert.deepEqual(t.result!.districts[0], base.districts[0]);
  near(t.result!.districts[4].values.T1, base.districts[4].values.T1-12);
  near(t.result!.districts[2].values.C1, base.districts[2].values.C1-14);
  assert.equal(t.result!.critical, 2);
  const rows = t.result!.districts;
  near(t.result!.score, 0.7*t.result!.average + 0.3*Math.min(...rows.map(r => r.score))-2);
  assert.deepEqual(stressTest([...input].reverse(), "flood").result, t.result);
});
test("heat shock is limited to Almaty and Saryarka and contributions use the shocked counterfactual", () => {
  const t = stressTest(samplePlan, "heat");
  assert.deepEqual(t.result!.districts[4], t.normal.districts[4]);
  near(t.result!.districts[1].values.C1, t.normal.districts[1].values.C1-20);
  for (const row of t.measures) {
    near(row.stressed!, t.result!.score-projectEffects(samplePlan.filter(c => c.measureId !== row.choice.measureId), t.event.shock).score);
  }
});
test("20 percent inflation invalidates a 95-unit plan without producing a score or auto-removing measures", () => {
  const t = stressTest(samplePlan, "prices");
  assert.equal(t.cost, 114); assert.equal(t.deficit, 14); assert.equal(t.result, null);
  assert.equal(t.measures.length, 5); assert.ok(t.measures.every(m => m.stressed === null));
});
test("a funded plan keeps its effects under inflation; all scores use the original engine", () => {
  const cheap: Choice[] = [{ measureId: "M9", districtId: "nura" }, { measureId: "M11", districtId: "esil" }, { measureId: "M10", districtId: "nura" }, { measureId: "M12" }, { measureId: "M4", districtId: "saryarka" }];
  const t = stressTest(cheap, "prices");
  near(t.cost, 73.2); assert.equal(t.deficit, 0);
  assert.deepEqual(t.result, projectEffects(cheap)); assert.deepEqual(t.withoutPlan, baseline);
});
test("incomplete plans remain invalid and shock calculations clip at zero and one hundred", () => {
  assert.throws(() => stressTest([], "flood"));
  const p = projectEffects([], { nura: { T1: -1000, T2: 1000 } });
  assert.equal(p.districts[4].values.T1, 0); assert.equal(p.districts[4].values.T2, 100);
});
