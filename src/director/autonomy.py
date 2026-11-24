"""Opt-in continuous self-improvement scheduling.

When enabled, the running worker periodically generates proposals and enqueues
one local-model author/test job. It never merges, pushes or deploys: the patch
still has to pass tests, independent review and owner approval.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .security import ValidationError, atomic_write_text
from .store import Store, utc_now


def _path(store: Store) -> Path:
    return Path(store.root) / ".director" / "autonomy.json"


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


def enable(
    store: Store,
    interval_minutes: float = 60.0,
    max_per_day: int = 4,
    provider: str = "ollama",
    model: str = "qwen2.5-coder:7b",
) -> dict[str, Any]:
    if not 1 <= interval_minutes <= 24 * 60:
        raise ValidationError("interval_minutes must be 1-1440")
    if not 1 <= max_per_day <= 100:
        raise ValidationError("max_per_day must be 1-100")
    _write(
        store,
        {
            "enabled": True,
            "interval_minutes": interval_minutes,
            "max_per_day": max_per_day,
            "provider": provider,
            "model": model,
            "last_run_at": None,
            "day": None,
            "runs_today": 0,
        },
    )
    return status(store)


def disable(store: Store) -> dict[str, Any]:
    data = _read(store)
    data["enabled"] = False
    _write(store, data)
    return status(store)


def status(store: Store) -> dict[str, Any]:
    data = _read(store)
    due_in = None
    if data.get("enabled"):
        last = data.get("last_run_at")
        if not last:
            due_in = 0.0
        else:
            try:
                due = datetime.fromisoformat(str(last)).timestamp() + float(data.get("interval_minutes", 60)) * 60
                due_in = max(0.0, round(due - time.time(), 1))
            except ValueError:
                due_in = 0.0
    return {
        "enabled": bool(data.get("enabled")),
        "interval_minutes": float(data.get("interval_minutes") or 60),
        "max_per_day": int(data.get("max_per_day") or 4),
        "provider": data.get("provider") or "ollama",
        "model": data.get("model") or "qwen2.5-coder:7b",
        "last_run_at": data.get("last_run_at"),
        "runs_today": int(data.get("runs_today") or 0),
        "due_in_seconds": due_in,
    }


def _patched_proposals(store: Store) -> set[str]:
    rows = store.conn.execute("SELECT proposal_id FROM patches WHERE proposal_id IS NOT NULL").fetchall()
    return {str(row["proposal_id"]) for row in rows}


def _pick_proposal(store: Store) -> dict[str, Any] | None:
    patched = _patched_proposals(store)
    for proposal in store.list_proposals(status="proposed", limit=100):
        if str(proposal["id"]) not in patched:
            return proposal
    return None


def maybe_run(store: Store) -> dict[str, Any] | None:
    data = _read(store)
    if not data.get("enabled"):
        return None
    today = datetime.now(timezone.utc).date().isoformat()
    runs_today = int(data.get("runs_today") or 0) if data.get("day") == today else 0
    if runs_today >= int(data.get("max_per_day") or 4):
        return None
    last = data.get("last_run_at")
    if last:
        try:
            if datetime.fromisoformat(str(last)).timestamp() + float(data.get("interval_minutes", 60)) * 60 > time.time():
                return None
        except ValueError:
            pass

    from .improve import generate_proposals

    generate_proposals(store)
    proposal = _pick_proposal(store)
    if proposal is None:
        data["last_run_at"] = utc_now()
        data["day"] = today
        data["runs_today"] = runs_today
        _write(store, data)
        return None

    investigation_id = store.enqueue_investigation(
        title=f"Autonomy: author proposal {proposal['id']}",
        hypothesis="A local model can author a patch that the selfdev gates may accept.",
        domain="general",
        priority=0.85,
        payload={
            "action": "selfdev_author",
            "proposal_id": proposal["id"],
            "provider": data.get("provider") or "ollama",
            "model": data.get("model") or "qwen2.5-coder:7b",
            "test": True,
            "timeout": 900.0,
        },
        dedupe_key=f"autonomy:author:{proposal['id']}",
    )
    data["last_run_at"] = utc_now()
    data["day"] = today
    data["runs_today"] = runs_today + 1
    _write(store, data)
    try:
        from . import audit

        audit.log(store, "director.autonomy", "improve.enqueue", proposal["id"], "queued")
    except Exception:
        pass
    return {
        "investigation_id": investigation_id,
        "proposal_id": proposal["id"],
        "status": "queued",
        "runs_today": runs_today + 1,
    }
