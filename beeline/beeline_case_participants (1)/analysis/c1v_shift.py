"""c1v: re-derive c1-07 (segment rules), c1-11 (covariate shift), c1-12 (cell coverage); boundary checks."""
import os
import numpy as np
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ct = pd.read_csv(os.path.join(P, "data", "change_tariff.csv"))
am = pd.read_csv(os.path.join(P, "data", "arpu_monthly.csv"))
tr = pd.read_csv(os.path.join(P, "data", "traffic.csv"))
pr = pd.read_csv(os.path.join(P, "customer_profile.csv"))
Q2 = ["2026-07-01", "2026-08-01", "2026-09-01"]


def seg3(v, a, b, labs, left_strict=True):
    # left_strict: v<a -> labs[0], v<=b -> labs[1]; else v<=a, v<=b (pd.cut style)
    lo = v < a if left_strict else v <= a
    out = np.where(lo, labs[0], np.where(v <= b, labs[1], labs[2]))
    return pd.Series(np.where(v.isna(), None, out), index=v.index)


def dseg(v):
    return pd.Series(np.where(v.isna(), None, np.where(v <= 0, "NON_USER", np.where(v <= 2000, "LITE", "HEAVY"))), index=v.index)


print("=== c1-07 segment rules on profile ===")
ok = pr.data_segment.notna()
for n, v in [("DATA_VOLUME", pr.DATA_VOLUME), ("LTE", pr.LTE_DATA_VOLUME), ("DATA+LTE", pr.DATA_VOLUME + pr.LTE_DATA_VOLUME)]:
    print(f"data from {n}: {(dseg(v)[ok] == pr.data_segment[ok]).mean():.4f}")
print("DATA_VOLUME exactly 2000:", int((pr.DATA_VOLUME == 2000).sum()), " exactly 0:", int((pr.DATA_VOLUME == 0).sum()),
      " in (0,1):", int(((pr.DATA_VOLUME > 0) & (pr.DATA_VOLUME < 1)).sum()))
calls = pr.OUT_LOC_ONNET_MIN + pr.OUT_LOC_OFFNET_MIN
has = pr.DATA_VOLUME.notna()
okc = pr.call_segment.notna()
cs = seg3(calls, 100, 400, ["LOW", "MEDIUM", "HIGH"])
print(f"call ONNET+OFFNET on usage rows: {(cs[has & okc] == pr.call_segment[has & okc]).mean():.4f} n={int((has & okc).sum())}")
print("call_segment for missing usage rows:", pr.call_segment[~has].value_counts(dropna=False).to_dict())
allmin = pr[["OUT_LOC_ONNET_MIN", "OUT_LOC_OFFNET_MIN", "OUT_INTER_MIN", "OUT_LOC_LAND_MIN"]].sum(axis=1)
print(f"call from 4 minute cols (all rows with call_segment): {(seg3(allmin, 100, 400, ['LOW','MEDIUM','HIGH'])[okc] == pr.call_segment[okc]).mean():.4f}")
print(f"call from OFFNET only: {(seg3(pr.OUT_LOC_OFFNET_MIN, 100, 400, ['LOW','MEDIUM','HIGH'])[okc] == pr.call_segment[okc]).mean():.4f}")
oka = pr.arpu_segment.notna()
for strict in [True, False]:
    s = seg3(pr.ARPU_3m_avg, 1000, 5000, ["LOW", "MID", "HIGH"], left_strict=strict)
    print(f"arpu from ARPU_3m_avg (LOW {'<' if strict else '<='}1000): {(s[oka] == pr.arpu_segment[oka]).mean():.4f}")
print("profile ARPU_3m_avg exactly 1000 or 5000:", int(pr.ARPU_3m_avg.isin([1000, 5000]).sum()),
      " history PREV exactly 1000 or 5000:", int(ct.AVG_ARPU_PREV_3M.isin([1000, 5000]).sum()))
print("profile arpu_segment NaN rows ARPU_3m_avg:", pr.ARPU_3m_avg[~oka].tolist())

print("\n=== history features (Jul-Sep traffic means) ===")
use = tr[tr.time_key.isin(Q2)].groupby("ID_NUMBER")[["DATA_VOLUME", "OUT_LOC_ONNET_MIN", "OUT_LOC_OFFNET_MIN"]].mean()
h = ct.drop_duplicates("ID_NUMBER").join(use, on="ID_NUMBER")
h["arpu_segment"] = seg3(h.AVG_ARPU_PREV_3M, 1000, 5000, ["LOW", "MID", "HIGH"])
h["data_segment"] = dseg(h.DATA_VOLUME)
h["call_segment"] = seg3((h.OUT_LOC_ONNET_MIN + h.OUT_LOC_OFFNET_MIN).fillna(0), 100, 400, ["LOW", "MEDIUM", "HIGH"])
print("history subscribers", len(h), " with Jul-Sep traffic", int(h.DATA_VOLUME.notna().sum()))


