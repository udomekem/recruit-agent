"""Model providers. The client talks to a `Provider`; tests use `FakeProvider`.

AnthropicProvider uses structured outputs (`output_config.format` with a JSON schema).
Forced tool use is not used: current models reject `tool_choice` any/tool.
SDK retries are off (`max_retries=0`) so the client owns the retry policy.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

import anthropic


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
    ) -> ProviderResponse:
        try:
            # Our messages and output_config are plain dicts; the SDK accepts them at runtime.
            output_config: Any = {
                "effort": effort,
                "format": {"type": "json_schema", "schema": json_schema},
            }
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
    ) -> ProviderResponse:
        self.calls.append(
            {
                "model": model,
                "system": system,
                "messages": [dict(m) for m in messages],
                "json_schema": json_schema,
                "effort": effort,
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
