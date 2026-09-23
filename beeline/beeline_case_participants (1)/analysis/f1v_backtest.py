"""f1v: independent re-check of the f1 robustness backtest (LOCAL VALIDATION ONLY, agent.py untouched).

Rebuilds the mock effect model from raw change_tariff.csv, perturbs it, runs agent / no-pilot agent /
template / my own confirm+slope counterfactuals through environment.make_environment + scoring_core,
and prints every number used in the verification. Deterministic (fixed seeds).
Run: python3 analysis/f1v_backtest.py
"""
import contextlib
import io
import os
import sys

import numpy as np
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, P)
import agent as A            # noqa: E402
import agent_template        # noqa: E402
import environment           # noqa: E402
import mock_environment as mock  # noqa: E402
from scoring_core import CHANNELS, score_campaigns, sanitize_campaigns  # noqa: E402

SEEDS = list(range(10))
SCEN = ["S0", "S2", "S4", "S5", "S7"]
prof = pd.read_csv(os.path.join(P, "customer_profile.csv"))
dt = pd.read_csv(os.path.join(P, "data", "dict_tariff.csv"))
ct = pd.read_csv(os.path.join(P, "data", "change_tariff.csv"))
BASE = prof["predicted_arpu"].sum()

# ---------------------------------------------------------------- effect model from raw data
d = ct[ct["AVG_ARPU_PREV_3M"] >= 100].copy()
d["arpu_segment"] = np.where(d["AVG_ARPU_PREV_3M"] <= 1000, "LOW", np.where(d["AVG_ARPU_PREV_3M"] <= 5000, "MID", "HIGH"))
d["pct"] = ((d["AVG_ARPU_NEXT_3M"] - d["AVG_ARPU_PREV_3M"]) / d["AVG_ARPU_PREV_3M"]).clip(-1, 3)
g = d.groupby(["tariff_plan_code_from", "tariff_plan_code_to", "arpu_segment"]).agg(
    arpu_change_pct=("pct", "mean"), count=("ID_NUMBER", "size")).reset_index()
g["conversion_rate"] = g["count"] / g.groupby(["tariff_plan_code_from", "arpu_segment"])["count"].transform("sum")
KEYS = ["tariff_plan_code_from", "tariff_plan_code_to", "arpu_segment"]
M0 = mock._mock_impact_model(ct)[KEYS].astype(str).merge(g, on=KEYS, how="left")  # my values, mock row order (S5 permutation depends on it)
print(f"history rows at exact segment boundaries 1000/5000: {int(d.AVG_ARPU_PREV_3M.isin([1000, 5000]).sum())}")
ref = mock._mock_impact_model(ct)
chk = M0.merge(ref.assign(arpu_segment=ref["arpu_segment"].astype(str)),
               on=["tariff_plan_code_from", "tariff_plan_code_to", "arpu_segment"], suffixes=("", "_r"))
print(f"M0 rows {len(M0)} (mock module {len(ref)}, matched {len(chk)}, max |diff pct| "
      f"{(chk.arpu_change_pct - chk.arpu_change_pct_r).abs().max():.2e}, conv {(chk.conversion_rate - chk.conversion_rate_r).abs().max():.2e})")
print(f"M0 median pct {M0.arpu_change_pct.median():+.4f} median conv {M0.conversion_rate.median():.4f}; "
      f"rows with pct < -0.5 (would be < -1 under x2): {(M0.arpu_change_pct < -0.5).sum()}")
F0 = mock._mock_fallback
MED = float(M0.arpu_change_pct.median())


def fwrap(fn):
    return lambda c, t, s, dd, fc: (fn(F0(c, t, s, dd, fc)[0]), F0(c, t, s, dd, fc)[1])


def reversed_model(M):
    M = M.copy()
    for _, grp in M.groupby(["tariff_plan_code_from", "arpu_segment"]):
        order = grp["arpu_change_pct"].sort_values(kind="mergesort")
        M.loc[order.index, "arpu_change_pct"] = order.values[::-1]
    return M


def scenario(name, perm_seed=2026):
    if name == "S0":
        return M0, F0
    if name == "S2":
        return M0.assign(arpu_change_pct=M0.arpu_change_pct * 2), fwrap(lambda x: 2 * x)
    if name == "S4":
        return reversed_model(M0), F0
    if name == "S5":
        return M0.assign(arpu_change_pct=np.random.default_rng(perm_seed).permutation(M0.arpu_change_pct.values)), F0
    if name == "S7":
        return M0.assign(arpu_change_pct=-M0.arpu_change_pct), fwrap(lambda x: -x)


