"""e1v: re-run strategies on the mock and re-derive the seed-42 regret numbers (verifier for e1-06..e1-11).

All nets come from the public local_eval.evaluate_agent (pilots included). Counterfactuals that break
the 10-campaign rule are scored with my own scorer (e1v_oracle.my_score) and labelled as such.
agent.py is imported, never modified; any module constant patched is restored in `finally`.

Run:  python3 analysis/e1v_runs.py
"""
import itertools
import math
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, P)
os.chdir(P)   # local_eval / mock_environment read data via relative paths

from e1v_effects import lp_bound  # noqa: E402
from e1v_oracle import my_score, oracle, setup  # noqa: E402
import agent as A  # noqa: E402
import agent_template  # noqa: E402
from local_eval import evaluate_agent  # noqa: E402
from mock_environment import make_mock_env  # noqa: E402

ct, dt, prof, E = setup()
BASE = E.set_index(["cur", "seg", "tgt"])["base"]


def run(agent, seed):
    res = evaluate_agent(agent, seed=seed, verbose=False)
    return (res["net_arpu_gain"] if res else 0.0), (res["n_pilots"] if res else 0), res


class NoPilots:
    """Independent no-exploration variant: the env simply offers zero pilots."""
    def act(self, env):
        env.pilots_left = 0
        self.a = A.Agent(verbose=False)
        return self.a.act(env)


class NoPilotShare:
    """Second variant, as the analyst did it: PILOT_MONEY_SHARE = 0."""
    def act(self, env):
        old = A.PILOT_MONEY_SHARE
        A.PILOT_MONEY_SHARE = 0
        try:
            self.a = A.Agent(verbose=False)
            return self.a.act(env)
        finally:
            A.PILOT_MONEY_SHARE = old


class TrueEffects:
    """Agent planner (_plan/_build) fed the true base effect for EVERY target, sd ~ 0, no pilots."""
    def act(self, env):
        a = A.Agent(verbose=False)
        a.cost = {c: float(v["cost_per_contact"]) for c, v in env.channels.items()}
        cells = a._cells(env.customer_profile)
        rows = []
        for c in cells.itertuples():
            for t in sorted(env.tariffs["tariff_plan_code"]):
                if t != c.tariff:
                    b = float(BASE[(c.tariff, c.seg, t)])
                    rows.append(dict(tariff=c.tariff, seg=c.seg, target=t, n=int(c.n), mass=float(c.mass),
                                     avg=float(c.avg), mu0=b, sd0=1e-9, mu=b, sd=1e-9, n_obs=0, ysum=0.0))
        self.a = a
        return a._plan(env, env.customer_profile, pd.DataFrame(rows))


class Template:
    def act(self, env):
        try:
            return agent_template.Agent().act(env)
        except Exception as ex:   # evaluate_agent would swallow this; record it
            self.crash = repr(ex)
            raise


def with_max_campaigns(k, fn):
    old = A.MAX_CAMPAIGNS
    A.MAX_CAMPAIGNS = k
    try:
        return fn()
    finally:
        A.MAX_CAMPAIGNS = old


