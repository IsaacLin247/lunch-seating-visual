"""Seating solver for one rotation.

Pipeline (Tab 4 of the site states the same equations):
    Stage 1 pods  ->  Stage 2 swap repair  ->  Stage 3 annealing  ->  Stage 4 CP-SAT (hinted)

Hard constraint: every submitter sits with >= 1 listed peer (same-grade listed
peers only during same-grade rotations).

Stage 3 energy (maximised; s_i = listed peers at i's table; m_ab = past
co-seatings of the pair while it was *not* a listed pair, alpha_ab = past
co-seatings while one of the two listed the other):

    E = sum_i ( 1000 * 1[s_i >= 1] - max(0, s_i - 1) )
        - (1/10) * sum_{(a,b) co-seated} ( 5 m_ab + 2 alpha_ab )

so an incidental repeat costs 5 per prior meeting and a listed-friend repeat 2,
the policy stated in the mechanism ("incidental repeats cost more than anchor
repeats").  Metropolis acceptance P(accept dE < 0) = exp(dE / T), T geometric
2.5 -> 0.02.  The code minimises C = -E (plus a constant) with every term
scaled by 10 so bookkeeping stays in integers; the temperature is scaled by the
same factor, so acceptance probabilities are identical.

Stage 4 objective: minimise 300 * sum z_i + sum w_ab r_ab over pairs seated
together in the previous rotation, w_ab = 100 (5 m_ab + 2 alpha_ab).

Invariants maintained by the local-search stages (checked by tests):
  * State tracks the number of friendless submitters; every candidate move
    (single swap, closure swap, padded closure swap, compound kick) is rejected
    if it would increase that number, so once an assignment is feasible the
    search never leaves the feasible region.
  * Repair accepts a swap only if the set of friendless submitters strictly
    shrinks (nobody previously satisfied is stranded).
  * A submitter whose effective list is empty makes the rotation infeasible and
    is reported as InfeasibleInputError before any search runs; CP-SAT never
    silently drops such a student.
"""
from __future__ import annotations

import math
import random
import time

from ortools.sat.python import cp_model

SCALE = 10                      # integer scaling of the Stage 3 energy
VIOL = 1000 * SCALE             # 1000 per friendless submitter
W_EXTRA = 1 * SCALE             # 1 per listed peer beyond the first
W_M = 5                         # (1/10) * 5 m_ab, scaled by 10   (incidental repeats)
W_ALPHA = 2                     # (1/10) * 2 alpha_ab, scaled by 10 (listed-pair repeats)
T0 = 2.5 * SCALE
T1 = 0.02 * SCALE
W_2PLUS_CPSAT = 300             # Stage 4: per student with >= 2 listed peers
CPSAT_REPEAT_SCALE = 100        # Stage 4: w_ab = 100 (5 m_ab + 2 alpha_ab)
CLOSURE_CAP = 7                 # largest movable group (one table)


class InfeasibleInputError(ValueError):
    """The submitted lists cannot all be satisfied in this rotation."""


