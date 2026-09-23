"""b1v: adversarial re-derivation of b1-09..12 (empirical Bayes, split-half, hierarchy) plus decision-impact checks.

Independent of analysis/b1_*.py. Deterministic (seeds 0..19 replicate the analyst's split; 100..119 are fresh).
Run from P: python3 analysis/b1v_reliability.py
"""
import os

import numpy as np
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FR, TO, PV, NX = "tariff_plan_code_from", "tariff_plan_code_to", "AVG_ARPU_PREV_3M", "AVG_ARPU_NEXT_3M"
ct = pd.read_csv(os.path.join(P, "data", "change_tariff.csv"))
price = dict(pd.read_csv(os.path.join(P, "data", "dict_tariff.csv"))[["tariff_plan_code", "price_tariff"]].values)
d = ct[ct[PV] >= 100].reset_index(drop=True)
d["seg"] = np.where(d[PV] <= 1000, "LOW", np.where(d[PV] <= 5000, "MID", "HIGH"))
d["rel"] = ((d[NX] - d[PV]) / d[PV]).clip(-1, 3)
d["cell"] = list(zip(d[FR], d["seg"], d[TO]))
y = d["rel"].values


def keyof(df, cols):
    return list(zip(*[df[c] for c in cols])) if len(cols) > 1 else list(df[cols[0]])


def eb(df, child, parent):
    """Nested unbalanced method of moments: E[sum n_i (m_i - m_p)^2] = (G-P) s2 + (N - sum n_i^2/n_p) t2."""
    ck = pd.Series(keyof(df, child), index=df.index)
    pk = pd.Series(keyof(df, parent), index=df.index) if parent else pd.Series(0, index=df.index)
    r = df["rel"]
    cs = pd.DataFrame({"c": ck, "p": pk, "y": r})
    gc = cs.groupby("c").agg(n=("y", "size"), m=("y", "mean"), ss=("y", lambda v: ((v - v.mean()) ** 2).sum()), p=("p", "first"))
    gp = cs.groupby("p")["y"].agg(["size", "mean"])
    s2 = gc["ss"].sum() / (len(cs) - len(gc))
    mp = gp["mean"].reindex(gc["p"]).values
    npar = gp["size"].reindex(gc["p"]).values
    ssb = (gc["n"].values * (gc["m"].values - mp) ** 2).sum()
    t2 = (ssb - (len(gc) - len(gp)) * s2) / (len(cs) - (gc["n"].values ** 2 / npar).sum())
    return s2, t2, len(gc)


print("== b1-09 empirical Bayes (clipped rel, kept rows)")
for name, c, p in [("to|global", [TO], []), ("(from,to)|to", [FR, TO], [TO]), ("cell|(from,to)", [FR, "seg", TO], [FR, TO]),
                   ("cell|(from,seg)", [FR, "seg", TO], [FR, "seg"]), ("cell|(seg,to)", [FR, "seg", TO], ["seg", TO]),
                   ("(seg,to)|seg", ["seg", TO], ["seg"]), ("seg|global", ["seg"], [])]:
    s2, t2, G = eb(d, c, p)
    print(f"  {name:<16} G {G:4d} sigma2 {s2:.4f} tau2 {t2:.5f} K {s2 / t2:.1f}")
n3 = d.groupby("cell").size()
s2, t2, _ = eb(d, [FR, "seg", TO], [FR, TO])
print(f"  median cell n {n3.median():.0f}: own weight K3={s2 / t2:.2f} -> {n3.median() / (n3.median() + s2 / t2):.3f}; K=15 -> {n3.median() / (n3.median() + 15):.3f}")
print("  per-seg cell|(from,to) inside the segment is undefined (from,to within seg == cell); per-seg cell|(to):")
for s in ["LOW", "MID", "HIGH"]:
    ds = d[d.seg == s]
    s2s, t2s, G = eb(ds, [FR, TO], [TO])
    wsd = np.sqrt(ds.groupby("cell")["rel"].apply(lambda v: ((v - v.mean()) ** 2).sum()).sum() / (len(ds) - ds["cell"].nunique()))
    print(f"  {s}: within-cell sd {wsd:.4f}; (from,to)|to within seg: sigma2 {s2s:.4f} tau2 {t2s:.5f} K {s2s / t2s:.1f} ({G} cells)")


# ------------------------------------------------------------ shrinkage chains
def fit(A, levels, Ks):
    g0 = A["rel"].mean()
    ests, parent_keys = [], None
    for cols, K in zip(levels, Ks):
        kk = keyof(A, cols)
        g = pd.DataFrame({"k": kk, "y": A["rel"].values}).groupby("k")["y"].agg(["sum", "size"])
        if parent_keys is None:
            par = np.full(len(g), g0)
        else:
            idx = [tuple(k[i] for i in parent_keys) if len(parent_keys) > 1 else k[parent_keys[0]] for k in
                   (x if isinstance(x, tuple) else (x,) for x in g.index)]
            par = np.array([ests[-1][j] for j in idx])
        est = dict(zip(g.index, (g["sum"].values + K * par) / (g["size"].values + K)))
        ests.append(est)
        if len(levels) > len(ests):
            nxt = levels[len(ests)]
            parent_keys = [nxt.index(c) for c in cols]
    return g0, ests


