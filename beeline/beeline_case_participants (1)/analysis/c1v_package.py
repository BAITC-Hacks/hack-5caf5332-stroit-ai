"""c1v: re-derive c1-08, c1-09, c1-10 (package fit) and c1-13 (within-cell segment effects, permutation tests)."""
import os
import numpy as np
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ct = pd.read_csv(os.path.join(P, "data", "change_tariff.csv"))
tr = pd.read_csv(os.path.join(P, "data", "traffic.csv"))
dt = pd.read_csv(os.path.join(P, "data", "dict_tariff.csv")).set_index("tariff_plan_code")
pr = pd.read_csv(os.path.join(P, "customer_profile.csv"))
Q2 = ["2026-07-01", "2026-08-01", "2026-09-01"]
ORDER = ["NO_PKG", "ZERO_USE", "<=50%", "50-100%", "EXCEEDS"]

cols = ["DATA_VOLUME", "OUT_LOC_ONNET_MIN", "OUT_LOC_OFFNET_MIN", "OUT_LOC_LAND_MIN", "OUT_LOC_OFFNET_PAID_MIN"]
use = tr[tr.time_key.isin(Q2)].groupby("ID_NUMBER")[cols].mean()
d = ct.merge(use, left_on="ID_NUMBER", right_index=True, how="inner")
d = d[d.AVG_ARPU_PREV_3M >= 100].reset_index(drop=True)
d["y"] = ((d.AVG_ARPU_NEXT_3M - d.AVG_ARPU_PREV_3M) / d.AVG_ARPU_PREV_3M).clip(-1, 3)
d["seg"] = pd.cut(d.AVG_ARPU_PREV_3M, [-np.inf, 1000, 5000, np.inf], labels=["LOW", "MID", "HIGH"]).astype(str)
d["dseg"] = np.where(d.DATA_VOLUME <= 0, "NON_USER", np.where(d.DATA_VOLUME <= 2000, "LITE", "HEAVY"))
cm = d.OUT_LOC_ONNET_MIN + d.OUT_LOC_OFFNET_MIN
d["cseg"] = np.where(cm < 100, "LOW", np.where(cm <= 400, "MEDIUM", "HIGH"))
print("rows PREV>=100 with Jul-Sep traffic:", len(d), " usage NaN:", int(d.DATA_VOLUME.isna().sum()))

mpk = dt.Min_another_operator_in_PKG + dt.Min_another_operator_and_city_in_PKG
land = dt.Min_another_operator_and_city_in_PKG > 0


def bucket(u, pkg):
    ratio = u / pkg.replace(0, np.nan)
    return pd.Series(np.select([pkg <= 0, u <= 0, ratio <= 0.5, ratio <= 1], ORDER[:4], "EXCEEDS"), index=u.index)


for side, col in [("from", "tariff_plan_code_from"), ("to", "tariff_plan_code_to")]:
    d[f"dp_{side}"] = d[col].map(dt.Data_in_PKG)
    d[f"mp_{side}"] = d[col].map(mpk)
    d[f"mu_{side}"] = d.OUT_LOC_OFFNET_MIN + np.where(d[col].map(land), d.OUT_LOC_LAND_MIN, 0)
d["cell"] = d.tariff_plan_code_from + "|" + d.seg + "|" + d.tariff_plan_code_to
d["n_cell"] = d.groupby("cell").y.transform("size")
d["res"] = d.y - d.groupby("cell").y.transform("mean")
big = d[d.n_cell >= 20]
print("within-cell rows (cells n>=20):", len(big), " cells:", big.cell.nunique())


def show(df, key, val, order=None):
    g = df.groupby(key)[val].agg(["size", "mean", "std"])
    g["ci"] = 1.96 * g["std"] / np.sqrt(g["size"])
    if order:
        g = g.reindex([o for o in order if o in g.index])
    return {k: (int(r["size"]), round(r["mean"], 4), round(r.ci, 4)) for k, r in g.iterrows()}


print("\n=== c1-08 data vs current package ===")
d["dcur"] = bucket(d.DATA_VOLUME, d.dp_from)
big = d[d.n_cell >= 20]
print("raw:", show(d, "dcur", "y", ORDER))
print("within:", show(big, "dcur", "res", ORDER))
d["mcur"] = bucket(d.mu_from, d.mp_from)
big = d[d.n_cell >= 20]
print("offnet raw:", show(d, "mcur", "y", ORDER))
print("offnet within:", show(big, "mcur", "res", ORDER))
print("paid offnet share by minute bucket:", d.assign(p=d.OUT_LOC_OFFNET_PAID_MIN > 0).groupby("mcur").p.mean().reindex(ORDER).round(4).to_dict())
# does the EXCEEDS effect survive controlling for PREV level within cell? (partial regression on log PREV)
b2 = big.copy()
b2["lp"] = np.log(b2.AVG_ARPU_PREV_3M)
b2["lp_r"] = b2.lp - b2.groupby("cell").lp.transform("mean")
b2["ex"] = (b2.dcur == "EXCEEDS").astype(float)
b2["ex_r"] = b2.ex - b2.groupby("cell").ex.transform("mean")
X = np.column_stack([b2.ex_r, b2.lp_r])
beta, *_ = np.linalg.lstsq(X, b2.res.to_numpy(), rcond=None)
resid = b2.res.to_numpy() - X @ beta
cov = np.linalg.inv(X.T @ X) * (resid @ resid) / (len(b2) - 2 - b2.cell.nunique())
print(f"within-cell OLS res ~ EXCEEDS + logPREV: beta_EXCEEDS={beta[0]:.4f} se={np.sqrt(cov[0, 0]):.4f}; beta_logPREV={beta[1]:.4f} se={np.sqrt(cov[1, 1]):.4f}")

