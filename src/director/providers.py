"""Local-only model/provider gateway with policy and budget enforcement.

No cloud provider, credential or network path is enabled here. The stub provider
is a deterministic local test double; the command provider runs an owner-supplied
local command in the supervised runner (prompt as the last argument). Both are
default-denied unless the contract enables `model_call_local`, an owner grant
matches, and the model-call budget is available.
"""

from __future__ import annotations

import uuid
from typing import Any, Mapping, Sequence

from .policy import PolicyGateway
from .runner import Runner
from .security import (
    BoundsError,
    ValidationError,
    dump_bounded,
    estimate_tokens,
    redact_text,
    scan_secrets,
    sha256_text,
)
from .store import BudgetExceeded, Store, utc_now

PROVIDERS = ("stub", "command")
MAX_PROMPT_CHARS = 16_384
MAX_OUTPUT_CHARS = 32_768


def _limit(store: Store, unit: str) -> float:
    for row in store.budget_status():
        if row["unit"] == unit:
            return float(row["limit_amount"])
    return 0.0


def call_model(
    store: Store,
    prompt: str,
    provider: str = "stub",
    model: str | None = None,
    command: Sequence[str] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise ValidationError("unknown provider")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValidationError("prompt must not be empty")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise BoundsError("prompt exceeds the local model bound")
    if scan_secrets(prompt, max_hits=1):
        raise ValidationError("prompt contains secret-like content; refused")
    if provider == "command":
        if not command:
            raise ValidationError("command provider requires a command list")
        command = list(command)
        if len(command) > 64 or not all(isinstance(part, str) and 0 < len(part) <= 4096 for part in command):
            raise ValidationError("invalid command list")

    latest = store.latest_contract()
    if not latest:
        raise ValidationError("no task contract saved")
    revision = int(latest[0]["revision"])
    policy = PolicyGateway(store)
    payload = {"prompt_sha256": sha256_text(prompt), "provider": provider, "model": model or ""}
    policy.require("director.model", "model_call_local", f"provider:{provider}", revision, payload=payload)

    input_tokens = estimate_tokens(prompt)
    output_reserve = 1024
    reservations: list[str] = []
    try:
        reservations.append(store.reserve_budget("model_calls", 1, revision, note=f"model:{provider}"))
        if _limit(store, "input_tokens") > 0:
            reservations.append(store.reserve_budget("input_tokens", input_tokens, revision, note="model input"))
        if _limit(store, "output_tokens") > 0:
            reservations.append(store.reserve_budget("output_tokens", output_reserve, revision, note="model output"))
    except BudgetExceeded:
        for reservation in reservations:
            store.release_reservation(reservation)
        raise

    event_payload: dict[str, Any] = {
        "provider": provider,
        "model": model or provider,
        "prompt_sha256": payload["prompt_sha256"],
        "input_tokens_estimate": input_tokens,
        "started_at": utc_now(),
    }
    try:
        if provider == "stub":
            output = f"[stub:{model or 'default'}] " + prompt[:280]
            limitations = "deterministic local stub; not a real model"
        else:
            runner = Runner(default_timeout=timeout, default_max_output=128 * 1024)
            workspace = runner.create_workspace()
            try:
                result = runner.run(
                    [*command, prompt],
                    workspace,
                    timeout=timeout,
                    max_output=128 * 1024,
                    memory_mb=512,
                    cpu_seconds=60,
                )
            finally:
                workspace.cleanup()
            if not result.ok:
                raise ValidationError("command provider failed")
            output = result.stdout.strip()
            limitations = (
                "owner-supplied local command; process-level supervision, not a sandbox; "
                "the command itself must not be trusted with network/secret access"
            )
        output = redact_text(output)[:MAX_OUTPUT_CHARS]
        output_tokens = estimate_tokens(output)
        if output_tokens > output_reserve and _limit(store, "output_tokens") > 0:
            # Do not exceed the reservation; record the overrun as a limitation.
            output_tokens = output_reserve
        for index, reservation in enumerate(reservations):
            unit = store.conn.execute(
                "SELECT unit FROM budget_reservations WHERE id=?", (reservation,)
            ).fetchone()["unit"]
            actual = 1 if unit == "model_calls" else (input_tokens if unit == "input_tokens" else output_tokens)
            store.settle_reservation(reservation, actual)
        event_payload.update(
            {
                "output_sha256": sha256_text(output),
                "output_tokens_estimate": output_tokens,
                "outcome": "ok",
                "finished_at": utc_now(),
            }
        )
        event_id = store.record_event("model.call", f"model:{uuid.uuid4().hex}", event_payload)
        return {
            "provider": provider,
            "model": model or provider,
            "output": output,
            "usage": {
                "model_calls": 1,
                "input_tokens_estimate": input_tokens,
                "output_tokens_estimate": output_tokens,
                "cost_usd": 0.0,
            },
            "event_id": event_id,
            "prompt_sha256": payload["prompt_sha256"],
            "limitations": limitations,
        }
    except Exception:
        for reservation in reservations:
            try:
                store.release_reservation(reservation)
            except Exception:
                pass
        event_payload.update({"outcome": "error", "finished_at": utc_now()})
        try:
            store.record_event("model.call", f"model:{uuid.uuid4().hex}", event_payload)
        except Exception:
            pass
        raise
