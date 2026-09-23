"""c1 part 5: reproduce profile segment definitions, then covariate shift history (pre-switch) vs target profile."""
import os
import numpy as np
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
pd.set_option("display.width", 200)

ct = pd.read_csv(os.path.join(P, "data", "change_tariff.csv"))
am = pd.read_csv(os.path.join(P, "data", "arpu_monthly.csv"))
tr = pd.read_csv(os.path.join(P, "data", "traffic.csv"))
pr = pd.read_csv(os.path.join(P, "customer_profile.csv"))

MIN_COLS = ["OUT_LOC_ONNET_MIN", "OUT_LOC_OFFNET_MIN", "OUT_INTER_MIN", "OUT_LOC_LAND_MIN"]


def data_seg(v):
    return pd.Series(np.select([v.isna(), v <= 0, v <= 2000], [None, "NON_USER", "LITE"], "HEAVY"), index=v.index).replace({None: np.nan})


def call_seg(v):
    return pd.Series(np.select([v.isna(), v < 100, v <= 400], [None, "LOW", "MEDIUM"], "HIGH"), index=v.index).replace({None: np.nan})


def arpu_seg(v):
    return pd.Series(np.select([v.isna(), v < 1000, v <= 5000], [None, "LOW", "MID"], "HIGH"), index=v.index).replace({None: np.nan})


print("=== A. Reproduce profile segment definitions ===")
ok = pr.data_segment.notna()
for name, v in {"DATA_VOLUME": pr.DATA_VOLUME, "LTE_DATA_VOLUME": pr.LTE_DATA_VOLUME,
                "DATA+LTE": pr.DATA_VOLUME + pr.LTE_DATA_VOLUME,
                "max(DATA,LTE)": np.maximum(pr.DATA_VOLUME, pr.LTE_DATA_VOLUME)}.items():
    print(f"data_segment from {name:16s}: agreement={(data_seg(v)[ok] == pr.data_segment[ok]).mean():.4f}")
okc = pr.call_segment.notna()
cands = {
    "ONNET+OFFNET": pr.OUT_LOC_ONNET_MIN + pr.OUT_LOC_OFFNET_MIN,
    "ONNET+OFFNET+LAND": pr.OUT_LOC_ONNET_MIN + pr.OUT_LOC_OFFNET_MIN + pr.OUT_LOC_LAND_MIN,
    "ONNET+OFFNET+INTER": pr.OUT_LOC_ONNET_MIN + pr.OUT_LOC_OFFNET_MIN + pr.OUT_INTER_MIN,
    "ONNET+OFFNET+INTER+LAND": pr[MIN_COLS].sum(axis=1),
    "OFFNET": pr.OUT_LOC_OFFNET_MIN,
    "ONNET+OFFNET+INTER+LAND+ROAM": pr[MIN_COLS].sum(axis=1) + pr.TOTAL_ROAM_CALL_AMT,
}
for name, v in cands.items():
    print(f"call_segment from {name:30s}: agreement={(call_seg(v)[okc] == pr.call_segment[okc]).mean():.4f}")
nu = pr.DATA_VOLUME.notna()
print(f"call_segment from ONNET+OFFNET on rows with usage present: agreement="
      f"{(call_seg(cands['ONNET+OFFNET'])[nu] == pr.call_segment[nu]).mean():.4f} (n={int(nu.sum())}); "
      f"rows with missing usage get call_segment={pr.call_segment[~nu].value_counts().to_dict()}")
oka = pr.arpu_segment.notna()
print(f"arpu_segment from ARPU_3m_avg: agreement={(arpu_seg(pr.ARPU_3m_avg)[oka] == pr.arpu_segment[oka]).mean():.4f}")
print("profile ARPU_trend values:", pr.ARPU_trend.value_counts(dropna=False).to_dict())
r = pr.ARPU_current / pr.ARPU_3m_avg.clip(lower=1)
print("ARPU_current/ARPU_3m_avg ratio quantiles by ARPU_trend:")
print(pr.assign(r=r).groupby("ARPU_trend")["r"].describe(percentiles=[0.01, 0.5, 0.99]).round(3).to_string())
print("profile usage missing:", int(pr.DATA_VOLUME.isna().sum()), " data_segment missing:", int(pr.data_segment.isna().sum()),
      " call_segment missing:", int(pr.call_segment.isna().sum()))

print("\n=== B. Build history pre-switch features (Jul-Sep 2026 means) ===")
win = ["2026-07-01", "2026-08-01", "2026-09-01"]
tw = tr[tr.time_key.isin(win)]
use = tw.groupby("ID_NUMBER")[["DATA_VOLUME", "LTE_DATA_VOLUME"] + MIN_COLS].mean()
os1 = tw.sort_values("time_key").groupby("ID_NUMBER")["OS_1"].last()
h = ct.drop_duplicates("ID_NUMBER").set_index("ID_NUMBER")
h = h.join(use, how="left").join(os1)
last_arpu = am[am.TIME_KEY == "2026-09-01"].groupby("ID_NUMBER")["ARPU_1M"].mean()
h["ARPU_sep"] = last_arpu
h["arpu_segment"] = arpu_seg(h.AVG_ARPU_PREV_3M)
h["data_segment"] = data_seg(h.DATA_VOLUME)
# ONNET+OFFNET reproduces the profile (section A); missing usage -> 0 -> LOW, as the profile does
h["call_segment"] = call_seg((h.OUT_LOC_ONNET_MIN + h.OUT_LOC_OFFNET_MIN).fillna(0))
print("history subscribers:", len(h), " with Jul-Sep traffic:", int(h.DATA_VOLUME.notna().sum()))
print("history OS_1 values:", h.OS_1.value_counts(dropna=False).to_dict())
print("profile has OS columns:", [c for c in pr.columns if c.startswith("OS")])

