"""Fast unit tests of the pipeline pieces (no exported data needed)."""
import random

from sim.generator import generate_network, honest_lists, coalition_lists
from sim.solver import Problem, table_layout, pod_greedy, State, swap_repair, anneal, solve_rotation, random_assignment


def _fresh(state="mixed", mode=None):
    net = generate_network(seed=11)
    base = honest_lists(net)
    lists = coalition_lists(net, mode, base) if mode else base
    caps, tg = table_layout(state)
    hist = [[0] * net.n for _ in range(net.n)]
    return net, lists, Problem(net.grade, lists, caps, tg, hist, state)


def test_network_shape():
    net = generate_network(seed=3)
    assert net.n == 257 and net.n11 == 132 and net.n12 == 125
    assert all(len(f) == 8 for f in net.friends)
    assert 0.4 < net.reciprocity < 0.6
    lists = honest_lists(net)
    assert all(len(l) >= 4 for l in lists)
    assert all(sum(1 for j in l if net.grade[j] == net.grade[i]) >= 2 for i, l in enumerate(lists))


def test_generator_deterministic():
    a, b = generate_network(seed=5), generate_network(seed=5)
    assert a.friends == b.friends and a.clique == b.clique


def test_table_layout():
    caps, tg = table_layout("same")
    assert sum(c for c, g in zip(caps, tg) if g == 11) == 132
    assert sum(c for c, g in zip(caps, tg) if g == 12) == 125
    assert table_layout("mixed")[1] == [None] * 40


def test_greedy_and_repair_satisfy_everyone():
    for state in ("mixed", "same"):
        net, lists, p = _fresh(state)
        rng = random.Random(0)
        st = State(p, pod_greedy(p, rng))
        assert swap_repair(st, rng)
        assert not p.check(st.assign)


def test_anneal_cost_bookkeeping_consistent():
    net, lists, p = _fresh("mixed")
    rng = random.Random(1)
    st = State(p, pod_greedy(p, rng))
    swap_repair(st, rng)
    best, cost = anneal(st, rng, iters=5000)
    assert cost == p.cost_breakdown(best)["total"]
    assert st.cost == p.cost_breakdown(st.assign)["total"]


def test_pipeline_without_cpsat_is_feasible_and_deterministic():
    net, lists, p = _fresh("same")
    a1, i1 = solve_rotation(p, seed=3, anneal_iters=10_000, cpsat_time=0)
    a2, i2 = solve_rotation(p, seed=3, anneal_iters=10_000, cpsat_time=0)
    assert a1 == a2 and i1["final"]["violations"] == 0


def test_pipeline_with_cpsat_deterministic_mode():
    net, lists, p = _fresh("same")
    a1, i1 = solve_rotation(p, seed=4, anneal_iters=5_000, cpsat_time=1.0, deterministic=True)
    a2, i2 = solve_rotation(p, seed=4, anneal_iters=5_000, cpsat_time=1.0, deterministic=True)
    assert a1 == a2
    assert not p.check(a1)


def test_k1_chain_is_seated_together():
    net, lists, p = _fresh("mixed", mode="k1")
    a, info = solve_rotation(p, seed=0, anneal_iters=10_000, cpsat_time=0)
    assert len({a[m] for m in net.clique}) == 1


def test_min4_wiring_is_split():
    net, lists, p = _fresh("mixed", mode="min4")
    a, info = solve_rotation(p, seed=0, anneal_iters=20_000, cpsat_time=0)
    assert len({a[m] for m in net.clique}) >= 2


def test_random_assignment_respects_state():
    net, lists, p = _fresh("same")
    a = random_assignment(p, random.Random(0))
    assert not any(True for _ in []) or p.members_of(a)
    for t, ms in enumerate(p.members_of(a)):
        assert len(ms) == p.caps[t]
        assert {p.grade[i] for i in ms} == {p.table_grade[t]}
