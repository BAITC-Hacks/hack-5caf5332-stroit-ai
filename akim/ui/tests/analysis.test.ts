import { test } from "node:test";
import assert from "node:assert/strict";
import { compareMobility, shortestRoute, mobilityState } from "../src/mobility";
import { AGENTS, population } from "../src/population";
import streets from "../src/astana-roads.json" with { type: "json" };
import { jevQuestions, parseJev, classifyComplaints } from "../server/jev";
import { locationCandidates } from "../server/locations";
import { verifiedPress, complaintRequest } from "../server/complaints";
import type { ThreadEvidence } from "../src/threads";
const post: ThreadEvidence = {
  url: "https://www.threads.com/@test/post/fixture",
  title: "Synthetic fixture",
  summary: "В Астане на улице А. Бектурова нет проезда для автобусов.",
  stance: "complaint",
  scope: "street",
  publishedAt: null,
};
test("routing changes when an alternative becomes cheaper", () => {
  const edges = [
    [1, 2],
    [0, 3],
    [0, 3],
    [1, 2],
  ];
  assert.deepEqual(
    shortestRoute(0, 3, edges, [
      [1, 4],
      [1, 1],
      [4, 4],
      [1, 4],
    ]),
    [0, 1, 3],
  );
  assert.deepEqual(
    shortestRoute(0, 3, edges, [
      [8, 4],
      [8, 8],
      [4, 4],
      [8, 4],
    ]),
    [0, 2, 3],
  );
});
test("same demand is compared; non-transport policies have no invented mobility impact", () => {
  const noTransport = compareMobility([
    { measureId: "M4", districtId: "nura" },
  ]);
  assert.deepEqual(noTransport.before, noTransport.after);
  const result = compareMobility([{ measureId: "M1", districtId: "saryarka" }]);
  assert.equal(result.before.trips.length, AGENTS);
  assert.equal(result.after.trips.length, AGENTS);
  assert.ok(result.after.metrics.carShare < result.before.metrics.carShare);
  assert.deepEqual(result.before.districts.nura, result.after.districts.nura);
  assert.ok(result.changedRoutes > 0);
  for (const p of population) {
    const trip = result.after.trips[p.id],
      graph = streets[p.districtId];
    assert.ok(Number.isFinite(trip.minutes) && trip.minutes >= 0);
    assert.deepEqual(graph.points[trip.route[0]], p.home);
    assert.deepEqual(graph.points[trip.route.at(-1)!], p.work);
    for (let i = 1; i < trip.route.length; i++)
      assert.ok(graph.edges[trip.route[i - 1]].includes(trip.route[i]));
    assert.deepEqual(mobilityState(p, 455, trip).point, p.home);
    assert.deepEqual(
      mobilityState(p, 460 + p.offset + trip.minutes + 1, trip).point,
      p.work,
    );
  }
});
function answers() {
  const { questions, locations } = jevQuestions([post]);
  const result: Record<string, unknown> = {};
  for (const key of Object.keys(questions))
    result[key] = key.endsWith("_location")
      ? {
          type: "choice",
          choice: locations[0][0].id,
          confidence: 0.92,
          probabilities: { [locations[0][0].id]: 0.96, unlocated: 0.04 },
        }
      : {
          type: "noul",
          noul:
            key.endsWith("direction_0") ||
            key.endsWith("_city") ||
            key.endsWith("_complaint")
              ? 0.95
              : 0.05,
        };
  return { response: { model: "jev-fixture", answers: result }, locations };
}
test("Jev gates city relevance, complaint relevance, categories and geolocation independently", () => {
  const { response, locations } = answers();
  const classified = parseJev(response, [post], locations).posts[0];
  assert.deepEqual(classified.directions, ["Транспорт"]);
  assert.equal(classified.decision, "accepted");
  assert.ok(classified.location?.name.includes("Бектуров"));
  response.answers["0_city"] = { type: "noul", noul: 0.1 };
  assert.equal(
    parseJev(response, [post], locations).posts[0].decision,
    "excluded",
  );
  assert.equal(parseJev(response, [post], locations).posts[0].location, null);
  response.answers["0_city"] = { type: "noul", noul: 0.6 };
  assert.equal(
    parseJev(response, [post], locations).posts[0].decision,
    "review",
  );
  delete response.answers["0_complaint"];
  assert.throws(() => parseJev(response, [post], locations));
});
test("unknown or ambiguous places stay unlocated; shortened street names resolve locally", () => {
  assert.ok(locationCandidates("Астана улица А. Бектурова").length > 0);
  assert.equal(
    locationCandidates("Астана улица А. Бектурова, проезд закрыт").length,
    1,
  );
  assert.equal(locationCandidates("В Астане закрыт проезд").length, 0);
  assert.ok(
    locationCandidates("Астана Сыганак и Толе би").some((l) =>
      /Толе|Төле/.test(l.name),
    ),
  );
  assert.equal(locationCandidates("Астана: автобусы опаздывают").length, 0);
  const { response, locations } = answers();
  response.answers["0_location"] = {
    type: "choice",
    choice: "unlocated",
    confidence: 0.9,
    probabilities: { unlocated: 0.95 },
  };
  assert.equal(parseJev(response, [post], locations).posts[0].location, null);
  response.answers["0_location"] = {
    type: "choice",
    choice: "invented-place",
    confidence: 0.99,
    probabilities: { "invented-place": 0.99 },
  };
  assert.throws(() => parseJev(response, [post], locations));
});
test("Jev failures expose no key and never silently accept evidence", async () => {
  let endpoint = "";
  const fake: typeof fetch = async (input, options) => {
    endpoint = String(input);
    assert.equal(
      new Headers(options?.headers).get("Authorization"),
      "Bearer fixture-secret",
    );
    return new Response("", { status: 401 });
  };
  await assert.rejects(
    classifyComplaints("fixture-secret", [post], undefined, fake),
    (e) => e instanceof Error && !e.message.includes("fixture-secret"),
  );
  assert.equal(endpoint, "https://api.typesafe.ai/v1/systemone");
});
test("secondary evidence must have an actual allowed search source and is labeled press", () => {
  const url = "https://informburo.kz/novosti/fixture";
  const item = {
    sourceUrl: url,
    summary: "Synthetic fixture",
    mentionsThreads: true,
  };
  assert.equal(verifiedPress({ posts: [item] }, []).length, 0);
  assert.equal(
    verifiedPress({ posts: [{ ...item, mentionsThreads: false }] }, [{ url }])
      .length,
    0,
  );
  const accepted = verifiedPress({ posts: [item, item] }, [{ url }]);
  assert.equal(accepted.length, 1);
  assert.equal(accepted[0].sourceKind, "press");
  assert.equal(
    complaintRequest.safeParse({ keywords: "test", direction: "unrelated" })
      .success,
    false,
  );
});