print("\n=== target vs history data-fit shares ===")
p = pr[pr.DATA_VOLUME.notna() & pr.current_tariff.notna()]
pb = bucket(p.DATA_VOLUME, p.current_tariff.map(dt.Data_in_PKG))
print("target:", pb.value_counts(normalize=True).reindex(ORDER).round(4).to_dict(), " n=", len(p))
print("history:", d.dcur.value_counts(normalize=True).reindex(ORDER).round(4).to_dict())

print("\n=== c1-09 destination fit ===")
d["dto"] = np.where(d.DATA_VOLUME <= d.dp_to, "FITS", "EXCEEDS_DEST")
d["mto"] = np.where(d.mu_to <= d.mp_to, "FITS", "EXCEEDS_DEST")
big = d[d.n_cell >= 20]
print("data raw:", show(d, "dto", "y"), " within:", show(big, "dto", "res"))
print("min raw:", show(d, "mto", "y"))

print("\n=== c1-10 destination choice vs from-mix (and vs (from,seg)-mix) ===")
for keys, lab in [(["tariff_plan_code_from"], "from"), (["tariff_plan_code_from", "seg"], "from,seg")]:
    mix = d.groupby(keys + ["tariff_plan_code_to"]).size()
    mix = (mix / mix.groupby(level=list(range(len(keys)))).transform("sum")).rename("p").reset_index()
    mix["pk"] = mix.tariff_plan_code_to.map(dt.Data_in_PKG)
    mix["mk"] = mix.tariff_plan_code_to.map(dt.Min_another_operator_in_PKG + dt.Min_another_operator_and_city_in_PKG)
    m = d[["ID_NUMBER", "DATA_VOLUME", "OUT_LOC_OFFNET_MIN", "dcur", "mcur"] + keys].reset_index().merge(mix, on=keys)
    m["f"] = (m.DATA_VOLUME <= m.pk) * m.p
    m["fm"] = (m.OUT_LOC_OFFNET_MIN <= m.mk) * m.p
    e = m.groupby("index")[["f", "fm"]].sum()
    d["exp_d"], d["exp_m"] = e.f, e.fm
    d["act_d"] = (d.DATA_VOLUME <= d.dp_to).astype(float)
    d["act_m"] = (d.OUT_LOC_OFFNET_MIN <= d.mp_to).astype(float)
    ex = d[d.dcur == "EXCEEDS"]
    df_ = ex.act_d - ex.exp_d
    print(f"[{lab}] data EXCEEDS: actual {ex.act_d.mean():.4f} expected {ex.exp_d.mean():.4f} lift {df_.mean() * 100:.2f} pp +- {1.96 * df_.std() / np.sqrt(len(df_)) * 100:.2f} (n={len(ex)})")
    b = d[d.dcur == "50-100%"]
    print(f"[{lab}] data 50-100%: lift {(b.act_d - b.exp_d).mean() * 100:.2f} pp")
    em = d[d.mcur == "EXCEEDS"]
    print(f"[{lab}] offnet EXCEEDS: lift {(em.act_m - em.exp_m).mean() * 100:.2f} pp (n={len(em)})")
print("data EXCEEDS share moving to bigger data pkg:", round(float((d.dp_to > d.dp_from)[d.dcur == "EXCEEDS"].mean()), 4))

print("\n=== c1-13 within-cell segment effects (permutation, own implementation, seed 7) ===")
rng = np.random.default_rng(7)


def perm_test(df, cellcol, segcol, nperm=1000):
    df = df.reset_index(drop=True)
    r = (df.y - df.groupby(cellcol).y.transform("mean")).to_numpy()
    cc = pd.factorize(df[cellcol])[0]
    sc = pd.factorize(df[segcol])[0]
    k = sc.max() + 1

    def stat(lab):
        key = cc * k + lab
        s, n = np.bincount(key, weights=r), np.bincount(key)
        return float((s[n > 0] ** 2 / n[n > 0]).sum())

    obs = stat(sc)
    idx_by_cell = [np.flatnonzero(cc == c) for c in range(cc.max() + 1)]
    ge = 0
    for _ in range(nperm):
        lab = sc.copy()
        for ix in idx_by_cell:
            lab[ix] = sc[rng.permutation(ix)]
        ge += stat(lab) >= obs
    return obs / float((r ** 2).sum()), (ge + 1) / (nperm + 1)


d["ft"] = d.tariff_plan_code_from + "|" + d.tariff_plan_code_to
for cellcol, segs in [("cell", ["dseg", "cseg"]), ("ft", ["seg", "dseg", "cseg"])]:
    sub = d[d.groupby(cellcol).y.transform("size") >= 20].copy()
    sub["r"] = sub.y - sub.groupby(cellcol).y.transform("mean")
    print(f"{cellcol}: cells={sub[cellcol].nunique()} rows={len(sub)}")
    for s in segs:
        eta, pv = perm_test(sub, cellcol, s)
        print(f"  {s}: eta2={eta:.4f} p={pv:.4f} means={show(sub, s, 'r')}")

rows = []
for cell, g in d.groupby("cell"):
    a, b = g.y[g.dseg == "HEAVY"], g.y[g.dseg == "LITE"]
    if len(a) >= 15 and len(b) >= 15:
        se = np.sqrt(a.var() / len(a) + b.var() / len(b))
        rows.append((cell, a.mean(), b.mean(), (a.mean() - b.mean()) / se))
z = pd.DataFrame(rows, columns=["cell", "heavy", "lite", "z"])
print(f"per-cell HEAVY vs LITE: cells={len(z)} |z|>1.96={int((z.z.abs() > 1.96).sum())} expected={0.05 * len(z):.1f}")
print(z.reindex(z.z.abs().sort_values(ascending=False).index).head(3).round(4).to_string(index=False))
