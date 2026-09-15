#!/usr/bin/env python3
"""Serve the demo locally with a saved student directory at /student_directory/.

    python serve_local.py [--port 8000] [--directory PATH]

The page loads names and photos from that route on startup, with no folder
picker. The directory stays where it is on disk and is never copied into docs/,
so GitHub Pages and the tests never serve it. The server listens on localhost only.
"""
from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
DEFAULT_DIRECTORY = Path.home() / "Downloads" / "directory" / "student_directory"
PREFIX = "/student_directory/"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, student_directory: Path, **kwargs):
        self.student_directory = student_directory
        super().__init__(*args, **kwargs)

    def translate_path(self, path: str) -> str:
        route = unquote(urlsplit(path).path)
        if not route.startswith(PREFIX):
            return super().translate_path(path)
        target = (self.student_directory / route[len(PREFIX):]).resolve()
        # Only files inside the directory: no traversal and no folder listings.
        if self.student_directory not in target.parents or target.is_dir():
            return str(self.student_directory / ".missing")
        return str(target)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve docs/ with a local student directory.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY,
                        help="saved student_directory folder (default: %(default)s)")
    args = parser.parse_args()
    student_directory = args.directory.expanduser().resolve()
    if not (student_directory / "11thgrade.html").is_file():
        print(f"Warning: no grade exports in {student_directory}; the page will show anonymous avatars.")
    handler = partial(Handler, directory=str(DOCS), student_directory=student_directory)
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Serving http://localhost:{args.port} with names and photos from {student_directory}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
