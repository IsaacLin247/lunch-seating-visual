"""The CP-SAT stage minimises exactly the canonical objective."""
from itertools import product

import pytest

from sim.objective import Objective, DEFAULT_OBJECTIVE, objective_from_config
from sim.solver import Problem, cpsat_polish, solve_rotation


def _small_problem(objective=None):
    # eight students, two tables of four; everyone lists two peers; a rich history
    grade = [11] * 8
    lists = [[1, 2], [0, 3], [3, 0], [2, 1], [5, 6], [4, 7], [7, 4], [6, 5]]
    m = [[0] * 8 for _ in range(8)]
    a = [[0] * 8 for _ in range(8)]
    for (x, y), k in {(0, 4): 3, (1, 5): 1, (2, 6): 2, (3, 7): 1, (0, 5): 1}.items():
        m[x][y] = m[y][x] = k                     # incidental meetings
    for (x, y), k in {(0, 1): 2, (4, 5): 1, (2, 3): 1}.items():
        a[x][y] = a[y][x] = k                     # listed-pair meetings
    prev = [[0, 4, 1, 6], [2, 5, 3, 7]]           # only some historical pairs met last time
    return Problem(grade, lists, [4, 4], [None, None], m, "mixed", prev_tables=prev, history_alpha=a,
                   objective=objective)


def _brute_force_optimum(p):
    best = None
    n = p.n
    for assign in product(range(p.T), repeat=n):
        if [assign.count(t) for t in range(p.T)] != p.targets:
            continue
        cb = p.cost_breakdown(list(assign))
        if cb["hard"]:
            continue
        if best is None or cb["total"] < best:
            best = cb["total"]
    return best


@pytest.mark.parametrize("objective", [None, Objective(extra_weight=0.5), Objective(extra_weight=3)])
def test_cpsat_objective_equals_independent_score_and_the_true_optimum(objective):
    p = _small_problem(objective)
    hint = [0, 0, 0, 0, 1, 1, 1, 1]
    assign, info = cpsat_polish(p, hint, time_limit=5, workers=1)
    assert info["status"] == "OPTIMAL" and info["exact"] and info["objectiveConsistent"]
    cb = p.cost_breakdown(assign)
    assert cb["hard"] == 0
    assert info["objective"] == p.obj.extra_int * cb["extraPeers"] + cb["repeat"] == cb["total"]
    assert cb["total"] == _brute_force_optimum(p)
    # every pair with nonzero history is modelled, not only last rotation's pairs
    assert info["pairVariables"] == sum(1 for x in range(8) for y in range(x + 1, 8) if p.W[x][y]) == 8


def test_historical_pairs_absent_from_the_preceding_rotation_still_cost():
    # (0, 5) met once before but did not share a table in the immediately preceding rotation
    p = _small_problem()
    assert p.W[0][5] == DEFAULT_OBJECTIVE.m_int and all(5 not in t or 0 not in t for t in p.prev_tables)
    exact, info_exact = cpsat_polish(p, [0, 0, 0, 0, 1, 1, 1, 1], time_limit=5, workers=1)
    prev, info_prev = cpsat_polish(p, [0, 0, 0, 0, 1, 1, 1, 1], time_limit=5, workers=1, pairs="previous")
    assert info_exact["pairVariables"] == 8 and info_prev["pairVariables"] == 4
    assert not info_prev["exact"]
    # the surrogate's objective omits four weighted pairs and underestimates the true cost
    cb_prev = p.cost_breakdown(prev)
    assert info_prev["objective"] <= p.obj.extra_int * cb_prev["extraPeers"] + cb_prev["repeat"]
    # independent scoring charges the omitted (0,5) meeting: two charts that differ only by
    # exchanging students 5 and 6 differ by exactly the (0,5)-type weights involved
    with_five = [0, 0, 1, 1, 0, 0, 1, 1]      # table 0 = {0,1,4,5}
    with_six = [0, 0, 1, 1, 0, 1, 0, 1]       # table 0 = {0,1,4,6}
    d = p.cost_breakdown(with_five)["repeat"] - p.cost_breakdown(with_six)["repeat"]
    assert d == (p.W[0][5] + p.W[1][5] + p.W[4][5] + p.W[2][6] + p.W[3][6] + p.W[7][6]) - (
        p.W[0][6] + p.W[1][6] + p.W[4][6] + p.W[2][5] + p.W[3][5] + p.W[7][5])
    assert p.W[0][5] > 0 and d != 0


def test_pipeline_guard_uses_independent_rescoring_and_reports_consistency():
    p = _small_problem()
    assign, info = solve_rotation(p, seed=0, anneal_iters=500, cpsat_time=2, workers=1)
    assert info["validation"]["valid"] and info["cpsat"]["objectiveConsistent"]
    assert info["final"]["total"] <= info["anneal"]["total"]
    assert info["final"] == p.cost_breakdown(assign)


def test_objective_integer_scaling_and_backward_compatible_defaults():
    d = DEFAULT_OBJECTIVE
    assert (d.scale, d.extra_int, d.m_int, d.alpha_int, d.violation_int) == (10, 10, 5, 2, 10000)
    assert (d.t0_int, d.t1_int) == (25.0, 0.2)
    assert d.describe()["cpsatObjective"] == "10 * extras + sum(5 m_ab + 2 alpha_ab)"
    half = objective_from_config({"extraWeight": 0.5})
    assert (half.scale, half.extra_int, half.m_int, half.alpha_int) == (10, 5, 5, 2)
    quarter = Objective(extra_weight=0.25)
    assert (quarter.scale, quarter.extra_int, quarter.m_int, quarter.alpha_int, quarter.violation_int) == (20, 5, 10, 4, 20000)
    assert float(quarter.unscaled(quarter.integer_cost(0, 3, quarter.pair_weight(1, 1)))) == pytest.approx(0.25 * 3 + 0.1 * 7)
    with pytest.raises(ValueError):
        Objective(extra_weight=-1)
    p = _small_problem(quarter)
    assert p.pen[0][3] == 2 * quarter.extra_int and p.pen[0][0] == quarter.violation_int
