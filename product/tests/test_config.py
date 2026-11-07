"""Config hygiene: every setting is documented, and side effects are off by default."""

from pathlib import Path

from app.config import Settings
from app.observability.tracing import NoopTracer, make_tracer

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"


def test_env_example_lists_every_setting() -> None:
    names = {
        line.split("=", 1)[0].strip()
        for line in ENV_EXAMPLE.read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    expected = {name.upper() for name in Settings.model_fields}
    compose_only = {n for n in names if n.startswith("MINIO_")}  # read by docker compose
    assert expected - names == set(), f"missing from .env.example: {sorted(expected - names)}"
    unknown = names - expected - compose_only
    assert unknown == set(), f"unknown in .env.example: {sorted(unknown)}"


def test_side_effects_off_by_default() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert not s.email_sending_enabled
    assert not s.phone_calls_enabled
    assert not s.calendar_booking_enabled


def test_tracing_off_without_keys() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert isinstance(make_tracer(s), NoopTracer)


def test_blank_secrets_from_env_example_count_as_unset(tmp_path: Path) -> None:
    """Found by the clean clone check: `cp .env.example .env` left `KEY=` lines that read
    as empty secrets, which switched tracing on with blank keys."""
    env = tmp_path / ".env"
    env.write_text(ENV_EXAMPLE.read_text())
    s = Settings(_env_file=str(env))  # type: ignore[call-arg]
    assert s.anthropic_api_key is None and s.recruiter_token is None
    assert s.langfuse_public_key is None and s.langfuse_secret_key is None
    assert not s.tracing_configured
    assert isinstance(make_tracer(s), NoopTracer)


def test_model_tiers_match_project_config() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert (s.model_extraction, s.model_judgement) == ("claude-haiku-5-5", "claude-sonnet-5-5")
