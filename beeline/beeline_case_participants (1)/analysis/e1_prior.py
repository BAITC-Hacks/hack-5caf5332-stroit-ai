"""e1 part 5: quality of our agent's prior mean mu0 against the TRUE mock base effect.

CIRCULARITY: the mock effects are built from the same data/change_tariff.csv as the prior, so
history-backed agreement here overstates how good the prior will be on the hidden environment.

Run:  python3 analysis/e1_prior.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e1_oracle as E  # noqa: E402  (chdirs to P, puts P on sys.path)

import agent as agent_mod  # noqa: E402
from mock_environment import make_mock_env  # noqa: E402


def spearman(a, b):
    a, b = pd.Series(a).rank(), pd.Series(b).rank()
    return float(np.corrcoef(a, b)[0, 1])


def main():
    profile, dt, im = E.load()
    eff, _ = E.true_effects(profile, dt, im)
    env, _ = make_mock_env(seed=0)
    a = agent_mod.Agent(verbose=False)
    cells = a._cells(env.customer_profile)
    prior = a._prior(env)
    valid = set(env.tariffs["tariff_plan_code"])
    h3 = a._hypotheses(cells, prior, valid)
    old = agent_mod.TARGETS_PER_CELL
    agent_mod.TARGETS_PER_CELL = 100
    try:
        h = a._hypotheses(cells, prior, valid)
    finally:
        agent_mod.TARGETS_PER_CELL = old
    t = eff.rename(columns={"current_tariff": "tariff", "arpu_segment": "seg"})[
        ["tariff", "seg", "target", "base", "source", "mass"]]
    h = h.merge(t.drop(columns="mass"), on=["tariff", "seg", "target"], how="left")
    assert h["base"].notna().all()
    print(f"=== PART 5: prior mu0 vs true mock base ratio ===")
    print(f"agent cells (n>=20): {len(cells)} covering {int(cells['n'].sum())} subscribers; hypotheses (all targets): {len(h)}")
    for name, d in [("all", h), ("history", h[h.source == "history"]), ("fallback", h[h.source == "fallback"])]:
        print(f"{name:<9} n={len(d):4d}  spearman={spearman(d['mu0'], d['base']):.3f}  "
              f"pearson={np.corrcoef(d['mu0'], d['base'])[0, 1]:.3f}  mean mu0={d['mu0'].mean():+.4f}  "
              f"mean true={d['base'].mean():+.4f}  MAE={np.abs(d['mu0'] - d['base']).mean():.4f}  "
              f"sign agreement={(np.sign(d['mu0']) == np.sign(d['base'])).mean():.1%}")
    within = h.groupby(["tariff", "seg"]).apply(lambda d: spearman(d["mu0"], d["base"]), include_groups=False)
    print(f"within-cell spearman: median {within.median():.3f}, min {within.min():.3f}, "
          f"cells below 0.5: {int((within < 0.5).sum())} of {len(within)}")

    g = h.groupby(["tariff", "seg"])
    top_prior = h.loc[g["mu0"].idxmax()].set_index(["tariff", "seg"])
    top_true = h.loc[g["base"].idxmax()].set_index(["tariff", "seg"])
    mass = cells.set_index(["tariff", "seg"])["mass"]
    agree = top_prior["target"] == top_true["target"]
    print(f"top-1 target agreement: {int(agree.sum())} of {len(agree)} cells; mass-weighted {mass[agree].sum() / mass.sum():.1%}")
    best_true = (top_true["base"].clip(lower=0) * mass).sum()
    got = (top_prior["base"].clip(lower=0) * mass).sum()
    print(f"value (base x mass, positive part) captured by the prior's top target: {got / best_true:.1%}")
    in3 = h3.merge(top_true.reset_index()[["tariff", "seg", "target"]], on=["tariff", "seg", "target"])
    cov3 = set(zip(in3["tariff"], in3["seg"]))
    miss = [k for k in top_true.index if k not in cov3]
    best3 = h3.merge(t, on=["tariff", "seg", "target"]).groupby(["tariff", "seg"])["base"].max()
    lost = ((top_true["base"] - best3.reindex(top_true.index)).clip(lower=0) * mass).sum()
    print(f"true best target inside the agent's top-{old} hypotheses: {len(top_true) - len(miss)} of {len(top_true)} cells; "
          f"base x mass lost by the top-{old} filter {lost:,.0f} of {best_true:,.0f} ({lost / best_true:.1%})")
    for k in miss:
        print(f"  missed: {k[0]}/{k[1]} true best {top_true.loc[k, 'target']} base {top_true.loc[k, 'base']:+.4f} "
              f"({top_true.loc[k, 'source']}), best in top-{old} {best3.get(k, np.nan):+.4f}, mass {mass[k]:,.0f}")
    fb = h[h.source == "fallback"]
    big = fb[fb["base"] > 0.05]
    print(f"fallback combos with true base > 0.05: {len(big)}; their mean mu0 {big['mu0'].mean():+.4f}; "
          f"how many of them are in the agent's top-{old}: "
          f"{len(big.merge(h3[['tariff', 'seg', 'target']], on=['tariff', 'seg', 'target']))}")
    pos = h[h["base"] > 0]
    print(f"spearman among truly positive combos (n={len(pos)}): {spearman(pos['mu0'], pos['base']):.3f}")
    k = agent_mod.KAPPA
    ok = h3[h3["mu0"] - k * h3["sd0"] > 0].drop_duplicates(["tariff", "seg"])
    print(f"risk screen mu0 - {k}*sd0 > 0 (what a zero-pilot plan can deploy): {len(ok)} of {h3[['tariff', 'seg']].drop_duplicates().shape[0]} "
          f"cells, {int(ok['n'].sum()):,} subscribers; combos with TRUE base > {k * agent_mod.PRIOR_SD:.2f}: "
          f"{int((h['base'] > k * agent_mod.PRIOR_SD).sum())} of {len(h)}")


if __name__ == "__main__":
    main()
