"""Closed-form expectations for uniformly random seating.

Used to sanity-check the simulated random baseline and to state the mixing
benchmark for a given schedule without simulation.

  * expected_distinct(...)  mean over students of the expected number of
    distinct schoolmates met over the year (each pair meets independently in
    each rotation with the hypergeometric probability that both land at the
    same table; rotations are independent under random seating).
  * expected_friend_coverage(...)  probability that a submitter has at least one
    eligible listed peer at their table, averaged over submitters and weighted
    by seat counts, per rotation state.
"""
from __future__ import annotations

from math import comb


def pair_meet_probability(caps, n):
    """P(two given students share a table) under a uniform random seating of n
    students into tables with the given capacities (sum caps == n)."""
    assert sum(caps) == n
    return sum(c * (c - 1) for c in caps) / (n * (n - 1))


def expected_distinct(grade, caps_mixed, caps_same_by_grade, states):
    """Expected distinct schoolmates met per student, averaged over students."""
    n = len(grade)
    sizes = {}
    for g in grade:
        sizes[g] = sizes.get(g, 0) + 1
    n_mixed = sum(1 for s in states if s == "mixed")
    n_same = len(states) - n_mixed
    q_mixed = pair_meet_probability(caps_mixed, n)
    q_same = {g: pair_meet_probability(caps_same_by_grade[g], sizes[g]) for g in sizes}
    total = 0.0
    for a in range(n):
        for b in range(n):
            if a == b:
                continue
            p_never = (1 - q_mixed) ** n_mixed
            if grade[a] == grade[b]:
                p_never *= (1 - q_same[grade[a]]) ** n_same
            total += 1 - p_never
    return total / n


def _p_no_listed_peer(k, n, c):
    """Given a student with k eligible listed peers among n-1 others, P(none of
    them is among the c-1 other seats at the student's table)."""
    if k == 0:
        return 1.0
    if c - 1 > n - 1 - k:
        return 0.0
    return comb(n - 1 - k, c - 1) / comb(n - 1, c - 1)


def expected_friend_coverage(grade, lists, caps_mixed, caps_same_by_grade, state):
    """P(>= 1 eligible listed peer at the table) for a random seating in `state`,
    averaged over submitters; each submitter sits at a table of capacity c with
    probability proportional to c within their eligible population."""
    n = len(grade)
    subs = [i for i, l in enumerate(lists) if l]
    if not subs:
        return 0.0
    total = 0.0
    for i in subs:
        if state == "mixed":
            k = len(lists[i])
            pop, caps = n, caps_mixed
        else:
            k = sum(1 for j in lists[i] if grade[j] == grade[i])
            pop = sum(1 for g in grade if g == grade[i])
            caps = caps_same_by_grade[grade[i]]
        seats = sum(caps)
        p_cov = sum(c / seats * (1 - _p_no_listed_peer(k, pop, c)) for c in caps)
        total += p_cov
    return 100.0 * total / len(subs)
