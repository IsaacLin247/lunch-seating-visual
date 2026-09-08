"""Admission, provenance, and actual stage snapshots used by the website."""
import pytest

from sim.generator import make_cohort, coalition_lists, honest_lists
from sim.scenarios import (SubmissionReviewRequired, build_lists, coalition_members,
                           make_all, run_year, validate_trace)


def test_screen_enabled_year_requires_review_of_forced_inputs():
    net = make_cohort(seed=7)
    lists = coalition_lists(net, "stratified", honest_lists(net))
    with pytest.raises(SubmissionReviewRequired):
        run_year(net, lists, "honest", rotations=1, anneal_iters=10, cpsat_time=0, log=None)


def test_shared_anchor_diagnostic_excludes_the_honest_anchor():
    net = make_cohort(seed=7)
    lists, extra = build_lists(net, "coalition_shared_anchor")
    members = coalition_members(net, "coalition_shared_anchor")
    assert len(members) == 7 and all(len(lists[i]) == 4 for i in members)
    report = extra["diagnosticScreen"]
    assert report["returnedStudents"] == sorted(net.ids()[i] for i in members)
    assert not report["honestFlagged"] and not report["unresolvedCandidates"]


def test_short_year_keeps_real_stage_snapshots_and_input_identity():
    t = make_all(seed=7, solver_seed=19, scenarios=["honest"], rotations=1,
                 anneal_iters=1000, cpsat_time=0, feasibility_time=0.1, log=None)["honest"]
    validate_trace(t)
    cfg = t["config"]
    assert cfg["rotations"] == 1 and cfg["populationSeed"] == 7 and cfg["seed"] == 19
    assert cfg["provenance"]["populationSeed"] == 7 and cfg["provenance"]["solverSeed"] == 19
    assert len(cfg["provenance"]["effectiveSourceHash"]) == 64
    r = t["rotations"][0]
    assert [x["name"] for x in r["pipeline"]] == ["construction", "repair", "annealing", "final"]
    assert r["pipeline"][-1]["tables"] == r["tables"]
    assert r["pipeline"][-1]["cost"]["violations"] == 0
    ids = {s["id"] for s in t["students"]}
    listed = dict(zip([s["id"] for s in t["students"]], map(set, t["listed"])))
    for stage in r["pipeline"]:
        assert set(x for tab in stage["tables"] for x in tab) == ids
        assert [len(tab) for tab in stage["tables"]] == cfg["tableCapacities"]
        violations = sum(bool(listed[i]) and not (listed[i] & (set(tab) - {i}))
                         for tab in stage["tables"] for i in tab)
        assert stage["cost"]["violations"] == violations
