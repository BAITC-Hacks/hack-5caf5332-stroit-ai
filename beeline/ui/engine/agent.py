"""Public-API-only adaptive agent. Does not import evaluator or mock internals."""
from pathlib import Path
import math
import time

import numpy as np
import pandas as pd


class Agent:
    def __init__(self, history_path=None, max_pilots=20, uncertainty_penalty=1.0, observer=None):
        self.history_path = Path(history_path) if history_path is not None else Path(__file__).parent / "data/change_tariff.csv"
        self.max_pilots = min(20, max(1, int(max_pilots)))
        self.penalty = float(uncertainty_penalty)
        self.observer = observer
        self.audit = {}

    def emit(self, event):
        self.audit["events"].append(event)
        if self.observer:
            self.observer(event)

    def history(self):
        """Ranking signal among historical switchers, NOT conversion probability."""
        try:
            frame = pd.read_csv(self.history_path)
            previous = pd.to_numeric(frame["AVG_ARPU_PREV_3M"], errors="coerce")
            following = pd.to_numeric(frame["AVG_ARPU_NEXT_3M"], errors="coerce")
            valid = (previous >= 100) & np.isfinite(previous) & np.isfinite(following) & (following >= 0)
            frame = frame.loc[valid].copy()
            frame["ratio"] = ((following[valid] - previous[valid]) / previous[valid]).clip(-1, 2)
            frame["arpu_segment"] = np.select([previous[valid] < 1000, previous[valid] <= 5000], ["LOW", "MID"], default="HIGH")
            grouped = frame.groupby(["tariff_plan_code_from", "tariff_plan_code_to", "arpu_segment"])["ratio"].agg(["median", "count"])
            self.audit["history"] = {"available": True, "rows": int(len(previous)), "usable_rows": int(valid.sum()), "min_previous_arpu": 100, "ratio_clip": [-1, 2], "use": "shortlist only; not a conversion estimate"}
            return {key: {"median": float(row["median"]), "n": int(row["count"])} for key, row in grouped.iterrows()}
        except (OSError, ValueError, KeyError) as exc:
            self.audit["history"] = {"available": False, "warning": str(exc)}
            return {}

    @staticmethod
    def campaign(c):
        return {"campaign_name": c["id"], "filter_arpu_segment": c["arpu"],
                "filter_data_segment": None, "filter_call_segment": None,
                "filter_current_tariff": c["current"], "target_tariff": c["target"], "channel": c["channel"]}

    def act(self, env):
        started = time.monotonic()
        self.audit = {"version": 1, "events": [], "pilots": [], "candidates": [], "plan": [],
                      "limits": {"budget": float(env.remaining_budget), "contacts": int(env.remaining_contacts), "pilots": int(env.pilots_left)},
                      "uncertainty": "Approximate SE=0.804/sqrt(actual n), inflated 20%; not a calibrated confidence guarantee. Repeat overlap is unknown.",
                      "config": {"max_pilots": self.max_pilots, "uncertainty_penalty": self.penalty, "deadline_seconds": 270}}
        profile = env.customer_profile.copy()
        required = {"ID_NUMBER", "current_tariff", "arpu_segment", "predicted_arpu"}
        if not required.issubset(profile.columns):
            raise ValueError("Missing required profile columns: " + str(sorted(required - set(profile.columns))))
        tariffs = sorted(set(env.tariffs["tariff_plan_code"].dropna().astype(str)))
        prices = dict(zip(env.tariffs["tariff_plan_code"], env.tariffs.get("price_tariff", pd.Series(0, index=env.tariffs.index))))
        predicted = pd.to_numeric(profile["predicted_arpu"], errors="coerce")
        valid = (np.isfinite(predicted) & (predicted >= 0) & profile.current_tariff.isin(tariffs)
                 & profile.arpu_segment.isin(["LOW", "MID", "HIGH"]) & profile.ID_NUMBER.notna())
        self.audit["quality"] = {"rows": len(profile), "invalid_rows": int((~valid).sum()),
                                  "duplicate_ids": int(profile.ID_NUMBER.duplicated().sum()),
                                  "missing_values": int(profile.isna().sum().sum())}
        if self.audit["quality"]["duplicate_ids"]:
            raise ValueError("Duplicate customer IDs: resolve input quality before planning")
        eligible_cell = profile.current_tariff.isin(tariffs) & profile.arpu_segment.isin(["LOW", "MID", "HIGH"])
        if ((~valid) & eligible_cell).any():
            # The submission contract has segment filters, not per-row exclusions.
            # Unknown ARPU/tariff cells are excluded by the same final filters;
            # corrupt ID/baseline inside a selected cell cannot be excluded safely.
            raise ValueError("Invalid required customer fields: resolve input quality before planning")
        profile = profile.loc[valid].copy()
        profile["predicted_arpu"] = predicted[valid]
        profile = profile.sort_values("ID_NUMBER")
        self.audit["audience"] = {"rows": len(profile), "baseline": float(profile.predicted_arpu.sum()), "cells": []}
        channels = {key: float(value["cost_per_contact"]) for key, value in env.channels.items()
                    if key in {"push", "sms", "digital_ads", "call"} and float(value["cost_per_contact"]) >= 0}
        if profile.empty or len(tariffs) < 2 or not channels or env.remaining_contacts <= 0:
            self.audit["stop_reason"] = "No eligible audience, tariffs, channels or contacts"
            self.audit["elapsed_seconds"] = time.monotonic() - started
            return []
        hist = self.history()
        cells = []
        for (current, arpu), group in profile.groupby(["current_tariff", "arpu_segment"], sort=True, observed=True):
            cell = {"id": f"{current}_{arpu}", "current": current, "arpu": arpu,
                    "count": len(group), "baseline": float(group.predicted_arpu.sum()),
                    "average": float(group.predicted_arpu.mean())}
            cells.append((cell, group))
        cells.sort(key=lambda pair: (-pair[0]["baseline"], pair[0]["id"]))
        self.audit["audience"]["cells"] = [cell for cell, _ in cells]
        frames = {cell["id"]: group for cell, group in cells}
        cell_map = {cell["id"]: cell for cell, _ in cells}
        base_channel = "sms" if "sms" in channels and channels["sms"] <= 10 and env.remaining_budget >= channels["sms"] * 50 else min(channels, key=channels.get)
        pool = []

        def add(cell, target, channel, prior, prior_n):
            key = f'{cell["id"]}_{target}_{channel}'
            if any(c["id"] == key for c in pool):
                return
            pool.append({"id": key, "cell": cell["id"], "current": cell["current"], "arpu": cell["arpu"],
                         "target": target, "channel": channel, "prior_rank": prior, "history_n": prior_n,
                         "n": 0, "weighted_sum": 0.0, "mean": None, "se": None, "pilot_count": 0})

        for cell, _ in cells[:12]:
            def rank(target):
                h = hist.get((cell["current"], target, cell["arpu"]), {})
                # Unknown transitions remain eligible; price distance is only a tie-breaker.
                return (-(h.get("median", 0.0) * min(1.0, h.get("n", 0) / 30)),
                        abs(float(prices.get(target, 0) or 0) - float(prices.get(cell["current"], 0) or 0)), target)
            options = sorted((t for t in tariffs if t != cell["current"]), key=rank)
            for target in options[:2]:
                h = hist.get((cell["current"], target, cell["arpu"]), {})
                add(cell, target, base_channel, float(h.get("median", 0)), int(h.get("n", 0)))
        initial = [next(c for c in pool if c["cell"] == cell["id"]) for cell, _ in cells[:8]]
        reserve = min(1500, max(1, int(env.remaining_contacts * 0.1)))
        successful = 0
        while successful < self.max_pilots and env.pilots_left > 0 and time.monotonic() - started < 270:
            if env.remaining_contacts < reserve + 10:
                self.audit["stop_reason"] = "Contact reserve for final plan"
                break
            measured = [c for c in pool if c["n"] > 0]
            pending = [c for c in initial if c["n"] == 0 and not c.get("failed")]
            if pending:
                chosen, reason = pending[0], "Initial exploration: high-baseline cell and history-ranked transition"
            else:
                # Compare alternative channels only after evidence on that exact transition.
                promising = sorted(measured, key=lambda c: -(c["mean"] - self.penalty * c["se"]) * cell_map[c["cell"]]["baseline"])
                for c in promising[:3]:
                    if c["mean"] > c["se"]:
                        for channel in channels:
                            if channels[channel] * 80 <= min(10000, env.remaining_budget * 0.15):
                                add(cell_map[c["cell"]], c["target"], channel, c["mean"], 0)
                untested = [c for c in pool if not c["n"] and not c.get("failed")
                            and channels[c["channel"]] * 80 <= max(0, env.remaining_budget * 0.2)]
                repeats = [c for c in measured if not c.get("failed") and c["n"] < 480 and c["mean"] + 1.28 * c["se"] > 0]
                if untested and (successful % 3 == 2 or not repeats):
                    chosen = max(untested, key=lambda c: (cell_map[c["cell"]]["baseline"] * (0.1 + max(0, min(0.5, c["prior_rank"]))), c["id"]))
                    reason = "Explore alternative transition/channel; ranking signal is not a predicted conversion"
                elif repeats:
                    chosen = max(repeats, key=lambda c: (cell_map[c["cell"]]["baseline"] * c["se"] * max(0, c["mean"] + c["se"]), c["id"]))
                    reason = "Repeat a promising uncertain candidate; update weighted estimate using actual sample size"
                else:
                    self.audit["stop_reason"] = "No affordable informative experiment"
                    break
            size = 80 if not chosen["n"] else (200 if chosen["mean"] > chosen["se"] else 160)
            unit = channels[chosen["channel"]]
            size = min(size, env.remaining_contacts - reserve)
            if unit:
                size = min(size, int(max(0, env.remaining_budget * 0.2) // unit))
            if size < 10:
                chosen["failed"] = True
                if chosen in initial:
                    initial.remove(chosen)
                if all(c.get("failed") for c in pool):
                    break
                continue
            request = {k: v for k, v in self.campaign(chosen).items() if k != "campaign_name"}
            before = {"budget": float(env.remaining_budget), "contacts": int(env.remaining_contacts)}
            try:
                result = env.run_pilot(n_customers=int(size), **request)
            except (RuntimeError, ValueError) as exc:
                chosen["failed"] = True
                self.emit({"type": "pilot_error", "candidate": chosen["id"], "message": str(exc)})
                if len([c for c in pool if c.get("failed")]) >= 5:
                    break
                continue
            n, ratio = int(result["n_customers"]), float(result["observed_lift_ratio"])
            if n <= 0 or not math.isfinite(ratio):
                raise ValueError("Pilot returned an invalid observation")
            chosen["n"] += n
            chosen["weighted_sum"] += ratio * n
            chosen["mean"] = chosen["weighted_sum"] / chosen["n"]
            chosen["se"] = 1.2 * 0.804 / math.sqrt(chosen["n"])
            chosen["pilot_count"] += 1
            entry = {"candidate": chosen["id"], "filters": request, "requested_n": int(size),
                     "reason": reason, "before": before, "result": result,
                     "updated_mean": chosen["mean"], "updated_se": chosen["se"]}
            self.audit["pilots"].append(entry)
            successful += 1
            self.emit({"type": "pilot", "number": successful, "candidate": chosen["id"], "observed_ratio": ratio,
                       "remaining_budget": float(env.remaining_budget), "remaining_contacts": int(env.remaining_contacts)})

        budget, contacts = float(env.remaining_budget), int(env.remaining_contacts)
        selected, occupied = [], set()
        measured = [c for c in pool if c["n"] > 0]

        def estimate(c):
            count = min(5000, contacts)
            if channels[c["channel"]]:
                count = min(count, int(budget // channels[c["channel"]]))
            group = frames[c["cell"]].iloc[:max(0, count)]
            baseline = float(group.predicted_arpu.sum())
            cost = len(group) * channels[c["channel"]]
            return {"contacts": len(group), "cost": cost, "gross": baseline * c["mean"],
                    "net": baseline * c["mean"] - cost,
                    "conservative_net": baseline * (c["mean"] - self.penalty * c["se"]) - cost}

        while len(selected) < 10 and contacts > 0:
            options = [(c, estimate(c)) for c in measured if c["cell"] not in occupied]
            options = [(c, e) for c, e in options if e["contacts"] and e["conservative_net"] > 0]
            if not options:
                break
            c, e = max(options, key=lambda pair: (pair[1]["conservative_net"], pair[0]["id"]))
            selected.append({"candidate": c["id"], "campaign": self.campaign(c), **e,
                             "reason": "Highest remaining conservative net; non-overlapping final cell"})
            occupied.add(c["cell"])
            budget -= e["cost"]
            contacts -= e["contacts"]
        if not selected and contacts > 0:
            # Contract requires a nonempty campaign, not a fabricated positive result.
            affordable = [(c, estimate(c)) for c in measured if estimate(c)["contacts"] > 0]
            if affordable:
                c, e = max(affordable, key=lambda pair: pair[1]["conservative_net"])
                selected = [{"candidate": c["id"], "campaign": self.campaign(c), **e, "reason": "low_confidence_fallback"}]
                self.audit["low_confidence_fallback"] = True
            else:
                cell = min((pair[0] for pair in cells), key=lambda c: (c["count"], c["id"]))
                channel = min(channels, key=channels.get)
                affordable_count = contacts if not channels[channel] else int(budget // channels[channel])
                count = min(5000, cell["count"], contacts, affordable_count)
                if count > 0:
                    target = next(t for t in tariffs if t != cell["current"])
                    add(cell, target, channel, 0, 0)
                    c = next(c for c in pool if c["cell"] == cell["id"] and c["target"] == target and c["channel"] == channel)
                    selected = [{"candidate": c["id"], "campaign": self.campaign(c), "contacts": count,
                                 "cost": count * channels[channel], "gross": None, "net": None,
                                 "conservative_net": None, "reason": "low_confidence_fallback: no observations"}]
                    self.audit["low_confidence_fallback"] = True
        self.audit["plan"] = selected
        chosen_ids = {p["candidate"] for p in selected}
        self.audit["candidates"] = [{k: v for k, v in c.items() if k != "weighted_sum"} |
            {"selected": c["id"] in chosen_ids,
             "decision": "selected" if c["id"] in chosen_ids else "unmeasured" if not c["n"] else "not_selected: uncertainty, alternative in same cell or resource tradeoff"}
            for c in pool]
        self.audit["remaining_after_pilots"] = {"budget": float(env.remaining_budget), "contacts": int(env.remaining_contacts), "pilots": int(env.pilots_left)}
        self.audit["stop_reason"] = self.audit.get("stop_reason", "Pilot allowance or time limit reached")
        self.audit["elapsed_seconds"] = time.monotonic() - started
        self.emit({"type": "complete", "campaigns": len(selected)})
        return [p["campaign"] for p in selected]
