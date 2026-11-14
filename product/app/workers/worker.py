"""arq worker: runs `advance`, rubric, rescore and email delivery jobs.
Start with `arq app.workers.worker.WorkerSettings`.

Retries inside a step are handled by the pipeline. arq's own `max_tries` covers the job
being lost (worker killed mid job): the job is re-run, and because every job carries the
state and version it was queued for, a re-run after the move happened is a no-op.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, ClassVar

from arq import cron, func
from arq.connections import RedisSettings

from app.config import get_settings
from app.db.session import make_engine, make_sessionmaker
from app.domain.jobs import JobState
from app.domain.states import CandidateState
from app.integrations.storage import make_storage
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
    store = make_storage(_settings)
    ensure = getattr(store, "ensure_bucket", None)
    if ensure is not None:
        await ensure()
    ctx["pipeline"] = Pipeline(
        make_sessionmaker(engine),
        ArqDispatcher(ctx["redis"]),
        tracer,
        _settings,
        llm=llm,
        storage=store,
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


async def rescore(ctx: dict[str, Any], candidate_id: str) -> str:
    pipeline: Pipeline = ctx["pipeline"]
    result = await pipeline.rescore(uuid.UUID(candidate_id))
    pipeline.tracer.flush()
    return result


async def deliver_email(ctx: dict[str, Any], outbox_id: str, attempt: int = 0) -> str:
    pipeline: Pipeline = ctx["pipeline"]
    result = await pipeline.deliver_email(uuid.UUID(outbox_id), attempt)
    pipeline.tracer.flush()
    return result


async def poll_inbox(ctx: dict[str, Any], mailbox_id: str) -> str:
    pipeline: Pipeline = ctx["pipeline"]
    result = await pipeline.poll_inbox(uuid.UUID(mailbox_id))
    pipeline.tracer.flush()
    return result


async def process_inbox_message(ctx: dict[str, Any], message_id: str) -> str:
    pipeline: Pipeline = ctx["pipeline"]
    result = await pipeline.process_inbox_message(uuid.UUID(message_id))
    pipeline.tracer.flush()
    return result


async def poll_inboxes(ctx: dict[str, Any]) -> int:
    """Cron: queue a poll for every active mailbox (phase 5B brief Q3: every 2 minutes)."""
    pipeline: Pipeline = ctx["pipeline"]
    return await pipeline.poll_all_inboxes(int(time.time() // _settings.inbox_poll_seconds))


_POLL_MINUTES = set(range(0, 60, max(1, _settings.inbox_poll_seconds // 60)))


class WorkerSettings:
    functions: ClassVar[list[Any]] = [
        advance,
        func(build_rubric_job, name="build_rubric"),
        rescore,
        deliver_email,
        poll_inbox,
        process_inbox_message,
    ]
    cron_jobs: ClassVar[list[Any]] = [cron(poll_inboxes, minute=_POLL_MINUTES, run_at_startup=True)]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
    max_tries = 3
    job_timeout = int(_settings.step_timeout_seconds * _settings.step_max_attempts + 30)
    keep_result = 3600
