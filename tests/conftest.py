import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DATA = os.environ.get("LSV_DATA_DIR", os.path.join(ROOT, "docs", "data"))
SCENARIOS = ["honest", "coalition_none", "coalition_min4", "coalition_stratified", "coalition_screened"]


def load(name):
    path = os.path.join(DATA, f"{name}.json")
    if not os.path.exists(path):
        pytest.skip(f"{path} missing - run `python sim/export_traces.py` first")
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="session", params=SCENARIOS)
def trace(request):
    return load(request.param)


@pytest.fixture(scope="session")
def traces():
    return {name: load(name) for name in SCENARIOS}
