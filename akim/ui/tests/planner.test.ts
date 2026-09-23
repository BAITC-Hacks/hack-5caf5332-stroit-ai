import { test } from "node:test";
import assert from "node:assert/strict";
import { samplePlan, type Choice } from "../src/data";
import { baseline, budget, simulate } from "../src/engine";
import {
  blockReason,
  contributions,
  criticalCells,
  decodePlan,
  encodePlan,
  explain,
  goals,
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
