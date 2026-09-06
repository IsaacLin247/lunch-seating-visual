"""Synthetic-but-realistic friendship network at true school scale.

Model (from the spec):
  * two grade blocks (11: 132 students, 12: 125 students)
  * within-grade bias 9:1 when picking background friends
  * lognormal popularity (sigma = 0.6) as the attraction weight
  * ~50% reciprocity of directed friendships
  * K = 8 "true" friends per student
  * latent friend groups (make_cohort): students are partitioned into groups of
    size U[6, 12] (within grade unless cross_grade_group_frac says otherwise);
    with probability omega a student also joins one secondary group; each true
    friendship is drawn with probability mu from the student's group(s)
    (popularity-weighted) and otherwise from the background distribution
    (which excludes the student's own group, so the in-group share is mu).
    mu = 0, omega = 0 (the default) is the plain grade-biased network.

Submitted lists = the true friends, filtered / padded so that they obey the
submission rules ("min-4-or-none", ">= 2 same-grade names").  At mu = 1 with
small groups honest submissions may be legitimately insular; that is the point.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

N11_DEFAULT = 132
N12_DEFAULT = 125
K_DEFAULT = 8
MIN_LIST = 4          # min-4-or-none rule
MIN_SAME_GRADE = 2    # so the guarantee is satisfiable in same-grade rotations


def student_id(i: int) -> str:
    return f"S{i + 1:03d}"


@dataclass
class Network:
    n11: int
    n12: int
    grade: np.ndarray                  # grade[i] in {11, 12}
    popularity: np.ndarray             # lognormal weights
    friends: list[list[int]]           # true friends, in preference order
    seed: int
    reciprocity: float                 # measured fraction of reciprocated edges
    clique: list[int] = field(default_factory=list)  # the 6 who may collude
    mu: float = 0.0
    omega: float = 0.0
    groups: list[list[int]] = field(default_factory=list)          # latent groups (member lists)
    primary: list[int] = field(default_factory=list)               # primary group index per student
    secondary: list[int | None] = field(default_factory=list)      # secondary group index or None

    def group_pool(self, i: int) -> set[int]:
        """Members of i's group(s), excluding i."""
        pool = set(self.groups[self.primary[i]]) if self.groups else set()
        if self.groups and self.secondary[i] is not None:
            pool |= set(self.groups[self.secondary[i]])
        pool.discard(i)
        return pool

    def in_group_fraction(self) -> float:
        """Fraction of true friendships that fall inside the lister's group(s)."""
        if not self.groups:
            return 0.0
        tot = sum(len(f) for f in self.friends)
        ing = sum(1 for i, f in enumerate(self.friends) for j in f if j in self.group_pool(i))
        return ing / tot if tot else 0.0

    @property
    def n(self) -> int:
        return self.n11 + self.n12

    def ids(self) -> list[str]:
        return [student_id(i) for i in range(self.n)]


def _measure_reciprocity(friends: list[set[int]]) -> float:
    total = sum(len(f) for f in friends)
    recip = sum(1 for i, f in enumerate(friends) for j in f if i in friends[j])
    return recip / total if total else 0.0


def _make_groups(rng, grade, group_size_dist, cross_grade_group_frac):
    """Partition students into latent groups of size U[lo, hi]."""
    lo, hi = group_size_dist
    pools = {g: [int(x) for x in rng.permutation(np.flatnonzero(grade == g))] for g in sorted(set(grade.tolist()))}
    groups: list[list[int]] = []
    last_of_grade: dict[int, int] = {}       # grade -> index of the last group holding that grade
    while any(pools.values()):
        size = int(rng.integers(lo, hi + 1))
        live = [g for g, p in pools.items() if p]
        if len(live) > 1 and rng.random() < cross_grade_group_frac:
            members = []
            while len(members) < size and any(pools[g] for g in live):
                g = live[int(rng.integers(len(live)))]
                if pools[g]:
                    members.append(pools[g].pop())
            grades_here = live
        else:
            g = max(live, key=lambda g: len(pools[g]))
            members = [pools[g].pop() for _ in range(min(size, len(pools[g])))]
            grades_here = [g]
        if len(members) < lo and any(g in last_of_grade for g in grades_here):
            # fold a small remainder into the last group that already holds this grade
            target = last_of_grade[next(g for g in grades_here if g in last_of_grade)]
            groups[target].extend(members)
        else:
            groups.append(members)
            for g in grades_here:
                last_of_grade[g] = len(groups) - 1
    return groups


