"""a1: target-audience profile of customer_profile.csv (schema, segments, predicted_arpu,
cells, ID ordering, reach). Deterministic; prints every number used in the report."""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from mock_environment import _mock_fallback  # noqa: E402  (read-only use: how the mock scores NaN tariffs)

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_rows", 200)

df = pd.read_csv(os.path.join(ROOT, "customer_profile.csv"))
dt = pd.read_csv(os.path.join(ROOT, "data", "dict_tariff.csv"))
PA = "predicted_arpu"
TOTAL = df[PA].sum()
N = len(df)
USAGE = ["OUT_LOC_ONNET_MIN", "OUT_LOC_OFFNET_MIN", "OUT_LOC_OFFNET_UNPAID_MIN", "OUT_LOC_OFFNET_PAID_MIN",
         "OUT_INTER_MIN", "OUT_LOC_LAND_MIN", "OUT_LOCAL_ONNET_SMS_AMT", "OUT_LOCAL_OFFNET_SMS_AMT",
         "OUT_LOCAL_LAND_PAID_SMS_AMT", "OUT_INTER_SMS_AMT", "DATA_VOLUME", "LTE_DATA_VOLUME",
         "TOTAL_ROAM_CALL_AMT", "TOTAL_ROAM_SMS_AMT", "TOTAL_ROAM_GPRS_MB"]
CONTACT = ["COUNT_CONTACT", "AVG_TRANSACT_CONTACT", "SUM_TRANSACT_CONTACT", "AVG_DURATION_CONTACT"]


def h(title):
    print(f"\n{'=' * 100}\n{title}\n{'=' * 100}")


def pct(a, b):
    return 100.0 * a / b if b else float("nan")


def spearman(a, b):
    m = a.notna() & b.notna()
    return float(a[m].rank().corr(b[m].rank()))


def cramers_v(a, b):
    t = pd.crosstab(a, b).values.astype(float)
    e = t.sum(1, keepdims=True) * t.sum(0, keepdims=True) / t.sum()
    chi2 = ((t - e) ** 2 / e).sum()
    return float(np.sqrt(chi2 / (t.sum() * (min(t.shape) - 1))))


# =================================================================================== 1
h("1. SCHEMA AND DATA QUALITY")
print(f"rows={N} cols={df.shape[1]}  sum(predicted_arpu)={TOTAL:,.2f}")
print("dtypes:", {k: str(v) for k, v in df.dtypes.value_counts().items()})
print("string columns:", [c for c in df.columns if df[c].dtype == object or str(df[c].dtype).startswith("str")])
na = df.isna().sum()
print("missing per column (non-zero):")
print(na[na > 0].to_string())

flags = pd.DataFrame({
    "tariff": df["current_tariff"].isna(), "arpu_seg": df["arpu_segment"].isna(),
    "arpu3m": df["ARPU_3m_avg"].isna(), "trend": df["ARPU_trend"].isna(),
    "arpu_cur": df["ARPU_current"].isna(), "usage": df[USAGE].isna().any(axis=1),
    "data_seg": df["data_segment"].isna(), "contact": df[CONTACT].isna().any(axis=1),
    "base_st": df["COUNT_BASE_STATION"].isna(),
})
print("\nall usage columns missing together:", int(df[USAGE].isna().all(axis=1).sum()),
      "| any usage missing:", int(flags["usage"].sum()))
print("all contact columns missing together:", int(df[CONTACT].isna().all(axis=1).sum()),
      "| any contact missing:", int(flags["contact"].sum()))
print("missing-pattern counts (True = missing):")
pat = flags.value_counts().reset_index(name="n")
print(pat.to_string(index=False))
print("\nco-occurrence with missing current_tariff (95 rows):")
t = flags["tariff"]
for c in flags.columns:
    print(f"  {c:9s} missing among tariff-missing: {int((flags[c] & t).sum()):4d} / {int(t.sum())}"
          f"   (column total {int(flags[c].sum())})")
print("arpu_seg missing == ARPU_3m_avg missing == ARPU_trend missing:",
      bool((flags["arpu_seg"] == flags["arpu3m"]).all() and (flags["arpu_seg"] == flags["trend"]).all()))
print("data_seg missing == usage missing:", bool((flags["data_seg"] == flags["usage"]).all()))
print("call_segment of usage-missing rows:", df.loc[flags["usage"], "call_segment"].value_counts(dropna=False).to_dict())
print("arpu_segment of tariff-missing rows:", df.loc[t, "arpu_segment"].value_counts(dropna=False).to_dict())

