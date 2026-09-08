"""Validity of the exported traces (docs/data/*.json)."""
import os
import re

from sim.scenarios import validate_trace
from tests.conftest import DATA, SCENARIOS

ID_RE = re.compile(r"^S\d{3}$")


def test_trace_passes_validator(trace):
    validate_trace(trace)


def test_capacities_exact(trace):
    caps = trace["config"]["tableCapacities"]
    assert len(caps) == 40 and caps.count(7) == 17 and caps.count(6) == 23 and sum(caps) == 257
    for rot in trace["rotations"]:
        for key in ("tables", "tablesRandom"):
            assert [len(t) for t in rot[key]] == caps


def test_every_submitter_guaranteed_every_rotation(trace):
    ids = [s["id"] for s in trace["students"]]
    listed = {ids[i]: set(l) for i, l in enumerate(trace["listed"])}
    grade = {s["id"]: s["grade"] for s in trace["students"]}
    for rot in trace["rotations"]:
        where = {s: t for t, tbl in enumerate(rot["tables"]) for s in tbl}
        for s, L in listed.items():
            if not L:
                continue
            mates = set(rot["tables"][where[s]]) - {s}
            if rot["state"] == "same":
                L = {j for j in L if grade[j] == grade[s]}
            assert mates & L, f"{s} friendless in rotation {rot['idx']}"
            assert rot["anchors"][s] in mates & L
        assert rot["stats"]["pctGe1"] == 100.0


def test_states_alternate_and_same_grade_partition(trace):
    states = [r["state"] for r in trace["rotations"]]
    assert len(states) == 16
    assert all(a != b for a, b in zip(states, states[1:]))
    assert set(states) == {"same", "mixed"}
    grade = {s["id"]: s["grade"] for s in trace["students"]}
    tg = trace["config"]["sameGradeTableGrade"]
    for rot in trace["rotations"]:
        if rot["state"] != "same":
            continue
        for key in ("tables", "tablesRandom"):
            for t, tbl in enumerate(rot[key]):
                assert {grade[s] for s in tbl} == {tg[t]}
    # partition sizes per the spec
    assert sum(c for c, g in zip(trace["config"]["tableCapacities"], tg) if g == 11) == 132
    assert sum(c for c, g in zip(trace["config"]["tableCapacities"], tg) if g == 12) == 125


def test_submission_rules(trace):
    grade = {s["id"]: s["grade"] for s in trace["students"]}
    ids = [s["id"] for s in trace["students"]]
    min4 = trace["config"]["rules"]["min4"]
    for i, L in enumerate(trace["listed"]):
        assert ids[i] not in L and len(L) == len(set(L))
        if not L:
            continue
        if min4:
            assert len(L) >= 4
            assert sum(1 for j in L if grade[j] == grade[ids[i]]) >= 2


def test_no_pii_only_synthetic_ids(trace):
    for s in trace["students"]:
        assert ID_RE.match(s["id"])
    assert set(s["id"] for s in trace["students"]) == {f"S{i:03d}" for i in range(1, 258)}
    banned = {"name", "email", "first", "last"}
    assert not (banned & set(trace["students"][0].keys()))


def test_random_baseline_is_mostly_friendless(traces):
    t = traces["honest"]
    ge1 = [r["stats"]["pctGe1Random"] for r in t["rotations"]]
    assert 5 < sum(ge1) / len(ge1) < 40


def test_proposed_system_mostly_exactly_one(traces):
    t = traces["honest"]
    ex1 = [r["stats"]["pctExactly1"] for r in t["rotations"]]
    assert min(ex1) > 90


def test_coalition_captures_table_without_defenses(traces):
    t = traces["coalition_none"]
    members = set(t["config"]["coalition"])
    assert len(members) == 6
    for rot in t["rotations"]:
        assert rot["coalition"]["intact"]
        assert any(members <= set(tbl) for tbl in rot["tables"])
    assert t["summary"]["coalitionIntactRotations"] == 16


def test_reference_star_observations_respect_structural_pattern_family(traces):
    t = traces["coalition_min4"]
    assert t["summary"]["coalitionIntactRotations"] == sum(r["coalition"]["intact"] for r in t["rotations"])
    for rot in t["rotations"]:
        c = rot["coalition"]
        assert c["avgCluster"] >= 3.0           # structural lower bound of the omission star
        assert c["pattern"] in {"3+3", "4+2", "6"}
    assert t["summary"]["coalitionAvgCluster"] >= 3.0


def test_stratified_attack_forces_same_grade_cohesion(traces):
    t = traces["coalition_stratified"]
    by_state = t["summary"]["coalitionIntactByState"]
    assert by_state["same"] == 8
    for rot in t["rotations"]:
        if rot["state"] == "same":
            assert rot["coalition"]["intact"]


