"""Serve the DIRECTOR landing page and console on loopback only.

This is a development/preview server, not the product API. It binds 127.0.0.1,
disables directory listings, and sends no-store + nosniff headers.
"""

from __future__ import annotations

import argparse
import os
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
        ".html": "text/html; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
    }

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def list_directory(self, path):  # noqa: ANN001
        self.send_error(404, "Not found")
        return None

    def log_message(self, fmt: str, *args) -> None:  # noqa: ANN002
        if os.environ.get("DIRECTOR_UI_LOG"):
            super().log_message(fmt, *args)


def make_server(web_dir: Path = WEB_DIR, port: int = 8765) -> ThreadingHTTPServer:
    directory = str(web_dir)

    class Bound(Handler):
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            super().__init__(*args, directory=directory, **kwargs)

    return ThreadingHTTPServer(("127.0.0.1", port), Bound)


def serve(port: int = 8765, open_browser: bool = True, web_dir: Path = WEB_DIR) -> int:
    server = make_server(web_dir, port)
    host, actual = server.server_address[:2]
    url = f"http://{host}:{actual}/"
    print(f"DIRECTOR UI: {url}")
    print("Loopback only. Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the DIRECTOR UI on loopback")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    return serve(port=args.port, open_browser=not args.no_open)


if __name__ == "__main__":
    raise SystemExit(main())
