# Prompt for Claude Fable 5.1 — Sim Astana UI

Copy the text below into Fable with this repository available. The deliverable is a working frontend in `akim/ui/`, not a design document.

---

You are building **Sim Astana / «Аким на 5 часов»**, a UI-first city decision simulator. Work autonomously through implementation and verification. Give brief progress updates, and finish with a concise report of what runs and any limitations. When you have enough information to act, act.

## Read these files first

- `akim/PROJECT.md` — product concept and the two AI experiences.
- `akim/file.md` — exact synthetic dataset, 14 measures, validation rules, and score formula. Treat this as the source of truth for values.
- `akim/reference/simfrancisco/NOTES.md` and all screenshots in `akim/reference/simfrancisco/screenshots/` — visual and interaction reference.
- `akim/reference/simfrancisco/src/app.js` and `map.js` — useful behavior reference; the screenshots are the visual reference.

Inspect the current repository before creating files. Build in `akim/ui/` so the project can be run independently. Use a small frontend stack you can run locally (React + TypeScript + Vite is a good default). Do not build FastAPI, a database, live Claude calls, authentication, a leaderboard, or a real-data ingestion pipeline in this pass.

## Product goal

Create a polished, interactive prototype that makes **Astana feel like a living city** and lets a user:

1. Explore five Astana districts and their synthetic residents on a map.
2. Choose **exactly five** city measures under a **100-unit** budget and understand the impact immediately.
3. Ask synthetic residents what they think about a measure or scenario.
4. See an **AI Akim** experience in two modes: **Advisor** analyzes the user's five decisions and suggests a concrete improvement; **Autopilot** proposes its own valid five-decision plan that the user can compare and optionally apply.

The map and the visual reaction of the city are the main experience. The decision tools should feel like carefully designed overlays on the map, not a conventional dashboard with a small map widget.

## Visual direction: match the Sim Francisco UI closely

Recreate the **composition, visual language, and interaction rhythm** shown in the local screenshots, adapted to Astana:

- Full-viewport, map-first canvas with a deep blue background and a large city map centered in the frame.
- A dense field of small resident sprites/dots that makes the city look inhabited. They should stay anchored to the relevant district during zoom and react visually to a poll or scenario.
- Compact rounded translucent controls: project title at top left; city/resident status and contextual information at top right; primary action dock near bottom center.
- The bottom **Ask the city** pill expands into a composer. Submission becomes a clear progress state, then a floating result card with approval, opposing share, district breakdown, and short resident quotes. Allow the user to dismiss it or ask another question.
- Clicking a district zooms into it; a **Whole city** control restores the overview. At closer zoom, a few short resident thought bubbles can appear without overwhelming the screen.
- Soft pale panels, restrained shadows, near-black text, rounded corners, smooth transitions, and green/red reaction colors. The map should remain legible behind overlays.

Do not use the San Francisco map as Astana. The reference folder contains screenshots and source behavior, not a reusable Astana basemap. Produce an original Astana map treatment. If accurate local district polygons or map assets already exist in the repository, use them. Otherwise build a clearly stylized Astana map with the Ishim/Esil river, a street/green-space texture, and **clearly labeled approximate** shapes for Есиль, Алматы, Сарыарка, Байконур, and Нура. Do not present hand-drawn boundaries as authoritative geography. Keep the result visually close to the reference: this is a city simulation, not a generic analytics dashboard.

Use Russian for primary UI copy and district/measure names from `file.md`. Keep labels short and readable. Accessibility matters: sufficient text contrast over the map, visible keyboard focus, labeled inputs, meaningful button states, and reduced-motion support.

## Main interaction flows

### 1. Explore the city

On load, show the whole city and a short, purposeful reveal of residents. The top status should state that this is a **synthetic simulation** and show the resident count. Hover/focus or click a district to see its name, baseline district score, top needs, and a few representative voices. The selected district should be obvious on the map. Let users return to the whole city easily.

### 2. Build a five-decision plan

