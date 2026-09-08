"""Fast unit tests of the pipeline pieces and its invariants."""
import random

import pytest

from sim.generator import make_cohort, honest_lists, coalition_lists
from sim import solver as S
from sim.solver import (Problem, table_layout, pod_greedy, State, swap_repair, anneal, solve_rotation,
                        random_assignment, feasibility_certificate, InfeasibleInputError)


def _fresh(state="mixed", mode=None, seed=11):
    net = make_cohort(seed=seed)
    base = honest_lists(net)
    lists = coalition_lists(net, mode, base) if mode else base
    caps, tg = table_layout(state)
    hist = [[0] * net.n for _ in range(net.n)]
    return net, lists, Problem(net.grade, lists, caps, tg, hist, state, history_alpha=[row[:] for row in hist])


def test_network_shape():
    net = make_cohort(seed=3)
    assert net.n == 257 and net.n11 == 132 and net.n12 == 125
    assert all(len(f) == 8 for f in net.friends)
    assert 0.4 < net.reciprocity < 0.6
    lists = honest_lists(net)
    assert all(len(l) >= 4 for l in lists)
    assert all(sum(1 for j in l if net.grade[j] == net.grade[i]) >= 2 for i, l in enumerate(lists))


def test_table_layout_default_and_general():
    caps, tg = table_layout("same")
    assert caps.count(7) == 17 and caps.count(6) == 23
    assert tg == [11] * 12 + [12] * 5 + [11] * 8 + [12] * 15
    caps, tg = table_layout("same", 126, 126)
    assert sum(caps) == 252 and caps.count(7) == 12
    assert sum(c for c, g in zip(caps, tg) if g == 11) == 126 and sum(c for c, g in zip(caps, tg) if g == 12) == 126
    assert table_layout("mixed", 240, 0)[0] == [6] * 40
    with pytest.raises(ValueError):
        table_layout("mixed", 100, 100)
    with pytest.raises(ValueError):
        table_layout("mixed", 150, 150)


def test_repeat_weights_follow_the_stated_policy():
    # incidental repeats cost 5 per meeting, listed-friend repeats 2
    lists = [[1], [0], [], []]
    m = [[0] * 4 for _ in range(4)]
    a = [[0] * 4 for _ in range(4)]
    a[0][1] = a[1][0] = 3          # listed pair met 3 times
    m[2][3] = m[3][2] = 2          # incidental pair met twice
    p = Problem([11] * 4, lists, [2, 2], [None, None], m, "mixed", history_alpha=a)
    assert p.W[0][1] == S.W_ALPHA * 3 and p.W[2][3] == S.W_M * 2
    # legacy single-matrix history is split by today's listed relation
    tot = [[0] * 4 for _ in range(4)]
    tot[0][1] = tot[1][0] = 3
    tot[2][3] = tot[3][2] = 2
    q = Problem([11] * 4, lists, [2, 2], [None, None], tot, "mixed")
    assert q.W[0][1] == S.W_ALPHA * 3 and q.W[2][3] == S.W_M * 2


def test_greedy_and_repair_satisfy_everyone():
    for state in ("mixed", "same"):
        net, lists, p = _fresh(state)
        rng = random.Random(0)
        st = State(p, pod_greedy(p, rng))
        assert swap_repair(st, rng)
        assert not p.check(st.assign) and st.viol == 0


def test_repair_never_strands_a_satisfied_student():
    # audit reproduction: the old rule accepted a swap that transferred the violation to student 6
    lists = ([[6, 7, 8, 9]] + [[j for j in range(1, 6) if i != j] for i in range(1, 6)]
             + [[j for j in range(6, 12) if i != j][:4] for i in range(6, 12)])
    p = Problem([11] * 12, lists, [6, 6], [None, None], [[0] * 12 for _ in range(12)], "mixed")
    st = State(p, [0] * 6 + [1] * 6)
    before = st.violated()
    swap_repair(st, random.Random(0), max_rounds=3)
    assert st.violated() <= before
    # random feasible instances: the violated set never grows during repair
    for seed in range(3):
        net, lists, p = _fresh("mixed", seed=20 + seed)
        rng = random.Random(seed)
        st = State(p, pod_greedy(p, rng))
        prev = st.violated()
        for _ in range(5):
            swap_repair(st, rng, max_rounds=1)
            cur = st.violated()
            assert cur <= prev
            prev = cur


def test_padded_groups_are_reclosed():
    base = [1, 0, 3, 2, 5, 4, 7, 8, 6, 10, 11, 9]
    lists = [[base[i]] + ([9, 10, 11] if i < 6 else [3, 4, 5]) for i in range(12)]
    p = Problem([11] * 12, lists, [6, 6], [None, None], [[0] * 12 for _ in range(12)], "mixed")
    st = State(p, [0] * 6 + [1] * 6)
    rng = random.Random(0)
    assert st.closure(0, rng) == {0, 1} and st.closure(6, rng) == {6, 7, 8}
    assert st.close_set({0, 1, 2}, 0, rng) == {0, 1, 2, 3}   # 3 would be orphaned otherwise


