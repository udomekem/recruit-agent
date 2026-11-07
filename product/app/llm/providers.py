"""Model providers. The client talks to a `Provider`; tests use `FakeProvider`.

- KieProvider (default since 2026-11-07): kie.ai's OpenAI Responses compatible endpoint,
  DeepSeek V4.1 Flash. Structured output via `text.format` json_schema.
- AnthropicProvider: Claude API with structured outputs (`output_config.format`). Forced
  tool use is not used: current models reject `tool_choice` any/tool. Kept so the
  provider can be switched back with LLM_PROVIDER=anthropic.
Provider side retries are off so the client owns the retry policy.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

import anthropic

FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass(frozen=True)
class ProviderResponse:
    text: str | None
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    model: str


class ProviderTransientError(Exception):
    """Worth retrying: rate limit, server error, network, timeout."""


class ProviderAuthError(Exception):
    """Bad or missing key. Never retried."""


class ProviderRequestError(Exception):
    """The request itself is wrong (400, 404, ...). Never retried."""


class Provider(Protocol):
    async def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any],
        max_tokens: int,
        effort: str,
        fallback: bool = False,
    ) -> ProviderResponse: ...


class AnthropicProvider:
    def __init__(self, api_key: str, timeout_seconds: float) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key, max_retries=0, timeout=timeout_seconds
        )

    async def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any],
        max_tokens: int,
        effort: str,
        fallback: bool = False,
    ) -> ProviderResponse:
        try:
            # Our messages and output_config are plain dicts; the SDK accepts them at runtime.
            output_config: Any = {
                "effort": effort,
                "format": {"type": "json_schema", "schema": json_schema},
            }
            if fallback:
                # Server side refusal fallback (Claude API): if the model declines, the API
                # re-runs the request on a fallback model chosen for the refusal category.
                resp: Any = await self._client.beta.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=cast(Any, messages),
                    output_config=output_config,
                    betas=[FALLBACK_BETA],
                    fallbacks=cast(Any, "default"),
                )
            else:
                resp = await self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=cast(Any, messages),
                    output_config=output_config,
                )
        except anthropic.AuthenticationError as exc:
            raise ProviderAuthError(str(exc)) from exc
        except anthropic.PermissionDeniedError as exc:
            raise ProviderAuthError(str(exc)) from exc
        except (anthropic.RateLimitError, anthropic.InternalServerError) as exc:
            raise ProviderTransientError(str(exc)) from exc
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
            raise ProviderTransientError(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderRequestError(f"{exc.status_code}: {exc}") from exc
        text = next((b.text for b in resp.content if b.type == "text"), None)
        return ProviderResponse(
            text=text,
            stop_reason=resp.stop_reason,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            model=resp.model,
        )


ScriptItem = str | Exception | ProviderResponse


class FakeProvider:
    """Answers from a script, in order. A str becomes a normal text response."""

    def __init__(self, script: Sequence[ScriptItem], model: str = "fake-model") -> None:
        self._script = list(script)
        self.model = model
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any],
        max_tokens: int,
        effort: str,
        fallback: bool = False,
    ) -> ProviderResponse:
        self.calls.append(
            {
                "model": model,
                "system": system,
                "messages": [dict(m) for m in messages],
                "json_schema": json_schema,
                "effort": effort,
                "fallback": fallback,
            }
        )
        if not self._script:
            raise AssertionError("FakeProvider script exhausted")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, ProviderResponse):
            return item
        return ProviderResponse(item, "end_turn", input_tokens=100, output_tokens=20, model=model)


class KieProvider:
    """kie.ai Responses endpoint (OpenAI Responses shape).

    Model page: https://kie.ai/deepseek-v4-1-flash (endpoint, `text.format` json_schema,
    `reasoning.effort`). `instructions` is always set: on kie.ai's codex endpoint an
    unset value means a default coding agent persona is applied (workspace ask-gpt notes).
    kie.ai can report errors as HTTP 200 with a `code` in the body, so both are checked.
    There is no server side refusal fallback; `fallback` is accepted and ignored.
    """

    def __init__(
        self, api_key: str, timeout_seconds: float, url: str, transport: Any = None
    ) -> None:
        import httpx

        self._url = url
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            transport=transport,  # tests pass httpx.MockTransport
        )

    @staticmethod
    def _input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for m in messages:
            kind = "output_text" if m["role"] == "assistant" else "input_text"
            out.append({"role": m["role"], "content": [{"type": kind, "text": str(m["content"])}]})
        return out

    @staticmethod
    def _raise_for(status: int, detail: str) -> None:
        if status in (401, 403):
            raise ProviderAuthError(f"{status}: {detail}")
        if status == 429 or status >= 500:
            raise ProviderTransientError(f"{status}: {detail}")
        raise ProviderRequestError(f"{status}: {detail}")

    async def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any],
        max_tokens: int,
        effort: str,
        fallback: bool = False,
    ) -> ProviderResponse:
        import httpx

        payload = {
            "model": model,
            "stream": False,
            "instructions": system,
            "input": self._input(messages),
            "text": {"format": {"type": "json_schema", "name": "output", "schema": json_schema}},
            "reasoning": {"effort": effort},
        }
        try:
            r = await self._client.post(self._url, json=payload)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise ProviderTransientError(f"kie.ai unreachable: {type(exc).__name__}") from exc
        if r.status_code != 200:
            self._raise_for(r.status_code, r.text[:300])
        try:
            body = r.json()
        except ValueError as exc:
            raise ProviderTransientError("kie.ai returned a non JSON body") from exc
        code = body.get("code")
        if isinstance(code, int) and code != 200 and not body.get("output"):
            self._raise_for(code, str(body.get("msg") or body.get("message") or body)[:300])
        if body.get("error"):
            err = body["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise ProviderRequestError(f"kie.ai error: {msg[:300]}")

        text_parts: list[str] = []
        refused = False
        for item in body.get("output") or []:
            if item.get("type") != "message":
                continue
            for chunk in item.get("content") or []:
                if chunk.get("type") == "refusal":
                    refused = True
                elif chunk.get("type") in ("output_text", "text") and chunk.get("text"):
                    text_parts.append(chunk["text"])
        usage = body.get("usage") or {}
        status = body.get("status")
        stop = "refusal" if refused else ("max_tokens" if status == "incomplete" else "end_turn")
        return ProviderResponse(
            text="".join(text_parts) or None,
            stop_reason=stop,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            model=str(body.get("model") or model),
        )
