"""Locate and serve the DIRECTOR landing page + console."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

from .security import ValidationError


def find_web_dir() -> Path:
    env = os.environ.get("DIRECTOR_WEB_DIR")
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.append(Path.cwd() / "web")
    candidates.append(Path(__file__).resolve().parents[2] / "web")
    for candidate in candidates:
        if (candidate / "index.html").is_file() and (candidate / "serve.py").is_file():
            return candidate.resolve()
    raise ValidationError(
        "web UI not found; run from the repository root or set DIRECTOR_WEB_DIR"
    )


def serve_ui(
    port: int = 8765,
    open_browser: bool = True,
    web_dir: str | Path | None = None,
) -> int:
    directory = Path(web_dir).resolve() if web_dir else find_web_dir()
    if not (directory / "index.html").is_file():
        raise ValidationError("web dir has no index.html")
    if not 0 <= port <= 65535:
        raise ValidationError("port must be 0-65535")

    spec = importlib.util.spec_from_file_location("_director_web_serve", directory / "serve.py")
    if spec is None or spec.loader is None:
        raise ValidationError("could not load the UI server")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    serve: Any = getattr(module, "serve")
    return int(serve(port=port, open_browser=open_browser, web_dir=directory))
