"""Website pilot: static accessibility checks plus a real Chromium CDP journey."""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from ..security import (
    BoundsError,
    PathSafetyError,
    ValidationError,
    atomic_write_bytes,
    bounded_json_loads,
    ensure_within,
    redact_text,
    safe_read_bytes,
    sha256_bytes,
)
from .base import Check, DomainResult, FindingDraft, PilotContext

EVALUATOR_VERSION = "website-evaluator/1.0"
_TEXT_INPUT_TYPES = {"", "text", "search", "email", "password", "tel", "url", "number"}
_WIDTH_RE = re.compile(r"(?<![-\w])width\s*:\s*(\d+)px", re.IGNORECASE)


class _Inspector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.decls: list[str] = []
        self.text_parts: list[str] = []

    def handle_decl(self, decl: str) -> None:
        self.decls.append(decl)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag.lower(), {k.lower(): (v or "") for k, v in attrs}))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.text_parts.append(data.strip())


def _find_browser() -> str | None:
    override = os.environ.get("DIRECTOR_BROWSER")
    if override and Path(override).is_file():
        return override
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    for name in ("chrome", "msedge", "chromium", "google-chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _read(ctx: PilotContext, rel: str, max_bytes: int = 2 * 1024 * 1024) -> str:
    target = ensure_within(ctx.fixture_path / rel, Path(ctx.store.root))
    return safe_read_bytes(target, Path(ctx.store.root), max_bytes=max_bytes).decode("utf-8", "replace")


def _static_checks(ctx: PilotContext) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    html_files = [e["path"] for e in ctx.fixture_entries if e["path"].lower().endswith((".html", ".htm"))]
    if not html_files:
        return (
            [
                {
                    "severity": "high",
                    "kind": "website_no_html",
                    "message": "no HTML entry point found in the fixture",
                    "path": ctx.fixture_rel,
                    "line": None,
                }
            ],
            {"html": None, "issues": 1},
        )
    html_rel = "index.html" if "index.html" in html_files else html_files[0]
    html_text = _read(ctx, html_rel)
    inspector = _Inspector()
    inspector.feed(html_text)
    issues: list[dict[str, Any]] = []

    def add(severity: str, kind: str, message: str, path: str) -> None:
        if len(issues) < 100:
            issues.append(
                {
                    "severity": severity,
                    "kind": kind,
                    "message": redact_text(message)[:500],
                    "path": path,
                    "line": None,
                }
            )

    if not any("doctype html" in decl.lower() for decl in inspector.decls):
        add("medium", "html_doctype", "missing HTML doctype", f"{ctx.fixture_rel}/{html_rel}")
    html_tags = [attrs for tag, attrs in inspector.tags if tag == "html"]
    if not html_tags or not html_tags[0].get("lang"):
        add("high", "html_lang", "html element has no lang attribute", f"{ctx.fixture_rel}/{html_rel}")
    metas = [attrs for tag, attrs in inspector.tags if tag == "meta"]
    viewport = any(
        attrs.get("name", "").lower() == "viewport"
        and "width=device-width" in attrs.get("content", "").replace(" ", "").lower()
        for attrs in metas
    )
    if not viewport:
        add("high", "viewport_meta", "missing responsive viewport meta tag", f"{ctx.fixture_rel}/{html_rel}")

    labels_for = {
        attrs.get("for", "")
        for tag, attrs in inspector.tags
        if tag == "label" and attrs.get("for")
    }
    for tag, attrs in inspector.tags:
        if tag == "img" and "alt" not in attrs:
            add("high", "img_alt", "image has no alt attribute", f"{ctx.fixture_rel}/{html_rel}")
        if tag == "input":
            input_type = attrs.get("type", "").lower()
            if input_type in _TEXT_INPUT_TYPES:
                input_id = attrs.get("id", "")
                labelled = (
                    (input_id and input_id in labels_for)
                    or bool(attrs.get("aria-label"))
                    or bool(attrs.get("aria-labelledby"))
                    or bool(attrs.get("title"))
                )
                if not labelled:
                    add("high", "input_label", f"input '{input_id or '(no id)'}' has no accessible label", f"{ctx.fixture_rel}/{html_rel}")
        if tag in {"div", "span"}:
            interactive = (
                bool(attrs.get("onclick"))
                or attrs.get("id", "") in {"add-to-cart", "checkout"}
                or "button" in attrs.get("class", "").lower()
            )
            if interactive and attrs.get("role", "") != "button":
                add(
                    "high",
                    "non_semantic_control",
                    f"non-semantic interactive element '{attrs.get('id') or tag}'",
                    f"{ctx.fixture_rel}/{html_rel}",
                )
        for attr in ("src", "href"):
            value = attrs.get(attr, "")
            if value.lower().startswith(("http://", "https://")):
                add("high", "external_resource", f"external resource requested: {value[:120]}", f"{ctx.fixture_rel}/{html_rel}")

    css_files = [e["path"] for e in ctx.fixture_entries if e["path"].lower().endswith(".css")]
    css_details: list[dict[str, Any]] = []
    for css_rel in css_files:
        css_text = _read(ctx, css_rel)
        has_mobile_query = bool(re.search(r"@media[^{]*max-width", css_text, re.IGNORECASE))
        for match in _WIDTH_RE.finditer(css_text):
            width = int(match.group(1))
            css_details.append({"file": css_rel, "width_px": width, "has_mobile_query": has_mobile_query})
            if width >= 900 and not has_mobile_query:
                add(
                    "medium",
                    "fixed_width_layout",
                    f"fixed width {width}px without a mobile media query",
                    f"{ctx.fixture_rel}/{css_rel}",
                )
    a11y_issues = [i for i in issues if i["kind"] in {"img_alt", "input_label", "non_semantic_control", "html_lang", "viewport_meta"}]
    details = {
        "html": html_rel,
        "issues": len(issues),
        "a11y_issues": len(a11y_issues),
        "css": css_details,
        "issue_list": issues,
    }
    return issues, details


def _copy_screenshots(ctx: PilotContext, workspace: Any, probe: dict[str, Any]) -> list[dict[str, Any]]:
    token = uuid.uuid4().hex[:12]
    directory = Path(ctx.store.root) / ".director" / "receipts" / f"website-{token}"
    copied: list[dict[str, Any]] = []
    for shot in (probe.get("screenshots") or [])[:4]:
        if not isinstance(shot, dict):
            continue
        name = Path(str(shot.get("name", "shot.png"))).name
        if not name.lower().endswith(".png"):
            continue
        try:
            data = safe_read_bytes(workspace.path(f"shots/{name}"), workspace.root, max_bytes=8 * 1024 * 1024)
        except (PathSafetyError, BoundsError, OSError):
            continue
        target = ensure_within(directory / name, Path(ctx.store.root))
        atomic_write_bytes(target, data, root=ctx.store.root)
        copied.append(
            {
                "name": name,
                "ref": target.relative_to(Path(ctx.store.root)).as_posix(),
                "sha256": sha256_bytes(data),
                "bytes": len(data),
            }
        )
    return copied


def evaluate(ctx: PilotContext) -> DomainResult:
    checks: list[Check] = []
    findings: list[FindingDraft] = []
    limitations = [
        "One controlled fixture and one headless browser engine; not a general website certification.",
        "Visual taste and screen-reader interoperability are not fully evaluated.",
        "Browser automation runs against file:// with network resolution disabled.",
    ]
    static_issues, static_details = _static_checks(ctx)
    static_failures = [i for i in static_issues if i["severity"] in {"critical", "high"}]
    checks.append(
        Check(
            criterion_key="website.static",
            description="static HTML/CSS checks find no critical accessibility or network issue",
            passed=not static_failures,
            details=static_details,
            subject_path=f"{ctx.fixture_rel}/{static_details.get('html') or ''}".rstrip("/"),
            subject_sha256=ctx.fixture_sha,
            confidence=0.9,
            limitations="static parsing is not a full HTML validator",
        )
    )
    for issue in static_issues:
        findings.append(
            FindingDraft(
                severity=issue["severity"],
                kind=issue["kind"],
                message=issue["message"],
                path=issue["path"],
                source_sha256=ctx.fixture_sha,
            )
        )

    node = shutil.which("node")
    browser = _find_browser()
    if not node or not browser:
        reason = "node is unavailable" if not node else "no Chromium-family browser found"
        for key, description in (
            ("website.journey", "real user journey completes"),
            ("website.keyboard", "keyboard reaches and activates the primary action"),
            ("website.mobile", "mobile viewport has no horizontal overflow"),
            ("website.network", "no external network requests"),
            ("website.a11y", "add control is a named button and search input is named"),
        ):
            checks.append(
                Check(
                    criterion_key=key,
                    description=description,
                    passed=False,
                    outcome="blocked",
                    details={"reason": reason},
                    subject_path=ctx.fixture_rel,
                    subject_sha256=ctx.fixture_sha,
                    limitations=reason,
                )
            )
        return DomainResult(
            status="blocked",
            checks=checks,
            findings=findings,
            limitations=limitations + [reason],
            resources={"node": bool(node), "browser": bool(browser)},
            blocked_reason=reason,
        )

    ctx.authorize("run_local_subprocess")
    ctx.authorize("launch_browser")
    workspace = ctx.create_workspace()
    probe: dict[str, Any] | None = None
    try:
        workspace.copy_tree(ctx.fixture_path, "site")
        probe_script = Path(__file__).resolve().parent.parent / "assets" / "browser_probe.mjs"
        workspace.copy_file(probe_script, "browser_probe.mjs")
        entry = "site/index.html"
        if not workspace.path(entry).is_file():
            html_files = [e["path"] for e in ctx.fixture_entries if e["path"].lower().endswith((".html", ".htm"))]
            if not html_files:
                return DomainResult(status="error", blocked_reason="no HTML entry point")
            entry = f"site/{html_files[0]}"
        run = ctx.runner.run(
            [
                node,
                "browser_probe.mjs",
                "--browser",
                browser,
                "--site",
                str(workspace.path(entry)),
                "--out",
                "probe.json",
                "--shot-dir",
                "shots",
                "--timeout",
                "25000",
            ],
            workspace,
            timeout=min(ctx.timeout_seconds, 90.0),
            max_output=256 * 1024,
            memory_mb=2048,
            cpu_seconds=90,
            env_extra={
                # Chromium refuses to start with a synthetic USERPROFILE; the
                # browser profile still lives in the disposable workspace and
                # network resolution is disabled.
                "USERPROFILE": os.environ.get("USERPROFILE", str(workspace.tmp)),
            },
        )
        probe_error: str | None = None
        try:
            probe = bounded_json_loads(
                safe_read_bytes(workspace.path("probe.json"), workspace.root, max_bytes=4 * 1024 * 1024),
                max_bytes=4 * 1024 * 1024,
            )
        except (PathSafetyError, BoundsError, ValidationError, OSError) as exc:
            probe = None
            probe_error = f"probe output unreadable: {type(exc).__name__}"
        if run.timed_out:
            limitations.append("browser probe timed out")
            return DomainResult(
                status="error",
                checks=checks,
                findings=findings,
                limitations=limitations,
                resources={"probe": run.to_dict(), "probe_output": probe},
                blocked_reason="browser probe timed out",
            )
        if not isinstance(probe, dict):
            limitations.append(probe_error or "browser probe produced no output")
            if run.stderr.strip():
                limitations.append("probe stderr: " + run.stderr.strip()[:300])
            return DomainResult(
                status="error",
                checks=checks,
                findings=findings,
                limitations=limitations,
                resources={"probe": run.to_dict()},
                blocked_reason="browser probe failed",
            )
        if not run.ok:
            limitations.append(f"browser probe exited {run.exit_code}: {str(probe.get('error', 'unknown'))[:200]}")
            return DomainResult(
                status="error",
                checks=checks,
                findings=findings,
                limitations=limitations,
                resources={"probe": run.to_dict(), "probe_output": probe},
                blocked_reason="browser probe failed",
            )
        if not probe.get("ok"):
            limitations.append("probe reported failure: " + str(probe.get("error", "unknown"))[:200])
            return DomainResult(
                status="error",
                checks=checks,
                findings=findings,
                limitations=limitations,
                resources={"probe": run.to_dict(), "probe_output": probe},
                blocked_reason="probe reported failure",
            )
        screenshots = _copy_screenshots(ctx, workspace, probe)
    finally:
        workspace.cleanup()

    journey = probe.get("journey") or {}
    keyboard = probe.get("keyboard") or {}
    mobile = probe.get("mobile") or {}
    desktop = probe.get("desktop") or {}
    network = probe.get("network") or {}
    accessibility = probe.get("accessibility") or {}
    console_errors = probe.get("console_errors") or []
    steps = journey.get("steps") or []
    failed_steps = [s for s in steps if isinstance(s, dict) and not s.get("ok")]
    details_common = {"steps": steps, "console_errors": console_errors[:20], "screenshots": screenshots}

    checks.append(
        Check(
            criterion_key="website.journey",
            description="search, add-to-cart and checkout complete in a real browser",
            passed=bool(journey.get("ok")) and bool(steps),
            details=details_common,
            subject_path=f"{ctx.fixture_rel}/index.html",
            subject_sha256=ctx.fixture_sha,
            confidence=0.95,
            limitations="single scripted journey; other flows untested",
        )
    )
    if not (journey.get("ok") and steps):
        findings.append(
            FindingDraft(
                severity="critical",
                kind="website_journey_broken",
                message="primary journey failed: " + ", ".join(str(s.get("name")) for s in failed_steps)[:300],
                path=f"{ctx.fixture_rel}/index.html",
                source_sha256=ctx.fixture_sha,
            )
        )
    if console_errors:
        findings.append(
            FindingDraft(
                severity="high",
                kind="website_console_error",
                message=f"{len(console_errors)} browser error(s): " + str(console_errors[0].get("text", ""))[:200],
                path=f"{ctx.fixture_rel}/app.js",
                source_sha256=ctx.fixture_sha,
                confidence=0.9,
            )
        )

    keyboard_ok = bool(keyboard.get("add_reachable") and keyboard.get("add_activated") and keyboard.get("checkout_reachable"))
    checks.append(
        Check(
            criterion_key="website.keyboard",
            description="keyboard focus reaches and activates the add-to-cart control",
            passed=keyboard_ok,
            details=keyboard,
            subject_path=f"{ctx.fixture_rel}/index.html",
            subject_sha256=ctx.fixture_sha,
            confidence=0.9,
            limitations="Tab/Enter only; no screen reader",
        )
    )
    if not keyboard_ok:
        findings.append(
            FindingDraft(
                severity="high",
                kind="website_keyboard",
                message="primary action is not reachable/activatable by keyboard",
                path=f"{ctx.fixture_rel}/index.html",
                source_sha256=ctx.fixture_sha,
            )
        )

    mobile_overflow = int(mobile.get("overflow_px") or 0)
    desktop_overflow = int(desktop.get("overflow_px") or 0)
    mobile_ok = mobile_overflow <= 1 and desktop_overflow <= 1
    checks.append(
        Check(
            criterion_key="website.mobile",
            description="390px and 1280px viewports have no horizontal overflow",
            passed=mobile_ok,
            details={"mobile": mobile, "desktop": desktop},
            subject_path=f"{ctx.fixture_rel}/styles.css",
            subject_sha256=ctx.fixture_sha,
            confidence=0.9,
        )
    )
    if not mobile_ok:
        findings.append(
            FindingDraft(
                severity="medium",
                kind="website_mobile_overflow",
                message=f"horizontal overflow {mobile_overflow}px at 390px viewport",
                path=f"{ctx.fixture_rel}/styles.css",
                source_sha256=ctx.fixture_sha,
            )
        )

    external = network.get("external_requests") or []
    network_ok = not external
    checks.append(
        Check(
            criterion_key="website.network",
            description="the page makes no external network requests",
            passed=network_ok,
            details=network,
            subject_path=f"{ctx.fixture_rel}/index.html",
            subject_sha256=ctx.fixture_sha,
            confidence=0.95,
        )
    )
    if external:
        findings.append(
            FindingDraft(
                severity="high",
                kind="website_external_network",
                message=f"{len(external)} external request(s); first: {str(external[0].get('url', ''))[:150]}",
                path=f"{ctx.fixture_rel}/index.html",
                source_sha256=ctx.fixture_sha,
            )
        )

    add_role = accessibility.get("add_role")
    search_name = accessibility.get("search_name")
    a11y_ok = add_role == "button" and bool(search_name) and not [i for i in static_issues if i["kind"] in {"img_alt", "input_label", "non_semantic_control"}]
    checks.append(
        Check(
            criterion_key="website.a11y",
            description="the add control has button role and the search input has an accessible name",
            passed=a11y_ok,
            details={
                "add_role": add_role,
                "add_name": accessibility.get("add_name"),
                "search_name": search_name,
                "search_role": accessibility.get("search_role"),
                "ax_node_count": len(accessibility.get("nodes") or []),
            },
            subject_path=f"{ctx.fixture_rel}/index.html",
            subject_sha256=ctx.fixture_sha,
            confidence=0.85,
            limitations="AX tree snapshot, not a screen-reader session",
        )
    )
    if not a11y_ok:
        findings.append(
            FindingDraft(
                severity="high",
                kind="website_a11y",
                message=f"accessibility roles/names incomplete (add role={add_role!r}, search name={search_name!r})",
                path=f"{ctx.fixture_rel}/index.html",
                source_sha256=ctx.fixture_sha,
            )
        )

    status = "pass" if all(check.passed for check in checks) else "fail"
    return DomainResult(
        status=status,
        checks=checks,
        findings=findings,
        limitations=limitations,
        resources={
            "node": node,
            "browser": browser,
            "screenshots": screenshots,
            "runtime_probe_ms": probe.get("runtime_ms"),
        },
        report={
            "static": static_details,
            "journey": journey,
            "keyboard": keyboard,
            "mobile": mobile,
            "desktop": desktop,
            "network": network,
            "console_errors": console_errors[:20],
            "accessibility": {
                "add_role": add_role,
                "add_name": accessibility.get("add_name"),
                "search_name": search_name,
                "node_count": len(accessibility.get("nodes") or []),
            },
            "screenshots": screenshots,
        },
    )
