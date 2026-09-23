# Sim Astana · Аким на 5 часов

A standalone, Russian-language city decision simulator. React + TypeScript + Vite; no backend or API keys.

## Run

From `akim/ui/`, with Node.js 22+:

```sh
npm ci && npm run dev
```

Open the localhost URL printed by Vite. The app bundles its fonts and draws its map locally; no external services are needed after installation. `npm run build` produces `dist/`; `npm run preview` serves that build.

In one minute: click Нура → explore its needs → create a plan (or try the prepared scenario) → compare before/after → ask residents → ask AI Аким for a swap. Plans persist in local storage. Escape closes overlays; all district labels are keyboard buttons.

## Preview

![Desktop city view](docs/desktop.png)

[Mobile preview](docs/mobile.png)

## Exact model

`src/data.ts` transcribes the synthetic district values, population shares, 14 measures, effect weights, lags, conflicts, and synergies from the supplied `akim/file.md` brief. The names of a few measures are shortened for display (M2 adaptive traffic lights, M7 modular school/kindergarten, M10 Safe City lighting/cameras).

`src/engine.ts` validates exactly five unique decisions, budget ≤100, at most two per direction, district assignments, and all conflicts. A plan can cover only three directions. `simulate()` returns `result: null` with errors for invalid plans. `projectEffects()` also calculates isolated proposal effects for polls; the UI does not display a plan score for those proposals or incomplete drafts.

- Baseline: **52.55768** → **52.56**.
- Example M7 Нура, M8 Нура, M10 Нура, M12, M5 Сарыарка: **95 units**, **56.54307**.
- Fixed synergies are not reduced by lag. The critical penalty counts district × indicator values **strictly below 40**.
- Advisor checks every valid single replacement, including changes of target district. It presents the highest-scoring alternative, even if a plan is already locally optimal; the comparison clearly shows the sign of the change.
- Autopilot starts from the reference plan and follows at most eight improving replacements. Its deterministic result costs **100**, scores **57.20556**, and is not claimed to be globally optimal.

## Demo boundaries

The map is original schematic artwork, with approximate shapes for five named districts, a stylized Esil river, streets, green spaces, and landmarks. These are **not authoritative district boundaries**. The city has 2,000 fixed-seed synthetic residents, distributed according to the supplied population shares. All dots remain in world coordinates during zoom.

`src/residents.ts` supports the three displayed example questions and “мой план”, with case, whitespace, punctuation, and ё normalization. Unsupported text returns guidance. No live LLM parses arbitrary questions.

Each district has six concern profiles. Each indicator starts with weight 1, receives +3 for a district priority and +4 for a profile priority; weights are normalized. For each profile:

```text
p(approval) = clamp(0.50 + 0.075 × weighted indicator gain − 0.00065 × proposal cost, 0.08, 0.94)
```

The district probability averages the six profiles, then rounds the district's approving resident count. City approval is the exact population-weighted total of those counts. Map green/red counts match the poll counts. This is a documented client approximation, **not measured public opinion**. Quotes are fixed templates tied to positive changes, negative changes, or absence of local benefit. The trade-off example compares independent approval of school + clinic in Нура against LRT in Есиль; the map explicitly shows the first proposal.

AI Аким uses local search and template explanations. Its short activity timeline records budget checks, simulations, demo polls, and alternative comparisons, with presentation delays; it is not model reasoning. Changes require an explicit Apply action. Before/after numbers always come from the engine.

## Future API connections

Keep the typed data boundaries in these modules when replacing local functions with async adapters:

- `engine.ts`: `simulate(plan)` → future `POST /simulate` or `/score`; returns validation errors and a district projection.
- `residents.ts`: `askCity(question, plan)` → future `POST /ask_city`; returns a supported poll or an explanatory error.
- `engine.ts`: `advise(plan)` and `autopilot()` → future advisor endpoints, returning proposed choices and calculated comparisons.
- `AkimPanel.tsx`: consumes these outputs and displays activity; `App.tsx` alone applies proposed choices.

## Verify

```sh
npm test
npx playwright install chromium
npm run test:browser
npm run build
```

Engine tests cover the reference scores, lag and all synergies, budget and conflict rules, district assignment, direction cap, invalid score behavior, negative effects/critical threshold, order invariance, repeatable polls, and advisor/autopilot validity. Browser tests exercise desktop and mobile flows, manual five-decision construction, budget/conflict blocks, asking, applying and dismissing advice, autopilot, persistence, keyboard focus, and a 360px layout. Screenshots and failure traces are written to ignored `test-results/`.
