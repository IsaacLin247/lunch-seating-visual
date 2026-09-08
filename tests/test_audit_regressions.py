"""Counterexamples from the second audit and independent certificate checks."""
import random

import pytest

from sim import screens
from sim.solver import Problem, table_layout


def capacity_pools():
    caps, table_grades = table_layout("same")
    by_grade = {g: [c for c, tg in zip(caps, table_grades) if tg == g] for g in (11, 12)}
    return caps, table_grades, by_grade


def shared_anchor_population():
    grades = [11] * 132 + [12] * 125
    lists = [[(i + 1) % 7, 7, 132, 133] for i in range(7)]
    for lo, size in ((7, 125), (132, 125)):
        lists += [[lo + (i + d) % size for d in (-2, -1, 1, 2)] for i in range(size)]
    return grades, lists


def test_shared_outside_anchor_capture_full_257_is_detected_and_feasible():
    grades, lists = shared_anchor_population()
    caps, table_grades, by_grade = capacity_pools()
    report = screens.run_screens(lists, grades, {"mixed": caps, "same": caps},
                                caps_by_grade_by_state={"same": by_grade})
    assert not report["min4Violations"] and not report["sameGradeViolations"]
    assert not report["ineligible"] and not report["unresolvedChecks"]
    assert not report["perState"]["mixed"]["flags"]
    flag, = report["perState"]["same"]["flags"]
    assert flag["screen"] == "targeted-coercion"
    assert flag["core"] == list(range(7)) and flag["outside"] == [7]
    assert flag["verdict"] == "proved-coercive" and flag["exact"]
    assert report["returnedStudents"] == list(range(7))

    # A complete valid chart establishes non-vacuous full-table capture. The
    # anchor and background rings fit consecutive blocks of their grade pools.
    tables = [list(range(7))] + [[] for _ in caps[1:]]
    remaining = {11: iter(range(7, 132)), 12: iter(range(132, 257))}
    for t in range(1, len(caps)):
        tables[t] = [next(remaining[table_grades[t]]) for _ in range(caps[t])]
    assign = [0] * 257
    for t, members in enumerate(tables):
        for i in members:
            assign[i] = t
    for state in ("mixed", "same"):
        p = Problem(grades, lists, caps, table_grades if state == "same" else [None] * len(caps),
                    [[0] * 257 for _ in grades], state)
        assert p.check(assign) == []


def test_deleting_anchor_exposes_a_core_but_restores_its_list_edges():
    lists = [[(i + 1) % 7, 7] for i in range(7)] + [[0, 8], [9], [8]]
    report = screens.coercion_screen(lists)
    core_flags = [f for f in report["flags"] if f["core"] == list(range(7))]
    assert len(core_flags) == 1
    assert core_flags[0]["outside"] == [7]
    assert 7 in core_flags[0]["anchorDeletions"]
    # A different outside anchor for each member permits separation.
    lists = [[(i + 1) % 7, i + 7] for i in range(7)] + [[] for _ in range(7)]
    assert screens.coercion_screen(lists)["flags"] == []


def test_grade_demand_never_borrows_the_other_grades_tables():
    grades = [11] * 132 + [12] * 125
    lists = [[(i + d) % 132 for d in (-2, -1, 1, 2)] for i in range(132)]
    core, followers = list(range(132, 145)), list(range(145, 174))
    lists += [[132 + (i + d) % 13 for d in (-2, -1, 1, 2)] for i in range(13)]
    lists += [core[:4] for _ in followers]
    lists += [[174 + (i + d) % 83 for d in (-2, -1, 1, 2)] for i in range(83)]
    caps, _, by_grade = capacity_pools()
    report = screens.run_screens(lists, grades, {"mixed": caps, "same": caps},
                                caps_by_grade_by_state={"same": by_grade})
    flag, = report["perState"]["same"]["demandFlags"]
    assert flag["core"] == core and flag["followers"] == followers
    assert (flag["demand"], flag["seats"], flag["maxTables"], flag["admissibleGrade"]) == (42, 41, 6, 12)
    assert report["perState"]["mixed"]["demandFlags"] == []
    assert set(report["returnedStudents"]) == set(core + followers)