print("\nunreachable by filter (rows whose filter column is NaN can never match an equality filter):")
for name, m in [("current_tariff", flags["tariff"]), ("arpu_segment", flags["arpu_seg"]),
                ("data_segment", flags["data_seg"]),
                ("tariff OR arpu_seg (agent's cell filters)", flags["tariff"] | flags["arpu_seg"]),
                ("tariff OR arpu_seg OR data_seg", flags["tariff"] | flags["arpu_seg"] | flags["data_seg"])]:
    print(f"  {name:42s} n={int(m.sum()):4d}  mass={df.loc[m, PA].sum():>12,.0f}  "
          f"({pct(df.loc[m, PA].sum(), TOTAL):.3f}% of total)")
m15 = df["current_tariff"].notna() & df["arpu_segment"].notna() & df["data_segment"].isna()
print("rows with tariff+arpu_seg but NaN data_segment:", int(m15.sum()),
      df.loc[m15].groupby(["current_tariff", "arpu_segment"]).size().to_dict())
print("mock fallback for a NaN current_tariff row -> (arpu_change_pct, conversion):",
      _mock_fallback(np.nan, "tariff_10", "HIGH", dt, 0.123))

print("\nduplicates: ID_NUMBER dup =", int(df["ID_NUMBER"].duplicated().sum()),
      "| full-row dup =", int(df.duplicated().sum()),
      "| ID sorted ascending:", bool(df["ID_NUMBER"].is_monotonic_increasing),
      "| ID min/max:", int(df["ID_NUMBER"].min()), int(df["ID_NUMBER"].max()))
for c in ["ARPU_current", "ARPU_3m_avg", PA]:
    s = df[c]
    print(f"{c:15s} ==0: {int((s == 0).sum()):4d}   <0: {int((s < 0).sum()):3d}   NaN: {int(s.isna().sum()):3d}")
z3 = df["ARPU_3m_avg"] == 0
print("rows with ARPU_3m_avg==0: predicted_arpu==0 among them:", int((z3 & (df[PA] == 0)).sum()), "of", int(z3.sum()),
      "| predicted_arpu==0 with ARPU_3m_avg>0:", int(((df[PA] == 0) & (df["ARPU_3m_avg"] > 0)).sum()))
print("predicted_arpu==0 by arpu_segment:", df.loc[df[PA] == 0, "arpu_segment"].value_counts(dropna=False).to_dict())
lo100 = df["ARPU_3m_avg"] < 100
print(f"ARPU_3m_avg<100 (history prior drops PREV<100): n={int(lo100.sum())} "
      f"({pct(lo100.sum(), N):.2f}% of subs, {pct(df.loc[lo100, PA].sum(), TOTAL):.2f}% of mass), "
      f"with predicted_arpu>0: {int((lo100 & (df[PA] > 0)).sum())}, mean predicted {df.loc[lo100, PA].mean():,.1f}")

print("\noutliers (quantiles; n_far = count > Q3 + 3*IQR):")
rows = []
for c in ["ARPU_current", "ARPU_3m_avg", PA, "DATA_VOLUME", "LTE_DATA_VOLUME", "OUT_LOC_ONNET_MIN",
          "OUT_LOC_OFFNET_MIN", "TOTAL_ROAM_GPRS_MB", "COUNT_BASE_STATION"]:
    s = df[c].dropna()
    q = s.quantile([0, .01, .25, .5, .75, .99, 1]).values
    rows.append(dict(col=c, min=q[0], p01=q[1], p25=q[2], p50=q[3], p75=q[4], p99=q[5], max=q[6],
                     n_far=int((s > q[4] + 3 * (q[4] - q[2])).sum())))
print(pd.DataFrame(rows).round(2).to_string(index=False))
top = df.nlargest(3, PA)[["ID_NUMBER", "ARPU_current", "ARPU_3m_avg", PA, "current_tariff", "arpu_segment"]]
print("top-3 predicted_arpu rows:\n", top.to_string(index=False))
print("largest predicted_arpu / 99th percentile:", round(df[PA].max() / df[PA].quantile(.99), 2),
      "| its share of total mass %:", round(pct(df[PA].max(), TOTAL), 4))

print("\nARPU_trend counts:", df["ARPU_trend"].value_counts(dropna=False).to_dict())
r = (df["ARPU_current"] / df["ARPU_3m_avg"]).replace([np.inf, -np.inf], np.nan)
print("ARPU_current/ARPU_3m_avg quantiles by ARPU_trend (labels overlap -> not a simple ratio rule):")
print(df.assign(r=r).groupby("ARPU_trend")["r"].quantile([.05, .25, .5, .75, .95]).unstack().round(3).to_string())

