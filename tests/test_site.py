"""Website contracts: truthful guarantees, dynamic traces, and accessible controls."""
import base64
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from tests.conftest import ROOT

DOCS = Path(ROOT) / "docs"


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def test_no_em_dashes_in_site_text_assets():
    offenders = []
    for path in DOCS.rglob("*"):
        if path.suffix not in {".html", ".css", ".js", ".json", ".svg", ".txt"}:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "\u2014" in line:
                offenders.append(f"{path.relative_to(ROOT)}:{n}")
    assert not offenders, f"em dashes found: {offenders}"


def test_guarantee_and_playback_scope_are_explicit():
    html = (DOCS / "index.html").read_text()
    assert "at least one eligible listed peer" in html
    assert "browser does not run optimization" in html
    assert "Exactly one and new acquaintances are optimization preferences" in html
    assert "UNKNOWN proves neither feasibility nor impossibility" in html
    assert "every already-satisfied submitter" in html
    assert "stage-controls" in html and "Early stages can violate the friend guarantee" in html
    assert "intervening search moves are not recorded" in html
    assert "docs/article.pdf" not in html and 'href="article.pdf"' in html


def test_algorithm_equations_have_eligible_edges_and_stage_specific_objectives():
    html = (DOCS / "index.html").read_text()
    assert r"\sum_{j\in L_i^{(q)}}x_{j,t}" in html
    assert r"V_{\mathrm{after}}\subsetneq V_{\mathrm{before}}" in html
    assert r"C=1000|V|" in html
    assert r"\max(0,s_i-1)" in html
    assert r"e^{-\Delta C/T}" in html
    assert r"\min\ 300\sum_i z_i" in html
    assert r"\in P_{q-1}" in html
    assert html.count(r"\[") == html.count(r"\]") == 6
    assert "katex.min.js" in html and "katex.min.css" in html and "auto-render.min.js" in html


def test_tab_relationships_and_canvas_alternatives():
    elements = Elements((DOCS / "index.html").read_text()).elements
    tabs = [attrs for _, attrs in elements if attrs.get("role") == "tab"]
    panels = {attrs["id"]: attrs for _, attrs in elements if attrs.get("role") == "tabpanel"}
    assert len(tabs) == len(panels) == 4
    assert sum(t.get("tabindex") == "0" for t in tabs) == 1
    for tab in tabs:
        assert panels[tab["aria-controls"]]["aria-labelledby"] == tab["id"]
    for tag, attrs in elements:
        if tag == "canvas":
            assert attrs.get("role") == "img" and attrs.get("aria-label")
    app = (DOCS / "app.js").read_text()
    assert "buttons[idx].focus()" in app
    assert "prefers-reduced-motion" in app


def test_modes_and_horizon_are_loaded_from_trace_data():
    app = (DOCS / "app.js").read_text()
    assert "data/manifest.json" in app
    assert "traces.honest.rotations.length" in app
    assert "share a rotation count and grade schedule" in app
    game = (DOCS / "tab3.js").read_text()
    assert "coalitionModes(ctx.traces)" in game
    assert "members.length" in game
    assert "config.diagnosticScreen" in game
    assert "trace.config.rules?.screens" in game
    assert "lists, state" in game and "stroke-dasharray" in game


def test_observed_coalition_summary_uses_charts_not_assumed_sixteen_rounds():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable for the pure JavaScript summary check")
    source = base64.b64encode((DOCS / "scenarios.js").read_bytes()).decode()
    trace = {"config": {"coalition": list("ABCDEFG")}, "rotations": [
        {"state": "mixed", "coalition": {"pattern": "4+3", "intact": False, "avgCluster": 25 / 7}},
        {"state": "same", "coalition": {"pattern": "7", "intact": True, "avgCluster": 7}},
    ]}
    program = f"""
      const {{ coalitionModes, observation, EXPLANATIONS }} = await import('data:text/javascript;base64,{source}');
      const trace = {json.dumps(trace)};
      const modes = coalitionModes({{honest: trace, coalition_shared_anchor: trace}});
      console.log(JSON.stringify({{modes: modes.map(([name]) => name), summary: observation(trace), star: EXPLANATIONS.coalition_min4.proof}}));
    """
    result = subprocess.run([node, "--input-type=module", "-e", program], check=True, capture_output=True, text=True)
    actual = json.loads(result.stdout)
    assert actual["modes"] == ["coalition_shared_anchor"]
    assert "2 saved rotations" in actual["summary"]
    assert "4+3 (1), 7 (1)" in actual["summary"]
    assert "1/2 rounds" in actual["summary"] and "1/1 same-grade" in actual["summary"]
    assert "5.29" in actual["summary"]
    assert "3+3, 4+2, and 6" in actual["star"]
    assert "shared table is allowed" in actual["star"]
