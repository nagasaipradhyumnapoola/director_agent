"""Tasks, tests and deterministic rubrics for the skill-matrix benchmark.

The benchmark is prompt-level: each tool is represented by a procedure file in
``benchmarks/skills`` and gets the identical task prompt, model and seed. It does
not claim to execute the upstream runtime or its hooks.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def read_skill(name: str) -> str:
    path = SKILLS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8").strip()


SLUGIFY_TEST = r'''
import os, sys, unittest
sys.path.insert(0, os.path.dirname(__file__))
from solution import slugify

class T(unittest.TestCase):
    def test_basic(self): self.assertEqual(slugify("Hello World"), "hello-world")
    def test_spaces(self): self.assertEqual(slugify("  A  B  "), "a-b")
    def test_unicode(self): self.assertEqual(slugify("Café déjà vu"), "cafe-deja-vu")
    def test_punctuation(self): self.assertEqual(slugify("Hello, World!"), "hello-world")
    def test_empty(self): self.assertEqual(slugify(""), "")
    def test_separators(self): self.assertEqual(slugify("---"), "")
    def test_truncate(self): self.assertEqual(slugify("A" * 100, max_length=10), "a" * 10)
    def test_truncate_hyphen(self): self.assertEqual(slugify("Hello World", max_length=8), "hello")
    def test_sharp_s(self): self.assertEqual(slugify("Straße"), "strasse")
    def test_umlaut(self): self.assertEqual(slugify("Über"), "uber")

if __name__ == "__main__":
    unittest.main(verbosity=0)
'''

DURATION_TEST = r'''
import os, sys, unittest
sys.path.insert(0, os.path.dirname(__file__))
from solution import parse_duration

class T(unittest.TestCase):
    def test_hours_minutes(self): self.assertEqual(parse_duration("1h30m"), 5400)
    def test_seconds(self): self.assertEqual(parse_duration("45s"), 45)
    def test_hours(self): self.assertEqual(parse_duration("2h"), 7200)
    def test_minutes(self): self.assertEqual(parse_duration("90m"), 5400)
    def test_mixed(self): self.assertEqual(parse_duration("1h 5m 10s"), 3910)
    def test_days(self): self.assertEqual(parse_duration("1d2h"), 93600)
    def test_bare(self): self.assertEqual(parse_duration("10"), 10)
    def test_case_space(self): self.assertEqual(parse_duration(" 1H 30M "), 5400)
    def test_empty(self):
        with self.assertRaises(ValueError): parse_duration("")
    def test_unknown(self):
        with self.assertRaises(ValueError): parse_duration("1x")
    def test_duplicate(self):
        with self.assertRaises(ValueError): parse_duration("1h1h")
    def test_order(self):
        with self.assertRaises(ValueError): parse_duration("1m1h")
    def test_negative(self):
        with self.assertRaises(ValueError): parse_duration("-1h")

if __name__ == "__main__":
    unittest.main(verbosity=0)
'''

INTERVAL_TEST = r'''
import os, sys, unittest
sys.path.insert(0, os.path.dirname(__file__))
from solution import merge_intervals

class T(unittest.TestCase):
    def test_merge(self): self.assertEqual(merge_intervals([(1,3),(2,6),(8,10),(15,18)]), [(1,6),(8,10),(15,18)])
    def test_touch(self): self.assertEqual(merge_intervals([(1,4),(4,5)]), [(1,5)])
    def test_sort(self): self.assertEqual(merge_intervals([(5,6),(1,2)]), [(1,2),(5,6)])
    def test_empty(self): self.assertEqual(merge_intervals([]), [])
    def test_point(self): self.assertEqual(merge_intervals([(1,1)]), [(1,1)])
    def test_disjoint(self): self.assertEqual(merge_intervals([(1,2),(3,4)]), [(1,2),(3,4)])
    def test_contained(self): self.assertEqual(merge_intervals([(1,5),(2,3)]), [(1,5)])
    def test_invalid(self):
        with self.assertRaises(ValueError): merge_intervals([(5,1)])
    def test_large(self): self.assertEqual(merge_intervals([(10**12,10**12+5),(10**12+5,10**12+9)]), [(10**12,10**12+9)])

if __name__ == "__main__":
    unittest.main(verbosity=0)
'''

DESIGN_PROMPT = """Create a single self-contained `index.html` for a "release readiness" card.
Requirements:
- semantic <main>, exactly one <h1>, a status summary, at least 3 evidence rows, one primary button
- design tokens via CSS custom properties, dark theme, brass accent
- visible :focus-visible styles; primary button at least 44px tall
- prefers-reduced-motion support
- responsive at 320px with no horizontal scroll
- inline SVG icons only; no emoji as structural icons
- no external assets, fonts, scripts or network requests
Return only a fenced ```html block."""


def _strip_fence(text: str) -> str:
    match = re.search(r"```(?:html|css|python|text|diff|markdown|md)?\s*\n(.*?)```", text, re.S | re.I)
    return match.group(1) if match else text


def _open_fence(text: str, languages: str) -> str | None:
    match = re.search(rf"```(?:{languages})?\s*\n", text, re.I)
    if not match:
        return None
    body = text[match.end():]
    end = body.find("```")
    if end >= 0:
        body = body[:end]
    return body.strip()


