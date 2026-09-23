"""c1v: re-derive c1-14 (segment-blind shrinkage parent in agent._prior) and measure its decision impact on mu0 = pct x conv."""
import os
import numpy as np
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
raw_ct = pd.read_csv(os.path.join(P, "data", "change_tariff.csv"))
pr = pd.read_csv(os.path.join(P, "customer_profile.csv"))
tariffs = sorted(pd.read_csv(os.path.join(P, "data", "dict_tariff.csv")).tariff_plan_code)
F, T, K = "tariff_plan_code_from", "tariff_plan_code_to", 15


def prep(df):
    df = df[df.AVG_ARPU_PREV_3M >= 100].copy()
    df["seg"] = pd.cut(df.AVG_ARPU_PREV_3M, [-np.inf, 1000, 5000, np.inf], labels=["LOW", "MID", "HIGH"]).astype(str)
    df["pct"] = ((df.AVG_ARPU_NEXT_3M - df.AVG_ARPU_PREV_3M) / df.AVG_ARPU_PREV_3M).clip(-1, 3)
    return df


def prior(df, parent):
    """Returns m3 (shrunk cell mean), n3, fallback(from,seg,to)->mean for unseen cells."""
    g0 = df.pct.mean()
    s3 = df.groupby([F, "seg", T]).pct.agg(["sum", "size"])
    if parent == "agent":
        s1 = df.groupby(T).pct.agg(["sum", "size"])
        m1 = (s1["sum"] + K * g0) / (s1["size"] + K)
        s2 = df.groupby([F, T]).pct.agg(["sum", "size"])
        m2 = (s2["sum"] + K * m1.loc[s2.index.get_level_values(1)].to_numpy()) / (s2["size"] + K)
        par = np.array([m2[(a, c)] for a, _, c in s3.index])
        fb = lambda a, s, c: m2.get((a, c), m1.get(c, g0))
    else:
        ms = df.groupby("seg").pct.mean()
        s2 = df.groupby(["seg", T]).pct.agg(["sum", "size"])
        m2 = (s2["sum"] + K * ms.loc[s2.index.get_level_values(0)].to_numpy()) / (s2["size"] + K)
        par = np.array([m2[(s, c)] for _, s, c in s3.index])
        fb = lambda a, s, c: m2.get((s, c), ms.get(s, g0))
    m3 = (s3["sum"] + K * par) / (s3["size"] + K)
    return m3, s3["size"], pd.Series(par, index=s3.index), fb


ct = prep(raw_ct)
print("rows PREV>=100:", len(ct))
raw = ct.groupby([F, "seg", T]).pct.mean()
for kind in ["agent", "segto"]:
    m3, n3, par, _ = prior(ct, kind)
    sh = m3 - raw
    lv = m3.index.get_level_values(1)
    print(f"[{kind}] weighted shift:", {s: round(float(np.average(sh[lv == s], weights=n3[lv == s])), 4) for s in ["LOW", "MID", "HIGH"]})
    thin = (lv == "HIGH") & (n3 < 15)
    print(f"[{kind}] HIGH cells n<15: {int(thin.sum())}, mean shift {sh[thin].mean():+.4f}; HIGH mean parent {par[lv == 'HIGH'].mean():+.4f}")
print(f"HIGH raw mean of cell means {raw[raw.index.get_level_values(1) == 'HIGH'].mean():+.4f}")

print("\nSplit-half (seed 11, 20 splits): weighted MSE vs held-out raw cell means")
rng = np.random.default_rng(11)
res = {"agent": [], "segto": []}
thin_res = {"agent": [], "segto": []}
for _ in range(20):
    a = rng.random(len(ct)) < 0.5
    A, B = ct[a], ct[~a]
    gB = B.groupby([F, "seg", T]).pct.agg(["mean", "size"])
    for kind in res:
        m3, n3, _, _ = prior(A, kind)
        j = gB.join(pd.DataFrame({"pred": m3, "nA": n3}), how="inner")
        res[kind].append(np.average((j["mean"] - j.pred) ** 2, weights=j["size"]))
        t = j[j.nA < 15]
        thin_res[kind].append(np.average((t["mean"] - t.pred) ** 2, weights=t["size"]))
dd = np.array(res["segto"]) - np.array(res["agent"])
print(f"  agent {np.mean(res['agent']):.4f}  segto {np.mean(res['segto']):.4f}  segto better in {int((dd < 0).sum())}/20")
dt_ = np.array(thin_res["segto"]) - np.array(thin_res["agent"])
print(f"  thin cells (nA<15): agent {np.mean(thin_res['agent']):.4f}  segto {np.mean(thin_res['segto']):.4f}  segto better {int((dt_ < 0).sum())}/20")

