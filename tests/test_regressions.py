"""Historical prototype defects encoded as regressions (docs/STATUS.md)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from director.analysis import ArtifactScanner, ScanConfig
from director.security import PathSafetyError, safe_state_db_path
from tests.helpers import new_store, write


def test_hardlinked_source_rejected(tmp_path):
    store = new_store(tmp_path)
    target = write(Path(store.root), "linked.py", "print('ok')\n")
    try:
        os.link(target, Path(store.root) / "alias.py")
    except OSError:
        pytest.skip("hardlinks unavailable")
    scan = ArtifactScanner(store).scan()
    assert scan.outcome == "fail"
    assert any(f["kind"] == "hardlink_boundary" and f["path"] == "linked.py" for f in scan.findings)
    store.close()


def test_hardlinked_state_db_rejected(tmp_path):
    store = new_store(tmp_path)
    db = store.path
    store.close()
    alias = db.parent / "alias.db"
    try:
        os.link(db, alias)
    except OSError:
        pytest.skip("hardlinks unavailable")
    with pytest.raises(PathSafetyError):
        safe_state_db_path(db.parent, "alias.db")


def test_output_bound_and_repeated_findings_deduped(tmp_path):
    store = new_store(tmp_path)
    for index in range(30):
        write(Path(store.root), f"file{index}.xyz", "unknown\n")
    scan = ArtifactScanner(store, ScanConfig(max_findings=3)).scan()
    assert len(scan.findings) <= 3
    assert scan.partial is True
    assert scan.omitted > 0
    assert scan.outcome == "partial"
    serialized = json.dumps(scan.findings)
    keys = [(f["kind"], f["path"], f["message"]) for f in scan.findings]
    assert len(keys) == len(set(keys))
    report = Path(store.root) / scan.report_ref
    assert report.stat().st_size <= 256 * 1024 + 4096
    store.close()


def test_uppercase_suffix_never_skipped(tmp_path):
    store = new_store(tmp_path)
    write(Path(store.root), "UPPER.PY", "def x(:\n")
    scan = ArtifactScanner(store).scan()
    assert any(f["kind"] == "syntax_error" and f["path"] == "UPPER.PY" for f in scan.findings)
    store.close()


def test_findings_carry_parent_metadata(tmp_path):
    store = new_store(tmp_path)
    write(Path(store.root), "leak.txt", "aws AKIAABCDEFGHIJKLMNOP\n")
    scan = ArtifactScanner(store).scan()
    rows = store.list_findings()
    assert rows
    for row in rows:
        assert row["receipt_id"] == scan.receipt_id
        assert row["evaluator_version"] == "artifact-scan/1.0"
        assert row["source_sha256"]
        assert row["created_at"]
        assert row["confidence"] is not None
        assert row["limitations"] is not None
    store.close()


def test_no_unchecked_format_passes(tmp_path):
    store = new_store(tmp_path)
    write(Path(store.root), "payload.xyz", "not checked\n")
    scan = ArtifactScanner(store).scan()
    assert scan.outcome == "partial"
    assert scan.unknown_formats == 1
    assert not any(f["severity"] in {"critical", "high"} for f in scan.findings)
    store.close()
