"""d1v: which hypotheses does the agent actually pilot on the mock? Deterministic seeds.
Run: python3 analysis/d1v_pilots_run.py
"""
import os
import sys

sys.dont_write_bytecode = True
import pandas as pd

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, P)
from agent import Agent  # noqa: E402
from mock_environment import make_mock_env  # noqa: E402

ct = pd.read_csv(os.path.join(P, "data", "change_tariff.csv"))
h = ct[ct.AVG_ARPU_PREV_3M >= 100].copy()
h["seg"] = pd.cut(h.AVG_ARPU_PREV_3M, [-float("inf"), 1000, 5000, float("inf")], labels=["LOW", "MID", "HIGH"]).astype(str)
seen = set(zip(h.tariff_plan_code_from, h.seg, h.tariff_plan_code_to))
rows = []
for seed in list(range(10)) + [42]:
    env, _ = make_mock_env(seed=seed, data_dir=os.path.join(P, "data"), profile_path=os.path.join(P, "customer_profile.csv"))
    ag = Agent(verbose=False)
    ag.act(env)
    rec = pd.DataFrame(ag.records)
    uns = [(t, s, g) not in seen for t, s, g in zip(rec.tariff, rec.seg, rec.target)]
    never_to = set(pd.read_csv(os.path.join(P, "data", "dict_tariff.csv")).tariff_plan_code) - set(ct.tariff_plan_code_to)
    if seed == 42:
        u = rec[uns]
        print("seed 42 unseen pilots (cell -> target, n):",
              list(zip(u.tariff + "/" + u.seg, u.target, u.n)))
    rows.append(dict(seed=seed, never_target_pilots=int(rec.target.isin(never_to).sum()), pilots=len(rec), contacts=int(rec.n.sum()), money=float(rec.cost.sum()),
                     unseen_pilots=int(sum(uns)), distinct_cells=rec[["tariff", "seg"]].drop_duplicates().shape[0],
                     pilots_on_top4_cells=int(rec.apply(lambda r: (r.tariff, r.seg) in {("tariff_8", "HIGH"), ("tariff_10", "HIGH"),
                                                                                         ("tariff_4", "HIGH"), ("tariff_11", "HIGH")}, axis=1).sum())))
df = pd.DataFrame(rows)
print(df.to_string(index=False))
print(f"total pilots={df.pilots.sum()} unseen={df.unseen_pilots.sum()}; mean contacts={df.contacts.mean():.1f} "
      f"(share of reach {100 * df.contacts.mean() / 15000:.2f}%), mean money={df.money.mean():,.0f}")
