"""c1 part 1-3: coverage/joins, PREV_3M reconciliation, pre-switch trajectory, tariff consistency."""
import os
import numpy as np
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)

ct = pd.read_csv(os.path.join(P, "data", "change_tariff.csv"))
am = pd.read_csv(os.path.join(P, "data", "arpu_monthly.csv"))
tr = pd.read_csv(os.path.join(P, "data", "traffic.csv"))
pr = pd.read_csv(os.path.join(P, "customer_profile.csv"))

print("=== 1. COVERAGE ===")
for name, df in [("change_tariff", ct), ("arpu_monthly", am), ("traffic", tr), ("profile", pr)]:
    print(f"{name}: rows={len(df)} unique_ID={df['ID_NUMBER'].nunique()}")
print("change_tariff duplicate IDs:", int(ct["ID_NUMBER"].duplicated().sum()))
print("change_tariff TIME_KEY values:", ct["TIME_KEY"].value_counts().to_dict())
S = {"ct": set(ct.ID_NUMBER), "am": set(am.ID_NUMBER), "tr": set(tr.ID_NUMBER), "pr": set(pr.ID_NUMBER)}
for a in S:
    for b in S:
        if a < b:
            inter = len(S[a] & S[b])
            print(f"overlap {a}&{b}: {inter}  ({inter / len(S[a]):.4f} of {a}, {inter / len(S[b]):.4f} of {b})")
print("ct IDs in both am and tr:", len(S["ct"] & S["am"] & S["tr"]))
print("ct IDs in neither am nor tr:", len(S["ct"] - S["am"] - S["tr"]))
print("ID ranges: ct", ct.ID_NUMBER.min(), ct.ID_NUMBER.max(), " pr", pr.ID_NUMBER.min(), pr.ID_NUMBER.max())

print("\narpu_monthly months:", am["TIME_KEY"].value_counts().sort_index().to_dict())
print("traffic months:", tr["time_key"].value_counts().sort_index().to_dict())
print("arpu_monthly rows per ID:", am.groupby("ID_NUMBER").size().value_counts().sort_index().to_dict())
print("arpu_monthly duplicate (ID,month):", int(am.duplicated(["ID_NUMBER", "TIME_KEY"]).sum()))
print("arpu_monthly ARPU_1M missing:", int(am["ARPU_1M"].isna().sum()), " negative:", int((am["ARPU_1M"] < 0).sum()),
      " zero:", int((am["ARPU_1M"] == 0).sum()))
print("traffic rows per ID:", tr.groupby("ID_NUMBER").size().value_counts().sort_index().to_dict())
dev = tr.groupby("ID_NUMBER")["DEVICE_ID"].nunique()
print("traffic devices per ID:", dev.value_counts().sort_index().to_dict())
print(f"share of traffic IDs with >1 device over Apr-Sep: {(dev > 1).mean():.4f}")
print("traffic DEVICE_ID missing:", int(tr["DEVICE_ID"].isna().sum()))
idm = tr.groupby(["ID_NUMBER", "time_key"]).size()
print("traffic (ID,month) rows:", idm.value_counts().sort_index().to_dict())
months_per_id = tr.groupby("ID_NUMBER")["time_key"].nunique()
print("traffic distinct months per ID:", months_per_id.value_counts().sort_index().to_dict())
tpi = tr.groupby("ID_NUMBER")["tariff_plan_code"].nunique()
print("traffic distinct tariffs per ID:", tpi.value_counts().sort_index().to_dict())
print("traffic missing per column (nonzero):", {c: int(v) for c, v in tr.isna().sum().items() if v})

print("\n=== 2. RECONCILE AVG_ARPU_PREV_3M ===")
wide = am.pivot_table(index="ID_NUMBER", columns="TIME_KEY", values="ARPU_1M", aggfunc="mean")
months = sorted(wide.columns)
print("months:", months)
m = ct.set_index("ID_NUMBER")[["AVG_ARPU_PREV_3M", "AVG_ARPU_NEXT_3M", "tariff_plan_code_from", "tariff_plan_code_to"]].join(wide, how="inner")
print("ct IDs with monthly ARPU:", len(m))
cands = {
    "mean Jul-Sep": months[3:6], "mean Jun-Aug": months[2:5], "mean May-Jul": months[1:4],
    "mean Apr-Jun": months[0:3], "mean Aug-Sep": months[4:6], "Sep only": months[5:6],
}
for name, cols in cands.items():
    full = m[cols].notna().all(axis=1)
    est = m.loc[full, cols].mean(axis=1)
    err = (est - m.loc[full, "AVG_ARPU_PREV_3M"]).abs()
    rel = err / m.loc[full, "AVG_ARPU_PREV_3M"].abs().clip(lower=1)
    print(f"{name:13s} n={int(full.sum())} exact(|err|<=0.01)={(err <= 0.01).mean():.4f} "
          f"within1%={(rel <= 0.01).mean():.4f} medianAbsErr={err.median():.2f} meanAbsErr={err.mean():.2f}")
