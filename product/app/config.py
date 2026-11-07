"""Typed configuration, loaded from environment variables (and `product/.env` locally).

Every field here must also appear in `.env.example`; a test enforces that.
Defaults are safe: no real email, call, or calendar action is possible unless a flag
is switched on explicitly.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "ci", "production"] = "development"

    # Storage and queue
    database_url: str = "postgresql+psycopg://recruit:recruit@localhost:5432/recruit"
    redis_url: str = "redis://localhost:6379/0"

    # Recruiter identity (phase 0: one token; real accounts arrive in phase 4)
    recruiter_token: SecretStr | None = None
    recruiter_id: str = "recruiter-dev"

    # LLM (model ids and tiers per shared/project-config.md)
    anthropic_api_key: SecretStr | None = None
    model_extraction: str = "claude-haiku-5-5"
    model_judgement: str = "claude-sonnet-5-5"
    effort_extraction: Effort = "low"
    effort_judgement: Effort = "high"
    llm_timeout_seconds: float = 60.0
    llm_max_tokens: int = 16000
    llm_max_invalid_retries: int = Field(default=2, ge=0)
    llm_max_provider_retries: int = Field(default=3, ge=0)
    llm_max_calls_per_process: int = Field(default=50, ge=1)

    # Tracing (tracing is off when either key is missing)
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"

    # Workflow
    step_max_attempts: int = Field(default=3, ge=1)
    step_timeout_seconds: float = 30.0
    step_retry_backoff_seconds: float = 1.0
    screen_call_max_attempts: int = Field(default=3, ge=1)
    no_answer_retry_delay_seconds: int = 3600

    # Side effect switches: all off by default
    email_sending_enabled: bool = False
    phone_calls_enabled: bool = False
    calendar_booking_enabled: bool = False

    @property
    def tracing_configured(self) -> bool:
        return self.langfuse_public_key is not None and self.langfuse_secret_key is not None


# USD per million tokens (input, output). Source: Claude API pricing, cached 2026-10-06.
# Haiku 5.5 rates apply to prompts up to 100K tokens.
MODEL_PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
}


@lru_cache
def get_settings() -> Settings:
    return Settings()
