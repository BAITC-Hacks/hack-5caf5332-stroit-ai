"""c1v: independent re-derivation of c1-01..c1-06 (coverage, PREV_3M window, zeros, trajectory, rebound, returners)."""
import os
import numpy as np
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ct = pd.read_csv(os.path.join(P, "data", "change_tariff.csv"))
am = pd.read_csv(os.path.join(P, "data", "arpu_monthly.csv"))
tr = pd.read_csv(os.path.join(P, "data", "traffic.csv"))
pr = pd.read_csv(os.path.join(P, "customer_profile.csv"))
M = ["2026-04-01", "2026-05-01", "2026-06-01", "2026-07-01", "2026-08-01", "2026-09-01"]
Q1, Q2 = M[:3], M[3:]


def ci(s):
    return f"{s.mean():.4f} +- {1.96 * s.std(ddof=1) / np.sqrt(len(s)):.4f} (n={len(s)})"


print("=== c1-01 coverage ===")
for n, d in [("ct", ct), ("am", am), ("tr", tr), ("pr", pr)]:
    print(n, "rows", len(d), "ids", d.ID_NUMBER.nunique())
print("ct duplicated IDs", int(ct.ID_NUMBER.duplicated().sum()), "TIME_KEY", ct.TIME_KEY.unique().tolist())
sct, sam, stra, spr = set(ct.ID_NUMBER), set(am.ID_NUMBER), set(tr.ID_NUMBER), set(pr.ID_NUMBER)
print("ct&am", len(sct & sam), round(len(sct & sam) / len(sct), 4), " ct&tr", len(sct & stra), round(len(sct & stra) / len(sct), 4))
print("pr&ct", len(spr & sct), "pr&am", len(spr & sam), "pr&tr", len(spr & stra))
print("am ids not in ct", len(sam - sct), " tr ids not in ct", len(stra - sct))
print("am months", sorted(am.TIME_KEY.unique()), " tr months", sorted(tr.time_key.unique()))
rows_per = am.groupby("ID_NUMBER").size()
mon_per = am.groupby("ID_NUMBER").TIME_KEY.nunique()
print("am IDs with 6 rows", int((rows_per == 6).sum()), " with 6 distinct months", int((mon_per == 6).sum()),
      " with 6 rows but <6 distinct months", int(((rows_per == 6) & (mon_per < 6)).sum()))
print("tr IDs with 6 distinct months", int((tr.groupby("ID_NUMBER").time_key.nunique() == 6).sum()))
print("tr max rows per (ID,month)", int(tr.groupby(["ID_NUMBER", "time_key"]).size().max()))
dev = tr.groupby("ID_NUMBER").DEVICE_ID.nunique()
print("tr share IDs >1 DEVICE_ID", round(float((dev > 1).mean()), 4), " DEVICE_ID NaN rows", int(tr.DEVICE_ID.isna().sum()))

print("\n=== c1-02 PREV_3M window ===")
c = ct.reset_index().rename(columns={"index": "row"})
def rowmean(months):
    return am[am.TIME_KEY.isin(months)].groupby("ID_NUMBER").ARPU_1M.mean()
for name, ms in [("rowmean Jul-Sep", Q2), ("rowmean Aug-Sep", M[4:]), ("rowmean Jun-Aug", M[2:5]),
                 ("rowmean Sep", M[5:]), ("rowmean Apr-Jun", Q1)]:
    est = c.ID_NUMBER.map(rowmean(ms))
    err = (est - c.AVG_ARPU_PREV_3M).abs()
    ok = est.notna()
    print(f"{name}: n_nonnull={int(ok.sum())} exact_share_of_all={(err <= 0.01).mean():.4f} exact_share_nonnull={(err[ok] <= 0.01).mean():.4f}")
# month-collapsed (dup months averaged) then mean over present months
mc = am[am.TIME_KEY.isin(Q2)].groupby(["ID_NUMBER", "TIME_KEY"]).ARPU_1M.mean().groupby("ID_NUMBER").mean()
e = (c.ID_NUMBER.map(mc) - c.AVG_ARPU_PREV_3M).abs()
miss = c[~(e <= 0.01)]
dupid = set(am[am.duplicated(["ID_NUMBER", "TIME_KEY"], keep=False)].ID_NUMBER)
print(f"month-collapsed exact={(e <= 0.01).mean():.4f}, misses={len(miss)}, misses in dup-ID set={int(miss.ID_NUMBER.isin(dupid).sum())}")
dd = am[am.duplicated(["ID_NUMBER", "TIME_KEY"], keep=False)]
print("dup (ID,month) rows", len(dd), "IDs", dd.ID_NUMBER.nunique(), " fully identical dup rows", int(am.duplicated().sum()))
s3 = am[am.TIME_KEY.isin(Q2)].groupby(["ID_NUMBER", "TIME_KEY"]).ARPU_1M.mean().groupby("ID_NUMBER").sum() / 3
e0 = (c.ID_NUMBER.map(s3).fillna(0) - c.AVG_ARPU_PREV_3M).abs()
print(f"sum/3 missing=0 exact={(e0 <= 0.01).mean():.4f}")