def cell_net(camps):
    """Per (cur, seg): net = best lift - all contact costs of its subscribers; dominant target/channel."""
    look = {c: E.set_index(["cur", "seg", "tgt"])["r_" + c] for c in ["push", "sms", "digital_ads", "call"]}
    cost = {"push": 0, "sms": 4, "digital_ads": 22, "call": 160}
    R, Bm, parts = 15000, 100000.0, []
    for cp in camps:
        s = prof
        ids = cp.get("explicit_ids")
        if isinstance(ids, list) and ids:
            s = s[s.ID_NUMBER.isin(ids)]
        else:
            if cp.get("filter_arpu_segment") is not None:
                s = s[s.arpu_segment == cp["filter_arpu_segment"]]
            if cp.get("filter_data_segment") is not None:
                s = s[s.data_segment == cp["filter_data_segment"]]
            if cp.get("filter_current_tariff") is not None:
                s = s[s.current_tariff.isin(cp["filter_current_tariff"].split(";"))]
        s = s.sort_values("ID_NUMBER").iloc[:5000].iloc[:max(R, 0)]
        k = cost[cp["channel"]]
        if k:
            s = s.iloc[:int(Bm // k)]
        R -= len(s)
        Bm -= len(s) * k
        key = pd.MultiIndex.from_arrays([s.current_tariff, s.arpu_segment, [cp["target_tariff"]] * len(s)])
        parts.append(pd.DataFrame(dict(ID=s.ID_NUMBER.values, cur=s.current_tariff.values, seg=s.arpu_segment.values,
                                       lift=look[cp["channel"]].reindex(key).fillna(0).values * s.predicted_arpu.values,
                                       cost=float(k), tgt=cp["target_tariff"], ch=cp["channel"])))
    d = pd.concat(parts, ignore_index=True)
    best = d.loc[d.groupby("ID")["lift"].idxmax()].set_index("ID")
    best["net"] = best["lift"] - d.groupby("ID")["cost"].sum()
    g = best.groupby(["cur", "seg"])
    out = g.agg(n=("net", "size"), net=("net", "sum"))
    out["tgt"] = g["tgt"].agg(lambda s: s.value_counts().index[0])
    out["ch"] = g["ch"].agg(lambda s: s.value_counts().index[0])
    return out


def main():
    seeds = list(range(10))
    print("=== e1-06: strategies via local_eval.evaluate_agent ===")
    ours, ours_inst = [], {}
    for s in seeds:
        ag = A.Agent(verbose=False)
        v, npil, _ = run(ag, s)
        ours.append(v)
        ours_inst[s] = ag
        hi = sum(r["seg"] == "HIGH" for r in ag.records)
        print(f"  our agent seed {s}: net {v:,.0f} pilots {npil} pilot contacts {sum(r['n'] for r in ag.records)} "
              f"pilot money {sum(r['cost'] for r in ag.records):,.0f} HIGH pilots {hi}")
    ours = pd.Series(ours)
    print(f"our agent: median {ours.median():,.0f} min {ours.min():,.0f} max {ours.max():,.0f} positive {(ours > 0).sum()}")

    ne = {}
    for s in [0, 1, 42]:
        x = NoPilots()
        ne[s] = run(x, s)
    y = NoPilotShare()
    ne_b = run(y, 0)
    print(f"no-exploration (pilots_left=0): seeds 0/1/42 -> {[f'{ne[s][0]:,.0f}' for s in ne]} pilots {[ne[s][1] for s in ne]}; "
          f"(PILOT_MONEY_SHARE=0) seed 0 -> {ne_b[0]:,.0f} pilots {ne_b[1]}")
    NE = ne[0][0]
    pdx = x.a.plan_detail
    print(f"no-exploration plan: {len(pdx)} campaigns, {sum(d['n'] for d in pdx):,} contacts, money {sum(d['cost'] for d in pdx):,.0f}, "
          f"channels {pd.Series([d['channel'] for d in pdx]).value_counts().to_dict()}")
    beat = int((ours < NE).sum())
    print(f"no-exploration beats our agent on {beat} of 10 seeds (agent max {ours.max():,.0f} vs {NE:,.0f})")

    tp = TrueEffects()
    TP, tp_pil, _ = run(tp, 0)
    tp1 = run(TrueEffects(), 7)[0]
    print(f"agent planner fed true effects: {TP:,.0f} (seed 7: {tp1:,.0f}); pilots {tp_pil}")
    tmpl, crashes = [], []
    for s in seeds:
        t = Template()
        v, npil, _ = run(t, s)
        tmpl.append(v)
        if hasattr(t, "crash"):
            crashes.append((s, t.crash))
    tmpl = pd.Series(tmpl)
    print(f"agent_template: median {tmpl.median():,.0f} min {tmpl.min():,.0f} max {tmpl.max():,.0f} positive {(tmpl > 0).sum()} "
          f"pilots/seed {npil}; crashes {crashes}")
    print(f"do nothing: {run(type('N', (), {'act': lambda self, env: []})(), 0)[0]:,.0f}")

    print("\n=== oracle (my construction, e1v_oracle) ===")
    o_plan, _, _, _ = oracle(prof, E, "cell")
    O = run(type("O", (), {"act": lambda self, env: [dict(c) for c in o_plan]})(), 42)[0]
    print(f"my oracle via evaluate_agent: {O:,.0f}")
    print(f"ratios: myO/no-exploration {O / NE:.2f}x; myO/agent median {O / ours.median():.2f}x; "
          f"agent median % of myO {ours.median() / O:.1%}; no-expl % {NE / O:.1%}; true-planner % {TP / O:.1%}")
    print(f"pilots realised (agent median - no-exploration) {ours.median() - NE:,.0f}; knowledge value (true planner - no-expl) {TP - NE:,.0f}")

    tp_nc = with_max_campaigns(1000, lambda: TrueEffects().act(make_mock_env(seed=0)[0]))
    print(f"true planner without its 10-campaign cut (rule-violating): {len(tp_nc)} campaigns, my-scorer net "
          f"{my_score(tp_nc, prof, E)['net']:,.0f} (vs capped {TP:,.0f})")

    print("\n=== e1-08/09/10: our agent at seed 42 ===")
    env, internals = make_mock_env(seed=42)
    ag = A.Agent(verbose=False)
    final = ag.act(env)[:10]
    pil = internals.executed_pilot_campaigns()
    sA, sF, sP = my_score(pil + final, prof, E), my_score(final, prof, E), my_score(pil, prof, E)
    Aoff = run(A.Agent(verbose=False), 42)[0]
    assert abs(sA["net"] - Aoff) < 1e-3 * abs(Aoff)
    print(f"A {sA['net']:,.0f} (official {Aoff:,.0f}); F {sF['net']:,.0f}; pilots {len(pil)} contacts {sP['contacts']} cost {sP['cost']:,.0f}; "
          f"incremental pilot gross {sA['gross'] - sF['gross']:,.0f}")
    pr = pd.DataFrame(ag.records)
    pr["true"] = [BASE[(r.tariff, r.seg, r.target)] for r in pr.itertuples()]
    pr["obs"] = pr["observed"] / 0.65
    print(pr[["tariff", "seg", "target", "n", "prior_mu", "true", "obs", "post_mu"]].round(4).to_string(index=False))
    hi = pr[pr.seg == "HIGH"]
    print(f"HIGH pilots {len(hi)} of {len(pr)}; max |true| among them {hi['true'].abs().max():.4f}; max true among them {hi['true'].max():.4f}; "
          f"true-negative pilots {int((pr['true'] < 0).sum())}; repeated hypotheses {int(pr.duplicated(['tariff', 'seg', 'target']).sum())}")
    nsd = 0.804 / 0.65 / math.sqrt(200)
    print(f"noise sd base units n=200 {nsd:.4f}; weight {0.09 / (0.09 + nsd ** 2):.3f}; "
          f"MAE prior {np.abs(pr.prior_mu - pr['true']).mean():.4f} obs {np.abs(pr.obs - pr['true']).mean():.4f} "
          f"post {np.abs(pr.post_mu - pr['true']).mean():.4f}")
    for cp, d in zip(final, sF["detail"]):
        print(f"  final {cp['target_tariff']:<9} {cp['channel']:<11} {cp['filter_arpu_segment']:<4} tariffs={cp['filter_current_tariff']:<38} "
              f"n={d['n']:5d} cost={d['cost']:7,.0f} gross={d['gross']:11,.0f} net={d['gross'] - d['cost']:11,.0f}")
    rl, bl = 15000 - sA["contacts"], 100000 - sA["cost"]
    print(f"unused reach {rl}, money {bl:,.0f}; campaigns {len(final)}")

    # sms -> digital_ads upgrades, scored for real (exhaustive over the sms campaigns)
    sms = [i for i, c in enumerate(final) if c["channel"] == "sms"]
    best = (0.0, ())
    for k in range(1, len(sms) + 1):
        for sub in itertools.combinations(sms, k):
            extra = sum(sF["detail"][i]["n"] * 18 for i in sub)
            if extra > bl:
                continue
            f2 = [dict(c, channel="digital_ads") if i in sub else c for i, c in enumerate(final)]
            g = my_score(pil + f2, prof, E)["net"] - sA["net"]
            if g > best[0]:
                best = (g, sub)
    print(f"best whole-campaign sms->digital_ads upgrade within unused money: +{best[0]:,.0f} "
          f"({[final[i]['filter_current_tariff'] + '/' + final[i]['filter_arpu_segment'] for i in best[1]]})")

    nc = with_max_campaigns(1000, lambda: (lambda ev: (A.Agent(verbose=False).act(ev[0]), ev[1]))(make_mock_env(seed=42)))
    nc_net = my_score(nc[1].executed_pilot_campaigns() + nc[0], prof, E)["net"]
    print(f"agent without its 10-campaign cut (rule-violating): {len(nc[0])} campaigns net {nc_net:,.0f} (+{nc_net - sA['net']:,.0f})")

    # decomposition with MY oracle
    O_red_plan, _, _, _ = oracle(prof, E, "cell", R=15000 - sP["contacts"], B=100000 - sP["cost"])
    O_red = my_score(O_red_plan, prof, E)["net"]
    co, cf = cell_net(O_red_plan), cell_net(final)
    m = co.join(cf, how="outer", lsuffix="_o", rsuffix="_f")
    for c in ["n_o", "n_f", "net_o", "net_f"]:
        m[c] = m[c].fillna(0)
    m["diff"] = m.net_o - m.net_f
    m["cat"] = np.select([m.tgt_f.isna(), m.tgt_o.isna(), m.tgt_o != m.tgt_f, m.ch_o != m.ch_f],
                         ["missing", "agent-only", "wrong target", "wrong channel"], "same")
    dec = m.groupby("cat").agg(cells=("diff", "size"), regret=("diff", "sum"), n_o=("n_o", "sum"), n_f=("n_f", "sum"))
    assert abs(dec.regret.sum() - (O_red - sF["net"])) < 1e-3 * abs(O_red - sF["net"])
    tot = O - sA["net"]
    print(f"\nmy O {O:,.0f}; O_red {O_red:,.0f}; A {sA['net']:,.0f}; regret {tot:,.0f} (A = {sA['net'] / O:.1%} of my O)")
    print(f"  pilot resources O-O_red {O - O_red:,.0f} ({(O - O_red) / tot:.1%}); pilot cost {sP['cost']:,.0f}; "
          f"pilot incremental lift {-(sA['gross'] - sF['gross']):,.0f}; pilots subtotal "
          f"{(O - O_red + sP['cost'] - (sA['gross'] - sF['gross'])) / tot:.1%}")
    print(dec.assign(share=dec.regret / tot).round(3).to_string())
    lp_full = lp_bound(prof, E)[0]
    lp_red = lp_bound(prof, E, R=15000 - sP["contacts"], B=100000 - sP["cost"])[0]
    print(f"certified pilot-resource cost via LP bounds: LP(15000,100000) - LP({15000 - sP['contacts']},{100000 - sP['cost']:,.0f}) "
          f"= {lp_full:,.0f} - {lp_red:,.0f} = {lp_full - lp_red:,.0f}")

    # root cause of missing cells: screened, invisible, allocation, or cut
    h = ag.hyps
    scr = h.groupby(["tariff", "seg"])["r_adj"].max()
    nc_cells = set()
    for c in nc[0]:
        for t in c["filter_current_tariff"].split(";"):
            nc_cells.add((t, c["filter_arpu_segment"]))
    miss = m[m.cat == "missing"]
    why = []
    for (cur, seg), r in miss.iterrows():
        if (cur, seg) not in scr.index:
            why.append("n<20: never a hypothesis")
        elif scr[(cur, seg)] <= 0:
            why.append("risk screen r_adj<=0")
        elif (cur, seg) in nc_cells:
            why.append("dropped by 10-campaign cut")
        else:
            why.append("passed screen, not allocated")
    miss = miss.assign(why=why)
    print("\nmissing oracle cells by root cause:\n" + miss.groupby("why").agg(cells=("diff", "size"), regret=("diff", "sum"),
                                                                            contacts=("n_o", "sum")).round(0).to_string())
    print(f"calibration at seed 42: {ag.calibration}; untested deploy threshold mu0 > {A.KAPPA * 0.3 - ag.calibration['bias']:.4f}")

    print("\n=== e1-11: risk screen on the raw prior (zero pilots) ===")
    a0 = A.Agent(verbose=False)
    env0, _ = make_mock_env(seed=0)
    h3 = a0._hypotheses(a0._cells(env0.customer_profile), a0._prior(env0), set(env0.tariffs["tariff_plan_code"]))
    ok = h3[h3.mu0 - A.KAPPA * h3.sd0 > 0].drop_duplicates(["tariff", "seg"])
    print(f"cells passing mu0-0.5*sd0>0: {len(ok)} of {h3[['tariff', 'seg']].drop_duplicates().shape[0]} ({int(ok.n.sum()):,} subscribers)")
    agent_cells = set(zip(h3.tariff, h3.seg))
    ee = E[[(c, s) in agent_cells for c, s in zip(E.cur, E.seg)]]
    print(f"true base > 0.15 among the agent's {len(ee)} combos: {int((ee.base > 0.15).sum())}; "
          f"0.15 / median positive base = {0.15 / E.loc[E.base > 0, 'base'].median():.1f}x")


if __name__ == "__main__":
    main()