u = df.dropna(subset=["DATA_VOLUME"])
print("\ndictionary consistency: LTE_DATA_VOLUME > DATA_VOLUME in", f"{pct((u.LTE_DATA_VOLUME > u.DATA_VOLUME).sum(), len(u)):.2f}%",
      "of rows (dictionary says LTE is a subset of DATA)")
print("OUT_LOC_OFFNET_MIN == UNPAID + PAID in",
      f"{pct(np.isclose(u.OUT_LOC_OFFNET_MIN, u.OUT_LOC_OFFNET_UNPAID_MIN + u.OUT_LOC_OFFNET_PAID_MIN).sum(), len(u)):.2f}% of rows")

# =================================================================================== 2
h("2. SEGMENT-LABEL CONSISTENCY")
a = df["ARPU_3m_avg"]
ok = df["arpu_segment"].notna()
conv = {
    "brief: <1000 LOW, 1000-5000 MID, >5000 HIGH": np.where(a < 1000, "LOW", np.where(a <= 5000, "MID", "HIGH")),
    "pd.cut right=True: <=1000 LOW, <=5000 MID": np.where(a <= 1000, "LOW", np.where(a <= 5000, "MID", "HIGH")),
    "right=False: <1000 LOW, <5000 MID, >=5000 HIGH": np.where(a < 1000, "LOW", np.where(a < 5000, "MID", "HIGH")),
}
print("rows exactly at 1000:", int((a == 1000).sum()), "| at 5000:", int((a == 5000).sum()))
for k, v in conv.items():
    print(f"  arpu_segment agreement [{k}]: {pct((v[ok] == df.loc[ok, 'arpu_segment']).sum(), ok.sum()):.3f}%")
c = df["ARPU_current"]
alt = np.where(c < 1000, "LOW", np.where(c <= 5000, "MID", "HIGH"))
okc = ok & c.notna()
print(f"  (same thresholds on ARPU_current instead: {pct((alt[okc] == df.loc[okc, 'arpu_segment']).sum(), okc.sum()):.3f}%)")
print("confusion (rows=label, cols=recomputed brief rule):")
print(pd.crosstab(df.loc[ok, "arpu_segment"], conv["brief: <1000 LOW, 1000-5000 MID, >5000 HIGH"][ok]).to_string())

okd = df["data_segment"].notna()
dcand = {
    "DATA_VOLUME": df["DATA_VOLUME"], "LTE_DATA_VOLUME": df["LTE_DATA_VOLUME"],
    "DATA+LTE": df["DATA_VOLUME"] + df["LTE_DATA_VOLUME"],
    "max(DATA,LTE)": df[["DATA_VOLUME", "LTE_DATA_VOLUME"]].max(axis=1),
    "DATA+ROAM_GPRS": df["DATA_VOLUME"] + df["TOTAL_ROAM_GPRS_MB"],
}
print("\ndata_segment candidates (0 -> NON_USER, (0,2000] -> LITE, >2000 HEAVY; also >=2000 HEAVY):")
for k, s in dcand.items():
    for lab, v in [(">2000", np.where(s <= 0, "NON_USER", np.where(s <= 2000, "LITE", "HEAVY"))),
                   (">=2000", np.where(s <= 0, "NON_USER", np.where(s < 2000, "LITE", "HEAVY")))]:
        print(f"  {k:16s} HEAVY{lab:7s}: {pct((v[okd] == df.loc[okd, 'data_segment']).sum(), okd.sum()):.3f}%")
dv = df["DATA_VOLUME"]
print("DATA_VOLUME exactly 2000:", int((dv == 2000).sum()), "| exactly 0:", int((dv == 0).sum()),
      "| NON_USER rows with LTE>0:", int(((df["data_segment"] == "NON_USER") & (df["LTE_DATA_VOLUME"] > 0)).sum()))

