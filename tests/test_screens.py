"""Spec 2: exact coercion-capability screen (property tests, wirings inline)."""
import pytest

from sim.generator import make_cohort, honest_lists, coalition_lists
from sim.screens import coercion_screen, closed_bipartition, insular_screen, boundary_screen, run_screens


def wiring(n, rule):
    return [rule(i) for i in range(n)]


@pytest.mark.parametrize("n", range(4, 13))
def test_complete_digraphs_never_flag(n):
    lists = wiring(n, lambda i: [j for j in range(n) if j != i])
    r = coercion_screen(lists)
    assert r["flags"] == [] and r["candidates"] and all(c["split"] for c in r["candidates"])


@pytest.mark.parametrize("n", range(3, 13))
def test_pure_chains_always_flag(n):
    lists = wiring(n, lambda i: [(i + 1) % n])
    r = coercion_screen(lists)
    assert len(r["flags"]) == 1 and r["flags"][0]["size"] == n


@pytest.mark.parametrize("n", range(4, 13))
def test_hub_wirings_flag(n):
    # everyone lists hub 0 plus the next member of a chain among the rest; the hub lists member 1
    lists = wiring(n, lambda i: [1] if i == 0 else [0, 1 + (i % (n - 1))])
    assert coercion_screen(lists)["flags"]


@pytest.mark.parametrize("n", range(4, 13))
def test_circulant_lists_do_not_flag(n):
    k = 2 if n % 2 == 0 else 3            # an interleaved split exists
    lists = wiring(n, lambda i: [(i + d) % n for d in range(1, k + 1)])
    r = coercion_screen(lists)
    assert r["flags"] == []
    assert closed_bipartition(list(range(n)), lists) is not None


def test_shared_outsider_wiring_is_a_boundary_candidate_but_splits():
    # six members each list the next three co-members plus one shared outsider (6);
    # the outsider and the rest of the school have ordinary lists
    lists = [[(i + d) % 6 for d in (1, 2, 3)] + [6] for i in range(6)]
    lists += [[7, 8, 9, 10]] + [[6, 7, 8, 9, 10, 11][:4]] * 5
    r = coercion_screen(lists)
    six = next(c for c in r["candidates"] if c["members"] == list(range(6)))
    assert "boundary" in six["sources"] and six["flagged"] is False
    assert not any(f["members"] == list(range(6)) for f in r["flags"])


def test_small_candidates_cannot_split_and_flag():
    lists = [[1], [0], [], []]            # a pair listing only each other
    r = coercion_screen(lists)
    assert r["flags"][0]["members"] == [0, 1]


def test_detectors_still_available_for_comparison():
    lists = wiring(6, lambda i: [(i + 1) % 6])
    assert insular_screen(lists)[0]["kernel"] == list(range(6))
    lists = [[3, 4, 5, 1], [3, 4, 5, 0], [3, 4, 5, 0], [], [], []]
    assert boundary_screen(lists)[0]["members"] == [0, 1, 2]


def test_on_the_synthetic_cohort():
    net = make_cohort(seed=11)
    base = honest_lists(net)
    assert run_screens(base)["flags"] == []
    k1 = run_screens(coalition_lists(net, "k1", base))
    assert set(k1["flaggedStudents"]) == set(net.clique) and k1["min4Violations"] == sorted(net.clique)
    m4 = run_screens(coalition_lists(net, "min4", base))
    assert m4["min4Violations"] == []
    assert set(m4["flaggedStudents"]) <= set(net.clique) and set(m4["returnedStudents"]) == set(net.clique)
    # the six-set itself is splittable; the flag comes from an unsplittable boundary cluster
    six = next(c for c in m4["candidates"] if set(c["members"]) == set(net.clique))
    assert six["flagged"] is False
    # honest cohorts with strong latent groups are insular but not coercive
    tight = make_cohort(seed=11, mu=1.0)
    r = run_screens(honest_lists(tight))
    assert r["candidates"] and r["flags"] == []
