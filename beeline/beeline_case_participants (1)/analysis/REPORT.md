# Beeline case — data analysis

The provided history is a weak, confounded prior. On the mock, our agent's pilots currently cost
more than they earn. The median historical mover does not gain ARPU (median change −0.2 %,
50.2 % downsell), HIGH-segment movers lose 12.9 % on average, and 62 % of audience
cell × target combinations have no history at all. With pilots switched off, the same agent beats
the submitted one on 10 of 10 mock seeds (median 4.69M vs 3.75M). The reason is placement: 16–18
of its 19 pilots go to HIGH cells whose true effects (~0.01) sit far below a 200-contact sms
pilot's noise (0.0875).

Method: six analyses (audience, history, cohort, economics, mock oracle, stress backtest), each
followed by an independent verifier that recomputed every numeric claim with its own code. Of 97
claims, 67 were confirmed, 23 corrected (the corrected values are used here) and 7 refuted (left
out). Mock results show mechanics and robustness, not the hidden score.

## Audience

Value sits in a few cells: 3 of 63 tariff × ARPU-segment cells hold 51.1 % of the 150.6M
predicted_arpu mass, and 9 cells hold 80 %. tariff_8/HIGH alone holds 24.6 %. No cell exceeds
the 5,000 per-campaign cap (the largest has 4,726 subscribers). Even so, tariff_8/HIGH cannot
share a campaign with any other top-6 HIGH cell.

Every segment label can be rebuilt exactly (100 % agreement):

- arpu_segment = ARPU_3m_avg with thresholds 1,000 / 5,000;
- data_segment = DATA_VOLUME, not LTE_DATA_VOLUME (which matches only 47.3 %);
- call_segment = OUT_LOC_ONNET_MIN + OUT_LOC_OFFNET_MIN.

predicted_arpu, the scorer's weight, is ARPU_3m_avg compressed toward the middle (slope 0.53,
log-log elasticity 0.435). It also contains 2,005 rows copied from ARPU_3m_avg, 1,999 rows
holding one of five constant values, and 103 zeros. As a result, where the prior applies, a LOW
subscriber is worth a median 5.7× their 3-month ARPU. Only 100 rows (0.21 % of mass) have no
tariff or ARPU segment. ID order is almost unrelated to value (Spearman 0.036), so the scorer's
cut at the first 5,000 IDs is harmless. Mass is not lift. In the agent's mock seed-42 plan, HIGH
campaigns earned 26 per contact, against 602 for MID and 1,130 for LOW.

## Tariff-change history

Of the 12,705 moves the agent keeps (PREV ≥ 100), the median relative change is −0.2 % and 50.2 %
are downsells. The clipped mean of +23 % comes from a low-ARPU tail.

| Segment before the move | Movers | Mean change | Median change | Downsell share |
|---|---|---|---|---|
| LOW (<1,000) | 1,799 | +102.2 % | +78.7 % | 41.9 % |
| MID (1,000–5,000) | 6,485 | +25.8 % | +14.8 % | 43.0 % |
| HIGH (>5,000) | 4,421 | −12.9 % | −12.4 % | 64.1 % |

- Regression to the mean: mean change falls from +109 % in the bottom PREV decile to −22 % in the
  top decile. Movers whose ARPU fell by more than 20 % before switching gain +73 %; movers whose
  ARPU was rising gain +10 %.
- Coverage: only 9 of 21 tariffs are ever a destination. 557 of 900 audience cell × target
  combinations (65.7 % of mass) have no history.
- Confounding: within MID, tariff_9 (+47 %) is about equal to tariff_8 (+45 %). Price upsells
  help, but weakly (Spearman 0.18).
- The agent's shrinkage pulls each (from, seg, to) estimate toward a segment-blind (from, to)
  mean, which inflates small HIGH cells by +0.31 on average. A (seg, to) parent roughly halves
  the split-half excess error (0.042 vs 0.079) and, in a mock A/B, raised median net from 3.75M
  to 3.98M (better on 9 of 10 seeds).
- Only cells holding 23 % of mass have a best target with a positive lower bound. The most
  reliable targets are tariff_4/MID → tariff_8 and tariff_13/MID → tariff_8.