print("\n=== c1-03 zeros ===")
print("ARPU_1M zero rows", int((am.ARPU_1M == 0).sum()))
print("zero share by month", am.assign(z=am.ARPU_1M == 0).groupby("TIME_KEY").z.mean().round(4).to_dict())
q2rows = am[am.TIME_KEY.isin(Q2)]
anyzero = q2rows.groupby("ID_NUMBER").ARPU_1M.apply(lambda s: (s == 0).any())
print("ct rows with any zero month Jul-Sep", round(float(c.ID_NUMBER.map(anyzero).fillna(False).mean()), 4))
anyzero_mc = q2rows.groupby(["ID_NUMBER", "TIME_KEY"]).ARPU_1M.mean().eq(0).groupby("ID_NUMBER").any()
print("ct rows with any zero month Jul-Sep (dup months averaged)", round(float(c.ID_NUMBER.map(anyzero_mc).fillna(False).mean()), 4))
print("target ARPU_current==0", round(float((pr.ARPU_current == 0).mean()), 4), " ARPU_3m_avg==0", round(float((pr.ARPU_3m_avg == 0).mean()), 4))
print("PREV==0 share", round(float((ct.AVG_ARPU_PREV_3M == 0).mean()), 4), " PREV<100 share", round(float((ct.AVG_ARPU_PREV_3M < 100).mean()), 4))
print("target ARPU_3m_avg<100 share", round(float((pr.ARPU_3m_avg < 100).mean()), 4),
      " ratio", round(float((ct.AVG_ARPU_PREV_3M < 100).mean() / (pr.ARPU_3m_avg < 100).mean()), 3))
print("NEXT==0 share", round(float((ct.AVG_ARPU_NEXT_3M == 0).mean()), 4),
      " NEXT==0 among PREV>=100", round(float((ct.AVG_ARPU_NEXT_3M[ct.AVG_ARPU_PREV_3M >= 100] == 0).mean()), 4))

print("\n=== c1-04 trajectory ===")
wide = am.groupby(["ID_NUMBER", "TIME_KEY"]).ARPU_1M.mean().unstack()
w = c.join(wide, on="ID_NUMBER")
full = w[M].notna().all(axis=1)
t6 = w[full].copy()
print("ct rows with all 6 months", len(t6), " unique IDs", t6.ID_NUMBER.nunique())
print("mean by month", t6[M].mean().round(1).tolist())
t6["q1"], t6["q2"] = t6[Q1].mean(axis=1), t6[Q2].mean(axis=1)
print("agg ratio q2/q1", round(t6.q2.sum() / t6.q1.sum(), 4))
x = np.arange(6) - 2.5
t6["slope"] = t6[M].to_numpy() @ x / (x ** 2).sum()
print(f"slope mean {t6.slope.mean():.2f} se {t6.slope.std(ddof=1) / np.sqrt(len(t6)):.2f} share>0 {(t6.slope > 0).mean():.4f}")
for to in ["tariff_9", "tariff_1", "tariff_4", "tariff_10", "tariff_8", "tariff_13"]:
    s = t6[t6.tariff_plan_code_to == to]
    print(f"  to {to}: n={len(s)} q1={s.q1.mean():.1f} q2={s.q2.mean():.1f} ratio={s.q2.sum() / s.q1.sum():.4f}")
s9 = t6[(t6.tariff_plan_code_to == "tariff_9")]
s9k = s9[s9.AVG_ARPU_PREV_3M >= 100]
print(f"  to tariff_9 PREV>=100: n={len(s9k)} ratio={s9k.q2.sum() / s9k.q1.sum():.4f}  share PREV<100 among tariff_9 6m rows={(s9.AVG_ARPU_PREV_3M < 100).mean():.4f}")
allk = t6[t6.AVG_ARPU_PREV_3M >= 100]
print(f"  ALL PREV>=100: n={len(allk)} ratio={allk.q2.sum() / allk.q1.sum():.4f}")
# non-switcher control (am IDs not in ct)
ns = wide.loc[wide.index.difference(pd.Index(sorted(sct)))]
nsf = ns[ns[M].notna().all(axis=1)]
print(f"non-ct am IDs with all 6 months: n={len(nsf)} mean by month {nsf[M].mean().round(1).tolist()}"
      f" ratio={nsf[Q2].mean(axis=1).sum() / max(nsf[Q1].mean(axis=1).sum(), 1):.4f}")

print("\n=== c1-05 rebound ===")
t6["pre"] = (t6.q2 - t6.q1) / t6.q1.clip(lower=1)
t6["y"] = ((t6.AVG_ARPU_NEXT_3M - t6.AVG_ARPU_PREV_3M) / t6.AVG_ARPU_PREV_3M).clip(-1, 3)
k = t6[t6.AVG_ARPU_PREV_3M >= 100].copy()
print(f"corr(pre clipped, y) {np.corrcoef(k.pre.clip(-1, 3), k.y)[0, 1]:.4f} n={len(k)}")
k["b"] = np.where(k.pre < -0.2, "DECL", np.where(k.pre > 0.2, "GROW", "STAB"))
k["b_le"] = np.where(k.pre <= -0.2, "DECL", np.where(k.pre >= 0.2, "GROW", "STAB"))
print("boundary rows exactly +-0.2:", int((k.pre.abs() == 0.2).sum()))
for b in ["DECL", "STAB", "GROW"]:
    print(f"  raw {b}: {ci(k.y[k.b == b])}")