valid = prof.dropna(subset=["current_tariff", "arpu_segment"])
CELL = valid.groupby(["current_tariff", "arpu_segment"]).agg(n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum"))
SUB = valid.dropna(subset=["data_segment"]).groupby(["current_tariff", "arpu_segment", "data_segment"]).agg(
    n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum"))
TGT = sorted(dt.tariff_plan_code)


def truth(M, F):
    fc = M["conversion_rate"].median()
    lk = {(a, s, b): (p, c) for a, b, s, p, c in M[["tariff_plan_code_from", "tariff_plan_code_to", "arpu_segment",
                                                     "arpu_change_pct", "conversion_rate"]].itertuples(index=False)}
    out = {}
    for (t, s) in CELL.index:
        for b in TGT:
            if b != t:
                out[(t, s, b)] = lk[(t, s, b)] if (t, s, b) in lk else tuple(map(float, F(t, b, s, dt, fc)))
    return out


def lift(tab, key, ch):
    p, c = tab.get(key, (0.0, 0.0))
    return p * min(1.0, c * CHANNELS[ch]["conversion_multiplier"])


def score(camps, M, F):
    if not camps:
        return dict(net=0.0, cost=0.0, contacts=0)
    df = pd.DataFrame(camps)
    for c in ["filter_arpu_segment", "filter_data_segment", "filter_call_segment", "filter_current_tariff", "explicit_ids"]:
        if c not in df:
            df[c] = None
    r = score_campaigns(df, prof, M, dt, BASE, F)
    return dict(net=r["net_arpu_gain"], cost=r["total_cost"], contacts=r["total_contacts"])


# ---------------------------------------------------------------- my counterfactual agents
class Confirm(A.Agent):
    K = 6

    def _run_pilots(self, env, h):
        m = env.channels["sms"]["conversion_multiplier"]
        sp = rc = 0
        for i in (h.mu0 * h.mass).sort_values(ascending=False, kind="mergesort").index[:self.K]:
            res = env.run_pilot(target_tariff=h.at[i, "target"], channel="sms", n_customers=int(min(200, h.at[i, "n"])),
                                filter_arpu_segment=h.at[i, "seg"], filter_current_tariff=h.at[i, "tariff"])
            n, y = res["n_customers"], res["observed_lift_ratio"] / m
            v = (A.NOISE_SD / m) ** 2 / n
            pr = 1 / h.at[i, "sd"] ** 2 + 1 / v
            h.at[i, "mu"] = (h.at[i, "mu"] / h.at[i, "sd"] ** 2 + y / v) / pr
            h.at[i, "sd"] = pr ** -0.5
            h.at[i, "n_obs"] += n
            h.at[i, "ysum"] += y * n
            sp, rc = sp + res["cost"], rc + n
            self.records.append(dict(tariff=h.at[i, "tariff"], seg=h.at[i, "seg"], target=h.at[i, "target"], n=n,
                                     observed=res["observed_lift_ratio"], prior_mu=h.at[i, "mu0"], post_mu=h.at[i, "mu"]))
        old = (A.PILOT_MONEY_SHARE, A.PILOT_REACH_SHARE)
        A.PILOT_MONEY_SHARE = max(0.0, old[0] - sp / env.total_budget)
        A.PILOT_REACH_SHARE = max(0.0, old[1] - rc / env.max_total_contacts)
        try:
            super()._run_pilots(env, h)
        finally:
            A.PILOT_MONEY_SHARE, A.PILOT_REACH_SHARE = old


class Slope(Confirm):
    def _calibrate(self, h):
        super()._calibrate(h)
        t = h.n_obs > 0
        den = (h.n_obs[t] * h.mu0[t] ** 2).sum()
        if t.sum() >= 3 and den > 0:
            self.slope = float(np.clip((h.ysum[t] * h.mu0[t]).sum() / den, -2, 3))
            h.loc[~t, "mu"] = h.loc[~t, "mu0"] * self.slope


class Rec(A.Agent):
    """Unchanged agent that also records the pre-truncation units of the plan."""
    def _build(self, units, profile, B, R):
        self.pre_units = list(units)
        return super()._build(units, profile, B, R)


def run(kind, M, F, seed):
    env, internals = environment.make_environment(prof, M, dt, CHANNELS, 100_000, 15_000, F, seed=seed)
    ag = {"template": agent_template.Agent, "confirm": Confirm, "slope": Slope}.get(kind, Rec)
    ag = ag() if kind == "template" else ag(verbose=False)
    old = A.PILOT_MONEY_SHARE
    if kind == "noexp":
        A.PILOT_MONEY_SHARE = 0.0
    crash = None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                fin = ag.act(env)
            except Exception as e:
                fin, crash = [], repr(e)
            fin = sanitize_campaigns(fin, env.tariffs)[:10]
    finally:
        A.PILOT_MONEY_SHARE = old
    pil = internals.executed_pilot_campaigns()
    r = score(pil + fin, M, F)
    r.update(n_pil=len(pil), n_fin=len(fin), crash=crash, pilot_net=score(pil, M, F)["net"] if pil else 0.0,
             fin_net=score(fin, M, F)["net"])
    return r, ag, pil


def units_of(ag, tab):
    h = ag.hyps
    tested = set(map(tuple, h.loc[h.n_obs > 0, ["tariff", "seg", "target"]].values))
    out = []
    for c in ag.plan_detail:
        s, dseg, b, ch = c["filter_arpu_segment"], c["filter_data_segment"], c["target_tariff"], c["channel"]
        for t in c["filter_current_tariff"].split(";"):
            n, mass = (CELL.loc[(t, s)] if dseg is None else SUB.loc[(t, s, dseg)])[["n", "mass"]]
            k = CHANNELS[ch]["cost_per_contact"]
            out.append(dict(tested=(t, s, b) in tested, n=n, mass=mass, money=n * k, seg=s, key=(t, s, b),
                            base=lift(tab, (t, s, b), "push") / 0.5, real=lift(tab, (t, s, b), ch) * mass - n * k))
    return pd.DataFrame(out)


# ---------------------------------------------------------------- oracle (independent: per-cell best, Lagrangian money price grid)
CH = list(CHANNELS)
COST = np.array([CHANNELS[c]["cost_per_contact"] for c in CH], float)
MULT = np.array([CHANNELS[c]["conversion_multiplier"] for c in CH], float)


def oracle(tab, M, F, grid):
    keys = list(tab)
    pct = np.array([tab[k][0] for k in keys]); cv = np.array([tab[k][1] for k in keys])
    n = np.array([CELL.loc[k[:2], "n"] for k in keys], float); ms = np.array([CELL.loc[k[:2], "mass"] for k in keys])
    gross = pct[:, None] * np.minimum(1, cv[:, None] * MULT[None]) * ms[:, None]
    net = gross - n[:, None] * COST[None]
    best = None
    for lam in grid:
        adj = net - lam * n[:, None] * COST[None]
        j = adj.argmax(1)
        df = pd.DataFrame(dict(t=[k[0] for k in keys], s=[k[1] for k in keys], b=[k[2] for k in keys], n=n,
                               ch=j, adj=adj[np.arange(len(keys)), j], net=net[np.arange(len(keys)), j]))
        df = df[df.net > 0].sort_values(["adj", "b"], ascending=[False, True]).drop_duplicates(["t", "s"])
        df = df.assign(pc=df.adj / df.n).sort_values("pc", ascending=False)
        R, Bm, pick = 15_000, 100_000.0, []
        for r in df.itertuples():
            if r.n <= R and r.n * COST[r.ch] <= Bm:
                R -= r.n; Bm -= r.n * COST[r.ch]; pick.append(r)
        grp = {}
        for r in pick:
            grp.setdefault((r.b, CH[r.ch], r.s), []).append(r)
        camps = []
        for k, v in grp.items():   # first-fit decreasing into <=5000-subscriber campaigns
            bins = []
            for x in sorted(v, key=lambda x: -x.n):
                b = next((b for b in bins if sum(y.n for y in b) + x.n <= 5000), None)
                (b.append(x) if b is not None else bins.append([x]))
            camps += [dict(v=sum(x.net for x in b), campaign_name=f"o{len(camps)}_{j}", filter_arpu_segment=k[2],
                           filter_current_tariff=";".join(sorted(x.t for x in b)), target_tariff=k[0], channel=k[1],
                           n=sum(x.n for x in b)) for j, b in enumerate(bins)]
        camps.sort(key=lambda c: -c["v"])
        camps = camps[:10]
        r = score([{k: v for k, v in c.items() if k not in ("v", "n")} for c in camps], M, F)
        if best is None or r["net"] > best["net"]:
            best = dict(r, lam=lam, ch={c: int(sum(x["n"] for x in camps if x["channel"] == c)) for c in CH}, groups=len(grp))
    return best


# ---------------------------------------------------------------- main
v200 = A.NOISE_SD / 0.65 / np.sqrt(200)
print(f"200-sms pilot noise sd in base units {v200:.4f}; weight vs PRIOR_SD {A.PRIOR_SD}: {A.PRIOR_SD**2/(A.PRIOR_SD**2+v200**2):.4f}; "
      f"posterior sd after one pilot {(1/A.PRIOR_SD**2+1/v200**2)**-0.5:.4f}")
print("cell sizes: " + ", ".join(f"{k} n={int(CELL.loc[k, 'n'])}" for k in [("tariff_8", "HIGH"), ("tariff_11", "HIGH")]))

# local_eval reproduction (S0) --------------------------------------------------
import local_eval  # noqa: E402
os.chdir(P)
le = []
for s in SEEDS:
    with contextlib.redirect_stdout(io.StringIO()):
        le.append(local_eval.evaluate_agent(A.Agent(verbose=False), seed=s, verbose=False)["net_arpu_gain"])
le = pd.Series(le)
print(f"local_eval seeds 0-9: median {le.median():,.0f} min {le.min():,.0f} max {le.max():,.0f} pos {(le > 0).sum()}/10")

rows, diag = [], {}
GRID_A = [0, 0.5, 1, 2, 4, 8, 16, 1e9]
GRID_B = sorted(set(GRID_A + list(np.round(np.arange(0, 40.01, 0.25), 2))))
for sc in SCEN:
    M, F = scenario(sc)
    tab = truth(M, F)
    oa, ob = oracle(tab, M, F, GRID_A), oracle(tab, M, F, GRID_B)
    print(f"\n[{sc}] oracle (analyst grid) net {oa['net']:,.0f} contacts {oa['contacts']:,} cost {oa['cost']:,.0f} lam {oa['lam']} "
          f"ch {oa['ch']} groups {oa['groups']} | finer grid net {ob['net']:,.0f} lam {ob['lam']} ch {ob['ch']}")
    allabs = pd.DataFrame([(k[1], abs(p * c)) for k, (p, c) in tab.items()], columns=["seg", "v"])
    print("  median |pct x conv| all (cell,target): " + ", ".join(f"{k} {v:.4f}" for k, v in allabs.groupby("seg").v.median().items()))
    diag[sc] = []
    for seed in SEEDS:
        for kind in ["agent", "noexp", "template", "confirm", "slope"]:
            if kind in ("confirm", "slope") and sc == "S4" and seed > 2:
                continue
            r, ag, pil = run(kind, M, F, seed)
            rows.append(dict(sc=sc, seed=seed, kind=kind, oracle=oa["net"], **r, slope=getattr(ag, "slope", np.nan)))
            if r["crash"]:
                print(f"  CRASH {kind} seed {seed}: {r['crash']}")
            if kind == "agent":
                pl = pd.DataFrame(ag.records)
                pl["true"] = [lift(tab, (a, b, c), "sms") / 0.65 for a, b, c in zip(pl.tariff, pl.seg, pl.target)]
                pl["z"] = pl["true"] * 0.65 / (0.804 / np.sqrt(pl.n))
                u = units_of(ag, tab)
                diag[sc].append(dict(seed=seed, pl=pl, u=u, bias=(ag.calibration or {}).get("bias", np.nan),
                                     pred=sum(c["value"] for c in ag.plan_detail), fin=r["fin_net"], h=ag.hyps))
            if kind == "noexp" and seed == 0:
                ne_u = units_of(ag, tab)
                pre = pd.DataFrame(ag.pre_units)
                ngroups = pre.groupby(["target", "channel", "seg", pre["data"].fillna("ALL")]).ngroups
                print(f"  noexp plan: {len(ag.plan_detail)} campaigns, pre-truncation units {len(pre)} in {ngroups} "
                      f"(target,channel,seg,data) groups; units dropped by 10-campaign cut: "
                      f"{len(pre) - len(ne_u)}, their contacts {int(pre.n.sum() - ne_u.n.sum())}")
                top = ne_u.assign(mu0=[ag.hyps.set_index(['tariff', 'seg', 'target']).loc[k, 'mu0'] for k in ne_u.key])
                top = top.assign(pm=top.mu0 * top.mass).sort_values("pm", ascending=False).head(5)
                zs = [lift(tab, k, "sms") / (0.804 / np.sqrt(200)) for k in top.key]
                print("  noexp top-5 units: " + "; ".join(f"{k[0]}/{k[1]}->{k[2]} z {z:+.2f}" for k, z in zip(top.key, zs))
                      + f" | median |z| {np.median(np.abs(zs)):.2f}")

R = pd.DataFrame(rows)
R.drop(columns=["crash"]).to_csv(os.path.join(P, "analysis", "f1v_runs.csv"), index=False)
print("\n=== net by scenario x strategy (seeds 0-9; S4 confirm/slope seeds 0-2 only) ===")
for sc in SCEN:
    a = R[(R.sc == sc) & (R.kind == "agent")].set_index("seed")
    for k in ["agent", "noexp", "template", "confirm", "slope"]:
        x = R[(R.sc == sc) & (R.kind == k)].set_index("seed")
        extra = f" beats agent {(x.net > a.net.loc[x.index]).sum()}/{len(x)}" if k != "agent" else ""
        extra += f" slope med {x.slope.median():+.2f}" if k == "slope" else ""
        print(f"{sc} {k:<9} median {x.net.median():>12,.0f} min {x.net.min():>12,.0f} max {x.net.max():>12,.0f} "
              f"pos {(x.net > 0).sum()}/{len(x)} share {x.net.median() / x.oracle.iloc[0]:+.3f} pilots {x.n_pil.median():.0f} "
              f"contacts {x.contacts.median():,.0f} money {x.cost.median():,.0f} pilot_net {x.pilot_net.median():,.0f}{extra}")

print("\n=== agent diagnostics (pooled over seeds) ===")
for sc in SCEN:
    D = diag[sc]
    pl = pd.concat([x["pl"] for x in D]); U = pd.concat([x["u"] for x in D])
    T, N = U[U.tested], U[~U.tested]
    h_all = pd.concat([x["h"] for x in D])
    print(f"{sc}: pilots HIGH {(pl.seg == 'HIGH').mean():.3f}, |z| med {pl.z.abs().median():.2f}, |z|<1 {(pl.z.abs() < 1).mean():.3f}, "
          f"true<0 {(pl.true < 0).mean():.3f}; bias med {np.nanmedian([x['bias'] for x in D]):+.3f}; "
          f"pred {np.median([x['pred'] for x in D]):,.0f} vs finals realized {np.median([x['fin'] for x in D]):,.0f}; "
          f"tested money share {T.money.sum() / U.money.sum():.3f}; real/contact tested {T.real.sum() / T.n.sum():.1f} "
          f"untested {N.real.sum() / N.n.sum():.1f}; untested true<=0 realized per run median "
          f"{np.median([x['u'].loc[~x['u'].tested & (x['u'].base <= 0), 'real'].sum() for x in D]):,.0f}")
    # final plan sd asymmetry (why tested near-zero cells beat untested prior winners)
    hh = h_all.assign(tested=h_all.n_obs > 0)
    print(f"   hypotheses: median sd tested {hh.loc[hh.tested, 'sd'].median():.3f} untested {hh.loc[~hh.tested, 'sd'].median():.3f} "
          f"-> KAPPA*sd penalty {A.KAPPA * hh.loc[hh.tested, 'sd'].median():.3f} vs {A.KAPPA * hh.loc[~hh.tested, 'sd'].median():.3f}")

# S0 seed 6 detail
x = [x for x in diag["S0"] if x["seed"] == 6][0]
p = x["pl"]; p = p[(p.tariff == "tariff_8") & (p.seg == "HIGH") & (p.target == "tariff_10")].iloc[0]
u = x["u"]
print(f"\nS0 seed 6: tariff_8/HIGH->tariff_10 prior {p.prior_mu:+.3f} obs {p.observed / 0.65:+.3f} post {p.post_mu:+.3f} true {p.true:+.3f}; "
      f"final money tested {u[u.tested].money.sum():,.0f} untested {u[~u.tested].money.sum():,.0f}; agent net "
      f"{R[(R.sc == 'S0') & (R.seed == 6) & (R.kind == 'agent')].net.iloc[0]:,.0f}")
