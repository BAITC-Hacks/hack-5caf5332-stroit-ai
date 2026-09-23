"""b1v: adversarial re-derivation of the b1 descriptive claims (b1-01..08, 13..16, caveats).

Independent of analysis/b1_*.py. Deterministic. Run from P: python3 analysis/b1v_core.py
"""
import math
import os

import numpy as np
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FR, TO, PV, NX = "tariff_plan_code_from", "tariff_plan_code_to", "AVG_ARPU_PREV_3M", "AVG_ARPU_NEXT_3M"


def seg_of(x):
    # right-closed like pd.cut(bins=[-inf,1000,5000,inf]); brief says <1000 / 1000-5000 / >5000
    return np.where(x <= 1000, "LOW", np.where(x <= 5000, "MID", "HIGH"))


def say(*a):
    print(*a)


ct = pd.read_csv(os.path.join(P, "data", "change_tariff.csv"))
price = dict(pd.read_csv(os.path.join(P, "data", "dict_tariff.csv"))[["tariff_plan_code", "price_tariff"]].values)
prof = pd.read_csv(os.path.join(P, "customer_profile.csv"))

say("== basics")
say("rows", len(ct), "NaN PREV", int(ct[PV].isna().sum()), "NaN NEXT", int(ct[NX].isna().sum()),
    "NaN from/to", int(ct[FR].isna().sum()), int(ct[TO].isna().sum()))
say("PREV exactly 1000:", int((ct[PV] == 1000).sum()), "exactly 5000:", int((ct[PV] == 5000).sum()),
    "| profile ARPU_3m_avg ==1000:", int((prof["ARPU_3m_avg"] == 1000).sum()), "==5000:", int((prof["ARPU_3m_avg"] == 5000).sum()))
say("NEXT<0 rows:", int((ct[NX] < 0).sum()), "PREV<0 rows:", int((ct[PV] < 0).sum()))
say("tariffs in history missing from dict:", sorted((set(ct[FR]) | set(ct[TO])) - set(price)))
say("tariff_9 movers by seg (kept):", ct[ct[PV] >= 100].assign(s=lambda x: seg_of(x[PV].values)).query(f"{TO} == 'tariff_9'")["s"].value_counts().to_dict(),
    "| tariff_8:", ct[ct[PV] >= 100].assign(s=lambda x: seg_of(x[PV].values)).query(f"{TO} == 'tariff_8'")["s"].value_counts().to_dict())

# ---------------------------------------------------------------- b1-01
say("\n== b1-01 PREV>=100 filter")
drop = ct[~(ct[PV] >= 100)]
say(f"dropped {len(drop)} ({100 * len(drop) / len(ct):.4f}%): zero {int((drop[PV] == 0).sum())}, negative {int((drop[PV] < 0).sum())}, "
    f"0<PREV<100 {int(((drop[PV] > 0) & (drop[PV] < 100)).sum())}")
dp = drop[drop[PV] > 0]
rr = (dp[NX] - dp[PV]) / dp[PV]
say(f"dropped PREV>0: n {len(dp)}, median rel {rr.median():.2f}, share >3 {100 * (rr > 3).mean():.4f}%, max {rr.max():.1f}")
low_p = prof[prof["arpu_segment"] == "LOW"]
say(f"profile LOW subs {len(low_p)}; ARPU_3m_avg<100 share {(low_p['ARPU_3m_avg'] < 100).mean():.4f}; <=0 share {(low_p['ARPU_3m_avg'] <= 0).mean():.4f}")
pm = low_p["predicted_arpu"]
say(f"  predicted_arpu mass share of LOW subs with ARPU_3m_avg<100: {pm[low_p['ARPU_3m_avg'] < 100].sum() / pm.sum():.4f}; "
    f"median predicted_arpu <100 band {pm[low_p['ARPU_3m_avg'] < 100].median():.2f} vs >=100 band {pm[low_p['ARPU_3m_avg'] >= 100].median():.2f}")
say(f"  LOW-segment share of total profile predicted_arpu mass: {pm.sum() / prof['predicted_arpu'].sum():.4f}")

