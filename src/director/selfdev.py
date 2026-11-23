"""Supervised self-modification: patch -> isolated worktree -> tests -> review -> merge.

The model/agent may author a patch, but it cannot merge it without an isolated
apply, the offline test suite, an independent review record and owner approval.
No push/deploy occurs here.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evidence import EvidenceLedger, environment_snapshot
from .runner import CREATE_NEW_PROCESS_GROUP, CREATE_NO_WINDOW, _kill_tree, _read_stream
from .security import (
    BoundsError,
    PathSafetyError,
    ValidationError,
    atomic_write_text,
    bounded_json_loads,
    dump_bounded,
    ensure_within,
    redact_text,
    sha256_text,
)
from .store import Store, utc_now

ALLOWED_PREFIXES = (
    "src/",
    "tests/",
    "docs/build/",
    "benchmarks/",
    "examples/",
    "integrations/",
)
ALLOWED_FILES = {
    "README.md",
    "CONTEXT.md",
    "AGENTS.md",
    "LICENSE",
    "NOTICE",
    "pyproject.toml",
    ".gitignore",
    ".gitattributes",
    "install.ps1",
    "install.sh",
    "uninstall.ps1",
    "uninstall.sh",
    "docs/BUILD_STATUS.md",
    "docs/SELF_IMPROVEMENT.md",
    "docs/HARNESS_INTEGRATION.md",
}
DENIED_PREFIXES = (
    "docs/research/",
    "fixtures/",
    "deliverables/",
    "var/",
    ".director/",
    ".git/",
    ".github/",
)
MAX_PATCH_BYTES = 1024 * 1024
MAX_TEST_OUTPUT = 512 * 1024
_PATH_LINE = re.compile(r"^(?:diff --git a/(.+?) b/(.+)$|--- a/(.+)$|\+\+\+ b/(.+)$)")
_ENV_KEEP = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "LOCALAPPDATA",
    "APPDATA",
    "HOMEDRIVE",
    "HOMEPATH",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "OS",
)


def _git(args: Sequence[str], cwd: Path, timeout: float = 60.0) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValidationError("git invocation failed") from exc
    if result.returncode != 0:
        raise ValidationError("git command failed: " + redact_text(result.stderr)[:300])
    return result.stdout.strip()


def _git_capture(args: Sequence[str], cwd: Path, timeout: float = 60.0) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", type(exc).__name__
    return result.returncode, result.stdout, result.stderr


def _validate_patch(text: str) -> list[str]:
    if not text.strip():
        raise ValidationError("patch is empty")
    raw = text.encode("utf-8")
    if len(raw) > MAX_PATCH_BYTES:
        raise BoundsError("patch exceeds the size bound")
    if b"\x00" in raw:
        raise ValidationError("binary patch rejected")
    if "GIT binary patch" in text:
        raise ValidationError("binary patch rejected")
    if re.search(r"^(?:new file mode|old mode) 120000", text, re.MULTILINE):
        raise ValidationError("symlink creation/changes are rejected")
    paths: set[str] = set()
    for line in text.splitlines():
        match = _PATH_LINE.match(line)
        if not match:
            continue
        for value in match.groups():
            if not value or value == "/dev/null":
                continue
            path = value.replace("\\", "/").strip()
            while path.startswith("./"):
                path = path[2:]
            if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
                raise ValidationError("absolute paths are rejected")
            parts = path.split("/")
            if ".." in parts or "." in parts or "" in parts:
                raise ValidationError("path traversal/normalisation rejected")
            lowered = path.lower()
            if any(lowered.startswith(prefix) for prefix in DENIED_PREFIXES):
                raise ValidationError(f"path is on the self-development deny list: {path[:120]}")
            if path not in ALLOWED_FILES and not any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES):
                raise ValidationError(f"path is outside the self-development allowlist: {path[:120]}")
            paths.add(path)
    if not paths:
        raise ValidationError("patch does not touch any allowed file")
    return sorted(paths)


def _patch_file(store: Store, patch: Mapping[str, Any]) -> Path:
    return ensure_within(Path(store.root) / str(patch["patch_path"]), Path(store.root))


def _worktree_path(store: Store, patch_id: str) -> Path:
    return ensure_within(Path(store.root) / "var" / "selfdev" / patch_id / "worktree", Path(store.root))


def _test_env(worktree: Path) -> dict[str, str]:
    env = {key: os.environ[key] for key in _ENV_KEEP if os.environ.get(key)}
    env["PYTHONPATH"] = str(worktree / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONHASHSEED"] = "0"
    env["NO_PROXY"] = "*"
    env["HTTP_PROXY"] = ""
    env["HTTPS_PROXY"] = ""
    return env


def _run_tests(
    worktree: Path,
    command: Sequence[str],
    timeout: float,
) -> dict[str, Any]:
    started = time.time()
    stdout_sink: list[tuple[bytes, bool]] = []
    stderr_sink: list[tuple[bytes, bool]] = []
    timed_out = False
    error = None
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            list(command),
            cwd=str(worktree),
            env=_test_env(worktree),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
        )
        threads = [
            threading.Thread(target=_read_stream, args=(process.stdout, MAX_TEST_OUTPUT, stdout_sink), daemon=True),
            threading.Thread(target=_read_stream, args=(process.stderr, MAX_TEST_OUTPUT, stderr_sink), daemon=True),
        ]
        for thread in threads:
            thread.start()
        try:
            process.wait(timeout=timeout)
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
        error = "test command not found"
    except OSError as exc:
        error = f"test command failed to start ({type(exc).__name__})"
    finally:
        if process is not None and process.poll() is None:
            _kill_tree(process)
    out, out_trunc = stdout_sink[0] if stdout_sink else (b"", False)
    err, err_trunc = stderr_sink[0] if stderr_sink else (b"", False)
    return {
        "command": [redact_text(part, 300) for part in command],
        "exit_code": None if process is None else process.returncode,
        "timed_out": timed_out,
        "error": error,
        "duration_seconds": round(time.time() - started, 4),
        "truncated": out_trunc or err_trunc,
        "stdout": redact_text(out.decode("utf-8", "replace")),
        "stderr": redact_text(err.decode("utf-8", "replace")),
    }


def create_patch(
    store: Store,
    patch_text: str,
    title: str,
    author: str = "agent",
    proposal_id: str | None = None,
) -> dict[str, Any]:
    changed = _validate_patch(patch_text)
    base_commit = _git(["rev-parse", "HEAD"], Path(store.root))
    patch_id = "patch_" + uuid.uuid4().hex
    rel_path = f".director/patches/{patch_id}.patch"
    target = ensure_within(Path(store.root) / rel_path, Path(store.root))
    atomic_write_text(target, patch_text, root=Path(store.root))
    digest = sha256_text(patch_text)
    store.add_patch(
        title=title,
        author=author,
        base_commit=base_commit,
        patch_path=rel_path,
        patch_sha256=digest,
        changed_files=changed,
        proposal_id=proposal_id,
        patch_id=patch_id,
    )
    return store.get_patch(patch_id)


def test_patch(
    store: Store,
    patch_id: str,
    command: Sequence[str] | None = None,
    timeout: float = 600.0,
) -> dict[str, Any]:
    patch = store.get_patch(patch_id)
    if patch["status"] not in {"proposed", "tested", "failed", "review_failed"}:
        raise ValidationError("patch is not in a testable state")
    patch_file = _patch_file(store, patch)
    if not patch_file.is_file():
        raise ValidationError("patch file missing")
    if sha256_text(patch_file.read_text(encoding="utf-8")) != patch["patch_sha256"]:
        raise ValidationError("patch file hash changed")
    worktree = _worktree_path(store, patch_id)
    if worktree.exists():
        _git_capture(["worktree", "remove", "--force", str(worktree)], Path(store.root))
        shutil.rmtree(worktree, ignore_errors=True)
    worktree.parent.mkdir(parents=True, exist_ok=True)
    _git(["worktree", "add", "--detach", str(worktree), str(patch["base_commit"])], Path(store.root))
    store.update_patch(patch_id, status="testing", worktree=worktree.relative_to(Path(store.root)).as_posix())

    check_code, check_out, check_err = _git_capture(
        ["apply", "--check", "--recount", str(patch_file)], worktree
    )
    if check_code != 0:
        summary = {
            "error": "patch does not apply",
            "detail": redact_text(check_err)[:1000],
        }
        _cleanup_worktree(store, patch_id)
        store.update_patch(patch_id, status="failed", test_summary=_json(summary), worktree=None)
        raise ValidationError("patch does not apply cleanly")

    apply_code, _apply_out, apply_err = _git_capture(
        ["apply", "--recount", str(patch_file)], worktree
    )
    if apply_code != 0:
        _cleanup_worktree(store, patch_id)
        store.update_patch(
            patch_id,
            status="failed",
            test_summary=_json({"error": "git apply failed", "detail": redact_text(apply_err)[:1000]}),
            worktree=None,
        )
        raise ValidationError("git apply failed")

    test_command = list(command or [sys.executable, "-m", "pytest", "-q"])
    result = _run_tests(worktree, test_command, timeout)
    passed = (
        result["error"] is None
        and not result["timed_out"]
        and result["exit_code"] == 0
    )
    output_text, _ = dump_bounded(
        {
            "command": result["command"],
            "exit_code": result["exit_code"],
            "timed_out": result["timed_out"],
            "duration_seconds": result["duration_seconds"],
            "truncated": result["truncated"],
            "stdout_tail": result["stdout"][-20_000:],
            "stderr_tail": result["stderr"][-20_000:],
        },
        max_bytes=MAX_TEST_OUTPUT,
    )
    output_rel = f".director/patches/{patch_id}.test.txt"
    atomic_write_text(Path(store.root) / output_rel, output_text, root=Path(store.root))
    summary = {
        "passed": passed,
        "exit_code": result["exit_code"],
        "timed_out": result["timed_out"],
        "error": result["error"],
        "duration_seconds": result["duration_seconds"],
        "command": result["command"],
        "base_commit": patch["base_commit"],
        "changed_files": bounded_json_loads(patch["changed_files"], max_bytes=32 * 1024),
    }
    ledger = EvidenceLedger(store)
    evidence = ledger.record(
        criterion_key="selfdev.patch",
        kind="selfdev_test",
        collector="director.selfdev",
        check_name="selfdev_test",
        check_version="selfdev/1.0",
        outcome="pass" if passed else "fail",
        subject_path=patch["patch_path"],
        params=summary,
        environment=environment_snapshot(),
        confidence=0.95 if passed else 0.7,
        limitations=(
            "tests run in an isolated worktree at the recorded base commit; "
            "merge still requires independent review and owner approval"
        ),
        raw_ref=output_rel,
    )
    if not passed:
        store.add_finding(
            {
                "severity": "high",
                "kind": "selfdev_test_failed",
                "message": f"self-development patch failed tests (exit {result['exit_code']})",
                "path": patch["patch_path"],
                "source_sha256": patch["patch_sha256"],
                "evaluator_version": "selfdev/1.0",
                "receipt_id": evidence["id"],
                "evidence_id": evidence["id"],
                "confidence": 0.95,
                "limitations": "see test output receipt",
            }
        )
    store.update_patch(
        patch_id,
        status="tested" if passed else "failed",
        worktree=None if not passed else worktree.relative_to(Path(store.root)).as_posix(),
        test_summary=_json(summary),
        test_output_ref=output_rel,
    )
    try:
        from . import audit

        audit.log(store, "director.selfdev", "selfdev.test", patch_id, "pass" if passed else "fail")
    except Exception:
        pass
    if not passed:
        _cleanup_worktree(store, patch_id)
    return {**store.get_patch(patch_id), "evidence_id": evidence["id"], "test": summary}


def record_review(
    store: Store,
    patch_id: str,
    verdict: str,
    reviewer: str,
    notes: str = "",
) -> dict[str, Any]:
    patch = store.get_patch(patch_id)
    if patch["status"] not in {"tested", "review_failed"}:
        raise ValidationError("patch must be tested before review")
    if verdict not in {"pass", "fail"}:
        raise ValidationError("review verdict must be pass or fail")
    if not reviewer or len(reviewer) > 200:
        raise ValidationError("reviewer is required")
    ledger = EvidenceLedger(store)
    evidence = ledger.record(
        criterion_key="selfdev.review",
        kind="selfdev_review",
        collector="director.selfdev",
        check_name="selfdev_review",
        check_version="selfdev/1.0",
        outcome="pass" if verdict == "pass" else "fail",
        subject_path=patch["patch_path"],
        params={"reviewer": reviewer, "notes": redact_text(notes)[:2000], "base_commit": patch["base_commit"]},
        environment=environment_snapshot(),
        confidence=0.8,
        limitations="human/agent review record; not a security audit",
        raw_ref=patch.get("test_output_ref"),
    )
    store.update_patch(
        patch_id,
        status="reviewed" if verdict == "pass" else "review_failed",
        review_verdict=verdict,
        reviewer=reviewer,
        review_notes=redact_text(notes)[:4000],
    )
    return {**store.get_patch(patch_id), "evidence_id": evidence["id"]}


def merge_patch(store: Store, patch_id: str, reason: str = "owner approved") -> dict[str, Any]:
    patch = store.get_patch(patch_id)
    if patch["status"] != "reviewed" or patch["review_verdict"] != "pass":
        raise ValidationError("patch must pass independent review before merge")
    root = Path(store.root)
    if _git(["status", "--porcelain"], root):
        raise ValidationError("working tree is not clean")
    current = _git(["rev-parse", "HEAD"], root)
    if current != patch["base_commit"]:
        raise ValidationError("HEAD moved since the patch base; rebase the proposal")
    if not patch.get("worktree"):
        raise ValidationError("tested worktree is missing; rerun the test")
    worktree = ensure_within(root / patch["worktree"], root)
    if not worktree.is_dir():
        raise ValidationError("tested worktree is missing; rerun the test")

    approval_id = store.request_approval(
        action_key=f"selfdev_merge:{patch_id}",
        details={"patch_id": patch_id, "changed_files": patch["changed_files"], "base_commit": current},
        reason=reason,
    )
    store.decide_approval(approval_id, "approved", "owner", reason)

    _git(["add", "-A"], worktree)
    _git(
        [
            "-c",
            "user.name=DIRECTOR",
            "-c",
            "user.email=director@local",
            "commit",
            "-m",
            f"selfdev: {patch['title'][:120]}",
        ],
        worktree,
    )
    commit = _git(["rev-parse", "HEAD"], worktree)
    branch = f"selfdev/{patch_id}"
    _git(["branch", "-f", branch, commit], root)
    try:
        _git(["merge", "--ff-only", branch], root)
    except ValidationError:
        raise
    store.update_patch(patch_id, status="merged", merge_commit=commit)
    try:
        from . import audit

        audit.log(store, "owner", "selfdev.merge", patch_id, "merged", {"commit": commit})
    except Exception:
        pass
    ledger = EvidenceLedger(store)
    evidence = ledger.record(
        criterion_key="selfdev.merge",
        kind="selfdev_merge",
        collector="director.selfdev",
        check_name="selfdev_merge",
        check_version="selfdev/1.0",
        outcome="pass",
        subject_path=patch["patch_path"],
        params={
            "base_commit": current,
            "merge_commit": commit,
            "approval_id": approval_id,
            "changed_files": bounded_json_loads(patch["changed_files"], max_bytes=32 * 1024),
        },
        environment=environment_snapshot(),
        confidence=0.95,
        limitations="local fast-forward merge only; no push/deploy",
        raw_ref=patch.get("test_output_ref"),
    )
    _cleanup_worktree(store, patch_id)
    return {
        **store.get_patch(patch_id),
        "merge_commit": commit,
        "approval_id": approval_id,
        "evidence_id": evidence["id"],
    }


def _cleanup_worktree(store: Store, patch_id: str) -> None:
    patch = store.get_patch(patch_id)
    rel = patch.get("worktree")
    if not rel:
        return
    worktree = ensure_within(Path(store.root) / rel, Path(store.root))
    _git_capture(["worktree", "remove", "--force", str(worktree)], Path(store.root))
    shutil.rmtree(worktree, ignore_errors=True)
    store.update_patch(patch_id, worktree=None)


def cleanup(store: Store) -> dict[str, Any]:
    cleaned = []
    for patch in store.list_patches(limit=1000):
        if patch.get("worktree"):
            _cleanup_worktree(store, patch["id"])
            cleaned.append(patch["id"])
    return {"cleaned": cleaned}


def patch_diff(store: Store, patch_id: str, max_bytes: int = 64 * 1024) -> str:
    patch = store.get_patch(patch_id)
    text = _patch_file(store, patch).read_text(encoding="utf-8")
    return text[:max_bytes]


def _json(value: Any) -> str:
    text, _ = dump_bounded(value, max_bytes=64 * 1024)
    return text
