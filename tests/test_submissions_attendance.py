"""Submission states, review decisions, attendance conflicts and occupancy targets."""
import pytest

from sim.attendance import RotationRoster, companion_conflicts
from sim.constraints import SchedulingConflict, occupancy_targets
from sim.generator import make_cohort, honest_lists
from sim.scenarios import SubmissionReviewRequired, build_lists, make_all, run_year
from sim.solver import Problem, table_layout
from sim.submissions import SubmissionRules, apply_decisions, build_submissions, obligation_lists, summarize


GRADE = [11, 11, 11, 11, 12, 12]


def test_short_lists_remain_visible_requests_not_silent_nonsubmission():
    raw = [[1, 2, 3, 4], [0, 2], [], [0, 1, 2, 4], [0, 1, 2, 3], [4]]
    subs = build_submissions(raw, GRADE, SubmissionRules(), policy="review")
    states = [s.state for s in subs]
    assert states == ["accepted", "pending_review", "voluntary_nonsubmission", "accepted", "pending_review", "pending_review"]
    assert subs[1].names == [0, 2] and "fewer than 4" in subs[1].reason
    assert subs[4].reason.startswith("0 same-grade")            # four names, none from grade 12
    assert obligation_lists(subs)[1] == [] and obligation_lists(subs)[0] == [1, 2, 3, 4]
    summary = summarize(subs)
    assert summary["pendingReview"] == [1, 4, 5] and summary["schedulable"] is False
    # the pending request keeps its names in the record
    assert subs[1].to_dict()["names"] == [0, 2] and subs[1].to_dict()["obligation"] == []


def test_review_decisions_keep_the_actual_obligation_or_record_a_withdrawal():
    raw = [[1, 2, 3, 4], [0, 2], [], [0, 1, 2, 4], [0, 1, 2, 3], [4]]
    subs = build_submissions(raw, GRADE, SubmissionRules(), policy="review",
                             decisions={1: {"decision": "approve", "note": "counsellor approved"},
                                        4: "withdraw", 5: {"decision": "resubmit", "names": [4, 0, 1, 2]}})
    assert subs[1].state == "approved_exception" and subs[1].obligation == [0, 2]
    assert subs[4].state == "voluntary_nonsubmission" and subs[4].decision == "withdraw" and subs[4].names == [0, 1, 2, 3]
    assert subs[5].state == "pending_review"        # the resubmission still fails the same-grade rule
    with pytest.raises(ValueError):
        apply_decisions(subs, GRADE, SubmissionRules(), {0: "approve"})   # not pending
    approved = build_submissions(raw, GRADE, SubmissionRules(), policy="approve")
    assert [s.state for s in approved].count("approved_exception") == 3
    withdrawn = build_submissions(raw, GRADE, SubmissionRules(), policy="withdraw")
    assert all(s.decision == "withdraw" and "reviewed withdrawal" in s.note for s in withdrawn if s.student in (1, 4, 5))
    legacy = build_submissions(raw, GRADE, SubmissionRules(), policy="none")
    assert [s.state for s in legacy] == [s.state for s in withdrawn]


def test_pending_requests_block_scheduling_and_approved_exceptions_keep_obligations():
    net = make_cohort(seed=7)
    lists, extra = build_lists(net, "honest", short_list_policy="review", list_cap=3)
    subs = extra["submissions"]
    assert all(s.state == "pending_review" for s in subs) and all(l == [] for l in lists)
    with pytest.raises(SubmissionReviewRequired, match="pending review"):
        run_year(net, lists, "honest", rotations=1, anneal_iters=10, cpsat_time=0, feasibility_time=1,
                 log=None, submissions=subs)
    lists_ok, extra_ok = build_lists(net, "honest", short_list_policy="approve", list_cap=3)
    assert all(s.state == "approved_exception" for s in extra_ok["submissions"])
    assert all(len(l) == 3 for l in lists_ok)
    p = Problem(net.grade, lists_ok, *table_layout("mixed"), [[0] * net.n for _ in range(net.n)], "mixed")
    assert all(p.submitter)