U = df[USAGE].fillna(0)
ccand = {
    "ONNET": U.OUT_LOC_ONNET_MIN, "OFFNET": U.OUT_LOC_OFFNET_MIN,
    "ONNET+OFFNET": U.OUT_LOC_ONNET_MIN + U.OUT_LOC_OFFNET_MIN,
    "ONNET+OFFNET+LAND": U.OUT_LOC_ONNET_MIN + U.OUT_LOC_OFFNET_MIN + U.OUT_LOC_LAND_MIN,
    "ONNET+OFFNET+INTER": U.OUT_LOC_ONNET_MIN + U.OUT_LOC_OFFNET_MIN + U.OUT_INTER_MIN,
    "ONNET+OFFNET+LAND+INTER": U.OUT_LOC_ONNET_MIN + U.OUT_LOC_OFFNET_MIN + U.OUT_LOC_LAND_MIN + U.OUT_INTER_MIN,
    "ALL4+ROAM_CALL": U.OUT_LOC_ONNET_MIN + U.OUT_LOC_OFFNET_MIN + U.OUT_LOC_LAND_MIN + U.OUT_INTER_MIN + U.TOTAL_ROAM_CALL_AMT,
    "ONNET+OFFNET_PAID": U.OUT_LOC_ONNET_MIN + U.OUT_LOC_OFFNET_PAID_MIN,
}
print("\ncall_segment candidates (<100 LOW, 100-400 MEDIUM, >400 HIGH; usage NaN filled with 0):")
best_call, best_acc = None, -1
for k, s in ccand.items():
    v = np.where(s < 100, "LOW", np.where(s <= 400, "MEDIUM", "HIGH"))
    acc = pct((v == df["call_segment"]).sum(), N)
    if acc > best_acc:
        best_call, best_acc = k, acc
    print(f"  {k:26s}: {acc:.3f}%")
s = ccand[best_call]
v = np.where(s < 100, "LOW", np.where(s <= 400, "MEDIUM", "HIGH"))
print(f"best call definition: {best_call} ({best_acc:.3f}%); mismatches: {int((v != df['call_segment']).sum())}")
print(pd.crosstab(df["call_segment"], v).to_string())
print("minutes range by label for best definition:")
print(df.assign(m=s).groupby("call_segment")["m"].agg(["min", "max"]).round(3).to_string())

# =================================================================================== 3
h("3. predicted_arpu")
p = df[PA]
print(p.describe(percentiles=[.01, .05, .25, .5, .75, .95, .99]).round(2).to_string())
print(f"zeros: {int((p == 0).sum())}  negatives: {int((p < 0).sum())}")
eq3 = np.isclose(p, df["ARPU_3m_avg"])
print(f"predicted_arpu == ARPU_3m_avg exactly: {int(eq3.sum())} rows ({pct(eq3.sum(), N):.2f}%), of which zeros: {int((eq3 & (p == 0)).sum())}")
print("  arpu_segment of exact-equality rows:", df.loc[eq3, "arpu_segment"].value_counts(dropna=False).to_dict())
vc = p.round(6).value_counts()
print(f"distinct values: {p.nunique()} of {N}; values repeated >=100 times:")
for val, cnt in vc[vc >= 100].items():
    g = df[p.round(6) == val]
    print(f"  {val:>12.6f} x{cnt}: arpu_segment {g['arpu_segment'].value_counts().to_dict()}  "
          f"trend {g['ARPU_trend'].value_counts().to_dict()}  n_tariffs={g['current_tariff'].nunique()}  "
          f"ARPU_3m_avg range {g['ARPU_3m_avg'].min():.0f}-{g['ARPU_3m_avg'].max():.0f}")
consts = [v for v in vc[vc >= 100].index if v > 0]
rep = p.round(6).isin(consts)
print(f"rows carrying one of the {len(consts)} non-zero repeated constants: {int(rep.sum())} ({pct(rep.sum(), N):.2f}%)"
      f"  mass={df.loc[rep, PA].sum():,.0f} ({pct(df.loc[rep, PA].sum(), TOTAL):.2f}%)")
print("  arpu_segment mix of constant rows vs whole base (%):",
      (df.loc[rep, "arpu_segment"].value_counts(normalize=True) * 100).round(1).to_dict(),
      (df["arpu_segment"].value_counts(normalize=True) * 100).round(1).to_dict())
print("  median ARPU_3m_avg of constant rows by arpu_segment:",
      df.loc[rep].groupby("arpu_segment")["ARPU_3m_avg"].median().round(0).to_dict())
kind = np.where(p == 0, "zero", np.where(rep, "constant", np.where(eq3, "equals_3m", "model")))
print("row kinds:", pd.Series(kind).value_counts().to_dict())

x = df.dropna(subset=["ARPU_current", "ARPU_3m_avg"])
trim = x[(x.ARPU_3m_avg <= x.ARPU_3m_avg.quantile(.99)) & (x.ARPU_current <= x.ARPU_current.quantile(.99))]
for c in ["ARPU_3m_avg", "ARPU_current"]:
    print(f"corr(predicted, {c}): pearson all={x[c].corr(x[PA]):.3f}  pearson trimmed p99={trim[c].corr(trim[PA]):.3f}"
          f"  spearman={spearman(x[c], x[PA]):.3f}")