def predict(model, levels, cells):
    g0, ests = model
    out = []
    for f, s, t in cells:
        v, row = g0, {FR: f, "seg": s, TO: t}
        for cols, est in zip(levels, ests):
            k = tuple(row[c] for c in cols) if len(cols) > 1 else row[cols[0]]
            v = est.get(k, v)
        out.append(v)
    return np.array(out)


CH = {"agent": [[TO], [FR, TO], [FR, "seg", TO]], "to>(seg,to)>cell": [[TO], ["seg", TO], [FR, "seg", TO]],
      "seg>(seg,to)>cell": [["seg"], ["seg", TO], [FR, "seg", TO]], "seg>(from,seg)>cell": [["seg"], [FR, "seg"], [FR, "seg", TO]]}
# self-check: agent chain reproduces agent.py _prior formula on the full data for one cell
_m = fit(d, CH["agent"], [15, 15, 15])
c0 = ("tariff_4", "MID", "tariff_8")
g1 = d[d[TO] == "tariff_8"]["rel"]
m1 = (g1.sum() + 15 * d["rel"].mean()) / (len(g1) + 15)
g2 = d[(d[FR] == "tariff_4") & (d[TO] == "tariff_8")]["rel"]
m2 = (g2.sum() + 15 * m1) / (len(g2) + 15)
g3 = d[d["cell"] == c0]["rel"]
assert abs((g3.sum() + 15 * m2) / (len(g3) + 15) - _m[1][2][c0]) < 1e-12


