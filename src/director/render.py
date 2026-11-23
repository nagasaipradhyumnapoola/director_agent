"""Minimal safe Markdown renderer and citation inspection."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

_CITATION_RE = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9_-]{0,31})\](?!\()")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")
_LINK_RE = re.compile(r"\[([^\]]{1,200})\]\((https?://[^\s)]{1,500})\)")


def _inline(text: str) -> str:
    escaped = html.escape(text, quote=True)
    escaped = _LINK_RE.sub(
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}" rel="noreferrer noopener">{m.group(1)}</a>',
        escaped,
    )
    escaped = _CITATION_RE.sub(
        lambda m: f'<span class="citation" data-source="{m.group(1)}">[{m.group(1)}]</span>',
        escaped,
    )
    escaped = re.sub(r"\*\*([^*]{1,500})\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]{1,500})`", r"<code>\1</code>", escaped)
    return escaped


def render_markdown(text: str, title: str = "DIRECTOR rendered document", max_chars: int = 400_000) -> str:
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[TRUNCATED]"
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    body: list[str] = []
    in_list = False
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            body.append("<p>" + _inline(" ".join(paragraph).strip()) + "</p>")
            paragraph = []

    for line in lines:
        stripped = line.strip()
        heading = _HEADING_RE.match(stripped)
        bullet = _BULLET_RE.match(line)
        if not stripped:
            flush_paragraph()
            if in_list:
                body.append("</ul>")
                in_list = False
            continue
        if heading:
            flush_paragraph()
            if in_list:
                body.append("</ul>")
                in_list = False
            level = min(len(heading.group(1)), 6)
            body.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
        elif bullet:
            flush_paragraph()
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{_inline(bullet.group(1))}</li>")
        else:
            paragraph.append(stripped)
    flush_paragraph()
    if in_list:
        body.append("</ul>")
    safe_title = html.escape(title, quote=True)
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{safe_title}</title>\n</head>\n<body>\n"
        + "\n".join(body)
        + "\n</body>\n</html>\n"
    )


def extract_citations(html_text: str) -> list[str]:
    return sorted(set(re.findall(r'data-source="([A-Za-z0-9_-]{1,32})"', html_text)))


def render_docx(markdown_text: str, target: Path) -> dict[str, Any] | None:
    try:
        from docx import Document  # type: ignore
    except Exception:
        return None
    document = Document()
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        heading = _HEADING_RE.match(stripped)
        if heading:
            document.add_heading(heading.group(2), level=min(len(heading.group(1)), 4))
        elif _BULLET_RE.match(line):
            document.add_paragraph(_BULLET_RE.match(line).group(1), style="List Bullet")  # type: ignore[union-attr]
        else:
            document.add_paragraph(stripped)
    document.save(str(target))
    reopened = Document(str(target))
    return {
        "path": target.name,
        "paragraphs": len(reopened.paragraphs),
        "bytes": target.stat().st_size,
    }
