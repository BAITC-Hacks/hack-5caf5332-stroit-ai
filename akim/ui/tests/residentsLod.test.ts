import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildResidentsLod,
  residentCellColor,
  residentCellRadius,
  snapResidentPixel,
  RESIDENT_CLUSTER_CELL,
  RESIDENT_CLUSTER_MAX_RADIUS,
  type ResidentScreenPoint,
} from "../src/residentsLod";

const point = (id: number, x = 1, y = 1, vote: boolean | null = null): ResidentScreenPoint => ({
  id, x, y, vote, alpha: 0.95, highlighted: false,
});

test("LOD switches at 12.5 and 14 with and without a poll", () => {
  for (const vote of [null, false, true]) {
    const points = [point(2, 1, 1, vote), point(1, 2, 2, vote)];
    for (const zoom of [10, 12, 12.499]) {
      const lod = buildResidentsLod(zoom, points);
      assert.equal(lod.detail, "cluster");
      assert.equal(lod.cells.size, 1);
      assert.equal(lod.residents.length, 0);
    }
    for (const zoom of [12.5, 13, 13.999]) {
      const lod = buildResidentsLod(zoom, points);
      assert.equal(lod.detail, "sparse");
      assert.equal(lod.cells.size, 1);
      assert.equal(lod.cells.get("0:0")?.resident.id, 1);
    }
    for (const zoom of [14, 18]) {
      const lod = buildResidentsLod(zoom, points);
      assert.equal(lod.detail, "full");
      assert.equal(lod.cells.size, 0);
      assert.deepEqual(lod.residents, points);
    }
  }
});

test("sparse selection uses the lowest ID independently of order and small motion within a cell", () => {
  const points = [point(9), point(2, 7, 7), point(5, 8, 1), point(4, 15, 7)];
  const ids = (input: ResidentScreenPoint[]) =>
    [...buildResidentsLod(13, input).cells.values()].map((cell) => cell.resident.id).sort();
  assert.deepEqual(ids(points), [2, 4]);
  assert.deepEqual(ids([...points].reverse()), [2, 4]);
  assert.deepEqual(ids(points.map((p) => ({ ...p, x: p.x + 0.25, y: p.y + 0.25 }))), [2, 4]);
});

test("clusters aggregate poll share and opacity, with neutral color before a poll", () => {
  const lod = buildResidentsLod(12, [
    point(1, 1, 1, true), point(2, 2, 1, true), point(3, 3, 1, false),
    { ...point(4, 4, 1), alpha: 0.2 },
  ]);
  const cell = lod.cells.get("0:0")!;
  assert.equal(cell.count, 4);
  assert.equal(cell.yes, 2);
  assert.equal(cell.votes, 3);
  assert.ok(Math.abs(cell.alphaSum / cell.count - 0.7625) < 1e-10);
  assert.equal(residentCellColor(0, 0), "#3d5c4a");
  assert.equal(residentCellColor(0, 4), "rgb(216, 88, 74)");
  assert.equal(residentCellColor(4, 4), "rgb(95, 174, 63)");
  assert.equal(residentCellColor(2, 4), "rgb(156, 131, 69)");
  assert.equal(residentCellColor(cell.yes, cell.votes), "rgb(135, 145, 67)");
});

test("cluster circles stay separated across cell edges, including negative coordinates", () => {
  const lod = buildResidentsLod(12, [point(1, -0.01), point(2, 0), point(3, 11.99), point(4, 12)]);
  assert.equal(lod.cells.size, 3);
  assert.equal(lod.cells.get("0:0")?.count, 2);
  assert.equal(lod.cells.get("-1:0")?.x, -6);
  assert.equal(lod.cells.get("1:0")?.x, 18);
  assert.ok(residentCellRadius(1) < residentCellRadius(9));
  assert.equal(residentCellRadius(2000), RESIDENT_CLUSTER_MAX_RADIUS);
  for (const ratio of [1, 1.25, 1.5, 2]) {
    const radius = snapResidentPixel(residentCellRadius(2000), ratio);
    assert.ok(radius * 2 + 1 / ratio < RESIDENT_CLUSTER_CELL);
  }
});

test("highlighted resident survives every LOD and is excluded from ordinary draws", () => {
  const selected = { ...point(99), highlighted: true };
  for (const zoom of [12, 12.5, 14]) {
    const lod = buildResidentsLod(zoom, [point(1), selected]);
    assert.equal(lod.highlighted, selected);
    assert.ok(lod.residents.every((p) => p.id !== selected.id));
    for (const cell of lod.cells.values()) {
      assert.equal(cell.count, 1);
      assert.equal(cell.resident.id, 1);
    }
  }
});

test("binning consumes a single-pass stream and snapping uses whole device pixels", () => {
  let visits = 0;
  function* points() {
    for (let i = 0; i < 2000; i++) {
      visits++;
      yield point(i);
    }
  }
  const lod = buildResidentsLod(12, points());
  assert.equal(visits, 2000);
  assert.equal(lod.cells.get("0:0")?.count, 2000);
  for (const ratio of [1, 1.25, 1.5, 2]) {
    for (const value of [-2.7, 0, 1.2, 3.5, 101.75]) {
      const snapped = snapResidentPixel(value, ratio);
      assert.equal(snapped * ratio, Math.round(value * ratio));
      assert.ok(Math.abs(snapped - value) <= 0.5 / ratio + 1e-12);
    }
  }
});
