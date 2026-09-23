"""e1v: independent re-derivation of the TRUE mock effect table, segment economics and the LP bound.

Verifier for analysis e1 (mock upper bound). Recomputes the mock impact model from raw
data/change_tariff.csv (asserting equality with the public mock_environment function), then all
PART 1 numbers and the per-subscriber LP dual bound with its own minimiser.

Run:  python3 analysis/e1v_effects.py
"""
import math
import os
import sys

import numpy as np
import pandas as pd

P = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, P)

CH = ["push", "sms", "digital_ads", "call"]
COST = np.array([0.0, 4.0, 22.0, 160.0])
MULT = np.array([0.50, 0.65, 0.85, 1.20])
B, R = 100_000.0, 15_000.0


def load():
    ct = pd.read_csv(os.path.join(P, "data", "change_tariff.csv"))
    dt = pd.read_csv(os.path.join(P, "data", "dict_tariff.csv"))
    prof = pd.read_csv(os.path.join(P, "customer_profile.csv"))
    return ct, dt, prof


def impact(ct):
    d = ct[ct["AVG_ARPU_PREV_3M"] >= 100].copy()
    prev = d["AVG_ARPU_PREV_3M"]
    d["seg"] = np.where(prev <= 1000, "LOW", np.where(prev <= 5000, "MID", "HIGH"))  # pd.cut is right-inclusive
    d["pct"] = ((d["AVG_ARPU_NEXT_3M"] - prev) / prev).clip(-1, 3)
    g = d.groupby(["tariff_plan_code_from", "seg", "tariff_plan_code_to"]).agg(pct=("pct", "mean"), cnt=("pct", "size"))
    tot = g.groupby(level=[0, 1])["cnt"].transform("sum")
    g["conv"] = g["cnt"] / tot
    return g.reset_index().rename(columns={"tariff_plan_code_from": "cur", "tariff_plan_code_to": "tgt"})


