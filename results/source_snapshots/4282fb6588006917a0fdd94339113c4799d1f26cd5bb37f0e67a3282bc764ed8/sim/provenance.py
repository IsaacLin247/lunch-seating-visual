"""Effective-source and input identities for auditable simulation artifacts.

Generated traces, papers and timestamps are deliberately outside the source
fingerprint.  A dirty checkout remains identifiable through hashes of the Python
source actually present, rather than by attributing it to HEAD alone.
"""
from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def json_value(value: Any):
    """Convert numpy values and dataclasses' containers to canonical JSON data."""
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(json_value(v) for v in value)
    if hasattr(value, "tolist"):
        return json_value(value.tolist())
    if isinstance(value, Path):
        return str(value)
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(json_value(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def file_sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_provenance(root=None) -> dict:
    """Return source hashes, full git identity/dirty state and runtime versions.

    ``effectiveSourceHash`` covers all sim Python modules and requirements.txt.
    The git dirty flag includes tracked edits and untracked source files, but
    does not make generated outputs part of the resume fingerprint.
    """
    root = Path(root) if root is not None else ROOT
    files = sorted((root / "sim").rglob("*.py"))
    if (root / "requirements.txt").exists():
        files.append(root / "requirements.txt")
    hashes = {str(p.relative_to(root)): file_sha256(p) for p in files}
    commit, dirty, git_status = None, None, None
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                         text=True, stderr=subprocess.DEVNULL).strip()
        git_status = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"],
                                             cwd=root, text=True, stderr=subprocess.DEVNULL).splitlines()
        dirty = bool(git_status)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    import numpy
    import ortools
    versions = {"python": platform.python_version(), "numpy": numpy.__version__,
                "ortools": ortools.__version__, "platform": platform.platform()}
    return {"schemaVersion": 1, "gitCommit": commit, "gitDirty": dirty,
            "gitStatus": git_status, "effectiveSourceHash": fingerprint(hashes),
            "sourceFiles": hashes, "sourceScope": "sim/**/*.py and requirements.txt; generated artifacts excluded",
            "versions": versions}


def trace_provenance(net, lists, run_config, generator_config=None) -> dict:
    """Identity and effective input sufficient to audit a direct ``run_year``.

    The actual generated graph is retained because callers can construct or
    modify Network objects manually.  Explicit generator parameters describe
    intent; the effective snapshot also captures any subsequent modifications.
    """
    source = source_provenance()
    network = json_value(vars(net))
    inputs = {"network": network, "submittedLists": json_value(lists),
              "runConfig": json_value(run_config),
              "generatorConfig": json_value(generator_config)}
    return {**source, "populationSeed": int(net.seed),
            "solverSeed": int(run_config.get("seed", net.seed)),
            "inputHash": fingerprint(inputs), "effectiveInputs": inputs}


def resume_fingerprint(configuration: dict, source: dict) -> str:
    """Resume only exact configurations on the same source and runtime versions."""
    return fingerprint({"configuration": configuration,
                        "effectiveSourceHash": source["effectiveSourceHash"],
                        "versions": source["versions"]})
