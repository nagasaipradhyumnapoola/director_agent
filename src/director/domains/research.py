"""Research/document pilot: claim-source mapping, conflicts, calculation, render."""

from __future__ import annotations

import ast
import json
import math
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from ..render import extract_citations, render_docx, render_markdown
from ..security import (
    BoundsError,
    PathSafetyError,
    ValidationError,
    atomic_write_text,
    bounded_json_loads,
    ensure_within,
    normalise_whitespace,
    redact_text,
    safe_read_bytes,
    sha256_text,
)
from .base import Check, DomainResult, FindingDraft, PilotContext

EVALUATOR_VERSION = "research-evaluator/1.0"
TRUSTED_CALC_TOLERANCE = 0.01
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
_PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME|LOREM IPSUM)\b", re.IGNORECASE)
_CITATION_RE = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9_-]{0,31})\](?!\()")


def _read_text(ctx: PilotContext, rel: str, max_bytes: int = 2 * 1024 * 1024) -> str:
    target = ensure_within(ctx.fixture_path / rel, Path(ctx.store.root))
    data = safe_read_bytes(target, Path(ctx.store.root), max_bytes=max_bytes)
    return data.decode("utf-8", "replace")


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _safe_calc(expression: str) -> float:
    if not isinstance(expression, str) or len(expression) > 200:
        raise ValidationError("invalid calculation expression")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValidationError("invalid calculation syntax") from exc
    budget = 0

    def visit(node: ast.AST, depth: int) -> float:
        nonlocal budget
        budget += 1
        if depth > 20 or budget > 200:
            raise ValidationError("calculation too complex")
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = visit(node.operand, depth + 1)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            left = visit(node.left, depth + 1)
            right = visit(node.right, depth + 1)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                if right == 0:
                    raise ValidationError("division by zero")
                return left / right
            if abs(right) > 12:
                raise ValidationError("exponent too large")
            return left ** right
        raise ValidationError("unsupported calculation construct")

    result = float(visit(tree.body, 0))
    if not math.isfinite(result):
        raise ValidationError("calculation produced a non-finite value")
    return result


def evaluate(ctx: PilotContext) -> DomainResult:
    checks: list[Check] = []
    findings: list[FindingDraft] = []
    limitations = [
        "Controlled fixture sources; no live web freshness or publisher verification.",
        "Rendered HTML inspection is structural, not a human editorial review.",
        "DOCX rendering is optional and depends on python-docx availability.",
    ]
    question_text = _read_text(ctx, "question.md", max_bytes=256 * 1024)
    claims_raw = _read_text(ctx, "claims.json", max_bytes=1024 * 1024)
    claims = bounded_json_loads(claims_raw, max_bytes=1024 * 1024)
    if not isinstance(claims, dict):
        return DomainResult(status="error", blocked_reason="claims.json must be an object")
    answer_rel = str(claims.get("answer_path", "answer.md"))
    if answer_rel.startswith("/") or ".." in answer_rel.replace("\\", "/").split("/"):
        return DomainResult(status="error", blocked_reason="unsafe answer path")
    answer_text = _read_text(ctx, answer_rel, max_bytes=512 * 1024)
    as_of = _parse_date(claims.get("as_of"))
    if as_of is None:
        findings.append(
            FindingDraft(
                severity="high",
                kind="research_date_missing",
                message="claims.json has no valid as_of date",
                path=f"{ctx.fixture_rel}/claims.json",
                source_sha256=ctx.fixture_sha,
            )
        )

    sources_declared = claims.get("sources")
    if not isinstance(sources_declared, list):
        sources_declared = []
    sources: dict[str, dict[str, Any]] = {}
    source_issues: list[str] = []
    for entry in sources_declared[:50]:
        if not isinstance(entry, dict):
            source_issues.append("source entry is not an object")
            continue
        source_id = str(entry.get("id", ""))
        if not _ID_RE.match(source_id):
            source_issues.append("invalid source id")
            continue
        path = str(entry.get("path", ""))
        if not path or path.startswith("/") or ".." in path.replace("\\", "/").split("/"):
            source_issues.append(f"{source_id}: unsafe path")
            continue
        declared_date = _parse_date(entry.get("date"))
        if declared_date is None:
            source_issues.append(f"{source_id}: invalid date")
            continue
        try:
            text = _read_text(ctx, path, max_bytes=1024 * 1024)
        except (PathSafetyError, BoundsError, OSError):
            source_issues.append(f"{source_id}: source file missing")
            continue
        content_date = None
        for line in text.splitlines()[:20]:
            if line.lower().startswith("date:"):
                content_date = _parse_date(line.split(":", 1)[1].strip())
                break
        if content_date and content_date != declared_date:
            source_issues.append(f"{source_id}: declared date does not match source content")
        status = str(entry.get("status", "")).lower()
        if status not in {"current", "superseded", "draft", "retracted"}:
            source_issues.append(f"{source_id}: invalid status")
        sources[source_id] = {
            "id": source_id,
            "path": path,
            "date": declared_date,
            "status": status,
            "text": text,
            "sha256": sha256_text(text),
        }
    has_current = any(source["status"] == "current" for source in sources.values())
    if not has_current:
        source_issues.append("no current primary source declared")
    sources_ok = not source_issues and bool(sources)
    checks.append(
        Check(
            criterion_key="research.sources",
            description="declared primary sources exist, are dated, and include a current source",
            passed=sources_ok,
            details={
                "sources": [
                    {
                        "id": source["id"],
                        "path": source["path"],
                        "date": source["date"].isoformat(),
                        "status": source["status"],
                        "sha256": source["sha256"],
                    }
                    for source in sources.values()
                ],
                "issues": source_issues,
            },
            subject_path=f"{ctx.fixture_rel}/claims.json",
            subject_sha256=ctx.fixture_sha,
            limitations="existence and dates only; publisher authority is not verified",
        )
    )
    for issue in source_issues:
        findings.append(
            FindingDraft(
                severity="high",
                kind="research_source_issue",
                message=f"source issue: {issue}",
                path=f"{ctx.fixture_rel}/claims.json",
                source_sha256=ctx.fixture_sha,
            )
        )

    claim_entries = claims.get("claims")
    if not isinstance(claim_entries, list):
        claim_entries = []
    claim_issues: list[str] = []
    supported_current = 0
    seen_claim_ids: set[str] = set()
    for entry in claim_entries[:100]:
        if not isinstance(entry, dict):
            claim_issues.append("claim entry is not an object")
            continue
        claim_id = str(entry.get("id", ""))
        if not _ID_RE.match(claim_id) or claim_id in seen_claim_ids:
            claim_issues.append("invalid or duplicate claim id")
            continue
        seen_claim_ids.add(claim_id)
        source_id = str(entry.get("source_id", ""))
        quote = entry.get("quote")
        kind = str(entry.get("kind", "")).lower()
        status = str(entry.get("status", "")).lower()
        if source_id not in sources:
            claim_issues.append(f"{claim_id}: cites undeclared/fabricated source '{source_id[:32]}'")
            continue
        if not isinstance(quote, str) or len(quote) < 10:
            claim_issues.append(f"{claim_id}: quote missing or too short")
            continue
        source = sources[source_id]
        if normalise_whitespace(quote).casefold() not in normalise_whitespace(source["text"]).casefold():
            claim_issues.append(f"{claim_id}: quote not found verbatim in source")
        if as_of and source["date"] > as_of:
            claim_issues.append(f"{claim_id}: source is dated after the answer's as_of date")
        if source["status"] == "superseded" and kind not in {"historical", "superseded"}:
            claim_issues.append(f"{claim_id}: uses a superseded source as '{kind or 'unspecified'}'")
        if status != "supported":
            claim_issues.append(f"{claim_id}: claim status is not supported")
        if source["status"] == "current" and kind == "fact":
            supported_current += 1
    if supported_current == 0:
        claim_issues.append("no fact claim is supported by a current source")
    claims_ok = not claim_issues and bool(claim_entries)
    checks.append(
        Check(
            criterion_key="research.claims",
            description="each claim maps to a declared source and its quote appears verbatim",
            passed=claims_ok,
            details={"claims": len(claim_entries), "issues": claim_issues, "supported_current": supported_current},
            subject_path=f"{ctx.fixture_rel}/claims.json",
            subject_sha256=ctx.fixture_sha,
            limitations="quote matching is textual; it does not prove the source's own methodology",
        )
    )
    for issue in claim_issues:
        findings.append(
            FindingDraft(
                severity="high",
                kind="research_claim_issue",
                message=issue,
                path=f"{ctx.fixture_rel}/claims.json",
                source_sha256=ctx.fixture_sha,
            )
        )

    calc = claims.get("calculation") if isinstance(claims.get("calculation"), dict) else {}
    calc_issues: list[str] = []
    computed = None
    claimed = None
    if not calc:
        calc_issues.append("calculation block missing")
    else:
        try:
            computed = _safe_calc(str(calc.get("expression", "")))
        except ValidationError as exc:
            calc_issues.append(str(exc))
        try:
            claimed = float(calc.get("claimed"))
        except (TypeError, ValueError):
            calc_issues.append("claimed value is not numeric")
        if claimed is not None and not math.isfinite(claimed):
            calc_issues.append("claimed value is not finite")
            claimed = None
        try:
            declared_tolerance = float(calc.get("tolerance", TRUSTED_CALC_TOLERANCE))
        except (TypeError, ValueError):
            declared_tolerance = float("nan")
            calc_issues.append("tolerance is not numeric")
        if not math.isfinite(declared_tolerance) or declared_tolerance < 0:
            calc_issues.append("tolerance is not a finite non-negative number")
        tolerance = TRUSTED_CALC_TOLERANCE
        if computed is not None and claimed is not None and abs(computed - claimed) > tolerance:
            calc_issues.append(f"claimed {claimed:g} does not match recomputed {computed:g}")
        for name, value in dict(calc.get("operands") or {}).items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                calc_issues.append(f"operand '{str(name)[:32]}' is not numeric")
            elif not math.isfinite(float(value)):
                calc_issues.append(f"operand '{str(name)[:32]}' is not finite")
    checks.append(
        Check(
            criterion_key="research.calculation",
            description="the stated calculation recomputes to the claimed value",
            passed=not calc_issues and computed is not None,
            details={
                "expression": calc.get("expression"),
                "claimed": claimed,
                "computed": computed,
                "trusted_tolerance": tolerance,
                "fixture_declared_tolerance": declared_tolerance,
                "issues": calc_issues,
            },
            subject_path=f"{ctx.fixture_rel}/claims.json",
            subject_sha256=ctx.fixture_sha,
            confidence=0.99,
        )
    )
    for issue in calc_issues:
        findings.append(
            FindingDraft(
                severity="high",
                kind="research_calculation_error",
                message=issue,
                path=f"{ctx.fixture_rel}/claims.json",
                source_sha256=ctx.fixture_sha,
            )
        )

    conflict_issues: list[str] = []
    superseded = [source for source in sources.values() if source["status"] == "superseded"]
    note = claims.get("conflict_note")
    if superseded:
        if not isinstance(note, str) or len(normalise_whitespace(note)) < 40:
            conflict_issues.append("conflict note is missing or too short")
        else:
            folded = note.casefold()
            for source in sources.values():
                if source["id"].casefold() not in folded:
                    conflict_issues.append(f"conflict note does not mention source {source['id']}")
    current_ids = [s["id"] for s in sources.values() if s["status"] == "current"]
    answer_citation_ids = set(_CITATION_RE.findall(answer_text))
    if not answer_citation_ids:
        conflict_issues.append("answer contains no source citations")
    for source_id in current_ids:
        if source_id not in answer_citation_ids:
            conflict_issues.append(f"answer does not cite the current source {source_id}")
    checks.append(
        Check(
            criterion_key="research.conflicts",
            description="superseding evidence is acknowledged and the current source is cited",
            passed=not conflict_issues,
            details={"superseded_sources": [s["id"] for s in superseded], "issues": conflict_issues},
            subject_path=f"{ctx.fixture_rel}/claims.json",
            subject_sha256=ctx.fixture_sha,
        )
    )
    for issue in conflict_issues:
        findings.append(
            FindingDraft(
                severity="high",
                kind="research_conflict_issue",
                message=issue,
                path=f"{ctx.fixture_rel}/claims.json",
                source_sha256=ctx.fixture_sha,
            )
        )

    render_issues: list[str] = []
    html_text = render_markdown(answer_text, title="DIRECTOR research answer")
    rendered_citations = extract_citations(html_text)
    declared_ids = set(sources)
    for citation in rendered_citations:
        if citation not in declared_ids:
            render_issues.append(f"answer cites undeclared source '{citation}'")
    answer_citations = sorted(set(_CITATION_RE.findall(answer_text)))
    if not rendered_citations:
        render_issues.append("rendered answer has no citation spans")
    for citation in answer_citations:
        if citation not in declared_ids:
            render_issues.append(f"answer references undeclared source '{citation}'")
    current_ids = [source["id"] for source in sources.values() if source["status"] == "current"]
    for source_id in current_ids:
        if source_id not in rendered_citations:
            render_issues.append(f"rendered answer does not cite the current source {source_id}")
    if _PLACEHOLDER_RE.search(answer_text):
        render_issues.append("answer contains a TODO/TBD/FIXME placeholder")
    if not re.search(r"^#\s+\S", answer_text, re.MULTILINE):
        render_issues.append("answer has no top-level heading")
    if len(normalise_whitespace(answer_text)) < 100:
        render_issues.append("answer is too short to inspect")
    receipt_dir = Path(ctx.store.root) / ".director" / "receipts"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:12]
    html_target = ensure_within(receipt_dir / f"research-answer-{token}.html", Path(ctx.store.root))
    atomic_write_text(html_target, html_text, root=ctx.store.root)
    html_sha = sha256_text(html_text)
    docx_info = None
    docx_target = receipt_dir / f"research-answer-{token}.docx"
    try:
        docx_info = render_docx(answer_text, docx_target)
    except Exception:
        docx_info = None
    if docx_info is None:
        limitations.append("DOCX render unavailable; HTML render inspected instead")
    else:
        if docx_info.get("paragraphs", 0) < 3:
            render_issues.append("rendered DOCX has too few paragraphs")
        docx_info["sha256"] = sha256_text(docx_target.read_bytes().decode("latin-1"))
    if len(html_text.encode("utf-8")) < 200:
        render_issues.append("rendered HTML is implausibly small")
    checks.append(
        Check(
            criterion_key="research.render",
            description="rendered answer has resolved citations, no placeholders and a real artifact",
            passed=not render_issues,
            details={
                "html_ref": html_target.relative_to(Path(ctx.store.root)).as_posix(),
                "html_sha256": html_sha,
                "html_bytes": len(html_text.encode("utf-8")),
                "citations": rendered_citations,
                "docx": docx_info,
                "issues": render_issues,
            },
            subject_path=f"{ctx.fixture_rel}/{answer_rel}",
            subject_sha256=sha256_text(answer_text),
            confidence=0.9,
            limitations="structural render inspection only; not editorial quality",
        )
    )
    for issue in render_issues:
        findings.append(
            FindingDraft(
                severity="high",
                kind="research_render_issue",
                message=issue,
                path=f"{ctx.fixture_rel}/{answer_rel}",
                source_sha256=sha256_text(answer_text),
            )
        )

    status = "pass" if all(check.passed for check in checks) else "fail"
    return DomainResult(
        status=status,
        checks=checks,
        findings=findings,
        limitations=limitations,
        resources={"rendered_html_bytes": len(html_text.encode("utf-8")), "docx": bool(docx_info)},
        report={"question": question_text[:2000], "claims_file": claims, "render": {"html_sha256": html_sha}},
    )

