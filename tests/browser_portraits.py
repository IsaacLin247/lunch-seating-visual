#!/usr/bin/env python3
"""Optional Playwright privacy/workflow check for browser-local portraits.

Run with the research environment:
    .venv/bin/python tests/browser_portraits.py

The script serves docs/ temporarily on localhost:8092, uses only generated
synthetic portraits, and writes no screenshots. --real-directory optionally
checks a local roster and reports aggregate counts only. No files are uploaded.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import re
import threading
import tempfile
from urllib.parse import urlsplit

from PIL import Image
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
STATS = ["s-rand-ge1", "s-rand-ex1", "s-rand-met", "s-prop-ge1", "s-prop-ex1", "s-prop-met"]
CANARY = "PRIVATE_FIXTURE_STUDENT"
EXIF_CANARY = "PRIVATE_EXIF_METADATA_MUST_BE_REMOVED"


INSTRUMENT = r"""
(() => {
  const audit = window.__portraitAudit = {
    beacons: [], sockets: [], events: [], drawCounts: {}, drawUrls: {}, invalidDraws: [],
    activeUrls: new Set(), revoked: 0, violations: [], xss: false
  };
  document.addEventListener('securitypolicyviolation', event => audit.violations.push({
    directive: event.violatedDirective, blocked: event.blockedURI
  }));
  const originalUrl = URL.createObjectURL.bind(URL);
  URL.createObjectURL = value => { const url = originalUrl(value); audit.activeUrls.add(url); return url; };
  const revoke = URL.revokeObjectURL.bind(URL);
  URL.revokeObjectURL = url => { audit.activeUrls.delete(url); audit.revoked++; return revoke(url); };
  navigator.sendBeacon = (...args) => { audit.beacons.push(String(args[0])); return false; };
  for (const key of ['WebSocket', 'EventSource']) {
    if (window[key]) window[key] = class {
      constructor(url) { audit.sockets.push(String(url)); throw new Error('Unexpected external communication'); }
    };
  }
  const draw = CanvasRenderingContext2D.prototype.drawImage;
  const bitmapSources = new WeakMap();
  CanvasRenderingContext2D.prototype.drawImage = function(image, ...coordinates) {
    const source = typeof image?.src === 'string' ? image.src : '';
    const sources = source.startsWith('blob:') ? [source] : [...(bitmapSources.get(image) || [])];
    if (sources.length) {
      const key = this.canvas.id || 'normalizer';
      audit.drawCounts[key] = (audit.drawCounts[key] || 0) + 1;
      const accumulated = new Set(bitmapSources.get(this.canvas) || []);
      for (const url of sources) accumulated.add(url);
      bitmapSources.set(this.canvas, accumulated);
      audit.drawUrls[key] = [...new Set([...(audit.drawUrls[key] || []), ...sources])];
      if (coordinates.some(value => !Number.isFinite(value))) audit.invalidDraws.push(key);
    } else if (source.startsWith('data:') && !this.canvas.id) {
      bitmapSources.delete(this.canvas);
    }
    return draw.call(this, image, ...coordinates);
  };
})();
"""


def fixture(folder):
    """Seven distinct valid pictures, one broken picture, one remote source,
    and an otherwise valid grade-nine directory ignored by this demonstration.
    """
    for grade, count in ((11, 15), (12, 2), (9, 1)):
        image_dir = folder / f"{grade}thgrade_files"
        image_dir.mkdir(parents=True)
        rows = []
        for index in range(1, count + 1):
            image_name = f"portrait-{index}.jpg"
            if grade == 11 and index not in {1, 2, 3, 4, 15}:
                if index == 7:
                    (image_dir / "broken.jpg").write_bytes(b"This is deliberately not a JPEG image")
                    source = "./11thgrade_files/broken.jpg"
                elif index == 8:
                    source = "https://privacy-canary.invalid/portrait.jpg"
                else:
                    source = f"./11thgrade_files/missing-{index}.jpg"
                rows.append(row(f"g{grade}-{index:03}", grade, source))
                continue
            color = ((grade * 13 + index * 39) % 256, (grade * 7 + index * 73) % 256, (grade * 19 + index * 29) % 256)
            exif = Image.Exif()
            exif[270] = EXIF_CANARY
            Image.new("RGB", (100 + index * 10, 140 + index * 5), color).save(image_dir / image_name, "JPEG", exif=exif)
            rows.append(row(f"g{grade}-{index:03}", grade, f"./{grade}thgrade_files/{image_name}"))
        html = "<!doctype html><html><head><script>window.__portraitAudit.xss=true</script>" \
               "<link rel='stylesheet' href='https://privacy-canary.invalid/style.css'></head><body>" \
               "<table id='directory-items-container'><tbody>" + "".join(rows) + "</tbody></table>" \
               "<iframe src='https://privacy-canary.invalid/iframe'></iframe></body></html>"
        (folder / f"{grade}thgrade.html").write_text(html)
    return 7


def row(identifier, grade, photo):
    return f"<tr><td><img class='bb-avatar-image' src='{photo}' onerror='window.__portraitAudit.xss=true'></td>" \
           f"<td><h3>{CANARY} {identifier} '28</h3><button class='user-options-button' data-userid='{identifier}'></button>" \
           f"<p>PRIVATE_CONTACT_{grade}@example.invalid</p></td></tr>"


def wait_loaded(page):
    page.wait_for_function("document.getElementById('loading').hidden", timeout=30000)
    page.locator("#portrait-load").wait_for(state="visible")
    page.wait_for_function("!document.getElementById('portrait-load').disabled")


def wait_portraits(page, loaded=True, timeout=30000):
    page.wait_for_function("expected => document.body.classList.contains('portrait-mode') === expected", arg=loaded, timeout=timeout)
    if loaded:
        page.wait_for_function("!document.getElementById('portrait-load').disabled && !document.getElementById('portrait-clear').disabled")


def stats(page):
    return {identifier: page.locator(f"#{identifier}").inner_text() for identifier in STATS}


def canvas_hash(page, identifier):
    return page.locator(f"#{identifier}").evaluate("canvas => canvas.toDataURL()")


def expected_stats(rotation):
    values = rotation["stats"]
    return dict(zip(STATS, [
        f"{values['pctGe1Random']:.1f}%", f"{values['pctExactly1Random']:.1f}%", f"{values['meanDistinctMetRandom']:.1f}",
        f"{values['pctGe1']:.1f}%", f"{values['pctExactly1']:.1f}%", f"{values['meanDistinctMet']:.1f}",
    ]))


def choose_rotation(page, index):
    page.locator("#scrub").evaluate("(el,value) => { el.value=String(value); el.dispatchEvent(new Event('input',{bubbles:true})); }", index + 1)
    page.wait_for_timeout(150)
    assert int(page.locator("#rot-num").inner_text()) == index + 1


def inspect_table(page, trace, rotation, source, table):
    page.locator("#portrait-source").select_option(source)
    page.locator("#portrait-table").select_option(str(table))
    page.locator("#portrait-inspection").wait_for(state="visible")
    labels = re.findall(r"\bS\d{3}\b", page.locator("#portrait-seats").inner_text())
    expected = trace["rotations"][rotation][source][table]
    assert sorted(set(labels)) == sorted(expected), (rotation, source, table, labels, expected)
    return page.locator('#portrait-inspection img[src^="blob:"]').count()


def simulation_context(page):
    label = page.locator(".demo-label")
    assert label.is_visible()
    assert "simulat" in label.inner_text().lower()
    assert label.evaluate("element => !element.closest('[role=tabpanel]')"), "Simulation context should remain visible across tabs"
    assert CANARY in page.locator("body").text_content()
    assert "PRIVATE_CONTACT" not in page.locator("body").text_content()


def image_receipts(page, container, known_urls, required=None):
    images = page.locator(f"{container} img").evaluate_all("images => images.map(image => ({src:image.getAttribute('src'),alt:image.alt}))")
    seen = set()
    for image in images:
        match = re.search(r"\bS\d{3}\b", image["alt"])
        if match and match[0] in known_urls:
            assert image["src"] == known_urls[match[0]], (container, match[0], "portrait identity changed")
            seen.add(match[0])
        elif image["src"].startswith("blob:"):
            raise AssertionError(f"Unexpected or unlabeled directory portrait in {container}")
    if required:
        assert required in seen, (container, required, "mapped portrait missing")
    return len(seen)


def assert_student_stats(page, trace, hero, rotation):
    met, met_random, anchors = set(), set(), set()
    covered = covered_random = 0
    for row in trace["rotations"][:rotation + 1]:
        met.update(next(table for table in row["tables"] if hero in table))
        met_random.update(next(table for table in row["tablesRandom"] if hero in table))
        anchor = row["anchors"].get(hero)
        if anchor:
            covered += 1
            anchors.add(anchor)
        covered_random += bool(row["anchorsRandom"].get(hero))
    met.discard(hero)
    met_random.discard(hero)
    names = trace["listed"][next(index for index, student in enumerate(trace["students"]) if student["id"] == hero)]
    expected = {"y-guaranteed": f"{covered} / {rotation + 1}", "y-guaranteed-rand": f"{covered_random} / {rotation + 1}", "y-met": str(len(met)), "y-met-rand": str(len(met_random)), "y-anchors": f"{len(anchors)} of {len(names)}"}
    assert {key: page.locator(f"#{key}").inner_text() for key in expected} == expected


def selection_state(page):
    return page.evaluate("""() => ({
      tab:document.querySelector('.tab[aria-selected=true]')?.id,
      rotation:document.getElementById('scrub').value,
      hero:document.getElementById('hero-select').value,
      mode:document.querySelector('#scenario-modes [aria-pressed=true]')?.dataset.mode,
      stage:document.querySelector('#stage-controls [aria-pressed=true]')?.dataset.stage,
      student:['y-guaranteed','y-guaranteed-rand','y-met','y-met-rand','y-anchors'].map(id=>document.getElementById(id).textContent),
      coalition:['g-avg','g-max','g-ge1','g-intact'].map(id=>document.getElementById(id).textContent),
      algorithm:['stage-violations','stage-extra','stage-energy','stage-seconds'].map(id=>document.getElementById(id).textContent)
    })""")


def no_remaining_portraits(page):
    assert page.locator('img[src^="blob:"],svg image[href^="blob:"],svg image[xlink\\:href^="blob:"]').count() == 0
    assert page.evaluate("window.__portraitAudit.activeUrls.size") == 0
    assert not page.evaluate("window.__portraitAudit.beacons")
    assert not page.evaluate("window.__portraitAudit.sockets")
    assert not page.evaluate("window.__portraitAudit.violations")
    assert page.evaluate("window.__portraitAudit.xss") is False
    assert page.evaluate("async () => { const entry=new URL(document.querySelector('script[type=module][src]').src); const avatars=await import('./avatars.js'+entry.search); return ['S001','S015','S133'].every(id => !avatars.directoryPortraitUri(id)); }")
    assert CANARY not in page.locator("body").text_content()
    painted = page.evaluate("({...window.__portraitAudit.drawCounts})")
    for tab in ("nav-room", "nav-student", "nav-game", "nav-math"):
        page.locator(f"#{tab}").click()
        page.wait_for_timeout(100)
        assert page.locator('img[src^="blob:"],svg image[href^="blob:"]').count() == 0
    assert page.evaluate("window.__portraitAudit.drawCounts") == painted, "A hidden canvas or decoded bitmap redrew a removed portrait"


def check_all_views(page, trace, scenarios, known_urls):
    target = "S001"
    last = len(trace["rotations"]) - 1
    receipts = 0
    page.locator("#nav-student").click()
    choose_rotation(page, last)
    page.locator("#hero-select").select_option(target)
    simulation_context(page)
    receipts += image_receipts(page, "#hero-avatar", known_urls, target)
    assert_student_stats(page, trace, target, last)
    hero_candidates = [student["id"] for student, names in zip(trace["students"], trace["listed"]) if target in names]
    page.locator("#hero-select").select_option(hero_candidates[0])
    receipts += image_receipts(page, "#friend-strip", known_urls, target)
    for source, container in (("tables", "#avatar-wall"), ("tablesRandom", "#ghost-row")):
        hero = next(identifier for table in trace["rotations"][0][source] if target in table for identifier in table if identifier != target)
        page.locator("#hero-select").select_option(hero)
        receipts += image_receipts(page, container, known_urls, target)
        assert_student_stats(page, trace, hero, last)
    page.wait_for_timeout(200)
    assert known_urls[target] in page.evaluate("window.__portraitAudit.drawUrls['room-hero'] || []")

    page.locator("#nav-game").click()
    simulation_context(page)
    modes = page.locator("#scenario-modes button").evaluate_all("buttons=>buttons.map(button=>button.dataset.mode)")
    for mode in modes:
        page.locator(f'#scenario-modes [data-mode="{mode}"]').click()
        row = scenarios[mode]["rotations"][last]
        assert page.locator("#g-avg").inner_text() == f"{row['coalition']['avgCluster']:.2f}"
        assert page.locator("#g-max").inner_text() == str(row["coalition"]["maxCluster"])
        vectors = page.locator("#wiring svg image").evaluate_all("images=>images.map(image=>({url:image.getAttribute('href'),clip:image.getAttribute('clip-path')}))")
        mapped_svg = 0
        for vector in vectors:
            match = re.search(r"S\d{3}", vector["clip"])
            assert match
            if match[0] in known_urls:
                assert vector["url"] == known_urls[match[0]], (mode, match[0], "SVG identity changed")
                mapped_svg += 1
            else:
                assert not vector["url"].startswith("blob:")
        assert mapped_svg >= 1, (mode, "No coalition portrait was rendered")
        receipts += mapped_svg
        page.wait_for_timeout(100)
        assert known_urls["S015"] in page.evaluate("window.__portraitAudit.drawUrls['room-game'] || []")

    page.locator("#nav-math").click()
    simulation_context(page)
    stages = trace["rotations"][last]["pipeline"]
    for stage in stages:
        page.locator(f'[data-stage="{stage["name"]}"]').click()
        page.wait_for_timeout(150)
        assert int(page.locator("#stage-violations").inner_text()) == stage["cost"]["violations"]
        assert float(page.locator("#stage-energy").inner_text().replace(",", "")) == stage["cost"]["total"] / 10
        assert known_urls[target] in page.evaluate("window.__portraitAudit.drawUrls['room-stage'] || []")
    page.locator("#stage-replay").click()
    page.wait_for_function("document.querySelector('#stage-controls [data-stage=final]').getAttribute('aria-pressed') === 'true'", timeout=10000)
    assert int(page.locator("#stage-violations").inner_text()) == stages[-1]["cost"]["violations"]
    page.locator("#stage-replay").click()  # stop its final delay timer
    for tab, canvas in (("nav-student", "room-hero"), ("nav-game", "room-game"), ("nav-math", "room-stage")):
        page.locator(f"#{tab}").click()
        page.locator("#portrait-zoom").select_option("1")
        page.wait_for_timeout(100)
        baseline = page.locator(f"#{canvas}").bounding_box()
        for zoom in ("1.5", "2", "3"):
            page.locator("#portrait-zoom").select_option(zoom)
            page.wait_for_timeout(100)
            bounds = page.locator(f"#{canvas}").bounding_box()
            assert bounds and baseline and bounds["width"] >= baseline["width"] * float(zoom) * 0.98
            assert not page.evaluate("window.__portraitAudit.invalidDraws")
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(150)
        assert not page.evaluate("document.documentElement.scrollWidth > innerWidth + 1"), f"Mobile portrait zoom escapes {tab}"
        page.set_viewport_size({"width": 1440, "height": 1100})
        page.locator("#portrait-zoom").select_option("1")
    return {"additionalIdentityReceipts": receipts, "coalitionModesChecked": len(modes), "algorithmStagesChecked": len(stages), "algorithmReplayChecked": True, "allPageZoomAndMobileChecked": True}


def load_and_clear_from_each_tab(page, fixture_folder):
    page.locator("#portrait-clear").click()
    page.wait_for_timeout(150)
    no_remaining_portraits(page)
    visited = []
    for tab in ("nav-student", "nav-game", "nav-math"):
        page.locator(f"#{tab}").click()
        choose_rotation(page, 1)
        if tab == "nav-student":
            page.locator("#hero-select").select_option("S015")
        elif tab == "nav-game":
            page.locator('#scenario-modes [data-mode="coalition_shared_anchor"]').click()
        else:
            page.locator('[data-stage="annealing"]').click()
        before = selection_state(page)
        page.locator("#portrait-folder").set_input_files(str(fixture_folder))
        wait_portraits(page)
        assert selection_state(page) == before, f"Loading photos changed the selected simulation state on {tab}"
        simulation_context(page)
        if tab == "nav-student":
            assert page.locator('#hero-avatar img[src^="blob:"]').count() == 1
        elif tab == "nav-game":
            assert page.locator('#wiring image[href^="blob:"]').count() >= 1
        page.locator("#portrait-clear").click()
        assert selection_state(page) == before, f"Clearing photos changed the selected simulation state on {tab}"
        no_remaining_portraits(page)
        visited.append(tab)
    return visited


def run(args):
    trace_path = ROOT / "docs/data/honest.json"
    trace_bytes = trace_path.read_bytes()
    trace = json.loads(trace_bytes)
    scenarios = {path.stem: json.loads(path.read_text()) for path in (ROOT / "docs/data").glob("coalition*.json")}
    trace_hash = hashlib.sha256(trace_bytes).hexdigest()
    server = None
    if args.base_url:
        base = args.base_url.rstrip("/") + "/"
    else:
        class QuietHandler(SimpleHTTPRequestHandler):
            def __init__(self, *positional, **keywords):
                super().__init__(*positional, directory=str(ROOT / "docs"), **keywords)

            def log_message(self, *unused):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", args.port), QuietHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}/"
    parsed_base = urlsplit(base)
    try:
        loopback = ipaddress.ip_address(parsed_base.hostname or "").is_loopback
    except ValueError:
        loopback = parsed_base.hostname == "localhost"
    if parsed_base.scheme not in {"http", "https"} or not loopback:
        raise ValueError("Browser portrait checks must target a localhost or loopback server.")
    expected_origin = (parsed_base.scheme, parsed_base.netloc)
    report = {"syntheticPhotos": 7, "externalRequests": 0, "writeRequests": 0, "traceSha256": trace_hash}
    try:
        with tempfile.TemporaryDirectory(prefix="seating-portrait-fixture-") as temporary, sync_playwright() as playwright:
            fixture_folder = Path(temporary) / "synthetic_directory"
            fixture_folder.mkdir()
            expected_photos = fixture(fixture_folder)
            browser = playwright.chromium.launch(executable_path=args.chrome, headless=True, args=["--no-sandbox"])
            try:
                context = browser.new_context(viewport={"width": 1440, "height": 1100}, reduced_motion="reduce")
                context.add_init_script(INSTRUMENT)
                requests, blocked, errors = [], [], []

                def route_request(route):
                    request = route.request
                    target = urlsplit(request.url)
                    if target.scheme in {"data", "blob"}:
                        route.continue_()
                        return
                    entry = {"method": request.method, "type": request.resource_type, "url": request.url}
                    requests.append(entry)
                    if (target.scheme, target.netloc) != expected_origin or request.method not in {"GET", "HEAD"}:
                        blocked.append(entry)
                        route.abort()
                    else:
                        route.continue_()
                context.route("**/*", route_request)
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base, wait_until="networkidle")
                wait_loaded(page)
                report["assetRelease"] = page.evaluate("new URL(document.querySelector('script[type=module][src]').src).searchParams.get('v')")
                initial_stats = stats(page)
                assert initial_stats == expected_stats(trace["rotations"][0])
                initial_canvas = canvas_hash(page, "room-proposed")
                assert not blocked, "The page attempted external network access before photo import"
                request_count = len(requests)
                page.locator("#portrait-folder").set_input_files(str(fixture_folder))
                wait_portraits(page)
                page.wait_for_timeout(300)
                assert stats(page) == initial_stats
                assert canvas_hash(page, "room-proposed") != initial_canvas
                assert CANARY in page.locator("body").text_content()
                assert "PRIVATE_CONTACT" not in page.locator("body").text_content()
                assert page.evaluate("window.__portraitAudit.xss") is False
                assert page.locator("#portrait-status").get_attribute("role") == "status"
                assert len(requests) == request_count, "Local import unexpectedly requested another HTTP resource"
                import_requests = len(requests) - request_count
                assert [int(number) for number in re.findall(r"\d+", page.locator("#portrait-status").inner_text())] == [17, expected_photos, len(trace["students"]) - expected_photos]
                assert not page.evaluate("window.__portraitAudit.violations"), "Imported HTML attempted a blocked resource or script"
                assert page.locator('#hero-select option[value="S001"]').inner_text().startswith(f"{CANARY} g11-001 (S001)")
                # A missing photo must not shift this or any later student's name.
                assert page.locator('#hero-select option[value="S005"]').inner_text().startswith(f"{CANARY} g11-005 (S005)")
                assert page.locator('#hero-select option[value="S015"]').inner_text().startswith(f"{CANARY} g11-015 (S015)")
                mapped_first = next(s["id"] for s in trace["students"] if s["grade"] == 11)
                table_index = next(index for index, table in enumerate(trace["rotations"][0]["tables"]) if mapped_first in table)
                assert inspect_table(page, trace, 0, "tables", table_index) >= 1
                sizes = page.locator('#portrait-inspection img[src^="blob:"]').evaluate_all("images => images.map(img => ({width:img.getBoundingClientRect().width,height:img.getBoundingClientRect().height,loaded:img.complete&&img.naturalWidth>0}))")
                assert sizes and all(size["loaded"] and size["width"] >= 60 and size["height"] >= 60 for size in sizes), sizes
                normalized = page.locator('#portrait-inspection img[src^="blob:"]').first.evaluate("async image => { const bytes=new Uint8Array(await (await fetch(image.src)).arrayBuffer()); return {jpeg:bytes[0]===255&&bytes[1]===216,metadata:new TextDecoder('latin1').decode(bytes).includes('PRIVATE_EXIF_METADATA_MUST_BE_REMOVED')}; }")
                assert normalized == {"jpeg": True, "metadata": False}
                # Match every usable fixture portrait's pixels to its synthetic
                # grade slot, not merely the number of images in the room.
                mapped_receipts = 0
                known_urls = {}
                for grade, offsets in ((11, (0, 1, 2, 3, 14)), (12, (0, 1))):
                    slots = sorted(s["id"] for s in trace["students"] if s["grade"] == grade)
                    for offset in offsets:
                        identifier = slots[offset]
                        index = next(i for i, table in enumerate(trace["rotations"][0]["tables"]) if identifier in table)
                        inspect_table(page, trace, 0, "tables", index)
                        card = page.locator(f'.portrait-seat[data-id="{identifier}"]')
                        known_urls[identifier] = card.locator('img[src^="blob:"]').get_attribute("src")
                        pixel = card.locator('img[src^="blob:"]').evaluate("async image => { await image.decode(); const canvas=document.createElement('canvas'); canvas.width=canvas.height=1; const ctx=canvas.getContext('2d'); ctx.drawImage(image,0,0,1,1); return [...ctx.getImageData(0,0,1,1).data].slice(0,3); }")
                        value = offset + 1
                        expected = [(grade * 13 + value * 39) % 256, (grade * 7 + value * 73) % 256, (grade * 19 + value * 29) % 256]
                        assert all(abs(actual - wanted) <= 4 for actual, wanted in zip(pixel, expected)), (identifier, pixel, expected)
                        mapped_receipts += 1
                assert page.evaluate("Object.keys(window.__portraitAudit.drawCounts).includes('room-proposed')")
                assert page.evaluate("Object.keys(window.__portraitAudit.drawCounts).includes('room-random')")
                inspected = []
                for rotation in (0, 1, len(trace["rotations"]) - 1):
                    choose_rotation(page, rotation)
                    assert stats(page) == expected_stats(trace["rotations"][rotation])
                    for source in ("tables", "tablesRandom"):
                        for table in (0, len(trace["rotations"][rotation][source]) - 1):
                            inspect_table(page, trace, rotation, source, table)
                            inspected.append([rotation, source, table])
                for zoom in ("1.5", "2", "3", "1"):
                    page.locator("#portrait-zoom").select_option(zoom)
                    page.wait_for_timeout(100)
                    bounds = page.locator("#room-proposed").bounding_box()
                    assert bounds and bounds["width"] > 100 and bounds["height"] > 100
                    assert not page.evaluate("window.__portraitAudit.invalidDraws")
                report.update(check_all_views(page, trace, scenarios, known_urls))
                page.locator("#nav-room").click()
                page.set_viewport_size({"width": 390, "height": 844})
                page.wait_for_timeout(250)
                assert not page.evaluate("document.documentElement.scrollWidth > innerWidth + 1"), "Mobile page overflows"
                page.locator("#portrait-zoom").select_option("3")
                page.wait_for_timeout(150)
                assert not page.evaluate("document.documentElement.scrollWidth > innerWidth + 1"), "Zoom escapes its room scroll container"
                page.set_viewport_size({"width": 1440, "height": 1100})
                page.locator("#portrait-zoom").select_option("1")
                choose_rotation(page, 0)
                page.locator("#portrait-clear").click()
                wait_portraits(page, loaded=False)
                assert page.locator("#portrait-inspection").is_hidden()
                page.wait_for_timeout(200)
                assert stats(page) == initial_stats
                assert canvas_hash(page, "room-proposed") == initial_canvas, "Clearing photos did not restore the original colored chart"
                assert page.evaluate("window.__portraitAudit.activeUrls.size") == 0
                assert page.evaluate("window.__portraitAudit.revoked") >= expected_photos
                no_remaining_portraits(page)
                assert not page.evaluate("window.__portraitAudit.beacons")
                assert not page.evaluate("window.__portraitAudit.sockets")
                assert not blocked, "The page attempted a network write or external request"
                assert not errors, errors
                assert hashlib.sha256(trace_path.read_bytes()).hexdigest() == trace_hash
                report.update(tablesChecked=len(inspected), mappedPortraitReceipts=mapped_receipts, rotationsChecked=3, zoomLevelsChecked=4, javaScriptErrors=errors, localImportRequests=import_requests, subsequentLocalAssetRequests=len(requests)-request_count, metadataRemoved=True, objectUrlsCleared=True, originalChartRestored=True)
                page.locator("#nav-room").click()
                page.locator("#portrait-folder").set_input_files(str(fixture_folder))
                wait_portraits(page)
                report["nonRoomLoadAndClearTabs"] = load_and_clear_from_each_tab(page, fixture_folder)
                page.locator("#portrait-folder").set_input_files(str(fixture_folder))
                wait_portraits(page)
                assert page.evaluate("window.__portraitAudit.activeUrls.size") > 0
                page.reload(wait_until="networkidle")
                wait_loaded(page)
                assert not page.locator("body").evaluate("body=>body.classList.contains('portrait-mode')")
                assert page.evaluate("window.__portraitAudit.activeUrls.size") == 0
                assert canvas_hash(page, "room-proposed") == initial_canvas
                report["reloadClearsPortraits"] = True
                if args.real_directory:
                    page.locator("#portrait-folder").set_input_files(str(args.real_directory.resolve()))
                    wait_portraits(page, timeout=120000)
                    assert not blocked
                    report["realDirectory"] = {"loaded": True, "objectUrls": page.evaluate("window.__portraitAudit.activeUrls.size")}
                    page.locator("#portrait-clear").click()
                    assert page.evaluate("window.__portraitAudit.activeUrls.size") == 0
                assert not blocked, "A later tab or reload attempted a network write or external request"
                assert not errors, errors
                assert not page.evaluate("window.__portraitAudit.violations")
                context.close()
            finally:
                browser.close()
    finally:
        if server:
            server.shutdown()
            server.server_close()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8092)
    parser.add_argument("--base-url", help="Use an already-running local docs server")
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    parser.add_argument("--real-directory", type=Path, help="Optional private aggregate-only check; never writes images or real names")
    run(parser.parse_args())
