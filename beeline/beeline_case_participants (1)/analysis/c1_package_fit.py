"""c1 parts 4 + 6: package fit vs relative ARPU change / destination choice; within-cell effect of data/call segment.

Usage window = Jul-Sep 2026 (same window as AVG_ARPU_PREV_3M, see c1_coverage.py).
Data usage = DATA_VOLUME (reproduces profile data_segment 100%, see c1_shift.py).
Call segment minutes = ONNET+OFFNET (reproduces profile call_segment 100% where usage present).
Minute package fit uses OFFNET minutes (package = minutes to other operators; tariff_12 counts OFFNET+LAND).
Relative change = clip((NEXT-PREV)/PREV, -1, 3), rows with PREV>=100 (same as mock_environment / agent).
"""
import os
import numpy as np
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
pd.set_option("display.width", 200)
rng = np.random.default_rng(0)

ct = pd.read_csv(os.path.join(P, "data", "change_tariff.csv"))
tr = pd.read_csv(os.path.join(P, "data", "traffic.csv"))
dt = pd.read_csv(os.path.join(P, "data", "dict_tariff.csv")).set_index("tariff_plan_code")
pr = pd.read_csv(os.path.join(P, "customer_profile.csv"))

win = ["2026-07-01", "2026-08-01", "2026-09-01"]
cols = ["DATA_VOLUME", "OUT_LOC_ONNET_MIN", "OUT_LOC_OFFNET_MIN", "OUT_LOC_LAND_MIN", "OUT_LOC_OFFNET_PAID_MIN"]
use = tr[tr.time_key.isin(win)].groupby("ID_NUMBER")[cols].mean()
h = ct.join(use, on="ID_NUMBER", how="inner")
h = h[h.AVG_ARPU_PREV_3M >= 100].copy()
h["y"] = ((h.AVG_ARPU_NEXT_3M - h.AVG_ARPU_PREV_3M) / h.AVG_ARPU_PREV_3M).clip(-1, 3)
h["arpu_segment"] = np.select([h.AVG_ARPU_PREV_3M < 1000, h.AVG_ARPU_PREV_3M <= 5000], ["LOW", "MID"], "HIGH")
h["data_segment"] = np.select([h.DATA_VOLUME <= 0, h.DATA_VOLUME <= 2000], ["NON_USER", "LITE"], "HEAVY")
cm = h.OUT_LOC_ONNET_MIN + h.OUT_LOC_OFFNET_MIN
h["call_segment"] = np.select([cm < 100, cm <= 400], ["LOW", "MEDIUM"], "HIGH")
print("analysis rows (PREV>=100 with Jul-Sep traffic):", len(h))


def min_pkg(code):
    return dt.loc[code, "Min_another_operator_in_PKG"] + dt.loc[code, "Min_another_operator_and_city_in_PKG"]


def min_use(df, code_col):
    land = np.where(df[code_col].map(dt.Min_another_operator_and_city_in_PKG) > 0, df.OUT_LOC_LAND_MIN, 0)
    return df.OUT_LOC_OFFNET_MIN + land


h["dpkg_from"] = h.tariff_plan_code_from.map(dt.Data_in_PKG)
h["dpkg_to"] = h.tariff_plan_code_to.map(dt.Data_in_PKG)
h["mpkg_from"] = h.tariff_plan_code_from.map(min_pkg)
h["mpkg_to"] = h.tariff_plan_code_to.map(min_pkg)
h["muse_from"] = min_use(h, "tariff_plan_code_from")
h["muse_to"] = min_use(h, "tariff_plan_code_to")
h["price_up"] = h.tariff_plan_code_to.map(dt.price_tariff) > h.tariff_plan_code_from.map(dt.price_tariff)

# residual vs (from, arpu_segment, to) cell mean = what the scorer's key cannot see
h["cell"] = h.tariff_plan_code_from + "|" + h.arpu_segment + "|" + h.tariff_plan_code_to
h["cell_n"] = h.groupby("cell")["y"].transform("size")
h["resid"] = h.y - h.groupby("cell")["y"].transform("mean")


def fit_bucket(u, pkg):
    r = u / pkg.where(pkg > 0)
    return pd.Series(np.select([pkg <= 0, u <= 0, r <= 0.5, r <= 1.0], ["NO_PKG", "ZERO_USE", "<=50%", "50-100%"], "EXCEEDS"),
                     index=u.index)


def table(df, by, val="y", order=None):
    g = df.groupby(by)[val].agg(["size", "mean", "std"])
    g["ci95"] = 1.96 * g["std"] / np.sqrt(g["size"])
    if order:
        g = g.reindex([o for o in order if o in g.index])
    return g.drop(columns="std").round(4)


