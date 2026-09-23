"""d1v: adversarial re-derivation of d1_economics claims from raw data + public modules.

Deterministic. Run: python3 analysis/d1v_verify.py
"""
import math
import os
import re
import sys

sys.dont_write_bytecode = True
import numpy as np
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, P)
import scoring_core as sc  # noqa: E402  (constants only)
import environment as envmod  # noqa: E402

CH = ["push", "sms", "digital_ads", "call"]
COST = {c: sc.CHANNELS[c]["cost_per_contact"] for c in CH}
MULT = {c: sc.CHANNELS[c]["conversion_multiplier"] for c in CH}
B, R = sc.TOTAL_BUDGET, sc.MAX_TOTAL_CONTACTS
SD = envmod.PER_CUSTOMER_STD


def Phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def Phi_inv(p):  # Newton on erf
    x = 0.0
    for _ in range(100):
        x -= (Phi(x) - p) / (math.exp(-x * x / 2) / math.sqrt(2 * math.pi))
    return x


def spearman(a, b):
    return pd.Series(np.asarray(a, float)).rank().corr(pd.Series(np.asarray(b, float)).rank())


dt = pd.read_csv(os.path.join(P, "data", "dict_tariff.csv"))
td = pd.read_csv(os.path.join(P, "tariff_dictionary.csv"))
prof = pd.read_csv(os.path.join(P, "customer_profile.csv"))
ct = pd.read_csv(os.path.join(P, "data", "change_tariff.csv"))
pa = prof["predicted_arpu"]
MASS = pa.sum()
print(f"constants cost={COST} mult={MULT} B={B} R={R} SD={SD}")

# ============================================================ 1 catalogue
print("\n=== 1 CATALOGUE ===")
num = ["Data_in_PKG", "Min_another_operator_in_PKG", "Min_another_operator_and_city_in_PKG", "price_tariff"]
a_ = dt.set_index("tariff_plan_code").sort_index()
b_ = td.set_index("tariff_plan_code").sort_index()
print("rows", len(dt), len(td), "same codes", set(a_.index) == set(b_.index),
      "numeric mismatches", int((a_[num] != b_.loc[a_.index, num]).to_numpy().sum()))
bad = {"price": 0, "mb": 0, "min": 0}
for code, row in b_.iterrows():
    d = row["description"]
    pr = float(d.split(" ")[0].replace(",", ""))
    mb = re.search(r"([\d,]+)\s*МБ", d)
    mb = float(mb.group(1).replace(",", "")) if mb else 0.0
    mn = sum(float(x) for x in re.findall(r"(\d+)\s*мин", d))
    bad["price"] += abs(pr - row.price_tariff) > 1e-9
    bad["mb"] += mb != row.Data_in_PKG
    bad["min"] += mn != row.Min_another_operator_in_PKG + row.Min_another_operator_and_city_in_PKG
print("description mismatches", bad)

price = a_["price_tariff"]
medp = float(price.median())
print(f"price min={price.min()} median={medp} mean={price.mean():.2f} max={price.max()}")
a_["mins"] = a_.Min_another_operator_in_PKG + a_.Min_another_operator_and_city_in_PKG
dups = a_.reset_index().groupby(num)["tariff_plan_code"].apply(list)
print("identical products:", [g for g in dups if len(g) > 1])
print("shared price:", [g for g in a_.reset_index().groupby("price_tariff")["tariff_plan_code"].apply(list) if len(g) > 1])

h = ct[ct.AVG_ARPU_PREV_3M >= 100].copy()
h["pct"] = ((h.AVG_ARPU_NEXT_3M - h.AVG_ARPU_PREV_3M) / h.AVG_ARPU_PREV_3M).clip(-1, 3)
print(f"history rows raw={len(ct)} PREV>=100={len(h)}; from==to rows raw={(ct.tariff_plan_code_from == ct.tariff_plan_code_to).sum()}")
for t in ["tariff_5", "tariff_6", "tariff_7", "tariff_8", "tariff_9", "tariff_21", "tariff_1"]:
    s = h.loc[h.tariff_plan_code_to == t, "pct"]
    print(f"  to {t}: raw n={(ct.tariff_plan_code_to == t).sum()} PREV>=100 n={len(s)} mean={s.mean():+.4f}")
never_to = sorted(set(a_.index) - set(ct.tariff_plan_code_to), key=lambda s: int(s[7:]))
never_from = sorted(set(a_.index) - set(ct.tariff_plan_code_from), key=lambda s: int(s[7:]))
print(f"never target: {len(never_to)} {never_to}; never source: {never_from}")

