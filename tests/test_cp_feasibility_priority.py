"""Retain a feasible initial CP witness when a later fallback is UNKNOWN."""
import pytest

from sim import solver


@pytest.mark.parametrize("incumbent_feasible", [False, True])
def test_cp_prioritizes_feasibility_but_preserves_guard_for_valid_incumbent(monkeypatch, incumbent_feasible):
    incumbent = [0, 1, 0, 1]
    cp_witness = [0, 0, 1, 1]
    lists = [[1], [0], [3], [2]]
    if incumbent_feasible:
        lists = [[1, 2], [0, 3], [0, 3], [1, 2]]
    history = [[0] * 4 for _ in range(4)]
    for a, b in [(0, 1), (2, 3)]:
        history[a][b] = history[b][a] = 100000
    problem = solver.Problem([11] * 4, lists, [2, 2], [None, None],
                             [[0] * 4 for _ in range(4)], "mixed", history_alpha=history)
    incumbent_cost = problem.cost_breakdown(incumbent)
    assert bool(incumbent_cost["violations"]) is not incumbent_feasible
    assert problem.check(cp_witness) == []
    assert problem.cost_breakdown(cp_witness)["total"] > incumbent_cost["total"]
    monkeypatch.setattr(solver, "pod_greedy", lambda *_: list(incumbent))
    monkeypatch.setattr(solver, "swap_repair", lambda *_: None)
    monkeypatch.setattr(solver, "anneal", lambda *_, **__: (
        list(incumbent), incumbent_cost["total"], incumbent_cost["violations"]))
    cp_calls = []
    def controlled_cp(*_, **kwargs):
        cp_calls.append(kwargs["time_limit"])
        if len(cp_calls) == 1:
            return list(cp_witness), {"status": "FEASIBLE"}
        return None, {"status": "UNKNOWN"}
    monkeypatch.setattr(solver, "cpsat_polish", controlled_cp)
    result, info = solver.solve_rotation(problem, anneal_iters=0, cpsat_time=.1)
    assert problem.check(result) == []
    assert result == (incumbent if incumbent_feasible else cp_witness)
    assert info["accepted"] == ("anneal" if incumbent_feasible else "cpsat")
    assert cp_calls == [.1]
    assert "cpsatFallback" not in info
