"""f1: robustness backtest of agent.py under perturbed effect models (LOCAL VALIDATION ONLY).

Mirrors local_eval.evaluate_agent, but with our own impact model M and fallback F per scenario.
Strategies: agent (as submitted), agent without pilots, agent_template, do-nothing (0), oracle-lite.
Run:  python3 analysis/f1_robustness.py            (8 scenarios x seeds 0-9)
      python3 analysis/f1_robustness.py --quick    (S0 + S7, seeds 0-1, for a smoke test)
"""
import contextlib
import io
import os
import sys
import time

import numpy as np
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, P)

import agent as agent_mod          # noqa: E402
import agent_template              # noqa: E402
import environment                 # noqa: E402
import mock_environment as mock    # noqa: E402
from scoring_core import MAX_CAMPAIGNS, MAX_CUSTOMERS_PER_CAMPAIGN, sanitize_campaigns, score_campaigns  # noqa: E402

QUICK = "--quick" in sys.argv
SEEDS = range(2) if QUICK else range(10)
CHANNELS, BUDGET, REACH = mock.CHANNELS, mock.TOTAL_BUDGET, mock.MAX_TOTAL_CONTACTS
CH = list(CHANNELS)
COST = np.array([CHANNELS[c]["cost_per_contact"] for c in CH], float)
MULT = np.array([CHANNELS[c]["conversion_multiplier"] for c in CH], float)
FILTER_COLS = ["filter_arpu_segment", "filter_data_segment", "filter_call_segment", "filter_current_tariff"]

profile = pd.read_csv(os.path.join(P, "customer_profile.csv"))
dict_tariff = pd.read_csv(os.path.join(P, "data", "dict_tariff.csv"))
M0 = mock._mock_impact_model(pd.read_csv(os.path.join(P, "data", "change_tariff.csv")))
F0 = mock._mock_fallback
BASELINE = profile["predicted_arpu"].sum()
TARGETS = sorted(dict_tariff["tariff_plan_code"])