print("\n=== C. Covariate shift history vs profile ===")


def compare(name, hs, ps, top=5):
    a = hs.value_counts(normalize=True, dropna=False)
    b = ps.value_counts(normalize=True, dropna=False)
    d = pd.concat([a.rename("history"), b.rename("target")], axis=1).fillna(0)
    d["diff_pp"] = (d.target - d.history) * 100
    tvd = 0.5 * d.diff_pp.abs().sum()
    print(f"\n{name}: TVD={tvd:.2f} pp  (n_history={hs.size}, n_target={ps.size})")
    print(d.reindex(d.diff_pp.abs().sort_values(ascending=False).index).head(top).round(4).to_string())
    return d, tvd


tvds = {}
d_tar, tvds["tariff"] = compare("tariff (history from vs target current_tariff)", h.tariff_plan_code_from, pr.current_tariff, top=8)
d_arpu, tvds["arpu_segment"] = compare("arpu_segment", h.arpu_segment, pr.arpu_segment)
d_data, tvds["data_segment"] = compare("data_segment", h.data_segment, pr.data_segment)
d_call, tvds["call_segment"] = compare("call_segment", h.call_segment, pr.call_segment)
hj = h.arpu_segment.fillna("NA") + "|" + h.data_segment.fillna("NA") + "|" + h.call_segment.fillna("NA")
pj = pr.arpu_segment.fillna("NA") + "|" + pr.data_segment.fillna("NA") + "|" + pr.call_segment.fillna("NA")
_, tvds["joint arpu|data|call"] = compare("joint arpu|data|call", hj, pj, top=6)
_, tvds["tariff x arpu_segment"] = compare("tariff x arpu_segment", h.tariff_plan_code_from + "|" + h.arpu_segment,
                                          pr.current_tariff.fillna("NA") + "|" + pr.arpu_segment.fillna("NA"), top=6)
print("\nTVD summary (pp):", {k: round(v, 2) for k, v in tvds.items()})

print("\nCHART segment mix rows (dimension,level,history_share,target_share):")
for dim, d in [("arpu", d_arpu), ("data", d_data), ("call", d_call)]:
    for lvl, row in d.iterrows():
        print(f"  {dim},{lvl},{row.history:.4f},{row.target:.4f}")

print("\nARPU quantiles: history AVG_ARPU_PREV_3M vs target ARPU_3m_avg")
qs = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]
qt = pd.DataFrame({"history_PREV3M": h.AVG_ARPU_PREV_3M.quantile(qs), "target_ARPU_3m_avg": pr.ARPU_3m_avg.quantile(qs)})
qt["ratio"] = qt.target_ARPU_3m_avg / qt.history_PREV3M
print(qt.round(2).to_string())
print(f"mean: history={h.AVG_ARPU_PREV_3M.mean():.2f} target={pr.ARPU_3m_avg.mean():.2f}; "
      f"zero share: history={(h.AVG_ARPU_PREV_3M == 0).mean():.4f} target={(pr.ARPU_3m_avg == 0).mean():.4f}; "
      f"<100 share: history={(h.AVG_ARPU_PREV_3M < 100).mean():.4f} target={(pr.ARPU_3m_avg < 100).mean():.4f}")
print("\nUsage quantiles (median, p90): history Jul-Sep mean vs target")
for c in ["DATA_VOLUME", "LTE_DATA_VOLUME", "OUT_LOC_OFFNET_MIN", "OUT_LOC_ONNET_MIN"]:
    print(f"  {c}: history median={h[c].median():.2f} p90={h[c].quantile(0.9):.2f} | "
          f"target median={pr[c].median():.2f} p90={pr[c].quantile(0.9):.2f}")

print("\nMedian ARPU within arpu_segment: history PREV3M vs target ARPU_3m_avg")
for s in ["LOW", "MID", "HIGH"]:
    a, b = h.AVG_ARPU_PREV_3M[h.arpu_segment == s], pr.ARPU_3m_avg[pr.arpu_segment == s]
    print(f"  {s}: history median={a.median():.2f} (n={a.size}) target median={b.median():.2f} (n={b.size})")

# Trend analog: history Sep ARPU vs PREV_3M, compare with profile ARPU_current / ARPU_3m_avg
hr = h.ARPU_sep / h.AVG_ARPU_PREV_3M.clip(lower=1)
print(f"\ncurrent/3m ratio median: history(Sep/PREV3M)={hr.median():.4f}  target(ARPU_current/ARPU_3m_avg)={r.median():.4f}")
print(f"share ratio>1.1: history={(hr > 1.1).mean():.4f} target={(r > 1.1).mean():.4f};  share ratio<0.9: "
      f"history={(hr < 0.9).mean():.4f} target={(r < 0.9).mean():.4f}")

# Target cells with no or thin history support at (tariff, arpu_segment)
hc = h.groupby(["tariff_plan_code_from", "arpu_segment"]).size()
pc = pr.groupby(["current_tariff", "arpu_segment"]).size()
cov = pd.concat([pc.rename("target_n"), hc.rename("history_n")], axis=1).fillna(0)
cov = cov[cov.target_n > 0]
for thr in [0, 20, 50]:
    sel = cov.history_n <= thr
    print(f"target subscribers in (tariff,arpu_seg) cells with history_n<={thr}: {int(cov.target_n[sel].sum())} "
          f"({cov.target_n[sel].sum() / cov.target_n.sum():.4f}), cells={int(sel.sum())}")
cov["ratio"] = cov.target_n / cov.target_n.sum() / (cov.history_n / cov.history_n.sum())
print("largest target (tariff,arpu_seg) cells and history support:")
print(cov.sort_values("target_n", ascending=False).head(10).round(3).to_string())
