"""e1v: independent mock oracle + independent scorer (verifier for e1-03/04/05).

Different algorithm from the analyst's: per unit, money is handled by an EXACT knapsack DP
(money in units of 2), reach by a Lagrange multiplier found by bisection, then a greedy fill.
The 10-campaign cap is enforced by backward elimination restricted to already-open campaign
keys (target, channel, arpu_segment [, data, call]), followed by a pairwise swap pass.
Every plan is scored twice: by my own re-implementation of the scoring rules and by the public
scoring_core.score_campaigns; both must agree.

Run:  python3 analysis/e1v_oracle.py
"""
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, P)
from e1v_effects import CH, COST, MULT, effect_table, impact, load  # noqa: E402

B_TOT, R_TOT, CAP, PER = 100_000, 15_000, 10, 5000
LEVELS = {"cell": [], "data": ["data_segment"], "call": ["data_segment", "call_segment"]}


def setup():
    ct, dt, prof = load()
    im = impact(ct)
    e, _ = effect_table(prof, dt, im)
    e = e[~e["same"]].reset_index(drop=True)
    return ct, dt, prof, e


# ---------------------------------------------------------------- my scorer
def my_score(camps, prof, e):
    look = {}
    for c in CH:
        look[c] = e.set_index(["cur", "seg", "tgt"])["r_" + c]
    R, Bm, cost_tot, parts, detail = R_TOT, float(B_TOT), 0.0, [], []
    for cp in camps:
        s = prof
        ids = cp.get("explicit_ids")
        if isinstance(ids, list) and ids:
            s = s[s["ID_NUMBER"].isin(ids)]
        else:
            for col, k in [("arpu_segment", "filter_arpu_segment"), ("data_segment", "filter_data_segment"),
                           ("call_segment", "filter_call_segment")]:
                if cp.get(k) is not None:
                    s = s[s[col] == cp[k]]
            if cp.get("filter_current_tariff") is not None:
                s = s[s["current_tariff"].isin(cp["filter_current_tariff"].split(";"))]
        s = s.sort_values("ID_NUMBER").iloc[:PER]
        s = s.iloc[:max(R, 0)]
        k = COST[CH.index(cp["channel"])]
        if k > 0:
            s = s.iloc[:max(int(Bm // k), 0)]
        R -= len(s)
        Bm -= len(s) * k
        cost_tot += len(s) * k
        key = pd.MultiIndex.from_arrays([s["current_tariff"], s["arpu_segment"], [cp["target_tariff"]] * len(s)])
        ratio = look[cp["channel"]].reindex(key).fillna(0.0).values
        lift = ratio * s["predicted_arpu"].values
        parts.append(pd.DataFrame({"ID": s["ID_NUMBER"].values, "lift": lift}))
        detail.append(dict(n=len(s), cost=len(s) * k, gross=float(lift.sum())))
    if not parts:
        return dict(net=0.0, gross=0.0, cost=0.0, contacts=0, detail=[])
    allp = pd.concat(parts)
    gross = float(allp.groupby("ID")["lift"].max().sum())
    return dict(net=gross - cost_tot, gross=gross, cost=cost_tot, contacts=R_TOT - R, detail=detail)


def official_score(camps, prof, dt, im_mock):
    from mock_environment import _mock_fallback
    from scoring_core import score_campaigns
    df = pd.DataFrame(camps)
    for col in ["filter_arpu_segment", "filter_data_segment", "filter_call_segment", "filter_current_tariff", "explicit_ids"]:
        if col not in df.columns:
            df[col] = None
    return score_campaigns(df, prof, im_mock, dt, prof["predicted_arpu"].sum(), _mock_fallback)


# ---------------------------------------------------------------- units / options
def units(prof, e, level):
    keys = ["current_tariff", "arpu_segment"] + LEVELS[level]
    u = (prof.dropna(subset=keys).groupby(keys)
         .agg(n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum")).reset_index())
    rc = ["r_" + c for c in CH]
    tab = {k: v for k, v in zip(map(tuple, e[["cur", "seg", "tgt"]].values), e[rc].values)}
    targets = sorted(e["tgt"].unique())
    opts = []   # per unit: list of (keystr, tgt, ch_idx, value, money, reach)
    for r in u.itertuples(index=False):
        rr = r._asdict()
        cur, seg = rr["current_tariff"], rr["arpu_segment"]
        tail = "|".join(str(rr[c]) for c in LEVELS[level]) or "*"
        lst = []
        for t in targets:
            if t == cur or (cur, seg, t) not in tab:   # history-only runs drop fallback combos
                continue
            ratios = tab[(cur, seg, t)]
            for ci in range(4):
                v = ratios[ci] * rr["mass"] - rr["n"] * COST[ci]
                if v > 0:
                    lst.append((f"{t}|{CH[ci]}|{seg}|{tail}", t, ci, float(v), float(rr["n"] * COST[ci]), int(rr["n"])))
        opts.append(lst)
    return u, opts


def solve(u, opts, allowed, R, B, iters=22):
    """Max sum value s.t. money<=B (exact DP, units of 2) and reach<=R (Lagrangian + greedy fill)."""
    Bu = int(B // 2)
    n = u["n"].values
    best_opts = []
    for i, lst in enumerate(opts):
        per_ch = {}
        for o in lst:
            if o[0] in allowed and (o[2] not in per_ch or o[3] > per_ch[o[2]][3]):
                per_ch[o[2]] = o
        best_opts.append(list(per_ch.values()))

    def dp(rho):
        val = np.zeros(Bu + 1)
        choice = np.full((len(n), Bu + 1), -1, np.int8)
        for i, lst in enumerate(best_opts):
            new = val.copy()
            for j, o in enumerate(lst):
                m = int(o[4] // 2)
                if m > Bu:
                    continue
                cand = np.full(Bu + 1, -np.inf)
                cand[m:] = val[:Bu + 1 - m] + o[3] - rho * o[5]
                better = cand > new
                new[better] = cand[better]
                choice[i, better] = j
            val = new
        b, pick = Bu, {}
        for i in range(len(n) - 1, -1, -1):
            j = choice[i, b]
            if j >= 0:
                pick[i] = best_opts[i][j]
                b -= int(pick[i][4] // 2)
        return pick

    def reach(pick):
        return sum(o[5] for o in pick.values())

    pick = dp(0.0)
    if reach(pick) > R:
        lo, hi = 0.0, 1.0
        while reach(dp(hi)) > R:
            hi *= 2
        for _ in range(iters):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if reach(dp(mid)) > R else (lo, mid)
        pick = dp(hi)
    r_left = R - reach(pick)
    b_left = B - sum(o[4] for o in pick.values())
    cand = sorted([(o[3] / o[5], i, o) for i, lst in enumerate(best_opts) if i not in pick for o in lst], reverse=True)
    for _, i, o in cand:
        if i not in pick and o[5] <= r_left and o[4] <= b_left:
            pick[i] = o
            r_left -= o[5]
            b_left -= o[4]
    return pick, r_left, b_left


def pack(u, pick):
    groups = {}
    for i, o in pick.items():
        groups.setdefault(o[0], []).append(i)
    camps = []
    for k, idx in groups.items():
        bins = []
        for i in sorted(idx, key=lambda i: -u["n"].iat[i]):
            for b in bins:
                if b["n"] + u["n"].iat[i] <= PER:
                    b["units"].append(i); b["n"] += u["n"].iat[i]; b["value"] += pick[i][3]
                    break
            else:
                bins.append(dict(key=k, units=[i], n=u["n"].iat[i], value=pick[i][3]))
        camps += bins
    return camps


def to_campaigns(u, camps):
    out = []
    for cp in sorted(camps, key=lambda c: -c["value"] / c["n"]):
        t, ch, seg, *rest = cp["key"].split("|")
        rest = [x for x in rest if x != "*"]
        data = rest[0] if len(rest) > 0 else None
        call = rest[1] if len(rest) > 1 else None
        out.append(dict(campaign_name=f"v_{t}_{ch}_{seg}_{data}_{call}", filter_arpu_segment=seg,
                        filter_data_segment=data, filter_call_segment=call,
                        filter_current_tariff=";".join(sorted(set(u["current_tariff"].iat[i] for i in cp["units"]))),
                        target_tariff=t, channel=ch))
    return out


def all_keys(opts):
    return {o[0] for lst in opts for o in lst}


def oracle(prof, e, level="cell", R=R_TOT, B=B_TOT, cap=True, allowed=None, swap=True, log=False):
    u, opts = units(prof, e, level)
    allowed = set(allowed) if allowed is not None else all_keys(opts)
    pick, rl, bl = solve(u, opts, allowed, R, B)
    if cap:
        open_ = {o[0] for o in pick.values()}
        while len(pack(u, pick)) > CAP:
            res = {}
            for k in open_:
                pk, _, _ = solve(u, opts, open_ - {k}, R, B)
                res[k] = sum(o[3] for o in pk.values())
            drop = max(res, key=res.get)
            open_ -= {drop}
            pick, rl, bl = solve(u, opts, open_, R, B)
            open_ = {o[0] for o in pick.values()}
        if swap:   # try replacing one open key by one key from the uncapped solution's pool
            pool = {o[0] for o in solve(u, opts, allowed, R, B)[0].values()} - open_
            cur = sum(o[3] for o in pick.values())
            improved = True
            while improved:
                improved = False
                for k_out in sorted(open_):
                    for k_in in sorted(pool):
                        ks = (open_ - {k_out}) | {k_in}
                        pk, a, b = solve(u, opts, ks, R, B)
                        v = sum(o[3] for o in pk.values())
                        if v > cur + 1 and len(pack(u, pk)) <= CAP:
                            pick, rl, bl, cur = pk, a, b, v
                            pool = (pool - {k_in}) | {k_out}
                            open_ = {o[0] for o in pk.values()}
                            improved = True
                            break
                    if improved:
                        break
    camps = pack(u, pick)
    plan = to_campaigns(u, camps)
    est = sum(o[3] for o in pick.values())
    # tail: truncated extra campaign on the leftover reach, if a slot is free
    if rl > 0 and (not cap or len(plan) < CAP):
        best = None
        for i, lst in enumerate(opts):
            if i in pick:
                continue
            for o in lst:
                if o[0] not in allowed:
                    continue
                k = COST[o[2]]
                take = min(o[5], rl, (bl // k) if k > 0 else rl)
                val = o[3] / o[5] * take
                if take > 0 and (best is None or val > best[0]):
                    best = (val, i, o)
        if best is not None:
            plan += to_campaigns(u, [dict(key=best[2][0], units=[best[1]], n=u["n"].iat[best[1]], value=best[0])])
            est += best[0]
    return plan, est, u, pick


def describe(plan, prof, e, tag):
    sc = my_score(plan, prof, e)
    ch = {}
    for cp, d in zip(plan, sc["detail"]):
        c = ch.setdefault(cp["channel"], [0, 0.0])
        c[0] += d["n"]
        c[1] += d["cost"]
    segs = {}
    for cp, d in zip(plan, sc["detail"]):
        s = segs.setdefault(cp["filter_arpu_segment"], {})
        s[cp["channel"]] = s.get(cp["channel"], 0) + d["n"]
    print(f"{tag}: campaigns {len(plan)} contacts {sc['contacts']:,} money {sc['cost']:,.0f} gross {sc['gross']:,.0f} "
          f"NET {sc['net']:,.0f}; by channel {ch}; contacts by seg/channel {segs}")
    return sc


def main():
    os.chdir(P)
    ct, dt, prof, e = setup()
    from mock_environment import _mock_impact_model
    im_mock = _mock_impact_model(ct)
    t0 = time.time()

    print("=== uncapped (rule-violating) plans at three granularities ===")
    nocap = {}
    for lv in ["cell", "data", "call"]:
        plan, est, u, pick = oracle(prof, e, lv, cap=False)
        sc = describe(plan, prof, e, f"nocap {lv:<4} units={len(u)}")
        nocap[lv] = sc["net"]
        off = official_score(plan, prof, dt, im_mock)["net_arpu_gain"]
        assert abs(off - sc["net"]) < 1e-3 * max(1, abs(off)), (off, sc["net"])
    print(f"[{time.time() - t0:.0f}s]")

    print("\n=== capped oracle, cell level ===")
    plan, est, u, pick = oracle(prof, e, "cell", cap=True)
    sc = describe(plan, prof, e, "MY ORACLE cap10 cell")
    off = official_score(plan, prof, dt, im_mock)
    assert abs(off["net_arpu_gain"] - sc["net"]) < 1e-3 * max(1, abs(sc["net"]))
    print(f"official scorer agrees: {off['net_arpu_gain']:,.0f}; truncated campaigns: "
          f"{sum(1 for d in off['campaigns_detail'] if d['capped_at_campaign_limit'] or d['capped_at_reach_budget'] or d['capped_at_money_budget'])}")
    for cp, d in zip(plan, sc["detail"]):
        print(f"  {cp['target_tariff']:<9} {cp['channel']:<11} {cp['filter_arpu_segment']:<4} n={d['n']:5d} cost={d['cost']:8,.0f} "
              f"gross={d['gross']:12,.0f}  tariffs={cp['filter_current_tariff']}")
    hist = e[e.src == "history"]
    plan_h, _, _, _ = oracle(prof, hist, "cell", cap=True)
    sch = describe(plan_h, prof, e, "MY ORACLE history-backed combos only")
    print(f"history-only / full = {sch['net'] / sc['net']:.1%}")
    # fallback share of gross in my oracle
    fb = e[e.src == "fallback"].set_index(["cur", "seg", "tgt"]).index
    fbg = 0.0
    for cp, d in zip(plan, sc["detail"]):
        for t in cp["filter_current_tariff"].split(";"):
            if (t, cp["filter_arpu_segment"], cp["target_tariff"]) in fb:
                fbg += my_score([cp], prof[prof.current_tariff == t], e)["gross"]
    print(f"gross from fallback-rule combos in my oracle: {fbg:,.0f} of {sc['gross']:,.0f}")
    print(f"[{time.time() - t0:.0f}s]")

    print("\n=== certified reference (from e1v_effects): LP bound 6,636,080 ===")
    print(f"my oracle / LP bound = {sc['net'] / 6636080:.1%}; analyst oracle 6,216,635 / mine = {6216635 / sc['net']:.1%}")
    print(f"cap cost: best nocap {max(nocap.values()):,.0f} - my capped {sc['net']:,.0f} = {max(nocap.values()) - sc['net']:,.0f}; "
          f"same granularity (cell) {nocap['cell'] - sc['net']:,.0f}")


if __name__ == "__main__":
    main()
