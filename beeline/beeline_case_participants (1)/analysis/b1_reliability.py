"""b1: reliability of (from, seg, to) cell estimates of the clipped relative ARPU change.

(a) empirical Bayes / nested method-of-moments variance components -> implied pseudo-count K = sigma^2/tau^2
(b) split-half: seeded 50/50 row splits, agent-style shrinkage fitted on half A, scored on half B cell means.
Run: python3 analysis/b1_reliability.py   (seeds 0..19, deterministic)
"""
import numpy as np
import pandas as pd

from b1_history import F, T, PREV, load, kept, shrink

KS = [0, 1, 2, 3, 5, 8, 10, 15, 20, 30, 50, 80, 100, 150, 250, 500, 1000]
REPORT_KS = [0, 5, 15, 50, 150]
SEEDS = range(20)


def nested_tau2(d, child, parent):
    """Unbalanced nested ANOVA (method of moments): variance of child means around their parent mean."""
    g = d.groupby(child)["rel"]
    n, m, v = g.size(), g.mean(), g.var(ddof=1).fillna(0)
    sigma2 = float(((n - 1) * v).sum() / (n - 1).sum())
    idx = n.index.to_frame(index=False)
    if parent:
        pm = d.groupby(parent)["rel"].mean()
        pn = d.groupby(parent).size()
        pkey = pd.MultiIndex.from_frame(idx[parent]) if len(parent) > 1 else pd.Index(idx[parent[0]])
        mp = pm.reindex(pkey).values
        n2p = (n.values ** 2 / pn.reindex(pkey).values).sum()
        P = len(pm)
    else:
        mp = d["rel"].mean()
        n2p = (n.values ** 2).sum() / len(d)
        P = 1
    ss = float((n.values * (m.values - mp) ** 2).sum())
    df = len(n) - P
    tau2 = (ss - df * sigma2) / (len(d) - n2p)
    return sigma2, tau2, len(n), P


AGENT_CHAIN = [[T], [F, T], [F, "seg", T]]
CHAINS = {"agent: to > (from,to) > cell": AGENT_CHAIN,
          "to > (seg,to) > cell": [[T], ["seg", T], [F, "seg", T]],
          "seg > (seg,to) > cell": [["seg"], ["seg", T], [F, "seg", T]],
          "seg > (from,seg) > cell": [["seg"], [F, "seg"], [F, "seg", T]]}


def _key(frame, keys):
    return pd.MultiIndex.from_frame(frame[keys]) if len(keys) > 1 else pd.Index(frame[keys[0]])


def shrink_chain(d, Ks, levels):
    """Generic hierarchical shrinkage, coarse -> fine; Ks = pseudo-count per level. Returns (g0, [estimates])."""
    g0 = d["rel"].mean()
    est, prev, out = g0, None, []
    for K, keys in zip(Ks, levels):
        g = d.groupby(keys)["rel"].agg(["sum", "size"])
        par = est if prev is None else est.reindex(_key(g.index.to_frame(index=False), prev)).values
        est = (g["sum"] + K * par) / (g["size"] + K)
        prev = keys
        out.append(est)
    return g0, out


def predict(fit, levels, cell_keys):
    """Finest available level for each B cell (the agent's fallback chain), else global mean."""
    g0, ests = fit
    fr = cell_keys.to_frame(index=False)
    p = np.full(len(fr), g0)
    for est, keys in zip(ests, levels):
        v = est.reindex(_key(fr, keys)).values
        p = np.where(np.isnan(v), p, v)
    return p


def wcorr(x, y, w):
    mx, my = np.average(x, weights=w), np.average(y, weights=w)
    return np.average((x - mx) * (y - my), weights=w) / np.sqrt(
        np.average((x - mx) ** 2, weights=w) * np.average((y - my) ** 2, weights=w))


