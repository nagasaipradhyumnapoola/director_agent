"""Append-only, redacted JSONL audit log with simple rotation."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Mapping

from .security import dump_bounded, redact_text
from .store import Store, utc_now

MAX_BYTES = 5 * 1024 * 1024


def _path(store: Store) -> Path:
    directory = Path(store.root) / ".director" / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "audit.jsonl"


def log(
    store: Store,
    actor: str,
    action: str,
    resource: str = "",
    outcome: str = "ok",
    meta: Mapping[str, Any] | None = None,
) -> None:
    try:
        path = _path(store)
        try:
            if path.stat().st_size > MAX_BYTES:
                backup = path.with_suffix(".jsonl.1")
                if backup.exists():
                    backup.unlink()
                path.replace(backup)
        except OSError:
            pass
        record = {
            "at": utc_now(),
            "actor": redact_text(str(actor))[:200],
            "action": redact_text(str(action))[:200],
            "resource": redact_text(str(resource))[:500],
            "outcome": redact_text(str(outcome))[:100],
            "meta": dict(meta or {}),
        }
        text, _ = dump_bounded(record, max_bytes=16 * 1024)
        text = redact_text(text, max_chars=32_000)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(text + "\n")
    except Exception:
        # Audit failure must not break the mediated action.
        return


def read(store: Store, limit: int = 100) -> list[dict[str, Any]]:
    path = _path(store)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-min(max(limit, 1), 1000):]
    out = []
    for line in lines:
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                out.append(value)
        except json.JSONDecodeError:
            continue
    return out
