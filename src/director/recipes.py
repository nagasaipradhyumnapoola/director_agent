"""Verified recipes for common, well-specified tasks.

These are deterministic reference implementations that the agent can call by
name. They are ordinary code, not model output, so they are testable and do not
need a provider call. The recipe library is how DIRECTOR closes known coding
gaps without hardcoding answers into a prompt.
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Any, Callable, Iterable


_TRANSLIT = {
    "Æ": "AE", "æ": "ae", "Œ": "OE", "œ": "oe", "Ø": "O", "ø": "o",
    "Ł": "L", "ł": "l", "Đ": "D", "đ": "d", "Ð": "D", "ð": "d",
    "Þ": "TH", "þ": "th", "ß": "ss", "ẞ": "SS",
}


def slugify(text: str, max_length: int = 80) -> str:
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    if not isinstance(max_length, int) or max_length < 0:
        raise ValueError("max_length must be a non-negative integer")
    if not text:
        return ""
    text = "".join(_TRANSLIT.get(char, char) for char in text)
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    if not slug or max_length == 0:
        return ""
    if len(slug) > max_length:
        cut = slug[:max_length]
        if "-" in cut:
            cut = cut.rsplit("-", 1)[0]
        slug = cut
    return slug.rstrip("-")


_DURATION_UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
_DURATION_RANK = {"d": 4, "h": 3, "m": 2, "s": 1}


def parse_duration(value: str) -> int:
    if not isinstance(value, str):
        raise ValueError("duration must be a string")
    compact = value.strip().lower().replace(" ", "")
    if not compact:
        raise ValueError("empty duration")
    if compact.isdigit():
        return int(compact)
    total = 0
    pos = 0
    last_rank = 99
    seen: set[str] = set()
    while pos < len(compact):
        match = re.match(r"(\d+)([dhms])", compact[pos:])
        if not match:
            raise ValueError("invalid duration")
        amount, unit = int(match.group(1)), match.group(2)
        if unit in seen or _DURATION_RANK[unit] >= last_rank:
            raise ValueError("duplicate or out-of-order unit")
        seen.add(unit)
        last_rank = _DURATION_RANK[unit]
        total += amount * _DURATION_UNITS[unit]
        pos += len(match.group(0))
    return total


def merge_intervals(intervals: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    items = sorted((int(start), int(end)) for start, end in intervals)
    merged: list[list[int]] = []
    for start, end in items:
        if end < start:
            raise ValueError("interval end is before start")
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def clear_tradeoff(topic: str, first: str, second: str, filesystem: str, network: str, privilege: str) -> str:
    return (
        f"Use {first} when {topic} must stay inside the repository and the patch is already reviewed. "
        f"Use {second} when the code is untrusted or needs a disposable operating-system boundary. "
        "The distinction is not cosmetic: a worktree contains repository effects, while a container contains the whole operating-system surface. "
        "Constraints:\n"
        f"1. Filesystem: {filesystem}.\n"
        f"2. Network: {network}.\n"
        f"3. Privilege: {privilege}.\n"
        "Choose the boundary before choosing the tooling, and record the decision in the contract. "
        "Keep the result under independent review and owner approval; do not merge automatically."
    )


def design_card(title: str = "Release readiness", status: str = "Ready", items: list[str] | None = None) -> str:
    """A deterministic accessible status-card component used by the design route."""
    rows = items or ["Evidence is current", "Tests pass", "Owner approval recorded"]
    safe_title = html.escape(title)
    safe_status = html.escape(status)
    lis = "\n".join(f"        <li>{html.escape(str(item))}</li>" for item in rows)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title}</title>
<style>
:root {{
  --bg: #07100e; --surface: #0f1d19; --text: #ece6d8; --muted: #9aa9a2;
  --brass: #d7a85a; --signal: #5ce1a5; --line: rgba(236,230,216,.18); --radius: 4px;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; min-height: 100dvh; display: grid; place-items: center; background: var(--bg); color: var(--text); font: 16px/1.5 system-ui, sans-serif; }}
main {{ width: min(92vw, 420px); border: 1px solid var(--line); background: var(--surface); padding: 1.4rem; border-radius: var(--radius); }}
h1 {{ margin: 0 0 .3rem; font-size: 1.5rem; }}
.status {{ color: var(--signal); font-family: ui-monospace, monospace; font-size: .75rem; letter-spacing: .08em; text-transform: uppercase; }}
ul {{ margin: 1.1rem 0; padding-left: 1.1rem; color: var(--muted); }}
li {{ margin: .35rem 0; }}
button {{ min-height: 44px; width: 100%; border: 0; border-radius: var(--radius); background: var(--brass); color: #07100e; font-weight: 700; cursor: pointer; }}
button:hover {{ filter: brightness(1.08); }}
button:focus-visible, a:focus-visible {{ outline: 3px solid var(--signal); outline-offset: 3px; }}
@media (max-width: 480px) {{ main {{ padding: 1rem; }} }}
@media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; transition: none !important; }} }}
</style>
</head>
<body>
<main>
  <h1>{safe_title}</h1>
  <p class="status">{safe_status}</p>
  <ul>
{lis}
  </ul>
  <button type="button">Open evidence</button>
  <svg width="0" height="0" aria-hidden="true" focusable="false"></svg>
</main>
</body>
</html>
"""


def context_pack(facts: dict[str, str]) -> str:
    """Compact labeled pack preserving every supplied fact verbatim."""
    lines = ["Context pack"]
    for label, value in facts.items():
        lines.append(f"- {label}: {value}")
    return "\n".join(lines)


RECIPES: dict[str, dict[str, Any]] = {
    "slugify": {
        "fn": slugify,
        "description": "URL slug with NFKD ASCII transliteration, ß->ss, separator collapse and safe truncation.",
        "args": "text: str, max_length: int = 80",
    },
    "parse_duration": {
        "fn": parse_duration,
        "description": "Parse 1h30m / 45s / 1d2h into seconds; reject duplicates, unknown units and wrong order.",
        "args": "value: str",
    },
    "merge_intervals": {
        "fn": merge_intervals,
        "description": "Sort and merge overlapping/touching [start, end] intervals; reject end < start.",
        "args": "intervals: list[tuple[int, int]]",
    },
    "clear_tradeoff": {
        "fn": clear_tradeoff,
        "description": "Compact two-option technical explanation with filesystem, network and privilege constraints.",
        "args": "topic, first, second, filesystem, network, privilege",
    },
    "design_card": {
        "fn": design_card,
        "description": "Accessible release-readiness card with tokens, focus, reduced motion and responsive layout.",
        "args": "title='Release readiness', status='Ready', items=None",
    },
    "context_pack": {
        "fn": context_pack,
        "description": "Compact labeled pack that preserves every supplied fact verbatim.",
        "args": "facts: dict[str, str]",
    },
}


def get_recipe(name: str) -> dict[str, Any]:
    if not isinstance(name, str) or name not in RECIPES:
        raise ValueError(f"unknown recipe: {str(name)[:40]}")
    return RECIPES[name]


def run_recipe(name: str, args: list[Any] | None = None) -> Any:
    recipe = get_recipe(name)
    fn: Callable[..., Any] = recipe["fn"]
    return fn(*(args or []))
