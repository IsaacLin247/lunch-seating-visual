#!/usr/bin/env python
"""Run reproducible experiments with a pre-solve attempt ledger and full traces.

Example bounded study (explicitly select sensitivity options to avoid a large
implicit batch)::

    python sim/experiments.py --seed-values 1,2 --scenarios honest,coalition_min4 \\
        --skip-budgets --skip-communities

The default output is results/verified_experiments.json. Historical schema-1
summaries are retained as explicitly unverified legacy evidence if loaded; they
never satisfy a resume key for a new run. A terminal success means the full
chart passed validation, including when a preliminary CP check was UNKNOWN.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sim.generator import make_cohort  # noqa: E402
from sim.provenance import file_sha256, resume_fingerprint, source_provenance  # noqa: E402
from sim.scenarios import SCENARIOS, SubmissionReviewRequired, make_all, validate_trace  # noqa: E402
from sim.solver import InfeasibleInputError  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ("seeds", "budgets", "communities", "horizons")
# Imported modules stay in memory even when another process edits their files.
# A long-running batch must never label old loaded code with a new on-disk hash.
IMPORTED_SOURCE = source_provenance()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_json(path, value):
    """Replace one artifact only after its complete JSON has reached disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as f:
            tmp_path = Path(f.name)
            json.dump(value, f, indent=1, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


@contextmanager
def manifest_lock(path):
    """Refuse concurrent writers rather than losing another process's attempts."""
    lock = Path(str(path) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"another experiment process is writing {path}") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def load_manifest(path):
    path = Path(path)
    if not path.exists():
        return {"schemaVersion": 2, **{k: [] for k in CATEGORIES}, "attempts": [], "batches": [],
                "meta": {"createdAt": utc_now()}}
    with path.open() as f:
        old = json.load(f)
    if old.get("schemaVersion") == 2:
        return old
    if old.get("schemaVersion") not in (None, 1):
        raise ValueError("unsupported experiment manifest schema")
    return {"schemaVersion": 2, **{k: [] for k in CATEGORIES}, "attempts": [], "batches": [],
            "meta": {"createdAt": utc_now()},
            "legacy": {"status": "unverified_summary_only", "originalFileSha256": file_sha256(path),
                       "reason": "No pre-run attempt ledger, exact source identity or retained per-run traces; not used for resume or failure-rate claims.",
                       "summaryOnly": old}}


def summary_of(trace):
    cfg = trace["config"]
    out = {
        "seed": cfg["seed"], "populationSeed": cfg.get("populationSeed", cfg["seed"]),
        "solverSeed": cfg.get("solverSeed", cfg["seed"]),
        "scenario": cfg["scenario"], "rotations": cfg["rotations"],
        "annealIters": cfg["solver"]["annealIters"],
        "cpsatTime": cfg["solver"]["cpsatTime"], "workers": cfg["solver"]["workers"],
        "mu": cfg["network"]["mu"], "omega": cfg["network"]["omega"],
        "reciprocity": cfg["network"]["reciprocity"], "inGroupFrac": cfg["network"]["inGroupFrac"],
        "feasibility": {k: v["status"] for k, v in cfg["feasibility"].items()},
        "expectedDistinctRandom": cfg["baseline"]["expectedDistinctRandom"],
        "leakageForcedEdges": trace["leakage"]["forcedEdges"],
        "leakageStudents": trace["leakage"]["studentsWithForcedEdge"],
        "leakageFullyDeterminedStudents": len(trace["leakage"]["fullyDeterminedStudents"]),
        "leakageCompleteTruePositiveRecoveryStudents": len(trace["leakage"].get("completeTruePositiveRecoveryStudents", [])),
        "fairness": trace["fairness"], "yearSolveSeconds": cfg["yearSolveSeconds"],
        "screenReturned": cfg.get("screen", {}).get("nReturned"),
        "screenUnresolved": cfg.get("screen", {}).get("nUnresolved"),
        "config": cfg,
    }
    out.update(trace["summary"])
    out["pctExactly1ByRotation"] = [r["stats"]["pctExactly1"] for r in trace["rotations"]]
    out["metByRotation"] = [r["stats"]["meanDistinctMet"] for r in trace["rotations"]]
    out["metRandomByRotation"] = [r["stats"]["meanDistinctMetRandom"] for r in trace["rotations"]]
    if cfg["coalitionMode"]:
        out["coalitionPatternsByRotation"] = [r["coalition"]["pattern"] for r in trace["rotations"]]
    return out


def experiment_configuration(seed=7, scenario="honest", *, solver_seed=None,
                             anneal_iters=300_000, cpsat_time=3.5, workers=8,
                             deterministic=True, feasibility_time=20.0, rotations=16,
                             first_state="mixed", mu=0.0, omega=0.0,
                             cross_grade_group_frac=0.0, short_list_policy="none"):
    generator = inspect.signature(make_cohort).bind_partial(seed=seed, mu=mu, omega=omega,
                                                           cross_grade_group_frac=cross_grade_group_frac)
    generator.apply_defaults()
    return {"populationSeed": seed, "solverSeed": seed if solver_seed is None else solver_seed,
            "scenario": scenario, "generator": dict(generator.arguments),
            "submission": {"shortListPolicy": short_list_policy},
            "run": {"anneal_iters": anneal_iters, "cpsat_time": cpsat_time, "workers": workers,
                    "deterministic": deterministic, "feasibility_time": feasibility_time,
                    "rotations": rotations, "first_state": first_state}}


def _run_configuration(config, runner):
    gen = config["generator"]
    return runner(seed=config["populationSeed"], solver_seed=config["solverSeed"],
                  scenarios=[config["scenario"]], log=None, generator_config=gen,
                  mu=gen["mu"], omega=gen["omega"], cross_grade_group_frac=gen["cross_grade_group_frac"],
                  short_list_policy=config["submission"]["shortListPolicy"], **config["run"])[config["scenario"]]


def _valid_saved_success(attempt, output):
    if attempt["status"] != "success" or not attempt.get("traceEvidence"):
        return False
    evidence = attempt["traceEvidence"]
    path = output.parent / evidence["path"]
    return path.is_file() and file_sha256(path) == evidence["sha256"]


def run_experiments(jobs, output, *, runner=None, validator=None, source_reader=None, log=print):
    """Execute (category, full configuration) jobs; persist every attempted run.

    Exceptions are terminal error rows and do not erase prior successes or abort
    unrelated jobs. Keyboard interruption is recorded and propagated. An abrupt
    process termination leaves a running row, explicitly marked interrupted on
    the next exclusive resume. A changed source/config/version or missing trace
    cannot reuse a previous success.
    """
    output = Path(output).resolve()
    runner = make_all if runner is None else runner
    validator = validate_trace if validator is None else validator
    check_imported_source = source_reader is None
    source_reader = source_provenance if source_reader is None else source_reader
    jobs = list(jobs)
    with manifest_lock(output):
        manifest = load_manifest(output)
        for old in manifest["attempts"]:
            if old["status"] == "running":
                old.update(status="interrupted_unfinished", observedAtResume=utc_now(),
                           note="Previous process did not persist a terminal outcome; never counted as success.")
        batch = {"id": uuid.uuid4().hex, "startedAt": utc_now(), "plannedRuns": len(jobs),
                 "attemptIds": [], "reusedAttemptIds": []}
        manifest["batches"].append(batch)
        atomic_json(output, manifest)
        for category, config in jobs:
            if category not in CATEGORIES:
                raise ValueError(f"unknown experiment category: {category}")
            source = source_reader()
            identity = resume_fingerprint({"category": category, **config}, source)
            reusable = next((a for a in reversed(manifest["attempts"])
                             if a["fingerprint"] == identity and _valid_saved_success(a, output)), None)
            if reusable:
                batch["reusedAttemptIds"].append(reusable["id"])
                continue
            attempt = {"id": uuid.uuid4().hex, "batchId": batch["id"], "category": category,
                       "fingerprint": identity, "configuration": config, "source": source,
                       "status": "running", "startedAt": utc_now()}
            manifest["attempts"].append(attempt)
            batch["attemptIds"].append(attempt["id"])
            atomic_json(output, manifest)  # necessarily before generation or solving
            start = time.perf_counter()
            try:
                if check_imported_source and source["effectiveSourceHash"] != IMPORTED_SOURCE["effectiveSourceHash"]:
                    raise RuntimeError("Source changed after Python imported the simulation; restart the experiment process.")
                trace = _run_configuration(config, runner)
                validator(trace)
                trace_path = output.parent / (output.stem + "_traces") / (attempt["id"] + ".json")
                atomic_json(trace_path, trace)
                attempt["traceEvidence"] = {"path": str(trace_path.relative_to(output.parent)),
                                            "sha256": file_sha256(trace_path),
                                            "validation": "passed"}
                after = source_reader()
                unchanged = (after["effectiveSourceHash"] == source["effectiveSourceHash"]
                             and after["versions"] == source["versions"])
                attempt["sourceUnchangedDuringRun"] = unchanged
                if not unchanged:
                    attempt.update(status="source_changed", sourceAfter=after,
                                   note="Trace retained but excluded from verified summaries: source changed during execution.")
                else:
                    statuses = {k: v["status"] for k, v in trace["config"]["feasibility"].items()}
                    attempt.update(status="success", preliminaryFeasibilityStatuses=statuses,
                                   preliminaryUnknownStates=[s for s, status in statuses.items() if status == "UNKNOWN"],
                                   feasibilityEvidence="validated full seating trace")
                    summary = summary_of(trace)
                    summary.update(attemptId=attempt["id"], fingerprint=identity, evidenceStatus="verified_trace",
                                   traceEvidence=attempt["traceEvidence"], wallSeconds=round(time.perf_counter() - start, 3))
                    manifest[category].append(summary)
            except KeyboardInterrupt:
                attempt.update(status="interrupted", error={"type": "KeyboardInterrupt", "message": "User/process interrupt"},
                               finishedAt=utc_now(), wallSeconds=round(time.perf_counter() - start, 3))
                atomic_json(output, manifest)
                raise
            except Exception as exc:
                status = ("review_required" if isinstance(exc, SubmissionReviewRequired) else
                          "infeasible_input" if isinstance(exc, InfeasibleInputError) else
                          "unknown" if isinstance(exc, TimeoutError) else "error")
                attempt.update(status=status, error={"type": type(exc).__name__, "message": str(exc),
                                                    "traceback": traceback.format_exc()})
                for attr in ("status", "solver_status", "feasibility_status"):
                    if hasattr(exc, attr):
                        attempt["error"][attr] = str(getattr(exc, attr))
            attempt.update(finishedAt=utc_now(), wallSeconds=round(time.perf_counter() - start, 3))
            atomic_json(output, manifest)
            if log:
                log(f"{category}: population {config['populationSeed']} {config['scenario']} "
                    f"{config['run']['rotations']} rotations -> {attempt['status']} ({attempt['wallSeconds']:.1f}s)")
        new_attempts = [a for a in manifest["attempts"] if a["id"] in batch["attemptIds"]]
        batch.update(finishedAt=utc_now(), terminalCounts={s: sum(a["status"] == s for a in new_attempts)
                                                         for s in sorted({a["status"] for a in new_attempts})})
        batch["status"] = "completed" if all(a["status"] == "success" for a in new_attempts) else "completed_with_errors"
        manifest["meta"].update(updatedAt=utc_now(), latestBatchStatus=batch["status"],
                                attemptCount=len(manifest["attempts"]),
                                terminalCounts={s: sum(a["status"] == s for a in manifest["attempts"])
                                                for s in sorted({a["status"] for a in manifest["attempts"]})})
        atomic_json(output, manifest)
        return manifest


def _csv(value, cast):
    return [cast(x.strip()) for x in value.split(",") if x.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "results" / "verified_experiments.json"))
    ap.add_argument("--seeds", type=int, default=10, help="population seeds 1..N, unless --seed-values is supplied")
    ap.add_argument("--seed-values", help="comma-separated explicit population seeds")
    ap.add_argument("--scenarios", default="honest,coalition_min4", help="comma-separated scenario names")
    ap.add_argument("--solver-seed", type=int, help="default: use each population seed")
    ap.add_argument("--anneal-iters", type=int, default=300_000)
    ap.add_argument("--cpsat-time", type=float, default=3.5)
    ap.add_argument("--feasibility-time", type=float, default=20.0)
    ap.add_argument("--rotations", type=int, default=16)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--wall-time", action="store_true", help="use wall time instead of deterministic solver budgets")
    ap.add_argument("--skip-budgets", action="store_true")
    ap.add_argument("--anneal-budgets", default="100000,300000,900000")
    ap.add_argument("--cpsat-budgets", default="", help="optional CP budget sweep at fixed annealing budget")
    ap.add_argument("--horizons", default="", help="optional rotation horizons, e.g. 5,16,32; larger probes cost more")
    ap.add_argument("--skip-communities", action="store_true")
    ap.add_argument("--communities", default="0.6:0.3,1.0:0.0", help="comma-separated mu:omega settings")
    ap.add_argument("--sensitivity-seeds", default="7", help="population seeds for each sensitivity setting")
    ap.add_argument("--sensitivity-scenarios", default="honest")
    args = ap.parse_args(argv)
    seeds = _csv(args.seed_values, int) if args.seed_values is not None else list(range(1, args.seeds + 1))
    scenarios = _csv(args.scenarios, str)
    sensitivity_seeds = _csv(args.sensitivity_seeds, int)
    sensitivity_scenarios = _csv(args.sensitivity_scenarios, str)
    if args.seeds < 0 or any(s < 0 for s in seeds + sensitivity_seeds):
        ap.error("seeds must be nonnegative")
    if set(scenarios + sensitivity_scenarios) - set(SCENARIOS):
        ap.error("unknown scenario; choices: " + ",".join(SCENARIOS))
    base = {"solver_seed": args.solver_seed, "anneal_iters": args.anneal_iters,
            "cpsat_time": args.cpsat_time, "feasibility_time": args.feasibility_time,
            "workers": args.workers, "deterministic": not args.wall_time, "rotations": args.rotations}
    jobs = []
    def add(category, selected_seeds, selected_scenarios, **changes):
        settings = {**base, **changes}
        if not 1 <= settings["rotations"] <= 64:
            ap.error("rotation horizons must lie in 1..64")
        if settings["anneal_iters"] < 0 or settings["cpsat_time"] < 0 or settings["feasibility_time"] < 0 or settings["workers"] < 1:
            ap.error("budgets must be nonnegative and workers positive")
        for seed in selected_seeds:
            for scenario in selected_scenarios:
                jobs.append((category, experiment_configuration(seed, scenario, **settings)))
    add("seeds", seeds, scenarios)
    if not args.skip_budgets:
        for iters in _csv(args.anneal_budgets, int):
            add("budgets", sensitivity_seeds, sensitivity_scenarios, anneal_iters=iters)
        for budget in _csv(args.cpsat_budgets, float):
            add("budgets", sensitivity_seeds, sensitivity_scenarios, cpsat_time=budget)
    for horizon in _csv(args.horizons, int):
        add("horizons", sensitivity_seeds, sensitivity_scenarios, rotations=horizon)
    if not args.skip_communities:
        for setting in _csv(args.communities, str):
            try:
                mu, omega = map(float, setting.split(":"))
            except ValueError:
                ap.error("community settings must be mu:omega")
            if not 0 <= mu <= 1 or not 0 <= omega <= 1:
                ap.error("mu and omega must lie in [0,1]")
            add("communities", sensitivity_seeds, sensitivity_scenarios, mu=mu, omega=omega)
    return run_experiments(jobs, args.out)


if __name__ == "__main__":
    main()
