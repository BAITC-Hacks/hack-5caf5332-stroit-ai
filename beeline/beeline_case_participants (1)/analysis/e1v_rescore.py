"""e1v: re-score the analyst's printed oracle plan (e1_oracle.py stdout, transcribed) with my own scorer
and the public evaluate_agent; check the rules (<=10 campaigns, <=5000 each, no truncation, limits).

Run:  python3 analysis/e1v_rescore.py
"""
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, P)
os.chdir(P)
from e1v_oracle import my_score, setup  # noqa: E402
from local_eval import evaluate_agent  # noqa: E402

PLAN = [  # target, channel, arpu, tariffs  (order as printed)
    ("tariff_8", "digital_ads", "MID", "tariff_1;tariff_12;tariff_13;tariff_17;tariff_3;tariff_4"),
    ("tariff_8", "digital_ads", "LOW", "tariff_11;tariff_12;tariff_13;tariff_17;tariff_18;tariff_20;tariff_9"),
    ("tariff_9", "sms", "LOW", "tariff_1;tariff_10;tariff_14;tariff_15;tariff_16;tariff_19;tariff_2;tariff_3;tariff_4;tariff_6;tariff_7;tariff_8"),
    ("tariff_11", "sms", "MID", "tariff_10;tariff_6"),
    ("tariff_10", "sms", "MID", "tariff_8"),
    ("tariff_8", "push", "MID", "tariff_11;tariff_15;tariff_16;tariff_18;tariff_19;tariff_2;tariff_20;tariff_9"),
    ("tariff_9", "push", "MID", "tariff_14"),
    ("tariff_12", "push", "HIGH", "tariff_11;tariff_16;tariff_2;tariff_21;tariff_7"),
    ("tariff_14", "push", "HIGH", "tariff_1;tariff_13;tariff_15;tariff_17;tariff_19;tariff_20;tariff_3;tariff_4;tariff_5"),
    ("tariff_11", "push", "HIGH", "tariff_12;tariff_18;tariff_6;tariff_9"),
]


def main():
    ct, dt, prof, E = setup()
    plan = [dict(campaign_name=f"o{i}", filter_arpu_segment=s, filter_current_tariff=tl, target_tariff=t, channel=c)
            for i, (t, c, s, tl) in enumerate(PLAN)]
    sc = my_score(plan, prof, E)
    off = evaluate_agent(type("O", (), {"act": lambda self, env: [dict(p) for p in plan]})(), seed=42, verbose=False)
    sizes = []
    for p in plan:
        s = prof[(prof.arpu_segment == p["filter_arpu_segment"]) & prof.current_tariff.isin(p["filter_current_tariff"].split(";"))]
        sizes.append(len(s))
    trunc = [d for d in off["campaigns_detail"] if d["capped_at_campaign_limit"] or d["capped_at_reach_budget"] or d["capped_at_money_budget"]]
    print(f"analyst oracle plan: my scorer net {sc['net']:,.0f} gross {sc['gross']:,.0f} money {sc['cost']:,.0f} contacts {sc['contacts']:,}; "
          f"official net {off['net_arpu_gain']:,.0f}; campaigns {len(plan)}; max segment size {max(sizes)}; truncated campaigns {len(trunc)}")
    by = pd.DataFrame([dict(ch=p["channel"], seg=p["filter_arpu_segment"], n=d["n"], cost=d["cost"], gross=d["gross"])
                       for p, d in zip(plan, sc["detail"])])
    print(by.groupby("ch")[["n", "cost", "gross"]].sum().round(0).to_string())
    print(by.groupby(["seg", "ch"])[["n", "gross"]].sum().round(0).to_string())
    dup = pd.Series([t for p in plan for t in [(x, p["filter_arpu_segment"]) for x in p["filter_current_tariff"].split(";")]])
    print(f"cells covered {dup.nunique()} (duplicates {int(dup.duplicated().sum())}); "
          f"per-subscriber best == sum of campaign gross (disjoint): {abs(sum(d['gross'] for d in sc['detail']) - sc['gross']) < 1e-6}")
    fb = set(map(tuple, E.loc[E.src == "fallback", ["cur", "seg", "tgt"]].values))
    fbg = 0.0
    for p in plan:
        for t in p["filter_current_tariff"].split(";"):
            if (t, p["filter_arpu_segment"], p["target_tariff"]) in fb:
                q = dict(p, filter_current_tariff=t)
                fbg += my_score([q], prof, E)["gross"]
    print(f"gross from fallback-rule combos: {fbg:,.0f} of {sc['gross']:,.0f}")


if __name__ == "__main__":
    main()
