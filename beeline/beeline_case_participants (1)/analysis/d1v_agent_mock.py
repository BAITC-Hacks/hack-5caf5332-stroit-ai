"""d1v: agent hypothesis coverage of unseen targets, mock signal sizes vs pilot noise,
avoidable pilot duplication via sub-slices, outlier slice. Deterministic.
Run: python3 analysis/d1v_agent_mock.py
"""
import math
import os
import sys

sys.dont_write_bytecode = True
import numpy as np
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, P)
from agent import Agent  # noqa: E402  (read-only; only its pure prior/hypothesis helpers are called)

prof = pd.read_csv(os.path.join(P, "customer_profile.csv"))
dt = pd.read_csv(os.path.join(P, "data", "dict_tariff.csv"))
ct = pd.read_csv(os.path.join(P, "data", "change_tariff.csv"))
price = dt.set_index("tariff_plan_code")["price_tariff"]
medp = float(price.median())
MASS = prof.predicted_arpu.sum()


def Phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


class Stub:
    tariffs = dt


never_to = set(dt.tariff_plan_code) - set(ct.tariff_plan_code_to)
ag = Agent(verbose=False)
cells = ag._cells(prof)
Pr = ag._prior(Stub())
h = ag._hypotheses(cells, Pr, set(dt.tariff_plan_code))
unseen_key = [(t, s, g) not in Pr["m3"].index for t, s, g in zip(h.tariff, h.seg, h.target)]
h["unseen"] = unseen_key
print(f"agent cells={len(cells)} hypotheses kept={len(h)}; with unseen (from,seg,to)={int(h.unseen.sum())}; "
      f"with never-target tariff={int(h.target.isin(never_to).sum())}")
print(f"  distinct targets among hypotheses={h.target.nunique()}: {sorted(h.target.unique(), key=lambda s: int(s[7:]))}")
print(f"  mass share of cells having >=1 unseen hypothesis="
      f"{100 * h[h.unseen].drop_duplicates(['tariff', 'seg']).mass.sum() / MASS:.2f}%")
print(f"  unseen hypotheses mu0 range=[{h[h.unseen].mu0.min():+.4f}, {h[h.unseen].mu0.max():+.4f}] sd0={h[h.unseen].sd0.unique()}")
print(f"  seen hypotheses mu0 median={h[~h.unseen].mu0.median():+.4f}")
row = h[(h.tariff == "tariff_8") & (h.seg == "HIGH")][["target", "mu0", "sd0", "unseen"]]
print("  tariff_8/HIGH hypotheses:\n", row.round(4).to_string(index=False))

# ---------------- mock: best target per cell, signal vs pilot noise
m = ct.copy()
m["seg"] = pd.cut(m.AVG_ARPU_PREV_3M, [-np.inf, 1000, 5000, np.inf], labels=["LOW", "MID", "HIGH"]).astype(str)
m = m[m.AVG_ARPU_PREV_3M >= 100].copy()
m["pct"] = ((m.AVG_ARPU_NEXT_3M - m.AVG_ARPU_PREV_3M) / m.AVG_ARPU_PREV_3M).clip(-1, 3)
mm = m.groupby(["tariff_plan_code_from", "seg", "tariff_plan_code_to"]).agg(pct=("pct", "mean"), cnt=("pct", "size"))
mm["conv"] = mm.cnt / mm.groupby(level=[0, 1]).cnt.transform("sum")
conv_med = float(mm.conv.median())
rows = []
for _, c in cells.iterrows():
    best = None
    for tgt in dt.tariff_plan_code:
        if tgt == c.tariff:
            continue
        key = (c.tariff, c.seg, tgt)
        if key in mm.index:
            r, fb = mm.loc[key, "pct"] * mm.loc[key, "conv"], False
        else:
            r, fb = float(np.clip(0.4 * (price[tgt] - price[c.tariff]) / medp, -1, 3)) * conv_med, True
        if best is None or r > best[0]:
            best = (r, tgt, fb)
    rows.append(dict(tariff=c.tariff, seg=c.seg, n=c.n, mass=c.mass, r=best[0], tgt=best[1], fallback=best[2]))
b = pd.DataFrame(rows)
w = b.mass / b.mass.sum()
print(f"\nmock best-target base lift r per cell (n>=20 cells={len(b)}): mass-weighted mean={float((w * b.r).sum()):.4f}; "
      f"quantiles 10/50/90 (unweighted)={b.r.quantile([.1, .5, .9]).round(4).tolist()}")
print(f"  mass share of cells whose best mock target is an unseen (fallback) target={100 * b[b.fallback].mass.sum() / b.mass.sum():.2f}%; "
      f"count={int(b.fallback.sum())}; their targets={b[b.fallback].tgt.value_counts().to_dict()}")
