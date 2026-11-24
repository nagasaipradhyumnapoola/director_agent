"""DIRECTOR operator CLI."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Sequence

from . import RELEASE_TARGET, __version__
from .adapter import SUPPORTED_HOSTS, generate as generate_adapter
from . import audit as audit_log
from .agent import run_agent
from .analysis import ArtifactScanner, ScanConfig
from .autonomy import disable as autonomy_disable, enable as autonomy_enable, maybe_run as autonomy_run, status as autonomy_status
from .backup import create_backup, list_backups, prune_backups, restore_backup, verify_backup
from .container import available as container_available, run as container_run
from .maintenance import (
    disable as maintenance_disable,
    enable as maintenance_enable,
    run_now as maintenance_run,
    status as maintenance_status,
)
from .context import ContextBuilder
from .demo import build_contract, run_demo
from .domains import PROFILES, provision_pilot_grants, run_pilot
from .evidence import EvidenceLedger
from .improve import add_manual_proposal, apply_proposal, author_patch, generate_proposals
from .keychain import (
    KeychainUnavailable,
    available as keychain_available,
    delete_secret,
    has_secret,
    set_secret,
)
from .policy import PolicyDenied, PolicyGateway
from .providers import PROVIDERS, call_model
from .service import install as service_install, remove as service_remove, status as service_status
from .ui import serve_ui
from .recipes import RECIPES, run_recipe
from .router import route as route_task
from .selfdev import (
    cleanup as selfdev_cleanup,
    create_patch,
    merge_patch,
    patch_diff,
    record_review,
    test_patch,
)
from .lifecycle import (
    pause as lifecycle_pause,
    process_one,
    read_lifecycle,
    recover as lifecycle_recover,
    resume as lifecycle_resume,
    start as lifecycle_start,
    status as lifecycle_status,
    stop as lifecycle_stop,
    worker_loop,
)
from .mcp_server import open_store_from_db, serve as mcp_serve
from .memory import MemoryIndex
from .models import KNOWN_ACTIONS, SUPPORTED_DOMAINS, TaskContract
from .security import (
    BoundsError,
    SafetyError,
    ValidationError,
    atomic_write_text,
    bounded_json_loads,
    dump_bounded,
    ensure_within,
    prepare_state_dir,
    redact_text,
    safe_error_message,
    safe_state_db_path,
)
from .store import BudgetExceeded, ConflictError, NotFoundError, Store, StoreError


def _root(args: argparse.Namespace, create: bool = False) -> Path:
    root = Path(args.root).resolve()
    if not root.is_dir():
        if create:
            root.mkdir(parents=True, exist_ok=True)
        else:
            raise ValidationError("project root is not a directory")
    return root


def _open(root: Path) -> Store:
    if not (root / ".director").is_dir():
        raise ValidationError("project not initialized; run 'director init'")
    store = Store.open(root)
    if not store.get_meta("project_id"):
        store.close()
        raise ValidationError("project has no identity; run 'director init'")
    return store


def _emit(obj: Any, max_bytes: int = 512 * 1024) -> str:
    text, truncated = dump_bounded(obj, max_bytes=max_bytes)
    print(text)
    if truncated:
        print("[output truncated to declared bound]", file=sys.stderr)
    return text


def _db_rel(root: Path, store: Store) -> str:
    return store.path.relative_to(root).as_posix()


def _read_json_file(path: Path, max_bytes: int = 4 * 1024 * 1024) -> Any:
    st = path.stat()
    if st.st_size > max_bytes:
        raise BoundsError(f"file exceeds {max_bytes} byte limit")
    return bounded_json_loads(path.read_bytes(), max_bytes=max_bytes)


# -- commands --------------------------------------------------------------
def cmd_init(args: argparse.Namespace) -> int:
    root = _root(args, create=args.create)
    store = Store.open_or_create(root, args.name or root.name)
    try:
        if args.contract:
            contract_path = Path(args.contract)
            if not contract_path.is_absolute():
                contract_path = root / contract_path
            data = _read_json_file(contract_path)
            if not isinstance(data, dict):
                raise ValidationError("contract file must contain an object")
            if not data.get("project_id") or data.get("project_id") in {"PLACEHOLDER", "placeholder"}:
                data["project_id"] = store.project_id
            contract = TaskContract.from_dict(data)
            store.save_contract(contract)
        elif store.latest_contract() is None:
            domains = tuple(args.domain or ["general"])
            store.save_contract(
                build_contract(store.project_id, domains, allow_container=args.allow_container)
            )
        latest = store.latest_contract()
        payload = {
            "project_id": store.project_id,
            "root": str(root),
            "database": _db_rel(root, store),
            "state_dir": str(store.path.parent),
            "contract": {
                "revision": latest[0]["revision"] if latest else None,
                "hash": latest[0]["hash"] if latest else None,
                "domains": list(latest[1].domains) if latest else [],
            },
            "release_target": RELEASE_TARGET,
        }
        _emit(payload)
    finally:
        store.close()
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    root = _root(args)
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, level: str = "error") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail, "level": level})

    add("python", sys.version_info >= (3, 11), sys.version.split()[0])
    import sqlite3

    add("sqlite", bool(sqlite3.sqlite_version), sqlite3.sqlite_version)
    state = root / ".director"
    add("state_dir", state.is_dir(), "present" if state.is_dir() else "missing; run init")
    db_ok = False
    if state.is_dir():
        try:
            prepare_state_dir(root)
            db_path = safe_state_db_path(state)
            db_ok = db_path.is_file()
            add("database_file", db_ok, "present" if db_ok else "missing")
        except SafetyError as exc:
            add("database_file", False, type(exc).__name__)
    if db_ok:
        store = _open(root)
        try:
            add("database_integrity", store.quick_check() == "ok", store.quick_check())
            add("fts5", store.fts_available, "available" if store.fts_available else "fallback LIKE")
            latest = store.latest_contract()
            add("contract", latest is not None, f"revision {latest[0]['revision']}" if latest else "missing")
            if latest:
                budgets = latest[1].budgets
                permissions = latest[1].permissions
                add("zero_model_budget", budgets.max_model_calls == 0, f"limit={budgets.max_model_calls}")
                add("zero_model_spend", store.model_calls_spent() == 0, f"spent={store.model_calls_spent():g}")
                add("external_network_off", not permissions.allow_external_network, "disabled")
                add("cloud_spend_off", not permissions.allow_cloud_spend, "disabled")
            lifecycle = lifecycle_status(store)
            add(
                "worker",
                not lifecycle["degraded"],
                "degraded" if lifecycle["degraded"] else str(lifecycle["lifecycle"].get("status")),
                level="warn" if lifecycle["degraded"] else "info",
            )
            schema = int(store.conn.execute("PRAGMA user_version").fetchone()[0])
            add("schema_version", schema == 4, str(schema))
            backups = list_backups(store)
            add("backup", bool(backups), backups[0]["modified_at"] if backups else "no backup yet", level="warn")
            keychain_ok, keychain_name = keychain_available()
            add("keychain", keychain_ok, keychain_name, level="warn")
            free = shutil.disk_usage(str(root)).free
            add("disk_space", free >= 1_000_000_000, f"{free // (1024 * 1024)} MiB free", level="warn")
        finally:
            store.close()
    import importlib.util

    add("mcp_sdk", importlib.util.find_spec("mcp") is not None, "installed" if importlib.util.find_spec("mcp") else "missing (tests skip)", level="warn")
    node_path = __import__("shutil").which("node"); add("node", node_path is not None, node_path or "missing (website pilot blocked)", level="warn")
    browser = next(
        (
            candidate
            for candidate in (
                os.environ.get("DIRECTOR_BROWSER"),
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                "/usr/bin/google-chrome",
                "/usr/bin/chromium",
            )
            if candidate and Path(candidate).is_file()
        ),
        None,
    )
    add("browser", browser is not None, browser or "missing (website pilot blocked)", level="warn")
    failures = [c for c in checks if not c["ok"] and c["level"] == "error"]
    payload = {
        "ok": not failures,
        "release_target": RELEASE_TARGET,
        "version": __version__,
        "checks": checks,
        "failures": [c["check"] for c in failures],
        "limitations": [
            "Process-level supervision is not a kernel sandbox.",
            "Native host tool-call compatibility is not proven by doctor.",
        ],
    }
    if args.json:
        _emit(payload)
    else:
        print(f"DIRECTOR {__version__} ({RELEASE_TARGET})")
        for check in checks:
            mark = "ok" if check["ok"] else ("warn" if check["level"] == "warn" else "FAIL")
            print(f"  [{mark:4}] {check['check']}: {check['detail']}")
        print("doctor:", "ok" if not failures else "failed")
    return 0 if not failures else 1


def cmd_status(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        summary = store.status_summary()
        acceptance = EvidenceLedger(store).criterion_status(verify=not args.no_verify)
        lifecycle = lifecycle_status(store)
        checkpoint = store.latest_checkpoint()
        payload = {
            **summary,
            "acceptance": acceptance,
            "lifecycle": lifecycle,
            "last_checkpoint": (
                {
                    "id": checkpoint["id"],
                    "created_at": checkpoint["created_at"],
                    "contract_revision": checkpoint["contract_revision"],
                }
                if checkpoint
                else None
            ),
            "database": _db_rel(root, store),
        }
        if args.json:
            _emit(payload)
        else:
            project = summary["project"]
            contract = summary["contract"]
            print(f"project: {project['name']} ({project['id']})")
            print(f"root: {project['root']}")
            print(f"contract: revision {contract['revision']} domains {contract['domains']} unsupported {contract['unsupported_domains']}")
            print(f"findings: {summary['findings'] or 'none'}")
            print(f"investigations: {summary['investigations'] or 'none'}")
            print(f"evidence: {summary['evidence'] or 'none'}")
            print(f"model calls spent: {summary['model_calls_spent']:g}")
            print(
                f"acceptance ({'verified' if not args.no_verify else 'UNVERIFIED'}): "
                f"{'complete' if acceptance['complete'] else 'incomplete'} unmet={acceptance['unmet']}"
            )
            print(f"worker: {lifecycle['lifecycle'].get('status')} degraded={lifecycle['degraded']}")
        return 0
    finally:
        store.close()


def cmd_contract(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        if args.action == "show":
            latest = store.latest_contract()
            if not latest:
                raise ValidationError("no contract saved")
            _emit({"revision": latest[0]["revision"], "hash": latest[0]["hash"], "contract": latest[1].to_dict()})
            return 0
        path = Path(args.file)
        if not path.is_absolute():
            path = root / path
        data = _read_json_file(path)
        if not isinstance(data, dict):
            raise ValidationError("contract file must contain an object")
        if not data.get("project_id") or data.get("project_id") in {"PLACEHOLDER", "placeholder"}:
            data["project_id"] = store.project_id
        contract = TaskContract.from_dict(data)
        contract_id = store.save_contract(contract)
        _emit({"contract_id": contract_id, "revision": contract.revision, "hash": contract.hash()})
        return 0
    finally:
        store.close()


def _scan_config(store: Store, args: argparse.Namespace) -> ScanConfig:
    latest = store.latest_contract()
    budgets = latest[1].budgets if latest else None
    return ScanConfig(
        max_files=args.max_files or (min(budgets.max_scan_files, 20000) if budgets else 2000),
        max_file_bytes=min(budgets.max_file_bytes, 8 * 1024 * 1024) if budgets else 1_048_576,
        max_findings=min(budgets.max_findings, 5000) if budgets else 500,
    )


def cmd_scan(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        scanner = ArtifactScanner(store, _scan_config(store, args))
        result = scanner.scan(roots=args.path or ["."], criterion_key=args.criterion)
        _emit(result.to_dict(), max_bytes=512 * 1024)
        return 0 if result.outcome == "pass" else 2
    finally:
        store.close()


def cmd_investigate(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        if args.run:
            _emit(process_one(store, worker=f"cli:{os.getpid()}"))
            return 0
        if args.list or not args.scan:
            _emit({"investigations": store.list_investigations(status=args.status, limit=args.limit)})
            return 0
        roots = args.path or ["."]
        for rel in roots:
            ensure_within(root / rel, root)
        investigation_id = store.enqueue_investigation(
            title="CLI requested artifact scan",
            hypothesis="A deterministic scan will surface unsafe or unsupported artifacts.",
            domain="general",
            priority=args.priority,
            payload={"action": "scan", "roots": roots},
            dedupe_key="scan:" + ",".join(roots),
        )
        _emit({"investigation_id": investigation_id, "status": "queued", "hint": "run 'director investigate --run' or 'director worker --once'"})
        return 0
    finally:
        store.close()


def cmd_worker(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        if args.once:
            _emit(process_one(store, worker=f"worker:{os.getpid()}"))
            return 0
        if not args.token:
            raise ValidationError("worker --loop requires --token from 'director start'")
        return worker_loop(store, args.token, poll_seconds=args.poll, once=False)
    finally:
        store.close()


def cmd_findings(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        if args.dismiss:
            if not args.reason:
                raise ValidationError("--reason is required with --dismiss")
            store.dismiss_finding(args.dismiss, args.reason)
            _emit({"dismissed": args.dismiss})
            return 0
        rows = store.list_findings(limit=args.limit, severity=args.severity) if args.severity else store.list_findings(limit=args.limit)
        _emit({"counts": store.finding_counts(), "findings": rows}, max_bytes=512 * 1024)
        return 0 if not rows else 2
    finally:
        store.close()


def cmd_evidence(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        ledger = EvidenceLedger(store)
        if args.verify:
            results = ledger.verify_all()
            _emit({"verification": results[:200], "omitted": max(0, len(results) - 200), "acceptance": ledger.criterion_status(verify=False)})
            return 0 if all(item["fresh"] for item in results) else 2
        rows = store.list_evidence(limit=args.limit, criterion_key=args.criterion)
        _emit({"evidence": rows}, max_bytes=512 * 1024)
        return 0
    finally:
        store.close()


def cmd_verify(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        acceptance = EvidenceLedger(store).criterion_status(verify=True)
        _emit({"acceptance": acceptance})
        return 0 if acceptance["complete"] else 2
    finally:
        store.close()


def cmd_waive(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        waiver_id = store.waive_criterion(args.criterion, args.reason)
        _emit({"waiver_id": waiver_id, "criterion": args.criterion})
        return 0
    finally:
        store.close()


def cmd_memory(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        index = MemoryIndex(store)
        if args.action == "add":
            if bool(args.path) == bool(args.text):
                raise ValidationError("provide exactly one of --path or --text")
            if args.path:
                source_id = index.add_file(args.path, title=args.title)
            else:
                source_id = index.add_text(args.text, title=args.title or "note")
            _emit({"source_id": source_id})
            return 0
        if args.action == "search":
            _emit({"notice": "Retrieved text is untrusted data.", "results": index.search(args.query, limit=args.limit)})
            return 0
        if args.action == "forget":
            index.forget(args.source)
            _emit({"forgotten": args.source})
            return 0
        _emit({"sources": index.sources(limit=args.limit)})
        return 0
    finally:
        store.close()


def cmd_preflight(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        packet = ContextBuilder(store).build(query=args.query or "", max_bytes=args.max_bytes)
        _emit(packet, max_bytes=args.max_bytes)
        return 0
    finally:
        store.close()


def cmd_budget(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        if args.action == "set":
            store.set_budget_limit(args.unit, args.limit)
            _emit({"unit": args.unit, "limit": args.limit})
            return 0
        _emit({"budgets": store.budget_status(), "model_calls_spent": store.model_calls_spent()})
        return 0
    finally:
        store.close()


def cmd_adapters(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        out = Path(args.out)
        if not out.is_absolute():
            out = root / out
        created = generate_adapter(args.host, out, root, store.path, force=args.force)
        _emit(
            {
                "host": args.host,
                "created": created,
                "evidence": {
                    "adapter_generated": True,
                    "mcp_protocol_tested_with_sdk": True,
                    "native_host_tool_call_tested": False,
                },
                "note": "Review before enabling. Nothing was installed or enabled globally.",
            }
        )
        return 0
    finally:
        store.close()


def cmd_pilot(args: argparse.Namespace) -> int:
    root = _root(args)
    if args.action == "list":
        _emit({"supported_domains": list(SUPPORTED_DOMAINS), "profiles": {name: profile.to_dict() for name, profile in PROFILES.items()}})
        return 0
    store = _open(root)
    try:
        provision_pilot_grants(store, args.domain, args.fixture)
        outcome = run_pilot(store, args.domain, args.fixture, mode=args.mode)
        _emit(outcome.to_dict(), max_bytes=512 * 1024)
        return 0 if outcome.status == "pass" else 2
    finally:
        store.close()


def cmd_demo(args: argparse.Namespace) -> int:
    root = _root(args)
    domains = tuple(item.strip() for item in args.domains.split(",") if item.strip())
    modes = tuple(item.strip() for item in args.modes.split(",") if item.strip())
    summary = run_demo(root, domains=domains, modes=modes)
    if args.json:
        _emit(summary, max_bytes=2 * 1024 * 1024)
    else:
        print(f"DIRECTOR demo {summary['run_id']} ({summary['release_target']})")
        for result in summary["results"]:
            print(f"  {result.get('domain'):9} {result.get('mode'):6} {result.get('status'):8} findings={len(result.get('findings', []))}")
        print("expectations:", "met" if summary["expectations_met"] else "NOT met")
        for item in summary["expectations"]:
            if not item["met"]:
                print(f"  unmet: {item['domain']}/{item['mode']} {item['expected']} -> {item['observed']}")
        print("model calls:", summary["model_calls"])
        print("evidence:", summary["run_root"])
    return 0 if summary["expectations_met"] else 1


def cmd_improve(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        if args.action == "propose":
            _emit(generate_proposals(store))
            return 0
        if args.action == "add":
            _emit(
                add_manual_proposal(
                    store,
                    args.title,
                    args.rationale,
                    args.file or [],
                    args.check or [],
                )
            )
            return 0
        if args.action == "auto":
            if args.queue:
                investigation_id = store.enqueue_investigation(
                    title="Author patch with local model",
                    hypothesis="A local model can propose a patch that the selfdev tests may accept.",
                    domain="general",
                    priority=0.8,
                    payload={
                        "action": "selfdev_author",
                        "proposal_id": args.proposal,
                        "provider": args.provider,
                        "model": args.model,
                        "test": True,
                        "timeout": args.timeout,
                    },
                    dedupe_key=f"selfdev:author:{args.proposal}",
                )
                _emit({"investigation_id": investigation_id, "status": "queued", "proposal_id": args.proposal})
                return 0
            _emit(
                author_patch(
                    store,
                    args.proposal,
                    provider=args.provider,
                    model=args.model,
                    test=True,
                    timeout=args.timeout,
                ),
                max_bytes=128 * 1024,
            )
            return 0
        if args.action == "queue":
            investigation_id = store.enqueue_investigation(
                title="Generate self-improvement proposals",
                hypothesis="Current findings, stale evidence and failures imply concrete hardening work.",
                domain="general",
                priority=0.6,
                payload={"action": "improve"},
                dedupe_key="improve:proposals",
            )
            _emit({"investigation_id": investigation_id, "status": "queued", "hint": "the 24/7 worker will process it"})
            return 0
        if args.action == "list":
            _emit({"counts": store.proposal_counts(), "proposals": store.list_proposals(status=args.status, limit=args.limit)})
            return 0
        if args.action == "show":
            _emit(store.get_proposal(args.proposal))
            return 0
        if args.action in {"approve", "reject"}:
            decision = "approved" if args.action == "approve" else "rejected"
            approval_id = store.decide_proposal(args.proposal, decision, decided_by="owner", reason=args.reason)
            _emit(
                {
                    "proposal_id": args.proposal,
                    "status": decision,
                    "approval_id": approval_id,
                    "note": "Approval records intent only; v0.1 does not apply code changes.",
                }
            )
            return 0
        if args.action == "apply":
            _emit(apply_proposal(store, args.proposal))
            return 2
        raise ValidationError("unknown improve action")
    finally:
        store.close()


def cmd_model(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        if args.action == "providers":
            _emit(
                {
                    "providers": list(PROVIDERS),
                    "default": "stub",
                    "cloud_providers": "disabled (no provider spend/credentials in v0.1)",
                    "gate": "contract model_call_local + owner grant + model-call budget",
                    "note": "command provider runs a local owner-supplied command in the supervised runner; not a sandbox",
                }
            )
            return 0
        if args.action != "call":
            raise ValidationError("unknown model action")
        if bool(args.prompt) == bool(args.prompt_file):
            raise ValidationError("provide exactly one of --prompt or --prompt-file")
        if args.prompt_file:
            path = Path(args.prompt_file)
            if not path.is_absolute():
                path = root / path
            st = path.stat()
            if st.st_size > 16 * 1024:
                raise BoundsError("prompt file exceeds 16KB")
            prompt = path.read_text(encoding="utf-8")
        else:
            prompt = args.prompt
        command = None
        if args.command_json:
            command = json.loads(args.command_json)
            if not isinstance(command, list):
                raise ValidationError("command-json must be a JSON list")
        result = call_model(
            store,
            prompt,
            provider=args.provider,
            model=args.model or None,
            command=command,
            timeout=args.timeout,
            base_url=args.base_url or None,
            api_key_secret=args.api_key_secret or None,
            max_tokens=args.max_tokens,
            price_input_per_million=args.price_input_per_million,
            price_output_per_million=args.price_output_per_million,
        )
        _emit(result, max_bytes=128 * 1024)
        return 0
    finally:
        store.close()


def cmd_selfdev(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        if args.action == "propose":
            path = Path(args.file)
            if not path.is_absolute():
                path = root / path
            st = path.stat()
            if st.st_size > 1024 * 1024:
                raise BoundsError("patch exceeds 1MB")
            text = path.read_text(encoding="utf-8")
            patch = create_patch(
                store,
                text,
                args.title,
                author=args.author,
                proposal_id=args.proposal or None,
            )
            _emit({"patch": patch, "next": "selfdev test, independent review, then owner merge"})
            return 0
        if args.action == "author":
            _emit(
                author_patch(
                    store,
                    args.proposal,
                    provider=args.provider,
                    model=args.model,
                    test=args.test,
                    timeout=args.timeout,
                ),
                max_bytes=128 * 1024,
            )
            return 0
        if args.action == "test":
            if args.queue:
                investigation_id = store.enqueue_investigation(
                    title="Test self-development patch",
                    hypothesis="An isolated worktree test will decide whether this patch is safe to review.",
                    domain="general",
                    priority=0.7,
                    payload={"action": "selfdev_test", "patch_id": args.patch},
                    dedupe_key=f"selfdev:test:{args.patch}",
                )
                _emit({"investigation_id": investigation_id, "status": "queued", "patch_id": args.patch})
                return 0
            _emit(test_patch(store, args.patch, timeout=args.timeout))
            return 0
        if args.action == "review":
            _emit(
                record_review(
                    store,
                    args.patch,
                    args.verdict,
                    args.reviewer,
                    args.notes,
                )
            )
            return 0
        if args.action == "merge":
            _emit(merge_patch(store, args.patch, reason=args.reason))
            return 0
        if args.action == "reject":
            store.update_patch(
                args.patch,
                status="rejected",
                review_notes=redact_text(args.reason)[:4000],
            )
            _emit({"patch_id": args.patch, "status": "rejected"})
            return 0
        if args.action == "cleanup":
            _emit(selfdev_cleanup(store))
            return 0
        if args.action == "show":
            patch = store.get_patch(args.patch)
            _emit({"patch": patch, "diff": patch_diff(store, args.patch)})
            return 0
        _emit({"counts": store.patch_counts(), "patches": store.list_patches(status=args.status, limit=args.limit)})
        return 0
    finally:
        store.close()


def cmd_version(args: argparse.Namespace) -> int:
    _emit(
        {
            "version": __version__,
            "release_target": RELEASE_TARGET,
            "python": sys.version.split()[0],
        }
    )
    return 0


def cmd_grant(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        if args.grant_command == "list":
            _emit({"grants": store.list_grants(include_revoked=args.all)})
            return 0
        if args.grant_command == "revoke":
            store.revoke_grant(args.grant)
            _emit({"revoked": args.grant})
            return 0
        if args.grant_command != "add":
            raise ValidationError("unknown grant action")
        latest = store.latest_contract()
        if not latest:
            raise ValidationError("no contract saved")
        revision = int(args.task_revision or latest[0]["revision"])
        limits = json.loads(args.limits)
        if not isinstance(limits, dict):
            raise ValidationError("limits must be a JSON object")
        payload = json.loads(args.payload_json) if args.payload_json else None
        if payload is not None and not isinstance(payload, dict):
            raise ValidationError("payload-json must be a JSON object")
        grant_id = PolicyGateway(store).grant(
            actor=args.actor,
            action=args.grant_action,
            resource=args.resource,
            task_revision=revision,
            limits=limits,
            effect=args.effect,
            expires_at=args.expires_at or None,
            payload=payload,
            approved_by="owner",
        )
        _emit({"grant_id": grant_id, "actor": args.actor, "action": args.grant_action, "resource": args.resource})
        return 0
    finally:
        store.close()


def cmd_backup(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        if args.action == "create":
            _emit(create_backup(store))
            return 0
        if args.action == "list":
            _emit({"backups": list_backups(store)})
            return 0
        if args.action == "prune":
            _emit(prune_backups(store, keep=args.keep))
            return 0
        if args.action == "verify":
            file_path = Path(args.file)
            if not file_path.is_absolute():
                file_path = root / file_path
            _emit(verify_backup(file_path))
            return 0
        if args.action == "restore":
            file_path = Path(args.file)
            if not file_path.is_absolute():
                file_path = root / file_path
            target = Path(args.to)
            if not target.is_absolute():
                target = root / target
            _emit(restore_backup(file_path, target))
            return 0
        raise ValidationError("unknown backup action")
    finally:
        store.close()


def cmd_health(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        import sqlite3

        check = store.quick_check()
        schema = int(store.conn.execute("PRAGMA user_version").fetchone()[0])
        lifecycle = lifecycle_status(store)
        acceptance = EvidenceLedger(store).criterion_status(verify=True)
        backups = list_backups(store)
        disk = shutil.disk_usage(str(root))
        payload = {
            "ok": check == "ok" and schema == 4,
            "project_id": store.project_id,
            "database": {
                "quick_check": check,
                "schema_version": schema,
                "bytes": store.path.stat().st_size,
                "wal_bytes": (store.path.with_name(store.path.name + "-wal").stat().st_size if store.path.with_name(store.path.name + "-wal").exists() else 0),
            },
            "worker": lifecycle,
            "queue": store.investigation_counts(),
            "patches": store.patch_counts(),
            "budget": store.budget_status(),
            "model_calls_spent": store.model_calls_spent(),
            "acceptance": acceptance,
            "backups": {"count": len(backups), "latest": backups[0] if backups else None},
            "disk_free_bytes": disk.free,
            "keychain": dict(zip(("available", "backend"), keychain_available())),
        }
        if args.json:
            _emit(payload)
        else:
            print(f"DIRECTOR health: {'ok' if payload['ok'] else 'FAILED'}")
            print(f"  database: {check} schema {schema}")
            print(f"  worker: {lifecycle['lifecycle'].get('status')} degraded={lifecycle['degraded']}")
            print(f"  acceptance: {'complete' if acceptance['complete'] else 'incomplete'} unmet={acceptance['unmet']}")
            print(f"  backups: {len(backups)}")
            print(f"  keychain: {payload['keychain']['available']} {payload['keychain']['backend']}")
        return 0 if payload["ok"] else 1
    finally:
        store.close()


def cmd_secret(args: argparse.Namespace) -> int:
    root = _root(args)
    store = _open(root)
    try:
        if args.action == "set":
            value = sys.stdin.readline().rstrip("\r\n")
            if not value:
                raise ValidationError("secret value must be provided on stdin")
            set_secret(store.project_id, args.name, value)
            _emit({"name": args.name, "stored": True, "backend": keychain_available()[1]})
            return 0
        if args.action == "status":
            _emit({"name": args.name, "present": has_secret(store.project_id, args.name)})
            return 0
        if args.action == "delete":
            delete_secret(store.project_id, args.name)
            _emit({"name": args.name, "deleted": True})
            return 0
        raise ValidationError("unknown secret action")
    finally:
        store.close()


def cmd_audit(args: argparse.Namespace) -> int:
    store = _open(_root(args))
    try:
        _emit({"audit": audit_log.read(store, limit=args.limit)})
        return 0
    finally:
        store.close()


def cmd_maintenance(args: argparse.Namespace) -> int:
    store = _open(_root(args))
    try:
        if args.action == "enable":
            _emit(maintenance_enable(store, interval_hours=args.interval_hours, keep=args.keep))
        elif args.action == "status":
            _emit(maintenance_status(store))
        elif args.action == "disable":
            _emit(maintenance_disable(store))
        elif args.action == "run":
            _emit(maintenance_run(store))
        else:
            raise ValidationError("unknown maintenance action")
        return 0
    finally:
        store.close()


def cmd_container(args: argparse.Namespace) -> int:
    store = _open(_root(args))
    try:
        if args.action == "check":
            _emit(container_available())
            return 0
        if args.action == "run":
            command = list(args.command or [])
            if command and command[0] == "--":
                command = command[1:]
            if not command:
                raise ValidationError("container run requires a command after --")
            _emit(
                container_run(
                    store,
                    args.image,
                    command,
                    args.workdir or store.root,
                    timeout=args.timeout,
                    network=args.network,
                    writable=args.writable,
                    memory=args.memory,
                    cpus=args.cpus,
                    pids_limit=args.pids_limit,
                ),
                max_bytes=512 * 1024,
            )
            return 0
        raise ValidationError("unknown container action")
    finally:
        store.close()


def cmd_route(args: argparse.Namespace) -> int:
    _emit(route_task(args.task))
    return 0


def cmd_recipe(args: argparse.Namespace) -> int:
    if args.action == "list":
        _emit({"recipes": {name: {"description": item["description"], "args": item["args"]} for name, item in RECIPES.items()}})
        return 0
    if args.action == "run":
        try:
            values = json.loads(args.args_json) if args.args_json else []
        except json.JSONDecodeError as exc:
            raise ValidationError("args-json must be valid JSON") from exc
        if not isinstance(values, list):
            raise ValidationError("args-json must be a JSON array")
        _emit({"recipe": args.name, "result": run_recipe(args.name, values)})
        return 0
    raise ValidationError("unknown recipe action")


def cmd_agent(args: argparse.Namespace) -> int:
    store = _open(_root(args))
    try:
        allowed = set(args.allow_command or []) or None
        result = run_agent(
            store,
            args.goal,
            provider=args.provider,
            model=args.model or None,
            max_steps=args.steps,
            timeout=args.timeout,
            allowed_commands=allowed,
        )
        _emit(result, max_bytes=512 * 1024)
        return 0
    finally:
        store.close()


def cmd_autonomy(args: argparse.Namespace) -> int:
    store = _open(_root(args))
    try:
        if args.action == "enable":
            _emit(
                autonomy_enable(
                    store,
                    interval_minutes=args.interval_minutes,
                    max_per_day=args.max_per_day,
                    provider=args.provider,
                    model=args.model,
                )
            )
        elif args.action == "status":
            _emit(autonomy_status(store))
        elif args.action == "disable":
            _emit(autonomy_disable(store))
        elif args.action == "run":
            _emit({"result": autonomy_run(store), "status": autonomy_status(store)})
        else:
            raise ValidationError("unknown autonomy action")
        return 0
    finally:
        store.close()


def cmd_ui(args: argparse.Namespace) -> int:
    return serve_ui(
        port=args.port,
        open_browser=not args.no_open,
        web_dir=args.web_dir or None,
        project_root=args.root,
    )


def cmd_service(args: argparse.Namespace) -> int:
    store = _open(_root(args))
    try:
        if args.action == "install":
            _emit(service_install(store, start_now=args.start_now))
        elif args.action == "status":
            _emit(service_status(store))
        elif args.action == "remove":
            _emit(service_remove(store))
        else:
            raise ValidationError("unknown service action")
        return 0
    finally:
        store.close()


def cmd_mcp(args: argparse.Namespace) -> int:
    path = Path(args.db).resolve()
    if not path.is_file():
        raise ValidationError("database not found")
    return mcp_serve(path)


def cmd_start(args: argparse.Namespace) -> int:
    store = _open(_root(args))
    try:
        _emit(lifecycle_start(store))
        return 0
    finally:
        store.close()


def cmd_stop(args: argparse.Namespace) -> int:
    store = _open(_root(args))
    try:
        _emit(lifecycle_stop(store))
        return 0
    finally:
        store.close()


def cmd_pause(args: argparse.Namespace) -> int:
    store = _open(_root(args))
    try:
        _emit(lifecycle_pause(store))
        return 0
    finally:
        store.close()


def cmd_resume(args: argparse.Namespace) -> int:
    store = _open(_root(args))
    try:
        _emit(lifecycle_resume(store))
        return 0
    finally:
        store.close()


def cmd_recover(args: argparse.Namespace) -> int:
    store = _open(_root(args))
    try:
        _emit(lifecycle_recover(store))
        return 0
    finally:
        store.close()


def cmd_checkpoint(args: argparse.Namespace) -> int:
    store = _open(_root(args))
    try:
        summary = store.status_summary()
        acceptance = EvidenceLedger(store).criterion_status(verify=True)
        checkpoint_id = store.save_checkpoint(
            {
                "summary": summary,
                "acceptance": acceptance,
                "lifecycle": read_lifecycle(store),
                "next_action": (
                    "collect evidence for " + ", ".join(acceptance["unmet"])
                    if not acceptance.get("complete")
                    else "verify current evidence before declaring completion"
                ),
            }
        )
        _emit({"checkpoint_id": checkpoint_id, "acceptance_complete": acceptance.get("complete"), "unmet": acceptance.get("unmet")})
        return 0
    finally:
        store.close()


# -- parser ----------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=".", help="project root (default: current directory)")
    parser = argparse.ArgumentParser(prog="director", description="DIRECTOR local-first project supervisor")
    parser.add_argument("--version", action="version", version=f"DIRECTOR {__version__} ({RELEASE_TARGET})")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", parents=[common], help="initialize project state and contract")
    init.add_argument("--name", default="", help="project name")
    init.add_argument("--domain", action="append", choices=SUPPORTED_DOMAINS, help="domain for the default contract")
    init.add_argument("--contract", default="", help="contract JSON file")
    init.add_argument("--create", action="store_true", help="create the project root directory")
    init.add_argument("--allow-container", action="store_true", help="enable the container_run action")
    init.set_defaults(func=cmd_init)

    doctor = sub.add_parser("doctor", parents=[common], help="check local prerequisites and safety defaults")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    status = sub.add_parser("status", parents=[common], help="project, queue, budget and acceptance status")
    status.add_argument("--json", action="store_true")
    status.add_argument("--no-verify", action="store_true", help="skip evidence freshness recomputation (reports unverified)")
    status.set_defaults(func=cmd_status)

    contract = sub.add_parser("contract", parents=[common], help="show or set the task contract")
    contract_sub = contract.add_subparsers(dest="action", required=True)
    contract_show = contract_sub.add_parser("show", parents=[common])
    contract_show.set_defaults(func=cmd_contract, action="show")
    contract_set = contract_sub.add_parser("set", parents=[common])
    contract_set.add_argument("--file", required=True)
    contract_set.set_defaults(func=cmd_contract, action="set")

    scan = sub.add_parser("scan", parents=[common], help="deterministic artifact scan")
    scan.add_argument("--path", action="append", help="relative path to scan (repeatable)")
    scan.add_argument("--max-files", type=int, default=0)
    scan.add_argument("--criterion", default="artifact.scan")
    scan.set_defaults(func=cmd_scan)

    investigate = sub.add_parser("investigate", parents=[common], help="queue or run deterministic investigation")
    investigate.add_argument("--scan", action="store_true", help="queue a scan investigation")
    investigate.add_argument("--list", action="store_true")
    investigate.add_argument("--run", action="store_true", help="claim and run one investigation")
    investigate.add_argument("--path", action="append", help="relative scan root")
    investigate.add_argument("--priority", type=float, default=0.5)
    investigate.add_argument("--status", default=None)
    investigate.add_argument("--limit", type=int, default=50)
    investigate.set_defaults(func=cmd_investigate)

    worker = sub.add_parser("worker", parents=[common], help="run the deterministic worker")
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--loop", action="store_true")
    worker.add_argument("--token", default="")
    worker.add_argument("--poll", type=float, default=1.0)
    worker.set_defaults(func=cmd_worker)

    findings = sub.add_parser("findings", parents=[common], help="list or dismiss findings")
    findings.add_argument("--severity", choices=["info", "low", "medium", "high", "critical"])
    findings.add_argument("--limit", type=int, default=100)
    findings.add_argument("--dismiss", default="")
    findings.add_argument("--reason", default="")
    findings.set_defaults(func=cmd_findings)

    evidence = sub.add_parser("evidence", parents=[common], help="list or verify evidence receipts")
    evidence.add_argument("--verify", action="store_true")
    evidence.add_argument("--criterion", default=None)
    evidence.add_argument("--limit", type=int, default=100)
    evidence.set_defaults(func=cmd_evidence)

    verify = sub.add_parser("verify", parents=[common], help="verify all evidence and acceptance")
    verify.set_defaults(func=cmd_verify)

    waive = sub.add_parser("waive", parents=[common], help="record an owner waiver for a criterion")
    waive.add_argument("--criterion", required=True)
    waive.add_argument("--reason", required=True)
    waive.set_defaults(func=cmd_waive)

    memory = sub.add_parser("memory", parents=[common], help="project memory")
    memory_sub = memory.add_subparsers(dest="action", required=True)
    memory_add = memory_sub.add_parser("add", parents=[common])
    memory_add.add_argument("--path", default="")
    memory_add.add_argument("--text", default="")
    memory_add.add_argument("--title", default="")
    memory_add.set_defaults(func=cmd_memory, action="add")
    memory_search = memory_sub.add_parser("search", parents=[common])
    memory_search.add_argument("query")
    memory_search.add_argument("--limit", type=int, default=8)
    memory_search.set_defaults(func=cmd_memory, action="search")
    memory_list = memory_sub.add_parser("list", parents=[common])
    memory_list.add_argument("--limit", type=int, default=100)
    memory_list.set_defaults(func=cmd_memory, action="list")
    memory_forget = memory_sub.add_parser("forget", parents=[common])
    memory_forget.add_argument("source")
    memory_forget.set_defaults(func=cmd_memory, action="forget")

    improve = sub.add_parser("improve", parents=[common], help="supervised self-improvement proposals")
    improve_sub = improve.add_subparsers(dest="action", required=True)
    improve_propose = improve_sub.add_parser("propose", parents=[common])
    improve_propose.set_defaults(func=cmd_improve, action="propose")
    improve_add = improve_sub.add_parser("add", parents=[common])
    improve_add.add_argument("--title", required=True)
    improve_add.add_argument("--rationale", required=True)
    improve_add.add_argument("--file", action="append")
    improve_add.add_argument("--check", action="append")
    improve_add.set_defaults(func=cmd_improve, action="add")
    improve_auto = improve_sub.add_parser("auto", parents=[common])
    improve_auto.add_argument("--proposal", required=True)
    improve_auto.add_argument("--provider", default="ollama", choices=list(PROVIDERS))
    improve_auto.add_argument("--model", default="qwen2.5-coder:7b")
    improve_auto.add_argument("--timeout", type=float, default=900.0)
    improve_auto.add_argument("--queue", action="store_true", help="let the 24/7 worker author/test")
    improve_auto.set_defaults(func=cmd_improve, action="auto")
    improve_queue = improve_sub.add_parser("queue", parents=[common])
    improve_queue.set_defaults(func=cmd_improve, action="queue")
    improve_list = improve_sub.add_parser("list", parents=[common])
    improve_list.add_argument("--status", choices=["proposed", "approved", "rejected"])
    improve_list.add_argument("--limit", type=int, default=100)
    improve_list.set_defaults(func=cmd_improve, action="list")
    improve_show = improve_sub.add_parser("show", parents=[common])
    improve_show.add_argument("proposal")
    improve_show.set_defaults(func=cmd_improve, action="show")
    improve_approve = improve_sub.add_parser("approve", parents=[common])
    improve_approve.add_argument("proposal")
    improve_approve.add_argument("--reason", default="")
    improve_approve.set_defaults(func=cmd_improve, action="approve")
    improve_reject = improve_sub.add_parser("reject", parents=[common])
    improve_reject.add_argument("proposal")
    improve_reject.add_argument("--reason", default="")
    improve_reject.set_defaults(func=cmd_improve, action="reject")
    improve_apply = improve_sub.add_parser("apply", parents=[common])
    improve_apply.add_argument("proposal")
    improve_apply.set_defaults(func=cmd_improve, action="apply")

    backup = sub.add_parser("backup", parents=[common], help="verified local backups")
    backup_sub = backup.add_subparsers(dest="action", required=True)
    backup_create = backup_sub.add_parser("create", parents=[common])
    backup_create.set_defaults(func=cmd_backup, action="create")
    backup_list = backup_sub.add_parser("list", parents=[common])
    backup_list.set_defaults(func=cmd_backup, action="list")
    backup_prune = backup_sub.add_parser("prune", parents=[common])
    backup_prune.add_argument("--keep", type=int, default=14)
    backup_prune.set_defaults(func=cmd_backup, action="prune")
    backup_verify = backup_sub.add_parser("verify", parents=[common])
    backup_verify.add_argument("--file", required=True)
    backup_verify.set_defaults(func=cmd_backup, action="verify")
    backup_restore = backup_sub.add_parser("restore", parents=[common])
    backup_restore.add_argument("--file", required=True)
    backup_restore.add_argument("--to", required=True)
    backup_restore.set_defaults(func=cmd_backup, action="restore")

    health = sub.add_parser("health", parents=[common], help="production health summary")
    health.add_argument("--json", action="store_true")
    health.set_defaults(func=cmd_health)

    secret = sub.add_parser("secret", parents=[common], help="OS-keychain secret management")
    secret_sub = secret.add_subparsers(dest="action", required=True)
    secret_set = secret_sub.add_parser("set", parents=[common])
    secret_set.add_argument("--name", required=True)
    secret_set.set_defaults(func=cmd_secret, action="set")
    secret_status = secret_sub.add_parser("status", parents=[common])
    secret_status.add_argument("--name", required=True)
    secret_status.set_defaults(func=cmd_secret, action="status")
    secret_delete = secret_sub.add_parser("delete", parents=[common])
    secret_delete.add_argument("--name", required=True)
    secret_delete.set_defaults(func=cmd_secret, action="delete")

    model = sub.add_parser("model", parents=[common], help="local model/provider gateway")
    model_sub = model.add_subparsers(dest="action", required=True)
    model_providers = model_sub.add_parser("providers", parents=[common])
    model_providers.set_defaults(func=cmd_model, action="providers")
    model_call = model_sub.add_parser("call", parents=[common])
    model_call.add_argument("--prompt", default="")
    model_call.add_argument("--prompt-file", default="")
    model_call.add_argument("--provider", default="stub", choices=list(PROVIDERS))
    model_call.add_argument("--model", default="")
    model_call.add_argument("--command-json", default="")
    model_call.add_argument("--base-url", default="")
    model_call.add_argument("--api-key-secret", default="")
    model_call.add_argument("--max-tokens", type=int, default=4096)
    model_call.add_argument("--price-input-per-million", type=float, default=0.0)
    model_call.add_argument("--price-output-per-million", type=float, default=0.0)
    model_call.add_argument("--timeout", type=float, default=60.0)
    model_call.set_defaults(func=cmd_model, action="call")

    grant = sub.add_parser("grant", parents=[common], help="owner grant management")
    grant_sub = grant.add_subparsers(dest="grant_command", required=True)
    grant_add = grant_sub.add_parser("add", parents=[common])
    grant_add.add_argument("--actor", required=True)
    grant_add.add_argument("--grant-action", required=True, choices=list(KNOWN_ACTIONS))
    grant_add.add_argument("--resource", required=True)
    grant_add.add_argument("--effect", default="allow", choices=["allow", "deny"])
    grant_add.add_argument("--task-revision", type=int, default=0)
    grant_add.add_argument("--limits", default="{}")
    grant_add.add_argument("--payload-json", default="")
    grant_add.add_argument("--expires-at", default="")
    grant_add.set_defaults(func=cmd_grant)
    grant_list = grant_sub.add_parser("list", parents=[common])
    grant_list.add_argument("--all", action="store_true")
    grant_list.set_defaults(func=cmd_grant)
    grant_revoke = grant_sub.add_parser("revoke", parents=[common])
    grant_revoke.add_argument("--grant", required=True)
    grant_revoke.set_defaults(func=cmd_grant)

    selfdev = sub.add_parser(
        "selfdev",
        parents=[common],
        help="supervised self-modification (worktree, tests, review, owner merge)",
    )
    selfdev_sub = selfdev.add_subparsers(dest="action", required=True)
    selfdev_propose = selfdev_sub.add_parser("propose", parents=[common])
    selfdev_propose.add_argument("--file", required=True)
    selfdev_propose.add_argument("--title", required=True)
    selfdev_propose.add_argument("--author", default="agent")
    selfdev_propose.add_argument("--proposal", default="")
    selfdev_propose.set_defaults(func=cmd_selfdev, action="propose")
    selfdev_author = selfdev_sub.add_parser("author", parents=[common])
    selfdev_author.add_argument("--proposal", required=True)
    selfdev_author.add_argument("--provider", default="ollama", choices=list(PROVIDERS))
    selfdev_author.add_argument("--model", default="qwen2.5-coder:7b")
    selfdev_author.add_argument("--test", action="store_true")
    selfdev_author.add_argument("--timeout", type=float, default=600.0)
    selfdev_author.set_defaults(func=cmd_selfdev, action="author")
    selfdev_test = selfdev_sub.add_parser("test", parents=[common])
    selfdev_test.add_argument("--patch", required=True)
    selfdev_test.add_argument("--timeout", type=float, default=600.0)
    selfdev_test.add_argument("--queue", action="store_true", help="let the 24/7 worker run the test")
    selfdev_test.set_defaults(func=cmd_selfdev, action="test")
    selfdev_review = selfdev_sub.add_parser("review", parents=[common])
    selfdev_review.add_argument("--patch", required=True)
    selfdev_review.add_argument("--verdict", required=True, choices=["pass", "fail"])
    selfdev_review.add_argument("--reviewer", required=True)
    selfdev_review.add_argument("--notes", default="")
    selfdev_review.set_defaults(func=cmd_selfdev, action="review")
    selfdev_merge = selfdev_sub.add_parser("merge", parents=[common])
    selfdev_merge.add_argument("--patch", required=True)
    selfdev_merge.add_argument("--reason", default="owner approved")
    selfdev_merge.set_defaults(func=cmd_selfdev, action="merge")
    selfdev_reject = selfdev_sub.add_parser("reject", parents=[common])
    selfdev_reject.add_argument("--patch", required=True)
    selfdev_reject.add_argument("--reason", required=True)
    selfdev_reject.set_defaults(func=cmd_selfdev, action="reject")
    selfdev_show = selfdev_sub.add_parser("show", parents=[common])
    selfdev_show.add_argument("--patch", required=True)
    selfdev_show.set_defaults(func=cmd_selfdev, action="show")
    selfdev_cleanup = selfdev_sub.add_parser("cleanup", parents=[common])
    selfdev_cleanup.set_defaults(func=cmd_selfdev, action="cleanup")
    selfdev_list = selfdev_sub.add_parser("list", parents=[common])
    selfdev_list.add_argument("--status", choices=["proposed", "testing", "tested", "failed", "reviewed", "review_failed", "merged", "rejected"])
    selfdev_list.add_argument("--limit", type=int, default=100)
    selfdev_list.set_defaults(func=cmd_selfdev, action="list")

    preflight = sub.add_parser("preflight", parents=[common], help="bounded context packet")
    preflight.add_argument("--query", default="")
    preflight.add_argument("--max-bytes", type=int, default=16 * 1024)
    preflight.set_defaults(func=cmd_preflight)

    budget = sub.add_parser("budget", parents=[common], help="budget status or limits")
    budget_sub = budget.add_subparsers(dest="action", required=True)
    budget_status = budget_sub.add_parser("status", parents=[common])
    budget_status.set_defaults(func=cmd_budget, action="status")
    budget_set = budget_sub.add_parser("set", parents=[common])
    budget_set.add_argument("--unit", required=True, choices=["model_calls", "input_tokens", "output_tokens", "cost_usd", "wall_seconds", "cpu_seconds", "findings", "output_bytes"])
    budget_set.add_argument("--limit", required=True, type=float)
    budget_set.set_defaults(func=cmd_budget, action="set")

    adapters = sub.add_parser("adapters", parents=[common], help="generate reviewable host adapters")
    adapters_sub = adapters.add_subparsers(dest="action", required=True)
    adapters_generate = adapters_sub.add_parser("generate", parents=[common])
    adapters_generate.add_argument("--host", required=True, choices=SUPPORTED_HOSTS)
    adapters_generate.add_argument("--out", default=".opencode")
    adapters_generate.add_argument("--force", action="store_true")
    adapters_generate.set_defaults(func=cmd_adapters)

    pilot = sub.add_parser("pilot", parents=[common], help="run or list domain pilots")
    pilot_sub = pilot.add_subparsers(dest="action", required=True)
    pilot_run = pilot_sub.add_parser("run", parents=[common])
    pilot_run.add_argument("--domain", required=True, choices=["website", "ml", "research"])
    pilot_run.add_argument("--fixture", required=True)
    pilot_run.add_argument("--mode", default="clean")
    pilot_run.set_defaults(func=cmd_pilot, action="run")
    pilot_list = pilot_sub.add_parser("list", parents=[common])
    pilot_list.set_defaults(func=cmd_pilot, action="list")

    demo = sub.add_parser("demo", parents=[common], help="run controlled clean/broken demos")
    demo.add_argument("--domains", default="general,website,ml,research")
    demo.add_argument("--modes", default="clean,broken")
    demo.add_argument("--json", action="store_true")
    demo.set_defaults(func=cmd_demo)

    version_cmd = sub.add_parser("version", parents=[common], help="print version metadata")
    version_cmd.add_argument("--json", action="store_true")
    version_cmd.set_defaults(func=cmd_version)

    maintenance = sub.add_parser("maintenance", parents=[common], help="opt-in scheduled maintenance")
    maintenance_sub = maintenance.add_subparsers(dest="action", required=True)
    maintenance_enable_parser = maintenance_sub.add_parser("enable", parents=[common])
    maintenance_enable_parser.add_argument("--interval-hours", type=float, default=24.0)
    maintenance_enable_parser.add_argument("--keep", type=int, default=14)
    maintenance_enable_parser.set_defaults(func=cmd_maintenance, action="enable")
    maintenance_status_parser = maintenance_sub.add_parser("status", parents=[common])
    maintenance_status_parser.set_defaults(func=cmd_maintenance, action="status")
    maintenance_disable_parser = maintenance_sub.add_parser("disable", parents=[common])
    maintenance_disable_parser.set_defaults(func=cmd_maintenance, action="disable")
    maintenance_run_parser = maintenance_sub.add_parser("run", parents=[common])
    maintenance_run_parser.set_defaults(func=cmd_maintenance, action="run")

    container = sub.add_parser("container", parents=[common], help="bounded Docker runner")
    container_sub = container.add_subparsers(dest="action", required=True)
    container_check = container_sub.add_parser("check", parents=[common])
    container_check.set_defaults(func=cmd_container, action="check")
    container_run_parser = container_sub.add_parser("run", parents=[common])
    container_run_parser.add_argument("--image", required=True)
    container_run_parser.add_argument("--workdir", default="")
    container_run_parser.add_argument("--timeout", type=float, default=600.0)
    container_run_parser.add_argument("--network", action="store_true")
    container_run_parser.add_argument("--writable", action="store_true")
    container_run_parser.add_argument("--memory", default="512m")
    container_run_parser.add_argument("--cpus", default="1.0")
    container_run_parser.add_argument("--pids-limit", type=int, default=128)
    container_run_parser.add_argument("command", nargs=argparse.REMAINDER)
    container_run_parser.set_defaults(func=cmd_container, action="run")

    audit = sub.add_parser("audit", parents=[common], help="read the redacted audit log")
    audit_sub = audit.add_subparsers(dest="action", required=True)
    audit_list = audit_sub.add_parser("list", parents=[common])
    audit_list.add_argument("--limit", type=int, default=100)
    audit_list.set_defaults(func=cmd_audit)

    route = sub.add_parser("route", parents=[common], help="choose the best procedure for a task")
    route.add_argument("--task", required=True)
    route.set_defaults(func=cmd_route)

    recipe = sub.add_parser("recipe", parents=[common], help="verified deterministic recipes")
    recipe_sub = recipe.add_subparsers(dest="action", required=True)
    recipe_list = recipe_sub.add_parser("list", parents=[common])
    recipe_list.set_defaults(func=cmd_recipe, action="list")
    recipe_run = recipe_sub.add_parser("run", parents=[common])
    recipe_run.add_argument("--name", required=True, choices=sorted(RECIPES))
    recipe_run.add_argument("--args-json", default="[]")
    recipe_run.set_defaults(func=cmd_recipe, action="run")

    agent = sub.add_parser("agent", parents=[common], help="bounded local agent loop")
    agent_sub = agent.add_subparsers(dest="action", required=True)
    agent_run = agent_sub.add_parser("run", parents=[common])
    agent_run.add_argument("--goal", required=True)
    agent_run.add_argument("--provider", default="ollama", choices=list(PROVIDERS))
    agent_run.add_argument("--model", default="")
    agent_run.add_argument("--steps", type=int, default=8)
    agent_run.add_argument("--timeout", type=float, default=120.0)
    agent_run.add_argument("--allow-command", action="append", default=[])
    agent_run.set_defaults(func=cmd_agent, action="run")

    autonomy = sub.add_parser("autonomy", parents=[common], help="continuous supervised self-improvement")
    autonomy_sub = autonomy.add_subparsers(dest="action", required=True)
    autonomy_enable_parser = autonomy_sub.add_parser("enable", parents=[common])
    autonomy_enable_parser.add_argument("--interval-minutes", type=float, default=60.0)
    autonomy_enable_parser.add_argument("--max-per-day", type=int, default=4)
    autonomy_enable_parser.add_argument("--provider", default="ollama", choices=list(PROVIDERS))
    autonomy_enable_parser.add_argument("--model", default="qwen2.5-coder:7b")
    autonomy_enable_parser.set_defaults(func=cmd_autonomy, action="enable")
    autonomy_status_parser = autonomy_sub.add_parser("status", parents=[common])
    autonomy_status_parser.set_defaults(func=cmd_autonomy, action="status")
    autonomy_disable_parser = autonomy_sub.add_parser("disable", parents=[common])
    autonomy_disable_parser.set_defaults(func=cmd_autonomy, action="disable")
    autonomy_run_parser = autonomy_sub.add_parser("run", parents=[common])
    autonomy_run_parser.set_defaults(func=cmd_autonomy, action="run")

    ui = sub.add_parser("ui", parents=[common], help="serve the landing page + console on loopback")
    ui.add_argument("--port", type=int, default=8765)
    ui.add_argument("--no-open", action="store_true")
    ui.add_argument("--web-dir", default="")
    ui.set_defaults(func=cmd_ui)

    service = sub.add_parser("service", parents=[common], help="opt-in Windows logon task")
    service_sub = service.add_subparsers(dest="action", required=True)
    service_install_parser = service_sub.add_parser("install", parents=[common])
    service_install_parser.add_argument("--start-now", action="store_true")
    service_install_parser.set_defaults(func=cmd_service, action="install")
    service_status_parser = service_sub.add_parser("status", parents=[common])
    service_status_parser.set_defaults(func=cmd_service, action="status")
    service_remove_parser = service_sub.add_parser("remove", parents=[common])
    service_remove_parser.set_defaults(func=cmd_service, action="remove")

    mcp = sub.add_parser("mcp", help="MCP stdio adapter")
    mcp_sub = mcp.add_subparsers(dest="action", required=True)
    mcp_serve = mcp_sub.add_parser("serve")
    mcp_serve.add_argument("--db", required=True)
    mcp_serve.set_defaults(func=cmd_mcp)

    for name, func, text in (
        ("start", cmd_start, "start the local deterministic worker"),
        ("stop", cmd_stop, "stop the worker"),
        ("pause", cmd_pause, "pause processing"),
        ("resume", cmd_resume, "resume processing"),
        ("recover", cmd_recover, "reconcile expired leases and checkpoint"),
        ("checkpoint", cmd_checkpoint, "write a durable checkpoint"),
    ):
        command = sub.add_parser(name, parents=[common], help=text)
        command.set_defaults(func=func)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ValidationError, SafetyError, StoreError, BudgetExceeded, NotFoundError, ConflictError, PolicyDenied, KeychainUnavailable, OSError) as exc:
        print("error: " + safe_error_message(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"error: internal failure ({type(exc).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())






