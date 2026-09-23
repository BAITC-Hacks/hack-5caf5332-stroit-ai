"""f1v shares: oracle sensitivity + risk-haircut asymmetry. Reads analysis/f1v_runs.csv and the finer-grid oracle
nets printed in analysis/f1v_backtest_output.txt (run f1v_backtest.py first). Run: python3 analysis/f1v_shares.py"""
import contextlib
import io
import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, "..")
sys.path.insert(0, P)
import agent as A            # noqa: E402
import environment           # noqa: E402
import mock_environment as mock  # noqa: E402

R = pd.read_csv(os.path.join(HERE, "f1v_runs.csv"))
txt = open(os.path.join(HERE, "f1v_backtest_output.txt")).read()
fine = {m[0]: float(m[1].replace(",", "")) for m in re.findall(r"\[(S\d)\] oracle .*?finer grid net ([\d,\-]+)", txt)}
print("=== share of oracle: analyst grid vs finer grid (median net / oracle) ===")
for sc, of in fine.items():
    x = R[R.sc == sc]
    oc = x.oracle.iloc[0]
    med = x.groupby("kind").net.median()
    print(f"{sc}: oracle analyst {oc:,.0f} finer {of:,.0f} (+{of / oc - 1:.1%}) | " +
          ", ".join(f"{k} {med[k] / oc:+.3f}->{med[k] / of:+.3f}" for k in ["agent", "noexp", "slope"]))
    ne = x[x.kind == "noexp"].set_index("seed").net
    for k in ["confirm", "slope"]:
        c = x[x.kind == k].set_index("seed").net
        print(f"    {k} beats noexp {(c > ne.loc[c.index]).sum()}/{len(c)}")

# ---- risk-haircut asymmetry and pilot usage, S0 mock ------------------------------------------------------------
prof = pd.read_csv(os.path.join(P, "customer_profile.csv"))
dt = pd.read_csv(os.path.join(P, "data", "dict_tariff.csv"))
M0 = mock._mock_impact_model(pd.read_csv(os.path.join(P, "data", "change_tariff.csv")))
pc, pm, fc = [], [], []
for seed in range(10):
    env, _ = environment.make_environment(prof, M0, dt, mock.CHANNELS, 100_000, 15_000, mock._mock_fallback, seed=seed)
    ag = A.Agent(verbose=False)
    with contextlib.redirect_stdout(io.StringIO()):
        ag.act(env)
    pc.append(sum(r["n"] for r in ag.records)); pm.append(sum(r["cost"] for r in ag.records))
    fc.append(sum(c["n"] for c in ag.plan_detail))
    if seed == 6:
        h = ag.hyps.set_index(["tariff", "seg", "target"])
        for k in [("tariff_8", "HIGH", "tariff_10"), ("tariff_11", "HIGH", "tariff_12"), ("tariff_4", "MID", "tariff_8"),
                  ("tariff_13", "MID", "tariff_8"), ("tariff_12", "MID", "tariff_8")]:
            r = h.loc[k]
            print(f"S0 seed 6 {'/'.join(k)}: tested {r.n_obs > 0} mu {r.mu:+.3f} sd {r.sd:.3f} r_adj {r.r_adj:+.3f} n {r.n} "
                  f"r_adj x mass {r.r_adj * r.mass:,.0f}")
print(f"S0 seeds 0-9 agent pilots: contacts median {np.median(pc):,.0f} money median {np.median(pm):,.0f}; "
      f"final-campaign contacts median {np.median(fc):,.0f} (pilot+final {np.median(np.array(pc) + np.array(fc)):,.0f} of 15,000)")
