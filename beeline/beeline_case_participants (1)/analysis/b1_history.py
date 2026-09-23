"""b1: tariff-change history (data/change_tariff.csv) -- quality, structure, outcomes, conversion x change.

Run: python3 analysis/b1_history.py   (deterministic, no randomness)
"""
import math
import os

import numpy as np
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BINS, LABELS = [-np.inf, 1000, 5000, np.inf], ["LOW", "MID", "HIGH"]
F, T = "tariff_plan_code_from", "tariff_plan_code_to"
PREV, NEXT = "AVG_ARPU_PREV_3M", "AVG_ARPU_NEXT_3M"
AGENT_K, N_TARIFFS = 15, 21
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_rows", 200)
pd.set_option("display.float_format", lambda x: f"{x:.4f}")


def load():
    ct = pd.read_csv(os.path.join(P, "data", "change_tariff.csv"))
    price = pd.read_csv(os.path.join(P, "data", "dict_tariff.csv")).set_index("tariff_plan_code")["price_tariff"]
    ct["seg"] = pd.cut(ct[PREV], BINS, labels=LABELS).astype(str)
    with np.errstate(divide="ignore", invalid="ignore"):
        ct["rel_raw"] = (ct[NEXT] - ct[PREV]) / ct[PREV]
    ct["rel"] = ct["rel_raw"].clip(-1, 3)
    ct["absd"] = ct[NEXT] - ct[PREV]
    ct["dprice"] = price.reindex(ct[T]).values - price.reindex(ct[F]).values
    return ct, price


def kept(ct):
    """The agent's / mock's filter: PREV >= 100."""
    return ct[ct[PREV] >= 100].copy()


def shrink(d, K, K12=None):
    """Agent-style hierarchical shrinkage: destination -> (from,to) -> (from,seg,to). Same K at all levels
    unless K12 is given (then K12 for the two upper levels, K for the cell level)."""
    K12 = K if K12 is None else K12
    g0 = d["rel"].mean()
    g1 = d.groupby(T)["rel"].agg(["sum", "size"])
    m1 = (g1["sum"] + K12 * g0) / (g1["size"] + K12)
    g2 = d.groupby([F, T])["rel"].agg(["sum", "size"])
    m2 = (g2["sum"] + K12 * m1.reindex(g2.index.get_level_values(1)).values) / (g2["size"] + K12)
    g3 = d.groupby([F, "seg", T])["rel"].agg(["sum", "size"])
    par = m2.reindex(pd.MultiIndex.from_arrays([g3.index.get_level_values(0), g3.index.get_level_values(2)])).values
    m3 = (g3["sum"] + K * par) / (g3["size"] + K)
    return g0, m1, m2, m3


def tmean(s, p=0.10):
    v = np.sort(s.dropna().values)
    k = int(len(v) * p)
    return float(v[k:len(v) - k].mean())


def wilson(k, n, z=1.96):
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return c - h, c + h


def outcome_table(d, key):
    d = d.assign(down=(d[NEXT] < d[PREV]).astype(float), flat=(d["rel_raw"].abs() < 0.05).astype(float))
    g = d.groupby(key)
    out = g.agg(n=("rel", "size"), mean=("rel", "mean"), sd=("rel", "std"), median=("rel_raw", "median"),
                tmean10=("rel_raw", tmean), down=("down", "mean"), flat=("flat", "mean"),
                abs_median=("absd", "median"), abs_mean=("absd", "mean"))
    out["ci_lo"] = out["mean"] - 1.96 * out["sd"] / np.sqrt(out["n"])
    out["ci_hi"] = out["mean"] + 1.96 * out["sd"] / np.sqrt(out["n"])
    out["ratio_of_means"] = g[NEXT].sum() / g[PREV].sum() - 1
    return out


def section(t):
    print("\n" + "=" * 100 + f"\n{t}\n" + "=" * 100)


