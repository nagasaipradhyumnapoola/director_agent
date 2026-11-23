"""Durable local substrate: SQLite schema, repository, queue, budgets, memory.

One database per project under ``<project>/.director/director.db``. All writes
that can race use SQLite transactions; queue claims use fencing tokens and
monotonic generations so an expired worker cannot publish.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from .models import TaskContract
from .security import (
    BoundsError,
    PathSafetyError,
    ValidationError,
    bounded_json_loads,
    canonical_json,
    dump_bounded,
    prepare_state_dir,
    redact_text,
    safe_state_db_path,
    sha256_text,
)

SCHEMA_VERSION = 3


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def utc_after(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(timespec="seconds")


def now_ts() -> float:
    return time.time()


def _new_id(prefix: str = "") -> str:
    raw = uuid.uuid4().hex
    return f"{prefix}{raw}" if prefix else raw


class StoreError(Exception):
    """Base repository error."""


class NotFoundError(StoreError):
    pass


class ConflictError(StoreError):
    pass


class FencedWriteError(StoreError):
    pass


class BudgetExceeded(StoreError):
    pass


class Store:
    def __init__(self, db_path: os.PathLike[str] | str, project_root: os.PathLike[str] | str):
        self.path = Path(os.path.abspath(os.fspath(db_path)))
        self.root = Path(os.path.abspath(os.fspath(project_root)))
        self._savepoint = 0
        self.conn = sqlite3.connect(str(self.path), timeout=30.0, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.execute("PRAGMA trusted_schema=OFF")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.fts_available = False
        self._migrate()
        self._ensure_fts()

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @classmethod
    def open(cls, project_root: os.PathLike[str] | str) -> "Store":
        root = Path(os.path.abspath(os.fspath(project_root)))
        state = prepare_state_dir(root)
        db = safe_state_db_path(state)
        return cls(db, root)

    @classmethod
    def open_or_create(cls, project_root: os.PathLike[str] | str, name: str) -> "Store":
        store = cls.open(project_root)
        project_id = store.get_meta("project_id")
        if not project_id:
            project_id = store.create_project(name, str(store.root))
        return store

    @property
    def project_id(self) -> str:
        project_id = self.get_meta("project_id")
        if not project_id:
            raise StoreError("database has no project; run 'director init' first")
        return project_id

    # -- transactions ------------------------------------------------------
    @contextmanager
    def tx(self, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        if self.conn.in_transaction:
            self._savepoint += 1
            name = f"sp{self._savepoint}"
            self.conn.execute(f"SAVEPOINT {name}")
            try:
                yield self.conn
            except Exception:
                self.conn.execute(f"ROLLBACK TO {name}")
                self.conn.execute(f"RELEASE {name}")
                raise
            else:
                self.conn.execute(f"RELEASE {name}")
            return
        self.conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        try:
            yield self.conn
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        else:
            self.conn.execute("COMMIT")

    def _migrate(self) -> None:
        version = int(self.conn.execute("PRAGMA user_version").fetchone()[0])
        if version > SCHEMA_VERSION:
            raise StoreError("database schema is newer than this DIRECTOR build")
        if version == 0:
            self._create_schema()
            self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            return
        if version < 2:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS proposals (
                  id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                  investigation_id TEXT,
                  signature TEXT NOT NULL,
                  title TEXT NOT NULL,
                  rationale TEXT NOT NULL,
                  category TEXT NOT NULL,
                  risk TEXT NOT NULL,
                  expected_impact TEXT NOT NULL,
                  files TEXT NOT NULL,
                  required_checks TEXT NOT NULL,
                  autonomy_level TEXT NOT NULL,
                  status TEXT NOT NULL,
                  approval_id TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE(project_id, signature)
                );
                CREATE INDEX IF NOT EXISTS idx_proposals_project
                  ON proposals(project_id, status, created_at DESC);
                """
            )
        if version < 3:
            columns = {
                str(row[1])
                for row in self.conn.execute("PRAGMA table_info(waivers)").fetchall()
            }
            if "contract_revision" not in columns:
                self.conn.execute(
                    "ALTER TABLE waivers ADD COLUMN contract_revision INTEGER NOT NULL DEFAULT 0"
                )
            if "contract_hash" not in columns:
                self.conn.execute(
                    "ALTER TABLE waivers ADD COLUMN contract_hash TEXT NOT NULL DEFAULT ''"
                )
        self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def _ensure_fts(self) -> None:
        """Detect FTS5 on every open so a separate process uses the same path."""
        try:
            self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(text, tokenize='unicode61')"
            )
            self.fts_available = True
        except sqlite3.OperationalError:
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS memory_fts_fallback (rowid INTEGER PRIMARY KEY, text TEXT)"
            )
            self.fts_available = False

    def _create_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projects (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              root TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'active'
            );
            CREATE TABLE IF NOT EXISTS goals (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              intent TEXT NOT NULL,
              revision INTEGER NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS task_contracts (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              revision INTEGER NOT NULL,
              hash TEXT NOT NULL,
              payload TEXT NOT NULL,
              created_at TEXT NOT NULL,
              UNIQUE(project_id, revision)
            );
            CREATE TABLE IF NOT EXISTS requirements (
              id TEXT PRIMARY KEY,
              contract_id TEXT NOT NULL REFERENCES task_contracts(id) ON DELETE CASCADE,
              key TEXT NOT NULL,
              text TEXT NOT NULL,
              domain TEXT NOT NULL,
              UNIQUE(contract_id, key)
            );
            CREATE TABLE IF NOT EXISTS criteria (
              id TEXT PRIMARY KEY,
              requirement_id TEXT NOT NULL REFERENCES requirements(id) ON DELETE CASCADE,
              key TEXT NOT NULL,
              description TEXT NOT NULL,
              evaluator TEXT NOT NULL,
              mandatory INTEGER NOT NULL,
              params TEXT NOT NULL,
              UNIQUE(requirement_id, key)
            );
            CREATE TABLE IF NOT EXISTS artifacts (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              path TEXT NOT NULL,
              sha256 TEXT NOT NULL,
              bytes INTEGER NOT NULL,
              kind TEXT NOT NULL,
              meta TEXT NOT NULL,
              created_at TEXT NOT NULL,
              UNIQUE(project_id, path, sha256)
            );
            CREATE TABLE IF NOT EXISTS events (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              type TEXT NOT NULL,
              dedupe_key TEXT NOT NULL,
              payload TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              processed_at TEXT,
              UNIQUE(project_id, dedupe_key)
            );
            CREATE TABLE IF NOT EXISTS investigations (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              dedupe_key TEXT,
              title TEXT NOT NULL,
              hypothesis TEXT NOT NULL,
              domain TEXT NOT NULL,
              priority REAL NOT NULL,
              status TEXT NOT NULL,
              payload TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              max_attempts INTEGER NOT NULL DEFAULT 3,
              next_at REAL NOT NULL DEFAULT 0,
              lease_token TEXT,
              lease_generation INTEGER NOT NULL DEFAULT 0,
              lease_expires_at REAL,
              worker TEXT,
              last_error TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(project_id, dedupe_key)
            );
            CREATE TABLE IF NOT EXISTS findings (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              investigation_id TEXT,
              severity TEXT NOT NULL,
              kind TEXT NOT NULL,
              message TEXT NOT NULL,
              path TEXT,
              source_sha256 TEXT,
              evaluator_version TEXT NOT NULL,
              receipt_id TEXT NOT NULL,
              confidence REAL NOT NULL,
              limitations TEXT NOT NULL,
              evidence_id TEXT,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              criterion_key TEXT NOT NULL,
              kind TEXT NOT NULL,
              subject_path TEXT,
              subject_sha256 TEXT,
              collector TEXT NOT NULL,
              check_name TEXT NOT NULL,
              check_version TEXT NOT NULL,
              params TEXT NOT NULL,
              environment TEXT NOT NULL,
              outcome TEXT NOT NULL,
              confidence REAL NOT NULL,
              limitations TEXT NOT NULL,
              raw_ref TEXT,
              task_revision INTEGER NOT NULL,
              policy_hash TEXT NOT NULL,
              created_at TEXT NOT NULL,
              valid_until TEXT,
              status TEXT NOT NULL,
              reason TEXT
            );
            CREATE TABLE IF NOT EXISTS grants (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              actor TEXT NOT NULL,
              action TEXT NOT NULL,
              resource TEXT NOT NULL,
              effect TEXT NOT NULL,
              limits TEXT NOT NULL,
              expires_at TEXT,
              task_revision INTEGER NOT NULL,
              approved_by TEXT NOT NULL,
              payload_hash TEXT,
              revoked INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS approvals (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              action_key TEXT NOT NULL,
              status TEXT NOT NULL,
              requested_at TEXT NOT NULL,
              decided_at TEXT,
              decided_by TEXT,
              reason TEXT,
              details TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS budgets (
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              unit TEXT NOT NULL,
              limit_amount REAL NOT NULL,
              reserved REAL NOT NULL DEFAULT 0,
              spent REAL NOT NULL DEFAULT 0,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(project_id, unit)
            );
            CREATE TABLE IF NOT EXISTS budget_reservations (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              unit TEXT NOT NULL,
              amount REAL NOT NULL,
              state TEXT NOT NULL,
              task_revision INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              settled_at TEXT,
              settled_amount REAL,
              note TEXT
            );
            CREATE TABLE IF NOT EXISTS memory_sources (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              path TEXT,
              sha256 TEXT NOT NULL,
              bytes INTEGER NOT NULL,
              title TEXT NOT NULL,
              kind TEXT NOT NULL,
              tainted INTEGER NOT NULL DEFAULT 1,
              deleted INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              UNIQUE(project_id, sha256)
            );
            CREATE TABLE IF NOT EXISTS memory_chunks (
              rowid INTEGER PRIMARY KEY AUTOINCREMENT,
              id TEXT UNIQUE NOT NULL,
              source_id TEXT NOT NULL REFERENCES memory_sources(id) ON DELETE CASCADE,
              project_id TEXT NOT NULL,
              ord INTEGER NOT NULL,
              text TEXT NOT NULL,
              start INTEGER NOT NULL,
              end INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memory_facts (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              subject TEXT NOT NULL,
              predicate TEXT NOT NULL,
              object TEXT NOT NULL,
              confidence REAL NOT NULL,
              provenance TEXT NOT NULL,
              status TEXT NOT NULL,
              valid_from TEXT,
              valid_to TEXT,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS graph_edges (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              src TEXT NOT NULL,
              dst TEXT NOT NULL,
              kind TEXT NOT NULL,
              provenance TEXT NOT NULL,
              confidence REAL NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notifications (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              severity TEXT NOT NULL,
              dedupe_key TEXT NOT NULL,
              message TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checkpoints (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              contract_revision INTEGER NOT NULL,
              payload TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS waivers (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              criterion_key TEXT NOT NULL,
              reason TEXT NOT NULL,
              decided_by TEXT NOT NULL,
              contract_revision INTEGER NOT NULL DEFAULT 0,
              contract_hash TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS proposals (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              investigation_id TEXT,
              signature TEXT NOT NULL,
              title TEXT NOT NULL,
              rationale TEXT NOT NULL,
              category TEXT NOT NULL,
              risk TEXT NOT NULL,
              expected_impact TEXT NOT NULL,
              files TEXT NOT NULL,
              required_checks TEXT NOT NULL,
              autonomy_level TEXT NOT NULL,
              status TEXT NOT NULL,
              approval_id TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(project_id, signature)
            );
            CREATE INDEX IF NOT EXISTS idx_proposals_project
              ON proposals(project_id, status, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_contracts_project ON task_contracts(project_id, revision DESC);
            CREATE INDEX IF NOT EXISTS idx_investigations_state ON investigations(project_id, status, priority DESC, created_at);
            CREATE INDEX IF NOT EXISTS idx_findings_project ON findings(project_id, status, severity, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_evidence_project ON evidence(project_id, criterion_key, status, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_grants_project ON grants(project_id, action, revoked);
            CREATE INDEX IF NOT EXISTS idx_memory_source ON memory_chunks(project_id, source_id);
            CREATE INDEX IF NOT EXISTS idx_graph_project ON graph_edges(project_id, kind);
            """
        )
        try:
            self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(text, tokenize='unicode61')"
            )
            self.fts_available = True
        except sqlite3.OperationalError:
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS memory_fts_fallback (rowid INTEGER PRIMARY KEY, text TEXT)"
            )
            self.fts_available = False

    # -- meta --------------------------------------------------------------
    def set_meta(self, key: str, value: str) -> None:
        with self.tx(immediate=True):
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def quick_check(self) -> str:
        return str(self.conn.execute("PRAGMA quick_check").fetchone()[0])

    # -- projects ----------------------------------------------------------
    def create_project(self, name: str, root: str) -> str:
        if not name or len(name) > 200:
            raise ValidationError("project name must be 1-200 characters")
        project_id = _new_id()
        now = utc_now()
        with self.tx(immediate=True):
            self.conn.execute(
                "INSERT INTO projects(id, name, root, created_at, updated_at, status) "
                "VALUES(?,?,?,?,?,'active')",
                (project_id, redact_text(name), root, now, now),
            )
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES('project_id', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (project_id,),
            )
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES('project_root', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (root,),
            )
        return project_id

    def get_project(self, project_id: str | None = None) -> dict[str, Any]:
        pid = project_id or self.project_id
        row = self.conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            raise NotFoundError("project not found")
        return dict(row)

    def touch_project(self) -> None:
        with self.tx(immediate=True):
            self.conn.execute(
                "UPDATE projects SET updated_at=? WHERE id=?", (utc_now(), self.project_id)
            )

    def add_artifact(
        self,
        path: str,
        sha256: str,
        size: int,
        kind: str,
        meta: Mapping[str, Any] | None = None,
    ) -> str:
        if not path or len(path) > 2048:
            raise ValidationError("invalid artifact path")
        if len(sha256) != 64:
            raise ValidationError("invalid artifact hash")
        meta_text, _ = dump_bounded(dict(meta or {}), max_bytes=16 * 1024)
        with self.tx(immediate=True):
            existing = self.conn.execute(
                "SELECT id FROM artifacts WHERE project_id=? AND path=? AND sha256=?",
                (self.project_id, path, sha256),
            ).fetchone()
            if existing:
                return str(existing["id"])
            artifact_id = _new_id("art_")
            self.conn.execute(
                "INSERT INTO artifacts(id, project_id, path, sha256, bytes, kind, meta, created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (artifact_id, self.project_id, path, sha256, int(size), kind, meta_text, utc_now()),
            )
        return artifact_id

    def list_artifacts(self, limit: int = 1000) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM artifacts WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
            (self.project_id, min(limit, 5000)),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- contracts ---------------------------------------------------------
    def save_contract(self, contract: TaskContract) -> str:
        if contract.project_id != self.project_id:
            raise ConflictError("contract project_id does not match this database")
        payload = contract.to_dict()
        payload_text = canonical_json(payload)
        contract_hash = contract.hash()
        with self.tx(immediate=True):
            existing = self.conn.execute(
                "SELECT id, hash FROM task_contracts WHERE project_id=? AND revision=?",
                (self.project_id, contract.revision),
            ).fetchone()
            if existing:
                if existing["hash"] != contract_hash:
                    raise ConflictError("contract revision already exists with different content")
                return str(existing["id"])
            contract_id = _new_id("con_")
            self.conn.execute(
                "INSERT INTO task_contracts(id, project_id, revision, hash, payload, created_at) "
                "VALUES(?,?,?,?,?,?)",
                (contract_id, self.project_id, contract.revision, contract_hash, payload_text, utc_now()),
            )
            self.conn.execute(
                "INSERT INTO goals(id, project_id, intent, revision, created_at) VALUES(?,?,?,?,?)",
                (_new_id("goal_"), self.project_id, contract.intent, contract.revision, utc_now()),
            )
            for requirement in contract.requirements:
                req_id = _new_id("req_")
                self.conn.execute(
                    "INSERT INTO requirements(id, contract_id, key, text, domain) VALUES(?,?,?,?,?)",
                    (req_id, contract_id, requirement.key, requirement.text, requirement.domain),
                )
                for criterion in requirement.criteria:
                    self.conn.execute(
                        "INSERT INTO criteria(id, requirement_id, key, description, evaluator, "
                        "mandatory, params) VALUES(?,?,?,?,?,?,?)",
                        (
                            _new_id("crit_"),
                            req_id,
                            criterion.key,
                            criterion.description,
                            criterion.evaluator,
                            1 if criterion.mandatory else 0,
                            canonical_json(dict(criterion.params)),
                        ),
                    )
        self._apply_contract_budgets(contract)
        return contract_id

    def _apply_contract_budgets(self, contract: TaskContract) -> None:
        mapping = {
            "model_calls": contract.budgets.max_model_calls,
            "input_tokens": contract.budgets.max_input_tokens,
            "output_tokens": contract.budgets.max_output_tokens,
            "cost_usd": contract.budgets.max_cost_usd,
            "wall_seconds": contract.budgets.max_wall_seconds,
            "cpu_seconds": contract.budgets.max_cpu_seconds,
            "findings": contract.budgets.max_findings,
            "output_bytes": contract.budgets.max_output_bytes,
        }
        for unit, limit in mapping.items():
            self.set_budget_limit(unit, float(limit))

    def latest_contract(self) -> tuple[dict[str, Any], TaskContract] | None:
        row = self.conn.execute(
            "SELECT * FROM task_contracts WHERE project_id=? ORDER BY revision DESC LIMIT 1",
            (self.project_id,),
        ).fetchone()
        if not row:
            return None
        data = bounded_json_loads(row["payload"], max_bytes=4 * 1024 * 1024)
        return dict(row), TaskContract.from_dict(data)

    def get_contract_revision(self, revision: int) -> tuple[dict[str, Any], TaskContract]:
        row = self.conn.execute(
            "SELECT * FROM task_contracts WHERE project_id=? AND revision=?",
            (self.project_id, revision),
        ).fetchone()
        if not row:
            raise NotFoundError("contract revision not found")
        data = bounded_json_loads(row["payload"], max_bytes=4 * 1024 * 1024)
        return dict(row), TaskContract.from_dict(data)

    def criteria(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT r.key AS requirement_key, r.domain, c.key, c.description, c.evaluator, "
            "c.mandatory, c.params FROM criteria c "
            "JOIN requirements r ON r.id = c.requirement_id "
            "JOIN task_contracts tc ON tc.id = r.contract_id "
            "WHERE tc.id = (SELECT id FROM task_contracts WHERE project_id=? "
            "ORDER BY revision DESC LIMIT 1) ORDER BY r.key, c.key",
            (self.project_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- budgets -----------------------------------------------------------
    def set_budget_limit(self, unit: str, limit_amount: float) -> None:
        if not math.isfinite(limit_amount) or limit_amount < 0:
            raise ValidationError("budget limit must be a finite non-negative number")
        with self.tx(immediate=True):
            self.conn.execute(
                "INSERT INTO budgets(project_id, unit, limit_amount, reserved, spent, updated_at) "
                "VALUES(?,?,?,0,0,?) ON CONFLICT(project_id, unit) DO UPDATE SET "
                "limit_amount=excluded.limit_amount, updated_at=excluded.updated_at",
                (self.project_id, unit, float(limit_amount), utc_now()),
            )

    def reserve_budget(self, unit: str, amount: float, task_revision: int, note: str = "") -> str:
        if not math.isfinite(amount) or amount <= 0:
            raise ValidationError("reservation amount must be positive and finite")
        with self.tx(immediate=True):
            row = self.conn.execute(
                "SELECT limit_amount, reserved, spent FROM budgets WHERE project_id=? AND unit=?",
                (self.project_id, unit),
            ).fetchone()
            if not row:
                self.conn.execute(
                    "INSERT INTO budgets(project_id, unit, limit_amount, reserved, spent, updated_at) "
                    "VALUES(?,?,0,0,0,?)",
                    (self.project_id, unit, utc_now()),
                )
                limit, reserved, spent = 0.0, 0.0, 0.0
            else:
                limit, reserved, spent = row["limit_amount"], row["reserved"], row["spent"]
            available = limit - reserved - spent
            if amount > available + 1e-9:
                raise BudgetExceeded(
                    f"budget '{unit}' exhausted (requested {amount:g}, available {max(available, 0):g})"
                )
            self.conn.execute(
                "UPDATE budgets SET reserved = reserved + ?, updated_at=? "
                "WHERE project_id=? AND unit=?",
                (amount, utc_now(), self.project_id, unit),
            )
            reservation_id = _new_id("res_")
            self.conn.execute(
                "INSERT INTO budget_reservations(id, project_id, unit, amount, state, "
                "task_revision, created_at, note) VALUES(?,?,?,?, 'reserved', ?,?,?)",
                (reservation_id, self.project_id, unit, float(amount), task_revision, utc_now(), note),
            )
        return reservation_id

    def settle_reservation(self, reservation_id: str, actual: float | None = None) -> float:
        with self.tx(immediate=True):
            row = self.conn.execute(
                "SELECT * FROM budget_reservations WHERE id=? AND project_id=?",
                (reservation_id, self.project_id),
            ).fetchone()
            if not row:
                raise NotFoundError("reservation not found")
            if row["state"] != "reserved":
                raise ConflictError("reservation is not open")
            settled = row["amount"] if actual is None else float(actual)
            if not math.isfinite(settled) or settled < 0:
                raise ValidationError("settled amount must be finite and non-negative")
            self.conn.execute(
                "UPDATE budgets SET reserved = MAX(reserved - ?, 0), spent = spent + ?, updated_at=? "
                "WHERE project_id=? AND unit=?",
                (row["amount"], settled, utc_now(), self.project_id, row["unit"]),
            )
            self.conn.execute(
                "UPDATE budget_reservations SET state='settled', settled_at=?, settled_amount=? "
                "WHERE id=?",
                (utc_now(), settled, reservation_id),
            )
        return settled

    def release_reservation(self, reservation_id: str) -> None:
        with self.tx(immediate=True):
            row = self.conn.execute(
                "SELECT * FROM budget_reservations WHERE id=? AND project_id=?",
                (reservation_id, self.project_id),
            ).fetchone()
            if not row:
                raise NotFoundError("reservation not found")
            if row["state"] != "reserved":
                return
            self.conn.execute(
                "UPDATE budgets SET reserved = MAX(reserved - ?, 0), updated_at=? "
                "WHERE project_id=? AND unit=?",
                (row["amount"], utc_now(), self.project_id, row["unit"]),
            )
            self.conn.execute(
                "UPDATE budget_reservations SET state='released', settled_at=? WHERE id=?",
                (utc_now(), reservation_id),
            )

    def budget_status(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT unit, limit_amount, reserved, spent, "
            "(limit_amount - reserved - spent) AS available FROM budgets "
            "WHERE project_id=? ORDER BY unit",
            (self.project_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def model_calls_spent(self) -> float:
        row = self.conn.execute(
            "SELECT spent FROM budgets WHERE project_id=? AND unit='model_calls'",
            (self.project_id,),
        ).fetchone()
        return float(row["spent"]) if row else 0.0

    # -- events ------------------------------------------------------------
    def record_event(self, event_type: str, dedupe_key: str, payload: Mapping[str, Any]) -> str:
        if not event_type or len(event_type) > 100:
            raise ValidationError("invalid event type")
        if not dedupe_key or len(dedupe_key) > 200:
            raise ValidationError("invalid event dedupe key")
        text, _ = dump_bounded(payload, max_bytes=64 * 1024)
        with self.tx(immediate=True):
            existing = self.conn.execute(
                "SELECT id FROM events WHERE project_id=? AND dedupe_key=?",
                (self.project_id, dedupe_key),
            ).fetchone()
            if existing:
                return str(existing["id"])
            event_id = _new_id("evt_")
            self.conn.execute(
                "INSERT INTO events(id, project_id, type, dedupe_key, payload, status, created_at) "
                "VALUES(?,?,?,?,?,'pending',?)",
                (event_id, self.project_id, event_type, dedupe_key, text, utc_now()),
            )
        return event_id

    def pending_events(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM events WHERE project_id=? AND status='pending' "
            "ORDER BY created_at LIMIT ?",
            (self.project_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_event_processed(self, event_id: str) -> None:
        with self.tx(immediate=True):
            self.conn.execute(
                "UPDATE events SET status='processed', processed_at=? WHERE id=? AND project_id=?",
                (utc_now(), event_id, self.project_id),
            )

    # -- investigations / queue -------------------------------------------
    def enqueue_investigation(
        self,
        title: str,
        hypothesis: str,
        domain: str = "general",
        priority: float = 0.5,
        payload: Mapping[str, Any] | None = None,
        max_attempts: int = 3,
        dedupe_key: str | None = None,
        next_in_seconds: float = 0.0,
    ) -> str:
        if not title or len(title) > 300:
            raise ValidationError("invalid investigation title")
        if not hypothesis or len(hypothesis) > 4000:
            raise ValidationError("invalid investigation hypothesis")
        if not (0.0 <= priority <= 1.0):
            raise ValidationError("priority must be between 0 and 1")
        if max_attempts < 1 or max_attempts > 10:
            raise ValidationError("max_attempts must be 1-10")
        text, _ = dump_bounded(dict(payload or {}), max_bytes=64 * 1024)
        with self.tx(immediate=True):
            if dedupe_key:
                existing = self.conn.execute(
                    "SELECT id FROM investigations WHERE project_id=? AND dedupe_key=?",
                    (self.project_id, dedupe_key),
                ).fetchone()
                if existing:
                    return str(existing["id"])
            investigation_id = _new_id("inv_")
            now = utc_now()
            self.conn.execute(
                "INSERT INTO investigations(id, project_id, dedupe_key, title, hypothesis, domain, "
                "priority, status, payload, attempts, max_attempts, next_at, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?, 'ready', ?, 0, ?, ?, ?, ?)",
                (
                    investigation_id,
                    self.project_id,
                    dedupe_key,
                    redact_text(title),
                    redact_text(hypothesis),
                    domain,
                    float(priority),
                    text,
                    max_attempts,
                    now_ts() + max(0.0, next_in_seconds),
                    now,
                    now,
                ),
            )
        return investigation_id

    def reconcile_expired(self, now: float | None = None) -> int:
        current = now_ts() if now is None else now
        with self.tx(immediate=True):
            cursor = self.conn.execute(
                "UPDATE investigations SET status = CASE WHEN attempts >= max_attempts "
                "THEN 'failed' ELSE 'ready' END, lease_token=NULL, lease_expires_at=NULL, "
                "worker=NULL, updated_at=? WHERE project_id=? AND status='running' "
                "AND lease_expires_at IS NOT NULL AND lease_expires_at < ?",
                (utc_now(), self.project_id, current),
            )
            return int(cursor.rowcount or 0)

    def claim_next(
        self, worker: str, lease_seconds: float = 120.0, now: float | None = None
    ) -> "Claim | None":
        current = now_ts() if now is None else now
        with self.tx(immediate=True):
            self.conn.execute(
                "UPDATE investigations SET status = CASE WHEN attempts >= max_attempts "
                "THEN 'failed' ELSE 'ready' END, lease_token=NULL, lease_expires_at=NULL, "
                "worker=NULL, updated_at=? WHERE project_id=? AND status='running' "
                "AND lease_expires_at IS NOT NULL AND lease_expires_at < ?",
                (utc_now(), self.project_id, current),
            )
            row = self.conn.execute(
                "SELECT * FROM investigations WHERE project_id=? AND status='ready' "
                "AND attempts < max_attempts AND next_at <= ? "
                "ORDER BY priority DESC, created_at ASC LIMIT 1",
                (self.project_id, current),
            ).fetchone()
            if not row:
                return None
            token = _new_id("lease_")
            generation = int(row["lease_generation"]) + 1
            attempts = int(row["attempts"]) + 1
            self.conn.execute(
                "UPDATE investigations SET status='running', lease_token=?, lease_generation=?, "
                "lease_expires_at=?, worker=?, attempts=?, updated_at=? "
                "WHERE id=? AND status='ready' AND lease_generation=?",
                (
                    token,
                    generation,
                    current + lease_seconds,
                    worker,
                    attempts,
                    utc_now(),
                    row["id"],
                    int(row["lease_generation"]),
                ),
            )
            updated = self.conn.execute(
                "SELECT * FROM investigations WHERE id=?", (row["id"],)
            ).fetchone()
            if not updated or updated["lease_token"] != token:
                raise FencedWriteError("claim lost a race")
            payload = bounded_json_loads(updated["payload"], max_bytes=64 * 1024)
            return Claim(
                id=str(updated["id"]),
                token=token,
                generation=generation,
                attempts=attempts,
                max_attempts=int(updated["max_attempts"]),
                title=str(updated["title"]),
                hypothesis=str(updated["hypothesis"]),
                domain=str(updated["domain"]),
                payload=payload if isinstance(payload, dict) else {},
                worker=worker,
            )

    def _assert_fence(self, claim: "Claim", now: float | None = None) -> sqlite3.Row:
        current = now_ts() if now is None else now
        row = self.conn.execute(
            "SELECT * FROM investigations WHERE id=? AND project_id=?",
            (claim.id, self.project_id),
        ).fetchone()
        if not row:
            raise FencedWriteError("investigation no longer exists")
        if row["status"] != "running":
            raise FencedWriteError("investigation is not running")
        if row["lease_token"] != claim.token or int(row["lease_generation"]) != claim.generation:
            raise FencedWriteError("stale lease token/generation rejected")
        if row["lease_expires_at"] is None or float(row["lease_expires_at"]) <= current:
            raise FencedWriteError("lease expired; publish rejected")
        return row

    def renew_lease(self, claim: "Claim", lease_seconds: float = 120.0) -> None:
        with self.tx(immediate=True):
            self._assert_fence(claim)
            self.conn.execute(
                "UPDATE investigations SET lease_expires_at=?, updated_at=? WHERE id=?",
                (now_ts() + lease_seconds, utc_now(), claim.id),
            )

    def complete_investigation(
        self, claim: "Claim", result: Mapping[str, Any] | None = None
    ) -> None:
        with self.tx(immediate=True):
            self._assert_fence(claim)
            payload_text, _ = dump_bounded(dict(result or {}), max_bytes=64 * 1024)
            self.conn.execute(
                "UPDATE investigations SET status='completed', payload=?, lease_token=NULL, "
                "lease_expires_at=NULL, worker=NULL, updated_at=? WHERE id=?",
                (payload_text, utc_now(), claim.id),
            )

    def fail_investigation(self, claim: "Claim", error: str) -> None:
        with self.tx(immediate=True):
            row = self._assert_fence(claim)
            attempts = int(row["attempts"])
            max_attempts = int(row["max_attempts"])
            if attempts >= max_attempts:
                status = "failed"
                next_at = 0.0
            else:
                status = "ready"
                next_at = now_ts() + min(300.0, 2.0 ** attempts)
            self.conn.execute(
                "UPDATE investigations SET status=?, lease_token=NULL, lease_expires_at=NULL, "
                "worker=NULL, last_error=?, next_at=?, updated_at=? WHERE id=?",
                (status, redact_text(error), next_at, utc_now(), claim.id),
            )

    def publish(
        self,
        claim: "Claim",
        evidence_items: Sequence[Mapping[str, Any]],
        findings: Sequence[Mapping[str, Any]],
    ) -> tuple[list[str], list[str]]:
        evidence_ids: list[str] = []
        finding_ids: list[str] = []
        with self.tx(immediate=True):
            self._assert_fence(claim)
            for item in evidence_items:
                evidence_ids.append(self._insert_evidence(dict(item), investigation_id=claim.id))
            for item in findings:
                finding_ids.append(self._insert_finding(dict(item), investigation_id=claim.id))
            self.conn.execute(
                "UPDATE investigations SET status='completed', lease_token=NULL, "
                "lease_expires_at=NULL, worker=NULL, updated_at=? WHERE id=?",
                (utc_now(), claim.id),
            )
        return evidence_ids, finding_ids

    def list_investigations(
        self, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM investigations WHERE project_id=? AND status=? "
                "ORDER BY created_at DESC LIMIT ?",
                (self.project_id, status, min(limit, 1000)),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM investigations WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
                (self.project_id, min(limit, 1000)),
            ).fetchall()
        return [dict(r) for r in rows]

    def investigation_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM investigations WHERE project_id=? GROUP BY status",
            (self.project_id,),
        ).fetchall()
        return {str(r["status"]): int(r["n"]) for r in rows}

    # -- evidence / findings ----------------------------------------------
    def _insert_evidence(
        self, item: Mapping[str, Any], investigation_id: str | None = None
    ) -> str:
        required = (
            "criterion_key",
            "kind",
            "collector",
            "check_name",
            "check_version",
            "outcome",
            "task_revision",
            "policy_hash",
        )
        for key in required:
            if key not in item:
                raise ValidationError(f"evidence missing '{key}'")
        outcome = str(item["outcome"])
        if outcome not in {"pass", "fail", "unknown", "blocked", "error", "partial"}:
            raise ValidationError("invalid evidence outcome")
        confidence = float(item.get("confidence", 1.0))
        if not (0.0 <= confidence <= 1.0):
            raise ValidationError("evidence confidence must be 0..1")
        evidence_id = str(item.get("id") or _new_id("ev_"))
        if len(evidence_id) > 80:
            raise ValidationError("evidence id too long")
        created = utc_now()
        params_text, _ = dump_bounded(dict(item.get("params", {})), max_bytes=32 * 1024)
        env_text, _ = dump_bounded(dict(item.get("environment", {})), max_bytes=32 * 1024)
        valid_until = item.get("valid_until")
        if valid_until is not None and not isinstance(valid_until, str):
            raise ValidationError("valid_until must be ISO text")
        self.conn.execute(
            "INSERT INTO evidence(id, project_id, criterion_key, kind, subject_path, "
            "subject_sha256, collector, check_name, check_version, params, environment, outcome, "
            "confidence, limitations, raw_ref, task_revision, policy_hash, created_at, valid_until, "
            "status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'valid')",
            (
                evidence_id,
                self.project_id,
                str(item["criterion_key"]),
                str(item["kind"]),
                item.get("subject_path"),
                item.get("subject_sha256"),
                str(item["collector"]),
                str(item["check_name"]),
                str(item["check_version"]),
                params_text,
                env_text,
                outcome,
                confidence,
                redact_text(str(item.get("limitations", "")))[:4000],
                item.get("raw_ref"),
                int(item["task_revision"]),
                str(item["policy_hash"]),
                created,
                valid_until,
            ),
        )
        return evidence_id

    def add_evidence(self, item: Mapping[str, Any]) -> str:
        with self.tx(immediate=True):
            return self._insert_evidence(item)

    def _insert_finding(
        self, item: Mapping[str, Any], investigation_id: str | None = None
    ) -> str:
        severity = str(item.get("severity", "info"))
        if severity not in {"info", "low", "medium", "high", "critical"}:
            raise ValidationError("invalid finding severity")
        kind = str(item.get("kind", "general"))
        message = redact_text(str(item.get("message", "")))[:4000]
        if not message:
            raise ValidationError("finding message must not be empty")
        evaluator_version = str(item.get("evaluator_version", ""))
        receipt_id = str(item.get("receipt_id", ""))
        path = item.get("path")
        source_sha = item.get("source_sha256")
        if not evaluator_version:
            raise ValidationError("finding requires evaluator_version")
        if not receipt_id:
            raise ValidationError("finding requires receipt_id")
        if path and not source_sha:
            raise ValidationError("path-bound finding requires source_sha256")
        confidence = float(item.get("confidence", 0.5))
        if not (0.0 <= confidence <= 1.0):
            raise ValidationError("finding confidence must be 0..1")
        finding_id = _new_id("f_")
        self.conn.execute(
            "INSERT INTO findings(id, project_id, investigation_id, severity, kind, message, path, "
            "source_sha256, evaluator_version, receipt_id, confidence, limitations, evidence_id, "
            "status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'open',?)",
            (
                finding_id,
                self.project_id,
                investigation_id or item.get("investigation_id"),
                severity,
                kind,
                message,
                path,
                source_sha,
                evaluator_version,
                receipt_id,
                confidence,
                redact_text(str(item.get("limitations", "")))[:4000],
                item.get("evidence_id"),
                utc_now(),
            ),
        )
        return finding_id

    def add_finding(self, item: Mapping[str, Any]) -> str:
        with self.tx(immediate=True):
            return self._insert_finding(item)

    def list_findings(
        self, limit: int = 100, severity: str | None = None, status: str = "open"
    ) -> list[dict[str, Any]]:
        params: list[Any] = [self.project_id, status]
        query = "SELECT * FROM findings WHERE project_id=? AND status=?"
        if severity:
            query += " AND severity=?"
            params.append(severity)
        query += " ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 " \
                 "WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END, created_at DESC LIMIT ?"
        params.append(min(max(limit, 1), 5000))
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def finding_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT severity, COUNT(*) AS n FROM findings WHERE project_id=? AND status='open' "
            "GROUP BY severity",
            (self.project_id,),
        ).fetchall()
        return {str(r["severity"]): int(r["n"]) for r in rows}

    def dismiss_finding(self, finding_id: str, reason: str) -> None:
        with self.tx(immediate=True):
            self.conn.execute(
                "UPDATE findings SET status='dismissed', limitations=? "
                "WHERE id=? AND project_id=?",
                (redact_text(reason)[:4000], finding_id, self.project_id),
            )

    def get_evidence(self, evidence_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM evidence WHERE id=? AND project_id=?",
            (evidence_id, self.project_id),
        ).fetchone()
        if not row:
            raise NotFoundError("evidence not found")
        return dict(row)

    def list_evidence(
        self, limit: int = 100, criterion_key: str | None = None
    ) -> list[dict[str, Any]]:
        if criterion_key:
            rows = self.conn.execute(
                "SELECT * FROM evidence WHERE project_id=? AND criterion_key=? "
                "ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (self.project_id, criterion_key, min(limit, 1000)),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM evidence WHERE project_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (self.project_id, min(limit, 1000)),
            ).fetchall()
        return [dict(r) for r in rows]

    def set_evidence_status(self, evidence_id: str, status: str, reason: str = "") -> None:
        if status not in {"valid", "stale", "superseded", "invalid"}:
            raise ValidationError("invalid evidence status")
        with self.tx(immediate=True):
            self.conn.execute(
                "UPDATE evidence SET status=?, reason=? WHERE id=? AND project_id=?",
                (status, redact_text(reason)[:2000], evidence_id, self.project_id),
            )

    def waive_criterion(self, criterion_key: str, reason: str, decided_by: str = "owner") -> str:
        if decided_by != "owner":
            raise ValidationError("only the owner can waive a criterion")
        if not reason or len(reason) > 2000:
            raise ValidationError("waiver reason is required")
        waiver_id = _new_id("waive_")
        latest = self.latest_contract()
        revision = int(latest[0]["revision"]) if latest else 0
        contract_hash = str(latest[0]["hash"]) if latest else ""
        with self.tx(immediate=True):
            self.conn.execute(
                "INSERT INTO waivers(id, project_id, criterion_key, reason, decided_by, "
                "contract_revision, contract_hash, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    waiver_id,
                    self.project_id,
                    criterion_key,
                    redact_text(reason),
                    decided_by,
                    revision,
                    contract_hash,
                    utc_now(),
                ),
            )
        return waiver_id

    def waivers(self) -> dict[str, dict[str, Any]]:
        latest = self.latest_contract()
        if not latest:
            return {}
        rows = self.conn.execute(
            "SELECT * FROM waivers WHERE project_id=? AND contract_revision=? AND contract_hash=? "
            "ORDER BY created_at DESC",
            (self.project_id, int(latest[0]["revision"]), str(latest[0]["hash"])),
        ).fetchall()
        out: dict[str, dict[str, Any]] = {}
        for row in rows:
            out.setdefault(str(row["criterion_key"]), dict(row))
        return out

    # -- self-improvement proposals ---------------------------------------
    def add_proposal(
        self,
        *,
        signature: str,
        title: str,
        rationale: str,
        category: str,
        risk: str,
        expected_impact: str,
        files: Sequence[str],
        required_checks: Sequence[str],
        investigation_id: str | None = None,
    ) -> str:
        if not signature or len(signature) > 300:
            raise ValidationError("invalid proposal signature")
        if not title or len(title) > 300:
            raise ValidationError("invalid proposal title")
        if not rationale or len(rationale) > 4000:
            raise ValidationError("invalid proposal rationale")
        if risk not in {"low", "medium", "high"}:
            raise ValidationError("invalid proposal risk")
        files_text, _ = dump_bounded([str(f)[:512] for f in list(files)[:50]], max_bytes=16 * 1024)
        checks_text, _ = dump_bounded(
            [str(c)[:300] for c in list(required_checks)[:30]], max_bytes=16 * 1024
        )
        with self.tx(immediate=True):
            existing = self.conn.execute(
                "SELECT id FROM proposals WHERE project_id=? AND signature=?",
                (self.project_id, signature),
            ).fetchone()
            if existing:
                return str(existing["id"])
            proposal_id = _new_id("prop_")
            now = utc_now()
            self.conn.execute(
                "INSERT INTO proposals(id, project_id, investigation_id, signature, title, rationale, "
                "category, risk, expected_impact, files, required_checks, autonomy_level, status, "
                "created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?, 'proposal-only', 'proposed', ?, ?)",
                (
                    proposal_id,
                    self.project_id,
                    investigation_id,
                    redact_text(signature)[:300],
                    redact_text(title)[:300],
                    redact_text(rationale)[:4000],
                    redact_text(category)[:100],
                    risk,
                    redact_text(expected_impact)[:1000],
                    files_text,
                    checks_text,
                    now,
                    now,
                ),
            )
        return proposal_id

    def list_proposals(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM proposals WHERE project_id=? AND status=? "
                "ORDER BY created_at DESC LIMIT ?",
                (self.project_id, status, min(max(limit, 1), 1000)),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM proposals WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
                (self.project_id, min(max(limit, 1), 1000)),
            ).fetchall()
        return [dict(r) for r in rows]

    def find_proposal(self, signature: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM proposals WHERE project_id=? AND signature=?",
            (self.project_id, signature),
        ).fetchone()
        return dict(row) if row else None

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM proposals WHERE id=? AND project_id=?",
            (proposal_id, self.project_id),
        ).fetchone()
        if not row:
            raise NotFoundError("proposal not found")
        return dict(row)

    def decide_proposal(
        self, proposal_id: str, decision: str, decided_by: str = "owner", reason: str = ""
    ) -> str:
        if decided_by != "owner":
            raise ValidationError("only the owner can decide a proposal")
        if decision not in {"approved", "rejected"}:
            raise ValidationError("decision must be approved or rejected")
        proposal = self.get_proposal(proposal_id)
        approval_id = self.request_approval(
            action_key=f"self_improve:{proposal_id}",
            details={"proposal_id": proposal_id, "category": proposal["category"], "risk": proposal["risk"]},
            reason=reason,
        )
        self.decide_approval(approval_id, decision, decided_by, reason)
        with self.tx(immediate=True):
            self.conn.execute(
                "UPDATE proposals SET status=?, approval_id=?, updated_at=? WHERE id=? AND project_id=?",
                (decision, approval_id, utc_now(), proposal_id, self.project_id),
            )
        return approval_id

    def proposal_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM proposals WHERE project_id=? GROUP BY status",
            (self.project_id,),
        ).fetchall()
        return {str(r["status"]): int(r["n"]) for r in rows}

    # -- grants / approvals -------------------------------------------------
    def add_grant(
        self,
        actor: str,
        action: str,
        resource: str,
        effect: str,
        limits: Mapping[str, Any],
        task_revision: int,
        approved_by: str,
        expires_at: str | None = None,
        payload_hash: str | None = None,
    ) -> str:
        if approved_by != "owner":
            raise ValidationError("only the owner may approve a capability grant")
        if effect not in {"allow", "deny"}:
            raise ValidationError("grant effect must be allow or deny")
        if not actor or len(actor) > 200:
            raise ValidationError("invalid grant actor")
        limits_text, _ = dump_bounded(dict(limits), max_bytes=16 * 1024)
        grant_id = _new_id("grant_")
        with self.tx(immediate=True):
            self.conn.execute(
                "INSERT INTO grants(id, project_id, actor, action, resource, effect, limits, "
                "expires_at, task_revision, approved_by, payload_hash, revoked, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,0,?)",
                (
                    grant_id,
                    self.project_id,
                    actor,
                    action,
                    resource,
                    effect,
                    limits_text,
                    expires_at,
                    task_revision,
                    approved_by,
                    payload_hash,
                    utc_now(),
                ),
            )
        return grant_id

    def get_grant(self, grant_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM grants WHERE id=? AND project_id=?",
            (grant_id, self.project_id),
        ).fetchone()
        if not row:
            raise NotFoundError("grant not found")
        return dict(row)

    def list_grants(self, include_revoked: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM grants WHERE project_id=?"
        if not include_revoked:
            query += " AND revoked=0"
        query += " ORDER BY created_at DESC, rowid DESC"
        rows = self.conn.execute(query, (self.project_id,)).fetchall()
        return [dict(r) for r in rows]

    def revoke_grant(self, grant_id: str) -> None:
        with self.tx(immediate=True):
            self.conn.execute(
                "UPDATE grants SET revoked=1 WHERE id=? AND project_id=?",
                (grant_id, self.project_id),
            )

    def request_approval(
        self, action_key: str, details: Mapping[str, Any], reason: str = ""
    ) -> str:
        approval_id = _new_id("appr_")
        details_text, _ = dump_bounded(dict(details), max_bytes=32 * 1024)
        with self.tx(immediate=True):
            self.conn.execute(
                "INSERT INTO approvals(id, project_id, action_key, status, requested_at, reason, "
                "details) VALUES(?,?,?, 'pending', ?,?,?)",
                (approval_id, self.project_id, action_key, utc_now(), redact_text(reason)[:2000], details_text),
            )
        return approval_id

    def decide_approval(
        self, approval_id: str, decision: str, decided_by: str, reason: str = ""
    ) -> None:
        if decision not in {"approved", "denied"}:
            raise ValidationError("decision must be approved or denied")
        if decided_by != "owner":
            raise ValidationError("only the owner can decide an approval")
        with self.tx(immediate=True):
            self.conn.execute(
                "UPDATE approvals SET status=?, decided_at=?, decided_by=?, reason=? "
                "WHERE id=? AND project_id=? AND status='pending'",
                (decision, utc_now(), decided_by, redact_text(reason)[:2000], approval_id, self.project_id),
            )

    def get_approval(self, approval_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM approvals WHERE id=? AND project_id=?",
            (approval_id, self.project_id),
        ).fetchone()
        if not row:
            raise NotFoundError("approval not found")
        return dict(row)

    # -- memory ------------------------------------------------------------
    def add_memory_source(
        self,
        text: str,
        title: str,
        kind: str = "text",
        path: str | None = None,
        tainted: bool = True,
        chunk_chars: int = 3000,
        overlap: int = 300,
        max_chunks: int = 5000,
    ) -> str:
        if not text:
            raise ValidationError("memory text must not be empty")
        if len(text) > 16 * 1024 * 1024:
            raise BoundsError("memory source exceeds 16MB")
        if overlap >= chunk_chars or overlap < 0:
            raise ValidationError("invalid chunk overlap")
        digest = sha256_text(text)
        with self.tx(immediate=True):
            existing = self.conn.execute(
                "SELECT id, deleted FROM memory_sources WHERE project_id=? AND sha256=?",
                (self.project_id, digest),
            ).fetchone()
            if existing:
                if not int(existing["deleted"]):
                    return str(existing["id"])
                self.conn.execute(
                    "DELETE FROM memory_sources WHERE id=? AND project_id=?",
                    (existing["id"], self.project_id),
                )
            source_id = _new_id("src_")
            self.conn.execute(
                "INSERT INTO memory_sources(id, project_id, path, sha256, bytes, title, kind, "
                "tainted, deleted, created_at) VALUES(?,?,?,?,?,?,?,?,0,?)",
                (
                    source_id,
                    self.project_id,
                    path,
                    digest,
                    len(text.encode("utf-8")),
                    redact_text(title)[:500],
                    kind,
                    1 if tainted else 0,
                    utc_now(),
                ),
            )
            start = 0
            order = 0
            while start < len(text) and order < max_chunks:
                end = min(len(text), start + chunk_chars)
                chunk = text[start:end]
                chunk_id = _new_id("chk_")
                cursor = self.conn.execute(
                    "INSERT INTO memory_chunks(id, source_id, project_id, ord, text, start, end) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (chunk_id, source_id, self.project_id, order, chunk, start, end),
                )
                fts_rowid = int(cursor.lastrowid)
                if self.fts_available:
                    self.conn.execute(
                        "INSERT INTO memory_fts(rowid, text) VALUES(?,?)", (fts_rowid, chunk)
                    )
                else:
                    self.conn.execute(
                        "INSERT INTO memory_fts_fallback(rowid, text) VALUES(?,?)",
                        (fts_rowid, chunk),
                    )
                order += 1
                if end >= len(text):
                    break
                start = end - overlap
        return source_id

    @staticmethod
    def _fts_query(query: str) -> str:
        terms: list[str] = []
        for raw in query.replace("\x00", " ").split():
            cleaned = "".join(ch for ch in raw if ch.isalnum() or ch in "._-")
            if cleaned:
                terms.append(f'"{cleaned}"')
            if len(terms) >= 20:
                break
        return " AND ".join(terms)

    def search_memory(
        self, query: str, limit: int = 8, include_tainted: bool = True
    ) -> list[dict[str, Any]]:
        if not query or len(query) > 512:
            raise ValidationError("invalid memory query")
        bounded_limit = min(max(limit, 1), 50)
        params: list[Any] = [self.project_id]
        taint_clause = "" if include_tainted else " AND s.tainted=0"
        if self.fts_available:
            match = self._fts_query(query)
            if not match:
                return []
            sql = (
                "SELECT c.id, c.text, c.ord, c.start, c.end, s.id AS source_id, s.path, "
                "s.sha256, s.title, s.tainted, bm25(memory_fts) AS score "
                "FROM memory_fts JOIN memory_chunks c ON c.rowid = memory_fts.rowid "
                "JOIN memory_sources s ON s.id = c.source_id "
                "WHERE memory_fts MATCH ? AND c.project_id=? AND s.deleted=0" + taint_clause
                + " ORDER BY score LIMIT ?"
            )
            rows = self.conn.execute(sql, [match, *params, bounded_limit]).fetchall()
        else:
            like = f"%{query[:128]}%"
            sql = (
                "SELECT c.id, c.text, c.ord, c.start, c.end, s.id AS source_id, s.path, "
                "s.sha256, s.title, s.tainted, 0.0 AS score "
                "FROM memory_chunks c JOIN memory_sources s ON s.id = c.source_id "
                "WHERE c.project_id=? AND s.deleted=0 AND c.text LIKE ?" + taint_clause
                + " ORDER BY c.ord LIMIT ?"
            )
            rows = self.conn.execute(sql, [*params, like, bounded_limit]).fetchall()
        return [dict(r) for r in rows]

    def forget_memory_source(self, source_id: str) -> None:
        with self.tx(immediate=True):
            source = self.conn.execute(
                "SELECT id FROM memory_sources WHERE id=? AND project_id=?",
                (source_id, self.project_id),
            ).fetchone()
            if not source:
                raise NotFoundError("memory source not found")
            rows = self.conn.execute(
                "SELECT rowid FROM memory_chunks WHERE source_id=? AND project_id=?",
                (source_id, self.project_id),
            ).fetchall()
            for row in rows:
                rowid = int(row["rowid"])
                if self.fts_available:
                    self.conn.execute("DELETE FROM memory_fts WHERE rowid=?", (rowid,))
                else:
                    self.conn.execute("DELETE FROM memory_fts_fallback WHERE rowid=?", (rowid,))
            self.conn.execute(
                "DELETE FROM memory_chunks WHERE source_id=? AND project_id=?",
                (source_id, self.project_id),
            )
            self.conn.execute(
                "UPDATE memory_sources SET deleted=1, path=NULL WHERE id=? AND project_id=?",
                (source_id, self.project_id),
            )

    def list_memory_sources(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, path, sha256, bytes, title, kind, tainted, deleted, created_at "
            "FROM memory_sources WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
            (self.project_id, min(limit, 1000)),
        ).fetchall()
        return [dict(r) for r in rows]

    def add_fact(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float,
        provenance: str,
        status: str = "proposed",
    ) -> str:
        if status not in {"proposed", "confirmed", "rejected"}:
            raise ValidationError("invalid fact status")
        if not (0.0 <= confidence <= 1.0):
            raise ValidationError("fact confidence must be 0..1")
        if status == "confirmed":
            raise ValidationError("confirmed facts require owner confirmation")
        fact_id = _new_id("fact_")
        with self.tx(immediate=True):
            self.conn.execute(
                "INSERT INTO memory_facts(id, project_id, subject, predicate, object, confidence, "
                "provenance, status, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    fact_id,
                    self.project_id,
                    redact_text(subject)[:500],
                    redact_text(predicate)[:200],
                    redact_text(obj)[:4000],
                    float(confidence),
                    redact_text(provenance)[:1000],
                    status,
                    utc_now(),
                ),
            )
        return fact_id

    def confirm_fact(self, fact_id: str, decided_by: str = "owner") -> None:
        if decided_by != "owner":
            raise ValidationError("only the owner can confirm a fact")
        with self.tx(immediate=True):
            self.conn.execute(
                "UPDATE memory_facts SET status='confirmed' WHERE id=? AND project_id=?",
                (fact_id, self.project_id),
            )

    def list_facts(self, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM memory_facts WHERE project_id=? AND status=? ORDER BY created_at DESC",
                (self.project_id, status),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM memory_facts WHERE project_id=? ORDER BY created_at DESC",
                (self.project_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- graph -------------------------------------------------------------
    def add_edge(
        self, src: str, dst: str, kind: str, provenance: str, confidence: float = 1.0
    ) -> str:
        allowed = {
            "depends_on",
            "implements",
            "derived_from",
            "evaluated_by",
            "contradicts",
            "supersedes",
            "related_to",
        }
        if kind not in allowed:
            raise ValidationError("unknown graph edge kind")
        if not (0.0 <= confidence <= 1.0):
            raise ValidationError("edge confidence must be 0..1")
        edge_id = _new_id("edge_")
        with self.tx(immediate=True):
            self.conn.execute(
                "INSERT INTO graph_edges(id, project_id, src, dst, kind, provenance, confidence, "
                "created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    edge_id,
                    self.project_id,
                    redact_text(src)[:500],
                    redact_text(dst)[:500],
                    kind,
                    redact_text(provenance)[:1000],
                    float(confidence),
                    utc_now(),
                ),
            )
        return edge_id

    def list_edges(self, kind: str | None = None) -> list[dict[str, Any]]:
        if kind:
            rows = self.conn.execute(
                "SELECT * FROM graph_edges WHERE project_id=? AND kind=? ORDER BY created_at",
                (self.project_id, kind),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM graph_edges WHERE project_id=? ORDER BY created_at",
                (self.project_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- checkpoints / notifications / status ------------------------------
    def save_checkpoint(self, payload: Mapping[str, Any]) -> str:
        latest = self.latest_contract()
        revision = latest[0]["revision"] if latest else 0
        text, _ = dump_bounded(dict(payload), max_bytes=128 * 1024)
        checkpoint_id = _new_id("ckpt_")
        with self.tx(immediate=True):
            self.conn.execute(
                "INSERT INTO checkpoints(id, project_id, contract_revision, payload, created_at) "
                "VALUES(?,?,?,?,?)",
                (checkpoint_id, self.project_id, int(revision), text, utc_now()),
            )
        return checkpoint_id

    def latest_checkpoint(self) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM checkpoints WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
            (self.project_id,),
        ).fetchone()
        if not row:
            return None
        data = bounded_json_loads(row["payload"], max_bytes=128 * 1024)
        return {**dict(row), "payload": data}

    def notify(self, severity: str, dedupe_key: str, message: str) -> str | None:
        if severity not in {"info", "warning", "critical"}:
            raise ValidationError("invalid notification severity")
        with self.tx(immediate=True):
            existing = self.conn.execute(
                "SELECT id FROM notifications WHERE project_id=? AND dedupe_key=? AND status='open'",
                (self.project_id, dedupe_key),
            ).fetchone()
            if existing:
                return None
            notification_id = _new_id("ntf_")
            self.conn.execute(
                "INSERT INTO notifications(id, project_id, severity, dedupe_key, message, status, "
                "created_at) VALUES(?,?,?,?,?, 'open', ?)",
                (
                    notification_id,
                    self.project_id,
                    severity,
                    dedupe_key,
                    redact_text(message)[:2000],
                    utc_now(),
                ),
            )
        return notification_id

    def list_notifications(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM notifications WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
            (self.project_id, min(limit, 1000)),
        ).fetchall()
        return [dict(r) for r in rows]

    def status_summary(self) -> dict[str, Any]:
        project = self.get_project()
        latest = self.latest_contract()
        findings = self.finding_counts()
        investigations = self.investigation_counts()
        try:
            proposals = self.proposal_counts()
        except sqlite3.OperationalError:
            proposals = {}
        evidence_rows = self.conn.execute(
            "SELECT outcome, COUNT(*) AS n FROM evidence WHERE project_id=? GROUP BY outcome",
            (self.project_id,),
        ).fetchall()
        return {
            "project": {
                "id": project["id"],
                "name": project["name"],
                "root": project["root"],
                "status": project["status"],
            },
            "contract": {
                "revision": latest[0]["revision"] if latest else None,
                "hash": latest[0]["hash"] if latest else None,
                "domains": list(latest[1].domains) if latest else [],
                "unsupported_domains": list(latest[1].unsupported_domains) if latest else [],
            },
            "findings": findings,
            "investigations": investigations,
            "proposals": proposals,
            "evidence": {str(r["outcome"]): int(r["n"]) for r in evidence_rows},
            "budgets": self.budget_status(),
            "model_calls_spent": self.model_calls_spent(),
            "fts_available": self.fts_available,
            "as_of": utc_now(),
        }


@dataclass
class Claim:
    id: str
    token: str
    generation: int
    attempts: int
    max_attempts: int
    title: str
    hypothesis: str
    domain: str
    payload: dict[str, Any]
    worker: str

