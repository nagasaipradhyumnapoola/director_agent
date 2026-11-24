"""Serve the DIRECTOR landing page and console on loopback only.

This is a development/preview server, not the product API. It binds 127.0.0.1,
disables directory listings, and sends no-store + nosniff headers.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

WEB_DIR = Path(__file__).resolve().parent
ROOT = WEB_DIR.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _live_state() -> dict:
    root = Path(os.environ.get("DIRECTOR_UI_ROOT") or ROOT).resolve()
    from director import audit
    from director.store import Store

    store = Store.open(root)
    try:
        status = store.status_summary()
        acceptance = status.get("acceptance") or {}
        criteria = acceptance.get("criteria") or []
        satisfied = sum(1 for item in criteria if item.get("satisfied"))
        percent = round(100 * satisfied / len(criteria)) if criteria else 0
        evidence = status.get("evidence") or {}
        findings = status.get("findings") or {}
        lifecycle = (status.get("lifecycle") or {}).get("lifecycle") or {}
        patches = []
        for patch in store.list_patches(limit=5):
            patches.append(
                {
                    "id": patch["id"],
                    "title": patch["title"],
                    "status": patch["status"],
                    "detail": (patch.get("test_summary") or "")[:160],
                }
            )
        logs = audit.read(store, limit=12)
        return {
            "ok": True,
            "project": {
                "name": status["project"]["name"],
                "release": "live project",
                "domain": (status.get("contract") or {}).get("domains", ["general"])[0],
                "commit": "HEAD",
            },
            "worker": {
                "status": lifecycle.get("status", "unknown"),
                "heartbeat_age_seconds": (status.get("lifecycle") or {}).get("heartbeat", {}).get("age_seconds"),
            },
            "kpis": [
                {"label": "Acceptance", "value": f"{percent}%", "delta": f"{satisfied}/{len(criteria)} criteria", "tone": "up" if acceptance.get("complete") else ""},
                {"label": "Evidence", "value": str(sum(int(v) for v in evidence.values() if isinstance(v, int))), "delta": "receipts by outcome", "tone": ""},
                {"label": "Model calls", "value": str(status.get("model_calls_spent", 0)), "delta": "owner-granted only", "tone": ""},
                {"label": "Findings", "value": str(sum(int(v) for v in findings.values() if isinstance(v, int))), "delta": "deterministic scan", "tone": ""},
            ],
            "acceptance": {
                "complete": bool(acceptance.get("complete")),
                "percent": percent,
                "criteria": [
                    {
                        "key": item.get("criterion_key", ""),
                        "label": item.get("criterion_key", ""),
                        "state": "pass" if item.get("satisfied") else "fail",
                        "evidence": item.get("evidence_id") or "—",
                    }
                    for item in criteria
                ],
            },
            "patches": patches,
            "audit": [
                {"at": str(row.get("at", ""))[11:19], "actor": row.get("actor", ""), "action": row.get("action", ""), "outcome": row.get("outcome", "")}
                for row in logs
            ],
        }
    finally:
        store.close()


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

    def do_GET(self) -> None:  # noqa: N802
        if urlsplit(self.path).path == "/api/state":
            try:
                payload = _live_state()
                body = json.dumps(payload, default=str).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:  # noqa: BLE001
                body = json.dumps({"ok": False, "error": type(exc).__name__}).encode("utf-8")
                self.send_response(503)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            return
        super().do_GET()

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