def tvd(a, b, label, show=4):
    pa, pb = a.fillna("NA").value_counts(normalize=True), b.fillna("NA").value_counts(normalize=True)
    d = pd.concat([pa.rename("hs"), pb.rename("tgt")], axis=1).fillna(0)
    d["diff_pp"] = (d.tgt - d.hs) * 100
    v = 0.5 * d.diff_pp.abs().sum()
    top = d.reindex(d.diff_pp.abs().sort_values(ascending=False).index).head(show)
    print(f"{label}: TVD={v:.2f} pp; top gaps {[(i, round(r.hs, 4), round(r.tgt, 4), round(r.diff_pp, 2)) for i, r in top.iterrows()]}")
    return v


print("\n=== c1-11 covariate shift: all history switchers (as analyst) ===")
tvd(h.tariff_plan_code_from, pr.current_tariff, "tariff")
tvd(h.arpu_segment, pr.arpu_segment, "arpu_segment")
tvd(h.data_segment, pr.data_segment, "data_segment")
tvd(h.call_segment, pr.call_segment, "call_segment")
tvd(h.arpu_segment.fillna("NA") + "|" + h.data_segment.fillna("NA") + "|" + h.call_segment.fillna("NA"),
    pr.arpu_segment.fillna("NA") + "|" + pr.data_segment.fillna("NA") + "|" + pr.call_segment.fillna("NA"), "joint a|d|c")
tvd(h.tariff_plan_code_from + "|" + h.arpu_segment.fillna("NA"), pr.current_tariff.fillna("NA") + "|" + pr.arpu_segment.fillna("NA"), "tariff x arpu")

print("\n=== c1-11 shift vs the population the prior actually uses (PREV>=100, all change rows) ===")
hk = ct[ct.AVG_ARPU_PREV_3M >= 100].copy()
hk["seg"] = pd.cut(hk.AVG_ARPU_PREV_3M, [-np.inf, 1000, 5000, np.inf], labels=["LOW", "MID", "HIGH"]).astype(str)
tvd(hk.seg, pr.arpu_segment, "arpu_segment (prior population)")
tvd(hk.tariff_plan_code_from + "|" + hk.seg, pr.current_tariff.fillna("NA") + "|" + pr.arpu_segment.fillna("NA"), "tariff x arpu (prior population)")

print("\nmedians: history PREV", round(h.AVG_ARPU_PREV_3M.median(), 2), " target ARPU_3m_avg", round(pr.ARPU_3m_avg.median(), 2))
for s in ["HIGH"]:
    print(f"  {s}: history {h.AVG_ARPU_PREV_3M[h.arpu_segment == s].median():.2f} target {pr.ARPU_3m_avg[pr.arpu_segment == s].median():.2f}")
sep = am[am.TIME_KEY == "2026-09-01"].groupby("ID_NUMBER").ARPU_1M.mean()
hr = h.ID_NUMBER.map(sep) / h.AVG_ARPU_PREV_3M.clip(lower=1)
r = pr.ARPU_current / pr.ARPU_3m_avg.clip(lower=1)
print(f"ratio median: history Sep/PREV {hr.median():.4f} (share>1.1 {(hr > 1.1).mean():.4f}); target cur/3m {r.median():.4f} (share>1.1 {(r > 1.1).mean():.4f})")
# a like-for-like analog: next month vs the previous 3 months (Sep vs mean Jun-Aug)
wide = am.groupby(["ID_NUMBER", "TIME_KEY"]).ARPU_1M.mean().unstack()
jja = wide[["2026-06-01", "2026-07-01", "2026-08-01"]].mean(axis=1)
hr2 = (wide["2026-09-01"] / jja.clip(lower=1)).reindex(h.ID_NUMBER)
print(f"history Sep / mean(Jun-Aug) median {hr2.median():.4f} share>1.1 {(hr2 > 1.1).mean():.4f} (n={int(hr2.notna().sum())})")
print("target ARPU_trend mix:", pr.ARPU_trend.value_counts(normalize=True).round(4).to_dict())
print("target cur/3m median by ARPU_trend:", pr.assign(r=r).groupby("ARPU_trend").r.median().round(4).to_dict())

print("\n=== c1-12 target cell coverage (tariff, arpu_segment) ===")
hc = h.groupby(["tariff_plan_code_from", "arpu_segment"]).size()
hc_k = hk.groupby(["tariff_plan_code_from", "seg"]).size()
hc_k.index.names = hc.index.names
pc = pr.groupby(["current_tariff", "arpu_segment"]).size()
pc.index.names = hc.index.names
cov = pd.concat([pc.rename("tgt"), hc.rename("hs"), hc_k.rename("hist_prior")], axis=1).fillna(0)
cov = cov[cov.tgt > 0]
for thr in [0, 20, 50]:
    s = cov.hs <= thr
    s2 = cov.hist_prior <= thr
    print(f"hist<={thr}: target {int(cov.tgt[s].sum())} ({cov.tgt[s].sum() / cov.tgt.sum():.4f}) cells {int(s.sum())} | "
          f"prior-pop hist<={thr}: target {int(cov.tgt[s2].sum())} cells {int(s2.sum())}")
cov["ratio"] = (cov.tgt / cov.tgt.sum()) / (cov.hs / cov.hs.sum())
print(cov.sort_values("tgt", ascending=False).head(8).round(3).to_string())
print("target subscribers with NaN current_tariff or arpu_segment:", int((pr.current_tariff.isna() | pr.arpu_segment.isna()).sum()))
