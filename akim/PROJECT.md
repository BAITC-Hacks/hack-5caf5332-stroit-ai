# Sim Astana — «Аким на 5 часов»

An AI city-management simulator for Astana. The user plays the akim: they get a fixed virtual budget, pick 5 city measures across transport, ecology, social infrastructure, safety and city services, and receive an **Astana Quality of Life Score** with an explanation of strengths, risks and trade-offs.

Two AI layers sit on top of a deterministic scoring engine:

- **Synthetic residents** — a population of simulated citizens spread across the city's districts who react to proposed decisions ("ask the city").
- **AI Akim** — an agent that uses tools (simulate, ask the city) to analyse the user's decisions, consult residents, and recommend improvements.

Inspired by [sim francisco](https://simfrancisco.org/) (a synthetic-population digital twin of San Francisco that polls 10,000 LLM residents on policy questions; notes in [`reference/simfrancisco/`](reference/simfrancisco/)), adapted to a budget-constrained decision game where the score must be reproducible.

---

## 1. Problem

City development decisions have to balance several directions at once — transport, greenery, social infrastructure, safety and service quality — under a limited budget. Decision makers need a way to compare scenarios and see how a budget split affects quality of life, district by district, and how residents are likely to perceive it.

**Users:** city managers, analysts, hackathon teams playing the simulator.

## 2. Core principle: numbers are deterministic, AI explains

| Layer | Deterministic? | Role |
|---|---|---|
| Scoring engine | Yes | Validates the decision set, computes indicator changes and the Score. The only source of numbers. |
| Resident approval | Yes | Approval per resident archetype = concern weights × indicator changes in their district. |
| Resident quotes | LLM (cached) | Human-language reactions generated from the approval numbers, never inventing numbers. |
| AI Akim | LLM agent | Calls tools, reasons over results, explains trade-offs, recommends swaps. |

Same inputs always give the same Score and the same approval. This satisfies the checks "all teams start from the same budget and data" and "changing the decision set changes the Score".

## 3. Input data

Synthetic dataset, no personal data. Full spec in [`file.md`](file.md); task brief in [`tz.md`](tz.md).

- **5 districts** (real Astana district names): Есиль, Алматы, Сарыарка, Байконур, Нура, with population shares 0.27 / 0.24 / 0.20 / 0.13 / 0.16.
- **10 indicators** on a 0–100 scale (higher is better): T1 road decongestion, T2 public transport access, E1 greenery, E2 air quality, S1 schools and kindergartens, S2 clinics, B1 street safety, B2 road safety, C1 utility reliability, C2 speed of resolving resident requests.
- **14 measures** (M1–M14), each with a cost, a lag in quarters, effects, and a type: *district* (applied to one chosen district) or *city* (applied to all).
- **Synergies** (M1+M2, M10+M12, M5+M6) and **conflicts** (M1/M3 anywhere; M4/M7 and M5/M13 in the same district).

## 4. Scoring engine

Follows `file.md` exactly.

**Rules (validator)** — an invalid set gets no Score, only a reason:
- budget 100, total cost ≤ 100;
- exactly 5 measures, no repeats;
- district measures require a district, city measures must not have one;
- at most 2 measures per direction;
- no conflicting pairs.

**Computation:**
1. New indicator value: `I'_dk = clip(I_dk + Σ effect_mk × (8 − L_m)/8 + synergies, 0, 100)`. Horizon is 8 quarters.
2. District score: `D_d = Σ w_k × I'_dk`. Weights: T1 .10, T2 .10, E1 .09, E2 .11, S1 .11, S2 .11, B1 .09, B2 .09, C1 .10, C2 .10.
3. City average weighted by population: `D_avg = Σ pop_d × D_d`.
4. `Score = 0.7 × D_avg + 0.3 × min(D_d) − 1.0 × N_crit`, where `N_crit` is the number of district×indicator values below 40.

Reference values used as tests: baseline without actions **52.56**; the example set `M7 Нура, M8 Нура, M10 Нура, M12, M5 Сарыарка` costs 95 and gives **≈56.5**.

The engine output also includes the change per district and indicator and **each measure's contribution** to the Score. The AI cites these numbers and does not recompute them.

## 5. Synthetic residents ("ask the city")

**Population.** About 2,000 residents distributed across the districts by population share. Each resident has a small profile (age group, has children, car owner, pensioner, renter or owner) and a vector of **concern weights** over the 10 indicators. Weights come from the profile and the district's character, for example:
- Нура: high weight on S1/S2 (weakest social infrastructure) and T2;
- Сарыарка: high weight on E2 (private-sector smog) and E1;
- Есиль: high weight on T1 (bridge traffic jams) and S1 (overcrowded schools);
- Алматы: high weight on C1 (old utilities) and T1.

Residents are grouped into about **30 archetypes** (5 districts × ~6 profiles) so each LLM request stays small.

**`ask_city(question)` pipeline:**

```
natural-language question
  → parse (LLM): extract the measures and districts it refers to
       unrelated to city measures → {supported: false, examples}
  → engine: indicator changes per district
  → approval (deterministic): per archetype Σ concern_k × Δindicator_k,
       minus a cost-awareness penalty
  → voices (one batched LLM call): short quote per archetype,
       conditioned on its approval and the changes that drove it
  → result: approval by district and archetype, top reasons for / against, quotes
```

Results are cached by a hash of the parsed proposal, so repeating a question gives an identical answer.

Supported question shapes:
- a single measure: "Should we build a school and kindergarten in Нура?"
- a trade-off: "LRT in Есиль or school + clinic in Нура?"
- a full set: "What do residents think of M7, M8, M10 in Нура, M12 and M5 in Сарыарка?"

## 6. AI Akim (agent)

An LLM agent that uses tools with a bounded loop (about 8 tool calls). Every step is logged and shown in the UI as a visible reasoning trace.

| Tool | Returns |
|---|---|
| `get_city_state()` | Districts, indicators, profiles |
| `list_measures()` | Catalog with costs, lags, effects, conflicts |
| `simulate(set)` | Validation result, Score, per-district changes, per-measure contribution |
| `ask_city(question)` | Resident approval and quotes (section 5) |
| `submit(set)` | Final validated set |

**Modes:**
- **Advisor (main).** The user makes the 5 decisions. Akim simulates the set, asks the city, and explains the Score, strengths, risks and consequences, then suggests concrete swaps (for example "replace M5 with M2: +0.8 Score, +12% approval in Есиль").
- **Autopilot (benchmark).** Akim searches for a strong set on his own. The result is a reference line on the leaderboard to compare teams against.

**What makes the explanation interesting** is the tension between the Score and approval. For example, the LRT may be popular in Есиль while the Score favours Нура's school and clinic, because 30% of the Score comes from the weakest district. Akim has to name that trade-off and its consequences.

## 7. Optional features

| Brief option | Implementation |
|---|---|
| Comparison of several teams | Each team's submission is a scenario from the same initial state; the leaderboard shows Score, approval and cost; Akim's autopilot result is the benchmark. |
| Visualization of district changes | Map of Astana districts shaded by D_d before and after; resident dots coloured by approval; a table of indicator changes. |
| AI recommendations | Akim's advisor mode: concrete swaps checked through `simulate`. |
| Unexpected city events | Event cards (e.g. "−38 °C frost: heating main break in Алматы, C1 −15, 20 units of budget required") applied to the scenario; the user reallocates the budget and the engine recalculates. |
| Short presentation | Auto-generated one-page summary: chosen set, Score, district map, resident quotes, Akim's verdict. |

## 8. Real-data layer (optional, offline)

Live APIs never feed the Score. The following are fetched once and committed as a snapshot, used for the map and a "reality check" panel (source details in [`../INVENTORY.md`](../INVENTORY.md)):

- district boundaries: map.gov.kz WFS `geonode:border_districts` (Astana district codes 711110000 Алматы, 711210000 Есиль, 711410000 Байконур, 711610000 Сарайшык, …);
- road accident points: gis.kgp.kz ArcGIS DTP service (Astana bounding box, 1,543 points in 2026 as of 2026-09-23);
- crime records: data.egov.kz `astana_kalasynyn_kylmystyk_kuk1` via the key-free Detailed API (per-district police department in `organ`);
- air quality: Open-Meteo Air Quality at each district centre;
- population: stat.gov.kz element 6584.

Example of how the AI uses it: "Нура's synthetic S1 = 38 is consistent with reality: it has the fewest schools per 1,000 residents of the five districts."

## 9. Architecture

```
┌──────────────── Browser (single HTML page, Leaflet) ────────────────┐
│ decision builder · budget bar · map · resident dots · Akim chat/trace │
│ leaderboard · event cards · summary export                           │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ JSON
┌───────────────────────────────▼─────────────────────────────────────┐
│ FastAPI                                                               │
│  engine.py     validator + score + contributions (pure, tested)       │
│  residents.py  population, archetypes, deterministic approval         │
│  ask_city.py   parse → engine → approval → voices (cached)            │
│  akim.py       agent loop over the tools, trace log                   │
│  data/         dataset.json (from file.md), real_snapshot.json        │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                         Claude API (claude-sonnet-5)
```

**API:**
- `GET /state`, `GET /measures`
- `POST /validate`, `POST /score`
- `POST /ask_city`
- `POST /akim/advise` (advisor), `POST /akim/autopilot`
- `POST /scenarios` (save a team's submission), `GET /leaderboard`
- `POST /events/{id}/apply`

## 10. Mapping to the evaluation criteria

| Criterion | How the project covers it |
|---|---|
| Fit and working scenario (25) | Full loop: pick 5 measures → validation and budget control → Score → AI explanation. All must-haves covered. |
| Technical implementation (25) | Deterministic engine separated from AI; a tool-using agent; a synthetic-resident layer with a grounded pipeline; caching; visible agent trace. |
| README and reproducibility (25) | One-command run; engine tests reproduce the reference numbers from `file.md` (52.56 baseline, ≈56.5 example); fixed seeds for residents. |
| Value and applicability (15) | Scenario comparison plus resident-perception signal, grounded in real Astana district geography and open data. |
| Originality and potential (10) | "Ask the city" synthetic population; Score vs approval trade-off; the dataset can be swapped for real city data, and the approach extends to other cities. |

## 11. Build order

1. `engine.py` + tests matching the `file.md` reference numbers.
2. Residents: population generator, archetypes, deterministic approval.
3. `ask_city` pipeline with caching.
4. Akim agent loop (advisor first, then autopilot).
5. UI: decision builder, budget bar, map, results, Akim chat.
6. Optional: events, leaderboard, summary export, real-data snapshot.
7. README: setup, architecture, run steps, demo scenario.

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| LLM invents numbers | The LLM receives only engine output and is instructed to cite it; numbers in the UI come from the engine. |
| Resident opinions look arbitrary | Approval is a deterministic formula over concern weights; the LLM only phrases it. |
| Akim replaces the user's decisions | Advisor mode is the default; autopilot is a benchmark only. |
| API latency or cost | Archetypes instead of individuals, one batched call, hash cache. |
| Live data sources go down | Real data is a committed snapshot, never a runtime dependency. |
