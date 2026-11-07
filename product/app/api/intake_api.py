"""Public apply page and recruiter intake endpoints (phase 1 design sections 3 and 4).

The apply page is plain server rendered HTML (brief Q2). It never echoes contact details
into logs; on a validation error it re-renders the form with the applicant's own input.
"""

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, ValidationError
from starlette.datastructures import UploadFile as StarletteUpload

from app.config import Settings
from app.db.models import Job
from app.domain.jobs import JobState
from app.domain.notice import CONSENT_LABEL, NOTICE_VERSION, notice_text
from app.intake.service import Application, IntakeRefused, submit
from app.workflow import jobs as J
from app.workflow.machine import ErasureIncomplete, erase_personal_data

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


class BulkItem(BaseModel):
    filename: str
    full_name: str = Field(min_length=2, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    phone: str | None = None


async def _read_limited(upload: UploadFile | StarletteUpload, limit: int) -> bytes:
    """Read at most limit + 1 bytes, so an oversize file is refused without reading it all."""
    data = await upload.read(limit + 1)
    return data


def register(app: FastAPI, cfg: Settings, Recruiter: Any, Pl: Any, Store: Any) -> None:  # noqa: N803
    async def _open_job(p: Any, job_id: uuid.UUID) -> tuple[Job | None, list[Any]]:
        async with p.sessions() as s:
            job = await s.get(Job, job_id)
        if job is None or job.state != JobState.OPEN:
            return None, []
        return job, await J.questions(p.sessions, job_id)

    def _page(
        request: Request,
        job: Job,
        qs: list[Any],
        errors: dict[str, str] | None = None,
        values: dict[str, Any] | None = None,
        status: int = 200,
    ) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request,
            "apply.html",
            {
                "job": job,
                "questions": qs,
                "errors": errors or {},
                "values": values or {},
                "notice": notice_text(cfg.company_name),
                "consent_label": CONSENT_LABEL,
                "notice_version": NOTICE_VERSION,
                "company": cfg.company_name,
                "max_mb": cfg.cv_max_bytes // (1024 * 1024),
            },
            status_code=status,
        )

    @app.get("/apply/{job_id}", response_class=HTMLResponse)
    async def apply_page(request: Request, job_id: uuid.UUID, p: Pl) -> HTMLResponse:
        job, qs = await _open_job(p, job_id)
        if job is None:
            return TEMPLATES.TemplateResponse(
                request, "apply_unavailable.html", {"company": cfg.company_name}, status_code=404
            )
        return _page(request, job, qs)

    @app.post("/apply/{job_id}", response_class=HTMLResponse)
    async def apply_submit(
        request: Request, job_id: uuid.UUID, p: Pl, store: Store
    ) -> HTMLResponse:
        job, qs = await _open_job(p, job_id)
        if job is None:
            return TEMPLATES.TemplateResponse(
                request, "apply_unavailable.html", {"company": cfg.company_name}, status_code=404
            )
        form = await request.form(max_files=1, max_fields=60)
        cv = form.get("cv")
        cv_bytes, cv_name = b"", ""
        if cv is not None and not isinstance(cv, str):
            cv_bytes = await _read_limited(cv, cfg.cv_max_bytes)
            cv_name = cv.filename or ""
        answers = {q.key: form.get(f"q_{q.key}") for q in qs}
        values = {k: v for k, v in form.items() if isinstance(v, str)}
        try:
            result = await submit(
                p,
                store,
                Application(
                    job_id=job_id,
                    source="apply_page",
                    full_name=str(form.get("full_name") or ""),
                    email=str(form.get("email") or ""),
                    phone=str(form.get("phone") or "") or None,
                    cv_bytes=cv_bytes,
                    cv_filename=cv_name,
                    answers=answers,
                    candidate_consented=form.get("consent") == "yes",
                ),
                cv_max_bytes=cfg.cv_max_bytes,
            )
        except IntakeRefused as exc:
            if exc.status == 404:
                return TEMPLATES.TemplateResponse(
                    request,
                    "apply_unavailable.html",
                    {"company": cfg.company_name},
                    status_code=404,
                )
            return _page(request, job, qs, exc.errors, values, status=exc.status)
        return TEMPLATES.TemplateResponse(
            request,
            "apply_result.html",
            {"job": job, "company": cfg.company_name, "duplicate": result.status == "duplicate"},
            status_code=201 if result.status == "created" else 200,
        )

    @app.post("/jobs/{job_id}/candidates/bulk")
    async def bulk_upload(
        job_id: uuid.UUID,
        actor: Recruiter,
        p: Pl,
        store: Store,
        files: list[UploadFile] = File(...),  # noqa: B008
        metadata: str = Form(...),
        original_platform: str = Form(..., min_length=2, max_length=60),
        consent_attested: bool = Form(...),
    ) -> JSONResponse:
        try:
            items = [BulkItem.model_validate(x) for x in json.loads(metadata)]
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            return JSONResponse(
                status_code=422, content={"error": "bad_metadata", "detail": str(exc)[:500]}
            )
        by_name = {i.filename: i for i in items}
        if len(files) > 50:
            return JSONResponse(
                status_code=422, content={"error": "too_many_files", "detail": "50 per upload"}
            )
        results: list[dict[str, Any]] = []
        for upload in files:
            meta = by_name.get(upload.filename or "")
            if meta is None:
                results.append(
                    {
                        "filename": upload.filename,
                        "status": "refused",
                        "errors": {"metadata": "no name and email for this file"},
                    }
                )
                continue
            try:
                r = await submit(
                    p,
                    store,
                    Application(
                        job_id=job_id,
                        source="bulk_upload",
                        full_name=meta.full_name,
                        email=meta.email,
                        phone=meta.phone,
                        cv_bytes=await _read_limited(upload, cfg.cv_max_bytes),
                        cv_filename=upload.filename or "",
                        recruiter_attested=consent_attested,
                        attested_by=actor,
                        original_platform=original_platform,
                    ),
                    cv_max_bytes=cfg.cv_max_bytes,
                )
                results.append(
                    {
                        "filename": upload.filename,
                        "status": r.status,
                        "candidate_id": str(r.candidate_id),
                    }
                )
            except IntakeRefused as exc:
                results.append(
                    {"filename": upload.filename, "status": "refused", "errors": exc.errors}
                )
        created = sum(r["status"] == "created" for r in results)
        return JSONResponse(status_code=200, content={"created": created, "results": results})

    @app.post("/candidates/{candidate_id}/erase")
    async def erase(candidate_id: uuid.UUID, actor: Recruiter, p: Pl, store: Store) -> JSONResponse:
        try:
            c = await erase_personal_data(p.sessions, store, candidate_id, actor_id=actor)
        except ErasureIncomplete as exc:
            return JSONResponse(
                status_code=503, content={"error": "erasure_incomplete", "detail": str(exc)}
            )
        return JSONResponse(
            status_code=200, content={"id": str(c.id), "state": c.state.value, "erased": True}
        )

    _ = (apply_page, apply_submit, bulk_upload, erase)
