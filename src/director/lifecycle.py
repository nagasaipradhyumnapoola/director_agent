"""Local worker lifecycle: start/stop/pause/resume, heartbeat and recovery.

The worker performs deterministic work only. It never calls a model and makes no
external network requests.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analysis import ArtifactScanner, ScanConfig
from .evidence import EvidenceLedger
from .security import (
    ValidationError,
    atomic_write_text,
    bounded_json_loads,
    dump_bounded,
    ensure_within,
    prepare_state_dir,
)
from .store import Claim, Store, FencedWriteError, utc_now

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
DETACHED_PROCESS = 0x00000008 if os.name == "nt" else 0
CREATE_NEW_PROCESS_GROUP = 0x00000200 if os.name == "nt" else 0

LIFECYCLE = "lifecycle.json"
HEARTBEAT = "worker.heartbeat"
STOP_FLAG = "worker.stop"
LOG = "worker.log"


def _state(store: Store) -> Path:
    state = Path(store.root) / ".director"
    if not state.is_dir():
        raise ValidationError("state directory missing; run init first")
    return state


def _read_small(path: Path, cap: int) -> bytes:
    st = path.stat()
    if st.st_size > cap:
        raise ValidationError("state file exceeds size bound")
    return path.read_bytes()


def read_lifecycle(store: Store) -> dict[str, Any]:
    state = _state(store)
    path = state / LIFECYCLE
    if not path.is_file():
        return {"status": "stopped"}
    try:
        data = bounded_json_loads(_read_small(path, 64 * 1024), max_bytes=64 * 1024)
    except Exception:
        return {"status": "unknown", "error": "unreadable lifecycle file"}
    return data if isinstance(data, dict) else {"status": "unknown"}


def write_lifecycle(store: Store, payload: dict[str, Any]) -> None:
    state = _state(store)
    text, _ = dump_bounded(payload, max_bytes=64 * 1024)
    atomic_write_text(state / LIFECYCLE, text, root=Path(store.root))


def _write_heartbeat(store: Store, token: str, status: str) -> None:
    state = _state(store)
    text, _ = dump_bounded(
        {"pid": os.getpid(), "token": token, "status": status, "at": utc_now()},
        max_bytes=8 * 1024,
    )
    atomic_write_text(state / HEARTBEAT, text, root=Path(store.root))


def heartbeat_status(store: Store) -> dict[str, Any]:
    state = Path(store.root) / ".director"
    path = state / HEARTBEAT
    if not path.is_file():
        return {"present": False, "stale": True, "age_seconds": None}
    try:
        data = bounded_json_loads(_read_small(path, 8 * 1024), max_bytes=8 * 1024)
        stamp = datetime.fromisoformat(str(data.get("at")))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - stamp).total_seconds()
        return {"present": True, "stale": age > 30, "age_seconds": round(age, 1), "data": data}
    except Exception:
        return {"present": True, "stale": True, "age_seconds": None}


def pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW,
            )
            return f'"{int(pid)}"' in result.stdout
        except (OSError, subprocess.SubprocessError):
            return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def _module_env() -> dict[str, str]:
    keep = ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "NUMBER_OF_PROCESSORS", "OS")
    env = {key: os.environ[key] for key in keep if os.environ.get(key)}
    src = Path(__file__).resolve().parent.parent
    existing = os.environ.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(src) + (os.pathsep + existing if existing else "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONHASHSEED"] = "0"
    return env


def _rotate_log(state: Path) -> None:
    path = state / LOG
    try:
        if path.is_file() and path.stat().st_size > 1_000_000:
            backup = state / (LOG + ".1")
            if backup.exists():
                backup.unlink()
            path.replace(backup)
    except OSError:
        pass


def start(store: Store) -> dict[str, Any]:
    current = read_lifecycle(store)
    if current.get("status") in {"running", "paused", "starting"} and pid_alive(current.get("pid")):
        return {"status": current.get("status"), "already_running": True, "pid": current.get("pid")}
    state = _state(store)
    _rotate_log(state)
    token = secrets.token_hex(8)
    starting = {
        "status": "starting",
        "pid": None,
        "token": token,
        "started_at": utc_now(),
        "updated_at": utc_now(),
    }
    write_lifecycle(store, starting)
    log_path = state / LOG
    creationflags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
    try:
        with log_path.open("ab") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "director",
                    "worker",
                    "--root",
                    str(store.root),
                    "--loop",
                    "--token",
                    token,
                ],
                cwd=str(store.root),
                env=_module_env(),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                creationflags=creationflags,
                close_fds=True,
            )
    except OSError as exc:
        write_lifecycle(store, {**starting, "status": "error", "error": type(exc).__name__})
        raise ValidationError("worker could not start") from exc
    running = {
        **starting,
        "status": "running",
        "pid": process.pid,
        "log": log_path.relative_to(Path(store.root)).as_posix(),
        "updated_at": utc_now(),
    }
    write_lifecycle(store, running)
    return {"status": "running", "pid": process.pid, "token": token}


def stop(store: Store) -> dict[str, Any]:
    current = read_lifecycle(store)
    if current.get("status") not in {"running", "paused", "starting"}:
        write_lifecycle(store, {**current, "status": "stopped", "pid": None, "updated_at": utc_now()})
        return {"status": "stopped", "already_stopped": True}
    state = _state(store)
    atomic_write_text(state / STOP_FLAG, utc_now(), root=Path(store.root))
    write_lifecycle(store, {**current, "status": "stopping", "updated_at": utc_now()})
    deadline = time.time() + 10
    while time.time() < deadline:
        if not pid_alive(current.get("pid")):
            break
        time.sleep(0.2)
    alive = pid_alive(current.get("pid"))
    final = {
        **current,
        "status": "stopped" if not alive else "stopping",
        "pid": None if not alive else current.get("pid"),
        "stopped_at": utc_now() if not alive else None,
        "updated_at": utc_now(),
    }
    write_lifecycle(store, final)
    return {
        "status": final["status"],
        "pid": final.get("pid"),
        "warning": None if not alive else "worker did not exit; inspect the pid and log",
    }


def pause(store: Store) -> dict[str, Any]:
    current = read_lifecycle(store)
    if current.get("status") not in {"running", "starting"}:
        raise ValidationError("worker is not running")
    write_lifecycle(store, {**current, "status": "paused", "updated_at": utc_now()})
    return {"status": "paused", "pid": current.get("pid")}


def resume(store: Store) -> dict[str, Any]:
    current = read_lifecycle(store)
    if current.get("status") != "paused":
        raise ValidationError("worker is not paused")
    write_lifecycle(store, {**current, "status": "running", "updated_at": utc_now()})
    return {"status": "running", "pid": current.get("pid")}


def status(store: Store) -> dict[str, Any]:
    current = read_lifecycle(store)
    alive = pid_alive(current.get("pid")) if current.get("status") in {"running", "paused", "starting", "stopping"} else False
    beat = heartbeat_status(store)
    return {
        "lifecycle": current,
        "pid_alive": alive,
        "heartbeat": beat,
        "degraded": bool(current.get("status") == "running" and (not alive or beat.get("stale"))),
    }


def _scan_config(store: Store) -> ScanConfig:
    latest = store.latest_contract()
    budgets = latest[1].budgets if latest else None
    if budgets:
        return ScanConfig(
            max_files=min(budgets.max_scan_files, 20000),
            max_file_bytes=min(budgets.max_file_bytes, 8 * 1024 * 1024),
            max_findings=min(budgets.max_findings, 5000),
        )
    return ScanConfig()


def process_claim(store: Store, claim: Claim) -> dict[str, Any]:
    payload = claim.payload or {}
    action = payload.get("action")
    if action == "scan":
        roots = payload.get("roots") or ["."]
        if not isinstance(roots, list) or not all(isinstance(r, str) for r in roots):
            store.fail_investigation(claim, "invalid scan roots")
            return {"status": "failed", "reason": "invalid scan roots"}
        scanner = ArtifactScanner(store, _scan_config(store))
        result = scanner.scan(roots=roots, criterion_key="artifact.scan", claim=claim)
        return {
            "status": "completed",
            "receipt_id": result.receipt_id,
            "outcome": result.outcome,
            "findings": len(result.findings),
        }
    if action == "improve":
        from .improve import generate_proposals

        proposal_result = generate_proposals(store, investigation_id=claim.id)
        store.complete_investigation(claim, proposal_result)
        return {"status": "completed", "created_proposals": proposal_result["created_count"]}
    if action == "selfdev_author":
        from .improve import author_patch

        proposal_id = str(payload.get("proposal_id") or "")
        if not proposal_id:
            store.fail_investigation(claim, "missing proposal_id")
            return {"status": "failed", "reason": "missing proposal_id"}
        authored = author_patch(
            store,
            proposal_id,
            provider=str(payload.get("provider") or "ollama"),
            model=str(payload.get("model") or "qwen2.5-coder:7b"),
            test=bool(payload.get("test", True)),
            timeout=float(payload.get("timeout") or 600.0),
        )
        store.complete_investigation(
            claim,
            {
                "proposal_id": proposal_id,
                "patch_id": authored["patch"]["id"],
                "patch_status": authored["patch"]["status"],
            },
        )
        return {
            "status": "completed",
            "proposal_id": proposal_id,
            "patch_id": authored["patch"]["id"],
            "patch_status": authored["patch"]["status"],
        }
    if action == "selfdev_test":
        from .selfdev import test_patch

        patch_id = str(payload.get("patch_id") or "")
        if not patch_id:
            store.fail_investigation(claim, "missing patch_id")
            return {"status": "failed", "reason": "missing patch_id"}
        patch_result = test_patch(store, patch_id, timeout=600.0)
        store.complete_investigation(
            claim,
            {
                "patch_id": patch_id,
                "status": patch_result["status"],
                "evidence_id": patch_result.get("evidence_id"),
            },
        )
        return {
            "status": "completed",
            "patch_id": patch_id,
            "patch_status": patch_result["status"],
        }
    if action == "noop":
        store.complete_investigation(claim, {"result": "noop"})
        return {"status": "completed"}
    store.fail_investigation(claim, "unknown investigation action")
    return {"status": "failed", "reason": "unknown action"}


def process_one(store: Store, worker: str = "worker") -> dict[str, Any]:
    claim = store.claim_next(worker, lease_seconds=300)
    if claim is None:
        return {"claimed": False}
    try:
        result = process_claim(store, claim)
        return {"claimed": True, "investigation_id": claim.id, **result}
    except FencedWriteError as exc:
        return {"claimed": True, "investigation_id": claim.id, "status": "fenced", "reason": type(exc).__name__}
    except Exception as exc:  # noqa: BLE001
        try:
            store.fail_investigation(claim, type(exc).__name__)
        except Exception:
            pass
        return {"claimed": True, "investigation_id": claim.id, "status": "error", "reason": type(exc).__name__}


def worker_loop(store: Store, token: str, poll_seconds: float = 1.0, once: bool = False) -> int:
    state = _state(store)
    token = token or ""
    next_maintenance = 0.0
    while True:
        current = read_lifecycle(store)
        if current.get("token") and token and current.get("token") != token:
            return 0
        current_status = current.get("status")
        if once:
            result = process_one(store, worker=f"worker:{os.getpid()}")
            print(json.dumps(result, sort_keys=True))
            return 0
        if current_status not in {"running", "paused", "starting"}:
            break
        if (state / STOP_FLAG).exists():
            try:
                (state / STOP_FLAG).unlink()
            except OSError:
                pass
            break
        _write_heartbeat(store, token, current_status)
        if current_status == "paused":
            time.sleep(max(0.2, poll_seconds))
            continue
        if time.monotonic() >= next_maintenance:
            next_maintenance = time.monotonic() + 60.0
            try:
                from .maintenance import maybe_run

                maybe_run(store)
            except Exception:
                pass
        result = process_one(store, worker=f"worker:{os.getpid()}")
        if not result.get("claimed"):
            time.sleep(max(0.2, poll_seconds))
    if token:
        current = read_lifecycle(store)
        if not current.get("token") or current.get("token") == token:
            write_lifecycle(
                store,
                {**current, "status": "stopped", "pid": None, "stopped_at": utc_now(), "updated_at": utc_now()},
            )
    return 0


def recover(store: Store) -> dict[str, Any]:
    reclaimed = store.reconcile_expired()
    summary = store.status_summary()
    acceptance = EvidenceLedger(store).criterion_status(verify=True)
    checkpoint_id = store.save_checkpoint(
        {
            "reason": "startup reconciliation",
            "reclaimed_leases": reclaimed,
            "summary": summary,
            "acceptance": acceptance,
            "lifecycle": read_lifecycle(store),
        }
    )
    return {
        "reclaimed_leases": reclaimed,
        "checkpoint_id": checkpoint_id,
        "pending_events": len(store.pending_events(limit=1000)),
        "investigations": summary["investigations"],
        "acceptance_complete": acceptance["complete"],
    }

