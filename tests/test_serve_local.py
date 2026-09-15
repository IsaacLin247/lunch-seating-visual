"""serve_local.py exposes only files inside the chosen directory, using a synthetic folder."""
from functools import partial
from http.server import ThreadingHTTPServer
import threading
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

import serve_local


@pytest.fixture
def server(tmp_path):
    folder = tmp_path / "student_directory"
    (folder / "11thgrade_files").mkdir(parents=True)
    (folder / "11thgrade.html").write_text("<table id='directory-items-container'></table>")
    (folder / "11thgrade_files" / "photo one.jpg").write_bytes(b"\xff\xd8\xff")
    (tmp_path / "outside.txt").write_text("not served")
    handler = partial(serve_local.Handler, directory=str(serve_local.DOCS), student_directory=folder.resolve())
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def status(url):
    try:
        with urlopen(url) as response:
            return response.status
    except HTTPError as error:
        error.close()
        return error.code


def test_serves_site_and_directory_files(server):
    assert status(f"{server}/index.html") == 200
    assert status(f"{server}/student_directory/11thgrade.html") == 200
    assert status(f"{server}/student_directory/11thgrade_files/photo%20one.jpg") == 200
    assert status(f"{server}/student_directory/12thgrade.html") == 404


def test_rejects_traversal_and_listings(server):
    assert status(f"{server}/student_directory/%2e%2e/outside.txt") == 404
    assert status(f"{server}/student_directory/") == 404
    assert status(f"{server}/student_directory/11thgrade_files/") == 404