def _sample_friends(rng, grade, pop, K, within_bias, p_recip, mu=0.0, group_pool=None):
    n = len(grade)
    friends: list[set[int]] = [set() for _ in range(n)]
    order: list[list[int]] = [[] for _ in range(n)]   # preference order
    for i in rng.permutation(n):
        need = K - len(friends[i])
        if need <= 0:
            continue
        w = pop * np.where(grade == grade[i], within_bias, 1.0)
        w[i] = 0.0
        for j in friends[i]:
            w[j] = 0.0
        picks = []
        rest = need
        if mu > 0 and group_pool is not None:
            cands = [j for j in group_pool[i] if j not in friends[i]]
            for j in group_pool[i]:
                w[j] = 0.0          # background draws exclude own group(s): in-group share == mu
            n_group = int(np.sum(rng.random(need) < mu))
            take = min(n_group, len(cands))
            if take:
                wg = pop[cands]
                chosen = rng.choice(len(cands), size=take, replace=False, p=wg / wg.sum())
                picks.extend(cands[c] for c in chosen)
                for j in picks:
                    w[j] = 0.0
            # mu = 1 means fully isolated groups: a small group simply yields fewer
            # friends.  Below 1, an exhausted group pool falls back to background.
            rest = need - take if mu < 1.0 else need - n_group
        if rest > 0:
            w = w / w.sum()
            picks.extend(int(j) for j in rng.choice(n, size=rest, replace=False, p=w))
        for j in picks:
            j = int(j)
            friends[i].add(j)
            order[i].append(j)
            if rng.random() < p_recip and len(friends[j]) < K and i not in friends[j]:
                friends[j].add(i)
                order[j].append(i)
    return friends, order


def make_cohort(seed: int = 7, n11: int = N11_DEFAULT, n12: int = N12_DEFAULT,
                K: int = K_DEFAULT, within_bias: float = 9.0, sigma: float = 0.6,
                target_reciprocity: float = 0.5, clique_size: int = 6,
                mu: float = 0.0, omega: float = 0.0, group_size_dist=(6, 12),
                cross_grade_group_frac: float = 0.0) -> Network:
    """Deterministic synthetic cohort with latent friend groups.

    mu     probability that a true friendship is drawn from the student's
           group(s) rather than the background (grade-biased) distribution
    omega  probability that a student also joins one secondary group
    The reciprocation probability is calibrated (deterministically, on the same
    seed) so that the measured reciprocity lands near ``target_reciprocity``.
    A ``clique`` of ``clique_size`` mid-popularity juniors who are mutual true
    friends is planted; the coalition scenarios use these six students.
    """
    n = n11 + n12
    grade = np.array([11] * n11 + [12] * n12)
    rng0 = np.random.default_rng(seed)
    pop = rng0.lognormal(mean=0.0, sigma=sigma, size=n)

    groups, primary, secondary, group_pool = [], [], [], None
    if mu > 0 or omega > 0:
        rng_g = np.random.default_rng([seed, 4])
        groups = _make_groups(rng_g, grade, group_size_dist, cross_grade_group_frac)
        primary = [0] * n
        for gi, members in enumerate(groups):
            for m in members:
                primary[m] = gi
        secondary = [None] * n
        for i in range(n):
            if len(groups) > 1 and rng_g.random() < omega:
                others = [gi for gi in range(len(groups)) if gi != primary[i]]
                secondary[i] = others[int(rng_g.integers(len(others)))]
        group_pool = []
        for i in range(n):
            pool = set(groups[primary[i]])
            if secondary[i] is not None:
                pool |= set(groups[secondary[i]])
            pool.discard(i)
            group_pool.append(sorted(pool))

    best = None
    for p in np.linspace(0.25, 0.75, 11):
        rng = np.random.default_rng([seed, 1])
        friends, order = _sample_friends(rng, grade, pop, K, within_bias, float(p), mu=mu, group_pool=group_pool)
        r = _measure_reciprocity(friends)
        if best is None or abs(r - target_reciprocity) < abs(best[0] - target_reciprocity):
            best = (r, friends, order, float(p))
    r, friends, order, p = best

    # Plant a clique of mid-popularity juniors (mutual true friends).  They keep
    # their K - (clique_size - 1) most preferred outside friends.
    rng_c = np.random.default_rng([seed, 2])
    juniors = np.arange(n11)
    if groups:
        # a real friend group: the junior latent group nearest median popularity
        med = float(np.median(pop[juniors]))
        jgroups = [g for g in groups if len(g) >= clique_size and all(grade[m] == 11 for m in g)]
        g = min(jgroups, key=lambda g: abs(float(np.median(pop[g])) - med))
        clique = sorted(sorted(g, key=lambda m: abs(pop[m] - med))[:clique_size])
    else:
        ranks = np.argsort(np.argsort(pop[juniors]))
        mid = juniors[(ranks > n11 * 0.35) & (ranks < n11 * 0.65)]
        clique = sorted(int(x) for x in rng_c.choice(mid, size=clique_size, replace=False))
    for a in clique:
        others = [b for b in clique if b != a]
        keep = [j for j in order[a] if j not in clique][: K - len(others)]
        order[a] = others + keep
        friends[a] = set(order[a])
    # Preference order is the sampling order; dedupe defensively.
    ordered = []
    for i in range(n):
        seen, lst = set(), []
        for j in order[i]:
            if j not in seen and j in friends[i]:
                seen.add(j)
                lst.append(j)
        ordered.append(lst)
    return Network(n11=n11, n12=n12, grade=grade, popularity=pop, friends=ordered,
                   seed=seed, reciprocity=_measure_reciprocity([set(f) for f in ordered]),
                   clique=clique, mu=mu, omega=omega, groups=groups, primary=primary, secondary=secondary)


