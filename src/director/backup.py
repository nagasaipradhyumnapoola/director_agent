"""Verified local backups and non-destructive restore.

Backups are ZIP archives containing a consistent SQLite online backup plus
receipts, proposals and patch artifacts. Restores go to a new project directory
only; they never overwrite an existing project.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .security import BoundsError, ValidationError, ensure_within, sha256_bytes
from .store import Store

MAX_DB_BYTES = 256 * 1024 * 1024
MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
MAX_FILE_BYTES = 16 * 1024 * 1024
ALLOWED_PREFIXES = ("receipts/", "proposals/", "patches/")


def _state(store: Store) -> Path:
    return Path(store.root) / ".director"


def _sha_file(path: Path, cap: int = MAX_FILE_BYTES) -> tuple[str, int]:
    st = path.stat()
    if st.st_size > cap:
        raise BoundsError("artifact exceeds backup file bound")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest(), st.st_size


def _collect(state: Path) -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []
    total = 0
    for prefix in ALLOWED_PREFIXES:
        directory = state / prefix.rstrip("/")
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(state).as_posix()
            if not any(rel.startswith(allowed) for allowed in ALLOWED_PREFIXES):
                continue
            size = path.stat().st_size
            total += size
            if total > MAX_ARTIFACT_BYTES:
                raise BoundsError("backup artifacts exceed size bound")
            out.append((path, rel))
    return out


def create_backup(store: Store) -> dict[str, Any]:
    state = _state(store)
    backups = state / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backups / f"director-{stamp}-{uuid.uuid4().hex[:6]}.zip"
    temp = Path(tempfile.mkdtemp(prefix="director-backup-"))
    try:
        db_copy = temp / "director.db"
        dest = sqlite3.connect(str(db_copy))
        try:
            store.conn.backup(dest)
        finally:
            dest.close()
        db_sha, db_size = _sha_file(db_copy, MAX_DB_BYTES)
        files: list[dict[str, Any]] = []
        entries: list[tuple[Path, str]] = [(db_copy, "director.db")]
        for path, rel in _collect(state):
            digest, size = _sha_file(path)
            files.append({"path": rel, "sha256": digest, "bytes": size})
            entries.append((path, rel))
        manifest = {
            "schema": "director.backup.v1",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "director_version": __version__,
            "project_id": store.project_id,
            "schema_version": int(store.conn.execute("PRAGMA user_version").fetchone()[0]),
            "database": {"path": "director.db", "sha256": db_sha, "bytes": db_size},
            "files": files,
        }
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            for path, arcname in entries:
                archive.write(path, arcname)
        digest, size = _sha_file(target, 512 * 1024 * 1024)
        return {
            "backup": target.relative_to(Path(store.root)).as_posix(),
            "bytes": size,
            "sha256": digest,
            "project_id": store.project_id,
            "files": len(files),
            "database_bytes": db_size,
            "created_at": manifest["created_at"],
        }
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def list_backups(store: Store) -> list[dict[str, Any]]:
    directory = _state(store) / "backups"
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.zip"), reverse=True):
        st = path.stat()
        out.append(
            {
                "backup": path.relative_to(Path(store.root)).as_posix(),
                "bytes": st.st_size,
                "modified_at": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds"),
            }
        )
    return out


def _safe_name(name: str) -> bool:
    if name.startswith("/") or "\\" in name or name.startswith("../") or "/../" in name:
        return False
    if name.startswith(".") or ":" in name:
        return False
    return name == "manifest.json" or name == "director.db" or any(
        name.startswith(prefix) for prefix in ALLOWED_PREFIXES
    )


def verify_backup(path: os.PathLike[str] | str) -> dict[str, Any]:
    backup = Path(path)
    if not backup.is_file():
        raise ValidationError("backup file not found")
    try:
        archive = zipfile.ZipFile(backup, "r")
    except zipfile.BadZipFile as exc:
        raise ValidationError("invalid backup archive") from exc
    with archive:
        names = archive.namelist()
        if "manifest.json" not in names or "director.db" not in names:
            raise ValidationError("backup missing manifest or database")
        for name in names:
            if not _safe_name(name):
                raise ValidationError("backup contains an unsafe path")
        try:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        except Exception as exc:
            raise ValidationError("backup manifest unreadable") from exc
        if not isinstance(manifest, dict) or manifest.get("schema") != "director.backup.v1":
            raise ValidationError("unsupported backup manifest")
        db_info = manifest.get("database") or {}
        data = archive.read("director.db")
        if len(data) > MAX_DB_BYTES:
            raise BoundsError("backup database exceeds bound")
        if sha256_bytes(data) != db_info.get("sha256"):
            raise ValidationError("backup database hash mismatch")
        for entry in manifest.get("files") or []:
            name = str(entry.get("path"))
            if not _safe_name(name):
                raise ValidationError("backup manifest contains unsafe path")
            payload = archive.read(name)
            if sha256_bytes(payload) != entry.get("sha256"):
                raise ValidationError(f"backup file hash mismatch: {name}")
        temp = Path(tempfile.mkdtemp(prefix="director-verify-"))
        try:
            db_path = temp / "director.db"
            db_path.write_bytes(data)
            conn = sqlite3.connect(str(db_path))
            try:
                check = conn.execute("PRAGMA quick_check").fetchone()[0]
            finally:
                conn.close()
            if check != "ok":
                raise ValidationError("backup database integrity check failed")
        finally:
            shutil.rmtree(temp, ignore_errors=True)
        return {
            "backup": str(backup),
            "project_id": manifest.get("project_id"),
            "created_at": manifest.get("created_at"),
            "files": len(manifest.get("files") or []),
            "database_bytes": db_info.get("bytes"),
            "integrity": "ok",
        }


def restore_backup(path: os.PathLike[str] | str, target_root: os.PathLike[str] | str) -> dict[str, Any]:
    summary = verify_backup(path)
    target = Path(target_root).resolve()
    if target.exists() and any(target.iterdir()):
        raise ValidationError("restore target must be new or empty")
    target.mkdir(parents=True, exist_ok=True)
    state = target / ".director"
    state.mkdir(exist_ok=True)
    with zipfile.ZipFile(path, "r") as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        allowed = ["director.db"] + [entry["path"] for entry in manifest.get("files") or []]
        for name in allowed:
            if not _safe_name(name):
                raise ValidationError("unsafe restore path")
            destination = ensure_within(state / name, target)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(name))
    return {
        **summary,
        "restored_to": str(target),
        "note": "open the restored directory with 'director status'; the original project was not modified",
    }
