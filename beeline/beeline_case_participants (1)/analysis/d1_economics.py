"""d1: tariff catalogue, channel economics, reach vs money, pilot statistics, campaign caps.

Deterministic (no randomness). Constants are imported from scoring_core / environment.
Run: python3 analysis/d1_economics.py
"""
import math
import os
import sys

sys.dont_write_bytecode = True   # do not touch __pycache__ of the read-only modules
import numpy as np
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, P)
from scoring_core import CHANNELS, TOTAL_BUDGET, MAX_TOTAL_CONTACTS, MAX_CAMPAIGNS, MAX_CUSTOMERS_PER_CAMPAIGN  # noqa: E402
from environment import PER_CUSTOMER_STD, MAX_PILOTS, MAX_PILOT_CUSTOMERS, MIN_PILOT_CUSTOMERS  # noqa: E402
from mock_environment import _mock_impact_model  # noqa: E402

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_rows", 200)
pd.set_option("display.max_colwidth", 120)

CH = list(CHANNELS)
COST = {c: CHANNELS[c]["cost_per_contact"] for c in CH}
MULT = {c: CHANNELS[c]["conversion_multiplier"] for c in CH}
B, R = TOTAL_BUDGET, MAX_TOTAL_CONTACTS


def Phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def Phi_inv(p):
    lo, hi = -12.0, 12.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if Phi(mid) < p else (lo, mid)
    return (lo + hi) / 2


dt = pd.read_csv(os.path.join(P, "data", "dict_tariff.csv"))
td = pd.read_csv(os.path.join(P, "tariff_dictionary.csv"))
prof = pd.read_csv(os.path.join(P, "customer_profile.csv"))
ct = pd.read_csv(os.path.join(P, "data", "change_tariff.csv"))

print("constants: CHANNELS", CHANNELS)
print(f"constants: TOTAL_BUDGET={B} MAX_TOTAL_CONTACTS={R} MAX_CAMPAIGNS={MAX_CAMPAIGNS} "
      f"MAX_CUSTOMERS_PER_CAMPAIGN={MAX_CUSTOMERS_PER_CAMPAIGN}")
print(f"constants: PER_CUSTOMER_STD={PER_CUSTOMER_STD} MAX_PILOTS={MAX_PILOTS} "
      f"pilot n in [{MIN_PILOT_CUSTOMERS},{MAX_PILOT_CUSTOMERS}]")

# ======================================================================= 1. catalogue
print("\n=== 1. TARIFF CATALOGUE ===")
num = ["Data_in_PKG", "Min_another_operator_in_PKG", "Min_another_operator_and_city_in_PKG", "price_tariff"]
print(f"rows: dict_tariff={len(dt)} tariff_dictionary={len(td)}; "
      f"same code set={set(dt.tariff_plan_code) == set(td.tariff_plan_code)}")
m = dt.merge(td, on="tariff_plan_code", suffixes=("", "_td"))
print("numeric column mismatches:", sum(int((m[c] != m[c + "_td"]).sum()) for c in num))
desc_price = m["description"].map(lambda s: float(s.split("—")[0].strip().replace(",", "")))
desc_mb = m["description"].str.extract(r"([\d,]+) МБ")[0].str.replace(",", "").astype(float).fillna(0)
desc_min = m["description"].str.extract(r"(\d+) мин")[0].astype(float).fillna(0)
tot_min = m["Min_another_operator_in_PKG"] + m["Min_another_operator_and_city_in_PKG"]
print("description vs numbers mismatches: price", int((abs(desc_price - m.price_tariff) > 1e-9).sum()),
      "MB", int((desc_mb != m.Data_in_PKG).sum()), "minutes", int((desc_min != tot_min).sum()))

dt["minutes"] = dt["Min_another_operator_in_PKG"] + dt["Min_another_operator_and_city_in_PKG"]
price = dt.set_index("tariff_plan_code")["price_tariff"]
med_price = float(price.median())
print(f"price: min={price.min()} median={med_price} mean={price.mean():.1f} max={price.max()}")