ORDER = ["NO_PKG", "ZERO_USE", "<=50%", "50-100%", "EXCEEDS"]
print("\nPaid-minute sanity: share with OFFNET_PAID_MIN>0 by offnet-vs-current-package bucket")
h["mfit_cur"] = fit_bucket(h.muse_from, h.mpkg_from)
print((h.assign(paid=h.OUT_LOC_OFFNET_PAID_MIN > 0).groupby("mfit_cur")["paid"].agg(["size", "mean"])).reindex(ORDER).round(4).to_string())

print("\n=== 4a. DATA: usage vs CURRENT package ===")
h["dfit_cur"] = fit_bucket(h.DATA_VOLUME, h.dpkg_from)
print("raw rel change:\n", table(h, "dfit_cur", order=ORDER).to_string())
hc = h[h.cell_n >= 20]
print(f"within-cell residual (cells n>=20, rows={len(hc)}):\n", table(h[h.cell_n >= 20], "dfit_cur", "resid", ORDER).to_string())
print("\n=== 4b. DATA: does DESTINATION package fit usage? ===")
h["dfit_to"] = np.where(h.DATA_VOLUME <= h.dpkg_to, "FITS", "EXCEEDS_DEST")
print("raw:\n", table(h, "dfit_to").to_string())
print("within-cell residual: (fit status is nearly constant within a cell only if usage is similar; residual compares subscribers of the same cell)")
print(table(h[h.cell_n >= 20], "dfit_to", "resid").to_string())
print("\nCHART data-fit rows (bucket,n,mean,lo,hi):")
t = table(h, "dfit_cur", order=ORDER)
for b, r in t.iterrows():
    print(f"  current:{b},{int(r['size'])},{r['mean']:.4f},{r['mean'] - r['ci95']:.4f},{r['mean'] + r['ci95']:.4f}")
t = table(h, "dfit_to")
for b, r in t.iterrows():
    print(f"  dest:{b},{int(r['size'])},{r['mean']:.4f},{r['mean'] - r['ci95']:.4f},{r['mean'] + r['ci95']:.4f}")

print("\n=== 4c. DATA: is destination CHOICE associated with fit? ===")
# null: destination drawn from the empirical destination mix of the same from-tariff (all movers, PREV>=100)
mix = h.groupby(["tariff_plan_code_from", "tariff_plan_code_to"]).size()
mix = (mix / mix.groupby(level=0).transform("sum")).rename("p").reset_index()
mix["dpkg_to"] = mix.tariff_plan_code_to.map(dt.Data_in_PKG)
mix["mpkg_to"] = mix.tariff_plan_code_to.map(min_pkg)


def expected_fit(df, usecol, pkgcol):
    out = np.zeros(len(df))
    for fr, idx in df.groupby("tariff_plan_code_from").indices.items():
        mm = mix[mix.tariff_plan_code_from == fr]
        u = df[usecol].to_numpy()[idx][:, None]
        out[idx] = ((u <= mm[pkgcol].to_numpy()[None, :]) * mm.p.to_numpy()[None, :]).sum(axis=1)
    return out


h["exp_dfit"] = expected_fit(h, "DATA_VOLUME", "dpkg_to")
h["act_dfit"] = (h.DATA_VOLUME <= h.dpkg_to).astype(float)
h["bigger_dpkg"] = (h.dpkg_to > h.dpkg_from).astype(float)
g = h.groupby("dfit_cur").agg(n=("y", "size"), actual_dest_fits=("act_dfit", "mean"),
                               expected_if_random_dest=("exp_dfit", "mean"), share_to_bigger_pkg=("bigger_dpkg", "mean"),
                               share_price_up=("price_up", "mean")).reindex(ORDER)
g["lift_pp"] = (g.actual_dest_fits - g.expected_if_random_dest) * 100
print(g.round(4).to_string())
ex = h[h.dfit_cur == "EXCEEDS"]
d = ex.act_dfit - ex.exp_dfit
print(f"EXCEEDS: actual-expected fit = {d.mean() * 100:.2f} pp, 95% CI +-{1.96 * d.std() / np.sqrt(len(d)) * 100:.2f} pp, n={len(d)}")

print("\n=== 4d. MINUTES (offnet) vs current / destination package ===")
print("raw rel change by current-minute fit:\n", table(h, "mfit_cur", order=ORDER).to_string())
print("within-cell residual:\n", table(h[h.cell_n >= 20], "mfit_cur", "resid", ORDER).to_string())
h["mfit_to"] = np.where(h.muse_to <= h.mpkg_to, "FITS", "EXCEEDS_DEST")
print("raw by destination-minute fit:\n", table(h, "mfit_to").to_string())
h["exp_mfit"] = expected_fit(h.assign(mu=h.OUT_LOC_OFFNET_MIN), "mu", "mpkg_to")
h["act_mfit"] = (h.OUT_LOC_OFFNET_MIN <= h.mpkg_to).astype(float)
g = h.groupby("mfit_cur").agg(n=("y", "size"), actual_dest_fits=("act_mfit", "mean"),
                               expected_if_random_dest=("exp_mfit", "mean")).reindex(ORDER)
