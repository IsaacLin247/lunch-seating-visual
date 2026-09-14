"""Regressions for publication-audit observer and statistical boundaries."""
import pytest

from sim.privacy import coseating_exposure, leakage_report, windowed_leakage
from results.verification.verify_privacy import check
from sim.generator import make_cohort
from sim.student_export import assert_no_private_data, student_facing_export
from sim.submissions import SubmissionRules, build_submissions


def waived_trace():
    # A's real list is {B}. The first rotation is explicitly exempt, so its
    # lone tablemate C cannot provide evidence that A listed C.
    return {
        "config": {"K": 1},
        "students": [{"id": i} for i in "ABC"],
        "listed": [["B"], [], []],
        "rotations": [{"tables": [["A", "C"], ["B"]],
                       "waivedObligations": {"A": "no present eligible peer"}}],
    }


def test_waived_rotation_does_not_falsely_force_an_unlisted_name():
    report = leakage_report(waived_trace())
    assert report["forcedEdges"] == 0
    assert report["forcedEdgesCorrect"] == 0
    assert report["inconsistentObservationStudents"] == []


def test_waiver_does_not_erase_valid_evidence_from_other_rotations():
    trace = waived_trace()
    trace["rotations"].append({"tables": [["A", "B"], ["C"]]})
    trace["leakage"] = leakage_report(trace)
    assert trace["leakage"]["perStudent"] == {"A": ["B"]}
    assert trace["leakage"]["inconsistentObservationStudents"] == []
    independent = check(trace)
    assert independent["provenForcedEntries"] == 1
    assert independent["errors"] == []
    assert independent["unresolved"] == []


def test_exposure_keeps_actual_observations_during_a_waiver():
    report = coseating_exposure(waived_trace())
    assert report["students"] == 1
    assert report["top1ListedRate"] == 0.0


@pytest.mark.parametrize("window", [0, -1, 1.5, True])
def test_invalid_retention_windows_are_not_reported_as_no_leakage(window):
    with pytest.raises(ValueError, match="positive integer"):
        windowed_leakage(waived_trace(), window)


@pytest.mark.parametrize("top", [0, -1, 1.5, True])
def test_exposure_requires_a_positive_integer_rank_count(top):
    with pytest.raises(ValueError, match="positive integer"):
        coseating_exposure(waived_trace(), top=top)


def test_planted_clique_cannot_exceed_the_declared_nomination_cap():
    with pytest.raises(ValueError, match="clique_size - 1 <= K"):
        make_cohort(seed=7, K=3)
    net = make_cohort(seed=7, K=3, clique_size=4)
    assert all(len(names) <= 3 for names in net.friends)
    assert all(set(net.clique) - {i} <= set(net.friends[i]) for i in net.clique)


def test_simulation_exception_policy_cannot_waive_the_public_cap():
    grade = [11] * 10
    raw = [list(range(1, 10))] + [[] for _ in range(9)]
    submissions = build_submissions(raw, grade, SubmissionRules(), policy="approve")
    assert submissions[0].state == "pending_review"
    assert submissions[0].names == list(range(1, 10))
    assert submissions[0].obligation == []


def test_explicit_exception_cannot_waive_the_public_cap():
    grade = [11] * 10
    raw = [list(range(1, 10))] + [[] for _ in range(9)]
    with pytest.raises(ValueError, match="exceeds the public cap"):
        build_submissions(raw, grade, SubmissionRules(), decisions={0: "approve"})
    changed_cap = build_submissions(raw, grade, SubmissionRules(max_list=9))
    assert changed_cap[0].state == "accepted"


def test_student_chart_export_omits_explicit_absence_records():
    trace = {
        "students": [{"id": i, "grade": 11} for i in "ABC"],
        "rotations": [{"idx": 1, "state": "mixed", "tables": [["A", "B"]], "absent": ["C"]}],
    }
    chart = student_facing_export(trace)
    assert "absent" not in chart["rotations"][0]
    assert "C" not in repr(chart)
    with pytest.raises(ValueError, match="private field"):
        assert_no_private_data({"rotations": [{"absent": ["C"]}]})
