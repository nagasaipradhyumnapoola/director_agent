"""Compatibility wrapper: OpenCode-specific adapter generation."""

from __future__ import annotations

from pathlib import Path

from .adapter import generate as _generate


def generate(
    out_dir: Path,
    project_root: Path,
    db_path: Path,
    force: bool = False,
) -> list[str]:
    return _generate("opencode", out_dir, project_root, db_path, force=force)