def split_eval(seeds, grid):
    rows, noise, corr = [], [], []
    for seed in seeds:
        perm = np.random.default_rng(seed).permutation(len(d))
        A, B = d.iloc[perm[: len(d) // 2]], d.iloc[perm[len(d) // 2:]]
        gb = B.groupby("cell")["rel"].agg(["mean", "size", "var"])
        ga = A.groupby("cell")["rel"].mean()
        both = gb.index.isin(ga.index)
        nb = gb["size"].values
        noise.append(gb.loc[both, "var"].fillna(0).sum() / nb[both].sum())
        x, yy, w = ga.reindex(gb.index[both]).values, gb.loc[both, "mean"].values, nb[both]
        mx, my = np.average(x, weights=w), np.average(yy, weights=w)
        corr.append(np.average((x - mx) * (yy - my), weights=w) / np.sqrt(np.average((x - mx) ** 2, weights=w) * np.average((yy - my) ** 2, weights=w)))
        for ch, Ks in grid:
            p = predict(fit(A, CH[ch], Ks), CH[ch], list(gb.index))
            e = nb * (p - gb["mean"].values) ** 2
            rows.append(dict(seed=seed, ch=ch, K=str(Ks), both=e[both].sum() / nb[both].sum(), all=e.sum() / nb.sum()))
    return pd.DataFrame(rows), float(np.mean(noise)), float(np.mean(corr)), float(np.std(corr, ddof=1))


KS = [0, 1, 2, 3, 5, 8, 10, 15, 20, 30, 50, 80, 100, 150]
grid = [("agent", (k, k, k)) for k in KS] + [("agent", (150, 150, 3)), ("agent", (150, 150, 5))]
grid += [(c, (15, 15, 15)) for c in ["to>(seg,to)>cell", "seg>(seg,to)>cell", "seg>(from,seg)>cell"]]
grid += [("seg>(from,seg)>cell", (50, 50, 8))]
grid += [(c, (k12, k12, k3)) for c in ["to>(seg,to)>cell", "seg>(seg,to)>cell"] for k12 in (5, 15, 50) for k3 in (3, 5, 8, 15, 30)]
for label, seeds in [("seeds 0..19 (analyst's split)", range(20)), ("fresh seeds 100..119", range(100, 120))]:
    r, nf, cm, cs = split_eval(seeds, grid)
    print(f"\n== b1-10/11 split-half, {label}: noise floor {nf:.4f}; raw A-vs-B weighted corr {cm:.4f} (sd {cs:.4f})")
    s = r.groupby(["ch", "K"])[["both", "all"]].mean()
    for k in [0, 5, 15, 50, 150]:
        v = s.loc[("agent", str((k, k, k)))]
        print(f"  agent K={k:<3} err_both {v['both']:.4f} err_all {v['all']:.4f} excess {v['both'] - nf:.4f}")
    ag = s.loc["agent"]
    ag_eq = ag.loc[[str((k, k, k)) for k in KS]]
    print(f"  agent equal-K argmin err_both {ag_eq['both'].idxmin()}, err_all {ag_eq['all'].idxmin()}")
    per = r[(r.ch == "agent") & r.K.isin([str((k, k, k)) for k in KS])]
    am = per.loc[per.groupby("seed")["both"].idxmin(), "K"].map(lambda t: int(t.strip("()").split(",")[0]))
    print(f"  per-seed argmin K: mean {am.mean():.1f} sd {am.std(ddof=1):.1f} min {am.min()} max {am.max()}")
    base = s.loc[("agent", str((15, 15, 15))), "both"] - nf
    print(f"  agent (5,5,5)/(15,15,15) excess ratio {(s.loc[('agent', str((5, 5, 5))), 'both'] - nf) / base:.4f}")
    for key in [("agent", (150, 150, 3)), ("agent", (150, 150, 5)), ("to>(seg,to)>cell", (15, 15, 15)),
                ("seg>(seg,to)>cell", (15, 15, 15)), ("seg>(from,seg)>cell", (15, 15, 15)), ("seg>(from,seg)>cell", (50, 50, 8))]:
        v = s.loc[(key[0], str(key[1]))]
        print(f"  {key[0]:<20} {str(key[1]):<14} err_both {v['both']:.4f} err_all {v['all']:.4f} excess {v['both'] - nf:.4f} ({(v['both'] - nf) / base:.3f}x agent K15)")
    seg_aware = s.loc[["to>(seg,to)>cell", "seg>(seg,to)>cell"]]
    kb = seg_aware["both"].idxmin()
    print(f"  best seg-aware grid point {kb}: err_both {seg_aware.loc[kb, 'both']:.4f} excess {seg_aware.loc[kb, 'both'] - nf:.4f}")

# ------------------------------------------------------------ decision impact of the prior change
print("\n== decision impact: agent top-3 hypotheses per audience cell under alternative priors (full data)")
prof = pd.read_csv(os.path.join(P, "customer_profile.csv")).dropna(subset=["current_tariff", "arpu_segment", "predicted_arpu"])
aud = prof.groupby(["current_tariff", "arpu_segment"]).agg(n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum"))
aud = aud[aud["n"] >= 20]
N = d.groupby([FR, "seg"]).size()
cnt = d.groupby("cell").size()
conv = {c: (n + 0.5) / (N[(c[0], c[1])] + 10.5) for c, n in cnt.items()}
conv_med = float(np.median(list(conv.values())))


def top3(ch, Ks):
    model = fit(d, CH[ch], Ks)
    out = {}
    for (f, s) in aud.index:
        cands = []
        for t in sorted(price):
            if t == f:
                continue
            c = (f, s, t)
            if c in cnt.index:
                mu = predict(model, CH[ch], [c])[0] * conv[c]
            else:   # agent.py unseen rule: (from,to) mean else to mean else global, x near-zero conversion
                g0, ests = model
                row = {FR: f, "seg": s, TO: t}
                pct = g0
                for cols, est in zip(CH[ch][:2], ests[:2]):
                    k = tuple(row[x] for x in cols) if len(cols) > 1 else row[cols[0]]
                    pct = est.get(k, pct)
                Nf = N.get((f, s), 0)
                mu = pct * (0.5 / (Nf + 10.5) if Nf > 0 else conv_med)
            cands.append((-mu, t, c in cnt.index))
        cands.sort()
        out[(f, s)] = [(t, seen, -m) for m, t, seen in cands[:3]]
    return out


base = top3("agent", (15, 15, 15))
unseen_in = sum(1 for v in base.values() for t, seen, _ in v if not seen)
print(f"  agent K=15: unseen combos among top-3 hypotheses: {unseen_in} of {3 * len(base)}; cells with <3 seen targets: "
      f"{sum(1 for (f, s) in aud.index if N.get((f, s), 0) and sum(1 for c in cnt.index if c[0] == f and c[1] == s) < 3)}")
mtot = aud["mass"].sum()
for ch, Ks in [("agent", (5, 5, 5)), ("agent", (150, 150, 3)), ("to>(seg,to)>cell", (15, 15, 15)), ("seg>(seg,to)>cell", (15, 15, 15))]:
    alt = top3(ch, Ks)
    ch1 = [c for c in base if base[c][0][0] != alt[c][0][0]]
    ch3 = [c for c in base if {t for t, _, _ in base[c]} != {t for t, _, _ in alt[c]}]
    print(f"  {ch:<18} {str(Ks):<14} top-1 changes in {len(ch1)} of {len(base)} cells (mass share {aud.loc[ch1, 'mass'].sum() / mtot:.4f}); "
          f"top-3 set changes in {len(ch3)} (mass share {aud.loc[ch3, 'mass'].sum() / mtot:.4f})")
    for c in sorted(ch1, key=lambda c: -aud.loc[c, "mass"])[:4]:
        print(f"     {c}: {base[c][0][0]} ({base[c][0][2]:+.4f}) -> {alt[c][0][0]} ({alt[c][0][2]:+.4f})")
