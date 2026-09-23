"""a1v: scorer-mechanics checks behind a1 implications (pilot re-contact, reach binding in the mock,
LOW weight ratio variants, zero-value rows). Uses the public scoring_core + mock only (mock = NOT the judge).
Deterministic (fixed seeds)."""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
os.chdir(ROOT)  # mock_environment reads data/ relative to cwd
from mock_environment import _mock_impact_model, _mock_fallback, make_mock_env  # noqa: E402
from scoring_core import score_campaigns  # noqa: E402
from agent import Agent  # noqa: E402

prof = pd.read_csv("customer_profile.csv")
dt = pd.read_csv("data/dict_tariff.csv")
ct = pd.read_csv("data/change_tariff.csv")
im = _mock_impact_model(ct)
PA = "predicted_arpu"
TOT = float(prof[PA].sum())
COLS = ["filter_arpu_segment", "filter_data_segment", "filter_call_segment", "filter_current_tariff", "explicit_ids"]


def score(camps):
    s = pd.DataFrame(camps)
    for c in COLS:
        if c not in s.columns:
            s[c] = None
    return score_campaigns(s, prof, im, dt, TOT, _mock_fallback)


# ---------------------------------------------------------------- 1. pilot re-contact mechanics
print("##### pilot re-contact (public scorer; counts are pure mechanics)")
rng = np.random.default_rng(7)
c8 = prof[(prof.current_tariff == "tariff_8") & (prof.arpu_segment == "HIGH")]
c13 = prof[(prof.current_tariff == "tariff_13") & (prof.arpu_segment == "MID")]
final = dict(campaign_name="final", filter_arpu_segment="HIGH", filter_current_tariff="tariff_8",
             target_tariff="tariff_10", channel="sms")
for nm, cell in [("pilot inside deployed cell", c8), ("pilot outside deployed cell", c13)]:
    ids = rng.choice(cell.ID_NUMBER.to_numpy(), 200, replace=False).tolist()
    pilot = dict(campaign_name="pilot", explicit_ids=ids, target_tariff="tariff_10", channel="sms")
    r = score([pilot, final])
    print(f"{nm}: total_contacts={r['total_contacts']} unique={r['unique_customers_targeted']} "
          f"duplicates={r['total_contacts'] - r['unique_customers_targeted']} cost={r['total_cost']:.0f}")

# ---------------------------------------------------------------- 2. agent's own plan in the mock (seed 42)
print("\n##### agent plan overlap with its pilots (mock seed 42)")
env, internals = make_mock_env(seed=42)
fin = Agent(verbose=False).act(env)
pil = internals.executed_pilot_campaigns()
fin = [{k: v for k, v in c.items() if not k.startswith("_")} for c in fin]
r = score(pil + fin)
npil = sum(len(p["explicit_ids"]) for p in pil)
print(f"pilots={len(pil)} pilot_contacts={npil} finals={len(fin)} total_contacts={r['total_contacts']} "
      f"unique={r['unique_customers_targeted']} duplicates={r['total_contacts'] - r['unique_customers_targeted']} "
      f"net={r['net_arpu_gain']:,.0f}")
pid = {i for p in pil for i in p["explicit_ids"]}
rf = score(fin)
overlap = rf["unique_customers_targeted"] + len(pid) - r["unique_customers_targeted"]
print(f"finals alone: contacts={rf['total_contacts']} unique={rf['unique_customers_targeted']}; unique pilot IDs={len(pid)} "
      f"(repeat contacts within pilots={npil - len(pid)}); pilot IDs re-contacted by finals={overlap}")
print(f"total cost={r['total_cost']:,.0f} of 100,000; reach used={r['total_contacts']} of 15,000; "
      f"final channels={pd.Series([c['channel'] for c in fin]).value_counts().to_dict()}; "
      f"final contacts by channel={ {d['channel']: 0 for d in rf['campaigns_detail']} | pd.DataFrame(rf['campaigns_detail']).groupby('channel').n_contacts.sum().to_dict()}")

det = pd.DataFrame(rf["campaigns_detail"]).assign(seg=[c["filter_arpu_segment"] for c in fin])
g = det.groupby("seg")[["n_contacts", "gross_lift"]].sum()
g["lift_per_contact"] = g.gross_lift / g.n_contacts
print("finals (disjoint, mock) by arpu_segment:\n", g.round(1).to_string())
top3 = {"tariff_8", "tariff_10", "tariff_11"}
print("finals touching tariff_8/10/11 HIGH:", [c["campaign_name"] for c in fin if c["filter_arpu_segment"] == "HIGH"
                                                and top3 & set(c["filter_current_tariff"].split(";"))])

# ---------------------------------------------------------------- 3. does reach bind? (MOCK effects only)
print("\n##### subscribers with positive best sms net lift under the MOCK impact model")
cells = prof.dropna(subset=["current_tariff", "arpu_segment"])[["current_tariff", "arpu_segment"]].drop_duplicates()
fbc = im["conversion_rate"].median()
rows = []
for t in dt.tariff_plan_code:
    m = cells.merge(im[im.tariff_plan_code_to == t], left_on=["current_tariff", "arpu_segment"],
                    right_on=["tariff_plan_code_from", "arpu_segment"], how="left")
    seen = m.arpu_change_pct.notna()
    fb = [_mock_fallback(a, t, s, dt, fbc) for a, s in zip(m.current_tariff, m.arpu_segment)]
    pct = np.where(seen, m.arpu_change_pct, [f[0] for f in fb])
    conv = np.where(seen, m.conversion_rate, [f[1] for f in fb])
    rows.append(pd.DataFrame(dict(current_tariff=m.current_tariff, arpu_segment=m.arpu_segment, target=t,
                                  seen=seen, ratio=pct * np.minimum(1, conv * 0.65))))
R = pd.concat(rows)
for nm, sub in [("all combos (history + price fallback)", R), ("history-observed combos only", R[R.seen])]:
    best = sub.groupby(["current_tariff", "arpu_segment"]).ratio.max().rename("best").reset_index()
    x = prof.merge(best, on=["current_tariff", "arpu_segment"], how="inner")
    net = x.best * x[PA] - 4
    print(f"{nm}: subs with net sms lift>0 = {int((net > 0).sum())} (mass {100 * x.loc[net > 0, PA].sum() / TOT:.2f}%); "
          f"cells with best ratio>0 = {int((best.best > 0).sum())} of {len(best)}")

# ---------------------------------------------------------------- 4. LOW weight ratio variants and zero rows
print("\n##### LOW weight ratio variants")
lo = prof[(prof.arpu_segment == "LOW") & (prof.ARPU_3m_avg >= 100)]
print(f"LOW with ARPU_3m_avg>=100: n={len(lo)} median ratio={(lo[PA] / lo.ARPU_3m_avg).median():.3f} "
      f"sum(pred)/sum(3m)={lo[PA].sum() / lo.ARPU_3m_avg.sum():.3f}")
z = prof[prof[PA] == 0]
print("zero-value rows by current_tariff:", z.current_tariff.value_counts(dropna=False).to_dict())