def extract_code(text: str) -> str:
    fenced = _open_fence(text, "python|py")
    if fenced:
        return fenced + "\n"
    return _strip_fence(text).strip() + "\n"


def extract_html(text: str) -> str:
    fenced = _open_fence(text, "html")
    if fenced:
        return fenced + "\n"
    return _strip_fence(text).strip() + "\n"


def extract_diff(text: str) -> str:
    fenced = _open_fence(text, "diff")
    body = fenced if fenced else text
    start = body.find("diff --git")
    if start < 0:
        start = body.find("--- ")
    if start >= 0:
        body = body[start:]
    return body.strip() + "\n"


def _run(cmd: list[str], cwd: Path, timeout: int = 30) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    return proc.returncode, (proc.stdout + proc.stderr)[-4000:]


def run_python_task(code: str, test_source: str) -> dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="director-matrix-"))
    try:
        (tmp / "solution.py").write_text(code, encoding="utf-8")
        (tmp / "test_solution.py").write_text(test_source, encoding="utf-8")
        code_rc, output = _run([sys.executable, "-P", "test_solution.py"], tmp, timeout=30)
        return {"ok": code_rc == 0, "detail": output[-1200:], "score": 1.0 if code_rc == 0 else 0.0}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF]")


def design_rubric(html: str) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    low = html.lower()
    checks["doctype"] = "<!doctype html" in low
    checks["lang"] = bool(re.search(r"<html[^>]+lang=", low))
    checks["viewport"] = "name=\"viewport\"" in low or "name='viewport'" in low
    checks["main"] = "<main" in low
    checks["h1_once"] = low.count("<h1") == 1
    checks["focus_visible"] = ":focus-visible" in low
    checks["reduced_motion"] = "prefers-reduced-motion" in low
    checks["tokens"] = len(re.findall(r"--[a-z0-9-]+\s*:", low)) >= 6
    checks["responsive"] = bool(re.search(r"@media[^{]*max-width", low))
    checks["inline_svg"] = "<svg" in low
    checks["no_emoji"] = not EMOJI.search(html)
    checks["no_external"] = not re.search(r"(?:src|href)\s*=\s*[\"']https?://", low)
    checks["button_target"] = bool(
        re.search(r"(?:min-height|height)\s*:\s*(?:4[4-9]|[5-9]\d|\d{3,})px", low)
        or re.search(r"padding\s*:\s*(?:[1-9]\d*px|[1-9](?:\.\d+)?rem)", low)
    )
    checks["three_rows"] = len(re.findall(r"<li", low)) >= 3 or len(re.findall(r"class=\"[^\"]*row", low)) >= 3
    score = sum(checks.values())
    return {
        "ok": score >= 10,
        "score": round(score / len(checks), 4),
        "raw": score,
        "max": len(checks),
        "checks": checks,
        "detail": ", ".join(name for name, passed in checks.items() if not passed) or "all checks",
    }


CLARITY_PROMPT = """Explain when to use a git worktree versus a Docker container for running an untrusted coding patch.
Write 100-150 words. Include three concrete constraints covering filesystem, network and privilege.
Use plain text only. No marketing language. Return only the explanation."""

BANNED = ("revolutionary", "game-changing", "game changing", "seamless", "best-in-class", "unleash", "supercharge")