def test_missing_grade_capacity_pool_is_an_explicit_unresolved_check():
    lists = [[1], [0], [3], [2]]
    report = screens.run_screens(lists, [11, 11, 12, 12], {"same": [2, 2]}, states=["same"])
    assert report["perState"]["same"]["demandStatus"] == "unresolved"
    assert report["perState"]["same"]["demandFlags"] == []
    assert report["unresolvedChecks"][0]["screen"] == "demand"
    with pytest.raises(ValueError, match="missing capacity pool"):
        screens.demand_screen(lists, [2, 2], grade=[11, 11, 12, 12], caps_by_grade={11: [2]})


def test_real_zero_budget_unknown_never_returns_students():
    # This easy even circulant has an explicit alternating split. A zero
    # deterministic budget exercises the actual CP-SAT UNKNOWN path.
    lists = [[(i + 1) % 22, (i + 2) % 22] for i in range(22)]
    assert screens.is_closed(range(0, 22, 2), lists)
    assert screens.is_closed(range(1, 22, 2), lists)
    assert screens._cpsat_split(list(range(22)), lists, time_limit=0) == (None, False)
    report = screens.run_screens(lists, deterministic_time=0)
    assert report["flags"] == [] and report["returnedStudents"] == []
    unresolved, = report["unresolvedCandidates"]
    assert unresolved["verdict"] == "unresolved" and not unresolved["flagged"]
    assert not unresolved["exact"]


def test_degree_shortcut_does_not_apply_to_unconstrained_anchor_vertices():
    lists = [[3, 4, 5], [3, 4, 5], [3, 4, 5]] + [[] for _ in range(25)]
    # Force the larger-candidate route independently of candidate generation.
    candidate = {}
    screens._decide_candidate(candidate, list(range(28)), lists, 0, allow_degree_shortcut=True)
    assert candidate["verdict"] == "unresolved"
    assert "Thomassen" not in candidate["reason"]
    assert screens.min_internal_outdegree({0, 1}, [[1, 1, 1], [0, 0, 0]]) == 1


def partitions(vertices):
    """All set partitions, independent of the screen's bipartition algorithm."""
    if not vertices:
        yield []
        return
    first, *rest = vertices
    for partition in partitions(rest):
        yield [[first], *partition]
        for k in range(len(partition)):
            yield [([first] + part if i == k else list(part)) for i, part in enumerate(partition)]


def test_certified_core_is_together_in_every_small_feasible_partition():
    rng = random.Random(1908)
    all_partitions = list(partitions(list(range(6))))
    certified = 0
    for _ in range(180):
        # Include non-submitters and shared anchors, which are excluded from
        # the minimum-out-degree theorem's scope.
        lists = [[j for j in range(6) if j != i and rng.random() < 0.3] for i in range(6)]
        flags = screens.coercion_screen(lists)["flags"]
        if not flags:
            continue
        certified += len(flags)
        for partition in all_partitions:
            where = {i: k for k, part in enumerate(partition) for i in part}
            feasible = all(not peers or any(where[i] == where[j] for j in peers)
                           for i, peers in enumerate(lists))
            if feasible:
                for flag in flags:
                    assert len({where[i] for i in flag["core"]}) == 1
    assert certified > 50


def test_candidate_truncation_is_reported_as_incomplete_coverage():
    lists = [[(i + 1) % 7, 7] for i in range(7)] + [[0, 8], [9], [8]]
    report = screens.coercion_screen(lists, target_limit=0)
    assert report["coverage"]["targetCandidatesTruncated"]
    assert report["coverage"]["targetCandidatesExamined"] == 0
    assert report["coverage"]["complete"] is False
