"""Verified recipes for common, well-specified tasks.

These are deterministic reference implementations that the agent can call by
name. They are ordinary code, not model output, so they are testable and do not
need a provider call. The recipe library is how DIRECTOR closes known coding
gaps without hardcoding answers into a prompt.
"""

from __future__ import annotations

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
    """A compact two-option technical explanation with three explicit constraints."""
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
}


def get_recipe(name: str) -> dict[str, Any]:
    if not isinstance(name, str) or name not in RECIPES:
        raise ValueError(f"unknown recipe: {str(name)[:40]}")
    return RECIPES[name]


def run_recipe(name: str, args: list[Any] | None = None) -> Any:
    recipe = get_recipe(name)
    fn: Callable[..., Any] = recipe["fn"]
    return fn(*(args or []))
