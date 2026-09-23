# First-time walk: Sim Astana (issue #21)

Build: branch `sim-astana-ui-20260923-135841` @ `87717df`, `akim/ui`, `npm run dev`, desktop 1456×822, 2026-09-23 ~16:30–16:50.

Coverage:
- **No keys:** all seven panels, on a local API with an empty `.env`.
- **With keys (partial, see F18):** only the first few steps. They ran against another local API instance (older build, OpenAI key) that was already bound to :8791. The live Worker was not walked.

Findings are in the order a first-time user meets them. Severity: **S** = stuck or misled, **M** = friction, **L** = polish.

## Arrival

- **F1 (M) Seven entry points in four corners.** [01](01-landing.jpg)
  - Hero CTA "Изменить город" and "Попробовать готовый сценарий" on the left.
  - Мобильность / Жалобы chips top-left.
  - Data hidden in the weather chip "15.8° AQI 25" top-right.
  - План / Спросить город / AI Аким dock at the bottom.
  - "О симуляции" as tiny text bottom-right.
  - Nothing says which to do first. Complaints and mobility are not mentioned in the hero.
- **F2 (M) The only onboarding is behind "О симуляции".** It is a small bottom-right link. [16](16-about.jpg)
  - Its 3-step path (районы → пять мер → жители и AI Аким) never mentions Мобильность, Жалобы or Данные.
  - The score formula lives only here.
- **F3 (L) Сарайшык shows "нет модели" on the map** with no explanation. [01](01-landing.jpg)

## Plan

- **F4 (S) The Мобильность / Жалобы chips float over the top of every left panel.** Affected: План, district card, AI Аким, Данные.
  - They hide panel titles ("План для города", "AI Аким", the data heading).
  - They hide the district card's "← Весь город" back link.
  - [02](02-plan-overlap.jpg) [06](06-district.jpg) [10](10-akim-advisor.jpg) [12](12-data.jpg)
- **F5 (M) "Попробовать готовый сценарий" applies five measures instantly and closes the hero.** [03](03-scenario-applied.jpg)
  - The only feedback is a toast and the score going 52,56 → 56,54 (+3,99).
  - The user never sees which five measures were chosen unless they reopen "Мой план".
- **F6 (S) The До / После toggle is small and ambiguous.** It sits inside the Quality of Life card. [04](04-before-toggle.jpg)
  - Switching to "До" reverts the district labels (Нура 53.0 → 49.2).
  - The big score stays at 56,54 +3,99, so before/after contradict each other.
  - The selected segment is hard to read.
- **F7 (L) The plan persists in localStorage.** A returning visitor (or the next judge on the same laptop) skips the hero and lands on "Мой план 5/5" with no way back to the intro except "О симуляции".

## District and residents

- **F8 (M) District click works and the card is clear** (needs, a resident quote, "Помочь району"). [06](06-district.jpg)
  - Discoverability relies on one small hero hint ("Нажмите на район…"), which is gone once a plan exists.
- **F9 (M) Clicking a moving dot opens a resident card** (name, job, district, priorities, routine). [07](07-resident.jpg)
  - Nothing says dots are clickable.
  - The card has no "ask this resident" action.
- **F10 (L) Leaflet exception on a map click:** `TypeError: Cannot read properties of undefined (reading '_leaflet_pos')` at `CityMap.tsx:204` (click handler). No visible breakage.

## Спросить город

- **F11 (S, no keys) Free-text questions are refused in local demo mode.** The error reads "В деморежиме доступны три вопроса ниже и «мой план»…". [09](09-ask-freetext-refused.jpg)
  - The input invites typing, and only after submit does the user learn it doesn't work.
  - Enter does not submit; the send button must be clicked.
- **F12 (M) "Ingest Threads" is an English engineering label in a Russian UI.** With no keys it is greyed out without saying why. "Учитывать при опросе" is unexplained. [08](08-ask-local.jpg)
- **F13 (L) The answer view is good.** 57,60% support, per-district bars, quotes, and "не реальный опрос" labelling. [08](08-ask-local.jpg)
  - The results don't link back to the map or a district.

## AI Аким

- **F14 (M) Opening AI Аким auto-runs the check.** It shows a 4-step trace, the verdict and "Ваш план 56,54 → 57,21". [10](10-akim-advisor.jpg)
  - The proposal and its Apply button are below the fold.
  - The Советник / Автопилот tabs are unexplained. Автопилот silently produces a different plan. [11](11-akim-autopilot.jpg)
  - The trace doesn't mention complaints or mobility.

## Данные города

- **F15 (M) There is no "Данные города" label anywhere.** The entry is the weather chip. [12](12-data.jpg)
  - The panel itself is honest: "Сохранённый снимок" badges, observation/request times, licences.
  - It says real data doesn't change scores, which leaves "why is it here?" open.

## Мобильность

- **F16 (S) With the ready-made scenario, До and После are identical** (39.2 / 39.2, …) because the scenario has no transport measures. [13](13-mobility-no-transport.jpg)
  - The first mobility view a judge sees shows no effect.
  - "Пример: автобусные полосы + светофоры" silently swaps measures in the user's plan. District scores change (Нура 53.0 → 52.2) with no confirmation. [14](14-mobility-example.jpg)
  - After the swap, "Участки с перегрузкой" rises 57.9 → 70.9 km while average trip time falls. Nothing explains this.
  - The panel opens on the right and covers the Quality of Life card.

## Жалобы

- **F17 (S, no keys) The complaint map is empty on first open** with no stored collection. [15](15-complaints-nokeys.jpg)
  - "Ingest Threads → карта" is disabled; "Классификатор Jev пока не подключён" is the only explanation.
  - A judge who never gets the shared 24h KV store sees nothing.
  - Opening Жалобы adds an unexplained "×" to the chip group.

## Not covered, and environment risk

- **With-keys walk** of Ask with Threads, Жалобы ingest with Jev, and Luna AI Аким: not done. This session had no local keys, and the live Worker was not driven because every call spends shared quota.
- **F18 (S, environment) Version mismatch.** The one with-keys attempt went to an older local API on :8791. The suggested question "Что жители думают о моём плане?" failed with "Укажите вопрос до 1000 символов и допустимые идентификаторы мер." [05](05-oldapi-ask-error.jpg)
  - The same question works on this branch's API.
  - The UI and API are not version-checked, so a stale deploy would fail like this in front of judges.
- **Fresh-visitor manual plan building** (catalog → district → five measures): only glanced at in [02](02-plan-overlap.jpg). Each measure needs "Выберите район", and there is a limit of one measure per direction.
- **Mobile layout:** not in this ticket (it is fog on the map).
