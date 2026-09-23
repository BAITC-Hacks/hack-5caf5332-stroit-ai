"""c1 follow-up to part 6: arpu_segment carries much within-(from,to) signal, but agent.py shrinks
(from, seg, to) means toward a segment-blind (from, to) parent. Measure the resulting bias and compare
with a segment-aware parent (seg, to) in split-half prediction. Replicates agent._prior (K=15, PREV>=100, clip)."""
import os
import numpy as np
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ct = pd.read_csv(os.path.join(P, "data", "change_tariff.csv"))
pr = pd.read_csv(os.path.join(P, "customer_profile.csv"))
ct = ct[ct.AVG_ARPU_PREV_3M >= 100].copy()
ct["seg"] = np.select([ct.AVG_ARPU_PREV_3M < 1000, ct.AVG_ARPU_PREV_3M <= 5000], ["LOW", "MID"], "HIGH")
ct["pct"] = ((ct.AVG_ARPU_NEXT_3M - ct.AVG_ARPU_PREV_3M) / ct.AVG_ARPU_PREV_3M).clip(-1, 3)
f, t, K = "tariff_plan_code_from", "tariff_plan_code_to", 15


def shrunk(df, parent_kind):
    g0 = df.pct.mean()
    g3 = df.groupby([f, "seg", t])["pct"].agg(["sum", "size"])
    if parent_kind == "agent_(from,to)":
        g1 = df.groupby(t)["pct"].agg(["sum", "size"])
        m1 = (g1["sum"] + K * g0) / (g1["size"] + K)
        g2 = df.groupby([f, t])["pct"].agg(["sum", "size"])
        m2 = (g2["sum"] + K * m1.reindex(g2.index.get_level_values(1)).values) / (g2["size"] + K)
        par = m2.reindex(list(zip(g3.index.get_level_values(0), g3.index.get_level_values(2)))).values
    else:  # (seg, to) shrunk toward seg mean
        gs = df.groupby("seg")["pct"].mean()
        g2 = df.groupby(["seg", t])["pct"].agg(["sum", "size"])
        m2 = (g2["sum"] + K * gs.reindex(g2.index.get_level_values(0)).values) / (g2["size"] + K)
        par = m2.reindex(list(zip(g3.index.get_level_values(1), g3.index.get_level_values(2)))).values
    return (g3["sum"] + K * par) / (g3["size"] + K), g3["size"], pd.Series(par, index=g3.index)


print("rows (PREV>=100):", len(ct))
raw = ct.groupby([f, "seg", t])["pct"].mean()
for kind in ["agent_(from,to)", "(seg,to)"]:
    m3, n3, par = shrunk(ct, kind)
    d = (m3 - raw)
    print(f"\nparent={kind}: shrinkage shift (shrunk - raw cell mean), count-weighted, by segment:")
    for s in ["LOW", "MID", "HIGH"]:
        idx = m3.index.get_level_values(1) == s
        w = n3[idx]
        print(f"  {s}: mean shift={np.average(d[idx], weights=w):+.4f}  cells={int(idx.sum())}  "
              f"mean parent-raw gap (unweighted)={(par[idx] - raw[idx]).mean():+.4f}")
    small = (n3 < 15) & (m3.index.get_level_values(1) == "HIGH")
    print(f"  HIGH cells with n<15: {int(small.sum())}, mean shift={d[small].mean():+.4f}")

print("\nSplit-half check (20 random halves, seed 0): fit on A, predict raw cell means of B, "
      "error weighted by n_B; cells present in both halves")
rng = np.random.default_rng(0)
res = {"agent_(from,to)": [], "(seg,to)": []}
res_seg = {k: {s: [] for s in ["LOW", "MID", "HIGH"]} for k in res}
for _ in range(20):
    a = rng.random(len(ct)) < 0.5
    A, B = ct[a], ct[~a]
    gB = B.groupby([f, "seg", t])["pct"].agg(["mean", "size"])
    for kind in res:
        m3, _, _ = shrunk(A, kind)
        j = gB.join(m3.rename("pred"), how="inner")
        res[kind].append(np.average((j["mean"] - j.pred) ** 2, weights=j["size"]))
        for s in ["LOW", "MID", "HIGH"]:
            js = j[j.index.get_level_values(1) == s]
            res_seg[kind][s].append(np.average((js["mean"] - js.pred) ** 2, weights=js["size"]))
for kind in res:
    print(f"  {kind}: weighted MSE mean={np.mean(res[kind]):.4f} (sd over splits {np.std(res[kind]):.4f}); by seg: "
          + ", ".join(f"{s}={np.mean(v):.4f}" for s, v in res_seg[kind].items()))
diff = np.array(res["(seg,to)"]) - np.array(res["agent_(from,to)"])
print(f"  (seg,to) minus agent MSE: mean={diff.mean():+.4f}, splits where (seg,to) better: {int((diff < 0).sum())}/20")

# unseen (from, seg, to) transitions: the agent falls back to m2(from,to); how far is m2 from the HIGH mean?
m3, n3, par = shrunk(ct, "agent_(from,to)")
hi = m3.index.get_level_values(1) == "HIGH"
print(f"\nHIGH cells: raw mean of cell means={raw[hi].mean():+.4f}, mean of agent parent m2={par[hi].mean():+.4f}")
print("target subscribers by arpu_segment:", pr.arpu_segment.value_counts().to_dict())