def effect_table(prof, dt, im):
    price = dt.set_index("tariff_plan_code")["price_tariff"]
    med = max(float(price.median()), 1.0)
    fbc = float(im["conv"].median())
    cells = (prof.dropna(subset=["current_tariff", "arpu_segment"])
             .groupby(["current_tariff", "arpu_segment"])
             .agg(n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum")).reset_index())
    rows = []
    look = im.set_index(["cur", "seg", "tgt"])
    for c in cells.itertuples():
        for t in sorted(dt["tariff_plan_code"]):
            key = (c.current_tariff, c.arpu_segment, t)
            if key in look.index:
                pct, conv, src = float(look.at[key, "pct"]), float(look.at[key, "conv"]), "history"
            else:
                if c.current_tariff in price.index and t in price.index:
                    pct = float(np.clip(0.4 * (price[t] - price[c.current_tariff]) / med, -1, 3))
                else:
                    pct = 0.0
                conv, src = fbc, "fallback"
            rows.append(dict(cur=c.current_tariff, seg=c.arpu_segment, tgt=t, n=c.n, mass=c.mass,
                             pct=pct, conv=conv, src=src, same=(t == c.current_tariff)))
    e = pd.DataFrame(rows)
    e["base"] = e["pct"] * e["conv"]
    for c, m in zip(CH, MULT):
        e["r_" + c] = e["pct"] * np.minimum(1.0, e["conv"] * m)
    return e, fbc


def lp_bound(prof, e, R=R, B=B):
    """min over (lam, rho) >= 0 of lam*B + rho*R + sum_i max(0, max_c V_ic - lam*cost_c - rho).
    V_ic uses the best target for the subscriber's sign of predicted_arpu (max ratio if arpu>=0 else min)."""
    rc = ["r_" + c for c in CH]
    mx = e.groupby(["cur", "seg"])[rc].max()
    mn = e.groupby(["cur", "seg"])[rc].min()
    s = prof[["current_tariff", "arpu_segment", "predicted_arpu"]].copy()
    k = pd.MultiIndex.from_frame(s[["current_tariff", "arpu_segment"]])
    a = s["predicted_arpu"].values[:, None]
    rmax = mx.reindex(k).fillna(0.0).values
    rmin = mn.reindex(k).fillna(0.0).values
    V = np.where(a >= 0, rmax * a, rmin * a) - COST[None, :]

    def g(lam, rho):
        return lam * B + rho * R + np.maximum(0.0, (V - lam * COST[None, :] - rho).max(1)).sum()

    def golden(f, lo, hi, it=90):
        gr = (math.sqrt(5) - 1) / 2
        a_, b_ = hi - gr * (hi - lo), lo + gr * (hi - lo)
        fa, fb = f(a_), f(b_)
        for _ in range(it):
            if fa <= fb:
                hi, b_, fb = b_, a_, fa
                a_ = hi - gr * (hi - lo)
                fa = f(a_)
            else:
                lo, a_, fa = a_, b_, fb
                b_ = lo + gr * (hi - lo)
                fb = f(b_)
        x = (lo + hi) / 2
        return x, f(x)

    def over_lam(rho):
        return golden(lambda l: g(l, rho), 0.0, 500.0)

    rho, _ = golden(lambda r: over_lam(r)[1], 0.0, float(np.nanmax(V)) + 1)
    lam, val = over_lam(rho)
    # coarse grid sanity: no grid point may beat the minimiser by more than rounding
    grid = min(g(l, r) for l in np.linspace(0, 40, 41) for r in np.linspace(0, 2000, 81))
    return val, lam, rho, grid, V


def main():
    ct, dt, prof = load()
    im = impact(ct)
    from mock_environment import _mock_impact_model  # public module, only for the equality assert
    ref = _mock_impact_model(ct)
    ref = ref.assign(arpu_segment=ref["arpu_segment"].astype(str)).set_index(
        ["tariff_plan_code_from", "arpu_segment", "tariff_plan_code_to"]).sort_index()
    mine = im.set_index(["cur", "seg", "tgt"]).sort_index()
    assert len(ref) == len(mine) and np.allclose(ref["arpu_change_pct"].values, mine["pct"].values) \
        and np.allclose(ref["conversion_rate"].values, mine["conv"].values)
    print(f"impact model rows {len(mine)} == public mock ({len(ref)}); pct/conv identical")

    print("\n--- raw data sanity ---")
    print(f"change_tariff rows {len(ct)}; from==to rows {int((ct.tariff_plan_code_from == ct.tariff_plan_code_to).sum())}; "
          f"rows with PREV<100 dropped by mock {int((ct.AVG_ARPU_PREV_3M < 100).sum())}; "
          f"PREV exactly 1000 or 5000: {int(ct.AVG_ARPU_PREV_3M.isin([1000, 5000]).sum())}")
    print(f"profile rows {len(prof)}; predicted_arpu<0: {int((prof.predicted_arpu < 0).sum())}; "
          f"predicted_arpu NaN: {int(prof.predicted_arpu.isna().sum())}; "
          f"current_tariff not in dict: {int((~prof.current_tariff.dropna().isin(dt.tariff_plan_code)).sum())}; "
          f"rows lacking tariff or arpu_segment: {int(prof[['current_tariff', 'arpu_segment']].isna().any(axis=1).sum())}")
    print(f"dict tariffs {dt.tariff_plan_code.nunique()}; median price {dt.price_tariff.median():.1f}")

    e, fbc = effect_table(prof, dt, im)
    same = e[e["same"]]
    print(f"fallback conversion (median mock conv) {fbc:.4f}; target==current combos {len(same)}, "
          f"history-backed {int((same.src == 'history').sum())}, nonzero base {int((same.base != 0).sum())}")
    e = e[~e["same"]].reset_index(drop=True)
    cells = e.drop_duplicates(["cur", "seg"])
    print(f"cells {len(cells)} subscribers {int(cells.n.sum())}; largest cell n {int(cells.n.max())} "
          f"({cells.loc[cells.n.idxmax(), 'cur']}/{cells.loc[cells.n.idxmax(), 'seg']}); cells n>5000: {int((cells.n > 5000).sum())}; "
          f"cells n<20: {int((cells.n < 20).sum())} with {int(cells.loc[cells.n < 20, 'n'].sum())} subscribers")

    print("\n--- e1-01 ---")
    pos = e["base"] > 0
    print(f"combos {len(e)}; positive {int(pos.sum())} ({pos.mean():.1%})")
    for s in ["history", "fallback"]:
        x = e[e.src == s]
        print(f"  {s}: {len(x)} combos, positive {int((x.base > 0).sum())}, zero {int((x.base == 0).sum())}, negative {int((x.base < 0).sum())}")
    q = e.loc[pos, "base"].quantile([0.5, 0.95])
    print(f"positive base median {q[0.5]:.4f}  p95 {q[0.95]:.4f}")
    for c, m in zip(CH, MULT):
        print(f"  capped conv*mult>1 at {c}: {int((e.conv * m > 1).sum())}")
    print(f"max history conversion_rate {e.loc[e.src == 'history', 'conv'].max():.4f} (call binds only above {1 / 1.2:.4f}); "
          f"in the full impact model (incl. from-segments absent from profile cells): max conv {im.conv.max():.4f}, "
          f"rows with conv>1/1.2: {int((im.conv > 1 / 1.2).sum())}")
    same_best = (e.groupby(["cur", "seg"])[[f"r_{c}" for c in CH]].idxmax().nunique(axis=1) == 1).all()
    print(f"best target identical across channels in every cell: {same_best}")

    print("\n--- e1-02 ---")
    avg = (e["mass"] / e["n"]).values
    vpc = np.stack([e["r_" + c].values * avg - k for c, k in zip(CH, COST)], 1)
    e["best_vpc"] = vpc.max(1)
    e["best_val"] = e["best_vpc"] * e["n"]
    e["best_ch"] = [CH[i] for i in vpc.argmax(1)]
    cb = e.sort_values("best_val", ascending=False).groupby(["cur", "seg"]).head(1)
    seg = cb.groupby("seg").apply(lambda d: pd.Series(dict(
        cells=len(d), subs=int(d.n.sum()), mass=d.mass.sum(), med_best_base=d.base.median(),
        vpc=(d.best_vpc * d.n).sum() / d.n.sum(), max_abs_best_base=d.base.abs().max())), include_groups=False)
    seg["mass_share"] = seg["mass"] / seg["mass"].sum()
    print(seg.round(4).to_string())
    print(f"LOW vpc / HIGH vpc = {seg.loc['LOW', 'vpc'] / seg.loc['HIGH', 'vpc']:.1f}x; MID / HIGH = {seg.loc['MID', 'vpc'] / seg.loc['HIGH', 'vpc']:.1f}x")
    cbp = cb[cb.best_val > 0]
    print(f"cells with positive best: {len(cbp)}; top-10 cells share {cbp.best_val.head(10).sum() / cbp.best_val.sum():.1%}")
    pv = e[e.best_val > 0].sort_values("best_val", ascending=False)
    print(f"positive combos at best channel {len(pv)}; top-10 combos share {pv.best_val.head(10).sum() / pv.best_val.sum():.1%}")
    hi = e[e.seg == "HIGH"]
    print(f"HIGH: max |base| over ALL targets {hi.base.abs().max():.4f}; max base {hi.base.max():.4f}; "
          f"HIGH cells whose best channel (unconstrained) is push: {int((cb[cb.seg == 'HIGH'].best_ch == 'push').sum())} of 21; "
          f"best channel counts HIGH {cb[cb.seg == 'HIGH'].best_ch.value_counts().to_dict()}")
    print(f"value per contact at SMS for the best HIGH combo per cell, subscriber-weighted: "
          f"{((cb[cb.seg == 'HIGH'].r_sms * cb[cb.seg == 'HIGH'].mass - 4 * cb[cb.seg == 'HIGH'].n).sum() / cb[cb.seg == 'HIGH'].n.sum()):.1f}")
    small = cb[cb.n < 20]
    print(f"cells with n<20 (invisible to agent MIN_CELL): {len(small)}, positive best value {small.loc[small.best_val > 0, 'best_val'].sum():,.0f} "
          f"of {cbp.best_val.sum():,.0f}; by seg {small.seg.value_counts().to_dict()}")

    print("\n--- e1-04 LP bound ---")
    val, lam, rho, grid, V = lp_bound(prof, e)
    print(f"LP dual bound {val:,.0f} at lam={lam:.4f} rho={rho:.2f}; best coarse-grid value {grid:,.0f}")
    print(f"subscribers with positive best-channel value (unconstrained): {int((V.max(1) > 0).sum())}")


if __name__ == "__main__":
    main()
