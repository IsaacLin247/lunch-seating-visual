"""Release consistency and stale-browser-module portrait regressions.

The browser checks are optional when Playwright/Chromium is unavailable.
Every release identifier is read from index.html rather than hard-coded.
"""
from functools import partial
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import threading
from urllib.parse import parse_qs, urlsplit

import pytest


DOCS = Path(__file__).resolve().parents[1] / "docs"
LOCAL_MODULE = re.compile(r"['\"](\./[^'\"]+\.js(?:\?[^'\"]*)?)['\"]")


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def entry_release():
    page = Assets()
    page.feed((DOCS / "index.html").read_text())
    entries = [attrs["src"] for tag, attrs in page.tags if tag == "script" and attrs.get("type") == "module" and attrs.get("src")]
    assert len(entries) == 1
    parsed = urlsplit(entries[0])
    release = parse_qs(parsed.query).get("v", [])
    assert len(release) == 1 and release[0], "The app entry needs an explicit release identifier"
    return entries[0], release[0], page.tags


def test_authored_module_graph_and_styles_share_entry_release():
    entry, release, tags = entry_release()
    authored = {path.name for path in DOCS.glob("*.js")}
    visited = set()

    def visit(name):
        if name in visited:
            return
        visited.add(name)
        for reference in LOCAL_MODULE.findall((DOCS / name).read_text()):
            parsed = urlsplit(reference)
            relative = parsed.path.removeprefix("./")
            if relative not in authored:
                assert (DOCS / relative).is_file(), f"Missing local dependency: {relative}"
                continue
            assert parse_qs(parsed.query).get("v") == [release], f"Mixed release: {name} imports {reference}"
            visit(relative)

    visit(urlsplit(entry).path)
    assert {"app.js", "portraits.js", "portrait-data.js", "avatars.js", "room.js", "tab1.js", "tab2.js", "tab3.js", "tab4.js"} <= visited
    styles = [attrs["href"] for tag, attrs in tags if tag == "link" and attrs.get("rel") == "stylesheet" and urlsplit(attrs.get("href", "")).path == "styles.css"]
    assert len(styles) == 1 and parse_qs(urlsplit(styles[0]).query).get("v") == [release]


@pytest.fixture
def asset_server():
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *unused):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(DOCS)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        try:
            instance = runtime.chromium.launch(executable_path=os.environ.get("CHROME_PATH"), headless=True)
        except playwright.Error as error:
            pytest.skip(f"Chromium is unavailable: {error}")
        try:
            yield instance
        finally:
            instance.close()


def legacy_tab(name):
    """The exact pre-portrait public API shape, kept stable across git commits.

    The original failure was independently reproduced with tab2.js from HEAD
    before this repair. Rendering details are irrelevant to the missing method.
    """
    number = re.fullmatch(r"tab([1-4])\.js", name).group(1)
    return f"export function createTab{number}() {{ return {{ render() {{}}, resize() {{}}, pause() {{}} }}; }}"


