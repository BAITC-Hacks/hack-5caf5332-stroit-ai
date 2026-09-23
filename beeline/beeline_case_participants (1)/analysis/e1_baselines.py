"""e1 part 3-4: strategies vs the mock oracle, and the regret decomposition of our agent at seed 42.

LOCAL VALIDATION ONLY (uses the mock's true effects). Scoring goes through local_eval.evaluate_agent
exactly (pilots included). agent.py is imported, never modified; module constants patched for a
variant are restored immediately.

Run:  python3 analysis/e1_baselines.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e1_oracle as E  # noqa: E402  (also chdirs to P and puts P on sys.path)

import agent as agent_mod  # noqa: E402
import agent_template  # noqa: E402
from local_eval import evaluate_agent  # noqa: E402
from mock_environment import make_mock_env  # noqa: E402
from scoring_core import MAX_CAMPAIGNS, MAX_TOTAL_CONTACTS, TOTAL_BUDGET, sanitize_campaigns  # noqa: E402

SEEDS = list(range(10))
profile, dt, im = E.load()
eff, _ = E.true_effects(profile, dt, im)
BASE = eff.set_index(["current_tariff", "arpu_segment", "target"])["base"]


class OracleAgent:
    def __init__(self, camps):
        self.camps = camps

    def act(self, env):
        return [dict(c) for c in self.camps]


class NoExplore:
    """Our agent with PILOT_MONEY_SHARE = 0: zero pilots, plans from the history prior."""
    def act(self, env):
        old = agent_mod.PILOT_MONEY_SHARE
        agent_mod.PILOT_MONEY_SHARE = 0
        try:
            self.a = agent_mod.Agent(verbose=False)
            return self.a.act(env)
        finally:
            agent_mod.PILOT_MONEY_SHARE = old


class TruePlanner:
    """Our agent's planner (_plan) fed the TRUE mock base effect for every target, sd ~ 0, no pilots."""
    def act(self, env):
        a = agent_mod.Agent(verbose=False)
        a.cost = {c: float(v["cost_per_contact"]) for c, v in env.channels.items()}
        old = agent_mod.TARGETS_PER_CELL
        agent_mod.TARGETS_PER_CELL = 100
        try:
            h = a._hypotheses(a._cells(env.customer_profile), a._prior(env), set(env.tariffs["tariff_plan_code"]))
        finally:
            agent_mod.TARGETS_PER_CELL = old
        h["mu"] = BASE.reindex(pd.MultiIndex.from_frame(h[["tariff", "seg", "target"]])).values
        h["sd"] = 1e-9
        return a._plan(env, env.customer_profile, h)


class Nothing:
    def act(self, env):
        return []


def net_of(agent, seed):
    res = evaluate_agent(agent, seed=seed, verbose=False)
    return (res["net_arpu_gain"], res.get("n_pilots", 0)) if res else (0.0, 0)