def main():
    ct, _ = load()
    d = kept(ct).reset_index(drop=True)
    print(f"kept rows {len(d)}, cells (from,seg,to) {d.groupby([F, 'seg', T]).ngroups}")

    # ------------------------------------------------------------ (a) empirical Bayes
    print("\n(a) EMPIRICAL BAYES variance components of clipped rel change")
    levels = [("destination | global", [T], []),
              ("(from,to) | destination", [F, T], [T]),
              ("(from,seg,to) | (from,to)", [F, "seg", T], [F, T]),
              ("(from,seg,to) | global", [F, "seg", T], []),
              ("(from,seg,to) | (from,seg)", [F, "seg", T], [F, "seg"]),
              ("(seg,to) | seg", ["seg", T], ["seg"]),
              ("(from,seg,to) | (seg,to)", [F, "seg", T], ["seg", T])]
    for name, child, parent in levels:
        s2, t2, G, Pn = nested_tau2(d, child, parent)
        K = s2 / t2 if t2 > 0 else float("inf")
        print(f"  {name:<28} groups {G:4d} parents {Pn:3d}  sigma^2 {s2:.4f}  tau^2 {t2:.5f}  tau {np.sqrt(max(t2, 0)):.4f}  "
              f"implied K {K:.1f}")
    s2, t2, _, _ = nested_tau2(d, [F, "seg", T], [F, T])
    K3 = s2 / t2
    n3 = d.groupby([F, "seg", T]).size()
    print(f"  cells with n < implied K3 ({K3:.1f}): {int((n3 < K3).sum())} of {len(n3)}; with n < 15: {int((n3 < 15).sum())}")
    print(f"  weight on own cell mean at median cell n={n3.median():.0f}: K3 -> {n3.median() / (n3.median() + K3):.3f}, "
          f"K=15 -> {n3.median() / (n3.median() + 15):.3f}")
    print("  pooled within-cell sd by seg:",
          {sg: round(float(np.sqrt(((g.size() - 1) * g.var(ddof=1).fillna(0)).sum() / (g.size() - 1).sum())), 4)
           for sg, g in ((sg, d[d["seg"] == sg].groupby([F, T])["rel"]) for sg in ["LOW", "MID", "HIGH"])})
    for sg in ["LOW", "MID", "HIGH"]:
        s2s, t2s, G, _ = nested_tau2(d[d["seg"] == sg], [F, T], [T])
        print(f"  within seg {sg}: (from,to) | destination  sigma^2 {s2s:.4f} tau^2 {t2s:.5f} implied K {s2s / t2s if t2s > 0 else float('inf'):.1f} ({G} cells)")

    # ------------------------------------------------------------ (b) split-half
    print("\n(b) SPLIT-HALF (fit on A, score on B cell means; error weighted by n_B)")
    rec, raw_corr = [], []
    for seed in SEEDS:
        perm = np.random.default_rng(seed).permutation(len(d))
        A, B = d.iloc[perm[: len(d) // 2]], d.iloc[perm[len(d) // 2:]]
        gb = B.groupby([F, "seg", T])["rel"].agg(["mean", "size", "var"])
        ga = A.groupby([F, "seg", T])["rel"].agg(["mean", "size"])
        both = gb.index.isin(ga.index)
        noise = float(gb["var"].fillna(0).sum() / gb["size"].sum())   # E[n_B*(meanB - true)^2] summed / sum n_B
        noise_both = float(gb.loc[both, "var"].fillna(0).sum() / gb.loc[both, "size"].sum())
        ib = gb.index[both]
        raw_corr.append(wcorr(ga["mean"].reindex(ib).values, gb.loc[both, "mean"].values, gb.loc[both, "size"].values))
        for K in KS:
            p = predict(shrink_chain(A, [K] * 3, AGENT_CHAIN), AGENT_CHAIN, gb.index)
            e = gb["size"].values * (p - gb["mean"].values) ** 2
            rec.append(dict(seed=seed, K=K, err_all=e.sum() / gb["size"].sum(),
                            err_both=e[both].sum() / gb.loc[both, "size"].sum(),
                            corr_both=wcorr(p[both], gb.loc[both, "mean"].values, gb.loc[both, "size"].values),
                            noise=noise, noise_both=noise_both, cells_B=len(gb), cells_both=int(both.sum()),
                            rows_B_unseen=int(gb.loc[~both, "size"].sum())))
    r = pd.DataFrame(rec)
    print(f"  seeds {len(SEEDS)}; B cells mean {r['cells_B'].mean():.1f}, in both halves {r['cells_both'].mean():.1f}, "
          f"B rows in cells unseen in A {r['rows_B_unseen'].mean():.1f}")
    print(f"  raw A-mean vs raw B-mean weighted corr (cells in both): mean {np.mean(raw_corr):.4f} sd {np.std(raw_corr, ddof=1):.4f}")
    print(f"  noise floor (B sampling noise, cells in both) mean {r['noise_both'].mean():.4f}; all cells {r['noise'].mean():.4f}")
    s = r.groupby("K").agg(err_both=("err_both", "mean"), err_both_sd=("err_both", "std"), err_all=("err_all", "mean"),
                           err_all_sd=("err_all", "std"), corr_both=("corr_both", "mean"), corr_sd=("corr_both", "std"))
    s["excess_both"] = s["err_both"] - r["noise_both"].mean()
    s["excess_vs_K0"] = s["excess_both"] / s.loc[0, "excess_both"]
    print(s.to_string())
    print("  requested K:", s.loc[REPORT_KS, ["err_both", "err_all", "corr_both", "excess_vs_K0"]].round(4).to_dict("index"))
    best_both = r.loc[r.groupby("seed")["err_both"].idxmin(), "K"]
    best_all = r.loc[r.groupby("seed")["err_all"].idxmin(), "K"]
    print(f"  argmin K on mean curve: err_both {int(s['err_both'].idxmin())}, err_all {int(s['err_all'].idxmin())}")
    print(f"  per-seed argmin K (err_both): mean {best_both.mean():.1f} sd {best_both.std(ddof=1):.1f} "
          f"values {sorted(best_both.tolist())}")
    print(f"  per-seed argmin K (err_all):  mean {best_all.mean():.1f} sd {best_all.std(ddof=1):.1f}")
    w15 = r[r["K"] == 15].set_index("seed")["err_both"]
    wb = r.loc[r.groupby("seed")["err_both"].idxmin()].set_index("seed")["err_both"]
    print(f"  K=15 excess error over per-seed best: mean {(w15 - wb).mean():.5f} (relative to noise-free excess at K=15: "
          f"{((w15 - wb) / (w15 - r['noise_both'].groupby(r['seed']).first())).mean():.4f})")

    # separate K for upper levels vs cell level, for the agent's chain and segment-aware chains
    print("\n  hierarchy x (K12 upper levels, K3 cell level) grid, mean err_both / err_all over seeds:")
    rows = []
    for seed in SEEDS:
        perm = np.random.default_rng(seed).permutation(len(d))
        A, B = d.iloc[perm[: len(d) // 2]], d.iloc[perm[len(d) // 2:]]
        gb = B.groupby([F, "seg", T])["rel"].agg(["mean", "size"])
        both = gb.index.isin(A.groupby([F, "seg", T]).size().index)
        for name, lv in CHAINS.items():
            for K12 in [0, 5, 15, 50, 150, 500]:
                for K3 in [0, 3, 5, 8, 15, 50, 150, 500]:
                    p = predict(shrink_chain(A, [K12, K12, K3], lv), lv, gb.index)
                    e = gb["size"].values * (p - gb["mean"].values) ** 2
                    rows.append(dict(seed=seed, chain=name, K12=K12, K3=K3,
                                     err_both=e[both].sum() / gb.loc[both, "size"].sum(), err_all=e.sum() / gb["size"].sum()))
    res = pd.DataFrame(rows).groupby(["chain", "K12", "K3"])[["err_both", "err_all"]].mean()
    print("  agent chain, err_both (rows K12, cols K3):")
    print(res.loc[list(CHAINS)[0], "err_both"].unstack().round(4).to_string())
    nf = r["noise_both"].mean()
    base = res.loc[(list(CHAINS)[0], 15, 15), "err_both"] - nf
    for name in CHAINS:
        sub = res.loc[name]
        kb = sub["err_both"].idxmin()
        e15 = sub.loc[(15, 15), "err_both"]
        print(f"  {name:<30} K12=K3=15: err_both {e15:.4f} err_all {sub.loc[(15, 15), 'err_all']:.4f} "
              f"excess {e15 - nf:.4f} ({(e15 - nf) / base:.3f} x agent) | best (K12,K3)=({kb[0]},{kb[1]}): "
              f"err_both {sub.loc[kb, 'err_both']:.4f} err_all {sub.loc[kb, 'err_all']:.4f} excess {sub.loc[kb, 'err_both'] - nf:.4f}")
    print(f"  noise floor (cells in both) {nf:.4f}")


def _selfcheck():
    """shrink_chain on the agent chain must reproduce b1_history.shrink (the agent's _prior formula)."""
    d = kept(load()[0])
    _, _, _, m3 = shrink(d, 15)
    _, ests = shrink_chain(d, [15, 15, 15], AGENT_CHAIN)
    assert np.allclose(ests[2].reindex(m3.index).values, m3.values)


if __name__ == "__main__":
    _selfcheck()
    main()