def generate_network(*args, **kwargs) -> Network:
    """Backward-compatible alias for make_cohort."""
    return make_cohort(*args, **kwargs)


def apply_rules(lst: list[int], me: int, net: Network, rng, enforce_min4: bool = True) -> list[int]:
    """Filter / pad a submitted list so it obeys the submission rules.

    * min-4-or-none: fewer than 4 names -> treated as no submission (empty list)
    * >= 2 same-grade names: pad with same-grade acquaintances (popularity
      weighted) so the guarantee is satisfiable during same-grade rotations.
    """
    lst = [j for j in dict.fromkeys(lst) if j != me]
    if not enforce_min4:
        return lst
    if not lst:
        return []
    same = [j for j in lst if net.grade[j] == net.grade[me]]
    if len(same) < MIN_SAME_GRADE:
        pool = [j for j in range(net.n) if net.grade[j] == net.grade[me] and j != me and j not in lst]
        w = net.popularity[pool]
        w = w / w.sum()
        extra = rng.choice(pool, size=MIN_SAME_GRADE - len(same), replace=False, p=w)
        lst = lst + [int(j) for j in extra]
    if len(lst) < MIN_LIST:
        pool = [j for j in range(net.n) if j != me and j not in lst]
        w = net.popularity[pool] * np.where(net.grade[pool] == net.grade[me], 9.0, 1.0)
        w = w / w.sum()
        extra = rng.choice(pool, size=MIN_LIST - len(lst), replace=False, p=w)
        lst = lst + [int(j) for j in extra]
    return lst


def honest_lists(net: Network, seed: int = 0, nonsubmit_frac: float = 0.0) -> list[list[int]]:
    """Every student submits their true friends (padded/filtered per the rules)."""
    rng = np.random.default_rng([net.seed, 3, seed])
    out = []
    for i in range(net.n):
        if nonsubmit_frac > 0 and rng.random() < nonsubmit_frac:
            out.append([])
            continue
        out.append(apply_rules(list(net.friends[i]), i, net, rng))
    return out


def coalition_lists(net: Network, mode: str, base: list[list[int]] | None = None) -> list[list[int]]:
    """Replace the clique's submissions with an adversarial wiring.

    mode = 'k1'   : each member lists ONLY the next member (a 6-cycle).  Every
                    member's single listed peer must be at their table, so the
                    hard guarantee drags the whole cycle onto one table.
    mode = 'min4' : each member lists 4 of the 5 co-members.  The omitted names
                    form two 3-cycles, the wiring that leaves the most
                    penalty-free triples for the solver to (maybe) keep together.
    """
    base = [list(l) for l in (base if base is not None else honest_lists(net))]
    c = net.clique
    m = len(c)
    if mode == "k1":
        for k, a in enumerate(c):
            base[a] = [c[(k + 1) % m]]
    elif mode == "min4":
        half = m // 2
        for k, a in enumerate(c):
            grp = k // half
            pos = k % half
            omitted = c[grp * half + (pos + 1) % half]
            base[a] = [b for b in c if b != a and b != omitted]
    else:
        raise ValueError(mode)
    return base
