"""Validated fallback charts: retained, keyed by hard constraints, never stale, never 'optimal'."""
import random

import pytest

from sim import solver
from sim.constraints import StaffConstraints, hard_constraint_key, validate_chart
from sim.fallbacks import FeasibleChartCache
from sim.generator import make_cohort, honest_lists
from sim.solver import Problem, SolveFailed, feasibility_certificate, solve_rotation, table_layout


def _problem(seed=11, state="mixed", **kw):
    net = make_cohort(seed=seed)
    lists = honest_lists(net)
    caps, tg = table_layout(state)
    zero = [[0] * net.n for _ in range(net.n)]
    return net, lists, Problem(net.grade, lists, caps, tg, zero, state, history_alpha=[r[:] for r in zero], **kw)


def _break_everything(monkeypatch, invalid):
    """Force every optimisation stage to fail: construction is invalid, repair
    and annealing do nothing, CP-SAT returns UNKNOWN."""
    monkeypatch.setattr(solver, "pod_greedy", lambda *_: list(invalid))
    monkeypatch.setattr(solver, "swap_repair", lambda *_: False)
    monkeypatch.setattr(solver, "anneal", lambda st, *_, **__: (list(st.assign), st.cost, st.viol))
    monkeypatch.setattr(solver, "cpsat_polish", lambda *_, **__: (None, {"status": "UNKNOWN"}))


def test_valid_preliminary_chart_survives_optimisation_failure(monkeypatch):
    lists = [[1], [0], [3], [2]]
    p = Problem([11] * 4, lists, [2, 2], [None, None], [[0] * 4 for _ in range(4)], "mixed")
    status, witness = feasibility_certificate(p, time_limit=2, workers=1)
    assert status in ("OPTIMAL", "FEASIBLE") and validate_chart(p, witness)["valid"]
    _break_everything(monkeypatch, invalid=[0, 1, 0, 1])   # every submitter friendless
    with pytest.raises(SolveFailed):
        solve_rotation(p, anneal_iters=10, cpsat_time=.1)
    assign, info = solve_rotation(p, anneal_iters=10, cpsat_time=.1, fallbacks=[witness])
    assert assign == witness and info["status"] == "fallback" and info["constructionFeasible"] is False
    assert info["validation"]["valid"] and info["optimalityProven"] is False
    # an invalid 'fallback' is never used, and is reported as such
    with pytest.raises(SolveFailed):
        solve_rotation(p, anneal_iters=10, cpsat_time=.1, fallbacks=[[0, 1, 0, 1]])


def test_incumbent_is_used_as_search_start_and_beats_a_worse_construction(monkeypatch):
    lists = [[1, 2], [0, 3], [0, 3], [1, 2]]
    hist = [[0] * 4 for _ in range(4)]
    alpha = [[0] * 4 for _ in range(4)]
    alpha[0][1] = alpha[1][0] = 5           # the pair (0,1) met five times before
    p = Problem([11] * 4, lists, [2, 2], [None, None], hist, "mixed", history_alpha=alpha)
    good = [0, 1, 0, 1]                     # 0 with 2, 1 with 3: no repeats
    worse = [0, 0, 1, 1]                    # 0 with 1: repeat cost
    assert validate_chart(p, good)["valid"] and validate_chart(p, worse)["valid"]
    monkeypatch.setattr(solver, "pod_greedy", lambda *_: list(worse))
    assign, info = solve_rotation(p, anneal_iters=0, cpsat_time=0, fallbacks=[good])
    assert assign == good and info["accepted"] == "incumbent" and info["status"] == "incumbent"
    assert info["constructionFeasible"] is True
    assert info["fallbacks"]["incumbent"]["repeat"] == 0


def test_hard_constraint_key_covers_feasibility_inputs_but_not_history():
    net, lists, p = _problem()
    caps, tg = table_layout("mixed")
    key = hard_constraint_key(net.grade.tolist(), lists, caps, tg, "mixed")
    # history is not part of the key
    assert key == hard_constraint_key(net.grade.tolist(), lists, caps, tg, "mixed")
    changed = [list(l) for l in lists]
    changed[0] = changed[0][:2]
    assert key != hard_constraint_key(net.grade.tolist(), changed, caps, tg, "mixed"), "preferences"
    assert key != hard_constraint_key(net.grade.tolist(), lists, caps, tg, "mixed", present=list(range(1, net.n))), "roster"
    assert key != hard_constraint_key(net.grade.tolist(), lists, *table_layout("same"), "same"), "eligibility"
    assert key != hard_constraint_key(net.grade.tolist(), lists, caps, tg, "mixed", targets=[c - (t == 0) for t, c in enumerate(caps)]), "capacities"
    staff = StaffConstraints(prohibited_pairs={frozenset((0, 1))})
    assert key != hard_constraint_key(net.grade.tolist(), lists, caps, tg, "mixed", staff=staff), "staff"


