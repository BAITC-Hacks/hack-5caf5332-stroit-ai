# Which scoring and pilot mechanics could the hidden environment change?

Resolves issue #11 (map #9). Paths below are relative to `beeline/beeline_case_participants (1)/`
unless prefixed; line numbers are from branch `worktree-beeline-agent` @ the commit this file sits on.

## Answer in one paragraph

The organisers state that the judge scores with the **same** `scoring_core.py` and runs the
**same** `environment.py` class; only the effect model differs (`scoring_core.py:8-10`,
`environment.py:4-7`, `local_eval.py:11-15`, `PARTICIPANT_GUIDE.md:195-196,210-211`). Taking
that at face value, everything structural is fixed: the effect lookup key
`(current_tariff, arpu_segment, target_tariff)`, the formula
`predicted_arpu × arpu_change_pct × min(conversion_rate × channel_mult, 1)`, the channel
table, the limits, ID-ordered truncation, max-per-customer dedup, and Gaussian pilot noise
`0.804/√n_actual`. What the hidden side supplies are the **arguments**: the `impact_model`
table (values *and* which keys exist), the `fallback_predict` rule for missing keys, and the
RNG seed. So the agent's structural assumptions (effect keyed by cell × target; data/call
segments do not change effect size; noise model) are guaranteed; its **numbers** (a prior
that nearly equals the mock's truth, the uniform calibration shift, the call haircut, the
fallback for unseen transitions) are only validated against the mock.

## 1. Fixed by public code

| Mechanic | Where | What exactly |
|---|---|---|
| Effect key | `scoring_core.py:147-155`, `environment.py:114-117` | segment rows merged to `impact_model` on `current_tariff→tariff_plan_code_from`, `arpu_segment`, filtered by `tariff_plan_code_to == target`. No other profile column enters the lookup. |
| Effect formula | `scoring_core.py:167-172` | `lift = arpu_change_pct × clip(conversion_rate × mult, ≤1) × predicted_arpu`; relative effect scaled by each subscriber's `predicted_arpu` (`scoring_core.py:137-140`). Missing key after fallback → 0 (`:172` `fillna(0.0)`). |
| Channel cost / multiplier | `scoring_core.py:21-26` (hard-coded in the scorer), repeated in `mock_environment.py:25-30` and `PARTICIPANT_GUIDE.md:105-110` | push 0/×0.50, sms 4/×0.65, digital_ads 22/×0.85, call 160/×1.20. |
| Conversion cap | `scoring_core.py:166-167`, `environment.py:126` | `clip(upper=1.0)`; only `call` (×1.2) can hit it, when `conversion_rate > 0.833`. |
| Limits | `scoring_core.py:16-18,27`; `environment.py:46-48` | 10 campaigns, 5 000/campaign, 15 000 contacts and 100 000 money *including pilots*; 20 pilots of 10–200 (`environment.py:148` clips the request). |
| Truncation | `scoring_core.py:198-215` | segment sorted by `ID_NUMBER`, then cut in order: per-campaign 5 000 → remaining reach → `remaining_money // cost` (paid channels only; push is reach-limited only). Cut is by lowest ID, not by value. |
| Ordering | `scoring_core.py:195`, `local_eval.py:46-48` | campaigns consumed in list order; the harness puts executed pilots first, finals after, so any cap bites the finals. Finals beyond 10 are dropped (`local_eval.py:45`); invalid tariff/channel dropped by `sanitize_campaigns` (`scoring_core.py:38-62`). |
| Dedup | `scoring_core.py:241-251` | each ID counted once at its `idxmax` lift across all campaigns (pilots included); repeat contacts still cost money and reach (`:217-221`). A customer only reached by a negative campaign counts negative. |
| Cost / net | `scoring_core.py:218-220,254` | cost = contacts × cost_per_contact for every campaign incl. pilots; `net = gross_lift − total_cost`. |
| Pilots in score | `environment.py:180-181`, `scoring_core.py:115-119` | pilot scored on its exact `explicit_ids` with the **true** effect; noise only affects what the agent sees, not the score. |
| Pilot noise | `environment.py:52,172-173` | `observed = mean(true per-customer ratio over picked) + N(0, 0.804/√n_actual)`; ratio already includes channel multiplier and cap. Sample is a random subset of the filtered segment (`:170`). |
| Pilot accounting | `environment.py:162-178` | `n_actual = min(requested∈[10,200], |segment|, affordable)`; raises if 0. Budget/contacts decremented identically to the scorer. `pilot_history` omits filters (`:183-193`). |
| Baseline | `PARTICIPANT_GUIDE.md:101-103` | 150 641 084 = `customer_profile.predicted_arpu.sum()` (verified: 23 441 rows, 150 641 084.25). |

## 2. What a hidden effect model can vary

Everything passed into `make_environment(...)` / `score_campaigns(...)` as a parameter
(`environment.py:93-94`, `scoring_core.py:176-178`):

1. **`impact_model` values** — `arpu_change_pct` and `conversion_rate` per
   `(from, arpu_segment, to)`. The case says they differ "заметно" from history
   (`environment.py:6-7`, `PARTICIPANT_GUIDE.md:56-59`), and that a no-exploration strategy
   earns ~15× less than an oracle (`PARTICIPANT_GUIDE.md:64-65`).
2. **`impact_model` coverage** — which keys exist. The mock has 451 keys built from history
   (`mock_environment.py:38-53`); hidden may cover more/other transitions.
