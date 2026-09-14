"""Optional Chromium regressions for browser-local demo portraits.

Run with ``python -m pytest tests/test_room_portraits.py`` after installing
Playwright and its Chromium browser. All image fixtures are generated colors;
these tests never read or export the school's directory or real photographs.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest


@pytest.fixture(scope="module")
def browser_origin():
    playwright = pytest.importorskip("playwright.sync_api")

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

    docs = Path(__file__).resolve().parents[1] / "docs"
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(docs)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with playwright.sync_playwright() as runtime:
            try:
                browser = runtime.chromium.launch(headless=True)
            except playwright.Error as exc:
                pytest.skip(f"Chromium is not installed: {exc}")
            yield browser, f"http://127.0.0.1:{server.server_port}"
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def page(browser_origin):
    browser, origin = browser_origin
    page = browser.new_page(viewport={"width": 1400, "height": 1000})
    page.goto(f"{origin}/data/index.json")
    page.set_content('<canvas id="room" style="width:1000px;height:600px" role="img" aria-label="Original chart"></canvas>')
    page.evaluate("""async () => {
      const html = await (await fetch('/index.html')).text();
      const entry = new DOMParser().parseFromString(html, 'text/html').querySelector('script[type="module"]');
      window.moduleQuery = new URL(entry.getAttribute('src'), location.origin).search;
      window.RoomView = (await import('/room.js' + moduleQuery)).RoomView;
      window.trace = await (await fetch('/data/honest.json')).json();
      window.waitFor = async predicate => {
        for (let i = 0; i < 200; i++) {
          if (predicate()) return;
          await new Promise(resolve => setTimeout(resolve, 10));
        }
        throw Error('Timed out waiting for a browser image or repaint');
      };
      window.colorBlob = async color => {
        const image = document.createElement('canvas'); image.width = 80; image.height = 120;
        image.getContext('2d').fillStyle = color; image.getContext('2d').fillRect(0, 0, 80, 120);
        return URL.createObjectURL(await new Promise(resolve => image.toBlob(resolve, 'image/png')));
      };
      window.pixel = (room, id, dx = 0, dy = 0) => {
        const p = room.pos.get(id), dpr = devicePixelRatio || 1;
        return [...room.ctx.getImageData(Math.round((p.x + dx) * dpr), Math.round((p.y + dy) * dpr), 1, 1).data];
      };
    }""")
    yield page
    page.close()


def test_circular_photo_outcome_ring_and_accessible_inspection(page):
    result = page.evaluate("""async () => {
      const canvas = document.querySelector('canvas'), events = [], id = trace.students[0].id;
      const url = await colorBlob('rgb(231,13,27)');
      const room = new RoomView(canvas, trace, {portraitProvider: sid => sid === id ? url : null,
        onSelectTable: info => events.push(info), showHoverFriends: false});
      room.draw();
      await waitFor(() => room._portraitCache.get(url)?.ready); room.draw();
      const center = pixel(room, id), corner = pixel(room, id, room.dotR * .9, room.dotR * .9);
      const ring = pixel(room, id, room.dotR + .5, 0);
      const table = room.rotInfo(0).tableOf.get(id), point = room.tableXY[table], rect = canvas.getBoundingClientRect();
      canvas.dispatchEvent(new MouseEvent('click', {clientX: point.x + rect.left, clientY: point.y + rect.top, bubbles: true}));
      const clicked = events.at(-1);
      canvas.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true}));
      canvas.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
      const keyboard = events.at(-1), role = canvas.getAttribute('role'), pointer = canvas.style.cursor;
      room.destroy(); URL.revokeObjectURL(url);
      return {center, corner, ring, clicked, keyboard, role, pointer, table};
    }""")
    assert result["center"] == [231, 13, 27, 255]
    assert result["corner"][:3] != [231, 13, 27]
    assert result["ring"][:3] != [231, 13, 27]
    assert result["clicked"]["table"] == result["table"]
    assert set(result["clicked"]) == {"table", "index", "ids", "key"}
    assert result["keyboard"]["table"] == (result["table"] + 1) % 40
    assert result["role"] == "button"
    assert result["pointer"] == "pointer"


def test_zoom_and_rotation_resizes_rebuild_every_target(page):
    result = page.evaluate("""() => {
      const canvas = document.querySelector('canvas');
      const room = new RoomView(canvas, trace, {portraitProvider: () => null, showAvatars: false});
      let checked = 0, rebuilt = true, contained = true;
      for (const [width, height] of [[320, 360], [800, 480], [1600, 960], [2400, 1440]]) {
        for (let rotation = 0; rotation < trace.rotations.length; rotation++) {
          room.goTo(rotation, false);
          const old = room.rotInfo(rotation).target;
          canvas.style.width = `${width}px`; canvas.style.height = `${height}px`; room.resize();
          const current = room.rotInfo(rotation).target;
          rebuilt &&= old !== current;
          for (const id of room.students) {
            const p = room.pos.get(id), target = current.get(id), r = room.dotR;
            contained &&= p.x - r >= 0 && p.x + r <= room.w && p.y - r >= 0 && p.y + r <= room.h;
            rebuilt &&= p.x === target.x && p.y === target.y;
            checked++;
          }
        }
      }
      const radiusAtZoom = room.dotR;
      room.goTo(0, true); room.resize();
      const noStaleAnimation = room.anim === null;
      room.destroy(); return {checked, rebuilt, contained, radiusAtZoom, noStaleAnimation};
    }""")
    assert result["checked"] >= 4 * 257
    assert result["rebuilt"]
    assert result["contained"]
    assert result["radiusAtZoom"] == 28
    assert result["noStaleAnimation"]


def test_nonblob_rejected_and_shared_fallback_repaints_both_rooms(page):
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    result = page.evaluate("""async () => {
      const canvasA = document.querySelector('canvas'), canvasB = canvasA.cloneNode();
      document.body.append(canvasB);
      const opts = {portraitProvider: () => 'https://invalid.example/never-fetch-a-photo.jpg'};
      const a = new RoomView(canvasA, trace, opts), b = new RoomView(canvasB, trace, opts);
      let imagesA = 0, imagesB = 0;
      const drawA = a.ctx.drawImage.bind(a.ctx), drawB = b.ctx.drawImage.bind(b.ctx);
      a.ctx.drawImage = (...args) => { imagesA++; drawA(...args); };
      b.ctx.drawImage = (...args) => { imagesB++; drawB(...args); };
      a.draw(); b.draw();
      const bothWaiting = a._pendingAvatars.size > 0 && b._pendingAvatars.size > 0;
      await waitFor(() => imagesA >= trace.students.length && imagesB >= trace.students.length);
      const noPhotoCache = a._portraitCache.size === 0 && b._portraitCache.size === 0;
      a.destroy(); b.destroy(); return {imagesA, imagesB, bothWaiting, noPhotoCache};
    }""")
    assert result["bothWaiting"]
    assert result["imagesA"] >= 257
    assert result["imagesB"] >= 257
    assert result["noPhotoCache"]
    assert not any("invalid.example" in request for request in requests)


def test_tab_replacement_clear_and_no_rich_hover_on_photos(page):
    result = page.evaluate("""async () => {
      const {createTab1} = await import('/tab1.js' + moduleQuery);
      const canvas = document.querySelector('canvas'); canvas.id = 'room-random';
      const other = canvas.cloneNode(); other.id = 'room-proposed'; document.body.append(other);
      const changed = [], tooltips = [], inspections = [];
      const originalSetOpts = RoomView.prototype.setOpts;
      RoomView.prototype.setOpts = function(opts) { if (!changed.includes(this)) changed.push(this); return originalSetOpts.call(this, opts); };
      const tab = createTab1({traces: {honest: trace}, showTooltip: info => tooltips.push(info), onPortraitTable: info => inspections.push(info)});
      const id = trace.students[0].id, red = await colorBlob('rgb(231,13,27)'), blue = await colorBlob('rgb(13,27,231)');
      tab.setPortraits(new Map([[id, red]])); changed.forEach(room => room.draw());
      await waitFor(() => changed.every(room => room._portraitCache.get(red)?.ready));
      const staleCallbacks = changed.map(room => room._portraitCache.get(red).image.onload);
      tab.setPortraits(new Map([[id, blue]]));
      const replacedCleanly = changed.every(room => !room._portraitCache.has(red));
      changed.forEach(room => room.draw());
      await waitFor(() => changed.every(room => room._portraitCache.get(blue)?.ready)); changed.forEach(room => room.draw());
      const bluePixels = changed.map(room => pixel(room, id));
      const noDetailedHover = changed.every(room => room.opts.onHover === null && room.opts.showHoverFriends === false);
      const selected = tab.selectTable(0, 'tablesRandom'), inspection = inspections.at(-1);
      tab.clearPortraits(); URL.revokeObjectURL(red); URL.revokeObjectURL(blue);
      let staleRedraws = 0;
      for (const room of changed) room.requestDraw = () => { staleRedraws++; };
      staleCallbacks.forEach(callback => callback());
      const clean = changed.every(room => room._portraitCache.size === 0 && room.opts.portraitProvider === null && !room.opts.showAvatars && room.opts.showHoverFriends && room.opts.onHover);
      const noSelectionAfterClear = tab.selectTable(0) === false;
      tab.destroy(); RoomView.prototype.setOpts = originalSetOpts;
      return {replacedCleanly, bluePixels, noDetailedHover, selected, inspection, clean, noSelectionAfterClear, staleRedraws, tooltipPayloads: tooltips.filter(Boolean).length};
    }""")
    assert result["replacedCleanly"]
    assert result["bluePixels"] == [[13, 27, 231, 255], [13, 27, 231, 255]]
    assert result["noDetailedHover"]
    assert result["selected"]
    assert result["inspection"]["key"] == "tablesRandom"
    assert result["clean"]
    assert result["noSelectionAfterClear"]
    assert result["staleRedraws"] == 0
    assert result["tooltipPayloads"] == 0