def test_screen_flags_the_stratified_attack_on_the_effective_graph(traces):
    t = traces["coalition_screened"]
    scr = t["config"]["screen"]
    assert scr["rule"].startswith("coercion+demand")
    assert scr["coalitionFlagged"] is True and scr["honestFlagged"] == []
    assert scr["perState"]["mixed"]["flags"] == []
    assert scr["perState"]["same"]["flags"]
    assert set(scr["returnedStudents"]) == set(t["config"]["coalition"])
    assert scr["min4Violations"] == [] and scr["sameGradeViolations"] == []
    assert scr["resubmission"].startswith("adversarial")
    after = scr["afterResubmission"]
    assert after["nFlagged"] == 0 and after["nReturned"] == 0
    assert "listedInitial" in t
    assert t["summary"]["coalitionIntactRotations"] == 0
    h = traces["honest"]["config"]["screen"]
    assert h["nFlagged"] == 0 and h["nReturned"] == 0


def test_precheck_status_does_not_claim_unknown_is_a_certificate(trace):
    feas = trace["config"]["feasibility"]
    assert set(feas) == {"mixed", "same"}
    assert all(v["status"] in ("OPTIMAL", "FEASIBLE", "UNKNOWN") for v in feas.values())
    # Every retained chart is independently checked even after UNKNOWN.
    validate_trace(trace)


def test_leakage_probe_is_recorded_and_correct(trace):
    lk = trace["leakage"]
    assert lk["forcedEdges"] == lk["forcedEdgesCorrect"] > 0
    assert lk["kMax"] == 8 and lk["rotationsObserved"] == 16


def test_random_baseline_matches_closed_form(traces):
    t = traces["honest"]
    b = t["config"]["baseline"]
    assert abs(b["expectedDistinctRandom"] - 72.289) < 0.01
    assert abs(t["summary"]["meanDistinctMetFinalRandom"] - b["expectedDistinctRandom"]) < 1.5
    assert abs(t["summary"]["pctGe1RandomMean"] - b["expectedFriendCoverageSchedule"]) < 3.0


def test_metadata_and_fairness_recorded(trace):
    cfg = trace["config"]
    assert cfg["versions"]["ortools"] and cfg["versions"]["numpy"] and cfg["versions"]["python"]
    assert cfg["network"]["K"] == cfg["K"] == 8
    assert cfg["submission"]["nSubmitters"] + cfg["submission"]["nNonSubmitters"] == cfg["n"]
    f = trace["fairness"]["distinctMet"]
    assert f["min"] <= f["median"] <= f["max"]
    assert trace["summary"]["maxSolveSeconds"] >= 0
    assert cfg["provenance"]["effectiveSourceHash"]
    assert len(cfg["provenance"]["gitCommit"]) == 40
    assert isinstance(cfg["provenance"]["gitDirty"], bool)
    assert isinstance(trace["summary"]["repeatsWorseThanRandomRotations"], list)


def test_index_lists_all_scenarios():
    import json
    path = os.path.join(DATA, "index.json")
    if not os.path.exists(path):
        import pytest
        pytest.skip("index.json missing")
    with open(path) as f:
        idx = json.load(f)
    assert [s["name"] for s in idx["scenarios"]] == SCENARIOS


def test_total_size_budget():
    total = sum(os.path.getsize(os.path.join(DATA, f"{n}.json")) for n in SCENARIOS if os.path.exists(os.path.join(DATA, f"{n}.json")))
    # Six full reference years now retain four real stage assignments per round.
    assert total < 6 * 1024 * 1024


def test_actual_pipeline_endpoints_are_validated_by_their_costs(trace):
    # Full independent cost recomputation also runs in the evidence verifier.
    assert [s["name"] for s in trace["rotations"][0]["pipeline"]] == ["construction", "repair", "annealing", "final"]
    for r in trace["rotations"]:
        assert r["pipeline"][-1]["tables"] == r["tables"]
        assert r["pipeline"][-1]["cost"] == r["stats"]["cost"]
        assert r["pipeline"][-1]["cost"]["violations"] == 0


def test_shared_anchor_full_table_and_targeted_diagnostic(traces):
    t=traces["coalition_shared_anchor"]
    core=set(t["config"]["coalition"])
    assert len(core)==7
    assert t["config"]["rules"]["screens"] is False
    for r in t["rotations"]:
        if r["state"]=="same":
            assert any(set(table)==core for table in r["tables"])
    screen=t["config"]["diagnosticScreen"]
    assert set(screen["returnedStudents"])==core
    assert screen["nUnresolved"]==0
