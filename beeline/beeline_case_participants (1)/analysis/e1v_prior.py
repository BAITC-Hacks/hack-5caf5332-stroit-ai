"""e1v: prior quality vs the true mock effect (verifier for e1-11/e1-12) + what the brief's pilot error rates imply.

Re-implements the agent's hierarchical-shrinkage prior from raw change_tariff.csv (asserting it
equals agent._hypotheses), then compares it with the true mock base effect.

Run:  python3 analysis/e1v_prior.py
"""
import math
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, P)
os.chdir(P)
from e1v_oracle import setup  # noqa: E402


def my_prior(ct, dt, prof):
    K = 15
    d = ct[ct.AVG_ARPU_PREV_3M >= 100].copy()
    prev = d.AVG_ARPU_PREV_3M
    d["seg"] = np.where(prev <= 1000, "LOW", np.where(prev <= 5000, "MID", "HIGH"))
    d["pct"] = ((d.AVG_ARPU_NEXT_3M - prev) / prev).clip(-1, 3)
    f, t = "tariff_plan_code_from", "tariff_plan_code_to"
    g0 = d.pct.mean()
    s1 = d.groupby(t).pct.agg(["sum", "size"])
    m1 = ((s1["sum"] + K * g0) / (s1["size"] + K)).to_dict()
    s2 = d.groupby([f, t]).pct.agg(["sum", "size"])
    m2 = {k: (r["sum"] + K * m1[k[1]]) / (r["size"] + K) for k, r in s2.iterrows()}
    s3 = d.groupby([f, "seg", t]).pct.agg(["sum", "size"])
    m3 = {k: (r["sum"] + K * m2[(k[0], k[2])]) / (r["size"] + K) for k, r in s3.iterrows()}
    nfs = d.groupby([f, "seg"]).size().to_dict()
    conv = {k: (r["size"] + 0.5) / (nfs[(k[0], k[1])] + 0.5 * len(dt)) for k, r in s3.iterrows()}
    conv_med = float(np.median(list(conv.values())))
    cells = (prof.dropna(subset=["current_tariff", "arpu_segment", "predicted_arpu"])
             .groupby(["current_tariff", "arpu_segment"]).agg(n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum")))
    cells = cells[cells.n >= 20]
    rows = []
    for (cur, seg), c in cells.iterrows():
        for tg in sorted(dt.tariff_plan_code):
            if tg == cur:
                continue
            k = (cur, seg, tg)
            if k in m3:
                mu, sd = m3[k] * conv[k], (0.30 if s3.loc[k, "size"] >= 5 else 0.40)
            else:
                pct = m2.get((cur, tg), m1.get(tg, g0))
                N = nfs.get((cur, seg), 0)
                mu, sd = pct * (0.5 / (N + 0.5 * len(dt)) if N > 0 else conv_med), 0.40
            rows.append(dict(tariff=cur, seg=seg, target=tg, n=int(c.n), mass=float(c.mass), mu0=mu, sd0=sd))
    return pd.DataFrame(rows)


def spear(a, b):
    return float(np.corrcoef(pd.Series(a).rank(), pd.Series(b).rank())[0, 1])


def Phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def main():
    ct, dt, prof, E = setup()
    h = my_prior(ct, dt, prof)
    import agent as A
    a = A.Agent(verbose=False)
    from mock_environment import make_mock_env
    env, _ = make_mock_env(seed=0)
    h3a = a._hypotheses(a._cells(env.customer_profile), a._prior(env), set(env.tariffs.tariff_plan_code))
    h3 = (h.sort_values(["tariff", "seg", "mu0", "target"], ascending=[True, True, False, True])
          .groupby(["tariff", "seg"]).head(3).reset_index(drop=True))
    assert (h3[["tariff", "seg", "target"]].values == h3a[["tariff", "seg", "target"]].values).all()
    assert np.allclose(h3.mu0.values, h3a.mu0.values) and np.allclose(h3.sd0.values, h3a.sd0.values)
    print(f"my prior == agent prior on its {len(h3a)} top-3 hypotheses (targets, mu0, sd0 identical)")

    t = E.rename(columns={"cur": "tariff", "tgt": "target"})[["tariff", "seg", "target", "base", "src"]]
    h = h.merge(t, on=["tariff", "seg", "target"], how="left")
    assert h.base.notna().all()
    print(f"agent cells {h[['tariff', 'seg']].drop_duplicates().shape[0]}, combos {len(h)}")
    for name, d in [("all", h), ("history", h[h.src == "history"]), ("fallback", h[h.src == "fallback"])]:
        print(f"  {name:<8} n={len(d):4d} spearman {spear(d.mu0, d.base):.3f}")
    w = h.groupby(["tariff", "seg"]).apply(lambda d: spear(d.mu0, d.base), include_groups=False)
    print(f"within-cell spearman median {w.median():.3f}")
    g = h.groupby(["tariff", "seg"])
    tp, tt = h.loc[g.mu0.idxmax()].set_index(["tariff", "seg"]), h.loc[g.base.idxmax()].set_index(["tariff", "seg"])
    agree = (tp.target == tt.target)
    mass = tt["mass"]
    best = (tt.base.clip(lower=0) * mass).sum()
    got = (tp.base.clip(lower=0) * mass).sum()
    print(f"top-1 agreement {int(agree.sum())} of {len(agree)}; value captured {got / best:.1%}")
    h3m = h3.merge(t, on=["tariff", "seg", "target"])
    in3 = h3m.merge(tt.reset_index()[["tariff", "seg", "target"]], on=["tariff", "seg", "target"])
    b3 = h3m.groupby(["tariff", "seg"]).base.max()
    lost = ((tt.base - b3.reindex(tt.index)).clip(lower=0) * mass).sum()
    print(f"top-3 recall {len(in3)} of {len(tt)}; base x mass lost {lost:,.0f} of {best:,.0f} ({lost / best:.1%})")

    print("\n--- brief's pilot error rates (n=30: ~1 in 4; n=200: ~1 in 25) ---")
    mu = -0.804 / math.sqrt(30) * (-0.6744897501960817)   # Phi^-1(0.25) = -0.67449
    print(f"implied 'moderately profitable' observed lift ratio {mu:.4f}; check P(obs<0 | n=200) = {Phi(-mu * math.sqrt(200) / 0.804):.4f}")
    sms = E.base * 0.65
    print(f"mock combos with observed sms ratio >= {mu:.3f}: {int((sms >= mu).sum())} of {len(E)}; "
          f"median positive observed sms ratio {sms[sms > 0].median():.4f}")
    hi = E[E.seg == "HIGH"]
    mx = hi.base.max() * 0.65
    print(f"best HIGH combo observed sms ratio {mx:.4f}: P(n=200 sms pilot reads it negative) = {Phi(-mx * math.sqrt(200) / 0.804):.3f}")


if __name__ == "__main__":
    main()
