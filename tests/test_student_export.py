"""Student-facing exports carry the assignment and nothing private."""
import json

import pytest

from sim.student_export import (PRIVATE_CONFIG_KEYS, PRIVATE_ROTATION_KEYS, PRIVATE_TRACE_KEYS,
                                assert_no_private_data, student_facing_export)
from tests.conftest import load


def _flatten_keys(node, out):
    if isinstance(node, dict):
        for k, v in node.items():
            out.add(k)
            _flatten_keys(v, out)
    elif isinstance(node, list):
        for v in node:
            _flatten_keys(v, out)
    return out


def test_student_export_omits_private_data():
    trace = load("honest")
    export = student_facing_export(trace, rotation=3)
    keys = _flatten_keys(export, set())
    assert not keys & (PRIVATE_TRACE_KEYS | PRIVATE_CONFIG_KEYS | PRIVATE_ROTATION_KEYS)
    assert export["includesHistory"] is False and len(export["rotations"]) == 1
    rot = export["rotations"][0]
    assert rot["idx"] == 3 and [len(t) for t in rot["tables"]] == trace["config"]["tableCapacities"]
    assert {s["id"] for t in rot["tables"] for s in t} == {s["id"] for s in trace["students"]}
    text = json.dumps(export)
    for private in ("listed", "anchors", "leakage", "screen", "pipeline", "tablesRandom", "submission"):
        assert f'"{private}"' not in text
    # no list information survives: every student's row holds only an id and a grade
    assert all(set(s) <= {"id", "grade"} for t in rot["tables"] for s in t)


def test_history_export_is_an_explicit_opt_in_with_a_warning():
    trace = load("honest")
    export = student_facing_export(trace, include_history=True)
    assert export["includesHistory"] and len(export["rotations"]) == len(trace["rotations"])
    assert "historyWarning" in export
    assert_no_private_data(export)


def test_private_fields_are_detected_at_any_depth():
    with pytest.raises(ValueError, match="private field"):
        assert_no_private_data({"rotations": [{"idx": 1, "extra": {"anchors": {}}}]})