# does price change explain history effects? (d1-04 'no product/price logic')
h["dprice"] = h.tariff_plan_code_to.map(price) - h.tariff_plan_code_from.map(price)
h["dprice_rel"] = h["dprice"] / h.tariff_plan_code_from.map(price).replace(0, np.nan)
print(f"row-level Pearson(pct, dprice)={h.pct.corr(h.dprice):.4f} Spearman={spearman(h.pct, h.dprice):.4f}")
print("  mean pct by sign of price change:",
      h.groupby(np.sign(h.dprice))["pct"].agg(["size", "mean"]).round(4).to_dict("index"))
pairs = h.groupby(["tariff_plan_code_from", "tariff_plan_code_to"]).agg(n=("pct", "size"), m=("pct", "mean"),
                                                                        dp=("dprice", "first"))
pairs20 = pairs[pairs.n >= 20]
print(f"  (from,to) pairs n>=20: {len(pairs20)}; Spearman(mean pct, dprice)={spearman(pairs20.m, pairs20.dp):.4f}")
for t in ["tariff_9", "tariff_21"]:
    sub = h[h.tariff_plan_code_to == t]
    print(f"  into {t}: mean dprice={sub.dprice.mean():+.1f}; share from cheaper tariff={(sub.dprice > 0).mean():.4f}; "
          f"top sources={sub.tariff_plan_code_from.value_counts().head(4).to_dict()}")

# Pareto dominance (independent vectorised)
X = a_[["price_tariff", "Data_in_PKG", "mins"]].to_numpy()
codes = a_.index.to_numpy()
dom = {}
for i in range(len(X)):
    ge = (X[:, 0] <= X[i, 0]) & (X[:, 1] >= X[i, 1]) & (X[:, 2] >= X[i, 2])
    st = (X[:, 0] < X[i, 0]) | (X[:, 1] > X[i, 1]) | (X[:, 2] > X[i, 2])
    by = [codes[j] for j in np.where(ge & st)[0] if j != i]
    if by:
        dom[codes[i]] = by
print(f"Pareto-dominated: {len(dom)}")
for k in ["tariff_4", "tariff_8", "tariff_10", "tariff_11", "tariff_14"]:
    print(f"  {k} dominated by {dom.get(k)}")
print(f"  tariff_14 dominator count={len(dom.get('tariff_14', []))}")

# profile per tariff
pc = prof.groupby("current_tariff").agg(n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum"),
                                        avg=("predicted_arpu", "mean"))
print(f"distinct current tariffs in profile={len(pc)}; with n>=20: {(pc.n >= 20).sum()}; "
      f"smallest={pc.n.sort_values().head(3).to_dict()}")
print(f"tariff_8: n={pc.loc['tariff_8', 'n']} mass share={100 * pc.loc['tariff_8', 'mass'] / MASS:.2f}%")
pcp = pc.join(price)
print(f"Spearman(price, mean predicted_arpu) all current tariffs={spearman(pcp.price_tariff, pcp.avg):.4f}; "
      f"n>=20 only={spearman(pcp[pcp.n >= 20].price_tariff, pcp[pcp.n >= 20].avg):.4f}")

t1 = prof[prof.current_tariff == "tariff_1"]
print(f"tariff_1: n={len(t1)} segs={t1.arpu_segment.value_counts().to_dict()} mass share="
      f"{100 * t1.predicted_arpu.sum() / MASS:.2f}% median pred={t1.predicted_arpu.median():.1f}")
print(f"  mock fallback median->tariff_1 {0.4 * (0 - medp) / medp:+.3f}; tariff_1->tariff_12 {0.4 * price['tariff_12'] / medp:+.3f}")

top7 = pc.sort_values("n", ascending=False).head(7)
print(f"top7 by n: share subs={100 * top7.n.sum() / len(prof):.2f}% mass={100 * top7.mass.sum() / MASS:.2f}%")
for t, r_ in top7.iterrows():
    p0 = price[t]
    up = price[price > p0].sort_values()
    print(f"  {t}: n={r_.n} mass={100 * r_.mass / MASS:.2f}% up/same/down={len(up)}/{(price == p0).sum() - 1}/"
          f"{(price < p0).sum()} cheapest_up={(up.index[0] + f' +{100 * (up.iloc[0] / p0 - 1):.1f}%') if len(up) else '-'}")