def test_absent_sole_companion_is_an_explicit_conflict():
    grade = [11, 11, 11, 12, 12, 12]
    lists = [[1, 3], [0, 3], [0, 1], [4, 5], [3, 5], [3, 4]]
    # student 0 lists 1 (same grade) and 3 (other grade): with 1 absent, the same-grade round has no companion
    conflicts = companion_conflicts(lists, grade, "same", present=[0, 2, 3, 4, 5])
    assert [c["student"] for c in conflicts] == [0]          # student 2 still has 0 present
    assert conflicts[0]["absentListed"] == [1] and conflicts[0]["ineligibleListed"] == [3]
    assert companion_conflicts(lists, grade, "mixed", present=[0, 2, 3, 4, 5]) == []
    roster = RotationRoster(grade, lists, [3, 3], [11, 12], "same", absent=[1])
    assert len(roster.conflicts) == 1 and roster.targets == [2, 3]
    waived = RotationRoster(grade, lists, [3, 3], [11, 12], "same", absent=[1], waivers={0: "counsellor decision"})
    assert waived.conflicts == [] and waived.lists[waived.index[0]] == []


def test_run_year_stops_on_a_conflict_unless_an_explicit_waiver_exists():
    net = make_cohort(seed=7)
    lists = honest_lists(net)
    grade = [int(g) for g in net.grade]
    hero = 0
    same = [j for j in lists[hero] if grade[j] == grade[hero]]
    absences = {r: list(same) for r in range(2)}   # every same-grade companion of student 0 is absent
    with pytest.raises(SchedulingConflict) as err:
        run_year(net, lists, "coalition_min4", rotations=2, anneal_iters=10, cpsat_time=0, feasibility_time=1,
                 log=None, attendance=absences)
    assert any(c["student"] == net.ids()[hero] for c in err.value.conflicts)
    assert all(a.startswith("S") for a in err.value.conflicts[0]["absentListed"])
    with pytest.raises(SchedulingConflict):   # a waiver for one rotation does not cover the other
        run_year(net, lists, "coalition_min4", rotations=2, anneal_iters=10, cpsat_time=0, feasibility_time=1,
                 log=None, attendance=absences, waivers={1: {hero: "counsellor decision"}})
    trace = run_year(net, lists, "coalition_min4", rotations=2, anneal_iters=10, cpsat_time=0, feasibility_time=1,
                     log=None, attendance=absences,
                     waivers={0: {hero: "counsellor decision"}, 1: {hero: "counsellor decision"}})
    for rot in trace["rotations"]:
        assert rot["waivedObligations"] == {net.ids()[hero]: "counsellor decision"}
        assert net.ids()[hero] not in rot["anchors"]
        assert rot["stats"]["obligatedPresent"] == rot["stats"]["present"] - 1   # only the waived student is unobligated
        assert rot["absent"] == sorted(net.ids()[j] for j in same)
    assert trace["outcomes"]["participation"]["waivedObligationsPerRotation"] == [1, 1]
    assert trace["config"]["provenance"]["effectiveInputs"]["waivers"]["0"] == {net.ids()[hero]: "counsellor decision"}


def test_occupancy_targets_stay_within_capacities_and_pools():
    caps, tg = table_layout("same")
    grade = [11] * 132 + [12] * 125
    present = [i for i in range(257) if i not in (0, 1, 2, 140)]
    targets = occupancy_targets(caps, tg, grade, present)
    assert sum(targets) == 253 and all(0 <= x <= c for x, c in zip(targets, caps))
    assert sum(x for x, g in zip(targets, tg) if g == 11) == 129
    assert sum(x for x, g in zip(targets, tg) if g == 12) == 124
    with pytest.raises(ValueError):
        occupancy_targets(caps, tg, grade, present, explicit=[c for c in caps])
    with pytest.raises(ValueError):
        occupancy_targets(caps, tg, grade, list(range(257)) + [0] * 30)


def test_participation_and_admission_are_reported_separately_from_coverage():
    traces = make_all(seed=3, scenarios=["coalition_min4"], rotations=2, anneal_iters=500, cpsat_time=0,
                      feasibility_time=1, log=None, nonsubmit_frac=0.2, absence_rate=0.05, conflict_policy="waive")
    trace = traces["coalition_min4"]
    part = trace["outcomes"]["participation"]
    assert part["submissionStates"]["voluntary_nonsubmission"] > 0
    assert part["obligatedStudents"] == part["submissionStates"]["accepted"] + part["submissionStates"]["approved_exception"]
    assert part["presentPerRotation"] == [len(trace["students"]) - len(r["absent"]) for r in trace["rotations"]]
    cov = trace["outcomes"]["proposed"]["coverageAmongObligated"]
    assert cov["atLeastOnePct"] == 100.0 and cov["obligatedStudentRotations"] == sum(r["stats"]["obligatedPresent"] for r in trace["rotations"])
    assert trace["config"]["submissions"]["counts"]["voluntary_nonsubmission"] == part["submissionStates"]["voluntary_nonsubmission"]
