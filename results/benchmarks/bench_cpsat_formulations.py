"""Benchmark the exact CP-SAT objective against the historical surrogate at 257 scale.

Runs a partial honest year with the local-search stages, then for a set of
rotations (with growing history) compares CP-SAT formulations on the same
hinted incumbent: wall time, status, model size, independent full-history
score of the returned chart, and whether it improved on the incumbent.
"""
import json, os, sys, time, random
sys.path.insert(0, os.getcwd())
from sim.generator import make_cohort, honest_lists
from sim.solver import Problem, table_layout, pod_greedy, State, swap_repair, anneal, cpsat_polish, solve_rotation
from sim.scenarios import state_for

seed = 7
net = make_cohort(seed=seed)
lists = honest_lists(net)
grade = [int(g) for g in net.grade]
n = net.n
hist_m = [[0]*n for _ in range(n)]
hist_a = [[0]*n for _ in range(n)]
listed = [set(l) for l in lists]
for i in range(n):
    for j in lists[i]:
        listed[j].add(i)
prev = None
rows = []
anneal_iters = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
rotations = int(sys.argv[2]) if len(sys.argv) > 2 else 8
budgets = [3.5]
for r in range(rotations):
    state = state_for(r)
    caps, tg = table_layout(state)
    p = Problem(grade, lists, caps, tg, hist_m, state, prev_tables=prev, history_alpha=hist_a)
    rng = random.Random(seed*1000 + r)
    st = State(p, pod_greedy(p, rng))
    swap_repair(st, rng)
    best, cost, viol = anneal(st, rng, iters=anneal_iters)
    inc = p.cost_breakdown(best)
    row = {"rotation": r+1, "state": state, "incumbent": inc, "historyPairs": sum(1 for a in range(n) for b in range(a+1, n) if p.W[a][b]),
           "prevPairs": sum(len(t)*(len(t)-1)//2 for t in prev) if prev else 0, "formulations": {}}
    for name, kw in (("exact", dict(pairs="all", extras="count")), ("previous-count", dict(pairs="previous", extras="count")),
                     ("legacy", dict(pairs="previous", extras="indicator"))):
        for b in budgets:
            t0 = time.perf_counter()
            a, info = cpsat_polish(p, best, time_limit=b, workers=8, seed=seed*1000+r, deterministic=True, **kw)
            wall = time.perf_counter() - t0
            rec = {"budget": b, "wall": round(wall, 2), "status": info["status"], "vars": info["vars"], "constraints": info["constraints"],
                   "pairVars": info["pairVariables"], "objective": info["objective"], "bound": info["bound"]}
            if a is not None:
                cb = p.cost_breakdown(a)
                rec["recomputed"] = cb
                rec["improvedTotal"] = inc["total"] - cb["total"]
                rec["feasible"] = cb["hard"] == 0
            row["formulations"][f"{name}@{b}"] = rec
    rows.append(row)
    print(json.dumps({k: v for k, v in row.items() if k != "formulations"}), flush=True)
    for k, v in row["formulations"].items():
        print("   ", k, {kk: vv for kk, vv in v.items() if kk != "recomputed"}, "total" , v.get("recomputed", {}).get("total"), flush=True)
    # advance history with the exact-accepted chart (or incumbent)
    chosen = best
    exact = row["formulations"].get("exact@3.5", {})
    members = p.members_of(chosen)
    for m in members:
        for x in m:
            for y in m:
                if x != y:
                    if y in listed[x]:
                        hist_a[x][y] += 1
                    else:
                        hist_m[x][y] += 1
    prev = members
json.dump(rows, open(os.path.join(os.environ.get("CLAUDE_JOB_DIR", "."), "tmp", "bench_cpsat.json"), "w"), indent=1)
