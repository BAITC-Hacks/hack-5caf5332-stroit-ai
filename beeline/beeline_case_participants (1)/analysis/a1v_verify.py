"""a1v: independent re-derivation of the a1 'Target audience profile' claims from raw customer_profile.csv.
Deterministic (fixed seeds). Prints every number used in the verification."""
import math
import os

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
df = pd.read_csv(os.path.join(ROOT, "customer_profile.csv"))
ct = pd.read_csv(os.path.join(ROOT, "data", "change_tariff.csv"))
PA = "predicted_arpu"
N = len(df)
TOT = float(df[PA].sum())
USAGE = ["OUT_LOC_ONNET_MIN", "OUT_LOC_OFFNET_MIN", "OUT_LOC_OFFNET_UNPAID_MIN", "OUT_LOC_OFFNET_PAID_MIN",
         "OUT_INTER_MIN", "OUT_LOC_LAND_MIN", "OUT_LOCAL_ONNET_SMS_AMT", "OUT_LOCAL_OFFNET_SMS_AMT",
         "OUT_LOCAL_LAND_PAID_SMS_AMT", "OUT_INTER_SMS_AMT", "DATA_VOLUME", "LTE_DATA_VOLUME",
         "TOTAL_ROAM_CALL_AMT", "TOTAL_ROAM_SMS_AMT", "TOTAL_ROAM_GPRS_MB"]
CONTACT = ["COUNT_CONTACT", "AVG_TRANSACT_CONTACT", "SUM_TRANSACT_CONTACT", "AVG_DURATION_CONTACT"]


def sec(t):
    print(f"\n##### {t}")


def share(m):
    return 100.0 * float(df.loc[m, PA].sum()) / TOT


def agree(pred, lab, mask):
    return 100.0 * float((pd.Series(pred, index=df.index)[mask] == lab[mask]).mean())


def cramers_v(a, b):
    t = pd.crosstab(a, b).to_numpy(dtype=float)
    e = np.outer(t.sum(1), t.sum(0)) / t.sum()
    chi2 = float(((t - e) ** 2 / e).sum())
    return math.sqrt(chi2 / (t.sum() * (min(t.shape) - 1)))


def spearman(a, b):
    m = a.notna() & b.notna()
    return float(np.corrcoef(a[m].rank().to_numpy(), b[m].rank().to_numpy())[0, 1])


