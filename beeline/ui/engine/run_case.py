"""External runner. Evaluator results never enter Agent.act or its decisions."""
import argparse
import os
import sys
import contextlib
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import time
import uuid

ROOT = Path(os.getcwd()).resolve()  # case folder: organizer scripts and data
sys.path.append(str(ROOT))

from agent import Agent
from agent_template import Agent as Starter
from local_eval import evaluate_agent
from make_submission import CAMPAIGN_COLUMNS
import pandas as pd



def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if hasattr(value, "item"):
        return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def manifest():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [ROOT / "customer_profile.csv", ROOT / "data/change_tariff.csv", ROOT / "data/dict_tariff.csv"]}


def dataset():
    profile = pd.read_csv(ROOT / "customer_profile.csv")
    groups = profile.groupby(["current_tariff", "arpu_segment"], observed=True).agg(
        count=("ID_NUMBER", "size"), baseline=("predicted_arpu", "sum"), average=("predicted_arpu", "mean")).reset_index()
    groups = groups.sort_values(["baseline", "current_tariff"], ascending=[False, True])
    history_rows = len(pd.read_csv(ROOT / "data/change_tariff.csv"))
    return clean({"rows": len(profile), "baseline": profile.predicted_arpu.sum(), "history_rows": history_rows,
                  "cells": [{"id": f'{r.current_tariff}_{r.arpu_segment}', "current": r.current_tariff,
                             "arpu": r.arpu_segment, "count": r.count, "baseline": r.baseline, "average": r.average}
                            for r in groups.itertuples(index=False)],
                  "quality": {"duplicate_ids": int(profile.ID_NUMBER.duplicated().sum()), "missing_values": int(profile.isna().sum().sum())},
                  "data_hashes": manifest(), "source": "Organizer participant pack; synthetic, not production Beeline data"})


def run(seed=42, observer=None):
    agent = Agent(observer=observer)
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        result = evaluate_agent(agent, seed=seed, verbose=False)
    if not agent.audit.get("plan") or "Агент упал" in log.getvalue() or "отброшена" in log.getvalue():
        raise RuntimeError("Agent did not produce a valid plan: " + log.getvalue())
    return clean({"mode": "organizer_mock", "run_id": uuid.uuid4().hex, "seed": seed, "created_at": time.time(),
                  "data_hashes": manifest(), "audit": agent.audit, "evaluation": result,
                  "evaluation_note": "Post-run mock evaluator result, NOT a forecast or future judging score.",
                  "log": log.getvalue()})


def benchmark(runs=10):
    rows = []
    for seed in range(runs):
        started = time.monotonic()
        agent = Agent()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            baseline = evaluate_agent(Starter(), seed=seed, verbose=False)
            actual = evaluate_agent(agent, seed=seed, verbose=False)
        if "Агент упал" in buffer.getvalue() or "отброшена" in buffer.getvalue():
            raise RuntimeError(buffer.getvalue())
        if not actual or not 1 <= len(agent.audit.get("plan", [])) <= 10:
            raise RuntimeError("Invalid final plan")
        assert actual["total_contacts"] <= 15000 and actual["total_cost"] <= 100000
        rows.append({"seed": seed, "starter_net": baseline["net_arpu_gain"], "agent_net": actual["net_arpu_gain"],
                     "contacts": actual["total_contacts"], "cost": actual["total_cost"],
                     "pilots": actual["n_pilots"], "campaigns": len(agent.audit["plan"]),
                     "seconds": time.monotonic() - started})
    def summary(key):
        values = [float(row[key]) for row in rows]
        return {"mean": statistics.mean(values), "median": statistics.median(values), "min": min(values),
                "max": max(values), "positive": sum(v > 0 for v in values)}
    return clean({"runs": rows, "starter": summary("starter_net"), "agent": summary("agent_net"),
                  "wins": sum(r["agent_net"] > r["starter_net"] for r in rows),
                  "note": "Same seed set; only organizer mock. No guarantee on hidden effects."})


def save_result(result, directory):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "run.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    campaigns = [p["campaign"] for p in result["audit"]["plan"]]
    pd.DataFrame(campaigns).reindex(columns=CAMPAIGN_COLUMNS).to_csv(directory / "submission.csv", index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=int, default=0)
    parser.add_argument("--out", default="../outputs")
    parser.add_argument("--describe", action="store_true")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.describe:
        print(json.dumps(dataset(), ensure_ascii=False))
    elif args.benchmark:
        report = benchmark(args.benchmark)
        (out / "benchmark.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        result = run()
        save_result(result, out)
        print(json.dumps({"net": result["evaluation"]["net_arpu_gain"], "pilots": len(result["audit"]["pilots"]), "campaigns": len(result["audit"]["plan"])}))
