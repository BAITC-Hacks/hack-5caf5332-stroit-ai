"""
Runs the agent once on the mock environment (seed 42, same as make_submission.py) and
writes flow_trace.js — the data behind flow.html (open it in a browser afterwards).

    python export_trace.py
"""
import contextlib
import io
import json

import pandas as pd

from agent import Agent
from environment import MAX_PILOTS
from local_eval import evaluate_agent
from mock_environment import CHANNELS, MAX_TOTAL_CONTACTS, TOTAL_BUDGET
from scoring_core import MAX_CAMPAIGNS, MAX_CUSTOMERS_PER_CAMPAIGN

SEED = 42


def main():
    agent = Agent(verbose=False)
    with contextlib.redirect_stdout(io.StringIO()):
        res = evaluate_agent(agent, seed=SEED, verbose=False)
    h = agent.hyps
    deployed = {}
    for c in agent.plan_detail:
        for t in c["filter_current_tariff"].split(";"):
            deployed[(t, c["filter_arpu_segment"], c["target_tariff"])] = c["channel"]
    hyps = [dict(tariff=r.tariff, seg=r.seg, target=r.target, n=int(r.n), mass=round(float(r.mass)),
                 mu0=round(float(r.mu0), 4), sd0=round(float(r.sd0), 4), mu=round(float(r.mu), 4),
                 sd=round(float(r.sd), 4), n_obs=int(r.n_obs), r_adj=round(float(r.r_adj), 4),
                 decision=deployed.get((r.tariff, r.seg, r.target), "dropped"))
            for r in h.itertuples()]
    trace = dict(
        seed=SEED,
        limits=dict(budget=TOTAL_BUDGET, contacts=MAX_TOTAL_CONTACTS, pilots=MAX_PILOTS,
                    per_campaign=MAX_CUSTOMERS_PER_CAMPAIGN, max_campaigns=MAX_CAMPAIGNS),
        channels={k: dict(cost=v["cost_per_contact"], mult=v["conversion_multiplier"]) for k, v in CHANNELS.items()},
        audience=dict(n=len(pd.read_csv("customer_profile.csv")), baseline=res["baseline_total_arpu"],
                      cells=int(h.drop_duplicates(["tariff", "seg"]).shape[0]), hypotheses=len(h)),
        hypotheses=hyps,
        pilots=[dict(i=i + 1, **r) for i, r in enumerate(agent.records)],
        calibration=agent.calibration,
        plan=agent.plan_detail,
        score=dict(net=res["net_arpu_gain"], gross=res["gross_arpu_lift"], cost=res["total_cost"],
                   contacts=res["total_contacts"], unique=res["unique_customers_targeted"],
                   coverage_pct=res["coverage_pct"], risk_pct=res["risk_score_pct"],
                   budget_used_pct=res["budget_used_pct"], n_pilots=res["n_pilots"],
                   campaigns=[dict(name=c["name"], channel=c["channel"], n=c["n_contacts"], cost=c["cost"],
                                   gross=c["gross_lift"], negative=c["n_negative"]) for c in res["campaigns_detail"]]),
    )
    with open("flow_trace.js", "w", encoding="utf-8") as f:
        f.write("window.FLOW_TRACE = " + json.dumps(trace, ensure_ascii=False, default=lambda o: o.item()) + ";\n")
    print(f"flow_trace.js written: {len(trace['pilots'])} pilots, {len(trace['plan'])} campaigns, "
          f"net {trace['score']['net']:,.0f}. Open flow.html in a browser.")


if __name__ == "__main__":
    main()