def clarity_rubric(text: str) -> dict[str, Any]:
    plain = _strip_fence(text).strip()
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'/-]*", plain)
    low = plain.lower()
    checks = {
        "length": 100 <= len(words) <= 160,
        "worktree": "worktree" in low,
        "container": "container" in low,
        "filesystem": "filesystem" in low or "file system" in low or "read-only" in low,
        "network": "network" in low,
        "privilege": "privilege" in low or "root" in low or "kernel" in low or "microvm" in low,
        "three_constraints": len(re.findall(r"(?m)^\s*(?:\d+[.)]|[-*])\s+\S", plain)) >= 3,
        "no_banned": not any(word in low for word in BANNED),
        "review": "review" in low or "owner" in low or "approval" in low,
        "no_code": "```" not in text,
    }
    score = sum(checks.values())
    return {
        "ok": score >= 8,
        "score": round(score / len(checks), 4),
        "raw": score,
        "max": len(checks),
        "checks": checks,
        "words": len(words),
        "detail": ", ".join(name for name, passed in checks.items() if not passed) or "all checks",
    }


CONTEXT_FACTS = [
    ("project", "ORBIT-7"),
    ("deadline", "2027-03-14"),
    ("budget", "$48,000"),
    ("owner", "Mira Chen"),
    ("repo", "orbit/ingest"),
    ("latency ceiling", "250ms"),
    ("p95 target", "180ms"),
    ("region", "eu-west-1"),
    ("dataset", "4.2M rows"),
    ("license", "CC-BY-4.0"),
    ("model", "qwen3.5:4b"),
    ("retry budget", "retry=3"),
    ("queue", "ingest-v2"),
    ("image", "python:3.12-slim"),
    ("mount", "read-only"),
    ("network", "network=none"),
    ("approver", "Dana Ruiz"),
    ("rollback tag", "orbit-2027.03.14"),
    ("evidence", "ev_9f3a"),
    ("tests", "85 tests"),
]


def build_context_brief() -> str:
    lines = [
        "PROJECT BRIEF — ORBIT-7 INGESTION RELEASE",
        "",
    ]
    for index, (label, value) in enumerate(CONTEXT_FACTS):
        lines.append(f"- {label}: {value}")
    lines += [
        "",
        "The ingestion release moves the batch pipeline onto the new queue while preserving",
        "the existing evidence contract. The owner has asked for a compact handoff that a",
        "new engineer can use without reading the whole brief.",
        "",
    ]
    filler = (
        "The working group reviewed the previous release, confirmed the scope and noted that "
        "the acceptance evidence must stay current. No new provider spend is approved. Any "
        "change to the queue or the image needs the approver's recorded decision. The team "
        "will re-run the offline checks after the change and attach the receipt."
    )
    for index in range(24):
        lines.append(f"Section {index + 1}. {filler}")
    return "\n".join(lines)


CONTEXT_BRIEF = build_context_brief()
CONTEXT_PROMPT = (
    "Compress the following brief into a context pack for the next engineer. "
    "Preserve every project identifier, number, date, path, constraint, owner, tag and open decision. "
    "Target at most 350 words. Use short labeled lines, no prose padding. Return only the pack.\n\n"
    + CONTEXT_BRIEF
)


def context_rubric(text: str) -> dict[str, Any]:
    low = text.lower()
    hits = [key for key, value in CONTEXT_FACTS if value.lower() in low]
    words = len(re.findall(r"\S+", text))
    input_words = len(re.findall(r"\S+", CONTEXT_BRIEF))
    retention = len(hits) / len(CONTEXT_FACTS)
    compression = max(0.0, 1 - words / input_words) if input_words else 0.0
    over = words > 450
    return {
        "ok": retention >= 0.9 and not over,
        "score": round(retention, 4),
        "retention": round(retention, 4),
        "compression": round(compression, 4),
        "words": words,
        "over_limit": over,
        "missing": [value for key, value in CONTEXT_FACTS if value.lower() not in low],
        "detail": f"{len(hits)}/{len(CONTEXT_FACTS)} facts; {words} words; compression {compression:.0%}",
    }


SELFDEV_PROMPT = """Fix the bug in this small git repository. Return a unified git diff only, no prose.
The diff will be applied with `git apply --recount` and the tests run.

FILE src/calc.py:
```python
def median(values):
    values = sorted(values)
    n = len(values)
    if n == 0:
        raise ValueError("empty")
    return values[n // 2]
```

FILE tests/test_calc.py:
```python
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from src.calc import median

class T(unittest.TestCase):
    def test_odd(self): self.assertEqual(median([3, 1, 2]), 2)
    def test_even(self): self.assertEqual(median([1, 2, 3, 4]), 2.5)
    def test_empty(self):
        with self.assertRaises(ValueError): median([])

if __name__ == "__main__":
    unittest.main(verbosity=0)
```

The even-length case is failing: median([1,2,3,4]) returns 3 instead of 2.5.
Keep the empty-list ValueError and the odd-length behavior. Return only the diff."""