def ols(y, cols):
    X = np.column_stack([np.ones(len(y))] + cols)
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    r2 = 1 - ((y - X @ b) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return b, r2


print(f"rows={N} cols={df.shape[1]} total_mass={TOT:,.2f}")

# ------------------------------------------------------------------ a1-01 missingness
sec("a1-01 missingness")
na = df.isna().sum()
print("NaN per column:", {k: int(v) for k, v in na[na > 0].items()})
tar = df["current_tariff"].isna()
ause = df[USAGE].isna().all(axis=1)
anyuse = df[USAGE].isna().any(axis=1)
dseg = df["data_segment"].isna()
aseg = df["arpu_segment"].isna()
print("all-usage-NaN", int(ause.sum()), "any-usage-NaN", int(anyuse.sum()), "data_seg NaN", int(dseg.sum()),
      "data_seg NaN == all-usage NaN:", bool((dseg == ause).all()))
print("tariff NaN", int(tar.sum()), "inside all-usage-NaN:", int((tar & ause).sum()))
print("tariff NaN with all CONTACT NaN:", int((tar & df[CONTACT].isna().all(axis=1)).sum()),
      "| with COUNT_BASE_STATION NaN:", int((tar & df["COUNT_BASE_STATION"].isna()).sum()))
print("CONTACT all-NaN rows:", int(df[CONTACT].isna().all(axis=1).sum()))
print("arpu_seg NaN", int(aseg.sum()), "== ARPU_3m_avg NaN:", bool((aseg == df["ARPU_3m_avg"].isna()).all()),
      "== ARPU_trend NaN:", bool((aseg == df["ARPU_trend"].isna()).all()), "overlap with tariff NaN:", int((aseg & tar).sum()))
print("call_segment NaN:", int(df["call_segment"].isna().sum()),
      "| call_segment of all-usage-NaN rows:", df.loc[ause, "call_segment"].value_counts(dropna=False).to_dict())
print("arpu_segment of tariff-NaN rows:", df.loc[tar, "arpu_segment"].value_counts(dropna=False).to_dict())

# ------------------------------------------------------------------ a1-02 unreachable
sec("a1-02 unreachable mass")
for nm, m in [("tariff", tar), ("arpu_seg", aseg), ("either", tar | aseg), ("data_seg", dseg)]:
    print(f"{nm}: n={int(m.sum())} mass={df.loc[m, PA].sum():,.2f} ({share(m):.3f}%)")

# ------------------------------------------------------------------ a1-03 dups, zeros, outlier
sec("a1-03 duplicates/zeros/outlier")
print("dup IDs:", int(df["ID_NUMBER"].duplicated().sum()), "| ID ascending:", bool(df["ID_NUMBER"].is_monotonic_increasing))
num = df.select_dtypes("number")
print("negative values in any numeric column:", int((num < 0).sum().sum()))
for c in ["ARPU_current", "ARPU_3m_avg", PA]:
    print(f"{c} ==0: {int((df[c] == 0).sum())}")
z = df[PA] == 0
print("pred==0 arpu_segment:", df.loc[z, "arpu_segment"].value_counts(dropna=False).to_dict(),
      "trend:", df.loc[z, "ARPU_trend"].value_counts(dropna=False).to_dict(),
      "ARPU_3m_avg==0 among them:", int((z & (df["ARPU_3m_avg"] == 0)).sum()))
print("ARPU_3m_avg==0 rows with pred>0:", int(((df["ARPU_3m_avg"] == 0) & ~z).sum()))
i = df[PA].idxmax()
p99 = float(df[PA].quantile(0.99))
print(f"max pred={df.at[i, PA]:.2f} ID={int(df.at[i, 'ID_NUMBER'])} ARPU_3m_avg={df.at[i, 'ARPU_3m_avg']:.2f} "
      f"cell={df.at[i, 'current_tariff']}/{df.at[i, 'arpu_segment']} p99={p99:.2f} ratio={df.at[i, PA] / p99:.2f} "
      f"share={100 * df.at[i, PA] / TOT:.4f}%")
cm = (df["current_tariff"] == df.at[i, "current_tariff"]) & (df["arpu_segment"] == df.at[i, "arpu_segment"])
print(f"its cell mean with / without it: {df.loc[cm, PA].mean():.2f} / {df.loc[cm & (df.index != i), PA].mean():.2f}")

# ------------------------------------------------------------------ a1-04 arpu_segment
sec("a1-04 arpu_segment")
a = df["ARPU_3m_avg"]
ok = aseg.eq(False)
lab = df["arpu_segment"]
print("rows at 1000:", int((a == 1000).sum()), "at 5000:", int((a == 5000).sum()))
print(f"brief (<1000,[1000,5000],>5000): {agree(np.where(a < 1000, 'LOW', np.where(a <= 5000, 'MID', 'HIGH')), lab, ok):.3f}%")
print(f"right=True (<=1000,<=5000): {agree(np.where(a <= 1000, 'LOW', np.where(a <= 5000, 'MID', 'HIGH')), lab, ok):.3f}%")
print(f"right=False (<1000,<5000): {agree(np.where(a < 1000, 'LOW', np.where(a < 5000, 'MID', 'HIGH')), lab, ok):.3f}%")
c = df["ARPU_current"]
okc = ok & c.notna()
print(f"ARPU_current same rule: {agree(np.where(c < 1000, 'LOW', np.where(c <= 5000, 'MID', 'HIGH')), lab, okc):.3f}%")
print("closest ARPU_3m_avg to 1000 / 5000 (abs diff):", float((a - 1000).abs().min()), float((a - 5000).abs().min()))
print("history AVG_ARPU_PREV_3M exactly 1000:", int((ct.AVG_ARPU_PREV_3M == 1000).sum()),
      "exactly 5000:", int((ct.AVG_ARPU_PREV_3M == 5000).sum()))

# ------------------------------------------------------------------ a1-05 data_segment
sec("a1-05 data_segment")
okd = dseg.eq(False)
dl = df["data_segment"]
D, L, G = df["DATA_VOLUME"], df["LTE_DATA_VOLUME"], df["TOTAL_ROAM_GPRS_MB"]
for nm, s in [("DATA", D), ("LTE", L), ("DATA+LTE", D + L), ("max", np.maximum(D, L)), ("DATA+ROAM", D + G)]:
    print(f"{nm}: {agree(np.where(s <= 0, 'NON_USER', np.where(s <= 2000, 'LITE', 'HEAVY')), dl, okd):.3f}%")
print("DATA exactly 0:", int((D == 0).sum()), "exactly 2000:", int((D == 2000).sum()), "negative:", int((D < 0).sum()))
print(f"LTE>DATA among non-NaN: {100 * float((L[okd] > D[okd]).mean()):.2f}%  NON_USER with LTE>0: {int(((dl == 'NON_USER') & (L > 0)).sum())}")

# ------------------------------------------------------------------ a1-06 call_segment
sec("a1-06 call_segment")
cl = df["call_segment"]
U = df[USAGE].fillna(0)
okall = cl.notna()
nou = ~ause
for nm, s in [("ONNET", U.OUT_LOC_ONNET_MIN), ("ONNET+OFFNET", U.OUT_LOC_ONNET_MIN + U.OUT_LOC_OFFNET_MIN),
              ("+LAND", U.OUT_LOC_ONNET_MIN + U.OUT_LOC_OFFNET_MIN + U.OUT_LOC_LAND_MIN),
              ("+INTER", U.OUT_LOC_ONNET_MIN + U.OUT_LOC_OFFNET_MIN + U.OUT_INTER_MIN),
              ("ONNET+OFFNET_PAID", U.OUT_LOC_ONNET_MIN + U.OUT_LOC_OFFNET_PAID_MIN)]:
    v = np.where(s < 100, "LOW", np.where(s <= 400, "MEDIUM", "HIGH"))
    print(f"{nm}: all rows {agree(v, cl, okall):.3f}%  usage-present rows {agree(v, cl, nou):.3f}%")
m = U.OUT_LOC_ONNET_MIN + U.OUT_LOC_OFFNET_MIN
print("range by label (usage-present):", df[nou].assign(m=m[nou]).groupby("call_segment")["m"].agg(["min", "max"]).round(3).to_dict("index"))

# ------------------------------------------------------------------ a1-07 predicted vs ARPU
sec("a1-07 predicted_arpu regressions")
x = df.dropna(subset=["ARPU_current", "ARPU_3m_avg"])
tr = x[(x.ARPU_3m_avg <= x.ARPU_3m_avg.quantile(.99)) & (x.ARPU_current <= x.ARPU_current.quantile(.99))]
y = tr[PA].to_numpy()
b1, r1 = ols(y, [tr.ARPU_3m_avg.to_numpy()])
b2, r2 = ols(y, [tr.ARPU_3m_avg.to_numpy(), tr.ARPU_current.to_numpy()])
print(f"trimmed n={len(tr)}: pred={b1[0]:.2f}+{b1[1]:.4f}*3m R2={r1:.3f}; 2-var {b2[0]:.2f}+{b2[1]:.4f}*3m{b2[2]:+.4f}*cur R2={r2:.3f}")
print(f"fixed point={b1[0] / (1 - b1[1]):,.0f} mean pred={df[PA].mean():,.0f}")
bu, ru = ols(x[PA].to_numpy(), [x.ARPU_3m_avg.to_numpy(), x.ARPU_current.to_numpy()])
print(f"untrimmed 2-var: {bu[0]:.2f}+{bu[1]:.4f}*3m{bu[2]:+.4f}*cur R2={ru:.3f}")
exact = df[PA] == df["ARPU_3m_avg"]
vc = df[PA].value_counts()
consts = [v for v, k in vc.items() if k >= 100 and v > 0]
isconst = df[PA].isin(consts)
model = ~(exact | isconst | z)
xm = tr[model.loc[tr.index]]
bm, rm = ols(xm[PA].to_numpy(), [xm.ARPU_3m_avg.to_numpy(), xm.ARPU_current.to_numpy()])
bm1, rm1 = ols(xm[PA].to_numpy(), [xm.ARPU_3m_avg.to_numpy()])
print(f"model rows only trimmed n={len(xm)}: 1-var slope {bm1[1]:.4f} R2={rm1:.3f}; 2-var {bm[0]:.2f}+{bm[1]:.4f}*3m{bm[2]:+.4f}*cur R2={rm:.3f}")
pos = x[(x.ARPU_3m_avg > 100) & (x[PA] > 0)]
bl, rl = ols(np.log(pos[PA].to_numpy()), [np.log(pos.ARPU_3m_avg.to_numpy())])
print(f"log-log n={len(pos)} elasticity={bl[1]:.3f} R2={rl:.3f}")
pm = x[(x.ARPU_3m_avg > 100) & model.loc[x.index]]
blm, rlm = ols(np.log(pm[PA].to_numpy()), [np.log(pm.ARPU_3m_avg.to_numpy())])
print(f"log-log model rows n={len(pm)} elasticity={blm[1]:.3f} R2={rlm:.3f}")
dec = pd.qcut(x["ARPU_3m_avg"].rank(method="first"), 10, labels=False)
dm = x.groupby(dec)[["ARPU_3m_avg", PA]].median()
print("decile medians first/last:", dm.iloc[0].round(0).to_dict(), dm.iloc[-1].round(0).to_dict())
print(f"spearman(pred, 3m)={spearman(x[PA], x.ARPU_3m_avg):.3f}  spearman(pred, cur)={spearman(x[PA], x.ARPU_current):.3f}")

# ------------------------------------------------------------------ a1-08 row kinds
sec("a1-08 row kinds")
close = np.isclose(df[PA], df["ARPU_3m_avg"])
print("exact == 3m:", int(exact.sum()), "isclose == 3m:", int(close.sum()), "of which zeros:", int((exact & z).sum()))
print("repeated values >=100:", {round(float(v), 2): int(vc[v]) for v in vc.index if vc[v] >= 100})
print(f"constant rows={int(isconst.sum())} ({100 * isconst.mean():.2f}%) mass share={share(isconst):.2f}% "
      f"ARPU_3m_avg range {df.loc[isconst, 'ARPU_3m_avg'].min():.0f}-{df.loc[isconst, 'ARPU_3m_avg'].max():.0f}")
print("kinds: zero", int(z.sum()), "const", int((isconst & ~z).sum()), "equal", int((exact & ~z & ~isconst).sum()),
      "model", int(model.sum()), "| equal+zero", int((exact & ~isconst).sum()), f"({100 * (exact & ~isconst).mean():.2f}%)")
print("LOW share const rows vs base (non-NaN seg):",
      round(100 * float((df.loc[isconst, 'arpu_segment'] == 'LOW').sum() / df.loc[isconst, 'arpu_segment'].notna().sum()), 1),
      round(100 * float((lab == 'LOW').sum() / ok.sum()), 1))
for v in consts:
    g = df[df[PA] == v]
    print(f"  const {v:.2f}: trend {g.ARPU_trend.value_counts().to_dict()} seg {g.arpu_segment.value_counts().to_dict()} "
          f"tariffs {g.current_tariff.nunique()} ARPU_cur==0 {int((g.ARPU_current == 0).sum())} usageNaN {int(ause[g.index].sum())}")
print("const rows by ARPU_trend share of trend group (%):",
      (df.groupby("ARPU_trend").apply(lambda g: 100 * g[PA].isin(consts).mean(), include_groups=False)).round(2).to_dict())

# ------------------------------------------------------------------ a1-09 value by segment
sec("a1-09 segment value")
xr = df[df.ARPU_3m_avg > 0]
for s in ["LOW", "MID", "HIGH"]:
    g = df[lab == s]
    gr = xr[xr.arpu_segment == s]
    g100 = gr[gr.ARPU_3m_avg >= 100]
    print(f"{s}: n={len(g)} ({100 * len(g) / N:.2f}%) mass {share(lab == s):.2f}% median_pred={g[PA].median():.2f} "
          f"median ratio={(gr[PA] / gr.ARPU_3m_avg).median():.3f} aggregate ratio sum(pred)/sum(3m)={g[PA].sum() / g.ARPU_3m_avg.sum():.3f} "
          f"median ratio (3m>=100)={(g100[PA] / g100.ARPU_3m_avg).median():.3f}")
lo = df.ARPU_3m_avg < 100
print(f"ARPU_3m_avg<100: n={int(lo.sum())} ({100 * lo.mean():.2f}%) mass {share(lo):.2f}%")

# ------------------------------------------------------------------ a1-10 concentration
sec("a1-10 concentration")
ps = np.sort(df[PA].to_numpy())[::-1]
cum = np.cumsum(ps) / ps.sum()
for q in (0.01, 0.10, 0.25, 0.50):
    k = int(round(q * N))
    print(f"top {q:.0%} k={k}: {100 * cum[k - 1]:.2f}%")


def gini(v):
    v = np.sort(v)
    n = len(v)
    return float(((2 * np.arange(1, n + 1) - n - 1) * v).sum() / (n * v.sum()))


print(f"gini pred={gini(df[PA].to_numpy()):.4f} gini 3m={gini(df.ARPU_3m_avg.dropna().to_numpy()):.4f}")

# ------------------------------------------------------------------ a1-11 cells
sec("a1-11 cells")
cells = (df.dropna(subset=["current_tariff", "arpu_segment"]).groupby(["current_tariff", "arpu_segment"])[PA]
         .agg(n="size", mass="sum").reset_index())
cells["cell"] = cells.current_tariff + "/" + cells.arpu_segment
cells["mean"] = cells.mass / cells.n
cells = cells.sort_values("mass", ascending=False).reset_index(drop=True)
cells["pct"] = 100 * cells.mass / TOT
cells["cum"] = cells.pct.cumsum()
print("tariffs in profile:", df.current_tariff.nunique(), "non-empty cells:", len(cells))
print(cells.head(10)[["cell", "n", "mass", "mean", "pct", "cum"]].round(2).to_string(index=False))
for q in (50, 80, 95):
    print(f"cells to reach {q}%: {int(np.argmax(cells.cum.to_numpy() >= q)) + 1}")
print("largest n:", int(cells.n.max()), "cells n>5000:", int((cells.n > 5000).sum()))
s20 = cells[cells.n < 20]
s60 = cells[(cells.n >= 20) & (cells.n < 60)]
print(f"n<20: {len(s20)} cells, {int(s20.n.sum())} subs, {s20.pct.sum():.3f}%; 20<=n<60: {len(s60)} cells, {s60.pct.sum():.3f}%;"
      f" total <60: {len(s20) + len(s60)} cells {s20.pct.sum() + s60.pct.sum():.3f}%")

# ------------------------------------------------------------------ a1-12 pairs
sec("a1-12 pairs")
hi6 = cells[cells.arpu_segment == "HIGH"].head(6)
for ii in range(6):
    for jj in range(ii + 1, 6):
        s = int(hi6.n.iloc[ii] + hi6.n.iloc[jj])
        if s > 5000:
            print(f"{hi6.cell.iloc[ii]} + {hi6.cell.iloc[jj]} = {s} (over by {s - 5000})")

# ------------------------------------------------------------------ a1-13 association
sec("a1-13 association")
for p_, q_ in [("current_tariff", "arpu_segment"), ("current_tariff", "data_segment"),
               ("current_tariff", "call_segment"), ("arpu_segment", "call_segment"), ("arpu_segment", "data_segment")]:
    mm = df[p_].notna() & df[q_].notna()
    print(f"V({p_},{q_})={cramers_v(df.loc[mm, p_], df.loc[mm, q_]):.3f}")
for _, rr in cells.head(5).iterrows():
    g0 = df[(df.current_tariff == rr.current_tariff) & (df.arpu_segment == rr.arpu_segment)]
    out = []
    for col in ["data_segment", "call_segment"]:
        g = g0.dropna(subset=[col])
        gm = g.groupby(col)[PA].transform("mean")
        out.append(f"{col} eta2={1 - ((g[PA] - gm) ** 2).sum() / ((g[PA] - g[PA].mean()) ** 2).sum():.4f}")
    print(rr.cell, out, "call means", g0.groupby("call_segment")[PA].mean().round(0).to_dict())

# ------------------------------------------------------------------ a1-14 ID ordering
sec("a1-14 ID ordering")
rho = spearman(df.ID_NUMBER, df[PA])
print(f"spearman(ID,pred)={rho:.4f} z~{rho * math.sqrt(N - 1):.2f}")
dd = pd.qcut(df.ID_NUMBER, 10, labels=False)
mt = df.current_tariff.notna()
v0 = cramers_v(dd[mt], df.current_tariff[mt])
rng = np.random.default_rng(12345)
nul = [cramers_v(pd.Series(rng.permutation(dd[mt].to_numpy())), df.current_tariff[mt].reset_index(drop=True)) for _ in range(200)]
print(f"V(ID decile, tariff)={v0:.4f} null(200 perms) mean={np.mean(nul):.4f} p95={np.quantile(nul, .95):.4f} max={np.max(nul):.4f} "
      f"perm p-value={(1 + sum(u >= v0 for u in nul)) / 201:.4f}")
for nm, mm in [("HIGH", lab == "HIGH"), ("MID", lab == "MID"), ("tariff_8 all", df.current_tariff == "tariff_8"),
               ("call LOW", cl == "LOW")]:
    g = df[mm].sort_values("ID_NUMBER")
    n_ = len(g)
    f = g[PA].iloc[:5000].mean()
    se = g[PA].std() / math.sqrt(5000) * math.sqrt((n_ - 5000) / (n_ - 1))
    print(f"{nm}: n={n_} first5000 vs all {100 * (f / g[PA].mean() - 1):+.2f}% z={(f - g[PA].mean()) / se:+.2f} "
          f"NaN-tariff kept {int(g.current_tariff.iloc[:5000].isna().sum())} of {int(g.current_tariff.isna().sum())}")
gh = df[lab == "HIGH"].sort_values("ID_NUMBER")
print(f"HIGH tariff_8 share all {100 * (gh.current_tariff == 'tariff_8').mean():.2f}% first5000 "
      f"{100 * (gh.current_tariff.iloc[:5000] == 'tariff_8').mean():.2f}%")

# ------------------------------------------------------------------ a1-15 reach
sec("a1-15 reach")
for k in (625, 4545, 11250, 15000):
    print(f"top {k}: {100 * cum[k - 1]:.2f}% min value {ps[k - 1]:.2f}")
print(f"marginal: 100 contacts at rank 15000 = {100 * 100 * ps[14999] / TOT:.3f}% of mass; "
      f"avg slope 11250->15000 individuals {100 * (cum[14999] - cum[11249]) / 37.5:.3f}% per 100")


def greedy(cd, cap):
    rem, un, um, k = cap, 0, 0.0, 0
    for _, rr in cd.sort_values(["mean", "n"], ascending=[False, True]).iterrows():
        if rr.n <= 5000 and rr.n <= rem:
            rem -= rr.n; un += rr.n; um += rr.mass; k += 1
    return int(un), um, k


def knap(cd, cap):
    best = np.zeros(cap + 1)
    for n_, m_ in zip(cd.n.astype(int), cd.mass):
        best[n_:] = np.maximum(best[n_:], best[:cap + 1 - n_] + m_)
    return float(best.max())


def finer(cols):
    d = df.dropna(subset=cols).groupby(cols)[PA].agg(n="size", mass="sum").reset_index()
    return d.assign(mean=d.mass / d.n)


for nm, cd in [("tariff x arpu", cells), ("x data", finer(["current_tariff", "arpu_segment", "data_segment"])),
               ("x call", finer(["current_tariff", "arpu_segment", "call_segment"])),
               ("x data x call", finer(["current_tariff", "arpu_segment", "data_segment", "call_segment"]))]:
    for cap in (15000, 11250):
        un, um, k = greedy(cd, cap)
        print(f"{nm} cap {cap}: greedy cells={k}/{len(cd)} contacts={un} {100 * um / TOT:.2f}%  "
              f"exact knapsack {100 * knap(cd, cap) / TOT:.2f}%")
un15, um15, _ = greedy(cells, 15000)
un11, um11, _ = greedy(cells, 11250)
print(f"avg slope cells 11250->15000: {100 * (um15 - um11) / TOT / 37.5:.3f}% per 100 contacts")
hi = lab == "HIGH"
print(f"all HIGH n={int(hi.sum())} {share(hi):.2f}%; top-4 cells n={int(cells.n.head(4).sum())} {cells.pct.head(4).sum():.2f}%")

# ------------------------------------------------------------------ a1-16 channels
sec("a1-16 channel break-even")
CH = {"push": (0, .50), "sms": (4, .65), "digital_ads": (22, .85), "call": (160, 1.20)}
print("affordable call", 100000 // 160, "digital", 100000 // 22, "sms", 100000 // 4)
for s in ["HIGH", "MID", "LOW"]:
    med = float(df.loc[lab == s, PA].median())
    be = {f"{p_}->{q_}": round((CH[q_][0] - CH[p_][0]) / ((CH[q_][1] - CH[p_][1]) * med), 5)
          for p_, q_ in [("push", "sms"), ("sms", "digital_ads"), ("digital_ads", "call")]}
    print(f"{s} median {med:.1f} sms-vs-nothing {4 / (.65 * med):.5f} {be}")
