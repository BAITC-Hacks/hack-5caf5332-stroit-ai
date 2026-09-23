import { test } from "node:test";
import assert from "node:assert/strict";
import {
  population,
  generatePopulation,
  inside,
  residentState,
  activityCounts,
  cohortSize,
} from "../src/population";
import { districts } from "../src/data";
test("2000 reproducible residents form the same 30 cohorts as the polls", () => {
  assert.equal(population.length, 2000);
  assert.deepEqual(generatePopulation(), population);
  assert.equal(new Set(population.map((p) => p.id)).size, 2000);
  for (const d of districts)
    assert.equal(
      Array.from({ length: 6 }, (_, i) => cohortSize(d.id, i)).reduce(
        (a, b) => a + b,
      ),
      Math.round(d.population * 2000),
    );
});
test("residents travel along continuous routes inside their synthetic district and return home", () => {
  for (const p of population) {
    const polygon = districts[p.districtIndex].polygon;
    for (const route of [p.toWork, p.toLeisure, p.toHome])
      for (let i = 0; i < route.length; i++) {
        assert.ok(inside(...route[i], polygon));
        if (i)
          assert.equal(
            Math.abs(route[i][0] - route[i - 1][0]) +
              Math.abs(route[i][1] - route[i - 1][1]),
            16,
          );
      }
    assert.deepEqual(residentState(p, 0).point, p.home);
    assert.deepEqual(residentState(p, 600).point, p.work);
    assert.deepEqual(residentState(p, 1200).point, p.leisure);
    assert.deepEqual(residentState(p, 1400).point, p.home);
    assert.deepEqual(residentState(p, 1200, true).point, p.home);
    assert.equal(residentState(p, 480 + p.offset).moving, true);
    assert.deepEqual(residentState(p, 600 + 1440), residentState(p, 600));
  }
  assert.equal(activityCounts(500).moving, 2000);
  assert.equal(activityCounts(0).home, 2000);
});