3. **`fallback_predict`** for missing keys — mock uses a tariff-price-difference rule
   (`mock_environment.py:56-62`); hidden rule is unknown.
4. **`fallback_conversion`** — derived as the median `conversion_rate` of whatever model is
   passed (`scoring_core.py:186`, `environment.py:105`).
5. **Conversion rates high enough to hit the cap** — in the mock the max is 0.697, so
   `0.697 × 1.2 < 1` and the cap never binds; the hidden model may push `call` into the cap.
6. **Seed** — pilot sampling and noise (`environment.py:106`).

Could vary only by breaking the "same code" claim (not expected):
- `channels` is a parameter of `make_environment` (`environment.py:93,109`) and pilots use
  `env.channels` (`:113,160`), but the scorer uses its hard-coded `CHANNELS`
  (`scoring_core.py:145,197`). A different judge `channels` dict would make pilots and score
  disagree; the case fixes the table (`PARTICIPANT_GUIDE.md:105-110`).
- `PER_CUSTOMER_STD` is a module constant (`environment.py:52`), not a parameter.
- The judge's own harness (equivalent of `local_eval.py`) is not public. Ordering
  "pilots first", the `[:10]` cut and whether `validate_strategy` (`scoring_core.py:65-110`,
  raises on >10 rows) is called are inferred from `local_eval.py` only.
- Edge: if a hidden table had duplicate rows per key (e.g. an extra hidden dimension), the
  merges at `scoring_core.py:150-155,171` would duplicate customers per campaign and dedup
  would keep the max. Speculative; nothing indicates it.

Not varied (profile is shared): `customer_profile.csv` is the scored audience
(`PARTICIPANT_GUIDE.md:120`), so segment sizes, `predicted_arpu` and filters behave identically.

## 3. agent.py assumptions: guaranteed vs mock-only

| Assumption (agent.py) | Status | Why |
|---|---|---|
| Effects keyed by `(current_tariff, arpu_segment, target)` (`:17-19`, `_cells` `:91-97`) | **Guaranteed** | Scorer/pilot merge only on these keys (`scoring_core.py:147-155`, `environment.py:114-117`). |
| data/call segments do not change effect size; only partition audiences (`:17-19`, fill-in `:277-303`, split `:307-318`) | **Guaranteed** | Same merge; within a cell the only per-subscriber variation is `predicted_arpu` scaling. Data slices change mass/cost only. |
| Pilot noise `0.804/√n_actual`, Gaussian, unbiased (`:29,190-194`) | **Guaranteed** | `environment.py:52,172`. Agent hard-codes 0.804 rather than importing it — fine while the constant holds. |
| Observed ratio = base × multiplier for sms (`y = obs/0.65`, `:190-191`) | **Guaranteed** for sms/push/ads | The cap can only bind if `conversion_rate × 0.65 > 1`, impossible for rates ≤ 1. |
| Call realises `1 + 0.75×0.2 = 1.15` (`_eff_mult`, `:50-53`) | **Heuristic** | True factor is `min(1.2, 1/cr)` per cell, unobservable from sms pilots. In the mock the cap never binds, so 1.15 *undervalues* call there; in hidden it may undervalue by ≤ 4 % (cap not binding) or overvalue by up to 15 % (`cr → 1`). |
| Pilots count in score; remaining limits already net of pilots (`:227`, guard `:340-347`) | **Guaranteed** | `environment.py:14-15,176-177`; `local_eval.py:46-48`. |
| Final campaigns are disjoint so no double counting (`README.md:111`) | **Guaranteed but incomplete** | Finals are disjoint from each other, but cover whole cells including already-piloted IDs → those pay a second contact while counting once (`scoring_core.py:241-243`). |
| Plan never relies on truncation (`:340-347`) | **Guaranteed** | Sizes recomputed with the same filters against `env.remaining_*`; matches `scoring_core.py:198-215`. |
| History prior is informative (`_prior` `:100-121`) | **Mock-only** | The mock's truth is built from the same `change_tariff.csv` with the same bins, `≥100` filter and `[-1,3]` clip (`mock_environment.py:38-53` vs `agent.py:102-105`); the prior nearly *is* the mock answer. Mock scores (`README.md:122-123`) are therefore optimistic. |
| Unseen transition → parent mean × near-zero conversion (`:133-137`) | **Mock-only (and mismatched)** | Mock fallback is price-based with median conversion (`mock_environment.py:56-62`); hidden fallback unknown. |
| One uniform prior bias shifts untested hypotheses (`_calibrate` `:209-220`) | **Mock-only fit** | Assumes hidden − history is a common additive shift; the hidden model is free to differ per key. |
| Top-3 targets per cell by prior (`:39,141-142`) | **Mock-only** | If hidden reorders targets, the true best target may never be a hypothesis. |
| `KAPPA=0.5`, pilot caps 25 %, `Z_PILOT`, `PRIOR_SD` (`:30-38`) | **Mock-tuned** | Chosen on mock seeds (`README.md:131-133`). |

## Sources

- `beeline/case.md` (same text as `PARTICIPANT_GUIDE.md`)
- `scoring_core.py`, `environment.py`, `mock_environment.py`, `local_eval.py`,
  `make_submission.py`, `agent.py`, `README.md`, `PARTICIPANT_GUIDE.md`
- Checked locally: `customer_profile.csv` row count and `predicted_arpu` sum; mock
  `impact_model` has 451 unique keys, `conversion_rate` max 0.697.