def test_release_graph_bypasses_unversioned_stale_tabs_and_loads_all_views(browser, asset_server, tmp_path):
    from tests.browser_portraits import INSTRUMENT, fixture, wait_portraits

    _, release, _ = entry_release()
    authored = {path.name for path in DOCS.glob("*.js")}
    folder = tmp_path / "synthetic_directory"
    folder.mkdir()
    fixture(folder)
    context = browser.new_context(viewport={"width": 1440, "height": 1100}, reduced_motion="reduce")
    context.add_init_script(INSTRUMENT)
    stale_hits, modules, unexpected, errors = [], [], [], []

    def serve_cache(route):
        parsed = urlsplit(route.request.url)
        name = parsed.path.lstrip("/")
        if parsed.netloc != urlsplit(asset_server).netloc or route.request.method != "GET":
            unexpected.append(route.request.url)
            route.abort()
            return
        if name in authored:
            modules.append((name, parsed.query))
        if re.fullmatch(r"tab[1-4]\.js", name) and not parsed.query:
            stale_hits.append(name)
            route.fulfill(status=200, content_type="application/javascript", headers={"Cache-Control": "public, max-age=31536000"}, body=legacy_tab(name))
        else:
            route.continue_()

    context.route("**/*", serve_cache)
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(asset_server, wait_until="networkidle")
        page.wait_for_function("document.getElementById('loading').hidden")
        assert stale_hits == [], "An unversioned tab requested the stale API shape"
        assert {name for name, _ in modules} >= {f"tab{number}.js" for number in range(1, 5)}
        assert all(parse_qs(query).get("v") == [release] for _, query in modules)

        # Install an old unversioned module into this page's actual ES-module
        # map. Its separate URL must not replace the already-running release.
        page.evaluate("async () => { const old=await import('./tab2.js'); window.__oldTabHasPortraits=typeof old.createTab2().setPortraits; }")
        assert page.evaluate("window.__oldTabHasPortraits") == "undefined"
        assert stale_hits == ["tab2.js"]
        baseline = page.locator("#s-prop-ge1").inner_text()
        page.locator("#portrait-folder").set_input_files(str(folder))
        wait_portraits(page)
        assert not page.locator("#portrait-status").evaluate("element=>element.classList.contains('error')")
        assert page.locator("#s-prop-ge1").inner_text() == baseline
        expected = page.evaluate("async () => { const entry=new URL(document.querySelector('script[type=module][src]').src); return (await import('./avatars.js'+entry.search)).directoryPortraitUri('S015'); }")
        assert expected.startswith("blob:")
        page.locator("#nav-student").click()
        page.locator("#hero-select").select_option("S015")
        assert page.locator("#hero-avatar img").get_attribute("src") == expected
        page.locator("#nav-game").click()
        assert expected in page.locator("#wiring svg image").evaluate_all("images=>images.map(image=>image.getAttribute('href'))")
        page.locator("#nav-math").click()
        page.locator('[data-stage="annealing"]').click()
        page.wait_for_function("Object.keys(window.__portraitAudit.drawCounts).includes('room-stage')")
        assert expected in page.evaluate("window.__portraitAudit.drawUrls['room-stage']")
        assert stale_hits == ["tab2.js"], "Portrait loading requested additional stale modules"
        assert not errors and not unexpected
        assert not page.evaluate("window.__portraitAudit.beacons")
        assert not page.evaluate("window.__portraitAudit.sockets")
    finally:
        context.close()


def test_incompatible_versioned_view_shows_recovery_before_reading_files(browser, asset_server):
    _, release, _ = entry_release()
    context = browser.new_context()
    page = context.new_page()
    mismatch = {"enabled": True, "requests": 0}
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def inconsistent_cache(route):
        parsed = urlsplit(route.request.url)
        if mismatch["enabled"] and parsed.path == "/tab2.js" and parse_qs(parsed.query).get("v") == [release]:
            mismatch["requests"] += 1
            route.fulfill(status=200, content_type="application/javascript", body=legacy_tab("tab2.js"))
        else:
            route.continue_()

    context.route("**/*", inconsistent_cache)
    try:
        page.goto(asset_server, wait_until="networkidle")
        page.locator("#reload-page").wait_for(state="visible")
        assert mismatch["requests"] == 1
        text = page.locator("#loading").inner_text()
        assert "older version" in text and "Reload" in text
        assert "is not a function" not in text
        assert page.locator("#portrait-controls").is_hidden()
        assert page.locator("#portrait-folder").evaluate("input=>input.files.length") == 0
        assert not errors
        mismatch["enabled"] = False
        page.locator("#reload-page").click()
        page.wait_for_function("document.getElementById('loading')?.hidden === true")
        assert parse_qs(urlsplit(page.url).query).get("v"), "Recovery should request a fresh document"
        assert page.locator("#portrait-load").is_enabled()
        assert page.locator("#reload-page").count() == 0
        assert not errors
    finally:
        context.close()