# nan-tolerant mean of Jul-Sep (for IDs with partial months)
est_nan = m[months[3:6]].mean(axis=1, skipna=True)
err_nan = (est_nan - m["AVG_ARPU_PREV_3M"]).abs()
print(f"nan-mean Jul-Sep n={int(est_nan.notna().sum())} exact={(err_nan <= 0.01).mean():.4f} "
      f"within1%={((err_nan / m['AVG_ARPU_PREV_3M'].abs().clip(lower=1)) <= 0.01).mean():.4f}")
# which rows have Jul-Sep incomplete?
bad = err_nan > 0.01
print("non-exact rows:", int(bad.sum()), " of which ID has duplicate (ID,month) rows in arpu_monthly:",
      int(m.index[bad].isin(am.loc[am.duplicated(["ID_NUMBER", "TIME_KEY"], keep=False), "ID_NUMBER"]).sum()),
      " ID duplicated in change_tariff:", int(m.index[bad].isin(ct.loc[ct.ID_NUMBER.duplicated(keep=False), "ID_NUMBER"]).sum()))
# duplicates: take the sum instead of mean for duplicated months
wide_sum = am.pivot_table(index="ID_NUMBER", columns="TIME_KEY", values="ARPU_1M", aggfunc="sum")
est_sum = ct.set_index("ID_NUMBER").join(wide_sum[months[3:6]], how="inner")
e2 = (est_sum[months[3:6]].mean(axis=1) - est_sum["AVG_ARPU_PREV_3M"]).abs()
print(f"nan-mean Jul-Sep with duplicate months summed: exact={(e2 <= 0.01).mean():.4f}")
rowmean = am[am.TIME_KEY.isin(months[3:6])].groupby("ID_NUMBER")["ARPU_1M"].mean()
e3 = (ct.set_index("ID_NUMBER")["AVG_ARPU_PREV_3M"] - rowmean.reindex(ct.ID_NUMBER).to_numpy()).abs()
print(f"row-level mean of all Jul-Sep rows (duplicates kept): exact={(e3 <= 0.01).mean():.4f} within1%={((e3 / ct.set_index('ID_NUMBER')['AVG_ARPU_PREV_3M'].abs().clip(lower=1)) <= 0.01).mean():.4f}")
dups = am[am.duplicated(["ID_NUMBER", "TIME_KEY"], keep=False)]
print("duplicate (ID,month) rows:", len(dups), " IDs:", dups.ID_NUMBER.nunique(),
      " exact duplicate rows:", int(am.duplicated().sum()))
print("zero ARPU_1M share by month:", (am.assign(z=am.ARPU_1M == 0).groupby("TIME_KEY")["z"].mean().round(4)).to_dict())
print("share of ct IDs with any zero month Jul-Sep:", round(float((m[months[3:6]] == 0).any(axis=1).mean()), 4))
print("AVG_ARPU_PREV_3M: zero share", round(float((ct.AVG_ARPU_PREV_3M == 0).mean()), 4), " <100 share",
      round(float((ct.AVG_ARPU_PREV_3M < 100).mean()), 4))
print("ct IDs by count of non-null Jul-Sep months:", m[months[3:6]].notna().sum(axis=1).value_counts().sort_index().to_dict())
print("ct IDs by count of non-null Apr-Sep months:", m[months].notna().sum(axis=1).value_counts().sort_index().to_dict())
# Sum/3 treating missing as 0
est0 = m[months[3:6]].fillna(0).sum(axis=1) / 3
err0 = (est0 - m["AVG_ARPU_PREV_3M"]).abs()
print(f"sum Jul-Sep/3 (missing=0) exact={(err0 <= 0.01).mean():.4f} within1%={((err0 / m['AVG_ARPU_PREV_3M'].abs().clip(lower=1)) <= 0.01).mean():.4f}")