cellmass = prof.groupby(["current_tariff", "arpu_segment"])["predicted_arpu"].agg(["size", "sum"])
hi3 = cellmass.loc[[(t, "HIGH") for t in ["tariff_10", "tariff_11", "tariff_12"]]]
print(f"HIGH cells of tariff_10/11/12: n={hi3['size'].tolist()} mass share each="
      f"{(100 * hi3['sum'] / MASS).round(2).tolist()} total={100 * hi3['sum'].sum() / MASS:.2f}%; "
      f"whole tariffs 10/11/12 total={100 * pc.loc[['tariff_10', 'tariff_11', 'tariff_12'], 'mass'].sum() / MASS:.2f}%")
big_cell = cellmass["size"].idxmax()
print(f"largest cell {big_cell} n={cellmass['size'].max()}")

# ============================================================ 2 channels
print("\n=== 2 CHANNELS ===")
q = pa.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
segmed = prof.groupby("arpu_segment")["predicted_arpu"].median()
levels = {**{f"q{int(k * 100)}": v for k, v in q.items()}, **{f"{s}_med": segmed[s] for s in ["LOW", "MID", "HIGH"]}}
for name, a in levels.items():
    print(f"  {name}={a:.1f} r*: " + " ".join(f"{c}={COST[c] / (MULT[c] * a):.5f}" for c in CH[1:]))
for lo, hi in [("push", "sms"), ("sms", "digital_ads"), ("digital_ads", "call")]:
    K = (COST[hi] - COST[lo]) / (MULT[hi] - MULT[lo])
    print(f"  {lo}->{hi}: K={K:.2f} r_inc@median={K / levels['q50']:.5f} @LOW={K / levels['LOW_med']:.5f} "
          f"dmult/dcost={1 / K:.5f}")
