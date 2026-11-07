"""Job dispatch. The job id is derived from the candidate and its state version, so the
same step can only be queued once per version (arq ignores a duplicate job id)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from app.domain.states import CandidateState


@dataclass(frozen=True)
class AdvanceJob:
    candidate_id: uuid.UUID
    expected_state: CandidateState
    expected_version: int
    defer_seconds: int = 0

    @property
    def job_id(self) -> str:
        return f"advance:{self.candidate_id}:v{self.expected_version}"


class Dispatcher(Protocol):
    async def enqueue(self, job: AdvanceJob) -> None: ...


class ArqDispatcher:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def enqueue(self, job: AdvanceJob) -> None:
        await self._pool.enqueue_job(
            "advance",
            str(job.candidate_id),
            job.expected_state.value,
            job.expected_version,
            _job_id=job.job_id,
            _defer_by=job.defer_seconds or None,
        )


class InlineDispatcher:
    """Collects jobs in memory; tests drain them in-process. Ignores defers."""

    def __init__(self) -> None:
        self.queue: list[AdvanceJob] = []
        self.history: list[AdvanceJob] = []

    async def enqueue(self, job: AdvanceJob) -> None:
        self.queue.append(job)
        self.history.append(job)
