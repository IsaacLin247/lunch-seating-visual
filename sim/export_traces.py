#!/usr/bin/env python
"""Generate every scenario trace and write docs/data/*.json.

    python sim/export_traces.py                # full quality, deterministic
    python sim/export_traces.py --fast         # quick smoke run (weaker solutions)
    python sim/export_traces.py --scenarios honest,coalition_none

Traces are deterministic for a given seed: the generator and annealer are
seeded and CP-SAT runs in its deterministic (interleaved) mode by default.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sim.scenarios import SCENARIOS, make_all  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "data"))
    ap.add_argument("--scenarios", default=",".join(SCENARIOS))
    ap.add_argument("--anneal-iters", type=int, default=300_000)
    ap.add_argument("--cpsat-time", type=float, default=3.5, help="CP-SAT budget per rotation (deterministic time, or seconds with --wallclock)")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--wallclock", action="store_true", help="multi-threaded wall-clock CP-SAT (faster, not bit-reproducible)")
    ap.add_argument("--fast", action="store_true", help="tiny budgets for smoke tests")
    args = ap.parse_args(argv)
    if args.fast:
        args.anneal_iters = 30_000
        args.cpsat_time = 1.0
    os.makedirs(args.out, exist_ok=True)
    t0 = time.perf_counter()
    traces = make_all(seed=args.seed, scenarios=args.scenarios.split(","), anneal_iters=args.anneal_iters,
                      cpsat_time=args.cpsat_time, workers=args.workers, deterministic=not args.wallclock)
    index = {"scenarios": [], "seed": args.seed}
    total = 0
    for name, trace in traces.items():
        path = os.path.join(args.out, f"{name}.json")
        with open(path, "w") as f:
            json.dump(trace, f, separators=(",", ":"))
        size = os.path.getsize(path)
        total += size
        index["scenarios"].append({"name": name, "file": f"{name}.json", "title": trace["config"]["title"],
                                   "short": trace["config"]["short"], "summary": trace["summary"],
                                   "bytes": size})
        print(f"wrote {path} ({size/1024:.0f} KB) summary={trace['summary']}")
    with open(os.path.join(args.out, "index.json"), "w") as f:
        json.dump(index, f, separators=(",", ":"))
    print(f"total data {total/1024:.0f} KB in {time.perf_counter()-t0:.0f}s")


if __name__ == "__main__":
    main()
