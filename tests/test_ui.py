from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from director.ui import find_web_dir
from web.serve import make_server


def test_ui_assets_exist():
    root = find_web_dir()
    for relative in (
        "index.html",
        "app.html",
        "data.json",
        "assets/styles.css",
        "assets/app.js",
        "assets/site.js",
        "assets/character.svg",
        "serve.py",
    ):
        assert (root / relative).is_file(), relative
    payload = json.loads((root / "data.json").read_text(encoding="utf-8"))
    assert payload["project"]["release"] == "v1.0.0-local-supervised"
    assert payload["retrieval"][-1]["tier"] == "100M"


def test_ui_server_is_loopback_and_no_directory_listing():
    server = make_server(find_web_dir(), 0)
    host, port = server.server_address[:2]
    assert host == "127.0.0.1"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=10) as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert "DIRECTOR" in body
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert response.headers["X-Frame-Options"] == "DENY"
        with urllib.request.urlopen(f"http://{host}:{port}/data.json", timeout=10) as response:
            assert json.loads(response.read().decode("utf-8"))["demo"] is True
        try:
            urllib.request.urlopen(f"http://{host}:{port}/assets/", timeout=10)
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError("directory listing should be blocked")
    finally:
        server.shutdown()
        server.server_close()
