"""Screens: exact coercion test on closed candidates of every effective graph,
plus the capacity demand check.  Includes the audit's counterexamples."""
import pytest

from sim.generator import make_cohort, honest_lists, coalition_lists
from sim.screens import (coercion_screen, closed_bipartition, demand_screen, effective_lists, run_screens,
                         insular_screen, boundary_screen, is_closed)
from sim.solver import table_layout

CAPS = [7] * 17 + [6] * 23


def wiring(n, rule):
    return [rule(i) for i in range(n)]


# ---------------------------------------------------------------- basics ------
@pytest.mark.parametrize("n", range(4, 13))
def test_complete_digraphs_never_flag(n):
    lists = wiring(n, lambda i: [j for j in range(n) if j != i])
    r = coercion_screen(lists)
    assert r["flags"] == [] and all(c["split"] for c in r["candidates"])


@pytest.mark.parametrize("n", range(2, 13))
def test_pure_chains_always_flag(n):
    lists = wiring(n, lambda i: [(i + 1) % n])
    r = coercion_screen(lists)
    assert len(r["flags"]) == 1 and r["flags"][0]["size"] == n


@pytest.mark.parametrize("n", range(4, 13))
def test_hub_wirings_flag(n):
    lists = wiring(n, lambda i: [1] if i == 0 else [0, 1 + (i % (n - 1))])
    assert coercion_screen(lists)["flags"]


@pytest.mark.parametrize("n", range(4, 13))
@pytest.mark.parametrize("k", (2, 3, 4))
def test_circulants_odd_step_two_is_coercive_others_split(n, k):
    # C_n(1..k): with k >= 3 Thomassen's theorem gives a split; with k = 2 an
    # interleaved split exists for even n, while every directed cycle of an odd
    # C_n(1,2) has length >= ceil(n/2), so two disjoint closed parts cannot fit.
    if k >= n:
        pytest.skip("complete")
    lists = wiring(n, lambda i: [(i + d) % n for d in range(1, k + 1)])
    flagged = bool(coercion_screen(lists)["flags"])
    assert flagged == (k == 2 and n % 2 == 1)


def test_non_submitters_are_unconstrained():
    # audit false positive: only student 0 has an obligation; {0,1} | {2,3,4} is fine
    assert run_screens([[1, 2, 3, 4], [], [], [], []])["flags"] == []


def test_external_anchors_are_not_coercion():
    # audit false positive: a reciprocal pair with three outside names each
    lists = [[1, 2, 6, 10], [0, 2, 6, 10]] + [[2 + (i + d) % 13 for d in range(1, 5)] for i in range(13)]
    assert run_screens(lists)["flags"] == []


def test_common_outsider_cycle_is_forced():
    # six members list the next member and one shared non-submitting outsider:
    # no closed split separates them, so the cycle is forced together
    lists = [[(i + 1) % 6, 6] for i in range(6)] + [[]]
    r = coercion_screen(lists)
    assert r["flags"] and r["flags"][0]["members"] == list(range(7))
    assert r["flags"][0]["submitters"] == list(range(6))


def test_closed_bipartition_requires_submitters_on_both_sides():
    lists = [[1], [0], [], []]
    assert closed_bipartition([0, 1, 2, 3], lists) is None
    assert is_closed({2, 3}, lists)  # vacuously


# ------------------------------------------- effective graphs (stratified) ----
def test_same_grade_capture_is_flagged_only_on_the_effective_graph():
    # audit critical finding: seven juniors list the next two around a cycle
    # plus two distinct seniors each; the seniors vanish in same-grade rounds
    grade = [11] * 7 + [12] * 14
    lists = [[(i + 1) % 7, (i + 2) % 7, 7 + 2 * i, 8 + 2 * i] for i in range(7)]
    lists += [[7 + ((i - 7 + d) % 14) for d in range(1, 5)] for i in range(7, 21)]
    r = run_screens(lists, grade, {"mixed": CAPS, "same": CAPS})
    assert r["perState"]["mixed"]["flags"] == []
    assert [f["members"] for f in r["perState"]["same"]["flags"]] == [list(range(7))]
    assert r["returnedStudents"] == list(range(7))
    assert r["min4Violations"] == [] and r["sameGradeViolations"] == []
    assert closed_bipartition(list(range(7)), effective_lists(lists, grade, "same")) is None


