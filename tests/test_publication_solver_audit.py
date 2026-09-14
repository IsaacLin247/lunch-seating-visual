"""Publication audit regressions for attendance, budgets and release guards."""
import pytest

from sim import screens, solver
from sim.attendance import RotationRoster
from sim.constraints import occupancy_targets
from sim.screens import ScreenBudget, run_screens
from sim.solver import Problem, SolveFailed, solve_rotation


def test_empty_eligibility_pools_close_every_table_and_reject_phantom_targets():
    grade = [11, 11, 12, 12]
    assert occupancy_targets([2, 2], [11, 12], grade, [0, 1]) == [2, 0]
    assert occupancy_targets([2, 2], [11, 12], grade, []) == [0, 0]
    assert occupancy_targets([2, 2], [None, None], grade, []) == [0, 0]
    with pytest.raises(ValueError, match="pool 12"):
        occupancy_targets([2, 2], [11, 12], grade, [0, 1], explicit=[2, 2])
    with pytest.raises(ValueError, match="pool None"):
        occupancy_targets([2, 2], [None, None], grade, [], explicit=[2, 2])
    with pytest.raises(ValueError, match="physical capacity"):
        occupancy_targets([2, 2], [None, None], grade, [0], explicit=[0.5, 0.5])


def test_all_absent_roster_schedules_an_empty_chart():
    grade = [11, 11, 12, 12]
    roster = RotationRoster(grade, [[1], [0], [3], [2]], [2, 2], [11, 12], "same",
                            absent=range(4))
    assert roster.conflicts == [] and roster.targets == [0, 0]
    p = Problem(roster.grade, roster.lists, roster.caps, roster.table_grade, [], "same",
                targets=roster.targets)
    assign, info = solve_rotation(p, anneal_iters=10, cpsat_time=0)
    assert assign == [] and info["validation"]["valid"]
    assert roster.expand(assign) == [None] * 4


def test_configured_exact_limit_selects_bounded_cp_instead_of_enumeration(monkeypatch):
    calls = []

    def undecided(members, lists, time_limit):
        calls.append((list(members), time_limit))
        return None, False

    def no_enumeration(*args):
        raise AssertionError("exact enumeration exceeds the configured budget")

    monkeypatch.setattr(screens, "_cpsat_split", undecided)
    monkeypatch.setattr(screens, "_exact_split", no_enumeration)
    result = run_screens([[1], [0]], budget=ScreenBudget(exact_limit=0, deterministic_time=0))
    assert calls == [([0, 1], 0)]
    assert result["flags"] == [] and len(result["unresolvedCandidates"]) == 1
    assert result["perState"]["mixed"]["coverage"]["exactEnumerationLimit"] == 0


def test_configured_closure_cap_limits_demand_candidates_too():
    lists = [[1], [0]]
    kwargs = {"caps_by_state": {"mixed": [1, 1]}}
    limited = run_screens(lists, budget=ScreenBudget(closure_cap=1, target_core_cap=0), **kwargs)
    expanded = run_screens(lists, budget=ScreenBudget(closure_cap=2, target_core_cap=0), **kwargs)
    assert limited["demandFlags"] == []
    assert len(expanded["demandFlags"]) == 1
    assert expanded["demandFlags"][0]["demand"] == 2


@pytest.mark.parametrize("invalid", [[1, 1, 0, 0], [0, 0, 0, 0]])
def test_validated_fallback_survives_unscored_eligibility_or_occupancy_failure(monkeypatch, invalid):
    p = Problem([11, 11, 12, 12], [[], [], [], []], [2, 2], [11, 12],
                [[0] * 4 for _ in range(4)], "same")
    witness = [0, 0, 1, 1]
    assert not p.validate(invalid)["valid"]
    assert p.cost_breakdown(invalid)["hard"] == 0  # these constraints are normally invariants
    monkeypatch.setattr(solver, "pod_greedy", lambda *_: list(invalid))
    monkeypatch.setattr(solver, "swap_repair", lambda *_: False)
    assign, info = solve_rotation(p, anneal_iters=0, cpsat_time=0, fallbacks=[witness])
    assert assign == witness and info["validation"]["valid"]
    assert not info["constructionFeasible"] and info["status"] == "fallback"


