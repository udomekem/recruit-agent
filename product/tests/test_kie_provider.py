"""kie.ai provider against a mocked HTTP endpoint (no network, no cost)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.config import Settings
from app.llm.factory import make_provider, provider_key_name
from app.llm.providers import (
    KieProvider,
    ProviderAuthError,
    ProviderRequestError,
    ProviderTransientError,
)

URL = "https://api.kie.ai/openai/v1/responses"


def provider(handler: Any) -> KieProvider:
    return KieProvider("test-key", 5.0, URL, transport=httpx.MockTransport(handler))


def ok_body(text: str = '{"a": 1}', **over: Any) -> dict[str, Any]:
    body = {
        "model": "deepseek-v4-1-flash",
        "status": "completed",
        "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "content": [{"type": "output_text", "text": text}]},
        ],
        "usage": {"input_tokens": 120, "output_tokens": 30},
    }
    body.update(over)
    return body


async def call(p: KieProvider) -> Any:
    return await p.complete(
        model="deepseek-v4-1-flash",
        system="be brief",
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "{}"},
            {"role": "user", "content": "fix it"},
        ],
        json_schema={"type": "object"},
        max_tokens=100,
        effort="medium",
        fallback=True,
    )


async def test_request_shape_and_parsed_response() -> None:
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=ok_body())

    r = await call(provider(handler))
    body = seen["body"]
    assert seen["auth"] == "Bearer test-key"
    assert body["model"] == "deepseek-v4-1-flash" and body["instructions"] == "be brief"
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["reasoning"] == {"effort": "medium"}
    assert [m["content"][0]["type"] for m in body["input"]] == [
        "input_text",
        "output_text",
        "input_text",
    ]
    assert (r.text, r.stop_reason, r.input_tokens, r.output_tokens) == (
        '{"a": 1}',
        "end_turn",
        120,
        30,
    )


@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (429, ProviderTransientError),
        (502, ProviderTransientError),
        (400, ProviderRequestError),
        (402, ProviderRequestError),
    ],
)
async def test_http_errors_are_classified(status: int, exc: type[Exception]) -> None:
    with pytest.raises(exc):
        await call(provider(lambda req: httpx.Response(status, text="nope")))


async def test_error_inside_a_200_body() -> None:
    """kie.ai can return HTTP 200 with an error code in the body."""
    with pytest.raises(ProviderAuthError):
        await call(provider(lambda req: httpx.Response(200, json={"code": 401, "msg": "bad key"})))
    with pytest.raises(ProviderTransientError):
        await call(provider(lambda req: httpx.Response(200, json={"code": 500, "msg": "busy"})))
    with pytest.raises(ProviderRequestError):
        await call(
            provider(lambda req: httpx.Response(200, json={"error": {"message": "bad schema"}}))
        )


async def test_network_failure_is_transient() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(ProviderTransientError):
        await call(provider(handler))


async def test_refusal_and_incomplete() -> None:
    refusal = ok_body(
        output=[{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}]
    )
    r = await call(provider(lambda req: httpx.Response(200, json=refusal)))
    assert r.stop_reason == "refusal" and r.text is None
    r = await call(provider(lambda req: httpx.Response(200, json=ok_body(status="incomplete"))))
    assert r.stop_reason == "max_tokens"


def test_factory_picks_provider_by_setting() -> None:
    kie = Settings(_env_file=None, kie_api_key="k")  # type: ignore[call-arg, arg-type]
    assert isinstance(make_provider(kie), KieProvider)
    assert make_provider(Settings(_env_file=None)) is None  # type: ignore[call-arg]
    anth = Settings(_env_file=None, llm_provider="anthropic")  # type: ignore[call-arg]
    assert provider_key_name(anth) == "ANTHROPIC_API_KEY" and make_provider(anth) is None