def table_layout(state: str, n11: int = 132, n12: int = 125, n_tables: int = 40):
    """Capacities and per-table grade restriction for one rotation.

    With n_tables tables seating 6 or 7 and every seat filled, the number of
    seven-seat tables is n7 = N - 6*n_tables, which must lie in [0, n_tables]
    (240 <= N <= 280 for 40 tables).  Seven-seat tables come first.  In a
    same-grade rotation the juniors take the largest feasible number x7 of
    seven-seat tables with 7*x7 + 6*x6 = n11; the seniors get the rest.  Table
    order is junior sevens, senior sevens, junior sixes, senior sixes, so the
    room splits into two halves in the visualisation.  For the default cohort
    (132/125) this gives 12x7 + 8x6 and 5x7 + 15x6.
    """
    N = n11 + n12
    n7 = N - 6 * n_tables
    if not 0 <= n7 <= n_tables:
        raise ValueError(f"{N} students cannot fill {n_tables} tables of 6 or 7 seats exactly")
    n6 = n_tables - n7
    caps = [7] * n7 + [6] * n6
    if state == "mixed":
        return caps, [None] * n_tables
    if state != "same":
        raise ValueError(state)
    split = None
    for x7 in range(min(n7, n11 // 7), -1, -1):
        rest = n11 - 7 * x7
        if rest % 6 == 0 and rest // 6 <= n6:
            split = (x7, rest // 6)
            break
    if split is None:
        raise ValueError(f"no grade partition of {n7}x7 + {n6}x6 tables seats exactly {n11} and {n12} students")
    x7, x6 = split
    tg = [11] * x7 + [12] * (n7 - x7) + [11] * x6 + [12] * (n6 - x6)
    assert sum(c for c, g in zip(caps, tg) if g == 11) == n11
    assert sum(c for c, g in zip(caps, tg) if g == 12) == n12
    return caps, tg


class Problem:
    """One rotation's data with fast lookups for the local-search phases.

    history_m[a][b]     past co-seatings of (a,b) while neither listed the other
    history_alpha[a][b] past co-seatings while one of them listed the other
    If history_alpha is None, history_m is taken as *all* past co-seatings and
    split by today's listed relation (identical when lists never change).
    """

    def __init__(self, grade, lists, caps, table_grade, history_m, state, prev_tables=None,
                 history_alpha=None):
        self.n = len(grade)
        self.T = len(caps)
        self.grade = list(grade)
        self.caps = list(caps)
        self.table_grade = list(table_grade)
        self.state = state
        self.lists = [list(l) for l in lists]
        self.submitter = [len(l) > 0 for l in lists]
        if state == "same":
            self.adj = [set(j for j in lists[i] if grade[j] == grade[i]) for i in range(self.n)]
        else:
            self.adj = [set(lists[i]) for i in range(self.n)]
        self.ineligible = [i for i in range(self.n) if self.submitter[i] and not self.adj[i]]
        # listed-pair relation (either direction, full lists)
        self.listed = [set(l) for l in lists]
        for i in range(self.n):
            for j in lists[i]:
                self.listed[j].add(i)
        n = self.n
        W = [[0] * n for _ in range(n)]
        for a in range(n):
            hm = history_m[a]
            ha = history_alpha[a] if history_alpha is not None else None
            la = self.listed[a]
            Wa = W[a]
            for b in range(a + 1, n):
                if ha is None:
                    m = hm[b]
                    w = (W_ALPHA if b in la else W_M) * m
                else:
                    w = W_M * hm[b] + W_ALPHA * ha[b]
                if w:
                    Wa[b] = w
                    W[b][a] = w
        self.W = W
        self.prev_tables = prev_tables
        self.pen = []
        for i in range(n):
            row = [W_EXTRA * max(0, c - 1) for c in range(self.n + 1)]
            row[0] = VIOL if self.submitter[i] else 0
            self.pen.append(row)
        self.allowed = [[t for t in range(self.T) if table_grade[t] is None or table_grade[t] == grade[i]]
                        for i in range(self.n)]
        self.students_by_grade = {}
        for i in range(n):
            self.students_by_grade.setdefault(grade[i], []).append(i)

    # ----- evaluation helpers -------------------------------------------------
    def members_of(self, assign):
        members = [[] for _ in range(self.T)]
        for i, t in enumerate(assign):
            members[t].append(i)
        return members

    def counts(self, assign, members=None):
        members = members or self.members_of(assign)
        cnt = [0] * self.n
        for ms in members:
            for i in ms:
                cnt[i] = sum(1 for j in ms if j in self.adj[i])
        return cnt

    def cost_breakdown(self, assign):
        members = self.members_of(assign)
        cnt = self.counts(assign, members)
        viol = sum(1 for i in range(self.n) if self.submitter[i] and cnt[i] == 0)
        two = sum(1 for i in range(self.n) if cnt[i] >= 2)
        extra = sum(max(0, c - 1) for c in cnt)
        rep = 0
        for ms in members:
            for x in range(len(ms)):
                Wa = self.W[ms[x]]
                for y in range(x + 1, len(ms)):
                    rep += Wa[ms[y]]
        return {"violations": viol, "twoPlus": two, "extraPeers": extra, "repeat": rep,
                "total": VIOL * viol + W_EXTRA * extra + rep}

    def check(self, assign):
        members = self.members_of(assign)
        for t in range(self.T):
            assert len(members[t]) == self.caps[t], f"table {t} has {len(members[t])} != {self.caps[t]}"
            if self.table_grade[t] is not None:
                assert all(self.grade[i] == self.table_grade[t] for i in members[t]), f"table {t} mixed grades"
        cnt = self.counts(assign, members)
        return [i for i in range(self.n) if self.submitter[i] and cnt[i] == 0]


# ----- phase 1: pod greedy -------------------------------------------------------
def pod_greedy(p: Problem, rng: random.Random):
    """Constructive start: pair students with a listed peer (mutual pairs first),
    then merge pods until every submitter has a listed peer inside their own pod
    (students with the fewest options go first, so one-directional chains
    a->b->c->... assemble before anyone else claims their seats), then place
    pods on tables largest-first, spreading them to avoid extra list overlap."""
    n = p.n
    unmatched = set(range(n))
    pods = []
    order = sorted(range(n), key=lambda i: (len(p.adj[i]) if p.submitter[i] else 99, rng.random()))
    for i in order:
        if i not in unmatched or not p.submitter[i]:
            continue
        cands = [j for j in p.adj[i] if j in unmatched and (i in p.adj[j] or len(p.adj[j]) >= len(p.adj[i]))]
        if cands:
            j = min(cands, key=lambda j: (0 if i in p.adj[j] else 1, p.W[i][j], len(p.adj[j]), rng.random()))
            pods.append([i, j])
            unmatched.discard(i)
            unmatched.discard(j)
    for i in sorted(unmatched):
        pods.append([i])
    pod_of = {}
    for k, pod in enumerate(pods):
        for m in pod:
            pod_of[m] = k

    max_pod = min(p.caps)
    changed = True
    while changed:
        changed = False
        needy = [m for m in range(n) if p.submitter[m] and p.adj[m]
                 and not any(j in p.adj[m] for j in pods[pod_of[m]])]
        needy.sort(key=lambda m: (len(p.adj[m]), rng.random()))
        for m in needy:
            k = pod_of[m]
            pod = pods[k]
            if any(j in p.adj[m] for j in pod):
                continue
            best = None
            for j in p.adj[m]:
                q = pod_of[j]
                if q == k or len(pods[q]) + len(pod) > max_pod:
                    continue
                other = pods[q]
                extra = sum(1 for x in pod for y in other if (y in p.adj[x] or x in p.adj[y])) - 1
                hist = sum(p.W[x][y] for x in pod for y in other)
                key = (W_EXTRA * max(extra, 0) + hist, len(other), rng.random())
                if best is None or key < best[0]:
                    best = (key, q)
            if best is None:
                continue
            q = best[1]
            for x in pods[q]:
                pod_of[x] = k
            pod.extend(pods[q])
            pods[q] = []
            changed = True
    pods = [pod for pod in pods if pod]

    assign = [-1] * n
    members = [[] for _ in range(p.T)]
    remaining = list(p.caps)
    pods.sort(key=lambda pod: (-len(pod), rng.random()))
    leftovers = []
    for pod in pods:
        g = p.grade[pod[0]]
        best = None
        for t in range(p.T):
            if remaining[t] < len(pod) or (p.table_grade[t] is not None and p.table_grade[t] != g):
                continue
            c = 0
            for m in pod:
                for o in members[t]:
                    c += p.W[m][o]
                    if o in p.adj[m] or m in p.adj[o]:
                        c += W_EXTRA
            key = (c, -remaining[t], rng.random())
            if best is None or key < best[0]:
                best = (key, t)
        if best is None:
            leftovers.extend(pod)
            continue
        t = best[1]
        for m in pod:
            assign[m] = t
            members[t].append(m)
        remaining[t] -= len(pod)
    for m in leftovers:
        for t in range(p.T):
            if remaining[t] > 0 and (p.table_grade[t] is None or p.table_grade[t] == p.grade[m]):
                assign[m] = t
                members[t].append(m)
                remaining[t] -= 1
                break
    assert all(a >= 0 for a in assign) and all(r == 0 for r in remaining)
    return assign


# ----- local-search state ------------------------------------------------------
class State:
    """Assignment plus per-table cached cost and friendless-submitter count.

    Moves are group swaps: a set Ga at table ta trades places with an equally
    sized set Gb at table tb.  Every move reports the change in the number of
    friendless submitters; callers reject moves that would increase it.
    """

    def __init__(self, p: Problem, assign):
        self.p = p
        self.assign = list(assign)
        self.members = p.members_of(assign)
        stats = [self.table_stats(ms) for ms in self.members]
        self.tcost = [c for c, _ in stats]
        self.tviol = [v for _, v in stats]
        self.cost = sum(self.tcost)
        self.viol = sum(self.tviol)

    def table_stats(self, ms):
        """(cost, number of friendless submitters) of a table."""
        p = self.p
        adj, W, pen, sub = p.adj, p.W, p.pen, p.submitter
        c = 0
        v = 0
        L = len(ms)
        for idx in range(L):
            x = ms[idx]
            ax = adj[x]
            k = 0
            for y in ms:
                if y in ax:
                    k += 1
            c += pen[x][k]
            if k == 0 and sub[x]:
                v += 1
            Wx = W[x]
            for j in range(idx + 1, L):
                c += Wx[ms[j]]
        return c, v

    def table_cost(self, ms):
        return self.table_stats(ms)[0]

    def cnt(self, x):
        ax = self.p.adj[x]
        return sum(1 for y in self.members[self.assign[x]] if y in ax)

    def counts(self):
        return [self.cnt(i) for i in range(self.p.n)]

    def violated(self):
        p = self.p
        return {i for i in range(p.n) if p.submitter[i] and self.cnt(i) == 0}

    # ----- closures ---------------------------------------------------------
    def close_set(self, G, t, rng, cap=CLOSURE_CAP):
        """Smallest superset of G (within table t) that orphans nobody who stays
        and keeps every mover anchored inside the group when possible."""
        p = self.p
        ms = self.members[t]
        G = set(G)
        changed = True
        while changed and len(G) <= cap:
            changed = False
            for x in ms:
                if x in G or not p.submitter[x]:
                    continue
                ax = p.adj[x]
                if any(y in ax for y in ms if y not in G):
                    continue
                if any(y in ax for y in ms):
                    G.add(x)
                    changed = True
            for g in list(G):
                if not p.submitter[g]:
                    continue
                ag = p.adj[g]
                if any(y in ag for y in G):
                    continue
                anchors = [y for y in ms if y in ag and y not in G]
                if anchors:
                    G.add(anchors[rng.randrange(len(anchors))])
                    changed = True
        if len(G) > cap:
            return None
        return G

    def closure(self, a, rng, cap=CLOSURE_CAP):
        return self.close_set({a}, self.assign[a], rng, cap)

    # ----- moves --------------------------------------------------------------
    def delta_group_swap(self, Ga, Gb):
        ta = self.assign[next(iter(Ga))]
        tb = self.assign[next(iter(Gb))]
        new_a = [x for x in self.members[ta] if x not in Ga] + list(Gb)
        new_b = [x for x in self.members[tb] if x not in Gb] + list(Ga)
        ca, va = self.table_stats(new_a)
        cb, vb = self.table_stats(new_b)
        d = ca + cb - self.tcost[ta] - self.tcost[tb]
        dv = va + vb - self.tviol[ta] - self.tviol[tb]
        return d, dv, (ta, tb, new_a, new_b, ca, cb, va, vb)

    def apply_group_swap(self, d, dv, payload):
        ta, tb, new_a, new_b, ca, cb, va, vb = payload
        self.members[ta] = new_a
        self.members[tb] = new_b
        for x in new_a:
            self.assign[x] = ta
        for x in new_b:
            self.assign[x] = tb
        self.tcost[ta] = ca
        self.tcost[tb] = cb
        self.tviol[ta] = va
        self.tviol[tb] = vb
        self.cost += d
        self.viol += dv

    def delta_swap(self, a, b):
        return self.delta_group_swap({a}, {b})

    def snapshot(self):
        return (list(self.assign), [list(m) for m in self.members], list(self.tcost), list(self.tviol),
                self.cost, self.viol)

    def restore(self, snap):
        """Restore in place: callers may hold aliases to these lists."""
        assign, members, tcost, tviol, cost, viol = snap
        self.assign[:] = assign
        for t in range(len(self.members)):
            self.members[t] = members[t]
        self.tcost[:] = tcost
        self.tviol[:] = tviol
        self.cost = cost
        self.viol = viol


def _friendless_after(st: State, payload):
    """Friendless submitters at the two affected tables after a proposed swap."""
    p = st.p
    _, _, new_a, new_b, *_ = payload
    out = set()
    for ms in (new_a, new_b):
        for x in ms:
            if p.submitter[x] and not any(y in p.adj[x] for y in ms):
                out.add(x)
    return out


def _friendless_before(st: State, ta, tb):
    p = st.p
    out = set()
    for t in (ta, tb):
        ms = st.members[t]
        for x in ms:
            if p.submitter[x] and not any(y in p.adj[x] for y in ms):
                out.add(x)
    return out


def best_rescue_swap(st: State, i: int):
    """Best single swap that gives friendless submitter i an anchor without
    stranding anyone who is currently satisfied, or None."""
    p = st.p
    ti = st.assign[i]
    best = None
    for j in p.adj[i]:
        tj = st.assign[j]
        if tj == ti:
            continue
        before = _friendless_before(st, ti, tj)
        for x in st.members[tj]:
            if x == j:
                continue
            d, dv, payload = st.delta_swap(i, x)
            after = _friendless_after(st, payload)
            if i in after or not after <= before:
                continue
            if best is None or d < best[0]:
                best = (d, dv, payload)
    return best


# ----- compound move --------------------------------------------------------------
def kick_and_repair(st: State, i: int, j: int, rng: random.Random) -> bool:
    """Force closure(i) onto listed peer j's table, evict an equally sized set of
    j's tablemates to i's old table, then re-seat anyone left friendless with
    rescue swaps.  Kept only if the total cost went down and no student who
    was satisfied before is friendless afterwards; otherwise fully undone."""
    p = st.p
    snap = st.snapshot()
    before = st.violated()
    ti, tj = st.assign[i], st.assign[j]
    if ti == tj:
        return False
    Gi = st.closure(i, rng)
    Gj = st.closure(j, rng)
    if Gi is None or Gj is None:
        return False
    cands = [x for x in st.members[tj] if x not in Gj]
    if len(cands) < len(Gi):
        return False
    rng.shuffle(cands)
    cands.sort(key=lambda x: -len(p.adj[x]))
    Gout = set(cands[:len(Gi)])
    d, dv, payload = st.delta_group_swap(Gi, Gout)
    st.apply_group_swap(d, dv, payload)
    for x in list(Gout) + [m for m in st.members[ti] if m not in Gout]:
        if not p.submitter[x] or st.cnt(x) > 0:
            continue
        best = best_rescue_swap(st, x)
        if best is not None:
            st.apply_group_swap(*best)
    if st.cost < snap[4] and st.violated() <= before:
        return True
    st.restore(snap)
    return False


# ----- phase 2: swap repair -----------------------------------------------------
def swap_repair(st: State, rng: random.Random, max_rounds: int = 20):
    """Give every friendless submitter an anchor.  A swap is accepted only if
    the set of friendless submitters strictly shrinks: the rescued student is
    satisfied afterwards and nobody who was satisfied is stranded."""
    p = st.p
    for _ in range(max_rounds):
        unsat = [i for i in range(p.n) if p.submitter[i] and st.cnt(i) == 0]
        if not unsat:
            return True
        rng.shuffle(unsat)
        progress = False
        for i in unsat:
            if st.cnt(i) > 0:
                continue
            best = best_rescue_swap(st, i)
            if best is not None:
                st.apply_group_swap(*best)
                progress = True
            else:
                peers = list(p.adj[i])
                rng.shuffle(peers)
                for j in peers:
                    if kick_and_repair(st, i, j, rng):
                        progress = True
                        break
        if not progress:
            break
    return st.viol == 0


# ----- phase 3: simulated annealing ----------------------------------------------
def anneal(st: State, rng: random.Random, iters: int = 300_000, t0: float = T0, t1: float = T1):
    """Stage 3: group-swap Metropolis annealing on the full-history energy.

    Move mix per iteration:
      * closure group swap (default): Ga = closure(a), Gb = closure(b); the
        smaller group is padded with random tablemates and re-closed
      * raw single swap {a} <-> {b}
      * peer-directed single swap: b is drawn from the table of one of a's
        listed peers, so students are often proposed next to a friend
      * targeted repair while anyone is friendless: a is a friendless
        submitter and b sits at one of a's listed peers' tables
    Any move that would increase the number of friendless submitters is
    rejected outright, so a feasible assignment never becomes infeasible.
    Returns (best_assign, best_cost, best_viol) with best = lexicographic
    (violations, cost).
    """
    p = st.p
    n = p.n
    if p.state == "same":
        pools = {g: list(v) for g, v in p.students_by_grade.items()}
    else:
        pools = {None: list(range(n))}
    pool_of = {}
    for g, v in pools.items():
        for i in v:
            pool_of[i] = v
    adj_list = [list(a) for a in p.adj]
    submitters = [i for i in range(n) if p.submitter[i] and p.adj[i]]
    assign = st.assign
    members = st.members
    best_key = (st.viol, st.cost)
    best_assign = list(assign)
    log_ratio = math.log(t1 / t0)
    rnd = rng.random
    randrange = rng.randrange
    exp = math.exp
    for k in range(iters):
        T = t0 * exp(log_ratio * k / iters)
        u = rnd()
        group = True
        if st.viol > 0 and submitters and k % 8 == 0:
            a = submitters[randrange(len(submitters))]
            if st.cnt(a) > 0:
                continue
            peers = adj_list[a]
            j = peers[randrange(len(peers))]
            if k % 64 == 0:
                if kick_and_repair(st, a, j, rng) and (st.viol, st.cost) < best_key:
                    best_key = (st.viol, st.cost)
                    best_assign = list(assign)
                continue
            mb = members[assign[j]]
            b = mb[randrange(len(mb))]
            if b == j:
                continue
            group = rnd() < 0.5
        elif u < 0.25:
            a = randrange(n)
            pool = pool_of[a]
            b = pool[randrange(len(pool))]
            group = False
        elif u < 0.5:
            a = randrange(n)
            peers = adj_list[a]
            if not peers:
                continue
            j = peers[randrange(len(peers))]
            mb = members[assign[j]]
            b = mb[randrange(len(mb))]
            if b == j:
                continue
            group = False
        else:
            a = randrange(n)
            pool = pool_of[a]
            b = pool[randrange(len(pool))]
        ta, tb = assign[a], assign[b]
        if ta == tb:
            continue
        if not group:
            Ga, Gb = {a}, {b}
        else:
            Ga = st.closure(a, rng)
            if Ga is None:
                continue
            Gb = st.closure(b, rng)
            if Gb is None:
                continue
            # pad the smaller group with random tablemates and re-close it
            tries = 0
            while len(Ga) != len(Gb) and tries < 4:
                tries += 1
                if len(Gb) < len(Ga):
                    mb = members[tb]
                    Gb = st.close_set(Gb | {mb[randrange(len(mb))]}, tb, rng)
                    if Gb is None:
                        break
                else:
                    ma = members[ta]
                    Ga = st.close_set(Ga | {ma[randrange(len(ma))]}, ta, rng)
                    if Ga is None:
                        break
            if Ga is None or Gb is None or len(Ga) != len(Gb):
                continue
        d, dv, payload = st.delta_group_swap(Ga, Gb)
        if dv > 0:
            continue
        if d <= 0 or rnd() < exp(-d / T):
            st.apply_group_swap(d, dv, payload)
            if (st.viol, st.cost) < best_key:
                best_key = (st.viol, st.cost)
                best_assign = list(assign)
    return best_assign, best_key[1], best_key[0]


# ----- phase 4: CP-SAT --------------------------------------------------------------
def _cpsat_solver(time_limit, workers, seed, deterministic, log=False):
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = workers
    solver.parameters.random_seed = seed
    solver.parameters.log_search_progress = log
    if deterministic:
        solver.parameters.interleave_search = True
        solver.parameters.max_deterministic_time = time_limit
    else:
        solver.parameters.max_time_in_seconds = time_limit
    return solver


def _base_model(p: Problem):
    """Assignment variables, capacities and the hard anchor constraints."""
    if p.ineligible:
        raise InfeasibleInputError(
            f"{len(p.ineligible)} submitter(s) have no eligible listed peer in this rotation: {p.ineligible[:10]}")
    n, T = p.n, p.T
    model = cp_model.CpModel()
    x = {}
    for i in range(n):
        for t in p.allowed[i]:
            x[i, t] = model.NewBoolVar(f"x{i}_{t}")
    at_table = [[] for _ in range(T)]
    for (i, t), v in x.items():
        at_table[t].append(v)
    for i in range(n):
        model.AddExactlyOne(x[i, t] for t in p.allowed[i])
    for t in range(T):
        model.Add(sum(at_table[t]) == p.caps[t])
    y1 = {}
    for i in range(n):
        if not p.submitter[i]:
            continue
        L = list(p.adj[i])
        ys = []
        for t in p.allowed[i]:
            S = sum(x[j, t] for j in L if (j, t) in x)
            y = model.NewBoolVar(f"y{i}_{t}")
            model.AddImplication(y, x[i, t])
            model.Add(S >= y)
            y1[i, t] = y
            ys.append(y)
        model.Add(sum(ys) >= 1)
    return model, x, y1


def feasibility_certificate(p: Problem, time_limit: float = 20.0, workers: int = 8, seed: int = 0,
                            deterministic: bool = True):
    """CP-SAT on the hard constraints only.  Returns (status, assign or None).

    OPTIMAL/FEASIBLE certifies feasibility with a witness; INFEASIBLE certifies
    that no seating satisfies every submitter; UNKNOWN means the budget expired."""
    model, x, _ = _base_model(p)
    solver = _cpsat_solver(time_limit, workers, seed, deterministic)
    status = solver.Solve(model)
    name = solver.StatusName(status)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        assign = [-1] * p.n
        for (i, t), v in x.items():
            if solver.Value(v):
                assign[i] = t
        return name, assign
    return name, None


def cpsat_polish(p: Problem, hint_assign, time_limit: float = 3.5, workers: int = 8,
                 seed: int = 0, deterministic: bool = True, log: bool = False):
    """Stage 4: exact model with the Stage 3 assignment as a complete hint."""
    model, x, y1 = _base_model(p)
    n = p.n
    obj = []
    z2 = {}
    for i in range(n):
        L = list(p.adj[i])
        nL = len(L)
        if nL < 2:
            continue
        z2[i] = model.NewBoolVar(f"z{i}")
        obj.append(W_2PLUS_CPSAT * z2[i])
        for t in p.allowed[i]:
            S = sum(x[j, t] for j in L if (j, t) in x)
            # x_it = 1 and S >= 2  =>  z_i = 1
            model.Add(S <= 1 + (nL - 1) * z2[i] + nL * (1 - x[i, t]))
    r = {}
    if p.prev_tables is not None:
        for tbl in p.prev_tables:
            for ai in range(len(tbl)):
                for bi in range(ai + 1, len(tbl)):
                    a, b = tbl[ai], tbl[bi]
                    w = p.W[a][b]
                    if w == 0:
                        continue
                    if a > b:
                        a, b = b, a
                    rv = model.NewBoolVar(f"r{a}_{b}")
                    for t in p.allowed[a]:
                        if (b, t) in x:
                            model.AddBoolOr([rv, x[a, t].Not(), x[b, t].Not()])
                    r[a, b] = rv
                    obj.append(CPSAT_REPEAT_SCALE * w * rv)
    model.Minimize(sum(obj))

    members = p.members_of(hint_assign)
    cnt = p.counts(hint_assign, members)
    for (i, t), v in x.items():
        model.AddHint(v, int(hint_assign[i] == t))
    for (i, t), v in y1.items():
        model.AddHint(v, int(hint_assign[i] == t and cnt[i] >= 1))
    for i, v in z2.items():
        model.AddHint(v, int(cnt[i] >= 2))
    for (a, b), v in r.items():
        model.AddHint(v, int(hint_assign[a] == hint_assign[b]))

    solver = _cpsat_solver(time_limit, workers, seed, deterministic, log)
    status = solver.Solve(model)
    info = {"status": solver.StatusName(status), "objective": None, "bound": None,
            "vars": len(model.Proto().variables), "constraints": len(model.Proto().constraints)}
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        info["objective"] = solver.ObjectiveValue()
        info["bound"] = solver.BestObjectiveBound()
        assign = [-1] * n
        for (i, t), v in x.items():
            if solver.Value(v):
                assign[i] = t
        return assign, info
    return None, info


# ----- the pipeline -------------------------------------------------------------------
def solve_rotation(p: Problem, seed: int = 0, anneal_iters: int = 300_000, cpsat_time: float = 3.5,
                   workers: int = 8, deterministic: bool = True, log=None):
    """Run the whole pipeline; returns (assign, info).

    Raises InfeasibleInputError if a submitter has no eligible listed peer, and
    RuntimeError if no stage produced a seating satisfying every submitter
    (the caller decides how to report that; nothing invalid is ever returned)."""
    if p.ineligible:
        raise InfeasibleInputError(
            f"{len(p.ineligible)} submitter(s) have no eligible listed peer in this rotation: {p.ineligible[:10]}")
    rng = random.Random(seed)
    t_start = time.perf_counter()
    info = {"snapshots": {}}

    assign = pod_greedy(p, rng)
    st = State(p, assign)
    info["greedy"] = p.cost_breakdown(assign)
    info["snapshots"]["greedy"] = list(assign)
    t1 = time.perf_counter()

    swap_repair(st, rng)
    info["repair"] = p.cost_breakdown(st.assign)
    info["snapshots"]["repair"] = list(st.assign)
    t2 = time.perf_counter()

    best_assign, best_cost, best_viol = anneal(st, rng, iters=anneal_iters)
    for attempt in range(6):
        if best_viol == 0:
            break
        st = State(p, best_assign)
        swap_repair(st, rng)
        best_assign, best_cost, best_viol = anneal(st, rng, iters=max(anneal_iters // 2, 20_000))
        info["annealRetries"] = attempt + 1
    info["anneal"] = p.cost_breakdown(best_assign)
    info["snapshots"]["anneal"] = list(best_assign)
    t3 = time.perf_counter()

    final = best_assign
    info["accepted"] = "anneal"
    if cpsat_time > 0:
        cp_assign, cp_info = cpsat_polish(p, best_assign, time_limit=cpsat_time, workers=workers,
                                          seed=seed, deterministic=deterministic)
        info["cpsat"] = cp_info
        if cp_assign is not None:
            cb = p.cost_breakdown(cp_assign)
            info["cpsatFull"] = cb
            # keep the CP-SAT seating only if it satisfies everyone and is not
            # worse on the full-history objective (CP-SAT sees only the
            # previous rotation's pairs)
            if cb["violations"] == 0 and cb["total"] <= info["anneal"]["total"]:
                final = cp_assign
                info["accepted"] = "cpsat"
    t4 = time.perf_counter()
    info["final"] = p.cost_breakdown(final)
    t5 = t4
    if info["final"]["violations"]:
        cp_assign, cp_info = cpsat_polish(p, final, time_limit=max(cpsat_time, 1.0) * 6, workers=workers,
                                          seed=seed, deterministic=deterministic)
        info["cpsatFallback"] = cp_info
        if cp_assign is not None and p.cost_breakdown(cp_assign)["violations"] == 0:
            final = cp_assign
            info["final"] = p.cost_breakdown(final)
            info["accepted"] = "cpsat-fallback"
        t5 = time.perf_counter()
    info["time"] = {"greedy": t1 - t_start, "repair": t2 - t1, "anneal": t3 - t2,
                    "cpsat": t4 - t3, "fallback": t5 - t4, "total": t5 - t_start}
    if info["final"]["violations"]:
        raise RuntimeError(f"pipeline left {info['final']['violations']} submitters without a listed peer")
    info["snapshots"]["final"] = list(final)
    if log:
        log(info)
    return final, info


def random_assignment(p: Problem, rng: random.Random):
    """Status-quo baseline: uniformly random seating respecting the state."""
    assign = [-1] * p.n
    slots = []
    for t in range(p.T):
        slots.extend([t] * p.caps[t])
    if p.state == "mixed":
        order = list(range(p.n))
        rng.shuffle(order)
        for i, t in zip(order, slots):
            assign[i] = t
    else:
        for g in p.students_by_grade:
            students = list(p.students_by_grade[g])
            rng.shuffle(students)
            gslots = [t for t in slots if p.table_grade[t] == g]
            for i, t in zip(students, gslots):
                assign[i] = t
    return assign