Add a prominent **Create a plan** action near the bottom dock. Open a drawer or floating panel while keeping the map visible. Show five empty decision slots, the measure catalog grouped by the five directions, and a district selector only for district measures. Each card should show cost, start lag, and plain-language impact. Make selection, removal, and replacement quick.

Keep a sticky budget display (`spent / 100` and remaining), a five-slot progress indicator, and helpful inline validation. Prevent over-budget choices and explain conflicts before selection. The rules in `file.md` are exact: five unique measures, at most two per direction, district required only for district measures, and the specified conflicts. **Do not require one measure from each direction**; the rule is five measures total across at least three directions. An invalid set has no score and shows the reason.

After a valid set is chosen, reveal the Astana Quality of Life Score, change from the 52.56 baseline, a before/after district view on the map, key indicator changes, and the largest trade-offs. Make it easy to edit a choice and see the effect update. Use the sample valid plan from `file.md` as a one-click demo path: M7 Нура, M8 Нура, M10 Нура, M12 citywide, M5 Сарыарка; cost 95, score approximately 56.5.

### 3. Ask the city

Keep the reference site's simple ask interaction. Offer a free-text question and three useful example chips (one measure, a district trade-off, and the current full plan). For a UI-only build, implement a small, honest demo resolver for supported examples and the current selected plan, with deterministic results from local fixtures or a documented client-side approximation. Unsupported questions should get a helpful suggestion, not a fabricated opinion. Show approval by district and representative quotes tied to the displayed direction of impact. Make **Synthetic residents · demo mode** visible near these results. Repeated input should return the same output.

### 4. AI Akim

Give the Akim a distinct but integrated overlay, accessible from the main map. In **Advisor** mode, he examines the current valid plan, summarizes strengths and risks, and presents at least one specific swap with a before/after comparison. The user can apply or dismiss the recommendation. In **Autopilot**, he presents a complete valid plan, why he chose it, its cost and score, and a direct comparison with the user's plan. Do not silently replace the user's choices.

Show a compact **activity timeline** such as “Checking budget,” “Simulating scenario,” “Consulting residents,” and “Comparing alternatives.” This is a user-facing record of steps and tool results, **not hidden model reasoning**. Since this pass has no live LLM, make the demo nature of AI Akim clear in the UI. Use deterministic local logic or fixtures for the interaction, and keep the state/data interface clean enough for future `simulate`, `ask_city`, and advisor API calls. Do not invent precise numerical claims in text that are not calculated or present in the fixture.

## Data and score behavior

Put the `file.md` district values, population shares, 14 measures, costs, lags, effects, synergies, and conflicts into typed local data. Implement the exact deterministic validation and scoring calculation **in the browser** so the core UI is functional without a backend. The baseline without actions is **52.56**. The sample five-measure set should be around **56.5** after applying lag, synergies, district weights, minimum-district term, and the penalty for each district × indicator strictly below 40. Only show scores for valid five-measure plans; when showing a draft preview, label it clearly as a preview if it uses different rules.

The score and indicator numbers must come from the local calculation, not from generated prose. The synthetic resident response and AI copy may be demo content, but their conclusions must stay consistent with the measured changes.

## Finish and verify

Build the actual frontend and run it. Check both desktop and narrow/mobile layouts, including open overlays and the full five-decision flow. Verify at least the baseline score, sample scenario, budget block, conflict rule, district selection rule, and one complete Advisor/Autopilot interaction. Fix visible layout or interaction problems you find. Provide a short `akim/ui/README.md` with one-command run instructions, the demo-mode boundary, and where future APIs connect.

The result should be something a hackathon judge can open and understand in under one minute: **explore Astana → make five choices → see the city and score change → ask residents → compare the AI Akim's recommendation**.

---

The prompt is shaped for Fable 5.1's long coding turns: it gives context and a concrete deliverable, asks for brief progress updates, keeps scope explicit, and requires verification before the final report. It also works with Fable 5.