print("\n--- Pre-switch trajectory (IDs with all 6 months) ---")
full6 = m[months].notna().all(axis=1)
t6 = m[full6]
print("IDs with all 6 months:", int(full6.sum()))
print("mean ARPU by month:", {k[:7]: round(v, 2) for k, v in t6[months].mean().items()})
print("median ARPU by month:", {k[:7]: round(v, 2) for k, v in t6[months].median().items()})
# per-ID slope: OLS over 6 months, normalized by own mean
x = np.arange(6) - 2.5
Y = t6[months].to_numpy()
slope = (Y * x).sum(axis=1) / (x ** 2).sum()
mean_i = Y.mean(axis=1)
t6 = t6.assign(slope=slope, rel_slope=slope / np.clip(mean_i, 1, None),
               q1=t6[months[0:3]].mean(axis=1), q2=t6[months[3:6]].mean(axis=1))
t6["q2_vs_q1"] = (t6["q2"] - t6["q1"]) / t6["q1"].clip(lower=1)
print(f"slope ARPU/month: mean={t6.slope.mean():.2f} median={t6.slope.median():.2f} "
      f"se={t6.slope.std(ddof=1) / np.sqrt(len(t6)):.2f}")
print(f"share with positive slope: {(t6.slope > 0).mean():.4f}")
print(f"Jul-Sep mean vs Apr-Jun mean: agg ratio={t6.q2.sum() / t6.q1.sum():.4f} median rel={t6.q2_vs_q1.median():.4f}")
t6["rel_change"] = ((t6.AVG_ARPU_NEXT_3M - t6.AVG_ARPU_PREV_3M) / t6.AVG_ARPU_PREV_3M).clip(-1, 3)
ok = t6.AVG_ARPU_PREV_3M >= 100
c = np.corrcoef(t6.loc[ok, "q2_vs_q1"].clip(-1, 3), t6.loc[ok, "rel_change"])[0, 1]
print(f"corr(pre-trend Jul-Sep vs Apr-Jun, clipped rel_change) PREV>=100: {c:.4f} n={int(ok.sum())}")
# pre-trend bucket vs rel change
t6["trend_b"] = pd.cut(t6["q2_vs_q1"], [-np.inf, -0.2, 0.2, np.inf], labels=["DECLINING<-20%", "STABLE", "GROWING>+20%"])
g = t6[ok].groupby("trend_b", observed=True)["rel_change"].agg(["size", "mean", "std"])
g["ci95"] = 1.96 * g["std"] / np.sqrt(g["size"])
print("rel_change by pre-trend bucket (PREV>=100):\n", g.round(4))
# same, within (from, arpu_segment, to) cells -> what the scorer key cannot see
t6["seg"] = np.select([t6.AVG_ARPU_PREV_3M < 1000, t6.AVG_ARPU_PREV_3M <= 5000], ["LOW", "MID"], "HIGH")
tk = t6[ok].copy()
tk["cell"] = tk.tariff_plan_code_from + "|" + tk.seg + "|" + tk.tariff_plan_code_to
tk = tk[tk.groupby("cell")["rel_change"].transform("size") >= 20]
tk["r"] = tk.rel_change - tk.groupby("cell")["rel_change"].transform("mean")
g = tk.groupby("trend_b", observed=True)["r"].agg(["size", "mean", "std"])
g["ci95"] = 1.96 * g["std"] / np.sqrt(g["size"])
print(f"within-(from,seg,to) residual by pre-trend bucket (cells n>=20, rows={len(tk)}):\n", g.round(4))
print("pre-trend bucket mix by arpu segment (share):")
print(t6.groupby("seg")["trend_b"].value_counts(normalize=True).unstack().round(4).to_string())

print("\n--- Trajectory by destination (top 8 destinations, all-6-months IDs) ---")
top_to = t6["tariff_plan_code_to"].value_counts().head(8).index
rows = []
for to in top_to:
    sub = t6[t6.tariff_plan_code_to == to]
    rows.append([to, len(sub)] + [round(v, 1) for v in sub[months].mean()] +
                [round(sub.slope.mean(), 2), round(sub.q2.sum() / sub.q1.sum(), 4)])