def test_changed_hard_constraints_prevent_stale_fallback_reuse():
    lists = [[1], [0], [3], [2], [], []]
    grade = [11] * 6
    p1 = Problem(grade, lists, [3, 3], [None, None], [[0] * 6 for _ in range(6)], "mixed")
    cache = FeasibleChartCache()
    key1 = hard_constraint_key(grade, lists, [3, 3], [None, None], "mixed")
    chart = [0, 0, 1, 1, 0, 1]
    assert cache.store(key1, p1, chart, "witness")
    assert cache.charts(key1, p1) == [chart]
    # a new obligation for student 4 (must sit with 2) changes the key ...
    lists2 = [[1], [0], [3], [2], [2], []]
    key2 = hard_constraint_key(grade, lists2, [3, 3], [None, None], "mixed")
    assert key2 != key1 and cache.charts(key2, Problem(grade, lists2, [3, 3], [None, None], [[0] * 6 for _ in range(6)], "mixed")) == []
    # ... and even a caller that wrongly reuses the old key gets nothing: revalidation rejects the stale chart
    p2 = Problem(grade, lists2, [3, 3], [None, None], [[0] * 6 for _ in range(6)], "mixed")
    assert cache.charts(key1, p2) == []
    assert cache.events[-1]["event"] == "stale"
    # an invalid chart is never stored
    assert not cache.store(key1, p1, [0, 1, 0, 1, 0, 1], "bad")


def test_optimality_is_only_claimed_with_an_exact_cp_proof():
    net, lists, p = _problem(state="same")
    assign, info = solve_rotation(p, seed=1, anneal_iters=2000, cpsat_time=0.5)
    assert info["status"] == "optimized"
    cp = info["cpsat"]
    assert info["optimalityProven"] == (info["accepted"] == "cpsat" and cp["status"] == "OPTIMAL" and cp["exact"])
    a2, i2 = solve_rotation(p, seed=1, anneal_iters=2000, cpsat_time=0.5, cpsat_pairs="previous")
    assert i2["cpsat"]["exact"] is False and i2["optimalityProven"] is False


def test_every_released_chart_satisfies_all_current_hard_constraints():
    from sim.scenarios import make_all, validate_trace
    net = make_cohort(seed=5)
    ids = net.ids()
    juniors = [i for i in range(net.n) if net.grade[i] == 11]
    staff = {"prohibitedPairs": [[ids[juniors[0]], ids[juniors[1]]], [ids[juniors[2]], ids[juniors[3]]]],
             "allowedTables": {ids[juniors[4]]: list(range(0, 12)) + list(range(17, 25))}}
    traces = make_all(seed=5, scenarios=["honest"], rotations=2, anneal_iters=3000, cpsat_time=0.5,
                      feasibility_time=5, log=None, staff=staff, absence_rate=0.05, conflict_policy="waive")
    trace = traces["honest"]
    validate_trace(trace)
    assert trace["config"]["staff"]["prohibitedPairs"] == sorted(sorted(p) for p in staff["prohibitedPairs"])
    for rot in trace["rotations"]:
        where = {s: t for t, tbl in enumerate(rot["tables"]) for s in tbl}
        for a, b in staff["prohibitedPairs"]:
            if a in where and b in where:
                assert where[a] != where[b]
        if ids[juniors[4]] in where:
            assert where[ids[juniors[4]]] in staff["allowedTables"][ids[juniors[4]]]
        assert rot["release"]["validation"]["valid"] and rot["release"]["status"] in ("optimized", "incumbent", "fallback")
        assert sum(rot["targets"]) == len(trace["students"]) - len(rot["absent"])
        assert all(x <= c for x, c in zip(rot["targets"], trace["config"]["tableCapacities"]))
    assert any(rot["absent"] for rot in trace["rotations"])
