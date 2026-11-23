from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from director.evidence import EvidenceLedger
from director.improve import author_patch
from director.lifecycle import process_one
from director.models import Budgets, PermissionPolicy
from director.policy import PolicyGateway
from director.security import ValidationError
from director.selfdev import create_patch, merge_patch, record_review, test_patch as run_patch_tests
from director.store import Store
from tests.helpers import make_contract

PATCH = """diff --git a/src/x.py b/src/x.py
--- a/src/x.py
+++ b/src/x.py
@@ -1 +1,2 @@
 value = 1
+extra = 2
"""

BAD_PATCH = """diff --git a/docs/research/x.md b/docs/research/x.md
--- a/docs/research/x.md
+++ b/docs/research/x.md
@@ -1 +1 @@
-old
+new
"""


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _repo(tmp_path: Path) -> tuple[Store, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "core.autocrlf", "false")
    (root / ".gitignore").write_text(".director/\nvar/\n__pycache__/\n.pytest_cache/\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "x.py").write_bytes(b"value = 1\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_smoke.py").write_text(
        "def test_smoke():\n    assert True\n", encoding="utf-8", newline="\n"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "init")
    store = Store.open_or_create(root, "selfdev")
    store.save_contract(
        make_contract(
            store.project_id,
            permissions=PermissionPolicy(allowed_actions=("read_artifact", "model_call_local")),
            budgets=Budgets(max_model_calls=2, max_wall_seconds=60),
        )
    )
    return store, root


def test_patch_test_review_merge_end_to_end(tmp_path):
    store, root = _repo(tmp_path)
    try:
        patch = create_patch(store, PATCH, "add extra value")
        assert patch["status"] == "proposed"
        tested = run_patch_tests(
            store,
            patch["id"],
            command=[
                sys.executable,
                "-c",
                "from pathlib import Path; assert 'extra = 2' in Path('src/x.py').read_text()",
            ],
        )
        assert tested["status"] == "tested"
        assert tested["test"]["passed"] is True
        evidence = store.list_evidence(limit=20)
        assert any(row["criterion_key"] == "selfdev.patch" and row["outcome"] == "pass" for row in evidence)
        with pytest.raises(ValidationError):
            merge_patch(store, patch["id"])
        reviewed = record_review(store, patch["id"], "pass", "independent-reviewer", "diff checked")
        assert reviewed["status"] == "reviewed"
        merged = merge_patch(store, patch["id"], reason="owner test")
        assert merged["status"] == "merged"
        assert (root / "src" / "x.py").read_text(encoding="utf-8") == "value = 1\nextra = 2\n"
        subject = _git(root, "log", "-1", "--format=%s")
        assert subject.startswith("selfdev:")
        assert store.get_patch(patch["id"])["merge_commit"]
    finally:
        store.close()


def test_patch_rejects_disallowed_paths_and_binary(tmp_path):
    store, _root = _repo(tmp_path)
    try:
        with pytest.raises(ValidationError):
            create_patch(store, BAD_PATCH, "research edit")
        with pytest.raises(ValidationError):
            create_patch(store, "GIT binary patch\n", "binary")
    finally:
        store.close()


def test_local_model_authors_a_patch_into_the_pipeline(tmp_path, monkeypatch):
    store, _root = _repo(tmp_path)
    responses = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            body = json.dumps(
                {
                    "response": PATCH,
                    "prompt_eval_count": 12,
                    "eval_count": 24,
                    "done": True,
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("OLLAMA_HOST", f"http://127.0.0.1:{server.server_port}")
        PolicyGateway(store).grant("director.model", "model_call_local", "provider:ollama", 1)
        proposal_id = store.add_proposal(
            signature="manual:model-author",
            title="add extra value",
            rationale="exercise local model authoring",
            category="manual",
            risk="medium",
            expected_impact="test",
            files=["src/x.py"],
            required_checks=["tests"],
        )
        result = author_patch(
            store,
            proposal_id,
            provider="ollama",
            model="mock-coder",
            test=True,
        )
        assert result["patch"]["status"] == "tested"
        assert result["patch"]["author"].startswith("model:ollama/")
        assert result["usage"]["model_calls"] == 1
        assert store.model_calls_spent() == 1
        assert (result["test"]["test"]["passed"]) is True
    finally:
        server.shutdown()
        server.server_close()
        store.close()


def test_worker_can_test_a_queued_patch(tmp_path):
    store, _root = _repo(tmp_path)
    try:
        patch = create_patch(store, PATCH, "worker tested patch")
        store.enqueue_investigation(
            "test queued patch",
            "worktree tests decide the state",
            payload={"action": "selfdev_test", "patch_id": patch["id"]},
            dedupe_key="selfdev:test:worker",
        )
        result = process_one(store, worker="worker-test")
        assert result["claimed"] is True
        assert result["status"] == "completed"
        assert store.get_patch(patch["id"])["status"] == "tested"
        assert store.list_investigations(status="completed")
    finally:
        store.close()


def test_failed_patch_records_evidence_and_finding(tmp_path):
    store, _root = _repo(tmp_path)
    try:
        patch = create_patch(store, PATCH, "failing patch")
        result = run_patch_tests(
            store,
            patch["id"],
            command=[sys.executable, "-c", "raise SystemExit(1)"],
        )
        assert result["status"] == "failed"
        assert result["test"]["passed"] is False
        assert result["worktree"] is None
        evidence = store.list_evidence(limit=20, criterion_key="selfdev.patch")
        assert evidence and evidence[0]["outcome"] == "fail"
        findings = store.list_findings()
        assert any(item["kind"] == "selfdev_test_failed" for item in findings)
    finally:
        store.close()
