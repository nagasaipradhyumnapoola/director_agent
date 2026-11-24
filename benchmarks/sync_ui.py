"""Copy the skill-matrix summary into the control-room demo data."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISPLAY = {
    "direct": "Direct model",
    "headroom": "Headroom",
    "ponytail": "Ponytail",
    "superpowers": "Superpowers",
    "ecc": "ECC",
    "ui_ux": "ui-ux-pro-max",
    "director": "DIRECTOR",
}
KIND = {
    "direct": "baseline",
    "headroom": "compression",
    "ponytail": "simplicity",
    "superpowers": "procedure",
    "ecc": "catalog",
    "ui_ux": "design",
    "director": "supervisor",
}


def main() -> int:
    matrix_path = ROOT / "benchmarks" / "results" / "skill_matrix.json"
    data_path = ROOT / "web" / "data.json"
    if not matrix_path.is_file():
        raise SystemExit("run benchmarks/skill_matrix.py first")
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    data = json.loads(data_path.read_text(encoding="utf-8"))
    summary = matrix["summary"]
    individual_path = ROOT / "benchmarks" / "results" / "skill_individual.json"
    best_at: dict[str, list[str]] = {}
    if individual_path.is_file():
        individual = json.loads(individual_path.read_text(encoding="utf-8"))
        best_at = individual.get("best_at", {})
    rows = []
    for tool, row in sorted(summary.items(), key=lambda item: -item[1]["overall"]):
        rows.append(
            {
                "tool": DISPLAY.get(tool, tool),
                "kind": KIND.get(tool, "procedure"),
                "best_at": best_at.get(tool, []),
                "scores": [
                    round(row["coding_rate"] * 100),
                    row["output_tokens"],
                    round(row["clarity"] * 100),
                    round(row["design"] * 100),
                    round(row["context_retention"] * 100),
                    round(row["selfdev_rate"] * 100),
                ],
            }
        )
    data["skill_matrix"] = {
        "status": "complete",
        "note": f"Prompt-level ablation · {matrix['meta']['model']} · {matrix['meta']['seeds']} seed(s) · {matrix['meta']['total_seconds']}s. Upstream runtimes not executed.",
        "metrics": ["coding", "tokens", "clarity", "design", "context", "self-improve"],
        "rows": rows,
    }
    data_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"updated {data_path} with {len(rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
