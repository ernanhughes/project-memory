"""Deterministic tests for the OpenCode/Muse provider (mocked HTTP only).

No test here may make a live or paid API call: every test that
touches the network monkeypatches ``urllib.request.urlopen``.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from providers import opencode as OC


class FakeHeaders(dict):
    def items(self):  # noqa: D102 - dict behaviour is the point
        return super().items()


class FakeResponse:
    def __init__(self, payload, status=200, headers=None):
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload)
        self._raw = payload.encode() if isinstance(payload, str) else payload
        self.status = status
        self.headers = FakeHeaders(headers or {})

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _install(monkeypatch, handler):
    calls: list = []

    def fake_urlopen(request, timeout=None):
        calls.append(request)
        return handler(request, timeout, calls)

    monkeypatch.setattr(OC.urllib.request, "urlopen", fake_urlopen)
    return calls


def _ok(payload, status=200, headers=None):
    def handler(request, timeout, calls):
        return FakeResponse(payload, status=status, headers=headers)

    return handler


# -- API key resolution ------------------------------------------------


def test_key_resolution_order(monkeypatch):
    for var in (
        "MEMORY_OPENCODE_API_KEY",
        "OPENCODE_ZEN_API_KEY",
        "WRITER_OPENCODE_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    assert OC.resolve_api_key() is None

    monkeypatch.setenv("WRITER_OPENCODE_API_KEY", "w-key")
    monkeypatch.setenv("OPENCODE_ZEN_API_KEY", "z-key")
    assert OC.resolve_api_key() == "z-key"

    monkeypatch.setenv("MEMORY_OPENCODE_API_KEY", "m-key")
    assert OC.resolve_api_key() == "m-key"

    assert OC.resolve_api_key(explicit="e-key") == "e-key"


def test_missing_key_returns_error_without_http(monkeypatch):
    for var in (
        "MEMORY_OPENCODE_API_KEY",
        "OPENCODE_ZEN_API_KEY",
        "WRITER_OPENCODE_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    calls = _install(monkeypatch, _ok({"output_text": "READY"}))
    result = OC.OpenCodeModel(api_key=None).generate("hi", max_tokens=64)
    assert result["response"] == ""
    assert result["error_type"] == "missing_api_key"
    assert result["attempts"] == 0
    assert calls == []


def test_is_available_false_without_key_and_never_raises(monkeypatch):
    for var in (
        "MEMORY_OPENCODE_API_KEY",
        "OPENCODE_ZEN_API_KEY",
        "WRITER_OPENCODE_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    assert OC.OpenCodeModel().is_available() is False


# -- base URL / model / reasoning --------------------------------------


def test_base_url_normalization_and_env_override(monkeypatch):
    monkeypatch.delenv("MEMORY_OPENCODE_BASE_URL", raising=False)
    assert (
        OC.OpenCodeModel(base_url="https://opencode.ai/zen/go/").responses_url
        == "https://opencode.ai/zen/go/v1/responses"
    )
    monkeypatch.setenv("MEMORY_OPENCODE_BASE_URL", "https://example.test/gw///")
    assert (
        OC.OpenCodeModel().responses_url == "https://example.test/gw/v1/responses"
    )
    assert OC.OpenCodeModel(base_url="https://x.test").base_url == "https://x.test"


def test_model_and_reasoning_resolution(monkeypatch):
    monkeypatch.delenv("MEMORY_MUSE_MODEL", raising=False)
    monkeypatch.delenv("MEMORY_OPENCODE_REASONING_EFFORT", raising=False)
    assert OC.resolve_model() == "muse-spark-1.3-contributor"
    assert OC.resolve_reasoning_effort() == "low"
    monkeypatch.setenv("MEMORY_MUSE_MODEL", "other-model")
    monkeypatch.setenv("MEMORY_OPENCODE_REASONING_EFFORT", "medium")
    assert OC.resolve_model() == "other-model"
    assert OC.resolve_reasoning_effort() == "medium"
    assert OC.resolve_model(explicit="explicit-m") == "explicit-m"


# -- response parsing ---------------------------------------------------


def _payload_response(monkeypatch, payload):
    monkeypatch.setenv("MEMORY_OPENCODE_API_KEY", "test-key")
    _install(monkeypatch, _ok(payload))
    return OC.OpenCodeModel().generate("hi")


def test_output_text_direct(monkeypatch):
    result = _payload_response(monkeypatch, {"output_text": "  READY  "})
    assert result["response"] == "  READY  ".strip()


def test_nested_output_message_parsing(monkeypatch):
    payload = {
        "output": [
            {"type": "reasoning", "content": [{"type": "text", "text": "NO"}]},
            "not-a-dict",
            {"type": "message", "content": "not-a-list"},
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "READY"},
                    {"type": "text", "text": "!"},
                    {"type": "other", "text": "IGNORE"},
                    {"type": "output_text", "text": None},
                ],
            },
        ]
    }
    assert _payload_response(monkeypatch, payload)["response"] == "READY!"


def test_empty_output_contract_single_attempt_without_budget(monkeypatch):
    monkeypatch.setenv("MEMORY_OPENCODE_API_KEY", "test-key")
    calls = _install(monkeypatch, _ok({"output": []}))
    result = OC.OpenCodeModel().generate("hi")
    assert result["response"] == ""
    assert result["error_type"] == "empty_output"
    assert result["attempts"] == 1
    assert len(calls) == 1


def test_empty_output_retries_once_with_doubled_budget(monkeypatch):
    monkeypatch.setenv("MEMORY_OPENCODE_API_KEY", "test-key")
    budgets: list = []

    def handler(request, timeout, calls):
        budgets.append(json.loads(request.data.decode())["max_output_tokens"])
        if len(calls) == 1:
            return FakeResponse({"output": []})
        return FakeResponse({"output_text": "READY"})

    _install(monkeypatch, handler)
    result = OC.OpenCodeModel().generate("hi", max_tokens=256)
    assert result["response"] == "READY"
    assert result["attempts"] == 2
    assert budgets == [256, 512]
    assert result["request"]["max_output_tokens"] == 512


def test_persistent_empty_output_reports_last_budget(monkeypatch):
    monkeypatch.setenv("MEMORY_OPENCODE_API_KEY", "test-key")
    calls = _install(monkeypatch, _ok({"output": []}))
    result = OC.OpenCodeModel().generate("hi", max_tokens=100)
    assert result["response"] == ""
    assert result["error_type"] == "empty_output"
    assert result["attempts"] == 2
    assert len(calls) == 2
    assert result["request"]["max_output_tokens"] == 200


# -- usage --------------------------------------------------------------


def test_usage_normalization(monkeypatch):
    payload = {
        "output_text": "READY",
        "usage": {
            "input_tokens": 120,
            "output_tokens": 30,
            "total_tokens": 150,
            "input_tokens_details": {"cached_tokens": 40},
            "output_tokens_details": {"reasoning_tokens": 12},
        },
    }
    result = _payload_response(monkeypatch, payload)
    assert result["usage"] == {
        "input_tokens": 120,
        "cached_input_tokens": 40,
        "output_tokens": 30,
        "reasoning_tokens": 12,
        "total_tokens": 150,
    }
    assert result["prompt_eval_count"] == 120
    assert result["eval_count"] == 30


def test_usage_missing_fields_default_to_zero(monkeypatch):
    result = _payload_response(monkeypatch, {"output_text": "READY"})
    assert result["usage"] == {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
    }


def test_usage_total_falls_back_to_sum(monkeypatch):
    result = _payload_response(
        monkeypatch,
        {"output_text": "x", "usage": {"input_tokens": 5, "output_tokens": 7}},
    )
    assert result["usage"]["total_tokens"] == 12


# -- failure contract ---------------------------------------------------


def _http_error(url="https://opencode.ai/zen/go/v1/responses", code=500):
    body = io.BytesIO(json.dumps({"error": {"message": "boom"}}).encode())
    headers = FakeHeaders(
        {"Retry-After": "7", "X-RateLimit-Remaining": "0", "Content-Type": "json"}
    )
    return urllib.error.HTTPError(url, code, "Server Error", headers, body)


def test_http_error_structure_hides_secrets(monkeypatch):
    monkeypatch.setenv("MEMORY_OPENCODE_API_KEY", "super-secret-key")

    def handler(request, timeout, calls):
        raise _http_error(code=500)

    _install(monkeypatch, handler)
    result = OC.OpenCodeModel().generate("hi", max_tokens=64)
    assert result["response"] == ""
    assert result["error_type"] == "http_error"
    assert result["status_code"] == 500
    assert result["retry_after"] == "7"
    assert result["rate_limit_headers"] == {
        "Retry-After": "7",
        "X-RateLimit-Remaining": "0",
    }
    assert result["error_payload"] == {"error": {"message": "boom"}}
    blob = json.dumps(result)
    assert "super-secret-key" not in blob


def test_rate_limit_error_type(monkeypatch):
    monkeypatch.setenv("MEMORY_OPENCODE_API_KEY", "k")

    def handler(request, timeout, calls):
        raise _http_error(code=429)

    _install(monkeypatch, handler)
    result = OC.OpenCodeModel().generate("hi")
    assert result["response"] == ""
    assert result["error_type"] == "rate_limited"
    assert result["status_code"] == 429


def test_network_error_never_becomes_prose(monkeypatch):
    monkeypatch.setenv("MEMORY_OPENCODE_API_KEY", "k")

    def handler(request, timeout, calls):
        raise urllib.error.URLError("connection refused")

    _install(monkeypatch, handler)
    result = OC.OpenCodeModel().generate("hi")
    assert result["response"] == ""
    assert result["error_type"] == "network"
    assert "unavailable" in result["error"].lower()


def test_invalid_response_when_payload_is_not_an_object(monkeypatch):
    monkeypatch.setenv("MEMORY_OPENCODE_API_KEY", "k")
    _install(monkeypatch, _ok(["not", "a", "dict"]))
    result = OC.OpenCodeModel().generate("hi")
    assert result["response"] == ""
    assert result["error_type"] == "invalid_response"


# -- request recording --------------------------------------------------


def test_temperature_default_zero_and_recorded(monkeypatch):
    monkeypatch.setenv("MEMORY_OPENCODE_API_KEY", "k")
    seen: dict = {}

    def handler(request, timeout, calls):
        seen.update(json.loads(request.data.decode()))
        return FakeResponse({"output_text": "READY"})

    _install(monkeypatch, handler)
    result = OC.OpenCodeModel().generate("hi", max_tokens=64)
    assert seen["temperature"] == 0.0
    assert seen["reasoning"] == {"effort": "low"}
    assert seen["model"] == "muse-spark-1.3-contributor"
    assert result["request"]["temperature"] == 0.0
    assert result["request"]["reasoning_effort"] == "low"
    assert "Bearer" not in json.dumps(result)


def test_session_header_only_when_given(monkeypatch):
    monkeypatch.setenv("MEMORY_OPENCODE_API_KEY", "k")
    seen_headers: list = []

    def handler(request, timeout, calls):
        # Unredirected header access preserves original casing.
        seen_headers.append(request.get_header("X-opencode-session"))
        return FakeResponse({"output_text": "READY"})

    calls = _install(monkeypatch, handler)
    OC.OpenCodeModel().generate("hi", session_id="sess-1")
    OC.OpenCodeModel().generate("hi")
    assert seen_headers[0] == "sess-1"
    assert seen_headers[1] is None
    assert len(calls) == 2


def test_constructor_session_used_unless_overridden(monkeypatch):
    monkeypatch.setenv("MEMORY_OPENCODE_API_KEY", "k")
    seen: list = []

    def handler(request, timeout, calls):
        seen.append(request.get_header("X-opencode-session"))
        return FakeResponse({"output_text": "READY"})

    _install(monkeypatch, handler)
    OC.OpenCodeModel(session_id="run-session").generate("hi")
    OC.OpenCodeModel(session_id="run-session").generate(
        "hi", session_id="call-session")
    assert seen == ["run-session", "call-session"]


def test_new_session_id_format():
    first = OC.new_session_id("memory-sr1")
    second = OC.new_session_id("memory-sr1")
    assert first.startswith("memory-sr1-")
    assert first != second


def test_is_available_success_and_failure(monkeypatch):
    monkeypatch.setenv("MEMORY_OPENCODE_API_KEY", "k")
    urls: list = []

    def handler(request, timeout, calls):
        urls.append(request.full_url)
        return FakeResponse({}, status=200)

    _install(monkeypatch, handler)
    assert OC.OpenCodeModel().is_available() is True
    assert urls == ["https://opencode.ai/zen/go/v1/models"]

    def failing(request, timeout, calls):
        raise urllib.error.URLError("down")

    _install(monkeypatch, failing)
    assert OC.OpenCodeModel().is_available() is False


def test_user_agent_is_memory_not_writer(monkeypatch):
    monkeypatch.setenv("MEMORY_OPENCODE_API_KEY", "k")
    agents: list = []

    def handler(request, timeout, calls):
        agents.append(request.get_header("User-agent"))
        return FakeResponse({"output_text": "READY"})

    _install(monkeypatch, handler)
    OC.OpenCodeModel().generate("hi")
    assert agents[0] == "MemoryBook OpenCodeClient"
    assert "Writer" not in agents[0]