b["obs_sms"] = 0.65 * b.r
b["pwrong200"] = [Phi(-o * math.sqrt(200) / 0.804) for o in b.obs_sms]
print(f"  observed via sms: mass-weighted mean={float((w * b.obs_sms).sum()):.4f}; "
      f"mass-weighted P(wrong sign @n=200)={float((w * b.pwrong200).sum()):.4f}; "
      f"share of mass with obs_sms>=0.099 (brief's 'moderate')={100 * b[b.obs_sms >= 0.099].mass.sum() / b.mass.sum():.2f}%")
print(b.sort_values("mass", ascending=False).head(8)[["tariff", "seg", "n", "tgt", "fallback", "r", "obs_sms", "pwrong200"]]
      .round(4).to_string(index=False))

pos = b[b.r > 0]
print(f"  cells with a positive best target: {len(pos)}/{len(b)}, subscribers={int(pos.n.sum())}, "
      f"mass share of all cells={100 * pos.mass.sum() / b.mass.sum():.2f}%; "
      f"non-positive cells: {b[b.r <= 0][['tariff', 'seg', 'n']].sort_values('n', ascending=False).head(5).values.tolist()}")
fb18 = float(np.clip(0.4 * (price['tariff_18'] - price['tariff_8']) / medp, -1, 3)) * conv_med
fb14 = float(np.clip(0.4 * (price['tariff_14'] - price['tariff_8']) / medp, -1, 3)) * conv_med
print(f"  mock fallback r for tariff_8/HIGH: ->tariff_18={fb18:.5f} (P wrong@200 via sms={Phi(-0.65 * fb18 * math.sqrt(200) / 0.804):.4f}); "
      f"->tariff_14={fb14:.5f} (P wrong={Phi(-0.65 * fb14 * math.sqrt(200) / 0.804):.4f})")

# tariff_9 inflow composition
h9 = m[m.tariff_plan_code_to == "tariff_9"]
print(f"history into tariff_9 (PREV>=100): n={len(h9)} mean={h9.pct.mean():+.4f}; excluding from tariff_1: "
      f"n={(h9.tariff_plan_code_from != 'tariff_1').sum()} mean={h9[h9.tariff_plan_code_from != 'tariff_1'].pct.mean():+.4f}; "
      f"from tariff_1 mean={h9[h9.tariff_plan_code_from == 'tariff_1'].pct.mean():+.4f}")
tos = m.groupby("tariff_plan_code_to").pct.agg(["size", "mean"]).sort_values("mean", ascending=False)
print("history mean pct by target (top 4):", tos.head(4).round(4).to_dict("index"))

# ---------------- pilot duplication avoidable via sub-slices
print("\nsub-slices of the 7 biggest cells with 60-200 subscribers (pilot whole slice, deploy complement):")
top = prof.groupby(["current_tariff", "arpu_segment"]).size().sort_values(ascending=False).head(7)
for (t, s), n in top.items():
    c = prof[(prof.current_tariff == t) & (prof.arpu_segment == s)]
    d = c.data_segment.value_counts(dropna=False).to_dict()
    k = c.call_segment.value_counts(dropna=False).to_dict()
    dk = c.groupby(["data_segment", "call_segment"]).size()
    print(f"  {t}/{s} n={n}: data={d} call={k} (data,call) slices in [60,200]={int(((dk >= 60) & (dk <= 200)).sum())} "
          f"sizes={sorted(dk[(dk >= 60) & (dk <= 200)].tolist())}")

# campaigns if the top-7-cell fill is merged per arpu_segment
cm = prof.groupby(["current_tariff", "arpu_segment"]).agg(n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum"))
cm = cm.sort_values("mass", ascending=False).head(7).copy()
cm.iloc[-1, cm.columns.get_loc("n")] = 15000 - int(cm.n.iloc[:-1].sum())
print(f"top-7 fill per-seg n={cm.groupby(level=1).n.sum().to_dict()} -> merged campaigns="
      f"{int(np.ceil(cm.groupby(level=1).n.sum() / 5000).sum())}")

# ---------------- outlier slice
o = prof.loc[prof.predicted_arpu.idxmax()]
for keys in [["current_tariff", "arpu_segment", "data_segment", "call_segment"],
             ["current_tariff", "arpu_segment", "call_segment"], ["current_tariff", "arpu_segment", "data_segment"]]:
    sl = prof[np.logical_and.reduce([prof[k] == o[k] for k in keys])]
    n, mass = len(sl), sl.predicted_arpu.sum()
    gross = 0.1 * 0.35 * mass
    opp = 138 * n * (10.4957 + 1)   # money shadow at r=0.1 from d1v_verify: d(gross)/dB = lam + 1
    print(f"outlier slice {'/'.join(str(o[k]) for k in keys)}: n={n} mass={mass:,.0f}; at r=0.1 ads->call gross gain="
          f"{gross:,.0f} vs opportunity cost of {138 * n:,} money={opp:,.0f}")
print(f"outlier alone: gross gain={0.1 * 0.35 * o.predicted_arpu:,.1f} vs opportunity={138 * 11.4957:,.1f}")
