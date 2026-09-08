"""Regression tests for truthful attempt counts and exact-source resumption."""
import copy
import json
from pathlib import Path

import pytest

from sim.experiments import experiment_configuration, load_manifest, run_experiments
from sim.provenance import fingerprint, resume_fingerprint, source_provenance


SOURCE = {"effectiveSourceHash": "test-source-v1", "versions": {"python": "test", "ortools": "test"}}


def sample_trace(seed=7, source=None, **kwargs):
    """A cheap chart fixture with accurate job/source declarations; no solve."""
    from sim.solver import table_layout
    source = copy.deepcopy(SOURCE if source is None else source)
    config_keys = {k: v for k, v in kwargs.items() if k in (
        "solver_seed", "anneal_iters", "cpsat_time", "workers", "deterministic", "feasibility_time",
        "rotations", "first_state", "mu", "omega", "cross_grade_group_frac", "short_list_policy")}
    config = experiment_configuration(seed=seed, scenario=kwargs.get("scenarios", ["honest"])[0], **config_keys)
    if "generator_config" in kwargs:
        config["generator"] = kwargs["generator_config"]
    gen, run = config["generator"], config["run"]
    n = gen["n11"] + gen["n12"]
    ids = [f"S{i:03d}" for i in range(1, n+1)]
    grade = [11]*gen["n11"] + [12]*gen["n12"]
    caps, tg = table_layout("same", gen["n11"], gen["n12"])
    remaining = {g: iter([i for i in range(n) if grade[i] == g]) for g in (11, 12)}
    tables = [[ids[next(remaining[g])] for _ in range(c)] for c, g in zip(caps, tg)]
    anchors = {i: table[(j+1) % len(table)] for table in tables for j, i in enumerate(table)}
    lists = [[anchors[i]] for i in ids]
    index = {i: j for j, i in enumerate(ids)}
    inputs = {"network": {"seed": seed, "n11": gen["n11"], "n12": gen["n12"], "grade": grade},
              "submittedLists": [[index[j] for j in row] for row in lists],
              "runConfig": {**run, "seed": config["solverSeed"], "scenario": config["scenario"]},
              "generatorConfig": {**gen, "short_list_policy": config["submission"]["shortListPolicy"]}}
    provenance = {**source, "populationSeed": seed, "solverSeed": config["solverSeed"],
                  "effectiveInputs": inputs, "inputHash": fingerprint(inputs)}
    return {"config": {"seed": config["solverSeed"], "populationSeed": seed, "scenario": config["scenario"],
                       "rotations": run["rotations"], "firstState": run["first_state"], "K": gen["K"],
                       "n": n, "tableCapacities": caps, "sameGradeTableGrade": tg,
                       "provenance": provenance,
                       "solver": {"annealIters": run["anneal_iters"], "cpsatTime": run["cpsat_time"],
                                  "workers": run["workers"], "deterministic": run["deterministic"],
                                  "feasibilityTime": run["feasibility_time"]},
                       "network": {"mu": gen["mu"], "omega": gen["omega"], "reciprocity": 1, "inGroupFrac": 0},
                       "feasibility": {"mixed": {"status": "UNKNOWN"}, "same": {"status": "OPTIMAL"}},
                       "baseline": {"expectedDistinctRandom": 1}, "yearSolveSeconds": 0,
                       "coalitionMode": None},
            "students": [{"id": i, "grade": g} for i, g in zip(ids, grade)],
            "listed": lists,
            "rotations": [{"idx": r+1, "state": run["first_state"] if r % 2 == 0 else
                           "same" if run["first_state"] == "mixed" else "mixed",
                           "tables": tables, "tablesRandom": tables, "anchors": anchors,
                           "stats": {"pctGe1": 100.0, "pctExactly1": 100,
                                     "meanDistinctMet": 1, "meanDistinctMetRandom": 1}}
                          for r in range(run["rotations"])],
            "leakage": {"forcedEdges": 0, "studentsWithForcedEdge": 0, "fullyDeterminedStudents": []},
            "fairness": {}, "summary": {"pctGe1Min": 100.0}}


def execute(jobs, out, runner, **kwargs):
    return run_experiments(jobs, out, runner=runner,
                           source_reader=kwargs.pop("source_reader", lambda: copy.deepcopy(SOURCE)),
                           log=None, **kwargs)