# ---------------------------------------------------------------- b1-02 / b1-03
k = ct[ct[PV] >= 100].copy()
k["seg"] = seg_of(k[PV].values)
k["raw"] = (k[NX] - k[PV]) / k[PV]
k["rel"] = k["raw"].clip(-1, 3)
k["d"] = k[NX] - k[PV]
k["dprice"] = k[TO].map(price) - k[FR].map(price)
say("\n== b1-02 clipping")
say(f"kept {len(k)}; raw>3: {int((k['raw'] > 3).sum())} ({100 * (k['raw'] > 3).mean():.4f}%); raw<-1: {int((k['raw'] < -1).sum())}")
for s in ["LOW", "MID", "HIGH"]:
    ks = k[k.seg == s]
    say(f"  {s}: n {len(ks)}, share >3 {(ks['raw'] > 3).mean():.4f}, NEXT==0 share {(ks[NX] == 0).mean():.4f}, "
        f"mean clipped {ks['rel'].mean():.4f}, mean of non-clipped rows {ks.loc[ks['raw'] <= 3, 'rel'].mean():.4f}, "
        f"mean clip@1 {ks['raw'].clip(-1, 1).mean():.4f}, clip@2 {ks['raw'].clip(-1, 2).mean():.4f}, clip@5 {ks['raw'].clip(-1, 5).mean():.4f}")
say(f"mean raw {k['raw'].mean():.4f} clipped {k['rel'].mean():.4f}; reduction {1 - k['rel'].mean() / k['raw'].mean():.4f}")
say(f"NEXT==0 kept rows {int((k[NX] == 0).sum())} ({100 * (k[NX] == 0).mean():.4f}%)")

say("\n== b1-03 overall")
v = np.sort(k["raw"].values)
cut = int(len(v) * 0.10)
say(f"n {len(k)}, mean clipped {k['rel'].mean():.4f}, mean raw {k['raw'].mean():.4f}, median {k['raw'].median():.4f}, "
    f"10%-trim {v[cut:len(v) - cut].mean():.4f}, ratio of means {k[NX].sum() / k[PV].sum() - 1:.4f}")
say(f"downsell {(k[NX] < k[PV]).mean():.4f}, flat |raw|<5% {(k['raw'].abs() < 0.05).mean():.4f}, up >5% {(k['raw'] > 0.05).mean():.4f}, "
    f"abs median {k['d'].median():.2f}, abs mean {k['d'].mean():.2f}")
say(f"median of clipped rel {k['rel'].median():.4f}; mean of rel clipped at 1 {k['raw'].clip(-1, 1).mean():.4f}")

# ---------------------------------------------------------------- b1-04
say("\n== b1-04 structure")
say(f"origins {ct[FR].nunique()}, destinations {ct[TO].nunique()}, pairs {ct.groupby([FR, TO]).ngroups}, "
    f"from==to rows {int((ct[FR] == ct[TO]).sum())}")