def main():
    ct, price = load()
    k = kept(ct)
    prof = pd.read_csv(os.path.join(P, "customer_profile.csv"))

    # ---------------------------------------------------------------- 1. data quality
    section("1. DATA QUALITY")
    print("rows", len(ct), "| unique ID", ct["ID_NUMBER"].nunique(), "| TIME_KEY values", ct["TIME_KEY"].unique().tolist())
    print("NaN per column:", ct[[PREV, NEXT, F, T]].isna().sum().to_dict())
    print("rows with from == to:", int((ct[F] == ct[T]).sum()))
    q = [0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1]
    print("\nPREV / NEXT quantiles:")
    print(pd.DataFrame({"PREV": ct[PREV].quantile(q), "NEXT": ct[NEXT].quantile(q)}).T.round(2))
    print("mean PREV %.2f  mean NEXT %.2f" % (ct[PREV].mean(), ct[NEXT].mean()))
    for c in (PREV, NEXT):
        print(f"{c}: negative {int((ct[c] < 0).sum())}, zero {int((ct[c] == 0).sum())}, "
              f"0<x<100 {int(((ct[c] > 0) & (ct[c] < 100)).sum())}")
    low = ct[ct[PREV] < 100]
    print(f"\nrows dropped by PREV>=100 filter: {len(low)} ({len(low) / len(ct):.4%})")
    lp = low[low[PREV] > 0]
    print(f"  of which PREV>0: {len(lp)}; their unclipped rel change quantiles (5/25/50/75/95 %):",
          lp["rel_raw"].quantile([0.05, 0.25, 0.5, 0.75, 0.95]).round(2).tolist())
    print(f"  their rel change > 3 (would be clipped): {int((lp['rel_raw'] > 3).sum())} "
          f"({(lp['rel_raw'] > 3).mean():.4%}); > 10: {int((lp['rel_raw'] > 10).sum())}; max {lp['rel_raw'].max():.1f}")
    print(f"  dropped rows' destination mix (top 5):", low[T].value_counts().head(5).to_dict())
    print(f"\nkept rows: {len(k)}")
    print(f"  clip at -1 touches {int((k['rel_raw'] < -1).sum())} rows ({(k['rel_raw'] < -1).mean():.4%}); "
          f"clip at 3 touches {int((k['rel_raw'] > 3).sum())} rows ({(k['rel_raw'] > 3).mean():.4%})")
    print(f"  rel_raw quantiles (1/5/50/95/99 %):", k["rel_raw"].quantile([0.01, 0.05, 0.5, 0.95, 0.99]).round(3).tolist())
    print(f"  mean rel unclipped {k['rel_raw'].mean():.4f} vs clipped {k['rel'].mean():.4f}")
    print(f"  kept rows with NEXT == 0 (rel = -1, full loss): {int((k[NEXT] == 0).sum())} ({(k[NEXT] == 0).mean():.4%}); by seg:",
          k.groupby("seg")[NEXT].apply(lambda s: round(float((s == 0).mean()), 4)).to_dict())
    print("  share clipped at +3 by seg:", k.groupby("seg")["rel_raw"].apply(lambda s: round(float((s > 3).mean()), 4)).to_dict())
    print(f"  duplicated ID rows = {int(ct['ID_NUMBER'].duplicated(keep=False).sum())}")
    print("  kept rows by seg (PREV thresholds 1000/5000):", k["seg"].value_counts().to_dict())
    print("  median PREV / price_from (price_from>0): %.4f ; median NEXT / price_to: %.4f" % (
        (k[PREV] / price.reindex(k[F]).values)[price.reindex(k[F]).values > 0].median(),
        (k[NEXT] / price.reindex(k[T]).values)[price.reindex(k[T]).values > 0].median()))

    # ---------------------------------------------------------------- 2. transition structure
    section("2. TRANSITION STRUCTURE (all rows unless noted)")
    print("distinct from", ct[F].nunique(), "| distinct to", ct[T].nunique(), "| distinct pairs", ct.groupby([F, T]).ngroups)
    all_t = set(price.index)
    print("dict tariffs never a destination:", sorted(all_t - set(ct[T])), "| never an origin:", sorted(all_t - set(ct[F])))
    print("\ndestination counts (all rows):")
    print(ct[T].value_counts().to_string())
    print("\norigin counts (all rows):")
    print(ct[F].value_counts().to_string())
    top_f, top_t = ct[F].value_counts().index[:10], ct[T].value_counts().index[:10]
    print("\nfrom x to counts, top-10 origins x top-10 destinations:")
    print(pd.crosstab(ct[F], ct[T]).loc[top_f, top_t].to_string())
    pc = ct.groupby([F, T]).size()
    print("\npair-count distribution: quantiles (10/25/50/75/90/max):",
          pc.quantile([0.1, 0.25, 0.5, 0.75, 0.9, 1]).tolist())
    print(f"  pairs n<5: {int((pc < 5).sum())}, n<10: {int((pc < 10).sum())}, n<30: {int((pc < 30).sum())}, "
          f"n>=100: {int((pc >= 100).sum())} of {len(pc)}; possible off-diagonal pairs {21 * 20}")
    print(f"  top-10 pairs hold {pc.nlargest(10).sum() / pc.sum():.4%} of rows")
    c3 = k.groupby([F, "seg", T]).size()
    print(f"\n(from, seg, to) cells on kept rows: {len(c3)}; quantiles (25/50/75/90):",
          c3.quantile([0.25, 0.5, 0.75, 0.9]).tolist())
    for lim in (5, 15, 30):
        print(f"  cells n<{lim}: {int((c3 < lim).sum())} ({(c3 < lim).mean():.4%}); rows in cells n>={lim}: "
              f"{c3[c3 >= lim].sum() / c3.sum():.4%}")
    print(f"  (from,seg) groups with movers: {k.groupby([F, 'seg']).ngroups}")

    # target-audience coverage
    seg_chk = pd.cut(prof["ARPU_3m_avg"], BINS, labels=LABELS).astype(str)
    ok = prof["arpu_segment"].notna()
    print(f"\nprofile arpu_segment vs cut(ARPU_3m_avg,1000/5000): mismatches {int((seg_chk[ok] != prof.loc[ok, 'arpu_segment']).sum())} of {int(ok.sum())}")
    pr = prof.dropna(subset=["current_tariff", "arpu_segment"])
    cells = pr.groupby(["current_tariff", "arpu_segment"]).agg(n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum"))
    movers = k.groupby([F, "seg"]).size()
    ndest = k.groupby([F, "seg"])[T].nunique()
    ndest10 = c3[c3 >= 10].groupby(level=[0, 1]).size()
    cells["movers"] = movers.reindex(cells.index).fillna(0).astype(int).values
    cells["dest_seen"] = ndest.reindex(cells.index).fillna(0).astype(int).values
    cells["dest_n10"] = ndest10.reindex(cells.index).fillna(0).astype(int).values
    tot_n, tot_m = cells["n"].sum(), cells["mass"].sum()
    print(f"profile cells (tariff x arpu_segment): {len(cells)}, subscribers {tot_n}, predicted_arpu mass {tot_m:,.0f}")
    for name, m in [("zero movers", cells["movers"] == 0), ("<10 movers", cells["movers"] < 10),
                    ("<30 movers", cells["movers"] < 30)]:
        print(f"  cells with {name}: {int(m.sum())} cells, {int(cells.loc[m, 'n'].sum())} subs "
              f"({cells.loc[m, 'n'].sum() / tot_n:.4%}), mass share {cells.loc[m, 'mass'].sum() / tot_m:.4%}")
    print("  zero/<10-mover cells:")
    print(cells[cells["movers"] < 10].sort_values("mass", ascending=False).to_string())
    cells["mass_share"] = cells["mass"] / tot_m
    print("\ntop-12 profile cells by mass with history coverage:")
    print(cells.sort_values("mass", ascending=False).head(12).to_string())
    big = cells[cells["n"] >= 20]
    rows = []
    for (tf, sg), r in big.iterrows():
        for tg in price.index:
            if tg != tf:
                rows.append((tf, sg, tg, r["mass"], int(c3.get((tf, sg, tg), 0))))
    ctg = pd.DataFrame(rows, columns=["tariff", "seg", "target", "mass", "n_hist"])
    ctg["band"] = pd.cut(ctg["n_hist"], [-1, 0, 4, 14, 29, np.inf], labels=["0", "1-4", "5-14", "15-29", ">=30"])
    cov = ctg.groupby("band", observed=False).agg(combos=("n_hist", "size"), mass=("mass", "sum"))
    cov["combo_share"] = cov["combos"] / cov["combos"].sum()
    cov["mass_weighted_share"] = cov["mass"] / cov["mass"].sum()
    print(f"\n(cell>=20 subs) x (20 targets) combos by historical movers n (mass-weighted = cell mass):")
    print(cov.drop(columns="mass").to_string())

    # ---------------------------------------------------------------- 3. outcomes
    section("3. OUTCOMES (kept rows, rel = clipped relative change unless 'raw')")
    r = k["rel_raw"]
    print(f"overall n {len(k)}: mean clipped {k['rel'].mean():.4f}, mean raw {r.mean():.4f}, median {r.median():.4f}, "
          f"10%-trimmed mean {tmean(r):.4f}, ratio of means {k[NEXT].sum() / k[PREV].sum() - 1:.4f}")
    print(f"  downsell share (NEXT<PREV) {(k[NEXT] < k[PREV]).mean():.4f}; no-change share (|rel|<5%) "
          f"{(r.abs() < 0.05).mean():.4f}; upsell >+5% {(r > 0.05).mean():.4f}")
    print(f"  absolute change: median {k['absd'].median():.2f}, mean {k['absd'].mean():.2f}")
    print(f"  all rows (incl. PREV<100): downsell share {(ct[NEXT] < ct[PREV]).mean():.4f}")
    ot = outcome_table(k, T).sort_values("n", ascending=False)
    print("\nby destination:")
    print(ot.to_string())
    print("\nby origin:")
    print(outcome_table(k, F).sort_values("n", ascending=False).to_string())
    print("\nby arpu segment (from PREV):")
    print(outcome_table(k, "seg").to_string())

    print("\nprice difference price_to - price_from:")
    k["dbucket"] = pd.cut(k["dprice"], [-np.inf, -2000, -500, 500, 2000, np.inf],
                          labels=["<-2000", "-2000..-500", "-500..500", "500..2000", ">2000"])
    print(outcome_table(k, "dbucket")[["n", "mean", "ci_lo", "ci_hi", "median", "down", "abs_median", "abs_mean", "ratio_of_means"]].to_string())
    rk = lambda s: s.rank()
    print(f"  Pearson corr(dprice, rel clipped) {k['dprice'].corr(k['rel']):.4f}; Spearman {rk(k['dprice']).corr(rk(k['rel_raw'])):.4f}")
    print(f"  Pearson corr(dprice, abs change) {k['dprice'].corr(k['absd']):.4f}; Spearman {rk(k['dprice']).corr(rk(k['absd'])):.4f}")
    b = np.cov(k["dprice"], k["absd"])[0, 1] / k["dprice"].var()
    print(f"  OLS slope abs change on dprice: {b:.4f} (1.0 = price change passes through fully)")
    for sg in LABELS:
        s = k[k["seg"] == sg]
        print(f"  seg {sg}: Spearman(dprice, rel) {rk(s['dprice']).corr(rk(s['rel_raw'])):.4f}, "
              f"Pearson(dprice, abs) {s['dprice'].corr(s['absd']):.4f}, n {len(s)}")

    print("\nregression to the mean:")
    k["prev_dec"] = pd.qcut(k[PREV], 10, labels=False)
    dec = k.groupby("prev_dec").agg(prev_lo=(PREV, "min"), prev_hi=(PREV, "max"), mean_rel=("rel", "mean"),
                                    median_rel=("rel_raw", "median"), down=("absd", lambda x: (x < 0).mean()))
    print("  by PREV decile (all kept rows):")
    print(dec.to_string())
    kk = k.copy()
    kk["lp"] = np.log(kk[PREV])
    grp = kk.groupby([F, T])
    kk["n_pair"] = grp["lp"].transform("size")
    kk = kk[kk["n_pair"] >= 20]
    kk["lp_c"] = kk["lp"] - kk.groupby([F, T])["lp"].transform("mean")
    kk["rel_c"] = kk["rel"] - kk.groupby([F, T])["rel"].transform("mean")
    kk["prev_c"] = kk[PREV] - kk.groupby([F, T])[PREV].transform("mean")
    kk["next_c"] = kk[NEXT] - kk.groupby([F, T])[NEXT].transform("mean")
    print(f"  within (from,to) pairs n>=20 ({kk.groupby([F, T]).ngroups} pairs, {len(kk)} rows): "
          f"corr(log PREV, rel clipped) {kk['lp_c'].corr(kk['rel_c']):.4f}; "
          f"OLS slope NEXT on PREV {np.cov(kk['prev_c'], kk['next_c'])[0, 1] / kk['prev_c'].var():.4f} (1 = no reversion)")
    k["cell_med"] = k.groupby([F, "seg", T])[PREV].transform("median")
    k["cell_n"] = k.groupby([F, "seg", T])[PREV].transform("size")
    c10 = k[k["cell_n"] >= 10]
    lo_half = c10[c10[PREV] <= c10["cell_med"]]
    hi_half = c10[c10[PREV] > c10["cell_med"]]
    print(f"  within (from,seg,to) cells n>=10 ({c10.groupby([F, 'seg', T]).ngroups} cells): mean rel below-median PREV "
          f"{lo_half['rel'].mean():.4f} (n {len(lo_half)}) vs above-median {hi_half['rel'].mean():.4f} (n {len(hi_half)})")
    print("  mean of ratios vs PREV-weighted mean (= ratio of means on clipped) by seg:")
    for sg in LABELS:
        s = k[k["seg"] == sg]
        print(f"    {sg}: mean clipped {s['rel'].mean():.4f}, PREV-weighted clipped {np.average(s['rel'], weights=s[PREV]):.4f}, "
              f"history median PREV {s[PREV].median():.2f}")
    print("  profile ARPU_3m_avg median by arpu_segment:", prof.groupby("arpu_segment")["ARPU_3m_avg"].median().round(2).to_dict())
    print("  profile predicted_arpu median by arpu_segment:", prof.groupby("arpu_segment")["predicted_arpu"].median().round(2).to_dict())
    lo_seg = k[k["seg"] == "LOW"]
    print(f"  LOW seg, PREV in [100,300): n {int((lo_seg[PREV] < 300).sum())}, mean rel {lo_seg.loc[lo_seg[PREV] < 300, 'rel'].mean():.4f}; "
          f"PREV in [300,1000]: n {int((lo_seg[PREV] >= 300).sum())}, mean rel {lo_seg.loc[lo_seg[PREV] >= 300, 'rel'].mean():.4f}")
    plow = prof.loc[prof["arpu_segment"] == "LOW", "ARPU_3m_avg"]
    print(f"  profile LOW subs {len(plow)}; share with ARPU_3m_avg < 100 (the band the PREV>=100 filter removes from history): "
          f"{(plow < 100).mean():.4f}; <= 0: {(plow <= 0).mean():.4f}")
    print(f"  profile LOW seg share with ARPU_3m_avg < 300: {(prof.loc[prof['arpu_segment'] == 'LOW', 'ARPU_3m_avg'] < 300).mean():.4f}; "
          f"history LOW (kept) share PREV < 300: {(lo_seg[PREV] < 300).mean():.4f}")

    # ---------------------------------------------------------------- 5. conversion share x change
    section("5. CONVERSION SHARE AND PRODUCT change x share (kept rows)")
    g0, m1, m2, m3 = shrink(k, AGENT_K)
    g3 = k.groupby([F, "seg", T])["rel"].agg(n="size", mean="mean", sd="std")
    N = k.groupby([F, "seg"]).size()
    g3["N"] = N.reindex(g3.index.droplevel(2)).values
    g3["share"] = g3["n"] / g3["N"]
    g3["conv_agent"] = (g3["n"] + 0.5) / (g3["N"] + 0.5 * N_TARIFFS)
    g3["m3_K15"] = m3.reindex(g3.index).values
    g3["prod_mock"] = g3["mean"] * g3["share"]
    g3["prod_agent"] = g3["m3_K15"] * g3["conv_agent"]
    se = g3["sd"] / np.sqrt(g3["n"])
    g3["chg_lcb"] = g3["mean"] - 1.96 * se
    s_lo, s_hi = wilson(g3["n"], g3["N"])
    g3["prod_lcb"] = np.where(g3["chg_lcb"] > 0, g3["chg_lcb"] * s_lo, g3["chg_lcb"] * s_hi)
    print("share distribution (cells n>=1): quantiles 50/75/90/max", g3["share"].quantile([0.5, 0.75, 0.9, 1]).round(4).tolist())
    print(f"max share per (from,seg): median {g3.groupby(level=[0, 1])['share'].max().median():.4f}")
    print(f"corr(share, mean change) over cells n>=10: {g3.loc[g3['n'] >= 10, 'share'].corr(g3.loc[g3['n'] >= 10, 'mean']):.4f}")
    g3 = g3.join(cells[["n", "mass"]].rename(columns={"n": "subs"}), on=[F, "seg"])
    aud = g3[g3["subs"] >= 20]
    print(f"triples whose (from,seg) is an audience cell >=20 subs: {len(aud)}; prod_mock>0: {int((aud['prod_mock'] > 0).sum())}; "
          f"prod_agent>0: {int((aud['prod_agent'] > 0).sum())}; prod_lcb>0 (n>=2): {int(((aud['prod_lcb'] > 0) & (aud['n'] >= 2)).sum())}")
    cols = ["n", "N", "share", "mean", "chg_lcb", "m3_K15", "prod_mock", "prod_agent", "prod_lcb", "subs", "mass"]
    print("\ntop-15 audience triples by prod_lcb (n>=10):")
    print(aud[aud["n"] >= 10].sort_values("prod_lcb", ascending=False).head(15)[cols].to_string())
    aud = aud.assign(prior_value=aud["prod_agent"] * aud["mass"])
    print("\ntop-15 audience triples by prod_agent x cell mass (agent prior value, base units):")
    print(aud.sort_values("prior_value", ascending=False).head(15)[cols + ["prior_value"]].to_string())
    print("\naudience cells: best target by prod_agent, and whether its change LCB > 0:")
    best = aud.sort_values("prod_agent", ascending=False).groupby(level=[0, 1]).head(1)
    print(f"  cells {len(best)}; best target chg_lcb>0: {int((best['chg_lcb'] > 0).sum())}; "
          f"best-target n<10: {int((best['n'] < 10).sum())}; mass share of cells whose best target has chg_lcb>0: "
          f"{best.loc[best['chg_lcb'] > 0, 'mass'].sum() / best['mass'].sum():.4f}")

    # unseen (cell, target) combos: agent prior vs the MOCK's price-based fallback (real env fallback unknown)
    med_price, med_conv = max(price.median(), 1.0), float(g3["share"].median())
    conv_agent_med = float(g3["conv_agent"].median())
    un = ctg[ctg["n_hist"] == 0].copy()
    un["fb_change"] = (0.4 * (price.reindex(un["target"]).values - price.reindex(un["tariff"]).values) / med_price).clip(-1, 3)
    un["fb_prod"] = un["fb_change"] * med_conv
    Nfs = N.reindex(pd.MultiIndex.from_frame(un[["tariff", "seg"]])).fillna(0).values
    pct = [m2.get((f, t), m1.get(t, g0)) for f, t in zip(un["tariff"], un["target"])]
    un["agent_mu0"] = np.array(pct) * np.where(Nfs > 0, 0.5 / (Nfs + 0.5 * N_TARIFFS), conv_agent_med)
    print(f"\nunseen audience combos: {len(un)}; median price {med_price:.1f}; mock fallback conversion (median share) {med_conv:.4f}")
    print(f"  mock fallback product > 0: {int((un['fb_prod'] > 0).sum())}; max {un['fb_prod'].max():.4f}; "
          f"agent prior mu0 for unseen: median {un['agent_mu0'].median():.4f}, max {un['agent_mu0'].max():.4f}")
    best_seen = aud.groupby(level=[0, 1])["prod_mock"].max()
    bu = un.groupby(["tariff", "seg"])["fb_prod"].max()
    both_ = best_seen.reindex(bu.index)
    print(f"  audience cells where best unseen fallback product > best seen mock product: {int((bu > both_.fillna(-np.inf)).sum())} of {len(bu)}")
    un["fb_value"] = un["fb_prod"] * un["mass"]
    print("  top-8 unseen combos by mock fallback product x cell mass:")
    print(un.sort_values("fb_value", ascending=False).head(8)[["tariff", "seg", "target", "mass", "fb_change", "fb_prod", "agent_mu0", "fb_value"]].to_string(index=False))


if __name__ == "__main__":
    main()
