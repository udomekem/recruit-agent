"""FastAPI app. Recruiter decisions are API calls only; the worker never makes them.

`create_app` takes optional pre-built parts so tests can inject an in-memory dispatcher,
a recording tracer and memory storage. Without them, the lifespan builds the real ones.
Phase 1 adds job, rubric, apply page, bulk upload and erasure routes (jobs_api, intake_api).
"""

import hmac
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api import intake_api, jobs_api
from app.config import Settings, get_settings
from app.db.session import make_engine, make_sessionmaker
from app.domain.states import ActorType, CandidateState
from app.integrations.storage import Storage, make_storage
from app.llm.factory import make_llm
from app.observability.tracing import make_tracer
from app.workflow.dispatch import ArqDispatcher
from app.workflow.jobs import JobNotFound
from app.workflow.machine import (
    CandidateNotFound,
    Snapshot,
    StaleTransition,
    TransitionRefused,
    apply_transition,
    audit_trail,
    create_candidate,
    get_candidate,
)
from app.workflow.pipeline import Pipeline

S = CandidateState


class CreateCandidate(BaseModel):
    display_label: str = Field(min_length=1, max_length=120)


class Decision(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    expected_version: int | None = None


class CandidateOut(BaseModel):
    id: uuid.UUID
    state: CandidateState
    state_version: int
    review_return_state: CandidateState | None
    screen_call_attempts: int
    display_label: str


class AuditOut(BaseModel):
    transition_id: str
    from_state: str | None
    to_state: str
    actor_type: str
    actor_id: str
    reason: str
    trace_id: str | None
    occurred_at: datetime


class CandidateDetail(CandidateOut):
    audit: list[AuditOut]


def _out(c: Snapshot) -> CandidateOut:
    return CandidateOut(**c.__dict__)


def create_app(
    settings: Settings | None = None,
    pipeline: Pipeline | None = None,
    storage: Storage | None = None,
) -> FastAPI:
    cfg = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = None
        arq_pool = None
        if pipeline is None:
            from arq import create_pool
            from arq.connections import RedisSettings

            engine = make_engine(cfg.database_url)
            arq_pool = await create_pool(RedisSettings.from_dsn(cfg.redis_url))
            tracer = make_tracer(cfg)
            llm = make_llm(cfg, tracer)
            app.state.pipeline = Pipeline(
                make_sessionmaker(engine), ArqDispatcher(arq_pool), tracer, cfg, llm=llm
            )
        else:
            app.state.pipeline = pipeline
        if storage is None:
            store = make_storage(cfg)
            ensure = getattr(store, "ensure_bucket", None)
            if ensure is not None:
                await ensure()
            app.state.storage = store
        else:
            app.state.storage = storage
        try:
            yield
        finally:
            app.state.pipeline.tracer.flush()
            if arq_pool is not None:
                await arq_pool.aclose()
            if engine is not None:
                await engine.dispose()

    app = FastAPI(title="Recruit Agent", version="0.0.1", lifespan=lifespan)
    if pipeline is not None:  # injected (tests): available even without running the lifespan
        app.state.pipeline = pipeline
    if storage is not None:
        app.state.storage = storage
    bearer = HTTPBearer(auto_error=False)

    def recruiter(
        creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> str:
        token = cfg.recruiter_token.get_secret_value() if cfg.recruiter_token else ""
        given = creds.credentials if creds else ""
        if not token or not hmac.compare_digest(given.encode(), token.encode()):
            raise HTTPException(status_code=401, detail="recruiter token required")
        return cfg.recruiter_id

    def pl(request: Request) -> Pipeline:
        return request.app.state.pipeline  # type: ignore[no-any-return]

    def st(request: Request) -> Storage:
        return request.app.state.storage  # type: ignore[no-any-return]

    Recruiter = Annotated[str, Depends(recruiter)]
    Pl = Annotated[Pipeline, Depends(pl)]
    Store = Annotated[Storage, Depends(st)]

    @app.exception_handler(JobNotFound)
    async def _job_missing(_: Request, exc: JobNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": "not_found", "detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _invalid(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": "invalid", "detail": str(exc)})

    @app.exception_handler(TransitionRefused)
    async def _refused(_: Request, exc: TransitionRefused) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"error": "illegal_transition", "detail": str(exc)}
        )

    @app.exception_handler(StaleTransition)
    async def _stale(_: Request, exc: StaleTransition) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": "already_moved", "detail": str(exc)})

    @app.exception_handler(CandidateNotFound)
    async def _missing(_: Request, exc: CandidateNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": "not_found", "detail": str(exc)})

    @app.get("/health")
    async def health(p: Pl) -> JSONResponse:
        checks: dict[str, str] = {}
        try:
            async with p.sessions() as s:
                await s.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {type(exc).__name__}"
        try:
            from redis.asyncio import Redis

            r = Redis.from_url(cfg.redis_url)
            try:
                await r.ping()
            finally:
                await r.aclose()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = f"error: {type(exc).__name__}"
        ok = all(v == "ok" for v in checks.values())
        return JSONResponse(
            status_code=200 if ok else 503, content={"status": "ok" if ok else "degraded", **checks}
        )

    @app.post("/candidates", status_code=201)
    async def create(body: CreateCandidate, actor: Recruiter, p: Pl) -> CandidateOut:
        """Test candidate with no job or personal data (phase 0 path). Off in production:
        real applications come through the intake adapter."""
        if cfg.environment == "production":
            raise HTTPException(status_code=404, detail="not available")
        c = await create_candidate(p.sessions, display_label=body.display_label, actor_id=actor)
        await p.schedule(c)
        return _out(c)

    @app.get("/candidates/{candidate_id}")
    async def detail(candidate_id: uuid.UUID, _: Recruiter, p: Pl) -> CandidateDetail:
        c = await get_candidate(p.sessions, candidate_id)
        trail = await audit_trail(p.sessions, candidate_id)
        return CandidateDetail(
            **_out(c).model_dump(),
            audit=[AuditOut.model_validate(e, from_attributes=True) for e in trail],
        )

    async def decide(
        p: Pipeline,
        candidate_id: uuid.UUID,
        actor: str,
        body: Decision,
        to: CandidateState | None,
        allowed_from: set[CandidateState] | None = None,
    ) -> CandidateOut:
        current = await get_candidate(p.sessions, candidate_id)
        if allowed_from is not None and current.state not in allowed_from:
            raise TransitionRefused(f"this action is not allowed from {current.state}")
        target = to if to is not None else current.review_return_state
        if target is None:
            raise TransitionRefused("no saved state to return to")
        moved = await apply_transition(
            p.sessions,
            candidate_id=candidate_id,
            to_state=target,
            actor_type=ActorType.RECRUITER,
            actor_id=actor,
            reason=body.reason,
            expected_state=current.state,
            expected_version=body.expected_version
            if body.expected_version is not None
            else current.state_version,
        )
        await p.schedule(moved)
        return _out(moved)

    @app.post("/candidates/{candidate_id}/shortlist")
    async def shortlist(
        candidate_id: uuid.UUID, body: Decision, actor: Recruiter, p: Pl
    ) -> CandidateOut:
        return await decide(p, candidate_id, actor, body, S.SHORTLISTED)

    @app.post("/candidates/{candidate_id}/reject")
    async def reject(
        candidate_id: uuid.UUID, body: Decision, actor: Recruiter, p: Pl
    ) -> CandidateOut:
        return await decide(p, candidate_id, actor, body, S.REJECTED)

    @app.post("/candidates/{candidate_id}/send-rejection")
    async def send_rejection(
        candidate_id: uuid.UUID, body: Decision, actor: Recruiter, p: Pl
    ) -> CandidateOut:
        # Phase 0: records the send decision only. No email is sent (EMAIL_SENDING_ENABLED=false).
        return await decide(p, candidate_id, actor, body, S.REJECTION_SENT)

    @app.post("/candidates/{candidate_id}/advance")
    async def advance(
        candidate_id: uuid.UUID, body: Decision, actor: Recruiter, p: Pl
    ) -> CandidateOut:
        return await decide(p, candidate_id, actor, body, S.ADVANCED)

    @app.post("/candidates/{candidate_id}/resolve-retry")
    async def resolve_retry(
        candidate_id: uuid.UUID, body: Decision, actor: Recruiter, p: Pl
    ) -> CandidateOut:
        return await decide(p, candidate_id, actor, body, None, allowed_from={S.NEEDS_REVIEW})

    @app.post("/candidates/{candidate_id}/withdraw")
    async def withdraw(
        candidate_id: uuid.UUID, body: Decision, actor: Recruiter, p: Pl
    ) -> CandidateOut:
        return await decide(p, candidate_id, actor, body, S.WITHDRAWN)

    jobs_api.register(app, Recruiter, Pl)
    intake_api.register(app, cfg, Recruiter, Pl, Store)

    _ = (
        shortlist,
        reject,
        send_rejection,
        advance,
        resolve_retry,
        withdraw,
        health,
        create,
        detail,
    )
    return app


def __getattr__(name: str) -> Any:
    # `uvicorn app.api.main:app` builds the app lazily so importing this module in tests
    # does not read the environment.
    if name == "app":
        return create_app()
    raise AttributeError(name)
