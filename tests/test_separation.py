"""Full-model separation tests and recurring-group diagnostics."""
from sim.diagnostics import recurring_groups
from sim.screens import ScreenBudget, full_model_screen, run_screens, separation_test
from sim.solver import Problem


def _shared_anchor_problem():
    # seven cycle members list their successor and one common anchor (student 7);
    # tables of size 7, 4 and 4: the cycle plus the anchor never fit one table,
    # while the mutual pairs (8,9), (10,11), (12,13) can use either small table
    lists = [[(i + 1) % 7, 7] for i in range(7)] + [[]] + [[9], [8], [11], [10], [13], [12], []]
    grade = [11] * 15
    zero = [[0] * 15 for _ in range(15)]
    return Problem(grade, lists, [7, 4, 4], [None, None, None], zero, "mixed", history_alpha=[r[:] for r in zero])


def test_full_model_screen_distinguishes_witness_forced_and_unknown():
    p = _shared_anchor_problem()
    forced = separation_test(p, list(range(7)), time_limit=5, workers=1)
    assert forced["verdict"] == "forced" and forced["baseStatus"] in ("OPTIMAL", "FEASIBLE")
    separable = separation_test(p, [8, 9, 10], time_limit=5, workers=1)
    assert separable["verdict"] == "separable" and len(separable["witnessTables"]) >= 2
    witness = separable["witness"]
    assert p.is_valid(witness) and len({witness[i] for i in (8, 9, 10)}) >= 2
    unresolved = separation_test(p, list(range(7)), time_limit=0, workers=1, base_status="FEASIBLE")
    assert unresolved["verdict"] == "unresolved"


def test_base_infeasible_instances_do_not_produce_forced_certificates():
    lists = [[1, 2, 3], [0], [0], [0]]      # four students, tables of 2: infeasible
    p = Problem([11] * 4, lists, [2, 2], [None, None], [[0] * 4 for _ in range(4)], "mixed")
    out = separation_test(p, [1, 2], time_limit=5, workers=1)
    assert out["verdict"] == "base-infeasible"


def test_budgeted_full_model_screen_reports_coverage_and_uses_screen_candidates():
    p = _shared_anchor_problem()
    report = run_screens(p.lists)
    state = report["perState"]["mixed"]
    fm = full_model_screen(p, state, budget=ScreenBudget(separation_time=5, full_model_limit=1), groups=[[8, 9, 10]])
    assert fm["coverage"]["candidatesExamined"] == 1 and fm["coverage"]["candidatesSkipped"] >= 1
    assert fm["results"][0]["origin"] == "supplied" and fm["results"][0]["verdict"] == "separable"
    assert any(r["verdict"] == "skipped" for r in fm["results"])
    full = full_model_screen(p, state, budget=ScreenBudget(separation_time=5, full_model_limit=10))
    verdicts = {tuple(r["group"]): r["verdict"] for r in full["results"]}
    assert verdicts[tuple(range(7))] == "forced"
    assert full_model_screen(p, state, budget=ScreenBudget(full_model_policy="none"))["coverage"]["candidatesDiscovered"] == 0


def test_recurring_groups_are_descriptive_and_maximal():
    tables = [[[1, 2, 3, 4, 5], [6, 7, 8, 9]], [[1, 2, 3, 4, 6], [5, 7, 8, 9]],
              [[1, 2, 3, 4, 5], [6, 7, 8, 9]], [[1, 2, 3, 7, 5], [6, 4, 8, 9]]]
    out = recurring_groups(tables, min_size=4, max_size=5)
    members = {tuple(g["members"]): g["count"] for g in out["groups"]}
    assert members[(1, 2, 3, 4)] == 3 and members[(1, 2, 3, 4, 5)] == 2 and (1, 2, 3) not in members
    assert "not evidence of intent" in out["note"] and out["threshold"] == 2
