#!/usr/bin/env python3
"""Local preview server with extensionless URLs like GitHub Pages."""

from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class SiteHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def resolve_clean_url(self, url_path: str) -> Path | None:
        url_path = url_path.split("?", 1)[0].split("#", 1)[0]
        if url_path != "/" and url_path.endswith("/"):
            url_path = url_path.rstrip("/")

        if url_path == "/":
            candidates = [ROOT / "index.html"]
        else:
            rel = url_path.lstrip("/")
            candidates = [ROOT / rel / "index.html", ROOT / f"{rel}.html"]

        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def do_GET(self):
        resolved = self.resolve_clean_url(self.path)
        if resolved is not None:
            self.path = "/" + resolved.relative_to(ROOT).as_posix()
        return super().do_GET()


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview thomasguest.art locally.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", "-p", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), SiteHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Serving {ROOT}")
    print(f"Preview at {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
