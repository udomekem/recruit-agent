"""Build the LLM client for the configured provider. The one place that knows providers."""

from __future__ import annotations

from app.config import Settings
from app.llm.client import LLMClient
from app.llm.providers import AnthropicProvider, KieProvider, Provider
from app.observability.tracing import Tracer


def provider_key_name(settings: Settings) -> str:
    return "KIE_API_KEY" if settings.llm_provider == "kie" else "ANTHROPIC_API_KEY"


def make_provider(settings: Settings) -> Provider | None:
    """The configured provider, or None when its key is not set."""
    if settings.llm_provider == "kie":
        if settings.kie_api_key is None:
            return None
        return KieProvider(
            settings.kie_api_key.get_secret_value(),
            settings.llm_timeout_seconds,
            settings.kie_responses_url,
        )
    if settings.anthropic_api_key is None:
        return None
    return AnthropicProvider(
        settings.anthropic_api_key.get_secret_value(), settings.llm_timeout_seconds
    )


def make_llm(settings: Settings, tracer: Tracer) -> LLMClient | None:
    provider = make_provider(settings)
    return LLMClient(provider, tracer, settings) if provider is not None else None