def apply_selfdev(diff: str) -> dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="director-matrix-selfdev-"))
    try:
        (tmp / "src").mkdir()
        (tmp / "tests").mkdir()
        (tmp / "src" / "calc.py").write_text(
            "def median(values):\n"
            "    values = sorted(values)\n"
            "    n = len(values)\n"
            "    if n == 0:\n"
            "        raise ValueError(\"empty\")\n"
            "    return values[n // 2]\n",
            encoding="utf-8",
        )
        (tmp / "tests" / "test_calc.py").write_text(
            "import os, sys, unittest\n"
            "sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))\n"
            "from src.calc import median\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_odd(self): self.assertEqual(median([3, 1, 2]), 2)\n"
            "    def test_even(self): self.assertEqual(median([1, 2, 3, 4]), 2.5)\n"
            "    def test_empty(self):\n"
            "        with self.assertRaises(ValueError): median([])\n\n"
            "if __name__ == \"__main__\":\n"
            "    unittest.main(verbosity=0)\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Bench"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.email", "bench@example.invalid"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=tmp, capture_output=True)
        (tmp / "change.diff").write_text(diff, encoding="utf-8")
        apply_rc, apply_out = _run(["git", "apply", "--recount", "change.diff"], tmp, timeout=20)
        if apply_rc != 0:
            return {"ok": False, "score": 0.0, "detail": "apply failed: " + apply_out[-700:]}
        test_rc, test_out = _run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], tmp, timeout=30)
        return {"ok": test_rc == 0, "score": 1.0 if test_rc == 0 else 0.0, "detail": test_out[-900:]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


SLUGIFY_PROMPT = """Write a Python module `solution.py` exposing `slugify(text: str, max_length: int = 80) -> str`.

Rules:
- lowercase ASCII transliteration: é -> e, ü -> u, ß -> ss; implement with unicodedata.normalize, do not hardcode accented literals
- keep letters and digits; convert any run of other characters to one hyphen
- strip leading/trailing hyphens
- truncate to max_length without leaving a trailing hyphen
- empty input or only separators -> ""
Return only a fenced ```python code block."""

DURATION_PROMPT = """Write a Python module `solution.py` exposing `parse_duration(value: str) -> int` returning seconds.

Accept: `1h30m`, `45s`, `2h`, `90m`, `1h 5m 10s`, `1d2h` (d=86400). Units h/m/s/d are case-insensitive; whitespace is ignored.
A bare integer means seconds.
Reject with ValueError: empty input, unknown unit, duplicate unit, units out of order, negative values.
Return only a fenced ```python code block."""

INTERVAL_PROMPT = """Write a Python module `solution.py` exposing `merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]`.

Merge overlapping and touching intervals, sort by start, keep tuples, empty -> [].
Raise ValueError if an interval has end < start.
Return only a fenced ```python code block."""


TASKS: dict[str, dict[str, Any]] = {
    "slugify": {"kind": "code", "max_tokens": 700, "prompt": SLUGIFY_PROMPT, "runner": lambda code: run_python_task(code, SLUGIFY_TEST)},
    "parse_duration": {"kind": "code", "max_tokens": 700, "prompt": DURATION_PROMPT, "runner": lambda code: run_python_task(code, DURATION_TEST)},
    "merge_intervals": {"kind": "code", "max_tokens": 600, "prompt": INTERVAL_PROMPT, "runner": lambda code: run_python_task(code, INTERVAL_TEST)},
    "design_card": {"kind": "html", "max_tokens": 1200, "prompt": DESIGN_PROMPT, "runner": design_rubric},
    "clarity_worktree": {"kind": "text", "max_tokens": 350, "prompt": CLARITY_PROMPT, "runner": clarity_rubric},
    "context_pack": {"kind": "text", "max_tokens": 550, "prompt": CONTEXT_PROMPT, "runner": context_rubric},
    "selfdev_median": {"kind": "diff", "max_tokens": 500, "prompt": SELFDEV_PROMPT, "runner": apply_selfdev},
}

TOOLS = {
    "direct": "direct",
    "headroom": "headroom",
    "ponytail": "ponytail",
    "superpowers": "superpowers",
    "ecc": "ecc",
    "ui_ux": "ui_ux",
    "director": "director",
}