pc = prof.groupby("current_tariff").agg(n_profile=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum"))
hist = ct[ct["AVG_ARPU_PREV_3M"] >= 100].copy()
hist["pct"] = ((hist["AVG_ARPU_NEXT_3M"] - hist["AVG_ARPU_PREV_3M"]) / hist["AVG_ARPU_PREV_3M"]).clip(-1, 3)
to_stats = hist.groupby("tariff_plan_code_to")["pct"].agg(n_hist_to="size", mean_pct_to="mean")
from_n = ct.groupby("tariff_plan_code_from").size().rename("n_hist_from")
lad = (dt.set_index("tariff_plan_code")[["price_tariff", "Data_in_PKG", "minutes"]]
       .join(pc).join(to_stats).join(from_n).reset_index()
       .sort_values(["price_tariff", "tariff_plan_code"]).reset_index(drop=True))
lad[["n_profile", "mass", "n_hist_to", "n_hist_from"]] = lad[["n_profile", "mass", "n_hist_to", "n_hist_from"]].fillna(0)
lad["mass_share_pct"] = 100 * lad["mass"] / prof["predicted_arpu"].sum()
lad["fallback_pct_from_median"] = 0.4 * (lad["price_tariff"] - med_price) / med_price
print("price ladder (profile n/mass, history PREV>=100 mean clipped pct as target):")
print(lad.drop(columns="mass").round(4).to_string())

never_to = sorted(set(dt.tariff_plan_code) - set(ct.tariff_plan_code_to), key=lambda t: int(t.split("_")[1]))
print(f"tariffs never a target in history (raw change_tariff): {len(never_to)} -> {never_to}")
print(f"tariffs never a source in history: {sorted(set(dt.tariff_plan_code) - set(ct.tariff_plan_code_from))}")
big = lad[lad.n_profile >= 20]
print(f"across current tariffs with n>=20 ({len(big)}): Spearman(price, mean predicted_arpu)="
      f"{big.price_tariff.rank().corr((big.mass / big.n_profile).rank()):.4f}")

grp = dt.groupby(num)["tariff_plan_code"].apply(list)
print("exact duplicate products (same price and packages):", [g for g in grp if len(g) > 1])
same_price = dt.groupby("price_tariff")["tariff_plan_code"].apply(list)
print("same price, any packages:", {p: g for p, g in same_price.items() if len(g) > 1})
for t in ["tariff_5", "tariff_6", "tariff_7", "tariff_8"]:
    s = hist[hist.tariff_plan_code_to == t]["pct"]
    print(f"  history as target {t}: n={len(s)} mean clipped pct={s.mean():+.4f} median={s.median():+.4f}; "
          f"profile n on it={int(pc['n_profile'].get(t, 0))}")

dominated = []
for _, a in dt.iterrows():
    for _, b in dt.iterrows():
        if a.tariff_plan_code == b.tariff_plan_code:
            continue
        ge = b.price_tariff <= a.price_tariff and b.Data_in_PKG >= a.Data_in_PKG and b.minutes >= a.minutes
        strict = b.price_tariff < a.price_tariff or b.Data_in_PKG > a.Data_in_PKG or b.minutes > a.minutes
        if ge and strict:
            dominated.append((a.tariff_plan_code, b.tariff_plan_code))
dom = pd.DataFrame(dominated, columns=["dominated", "by"]).groupby("dominated")["by"].apply(list)
print(f"Pareto-dominated tariffs (price<=, data>=, minutes>=, one strict): {len(dom)}")
print(dom.to_string())

t1 = prof[prof.current_tariff == "tariff_1"]
print(f"tariff_1 (price 0, no packages): profile n={len(t1)} "
      f"median ARPU_3m_avg={t1.ARPU_3m_avg.median():.1f} median predicted_arpu={t1.predicted_arpu.median():.1f} "
      f"mass share={100 * t1.predicted_arpu.sum() / prof.predicted_arpu.sum():.2f}%")
print("  tariff_1 arpu_segment counts:", t1.arpu_segment.value_counts(dropna=False).to_dict())
print(f"  history: from tariff_1 n={int((ct.tariff_plan_code_from == 'tariff_1').sum())}, "
      f"to tariff_1 n={int((ct.tariff_plan_code_to == 'tariff_1').sum())}, "
      f"to tariff_1 with PREV>=100 mean clipped pct="
      f"{hist[hist.tariff_plan_code_to == 'tariff_1']['pct'].mean():+.4f}")
print(f"  mock fallback into tariff_1 from the median-price tariff = {0.4 * (0 - med_price) / med_price:+.3f}; "
      f"from tariff_1 to tariff_12 = {0.4 * (price['tariff_12'] - 0) / med_price:+.3f}")

print("upsell/lateral/downsell targets by price for the 7 largest current tariffs:")
top7 = pc.sort_values("n_profile", ascending=False).head(7)
rows = []
for t, r_ in top7.iterrows():
    p0 = price[t]
    up = price[price > p0].sort_values()
    rows.append(dict(tariff=t, n=int(r_.n_profile), mass_share_pct=round(100 * r_.mass / prof.predicted_arpu.sum(), 2),
                     price=p0, n_up=len(up), n_same=int((price == p0).sum()) - 1, n_down=int((price < p0).sum()),
                     cheapest_up=f"{up.index[0]} (+{100 * (up.iloc[0] / p0 - 1):.1f}%)" if len(up) else "-",
                     upsells=",".join(up.index.str.replace("tariff_", "t"))))
print(pd.DataFrame(rows).to_string(index=False))
print(f"top-7 tariffs hold {100 * top7.n_profile.sum() / len(prof):.2f}% of subscribers and "
      f"{100 * top7.mass.sum() / prof.predicted_arpu.sum():.2f}% of predicted_arpu mass")

# ======================================================================= 2. channels
print("\n=== 2. CHANNEL ECONOMICS ===")
pa = prof["predicted_arpu"]
print(f"predicted_arpu: n={pa.notna().sum()} missing={int(pa.isna().sum())} <=0: {int((pa <= 0).sum())} "
      f"sum={pa.sum():,.0f} mean={pa.mean():.1f}")
qs = [0.10, 0.25, 0.50, 0.75, 0.90]
qv = pa.quantile(qs)
levels = [(f"q{int(q * 100)}", float(v)) for q, v in qv.items()]
segmed = prof.groupby("arpu_segment")["predicted_arpu"].agg(["size", "median", "sum"])
segmed["mass_share_pct"] = 100 * segmed["sum"] / pa.sum()
print("per arpu_segment:\n", segmed.round(2).to_string())
levels += [(f"{s}_median", float(segmed.loc[s, "median"])) for s in ["LOW", "MID", "HIGH"]]
print("break-even base lift ratio r* = cost / (multiplier x predicted_arpu):")
be_rows = []
for name, a in levels:
    row = dict(level=name, predicted_arpu=round(a, 1))
    for c in CH:
        row[c] = round(COST[c] / (MULT[c] * a), 5)
    be_rows.append(row)
print(pd.DataFrame(be_rows).to_string(index=False))

pairs = [("push", "sms"), ("sms", "digital_ads"), ("digital_ads", "call"),
         ("push", "digital_ads"), ("sms", "call"), ("push", "call")]
print("incremental break-even: upgrade lo->hi pays iff r x arpu > K = dcost/dmult; r_inc = K/arpu")
inc_rows = []
for lo, hi in pairs:
    K = (COST[hi] - COST[lo]) / (MULT[hi] - MULT[lo])
    row = dict(upgrade=f"{lo}->{hi}", K=round(K, 2))
    for name, a in levels:
        if name in ("q50", "LOW_median", "MID_median", "HIGH_median", "q90"):
            row[f"r_inc@{name}"] = round(K / a, 5)
    inc_rows.append(row)
print(pd.DataFrame(inc_rows).to_string(index=False))
print("multiplier gained per unit of money for each upgrade (what matters once money binds):")
eff = {}
for lo, hi in pairs[:3]:
    eff[(lo, hi)] = (MULT[hi] - MULT[lo]) / (COST[hi] - COST[lo])
    print(f"  {lo}->{hi}: dmult/dcost = {eff[(lo, hi)]:.5f}")
print(f"  sms->ads is {eff[('sms', 'digital_ads')] / eff[('digital_ads', 'call')]:.3f}x more money-efficient than ads->call; "
      f"push->sms is {eff[('push', 'sms')] / eff[('sms', 'digital_ads')]:.3f}x more than sms->ads")

print("capacity with the whole budget and reach:")
for c in CH:
    by_money = math.inf if COST[c] == 0 else B // COST[c]
    n = int(min(R, by_money))
    binds = "reach" if by_money >= R else "money"
    print(f"  {c:12s} contacts by money={by_money} -> usable={n} ({binds} binds); money used={n * COST[c]:,}; "
          f"share of audience={100 * n / len(prof):.1f}%")
print(f"  money/reach crossover cost per contact = {B / R:.4f} (channels cheaper than this are reach-bound)")
print(f"  10 campaigns x {MAX_CUSTOMERS_PER_CAMPAIGN} = {MAX_CAMPAIGNS * MAX_CUSTOMERS_PER_CAMPAIGN} slots vs reach {R}")

mm = _mock_impact_model(ct)
sat = 1 / MULT["call"]
print(f"conversion cap: call saturates when conversion_rate > 1/{MULT['call']} = {sat:.4f}; other channels never")
print(f"  mock model rows={len(mm)}; rows with conv>{sat:.3f}: {int((mm.conversion_rate > sat).sum())} "
      f"({100 * (mm.conversion_rate > sat).mean():.2f}%); movers in those rows: "
      f"{100 * mm.loc[mm.conversion_rate > sat, 'count'].sum() / mm['count'].sum():.2f}%")
print(f"  mock conversion_rate quantiles 50/90/99: {mm.conversion_rate.quantile([.5, .9, .99]).round(4).tolist()}")
cells_all = prof.groupby(["current_tariff", "arpu_segment"]).agg(n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum"))
satcells = mm[mm.conversion_rate > sat][["tariff_plan_code_from", "arpu_segment"]].drop_duplicates()
satcells = satcells.set_index(["tariff_plan_code_from", "arpu_segment"]).index
hit = cells_all[cells_all.index.isin(satcells)]
print(f"  profile cells having >=1 call-saturating target in the mock: {len(hit)} cells, "
      f"n={int(hit.n.sum())}, mass share={100 * hit.mass.sum() / pa.sum():.2f}%")
for conv in [0.3, 0.6, 0.8333, 1.0]:
    print(f"  conv={conv}: effective call/sms multiplier ratio = {min(1, conv * MULT['call']) / (conv * MULT['sms']):.4f}")

# ======================================================================= 3. reach vs money
print("\n=== 3. REACH VS MONEY ===")
a_med, a_high = float(pa.median()), float(segmed.loc["HIGH", "median"])
rs = [0.02, 0.05, 0.10, 0.20]
pc_rows = []
for r in rs:
    for name, a in [("median", a_med), ("HIGH_median", a_high)]:
        nets = {c: r * MULT[c] * a - COST[c] for c in CH}
        row = dict(r=r, arpu=name, **{c: round(v, 1) for c, v in nets.items()})
        row["best_per_contact"] = max(nets, key=nets.get)
        # whole budget+reach on one channel, homogeneous audience at this arpu
        tot = {c: nets[c] * int(min(R, math.inf if COST[c] == 0 else B // COST[c])) for c in CH}
        row["best_single_channel_total"] = max(tot, key=tot.get)
        row["its_total"] = round(max(tot.values()))
        pc_rows.append(row)
print("net per contact = r x mult x arpu - cost (base lift ratio r, homogeneous audience):")
print(pd.DataFrame(pc_rows).to_string(index=False))

a_sorted = np.sort(pa.dropna().values)[::-1]
S = np.concatenate([[0.0], np.cumsum(a_sorted)])


def best_mix(r, budget=B, reach=R):
    """Exact optimum for a uniform base lift r over the real predicted_arpu distribution.
    Single crossing => contact the top-`reach` by arpu; call > ads > sms > push in arpu order."""
    N = min(reach, len(a_sorted))
    n_sms_ok = int((a_sorted > COST["sms"] / ((MULT["sms"] - MULT["push"]) * r)).sum())
    best = (-math.inf, 0, 0, 0)
    for i in range(0, int(min(budget // COST["call"], N)) + 1):
        j = np.arange(0, int(min((budget - COST["call"] * i) // COST["digital_ads"], N - i)) + 1)
        money = budget - COST["call"] * i - COST["digital_ads"] * j
        s = np.minimum(np.minimum(money // COST["sms"], N - i - j), np.maximum(n_sms_ok - i - j, 0)).astype(int)
        k2, k3 = i + j, i + j + s
        val = r * (MULT["call"] * S[i] + MULT["digital_ads"] * (S[k2] - S[i]) + MULT["sms"] * (S[k3] - S[k2])
                   + MULT["push"] * (S[N] - S[k3])) - COST["call"] * i - COST["digital_ads"] * j - COST["sms"] * s
        t = int(val.argmax())
        if val[t] > best[0]:
            best = (float(val[t]), i, int(j[t]), int(s[t]))
    v, i, j, s = best
    assert COST["call"] * i + COST["digital_ads"] * j + COST["sms"] * s <= budget and i + j + s <= N
    return dict(net=v, call=i, digital_ads=j, sms=s, push=N - i - j - s,
                money=COST["call"] * i + COST["digital_ads"] * j + COST["sms"] * s)


print("predicted_arpu at descending rank:",
      {k: round(float(a_sorted[k - 1]), 1) for k in [1, 625, 2222, 4545, 15000, len(a_sorted)]})
print(f"predicted_arpu: max={pa.max():.1f} min={pa.min():.1f} exactly 0: {int((pa == 0).sum())} negative: {int((pa < 0).sum())}")
print(f"all-sms money on 15000 contacts = {R * COST['sms']}; leftover {B - R * COST['sms']} buys "
      f"{(B - R * COST['sms']) / (COST['digital_ads'] - COST['sms']):.1f} sms->ads upgrades "
      f"or {(B - R * COST['sms']) / (COST['call'] - COST['sms']):.1f} sms->call upgrades")
ratio_call = eff[("sms", "digital_ads")] / eff[("digital_ads", "call")]
print(f"with money binding, ads->call beats spending the same money on sms->ads only if the call target's r x arpu "
      f">= {ratio_call:.3f} x that of the marginal ads subscriber; at equal r and marginal arpu "
      f"{a_sorted[2221]:.1f} (rank 2222) that is arpu >= {ratio_call * a_sorted[2221]:.1f}; "
      f"subscribers above it: {int((a_sorted >= ratio_call * a_sorted[2221]).sum())}")

mix_rows, shadow = [], {}
for r in rs + [0.30, 0.45]:
    base = best_mix(r)
    rho = (best_mix(r, reach=R + 100)["net"] - base["net"]) / 100
    lam = (best_mix(r, budget=B + 1000)["net"] - base["net"]) / 1000
    shadow[r] = (rho, lam)
    push_only = r * MULT["push"] * S[min(R, len(a_sorted))]
    mix_rows.append(dict(r=r, net=round(base["net"]), call=base["call"], ads=base["digital_ads"], sms=base["sms"],
                         push=base["push"], money_used=base["money"], reach_shadow=round(rho, 2),
                         money_shadow=round(lam, 4), push_only_net=round(push_only),
                         mix_gain_vs_push_pct=round(100 * (base["net"] / push_only - 1), 2)))
print("optimal channel mix, uniform r over the real audience (top-15000 by predicted_arpu), no pilots:")
print(pd.DataFrame(mix_rows).to_string(index=False))
print("reach_shadow = extra net per extra contact of reach; money_shadow = extra net per extra unit of money")

print("mix when only the top-N subscribers are worth contacting (positive pool smaller than reach), r=0.1:")
for pool in [1000, 2500, 5000, 7500, 10000, 15000]:
    mx = best_mix(0.10, reach=pool)
    rho = (best_mix(0.10, reach=pool + 100)["net"] - mx["net"]) / 100
    lam = (best_mix(0.10, reach=pool, budget=B + 1000)["net"] - mx["net"]) / 1000
    print(f"  pool={pool:5d}: call/ads/sms/push={mx['call']}/{mx['digital_ads']}/{mx['sms']}/{mx['push']} "
          f"money={mx['money']:,} net={mx['net']:,.0f} reach_shadow={rho:.2f} money_shadow={lam:.4f}")

print("opportunity cost of pilot spend (pilot contacts assumed to add no lift beyond the final plan):")
for label, ch, npil in [("20x200 sms", "sms", 4000), ("agent cap 3750 sms", "sms", 3750),
                        ("20x200 push", "push", 4000), ("10x200 digital_ads", "digital_ads", 2000)]:
    bb, rr = B - npil * COST[ch], R - npil
    info = npil * (MULT[ch] / MULT["sms"]) ** 2
    out = []
    for r in rs:
        full, less = best_mix(r)["net"], best_mix(r, budget=bb, reach=rr)
        loss = 100 * (1 - less["net"] / full)
        out.append(f"r={r}: -{loss:.2f}% ({1000 * loss / info:.3f}%/1000 sms-eq; mix call/ads/sms/push="
                   f"{less['call']}/{less['digital_ads']}/{less['sms']}/{less['push']})")
    print(f"  {label:20s} B={bb} R={rr} info={info:.0f} sms-eq contacts: " + "; ".join(out))


# ======================================================================= 4. pilots
print("\n=== 4. PILOT STATISTICS ===")
effects = [0.02, 0.05, 0.10, 0.20, 0.30, 0.45]
ns = [10, 30, 60, 100, 150, 200]
print("P(observed sign wrong) = Phi(-effect / (0.804/sqrt(n))), observed scale:")
pw = pd.DataFrame({f"n={n}": [Phi(-e / (PER_CUSTOMER_STD / math.sqrt(n))) for e in effects] for n in ns},
                  index=[f"e={e}" for e in effects])
print(pw.round(4).to_string())
for n in [30, 200]:
    for p in [0.25, 0.04]:
        e = -Phi_inv(p) * PER_CUSTOMER_STD / math.sqrt(n)
        print(f"  effect giving P(wrong)={p} at n={n}: {e:.4f}")
e30 = -Phi_inv(0.25) * PER_CUSTOMER_STD / math.sqrt(30)
print(f"brief check: effect implied by 1-in-4 at n=30 = {e30:.4f}; at that effect n=200 gives "
      f"P={Phi(-e30 / (PER_CUSTOMER_STD / math.sqrt(200))):.4f} (1 in "
      f"{1 / Phi(-e30 / (PER_CUSTOMER_STD / math.sqrt(200))):.1f}); cost ratio 200/30 = {200 / 30:.3f}")
for c in ["sms", "digital_ads", "call", "push"]:
    print(f"  implied base-scale effect if piloted via {c}: {e30 / MULT[c]:.4f}")

print("20 pilots x 200 contacts:")
n_all = MAX_PILOTS * MAX_PILOT_CUSTOMERS
for c in CH:
    money = n_all * COST[c]
    print(f"  {c:12s} contacts={n_all} money={money:,} ({100 * money / B:.1f}% of budget) "
          f"reach={100 * n_all / R:.1f}% feasible={money <= B}")
print(f"  call pilots max contacts with whole budget = {B // COST['call']}")

print("base-scale SE of one pilot (0.804/(mult*sqrt(n))) and information per contact relative to sms:")
for c in CH:
    print(f"  {c:12s} SE@n=200={PER_CUSTOMER_STD / (MULT[c] * math.sqrt(200)):.4f} "
          f"info/contact vs sms={(MULT[c] / MULT['sms']) ** 2:.4f} "
          f"n to match sms n=200: {200 * (MULT['sms'] / MULT[c]) ** 2:.1f} "
          f"money per unit precision vs sms: {'n/a' if COST[c] == 0 else round((COST[c] / MULT[c] ** 2) / (COST['sms'] / MULT['sms'] ** 2), 3)}")

print("pilot information (mult^2, base scale) per unit of shadow cost (reach_shadow + cost x money_shadow):")
for r in rs:
    rho, lam = shadow[r]
    vals = {c: MULT[c] ** 2 / (rho + COST[c] * lam) for c in CH}
    print(f"  r={r}: " + " ".join(f"{c}={v * 1000:.4f}e-3" for c, v in vals.items())
          + f" -> best {max(vals, key=vals.get)}; ads/sms={vals['digital_ads'] / vals['sms']:.3f}")

za, zb = Phi_inv(0.95), Phi_inv(0.80)
print(f"z(0.95)={za:.4f} z(0.80)={zb:.4f}")
print("n per arm to separate two targets (two independent pilots), 80% power, one-sided 5%:")
for d in [0.02, 0.05, 0.10]:
    n2 = 2 * (PER_CUSTOMER_STD * (za + zb) / d) ** 2
    n1 = (PER_CUSTOMER_STD * (za + zb) / d) ** 2
    print(f"  delta={d}: two-arm n/arm={math.ceil(n2)} (pilots of 200 needed per arm={math.ceil(n2 / 200)}); "
          f"vs known threshold n={math.ceil(n1)}; base-scale delta via sms -> n/arm={math.ceil(n2 * MULT['sms'] ** 2)}")
print(f"  MDE at n=200 (observed scale): two-arm={(za + zb) * PER_CUSTOMER_STD * math.sqrt(2 / 200):.4f} "
      f"one-sample={(za + zb) * PER_CUSTOMER_STD / math.sqrt(200):.4f}; "
      f"base scale via sms two-arm={(za + zb) * PER_CUSTOMER_STD * math.sqrt(2 / 200) / MULT['sms']:.4f}")

# ======================================================================= 5. campaign caps
print("\n=== 5. CAMPAIGN CAPS ===")
print(f"missing: current_tariff={int(prof.current_tariff.isna().sum())} arpu_segment={int(prof.arpu_segment.isna().sum())} "
      f"(unreachable by tariff/segment filters; mock fallback gives them 0 lift)")
cells = cells_all.sort_values("mass", ascending=False).reset_index()
cells["cum_n"] = cells.n.cumsum()
cells["cum_mass_pct"] = 100 * cells.mass.cumsum() / pa.sum()
cells["avg_arpu"] = cells.mass / cells.n
print(f"cells (tariff x arpu_segment): {len(cells)}; with n>=20: {int((cells.n >= 20).sum())} "
      f"holding {100 * cells[cells.n >= 20].mass.sum() / pa.sum():.2f}% of mass; with n>{MAX_CUSTOMERS_PER_CAMPAIGN}: "
      f"{int((cells.n > MAX_CUSTOMERS_PER_CAMPAIGN).sum())}")
print(cells.head(12).round(2).to_string())
for share in [50, 80, 90]:
    k = int((cells.cum_mass_pct < share).sum()) + 1
    print(f"  top cells to reach {share}% of mass: {k} cells, {int(cells.n.iloc[:k].sum())} subscribers")
k15 = int((cells.cum_n < R).sum()) + 1
top = cells.iloc[:k15].copy()
top.loc[top.index[-1], "n"] = R - int(top.n.iloc[:-1].sum())   # last cell partially covered
print(f"  top-mass cells filling reach {R}: {k15} cells, mass share covered="
      f"{100 * (cells.mass.iloc[:k15 - 1].sum() + cells.avg_arpu.iloc[k15 - 1] * top.n.iloc[-1]) / pa.sum():.2f}%")
print(f"  campaigns if one per cell (split at 5000): {int(np.ceil(top.n / MAX_CUSTOMERS_PER_CAMPAIGN).sum())}; "
      f"if merged per arpu_segment (same target+channel): "
      f"{int(np.ceil(top.groupby('arpu_segment').n.sum() / MAX_CUSTOMERS_PER_CAMPAIGN).sum())}; "
      f"floor ceil(R/5000)={math.ceil(R / MAX_CUSTOMERS_PER_CAMPAIGN)}")
print(top[["current_tariff", "arpu_segment", "n", "avg_arpu", "cum_mass_pct"]].round(1).to_string())

rk = prof.ID_NUMBER.rank().corr(prof.predicted_arpu.rank())
print(f"ID order vs value: Spearman(ID, predicted_arpu)={rk:.4f}; "
      f"Spearman(ID, ARPU_3m_avg)={prof.ID_NUMBER.rank().corr(prof.ARPU_3m_avg.rank()):.4f}")
first = prof.sort_values("ID_NUMBER").head(MAX_CUSTOMERS_PER_CAMPAIGN)
print(f"  unfiltered campaign keeps first {MAX_CUSTOMERS_PER_CAMPAIGN} IDs: mean predicted_arpu={first.predicted_arpu.mean():.1f} "
      f"vs audience {pa.mean():.1f}; mass share={100 * first.predicted_arpu.sum() / pa.sum():.2f}% "
      f"(proportional would be {100 * MAX_CUSTOMERS_PER_CAMPAIGN / len(prof):.2f}%)")
print("  first-5000 arpu_segment mix:", first.arpu_segment.value_counts().to_dict())
dec = pd.qcut(prof.ID_NUMBER.rank(), 5, labels=False)
print("  mean predicted_arpu by ID quintile:", prof.groupby(dec).predicted_arpu.mean().round(1).tolist())
for seg in ["LOW", "MID", "HIGH"]:
    s = prof[prof.arpu_segment == seg].sort_values("ID_NUMBER")
    if len(s) > MAX_CUSTOMERS_PER_CAMPAIGN:
        kept = s.head(MAX_CUSTOMERS_PER_CAMPAIGN).predicted_arpu
        print(f"  segment {seg}: n={len(s)}, first-5000 mean={kept.mean():.1f} vs segment mean={s.predicted_arpu.mean():.1f} "
              f"(kept mass share of segment={100 * kept.sum() / s.predicted_arpu.sum():.2f}%)")
for (t, sg), n in cells_all.n.items():
    if n > MAX_CUSTOMERS_PER_CAMPAIGN:
        s = prof[(prof.current_tariff == t) & (prof.arpu_segment == sg)].sort_values("ID_NUMBER")
        kept = s.head(MAX_CUSTOMERS_PER_CAMPAIGN).predicted_arpu
        print(f"  cell {t}/{sg}: n={n}, first-5000 mean={kept.mean():.1f} vs cell mean={s.predicted_arpu.mean():.1f}")
print(f"pilot re-contact: pilots sample randomly inside the filtered cell and final campaigns cannot exclude IDs, "
      f"so 20x200={n_all} pilot contacts in later-deployed cells are paid twice = {100 * n_all / R:.1f}% of reach")
