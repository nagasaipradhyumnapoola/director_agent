"""Local-only model/provider gateway with policy and budget enforcement.

No cloud provider, credential or network path is enabled here. The stub provider
is a deterministic local test double; the command provider runs an owner-supplied
local command in the supervised runner (prompt as the last argument). Both are
default-denied unless the contract enables `model_call_local`, an owner grant
matches, and the model-call budget is available.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
import uuid
from typing import Any, Mapping, Sequence

from .keychain import KeychainUnavailable, get_secret
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

PROVIDERS = ("stub", "command", "ollama", "openai_compatible")
MAX_PROMPT_CHARS = 28_000
MAX_OUTPUT_CHARS = 32_768
MAX_HTTP_RESPONSE = 8 * 1024 * 1024
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _ollama_base() -> str:
    raw = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").strip()
    if not raw.startswith(("http://", "https://")):
        raw = "http://" + raw
    parsed = urllib.parse.urlparse(raw)
    if parsed.hostname not in LOCAL_HOSTS:
        raise ValidationError("ollama endpoint must be loopback/local only")
    return raw.rstrip("/")


def _openai_generate(
    base_url: str,
    model: str,
    prompt: str,
    api_key: str | None,
    max_tokens: int,
    timeout: float,
) -> dict[str, Any]:
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.15,
            "max_tokens": max_tokens,
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=payload,
        headers=headers,
        method="POST",
    )
    opener = urllib.request.build_opener()
    try:
        with opener.open(request, timeout=min(max(timeout, 5.0), 600.0)) as response:
            data = response.read(MAX_HTTP_RESPONSE + 1)
    except Exception as exc:  # noqa: BLE001
        raise ValidationError("OpenAI-compatible request failed") from exc
    if len(data) > MAX_HTTP_RESPONSE:
        raise BoundsError("provider response exceeds bound")
    try:
        parsed = json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise ValidationError("provider response was not JSON") from exc
    if not isinstance(parsed, dict):
        raise ValidationError("provider response was not an object")
    return parsed


def _ollama_generate(base: str, model: str, prompt: str, timeout: float) -> dict[str, Any]:
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.15, "num_predict": 4096},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        base + "/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=min(max(timeout, 5.0), 600.0)) as response:
            data = response.read(MAX_HTTP_RESPONSE + 1)
    except Exception as exc:  # noqa: BLE001
        raise ValidationError("local ollama request failed") from exc
    if len(data) > MAX_HTTP_RESPONSE:
        raise BoundsError("ollama response exceeds bound")
    try:
        parsed = json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise ValidationError("ollama response was not JSON") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("response"), str):
        raise ValidationError("ollama response missing text")
    return parsed


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
    base_url: str | None = None,
    api_key_secret: str | None = None,
    max_tokens: int = 4096,
    price_input_per_million: float = 0.0,
    price_output_per_million: float = 0.0,
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
    api_key: str | None = None
    base = base_url
    if provider == "openai_compatible":
        if not base or not model:
            raise ValidationError("openai_compatible requires base_url and model")
        parsed_url = urllib.parse.urlparse(base)
        if parsed_url.scheme not in ("http", "https") or not parsed_url.hostname:
            raise ValidationError("invalid base_url")
        local_provider = parsed_url.hostname in LOCAL_HOSTS
        action = "model_call_local" if local_provider else "model_call"
    else:
        local_provider = True
        action = "model_call_local"
    payload = {
        "prompt_sha256": sha256_text(prompt),
        "provider": provider,
        "model": model or "",
        "base_url": base or "",
    }
    policy.require("director.model", action, f"provider:{provider}", revision, payload=payload)
    if provider == "openai_compatible" and not local_provider:
        if not api_key_secret:
            raise ValidationError("external provider requires api_key_secret")
        try:
            api_key = get_secret(store.project_id, api_key_secret)
        except KeychainUnavailable as exc:
            raise ValidationError("OS keychain unavailable") from exc
        if not api_key:
            raise ValidationError("provider credential not found in OS keychain")

    input_tokens = estimate_tokens(prompt)
    output_reserve = max_tokens if provider == "openai_compatible" else (4096 if provider == "ollama" else 1024)
    estimated_cost = (
        input_tokens / 1_000_000 * max(price_input_per_million, 0.0)
        + output_reserve / 1_000_000 * max(price_output_per_million, 0.0)
    )
    reservations: list[str] = []
    try:
        reservations.append(store.reserve_budget("model_calls", 1, revision, note=f"model:{provider}"))
        if _limit(store, "input_tokens") > 0:
            reservations.append(store.reserve_budget("input_tokens", input_tokens, revision, note="model input"))
        if _limit(store, "output_tokens") > 0:
            reservations.append(store.reserve_budget("output_tokens", output_reserve, revision, note="model output"))
        if estimated_cost > 0 and _limit(store, "cost_usd") > 0:
            reservations.append(store.reserve_budget("cost_usd", estimated_cost, revision, note="model cost"))
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
    actual_input = input_tokens
    actual_output: int | None = None
    cost_actual = 0.0
    try:
        if provider == "stub":
            output = f"[stub:{model or 'default'}] " + prompt[:280]
            limitations = "deterministic local stub; not a real model"
        elif provider == "ollama":
            if not model:
                raise ValidationError("ollama requires a model name")
            try:
                parsed = _ollama_generate(_ollama_base(), model, prompt, timeout)
            except ValidationError:
                raise
            output = str(parsed.get("response") or "")
            actual_output = int(parsed.get("eval_count") or estimate_tokens(output))
            actual_input = int(parsed.get("prompt_eval_count") or input_tokens)
            limitations = (
                "local Ollama model; loopback HTTP only; output is untrusted and "
                "cannot certify its own work"
            )
        elif provider == "openai_compatible":
            parsed = _openai_generate(
                str(base),
                str(model),
                prompt,
                api_key,
                max_tokens,
                timeout,
            )
            try:
                output = str(parsed["choices"][0]["message"]["content"])
            except (KeyError, IndexError, TypeError) as exc:
                raise ValidationError("provider response missing content") from exc
            usage = parsed.get("usage") if isinstance(parsed.get("usage"), dict) else {}
            actual_input = int(usage.get("prompt_tokens") or input_tokens)
            actual_output = int(usage.get("completion_tokens") or estimate_tokens(output))
            cost_actual = (
                actual_input / 1_000_000 * max(price_input_per_million, 0.0)
                + actual_output / 1_000_000 * max(price_output_per_million, 0.0)
            )
            limitations = (
                "OpenAI-compatible endpoint; output untrusted; "
                + ("loopback/local" if local_provider else "external network with owner grant")
            )
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
        if actual_output is None:
            actual_output = estimate_tokens(output)
        if actual_output > output_reserve and _limit(store, "output_tokens") > 0:
            # The local provider may exceed the reserved estimate; record the
            # overrun rather than silently pretending it was free.
            limitations += f"; output token overrun {actual_output - output_reserve}"
        for reservation in reservations:
            unit = store.conn.execute(
                "SELECT unit FROM budget_reservations WHERE id=?", (reservation,)
            ).fetchone()["unit"]
            if unit == "model_calls":
                actual = 1
            elif unit == "input_tokens":
                actual = actual_input
            elif unit == "output_tokens":
                actual = actual_output
            else:
                actual = cost_actual
            store.settle_reservation(reservation, actual)
        event_payload.update(
            {
                "output_sha256": sha256_text(output),
                "input_tokens_actual": actual_input,
                "output_tokens_actual": actual_output,
                "cost_usd_actual": round(cost_actual, 8),
                "outcome": "ok",
                "finished_at": utc_now(),
            }
        )
        event_id = store.record_event("model.call", f"model:{uuid.uuid4().hex}", event_payload)
        try:
            from . import audit

            audit.log(
                store,
                "director.model",
                "model.call",
                f"provider:{provider}",
                "ok" if provider == "stub" else "ok",
                {"model": model or provider, "cost_usd": round(cost_actual, 8)},
            )
        except Exception:
            pass
        return {
            "provider": provider,
            "model": model or provider,
            "output": output,
            "usage": {
                "model_calls": 1,
                "input_tokens": actual_input,
                "output_tokens": actual_output,
                "cost_usd": round(cost_actual, 8),
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
