"""Small CPU ML pilot evaluator: manifest, leakage, held-out, reproducibility."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import sys
from pathlib import Path
from typing import Any

from ..security import (
    BoundsError,
    PathSafetyError,
    ValidationError,
    bounded_json_loads,
    dump_bounded,
    ensure_within,
    normalise_whitespace,
    safe_read_bytes,
)
from .base import Check, DomainResult, FindingDraft, PilotContext, PROFILES

EVALUATOR_VERSION = "ml-evaluator/1.0"
TRUSTED_HELDOUT_MARGIN = 0.10
TRUSTED_MIN_TEST_ACCURACY = 0.75
TRUSTED_MIN_SLICE_ACCURACY = 0.55
MAX_ROWS = 10_000
_SUSPICIOUS = ("target", "label", "leak", "outcome", "future", "y_", "ground_truth")


def _read_bytes(ctx: PilotContext, rel: str, max_bytes: int = 4 * 1024 * 1024) -> bytes:
    target = ensure_within(ctx.fixture_path / rel, Path(ctx.store.root))
    return safe_read_bytes(target, Path(ctx.store.root), max_bytes=max_bytes)


def _read_json(ctx: PilotContext, rel: str) -> Any:
    return bounded_json_loads(_read_bytes(ctx, rel, 2 * 1024 * 1024), max_bytes=2 * 1024 * 1024)


def _assign_split(seed: int, row_id: str, spec: dict[str, Any]) -> str:
    digest = hashlib.sha256(f"{seed}:{row_id}".encode("utf-8")).hexdigest()
    position = int(digest[:16], 16) / float(1 << 64)
    train = float(spec.get("train", 0.7))
    validation = float(spec.get("validation", 0.15))
    if position < train:
        return "train"
    if position < train + validation:
        return "validation"
    return "test"


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 1e-12 or vy <= 1e-12:
        return 0.0
    return cov / math.sqrt(vx * vy)


def _rows(data: bytes, features: list[str], label: str) -> list[dict[str, Any]]:
    text = data.decode("utf-8", "replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValidationError("dataset has no header")
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(reader):
        if index >= MAX_ROWS:
            raise ValidationError("dataset exceeds row bound")
        values = []
        for feature in features:
            try:
                number = float(raw.get(feature, ""))
            except (TypeError, ValueError):
                number = None
            if number is None or not math.isfinite(number):
                values = []
                break
            values.append(number)
        try:
            y = float(raw.get(label, ""))
        except (TypeError, ValueError):
            continue
        if not values or y not in (0.0, 1.0):
            continue
        row_id = str(raw.get("id", f"row-{index}"))
        rows.append({"id": row_id, "x": values, "y": int(y)})
    return rows


def _leakage(rows: list[dict[str, Any]], features: list[str], spec: dict[str, Any], seed: int) -> dict[str, Any]:
    by_split: dict[str, list[dict[str, Any]]] = {"train": [], "validation": [], "test": []}
    for row in rows:
        by_split[_assign_split(seed, row["id"], spec)].append(row)
    train = by_split["train"]
    heldout = by_split["validation"] + by_split["test"]
    train_keys = {tuple(round(v, 6) for v in row["x"]) for row in train}
    duplicates = sum(1 for row in heldout if tuple(round(v, 6) for v in row["x"]) in train_keys)
    train_ids = {row["id"] for row in train}
    duplicate_ids = sum(1 for row in heldout if row["id"] in train_ids)
    derived: list[dict[str, Any]] = []
    labels = [row["y"] for row in rows]
    for index, feature in enumerate(features):
        values = [row["x"][index] for row in rows]
        corr = abs(_pearson(values, labels))
        name = feature.lower()
        suspicious_name = any(token in name for token in _SUSPICIOUS)
        if corr >= 0.999 or (suspicious_name and corr >= 0.95):
            derived.append({"feature": feature, "abs_correlation": round(corr, 6)})
    exact_copy = sum(
        1 for row in rows if len(features) > 1 and all(abs(v - row["y"]) < 1e-9 for v in row["x"])
    )
    return {
        "splits": {name: len(value) for name, value in by_split.items()},
        "duplicate_feature_rows_across_splits": duplicates,
        "duplicate_ids_across_splits": duplicate_ids,
        "target_derived_features": derived,
        "rows_equal_to_label": exact_copy,
    }


def _manifest_issues(manifest: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    dataset = manifest.get("dataset")
    if not isinstance(dataset, dict):
        return ["manifest.dataset missing or invalid"]
    for key in ("name", "source", "license", "rights", "collected", "intended_use"):
        value = dataset.get(key)
        if not isinstance(value, str) or not value.strip():
            issues.append(f"dataset.{key} missing")
    if not isinstance(manifest.get("features"), list) or not manifest["features"]:
        issues.append("manifest.features missing")
    if not isinstance(manifest.get("split"), dict):
        issues.append("manifest.split missing")
    if not isinstance(manifest.get("label"), str):
        issues.append("manifest.label missing")
    if isinstance(dataset.get("source"), str) and dataset["source"].lower().startswith("http"):
        issues.append("dataset.source is a URL; provenance file required")
    return issues


def evaluate(ctx: PilotContext) -> DomainResult:
    residual = safe_read_bytes(
        ensure_within(ctx.fixture_path / "manifest.json", Path(ctx.store.root)),
        Path(ctx.store.root),
        max_bytes=2 * 1024 * 1024,
    )
    manifest = bounded_json_loads(residual, max_bytes=2 * 1024 * 1024)
    config = _read_json(ctx, "run_config.json")
    if not isinstance(manifest, dict) or not isinstance(config, dict):
        return DomainResult(status="error", blocked_reason="manifest/config must be objects")
    features = [str(f) for f in manifest.get("features", []) if isinstance(f, str)]
    label = str(manifest.get("label", "label"))
    dataset_bytes = _read_bytes(ctx, "data.csv", max_bytes=8 * 1024 * 1024)
    dataset_sha = hashlib.sha256(dataset_bytes).hexdigest()
    rows = _rows(dataset_bytes, features, label)
    checks: list[Check] = []
    findings: list[FindingDraft] = []
    limitations = [
        "Synthetic controlled fixture; results do not establish production model quality.",
        "Acceptance thresholds come from DIRECTOR profile constants, not fixture config.",
        "Trainer runs with -I -P so fixture files cannot shadow stdlib imports.",
        "Pure-Python CPU baseline, not a deployment artifact.",
        "Two identical runs test local determinism only, not cross-platform reproducibility.",
    ]

    issues = _manifest_issues(manifest)
    checks.append(
        Check(
            criterion_key="ml.manifest",
            description="dataset manifest, provenance, rights and split spec are complete",
            passed=not issues,
            details={"issues": issues, "dataset_sha256": dataset_sha, "rows": len(rows)},
            subject_path=f"{ctx.fixture_rel}/manifest.json",
            subject_sha256=ctx.fixture_sha,
            limitations="manifest completeness does not establish data quality",
        )
    )
    for issue in issues:
        findings.append(
            FindingDraft(
                severity="high",
                kind="ml_manifest_incomplete",
                message=f"ML manifest issue: {issue}",
                path=f"{ctx.fixture_rel}/manifest.json",
                source_sha256=ctx.fixture_sha,
            )
        )

    spec = dict(config.get("split") or manifest.get("split") or {})
    seed = int(config.get("seed", spec.get("seed", 0)))
    leakage = _leakage(rows, features, spec, seed)
    leak_passed = (
        leakage["duplicate_feature_rows_across_splits"] == 0
        and leakage["duplicate_ids_across_splits"] == 0
        and not leakage["target_derived_features"]
    )
    checks.append(
        Check(
            criterion_key="ml.leakage",
            description="no train/held-out duplication and no target-derived feature",
            passed=leak_passed,
            details=leakage,
            subject_path=f"{ctx.fixture_rel}/data.csv",
            subject_sha256=dataset_sha,
            confidence=0.85,
            limitations="heuristic detection; not proof of absence of subtler leakage",
        )
    )
    if leakage["duplicate_feature_rows_across_splits"]:
        findings.append(
            FindingDraft(
                severity="critical",
                kind="ml_split_leak",
                message=(
                    f"{leakage['duplicate_feature_rows_across_splits']} held-out rows duplicate "
                    "training feature vectors"
                ),
                path=f"{ctx.fixture_rel}/data.csv",
                source_sha256=dataset_sha,
            )
        )
    if leakage["target_derived_features"]:
        names = ", ".join(item["feature"] for item in leakage["target_derived_features"])
        findings.append(
            FindingDraft(
                severity="critical",
                kind="ml_target_leak",
                message=f"target-derived feature(s) detected: {names}",
                path=f"{ctx.fixture_rel}/data.csv",
                source_sha256=dataset_sha,
            )
        )
    if leakage["duplicate_ids_across_splits"]:
        findings.append(
            FindingDraft(
                severity="high",
                kind="ml_id_leak",
                message=f"{leakage['duplicate_ids_across_splits']} ids appear in both train and held-out",
                path=f"{ctx.fixture_rel}/data.csv",
                source_sha256=dataset_sha,
            )
        )

    trainer = Path(__file__).resolve().parent.parent / "assets" / "train_logistic.py"
    workspace = ctx.create_workspace()
    metrics1: dict[str, Any] | None = None
    metrics2: dict[str, Any] | None = None
    run_resources: dict[str, Any] = {}
    trainer_error: str | None = None
    try:
        workspace.copy_tree(ctx.fixture_path, "data")
        workspace.copy_file(trainer, "trainer/train_logistic.py")
        for attempt in (1, 2):
            result = ctx.runner.run(
                [sys.executable, "-I", "-P", str(workspace.path("trainer/train_logistic.py"))],
                workspace,
                timeout=min(ctx.timeout_seconds, 120.0),
                max_output=256 * 1024,
                memory_mb=1024,
                cpu_seconds=60,
                cwd_rel="data",
            )
            run_resources[f"run{attempt}"] = result.to_dict()
            if not result.ok:
                trainer_error = result.error or ("timeout" if result.timed_out else f"exit {result.exit_code}")
                break
            try:
                metrics_bytes = safe_read_bytes(
                    workspace.path("data/metrics.json"), workspace.root, max_bytes=4 * 1024 * 1024
                )
                parsed = bounded_json_loads(metrics_bytes, max_bytes=4 * 1024 * 1024)
            except (PathSafetyError, BoundsError, ValidationError, OSError) as exc:
                trainer_error = f"metrics unreadable: {type(exc).__name__}"
                break
            if attempt == 1:
                metrics1 = parsed
            else:
                metrics2 = parsed
    finally:
        workspace.cleanup()

    if trainer_error or not isinstance(metrics1, dict):
        findings.append(
            FindingDraft(
                severity="high",
                kind="ml_trainer_error",
                message=f"training/evaluation run failed: {trainer_error or 'no metrics'}",
                path=f"{ctx.fixture_rel}/run_config.json",
                source_sha256=ctx.fixture_sha,
                limitations="no held-out metric is available",
            )
        )
        for key, description in (
            ("ml.heldout", "held-out metric beats baseline threshold"),
            ("ml.reproducible", "two runs agree"),
            ("ml.slices", "slice metrics are adequate"),
            ("ml.resources", "resource report recorded"),
        ):
            checks.append(
                Check(
                    criterion_key=key,
                    description=description,
                    passed=False,
                    outcome="blocked",
                    details={"reason": trainer_error or "no metrics"},
                    subject_path=ctx.fixture_rel,
                    subject_sha256=ctx.fixture_sha,
                    limitations="training run failed",
                )
            )
        return DomainResult(
            status="error",
            checks=checks,
            findings=findings,
            limitations=limitations,
            resources=run_resources,
            blocked_reason="training run failed",
        )

    test_metrics = metrics1.get("test") or {}
    baseline = float(metrics1.get("baseline_majority_accuracy", 0.0))
    declared_acceptance = config.get("acceptance") or {}
    margin = TRUSTED_HELDOUT_MARGIN
    minimum = TRUSTED_MIN_TEST_ACCURACY
    accuracy = float(test_metrics.get("accuracy", 0.0))
    threshold = max(baseline + margin, minimum)
    heldout_pass = bool(test_metrics.get("n")) and accuracy >= threshold
    checks.append(
        Check(
            criterion_key="ml.heldout",
            description="held-out accuracy beats the majority baseline by the configured margin",
            passed=heldout_pass,
            details={
                "test_accuracy": accuracy,
                "baseline": baseline,
                "threshold": round(threshold, 6),
                "test": test_metrics,
                "validation": metrics1.get("validation"),
                "trusted_threshold_source": "director profile constants",
                "fixture_declared_acceptance": declared_acceptance,
            },
            subject_path=f"{ctx.fixture_rel}/data.csv",
            subject_sha256=dataset_sha,
            confidence=0.9,
            limitations="single small synthetic split; no confidence interval",
        )
    )
    if not heldout_pass:
        findings.append(
            FindingDraft(
                severity="high",
                kind="ml_heldout_underperforms",
                message=f"held-out accuracy {accuracy:.3f} is below threshold {threshold:.3f}",
                path=f"{ctx.fixture_rel}/data.csv",
                source_sha256=dataset_sha,
            )
        )

    reproducible = bool(
        metrics2
        and metrics1.get("weights_hash") == metrics2.get("weights_hash")
        and (metrics1.get("test") or {}).get("accuracy") == (metrics2.get("test") or {}).get("accuracy")
        and metrics1.get("split_counts") == metrics2.get("split_counts")
    )
    checks.append(
        Check(
            criterion_key="ml.reproducible",
            description="two identical runs produce the same weights hash and held-out accuracy",
            passed=reproducible,
            details={
                "run1_weights_hash": metrics1.get("weights_hash"),
                "run2_weights_hash": (metrics2 or {}).get("weights_hash"),
                "run1_test_accuracy": (metrics1.get("test") or {}).get("accuracy"),
                "run2_test_accuracy": ((metrics2 or {}).get("test") or {}).get("accuracy"),
                "seed": metrics1.get("seed"),
            },
            subject_path=f"{ctx.fixture_rel}/run_config.json",
            subject_sha256=ctx.fixture_sha,
            confidence=0.9,
            limitations="local repeatability only; cross-platform reproducibility not tested",
        )
    )
    if not reproducible:
        findings.append(
            FindingDraft(
                severity="high",
                kind="ml_nondeterministic",
                message="two identical runs did not agree on weights/accuracy",
                path=f"{ctx.fixture_rel}/run_config.json",
                source_sha256=ctx.fixture_sha,
            )
        )

    min_slice = TRUSTED_MIN_SLICE_ACCURACY
    slices = metrics1.get("slices") or {}
    weak = [
        name
        for name, data in slices.items()
        if not data.get("low_support") and float(data.get("accuracy", 0.0)) < min_slice
    ]
    checks.append(
        Check(
            criterion_key="ml.slices",
            description="reported test slices meet the minimum accuracy",
            passed=bool(slices) and not weak,
            details={"slices": slices, "weak_slices": weak, "minimum": min_slice},
            subject_path=f"{ctx.fixture_rel}/data.csv",
            subject_sha256=dataset_sha,
            confidence=0.75,
            limitations="fixture slices are coarse and may be imbalanced",
        )
    )
    for name in weak:
        findings.append(
            FindingDraft(
                severity="medium",
                kind="ml_weak_slice",
                message=f"slice '{name}' accuracy below {min_slice:.2f}",
                path=f"{ctx.fixture_rel}/data.csv",
                source_sha256=dataset_sha,
            )
        )

    resources_ok = bool(metrics1.get("peak_memory_bytes") is not None and metrics1.get("runtime_seconds"))
    checks.append(
        Check(
            criterion_key="ml.resources",
            description="resource and environment report recorded",
            passed=resources_ok,
            details={
                "runtime_seconds": metrics1.get("runtime_seconds"),
                "peak_memory_bytes": metrics1.get("peak_memory_bytes"),
                "environment": metrics1.get("environment"),
                "runner": run_resources,
            },
            subject_path=f"{ctx.fixture_rel}/run_config.json",
            subject_sha256=ctx.fixture_sha,
            limitations="runner peak memory is unknown; child tracemalloc value is reported",
        )
    )

    status = "pass" if all(check.passed for check in checks) else "fail"
    report, _ = dump_bounded(
        {
            "manifest": manifest,
            "config": config,
            "metrics_run1": metrics1,
            "leakage": leakage,
            "runs": run_resources,
        },
        max_bytes=256 * 1024,
    )
    return DomainResult(
        status=status,
        checks=checks,
        findings=findings,
        limitations=limitations,
        resources=run_resources,
        report=json.loads(report),
    )