print(pd.DataFrame(rows, columns=["to", "n"] + [c[:7] for c in months] + ["mean_slope", "q2/q1"]).to_string(index=False))
print("\n--- Trajectory by origin (top 8 origins) ---")
rows = []
for fr in t6["tariff_plan_code_from"].value_counts().head(8).index:
    sub = t6[t6.tariff_plan_code_from == fr]
    rows.append([fr, len(sub)] + [round(v, 1) for v in sub[months].mean()] +
                [round(sub.slope.mean(), 2), round(sub.q2.sum() / sub.q1.sum(), 4)])
print(pd.DataFrame(rows, columns=["from", "n"] + [c[:7] for c in months] + ["mean_slope", "q2/q1"]).to_string(index=False))
# chart rows: mean by month, overall + top 3 destinations
print("\nCHART trajectory rows:")
for grp, sub in [("ALL", t6)] + [(to, t6[t6.tariff_plan_code_to == to]) for to in ["tariff_8", "tariff_13", "tariff_9"]]:
    for mo in months:
        print(f"  {grp},{mo[:7]},{sub[mo].mean():.1f},{len(sub)}")

print("\n=== 3. TRAFFIC TARIFF vs tariff_plan_code_from ===")
tr_sorted = tr.sort_values(["ID_NUMBER", "time_key"])
last = tr_sorted.groupby("ID_NUMBER").tail(1).drop_duplicates("ID_NUMBER", keep="last")
# latest month per ID, possibly multiple devices: take all device tariffs in the latest month
lastmonth = tr.groupby("ID_NUMBER")["time_key"].transform("max")
latest = tr[tr.time_key == lastmonth]
lat_tar = latest.groupby("ID_NUMBER")["tariff_plan_code"].agg(lambda s: set(s.dropna()))
lat_month = latest.groupby("ID_NUMBER")["time_key"].first()
j = ct.set_index("ID_NUMBER").join(lat_tar.rename("lat"), how="inner").join(lat_month.rename("lat_month"))
j["match_from"] = [f in s for f, s in zip(j.tariff_plan_code_from, j.lat)]
j["match_to"] = [t in s for t, s in zip(j.tariff_plan_code_to, j.lat)]
j["n_tar"] = j.lat.map(len)
print("ct IDs joined to traffic:", len(j))
print("latest traffic month distribution:", j.lat_month.value_counts().sort_index().to_dict())
print(f"latest-month tariff == from: {j.match_from.mean():.4f}  == to: {j.match_to.mean():.4f}  "
      f"neither: {((~j.match_from) & (~j.match_to)).mean():.4f}  multiple tariffs in latest month: {(j.n_tar > 1).mean():.4f}")
print("match_from by latest month:", j.groupby("lat_month")["match_from"].mean().round(4).to_dict())
# any month match
any_tar = tr.groupby("ID_NUMBER")["tariff_plan_code"].agg(lambda s: set(s.dropna()))
j2 = ct.set_index("ID_NUMBER").join(any_tar.rename("any"), how="inner")
print(f"'from' appears in any traffic month: {np.mean([f in s for f, s in zip(j2.tariff_plan_code_from, j2['any'])]):.4f}  "
      f"'to' appears in any month: {np.mean([t in s for t, s in zip(j2.tariff_plan_code_to, j2['any'])]):.4f}")
j2["to_seen"] = [t in s for t, s in zip(j2.tariff_plan_code_to, j2["any"])]
j2 = j2[j2.AVG_ARPU_PREV_3M >= 100]
j2["y"] = ((j2.AVG_ARPU_NEXT_3M - j2.AVG_ARPU_PREV_3M) / j2.AVG_ARPU_PREV_3M).clip(-1, 3)
g = j2.groupby("to_seen")["y"].agg(["size", "mean", "std"])
g["ci95"] = 1.96 * g["std"] / np.sqrt(g["size"])
print("rel change (PREV>=100) by 'destination already seen in Apr-Sep traffic' (returners):\n", g.round(4))
mis = j[~j.match_from]
print("top mismatches (from -> latest traffic tariff):")
mm = pd.Series([f"{f}->{sorted(s)}" for f, s in zip(mis.tariff_plan_code_from, mis.lat)]).value_counts().head(8)
print(mm.to_string())
print("ct from==to rows:", int((ct.tariff_plan_code_from == ct.tariff_plan_code_to).sum()))