# agent-style segmentation (pd.cut right-inclusive) vs brief (<1000)
k["seg"] = pd.cut(k.AVG_ARPU_PREV_3M, [-np.inf, 1000, 5000, np.inf], labels=["LOW", "MID", "HIGH"]).astype(str)
k["cell"] = k.tariff_plan_code_from + "|" + k.seg + "|" + k.tariff_plan_code_to
kk = k[k.groupby("cell").y.transform("size") >= 20].copy()
kk["r"] = kk.y - kk.groupby("cell").y.transform("mean")
print(f"within-cell rows={len(kk)}")
for b in ["DECL", "STAB", "GROW"]:
    print(f"  resid {b}: {ci(kk.r[kk.b == b])}")
t6["seg"] = pd.cut(t6.AVG_ARPU_PREV_3M, [-np.inf, 1000, 5000, np.inf], labels=["LOW", "MID", "HIGH"]).astype(str)
t6["decl"] = t6.pre < -0.2
print("share declining by seg (all 6m rows):", t6.groupby("seg").decl.mean().round(4).to_dict())
print("share declining by seg (PREV>=100):", k.assign(d=k.b == "DECL").groupby("seg").d.mean().round(4).to_dict())
print("n by seg (all, PREV>=100):", t6.seg.value_counts().to_dict(), k.seg.value_counts().to_dict())
# target: ARPU_trend mix by arpu_segment
print("target ARPU_trend share by arpu_segment:")
print(pr.groupby("arpu_segment").ARPU_trend.value_counts(normalize=True).unstack().round(4).to_string())

print("\n=== c1-06 traffic tariff vs from ===")
print("tariff NaN share by month", tr.assign(n=tr.tariff_plan_code.isna()).groupby("time_key").n.mean().round(4).to_dict())
lm = tr.loc[tr.groupby("ID_NUMBER").time_key.transform("max") == tr.time_key, ["ID_NUMBER", "time_key", "tariff_plan_code"]]
j = c.merge(lm, on="ID_NUMBER", how="inner")
print("ct rows joined", len(j), " latest month dist", j.time_key.value_counts().sort_index().to_dict())
print(f"latest==from {(j.tariff_plan_code == j.tariff_plan_code_from).mean():.4f}  ==to {(j.tariff_plan_code == j.tariff_plan_code_to).mean():.4f}"
      f"  latest NaN {j.tariff_plan_code.isna().mean():.4f}")
# last non-null tariff
nn = tr.dropna(subset=["tariff_plan_code"]).sort_values("time_key").groupby("ID_NUMBER").tariff_plan_code.last()
jj = c.assign(last_t=c.ID_NUMBER.map(nn)).dropna(subset=["last_t"])
print(f"last non-null tariff==from {(jj["last_t"] == jj.tariff_plan_code_from).mean():.4f} (n={len(jj)})")
seen = tr.dropna(subset=["tariff_plan_code"]).groupby("ID_NUMBER").tariff_plan_code.agg(set)
cj = c[c.ID_NUMBER.isin(seen.index)].copy()
cj["from_seen"] = [a in seen[i] for a, i in zip(cj.tariff_plan_code_from, cj.ID_NUMBER)]
cj["to_seen"] = [a in seen[i] for a, i in zip(cj.tariff_plan_code_to, cj.ID_NUMBER)]
print(f"from seen any month {cj.from_seen.mean():.4f}  to seen any month {cj.to_seen.mean():.4f} (n={len(cj)})")
cj = cj[cj.AVG_ARPU_PREV_3M >= 100]
cj["y"] = ((cj.AVG_ARPU_NEXT_3M - cj.AVG_ARPU_PREV_3M) / cj.AVG_ARPU_PREV_3M).clip(-1, 3)
print("returners", ci(cj.y[cj.to_seen]), " others", ci(cj.y[~cj.to_seen]))
cj["seg"] = pd.cut(cj.AVG_ARPU_PREV_3M, [-np.inf, 1000, 5000, np.inf], labels=["LOW", "MID", "HIGH"]).astype(str)
cj["cell"] = cj.tariff_plan_code_from + "|" + cj.seg + "|" + cj.tariff_plan_code_to
cc = cj[cj.groupby("cell").y.transform("size") >= 20].copy()
cc["r"] = cc.y - cc.groupby("cell").y.transform("mean")
print("within-cell returners", ci(cc.r[cc.to_seen]), " others", ci(cc.r[~cc.to_seen]))
print("ct from==to rows", int((ct.tariff_plan_code_from == ct.tariff_plan_code_to).sum()))