print(f"  ratio sms->ads vs ads->call money efficiency={(0.2 / 18) / (0.35 / 138):.4f}")
for c in CH:
    cap = R if COST[c] == 0 else min(R, B // COST[c])
    print(f"  capacity {c}: {cap} money={cap * COST[c]}")

# mock conversion recomputed from raw
m = ct.copy()
m["seg"] = pd.cut(m.AVG_ARPU_PREV_3M, [-np.inf, 1000, 5000, np.inf], labels=["LOW", "MID", "HIGH"]).astype(str)
m = m[m.AVG_ARPU_PREV_3M >= 100].copy()
m["pct"] = ((m.AVG_ARPU_NEXT_3M - m.AVG_ARPU_PREV_3M) / m.AVG_ARPU_PREV_3M).clip(-1, 3)
mm = m.groupby(["tariff_plan_code_from", "seg", "tariff_plan_code_to"]).agg(pct=("pct", "mean"), cnt=("pct", "size")).reset_index()
mm["conv"] = mm.cnt / mm.groupby(["tariff_plan_code_from", "seg"]).cnt.transform("sum")
from mock_environment import _mock_impact_model  # noqa: E402  (cross-check only)
mref = _mock_impact_model(ct)
print(f"mock rows mine={len(mm)} module={len(mref)}; conv>1/1.2: {(mm.conv > 1 / 1.2).sum()}; max conv={mm.conv.max():.4f}; "
      f"quantiles 50/90/99={mm.conv.quantile([.5, .9, .99]).round(4).tolist()}; module median={mref.conversion_rate.median():.4f}")
nt = mm.groupby(["tariff_plan_code_from", "seg"]).size()
print(f"  (from,seg) groups={len(nt)}; with a single target={int((nt == 1).sum())}")

# ============================================================ 3 reach vs money
print("\n=== 3 REACH VS MONEY ===")
a_sorted = np.sort(pa.to_numpy())[::-1]
S = np.concatenate([[0.0], np.cumsum(a_sorted)])


def opt(r, budget=B, reach=R):
    """Exhaustive over (calls c, ads a); sms count s is then optimal in closed form; push fills the rest."""
    N = min(reach, len(a_sorted))
    cmax = int(min(budget // 160, N))
    c = np.arange(cmax + 1)[:, None]
    a = np.arange(int(min(budget // 22, N)) + 1)[None, :]
    money = budget - 160 * c - 22 * a
    ok = (money >= 0) & (c + a <= N)
    n_ok = int((a_sorted > 4 / (0.15 * r)).sum()) if r > 0 else 0
    s = np.clip(np.minimum(np.minimum(money // 4, N - c - a), n_ok - c - a), 0, None)
    s = np.where(ok, s, 0)
    ca, cas = np.where(ok, c + a, 0), np.where(ok, c + a + s, 0)
    val = r * (1.2 * S[np.broadcast_to(c, ca.shape)] + 0.85 * (S[ca] - S[np.broadcast_to(c, ca.shape)])
               + 0.65 * (S[cas] - S[ca]) + 0.5 * (S[N] - S[cas])) - 160 * c - 22 * a - 4 * s
    val = np.where(ok, val, -np.inf)
    k = np.unravel_index(int(np.argmax(val)), val.shape)
    ci, ai = int(k[0]), int(k[1])
    si = int(s[k])
    return dict(net=float(val[k]), call=ci, ads=ai, sms=si, push=N - ci - ai - si, money=160 * ci + 22 * ai + 4 * si)


shadow = {}
for r in [0.02, 0.05, 0.1, 0.2, 0.3, 0.45]:
    o = opt(r)
    rho = (opt(r, reach=R + 100)["net"] - o["net"]) / 100
    lam = (opt(r, budget=B + 1000)["net"] - o["net"]) / 1000
    rho1 = opt(r, reach=R + 1)["net"] - o["net"]
    lam1 = (opt(r, budget=B + 22)["net"] - o["net"]) / 22
    shadow[r] = (rho, lam)
    push_only = r * 0.5 * S[R]
    sms_only = r * 0.65 * S[R] - 4 * R
    print(f"r={r}: mix c/a/s/p={o['call']}/{o['ads']}/{o['sms']}/{o['push']} money={o['money']} net={o['net']:,.0f} "
          f"rho={rho:.2f} lam={lam:.4f} (rho+1={rho1:.2f} lam+22={lam1:.4f}) gain vs push={100 * (o['net'] / push_only - 1):.2f}% "
          f"all-sms real top15000={sms_only:,.0f} mix gain vs all-sms={100 * (o['net'] / sms_only - 1):.2f}%")

amed = float(pa.median())
print(f"median pred={amed:.1f}; per-contact net at r=0.1: " +
      " ".join(f"{c}={0.1 * MULT[c] * amed - COST[c]:.1f}" for c in CH) +
      f"; homogeneous-median all-sms total={(0.1 * 0.65 * amed - 4) * R:,.0f}")
print(f"top-15000 mean pred={a_sorted[:R].mean():.1f} vs median {amed:.1f}; rank2222 pred={a_sorted[2221]:.1f} "
      f"x4.381={4.3810 * a_sorted[2221]:.1f}; subs above={(a_sorted >= (0.2 / 18) / (0.35 / 138) * a_sorted[2221]).sum()}; "
      f"max={a_sorted[0]:.1f} second={a_sorted[1]:.1f}")
for pool in [1000, 2500, 5000, 7500, 10000, 15000]:
    o = opt(0.1, reach=pool)
    rho = (opt(0.1, reach=pool + 100)["net"] - o["net"]) / 100
    lam = (opt(0.1, reach=pool, budget=B + 1000)["net"] - o["net"]) / 1000
    print(f"  pool={pool}: c/a/s/p={o['call']}/{o['ads']}/{o['sms']}/{o['push']} money={o['money']} net={o['net']:,.0f} "
          f"rho={rho:.2f} lam={lam:.4f}")
for label, ch, npil in [("20x200 sms", "sms", 4000), ("3750 sms", "sms", 3750), ("20x200 push", "push", 4000),
                        ("10x200 ads", "digital_ads", 2000)]:
    out = []
    info = npil * (MULT[ch] / 0.65) ** 2
    for r in [0.02, 0.1, 0.2]:
        loss = 100 * (1 - opt(r, budget=B - npil * COST[ch], reach=R - npil)["net"] / opt(r)["net"])
        out.append(f"r={r}: -{loss:.2f}% ({1000 * loss / info:.3f}%/1000 sms-eq)")
    print(f"  pilot cost {label}: " + "; ".join(out))

# ============================================================ 4 pilots
print("\n=== 4 PILOTS ===")
for e in [0.02, 0.05, 0.1, 0.2, 0.3, 0.45]:
    print(f"  e={e}: " + " ".join(f"n{n}={Phi(-e * math.sqrt(n) / SD):.4f}" for n in [10, 30, 60, 100, 150, 200]))
e30 = -Phi_inv(0.25) * SD / math.sqrt(30)
p200 = Phi(-e30 * math.sqrt(200) / SD)
print(f"brief: e30={e30:.4f} P@200={p200:.4f} (1 in {1 / p200:.1f}) base via sms={e30 / 0.65:.4f} push={e30 / 0.5:.4f}")
for c in CH:
    print(f"  {c}: SE200 base={SD / (MULT[c] * math.sqrt(200)):.4f} info vs sms={(MULT[c] / 0.65) ** 2:.4f} "
          f"20x200 money={4000 * COST[c]}")
for r, (rho, lam) in shadow.items():
    v = {c: MULT[c] ** 2 / (rho + COST[c] * lam) for c in CH}
    print(f"  info/shadow r={r}: ads/sms={v['digital_ads'] / v['sms']:.3f} push/sms={v['push'] / v['sms']:.3f} "
          f"call/sms={v['call'] / v['sms']:.3f}")
za, zb = Phi_inv(0.95), Phi_inv(0.8)
print(f"z={za:.4f},{zb:.4f}")
for d in [0.1, 0.05, 0.02]:
    print(f"  delta={d}: n/arm={math.ceil(2 * (SD * (za + zb) / d) ** 2)}")
print(f"  MDE n=200 two-arm={(za + zb) * SD * math.sqrt(2 / 200):.4f} one={(za + zb) * SD / math.sqrt(200):.4f} "
      f"base sms={(za + zb) * SD * math.sqrt(2 / 200) / 0.65:.4f}")

# ============================================================ 5 caps
print("\n=== 5 CAPS ===")
cells = prof.groupby(["current_tariff", "arpu_segment"]).agg(n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum"))
cells = cells.sort_values("mass", ascending=False)
cells["cm"] = 100 * cells.mass.cumsum() / MASS
print(f"cells={len(cells)} n>=20={int((cells.n >= 20).sum())} mass>=20={100 * cells[cells.n >= 20].mass.sum() / MASS:.2f}% "
      f"max n={cells.n.max()} >5000={int((cells.n > 5000).sum())}")
print(cells.head(9).round(2).to_string())
print(f"top3 mass={cells.cm.iloc[2]:.2f}% n={cells.n.iloc[:3].sum()}; cells to 80%={int((cells.cm < 80).sum()) + 1}")
cn = cells.n.cumsum()
k = int((cn < R).sum()) + 1
covered = cells.mass.iloc[:k - 1].sum() + (R - cn.iloc[k - 2]) * cells.mass.iloc[k - 1] / cells.n.iloc[k - 1]
print(f"cells to fill {R}: {k}; mass covered={100 * covered / MASS:.2f}%")
print(f"Spearman(ID, pred)={spearman(prof.ID_NUMBER, pa):.4f}")
f5 = prof.sort_values("ID_NUMBER").head(5000)
print(f"first5000 mass={100 * f5.predicted_arpu.sum() / MASS:.2f}% proportional={100 * 5000 / len(prof):.2f}%")
hs = prof[prof.arpu_segment == "HIGH"].sort_values("ID_NUMBER")
print(f"HIGH n={len(hs)} first5000 mass share={100 * hs.head(5000).predicted_arpu.sum() / hs.predicted_arpu.sum():.2f}% "
      f"count share={100 * 5000 / len(hs):.2f}%")
print(f"missing tariff={prof.current_tariff.isna().sum()} seg={prof.arpu_segment.isna().sum()} "
      f"pred==0: {(pa == 0).sum()} neg={(pa < 0).sum()} max={pa.max():.1f}")
z0 = prof[pa == 0]
print(f"  zero-pred rows: missing tariff among them={z0.current_tariff.isna().sum()}; segs={z0.arpu_segment.value_counts(dropna=False).to_dict()}; "
      f"top tariffs={z0.current_tariff.value_counts().head(3).to_dict()}")
mt = prof[prof.current_tariff.isna()]
print(f"  missing-tariff rows: pred==0 among them={(mt.predicted_arpu == 0).sum()}; segs={mt.arpu_segment.value_counts(dropna=False).to_dict()}; "
      f"mass share={100 * mt.predicted_arpu.sum() / MASS:.3f}%")
out = prof.loc[pa.idxmax()]
cell_out = prof[(prof.current_tariff == out.current_tariff) & (prof.arpu_segment == out.arpu_segment)]
print(f"  outlier cell={out.current_tariff}/{out.arpu_segment}/{out.data_segment}/{out.call_segment} "
      f"cell n={len(cell_out)}; its share of cell mass={100 * out.predicted_arpu / cell_out.predicted_arpu.sum():.2f}%")