say("destinations:", sorted(ct[TO].unique(), key=lambda s: int(s.split('_')[1])))
say("never origin:", sorted(set(price) - set(ct[FR])), "never destination count:", len(set(price) - set(ct[TO])))
say("tariff_8 as destination (all rows):", int((ct[TO] == "tariff_8").sum()))
cell = k.groupby([FR, "seg", TO]).size()
say(f"kept (from,seg,to) cells {len(cell)}, median n {cell.median()}, share n<15 {100 * (cell < 15).mean():.4f}%")
pr = prof.dropna(subset=["current_tariff", "arpu_segment"])
aud = pr.groupby(["current_tariff", "arpu_segment"]).agg(subs=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum"))
say(f"profile rows with NaN predicted_arpu: {int(prof['predicted_arpu'].isna().sum())}")
tot_mass = aud["mass"].sum()
aud = aud[aud["subs"] >= 20]
say(f"audience cells >=20 subs: {len(aud)}, their mass share {aud['mass'].sum() / tot_mass:.4f}")
combos = [(f, s, t, m) for (f, s), m in aud["mass"].items() for t in price if t != f]
cb = pd.DataFrame(combos, columns=["f", "s", "t", "mass"])
cb["n"] = [int(cell.get((f, s, t), 0)) for f, s, t in zip(cb.f, cb.s, cb.t)]
z, big = cb["n"] == 0, cb["n"] >= 30
say(f"combos {len(cb)}; zero {int(z.sum())} ({z.mean():.4f}; mass-w {cb.loc[z, 'mass'].sum() / cb['mass'].sum():.4f}); "
    f">=30 {int(big.sum())} ({big.mean():.4f}; mass-w {cb.loc[big, 'mass'].sum() / cb['mass'].sum():.4f})")
t21 = pr[pr["current_tariff"] == "tariff_21"]
say(f"profile tariff_21 subs {len(t21)}, mass share {100 * t21['predicted_arpu'].sum() / tot_mass:.4f}%, "
    f"history movers from tariff_21 {int((ct[FR] == 'tariff_21').sum())}")

# ---------------------------------------------------------------- b1-05 / b1-06 / b1-07 tables
def table(g):
    n = g["rel"].size()
    m = g["rel"].mean()
    se = g["rel"].std() / np.sqrt(n)
    return pd.DataFrame({"n": n, "mean": m.round(4), "lo": (m - 1.96 * se).round(4), "hi": (m + 1.96 * se).round(4),
                         "median_raw": g["raw"].median().round(4), "down": g["down"].mean().round(4),
                         "ratio_means": (g[NX].sum() / g[PV].sum() - 1).round(4)})


k["down"] = (k[NX] < k[PV]).astype(float)
pd.set_option("display.width", 200)
say("\n== b1-05 by destination")
say(table(k.groupby(TO)).sort_values("n", ascending=False).to_string())
say("\n  destination x seg mean (n):")
xs = k.groupby([TO, "seg"])["rel"].agg(["mean", "size"]).round(4)
say(xs.unstack().to_string())
say("\n== b1-06 by seg")
say(table(k.groupby("seg")).to_string())
say("\n== b1-07 dprice")
say("dprice exact ties at bucket edges:", {e: int((k["dprice"] == e).sum()) for e in (-2000, -500, 500, 2000)},
    "| dprice==0 rows:", int((k["dprice"] == 0).sum()))
k["db"] = pd.cut(k["dprice"], [-np.inf, -2000, -500, 500, 2000, np.inf])
say(table(k.groupby("db", observed=True)).to_string())
r1, r2 = k["dprice"].rank(), k["raw"].rank()
say(f"Spearman(dprice, raw) {r1.corr(r2):.4f}; Spearman(dprice, clipped) {r1.corr(k['rel'].rank()):.4f}; "
    f"Pearson(dprice, clipped) {k['dprice'].corr(k['rel']):.4f}")
X = np.c_[np.ones(len(k)), k["dprice"].values]
b = np.linalg.lstsq(X, k["d"].values, rcond=None)[0]
say(f"OLS slope abs change on dprice {b[1]:.4f}")
pf = k[FR].map(price)
say(f"median PREV/price_from (price_from>0) {(k[PV] / pf)[pf > 0].median():.4f}")
for s in ["LOW", "MID", "HIGH"]:
    ks = k[k.seg == s]
    Xs = np.c_[np.ones(len(ks)), ks["dprice"].values]
    say(f"  {s}: Spearman(dprice, raw) {ks['dprice'].rank().corr(ks['raw'].rank()):.4f}, OLS abs slope {np.linalg.lstsq(Xs, ks['d'].values, rcond=None)[0][1]:.4f}")

# ---------------------------------------------------------------- b1-08
say("\n== b1-08 regression to the mean")
k["dec"] = pd.qcut(k[PV], 10, labels=False)
dd = k.groupby("dec").agg(mean=("rel", "mean"), down=("down", "mean"))
say(f"decile0 mean {dd['mean'].iloc[0]:.4f} down {dd['down'].iloc[0]:.4f}; decile9 mean {dd['mean'].iloc[-1]:.4f} down {dd['down'].iloc[-1]:.4f}")
pn = k.groupby([FR, TO])[PV].transform("size")
w = k[pn >= 20].copy()
say(f"pairs n>=20: {w.groupby([FR, TO]).ngroups}, rows {len(w)}")
for c in (PV, NX, "rel"):
    w[c + "_c"] = w[c] - w.groupby([FR, TO])[c].transform("mean")
w["lp_c"] = np.log(w[PV]) - w.groupby([FR, TO])[PV].transform(lambda s: np.log(s).mean())
say(f"  within-pair corr(logPREV, rel) {w['lp_c'].corr(w['rel_c']):.4f}; OLS slope NEXT on PREV "
    f"{(w[PV + '_c'] * w[NX + '_c']).sum() / (w[PV + '_c'] ** 2).sum():.4f}")
# robustness: slope without the top 1% PREV rows, and log-log slope (NEXT>0)
q99 = w[PV].quantile(0.99)
ww = w[w[PV] <= q99].copy()
for c in (PV, NX):
    ww[c + "_c"] = ww[c] - ww.groupby([FR, TO])[c].transform("mean")
say(f"  robustness: slope excluding PREV>p99 ({q99:.1f}) {(ww[PV + '_c'] * ww[NX + '_c']).sum() / (ww[PV + '_c'] ** 2).sum():.4f}")
wl = w[w[NX] > 0].copy()
wl["a"] = np.log(wl[PV]) - wl.groupby([FR, TO])[PV].transform(lambda s: np.log(s).mean())
wl["b"] = np.log(wl[NX]) - wl.groupby([FR, TO])[NX].transform(lambda s: np.log(s).mean())
say(f"  log-log within-pair slope (NEXT>0, n {len(wl)}): {(wl['a'] * wl['b']).sum() / (wl['a'] ** 2).sum():.4f}")
cn = k.groupby([FR, "seg", TO])[PV].transform("size")
c10 = k[cn >= 10].copy()
med = c10.groupby([FR, "seg", TO])[PV].transform("median")
say(f"  cells n>=10: {c10.groupby([FR, 'seg', TO]).ngroups}; below/at-median mean {c10.loc[c10[PV] <= med, 'rel'].mean():.4f}, "
    f"above {c10.loc[c10[PV] > med, 'rel'].mean():.4f}")

# ---------------------------------------------------------------- b1-13..16 products
say("\n== b1-13..16 change x share")
g = k.groupby([FR, "seg", TO])["rel"].agg(n="size", mean="mean", sd="std")
N = k.groupby([FR, "seg"]).size()
g["N"] = [N[(f, s)] for f, s, _ in g.index]
g["share"] = g["n"] / g["N"]
# agent prior (K=15 chain: to -> (from,to) -> cell)
K = 15
g0 = k["rel"].mean()
d1 = k.groupby(TO)["rel"].agg(["sum", "size"])
m1 = ((d1["sum"] + K * g0) / (d1["size"] + K)).to_dict()
d2 = k.groupby([FR, TO])["rel"].agg(["sum", "size"])
m2 = {(f, t): (r["sum"] + K * m1[t]) / (r["size"] + K) for (f, t), r in d2.iterrows()}
g["m3"] = [(g.loc[i, "mean"] * g.loc[i, "n"] + K * m2[(i[0], i[2])]) / (g.loc[i, "n"] + K) for i in g.index]
g["conv"] = (g["n"] + 0.5) / (g["N"] + 0.5 * 21)
g["p_mock"] = g["mean"] * g["share"]
g["p_agent"] = g["m3"] * g["conv"]
g["lcb"] = g["mean"] - 1.96 * g["sd"] / np.sqrt(g["n"])
zz = 1.96
ph = g["share"]
den = 1 + zz * zz / g["N"]
cen = (ph + zz * zz / (2 * g["N"])) / den
hw = zz * np.sqrt(ph * (1 - ph) / g["N"] + zz * zz / (4 * g["N"] ** 2)) / den
g["p_lcb"] = np.where(g["lcb"] > 0, g["lcb"] * (cen - hw), g["lcb"] * (cen + hw))
say(f"share median {g['share'].median():.4f}, p90 {g['share'].quantile(0.9):.4f}, max {g['share'].max():.4f}; "
    f"median max-share per (from,seg) {g.groupby(level=[0, 1])['share'].max().median():.4f}")
g10 = g[g["n"] >= 10]
say(f"corr(share, mean) n>=10 cells ({len(g10)}): {g10['share'].corr(g10['mean']):.4f}; Spearman {g10['share'].rank().corr(g10['mean'].rank()):.4f}")
ga = g.join(aud, on=[FR, "seg"], how="inner")
say(f"audience triples with history {len(ga)}; p_mock>0 {int((ga.p_mock > 0).sum())}; p_agent>0 {int((ga.p_agent > 0).sum())}; "
    f"p_lcb>0 & n>=2 {int(((ga.p_lcb > 0) & (ga.n >= 2)).sum())}; p_lcb>0 any n {int((ga.p_lcb > 0).sum())}")
show = [("tariff_4", "MID", "tariff_8"), ("tariff_13", "MID", "tariff_8"), ("tariff_12", "MID", "tariff_8"),
        ("tariff_8", "LOW", "tariff_9"), ("tariff_4", "LOW", "tariff_9"), ("tariff_13", "LOW", "tariff_8"),
        ("tariff_8", "MID", "tariff_10"), ("tariff_8", "HIGH", "tariff_10"), ("tariff_11", "HIGH", "tariff_12")]
cols = ["n", "N", "share", "mean", "lcb", "m3", "p_mock", "p_agent", "p_lcb", "subs", "mass"]
say(ga.loc[show, cols].round(4).to_string())
ga["val"] = ga["p_agent"] * ga["mass"]
say("top-3 prior values:", [(i, round(v, 1)) for i, v in ga["val"].nlargest(3).items()])
say("top-5 by p_lcb (n>=10):")
say(ga[ga.n >= 10].sort_values("p_lcb", ascending=False).head(5)[cols].round(4).to_string())

# b1-14
say("\n== b1-14 best target per audience cell")
best = ga.sort_values("p_agent", ascending=False).groupby(level=[0, 1]).head(1)
mtot = aud["mass"].sum()
say(f"cells with any history {best.index.droplevel(2).nunique()} of {len(aud)}; best-by-p_agent lcb>0: {int((best.lcb > 0).sum())}, "
    f"mass share (of cells with history) {best.loc[best.lcb > 0, 'mass'].sum() / best['mass'].sum():.4f}, "
    f"of all audience mass {best.loc[best.lcb > 0, 'mass'].sum() / mtot:.4f}")
anyl = ga[ga.lcb > 0].groupby(level=[0, 1]).size()
say(f"cells with ANY target lcb>0: {len(anyl)}, mass share {aud.loc[anyl.index, 'mass'].sum() / mtot:.4f}")
anyp = ga[(ga.p_lcb > 0) & (ga.n >= 2)].groupby(level=[0, 1]).size()
say(f"cells with ANY target p_lcb>0 (n>=2): {len(anyp)}, mass share {aud.loc[anyp.index, 'mass'].sum() / mtot:.4f}")
say("big HIGH cells: mass share and best target / any lcb>0 target:")
for c in [("tariff_8", "HIGH"), ("tariff_10", "HIGH"), ("tariff_4", "HIGH"), ("tariff_11", "HIGH")]:
    sub = ga.loc[c[0]].loc[c[1]] if (c[0], c[1]) in N.index else None
    bt = sub.sort_values("p_agent", ascending=False).iloc[0]
    pos = sub[sub.lcb > 0]
    say(f"  {c}: subs {aud.loc[c, 'subs']}, mass share {aud.loc[c, 'mass'] / tot_mass:.4f}, best {bt.name} p_agent {bt.p_agent:.4f} "
        f"lcb {bt.lcb:.4f}; targets with lcb>0: {[(t, round(r.lcb, 4), int(r.n)) for t, r in pos.iterrows()]}")
say("tariff_8 HIGH seen targets p_mock:", ga.loc[("tariff_8", "HIGH")]["p_mock"].round(4).to_dict())
say("tariff_11 HIGH -> tariff_12:", ga.loc[("tariff_11", "HIGH", "tariff_12"), ["mean", "p_lcb"]].round(4).to_dict())

# b1-15 unseen
say("\n== b1-15 unseen combos (MOCK fallback)")
medp = max(float(np.median(list(price.values()))), 1.0)
fbconv = float(g["share"].median())
un = cb[cb.n == 0].copy()
un["fb_chg"] = np.clip(0.4 * (un.t.map(price) - un.f.map(price)) / medp, -1, 3)
un["fb_prod"] = un["fb_chg"] * fbconv
conv_med = float(g["conv"].median())
un["mu0"] = [m2.get((f, t), m1.get(t, g0)) * (0.5 / (N[(f, s)] + 10.5) if (f, s) in N.index else conv_med)
             for f, s, t in zip(un.f, un.s, un.t)]
say(f"unseen {len(un)}; median price {medp:.1f}; fallback conv {fbconv:.4f}; fb_prod>0 {int((un.fb_prod > 0).sum())}, max {un.fb_prod.max():.4f}; "
    f"agent mu0 median {un.mu0.median():.4f} max {un.mu0.max():.4f}")
bs = ga.groupby(level=[0, 1])["p_mock"].max()
bu = un.groupby(["f", "s"])["fb_prod"].max()
say(f"cells where best unseen fb_prod > best seen p_mock: {int((bu > bs.reindex(bu.index).fillna(-np.inf)).sum())} of {len(bu)}")
say("tariff_8 HIGH unseen fb_prod top:", un[(un.f == "tariff_8") & (un.s == "HIGH")].nlargest(3, "fb_prod")[["t", "fb_prod"]].round(4).values.tolist())
# detectability of such effects by one sms pilot of 200 (env noise 0.804/sqrt(n), observed = product x 0.65)
se = 0.804 / math.sqrt(200)
mde = 2 * se / 0.65
say(f"sms n=200 pilot: se of observed {se:.4f}; product needed for z=2 {mde:.4f}; fb_prod >= that: {int((un.fb_prod >= mde).sum())}; "
    f"z of tariff_8 HIGH->tariff_14 at n=200: {0.65 * un.loc[(un.f == 'tariff_8') & (un.s == 'HIGH') & (un.t == 'tariff_14'), 'fb_prod'].iloc[0] / se:.3f}")
say(f"audience triples with |p_agent| >= {mde:.4f}: {int((ga.p_agent.abs() >= mde).sum())} of {len(ga)}; with p_mock >= it: {int((ga.p_mock >= mde).sum())}")

# ---------------------------------------------------------------- caveat: profile vs history LOW
say("\n== caveats")
ok = prof["arpu_segment"].notna()
say(f"profile arpu_segment mismatches vs right-closed cut: {int((seg_of(prof.loc[ok, 'ARPU_3m_avg'].values) != prof.loc[ok, 'arpu_segment'].values).sum())} of {int(ok.sum())}")
hl = k[k.seg == "LOW"]
say(f"profile LOW median ARPU_3m_avg {low_p['ARPU_3m_avg'].median():.2f}; share <300 {(low_p['ARPU_3m_avg'] < 300).mean():.4f}; "
    f"history kept LOW share PREV<300 {(hl[PV] < 300).mean():.4f}")

say("\n== extra: clip dependence of the 'robust' triples")
for c in [("tariff_8", "LOW", "tariff_9"), ("tariff_4", "LOW", "tariff_9"), ("tariff_13", "LOW", "tariff_8"), ("tariff_4", "MID", "tariff_8")]:
    x = k[(k[FR] == c[0]) & (k.seg == c[1]) & (k[TO] == c[2])]
    say(f"  {c}: n {len(x)}, share raw>3 {(x['raw'] > 3).mean():.4f}, mean clip3 {x['rel'].mean():.4f}, clip1 {x['raw'].clip(-1, 1).mean():.4f}, "
        f"median {x['raw'].median():.4f}, downsell {(x[NX] < x[PV]).mean():.4f}")
say("HIGH-segment movers: destinations with mean>0:", xs["mean"].xs("HIGH", level=1)[xs["mean"].xs("HIGH", level=1) > 0].to_dict(),
    "| HIGH -> tariff_9 n", int(xs["size"][("tariff_9", "HIGH")]))
say(f"prior products of the 4 big HIGH cells vs sms-200 z=2 threshold {mde:.4f}: ratio threshold/best p_agent "
    f"tariff_8 HIGH {mde / ga.loc[('tariff_8', 'HIGH')]['p_agent'].max():.1f}x, tariff_11 HIGH {mde / ga.loc[('tariff_11', 'HIGH')]['p_agent'].max():.1f}x")
ga["se_prod"] = ga["sd"] / np.sqrt(ga["n"]) * ga["conv"]
say("history sampling se of the product (sd/sqrt(n) x conv), audience triples n>=2, by seg (median, max):",
    {s: (round(float(x.median()), 4), round(float(x.max()), 4)) for s, x in ga[ga.n >= 2].groupby(level=1)["se_prod"]}, "vs agent PRIOR_SD 0.30")
say(f"z of one sms n=200 pilot if truth = prior 0.2318 (tariff_4 MID->tariff_8): {0.65 * 0.2318 / se:.2f}")
