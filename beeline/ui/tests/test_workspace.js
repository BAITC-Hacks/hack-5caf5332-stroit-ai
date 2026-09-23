/* Offline regression checks: real audit fixture, minimal DOM, no listening ports. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "..");
const fixture = JSON.parse(fs.readFileSync(path.join(root, "docs/run.example.json")));
const snapshot = JSON.stringify(fixture);
const cells = [...new Map(fixture.audit.candidates.filter(c => !c.members?.length)
  .map(c => [c.cell, { id: c.cell, current: c.current, arpu: c.arpu, count: 100, average: 1000 }])).values()];
const fixtureData = {
  rows: cells.length * 100, baseline: 100000, history_rows: 1000, cells,
  quality: { duplicate_ids: 0, missing_values: 0 }, data_hashes: fixture.data_hashes,
};
const nodes = new Map();
function node(selector) {
  if (!nodes.has(selector)) nodes.set(selector, {
    innerHTML: "", textContent: "", open: false, isConnected: true,
    classList: { add() {} }, addEventListener() {}, focus() {},
    showModal() { this.open = true; }, close() { this.open = false; },
    querySelectorAll() { return []; },
  });
  return nodes.get(selector);
}
const events = {}, windowEvents = {}, requests = [], timers = new Map();
let timerId = 0, route;
const context = vm.createContext({
  fixture, fixtureData, URLSearchParams, Intl, AbortSignal,
  document: {
    querySelector: node, querySelectorAll: () => [], activeElement: node("trigger"),
    addEventListener: (name, handler) => { events[name] = handler; },
  },
  location: { search: "" }, history: { pushState() {}, replaceState() {} },
  addEventListener: (name, handler) => { windowEvents[name] = handler; },
  setTimeout: callback => { timers.set(++timerId, callback); return timerId; },
  clearTimeout: id => timers.delete(id),
  fetch: async (url, options) => {
    requests.push({ url, options });
    return { ok: true, json: async () => route(url, options) };
  },
});
const source = fs.readFileSync(path.join(root, "src/workspace.js"), "utf8");
vm.runInContext(source.replace(/boot\(\);\s*$/, ""), context);
const evaluate = code => vm.runInContext(code, context);
const reset = () => evaluate(`result = fixture; data = fixtureData; loading = false;
  busy = false; apiError = ''; jobError = false; runNotice = ''; awaitingResult = false;
  params = new URLSearchParams();`);
async function tick() {
  assert.equal(timers.size, 1, "Only one polling timer should be active");
  const [id, callback] = timers.entries().next().value;
  timers.delete(id);
  await callback();
}
async function checks() {
  reset();
  for (const screen of ["audience", "pilots", "plan"]) {
    evaluate(`params.set('screen', '${screen}'); render();`);
    assert.match(node("#main").innerHTML, /<h1>/);
    assert.doesNotMatch(node("#main").innerHTML, /mock|evaluator|NaN|undefined/);
  }
  for (const c of fixture.audit.candidates.filter(c => c.selected)) {
    evaluate(`detail(${JSON.stringify(c.id)}, false)`);
    const html = node("#dialog-content").innerHTML;
    assert.match(html, /Оценка эффекта/);
    assert.doesNotMatch(html, /20%|Среднее по пилотам|NaN|undefined/);
    assert.ok(html.includes(fixture.audit.uncertainty));
    if (c.basis !== "pilots") {
      assert.match(html, /history-estimate/);
      assert.match(html, /оценка по истории, пилотов не было/);
      assert.match(html, /калибровкой по пилотам других гипотез/);
    }
    if (c.members?.length) {
      assert.equal((html.match(/class="alternative-group"/g) || []).length, c.members.length);
      for (const id of c.members) {
        const member = fixture.audit.candidates.find(m => m.id === id);
        assert.ok(html.includes(`<h4>${member.current} · ${member.arpu}</h4>`));
      }
    }
  }
  // The example's merged campaigns have no pilots: add observations on two members
  // to exercise the reported bug, including repeated observations and an outsider.
  const merged = fixture.audit.candidates.find(c => c.members?.length > 1);
  const testResult = structuredClone(fixture);
  const pilot = fixture.audit.pilots[0];
  testResult.audit.pilots.push(
    { ...pilot, candidate: merged.members[0], result: { ...pilot.result, pilot: "member-first" } },
    { ...pilot, candidate: merged.members[1], result: { ...pilot.result, pilot: "member-second" } },
    { ...pilot, candidate: merged.members[0], result: { ...pilot.result, pilot: "member-repeat" } },
    { ...pilot, candidate: "outsider", result: { ...pilot.result, pilot: "outside-pilot" } },
  );
  testResult.audit.uncertainty = '<unsafe>Текст агента & условия</unsafe>';
  context.testResult = testResult;
  evaluate(`result = testResult; detail(${JSON.stringify(merged.id)}, false)`);
  const detail = node("#dialog-content").innerHTML;
  for (const label of ["member-first", "member-second", "member-repeat"]) assert.ok(detail.includes(label));
  assert.ok(!detail.includes("outside-pilot"));
  assert.match(detail, /&lt;unsafe&gt;Текст агента &amp; условия&lt;\/unsafe&gt;/);
  evaluate(`result = {...testResult, audit: {...testResult.audit, uncertainty: null}};
    detail(${JSON.stringify(merged.id)}, false)`);
  assert.match(node("#dialog-content").innerHTML, /подробные допущения в аудите не указаны/);
  // No history estimate can receive the green evidence class, even with mean > SE.
  assert.doesNotMatch(evaluate('effectStatus({basis:"prior+calibration",mean:0.5,se:0.1,pilot_count:0})'), /has-evidence/);
  assert.match(evaluate('effectStatus({mean:0.5,se:0.1,pilot_count:2})'), /has-evidence/);
  reset();
  const status = evaluate('cellStatuses()');
  const planned = new Set(fixture.audit.plan.flatMap(p => {
    const c = fixture.audit.candidates.find(c => c.id === p.candidate);
    return c.members ? c.members.map(id => fixture.audit.candidates.find(c => c.id === id).cell) : [c.cell];
  }));
  const tested = new Set(fixture.audit.pilots.map(p => fixture.audit.candidates.find(c => c.id === p.candidate).cell));
  const statuses = new Set();
  for (const cell of cells) {
    const expected = planned.has(cell.id) ? "в плане" : tested.has(cell.id) ? "проверена" : "не проверялась";
    assert.equal(status(cell.id), expected);
    statuses.add(expected);
  }
  assert.equal(statuses.size, 3);
  evaluate('renderSegments()');
  assert.match(node("#segment-results").innerHTML, /<th scope="col">Статус<\/th>/);
  assert.match(node("#segment-results").innerHTML, /data-label="Статус"/);
  assert.match(node("#segment-results").innerHTML, /class="is-planned"/);
  assert.equal((node("#segment-results").innerHTML.match(/<tr role="row" class=/g) || []).length, 12);
  events.input({ target: { id: "segment-search", value: "tariff_13" } });
  assert.equal(evaluate('params.get("q")'), "tariff_13");
  events.change({ target: { id: "arpu-filter", value: "LOW" } });
  assert.equal(evaluate('params.get("arpu")'), "LOW");
  assert.equal((node("#segment-results").innerHTML.match(/<tr role="row" class=/g) || []).length, 1);
  assert.match(node("#segment-results").innerHTML, /tariff_13/);
  context.location.search = '?screen=audience&q=tariff_13&arpu=LOW&page=1';
  windowEvents.popstate();
  assert.equal(evaluate('params.get("q")'), "tariff_13");
  assert.equal(evaluate('params.get("arpu")'), "LOW");
  evaluate('url({q:null, arpu:null, page:"2"}); renderSegments()');
  assert.match(node("#segment-results").innerHTML, /2 \/ /);
  evaluate('url({q:"absent",page:null}); renderSegments()');
  assert.match(node("#segment-results").innerHTML, /Таких сегментов нет/);
  reset();
  evaluate('result = null; renderSegments()');
  assert.match(node("#segment-results").innerHTML, /не проверялась/);
  assert.doesNotMatch(node("#segment-results").innerHTML, /class="is-planned"/);
  reset();
  const fresh = { ...fixture, run_id: "new-run-123456", created_at: 0 };
  let statusValue = "running";
  route = url => ({
    "/api/run": { status: "running" }, "/api/status": { status: statusValue },
    "/api/result": fresh, "/api/data": fixtureData, "/api/benchmark": { runs: [] },
  })[url];
  await evaluate('run()');
  assert.equal(requests[0].options.method, "POST");
  assert.equal(evaluate('busy'), true);
  assert.equal(evaluate('runNotice'), "");
  await tick();
  assert.equal(evaluate('busy'), true);
  evaluate('params.set("screen", "plan"); render()');
  statusValue = "complete";
  await tick();
  assert.equal(evaluate('busy'), false);
  assert.equal(timers.size, 0);
  assert.match(node("#main").innerHTML, /План обновлён, прогон new-run-, \d\d:\d\d/);
  assert.match(node("#announcer").textContent, /План обновлён, прогон new-run-/);
  // Starting another run removes stale confirmation; failed polling can recover via boot.
  await evaluate('run()');
  assert.equal(evaluate('runNotice'), "");
  route = () => { throw new Error("connection lost"); };
  await tick();
  assert.equal(evaluate('apiError'), "poll");
  route = url => ({
    "/api/status": { status: "complete" }, "/api/result": { ...fresh, run_id: "recovered-run" },
    "/api/data": fixtureData, "/api/benchmark": { runs: [] },
  })[url];
  await evaluate('boot()');
  assert.match(node("#main").innerHTML, /План обновлён, прогон recovere/);
  assert.equal(JSON.stringify(fixture), snapshot, "Render must not mutate the audit");
  console.log("PASS: three screens; merged observations and alternatives; history estimates; uncertainty escaping/fallback; all cell statuses; search/filter/pagination/URL; POST/polling/confirmation/recovery.");
}
checks().catch(error => { console.error(error); process.exitCode = 1; });
