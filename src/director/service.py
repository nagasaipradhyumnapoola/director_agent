"""Opt-in Windows logon task for the DIRECTOR worker.

This is a user-level Task Scheduler entry, not a Windows service. It starts
`director start` at logon; the worker then runs while the user session is alive.
Remove it with `director service remove`.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any

from .security import ValidationError, atomic_write_text
from .store import Store

CREATE_NO_WINDOW = 0x08000000


def task_name(store: Store) -> str:
    digest = hashlib.sha256(store.project_id.encode("utf-8")).hexdigest()[:10]
    return f"DIRECTOR-{digest}"


def _wrapper(store: Store) -> Path:
    path = Path(store.root) / ".director" / "director-service.cmd"
    src = Path(__file__).resolve().parent.parent
    text = (
        "@echo off\r\n"
        f'set "PYTHONPATH={src};%PYTHONPATH%"\r\n'
        f'"{sys.executable}" -m director start --root "{store.root}"\r\n'
    )
    atomic_write_text(path, text, root=Path(store.root))
    return path


def _startup_path(store: Store) -> Path | None:
    appdata = __import__("os").environ.get("APPDATA")
    if not appdata:
        return None
    startup = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup / f"{task_name(store)}.cmd"


def _run(args: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValidationError("Task Scheduler command failed") from exc
    return result.returncode, (result.stdout + result.stderr).strip()


def install(store: Store, start_now: bool = False) -> dict[str, Any]:
    if __import__("os").name != "nt":
        raise ValidationError("service install is currently Windows-only")
    wrapper = _wrapper(store)
    name = task_name(store)
    code, output = _run(
        [
            "schtasks",
            "/Create",
            "/TN",
            name,
            "/SC",
            "ONLOGON",
            "/TR",
            f'"{wrapper}"',
            "/F",
            "/RL",
            "LIMITED",
        ]
    )
    method = "task-scheduler"
    startup_file = None
    if code != 0:
        startup = _startup_path(store)
        if startup is None:
            raise ValidationError("could not create logon task: " + output[:300])
        startup.parent.mkdir(parents=True, exist_ok=True)
        startup.write_text(
            "@echo off\r\n"
            f'start "" /min "{wrapper}"\r\n',
            encoding="utf-8",
        )
        startup_file = str(startup)
        method = "startup-folder"
    if start_now:
        from .lifecycle import start

        start(store)
    try:
        from . import audit

        audit.log(store, "owner", "service.install", method, "ok")
    except Exception:
        pass
    return {
        "installed": True,
        "method": method,
        "task": name if method == "task-scheduler" else None,
        "startup_file": startup_file,
        "trigger": "at user logon",
        "wrapper": wrapper.relative_to(Path(store.root)).as_posix(),
        "started_now": start_now,
        "note": "user-session autostart, not a Windows service; host must be logged in",
    }


def status(store: Store) -> dict[str, Any]:
    name = task_name(store)
    code, output = _run(["schtasks", "/Query", "/TN", name, "/FO", "LIST"])
    startup = _startup_path(store)
    startup_exists = bool(startup and startup.is_file())
    return {
        "installed": code == 0 or startup_exists,
        "task": name if code == 0 else None,
        "startup_file": str(startup) if startup_exists else None,
        "method": "task-scheduler" if code == 0 else ("startup-folder" if startup_exists else None),
        "detail": output[:2000] if code == 0 else "",
    }


def remove(store: Store) -> dict[str, Any]:
    if __import__("os").name != "nt":
        raise ValidationError("service remove is currently Windows-only")
    name = task_name(store)
    code, output = _run(["schtasks", "/Delete", "/TN", name, "/F"])
    startup = _startup_path(store)
    startup_removed = False
    if startup and startup.is_file():
        startup.unlink()
        startup_removed = True
    return {
        "removed": code == 0 or startup_removed,
        "task": name if code == 0 else None,
        "startup_file_removed": startup_removed,
        "detail": output[:500] if code == 0 else "",
    }