valid = profile.dropna(subset=["current_tariff", "arpu_segment"])
CELLS = (valid.groupby(["current_tariff", "arpu_segment"]).agg(n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum"))
         .reset_index().rename(columns={"current_tariff": "tariff", "arpu_segment": "seg"}))
CELL_STATS = {(t, s): (n, m) for t, s, n, m in CELLS.itertuples(index=False)}
SUB_STATS = {k: (int(v["n"]), float(v["mass"])) for k, v in
             valid.dropna(subset=["data_segment"]).groupby(["current_tariff", "arpu_segment", "data_segment"])
             .agg(n=("ID_NUMBER", "size"), mass=("predicted_arpu", "sum")).iterrows()}


# ------------------------------------------------------------------ scenarios
def wrap(g):
    def F(cur, tgt, seg, dt, fc):
        pct, conv = F0(cur, tgt, seg, dt, fc)
        return g(pct), conv
    return F


def scenarios():
    pct = M0["arpu_change_pct"]
    med = float(pct.median())
    rev = M0.copy()
    for _, idx in rev.groupby(["tariff_plan_code_from", "arpu_segment"], observed=True).groups.items():
        s = rev.loc[idx, "arpu_change_pct"].sort_values(kind="mergesort")
        rev.loc[s.index, "arpu_change_pct"] = s.values[::-1]
    perm = M0.assign(arpu_change_pct=np.random.default_rng(2026).permutation(pct.values))
    print(f"M0 rows {len(M0)}; median arpu_change_pct {med:+.4f}; median conversion {M0['conversion_rate'].median():.4f}")
    S = {
        "S0 mock": (M0, F0),
        "S1 x0.5": (M0.assign(arpu_change_pct=pct * 0.5), wrap(lambda x: x * 0.5)),
        "S2 x2": (M0.assign(arpu_change_pct=pct * 2), wrap(lambda x: x * 2)),
        "S3 downsell": (M0.assign(arpu_change_pct=pct - med), wrap(lambda x: x - med)),
        "S4 reversed": (rev, F0),
        "S5 permuted": (perm, F0),
        "S6 conv x3": (M0.assign(conversion_rate=M0["conversion_rate"] * 3), F0),
        "S7 sign flip": (M0.assign(arpu_change_pct=-pct), wrap(lambda x: -x)),
    }
    if QUICK:
        S = {k: S[k] for k in ("S0 mock", "S7 sign flip")}
    for k, (M, _) in S.items():
        print(f"  {k:<13} share of model rows with arpu_change_pct<0: {(M['arpu_change_pct'] < 0).mean():.3f}")
    return S


# ------------------------------------------------------------------ truth / scoring
def truth(M, F):
    """(tariff, seg, target) -> (pct, conv) exactly as the scorer resolves it (model row, else fallback)."""
    fc = M["conversion_rate"].median()
    d = {k: (a, b) for k, a, b in zip(zip(M["tariff_plan_code_from"], M["arpu_segment"].astype(str),
                                          M["tariff_plan_code_to"]), M["arpu_change_pct"], M["conversion_rate"])}
    rows = []
    for t, s, n, m in CELLS.itertuples(index=False):
        for g in TARGETS:
            if g == t:
                continue
            pct, cv = d[(t, s, g)] if (t, s, g) in d else F(t, g, s, dict_tariff, fc)
            rows.append((t, s, g, float(pct), float(cv), int(n), float(m)))
    T = pd.DataFrame(rows, columns=["tariff", "seg", "target", "pct", "conv", "n", "mass"])
    return T, {(t, s, g): (p, c) for t, s, g, p, c in zip(T.tariff, T.seg, T.target, T.pct, T.conv)}


def ratio(tab, key, ch):
    pct, cv = tab.get(key, (0.0, 0.0))
    return pct * min(1.0, cv * CHANNELS[ch]["conversion_multiplier"])


def score(camps, M, F):
    if not camps:
        return dict(net=0.0, gross=0.0, cost=0.0, contacts=0)
    df = pd.DataFrame(camps)
    for c in FILTER_COLS + ["explicit_ids"]:
        if c not in df.columns:
            df[c] = None
    r = score_campaigns(df, profile, M, dict_tariff, BASELINE, F)
    return dict(net=r["net_arpu_gain"], gross=r["gross_arpu_lift"], cost=r["total_cost"], contacts=r["total_contacts"])


# ------------------------------------------------------------------ oracle-lite
def oracle(T, M, F):
    """True effects, best (target, channel) per cell, greedy fill, <=10 campaigns, no pilots; best over a money-price grid."""
    gross = T["pct"].values[:, None] * np.minimum(1.0, T["conv"].values[:, None] * MULT[None, :]) * T["mass"].values[:, None]
    val = gross - T["n"].values[:, None] * COST[None, :]
    best = None
    for lam in [0, 0.5, 1, 2, 4, 8, 16, 1e9]:
        adj = gross - T["n"].values[:, None] * COST[None, :] * (1 + lam)
        c = adj.argmax(1)
        ar = np.arange(len(T))
        cand = T.assign(ch=c, adj=adj[ar, c], val=val[ar, c])
        cand = cand[cand["val"] > 0].sort_values(["adj", "target"], ascending=[False, True])
        cand = cand.drop_duplicates(["tariff", "seg"])
        cand = cand.assign(pc=cand["adj"] / cand["n"]).sort_values("pc", ascending=False)
        R, B, groups = REACH, BUDGET, {}
        for r in cand.itertuples():
            k = COST[r.ch] * r.n
            if r.n <= R and k <= B:
                R, B = R - r.n, B - k
                groups.setdefault((r.target, CH[r.ch], r.seg), []).append((r.n, r.val, r.tariff))
        camps = []
        for (tgt, ch, seg), us in groups.items():
            bins = []
            for n, v, t in sorted(us, key=lambda u: (-u[0], u[2])):
                for b in bins:
                    if b[0] + n <= MAX_CUSTOMERS_PER_CAMPAIGN:
                        b[0] += n; b[1] += v; b[2].append(t)
                        break
                else:
                    bins.append([n, v, [t]])
            camps += [dict(v=b[1], campaign_name=f"oracle_{tgt}_{ch}_{seg}_{i}", filter_arpu_segment=seg,
                           filter_current_tariff=";".join(sorted(b[2])), target_tariff=tgt, channel=ch)
                      for i, b in enumerate(bins)]
        camps = sorted(camps, key=lambda c: -c["v"])[:MAX_CAMPAIGNS]
        res = score([{k: v for k, v in c.items() if k != "v"} for c in camps], M, F)
        if best is None or res["net"] > best["net"]:
            best = dict(res, lam=lam, n_camps=len(camps),
                        ch_contacts={ch: sum(CELL_STATS[(t, c["filter_arpu_segment"])][0]
                                             for c in camps if c["channel"] == ch
                                             for t in c["filter_current_tariff"].split(";")) for ch in CH})
    return best


# ------------------------------------------------------------------ counterfactual (analysis only, agent.py untouched)
class ConfirmAgent(agent_mod.Agent):
    """Agent + 'confirm first': the first K pilots (sms, n=200) go to the hypotheses the plan leans on most
    (largest mu0 x cell mass), then the unchanged VOI loop runs on what is left of the SAME pilot money/reach caps."""
    K = 6

    def _run_pilots(self, env, h):
        m = float(env.channels["sms"]["conversion_multiplier"])
        spent = reached = 0
        for i in (h["mu0"] * h["mass"]).sort_values(ascending=False, kind="mergesort").index[:self.K]:
            r = h.loc[i]
            res = env.run_pilot(target_tariff=r["target"], channel="sms", n_customers=int(min(200, r["n"])),
                                filter_arpu_segment=r["seg"], filter_current_tariff=r["tariff"])
            n_act, y = int(res["n_customers"]), float(res["observed_lift_ratio"]) / m
            v = (agent_mod.NOISE_SD / m) ** 2 / n_act
            prec = 1 / h.loc[i, "sd"] ** 2 + 1 / v
            h.loc[i, "mu"] = (h.loc[i, "mu"] / h.loc[i, "sd"] ** 2 + y / v) / prec
            h.loc[i, "sd"] = float(np.sqrt(1 / prec))
            h.loc[i, "n_obs"] += n_act
            h.loc[i, "ysum"] += y * n_act
            spent, reached = spent + res["cost"], reached + n_act
            self.records.append(dict(tariff=r["tariff"], seg=r["seg"], target=r["target"], channel="sms", n=n_act,
                                     cost=res["cost"], observed=res["observed_lift_ratio"], prior_mu=r["mu0"],
                                     post_mu=h.loc[i, "mu"], post_sd=h.loc[i, "sd"]))
        old = agent_mod.PILOT_MONEY_SHARE, agent_mod.PILOT_REACH_SHARE
        agent_mod.PILOT_MONEY_SHARE = max(0.0, old[0] - spent / env.total_budget)
        agent_mod.PILOT_REACH_SHARE = max(0.0, old[1] - reached / env.max_total_contacts)
        try:
            super()._run_pilots(env, h)
        finally:
            agent_mod.PILOT_MONEY_SHARE, agent_mod.PILOT_REACH_SHARE = old


class SlopeAgent(ConfirmAgent):
    """ConfirmAgent + multiplicative calibration: untested mu = mu0 x b, where b is the n-weighted least-squares
    slope (through 0) of pilot-observed base effect on mu0. Catches scale (x0.5, x2) and sign errors of the prior."""

    def _calibrate(self, h):
        super()._calibrate(h)
        t = h["n_obs"] > 0
        w = (h.loc[t, "n_obs"] * h.loc[t, "mu0"] ** 2).sum()
        if t.sum() < 3 or w <= 0:
            return
        b = float(np.clip((h.loc[t, "ysum"] * h.loc[t, "mu0"]).sum() / w, -2, 3))
        h.loc[~t, "mu"] = h.loc[~t, "mu0"] * b
        self.calibration = dict(self.calibration or {}, slope=b)


# ------------------------------------------------------------------ one evaluation (mirrors local_eval)
@contextlib.contextmanager
def no_pilots(on):
    old = agent_mod.PILOT_MONEY_SHARE
    if on:
        agent_mod.PILOT_MONEY_SHARE = 0
    try:
        yield
    finally:
        agent_mod.PILOT_MONEY_SHARE = old


def evaluate(kind, M, F, seed):
    env, internals = environment.make_environment(
        profile, impact_model=M, dict_tariff=dict_tariff, channels=CHANNELS, total_budget=BUDGET,
        max_total_contacts=REACH, fallback_predict=F, seed=seed)
    ag = (agent_template.Agent() if kind == "template" else ConfirmAgent(verbose=False) if kind == "confirm" else
          SlopeAgent(verbose=False) if kind == "slope" else agent_mod.Agent(verbose=False))
    crash = None
    with no_pilots(kind == "noexp"), contextlib.redirect_stdout(io.StringIO()):
        try:
            finals = ag.act(env)
        except Exception as e:  # mirror local_eval: a crash keeps the pilots, drops the finals
            finals, crash = [], f"{type(e).__name__}: {e}"
        finals = sanitize_campaigns(finals, env.tariffs)[:MAX_CAMPAIGNS]
    pilots = internals.executed_pilot_campaigns()
    res = score(pilots + finals, M, F)
    res.update(n_pilots=len(pilots), n_finals=len(finals), crash=crash,
               pilot_net=score(pilots, M, F)["net"] if pilots else 0.0,
               slope=(getattr(ag, "calibration", None) or {}).get("slope", float("nan")))
    return res, ag, pilots


def diagnose(ag, pilots, tab, M, F):
    """Per-pilot prior/observed/posterior vs truth; per-unit realized value of the plan (tested vs untested)."""
    m_ref = CHANNELS["sms"]["conversion_multiplier"]
    prec = []
    for r in ag.records:
        key = (r["tariff"], r["seg"], r["target"])
        prec.append(dict(key="/".join(key), prior=r["prior_mu"], obs=r["observed"] / m_ref, post=r["post_mu"],
                         true=ratio(tab, key, "sms") / m_ref, n=r["n"], cost=r["cost"], high=r["seg"] == "HIGH",
                         z=ratio(tab, key, "sms") / (0.804 / np.sqrt(r["n"]))))
    tested, hmu = set(), {}
    if hasattr(ag, "hyps"):
        h = ag.hyps
        tested = set(zip(h.loc[h["n_obs"] > 0, "tariff"], h.loc[h["n_obs"] > 0, "seg"], h.loc[h["n_obs"] > 0, "target"]))
        hmu = {k: (a, b) for k, a, b in zip(zip(h["tariff"], h["seg"], h["target"]), h["mu0"], h["mu"])}
    units = []
    for c in ag.plan_detail:
        seg, d, tgt, ch = c["filter_arpu_segment"], c["filter_data_segment"], c["target_tariff"], c["channel"]
        for t in c["filter_current_tariff"].split(";"):
            n, mass = CELL_STATS.get((t, seg), (0, 0.0)) if d is None else SUB_STATS.get((t, seg, d), (0, 0.0))
            mu0, mu = hmu.get((t, seg, tgt), (float("nan"), float("nan")))
            units.append(dict(key=f"{t}/{seg}/{d or 'ALL'}->{tgt}", tested=(t, seg, tgt) in tested, channel=ch, n=n,
                              mu0=mu0, mu=mu, true=ratio(tab, (t, seg, tgt), "push") / 0.5, mass=mass,
                              z200=ratio(tab, (t, seg, tgt), "sms") / (0.804 / np.sqrt(200)),
                              money=n * CHANNELS[ch]["cost_per_contact"],
                              real=ratio(tab, (t, seg, tgt), ch) * mass - n * CHANNELS[ch]["cost_per_contact"]))
    pilot_only = score(pilots, M, F)["net"] if pilots else 0.0
    return dict(pilots=prec, units=units, predicted=sum(c["value"] for c in ag.plan_detail),
                finals_real=score(ag.plan_detail and [{k: v for k, v in c.items() if k not in ("n", "cost", "value")}
                                                       for c in ag.plan_detail] or [], M, F)["net"],
                pilot_net=pilot_only, bias=(ag.calibration or {}).get("bias", float("nan")))


# ------------------------------------------------------------------ main
def main():
    t0 = time.time()
    rows, diags, oracles, noexp_units = [], {}, {}, {}
    for sname, (M, F) in scenarios().items():
        T, tab = truth(M, F)
        orc = oracle(T, M, F)
        oracles[sname] = orc
        print(f"\n[{sname}] oracle-lite net {orc['net']:,.0f} (gross {orc['gross']:,.0f}, cost {orc['cost']:,.0f}, "
              f"contacts {orc['contacts']:,}, campaigns {orc['n_camps']}, money price {orc['lam']}); "
              f"oracle contacts by channel {orc['ch_contacts']}")
        pos_true = T.assign(v=T["pct"] * np.minimum(1, T["conv"] * 0.5) * T["mass"])
        print(f"  cells with a positive push target: {int((pos_true.groupby(['tariff', 'seg'])['v'].max() > 0).sum())} of {len(CELLS)}")
        scale = (T["pct"] * T["conv"]).abs().groupby(T["seg"]).median()
        print("  median |true base effect pct x conv| over all (cell, target) by segment: "
              + ", ".join(f"{k} {v:.4f}" for k, v in scale.items()))
        diags[sname] = []
        for seed in SEEDS:
            line = {}
            for kind in ("agent", "noexp", "template", "confirm", "slope"):
                res, ag, pilots = evaluate(kind, M, F, seed)
                rows.append(dict(scenario=sname, seed=seed, strategy=kind, **{k: v for k, v in res.items()}))
                line[kind] = res
                if kind == "agent":
                    dg = diagnose(ag, pilots, tab, M, F)
                    dg.update(seed=seed, net=res["net"])
                    diags[sname].append(dg)
                if kind == "noexp" and seed == SEEDS[0]:   # deterministic plan: identical for every seed
                    noexp_units[sname] = diagnose(ag, pilots, tab, M, F)["units"]
                if res["crash"]:
                    print(f"  !! {kind} crashed seed {seed}: {res['crash']}")
            rows.append(dict(scenario=sname, seed=seed, strategy="nothing", net=0.0, gross=0.0, cost=0.0, contacts=0,
                             n_pilots=0, n_finals=0, crash=None, pilot_net=0.0))
            rows.append(dict(scenario=sname, seed=seed, strategy="oracle", net=orc["net"], gross=orc["gross"],
                             cost=orc["cost"], contacts=orc["contacts"], n_pilots=0, n_finals=orc["n_camps"], crash=None,
                             pilot_net=0.0))
            a = line["agent"]
            print(f"  seed {seed}: agent {a['net']:>12,.0f} (pilots {a['n_pilots']:2d}, finals {a['n_finals']:2d}, "
                  f"contacts {a['contacts']:>6,}, money {a['cost']:>8,.0f}) | noexp {line['noexp']['net']:>12,.0f} | "
                  f"template {line['template']['net']:>12,.0f} | confirm {line['confirm']['net']:>12,.0f} | "
                  f"slope {line['slope']['net']:>12,.0f} | {time.time() - t0:5.0f}s")

    R = pd.DataFrame(rows)
    R.drop(columns=["crash"]).to_csv(os.path.join(P, "analysis", "f1_runs.csv"), index=False)
    order = list(oracles)
    strat = ["agent", "noexp", "template", "nothing", "oracle", "confirm", "slope"]
    v200 = agent_mod.NOISE_SD / CHANNELS["sms"]["conversion_multiplier"] / np.sqrt(200)
    print(f"\nagent constants: 200-sms pilot noise sd in base units {v200:.4f}; prior sd {agent_mod.PRIOR_SD}; "
          f"weight a single 200-pilot gets vs the prior {agent_mod.PRIOR_SD ** 2 / (agent_mod.PRIOR_SD ** 2 + v200 ** 2):.3f}")

    print("\n=== TABLE A: net by scenario x strategy (seeds %d-%d) ===" % (SEEDS[0], SEEDS[-1]))
    print(f"{'scenario':<13} {'strategy':<9} {'median':>12} {'min':>12} {'max':>12} {'pos/10':>6}")
    for s in order:
        for k in strat:
            x = R[(R.scenario == s) & (R.strategy == k)]["net"]
            print(f"{s:<13} {k:<9} {x.median():>12,.0f} {x.min():>12,.0f} {x.max():>12,.0f} {int((x > 0).sum()):>3}/{len(x)}")

    print("\n=== TABLE B: agent usage and share of oracle ===")
    print(f"{'scenario':<13} {'pilots':>6} {'contacts':>9} {'money':>9} {'finals':>6} {'agent_med':>12} {'oracle':>12} "
          f"{'share':>7} {'noexp_share':>11} {'agent<noexp':>11}")
    share_rows = []
    for s in order:
        a = R[(R.scenario == s) & (R.strategy == "agent")].set_index("seed")
        ne = R[(R.scenario == s) & (R.strategy == "noexp")].set_index("seed")
        o = oracles[s]["net"]
        sh, shn = a["net"].median() / o, ne["net"].median() / o
        worse = int((a["net"] < ne["net"]).sum())
        share_rows.append(dict(scenario=s, agent_share=round(sh, 4), noexp_share=round(shn, 4)))
        print(f"{s:<13} {a['n_pilots'].median():>6.1f} {a['contacts'].median():>9,.0f} {a['cost'].median():>9,.0f} "
              f"{a['n_finals'].median():>6.1f} {a['net'].median():>12,.0f} {o:>12,.0f} {sh:>7.3f} {shn:>11.3f} {worse:>8}/10"
              f"   | noexp contacts {ne['contacts'].median():,.0f} money {ne['cost'].median():,.0f}")
        for k in ("confirm", "slope"):
            cf = R[(R.scenario == s) & (R.strategy == k)].set_index("seed")
            print(f"{'':<13} counterfactual {k:<7}: median {cf['net'].median():,.0f} min {cf['net'].min():,.0f} "
                  f"share {cf['net'].median() / o:.3f} pos {int((cf['net'] > 0).sum())}/10 beats agent "
                  f"{int((cf['net'] > a['net']).sum())}/10 beats noexp {int((cf['net'] > ne['net']).sum())}/10 "
                  f"pilots {cf['n_pilots'].median():.1f} contacts {cf['contacts'].median():,.0f} money {cf['cost'].median():,.0f} "
                  f"pilot-only net {cf['pilot_net'].median():,.0f} (agent {a['pilot_net'].median():,.0f})"
                  + (f" median slope b {cf['slope'].median():+.2f}" if k == "slope" else ""))

    print("\n=== TABLE C: agent diagnostics (pooled over seeds) ===")
    print(f"{'scenario':<13} {'|prior-true|':>12} {'|post-true|':>11} {'sign_ok':>7} {'pilot_true<0':>12} {'bias_med':>8} "
          f"{'pilot_net':>10} {'pred_plan':>12} {'real_finals':>12} {'tested_ctc':>10} {'tested_mny':>10} "
          f"{'real/ctc_T':>10} {'real/ctc_U':>10}")
    for s in order:
        D = diags[s]
        pl = pd.DataFrame([p for d in D for p in d["pilots"]])
        un = pd.DataFrame([u for d in D for u in d["units"]])
        if len(pl):
            e_prior = (pl.prior - pl.true).abs().median()
            e_post = (pl.post - pl.true).abs().median()
            sign_ok = (np.sign(pl.post) == np.sign(pl.true)).mean()
            neg = (pl.true < 0).mean()
        else:
            e_prior = e_post = sign_ok = neg = float("nan")
        if len(un):
            tctc = un.loc[un.tested, "n"].sum() / max(un["n"].sum(), 1)
            tmon = un.loc[un.tested, "money"].sum() / max(un["money"].sum(), 1)
            rT = un.loc[un.tested, "real"].sum() / max(un.loc[un.tested, "n"].sum(), 1)
            rU = un.loc[~un.tested, "real"].sum() / max(un.loc[~un.tested, "n"].sum(), 1)
        else:
            tctc = tmon = rT = rU = float("nan")
        print(f"{s:<13} {e_prior:>12.3f} {e_post:>11.3f} {sign_ok:>7.3f} {neg:>12.3f} "
              f"{np.nanmedian([d['bias'] for d in D]):>+8.3f} {np.median([d['pilot_net'] for d in D]):>10,.0f} "
              f"{np.median([d['predicted'] for d in D]):>12,.0f} {np.median([d['finals_real'] for d in D]):>12,.0f} "
              f"{tctc:>10.3f} {tmon:>10.3f} {rT:>10.1f} {rU:>10.1f}")
        if len(un):
            mix = un.groupby("channel")["n"].sum() / un["n"].sum()
            print(f"   final-contact channel mix: " + ", ".join(f"{k} {v:.3f}" for k, v in mix.items()))

    print("\n=== TABLE D: where pilots go vs what the plan relies on (agent, pooled over seeds) ===")
    print("  z = true sms lift ratio / (0.804/sqrt(n)): expected z-score of the pilot signal; |z|<1 = pilot mostly measures noise")
    print(f"{'scenario':<13} {'pil_HIGH':>8} {'pil_|z|med':>10} {'pil_|z|<1':>9} {'pil_ctc':>7} {'pil_money':>9} "
          f"{'FP_units':>8} {'FP_real':>10} {'untestNeg_real':>14} {'plan_top5_|z200|':>16}")
    for s in order:
        D = diags[s]
        pl = pd.DataFrame([p for d in D for p in d["pilots"]])
        fp_n = [sum(1 for u in d["units"] if u["tested"] and u["true"] <= 0) for d in D]
        fp_r = [sum(u["real"] for u in d["units"] if u["tested"] and u["true"] <= 0) for d in D]
        un_r = [sum(u["real"] for u in d["units"] if not u["tested"] and u["true"] <= 0) for d in D]
        top = sorted(noexp_units[s], key=lambda u: -u["mu0"] * u["mass"])[:5]
        print(f"{s:<13} {pl['high'].mean():>8.3f} {pl['z'].abs().median():>10.2f} {(pl['z'].abs() < 1).mean():>9.3f} "
              f"{np.median([sum(p['n'] for p in d['pilots']) for d in D]):>7,.0f} "
              f"{np.median([sum(p['cost'] for p in d['pilots']) for d in D]):>9,.0f} "
              f"{np.median(fp_n):>8.1f} {np.median(fp_r):>10,.0f} {np.median(un_r):>14,.0f} "
              f"{np.median([abs(u['z200']) for u in top]):>16.2f}")
    print("  no-exploration plan: top-5 units by prior mass-weighted effect (same prior in every scenario), true base effect / z of a 200-sms pilot:")
    for s in order:
        top = sorted(noexp_units[s], key=lambda u: -u["mu0"] * u["mass"])[:5]
        print(f"   {s:<13} " + "; ".join(f"{u['key']} mu0 {u['mu0']:+.3f} true {u['true']:+.3f} z {u['z200']:+.1f}" for u in top))

    print("\n=== FAILURE MODES: agent net < 0, or agent < no-exploration ===")
    for s in order:
        a = R[(R.scenario == s) & (R.strategy == "agent")].set_index("seed")
        ne = R[(R.scenario == s) & (R.strategy == "noexp")].set_index("seed")
        shortfall = a["net"] - np.maximum(ne["net"], 0.0)   # vs the better of no-exploration and doing nothing
        worst = int(shortfall.idxmin())
        for d in diags[s]:
            sd = d["seed"]
            if a.loc[sd, "net"] < 0 or a.loc[sd, "net"] < ne.loc[sd, "net"]:
                if sd == worst:   # one detailed dump per scenario (worst seed): pilots and the 6 biggest units by |realized|
                    print(f"  --- detail {s} worst seed {sd} (base units = pct x conv; true for units at multiplier 1) ---")
                    for p in d["pilots"]:
                        print(f"    pilot {p['key']:<26} n={p['n']:3d} prior {p['prior']:+.3f} obs {p['obs']:+.3f} "
                              f"post {p['post']:+.3f} true {p['true']:+.3f}")
                    for u in sorted(d["units"], key=lambda u: -abs(u["real"]))[:6]:
                        print(f"    unit  {u['key']:<32} {u['channel']:<11} n={u['n']:5d} tested={u['tested']!s:<5} "
                              f"mu0 {u['mu0']:+.3f} mu {u['mu']:+.3f} true {u['true']:+.3f} money {u['money']:>7,.0f} "
                              f"realized {u['real']:>11,.0f}")
                un = pd.DataFrame(d["units"]) if d["units"] else pd.DataFrame(columns=["tested", "real", "n", "money"])
                print(f"  {s:<13} seed {sd}: agent {a.loc[sd, 'net']:>11,.0f} noexp {ne.loc[sd, 'net']:>11,.0f} "
                      f"gap {a.loc[sd, 'net'] - ne.loc[sd, 'net']:>+11,.0f} | pilot_net {d['pilot_net']:>9,.0f} "
                      f"bias {d['bias']:+.3f} | finals predicted {d['predicted']:>11,.0f} realized {d['finals_real']:>11,.0f} "
                      f"(tested {un.loc[un.tested.astype(bool), 'real'].sum():>10,.0f}, untested "
                      f"{un.loc[~un.tested.astype(bool), 'real'].sum():>10,.0f}) money tested "
                      f"{un.loc[un.tested.astype(bool), 'money'].sum():>7,.0f} untested {un.loc[~un.tested.astype(bool), 'money'].sum():>7,.0f}")

    print("\nCHART grouped-bar medians:")
    med = R.groupby(["scenario", "strategy"])["net"].median().reset_index()
    print(med.to_json(orient="records"))
    print("CHART agent share of oracle:")
    print(pd.DataFrame(share_rows).to_json(orient="records"))
    print(f"\ntotal runtime {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