print("\nDecision impact on the agent's hypothesis set (mu0 = pct x conv, top-3 per target cell)")
prof = pr.dropna(subset=["current_tariff", "arpu_segment", "predicted_arpu"])
cells = prof.groupby(["current_tariff", "arpu_segment"]).agg(n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum")).reset_index()
cells = cells[cells.n >= 20]
print("target cells n>=20:", len(cells), " subscribers:", int(cells.n.sum()), " HIGH subscribers (all profile):", int((pr.arpu_segment == "HIGH").sum()), "of", len(pr))
nfs = ct.groupby([F, "seg"]).size()
nt = len(tariffs)
conv_all = None
hyp = {}
for kind in ["agent", "segto"]:
    m3, n3, _, fb = prior(ct, kind)
    tot = np.array([nfs[(a, s)] for a, s, _ in m3.index])
    conv = (n3 + 0.5) / (tot + 0.5 * nt)
    rows = []
    for _, c in cells.iterrows():
        for tg in tariffs:
            if tg == c.current_tariff:
                continue
            key = (c.current_tariff, c.arpu_segment, tg)
            if key in m3.index:
                pct, cv, n = m3[key], conv[key], int(n3[key])
            else:
                N = nfs.get((c.current_tariff, c.arpu_segment), 0)
                pct, cv, n = fb(*key), (0.5 / (N + 0.5 * nt) if N > 0 else float(conv.median())), 0
            rows.append((c.current_tariff, c.arpu_segment, tg, int(c.n), float(c.mass), pct, cv, pct * cv, n))
    h = pd.DataFrame(rows, columns=["tariff", "seg", "target", "n", "mass", "pct", "conv", "mu0", "n3"])
    h = h.sort_values(["tariff", "seg", "mu0", "target"], ascending=[True, True, False, True])
    hyp[kind] = h
    top3 = h.groupby(["tariff", "seg"]).head(3)
    hi = top3[top3.seg == "HIGH"]
    print(f"[{kind}] top-3 hyps: {len(top3)}; HIGH: {len(hi)}, of which n3<15: {int((hi.n3 < 15).sum())}, unseen: {int((hi.n3 == 0).sum())}; "
          f"all top-3 unseen: {int((top3.n3 == 0).sum())}")
ha, hs = hyp["agent"], hyp["segto"]
mg = ha.merge(hs, on=["tariff", "seg", "target"], suffixes=("_a", "_s"))
for s in ["LOW", "MID", "HIGH"]:
    x = mg[mg.seg == s]
    print(f"  {s}: mean |mu0_a - mu0_s| = {np.abs(x.mu0_a - x.mu0_s).mean():.4f}, mean (pct_a - pct_s) = {(x.pct_a - x.pct_s).mean():+.4f}, "
          f"mean conv = {x.conv_a.mean():.4f}")
ta = ha.groupby(["tariff", "seg"]).head(1).set_index(["tariff", "seg"])
ts = hs.groupby(["tariff", "seg"]).head(1).set_index(["tariff", "seg"])
jj = ta.join(ts[["target", "mu0"]], rsuffix="_s")
chg = jj.target != jj.target_s
print(f"top-1 target changes in {int(chg.sum())} of {len(jj)} cells, covering {int(jj.n[chg].sum())} target subscribers "
      f"(HIGH cells changed: {int(chg[jj.index.get_level_values(1) == 'HIGH'].sum())})")
print(jj[chg][["n", "target", "mu0", "target_s", "mu0_s"]].round(4).to_string())
s3a = set(map(tuple, ha.groupby(["tariff", "seg"]).head(3)[["tariff", "seg", "target"]].to_numpy()))
s3s = set(map(tuple, hs.groupby(["tariff", "seg"]).head(3)[["tariff", "seg", "target"]].to_numpy()))
print(f"top-3 hypothesis sets differ by {len(s3a - s3s)} hypotheses (of {len(s3a)})")
# sign of mu0 for top-1 under each
print(f"top-1 mu0>0 cells: agent {int((jj.mu0 > 0).sum())}, segto {int((jj.mu0_s > 0).sum())}")

print("\nScale check: can an untested hypothesis pass r_adj = mu - 0.5*sd (sd>=0.30) without calibration?")
for kind in ["agent", "segto"]:
    t3 = hyp[kind].groupby(["tariff", "seg"]).head(3)
    print(f"[{kind}] top-3 mu0 max {t3.mu0.max():.4f}, count mu0>0.15: {int((t3.mu0 > 0.15).sum())}, "
          f"HIGH top-3 with target tariff_9: {int(((t3.seg == 'HIGH') & (t3.target == 'tariff_9')).sum())}")

print("\nHIGH -> tariff_9 detail (agent prior vs raw history)")
m3a, n3a, para, _ = prior(ct, "agent")
m3s, _, pars, _ = prior(ct, "segto")
for fr in ["tariff_10", "tariff_4", "tariff_14", "tariff_8", "tariff_11"]:
    key = (fr, "HIGH", "tariff_9")
    if key in m3a.index:
        print(f"  {key}: n={int(n3a[key])} raw={raw[key]:+.4f} agent m3={m3a[key]:+.4f} (parent {para[key]:+.4f}) segto m3={m3s[key]:+.4f} (parent {pars[key]:+.4f})")
    else:
        print(f"  {key}: unseen")
for kind in ["agent", "segto"]:
    q = hyp[kind]
    q = q[(q.seg == "HIGH") & (q.target == "tariff_9") & q.tariff.isin(["tariff_10", "tariff_4", "tariff_14", "tariff_8", "tariff_11"])]
    print(f"  [{kind}] fallback pct/conv/mu0:", q[["tariff", "pct", "conv", "mu0", "n3"]].round(4).to_dict("records"))
x9 = ct[ct[T] == "tariff_9"]
print("  history ->tariff_9 mean pct by seg:", x9.groupby("seg").pct.agg(["size", "mean"]).round(4).to_dict("index"))

print("\nSplit-half by segment (seed 11, 20 splits)")
rng = np.random.default_rng(11)
bys = {k: {s: [] for s in ["LOW", "MID", "HIGH"]} for k in ["agent", "segto"]}
for _ in range(20):
    a = rng.random(len(ct)) < 0.5
    A, B = ct[a], ct[~a]
    gB = B.groupby([F, "seg", T]).pct.agg(["mean", "size"])
    for kind in bys:
        m3, _, _, _ = prior(A, kind)
        j = gB.join(m3.rename("pred"), how="inner")
        for s in bys[kind]:
            x = j[j.index.get_level_values(1) == s]
            bys[kind][s].append(np.average((x["mean"] - x.pred) ** 2, weights=x["size"]))
for kind in bys:
    print(f"  {kind}:", {s: round(float(np.mean(v)), 4) for s, v in bys[kind].items()})
