"""Lexical project memory with provenance, taint and explicit deletion."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from .security import (
    BoundsError,
    PathSafetyError,
    SecretLeakError,
    ValidationError,
    ensure_within,
    safe_read_bytes,
    scan_secrets,
)
from .store import Store


class MemoryIndex:
    """Thin, safe wrapper over the store's FTS-backed memory."""

    def __init__(self, store: Store):
        self.store = store
        self.root = Path(store.root)

    def add_text(
        self,
        text: str,
        title: str,
        path: str | None = None,
        tainted: bool = True,
        kind: str = "text",
    ) -> str:
        if scan_secrets(text, max_hits=1):
            raise SecretLeakError("secret-like content rejected from memory")
        return self.store.add_memory_source(
            text=text,
            title=title,
            path=path,
            tainted=tainted,
            kind=kind,
        )

    def add_file(
        self,
        rel_path: str,
        title: str | None = None,
        max_bytes: int = 8 * 1024 * 1024,
        tainted: bool = True,
    ) -> str:
        target = ensure_within(self.root / rel_path, self.root)
        data = safe_read_bytes(target, self.root, max_bytes=max_bytes)
        if b"\x00" in data[:8192]:
            raise ValidationError("binary files are not indexed as text")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("utf-8", "replace")
        if not text.strip():
            raise ValidationError("file is empty")
        if scan_secrets(text, max_hits=1):
            raise SecretLeakError("secret-like content rejected from memory")
        rel = target.relative_to(self.root).as_posix()
        return self.store.add_memory_source(
            text=text,
            title=title or Path(rel).name,
            path=rel,
            tainted=tainted,
            kind="file",
        )

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        return self.store.search_memory(query, limit=limit)

    def forget(self, source_id: str) -> None:
        self.store.forget_memory_source(source_id)

    def sources(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.list_memory_sources(limit=limit)
