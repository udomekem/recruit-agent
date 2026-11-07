"""Shared fixtures. Database tests use a separate `recruit_test` database, migrated with
Alembic once per session and truncated between tests."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.config import Settings
from app.db.session import SessionMaker, make_engine, make_sessionmaker
from app.observability.tracing import RecordingTracer
from app.workflow.dispatch import InlineDispatcher
from app.workflow.pipeline import Pipeline
from app.workflow.steps import StubBehaviour, StubSteps

PRODUCT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://recruit:recruit@localhost:5432/recruit_test"
)
TEST_TOKEN = "test-recruiter-token"


def _ensure_database(url: str) -> None:
    u = make_url(url)
    admin = u.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    with psycopg.connect(admin, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (u.database,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{u.database}"')


@pytest.fixture(scope="session")
def migrated_db() -> Iterator[str]:
    _ensure_database(TEST_DATABASE_URL)
    cfg = Config(str(PRODUCT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PRODUCT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")
    yield TEST_DATABASE_URL


@pytest.fixture
def settings(migrated_db: str) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        environment="test",
        database_url=migrated_db,
        recruiter_token=TEST_TOKEN,  # type: ignore[arg-type]
        step_retry_backoff_seconds=0.0,
        step_timeout_seconds=2.0,
    )


@pytest.fixture
async def sessions(settings: Settings) -> AsyncIterator[SessionMaker]:
    engine = make_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE audit_events, candidates CASCADE"))
    yield make_sessionmaker(engine)
    await engine.dispose()


@pytest.fixture
def tracer() -> RecordingTracer:
    return RecordingTracer()


@pytest.fixture
def behaviour() -> StubBehaviour:
    return StubBehaviour()


@pytest.fixture
def pipeline(
    sessions: SessionMaker, tracer: RecordingTracer, settings: Settings, behaviour: StubBehaviour
) -> Pipeline:
    return Pipeline(sessions, InlineDispatcher(), tracer, settings, StubSteps(behaviour))
