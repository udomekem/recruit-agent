"""arq worker: runs `advance` jobs. Start with `arq app.workers.worker.WorkerSettings`.

Retries inside a step are handled by the pipeline. arq's own `max_tries` covers the job
being lost (worker killed mid job): the job is re-run, and because every job carries the
state and version it was queued for, a re-run after the move happened is a no-op.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from arq import func
from arq.connections import RedisSettings

from app.config import get_settings
from app.db.session import make_engine, make_sessionmaker
from app.domain.jobs import JobState
from app.domain.states import CandidateState
from app.llm.factory import make_llm
from app.observability.tracing import make_tracer
from app.workflow.dispatch import ArqDispatcher
from app.workflow.pipeline import Pipeline

_settings = get_settings()


async def startup(ctx: dict[str, Any]) -> None:
    engine = make_engine(_settings.database_url)
    ctx["engine"] = engine
    tracer = make_tracer(_settings)
    llm = make_llm(_settings, tracer)
    ctx["pipeline"] = Pipeline(
        make_sessionmaker(engine), ArqDispatcher(ctx["redis"]), tracer, _settings, llm=llm
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    ctx["pipeline"].tracer.flush()
    await ctx["engine"].dispose()


async def advance(
    ctx: dict[str, Any], candidate_id: str, expected_state: str, expected_version: int
) -> str:
    pipeline: Pipeline = ctx["pipeline"]
    moved = await pipeline.advance(
        uuid.UUID(candidate_id), CandidateState(expected_state), expected_version
    )
    pipeline.tracer.flush()
    return moved.state.value if moved else "no-op"


async def build_rubric_job(
    ctx: dict[str, Any], job_id: str, expected_state: str, expected_version: int
) -> str:
    pipeline: Pipeline = ctx["pipeline"]
    moved = await pipeline.build_rubric(
        uuid.UUID(job_id), JobState(expected_state), expected_version
    )
    pipeline.tracer.flush()
    return moved.state.value if moved else "no-op"


class WorkerSettings:
    functions: ClassVar[list[Any]] = [advance, func(build_rubric_job, name="build_rubric")]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
    max_tries = 3
    job_timeout = int(_settings.step_timeout_seconds * _settings.step_max_attempts + 30)
    keep_result = 3600
