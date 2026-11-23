#!/usr/bin/env python3
"""Deterministic small CPU logistic-regression pilot trainer (stdlib only).

Reads manifest.json, run_config.json and data.csv from the current directory and
writes metrics.json. This is a fixture-scale baseline, not a deployment model.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import time
import tracemalloc
from pathlib import Path

MAX_ROWS = 10_000
MAX_FEATURES = 20


def sigmoid(z: float) -> float:
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def as_float(value: str) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def split_name(seed: int, row_id: str, spec: dict) -> str:
    digest = hashlib.sha256(f"{seed}:{row_id}".encode("utf-8")).hexdigest()
    position = int(digest[:16], 16) / float(1 << 64)
    if position < float(spec.get("train", 0.7)):
        return "train"
    if position < float(spec.get("train", 0.7)) + float(spec.get("validation", 0.15)):
        return "validation"
    return "test"


def value_of(row: dict, features: list[str]) -> list[float] | None:
    out = []
    for feature in features:
        number = as_float(row.get(feature, ""))
        if number is None:
            return None
        out.append(number)
    return out


def metrics_for(rows, features, label_col, mean, std, weights, bias) -> dict:
    if not rows:
        return {"n": 0, "accuracy": 0.0, "log_loss": 0.0, "confusion": {}}
    correct = 0
    loss = 0.0
    tp = fp = tn = fn = 0
    for row in rows:
        x = [(row[f] - mean[i]) / std[i] for i, f in enumerate(features)]
        z = bias + sum(w * xi for w, xi in zip(weights, x))
        p = sigmoid(z)
        label = row[label_col]
        pred = 1 if p >= 0.5 else 0
        if pred == label:
            correct += 1
        loss -= label * math.log(max(p, 1e-12)) + (1 - label) * math.log(max(1 - p, 1e-12))
        if pred == 1 and label == 1:
            tp += 1
        elif pred == 1 and label == 0:
            fp += 1
        elif pred == 0 and label == 0:
            tn += 1
        else:
            fn += 1
    n = len(rows)
    return {
        "n": n,
        "accuracy": round(correct / n, 6),
        "log_loss": round(loss / n, 6),
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
    }


def main() -> int:
    started = time.time()
    tracemalloc.start()
    config = json.loads(Path("run_config.json").read_text(encoding="utf-8"))
    manifest = json.loads(Path("manifest.json").read_text(encoding="utf-8"))
    features = list(manifest.get("features", []))
    if not features or len(features) > MAX_FEATURES:
        raise SystemExit("invalid feature list")
    label_col = str(manifest.get("label", "label"))
    group_col = str(manifest.get("group", "group"))
    spec = dict(config.get("split") or manifest.get("split") or {})
    seed = int(config.get("seed", spec.get("seed", 1234)))
    lr = float(config.get("learning_rate", 0.2))
    epochs = int(config.get("epochs", 400))
    l2 = float(config.get("l2", 0.0))
    if not (0.0 < lr < 10.0) or not (1 <= epochs <= 20_000) or not (0.0 <= l2 < 1.0):
        raise SystemExit("invalid training configuration")

    raw = Path("data.csv").read_bytes()
    dataset_sha = hashlib.sha256(raw).hexdigest()
    rows: list[dict] = []
    with Path("data.csv").open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or label_col not in reader.fieldnames:
            raise SystemExit("missing label column")
        if group_col not in (reader.fieldnames or []):
            group_col = ""
        for index, raw_row in enumerate(reader):
            if index >= MAX_ROWS:
                raise SystemExit("too many rows")
            vector = value_of(raw_row, features)
            label = as_float(raw_row.get(label_col, ""))
            if vector is None or label not in (0.0, 1.0):
                continue
            row = {feature: vector[i] for i, feature in enumerate(features)}
            row[label_col] = int(label)
            row["__id"] = str(raw_row.get("id", f"row-{index}"))
            row["__group"] = str(raw_row.get(group_col, "")) if group_col else ""
            rows.append(row)
    if len(rows) < 30:
        raise SystemExit("not enough valid rows")

    splits = {"train": [], "validation": [], "test": []}
    for row in rows:
        splits[split_name(seed, row["__id"], spec)].append(row)

    mean = [0.0] * len(features)
    std = [1.0] * len(features)
    if not splits["train"]:
        raise SystemExit("empty train split")
    for i, feature in enumerate(features):
        values = [row[feature] for row in splits["train"]]
        mean[i] = sum(values) / len(values)
        variance = sum((v - mean[i]) ** 2 for v in values) / len(values)
        std[i] = math.sqrt(variance) or 1.0

    train = [
        ([(row[f] - mean[i]) / std[i] for i, f in enumerate(features)], row[label_col])
        for row in splits["train"]
    ]
    weights = [0.0] * len(features)
    bias = 0.0
    for _epoch in range(epochs):
        grad_w = [0.0] * len(features)
        grad_b = 0.0
        for x, y in train:
            z = bias + sum(w * xi for w, xi in zip(weights, x))
            error = sigmoid(z) - y
            for j, xi in enumerate(x):
                grad_w[j] += error * xi
            grad_b += error
        n = len(train)
        for j in range(len(weights)):
            weights[j] -= lr * (grad_w[j] / n + l2 * weights[j])
        bias -= lr * grad_b / n

    test_metrics = metrics_for(splits["test"], features, label_col, mean, std, weights, bias)
    validation_metrics = metrics_for(splits["validation"], features, label_col, mean, std, weights, bias)
    train_metrics = metrics_for(splits["train"], features, label_col, mean, std, weights, bias)
    if not splits["test"]:
        raise SystemExit("empty test split")

    labels = [row[label_col] for row in splits["test"]]
    baseline = max(labels.count(0), labels.count(1)) / len(labels)
    slices = {}
    if group_col:
        groups: dict[str, list] = {}
        for row in splits["test"]:
            groups.setdefault(row["__group"], []).append(row)
        for name, group_rows in sorted(groups.items()):
            slices[name] = metrics_for(group_rows, features, label_col, mean, std, weights, bias)
            slices[name]["low_support"] = len(group_rows) < 20
    by_label = {}
    for value in (0, 1):
        subset = [row for row in splits["test"] if row[label_col] == value]
        by_label[str(value)] = metrics_for(subset, features, label_col, mean, std, weights, bias)

    weights_hash = hashlib.sha256(
        json.dumps(
            {"weights": [round(w, 8) for w in weights], "bias": round(bias, 8)},
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    current, peak = tracemalloc.get_traced_memory()
    metrics = {
        "schema": "director.ml.metrics.v1",
        "dataset_sha256": dataset_sha,
        "seed": seed,
        "config": {
            "model": config.get("model", "logistic_regression"),
            "learning_rate": lr,
            "epochs": epochs,
            "l2": l2,
            "features": features,
        },
        "rows": len(rows),
        "split_counts": {name: len(value) for name, value in splits.items()},
        "train": train_metrics,
        "validation": validation_metrics,
        "test": test_metrics,
        "baseline_majority_accuracy": round(baseline, 6),
        "slices": slices,
        "by_label": by_label,
        "weights_hash": weights_hash,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
        },
        "runtime_seconds": round(time.time() - started, 4),
        "peak_memory_bytes": int(peak),
        "determinism_notes": [
            "zero initialisation, fixed row order, no default randomness",
            "cross-platform floats can differ at low-order bits",
        ],
    }
    Path("metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
