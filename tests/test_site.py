"""Site-copy acceptance checks (docs/): no em dashes, Tab 4 math page."""
import os
import re

from tests.conftest import ROOT

DOCS = os.path.join(ROOT, "docs")
INDEX = os.path.join(DOCS, "index.html")

EQUATIONS = [
    r"\sum_{t} x_{i,t} = 1 \ \ \forall i, \qquad \sum_{i} x_{i,t} = c_t \ \ \forall t",
    r"y_{i,t} \le x_{i,t}, \qquad y_{i,t} \le \sum_{j \in L_i} x_{j,t}, \qquad \sum_{t} y_{i,t} \ge 1",
    r"i^{*} = \arg\min_{i \in U} \, |L_i \cap U|",
    r"s'_i \ge 1, \qquad s'_j \ge 1, \qquad \sum_{k \in A} \mathbf{1}[s'_k \ge 1] \ \ge\ \sum_{k \in A} \mathbf{1}[s_k \ge 1]",
    r"E = \sum_{i} \Big( 1000\,\mathbf{1}[s_i \ge 1] - \max(0,\, s_i - 1) \Big) - \frac{1}{10} \sum_{(a,b)\ \text{co-seated}} \big( 5\, m_{ab} + 2\, \alpha_{ab} \big)",
    r"P(\text{accept } \Delta < 0) = e^{\Delta / T}",
    r"\min\ \ 300 \sum_{i,t} y^{(2)}_{i,t} + \sum_{(a,b)} w_{ab}\, r_{ab}, \qquad w_{ab} = 100 \big( 5\, m_{ab} + 2\, \alpha_{ab} \big)",
    r"\nexists\ S = A \uplus B:\ |A|, |B| \ge 2,\ A, B\ \text{both closed}",
]


def _site_files():
    for dirpath, _, files in os.walk(DOCS):
        for f in files:
            yield os.path.join(dirpath, f)


def test_no_em_dashes_anywhere_in_docs():
    offenders = []
    for path in _site_files():
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for n, line in enumerate(fh, 1):
                if "\u2014" in line:
                    offenders.append(f"{os.path.relpath(path, ROOT)}:{n}")
    assert offenders == [], f"em dashes found: {offenders}"


def _tab4_html():
    html = open(INDEX, encoding="utf-8").read()
    m = re.search(r'<section id="tab-math".*?</section>', html, re.S)
    assert m, "Tab 4 section missing"
    return m.group(0)


def test_tab4_equations_verbatim_and_in_order():
    sec = _tab4_html()
    pos = -1
    for eq in EQUATIONS:
        i = sec.find(eq)
        assert i >= 0, f"equation missing: {eq}"
        assert i > pos, f"equation out of order: {eq}"
        pos = i
    assert sec.count(r"\[") == len(EQUATIONS) == sec.count(r"\]"), "every equation must be in display mode"


def test_tab4_prose_under_150_words():
    sec = _tab4_html()
    text = re.sub(r"\\\[.*?\\\]", " ", sec, flags=re.S)      # display math
    text = re.sub(r"\\\(.*?\\\)", " ", text, flags=re.S)     # inline math
    text = re.sub(r"<[^>]+>", " ", text)
    words = [w for w in re.split(r"\s+", text) if re.search(r"[A-Za-z]", w)]
    assert len(words) < 150, f"{len(words)} words of prose"


def test_katex_loaded_from_cdn_and_four_tabs():
    html = open(INDEX, encoding="utf-8").read()
    assert "KaTeX" in html and "katex.min.js" in html and "auto-render.min.js" in html and "katex.min.css" in html
    assert len(re.findall(r'class="tab[ "].*?data-tab="', html)) == 4
    assert 'data-tab="math"' in html
    assert len(re.findall(r'data-mode="coalition_', html)) == 4
