# solution/providers/opencode.py
"""Muse Spark via the OpenCode Zen/Go Responses API (stdlib-only).

Adapted from the working Writer reference client
(``writer_ai/models/opencode.py``) so Memory stays independently
runnable: no dependency on the Writer package and no third-party
HTTP library — plain :mod:`urllib` only.

Design principles (preserved from the reference):

- plain requests, no state in the client;
- transport/provider failures returned through ``error`` so a
  diagnostic sentence can never be mistaken for reader prose;
- reasoning-capable models may consume part of the output budget
  as reasoning tokens, so one retry with a doubled budget follows
  a successful HTTP response that carries no assistant text.

Environment resolution order (documented, never committed)::

    explicit argument
    MEMORY_OPENCODE_API_KEY
    OPENCODE_ZEN_API_KEY
    WRITER_OPENCODE_API_KEY   (convenience fallback only)

Authentication headers are never written to logs, caches, or
frozen experiment artifacts.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://opencode.ai/zen/go"
DEFAULT_MODEL = "muse-spark-1.3-contributor"
DEFAULT_REASONING_EFFORT = "low"
#: Experimental default: maximum reproducibility for reader transfer.
DEFAULT_TEMPERATURE = 0.0
USER_AGENT = "MemoryBook OpenCodeClient"
EMPTY_OUTPUT_ERROR_TYPE = "empty_output"

_ERROR_BODY_LIMIT = 2000


def resolve_api_key(explicit: Optional[str] = None) -> Optional[str]:
    """Resolve the API key without ever printing or storing it."""
    if explicit:
        return explicit
    return (
        os.environ.get("MEMORY_OPENCODE_API_KEY")
        or os.environ.get("OPENCODE_ZEN_API_KEY")
        or os.environ.get("WRITER_OPENCODE_API_KEY")
    )


def resolve_base_url(explicit: Optional[str] = None) -> str:
    """Resolve the gateway base URL (no ``/v1/...`` suffix)."""
    raw = explicit or os.environ.get("MEMORY_OPENCODE_BASE_URL") or DEFAULT_BASE_URL
    return raw.rstrip("/") or DEFAULT_BASE_URL


def resolve_model(explicit: Optional[str] = None) -> str:
    """Resolve the model name; never silently substitute at call time."""
    return explicit or os.environ.get("MEMORY_MUSE_MODEL") or DEFAULT_MODEL


def resolve_reasoning_effort(explicit: Optional[str] = None) -> str:
    """Resolve reasoning effort; fixed per comparison (default ``low``)."""
    return (
        explicit
        or os.environ.get("MEMORY_OPENCODE_REASONING_EFFORT")
        or DEFAULT_REASONING_EFFORT
    )


def new_session_id(prefix: str = "memory") -> str:
    """Generate a stable-per-run routing session id.

    The Go gateway requires ``x-opencode-session`` for routing (and
    uses it for prompt-cache affinity). It carries no conversation
    state: every request still sends its full input with no
    chaining, so paired conditions stay independent.
    """
    import uuid

    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def extract_response_text(payload: Dict[str, Any]) -> str:
    """Extract assistant text from a Responses API payload."""
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    parts: list[str] = []
    output = payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") in ("output_text", "text"):
                    text = block.get("text")
                    if isinstance(text, str) and text:
                        parts.append(text)
    return "".join(parts)


def extract_usage(payload: Dict[str, Any]) -> Dict[str, int]:
    """Normalise Responses API usage; preserve nothing secret."""
    usage = payload.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}

    input_details = usage.get("input_tokens_details") or {}
    if not isinstance(input_details, dict):
        input_details = {}

    output_details = usage.get("output_tokens_details") or {}
    if not isinstance(output_details, dict):
        output_details = {}

    input_tokens = _as_int(usage.get("input_tokens"))
    output_tokens = _as_int(usage.get("output_tokens"))
    total_tokens = _as_int(usage.get("total_tokens")) or input_tokens + output_tokens

    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": _as_int(input_details.get("cached_tokens")),
        "output_tokens": output_tokens,
        "reasoning_tokens": _as_int(output_details.get("reasoning_tokens")),
        "total_tokens": total_tokens,
    }


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_headers(headers: Any) -> Dict[str, str]:
    try:
        items = dict(headers.items()) if hasattr(headers, "items") else dict(headers)
    except Exception:
        return {}
    return {str(k): str(v) for k, v in items.items()}


def _rate_limit_headers(headers: Dict[str, str]) -> Dict[str, str]:
    return {
        k: v
        for k, v in headers.items()
        if "rate" in k.lower() or "limit" in k.lower() or "retry" in k.lower()
    }


class OpenCodeModel:
    """Minimal OpenCode (Zen / Go) reader over the Responses API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
        # Construction never raises for a missing key and never
        # performs I/O; availability is checked via is_available().
        self.base_url = resolve_base_url(base_url)
        self.api_key = api_key
        self.reasoning_effort = resolve_reasoning_effort(reasoning_effort)
        # Routing session for the Go gateway (required; routing and
        # cache affinity only — requests stay stateless, no chaining).
        self.session_id = session_id

    @property
    def responses_url(self) -> str:
        return f"{self.base_url}/v1/responses"

    def _headers(self, session_id: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {resolve_api_key(self.api_key)}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        if session_id:
            headers["x-opencode-session"] = session_id
        return headers

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        timeout_seconds: int = 600,
        reasoning_effort: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate via POST ``{base_url}/v1/responses``.

        Success returns ``response`` plus normalised ``usage``.
        Every failure returns ``response == ""`` with ``error`` and
        ``error_type`` — never reader prose.
        """
        name = resolve_model(model)
        effort = resolve_reasoning_effort(
            reasoning_effort if reasoning_effort is not None else self.reasoning_effort
        )
        api_key = resolve_api_key(self.api_key)
        if not api_key:
            message = (
                "OpenCode API key not configured. Set MEMORY_OPENCODE_API_KEY "
                "or OPENCODE_ZEN_API_KEY."
            )
            logger.warning(message)
            return {
                "response": "",
                "error": message,
                "error_type": "missing_api_key",
                "model": name,
                "attempts": 0,
            }

        body: Dict[str, Any] = {
            "model": name,
            "input": prompt,
            "reasoning": {"effort": effort},
        }
        requested_max_tokens = int(max_tokens) if max_tokens is not None else None
        if requested_max_tokens is not None:
            body["max_output_tokens"] = requested_max_tokens
        if temperature is not None:
            body["temperature"] = float(temperature)

        def request_info(attempts: int, budget: Optional[int]) -> Dict[str, Any]:
            return {
                "model": name,
                "temperature": float(temperature) if temperature is not None else None,
                "reasoning_effort": effort,
                "max_output_tokens": budget,
                "attempts": attempts,
                # Host only — never credentials.
                "url": self.responses_url,
            }

        url = self.responses_url
        active_session = (session_id if session_id is not None
                          else self.session_id)
        headers = self._headers(active_session)
        attempts = 2 if requested_max_tokens is not None else 1
        last_empty_payload: Optional[Dict[str, Any]] = None
        last_empty_usage: Dict[str, int] = {}
        last_budget: Optional[int] = requested_max_tokens

        for attempt_index in range(attempts):
            attempt_body = dict(body)
            if requested_max_tokens is not None and attempt_index:
                last_budget = requested_max_tokens * 2
                attempt_body["max_output_tokens"] = last_budget
                logger.info(
                    "Retrying OpenCode call with max_output_tokens=%s "
                    "after empty output",
                    last_budget,
                )
            else:
                last_budget = requested_max_tokens
            try:
                payload = self._post(url, headers, attempt_body, timeout_seconds)
            except urllib.error.HTTPError as exc:
                return self._http_error(exc, name, attempt_index + 1)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                return self._network_error(exc, name, attempt_index + 1)
            if not isinstance(payload, dict):
                message = "OpenCode returned a non-object JSON response"
                logger.warning(message)
                return {
                    "response": "",
                    "error": message,
                    "error_type": "invalid_response",
                    "model": name,
                    "attempts": attempt_index + 1,
                    "request": request_info(attempt_index + 1, last_budget),
                }
            text = extract_response_text(payload).strip()
            usage = extract_usage(payload)
            if text:
                return {
                    "response": text,
                    "prompt_eval_count": usage["input_tokens"],
                    "eval_count": usage["output_tokens"],
                    "usage": usage,
                    "raw_response": payload,
                    "model": name,
                    "attempts": attempt_index + 1,
                    "request": request_info(attempt_index + 1, last_budget),
                }
            last_empty_payload = payload
            last_empty_usage = usage

        message = (
            "OpenCode returned no output text "
            "(reasoning may have consumed the output budget; "
            "increase max_output_tokens)"
        )
        logger.warning(message)
        return {
            "response": "",
            "error": message,
            "error_type": EMPTY_OUTPUT_ERROR_TYPE,
            "usage": last_empty_usage,
            "raw_response": last_empty_payload,
            "model": name,
            "attempts": attempts,
            "request": request_info(attempts, last_budget),
        }

    def _post(
        self, url: str, headers: Dict[str, str], body: Dict[str, Any], timeout: int
    ) -> Any:
        logger.debug("Calling OpenCode Responses API at %s", url)
        request = urllib.request.Request(
            url, data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        return json.loads(raw) if raw.strip() else {}

    def _http_error(
        self, exc: urllib.error.HTTPError, model: str, attempts: int
    ) -> Dict[str, Any]:
        status_code: Optional[int] = getattr(exc, "code", None)
        raw_headers = _safe_headers(getattr(exc, "headers", {}) or {})
        try:
            body_bytes = exc.read()
        except Exception:
            body_bytes = b""
        if isinstance(body_bytes, bytes):
            body_text = body_bytes.decode("utf-8", errors="replace")
        else:
            body_text = str(body_bytes)
        error_payload: Any = body_text[:_ERROR_BODY_LIMIT]
        if body_text.strip():
            try:
                error_payload = json.loads(body_text)
            except (ValueError, TypeError):
                pass
        error_type = "rate_limited" if status_code == 429 else "http_error"
        message = (
            f"OpenCode HTTP {status_code}"
            if status_code is not None
            else f"OpenCode HTTP error: {exc}"
        )
        logger.warning("OpenCode HTTP request failed: %s", message)
        return {
            "response": "",
            "error": message,
            "error_type": error_type,
            "status_code": status_code,
            "retry_after": raw_headers.get("Retry-After"),
            "rate_limit_headers": _rate_limit_headers(raw_headers),
            "error_payload": error_payload,
            "model": model,
            "attempts": attempts,
        }

    def _network_error(
        self, exc: Exception, model: str, attempts: int
    ) -> Dict[str, Any]:
        if isinstance(exc, urllib.error.URLError):
            reason = exc.reason
            if isinstance(reason, (TimeoutError, socket.timeout)):
                error_type: str = "timeout"
                message = f"OpenCode request timed out: {exc}"
            else:
                error_type = "network"
                message = f"OpenCode service unavailable: {exc}"
        elif isinstance(exc, (TimeoutError, socket.timeout)):
            error_type = "timeout"
            message = f"OpenCode request timed out: {exc}"
        else:
            error_type = "network"
            message = f"OpenCode service unavailable: {exc}"
        logger.warning("OpenCode request failed: %s", message)
        return {
            "response": "",
            "error": message,
            "error_type": error_type,
            "model": model,
            "attempts": attempts,
        }

    def is_available(self) -> bool:
        """Check the gateway is reachable and a key is configured."""
        api_key = resolve_api_key(self.api_key)
        if not api_key:
            return False
        try:
            request = urllib.request.Request(
                f"{self.base_url}/v1/models",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": USER_AGENT,
                },
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                return getattr(response, "status", 200) == 200
        except Exception as exc:  # availability checks never raise
            logger.warning("OpenCode availability check failed: %s", exc)
            return False


def main(argv: Optional[list] = None) -> int:
    """Smoke-test CLI: ``python -m providers.opencode --prompt ...``."""
    parser = argparse.ArgumentParser(
        description="Smoke-test Muse Spark via the OpenCode Responses API."
    )
    parser.add_argument("--prompt", default="Return exactly the word READY")
    parser.add_argument("--model", default=None)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--reasoning-effort", default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--base-url", default=None)
    args = parser.parse_args(argv)

    client = OpenCodeModel(base_url=args.base_url)
    if not resolve_api_key(client.api_key):
        print(
            "OpenCode API key not configured. Set MEMORY_OPENCODE_API_KEY "
            "or OPENCODE_ZEN_API_KEY."
        )
        return 2
    session_id = args.session_id or new_session_id("memory-smoke")
    result = client.generate(
        args.prompt,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout_seconds=args.timeout,
        reasoning_effort=args.reasoning_effort,
        session_id=session_id,
    )
    if result.get("error"):
        print(f"error_type: {result.get('error_type')}")
        print(f"error: {result.get('error')}")
        if result.get("status_code") is not None:
            print(f"status_code: {result.get('status_code')}")
        return 1
    print(f"model: {result.get('model')}")
    print(f"attempts: {result.get('attempts')}")
    print(f"session_id: {session_id}")
    print(f"response: {result.get('response')}")
    usage = result.get("usage") or {}
    print(
        "usage: input={input_tokens} cached={cached_input_tokens} "
        "output={output_tokens} reasoning={reasoning_tokens} "
        "total={total_tokens}".format(
            input_tokens=usage.get("input_tokens"),
            cached_input_tokens=usage.get("cached_input_tokens"),
            output_tokens=usage.get("output_tokens"),
            reasoning_tokens=usage.get("reasoning_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