## Usage and cohort shift

AVG_ARPU_PREV_3M equals the mean of Jul–Sep 2026 monthly ARPU on every row. Traffic tariffs match
the pre-switch tariff on 99.6 % of moves. The history cohort looks little like the target:

| Dimension | Shift (total variation) | Largest gap, history → target |
|---|---|---|
| Tariff | 48.3 pp | target concentrated in tariff_8/10/4/14 |
| ARPU segment | 29.6 pp (24.6 pp on PREV ≥ 100 rows) | HIGH 29.8 % → 59.4 % |
| Data segment | 21.6 pp | NON_USER 25.9 % → 5.7 % |
| Call segment | 6.3 pp | similar mix |

History also looks more like churn: 9.5 % of movers have PREV = 0, against 3.0 % of the target.
Usage adds no targeting signal. Subscribers who exceed their data package change less (within-cell
−0.07 ± 0.04), and "destination fits usage" vanishes within cells (+0.005 vs −0.020). Within
(from, seg, to) cells, data_segment explains 4 % of residual variance and call_segment is not
significant (p = 0.55). The public scorer keys effects only on (from, arpu_segment, to).

## Tariffs, channels and pilots

At median predicted_arpu (6,238), a contact pays for itself at a base lift of 0.001 via sms, 0.004
via digital_ads and 0.021 via call.

| Channel | Cost per contact | Multiplier | Contacts for 100,000 | Limit that binds |
|---|---|---|---|---|
| push | 0 | 0.50 | 15,000 | reach |
| sms | 4 | 0.65 | 15,000 | reach |
| digital_ads | 22 | 0.85 | 4,545 | money |
| call | 160 | 1.20 | 625 | money |

- With both limits binding, the best mix is the same for any uniform lift from 0.02 to 0.45:
  about 12,800 sms, 2,200 digital_ads and 1 call. Moving from sms to ads buys 4.4× more multiplier
  per unit of money than moving from ads to call. The mix adds only 5–7 % over all-sms on the
  same audience, so choosing cells and targets matters far more than choosing channels.
- Pilots can check a sign, not rank targets. An effect of 0.1 shows the wrong sign 24.8 % of the
  time at n = 30 and 3.9 % at n = 200, which matches the brief. Separating two targets 0.1 apart
  needs 800 subscribers per arm.
- The two tariff files agree. tariff_5–8 are the same product, and 14 of 21 tariffs are
  Pareto-dominated. Final campaigns cannot exclude pilot IDs, so pilots in deployed cells are paid
  for twice.

## Mock upper bound (mock only)

The mock is built from the same history as the prior, so it cannot show what exploration is
worth. The brief says a strategy without exploration earns ~15× less; on the mock the gap is only
1.33×.

| Strategy (mock, seeds 0–9) | Median net | Share of oracle |
|---|---|---|
| Certified LP upper bound | 6,636,080 | 105 % |
| Oracle: known effects, no pilots | 6,290,539 | 100 % |
| Agent planner given the true effects | 5,681,741 | 90 % |
| Agent with pilots switched off | 4,690,960 | 75 % |
| Agent as submitted | 3,745,392 | 60 % |
| agent_template baseline | −357,948 | −6 % |

At seed 42 the agent is 1.94M short of the oracle. Missing coverage is the largest loss: the
mu − 0.5·sd risk screen drops 11 cells worth about 0.94M. Channel choice comes next, and pilots
account for about 20 %. 16 of 19 pilots went to HIGH cells whose true effects are at most 0.031,
below a 200-contact sms pilot's noise of 0.0875, yet one pilot gets 92 % of the weight in the
update. The agent left 2,229 contacts and 28,630 money unused; upgrading sms campaigns to
digital_ads with that money would add about 0.10M.

## Robustness backtest (mock only)

8 perturbed mock worlds × 10 seeds. Median net:

