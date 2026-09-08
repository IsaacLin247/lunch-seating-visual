#!/usr/bin/env python
"""Generate vector paper figures exclusively from verified, retained evidence.

    .venv/bin/python paper/make_figures.py
    .venv/bin/python paper/make_figures.py --figures structural_examples
    .venv/bin/python paper/make_figures.py --retained-source

Empirical figures reject historical summary-only inputs, altered trace files,
source mismatches, and traces that do not match their recorded configurations.
Each PDF has a JSON sidecar recording its inputs and plotted values.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BLUE = "#0072B2"
ORANGE = "#D55E00"
GREEN = "#009E73"
GRAY = "#81858a"
INK = "#222b32"
PALETTE = [BLUE, ORANGE, GREEN, "#CC79A7", "#56B4E9", "#E69F00"]
SCENARIOS = ("honest", "coalition_none", "coalition_min4", "coalition_stratified",
             "coalition_shared_anchor", "coalition_screened")
LABELS = ("Honest", "One-name cycle", "Omission star", "Same-grade attack",
          "Shared anchor", "Screened resubmission")
FIGURES = ("structural_examples", "pipeline", "reference_year", "population_results",
           "sensitivity", "leakage_fairness")
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                     "axes.labelsize": 9, "axes.titlesize": 10,
                     "xtick.labelsize": 9, "ytick.labelsize": 9,
                     "legend.fontsize": 9, "text.color": INK,
                     "axes.labelcolor": INK, "axes.edgecolor": "#abb2b8",
                     "axes.spines.top": False, "axes.spines.right": False,
                     "pdf.fonttype": 42, "ps.fonttype": 42,
                     "savefig.bbox": "tight", "savefig.pad_inches": .06})


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def source_hash(source_root):
    paths = sorted((source_root / "sim").rglob("*.py")) + [source_root / "requirements.txt"]
    return sha(canonical({str(p.relative_to(source_root)): sha(p.read_bytes()) for p in paths}))


def need(condition, message):
    if not condition:
        raise ValueError(message)


class Evidence:
    def __init__(self, manifest, trace_dir, retained_source=False):
        self.manifest_path = manifest.resolve()
        self.trace_dir = trace_dir.resolve()
        self.retained_source = retained_source
        self.source_root = ROOT
        self.source_hash = None if retained_source else source_hash(ROOT)
        self.files = {}
        self.records = None

    def read(self, path):
        path = path.resolve()
        raw = path.read_bytes()
        self.files[str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)] = sha(raw)
        return json.loads(raw)

    def validate_trace(self, trace, label):
        cfg = trace["config"]
        provenance = cfg.get("provenance", {})
        if self.retained_source and self.source_hash is None:
            identity = provenance.get("effectiveSourceHash", "")
            need(len(identity) == 64 and all(c in "0123456789abcdef" for c in identity),
                 f"{label}: invalid archived source identity")
            self.source_root = ROOT / "results/source_snapshots" / identity
            need(self.source_root.is_dir(), f"{label}: audited source snapshot is unavailable")
            self.source_hash = source_hash(self.source_root)
        need(provenance.get("effectiveSourceHash") == self.source_hash,
             f"{label}: trace has no current source provenance; regenerate it")
        need(sha(canonical(provenance["sourceFiles"])) == self.source_hash,
             f"{label}: inconsistent source fingerprint")
        inputs = provenance["effectiveInputs"]
        need(sha(canonical(inputs)) == provenance["inputHash"], f"{label}: input hash mismatch")
        ids = [s["id"] for s in trace["students"]]
        need([[ids[j] for j in row] for row in inputs["submittedLists"]] == trace["listed"],
             f"{label}: submitted lists disagree with effective inputs")
        need(len(trace["rotations"]) == cfg["rotations"], f"{label}: incomplete rotation horizon")
        run = inputs["runConfig"]
        need(run["scenario"] == cfg["scenario"] and run["rotations"] == cfg["rotations"],
             f"{label}: trace configuration disagrees with effective inputs")
        need(provenance["populationSeed"] == inputs["network"]["seed"], f"{label}: population seed mismatch")
        need(provenance["solverSeed"] == run["seed"], f"{label}: solver seed mismatch")
        return trace

    def module(self, name):
        """Load a pure analysis helper from the exact verified source tree."""
        need(self.source_hash is not None, "Validate trace provenance before loading analysis helpers")
        path = self.source_root / "sim" / (name + ".py")
        spec = importlib.util.spec_from_file_location("figure_" + name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def reference(self, scenario="honest"):
        path = self.trace_dir / (scenario + ".json")
        trace = self.validate_trace(self.read(path), str(path))
        cfg = trace["config"]
        need(cfg["scenario"] == scenario and cfg["provenance"]["populationSeed"] == 7,
             f"{path}: expected reference scenario {scenario}, population seed 7")
        need(cfg["rotations"] == 16, f"{path}: reference year must have 16 rotations")
        return trace

    def experiments(self):
        if self.records is not None:
            return self.records
        manifest = self.read(self.manifest_path)
        need(manifest.get("schemaVersion") == 2, "Empirical figures require a schema-2 attempt ledger")
        self.records = []
        for attempt in manifest["attempts"]:
            if attempt["status"] != "success":
                continue
            evidence = attempt.get("traceEvidence")
            need(evidence, f"{attempt['id']}: success without retained trace")
            path = self.manifest_path.parent / evidence["path"]
            raw = path.read_bytes()
            need(sha(raw) == evidence["sha256"], f"{path}: evidence hash mismatch")
            trace = self.validate_trace(self.read(path), str(path))
            cfg = attempt["configuration"]
            provenance = trace["config"]["provenance"]
            inputs = provenance["effectiveInputs"]
            need(attempt["source"]["effectiveSourceHash"] == self.source_hash,
                 f"{path}: attempt source mismatch")
            need(attempt["source"]["versions"] == provenance["versions"], f"{path}: runtime mismatch")
            expected_fingerprint = sha(canonical({
                "configuration": {"category": attempt["category"], **cfg},
                "effectiveSourceHash": self.source_hash, "versions": attempt["source"]["versions"]}))
            need(attempt["fingerprint"] == expected_fingerprint, f"{path}: resume fingerprint mismatch")
            need(provenance["populationSeed"] == cfg["populationSeed"] and
                 provenance["solverSeed"] == cfg["solverSeed"], f"{path}: attempt seed mismatch")
            need(inputs["runConfig"] == {**cfg["run"], "scenario": cfg["scenario"], "seed": cfg["solverSeed"]},
                 f"{path}: requested run and returned trace differ")
            need(inputs["generatorConfig"] == {**cfg["generator"],
                 "short_list_policy": cfg["submission"]["shortListPolicy"]},
                 f"{path}: requested generator and returned trace differ")
            self.records.append((attempt, trace))
        need(self.records, "No current successful trace evidence is available")
        self.attempt_statuses = dict(Counter(a["status"] for a in manifest["attempts"]))
        return self.records


def chart_series(trace):
    """Recompute the plotted empirical quantities from the seating charts."""
    ids = [s["id"] for s in trace["students"]]
    listed = dict(zip(ids, map(set, trace["listed"])))
    result = {}
    for key in ("tables", "tablesRandom"):
        met = {i: set() for i in ids}
        rows = []
        for rotation in trace["rotations"]:
            counts = []
            for table in rotation[key]:
                for i in table:
                    peers = set(table) - {i}
                    met[i].update(peers)
                    if listed[i]:
                        counts.append(len(peers & listed[i]))
            rows.append({"meanDistinct": sum(map(len, met.values())) / len(ids),
                         "exactlyOne": 100 * sum(c == 1 for c in counts) / len(counts) if counts else 0,
                         "guarantee": 100 * sum(c >= 1 for c in counts) / len(counts) if counts else 0})
        result[key] = rows
        result[key + "Distinct"] = {i: len(names) for i, names in met.items()}
    return result


def save(fig, out_dir, name, values, evidence=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / (name + ".pdf")
    fig.savefig(path, metadata={"Title": name.replace("_", " "),
                               "Author": "Lunch seating study", "CreationDate": None,
                               "ModDate": None})
    plt.close(fig)
    metadata = {"figure": path.name, "pdfSha256": sha(path.read_bytes()),
                "generatorSha256": sha(Path(__file__).read_bytes()),
                "type": "empirical" if evidence else "structural",
                "inputs": dict(evidence.files) if evidence else {},
                "effectiveSourceHash": evidence.source_hash if evidence else None,
                "sourceVerification": ("retained_snapshot" if evidence.retained_source else "working_tree") if evidence else None,
                "plottedValues": values}
    path.with_suffix(".json").write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n")
    print(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path, flush=True)


def prettify(ax, ylabel=None, xlabel=None):
    ax.set_axisbelow(True)
    ax.grid(axis="y", alpha=.18)
    if ylabel:
        ax.set_ylabel(ylabel)
    if xlabel:
        ax.set_xlabel(xlabel)


def graph_node(ax, xy, label, color=BLUE, radius=.11):
    ax.add_patch(Circle(xy, radius, facecolor="white", edgecolor=color, lw=1.4, zorder=4))
    ax.text(*xy, str(label), ha="center", va="center", fontsize=9, color=color, zorder=5)


def graph_edge(ax, start, end, color=BLUE, rad=0, alpha=.75):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=8,
                                shrinkA=9, shrinkB=9, linewidth=.85, color=color,
                                alpha=alpha, connectionstyle=f"arc3,rad={rad}", zorder=2))


def structural_examples(out_dir):
    fig = plt.figure(figsize=(6.5, 5.05))
    gs = fig.add_gridspec(2, 6, height_ratios=[1.5, 1], hspace=.55, wspace=.5)
    ax = fig.add_subplot(gs[0, :3])
    positions = {i: (math.cos(math.pi/2 + 2*math.pi*i/7),
                     math.sin(math.pi/2 + 2*math.pi*i/7)) for i in range(7)}
    for step, color in [(1, BLUE), (2, ORANGE)]:
        for i in range(7):
            graph_edge(ax, positions[i], positions[(i+step) % 7], color, .08 if step == 2 else 0)
    for i, xy in positions.items():
        graph_node(ax, xy, i)
    ax.set_title("a  Odd seven-member graph", loc="left", fontweight="bold")
    ax.text(0, -1.4, "Edges +1 (blue), +2 (orange) mod 7\nDirected cycles need at least 4 members;\ntwo disjoint cycles cannot fit.",
            ha="center", va="top", fontsize=9)
    ax.set(xlim=(-1.45, 1.45), ylim=(-1.72, 1.35), aspect="equal")
    ax.axis("off")
    ax = fig.add_subplot(gs[0, 3:])
    pos = {i: (.85*math.cos(math.pi/2 + 2*math.pi*i/7)-.32,
               .85*math.sin(math.pi/2 + 2*math.pi*i/7)) for i in range(7)}
    anchor = (1.28, 0)
    for i in range(7):
        graph_edge(ax, pos[i], pos[(i+1) % 7])
        graph_edge(ax, pos[i], anchor, ORANGE, alpha=.5)
    for i, xy in pos.items():
        graph_node(ax, xy, i)
    graph_node(ax, anchor, "h", ORANGE)
    ax.set_title("b  Shared outside anchor", loc="left", fontweight="bold")
    ax.text(.05, -1.4, "Same-grade names: successor and h\nThe cycle plus h needs 8 seats;\nmaximum table size is 7.",
            ha="center", va="top", fontsize=9)
    ax.set(xlim=(-1.65, 1.65), ylim=(-1.72, 1.35), aspect="equal")
    ax.axis("off")
    partitions = [[[0, 2, 3], [1, 4, 5]], [[0, 1, 2, 3], [4, 5]], [[0, 1, 2, 3, 4, 5]]]
    for index, parts in enumerate(partitions):
        ax = fig.add_subplot(gs[1, 2*index:2*index+2])
        xs = np.linspace(-.6, .6, len(parts)) if len(parts) > 1 else [0]
        for x, part in zip(xs, parts):
            radius = .43 if len(parts) == 1 else .35
            ax.add_patch(FancyBboxPatch((x-radius-.09, -.49), 2*radius+.18, .98,
                                        boxstyle="round,pad=.01,rounding_size=.12",
                                        facecolor="#f2f5f7", edgecolor="#aab7c0", lw=.9))
            positions = {j: (x+radius*math.cos(math.pi/2+2*math.pi*k/len(part)),
                             radius*math.sin(math.pi/2+2*math.pi*k/len(part))) for k, j in enumerate(part)}
            for i in part:
                omitted = 1 if i == 0 else 0
                j = next(j for j in part if j != i and j != omitted)
                graph_edge(ax, positions[i], positions[j], GREEN)
            for i, xy in positions.items():
                graph_node(ax, xy, i, GREEN, .105)
        pattern = "+".join(map(str, map(len, parts)))
        score = sum(len(p)**2 for p in parts)/6
        ax.set_title(f"{chr(99+index)}  {pattern} partition", loc="left", fontweight="bold")
        score_label = "10/3" if index == 1 else f"{score:g}"
        ax.text(0, -.72, f"Mean cluster = {score_label}", ha="center", fontsize=9)
        ax.set(xlim=(-1.2, 1.2), ylim=(-.91, .73), aspect="equal")
        ax.axis("off")
    fig.text(.5, .02, "Omission star: 0 omits 1; all others omit 0. Each lists the other four.\n"
             "Bottom arrows show one listed peer per member. All three partitions are feasible.\n"
             "Mean cluster is weighted by members: the sum of squared part sizes, divided by 6.",
             ha="center", fontsize=9)
    save(fig, out_dir, "structural_examples", {"oddGraph": {"n": 7, "steps": [1, 2]},
         "sharedAnchor": {"coalition": 7, "capacity": 7}, "omissionStarPartitions": partitions})


def pipeline(evidence, out_dir):
    candidates = [trace for attempt, trace in evidence.experiments()
                  if attempt["category"] == "seeds" and attempt["configuration"]["scenario"] == "honest"
                  and attempt["configuration"]["populationSeed"] == 2
                  and attempt["configuration"]["run"]["rotations"] == 16]
    need(len(candidates) == 1, "Pipeline figure requires exactly one verified honest seed-2 reference")
    trace = candidates[0]
    rotation = trace["rotations"][0]
    stages = rotation.get("pipeline", [])
    need(len(stages) == 4, "Pipeline figure requires four retained stage assignments")
    ids = [s["id"] for s in trace["students"]]
    lists = dict(zip(ids, map(set, trace["listed"])))
    fig, axes = plt.subplots(2, 2, figsize=(6.5, 5.4), layout="constrained")
    records = []
    for index, (ax, stage) in enumerate(zip(axes.flat, stages)):
        for t, table in enumerate(stage["tables"]):
            center = (t % 8, -(t // 8))
            ax.add_patch(Circle(center, .39, facecolor="#f2f5f7", edgecolor="#d5dbe0", lw=.55))
            pos = {i: (center[0] + .29*math.cos(math.pi/2+2*math.pi*k/len(table)),
                       center[1] + .29*math.sin(math.pi/2+2*math.pi*k/len(table))) for k, i in enumerate(table)}
            for i in table:
                peers = (set(table)-{i}) & lists[i]
                color = BLUE if peers else ORANGE if lists[i] else GRAY
                if peers:
                    j = sorted(peers)[0]
                    ax.plot([pos[i][0], pos[j][0]], [pos[i][1], pos[j][1]], color=BLUE, alpha=.2, lw=.5, zorder=2)
                ax.scatter(*pos[i], s=5.4, color=color, linewidths=0, zorder=3)
        cost = stage["cost"]
        title = ("Pod construction", "Swap repair", "Annealing", "Final accepted seating")[index]
        ax.set_title(f"{chr(97+index)}  {title}", loc="left", fontweight="bold")
        ax.text(3.5, -4.6, f"Without a listed peer: {cost['violations']}\nExtra listed peers: {cost['extraPeers']}",
                ha="center", va="top", fontsize=9)
        ax.set(xlim=(-.58, 7.58), ylim=(-5.6, .62), aspect="equal")
        ax.axis("off")
        records.append({"stage": stage["name"], "cost": cost, "seconds": stage["seconds"]})
    fig.suptitle("Honest population seed 2, rotation 1 (mixed): every table and student", fontsize=10)
    fig.supxlabel("Blue: has a listed peer    Orange: lacks a listed peer    Gray: no submission", fontsize=9)
    save(fig, out_dir, "pipeline", {"populationSeed": 2, "rotation": 1, "acceptedPhase":
         rotation["stats"]["acceptedPhase"], "stages": records}, evidence)


def reference_year(evidence, out_dir):
    trace = evidence.reference()
    expected_distinct = evidence.module("baseline").expected_distinct
    data = chart_series(trace)
    x = np.arange(1, len(trace["rotations"])+1)
    fig, axes = plt.subplots(1, 2, figsize=(6.5, 2.8), layout="constrained")
    cfg = trace["config"]
    grades = [s["grade"] for s in trace["students"]]
    by_grade = {g: [c for c, tg in zip(cfg["tableCapacities"], cfg["sameGradeTableGrade"]) if tg == g]
                for g in set(grades)}
    states = [r["state"] for r in trace["rotations"]]
    expected = [expected_distinct(grades, cfg["tableCapacities"], by_grade, states[:r]) for r in x]
    axes[0].plot(x, expected, color=GREEN, label="Random expectation", ls="--", lw=1.6, zorder=4)
    for key, color, label, marker in [("tables", BLUE, "Proposed", "o"),
                                      ("tablesRandom", GRAY, "Paired random", "s")]:
        axes[0].plot(x, [r["meanDistinct"] for r in data[key]], color=color, label=label, marker=marker, ms=3, lw=1.6)
        axes[1].plot(x, [r["exactlyOne"] for r in data[key]], color=color, label=label, marker=marker, ms=3, lw=1.6)
    for ax in axes:
        for r in x:
            if states[r-1] == "same":
                ax.axvspan(r-.5, r+.5, color=BLUE, alpha=.055, lw=0)
        ax.set_xticks([1, 4, 8, 12, 16])
        ax.set_xlim(.5, 16.5)
        prettify(ax, xlabel="Rotation")
    axes[0].set_title("a  Distinct schoolmates met", loc="left", fontweight="bold")
    axes[0].set_ylabel("Mean per student")
    axes[0].legend(frameon=False)
    axes[1].set_title("b  Exactly one listed peer", loc="left", fontweight="bold")
    axes[1].set_ylabel("Submitters (%)")
    axes[1].set_ylim(0, 105)
    save(fig, out_dir, "reference_year", {"populationSeed": 7, "series": data,
         "analyticRandomExpectation": expected, "shading": "same-grade rotations"}, evidence)


def population_results(evidence, out_dir):
    selected = {}
    for attempt, trace in evidence.experiments():
        c = attempt["configuration"]
        if (attempt["category"] == "seeds" and c["scenario"] == "honest" and
            c["run"]["rotations"] == 16 and c["run"]["anneal_iters"] == 300000 and
            c["run"]["cpsat_time"] == 3.5 and c["generator"]["mu"] == c["generator"]["omega"] == 0):
            need(c["populationSeed"] not in selected, "Duplicate honest population seed in the analysis set")
            selected[c["populationSeed"]] = chart_series(trace)
    need(set(selected) == set(range(1, 11)), "Population figure requires all ten verified honest seeds 1..10")
    seeds = sorted(selected)
    proposed = [selected[s]["tables"][-1]["meanDistinct"] for s in seeds]
    random = [selected[s]["tablesRandom"][-1]["meanDistinct"] for s in seeds]
    difference = np.array(proposed)-np.array(random)
    rng = np.random.default_rng(20260908)
    bootstrap_means = difference[rng.integers(0, len(seeds), size=(20000, len(seeds)))].mean(axis=1)
    ci_low, ci_high = np.quantile(bootstrap_means, [.025, .975], method="linear")
    mean_difference = float(difference.mean())
    fig, axes = plt.subplots(1, 2, figsize=(6.5, 3.0), layout="constrained", gridspec_kw={"width_ratios": [1.15, 1]})
    for s, p, r in zip(seeds, proposed, random):
        axes[0].plot([r, p], [s, s], color="#aebcc7", lw=1.4)
    axes[0].scatter(random, seeds, color=GRAY, marker="s", s=23, label="Paired random", zorder=3)
    axes[0].scatter(proposed, seeds, color=BLUE, s=27, label="Proposed", zorder=3)
    axes[0].set(yticks=seeds, ylabel="Population seed", xlabel="Mean distinct schoolmates after 16 rotations")
    axes[0].set_ylim(-1.5, 10.5)
    axes[0].set_title("a  Paired outcomes", loc="left", fontweight="bold")
    axes[0].legend(frameon=False, fontsize=9, loc="lower right")
    axes[0].grid(axis="x", alpha=.15)
    axes[1].axhline(0, color=GRAY, lw=.8)
    axes[1].bar(seeds, difference, color=[BLUE if d >= 0 else ORANGE for d in difference], width=.7)
    axes[1].axhspan(ci_low, ci_high, color=INK, alpha=.1, label="95% paired bootstrap CI")
    axes[1].axhline(mean_difference, color=INK, lw=1, ls="--", label=f"Mean = {mean_difference:.2f}")
    axes[1].set(xticks=seeds, xlabel="Population seed", ylabel="Proposed minus paired random")
    axes[1].set_ylim(0, max(difference) + 1.15)
    axes[1].set_title("b  Difference within each cohort", loc="left", fontweight="bold")
    prettify(axes[1])
    axes[1].legend(frameon=False, fontsize=9, loc="upper left")
    save(fig, out_dir, "population_results", {"seeds": seeds, "proposed": proposed,
         "pairedRandom": random, "difference": difference.tolist(),
         "pairedPopulationBootstrap": {"mean": mean_difference, "ci95": [float(ci_low), float(ci_high)],
             "resamples": 20000, "randomSeed": 20260908, "rng": "numpy.random.PCG64",
             "numpyVersion": np.__version__,
             "resamplingUnit": "paired population seed", "populationSeeds": seeds,
             "interval": "95% percentile", "quantileMethod": "linear"},
         "attemptStatuses": evidence.attempt_statuses}, evidence)


def sensitivity(evidence, out_dir):
    rows = []
    for attempt, trace in evidence.experiments():
        c = attempt["configuration"]
        if c["populationSeed"] != 7 or c["scenario"] != "honest" or c["run"]["rotations"] != 16:
            continue
        data = chart_series(trace)
        rows.append({"category": attempt["category"], "anneal": c["run"]["anneal_iters"],
                     "cp": c["run"]["cpsat_time"], "mu": c["generator"]["mu"],
                     "omega": c["generator"]["omega"], "attemptId": attempt["id"],
                     "difference": data["tables"][-1]["meanDistinct"]-data["tablesRandom"][-1]["meanDistinct"],
                     "exactlyOne": sum(r["exactlyOne"] for r in data["tables"])/16})
    def unique(values, key):
        found = {}
        for row in values:
            value = key(row)
            if value not in found or row["category"] in ("budgets", "communities"):
                found[value] = row
        return [found[k] for k in sorted(found)]
    anneal = unique([r for r in rows if r["mu"] == r["omega"] == 0 and r["cp"] == 3.5], lambda r: r["anneal"])
    cp = unique([r for r in rows if r["mu"] == r["omega"] == 0 and r["anneal"] == 300000], lambda r: r["cp"])
    communities = unique([r for r in rows if r["anneal"] == 300000 and r["cp"] == 3.5], lambda r: (r["mu"], r["omega"]))
    need({r["anneal"] for r in anneal} == {100000, 300000, 900000}
         and {r["cp"] for r in cp} == {.1, 1.0, 3.5}
         and {(r["mu"], r["omega"]) for r in communities} == {(0, 0), (.6, .3), (1, 0)},
         "Sensitivity figure requires all planned annealing, CP budget, and community settings")
    fig, axes = plt.subplots(2, 3, figsize=(6.5, 4.2), layout="constrained", sharey="row")
    plotted = {}
    settings = [("Annealing budget", anneal, lambda r: f"{r['anneal']/1000:g}k", "Iterations"),
                ("CP-SAT budget", cp, lambda r: f"{r['cp']:g}", "Deterministic-time units"),
                ("Community structure", communities, lambda r: f"{r['mu']:g}, {r['omega']:g}", r"$(\mu,\omega)$")]
    for col, (title, selected, label, xlabel) in enumerate(settings):
        x = range(len(selected))
        labels = [label(r) for r in selected]
        for row, field in [(0, "difference"), (1, "exactlyOne")]:
            ax = axes[row, col]
            ax.plot(x, [r[field] for r in selected], marker="o", color=BLUE if row == 0 else GREEN, lw=1.4, ms=4)
            ax.set_xticks(list(x), labels)
            ax.set_xlim(-.3, len(selected)-.7)
            prettify(ax)
            if row == 0:
                ax.axhline(0, color=GRAY, lw=.7)
                ax.set_title(f"{chr(97+col)}  {title}", loc="left", fontweight="bold")
            else:
                ax.set_xlabel(xlabel)
        plotted[title] = selected
    axes[0, 0].set_ylabel("Distinct contacts gained\n(proposed − paired random)")
    axes[1, 0].set_ylabel("Exactly one listed peer\n(mean submitter %)")
    fig.suptitle("One-factor probes, honest population seed 7, 16 rotations", fontsize=10)
    save(fig, out_dir, "sensitivity", plotted, evidence)


def leakage_fairness(evidence, out_dir):
    evidence.reference()
    leakage_report = evidence.module("privacy").leakage_report
    fig, axes = plt.subplots(1, 2, figsize=(6.5, 3.1), layout="constrained")
    prefix_data = {}
    prefixes = list(range(1, 17))
    for scenario, label, color, marker in zip(SCENARIOS, LABELS, PALETTE, ["o", "s", "^", "D", "v", "P"]):
        trace = evidence.reference(scenario)
        counts = [leakage_report({**trace, "rotations": trace["rotations"][:r]}, k_max=8)["forcedEdges"]
                  for r in prefixes]
        need(counts[-1] == trace["leakage"]["forcedEdges"], f"{scenario}: full-year privacy count mismatch")
        axes[0].plot(prefixes, counts, color=color, label=label, lw=1.35, marker=marker, ms=3)
        prefix_data[scenario] = counts
    for r in range(2, 17, 2):
        axes[0].axvspan(r-.5, r+.5, color=BLUE, alpha=.055, lw=0)
    axes[0].set_xlim(.5, 16.5)
    axes[0].set_title("a  Chart-only forced list entries", loc="left", fontweight="bold")
    axes[0].set_xticks([1, 4, 8, 12, 16])
    prettify(axes[0], ylabel="Forced directed entries (public cap 8)", xlabel="Observed rotations")
    axes[0].legend(frameon=False, fontsize=9, loc="upper left")
    trace = evidence.reference()
    data = chart_series(trace)
    ids = [s["id"] for s in trace["students"]]
    indegree = Counter(j for row in trace["listed"] for j in row)
    points = Counter((indegree[i], data["tablesDistinct"][i]) for i in ids)
    axes[1].scatter([p[0] for p in points], [p[1] for p in points], s=[12+7*(n-1) for n in points.values()],
                    color=BLUE, alpha=.52, linewidths=.3, edgecolors="white")
    ordered = sorted(ids, key=lambda i: (indegree[i], i))
    q = len(ids)//4
    quartiles = {}
    for label, subset, color in [("Lowest quartile", ordered[:q], ORANGE),
                                  ("Highest quartile", ordered[-q:], GREEN)]:
        x = sum(indegree[i] for i in subset)/q
        y = sum(data["tablesDistinct"][i] for i in subset)/q
        axes[1].scatter([x], [y], marker="D", color=color, s=42, edgecolor="white", linewidth=.6, zorder=4, label=label)
        quartiles[label] = {"n": q, "meanInDegree": x, "meanDistinctMet": y}
    axes[1].set_title("b  Honest reference cohort", loc="left", fontweight="bold")
    prettify(axes[1], ylabel="Distinct schoolmates after 16 rotations", xlabel="Submitted-list in-degree")
    axes[1].legend(frameon=False, fontsize=9, loc="lower right")
    save(fig, out_dir, "leakage_fairness", {"publicCap": 8, "prefixRotations": prefixes,
         "forcedEntries": prefix_data, "fairnessPoints": [{"inDegree": x, "distinctMet": y, "n": n}
         for (x, y), n in sorted(points.items())], "quartiles": quartiles}, evidence)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, default=ROOT / "results/verified_experiments.json")
    parser.add_argument("--trace-dir", type=Path, default=ROOT / "docs/data")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "article/figures")
    parser.add_argument("--retained-source", action="store_true",
                        help="verify analysis source against results/source_snapshots/HASH")
    parser.add_argument("--figures", default=",".join(FIGURES), help="comma-separated figure names")
    args = parser.parse_args(argv)
    selected = args.figures.split(",")
    need(set(selected) <= set(FIGURES), "Unknown figure requested")
    for name in selected:
        if name == "structural_examples":
            structural_examples(args.out_dir.resolve())
        else:
            evidence = Evidence(args.manifest, args.trace_dir, retained_source=args.retained_source)
            globals()[name](evidence, args.out_dir.resolve())


if __name__ == "__main__":
    main()
