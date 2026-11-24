"""Bounded local agent loop.

The agent is deliberately small and inspectable: the model proposes one JSON
tool call at a time, DIRECTOR validates and executes it, and the observation is
fed back. It cannot write project files directly, merge, push, deploy or grant
itself permissions. Code changes become selfdev patches for the normal gates.

The default model call goes through ``providers.call_model`` and therefore needs
the contract action, owner grant and budget. Tests and embedding can pass a
``model_fn`` instead.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Sequence

from . import audit
from .memory import MemoryIndex
from .policy import PolicyGateway
from .providers import call_model
from .security import BoundsError, ValidationError, atomic_write_text, redact_text
from .store import Store, utc_now

MAX_STEPS = 20
MAX_FILE = 200 * 1024
MAX_OBSERVATION = 4000
MAX_PATCH = 128 * 1024
SKIP_DIRS = {".git", ".director", "var", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}
DEFAULT_COMMANDS = {"python", "python3", "pytest", "git", "node", "npm", "pnpm", "yarn"}

TOOL_HELP = """Available tools (reply with exactly one JSON object):
{"tool":"list_files","path":"."}
{"tool":"read_file","path":"src/example.py"}
{"tool":"run_command","argv":["python","-m","pytest","-q"]}
{"tool":"browser_capture","url":"http://127.0.0.1:8765/"}
{"tool":"memory_search","query":"evidence"}
{"tool":"remember","title":"decision","text":"..."}
{"tool":"route","task":"Design an accessible card"}
{"tool":"orchestrate","goal":"Design a card; explain the tradeoff"}
{"tool":"recipe","name":"slugify","args":["Hello World",80]}
{"tool":"propose_patch","title":"Fix X","diff":"diff --git ..."}
{"tool":"finish","summary":"what was done and what remains"}
Rules: one tool per turn; no prose outside JSON; no direct project writes; never merge/push/deploy."""


def _run_id() -> str:
    return "run_" + uuid.uuid4().hex


def _safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise ValidationError("invalid path")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValidationError("path escapes the project") from exc
    for part in candidate.relative_to(root.resolve()).parts:
        if part in {".git", ".director"}:
            raise ValidationError("path is protected")
    return candidate


def _text_result(value: Any) -> str:
    if isinstance(value, str):
        return redact_text(value, max_chars=MAX_OBSERVATION)
    text = json.dumps(value, sort_keys=True, default=str)
    return redact_text(text, max_chars=MAX_OBSERVATION)


def _parse_action(text: str) -> dict[str, Any]:
    raw = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S | re.I)
    if fenced:
        raw = fenced.group(1)
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        raise ValidationError("model response did not contain a JSON object")
    value = json.loads(raw[start : end + 1])
    if not isinstance(value, dict) or not isinstance(value.get("tool"), str):
        raise ValidationError("model response is not a tool call")
    return value


def _list_files(root: Path, relative: str = ".") -> list[str]:
    base = _safe_path(root, relative)
    if not base.is_dir():
        raise ValidationError("not a directory")
    out: list[str] = []
    for current, dirs, files in os.walk(base):
        dirs[:] = [d for d in sorted(dirs) if d not in SKIP_DIRS and not d.startswith(".")]
        for name in sorted(files):
            path = Path(current) / name
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                continue
            out.append(rel)
            if len(out) >= 300:
                return out
    return out


def _read_file(root: Path, relative: str) -> dict[str, Any]:
    path = _safe_path(root, relative)
    if not path.is_file():
        raise ValidationError("file does not exist")
    if path.is_symlink():
        raise ValidationError("symlinks are not read")
    data = path.read_bytes()
    if len(data) > MAX_FILE:
        raise BoundsError("file exceeds 200KB")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("file is not UTF-8 text") from exc
    return {"path": relative, "bytes": len(data), "text": redact_text(text, max_chars=MAX_OBSERVATION)}


def _run_command(store: Store, root: Path, argv: Sequence[str], allowed: set[str], timeout: float) -> dict[str, Any]:
    if not argv or len(argv) > 64:
        raise ValidationError("invalid command")
    if argv[0] not in allowed:
        raise ValidationError(f"command not allowed: {argv[0][:40]}")
    for item in argv:
        if not isinstance(item, str) or not item or "\x00" in item or len(item) > 4096:
            raise ValidationError("invalid argument")
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "PYTHONPATH": str(Path(store.root) / "src"),
        "PYTHONIOENCODING": "utf-8",
        "TEMP": tempfile.gettempdir(),
        "TMP": tempfile.gettempdir(),
    }
    proc = subprocess.run(
        list(argv),
        cwd=root,
        capture_output=True,
        text=True,
        timeout=max(1, min(timeout, 600)),
        env=env,
    )
    return {
        "argv": list(argv),
        "exit_code": proc.returncode,
        "stdout": redact_text(proc.stdout[-MAX_OBSERVATION:], max_chars=MAX_OBSERVATION),
        "stderr": redact_text(proc.stderr[-MAX_OBSERVATION:], max_chars=MAX_OBSERVATION),
    }


def _chrome_path() -> str:
    candidates = [
        os.environ.get("DIRECTOR_CHROME", ""),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise ValidationError("no Chromium-family browser found")


def _browser_capture(root: Path, url: str, timeout: float = 45.0) -> dict[str, Any]:
    if not isinstance(url, str) or not re.match(r"^(https?|file)://", url, re.I):
        raise ValidationError("browser URL must be http(s) or file")
    chrome = _chrome_path()
    out_dir = Path(tempfile.mkdtemp(prefix="director-browser-"))
    profile = out_dir / "profile"
    shot = out_dir / "capture.png"
    common = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={profile}",
    ]
    dom = subprocess.run(
        [*common, "--dump-dom", url],
        capture_output=True,
        text=True,
        timeout=max(5, min(timeout, 120)),
    )
    image = subprocess.run(
        [*common, f"--screenshot={shot}", "--window-size=1280,900", url],
        capture_output=True,
        text=True,
        timeout=max(5, min(timeout, 120)),
    )
    html = dom.stdout[: 512 * 1024]
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return {
        "url": url,
        "title": re.sub(r"\s+", " ", title.group(1)).strip() if title else "",
        "text": redact_text(text[:MAX_OBSERVATION], max_chars=MAX_OBSERVATION),
        "screenshot": str(shot) if shot.is_file() else None,
        "exit_code": dom.returncode,
        "image_exit_code": image.returncode,
        "dom_bytes": len(html),
        "limits": "headless capture only; click/type requires the host browse tools",
    }


def run_agent(
    store: Store,
    goal: str,
    *,
    provider: str = "ollama",
    model: str | None = None,
    max_steps: int = 8,
    timeout: float = 120.0,
    allowed_commands: set[str] | None = None,
    model_fn: Callable[[str], str] | None = None,
    auto_orchestrate: bool = True,
) -> dict[str, Any]:
    if not isinstance(goal, str) or not goal.strip() or len(goal) > 8000:
        raise ValidationError("goal must be 1-8000 chars")
    if not 1 <= max_steps <= MAX_STEPS:
        raise ValidationError(f"max_steps must be 1-{MAX_STEPS}")
    if not 1 <= timeout <= 600:
        raise ValidationError("timeout must be 1-600 seconds")

    policy = PolicyGateway(store)
    latest = store.latest_contract()
    revision = int(latest[0]["revision"]) if latest else 1
    policy.require("director.agent", "read_artifact", "project", revision)
    allowed = set(DEFAULT_COMMANDS if allowed_commands is None else allowed_commands)
    run_id = _run_id()
    root = Path(store.root).resolve()
    run_dir = root / ".director" / "agent" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    transcript: list[dict[str, Any]] = []
    started = time.perf_counter()
    audit.log(store, "director.agent", "agent.start", run_id, "ok", {"goal": goal[:160]})

    if auto_orchestrate:
        from .orchestrator import execute as orchestrate, plan as orchestrate_plan

        planned = orchestrate_plan(goal)
        if planned and all(step["kind"] in {"design", "clarity"} for step in planned):
            execution = orchestrate(goal)
            if execution.get("planned", 1) == 0 and execution.get("executed") == len(planned):
                result = {
                    "run_id": run_id,
                    "status": "finished",
                    "goal": goal,
                    "steps": 1,
                    "summary": f"deterministic orchestrator executed {execution['executed']} step(s)",
                    "transcript": [{"step": 1, "tool": "orchestrate", "observation": execution}],
                    "duration_s": round(time.perf_counter() - started, 3),
                    "model": {"provider": "deterministic", "model": "orchestrator"},
                    "transcript_ref": f".director/agent/{run_id}/transcript.json",
                    "mode": "deterministic_orchestrator",
                    "note": "No model call. Deterministic design/clarity recipes executed and can be graded.",
                }
                atomic_write_text(
                    run_dir / "transcript.json",
                    json.dumps([{"step": 1, "tool": "orchestrate", "observation": execution}], indent=2, default=str),
                    root=root,
                )
                atomic_write_text(run_dir / "result.json", json.dumps(result, indent=2, default=str), root=root)
                audit.log(store, "director.agent", "agent.finish", run_id, "finished", {"mode": "deterministic"})
                return result

    def call(prompt: str) -> str:
        if model_fn is not None:
            return str(model_fn(prompt))
        grant = policy.require(
            "director.model",
            "model_call_local",
            f"provider:{provider}",
            revision,
            payload={"run_id": run_id, "goal": goal[:200]},
        )
        del grant
        result = call_model(store, prompt, provider=provider, model=model, timeout=timeout, max_tokens=1400)
        return str(result["output"])

    system = (
        "You are Diro, the DIRECTOR local agent. You are careful, concrete and bounded.\n"
        "You operate inside one project root. You may inspect, run allowlisted commands, "
        "capture a browser page, use memory, and propose a patch. You cannot write project "
        "files directly, merge, push, deploy, spend or grant permissions.\n\n"
        + TOOL_HELP
    )
    status = "max_steps"
    summary = ""
    seen: set[str] = set()
    for step in range(1, max_steps + 1):
        recent = transcript[-6:]
        prompt = (
            f"GOAL:\n{goal}\n\nPROJECT: {root}\nSTEP {step}/{max_steps}\n"
            "RECENT OBSERVATIONS:\n"
            + json.dumps(recent, ensure_ascii=False, default=str)[: 12000]
            + "\n\nRULES: do not repeat a tool call that already succeeded. "
            "If the goal is satisfied, call finish now. Otherwise choose a different tool.\n\nSYSTEM:\n"
            + system
            + "\nReply with one JSON tool call now."
        )
        if len(prompt) > 24_000:
            prompt = prompt[:24_000]
        raw = call(prompt)
        try:
            action = _parse_action(raw)
        except (ValidationError, json.JSONDecodeError) as exc:
            transcript.append({"step": step, "raw": redact_text(raw, max_chars=1200), "error": str(exc)})
            continue
        tool = action["tool"]
        signature = tool + ":" + json.dumps({k: v for k, v in action.items() if k != "tool"}, sort_keys=True, default=str)
        if signature in seen:
            observation = {"error": "repeated tool call ignored; call finish or choose a different tool"}
            transcript.append({"step": step, "tool": tool, "observation": observation})
            continue
        seen.add(signature)
        observation: Any
        try:
            if tool == "finish":
                status = "finished"
                summary = str(action.get("summary") or "")[:4000]
                transcript.append({"step": step, "tool": tool, "summary": summary})
                break
            if tool == "list_files":
                observation = _list_files(root, str(action.get("path") or "."))
            elif tool == "read_file":
                observation = _read_file(root, str(action.get("path") or ""))
            elif tool == "run_command":
                policy.require("director.agent", "run_local_subprocess", "project", revision)
                observation = _run_command(store, root, list(action.get("argv") or []), allowed, timeout)
            elif tool == "browser_capture":
                policy.require("director.agent", "launch_browser", "project", revision)
                observation = _browser_capture(root, str(action.get("url") or ""), timeout)
            elif tool == "memory_search":
                observation = MemoryIndex(store).search(str(action.get("query") or ""), limit=8)
            elif tool == "remember":
                text = str(action.get("text") or "")
                title = str(action.get("title") or "agent note")
                source_id = MemoryIndex(store).add_text(text, title, kind="agent")
                observation = {"source_id": source_id}
            elif tool == "recipe":
                from .recipes import get_recipe, run_recipe

                recipe = get_recipe(str(action.get("name") or ""))
                args = action.get("args") or []
                if not isinstance(args, list):
                    raise ValidationError("recipe args must be a list")
                observation = {"name": action.get("name"), "result": run_recipe(str(action["name"]), args), "description": recipe["description"]}
            elif tool == "route":
                from .router import route as route_task

                observation = route_task(str(action.get("task") or ""))
            elif tool == "orchestrate":
                from .orchestrator import execute as orchestrate

                observation = orchestrate(str(action.get("goal") or ""))
            elif tool == "propose_patch":
                from .selfdev import create_patch

                diff = str(action.get("diff") or "")
                if len(diff) > MAX_PATCH:
                    raise BoundsError("patch exceeds 128KB")
                patch = create_patch(store, diff, str(action.get("title") or "agent proposal")[:200], author="director.agent")
                observation = {"patch_id": patch["id"], "changed_files": patch.get("changed_files") or []}
            else:
                raise ValidationError(f"unknown tool: {tool[:40]}")
        except Exception as exc:  # tool errors are observations, not crashes
            observation = {"error": f"{type(exc).__name__}: {str(exc)[:300]}"}
        transcript.append({"step": step, "tool": tool, "observation": observation})
        atomic_write_text(run_dir / "transcript.json", json.dumps(transcript, indent=2, default=str), root=root)

    result = {
        "run_id": run_id,
        "status": status,
        "goal": goal,
        "steps": len(transcript),
        "summary": summary,
        "transcript": transcript,
        "duration_s": round(time.perf_counter() - started, 3),
        "model": {"provider": provider, "model": model or "default"},
        "transcript_ref": f".director/agent/{run_id}/transcript.json",
        "note": "Model output is untrusted. Proposed patches still need selfdev test/review/merge.",
    }
    atomic_write_text(run_dir / "result.json", json.dumps(result, indent=2, default=str), root=root)
    audit.log(store, "director.agent", "agent.finish", run_id, status, {"steps": result["steps"]})
    return result
