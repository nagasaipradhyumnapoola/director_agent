from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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


def test_openai_compatible_loopback_provider(tmp_path):
    store = _store(tmp_path)
    responses = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            responses.append(body)
            payload = json.dumps(
                {
                    "choices": [{"message": {"content": "MOCK"}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 3},
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        PolicyGateway(store).grant("director.model", "model_call_local", "provider:openai_compatible", 1)
        result = call_model(
            store,
            "hello",
            provider="openai_compatible",
            model="mock-model",
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            max_tokens=16,
            price_input_per_million=1.0,
            price_output_per_million=2.0,
            timeout=30,
        )
        assert result["output"] == "MOCK"
        assert result["usage"]["input_tokens"] == 12
        assert result["usage"]["output_tokens"] == 3
        assert result["usage"]["cost_usd"] > 0
        assert responses and responses[0]["model"] == "mock-model"
    finally:
        server.shutdown()
        server.server_close()
        store.close()


def test_openai_loopback_uses_keychain_secret(tmp_path, monkeypatch):
    store = _store(tmp_path)
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["auth"] = self.headers.get("Authorization", "")
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            payload = json.dumps(
                {"choices": [{"message": {"content": "OK"}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr("director.providers.get_secret", lambda *_a, **_k: "loopback-key")
    try:
        PolicyGateway(store).grant("director.model", "model_call_local", "provider:openai_compatible", 1)
        result = call_model(
            store,
            "hello",
            provider="openai_compatible",
            model="mock-model",
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            api_key_secret="provider/mock",
            max_tokens=16,
            timeout=30,
        )
        assert result["output"] == "OK"
        assert seen["auth"] == "Bearer loopback-key"
    finally:
        server.shutdown()
        server.server_close()
        store.close()


def test_openai_external_endpoint_is_policy_denied_without_network(tmp_path):
    store = _store(tmp_path)
    try:
        PolicyGateway(store).grant("director.model", "model_call_local", "provider:openai_compatible", 1)
        with pytest.raises(PolicyDenied):
            call_model(
                store,
                "hello",
                provider="openai_compatible",
                model="mock-model",
                base_url="https://example.com/v1",
            )
        assert store.model_calls_spent() == 0
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
