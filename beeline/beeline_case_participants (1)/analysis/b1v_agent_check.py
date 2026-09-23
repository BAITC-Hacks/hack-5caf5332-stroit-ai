"""b1v: check b1 claims against the REAL agent code (agent.py, read-only import) and the local MOCK.

1. Which of the agent's top-3 hypotheses per audience cell are unseen (from,seg,to) combos (b1-04 / b1-15).
2. Mock-only A/B of the two recommended prior fixes (b1-10 K=5, b1-11 (seg,to) parent) vs the submitted agent,
   seeds 0..9 via local_eval.evaluate_agent. Mock truth = raw history cell means, so this is NOT evidence about
   the hidden environment; it only shows whether the fixes move decisions/score at all.
Run from P: python3 analysis/b1v_agent_check.py
"""
import contextlib
import io
import os
import sys

import numpy as np
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
os.chdir(P)                       # local_eval / mock read data via relative paths
sys.path.insert(0, P)
import agent as A                 # noqa: E402
import local_eval                 # noqa: E402

prof = pd.read_csv("customer_profile.csv")
tariffs = pd.read_csv("data/dict_tariff.csv")


class Stub:
    pass


env = Stub()
env.tariffs = tariffs
ag = A.Agent(verbose=False)
cells = ag._cells(prof)
Pp = ag._prior(env)
h = ag._hypotheses(cells, Pp, set(tariffs["tariff_plan_code"]))
seen = set(Pp["m3"].index)
h["seen"] = [(t, s, g) in seen for t, s, g in zip(h.tariff, h.seg, h.target)]
tot = cells["mass"].sum()
print(f"agent hypotheses {len(h)} in {len(cells)} cells; unseen combos among them {int((~h.seen).sum())}")
top1 = h.groupby(["tariff", "seg"]).head(1)
u1 = top1[~top1.seen]
print(f"cells whose TOP-1 hypothesis is an unseen combo: {len(u1)}, mass share {u1['mass'].sum() / tot:.4f}")
print(u1[["tariff", "seg", "target", "n", "mu0", "sd0"]].to_string(index=False))
print("mu0 of unseen hypotheses: median %.4f max %.4f" % (h.loc[~h.seen, "mu0"].median(), h.loc[~h.seen, "mu0"].max()))
n_combo = len(cells) * (len(tariffs) - 1)
n_seen_combo = sum(1 for t, s in zip(cells.tariff, cells.seg) for g in tariffs["tariff_plan_code"] if (t, s, g) in seen)
print(f"seen hypotheses {int(h.seen.sum())}; seen audience combos {n_seen_combo}, of which never kept as hypotheses "
      f"{n_seen_combo - int(h.seen.sum())}; audience combos {n_combo}, never hypotheses {n_combo - len(h)} ({(n_combo - len(h)) / n_combo:.4f}); "
      f"unseen combos never hypotheses {n_combo - n_seen_combo - int((~h.seen).sum())} ({(n_combo - n_seen_combo - int((~h.seen).sum())) / n_combo:.4f})")


class SegToAgent(A.Agent):
    """Same agent, prior cell means shrunk toward (seg,to) instead of (from,to); unseen combos get the (seg,to) mean."""

    def _prior(self, env):
        base = super()._prior(env)
        ct = pd.read_csv(os.path.join(A.HERE, "data", "change_tariff.csv"))
        ct = ct[ct["AVG_ARPU_PREV_3M"] >= 100].copy()
        ct["seg"] = pd.cut(ct["AVG_ARPU_PREV_3M"], A.ARPU_BINS, labels=A.ARPU_LABELS).astype(str)
        ct["pct"] = ((ct["AVG_ARPU_NEXT_3M"] - ct["AVG_ARPU_PREV_3M"]) / ct["AVG_ARPU_PREV_3M"]).clip(-1, 3)
        f, t, K = "tariff_plan_code_from", "tariff_plan_code_to", A.SHRINK_K
        g0 = ct["pct"].mean()
        g1 = ct.groupby(t)["pct"].agg(["sum", "size"])
        m1 = (g1["sum"] + K * g0) / (g1["size"] + K)
        g2 = ct.groupby(["seg", t])["pct"].agg(["sum", "size"])
        m2 = (g2["sum"] + K * m1.reindex(g2.index.get_level_values(1)).values) / (g2["size"] + K)
        g3 = ct.groupby([f, "seg", t])["pct"].agg(["sum", "size"])
        m3 = (g3["sum"] + K * m2.reindex(list(zip(g3.index.get_level_values(1), g3.index.get_level_values(2)))).values) / (g3["size"] + K)
        m3, n3, conv = dict(m3), dict(g3["size"]), dict(base["conv"])
        for tf in prof["current_tariff"].dropna().unique():
            for sg in A.ARPU_LABELS:
                N = base["n_from_seg"].get((tf, sg), 0)
                for tg in tariffs["tariff_plan_code"]:
                    if tg != tf and (tf, sg, tg) not in m3:
                        m3[(tf, sg, tg)] = m2.get((sg, tg), m1.get(tg, g0))
                        n3[(tf, sg, tg)] = 0            # -> PRIOR_SD_FALLBACK, as for unseen
                        conv[(tf, sg, tg)] = 0.5 / (N + 0.5 * base["n_targets"]) if N > 0 else base["conv_median"]
        return dict(base, m3=pd.Series(m3), n3=pd.Series(n3), conv=pd.Series(conv))


def run(make, seeds, k=None):
    out = []
    old = A.SHRINK_K
    if k is not None:
        A.SHRINK_K = k
    try:
        for s in seeds:
            with contextlib.redirect_stdout(io.StringIO()):
                r = local_eval.evaluate_agent(make(), seed=s, verbose=False)
            out.append(r["net_arpu_gain"])
    finally:
        A.SHRINK_K = old
    return np.array(out)


seeds = range(10)
res = {"agent K=15 (submitted)": run(lambda: A.Agent(verbose=False), seeds),
       "agent K=5": run(lambda: A.Agent(verbose=False), seeds, k=5),
       "(seg,to) parent K=15": run(lambda: SegToAgent(verbose=False), seeds)}
print("\nMOCK net by seed 0..9:")
for name, v in res.items():
    print(f"  {name:<24} median {np.median(v):,.0f} mean {v.mean():,.0f} min {v.min():,.0f} max {v.max():,.0f} | "
          + " ".join(f"{x:,.0f}" for x in v))
b = res["agent K=15 (submitted)"]
for name in list(res)[1:]:
    dlt = res[name] - b
    print(f"  {name} minus submitted: mean {dlt.mean():,.0f}, median {np.median(dlt):,.0f}, better in {int((dlt > 0).sum())} of {len(dlt)} seeds")
