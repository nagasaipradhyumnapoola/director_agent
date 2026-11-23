"""Prompt-level upstream skill ablation with a local coding model.

This exercises the *skill instructions* from pinned upstream revisions, not their
runtimes. Headroom compression/proxy behavior, hooks and installers are not run.
One small task, one local model, one run each: a signal, not a leaderboard.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from director.models import Budgets, PermissionPolicy
from director.policy import PolicyGateway
from director.providers import call_model
from director.store import Store

PINNED = {
    "ponytail": "https://raw.githubusercontent.com/DietrichGebert/ponytail/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/skills/ponytail/SKILL.md",
    "superpowers_tdd": "https://raw.githubusercontent.com/obra/superpowers/22f0b463e7a5e579904dd6211a520321035526f7/skills/test-driven-development/SKILL.md",
    "ecc_ai_regression": "https://raw.githubusercontent.com/affaan-m/ECC/4adeee6732a12d1540f49a4d50a38ce8c97f9a53/skills/ai-regression-testing/SKILL.md",
    "headroom_skill": "https://raw.githubusercontent.com/headroomlabs-ai/headroom/ce0460cfa8598dc939243dbc7aec4b2d35f4e44a/skills/headroom/SKILL.md",
}

TASK = """You are authoring one small Python change.

TASK: create src/units.py with a function format_bytes(num) -> str:
- 0 -> "0B"
- 1023 -> "1023B"
- 1024 -> "1KB"
- 1048576 -> "1MB"
- negative -> "Invalid"
Also create tests/test_units.py. Tests run with PYTHONPATH=<repo>/src and use:
    from units import format_bytes
Keep it dependency-free and Python 3.11+ compatible.

Return ONLY a unified git diff. New files need diff --git a/path b/path,
new file mode 100644, --- /dev/null, +++ b/path. Do not wrap it in markdown.
The patch must apply with `git apply --recount` at the repository root.
"""


def _fetch(url: str) -> str:
    cache = Path("var/upstream") / (url.rsplit("/", 1)[-1] + "-" + str(abs(hash(url)))[:8])
    if cache.is_file():
        return cache.read_text(encoding="utf-8")
    with urllib.request.urlopen(url, timeout=30) as response:
        text = response.read(64 * 1024).decode("utf-8", "replace")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text


def _make_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Bench"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.email", "bench@example.invalid"], cwd=root, capture_output=True)
    (root / "src").mkdir()
    (root / "src" / ".keep").write_text("", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / ".keep").write_text("", encoding="utf-8")
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, capture_output=True)


def _reset(root: Path) -> None:
    subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=root, capture_output=True)
    subprocess.run(["git", "clean", "-fd"], cwd=root, capture_output=True)


def _run_variant(store: Store, repo: Path, model: str, variant: str, skill_text: str) -> dict:
    prompt = TASK
    if skill_text:
        prompt += "\n\nFOLLOW THIS SKILL INSTRUCTION:\n" + skill_text[:9000]
    started = time.perf_counter()
    try:
        result = call_model(store, prompt, provider="ollama", model=model, timeout=300)
        wall = time.perf_counter() - started
        raw = result["output"].strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw
            raw = raw.rstrip()
            if raw.endswith("```"):
                raw = raw[:-3].rstrip()
    except Exception as exc:
        return {
            "variant": variant,
            "ok": False,
            "error": type(exc).__name__,
            "wall_seconds": round(time.perf_counter() - started, 3),
        }
    start = raw.find("diff --git ")
    patch = raw[start:] if start >= 0 else ""
    fence = patch.find("```")
    if fence >= 0:
        patch = patch[:fence]
    patch = patch.strip() + "\n" if patch.strip() else ""
    applied = False
    test_exit = None
    test_output = ""
    if patch:
        patch_file = repo / "candidate.patch"
        patch_file.write_text(patch, encoding="utf-8")
        apply_result = subprocess.run(
            ["git", "apply", "--recount", str(patch_file)],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=60,
        )
        applied = apply_result.returncode == 0
        if applied:
            test_env = {
                key: os.environ[key]
                for key in (
                    "PATH",
                    "PATHEXT",
                    "SYSTEMROOT",
                    "WINDIR",
                    "TEMP",
                    "TMP",
                    "USERPROFILE",
                    "APPDATA",
                    "LOCALAPPDATA",
                )
                if os.environ.get(key)
            }
            test_env["PYTHONPATH"] = str(repo / "src")
            test_env["PYTHONIOENCODING"] = "utf-8"
            test = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "tests/test_units.py"],
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=120,
                env=test_env,
            )
            test_exit = test.returncode
            test_output = (test.stdout + test.stderr)[-2000:]
        else:
            test_output = apply_result.stderr[-2000:]
    _reset(repo)
    return {
        "variant": variant,
        "ok": applied and test_exit == 0,
        "applied": applied,
        "test_exit": test_exit,
        "wall_seconds": round(wall, 3),
        "usage": result.get("usage"),
        "output_preview": raw[:500],
        "test_tail": test_output[-1000:],
    }


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="director-composition-"))
    (tmp / "state").mkdir()
    store = Store.open_or_create(tmp / "state", "composition")
    try:
        store.save_contract(
            __import__("director.demo", fromlist=["build_contract"]).build_contract(
                store.project_id, ("general",)
            )
        )
        from director.models import TaskContract

        latest = store.latest_contract()[1]
        store.save_contract(
            TaskContract(
                project_id=latest.project_id,
                revision=2,
                intent=latest.intent,
                deliverables=latest.deliverables,
                constraints=latest.constraints,
                non_goals=latest.non_goals,
                assumptions=latest.assumptions,
                domains=latest.domains,
                requirements=latest.requirements,
                budgets=Budgets(max_model_calls=10, max_wall_seconds=3600),
                permissions=PermissionPolicy(allowed_actions=("read_artifact", "model_call_local")),
                stopping_conditions=latest.stopping_conditions,
            )
        )
        PolicyGateway(store).grant("director.model", "model_call_local", "provider:ollama", 2)
        model = "qwen2.5-coder:7b"
        repo = tmp / "repo"
        _make_repo(repo)
        variants = {"baseline": ""}
        for name, url in PINNED.items():
            try:
                variants[name] = _fetch(url)
            except Exception:
                variants[name] = ""
        results = []
        for name, text in variants.items():
            results.append(_run_variant(store, repo, model, name, text))
        payload = {
            "schema": "director.composition_ablation.v1",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": model,
            "task": "format_bytes helper + test",
            "runs_per_variant": 1,
            "results": results,
            "limitations": [
                "prompt/skill instructions only; upstream runtimes/hooks/installers not executed",
                "Headroom compression/proxy/caching is not measured",
                "one small task, one local model, one run; not a leaderboard",
                "scores are noisy and not statistically significant",
            ],
        }
        out = Path(__file__).resolve().parent / "results" / "prompt_ablation.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(out), "results": results}, indent=2))
        return 0
    finally:
        store.close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