def test_attempt_precedes_solver_and_failure_does_not_erase_denominator(tmp_path):
    out = tmp_path / "study.json"
    seen = []
    def runner(**kwargs):
        saved = json.loads(out.read_text())
        assert saved["attempts"][-1]["status"] == "running"
        assert saved["attempts"][-1]["configuration"]["populationSeed"] == kwargs["seed"]
        seen.append(kwargs["seed"])
        if kwargs["seed"] == 1:
            raise RuntimeError("controlled failure")
        return {"honest": sample_trace(**kwargs)}
    jobs = [("seeds", experiment_configuration(seed=s)) for s in (1, 2)]
    manifest = execute(jobs, out, runner)
    assert seen == [1, 2]
    assert [a["status"] for a in manifest["attempts"]] == ["error", "success"]
    assert manifest["meta"]["attemptCount"] == 2
    assert manifest["batches"][-1]["status"] == "completed_with_errors"
    good = manifest["attempts"][1]
    assert (out.parent / good["traceEvidence"]["path"]).is_file()
    assert good["preliminaryUnknownStates"] == ["mixed"]
    assert good["feasibilityEvidence"] == "validated full seating trace"


def test_exact_resume_requires_configuration_source_runtime_and_full_trace(tmp_path):
    out = tmp_path / "study.json"
    calls = []
    active_source = copy.deepcopy(SOURCE)
    def runner(**kwargs):
        calls.append(kwargs)
        return {"honest": sample_trace(source=active_source, **kwargs)}
    job = ("seeds", experiment_configuration())
    execute([job], out, runner)
    execute([job], out, runner)
    assert len(calls) == 1
    changed = ("seeds", experiment_configuration(cpsat_time=0.5))
    execute([changed], out, runner)
    assert len(calls) == 2
    source2 = {**SOURCE, "effectiveSourceHash": "test-source-v2"}
    active_source = source2
    manifest = execute([job], out, runner, source_reader=lambda: source2)
    assert len(calls) == 3
    evidence = out.parent / manifest["attempts"][-1]["traceEvidence"]["path"]
    evidence.write_text("tampered evidence")
    execute([job], out, runner, source_reader=lambda: source2)
    assert len(calls) == 4


def test_resume_fingerprint_covers_runtime_and_complete_generator_configuration():
    base = experiment_configuration(seed=2, solver_seed=9)
    assert base["populationSeed"] == 2 and base["solverSeed"] == 9
    assert {"group_size_dist", "target_reciprocity", "clique_size", "cross_grade_group_frac"} <= base["generator"].keys()
    changed = copy.deepcopy(base)
    changed["generator"]["sigma"] = 0.9
    assert resume_fingerprint(base, SOURCE) != resume_fingerprint(changed, SOURCE)
    assert resume_fingerprint(base, SOURCE) != resume_fingerprint(base, {**SOURCE, "versions": {"python": "new"}})


def test_legacy_rows_are_preserved_but_cannot_satisfy_new_resume(tmp_path):
    out = tmp_path / "study.json"
    old = {"seeds": [{"scenario": "honest", "seed": 7}], "budgets": [], "communities": [],
           "meta": {"finished": "historical"}}
    out.write_text(json.dumps(old))
    migrated = load_manifest(out)
    assert migrated["legacy"]["summaryOnly"] == old
    assert migrated["seeds"] == [] and migrated["attempts"] == []
    result = execute([("seeds", experiment_configuration())], out,
                     lambda **_: {"honest": sample_trace()})
    assert len(result["attempts"]) == 1 and result["attempts"][0]["status"] == "success"
    assert result["legacy"]["status"] == "unverified_summary_only"


def test_interrupted_attempt_stays_visible_on_resume(tmp_path):
    out = tmp_path / "study.json"
    job = ("seeds", experiment_configuration())
    def interrupted(**_):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        execute([job], out, interrupted)
    assert json.loads(out.read_text())["attempts"][0]["status"] == "interrupted"
    manifest = execute([job], out, lambda **_: {"honest": sample_trace()})
    assert [a["status"] for a in manifest["attempts"]] == ["interrupted", "success"]


def test_validation_failure_and_timeout_are_terminal_outcomes(tmp_path):
    out = tmp_path / "study.json"
    def runner(**kwargs):
        if kwargs["seed"] == 2:
            raise TimeoutError("no certified outcome within budget")
        trace = sample_trace(**kwargs)
        trace["rotations"][0]["tables"] = [["S001", "S003"], ["S002", "S004"]]
        return {"honest": trace}
    manifest = execute([("seeds", experiment_configuration(seed=s)) for s in (1, 2)], out, runner)
    assert [a["status"] for a in manifest["attempts"]] == ["error", "unknown"]
    assert manifest["seeds"] == []


def test_source_change_during_run_retains_trace_but_excludes_verified_summary(tmp_path):
    sources = iter([SOURCE, {**SOURCE, "effectiveSourceHash": "changed-during-run"}])
    manifest = execute([("seeds", experiment_configuration())], tmp_path / "study.json",
                       lambda **_: {"honest": sample_trace()}, source_reader=lambda: next(sources))
    assert manifest["attempts"][0]["status"] == "source_changed"
    assert manifest["attempts"][0]["traceEvidence"]["validation"] == "passed"
    assert manifest["seeds"] == []