def main():
    o_camps, o_est, o_info = E.oracle(profile, eff, "cell", smart=True)
    O = net_of(OracleAgent(o_camps), 42)[0]
    print(f"oracle (cell|cap10-smart, from e1_oracle.py) via evaluate_agent: net {O:,.0f}  "
          f"(lam={o_info['lam']:.3f}, rho={o_info['rho']:.3f})")

    # ------------------------------------------------------------ PART 3
    print("\n=== PART 3: strategies, scored by local_eval.evaluate_agent (pilots included), seeds 0-9 ===")
    makers = {"oracle (known effects, no pilots)": lambda: OracleAgent(o_camps),
              "agent planner fed true effects": TruePlanner,
              "our agent": lambda: agent_mod.Agent(verbose=False),
              "our agent, no exploration": NoExplore,
              "agent_template": agent_template.Agent,
              "do nothing": Nothing}
    rows, per_seed, calib = [], [], []
    for name, mk in makers.items():
        vals = []
        for s in SEEDS:
            inst = mk()
            v, npil = net_of(inst, s)
            vals.append(v)
            per_seed.append(dict(strategy=name, seed=s, net=v, pilots=npil))
            if name == "our agent":
                calib.append(dict(seed=s, net=v, **(inst.calibration or {}),
                                  pilot_contacts=sum(r["n"] for r in inst.records),
                                  pilot_cost=sum(r["cost"] for r in inst.records),
                                  plan_contacts=sum(d["n"] for d in inst.plan_detail),
                                  plan_cost=sum(d["cost"] for d in inst.plan_detail),
                                  plan_campaigns=len(inst.plan_detail)))
        v = pd.Series(vals)
        rows.append(dict(strategy=name, median=v.median(), min=v.min(), max=v.max(), mean=v.mean(),
                         pct_oracle_median=100 * v.median() / O, positive=int((v > 0).sum())))
    tab = pd.DataFrame(rows)
    with pd.option_context("display.width", 250, "display.max_columns", 20):
        print(tab.round(1).to_string(index=False))
        ps = pd.DataFrame(per_seed).pivot(index="seed", columns="strategy", values="net")
        print("\nper-seed net:\n" + ps.round(0).to_string())
        print("\npilots per seed:\n" + pd.DataFrame(per_seed).pivot(index="seed", columns="strategy",
                                                                     values="pilots").to_string())
    cb = pd.DataFrame(calib)
    print("\nour agent per seed: calibration bias applied to untested priors, pilot and plan usage:\n"
          + cb.round(4).to_string(index=False))
    print(f"corr(calibration bias, net) over seeds = {cb['bias'].corr(cb['net']):.3f}")
    med = tab.set_index("strategy")["median"]
    ne = med["our agent, no exploration"]
    print(f"\n15x claim on the mock: oracle / no-exploration = {O / ne:.2f}x ; oracle / our agent (median) = "
          f"{O / med['our agent']:.2f}x ; oracle / agent_template (median) = {O / med['agent_template']:.2f}x")
    print(f"value of perfect knowledge inside our planner: true-planner - no-exploration = "
          f"{med['agent planner fed true effects'] - ne:,.0f}; realised by pilots (median agent - no-exploration) = "
          f"{med['our agent'] - ne:,.0f}")
    print(f"planner heuristic gap: oracle - true-planner = {O - med['agent planner fed true effects']:,.0f}")
    ne_inst = NoExplore()
    net_of(ne_inst, 0)
    pd_ = ne_inst.a.plan_detail
    print(f"no-exploration plan: {len(pd_)} campaigns, {sum(d['n'] for d in pd_):,} contacts "
          f"(idle reach {MAX_TOTAL_CONTACTS - sum(d['n'] for d in pd_):,}), "
          f"cost {sum(d['cost'] for d in pd_):,.0f}, channels {pd.Series([d['channel'] for d in pd_]).value_counts().to_dict()}")
    old = agent_mod.MAX_CAMPAIGNS
    agent_mod.MAX_CAMPAIGNS = 1000
    try:
        env0, _ = make_mock_env(seed=0)
        tp = TruePlanner().act(env0)
        env0, _ = make_mock_env(seed=0)
        ne_nc = NoExplore().act(env0)
    finally:
        agent_mod.MAX_CAMPAIGNS = old
    tp_net = E.score(tp, profile, dt, im)["net_arpu_gain"]
    print(f"without the planner's 10-campaign cut: true-planner {len(tp)} campaigns net "
          f"{tp_net:,.0f} (cut costs {tp_net - med['agent planner fed true effects']:,.0f}); no-exploration "
          f"{len(ne_nc)} campaigns net {E.score(ne_nc, profile, dt, im)['net_arpu_gain']:,.0f}")

    # ------------------------------------------------------------ PART 4
    print("\n=== PART 4: regret decomposition, our agent at seed 42 ===")
    env, internals = make_mock_env(seed=42)
    ag = agent_mod.Agent(verbose=False)
    final = sanitize_campaigns(ag.act(env), env.tariffs)[:MAX_CAMPAIGNS]
    pilots = internals.executed_pilot_campaigns()
    rA, rF, rP = (E.score(x, profile, dt, im) for x in (pilots + final, final, pilots))
    A, F = rA["net_arpu_gain"], rF["net_arpu_gain"]
    assert abs(A - net_of(agent_mod.Agent(verbose=False), 42)[0]) < 1e-6
    p_n, p_cost = rP["total_contacts"], rP["total_cost"]
    p_incr = rA["gross_arpu_lift"] - rF["gross_arpu_lift"]
    print(f"agent net A={A:,.0f}; final campaigns alone F={F:,.0f} ({len(final)} campaigns, "
          f"{rF['total_contacts']:,} contacts, cost {rF['total_cost']:,.0f})")
    print(f"pilots: {len(pilots)} pilots, {p_n:,} contacts, cost {p_cost:,.0f}, gross lift alone "
          f"{rP['gross_arpu_lift']:,.0f}, incremental gross lift after dedup {p_incr:,.0f}, net alone {rP['net_arpu_gain']:,.0f}")
    pr = pd.DataFrame(ag.records)
    pr["true_base"] = BASE.reindex(pd.MultiIndex.from_frame(pr[["tariff", "seg", "target"]])).values
    pr["obs_base"] = pr["observed"] / 0.65
    with pd.option_context("display.width", 250, "display.max_columns", 20):
        print("pilots at seed 42 (base units; obs_base = observed / 0.65):\n" +
              pr[["tariff", "seg", "target", "n", "prior_mu", "true_base", "obs_base", "post_mu", "post_sd"]]
              .round(4).to_string(index=False))
    print(f"pilot |obs - true| mean {np.abs(pr['obs_base'] - pr['true_base']).mean():.4f}; "
          f"|prior - true| mean {np.abs(pr['prior_mu'] - pr['true_base']).mean():.4f}; "
          f"|post - true| mean {np.abs(pr['post_mu'] - pr['true_base']).mean():.4f}; "
          f"pilots on true-negative hypotheses {int((pr['true_base'] < 0).sum())}; calibration {ag.calibration}")
    nsd = agent_mod.NOISE_SD / 0.65 / np.sqrt(200)
    w = agent_mod.PRIOR_SD ** 2 / (agent_mod.PRIOR_SD ** 2 + nsd ** 2)
    print(f"pilot noise sd in base units (sms, n=200) {nsd:.4f}; weight of one such pilot against PRIOR_SD "
          f"{agent_mod.PRIOR_SD}: {w:.3f}; pilots on HIGH-segment cells {int((pr['seg'] == 'HIGH').sum())} of {len(pr)}, "
          f"max |true base| among them {pr.loc[pr['seg'] == 'HIGH', 'true_base'].abs().max():.4f}")
    R_left, B_left = MAX_TOTAL_CONTACTS - rA["total_contacts"], TOTAL_BUDGET - rA["total_cost"]
    print(f"unused at the end: reach {R_left:,} of {MAX_TOTAL_CONTACTS:,}, money {B_left:,.0f} of {TOTAL_BUDGET:,}")

    red_camps, _, red_info = E.oracle(profile, eff, "cell", R=MAX_TOTAL_CONTACTS - p_n, B=TOTAL_BUDGET - p_cost, smart=True)
    O_red = E.score(red_camps, profile, dt, im)["net_arpu_gain"]
    print(f"oracle with the budget left after pilots (R={MAX_TOTAL_CONTACTS - p_n}, B={TOTAL_BUDGET - p_cost:,.0f}): "
          f"O_red={O_red:,.0f}")

    # cell-level comparison O_red vs F (both without pilots, same remaining budgets)
    def cells(camps):
        _, best = E.ledger(camps, profile, dt, im)
        best["net"] = best["expected_lift_per_customer"] - best["cost_all"]
        g = best.groupby(["current_tariff", "arpu_segment"])
        out = g.agg(n=("ID_NUMBER", "size"), net=("net", "sum"))
        out["target"] = g["target"].agg(lambda s: s.value_counts().index[0])
        out["channel"] = g["channel"].agg(lambda s: s.value_counts().index[0])
        return out
    co, cf = cells(red_camps), cells(final)
    m = co.join(cf, how="outer", lsuffix="_o", rsuffix="_f")
    m[["net_o", "net_f", "n_o", "n_f"]] = m[["net_o", "net_f", "n_o", "n_f"]].fillna(0)
    m["diff"] = m["net_o"] - m["net_f"]
    cat = np.select([m["target_f"].isna(), m["target_o"].isna(), m["target_o"] != m["target_f"],
                     m["channel_o"] != m["channel_f"]],
                    ["oracle cell missing from plan", "cell only in agent plan", "wrong target",
                     "same target, wrong channel"], "same target+channel (coverage)")
    m["category"] = cat
    dec = m.groupby("category").agg(cells=("diff", "size"), regret=("diff", "sum"),
                                    oracle_net=("net_o", "sum"), agent_net=("net_f", "sum"),
                                    oracle_n=("n_o", "sum"), agent_n=("n_f", "sum"))
    with pd.option_context("display.width", 250, "display.max_columns", 20):
        print("\nO_red - F by cell category:\n" + dec.round(0).to_string())
        print("\nlargest per-cell regrets:\n" + m.sort_values("diff", ascending=False).head(10)
              [["target_o", "channel_o", "n_o", "net_o", "target_f", "channel_f", "n_f", "net_f", "diff", "category"]]
              .round(0).to_string())
    assert abs(dec["regret"].sum() - (O_red - F)) < 1e-3 * max(1.0, abs(O_red - F))

    neg = [d for d in rF["campaigns_detail"] if d["gross_lift"] - d["cost"] < 0]
    negp = [d for d in rP["campaigns_detail"] if d["gross_lift"] - d["cost"] < 0]
    print(f"\nfinal campaigns with negative true net: {len(neg)} (sum {sum(d['gross_lift'] - d['cost'] for d in neg):,.0f}); "
          f"pilots with negative true net: {len(negp)} of {len(pilots)} "
          f"(sum {sum(d['gross_lift'] - d['cost'] for d in negp):,.0f})")
    for d, c in zip(rF["campaigns_detail"], final):
        print(f"  final {c['target_tariff']:<9} {c['channel']:<11} arpu={c['filter_arpu_segment']:<4} "
              f"data={str(c.get('filter_data_segment')):<8} tariffs={c['filter_current_tariff']:<40} "
              f"n={d['n_contacts']:5d} cost={d['cost']:8,.0f} gross={d['gross_lift']:12,.0f}")

    # leftover money spent on sms -> digital_ads upgrades of the agent's own final campaigns (true values;
    # mock conversion caps never bind, so gross scales with the channel multiplier)
    ups = []
    for d, c in zip(rF["campaigns_detail"], final):
        if c["channel"] == "sms" and d["gross_lift"] > 0:
            extra = d["n_contacts"] * 18
            ups.append((d["gross_lift"] * (0.85 / 0.65 - 1) - extra, extra))
    left, gain = B_left, 0.0
    for g_, x in sorted(ups, key=lambda t: -t[0] / t[1]):
        if x <= left and g_ > 0:
            gain, left = gain + g_, left - x
    print(f"upgrading whole sms campaigns to digital_ads with the unused money {B_left:,.0f}: +{gain:,.0f} "
          f"(money left {left:,.0f})")

    # unused reach/money: what the oracle could add with the leftovers in untouched cells and free slots
    touched = set(map(tuple, E.ledger(final, profile, dt, im)[0][["current_tariff", "arpu_segment"]].values))
    keep = ~pd.Series(list(zip(profile["current_tariff"], profile["arpu_segment"]))).isin(touched).values
    slots = MAX_CAMPAIGNS - len(final)
    fill_val = 0.0
    if slots > 0 and R_left > 0:
        fill, _, _ = E.oracle(profile[keep], eff, "cell", R=R_left, B=B_left, max_campaigns=slots, smart=True)
        fill_val = E.score(pilots + final + fill, profile, dt, im)["net_arpu_gain"] - A
        print(f"fill of unused reach/money ({slots} free slots, untouched cells): +{fill_val:,.0f} "
              f"({len(fill)} extra campaigns)")

    # campaign-count cap for the agent: same pilots (seed 42), planner allowed any number of campaigns
    old = agent_mod.MAX_CAMPAIGNS
    agent_mod.MAX_CAMPAIGNS = 1000
    try:
        env2, int2 = make_mock_env(seed=42)
        final_nc = agent_mod.Agent(verbose=False).act(env2)
        nc = E.score(int2.executed_pilot_campaigns() + final_nc, profile, dt, im)["net_arpu_gain"]
    finally:
        agent_mod.MAX_CAMPAIGNS = old
    print(f"agent without its 10-campaign cut: {len(final_nc)} campaigns, net {nc:,.0f} (cap cost {nc - A:,.0f})")

    UB_nocap = E.score(E.oracle(profile, eff, "call", cap=False)[0], profile, dt, im)["net_arpu_gain"]
    print("\nREGRET DECOMPOSITION (O - A, exact additive):")
    parts = [("pilot resources (O - O_red)", O - O_red), ("pilot direct cost", p_cost),
             ("pilot lift credited (incremental)", -p_incr)]
    parts += [(f"final plan: {k}", v) for k, v in dec["regret"].items()]
    for k, v in parts:
        print(f"  {k:<48} {v:>12,.0f}   {100 * v / (O - A):6.1f}% of regret")
    pil = sum(v for k, v in parts[:3])
    print(f"  {'subtotal pilots':<48} {pil:>12,.0f}   {100 * pil / (O - A):6.1f}%")
    print(f"  {'subtotal final plan (O_red - F)':<48} {O_red - F:>12,.0f}   {100 * (O_red - F) / (O - A):6.1f}%")
    print(f"  {'TOTAL':<48} {sum(v for _, v in parts):>12,.0f}   check O - A = {O - A:,.0f}")
    assert abs(sum(v for _, v in parts) - (O - A)) < 1e-3 * abs(O - A)
    print(f"side metrics: unused reach {R_left:,}, unused money {B_left:,.0f}, fill value {fill_val:,.0f}; "
          f"oracle's own campaign-cap cost (UB_nocap - O) {UB_nocap - O:,.0f}; agent cap cost {nc - A:,.0f}")
    print(f"agent = {100 * A / O:.1f}% of oracle; regret {O - A:,.0f}")


if __name__ == "__main__":
    main()