def test_solo_actor_riding_a_coercive_pod_is_flagged():
    # audit A6: five juniors form C5(1,2) with two seniors each; a sixth junior lists four of them
    grade = [11] * 6 + [12] * 12
    lists = [[(i + 1) % 5, (i + 2) % 5, 6 + 2 * i, 7 + 2 * i] for i in range(5)] + [[0, 1, 2, 3]]
    lists += [[6 + (i + d) % 12 for d in range(1, 5)] for i in range(12)]
    r = run_screens(lists, grade, {"mixed": CAPS, "same": CAPS})
    assert r["perState"]["mixed"]["flags"] == []
    assert set(r["returnedStudents"]) == set(range(6))


def test_ineligible_submitters_reported():
    grade = [11, 12, 11, 11, 11]
    lists = [[1], [0], [3, 4], [2, 4], [2, 3]]
    r = run_screens(lists, grade, {"mixed": [5], "same": [5]})
    assert r["ineligible"] == [0, 1]


# -------------------------------------------------------- demand (capacity) ----
def test_k5_plus_followers_is_over_demanded():
    # audit critical finding: five mutual listers plus ten followers need 15 seats
    # at tables that each hold >= 2 core members, but 5 core members allow 2 tables
    lists = [[j for j in range(5) if j != i] for i in range(5)] + [list(range(4))] * 10
    lists += [[15 + ((i - 15 + d) % 20) for d in range(1, 5)] for i in range(15, 35)]
    flags = demand_screen(lists, CAPS)
    assert len(flags) == 1
    f = flags[0]
    assert f["core"] == list(range(5)) and f["followers"] == list(range(5, 15))
    assert f["maxTables"] == 2 and f["seats"] == 14 and f["demand"] == 15
    r = run_screens(lists, None, {"mixed": CAPS})
    assert set(r["returnedStudents"]) == set(range(15)) and r["flags"] == []


def test_demand_screen_passes_ordinary_cores():
    lists = [[j for j in range(5) if j != i] for i in range(5)] + [list(range(4))] * 9
    lists += [[14 + ((i - 14 + d) % 20) for d in range(1, 5)] for i in range(14, 34)]
    assert demand_screen(lists, CAPS) == []


# --------------------------------------------------------- large candidates ----
def test_large_candidates_use_thomassen_or_heuristic():
    n = 30
    lists = wiring(n, lambda i: [(i + d) % n for d in range(1, 4)])      # min out-degree 3
    r = coercion_screen(lists)
    assert r["flags"] == [] and r["candidates"][0]["reason"].startswith("minimum internal out-degree")
    lists = wiring(n, lambda i: [(i + d) % n for d in range(1, 3)])      # even circulant step 2
    r = coercion_screen(lists)
    assert r["flags"] == [] and "split" in r["candidates"][0]
    n = 25
    lists = wiring(n, lambda i: [(i + d) % n for d in range(1, 3)])      # odd C25(1,2): no split exists
    r = coercion_screen(lists)
    assert r["flags"] and r["flags"][0]["exact"] is True


# ------------------------------------------------------ synthetic cohort ------
def test_on_the_synthetic_cohort():
    net = make_cohort(seed=11)
    base = honest_lists(net)
    grade = list(int(g) for g in net.grade)
    caps = {"mixed": table_layout("mixed")[0], "same": table_layout("same")[0]}
    assert run_screens(base, grade, caps)["returnedStudents"] == []
    k1 = run_screens(coalition_lists(net, "k1", base), grade, caps)
    assert set(k1["flaggedStudents"]) == set(net.clique) and k1["min4Violations"] == sorted(net.clique)
    star = run_screens(coalition_lists(net, "min4", base), grade, caps)
    assert star["flags"] == [] and star["demandFlags"] == [] and star["min4Violations"] == []
    strat = run_screens(coalition_lists(net, "stratified", base), grade, caps)
    assert strat["perState"]["mixed"]["flags"] == []
    assert set(strat["returnedStudents"]) == set(net.clique) and strat["min4Violations"] == []
    tight = make_cohort(seed=11, mu=1.0)
    r = run_screens(honest_lists(tight), grade, caps)
    assert r["perState"]["mixed"]["candidates"] and r["flags"] == []


def test_legacy_detectors_still_available():
    lists = wiring(6, lambda i: [(i + 1) % 6])
    assert insular_screen(lists)[0]["kernel"] == list(range(6))
    lists = [[3, 4, 5, 1], [3, 4, 5, 0], [3, 4, 5, 0], [], [], []]
    assert boundary_screen(lists)[0]["members"] == [0, 1, 2]
