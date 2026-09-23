"""Contract and adaptive-behaviour tests; no browser or private effects used by agent."""
from pathlib import Path
import ast
import os
import sys
import unittest
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from agent import Agent
from make_submission import build_submission


class FakeEnv:
    def __init__(self, winner="tariff_3", n=400, budget=100000, contacts=15000):
        self.customer_profile = pd.DataFrame([
            {"ID_NUMBER": cell * n + i, "current_tariff": f"tariff_{cell+1}", "arpu_segment": "HIGH", "predicted_arpu": 6000.0}
            for cell in range(3) for i in range(n)])
        self.tariffs = pd.DataFrame({"tariff_plan_code": ["tariff_1","tariff_2","tariff_3"], "price_tariff": [1000,2000,3000]})
        self.channels = {"push":{"cost_per_contact":0}, "sms":{"cost_per_contact":4}, "digital_ads":{"cost_per_contact":22}, "call":{"cost_per_contact":160}}
        self.remaining_budget, self.remaining_contacts, self.pilots_left = budget, contacts, 20
        self.pilot_history = []
        self.calls = []
        self.winner = winner

    def run_pilot(self, target_tariff, channel, n_customers, **filters):
        assert 10 <= n_customers <= 200
        rows=self.customer_profile[(self.customer_profile.current_tariff==filters["filter_current_tariff"]) &
                                   (self.customer_profile.arpu_segment==filters["filter_arpu_segment"])]
        cost=self.channels[channel]["cost_per_contact"]
        n=min(n_customers,len(rows),self.remaining_contacts)
        if cost:n=min(n,int(self.remaining_budget//cost))
        if n<1 or self.pilots_left<1:raise RuntimeError("No resources")
        ratio=0.4 if target_tariff==self.winner else -0.2
        self.remaining_budget-=n*cost; self.remaining_contacts-=n; self.pilots_left-=1
        value={"pilot":f"pilot_{len(self.calls)+1}","target_tariff":target_tariff,"channel":channel,"n_customers":n,"cost":n*cost,
               "observed_lift_ratio":ratio,"observed_lift_total":ratio*n*6000,"remaining_budget":self.remaining_budget,"remaining_contacts":self.remaining_contacts}
        self.calls.append((target_tariff,channel,n,filters["filter_current_tariff"]))
        self.pilot_history.append(value)
        return value


class Contract(unittest.TestCase):
    def agent(self):return Agent(history_path=ROOT/"tests/absent-history.csv")

    def test_adapts_to_changed_effects(self):
        a,b=self.agent(),self.agent(); ea,eb=FakeEnv("tariff_2"),FakeEnv("tariff_3")
        pa,pb=a.act(ea),b.act(eb)
        self.assertNotEqual(pa,pb)
        self.assertNotEqual(ea.calls,eb.calls)
        self.assertTrue(all(p["target_tariff"]=="tariff_2" for p in pa))
        self.assertTrue(all(p["target_tariff"]=="tariff_3" for p in pb))

    def test_negative_observations_are_kept(self):
        a=self.agent(); plan=a.act(FakeEnv("missing"))
        self.assertTrue(a.audit["low_confidence_fallback"])
        self.assertTrue(all(p["result"]["observed_lift_ratio"]<0 for p in a.audit["pilots"]))
        self.assertGreaterEqual(len(plan),1)

    def test_resource_limits_and_nonoverlap(self):
        a=self.agent();e=FakeEnv(n=6000);plan=a.act(e)
        self.assertTrue(1<=len(plan)<=10)
        self.assertLessEqual(sum(p["contacts"] for p in a.audit["plan"]),e.remaining_contacts)
        self.assertLessEqual(sum(p["cost"] for p in a.audit["plan"]),e.remaining_budget)
        self.assertTrue(all(p["contacts"]<=5000 for p in a.audit["plan"]))
        self.assertEqual(len({(p["filter_current_tariff"],p["filter_arpu_segment"]) for p in plan}),len(plan))
        self.assertTrue(all("explicit_ids" not in p for p in plan))

    def test_actual_pilot_size(self):
        a=self.agent();a.act(FakeEnv(n=5))
        self.assertTrue(a.audit["pilots"])
        self.assertTrue(all(p["result"]["n_customers"]==5 for p in a.audit["pilots"]))

    def test_zero_budget_uses_free_channel(self):
        a=self.agent();plan=a.act(FakeEnv(budget=0))
        self.assertTrue(plan)
        self.assertTrue(all(p["channel"]=="push" for p in plan))

    def test_no_pilot_allowance_is_explicit_fallback(self):
        a=self.agent();e=FakeEnv();e.pilots_left=0;plan=a.act(e)
        self.assertTrue(plan);self.assertTrue(a.audit["low_confidence_fallback"])
        self.assertIsNone(a.audit["plan"][0]["net"])

    def test_empty_profile(self):
        a=self.agent();e=FakeEnv();e.customer_profile=e.customer_profile.iloc[:0]
        self.assertEqual(a.act(e),[])
        self.assertIn("stop_reason",a.audit)

    def test_duplicates_fail_explicitly(self):
        e=FakeEnv();e.customer_profile.loc[1,"ID_NUMBER"]=0
        with self.assertRaisesRegex(ValueError,"Duplicate"):self.agent().act(e)

    def test_invalid_required_rows_fail_explicitly(self):
        e=FakeEnv();e.customer_profile.loc[1,"predicted_arpu"]=float("nan")
        with self.assertRaisesRegex(ValueError,"Invalid required"):self.agent().act(e)

    def test_missing_segment_is_excluded_by_final_filters(self):
        e=FakeEnv();e.customer_profile.loc[1,"arpu_segment"]=None
        a=self.agent();plan=a.act(e)
        self.assertEqual(a.audit["quality"]["invalid_rows"],1)
        self.assertEqual(a.audit["audience"]["rows"],len(e.customer_profile)-1)
        self.assertTrue(all(p["filter_arpu_segment"]=="HIGH" for p in plan))

    def test_source_uses_only_public_env(self):
        tree=ast.parse((ROOT/"engine/agent.py").read_text())
        allowed={"customer_profile","tariffs","channels","remaining_budget","remaining_contacts","pilots_left","pilot_history","run_pilot"}
        for node in ast.walk(tree):
            if isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id=="env":
                self.assertIn(node.attr,allowed)
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                text=ast.unparse(node)
                self.assertNotIn("mock_environment",text);self.assertNotIn("scoring_core",text)

    def test_submission_is_reproducible(self):
        previous=os.getcwd()
        try:
            os.chdir(ROOT/"engine")
            one=build_submission(Agent());two=build_submission(Agent())
            pd.testing.assert_frame_equal(one,two)
        finally:os.chdir(previous)


if __name__=="__main__":unittest.main(verbosity=2)
