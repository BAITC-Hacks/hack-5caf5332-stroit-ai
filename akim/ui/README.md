# Sim Astana · Аким на 5 часов

Russian-language city decision simulator: React, TypeScript, Leaflet, Canvas and a Cloudflare Worker API. Explore the city, choose five investments, ask simulated residents and compare AI Akim's proposals.

**Live:** https://sim-astana.diaskhalniyasov.workers.dev

## Run

Live AI modes require an OpenAI key with access to the configured model. Everything else works without it, including local planning, resident simulation and goal search with structured constraints.

Node.js 22+; run from `akim/ui`:

```sh
npm ci
cp .env.example .env
# Set OPENAI_API_KEY in .env. Never put it in VITE_* variables.
npm run dev
```

Open **http://127.0.0.1:5173**. Vite proxies `/api` to **127.0.0.1:8791**. To use another API port, update `.env` and the proxy in `vite.config.ts`. For a built app, `npm run build && npm start` serves both UI and API at **http://127.0.0.1:8791**. `npm run preview` is only a static preview; use `npm start` for live services.

The configured model is **`gpt-6-luna`**, using OpenAI Responses, structured outputs, function calls and low reasoning effort. The key stays on the server in an ignored `.env`; no key is returned to the browser. Without a key, explicitly labeled local resident/advisor modes remain available. Live failures show an error; they do not silently switch models.

Choose a district → create a plan or load the example → compare before/after → ask residents → open AI Akim and press **Проверить план с AI**. Proposals require **Apply** to change your plan. Plans persist in local storage. Escape closes panels. Reduced-motion settings pause the city clock initially.

![City view](docs/desktop.png)

[Mobile](docs/mobile.png) · [Real data panel](docs/sources.png) · [Resident profile](docs/resident.png)

## Real city data

`server/city-data.ts` calls the JSON endpoints listed below. Project context and requirements are in `akim/tz.md`, `akim/file.md` and `akim/PROJECT.md`. `GET /api/city` exposes normalized records with source URL, attribution, observation date, retrieval date and **live / cached / unavailable** status.

