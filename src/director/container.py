"""Bounded Docker container runner.

This is the process-level containment upgrade DIRECTOR can offer when a Docker
daemon is available. It is deliberately small:

- the source directory is mounted read-only (``/work``);
- networking is disabled unless the caller explicitly opts in *and* the project
  policy allows external network;
- the container runs as an unprivileged uid/gid, with memory, CPU, pid and
  output bounds and a writable tmpfs only under ``/tmp``.

It is still not a hardened microVM: the Docker daemon and image supply chain are
trusted, and kernel/shared-kernel isolation is only as good as the host Docker
configuration. Use it to run untrusted build/test steps, not hostile code.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Sequence

from .policy import PolicyGateway
from .security import BoundsError, ValidationError
from .store import Store

MAX_OUTPUT = 256 * 1024
MAX_TIMEOUT = 3600.0
_IMAGE_RE = r"^[A-Za-z0-9][A-Za-z0-9._/@:+-]{0,199}$"


def _docker() -> str:
    return shutil.which("docker") or "docker"


def available() -> dict[str, Any]:
    """Report whether a usable Docker daemon is reachable."""
    try:
        result = subprocess.run(
            [_docker(), "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "reason": f"{type(exc).__name__}: {str(exc)[:160]}"}
    version = result.stdout.strip()
    return {
        "available": result.returncode == 0 and bool(version),
        "server_version": version if result.returncode == 0 else None,
        "reason": result.stderr.strip()[:300] if result.returncode != 0 else "",
    }


def _validate_image(image: str) -> str:
    import re

    if not isinstance(image, str) or not re.match(_IMAGE_RE, image):
        raise ValidationError("invalid container image reference")
    return image


def _validate_command(command: Sequence[str]) -> list[str]:
    if not command or len(command) > 128:
        raise ValidationError("container command must have 1-128 arguments")
    out = []
    for item in command:
        if not isinstance(item, str) or not item or "\x00" in item:
            raise ValidationError("invalid container argument")
        if len(item) > 4096:
            raise BoundsError("container argument too large")
        out.append(item)
    return out


def run(
    store: Store,
    image: str,
    command: Sequence[str],
    workdir: str | Path,
    *,
    timeout: float = 600.0,
    network: bool = False,
    writable: bool = False,
    memory: str = "512m",
    cpus: str = "1.0",
    pids_limit: int = 128,
    user: str = "65534:65534",
) -> dict[str, Any]:
    """Run ``command`` inside a bounded, read-only container."""
    image = _validate_image(image)
    argv = _validate_command(command)
    if not 1 <= timeout <= MAX_TIMEOUT:
        raise ValidationError("timeout must be 1-3600 seconds")
    if not 1 <= pids_limit <= 1024:
        raise ValidationError("pids_limit must be 1-1024")

    root = Path(workdir).resolve()
    if not root.is_dir():
        raise ValidationError("workdir does not exist")

    policy = PolicyGateway(store)
    latest = store.latest_contract()
    revision = int(latest[0]["revision"]) if latest else 1
    if network:
        policy.require("director.container", "network_read", "container", revision)
    policy.require(
        "director.container",
        "container_run",
        "container",
        revision,
        payload={"image": image, "network": network, "writable": writable},
    )

    relative = root.as_posix()
    args = [
        _docker(),
        "run",
        "--rm",
        "--network",
        "host" if network else "none",
        "--memory",
        memory,
        "--cpus",
        cpus,
        "--pids-limit",
        str(pids_limit),
        "--user",
        user,
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "-e",
        "HOME=/tmp",
        "-v",
        f"{relative}:/work:" + ("rw" if writable else "ro"),
        "-w",
        "/work",
        image,
        *argv,
    ]
    started = time.monotonic()
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return {
            "image": image,
            "command": argv,
            "outcome": "timeout",
            "exit_code": None,
            "duration_s": round(time.monotonic() - started, 3),
            "stdout": (exc.stdout or b"")[-MAX_OUTPUT:].decode("utf-8", "replace"),
            "stderr": (exc.stderr or b"")[-MAX_OUTPUT:].decode("utf-8", "replace"),
        }
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValidationError("container execution failed") from exc

    stdout = result.stdout[-MAX_OUTPUT:].decode("utf-8", "replace")
    stderr = result.stderr[-MAX_OUTPUT:].decode("utf-8", "replace")
    record = {
        "image": image,
        "command": argv,
        "network": network,
        "writable": writable,
        "exit_code": result.returncode,
        "outcome": "ok" if result.returncode == 0 else "failed",
        "duration_s": round(time.monotonic() - started, 3),
        "stdout": stdout,
        "stderr": stderr,
        "bounds": {
            "memory": memory,
            "cpus": cpus,
            "pids_limit": pids_limit,
            "timeout_s": timeout,
            "user": user,
            "cap_drop": "ALL",
            "no_new_privileges": True,
        },
    }
    try:
        from . import audit

        audit.log(store, "director.container", "container.run", f"image:{image}", record["outcome"])
    except Exception:
        pass
    return record
