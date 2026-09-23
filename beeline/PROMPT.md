# Build the Beeline tariff campaign agent

Work in `beeline/beeline_case_participants (1)/` (path from the repository root). The case specification is `../case.md` from that directory; the same brief is included as `PARTICIPANT_GUIDE.md`. All customer data, tariffs, amounts, and effects in this challenge are synthetic. Build the **working submission**, not just a proposal.

## Goal

Implement an autonomous campaign planning agent for a marketing analyst. Given the current subscriber profile, it must use historical data as a prior, run informative pilot campaigns on the target audience, update its estimates from the noisy results, and return a plan of **1–10 valid campaigns** that seeks to maximize **net ARPU gain** under the shared contact and money limits. The scoring effects on the hidden evaluation differ from those in the local mock. Favor a sound, adaptive decision procedure over constants tuned to the mock score.

Start with a brief user-facing update saying what you are inspecting. Give short, evidence-based progress updates during longer work. Complete implementation and verification before your final response. Make routine implementation decisions yourself; ask only if information essential to the task is unavailable. Keep the final response short and self-contained: what you built, what you ran, the observed results, and any material limitation. Do not describe unrun checks as passed.

## Read before implementing

Inspect these files and the relevant CSV headers, row counts, distributions, and missing values:

- `../case.md` and `PARTICIPANT_GUIDE.md` for the requirements.
- `environment.py` for the **public** `AgentEnvironment` interface and `run_pilot` return shape.
- `scoring_core.py` for public scoring mechanics, validation, order of campaigns, caps, and deduplication.
- `local_eval.py`, `make_submission.py`, and `agent_template.py` for the entry point and verification commands. The template is a deliberately weak baseline.
- `customer_profile.csv`, `feature_dictionary.csv`, `tariff_dictionary.csv`, and the CSVs in `data/`. `data/change_tariff.csv` describes historical tariff changes in a **different subscriber sample**. Do not join its IDs to the target profile as if they were the same cohort.

The Fable guidance motivating this prompt is [Prompting Claude Fable 5.1](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1) and [Prompting Claude Fable 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5). Act once you have enough information, stay within the requested scope, ground status reports in tool results, and finish the work and its checks before stopping. Batch independent reads when useful. Do not add unrelated features or extensive tests.

## Required interface and scoring facts

Create `agent.py` in the participant directory with:

```python
class Agent:
    def act(self, env) -> list[dict]:
        ...
```

At runtime, use only the intended public interface: `env.customer_profile` (a pandas DataFrame of 23,441 target subscribers), `env.tariffs`, `env.channels`, `env.remaining_budget`, `env.remaining_contacts`, `env.pilots_left`, `env.pilot_history`, and `env.run_pilot(...)`. The profile includes `current_tariff`, `arpu_segment`, `data_segment`, `call_segment`, and `predicted_arpu`. The 21 valid targets come from `env.tariffs["tariff_plan_code"]`.

`env.run_pilot(target_tariff=..., channel=..., n_customers=..., filter_arpu_segment=..., filter_data_segment=..., filter_call_segment=..., filter_current_tariff=...)` accepts 10–200 requested customers per pilot. It samples from the filtered target segment, consumes real contact and money budgets, and returns `n_customers`, `cost`, `observed_lift_ratio`, `observed_lift_total`, and remaining limits. The result can contain fewer contacts than requested if the segment or budget is smaller. `env.pilot_history` records results but does **not** include all filters, so retain the hypothesis and filter metadata in your own runtime records when needed. A single pilot is noisy: the supplied environment uses approximate standard error `0.804 / sqrt(actual_n)` for the observed relative lift. Use actual sample sizes in updates; account for uncertainty when deciding whether to explore or deploy.