| Source                                                                                                                                                                                                                                  | Usage                                                                | Limits                                                                                       |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| [Open-Meteo weather](https://api.open-meteo.com/v1/forecast?latitude=51.1694&longitude=71.4491&current=temperature_2m,wind_speed_10m,weather_code&timezone=Asia%2FAlmaty)                                                               | Temperature, wind, weather code; context for AI and evening routines | Forecast model at a city point, not a station measurement                                    |
| [Open-Meteo / CAMS air](https://air-quality-api.open-meteo.com/v1/air-quality?latitude=51.1694&longitude=71.4491&current=pm2_5,pm10,european_aqi&timezone=Asia%2FAlmaty)                                                                | European AQI, PM2.5 and PM10; AI context                             | Modeled grid; no claim of district-level measurements                                        |
| [KGP ArcGIS DTP](https://gis.kgp.kz/arcgis/rest/services/KPSSU/DTP/FeatureServer/0)                                                                                                                                                     | Count of 2026 accident records within 71.2–71.65°E, 51.0–51.3°N      | Bounding box differs from the administrative city; not an official Astana total              |
| [Bureau of National Statistics, table 6584](https://stat.gov.kz/api/iblock/element/6584/json/file/ru/)                                                                                                                                  | Latest all-population Astana series; periods sorted by date          | Latest verified observation: 1,528,703 at 2025-12-31, not a live population counter          |
| [National Geoportal WFS](https://map.gov.kz/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature&typeNames=geonode:border_districts&outputFormat=application/json&propertyName=kato,name_ru&CQL_FILTER=kato%20LIKE%20%2771%25%27) | Unique district KATO registry, deduplicating multipart entries       | Six real districts are shown; Sarayshyk has no synthetic score in the five-district game |

Weather/air cache for 15 minutes; other sources for 24 hours. Timeouts, invalid/partial responses and upstream failures return an explicitly dated saved snapshot or `unavailable`, never invented readings. `npm run data:check` prints concise endpoint status. Cached JSON lives in ignored `.cache/store` locally and Cloudflare KV in production.

Real data is supplied to the LLM as context. It does **not** overwrite the original synthetic quality-of-life indices, district weights or assumed policy effects. Refresh checks the server's cache policy; observation and retrieval times are shown separately.

## Public Threads evidence

In **Спросить город**, type a proposed decision and click **Ingest Threads**. Luna expands it into up to six searches covering the street, problem, synonyms and neutral/supportive alternatives in Russian, Kazakh and English. For a road near Seifullin, queries include `Астана Сейфуллина пробки`, `Astana Seifullin traffic` and `Астана устал от пробок`.

Search uses OpenAI Responses `web_search`, restricted to public `threads.com` / `threads.net` pages. The interface displays planned and executed queries, source links, AI paraphrases, complaint/support labels, and whether each post refers to the street or Astana generally. Only post URLs present in actual search sources are accepted. Publication dates are marked unconfirmed; invented posts and profile URLs are rejected. Enable **Учитывать при опросе** to search automatically with the next city question and supply the evidence to the synthetic resident model. Unsupported policy questions still return Threads evidence with a clarification notice.

This searches **web-indexed public posts**, not the complete Threads feed or a representative public survey. No matches means insufficient indexed evidence, not no complaints. Search results are reused within a 30-minute cache window. No Meta account/token is needed; no private posts or personal profiles are collected.

## Cloudflare deployment

The frontend and `/api/*` share one Worker origin; static assets are served by Cloudflare. `wrangler.jsonc` defines the deployment and KV/rate-limit bindings. OpenAI credentials are Worker secrets and never enter the browser bundle.

```sh
# Authenticate Wrangler to the Cloudflare account first.
npx wrangler secret put OPENAI_API_KEY
npx wrangler secret put SESSION_SECRET # random, high-entropy value
npm run deploy
```

For another account, create a KV namespace with `npx wrangler kv namespace create CACHE` and replace the ID in `wrangler.jsonc`. The current deployment was uploaded through the authenticated Cloudflare API. `OPENAI_MODEL` remains `gpt-6-luna`.

Local Worker preview: copy the API key and a random `SESSION_SECRET` into ignored `.dev.vars`, run `npm run build`, then `npm run dev:cloud` at **http://127.0.0.1:8792**. Run `npm run types:cloud` after binding changes and `npm run check:cloud` before publishing. The separate Express/Vite workflow above remains available.

## Conventional budget units and reference prices

The game budget is **100 conventional units (у.е.)**, as specified in `akim/file.md`. Measure costs in these units drive validation and resident calculations. Million-tenge figures in `src/money.ts` (`referenceMln`) are **reference-only** estimates, not a currency conversion, spending limit or the city's available investment budget.

- Published 2026 city costs: **1,286,453.4108 million ₸**. [Astana budget decision](https://old.adilet.zan.kz/rus/docs/G25AAZ3524M) states 1,286,453,410.8 **thousand** ₸; this app divides by 1,000. Source snapshot verified 2026-09-23, not refreshed automatically.
- M7: **8,400 million ₸**. [Government school benchmark](https://primeminister.kz/ru/news/asset_recovery/novaya-shkola-na-1200-uchenicheskih-mest-budet-postroena-v-astane-na-sredstva-iz-vozvrashchennyh-aktivov-31773): 7,000 million for a 1,200-place school, plus an explicitly assumed 1,400 million for kindergarten/reserve.
- M8: **7,200 million ₸**, a historical mean from [the 2024–2028 forecast](https://www.gov.kz/memleket/entities/astana/documents/details/533548?lang=ru): five clinics for 36,000 million. Not a current tender estimate.
- Other prices are scoped scenario estimates, including a limited LRT phase, **not actual awarded contract amounts**. Each measure's expandable price basis and `src/money.ts` explain its scope.

## Resident simulation

`src/population.ts` creates **2,000 reproducible synthetic people**, with names, ages, six concern profiles per district, homes, work/study destinations and leisure destinations. These are fictional profiles, unrelated to personal records.

Residents follow daily schedules and connected routes along a bundled OpenStreetMap street graph: home → work/study/errands → leisure → home. Travel uses individual departure offsets. The clock supports pause and 6/30/120 simulated minutes per second. Click a person or the resident button to inspect their profile and current activity. Rain, temperature below −10°C or wind above 40 km/h sends them home after work instead of leisure; this simple behavioral rule is a scenario assumption, using the latest available weather snapshot. Destinations and journeys are fictional, with simplified timings and no one-way or access rules. The basemap uses OpenStreetMap; district geometry comes from the National Geoportal. [Map provenance and reproduction](docs/MAP.md).

The routine / persona / batched-opinion design is inspired by [Sim Francisco](https://github.com/tejasprabhune/simfrancisco). Implementation is original. Character artwork is attributed and licensed separately in [ATTRIBUTION.md](docs/ATTRIBUTION.md).

### Resident opinions

In OpenAI mode, an arbitrary question is parsed into one or two proposals using only the 14 measures and five modeled districts. Invalid, ambiguous or unsupported proposals return a clarification error. The LLM receives actual indicator deltas, budget, profile priorities and dated city context. It returns **30 cohort probabilities and quotes**; the server validates every district/profile combination and computes counts for the exact resident cohorts. Green/red markers correspond to those computed votes. Comparisons show independent approval of two proposals.

These are **model estimates of synthetic opinion**, never actual public polling. They are cached for 24 hours for the same model, proposal and city context. No LLM request runs on animation frames or for each individual resident.

Local mode supports the three examples and “мой план”. Its six concern profiles average this rule, then round district votes:

```text
p(approval) = clamp(0.50 + 0.075 × weighted indicator gain
                   − 0.065 × (proposal cost in units / 100), 0.08, 0.94)
```

Indicator concern starts at 1, adds 3 for district priorities and 4 for profile priorities, then normalizes. Quotes are local templates. This mode is labeled in the UI.

## AI Akim and the scoring engine

`src/data.ts` / `src/engine.ts` preserve the brief's synthetic values, effects, lags, synergies and conflicts. A valid plan has exactly five unique decisions, cost ≤100 у.е., at most two per direction and correct district assignments. Invalid plans have no displayed score.

- Baseline **52.55768**.
- Example M7 Nura, M8 Nura, M10 Nura, M12, M5 Saryarka: **95 у.е.**, score **56.54307**.
- Fixed synergy is not reduced by lag. Each district/indicator strictly below 40 incurs a penalty.
- Local advisor checks every valid single replacement; local autopilot follows at most eight improving replacements. It does not claim a global optimum.

In live mode, Luna chooses through a bounded loop of at most eight tool requests, with explicit completion from verified candidates near the limit. It uses a sequence of `simulate`, `ask_residents` and `submit_plan` function calls. `ask_residents` here is an explicitly described **local analytic approximation** to compare candidates; the separate resident polling UI uses the LLM cohort survey. Submission requires both simulation and consultation for that exact plan. Advisor must replace exactly one decision. The server recalculates all scores and costs, then asks Luna for a qualitative explanation. Activity rows report tool actions, not hidden model reasoning. Cached runs are labeled.

Goal mode accepts a Russian `goal` (up to 300 characters), such as “Улучшить транспорт, защитить Нуру и оставить 20 у.е.”, or a structured `constraints` object (takes precedence over text). Fields: `priorities` (names from `src/data.ts`), `protectedDistricts` (district IDs), `minSupportPercent` (0–100, local `pollProposal` approval), `reserveUnits` (0–100), `mustInclude` / `mustExclude` (measure IDs). Omitted fields default to empty lists or zero. Priorities influence ranking; all other constraints are mandatory. District protection compares scores with the city's baseline, not the current plan. A bounded search (24 partial candidates, then up to eight single replacements from four seeds) supplies a feasible candidate when found; it does not prove global optimality or infeasibility. Live submissions are checked server-side and retried on violations; the explanation describes constraints and sacrifices. Without a key, send `constraints`: search runs entirely locally and returns `model:"local"`, `cached:false`. Text-only goals need OpenAI. Goal results include the resolved `constraints`; unmet constraints produce an explicit error, never a relaxed plan.

API routes:

- `GET /api/health`: model, configured flag, local session token; never the API key.
- `GET /api/city`: dated source records.
- `POST /api/ask`: `{ question, plan, useThreads? }` → `{ poll, evidence?, notice? }`.
- `POST /api/threads/ingest`: `{ question, plan }` → `{ evidence }`.
- `POST /api/akim`: `{ mode: "advisor" | "autopilot" | "goal", plan, goal?, constraints? }` → NDJSON activity/result/error events. Goal mode requires `goal` or `constraints`; e.g. `{ "mode": "goal", "plan": [], "constraints": { "priorities": ["Транспорт"], "reserveUnits": 20 } }`.
- `POST /api/explain`: `{ plan, priorities }` → `{ brief: { summary, tradeoff, nextStep, model, cached } }`.

POSTs require a session token and same-origin requests, with schema/body limits and cancellation/timeouts. The local Express server allows two concurrent requests and 30 requests per 15 minutes. The public Worker uses hourly IP-bound signed tokens and Cloudflare rate limits: 5 AI requests/minute per IP and 20/minute per serving location. These limits are abuse throttles, not login authentication or a global spending cap. Responses API calls use `store: false`.

## Verify

```sh
npm test
npx playwright install chromium
npm run test:browser
npm run build
npm run data:check
```

Unit tests cover calculations, prices, validity, resident paths/schedules, population parsing, district deduplication, malformed cohort rejection, goal parsing/constraints/local search and safe errors. 16 browser cases cover desktop/mobile plan flows, clock and profiles, source display, real-mode API contracts, streaming proposals, explicit application, failure handling, persistence and keyboard access. Browser API fixtures make tests deterministic and avoid paid calls. Screenshots/traces go to ignored `test-results/`.

Live verification on 2026-09-23: all five city endpoints responded; `gpt-6-luna` returned valid 30-cohort school and free-text park polls and tool-based advisor/autopilot plans. Secrets are excluded from source, artifacts and browser bundles.

Cloudflare verification on 2026-09-23: public desktop/mobile pages loaded without JavaScript errors, OSM tiles rendered, all five city sources were available, Seifullin Threads search executed all six queries and returned zero indexed matches, Luna produced a resident poll and a validated one-change advisor plan. 23 unit tests, 16 browser cases, TypeScript and the Worker dry-run pass.
