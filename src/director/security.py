"""Security primitives: path/link safety, bounded parsing, secret redaction.

These are defense-in-depth controls, not a kernel sandbox. DIRECTOR only
enforces effects it actually mediates.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from pathlib import Path
from typing import Any, Iterable

MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 200_000
MAX_TEXT_CHARS = 1_000_000
MAX_PATH_CHARS = 4096
MAX_REDACT_SCAN = 4 * 1024 * 1024
MAX_MCP_FRAME = 1024 * 1024
MAX_OUTPUT_BYTES = 256 * 1024
MAX_FINDINGS = 500

_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class SafetyError(Exception):
    """Base class for rejected untrusted input."""


class BoundsError(SafetyError):
    """Input or output exceeded a declared bound."""


class PathSafetyError(SafetyError):
    """A path crossed a declared boundary or used a link."""


class SecretLeakError(SafetyError):
    """A secret-like value was found where it must not be stored."""


class ValidationError(SafetyError):
    """A typed value failed validation. Messages never echo raw values."""


# ---------------------------------------------------------------------------
# Hashing and time-free helpers
# ---------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8", "surrogatepass"))


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_object(obj: Any) -> str:
    return sha256_text(canonical_json(obj))


def estimate_tokens(text: str) -> int:
    """Rough estimate only (4 chars/token); label it as an estimate."""
    return int(math.ceil(len(text) / 4.0))


# ---------------------------------------------------------------------------
# Link / path safety
# ---------------------------------------------------------------------------


def _is_link(st: os.stat_result) -> bool:
    if stat.S_ISLNK(st.st_mode):
        return True
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & _REPARSE)


def is_link_like(st: os.stat_result) -> bool:
    """Public link/junction/reparse detector for walking code."""
    return _is_link(st)


def _norm(path: os.PathLike[str] | str) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def ensure_within(path: os.PathLike[str] | str, root: os.PathLike[str] | str) -> Path:
    """Return an absolute path proven to be inside ``root`` (no resolution)."""
    raw = os.fspath(path)
    if len(raw) > MAX_PATH_CHARS:
        raise PathSafetyError("path exceeds maximum length")
    root_abs = os.path.abspath(os.fspath(root))
    path_abs = os.path.abspath(raw)
    try:
        common = os.path.commonpath([_norm(root_abs), _norm(path_abs)])
    except ValueError as exc:  # different drives
        raise PathSafetyError("path is on a different volume") from exc
    if common != _norm(root_abs):
        raise PathSafetyError("path escapes the declared project root")
    return Path(path_abs)


def assert_no_links(path: os.PathLike[str] | str, root: os.PathLike[str] | str) -> None:
    """Reject symlinks, junctions and reparse points from root down to path."""
    target = ensure_within(path, root)
    root_path = Path(os.path.abspath(os.fspath(root)))
    rel = target.relative_to(root_path)
    cur = root_path
    for part in rel.parts:
        cur = cur / part
        try:
            st = os.lstat(cur)
        except FileNotFoundError:
            continue
        if _is_link(st):
            raise PathSafetyError(f"link/reparse point rejected at '{part}'")
    try:
        st = os.lstat(root_path)
        if _is_link(st):
            raise PathSafetyError("project root is a link/reparse point")
    except FileNotFoundError:
        raise PathSafetyError("project root does not exist")


def _read_fd_all(fd: int, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= limit:
        chunk = os.read(fd, min(65536, limit + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


def safe_read_bytes(
    path: os.PathLike[str] | str,
    root: os.PathLike[str] | str,
    max_bytes: int = MAX_JSON_BYTES,
) -> bytes:
    """Read a regular, non-linked, non-hardlinked file with a hard byte cap."""
    target = ensure_within(path, root)
    assert_no_links(target, root)
    try:
        before = os.lstat(target)
    except FileNotFoundError as exc:
        raise PathSafetyError("file does not exist") from exc
    if not stat.S_ISREG(before.st_mode):
        raise PathSafetyError("not a regular file")
    if before.st_nlink > 1:
        raise PathSafetyError("hardlinked file rejected")
    if before.st_size > max_bytes:
        raise BoundsError(f"file exceeds {max_bytes} byte limit")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(target), flags)
    except OSError as exc:
        raise PathSafetyError("file could not be opened safely") from exc
    try:
        after = os.fstat(fd)
        if after.st_nlink > 1:
            raise PathSafetyError("hardlinked file rejected on open")
        if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
            raise PathSafetyError("file was replaced during open")
        if not stat.S_ISREG(after.st_mode):
            raise PathSafetyError("not a regular file")
        data = _read_fd_all(fd, max_bytes)
    finally:
        os.close(fd)
    if len(data) > max_bytes:
        raise BoundsError(f"file exceeds {max_bytes} byte limit")
    return data


def safe_hash_file(
    path: os.PathLike[str] | str,
    root: os.PathLike[str] | str,
    max_bytes: int = 64 * 1024 * 1024,
) -> tuple[str, int]:
    data = safe_read_bytes(path, root, max_bytes=max_bytes)
    return sha256_bytes(data), len(data)


def prepare_state_dir(project_root: os.PathLike[str] | str) -> Path:
    root = Path(os.path.abspath(os.fspath(project_root)))
    if not root.is_dir():
        raise PathSafetyError("project root is not a directory")
    assert_no_links(root, root)
    state = root / ".director"
    if state.exists():
        st = os.lstat(state)
        if _is_link(st) or not stat.S_ISDIR(st.st_mode):
            raise PathSafetyError("state directory is not a plain directory")
    else:
        os.makedirs(state, exist_ok=False)
    assert_no_links(state, root)
    return state


_RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def check_simple_filename(name: str) -> str:
    if not name or len(name) > 128:
        raise PathSafetyError("invalid filename length")
    if name in (".", "..") or "/" in name or "\\" in name:
        raise PathSafetyError("filename must be a simple name")
    if name.split(".")[0].lower() in _RESERVED_NAMES:
        raise PathSafetyError("reserved device name rejected")
    return name


def safe_state_db_path(state: os.PathLike[str] | str, name: str = "director.db") -> Path:
    check_simple_filename(name)
    state_path = Path(os.path.abspath(os.fspath(state)))
    db = state_path / name
    if db.exists():
        st = os.lstat(db)
        if _is_link(st) or not stat.S_ISREG(st.st_mode):
            raise PathSafetyError("state database is not a plain file")
        if st.st_nlink > 1:
            raise PathSafetyError("state database is hardlinked")
    return db


def atomic_write_bytes(
    path: os.PathLike[str] | str,
    data: bytes,
    root: os.PathLike[str] | str | None = None,
) -> None:
    target = Path(os.path.abspath(os.fspath(path)))
    if root is not None:
        ensure_within(target, root)
    parent = target.parent
    os.makedirs(parent, exist_ok=True)
    tmp = parent / f".{target.name}.{os.getpid()}.tmp"
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            try:
                os.unlink(tmp)
            except OSError:
                pass


def atomic_write_text(
    path: os.PathLike[str] | str,
    text: str,
    root: os.PathLike[str] | str | None = None,
) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), root=root)


# ---------------------------------------------------------------------------
# Secret detection and redaction
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private_key",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----.*?"
            r"-----END (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("stripe_key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{16,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("bearer", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*")),
    (
        "generic_secret",
        re.compile(
            r"(?i)\b(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|"
            r"authorization)\b\s*[:=]\s*[\"']?([^\s\"'#]{6,})"
        ),
    ),
)


def redact_text(text: str, max_chars: int = MAX_REDACT_SCAN) -> str:
    if not isinstance(text, str):
        text = str(text)
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    for kind, pattern in _SECRET_PATTERNS:
        text = pattern.sub(f"[REDACTED:{kind}]", text)
    if truncated:
        text += "\n[TRUNCATED:redaction-scan-limit]"
    return text


def scan_secrets(text: str, max_hits: int = 1000) -> list[dict[str, Any]]:
    """Return secret *locations*, never the secret value itself."""
    if not isinstance(text, str):
        return []
    text = text[:MAX_REDACT_SCAN]
    hits: list[dict[str, Any]] = []
    for kind, pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            hits.append({"kind": kind, "line": line})
            if len(hits) >= max_hits:
                return hits
    return hits


def contains_secret(text: str) -> bool:
    return bool(scan_secrets(text, max_hits=1))


def safe_error_message(exc: BaseException, max_len: int = 240) -> str:
    message = f"{type(exc).__name__}: {exc}"
    message = redact_text(message, max_chars=max_len)
    message = " ".join(message.split())
    return message[:max_len]


# ---------------------------------------------------------------------------
# Bounded JSON
# ---------------------------------------------------------------------------


def _reject_constant(value: str) -> Any:
    raise BoundsError("non-finite JSON number rejected")


def _check_shape(obj: Any, max_depth: int, max_nodes: int) -> None:
    stack: list[tuple[Any, int]] = [(obj, 1)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            raise BoundsError("JSON node count exceeded")
        if depth > max_depth:
            raise BoundsError("JSON nesting too deep")
        if isinstance(value, dict):
            stack.extend((k, depth + 1) for k in value.keys())
            stack.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, (list, tuple)):
            stack.extend((v, depth + 1) for v in value)


def bounded_json_loads(
    data: bytes | str,
    max_bytes: int = MAX_JSON_BYTES,
    max_depth: int = MAX_JSON_DEPTH,
    max_nodes: int = MAX_JSON_NODES,
) -> Any:
    if isinstance(data, str):
        raw = data.encode("utf-8", "strict")
    elif isinstance(data, (bytes, bytearray)):
        raw = bytes(data)
    else:
        raise BoundsError("JSON input must be bytes or text")
    if len(raw) > max_bytes:
        raise BoundsError(f"input exceeds {max_bytes} bytes")
    try:
        obj = json.loads(raw, parse_constant=_reject_constant)
    except BoundsError:
        raise
    except RecursionError as exc:
        raise BoundsError("JSON nesting too deep") from exc
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValidationError("malformed JSON input") from exc
    _check_shape(obj, max_depth, max_nodes)
    return obj


def _shrink(obj: Any, max_str: int, max_items: int, depth: int = 0) -> Any:
    if depth > 10:
        return "[depth-limit]"
    if isinstance(obj, str):
        if len(obj) > max_str:
            return obj[:max_str] + f"...[truncated {len(obj) - max_str} chars]"
        return obj
    if isinstance(obj, dict):
        items = list(obj.items())
        result: dict[str, Any] = {}
        for key, value in items[:max_items]:
            result[str(key)[:200]] = _shrink(value, max_str, max_items, depth + 1)
        if len(items) > max_items:
            result["_omitted_keys"] = len(items) - max_items
        return result
    if isinstance(obj, (list, tuple)):
        result_list = [_shrink(v, max_str, max_items, depth + 1) for v in obj[:max_items]]
        if len(obj) > max_items:
            result_list.append(f"[omitted {len(obj) - max_items} items]")
        return result_list
    return obj


def dump_bounded(
    obj: Any,
    max_bytes: int = MAX_OUTPUT_BYTES,
    ensure_ascii: bool = False,
) -> tuple[str, bool]:
    """Serialize to bounded valid JSON. Returns (text, truncated)."""
    try:
        text = json.dumps(obj, ensure_ascii=ensure_ascii, default=str)
    except (TypeError, RecursionError):
        text = json.dumps({"_error": "unserializable output"}, ensure_ascii=True)
        return text, True
    if len(text.encode("utf-8")) <= max_bytes:
        return text, False
    for max_str, max_items in ((4000, 200), (1000, 50), (300, 20), (100, 10)):
        candidate = _shrink(obj, max_str, max_items)
        if isinstance(candidate, dict):
            candidate = dict(candidate)
            candidate["_truncated"] = True
        text = json.dumps(candidate, ensure_ascii=ensure_ascii, default=str)
        if len(text.encode("utf-8")) <= max_bytes:
            return text, True
    fallback = {
        "_truncated": True,
        "_reason": f"serialized output exceeded {max_bytes} bytes",
        "_original_type": type(obj).__name__,
    }
    return json.dumps(fallback, ensure_ascii=ensure_ascii), True


def bounded_text(text: str, max_chars: int = MAX_TEXT_CHARS) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars] + "\n[TRUNCATED]", True


def normalise_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def safe_relpath(path: os.PathLike[str] | str, root: os.PathLike[str] | str) -> str:
    target = ensure_within(path, root)
    root_path = Path(os.path.abspath(os.fspath(root)))
    return target.relative_to(root_path).as_posix()


def iter_text_lines(data: bytes, max_lines: int = 100_000) -> Iterable[str]:
    text = data.decode("utf-8", "replace")
    for index, line in enumerate(text.splitlines()):
        if index >= max_lines:
            break
        yield line
