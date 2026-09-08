#!/usr/bin/env python
"""Robustness experiments: independent population seeds, solver budgets and
community regimes.  Writes results/experiments.json incrementally.

    python sim/experiments.py --seeds 10            # ~80 min on 8 cores

Each run is a full 16-rotation year at the export defaults unless stated; only
summaries are stored (the full traces are ~160 KB each).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sim.scenarios import make_all  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def summary_of(trace):
    cfg = trace["config"]
    out = {
        "seed": cfg["seed"], "scenario": cfg["scenario"], "annealIters": cfg["solver"]["annealIters"],
        "cpsatTime": cfg["solver"]["cpsatTime"], "workers": cfg["solver"]["workers"],
        "mu": cfg["network"]["mu"], "omega": cfg["network"]["omega"],
        "reciprocity": cfg["network"]["reciprocity"], "inGroupFrac": cfg["network"]["inGroupFrac"],
        "feasibility": {k: v["status"] for k, v in cfg["feasibility"].items()},
        "expectedDistinctRandom": cfg["baseline"]["expectedDistinctRandom"],
        "leakageForcedEdges": trace["leakage"]["forcedEdges"],
        "leakageStudents": trace["leakage"]["studentsWithForcedEdge"],
        "fairness": trace["fairness"],
        "yearSolveSeconds": cfg["yearSolveSeconds"],
        "screenReturned": cfg.get("screen", {}).get("nReturned"),
    }
    out.update({k: v for k, v in trace["summary"].items()})
    out["pctExactly1ByRotation"] = [r["stats"]["pctExactly1"] for r in trace["rotations"]]
    out["metByRotation"] = [r["stats"]["meanDistinctMet"] for r in trace["rotations"]]
    out["metRandomByRotation"] = [r["stats"]["meanDistinctMetRandom"] for r in trace["rotations"]]
    if cfg["coalitionMode"]:
        out["coalitionPatternsByRotation"] = [r["coalition"]["pattern"] for r in trace["rotations"]]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "experiments.json"))
    ap.add_argument("--seeds", type=int, default=10, help="population seeds 1..N")
    ap.add_argument("--skip-budgets", action="store_true")
    ap.add_argument("--skip-communities", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    results = {"seeds": [], "budgets": [], "communities": [], "meta": {"started": time.strftime("%Y-%m-%dT%H:%M:%S")}}
    if os.path.exists(args.out):
        with open(args.out) as f:
            results = json.load(f)

    def save():
        with open(args.out, "w") as f:
            json.dump(results, f, indent=1)

    done = {(r["scenario"], r["seed"]) for r in results["seeds"]}
    for seed in range(1, args.seeds + 1):
        for scenario in ("honest", "coalition_min4"):
            if (scenario, seed) in done:
                continue
            t0 = time.perf_counter()
            traces = make_all(seed=seed, scenarios=[scenario], log=None, workers=args.workers)
            s = summary_of(traces[scenario])
            s["wallSeconds"] = round(time.perf_counter() - t0, 1)
            results["seeds"].append(s)
            save()
            print(f"seed {seed} {scenario}: exactly1 {s['pctExactly1Mean']} met {s['meanDistinctMetFinal']} vs {s['meanDistinctMetFinalRandom']} "
                  f"(expected {s['expectedDistinctRandom']}) cluster {s.get('coalitionAvgCluster')} {s['wallSeconds']}s", flush=True)

    if not args.skip_budgets:
        done_b = {r["annealIters"] for r in results["budgets"]}
        for iters in (100_000, 300_000, 900_000):
            if iters in done_b:
                continue
            t0 = time.perf_counter()
            traces = make_all(seed=7, scenarios=["honest"], log=None, anneal_iters=iters, workers=args.workers)
            s = summary_of(traces["honest"])
            s["wallSeconds"] = round(time.perf_counter() - t0, 1)
            results["budgets"].append(s)
            save()
            print(f"budget {iters}: exactly1 {s['pctExactly1Mean']} met {s['meanDistinctMetFinal']} max solve {s['maxSolveSeconds']}s {s['wallSeconds']}s", flush=True)

    if not args.skip_communities:
        done_c = {(r["mu"], r["omega"]) for r in results["communities"]}
        for mu, omega in ((0.6, 0.3), (1.0, 0.0)):
            if (mu, omega) in done_c:
                continue
            t0 = time.perf_counter()
            traces = make_all(seed=7, scenarios=["honest"], log=None, mu=mu, omega=omega, workers=args.workers)
            s = summary_of(traces["honest"])
            s["wallSeconds"] = round(time.perf_counter() - t0, 1)
            results["communities"].append(s)
            save()
            print(f"community mu={mu} omega={omega}: exactly1 {s['pctExactly1Mean']} met {s['meanDistinctMetFinal']} vs {s['meanDistinctMetFinalRandom']} {s['wallSeconds']}s", flush=True)
    results["meta"]["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save()


if __name__ == "__main__":
    main()
