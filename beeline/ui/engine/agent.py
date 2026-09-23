"""Adapter between the team agent in the case folder and the UI audit contract.

Runs `<case folder>/agent.py` (the submission, e.g. PR #4) without modifying it and
fills `self.audit` for run_case.py / the workspace UI. If the team agent already
exposes a non-empty `audit`, it is used as is. If the case folder has no agent.py,
falls back to engine/reference_agent.py.
"""
from collections import Counter
import importlib.util
import math
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
CASE = Path(os.environ.get("BEELINE_CASE", os.getcwd())).resolve()
TEAM_AGENT = CASE / "agent.py"
CAMPAIGN_FIELDS = ["campaign_name", "filter_arpu_segment", "filter_data_segment",
                   "filter_call_segment", "filter_current_tariff", "target_tariff", "channel"]


def _load_team():
    if TEAM_AGENT.exists() and TEAM_AGENT != HERE / "agent.py":
        spec = importlib.util.spec_from_file_location("team_agent", TEAM_AGENT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.Agent, "team"
    from reference_agent import Agent as Reference
    return Reference, "reference"


def _history_counts(path):
    try:
        frame = pd.read_csv(path)
        previous = pd.to_numeric(frame["AVG_ARPU_PREV_3M"], errors="coerce")
        frame = frame[previous >= 100].copy()
        frame["seg"] = np.select([previous[previous >= 100] < 1000, previous[previous >= 100] <= 5000], ["LOW", "MID"], default="HIGH")
        return frame.groupby(["tariff_plan_code_from", "tariff_plan_code_to", "seg"]).size().to_dict()
    except (OSError, ValueError, KeyError):
        return {}


def _text(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return str(value)


class Agent:
    def __init__(self, observer=None, **_):
        cls, self.source = _load_team()
        params = getattr(cls.__init__, "__code__", None)
        self.inner = cls(verbose=False) if params and "verbose" in params.co_varnames else cls()
        self.observer = observer
        self.audit = {}

    def act(self, env):
        started = time.monotonic()
        totals = {"budget": float(env.total_budget), "contacts": int(env.max_total_contacts), "pilots": int(env.pilots_left)}
        plan = self.inner.act(env) or []
        inner_audit = getattr(self.inner, "audit", None)
        if isinstance(inner_audit, dict) and inner_audit.get("plan"):
            self.audit = inner_audit
        else:
            self.audit = self._build(env, plan, totals, started)
        self.audit.setdefault("config", {})["agent_source"] = self.source
        self.audit["config"]["agent_file"] = str(TEAM_AGENT if self.source == "team" else HERE / "reference_agent.py")
        if self.observer:
            self.observer({"type": "complete", "campaigns": len(plan)})
        return plan

    # ------------------------------------------------------------ mapping
    def _build(self, env, plan, totals, started):
        inner = self.inner
        hyps = getattr(inner, "hyps", None)
        records = list(getattr(inner, "records", []) or [])
        detail = list(getattr(inner, "plan_detail", []) or [])
        if hyps is None or not detail:
            raise ValueError("Team agent exposes neither audit nor records/hyps/plan_detail")
        mult = {c: float(v["conversion_multiplier"]) for c, v in env.channels.items()}
        hist = _history_counts(CASE / "data" / "change_tariff.csv")
        hid = lambda t, s, g: f"{t}_{s}_{g}"

        def members(campaign):
            tariffs = [t.strip() for t in str(campaign["filter_current_tariff"]).split(";") if t.strip()]
            return {(t, campaign["filter_arpu_segment"], campaign["target_tariff"]) for t in tariffs}

        channel_of, campaign_of, single = {}, {}, {}
        for c in detail:
            keys = members(c)
            for key in keys:
                channel_of[key] = c["channel"]
                campaign_of[key] = c["campaign_name"]
                single[key] = len(keys) == 1
        pilot_count = Counter((r["tariff"], r["seg"], r["target"]) for r in records)

        candidates, by_key = [], {}
        for row in hyps.itertuples(index=False):
            key = (row.tariff, row.seg, row.target)
            channel = channel_of.get(key, "sms")
            m = mult[channel]
            tested = int(row.n_obs) > 0
            selected = bool(single.get(key))
            decision = ("selected" if selected else f"part_of_campaign: {campaign_of[key]}" if key in campaign_of
                        else "unmeasured" if not tested else "not_selected: risk-adjusted lift below alternative or resource price")
            cand = {"id": hid(*key), "cell": f"{row.tariff}_{row.seg}", "current": row.tariff, "arpu": row.seg,
                    "target": row.target, "channel": channel, "prior_rank": float(row.mu0),
                    "history_n": int(hist.get((row.tariff, row.target, row.seg), 0)),
                    "n": int(row.n_obs), "mean": float(row.mu) * m, "se": float(row.sd) * m,
                    "basis": "pilots" if tested else "prior+calibration",
                    "mass": float(row.mass), "cell_size": int(row.n),
                    "pilot_count": int(pilot_count.get(key, 0)), "selected": selected, "decision": decision}
            candidates.append(cand)
            by_key[key] = cand

        pilots, before, seen = [], {"budget": totals["budget"], "contacts": totals["contacts"]}, Counter()
        for i, r in enumerate(records, 1):
            key = (r["tariff"], r["seg"], r["target"])
            seen[key] += 1
            m = mult[r["channel"]]
            pilots.append({
                "candidate": hid(*key),
                "filters": {"filter_arpu_segment": r["seg"], "filter_data_segment": None, "filter_call_segment": None,
                            "filter_current_tariff": r["tariff"], "target_tariff": r["target"], "channel": r["channel"]},
                "requested_n": int(r["n"]),
                "reason": (f"Initial: value-of-information pick, prior {float(r['prior_mu']):+.3f}" if seen[key] == 1
                           else "Repeat: posterior still close to the decision threshold"),
                "before": before,
                "result": {"pilot": f"pilot_{i}", "target_tariff": r["target"], "channel": r["channel"],
                           "n_customers": int(r["n"]), "cost": float(r["cost"]),
                           "observed_lift_ratio": float(r["observed"]),
                           "remaining_budget": float(r["budget_after"]), "remaining_contacts": int(r["contacts_after"])},
                "updated_mean": float(r["post_mu"]) * m, "updated_se": float(r["post_sd"]) * m})
            before = {"budget": float(r["budget_after"]), "contacts": int(r["contacts_after"])}

        plan_rows = []
        for c in detail:
            keys = members(c)
            rows = [by_key[k] for k in keys if k in by_key]
            m = mult[c["channel"]]
            if len(keys) == 1 and rows:
                cid = rows[0]["id"]
            else:
                mass = sum(r["mass"] for r in rows) or 1.0
                cid = c["campaign_name"]
                candidates.append({
                    "id": cid, "cell": f"{c['filter_current_tariff']}_{c['filter_arpu_segment']}",
                    "current": str(c["filter_current_tariff"]).replace(";", " + "), "arpu": c["filter_arpu_segment"],
                    "target": c["target_tariff"], "channel": c["channel"],
                    "prior_rank": sum(r["prior_rank"] * r["mass"] for r in rows) / mass,
                    "history_n": sum(r["history_n"] for r in rows), "n": sum(r["n"] for r in rows),
                    "mean": sum(r["mean"] / mult[r["channel"]] * r["mass"] for r in rows) / mass * m,
                    "se": math.sqrt(sum((r["se"] / mult[r["channel"]] * r["mass"]) ** 2 for r in rows)) / mass * m,
                    "basis": "pilots" if any(r["n"] for r in rows) else "prior+calibration",
                    "mass": mass, "cell_size": sum(r["cell_size"] for r in rows),
                    "pilot_count": sum(r["pilot_count"] for r in rows), "selected": True, "decision": "selected",
                    "members": [r["id"] for r in rows]})
            net, cost = float(c["value"]), float(c["cost"])
            plan_rows.append({"candidate": cid,
                              "campaign": {k: _text(c.get(k)) for k in CAMPAIGN_FIELDS},
                              "contacts": int(c["n"]), "cost": cost, "gross": net + cost, "net": net,
                              "conservative_net": None,
                              "reason": "Lagrangian allocation: best channel per cell under money and reach prices; packed into <=10 disjoint campaigns"})

        profile = env.customer_profile
        cells = (profile.dropna(subset=["current_tariff", "arpu_segment", "predicted_arpu"])
                 .groupby(["current_tariff", "arpu_segment"], observed=True)["predicted_arpu"]
                 .agg(["size", "sum", "mean"]).reset_index())
        last = pilots[-1]["result"] if pilots else None
        calibration = getattr(inner, "calibration", None)
        return {
            "version": 2, "events": [], "pilots": pilots, "candidates": candidates, "plan": plan_rows,
            "limits": totals,
            "uncertainty": "Posterior mean and sd per hypothesis (Gaussian update with noise 0.804/sqrt(n)), shown in the units of the campaign channel. Untested cells carry prior + calibration, not pilot evidence.",
            "calibration": {k: float(v) for k, v in calibration.items()} if isinstance(calibration, dict) else None,
            "quality": {"rows": int(len(profile)), "invalid_rows": int(profile[["current_tariff", "arpu_segment", "predicted_arpu"]].isna().any(axis=1).sum()),
                        "duplicate_ids": int(profile["ID_NUMBER"].duplicated().sum()), "missing_values": int(profile.isna().sum().sum())},
            "audience": {"rows": int(len(profile)), "baseline": float(profile["predicted_arpu"].sum()),
                         "cells": [{"id": f"{r.current_tariff}_{r.arpu_segment}", "current": r.current_tariff, "arpu": r.arpu_segment,
                                    "count": int(r.size), "baseline": float(r.sum), "average": float(r.mean)} for r in cells.itertuples(index=False)]},
            "remaining_after_pilots": {"budget": float(last["remaining_budget"]) if last else totals["budget"],
                                       "contacts": int(last["remaining_contacts"]) if last else totals["contacts"],
                                       "pilots": int(env.pilots_left)},
            "low_confidence_fallback": bool(plan_rows) and all(p["net"] <= 0 for p in plan_rows),
            "stop_reason": "Team agent finished its pilot loop", "elapsed_seconds": time.monotonic() - started,
        }
