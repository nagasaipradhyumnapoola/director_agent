"""Supervised local subprocess runner.

Containment is process-level: temp workspace, scrubbed environment, wall/output
caps, process-tree termination and (Windows) a kill-on-close job object. This is
not a kernel/container sandbox.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .security import (
    BoundsError,
    PathSafetyError,
    ValidationError,
    ensure_within,
    is_link_like,
    redact_text,
)
from .winjob import WindowsJob

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
CREATE_NEW_PROCESS_GROUP = 0x00000200 if os.name == "nt" else 0

_ENV_ALLOWLIST = {
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "PROCESSOR_IDENTIFIER",
    "OS",
    "LANG",
    "LC_ALL",
    "TZ",
}


@dataclass
class RunResult:
    argv: list[str]
    exit_code: int | None
    timed_out: bool
    duration_seconds: float
    stdout: str
    stderr: str
    stdout_bytes: int
    stderr_bytes: int
    truncated: bool
    error: str | None
    resources: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "argv": [redact_text(a, max_chars=300) for a in self.argv],
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "duration_seconds": round(self.duration_seconds, 4),
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "truncated": self.truncated,
            "error": self.error,
            "resources": self.resources,
            "stdout_preview": self.stdout[:1000],
            "stderr_preview": self.stderr[:1000],
        }


class Workspace:
    """Temporary directory with copies only; never links to project files."""

    def __init__(self, max_bytes: int = 128 * 1024 * 1024, max_files: int = 5000):
        self.root = Path(tempfile.mkdtemp(prefix="director-run-"))
        self.tmp = self.root / "tmp"
        self.tmp.mkdir()
        self.max_bytes = max_bytes
        self.max_files = max_files
        self._copied = 0
        self._bytes = 0
        self.kept = False

    def path(self, rel: str) -> Path:
        return ensure_within(self.root / rel, self.root)

    def write_text(self, rel: str, text: str) -> Path:
        target = self.path(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        return target

    def _reserve(self, st: os.stat_result) -> None:
        self._copied += 1
        self._bytes += st.st_size
        if self._copied > self.max_files or self._bytes > self.max_bytes:
            raise BoundsError("workspace copy budget exceeded")

    def copy_file(self, source: os.PathLike[str] | str, rel: str) -> Path:
        src = Path(source)
        if not src.is_file():
            raise ValidationError("source file missing")
        st = os.lstat(src)
        if is_link_like(st) or st.st_nlink > 1:
            raise PathSafetyError("refusing to copy a linked or hardlinked file")
        self._reserve(st)
        target = self.path(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        return target

    def copy_tree(self, source: os.PathLike[str] | str, rel: str) -> Path:
        src = Path(source)
        if src.is_file():
            return self.copy_file(src, rel)
        if not src.is_dir():
            raise ValidationError("source directory missing")
        destination = self.path(rel)
        destination.mkdir(parents=True, exist_ok=True)
        for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
            current = Path(dirpath)
            keep: list[str] = []
            for name in dirnames:
                child = current / name
                st = os.lstat(child)
                if is_link_like(st):
                    raise PathSafetyError("refusing to copy a linked directory")
                (destination / child.relative_to(src)).mkdir(parents=True, exist_ok=True)
                keep.append(name)
            dirnames[:] = keep
            for name in filenames:
                child = current / name
                st = os.lstat(child)
                if is_link_like(st) or st.st_nlink > 1:
                    raise PathSafetyError("refusing to copy a linked or hardlinked file")
                self._reserve(st)
                target = destination / child.relative_to(src)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(child, target)
        return destination

    def cleanup(self) -> None:
        if not self.kept:
            shutil.rmtree(self.root, ignore_errors=True)


def _read_stream(stream: Any, cap: int, sink: list[tuple[bytes, bool]]) -> None:
    if stream is None:
        sink.append((b"", False))
        return
    buffer = bytearray()
    truncated = False
    try:
        while True:
            chunk = stream.read(8192)
            if not chunk:
                break
            room = cap - len(buffer)
            if room > 0:
                buffer.extend(chunk[:room])
                if len(chunk) > room:
                    truncated = True
            else:
                truncated = True
    except (ValueError, OSError):
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass
    sink.append((bytes(buffer), truncated))


def _kill_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                capture_output=True,
                timeout=10,
                creationflags=CREATE_NO_WINDOW,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        process.kill()
    except (ProcessLookupError, OSError):
        pass


class Runner:
    def __init__(self, default_timeout: float = 120.0, default_max_output: int = 256 * 1024):
        self.default_timeout = default_timeout
        self.default_max_output = default_max_output

    def create_workspace(self) -> Workspace:
        return Workspace()

    def _env(self, workspace: Workspace, extra: Mapping[str, str] | None) -> dict[str, str]:
        env: dict[str, str] = {}
        for key in _ENV_ALLOWLIST:
            value = os.environ.get(key)
            if value:
                env[key] = value
        for key, value in {
            "HOME": workspace.tmp,
            "USERPROFILE": workspace.tmp,
            "APPDATA": workspace.tmp,
            "LOCALAPPDATA": workspace.tmp,
            "TEMP": workspace.tmp,
            "TMP": workspace.tmp,
            "TMPDIR": workspace.tmp,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "NO_PROXY": "*",
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "ALL_PROXY": "",
        }.items():
            env[key] = str(value)
        if extra:
            for key, value in extra.items():
                if not isinstance(key, str) or len(key) > 100 or len(str(value)) > 4096:
                    raise ValidationError("invalid environment override")
                env[key] = str(value)
        return env

    def _validate_argv(self, argv: Sequence[str]) -> list[str]:
        if not argv or len(argv) > 64:
            raise ValidationError("invalid argv length")
        out: list[str] = []
        for part in argv:
            if not isinstance(part, str) or not part or "\x00" in part or len(part) > 4096:
                raise ValidationError("invalid argv element")
            out.append(part)
        return out

    def run(
        self,
        argv: Sequence[str],
        workspace: Workspace,
        timeout: float | None = None,
        max_output: int | None = None,
        env_extra: Mapping[str, str] | None = None,
        memory_mb: int = 1024,
        cpu_seconds: int = 60,
        cwd_rel: str | None = None,
    ) -> RunResult:
        argv_list = self._validate_argv(argv)
        limit = float(timeout if timeout is not None else self.default_timeout)
        if limit <= 0 or limit > 3600:
            raise ValidationError("invalid timeout")
        cap = int(max_output if max_output is not None else self.default_max_output)
        if cap <= 0 or cap > 16 * 1024 * 1024:
            raise ValidationError("invalid output cap")
        env = self._env(workspace, env_extra)
        cwd = workspace.path(cwd_rel) if cwd_rel else workspace.root
        if not cwd.is_dir():
            raise ValidationError("run directory does not exist")
        started = time.time()
        stdout_sink: list[tuple[bytes, bool]] = []
        stderr_sink: list[tuple[bytes, bool]] = []
        timed_out = False
        error: str | None = None
        job = WindowsJob(memory_mb=memory_mb, cpu_seconds=cpu_seconds)
        process: subprocess.Popen[bytes] | None = None
        try:
            process = subprocess.Popen(
                argv_list,
                cwd=str(cwd),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
                start_new_session=os.name != "nt",
            )
            job.assign(process)
            threads = [
                threading.Thread(target=_read_stream, args=(process.stdout, cap, stdout_sink), daemon=True),
                threading.Thread(target=_read_stream, args=(process.stderr, cap, stderr_sink), daemon=True),
            ]
            for thread in threads:
                thread.start()
            try:
                process.wait(timeout=limit)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_tree(process)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
            for thread in threads:
                thread.join(timeout=10)
        except FileNotFoundError:
            error = "executable not found"
        except PermissionError:
            error = "executable not permitted"
        except OSError as exc:
            error = f"process failed to start ({type(exc).__name__})"
        finally:
            if process is not None and process.poll() is None:
                _kill_tree(process)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            job.close()
        duration = time.time() - started
        stdout_raw, stdout_trunc = stdout_sink[0] if stdout_sink else (b"", False)
        stderr_raw, stderr_trunc = stderr_sink[0] if stderr_sink else (b"", False)
        stdout = redact_text(stdout_raw.decode("utf-8", "replace"))
        stderr = redact_text(stderr_raw.decode("utf-8", "replace"))
        resources = {
            "wall_seconds": round(duration, 4),
            "timeout_seconds": limit,
            "max_output_bytes_per_stream": cap,
            "stdout_bytes": len(stdout_raw),
            "stderr_bytes": len(stderr_raw),
            "peak_memory_mb": "unknown",
            "memory_limit_mb": memory_mb,
            "cpu_limit_seconds": cpu_seconds,
            "windows_job_object": "applied" if job.applied else ("unavailable" if job.error else "not_windows"),
            "job_object_error": job.error,
            "network_default": "policy-denied-and-scrubbed-env",
            "isolation_level": "process-level-supervised (not a kernel sandbox)",
        }
        return RunResult(
            argv=argv_list,
            exit_code=None if process is None else process.returncode,
            timed_out=timed_out,
            duration_seconds=duration,
            stdout=stdout,
            stderr=stderr,
            stdout_bytes=len(stdout_raw),
            stderr_bytes=len(stderr_raw),
            truncated=stdout_trunc or stderr_trunc,
            error=error,
            resources=resources,
        )