def lsq(d, cols, logy=False):
    y = np.log(d[PA].values) if logy else d[PA].values
    X = np.column_stack([np.ones(len(d))] + [np.log(d[c].values) if logy else d[c].values for c in cols])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    r2 = 1 - ((y - X @ b) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return b, r2


for cols in (["ARPU_3m_avg"], ["ARPU_current"], ["ARPU_3m_avg", "ARPU_current"]):
    b, r2 = lsq(trim, cols)
    print(f"OLS (trimmed, n={len(trim)}) predicted ~ 1 + {' + '.join(cols)}: coef={np.round(b, 4).tolist()}  R2={r2:.3f}")
b, _ = lsq(trim, ["ARPU_3m_avg"])
print(f"fixed point of the 1-var fit (pred == ARPU_3m_avg): {b[0] / (1 - b[1]):,.0f}; base mean predicted={p.mean():,.0f}")
trim_model = trim[pd.Series(kind, index=df.index).loc[trim.index] == "model"]
for cols in (["ARPU_3m_avg"], ["ARPU_3m_avg", "ARPU_current"]):
    b, r2 = lsq(trim_model, cols)
    print(f"OLS on 'model' rows only (n={len(trim_model)}) ~ 1 + {' + '.join(cols)}: coef={np.round(b, 4).tolist()}  R2={r2:.3f}")
pos = x[(x.ARPU_3m_avg > 100) & (x[PA] > 0)]
b, r2 = lsq(pos, ["ARPU_3m_avg"], logy=True)
print(f"log-log (ARPU_3m_avg>100, n={len(pos)}): log(pred) = {b[0]:.3f} + {b[1]:.3f}*log(ARPU_3m_avg)  R2={r2:.3f}"
      f"  -> elasticity {b[1]:.3f} (<1 = shrinkage toward the centre)")
x = x.assign(dec=pd.qcut(x["ARPU_3m_avg"].rank(method="first"), 10, labels=False) + 1)
print("medians by ARPU_3m_avg decile (compression check):")
print(x.groupby("dec")[["ARPU_3m_avg", "ARPU_current", PA]].median().round(0).to_string())

print("\nratio predicted/ARPU_3m_avg by arpu_segment (ARPU_3m_avg>0):")
xr = df[df["ARPU_3m_avg"] > 0].assign(r=lambda d: d[PA] / d["ARPU_3m_avg"])
print(xr.groupby("arpu_segment")["r"].quantile([.1, .5, .9]).unstack().round(3).to_string())

print("\npredicted_arpu by arpu_segment x ARPU_trend:")
seg_tr = (df.groupby(["arpu_segment", "ARPU_trend"])[PA]
          .agg(n="size", mean="mean", p25=lambda s: s.quantile(.25), p50="median", p75=lambda s: s.quantile(.75),
               mass="sum").reset_index())
seg_tr["mass_share_pct"] = 100 * seg_tr["mass"] / TOTAL
print(seg_tr.round(1).to_string(index=False))
seg = df.groupby("arpu_segment", dropna=False)[PA].agg(n="size", mean="mean", median="median", mass="sum")
seg["n_share_pct"] = 100 * seg["n"] / N
seg["mass_share_pct"] = 100 * seg["mass"] / TOTAL
seg["mean_ARPU_3m_avg"] = df.groupby("arpu_segment", dropna=False)["ARPU_3m_avg"].mean()
print("\nby arpu_segment:\n", seg.round(2).to_string())

ps = np.sort(p.values)[::-1]
cum = np.cumsum(ps) / ps.sum()
for q in (0.01, 0.10, 0.25, 0.50):
    k = int(round(q * N))
    print(f"top {q:.0%} ({k} subs) hold {100 * cum[k - 1]:.2f}% of predicted_arpu mass")
lor = np.cumsum(np.sort(p.values)) / p.sum()
print(f"Gini(predicted_arpu) = {1 - 2 * lor.mean() + 1 / N:.4f};  Gini(ARPU_3m_avg) = "
      f"{(lambda v: 1 - 2 * (np.cumsum(v) / v.sum()).mean() + 1 / len(v))(np.sort(df['ARPU_3m_avg'].dropna().values)):.4f}")

# =================================================================================== 4
h("4. CELLS = current_tariff x arpu_segment")
cells = (df.dropna(subset=["current_tariff", "arpu_segment"])
         .groupby(["current_tariff", "arpu_segment"])[PA].agg(n="size", mass="sum", mean="mean").reset_index()
         .sort_values("mass", ascending=False).reset_index(drop=True))
cells["cell"] = cells["current_tariff"] + "/" + cells["arpu_segment"]
cells["mass_pct"] = 100 * cells["mass"] / TOTAL
cells["cum_pct"] = cells["mass_pct"].cumsum()
cells["cum_n"] = cells["n"].cumsum()
print(f"non-empty cells: {len(cells)} (of 21 tariffs x 3 segments = 63); tariffs present: {df['current_tariff'].nunique()}")
print(cells[["cell", "n", "mass", "mean", "mass_pct", "cum_pct", "cum_n"]].round(2).to_string(index=False))
for q in (50, 80, 95):
    print(f"cells needed for {q}% of total mass: {int((cells['cum_pct'] < q).sum()) + 1}")
big = cells[cells["n"] > 5000]
print("cells with n>5000 (must be split):", big[["cell", "n", "mass_pct"]].round(2).to_dict("records"))
small = cells[cells["n"] < 20]
print(f"cells with n<20: {len(small)}  total n={int(small['n'].sum())}  mass%={small['mass_pct'].sum():.3f}  ->",
      small["cell"].tolist())
mid = cells[(cells["n"] >= 20) & (cells["n"] < 60)]
print(f"cells with 20<=n<60 (too small for agent's PILOT_N_MIN=60): {len(mid)}  mass%={mid['mass_pct'].sum():.3f}")

sub = (df.dropna(subset=["current_tariff", "arpu_segment", "data_segment"])
       .groupby(["current_tariff", "arpu_segment", "data_segment"])[PA].agg(n="size", mass="sum").reset_index())
print("\nsplits of n>5000 cells by data_segment:")
for _, rr in big.iterrows():
    s2 = sub[(sub.current_tariff == rr.current_tariff) & (sub.arpu_segment == rr.arpu_segment)]
    print(f"  {rr.cell}: " + ", ".join(f"{d}={n}" for d, n in zip(s2.data_segment, s2.n)),
          "| max part", int(s2.n.max()))
print("finer cells (tariff x arpu x data) with n>5000:", int((sub.n > 5000).sum()))
top_hi = cells[cells.arpu_segment == "HIGH"].head(6)
pairs_over = [(a_.cell, b_.cell, int(a_.n + b_.n)) for i, a_ in enumerate(top_hi.itertuples())
              for b_ in list(top_hi.itertuples())[i + 1:] if a_.n + b_.n > 5000]
print("pairs of top-6 HIGH cells that cannot share one campaign (n sum > 5000):", pairs_over)

print("\nper-tariff totals:")
tt = (df.groupby("current_tariff")[PA].agg(n="size", mass="sum", mean="mean")
      .assign(mass_pct=lambda d: 100 * d["mass"] / TOTAL).sort_values("mass", ascending=False))
tt["price"] = dt.set_index("tariff_plan_code")["price_tariff"].reindex(tt.index)
tt["share_HIGH_pct"] = 100 * df[df.arpu_segment == "HIGH"].groupby("current_tariff").size().reindex(tt.index).fillna(0) / tt["n"]
print(tt.round(2).to_string())

print("\ncross-tab arpu_segment x data_segment (row %):")
print(pd.crosstab(df.arpu_segment, df.data_segment, normalize="index").mul(100).round(1).to_string())
print("cross-tab arpu_segment x call_segment (row %):")
print(pd.crosstab(df.arpu_segment, df.call_segment, normalize="index").mul(100).round(1).to_string())
print("counts data_segment x call_segment:")
print(pd.crosstab(df.data_segment, df.call_segment, margins=True).to_string())
for a_, b_ in [("current_tariff", "arpu_segment"), ("current_tariff", "data_segment"), ("current_tariff", "call_segment"),
               ("arpu_segment", "data_segment"), ("arpu_segment", "call_segment"), ("data_segment", "call_segment")]:
    m = df[a_].notna() & df[b_].notna()
    print(f"Cramer's V({a_}, {b_}) = {cramers_v(df.loc[m, a_], df.loc[m, b_]):.3f}")
for c in ["data_segment", "call_segment"]:
    print(f"predicted_arpu by {c}:",
          df.groupby(c)[PA].agg(["size", "mean", "median"]).round(1).to_dict("index"))
print("within-cell refinement: share of predicted_arpu variance explained by data/call segment inside top-5 cells:")
for _, rr in cells.head(5).iterrows():
    g0 = df[(df.current_tariff == rr.current_tariff) & (df.arpu_segment == rr.arpu_segment)]
    for c in ["data_segment", "call_segment"]:
        g = g0.dropna(subset=[c])
        gm = g.groupby(c)[PA].transform("mean")
        r2 = 1 - ((g[PA] - gm) ** 2).sum() / ((g[PA] - g[PA].mean()) ** 2).sum()
        print(f"  {rr.cell:15s} {c:12s} eta^2={r2:.4f}  n={g.groupby(c).size().to_dict()}  "
              f"means={g.groupby(c)[PA].mean().round(0).to_dict()}")

# =================================================================================== 5
h("5. ID ORDERING (scorer keeps first 5000 by ascending ID_NUMBER)")
print(f"spearman(ID, predicted_arpu)={spearman(df.ID_NUMBER, df[PA]):.4f}  "
      f"spearman(ID, ARPU_3m_avg)={spearman(df.ID_NUMBER, df.ARPU_3m_avg):.4f}")
df["id_dec"] = pd.qcut(df["ID_NUMBER"], 10, labels=False) + 1
dec = df.groupby("id_dec").agg(id_min=("ID_NUMBER", "min"), id_max=("ID_NUMBER", "max"),
                               mean_pred=(PA, "mean"), share_HIGH=("arpu_segment", lambda s: (s == "HIGH").mean() * 100),
                               n_tariff_na=("current_tariff", lambda s: s.isna().sum()))
print(dec.round(2).to_string())
m = df.current_tariff.notna()
print(f"Cramer's V(ID decile, current_tariff)={cramers_v(df.loc[m, 'id_dec'], df.loc[m, 'current_tariff']):.4f}  "
      f"Cramer's V(ID decile, arpu_segment)={cramers_v(df.loc[df.arpu_segment.notna(), 'id_dec'], df.loc[df.arpu_segment.notna(), 'arpu_segment']):.4f}")
# null reference for Cramer's V with same shape: shuffled ID deciles (fixed seed)
rng = np.random.default_rng(0)
null = [cramers_v(pd.Series(rng.permutation(df.loc[m, "id_dec"].values)), df.loc[m, "current_tariff"].reset_index(drop=True))
        for _ in range(20)]
print(f"  null Cramer's V(shuffled decile, tariff): mean={np.mean(null):.4f} max={np.max(null):.4f}")

print("\ntruncation bias for groups >5000: mean predicted of first 5000 by ID vs group mean; z vs random 5000")
groups = [("HIGH (all tariffs)", df.arpu_segment == "HIGH"), ("MID (all tariffs)", df.arpu_segment == "MID"),
          ("GROWING trend", df.ARPU_trend == "GROWING")]
groups += [(f"cell {rr.cell}", (df.current_tariff == rr.current_tariff) & (df.arpu_segment == rr.arpu_segment))
           for _, rr in big.iterrows()]
groups += [(f"tariff {tn} (all segments)", df.current_tariff == tn) for tn in tt.index[tt["n"] > 5000]]
groups += [("call_segment LOW (all)", df.call_segment == "LOW")]
for name, mm in groups:
    g = df[mm].sort_values("ID_NUMBER")
    n_ = len(g)
    first = g[PA].iloc[:5000].mean()
    se = g[PA].std() / np.sqrt(5000) * np.sqrt((n_ - 5000) / (n_ - 1))
    print(f"  {name:28s} n={n_:5d} group_mean={g[PA].mean():8.1f} first5000_mean={first:8.1f} "
          f"diff={100 * (first / g[PA].mean() - 1):+.2f}%  z={(first - g[PA].mean()) / se:+.2f}  "
          f"dropped={n_ - 5000}  NaN-tariff rows kept={int(g['current_tariff'].iloc[:5000].isna().sum())}"
          f" of {int(g['current_tariff'].isna().sum())}")
g = df[df.arpu_segment == "HIGH"].sort_values("ID_NUMBER")
mix = pd.DataFrame({"all": g.current_tariff.value_counts(normalize=True),
                    "first5000": g.current_tariff.iloc[:5000].value_counts(normalize=True)}).mul(100).round(2)
print("tariff mix (%) of HIGH, whole vs first 5000 by ID (top 5):\n", mix.sort_values("all", ascending=False).head(5).to_string())

# =================================================================================== 6
h("6. REACH (15,000 contacts)")
REACH = 15000
for k in (625, 4545, 11250, 15000):
    print(f"top {k:5d} subscribers by predicted_arpu hold {100 * cum[k - 1]:.2f}% of mass "
          f"({ps[:k].sum():,.0f}); min predicted_arpu among them {ps[k - 1]:,.1f}")
print("(625 = 100000/160 call contacts; 4545 = 100000/22 digital_ads; 11250 = 15000 minus agent's 25% pilot reach cap)")


def greedy(cells_df, cap, per_cell_max=None):
    rem, used_n, used_m, k = cap, 0, 0.0, 0
    for _, rr in cells_df.sort_values(["mean", "n"], ascending=[False, True]).iterrows():
        if per_cell_max and rr.n > per_cell_max:
            continue
        if rr.n <= rem:
            rem -= rr.n; used_n += rr.n; used_m += rr.mass; k += 1
    return used_n, used_m, k


def finer(cols):
    d = df.dropna(subset=cols).groupby(cols)[PA].agg(n="size", mass="sum").reset_index()
    return d.assign(mean=d["mass"] / d["n"])


variants = [("tariff x arpu (whole cells)", cells),
            ("tariff x arpu, cells n>=20 only", cells[cells.n >= 20]),
            ("tariff x arpu x data", finer(["current_tariff", "arpu_segment", "data_segment"])),
            ("tariff x arpu x call", finer(["current_tariff", "arpu_segment", "call_segment"])),
            ("tariff x arpu x data x call", finer(["current_tariff", "arpu_segment", "data_segment", "call_segment"]))]
print("greedy whole-cell packing by mean predicted_arpu (each cell n<=5000, skip cells that do not fit):")
for name, cd in variants:
    for cap in (15000, 11250):
        un, um, k = greedy(cd, cap, 5000)
        print(f"  {name:34s} cap={cap}: cells={k:3d} of {len(cd):3d} contacts={int(un):5d} mass={um:,.0f} ({pct(um, TOTAL):.2f}%)")
hi = df.arpu_segment == "HIGH"
print(f"all HIGH subscribers: n={int(hi.sum())} mass={df.loc[hi, PA].sum():,.0f} ({pct(df.loc[hi, PA].sum(), TOTAL):.2f}%)")
top4 = cells.head(4)
print(f"top-4 cells by mass {top4['cell'].tolist()}: n={int(top4['n'].sum())} mass%={top4['mass_pct'].sum():.2f}")
print("best cells by mean predicted_arpu (n>=20):")
print(cells[cells.n >= 20].sort_values("mean", ascending=False).head(10)[["cell", "n", "mean", "mass_pct"]].round(2).to_string(index=False))

print("\nchannel break-even: base lift ratio (arpu_change_pct x conversion) needed per subscriber to prefer the "
      "costlier channel, at the median predicted_arpu of each segment (ignores the conversion cap at 1)")
CH = {"push": (0, .50), "sms": (4, .65), "digital_ads": (22, .85), "call": (160, 1.20)}
pairs = [("push", "sms"), ("sms", "digital_ads"), ("digital_ads", "call"), ("sms", "call")]
for sname in ["LOW", "MID", "HIGH"]:
    med = df.loc[df.arpu_segment == sname, PA].median()
    out = {f"{lo}->{hi}": round(float((CH[hi][0] - CH[lo][0]) / ((CH[hi][1] - CH[lo][1]) * med)), 5) for lo, hi in pairs}
    out["sms_breaks_even"] = round(float(4 / (.65 * med)), 5)
    print(f"  {sname:4s} median predicted={med:8.1f}: {out}")

# =================================================================================== charts
h("CHART ROWS (JSON)")
c1 = cells.head(25)[["cell", "n", "mass", "mean"]].copy()
c1["mass"] = c1["mass"].round(0)
c1["mean"] = c1["mean"].round(1)
print("chart1_mass_by_cell =", json.dumps(c1.to_dict("records")))
c2 = seg_tr.assign(group=seg_tr["arpu_segment"] + "/" + seg_tr["ARPU_trend"])[["group", "arpu_segment", "n", "p25", "p50", "p75"]]
c2 = c2.assign(sort=c2["arpu_segment"].map({"LOW": 0, "MID": 1, "HIGH": 2})).sort_values(["sort", "group"]).drop(columns="sort")
print("chart2_pred_by_segment_trend =", json.dumps(c2.round(1).to_dict("records")))
xs = list(range(0, 22501, 1500)) + [N]
ind = [0.0 if k == 0 else round(100 * cum[k - 1], 2) for k in xs]
cel = [round(100 * greedy(cells, k, 5000)[1] / TOTAL, 2) for k in xs]
c3 = [{"contacts": k, "series": "best subscribers", "mass_pct": v} for k, v in zip(xs, ind)]
c3 += [{"contacts": k, "series": "whole tariff x arpu cells", "mass_pct": v} for k, v in zip(xs, cel)]
print("chart3_cumulative =", json.dumps(c3))
