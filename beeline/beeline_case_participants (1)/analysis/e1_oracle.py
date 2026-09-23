"""e1 part 1-2: true mock effects and the oracle plan / upper bounds.

LOCAL VALIDATION ONLY: reads the mock impact model (mock_environment._mock_impact_model,
_mock_fallback) to know the true mock effects offline. The agent never sees any of this.

Run:  python3 analysis/e1_oracle.py
"""
import os
import sys

import numpy as np
import pandas as pd

P = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, P)
os.chdir(P)  # mock_environment / local_eval read data via relative paths

from mock_environment import _mock_fallback, _mock_impact_model  # noqa: E402
from scoring_core import (CHANNELS, MAX_CAMPAIGNS, MAX_CUSTOMERS_PER_CAMPAIGN,  # noqa: E402
                          MAX_TOTAL_CONTACTS, TOTAL_BUDGET, apply_filters, score_campaign,
                          score_campaigns)

CH = list(CHANNELS)
COST = np.array([CHANNELS[c]["cost_per_contact"] for c in CH], float)
MULT = np.array([CHANNELS[c]["conversion_multiplier"] for c in CH], float)
RCOLS = ["r_" + c for c in CH]
LEVELS = {"cell": [], "data": ["data_segment"], "call": ["data_segment", "call_segment"]}


def load():
    profile = pd.read_csv("customer_profile.csv")
    dt = pd.read_csv("data/dict_tariff.csv")
    im = _mock_impact_model(pd.read_csv("data/change_tariff.csv"))
    return profile, dt, im