| World | Agent as submitted | Agent, no pilots | Confirm-first + slope (counterfactual) | Agent positive seeds |
|---|---|---|---|---|
| S0 mock | 3,745,392 | 4,690,960 | 4,342,684 | 10/10 |
| S1 effects ×0.5 | 1,871,230 | 2,296,190 | 1,464,235 | 10/10 |
| S2 effects ×2 | 6,731,942 | 9,480,501 | 9,915,746 | 10/10 |
| S3 downsell shift | 2,811,390 | 3,848,092 | 2,971,271 | 10/10 |
| S4 ranking reversed | 26,082 | 629,039 | −531,258 | 6/10 |
| S5 permuted | 2,684,977 | 2,144,077 | 4,606,136 | 10/10 |
| S6 conversion ×3 | 10,336,078 | 11,389,846 | 13,407,754 | 10/10 |
| S7 sign flip | −3,620,003 | −4,888,120 | −556,430 | 0/10 |

In S0–S4 the agent without pilots beats the submitted agent on 10 of 10 seeds. 86–94 % of pilots
land on HIGH cells with near-zero priors, where a 200-contact sms pilot has a median |z| of only
0.06–0.33. The LOW/MID → tariff_8/9 units that drive the plan (|z| ≈ 3 per pilot) are never tested,
so the additive calibration (bias −0.02 to −0.05) cannot detect a scale or sign error. Spending the
first 6 pilots on plan-driving units beat the agent on 7–9 of 10 seeds in most worlds. Adding a
multiplicative slope calibration beat it on 10 of 10 seeds in the ×2, conversion ×3 and sign-flip
worlds, but did worse under ×0.5 effects and reversed rankings. Caveats: S0–S3 favour
no-exploration by construction, S5 rests on one permutation draw, and the oracle-lite reference in
f1_robustness.py understates the optimum by 6–48 %.

## Implications for the agent

Ranked by strength of evidence. None of these changes has been applied to agent.py yet.

1. Point the first pilots at the units the plan depends on (tariff_4/MID→8, tariff_13/MID→8,
   tariff_8/LOW→9, tariff_12/MID→8, tariff_14/LOW→9) before exploring big HIGH cells. On the plain
   mock, confirm-first beat the agent on 7 of 10 seeds and raised the worst seed from 1.21M to
   2.76M.
2. Scale the prior sd to the effect size, by segment, instead of a flat 0.30. True HIGH effects are
   about 0.01, so one noisy pilot now gets 92 % weight and pulls false positives into the plan.
3. Shrink toward a (seg, to) parent instead of (from, to): half the out-of-sample prior error;
   mock median 3.98M (better on 9 of 10 seeds).
4. Replace the additive calibration with a multiplicative slope from confirm pilots, plus a loss
   gate when pilots contradict the prior.
5. Relax the risk screen for untested cells (mu − 0.15) and fill spare reach with free push on
   cells whose posterior is positive (the no-pilot plan leaves 10,320 contacts idle).
6. Keep a current_tariff filter on every campaign, never target tariff_1 (−34 % in history), keep
   the Lagrangian channel allocation.

Do not cut pilots just because of mock scores: the mock cannot show what exploration is worth.

## Reproduce

Run from the participant directory with Python 3, pandas and numpy only. Analyst scripts are the
evidence; `*v_*` scripts re-derive the same numbers independently. Every script prints what it
reports.

| Section | Analyst scripts | Independent re-derivation |
|---|---|---|
| Audience | a1_profile.py | a1v_verify.py, a1v_mechanics.py |
| History | b1_history.py, b1_reliability.py | b1v_core.py, b1v_reliability.py, b1v_agent_check.py |
| Usage and cohort | c1_coverage.py, c1_shift.py, c1_package_fit.py, c1_shrink_parent.py | c1v_coverage.py, c1v_shift.py, c1v_package.py, c1v_shrink.py |
| Tariffs, channels, pilots | d1_economics.py | d1v_verify.py, d1v_agent_mock.py, d1v_pilots_run.py |
| Mock upper bound | e1_oracle.py, e1_baselines.py, e1_prior.py | e1v_effects.py, e1v_oracle.py, e1v_rescore.py, e1v_runs.py, e1v_prior.py |
| Robustness backtest | f1_robustness.py (writes f1_runs.csv) | f1v_backtest.py, f1v_extra.py, f1v_shares.py |

Example: `python3 analysis/b1_history.py`. The backtest runs 560 agent evaluations and takes a few
minutes.
