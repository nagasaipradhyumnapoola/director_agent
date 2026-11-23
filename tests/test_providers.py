from __future__ import annotations

import sys

import pytest

from director.models import Budgets, PermissionPolicy
from director.policy import PolicyDenied, PolicyGateway
from director.providers import call_model
from director.security import ValidationError
from director.store import BudgetExceeded
from tests.helpers import new_store


def _store(tmp_path):
    return new_store(
        tmp_path,
        permissions=PermissionPolicy(allowed_actions=("read_artifact", "model_call_local")),
        budgets=Budgets(max_model_calls=2, max_wall_seconds=60),
    )


def test_local_model_default_denied(tmp_path):
    store = _store(tmp_path)
    try:
        with pytest.raises(PolicyDenied):
            call_model(store, "hello")
        assert store.model_calls_spent() == 0
    finally:
        store.close()


def test_stub_model_requires_owner_grant_and_budget(tmp_path):
    store = _store(tmp_path)
    try:
        PolicyGateway(store).grant("director.model", "model_call_local", "provider:stub", 1)
        result = call_model(store, "hello local model")
        assert "hello local model" in result["output"]
        assert result["usage"]["model_calls"] == 1
        assert store.model_calls_spent() == 1
        events = store.pending_events()
        assert any(event["type"] == "model.call" for event in events)
        second = call_model(store, "second call")
        assert second["provider"] == "stub"
        with pytest.raises(BudgetExceeded):
            call_model(store, "third call")
    finally:
        store.close()


def test_command_provider_runs_scrubbed_local_command(tmp_path):
    store = _store(tmp_path)
    try:
        PolicyGateway(store).grant("director.model", "model_call_local", "provider:command", 1)
        result = call_model(
            store,
            "hello",
            provider="command",
            model="local-test",
            command=[sys.executable, "-c", "import sys; print(sys.argv[-1].upper())"],
            timeout=30,
        )
        assert result["output"].strip() == "HELLO"
        assert result["usage"]["model_calls"] == 1
        assert store.model_calls_spent() == 1
    finally:
        store.close()


def test_secret_like_prompt_is_refused_before_call(tmp_path):
    store = _store(tmp_path)
    try:
        PolicyGateway(store).grant("director.model", "model_call_local", "provider:stub", 1)
        with pytest.raises(ValidationError):
            call_model(store, "aws AKIAABCDEFGHIJKLMNOP")
        assert store.model_calls_spent() == 0
    finally:
        store.close()