Return a Python list of 1–10 campaign dictionaries. Each needs a valid `target_tariff` and `channel`; `campaign_name` is useful. Optional filters are `filter_arpu_segment` (`LOW`, `MID`, `HIGH`), `filter_data_segment` (`NON_USER`, `LITE`, `HEAVY`), `filter_call_segment` (`LOW`, `MEDIUM`, `HIGH`), and `filter_current_tariff` (one valid tariff or semicolon-separated valid tariffs). Omitted filters match everyone. Verify every returned segment is nonempty and correctly sized before selecting it.

The limits apply to **pilots and final campaigns together**: at most 20 pilots, 10–200 subscribers per pilot, 5,000 subscribers per final campaign, 15,000 total contacts, and 100,000 monetary units. Channel costs and conversion multipliers are `push` (0, 0.50), `sms` (4, 0.65), `digital_ads` (22, 0.85), and `call` (160, 1.20). Use `env.channels` as the runtime source for these values. The true lift is a *fraction of each subscriber's `predicted_arpu`*, not a fixed amount per subscriber. Net gain is total lift for unique subscribers minus **all** contact costs, including pilots. On overlapping campaigns, a subscriber contributes only their best lift, while every contact still consumes money and reach. The scorer processes campaigns in list order, caps each at 5,000, and truncates further to remaining contact and money budgets; capped selection is by ascending `ID_NUMBER`. Model these effects when sizing, ordering, and comparing candidates. Do not rely on silent truncation to make a plan fit.

## Approach to implement

Use your judgment to choose the simplest robust method that meets the goal. The design should visibly include these behaviors:

1. Build candidate target-tariff and segment hypotheses from the allowed historical files and target profile. Handle sparse historical transitions with shrinkage or a defensible fallback, and guard against unstable ratios from very small prior ARPU. Historical effects are priors, **not** revealed target-audience effects.
2. Allocate pilot size and count according to expected information value, segment size/ARPU, contact cost, and remaining budget. A pilot must actually influence candidate ranking or deployment decisions. Avoid spending the full budget on exploration or trusting one small lucky observation.
3. Update estimated lift and uncertainty from pilot results. Select target tariffs and channels by expected **incremental net gain**, considering subscriber ARPU, channel cost, exposure size, overlap, and risk of a negative result. Use the actual channel multipliers carefully; conversion probabilities may be capped at 1, so simple ratio scaling across channels is only an approximation.
4. Produce a valid final plan with explicit budgets and sizes. Keep the process deterministic for the fixed submission seed: no uncontrolled randomness or nondeterministic external model output. If you use an LLM inside `act`, it must be genuinely involved in a decision, use `os.environ["OPENAI_API_KEY"]` for its key, have a timeout and `try/except` fallback, and leave the agent functional without network access. An LLM is optional; reliable performance matters more than adding one for appearance.
5. Never inspect hidden effects or environment internals at runtime through `__closure__`, `gc`, organizer files, or similar routes. Public scoring code is for understanding mechanics; mock effects are only for local validation. Do not train decisions to fixed mock outcomes.

Prefer a concise implementation with clear functions for historical prior, pilot selection/update, and final campaign selection. Keep runtime under the case's **10-minute** limit including any model calls. Read package data using paths relative to `agent.py` so the agent does not depend on the shell's current directory. Preserve reproducibility for `make_submission.py` (seed 42).

## Deliverables and checks

Create or update only what this submission needs in the participant directory:

- `agent.py` with the working `Agent.act(env)` implementation.
- `submission.csv` generated by **running** `python make_submission.py`, never hand edited.
- `requirements.txt` only if extra dependencies are needed.
- A concise `README.md` explaining the method, inputs, dependencies, run commands, pilot update, fallback behavior, and why the local mock cannot predict the hidden score.

From the participant directory, run `python local_eval.py`, `python local_eval.py --runs 10`, and `python make_submission.py`. Inspect the evaluator output for crashes, rejected or empty campaigns, actual pilot count, budget and contact use, caps, overlap, and the distribution of net results across seeds. Fix any genuine failures. Make sure the submission is reproducible from the final code. Report the observed numbers accurately, including negative or unstable results; do not claim the mock result estimates the hidden score.
