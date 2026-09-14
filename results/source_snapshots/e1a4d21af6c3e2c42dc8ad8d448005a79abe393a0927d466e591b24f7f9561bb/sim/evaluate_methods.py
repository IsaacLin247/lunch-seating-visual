#!/usr/bin/env python
"""Method comparison on common populations, conditions and inputs.

Every job is a full-year run recorded in the same attempt ledger as the main
study (category ``evaluation``), so validity, runtime, objective components,
individual outcome distributions and fallback frequency come from retained,
independently checkable traces.  The matched random baseline is computed
inside every run on the same present roster and occupancy targets.

Methods
  hybrid            construction, repair, annealing, exact CP-SAT, validated fallbacks
  construct_repair  construction and repair with the feasibility fallback only

Conditions (all on the same population seed)
  reference          honest lists of up to eight names
  short_lists        generated lists truncated to four names (approved exceptions where the rule fails)
  three_name_lists   generated lists truncated to three names, all approved exceptions
  concentrated       isolated latent communities (mu = 1, omega = 0)
  nonsubmission      one quarter of students submit nothing
  absences           six percent synthetic absence rate, waivers recorded for unavoidable conflicts
  coalition_star     the six-member omission star
  shared_anchor      the seven-member shared-anchor attack (screens off)
  infeasible         the known infeasible demand core with a 240-unit feasibility budget
                     (proven infeasible; nothing scheduled)
  time_limited       tiny preliminary feasibility and CP budgets on honest lists (the
                     UNKNOWN precheck does not block a later validated chart)
  time_limited_infeasible
                     the infeasible core with a tiny feasibility budget: bounded search
                     ends without a chart and the outcome is reported as unknown, not as
                     a proof of infeasibility

Example::

    python sim/evaluate_methods.py --seed-values 1,2,3 --anneal-iters 100000 --cpsat-time 1.0 \\
        --out results/revised_evaluation.json
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sim.experiments import ROOT, experiment_configuration, run_experiments  # noqa: E402
from sim.scenarios import METHODS  # noqa: E402

CONDITIONS = {
    "reference": {},
    "short_lists": {"list_cap": 4, "short_list_policy": "approve"},
    "three_name_lists": {"list_cap": 3, "short_list_policy": "approve"},
    "concentrated": {"mu": 1.0, "omega": 0.0},
    "nonsubmission": {"nonsubmit_frac": 0.25},
    "absences": {"absence_rate": 0.06, "conflict_policy": "waive"},
    "coalition_star": {"scenario": "coalition_min4"},
    "shared_anchor": {"scenario": "coalition_shared_anchor"},
    "infeasible": {"scenario": "infeasible_demand", "feasibility_time": 240.0},
    "time_limited": {"feasibility_time": 0.02, "cpsat_time": 0.02},
    "time_limited_infeasible": {"scenario": "infeasible_demand", "feasibility_time": 0.02, "cpsat_time": 0.02},
}


def build_jobs(seeds, conditions, methods, base, extra_solver_seeds=()):
    jobs = []
    for seed in seeds:
        for name in conditions:
            settings = {**base, **CONDITIONS[name]}
            scenario = settings.pop("scenario", "honest")
            solver_seeds = [None] + ([seed + s for s in extra_solver_seeds] if name == "reference" else [])
            for solver_seed in solver_seeds:
                for method in methods:
                    config = experiment_configuration(seed, scenario, solver_seed=solver_seed, method=method, **settings)
                    config["condition"] = name
                    jobs.append(("evaluation", config))
    return jobs


def _csv(value, cast):
    return [cast(x.strip()) for x in value.split(",") if x.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "results" / "revised_evaluation.json"))
    ap.add_argument("--seed-values", default="1,2,3", help="population seeds")
    ap.add_argument("--extra-solver-seeds", default="100", help="additional solver seed offsets for the reference condition")
    ap.add_argument("--conditions", default=",".join(CONDITIONS))
    ap.add_argument("--methods", default=",".join(METHODS))
    ap.add_argument("--anneal-iters", type=int, default=100_000)
    ap.add_argument("--cpsat-time", type=float, default=1.0)
    ap.add_argument("--feasibility-time", type=float, default=10.0)
    ap.add_argument("--rotations", type=int, default=16)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--extra-weight", type=float, default=1.0)
    args = ap.parse_args(argv)
    conditions = _csv(args.conditions, str)
    methods = _csv(args.methods, str)
    if set(conditions) - set(CONDITIONS) or set(methods) - set(METHODS):
        ap.error("unknown condition or method")
    base = {"anneal_iters": args.anneal_iters, "cpsat_time": args.cpsat_time,
            "feasibility_time": args.feasibility_time, "rotations": args.rotations, "workers": args.workers,
            "extra_weight": args.extra_weight}
    jobs = build_jobs(_csv(args.seed_values, int), conditions, methods, base,
                      extra_solver_seeds=_csv(args.extra_solver_seeds, int))
    print(f"{len(jobs)} evaluation jobs", flush=True)
    return run_experiments(jobs, args.out)


if __name__ == "__main__":
    main()
