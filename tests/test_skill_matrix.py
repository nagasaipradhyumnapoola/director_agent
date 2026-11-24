from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location("bench_skill_matrix", ROOT / "benchmarks" / "skill_matrix.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skill_matrix_self_test_passes():
    assert _module().self_test() == 0


def test_matrix_rubrics_reject_empty_artifacts():
    matrix = _module()
    tasks = matrix.tasks
    assert tasks.design_rubric("")["score"] < 0.2
    assert tasks.clarity_rubric("")["score"] < 0.3
    assert tasks.context_rubric("")["retention"] == 0.0


def test_matrix_extracts_unclosed_fences():
    matrix = _module()
    text = "```python\ndef add(a, b):\n    return a + b\n"
    assert "return a + b" in matrix.tasks.extract_code(text)
