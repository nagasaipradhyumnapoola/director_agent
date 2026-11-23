from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from director.analysis import ArtifactScanner, ScanConfig
from director.security import (
    BoundsError,
    PathSafetyError,
    bounded_json_loads,
    dump_bounded,
    ensure_within,
    redact_text,
    safe_error_message,
    safe_read_bytes,
    safe_state_db_path,
    scan_secrets,
)
from tests.helpers import new_store, write


def test_redaction_removes_secret_and_not_in_errors():
    secret = "sk-abcdefghijklmnopqrstuvwxyz0123456789"
    text = f"token = {secret}"
    redacted = redact_text(text)
    assert secret not in redacted
    assert "REDACTED" in redacted
    assert scan_secrets(text)[0]["kind"] in {"openai_key", "generic_secret"}
    message = safe_error_message(ValueError(f"bad value {secret}"))
    assert secret not in message


def test_bounded_json_rejects_oversize_depth_and_nonfinite():
    with pytest.raises(BoundsError):
        bounded_json_loads(b"[" * 10 + b"]" * 10, max_bytes=4)
    with pytest.raises(BoundsError):
        bounded_json_loads(json.dumps({"a": "x" * 1000}), max_bytes=100)
    deep = "[" * 50 + "0" + "]" * 50
    with pytest.raises(BoundsError):
        bounded_json_loads(deep, max_depth=10)


def test_dump_bounded_is_valid_bounded_json():
    payload = {"items": [{"text": "x" * 5000} for _ in range(200)]}
    text, truncated = dump_bounded(payload, max_bytes=4096)
    assert truncated is True
    assert len(text.encode("utf-8")) <= 4096
    json.loads(text)


def test_traversal_and_hardlink_and_size_limits(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    with pytest.raises(PathSafetyError):
        ensure_within(outside, root)
    linked = root / "hard.txt"
    linked.write_text("secret", encoding="utf-8")
    try:
        os.link(linked, root / "second.txt")
    except OSError:
        pytest.skip("hardlinks unavailable on this filesystem")
    with pytest.raises(PathSafetyError):
        safe_read_bytes(linked, root)
    big = root / "big.txt"
    big.write_text("x" * 100, encoding="utf-8")
    with pytest.raises(BoundsError):
        safe_read_bytes(big, root, max_bytes=10)
    db = root / "state.db"
    db.write_text("x", encoding="utf-8")
    os.link(db, root / "db-link.db")
    with pytest.raises(PathSafetyError):
        safe_state_db_path(root, "db-link.db")


def test_junction_rejected_and_scanned(tmp_path):
    if os.name != "nt":
        pytest.skip("junction test is Windows-only")
    store = new_store(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside secret", encoding="utf-8")
    junction = Path(store.root) / "linked"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip("junction creation not permitted")
    try:
        scan = ArtifactScanner(store).scan()
        assert scan.outcome == "fail"
        kinds = {finding["kind"] for finding in scan.findings}
        assert "link_boundary" in kinds
        assert any(finding["severity"] == "critical" for finding in scan.findings)
    finally:
        try:
            os.rmdir(junction)
        except OSError:
            pass
        store.close()


def test_uppercase_suffix_is_syntax_checked(tmp_path):
    store = new_store(tmp_path)
    write(Path(store.root), "broken.PY", "def x(:\n")
    write(Path(store.root), "ok.JSON", '{"ok": true}\n')
    write(Path(store.root), "bad.JSON", '{"ok": false,}\n')
    scan = ArtifactScanner(store).scan()
    kinds = {(f["kind"], f["path"]) for f in scan.findings}
    assert ("syntax_error", "broken.PY") in kinds
    assert ("json_error", "bad.JSON") in kinds
    assert scan.outcome == "fail"
    store.close()


def test_unsupported_format_never_clean_pass(tmp_path):
    store = new_store(tmp_path)
    write(Path(store.root), "data.xyz", "unknown format\n")
    scan = ArtifactScanner(store).scan()
    assert scan.unknown_formats >= 1
    assert scan.outcome != "pass"
    assert any(f["kind"] == "unsupported_format" for f in scan.findings)
    store.close()


def test_secret_never_stored_or_echoed(tmp_path):
    secret = "AKIAABCDEFGHIJKLMNOP"
    store = new_store(tmp_path)
    write(Path(store.root), "leak.txt", f"aws = {secret}\n")
    scan = ArtifactScanner(store).scan()
    assert scan.outcome == "fail"
    serialized = json.dumps(scan.findings)
    assert secret not in serialized
    rows = store.list_findings()
    assert secret not in json.dumps(rows)
    assert any(f["kind"] == "secret_exposed" for f in rows)
    store.close()


def test_finding_bound_and_parent_metadata(tmp_path):
    store = new_store(tmp_path)
    for index in range(40):
        write(Path(store.root), f"f{index}.xyz", "unknown\n")
    scan = ArtifactScanner(store, ScanConfig(max_findings=5)).scan()
    assert len(scan.findings) <= 5
    assert scan.partial is True
    assert scan.omitted > 0
    assert scan.outcome == "partial"
    rows = store.list_findings(limit=100)
    assert rows
    for row in rows:
        assert row["receipt_id"] == scan.receipt_id
        assert row["evaluator_version"]
        assert row["source_sha256"]
        assert row["created_at"]
    report = Path(store.root) / scan.report_ref
    assert report.is_file()
    assert report.stat().st_size <= 256 * 1024 + 4096
    store.close()
def test_scan_snapshot_detects_new_junction_directory(tmp_path):
    from director.analysis import ArtifactScanner
    from director.evidence import EvidenceLedger

    if os.name != "nt":
        pytest.skip("junction test is Windows-only")
    store = new_store(tmp_path)
    write(tmp_path / "project", "safe.py", "print('ok')\n")
    scan = ArtifactScanner(store).scan()
    assert scan.outcome == "pass"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.txt").write_text("outside", encoding="utf-8")
    junction = Path(store.root) / "newlink"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        store.close()
        pytest.skip("junction creation not permitted")
    try:
        ledger = EvidenceLedger(store)
        verification = ledger.verify(scan.receipt_id)
        assert verification["fresh"] is False
        assert "scanned tree changed" in verification["reasons"]
        assert ledger.criterion_status()["complete"] is False
    finally:
        try:
            os.rmdir(junction)
        except OSError:
            pass
        store.close()


def test_partial_scan_receipt_is_consistent(tmp_path):
    from director.analysis import ArtifactScanner, ScanConfig

    store = new_store(tmp_path)
    for index in range(10):
        write(tmp_path / "project", f"x{index}.xyz", "unknown\n")
    scan = ArtifactScanner(store, ScanConfig(max_files=5)).scan(roots=[".", "."])
    assert scan.partial is True
    assert scan.outcome != "pass"
    report = json.loads((Path(store.root) / scan.report_ref).read_text(encoding="utf-8"))
    assert report["partial"] is True
    assert "snapshot" in report
    assert len(report["snapshot"]["sha256"]) == 64
    store.close()