def test_anneal_never_leaves_the_feasible_region():
    net, lists, p = _fresh("mixed")
    rng = random.Random(1)
    st = State(p, pod_greedy(p, rng))
    swap_repair(st, rng)
    assert st.viol == 0
    seen_violation = []
    orig = State.apply_group_swap

    def guarded(self, d, dv, payload):
        if self.viol == 0 and dv > 0:
            seen_violation.append(dv)
        return orig(self, d, dv, payload)

    State.apply_group_swap = guarded
    try:
        best, cost, viol = anneal(st, rng, iters=20000)
    finally:
        State.apply_group_swap = orig
    assert seen_violation == [] and viol == 0 and st.viol == 0
    assert cost == p.cost_breakdown(best)["total"]
    assert st.cost == p.cost_breakdown(st.assign)["total"]
    assert p.check(best) == []


def test_state_bookkeeping_matches_recomputation():
    net, lists, p = _fresh("same")
    rng = random.Random(3)
    st = State(p, pod_greedy(p, rng))
    for _ in range(300):
        a, b = rng.sample(range(p.n), 2)
        if st.assign[a] == st.assign[b] or p.grade[a] != p.grade[b]:
            continue
        d, dv, payload = st.delta_swap(a, b)
        st.apply_group_swap(d, dv, payload)
    cb = p.cost_breakdown(st.assign)
    assert st.cost == cb["total"] and st.viol == cb["violations"]


def test_pipeline_without_cpsat_is_feasible_and_deterministic():
    net, lists, p = _fresh("same")
    a1, i1 = solve_rotation(p, seed=3, anneal_iters=10_000, cpsat_time=0)
    a2, i2 = solve_rotation(p, seed=3, anneal_iters=10_000, cpsat_time=0)
    assert a1 == a2 and i1["final"]["violations"] == 0
    assert set(i1["time"]) == {"greedy", "repair", "anneal", "cpsat", "fallback", "total"}


def test_pipeline_with_cpsat_deterministic_mode():
    net, lists, p = _fresh("same")
    a1, i1 = solve_rotation(p, seed=4, anneal_iters=5_000, cpsat_time=1.0, deterministic=True)
    a2, i2 = solve_rotation(p, seed=4, anneal_iters=5_000, cpsat_time=1.0, deterministic=True)
    assert a1 == a2 and not p.check(a1)


def test_empty_effective_list_is_rejected_not_dropped():
    # audit: two students listing only each other across grades in a same-grade rotation
    p = Problem([11, 12], [[1], [0]], [1, 1], [11, 12], [[0, 0], [0, 0]], "same")
    assert p.ineligible == [0, 1]
    with pytest.raises(InfeasibleInputError):
        S.cpsat_polish(p, [0, 1], time_limit=1, workers=1)
    with pytest.raises(InfeasibleInputError):
        solve_rotation(p, anneal_iters=100, cpsat_time=0)
    with pytest.raises(InfeasibleInputError):
        feasibility_certificate(p, time_limit=1, workers=1)


def test_feasibility_certificate():
    net, lists, p = _fresh("mixed")
    status, assign = feasibility_certificate(p, time_limit=10, workers=4)
    assert status in ("OPTIMAL", "FEASIBLE") and p.check(assign) == []
    # audit K5 + followers: provably infeasible
    n = 257
    L = [[] for _ in range(n)]
    for i in range(5):
        L[i] = [j for j in range(5) if j != i]
    for i in range(5, 15):
        L[i] = list(range(4))
    for members in (list(range(15, 132)), list(range(132, 257))):
        for ix, i in enumerate(members):
            L[i] = [members[(ix + d) % len(members)] for d in range(1, 5)]
    caps, tg = table_layout("same")
    q = Problem([11] * 132 + [12] * 125, L, caps, tg, [[0] * n for _ in range(n)], "same")
    status, _ = feasibility_certificate(q, time_limit=20, workers=4)
    assert status == "INFEASIBLE"


def test_k1_chain_is_seated_together():
    net, lists, p = _fresh("mixed", mode="k1")
    a, info = solve_rotation(p, seed=0, anneal_iters=10_000, cpsat_time=0)
    assert len({a[m] for m in net.clique}) == 1


def test_star_wiring_is_split_but_not_into_pairs():
    net, lists, p = _fresh("mixed", mode="min4")
    a, info = solve_rotation(p, seed=0, anneal_iters=20_000, cpsat_time=0)
    sizes = sorted(sum(1 for m in net.clique if a[m] == t) for t in set(a[m] for m in net.clique))
    assert len(sizes) >= 2 and max(sizes) >= 3


def test_stratified_attack_captures_only_in_same_grade_rotations():
    net, lists, p = _fresh("same", mode="stratified")
    a, info = solve_rotation(p, seed=0, anneal_iters=20_000, cpsat_time=0)
    assert len({a[m] for m in net.clique}) == 1
    net, lists, p = _fresh("mixed", mode="stratified")
    a, info = solve_rotation(p, seed=0, anneal_iters=20_000, cpsat_time=0)
    assert len({a[m] for m in net.clique}) >= 2


def test_random_assignment_respects_state():
    net, lists, p = _fresh("same")
    a = random_assignment(p, random.Random(0))
    for t, ms in enumerate(p.members_of(a)):
        assert len(ms) == p.caps[t]
        assert {p.grade[i] for i in ms} == {p.table_grade[t]}