def true_effects(profile, dt, im):
    """Row per (current_tariff, arpu_segment, target != current): true pct, conversion, base, per-channel ratio."""
    fb_conv = float(im["conversion_rate"].median())
    cells = (profile.dropna(subset=["current_tariff", "arpu_segment"])
             .groupby(["current_tariff", "arpu_segment"])
             .agg(n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum")).reset_index())
    g = cells.merge(pd.DataFrame({"target": sorted(dt["tariff_plan_code"])}), how="cross")
    g = g[g["target"] != g["current_tariff"]]
    m = im.assign(arpu_segment=im["arpu_segment"].astype(str)).rename(
        columns={"tariff_plan_code_from": "current_tariff", "tariff_plan_code_to": "target"})
    g = g.merge(m[["current_tariff", "arpu_segment", "target", "arpu_change_pct", "conversion_rate", "count"]],
                how="left", on=["current_tariff", "arpu_segment", "target"])
    miss = g["arpu_change_pct"].isna()
    g["source"] = np.where(miss, "fallback", "history")
    fb = [_mock_fallback(r.current_tariff, r.target, r.arpu_segment, dt, fb_conv) for r in g[miss].itertuples()]
    g.loc[miss, "arpu_change_pct"] = [f[0] for f in fb]
    g.loc[miss, "conversion_rate"] = [f[1] for f in fb]
    g["base"] = g["arpu_change_pct"] * g["conversion_rate"]
    for c, mu in zip(CH, MULT):
        g["r_" + c] = g["arpu_change_pct"] * np.minimum(1.0, g["conversion_rate"] * mu)
    return g.reset_index(drop=True), fb_conv


# ------------------------------------------------------------------ scoring helpers
def to_frame(campaigns):
    df = pd.DataFrame(campaigns)
    for col in ["filter_arpu_segment", "filter_data_segment", "filter_call_segment",
                "filter_current_tariff", "explicit_ids"]:
        if col not in df.columns:
            df[col] = None
    return df


def score(campaigns, profile, dt, im):
    df = to_frame(campaigns)
    return score_campaigns(df, profile, im, dt, profile["predicted_arpu"].sum(), _mock_fallback, team_id="e1")


def ledger(campaigns, profile, dt, im):
    """Per-contact rows with the exact truncation of score_campaigns; returns (rows, per-subscriber best)."""
    df = to_frame(campaigns)
    fbc = im["conversion_rate"].median()
    R, B, parts = MAX_TOTAL_CONTACTS, TOTAL_BUDGET, []
    for i, c in df.iterrows():
        cost = CHANNELS[c["channel"]]["cost_per_contact"]
        seg = apply_filters(profile, c).sort_values("ID_NUMBER").iloc[:MAX_CUSTOMERS_PER_CAMPAIGN]
        seg = seg.iloc[:max(R, 0)]
        if cost > 0:
            seg = seg.iloc[:max(int(B // cost), 0)]
        R -= len(seg)
        B -= len(seg) * cost
        s = score_campaign(seg, c["target_tariff"], im, dt, fbc, c["channel"], _mock_fallback)
        parts.append(s[["ID_NUMBER", "current_tariff", "arpu_segment", "expected_lift_per_customer"]].assign(
            campaign=c.get("campaign_name", f"c{i}"), cidx=i, cost=float(cost),
            target=c["target_tariff"], channel=c["channel"],
            pilot=isinstance(c.get("explicit_ids"), list)))
    rows = pd.concat(parts, ignore_index=True)
    best = rows.loc[rows.groupby("ID_NUMBER")["expected_lift_per_customer"].idxmax()].copy()
    best = best.drop(columns="cost").merge(rows.groupby("ID_NUMBER")["cost"].sum().rename("cost_all"),
                                           left_on="ID_NUMBER", right_index=True)
    return rows, best


# ------------------------------------------------------------------ oracle
def make_units(profile, eff, level):
    keys = ["current_tariff", "arpu_segment"] + LEVELS[level]
    u = (profile.dropna(subset=keys).groupby(keys)
         .agg(n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum")).reset_index())
    targets = sorted(eff["target"].unique())
    idx = eff.set_index(["current_tariff", "arpu_segment", "target"])
    cell_ix = pd.MultiIndex.from_frame(u[["current_tariff", "arpu_segment"]])
    Rt = np.full((len(u), len(targets), len(CH)), np.nan)
    H = np.zeros((len(u), len(targets), len(CH)), bool)
    for ti, t in enumerate(targets):
        sub = idx.xs(t, level="target").reindex(cell_ix)
        Rt[:, ti, :] = sub[RCOLS].values
        H[:, ti, :] = (sub["source"].values == "history")[:, None]
    n, mass = u["n"].values.astype(float), u["mass"].values
    V = Rt * mass[:, None, None] - n[:, None, None] * COST[None, None, :]
    V = np.where(np.isnan(V), -np.inf, V).reshape(len(u), -1)
    M = (n[:, None] * np.tile(COST, len(targets))[None, :])
    data = u["data_segment"].values if "data_segment" in u else np.array(["*"] * len(u))
    call = u["call_segment"].values if "call_segment" in u else np.array(["*"] * len(u))
    opt_t = np.repeat(np.arange(len(targets)), len(CH))
    opt_c = np.tile(np.arange(len(CH)), len(targets))
    keystr = np.array([[f"{targets[opt_t[k]]}|{CH[opt_c[k]]}|{u['arpu_segment'].iat[i]}|{data[i]}|{call[i]}"
                        for k in range(len(opt_t))] for i in range(len(u))])
    K, keys_uniq = pd.factorize(keystr.ravel())
    return dict(u=u, n=n, V=V, M=M, H=H.reshape(len(u), -1), K=K.reshape(len(u), -1), keys=keys_uniq,
                targets=targets, opt_t=opt_t, opt_c=opt_c, level=level)


def _tot(o, allowed, lam, rho):
    adj = np.where(allowed, o["V"] - lam * o["M"] - rho * o["n"][:, None], -np.inf)
    j = adj.argmax(1)
    keep = adj[np.arange(len(j)), j] > 0
    return keep, j, float(o["M"][keep, j[keep]].sum()), float(o["n"][keep].sum())


def _lagrange(o, allowed, R, B):
    def lam_for(rho):
        if _tot(o, allowed, 0.0, rho)[2] <= B:
            return 0.0
        lo, hi = 0.0, 1.0
        while _tot(o, allowed, hi, rho)[2] > B and hi < 1e12:
            hi *= 2
        for _ in range(30):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if _tot(o, allowed, mid, rho)[2] > B else (lo, mid)
        return hi
    rho = 0.0
    if _tot(o, allowed, lam_for(0.0), 0.0)[3] > R:
        lo, hi = 0.0, 1.0
        while _tot(o, allowed, lam_for(hi), hi)[3] > R and hi < 1e12:
            hi *= 2
        for _ in range(30):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if _tot(o, allowed, lam_for(mid), mid)[3] > R else (lo, mid)
        rho = hi
    lam = lam_for(rho)
    keep, j, _, _ = _tot(o, allowed, lam, rho)
    return {int(i): int(j[i]) for i in np.flatnonzero(keep)}, lam, rho


def _fill(o, allowed, chosen, R, B):
    """Repair to fit, then greedily add whole units by value per contact."""
    n, V, M = o["n"], o["V"], o["M"]
    order = sorted(chosen, key=lambda i: V[i, chosen[i]] / n[i])
    while sum(n[i] for i in chosen) > R or sum(M[i, chosen[i]] for i in chosen) > B:
        chosen.pop(order.pop(0))
    r_left = R - sum(n[i] for i in chosen)
    b_left = B - sum(M[i, chosen[i]] for i in chosen)
    cand = [i for i in range(len(n)) if i not in chosen and np.any(allowed[i] & (V[i] > 0))]
    cand.sort(key=lambda i: -np.max(np.where(allowed[i], V[i], -np.inf)) / n[i])
    for i in cand:
        if n[i] > r_left:
            continue
        ok = allowed[i] & (V[i] > 0) & (M[i] <= b_left)
        if ok.any():
            j = int(np.argmax(np.where(ok, V[i], -np.inf)))
            chosen[i] = j
            r_left -= n[i]
            b_left -= M[i, j]
    return chosen, r_left, b_left


def _pack(o, chosen):
    groups = {}
    for i, j in chosen.items():
        groups.setdefault(int(o["K"][i, j]), []).append(i)
    camps = []
    for k, us in groups.items():
        bins = []
        for i in sorted(us, key=lambda i: (-o["n"][i], o["u"]["current_tariff"].iat[i])):
            for b in bins:
                if b["n"] + o["n"][i] <= MAX_CUSTOMERS_PER_CAMPAIGN:
                    b["units"].append(i); b["n"] += o["n"][i]; b["value"] += o["V"][i, chosen[i]]
                    break
            else:
                bins.append(dict(key=k, units=[i], n=o["n"][i], value=o["V"][i, chosen[i]]))
        camps += bins
    return camps


def _campaign_dict(o, key, units, name):
    t, c, seg, data, call = o["keys"][key].split("|")
    return dict(campaign_name=name, filter_arpu_segment=seg,
                filter_data_segment=None if data == "*" else data,
                filter_call_segment=None if call == "*" else call,
                filter_current_tariff=";".join(sorted(o["u"]["current_tariff"].iat[i] for i in units)),
                target_tariff=t, channel=c, explicit_ids=None)


def _solve(o, allowed, R, B):
    chosen, lam, rho = _lagrange(o, allowed, R, B)
    chosen, r_left, b_left = _fill(o, allowed, chosen, R, B)
    return chosen, r_left, b_left, lam, rho


def oracle(profile, eff, level, R=MAX_TOTAL_CONTACTS, B=TOTAL_BUDGET, max_campaigns=MAX_CAMPAIGNS,
           cap=True, history_only=False, smart=False):
    """Known-effects plan: Lagrangian money/reach channel+target choice per unit, greedy fill,
    first-fit packing into <=5000 campaigns; while over the campaign cap, drop a campaign key and
    re-solve (cheap: the least valuable key; smart: the key whose removal keeps the most value).
    A partial 'tail' campaign uses leftover reach if a slot remains."""
    o = make_units(profile, eff, level)
    allowed = np.isfinite(o["V"]) & (o["V"] > 0)
    if history_only:
        allowed &= o["H"]
    while True:
        chosen, r_left, b_left, lam, rho = _solve(o, allowed, R, B)
        camps = _pack(o, chosen)
        if not cap or len(camps) <= max_campaigns:
            break
        kv = {}
        for cp in camps:
            kv[cp["key"]] = kv.get(cp["key"], 0.0) + cp["value"]
        drop = min(kv, key=kv.get)
        if smart:   # ponytail: one re-solve per candidate key; fine for the 63-unit cell level only
            vals = {k: sum(o["V"][i, j] for i, j in _solve(o, allowed & (o["K"] != k), R, B)[0].items())
                    for k in kv}
            drop = max(vals, key=vals.get)
        allowed &= o["K"] != drop
    camps.sort(key=lambda cp: -cp["value"] / cp["n"])
    out = [_campaign_dict(o, cp["key"], cp["units"], f"oracle_{o['level']}_{i}") for i, cp in enumerate(camps)]
    est = sum(cp["value"] for cp in camps)
    # tail: best unused unit truncated by the scorer to the leftover reach/money
    if r_left > 0 and (not cap or len(out) < max_campaigns):
        best = None
        for i in range(len(o["n"])):
            if i in chosen:
                continue
            for j in np.flatnonzero(allowed[i]):
                c = o["opt_c"][j]
                take = min(o["n"][i], r_left, (b_left // COST[c]) if COST[c] > 0 else r_left)
                val = o["V"][i, j] / o["n"][i] * take
                if take > 0 and (best is None or val > best[0]):
                    best = (val, i, j)
        if best is not None and best[0] > 0:
            out.append(_campaign_dict(o, int(o["K"][best[1], best[2]]), [best[1]], f"oracle_{o['level']}_tail"))
            est += best[0]
    return out, est, dict(lam=lam, rho=rho, n_units=len(o["n"]))


def lp_bound(profile, eff, R=MAX_TOTAL_CONTACTS, B=TOTAL_BUDGET):
    """Per-subscriber LP dual bound: any plan (pilots included) nets at most min_{lam,rho} g(lam,rho)."""
    best = eff.groupby(["current_tariff", "arpu_segment"])[RCOLS].max()
    s = profile.join(best, on=["current_tariff", "arpu_segment"])
    V = s[RCOLS].fillna(0.0).values * s["predicted_arpu"].values[:, None] - COST[None, :]

    def g(lam, rho):
        return lam * B + rho * R + np.maximum(0.0, (V - lam * COST[None, :] - rho).max(1)).sum()

    def h(rho):
        lo, hi = 0.0, 200.0
        for _ in range(80):
            a, b = lo + (hi - lo) / 3, hi - (hi - lo) / 3
            lo, hi = (lo, b) if g(a, rho) <= g(b, rho) else (a, hi)
        lam = (lo + hi) / 2
        return g(lam, rho), lam

    lo, hi = 0.0, float(V.max())
    for _ in range(80):
        a, b = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        lo, hi = (lo, b) if h(a)[0] <= h(b)[0] else (a, hi)
    rho = (lo + hi) / 2
    val, lam = h(rho)
    return val, lam, rho


# ------------------------------------------------------------------ report
def part1(eff):
    print("=== PART 1: true mock effects per (current_tariff, arpu_segment, target) ===")
    cells = eff.drop_duplicates(["current_tariff", "arpu_segment"])
    print(f"cells={len(cells)}  subscribers in cells={int(cells['n'].sum())}  combos={len(eff)} "
          f"(20 targets per cell, target==current excluded: mock gives it 0)")
    for s in ["history", "fallback"]:
        e = eff[eff["source"] == s]
        print(f"source={s:<8} combos={len(e):4d}  positive base={int((e['base'] > 0).sum()):4d}  "
              f"zero={int((e['base'] == 0).sum()):4d}  negative={int((e['base'] < 0).sum()):4d}")
    pos = eff["base"] > 0
    print(f"positive combos total: {int(pos.sum())} of {len(eff)} ({pos.mean():.1%})")
    q = [0.05, 0.25, 0.5, 0.75, 0.95]
    print("base ratio quantiles (all)      :", {k: round(v, 4) for k, v in eff["base"].quantile(q).items()})
    print("base ratio quantiles (positive) :", {k: round(v, 4) for k, v in eff.loc[pos, "base"].quantile(q).items()})
    print("conversion_rate quantiles (history):",
          {k: round(v, 4) for k, v in eff.loc[eff.source == "history", "conversion_rate"].quantile(q).items()})
    for c, mu in zip(CH, MULT):
        capped = int((eff["conversion_rate"] * mu > 1).sum())
        print(f"channel {c:<11} mult={mu:.2f}  combos where conv*mult>1 (capped)={capped:4d}  "
              f"mean ratio over positive combos={eff.loc[pos, 'r_' + c].mean():.4f}")
    avg = eff["mass"] / eff["n"]
    vpc = np.stack([eff["r_" + c].values * avg.values - k for c, k in zip(CH, COST)], 1)
    val = vpc * eff["n"].values[:, None]
    eff["best_ch"] = [CH[i] for i in val.argmax(1)]
    eff["best_val"] = val.max(1)
    eff["sms_val"] = val[:, CH.index("sms")]
    eff["best_vpc"] = vpc.max(1)
    pv = eff[eff["best_val"] > 0].sort_values("best_val", ascending=False)
    print(f"combos with positive value at best channel (ignoring money/reach): {len(pv)}; "
          f"total positive value {pv['best_val'].sum():,.0f}; top-10 share {pv['best_val'].head(10).sum() / pv['best_val'].sum():.1%}; "
          f"fallback share of that value {pv.loc[pv.source == 'fallback', 'best_val'].sum() / pv['best_val'].sum():.1%}")
    ps = eff[eff["sms_val"] > 0].sort_values("sms_val", ascending=False)
    print(f"same at sms for every combo: positive {len(ps)}; top-10 share {ps['sms_val'].head(10).sum() / ps['sms_val'].sum():.1%}")
    cb = eff.sort_values("best_val", ascending=False).groupby(["current_tariff", "arpu_segment"]).head(1)
    cbp = cb[cb["best_val"] > 0]
    print(f"cells whose best combo is positive: {len(cbp)} of {len(cb)} (subscribers {int(cbp['n'].sum())}); "
          f"top-10 cells hold {cbp['best_val'].head(10).sum() / cbp['best_val'].sum():.1%} of best-per-cell value; "
          f"best target is a fallback combo in {int((cbp.source == 'fallback').sum())} cells")
    print("best-per-cell channel counts (unconstrained):", cbp["best_ch"].value_counts().to_dict())
    cb = cb.assign(vpc_n=cb["best_vpc"] * cb["n"])
    seg = cb.groupby("arpu_segment").agg(cells=("n", "size"), subscribers=("n", "sum"), mass=("mass", "sum"),
                                         median_best_base=("base", "median"), max_best_base=("base", "max"),
                                         vpc_n=("vpc_n", "sum"))
    seg["mass_share"] = seg["mass"] / seg["mass"].sum()
    seg["avg_best_value_per_contact"] = seg["vpc_n"] / seg["subscribers"]
    print("by arpu_segment (best target per cell, best channel ignoring money):\n"
          + seg.drop(columns="vpc_n").round(4).to_string())
    print("\nTop 10 combos by value at best channel (ignoring money/reach):")
    cols = ["current_tariff", "arpu_segment", "target", "n", "source", "arpu_change_pct", "conversion_rate",
            "base", "r_sms", "r_call", "best_ch", "best_vpc", "best_val"]
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(pv[cols].head(10).round(4).to_string(index=False))
    print("\nTop 10 cells by value per contact at best channel (best target):")
    cv = cb[cb["best_val"] > 0].sort_values("best_vpc", ascending=False)
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(cv[cols].head(10).round(4).to_string(index=False))
    return eff


def self_check(profile, dt, im, eff):
    """Scored single campaign must equal our effect-table estimate."""
    e = eff[(eff["current_tariff"] == "tariff_8") & (eff["arpu_segment"] == "HIGH")].sort_values("base").iloc[-1]
    camp = [dict(campaign_name="chk", filter_arpu_segment="HIGH", filter_current_tariff="tariff_8",
                 target_tariff=e["target"], channel="sms")]
    res = score(camp, profile, dt, im)
    est = e["r_sms"] * e["mass"] - e["n"] * 4
    assert abs(res["net_arpu_gain"] - est) < 1e-6 * max(1.0, abs(est)), (res["net_arpu_gain"], est)
    print(f"self-check OK: tariff_8/HIGH -> {e['target']} sms scored {res['net_arpu_gain']:,.2f} == table {est:,.2f}")


def run_oracles(profile, dt, im, eff, verbose=True):
    rows, plans = [], {}
    variants = [(lv, cap, hist, False) for lv in LEVELS for cap, hist in [(True, False), (False, False), (True, True)]]
    variants += [("cell", True, False, True), ("cell", True, True, True)]
    for level, cap, hist, smart in variants:
        camps, est, info = oracle(profile, eff, level, cap=cap, history_only=hist, smart=smart)
        res = score(camps, profile, dt, im)
        name = f"{level}|{'cap10' if cap else 'nocap'}{'-smart' if smart else ''}|{'history-only' if hist else 'all'}"
        plans[name] = camps
        rows.append(dict(variant=name, campaigns=len(camps), contacts=res["total_contacts"],
                         cost=res["total_cost"], gross=res["gross_arpu_lift"], net=res["net_arpu_gain"],
                         est=est, lam=info["lam"], rho=info["rho"]))
    tab = pd.DataFrame(rows)
    if verbose:
        with pd.option_context("display.width", 250, "display.max_columns", 30):
            print(tab.round(3).to_string(index=False))
    return tab, plans


def main():
    profile, dt, im = load()
    eff, fbc = true_effects(profile, dt, im)
    print(f"fallback conversion (median of mock conversion_rate) = {fbc:.4f}; "
          f"median tariff price = {dt['price_tariff'].median():.1f}")
    self_check(profile, dt, im, eff)
    part1(eff)

    print("\n=== PART 2: oracle (known effects, no pilots) ===")
    tab, plans = run_oracles(profile, dt, im, eff)
    cap = tab[tab["variant"].str.contains("cap10") & tab["variant"].str.endswith("|all")]
    best = cap.loc[cap["net"].idxmax()]
    nocap = tab[tab["variant"].str.contains("nocap")]
    hist = tab[tab["variant"].str.endswith("history-only")]
    print(f"\nORACLE (best capped variant {best['variant']}): net {best['net']:,.0f}  gross {best['gross']:,.0f}  "
          f"cost {best['cost']:,.0f}  contacts {best['contacts']:,}  campaigns {best['campaigns']}")
    print(f"UPPER BOUND ignoring 10-campaign cap (best nocap variant {nocap.loc[nocap['net'].idxmax(), 'variant']}): "
          f"net {nocap['net'].max():,.0f}")
    print(f"ORACLE restricted to history-backed combos (best capped variant): net {hist['net'].max():,.0f} "
          f"({hist['net'].max() / best['net']:.1%} of oracle)")
    ub, lam, rho = lp_bound(profile, eff)
    print(f"PER-SUBSCRIBER LP DUAL BOUND (any plan, any filters, pilots included): {ub:,.0f} "
          f"(lam={lam:.4f}, rho={rho:.2f}); oracle = {best['net'] / ub:.1%} of it")
    print(f"campaign-cap cost for the oracle (nocap - cap): {nocap['net'].max() - best['net']:,.0f}")

    camps = plans[best["variant"]]
    rows, bst = ledger(camps, profile, dt, im)
    eff_src = eff.set_index(["current_tariff", "arpu_segment", "target"])["source"]
    bst["source"] = eff_src.reindex(pd.MultiIndex.from_frame(bst[["current_tariff", "arpu_segment", "target"]])).values
    print(f"oracle gross lift from fallback-rule combos: "
          f"{bst.loc[bst.source == 'fallback', 'expected_lift_per_customer'].sum():,.0f} of "
          f"{bst['expected_lift_per_customer'].sum():,.0f}")
    res = score(camps, profile, dt, im)
    print("\nOracle campaigns:")
    for c, d in zip(camps, res["campaigns_detail"]):
        print(f"  {c['target_tariff']:<9} {c['channel']:<11} arpu={c['filter_arpu_segment']:<4} "
              f"data={str(c['filter_data_segment']):<8} call={str(c['filter_call_segment']):<6} "
              f"tariffs={c['filter_current_tariff']:<40} n={d['n_contacts']:5d} cost={d['cost']:8,.0f} "
              f"gross={d['gross_lift']:12,.0f}")
    by_ch = rows.groupby("channel").agg(contacts=("ID_NUMBER", "size"), cost=("cost", "sum"),
                                         gross=("expected_lift_per_customer", "sum"))
    print("oracle by channel:\n" + by_ch.round(0).to_string())


if __name__ == "__main__":
    main()