g["lift_pp"] = (g.actual_dest_fits - g.expected_if_random_dest) * 100
print("destination-choice (offnet only, ignores tariff_12 land add-on):\n", g.round(4).to_string())

print("\n=== 4e. Target profile: how many exceed their CURRENT package? ===")
p = pr[pr.DATA_VOLUME.notna() & pr.current_tariff.notna()].copy()
p["dfit_cur"] = fit_bucket(p.DATA_VOLUME, p.current_tariff.map(dt.Data_in_PKG))
p["mfit_cur"] = fit_bucket(min_use(p, "current_tariff"), p.current_tariff.map(min_pkg))
print("target data-fit shares:", p.dfit_cur.value_counts(normalize=True).reindex(ORDER).round(4).to_dict())
print("history data-fit shares:", h.dfit_cur.value_counts(normalize=True).reindex(ORDER).round(4).to_dict())
print("target minute-fit shares:", p.mfit_cur.value_counts(normalize=True).reindex(ORDER).round(4).to_dict())
print("history minute-fit shares:", h.mfit_cur.value_counts(normalize=True).reindex(ORDER).round(4).to_dict())

print("\n=== 6. Within-cell differences by data/call segment ===")
print("Public scorer keys effect and conversion by (current_tariff, arpu_segment, target) only (scoring_core.score_campaign).")


def within_test(df, cellcol, segcol, n_perm=1000):
    """Between-segment sum of squares of residuals within cells; permutation p (labels shuffled within cell)."""
    df = df.reset_index(drop=True)
    cc = pd.factorize(df[cellcol])[0]
    sc = pd.factorize(df[segcol])[0]
    ns = sc.max() + 1
    r = (df.y - df.groupby(cellcol)["y"].transform("mean")).to_numpy()

    def ss(lbl):
        key = cc * ns + lbl
        s = np.bincount(key, r)
        n = np.bincount(key)
        return float((s[n > 0] ** 2 / n[n > 0]).sum())

    obs = ss(sc)
    order = np.lexsort((rng.random(len(df)), cc))  # rows sorted by cell
    perm_ge = 0
    for _ in range(n_perm):
        o2 = np.lexsort((rng.random(len(df)), cc))
        lbl = np.empty_like(sc)
        lbl[order] = sc[o2]
        perm_ge += ss(lbl) >= obs
    eta2 = obs / float((r ** 2).sum())
    return obs, eta2, (perm_ge + 1) / (n_perm + 1)


for cellcol, label in [("cell", "(from, arpu_seg, to)"), ("ft", "(from, to)")]:
    h["ft"] = h.tariff_plan_code_from + "|" + h.tariff_plan_code_to
    sub = h[h.groupby(cellcol)["y"].transform("size") >= 20].copy()
    sub["r"] = sub.y - sub.groupby(cellcol)["y"].transform("mean")
    print(f"\ncells {label} with n>=20: {sub[cellcol].nunique()} cells, {len(sub)} rows")
    for seg in ["data_segment", "call_segment", "arpu_segment"]:
        if cellcol == "cell" and seg == "arpu_segment":
            continue
        obs, eta2, pval = within_test(sub, cellcol, seg)
        print(f"  {seg}: within-cell share of residual variance explained={eta2:.4f}  permutation p={pval:.4f}")
        print("   ", table(sub, seg, "r").to_dict("index"))

# largest per-cell HEAVY vs LITE gaps among the big cells (data) - decision relevance
print("\nPer-cell HEAVY minus LITE / NON_USER mean y, (from,seg,to) cells with >=15 rows in both groups:")
rows = []
for cell, g in h.groupby("cell"):
    a, b, c = g.y[g.data_segment == "HEAVY"], g.y[g.data_segment == "LITE"], g.y[g.data_segment == "NON_USER"]
    if len(a) >= 15 and len(b) >= 15:
        se = np.sqrt(a.var() / len(a) + b.var() / len(b))
        rows.append([cell, len(a), len(b), round(a.mean(), 4), round(b.mean(), 4), round(a.mean() - b.mean(), 4), round(se, 4)])
cells = pd.DataFrame(rows, columns=["cell", "n_heavy", "n_lite", "y_heavy", "y_lite", "diff", "se"])
cells["z"] = (cells["diff"] / cells.se).round(2)
print(cells.sort_values("z", key=np.abs, ascending=False).head(10).to_string(index=False))
print(f"cells compared={len(cells)}, |z|>1.96: {int((cells.z.abs() > 1.96).sum())} (expected by chance ~{0.05 * len(cells):.1f})")