def test_source_fingerprint_excludes_generated_outputs_and_includes_effective_edits(tmp_path):
    (tmp_path / "sim").mkdir()
    source = tmp_path / "sim" / "model.py"
    source.write_text("answer = 1\n")
    (tmp_path / "requirements.txt").write_text("numpy==2.5.2\n")
    before = source_provenance(tmp_path)
    (tmp_path / "trace.json").write_text('{"generated": true}')
    after_output = source_provenance(tmp_path)
    assert before["effectiveSourceHash"] == after_output["effectiveSourceHash"]
    source.write_text("answer = 2\n")
    after_edit = source_provenance(tmp_path)
    assert before["effectiveSourceHash"] != after_edit["effectiveSourceHash"]
    assert before["gitCommit"] is None


def test_submission_review_and_infeasible_input_have_distinct_denominator_statuses(tmp_path):
    from sim.scenarios import SubmissionReviewRequired
    from sim.solver import InfeasibleInputError
    def runner(**kwargs):
        assert "generator_config" in kwargs
        if kwargs["seed"] == 1:
            raise SubmissionReviewRequired("needs review")
        raise InfeasibleInputError("proved impossible")
    manifest = execute([("communities", experiment_configuration(seed=s)) for s in (1, 2)],
                       tmp_path / "study.json", runner)
    assert [a["status"] for a in manifest["attempts"]] == ["review_required", "infeasible_input"]
    assert manifest["communities"] == []


@pytest.mark.parametrize("change", ["delete", "tamper"])
def test_unavailable_evidence_is_not_retained_as_a_verified_success(tmp_path, change):
    out = tmp_path / "study.json"
    job = ("seeds", experiment_configuration())
    runner = lambda **kwargs: {"honest": sample_trace(**kwargs)}
    manifest = execute([job], out, runner)
    first = manifest["attempts"][0]
    evidence_path = out.parent / first["traceEvidence"]["path"]
    if change == "delete":
        evidence_path.unlink()
    else:
        evidence_path.write_text("changed evidence")
    resumed = execute([job], out, runner)
    assert [a["status"] for a in resumed["attempts"]] == ["evidence_unavailable", "success"]
    assert resumed["meta"]["terminalCounts"] == {"evidence_unavailable": 1, "success": 1}
    assert resumed["meta"]["attemptCount"] == 2
    assert len(resumed["seeds"]) == 1
    assert resumed["seeds"][0]["attemptId"] == resumed["attempts"][1]["id"]
    invalidated = resumed["attempts"][0]
    assert invalidated["originalTerminalStatus"] == "success"
    assert invalidated["unverifiedSummaries"][0]["evidenceStatus"] == "evidence_unavailable"
    again = execute([job], out, runner)
    assert len(again["attempts"]) == 2
    assert again["batches"][-1]["reusedAttemptIds"] == [again["attempts"][1]["id"]]


@pytest.mark.parametrize("mismatch", ["seed", "population_seed", "horizon", "schedule", "budget", "source", "runtime", "generator", "input_hash", "missing_provenance"])
def test_returned_trace_must_match_requested_job_and_provenance(tmp_path, mismatch):
    job = ("seeds", experiment_configuration(seed=17, solver_seed=29, rotations=3, anneal_iters=17, cpsat_time=.75))
    def runner(**kwargs):
        trace = sample_trace(**kwargs)
        cfg = trace["config"]
        prov = cfg["provenance"]
        if mismatch == "seed":
            cfg["seed"] = 7
        elif mismatch == "population_seed":
            cfg["populationSeed"] = 7
        elif mismatch == "horizon":
            cfg["rotations"] = 1
            trace["rotations"] = trace["rotations"][:1]
        elif mismatch == "schedule":
            for rotation in trace["rotations"]:
                rotation["state"] = "same" if rotation["state"] == "mixed" else "mixed"
        elif mismatch == "budget":
            cfg["solver"]["cpsatTime"] = 3.5
        elif mismatch == "source":
            prov["effectiveSourceHash"] = "another-source"
        elif mismatch == "runtime":
            prov["versions"]["ortools"] = "another-version"
        elif mismatch == "generator":
            prov["effectiveInputs"]["generatorConfig"]["sigma"] = .99
            prov["inputHash"] = fingerprint(prov["effectiveInputs"])
        elif mismatch == "input_hash":
            prov["inputHash"] = "incorrect"
        else:
            del cfg["provenance"]
        return {"honest": trace}
    out = tmp_path / "study.json"
    bad = execute([job], out, runner)
    assert bad["attempts"][0]["status"] == "error"
    assert bad["attempts"][0]["error"]["type"] == "ValueError"
    assert not bad["seeds"]
    corrected = execute([job], out, lambda **kwargs: {"honest": sample_trace(**kwargs)})
    assert [a["status"] for a in corrected["attempts"]] == ["error", "success"]