def test_construct_repair_baseline_does_not_run_an_optimizing_cp_rescue(monkeypatch):
    p = Problem([11] * 4, [[1], [0], [3], [2]], [2, 2], [None, None],
                [[0] * 4 for _ in range(4)], "mixed")
    monkeypatch.setattr(solver, "pod_greedy", lambda *_: [0, 1, 0, 1])
    monkeypatch.setattr(solver, "swap_repair", lambda *_: False)

    def no_cp(*args, **kwargs):
        raise AssertionError("construct_repair must stop after repair")

    monkeypatch.setattr(solver, "cpsat_polish", no_cp)
    with pytest.raises(SolveFailed):
        solve_rotation(p, method="construct_repair")
    assign, info = solve_rotation(p, method="construct_repair", fallbacks=[[0, 0, 1, 1]])
    assert assign == [0, 0, 1, 1] and info["status"] == "fallback"
    assert "cpsatFallback" not in info


@pytest.mark.parametrize("cp_status", ["FEASIBLE", "OPTIMAL"])
def test_cp_returning_the_cached_chart_counts_as_successful_search(monkeypatch, cp_status):
    p = Problem([11] * 4, [[1], [0], [3], [2]], [2, 2], [None, None],
                [[0] * 4 for _ in range(4)], "mixed")
    witness = [0, 0, 1, 1]
    monkeypatch.setattr(solver, "pod_greedy", lambda *_: [0, 1, 0, 1])
    monkeypatch.setattr(solver, "swap_repair", lambda *_: False)
    monkeypatch.setattr(solver, "cpsat_polish", lambda *_, **__: (list(witness), {"status": cp_status, "exact": True}))
    assign, info = solve_rotation(p, anneal_iters=0, cpsat_time=.1, fallbacks=[witness])
    assert assign == witness and info["accepted"] == "cpsat"
    assert info["status"] == "incumbent" and not info["constructionFeasible"]
    assert info["optimalityProven"] == (cp_status == "OPTIMAL")


def test_unused_eligibility_state_does_not_reject_a_requested_mixed_rotation():
    from sim.generator import make_cohort
    from sim.scenarios import run_year
    net = make_cohort(seed=1)
    lists = [[] for _ in range(net.n)]
    lists[0] = [net.n11]  # a valid mixed-state obligation, ineligible in same-grade rounds
    trace = run_year(net, lists, "coalition_none", rotations=1, first_state="mixed", anneal_iters=0,
                     cpsat_time=0, feasibility_time=1, workers=1, log=None)
    assert set(trace["config"]["feasibility"]) == {"mixed"}
    assert trace["rotations"][0]["release"]["validation"]["valid"]
    assert trace["rotations"][0]["stats"]["pctGe1"] == 100


def test_absence_can_remove_a_dependency_that_makes_the_full_roster_infeasible():
    from sim.generator import make_cohort
    from sim.scenarios import run_year
    net = make_cohort(seed=1)
    lists = [[] for _ in range(net.n)]
    for i in range(1, 8):
        lists[i] = [0]  # eight forced people exceed capacity seven when everybody attends
    trace = run_year(net, lists, "coalition_none", rotations=1, attendance={0: [7]}, anneal_iters=0,
                     cpsat_time=0, feasibility_time=1, workers=1, log=None)
    rotation = trace["rotations"][0]
    assert rotation["absent"] == [net.ids()[7]]
    assert rotation["stats"]["pctGe1"] == 100 and rotation["release"]["validation"]["valid"]
    assert any(set(net.ids()[:7]) <= set(table) for table in rotation["tables"])


def test_attendance_callback_matches_recorded_roster_and_compact_screen_groups():
    from sim.generator import make_cohort
    from sim.scenarios import run_year
    net = make_cohort(seed=1)
    calls = []

    def attendance(rotation):
        calls.append(rotation)
        return [0] if len(calls) == 1 else [1]

    trace = run_year(net, [[] for _ in range(net.n)], "coalition_none", rotations=1, attendance=attendance,
                     suspected_groups=[[0, 1, 2]], screen_budget=ScreenBudget(separation_time=1, full_model_limit=1),
                     anneal_iters=0, cpsat_time=0, feasibility_time=1, workers=1, log=None)
    ids = net.ids()
    assert calls == [0]
    assert trace["rotations"][0]["absent"] == [ids[0]]
    assert trace["config"]["provenance"]["effectiveInputs"]["attendance"] == {"0": [ids[0]]}
    report = trace["config"]["fullModelScreen"]["mixed"]
    assert report["results"][0]["group"] == [ids[1], ids[2]]
    assert report["hardConstraintKey"] == trace["rotations"][0]["release"]["hardConstraintKey"]


def test_unresolved_full_model_checks_block_the_review_gate():
    from sim.scenarios import _review_gate
    reasons = _review_gate("honest", {"fullModelScreen": {"unresolvedGroups": [{"status": "UNKNOWN"}]}},
                           {"pendingReview": [], "approvedExceptions": []}, False)
    assert reasons == ["1 unresolved full-model separation check(s)"]
