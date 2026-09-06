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


def test_min4_rule_scatters_coalition(traces):
    t = traces["coalition_min4"]
    intact = sum(1 for r in t["rotations"] if r["coalition"]["intact"])
    assert intact <= 1
    assert t["summary"]["coalitionAvgCluster"] < 3.0
    for rot in t["rotations"]:
        assert rot["coalition"]["maxCluster"] <= 3


def test_screens_flag_coalition_not_honest_students(traces):
    t = traces["coalition_screened"]
    scr = t["config"]["screen"]
    assert scr["rule"] == "coercion"
    assert scr["coalitionFlagged"] is True
    assert scr["honestFlagged"] == []
    assert scr["flags"] and all(f["screen"] == "coercion" for f in scr["flags"])
    assert set(scr["flaggedStudents"]) <= set(t["config"]["coalition"])
    assert set(scr["returnedStudents"]) == set(t["config"]["coalition"])
    assert scr["afterResubmission"]["nFlagged"] == 0 and scr["afterResubmission"]["nReturned"] == 0
    assert "listedInitial" in t
    h = traces["honest"]["config"]["screen"]
    assert h["nFlagged"] == 0 and h["nReturned"] == 0


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
    assert total < 2 * 1024 * 1024
