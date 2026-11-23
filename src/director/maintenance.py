"""Opt-in periodic maintenance performed by the 24/7 worker.

Only scheduled backups are supported today. The worker checks the enabled flag
and the last-run time; when due it creates a verified ZIP backup and prunes old
archives. Nothing here runs unless the owner enables it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .backup import create_backup, prune_backups
from .security import ValidationError, atomic_write_text
from .store import Store, utc_now


def _path(store: Store) -> Path:
    return Path(store.root) / ".director" / "maintenance.json"


def _read(store: Store) -> dict[str, Any]:
    path = _path(store)
    if not path.is_file():
        return {"enabled": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"enabled": False}
    return data if isinstance(data, dict) else {"enabled": False}


def _write(store: Store, data: dict[str, Any]) -> None:
    atomic_write_text(_path(store), json.dumps(data, sort_keys=True), root=Path(store.root))


def enable(store: Store, interval_hours: float = 24.0, keep: int = 14) -> dict[str, Any]:
    if not 0.05 <= interval_hours <= 24 * 365:
        raise ValidationError("interval_hours must be between 0.05 and 8760")
    if not 1 <= keep <= 1000:
        raise ValidationError("keep must be 1-1000")
    data = {"enabled": True, "interval_hours": interval_hours, "keep": keep, "last_run_at": None}
    _write(store, data)
    return status(store)


def disable(store: Store) -> dict[str, Any]:
    data = _read(store)
    data["enabled"] = False
    _write(store, data)
    return status(store)


def status(store: Store) -> dict[str, Any]:
    data = _read(store)
    interval = float(data.get("interval_hours") or 24.0)
    last = data.get("last_run_at")
    due_in = None
    if data.get("enabled"):
        if not last:
            due_in = 0.0
        else:
            try:
                from datetime import datetime

                parsed = datetime.fromisoformat(str(last))
                due = parsed.timestamp() + interval * 3600
                due_in = max(0.0, round(due - time.time(), 1))
            except ValueError:
                due_in = 0.0
    return {
        "enabled": bool(data.get("enabled")),
        "interval_hours": interval,
        "keep": int(data.get("keep") or 14),
        "last_run_at": last,
        "due_in_seconds": due_in,
    }


def maybe_run(store: Store) -> dict[str, Any] | None:
    data = _read(store)
    if not data.get("enabled"):
        return None
    interval = float(data.get("interval_hours") or 24.0)
    last = data.get("last_run_at")
    if last:
        try:
            from datetime import datetime

            if datetime.fromisoformat(str(last)).timestamp() + interval * 3600 > time.time():
                return None
        except ValueError:
            pass
    return run_now(store)


def run_now(store: Store) -> dict[str, Any]:
    data = _read(store)
    keep = int(data.get("keep") or 14)
    backup = create_backup(store)
    pruned = prune_backups(store, keep=keep)
    data["last_run_at"] = utc_now()
    data.setdefault("enabled", True)
    _write(store, data)
    try:
        from . import audit

        audit.log(store, "director.maintenance", "backup.scheduled", backup["backup"], "ok")
    except Exception:
        pass
    return {
        "backup": backup["backup"],
        "sha256": backup["sha256"],
        "deleted": pruned["deleted"],
        "kept": pruned["kept"],
        "at": data["last_run_at"],
    }
