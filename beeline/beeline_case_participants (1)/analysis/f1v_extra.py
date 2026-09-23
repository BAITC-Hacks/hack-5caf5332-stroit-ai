"""f1v extra checks: things the f1 backtest did not test. Reuses the scenario/scoring helpers of f1v_backtest
by import-free copy of the minimum needed. Deterministic. Run: python3 analysis/f1v_extra.py"""
import contextlib
import io
import os
import sys

import numpy as np
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, P)
import agent as A            # noqa: E402
import agent_template        # noqa: E402
import environment           # noqa: E402
import mock_environment as mock  # noqa: E402
from scoring_core import CHANNELS, score_campaigns, sanitize_campaigns  # noqa: E402

prof = pd.read_csv(os.path.join(P, "customer_profile.csv"))
dt = pd.read_csv(os.path.join(P, "data", "dict_tariff.csv"))
ct = pd.read_csv(os.path.join(P, "data", "change_tariff.csv"))
BASE = prof["predicted_arpu"].sum()
M0 = mock._mock_impact_model(ct)
M0 = M0.assign(arpu_segment=M0["arpu_segment"].astype(str))
F0 = mock._mock_fallback
KEYS = set(zip(M0.tariff_plan_code_from, M0.arpu_segment, M0.tariff_plan_code_to))
valid = prof.dropna(subset=["current_tariff", "arpu_segment"])
CELL = valid.groupby(["current_tariff", "arpu_segment"]).agg(n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum"))


def truth(M, F):
    fc = M["conversion_rate"].median()
    lk = {(a, s, b): (p, c) for a, b, s, p, c in M[["tariff_plan_code_from", "tariff_plan_code_to", "arpu_segment",
                                                     "arpu_change_pct", "conversion_rate"]].itertuples(index=False)}
    return {(t, s, b): (lk[(t, s, b)] if (t, s, b) in lk else tuple(map(float, F(t, b, s, dt, fc))))
            for (t, s) in CELL.index for b in dt.tariff_plan_code if b != t}


def lift(tab, k, ch):
    p, c = tab[k]
    return p * min(1.0, c * CHANNELS[ch]["conversion_multiplier"])


def score(camps, M, F):
    if not camps:
        return 0.0
    df = pd.DataFrame(camps)
    for c in ["filter_arpu_segment", "filter_data_segment", "filter_call_segment", "filter_current_tariff", "explicit_ids"]:
        if c not in df:
            df[c] = None
    return score_campaigns(df, prof, M, dt, BASE, F)["net_arpu_gain"]


def run(kind, M, F, seed):
    env, internals = environment.make_environment(prof, M, dt, CHANNELS, 100_000, 15_000, F, seed=seed)
    ag = agent_template.Agent() if kind == "template" else A.Agent(verbose=False)
    old = A.PILOT_MONEY_SHARE
    A.PILOT_MONEY_SHARE = 0.0 if kind == "noexp" else old
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            fin = sanitize_campaigns(ag.act(env), env.tariffs)[:10]
    finally:
        A.PILOT_MONEY_SHARE = old
    return score(internals.executed_pilot_campaigns() + fin, M, F), ag


# (a) S5 is one permutation draw: how much do the S5 conclusions depend on it? --------------------------
print("=== (a) S5 permutation draws (env seeds 0-2) ===")
for ps in [2026, 1, 2, 3, 4]:
    M = M0.assign(arpu_change_pct=np.random.default_rng(ps).permutation(M0.arpu_change_pct.values))
    res = {k: [run(k, M, F0, s)[0] for s in range(3)] for k in ["agent", "noexp", "template"]}
    print(f"perm {ps}: " + " | ".join(f"{k} median {np.median(v):,.0f} min {min(v):,.0f}" for k, v in res.items())
          + f" | template > agent {sum(t > a for t, a in zip(res['template'], res['agent']))}/3, "
            f"agent > noexp {sum(a > n for a, n in zip(res['agent'], res['noexp']))}/3")

# (b) template's fixed hypotheses: S0 and S7 are mirror images ------------------------------------------
print("\n=== (b) template hypotheses: true sms lift ratio in S0 and S7 ===")
cells = prof.groupby(["current_tariff", "arpu_segment"]).size().sort_values(ascending=False).head(4)
t0 = truth(M0, F0)
t7 = truth(M0.assign(arpu_change_pct=-M0.arpu_change_pct), lambda c, t, s, dd, fc: (-F0(c, t, s, dd, fc)[0], fc))
neg0 = nh = 0
for (t, s), n in cells.items():
    for b in ["tariff_8", "tariff_9"]:
        if b != t:
            k = (t, s, b)
            neg0 += lift(t0, k, "sms") < 0; nh += 1
            print(f"  {t}/{s} (n={n}) -> {b}: in-model {k in KEYS}; S0 {lift(t0, k, 'sms'):+.4f} S7 {lift(t7, k, 'sms'):+.4f}")
print(f"  template hypotheses with negative true effect in S0: {neg0} of {nh}")

# (c) fallback exposure: S4 and S5 perturb only in-model rows -----------------------------------------------
print("\n=== (c) fallback exposure of the agent's hypothesis set ===")
ag = A.Agent(verbose=False)
env, _ = environment.make_environment(prof, M0, dt, CHANNELS, 100_000, 15_000, F0, seed=0)
h = ag._hypotheses(ag._cells(env.customer_profile), ag._prior(env), set(env.tariffs.tariff_plan_code))
fb = np.array([(a, b, c) not in KEYS for a, b, c in zip(h.tariff, h.seg, h.target)])
print(f"  hypotheses {len(h)}; resolved by fallback (not in model) {fb.sum()} ({fb.mean():.3f}); "
      f"share of prior mass-weighted value mu0*mass>0 on fallback {(h.mu0 * h.mass)[fb].clip(lower=0).sum() / (h.mu0 * h.mass).clip(lower=0).sum():.3f}")
rv = M0.copy()
for _, grp in rv.groupby(["tariff_plan_code_from", "arpu_segment"]):
    o = grp.arpu_change_pct.sort_values(kind="mergesort")
    rv.loc[o.index, "arpu_change_pct"] = o.values[::-1]
print(f"  S4: model rows whose pct is unchanged by the reversal {(rv.arpu_change_pct == M0.arpu_change_pct).sum()} of {len(M0)}")
hk = list(zip(h.tariff, h.seg, h.target))
t4 = truth(rv, F0)
print(f"  S4: agent hypotheses whose true effect is unchanged vs S0 {sum(t4[k] == t0[k] for k in hk)} of {len(hk)}")
# is the prior's top-1 target per cell still the truth's top-1 in S4?  (ranking by pct x conv, as the agent does)
top_prior = h.sort_values("mu0", ascending=False).drop_duplicates(["tariff", "seg"])
same0 = same4 = 0
for r in top_prior.itertuples():
    cand = [b for b in dt.tariff_plan_code if b != r.tariff]
    b0 = max(cand, key=lambda b: t0[(r.tariff, r.seg, b)][0] * t0[(r.tariff, r.seg, b)][1])
    b4 = max(cand, key=lambda b: t4[(r.tariff, r.seg, b)][0] * t4[(r.tariff, r.seg, b)][1])
    same0 += b0 == r.target; same4 += b4 == r.target
print(f"  prior top target = true top target (pct x conv): S0 {same0}/{len(top_prior)}, S4 {same4}/{len(top_prior)}")

# (d) call channel: would it ever be chosen if money were free? ---------------------------------------------
print("\n=== (d) call channel check ===")
for name, M, F in [("S0", M0, F0), ("S6 conv x3", M0.assign(conversion_rate=M0.conversion_rate * 3), F0)]:
    tab = truth(M, F)
    best_ch = {}
    for (t, s), row in CELL.iterrows():
        vals = {ch: max(lift(tab, (t, s, b), ch) * row.mass - row.n * CHANNELS[ch]["cost_per_contact"]
                        for b in dt.tariff_plan_code if b != t) for ch in CHANNELS}
        best_ch[(t, s)] = max(vals, key=vals.get)
        # value per unit of money of upgrading digital_ads -> call on the best call target
    cnt = pd.Series(best_ch).value_counts()
    ratios = []
    for (t, s), row in CELL.iterrows():
        bc = max((b for b in dt.tariff_plan_code if b != t), key=lambda b: lift(tab, (t, s, b), "call"))
        bd = max((b for b in dt.tariff_plan_code if b != t), key=lambda b: lift(tab, (t, s, b), "digital_ads"))
        inc = lift(tab, (t, s, bc), "call") * row.mass - lift(tab, (t, s, bd), "digital_ads") * row.mass
        ratios.append(inc / (row.n * (160 - 22)))
    print(f"  {name}: best channel per cell with money unconstrained: {cnt.to_dict()}; "
          f"max incremental value per extra money unit, call vs digital_ads: {max(ratios):.2f}")

# (e) effect scale over the hypotheses the agent actually considers (S0) ------------------------------------
print("\n=== (e) S0 true |pct x conv| by segment: all (cell,target) vs agent's top-3 hypotheses ===")
allv = pd.DataFrame([(k[1], abs(p * c)) for k, (p, c) in t0.items()], columns=["seg", "v"])
hv = h.assign(v=[abs(t0[k][0] * t0[k][1]) for k in hk])
print("  all pairs median: " + ", ".join(f"{s} {v:.4f}" for s, v in allv.groupby("seg").v.median().items()))
print("  agent hypotheses median: " + ", ".join(f"{s} {v:.4f}" for s, v in hv.groupby("seg").v.median().items())
      + f"; overall {hv.v.median():.4f}; max LOW/MID {hv[hv.seg != 'HIGH'].v.max():.4f}, max HIGH {hv[hv.seg == 'HIGH'].v.max():.4f}")
print(f"  agent hypotheses median |prior mu0 - true| {np.median(np.abs(h.mu0.values - np.array([t0[k][0] * t0[k][1] for k in hk]))):.4f}")
