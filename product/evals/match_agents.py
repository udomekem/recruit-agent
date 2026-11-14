"""Phase 5B eval agents (phase 5B design section 9).

- `match_rules` v1: the code rules and subject redaction (no model).
- `job_matcher` v1: the real path for a CV that arrived without a job: extract (hidden
  text removed), redact, parse, final redact, then the job matcher and the code rule
  (threshold and gap from settings). The redacted text of each file is cached for the
  run, so three runs parse each CV once.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.inbox.rules import OpenJob, match_rules, redact_subject

RUNTIME: dict[str, Any] = {}
_REDACTED: dict[str, tuple[str, float]] = {}
TWIN_TITLE = "Data Analyst (Reporting)"


def match_rules_v1(case_input: dict[str, Any]) -> dict[str, Any]:
    ids = {j["key"]: uuid.uuid5(uuid.NAMESPACE_URL, j["key"]) for j in case_input["jobs"]}
    jobs = [OpenJob(ids[j["key"]], j["title"], j["code"], j["open"]) for j in case_input["jobs"]]
    m = match_rules(case_input["subject"], case_input["to"], case_input["kind"], jobs)
    key = next((k for k, v in ids.items() if v == m.job_id), None)
    return {
        "job": key,
        "route": m.route,
        "subject": redact_subject(case_input["subject"], case_input.get("names") or []),
    }


def prepare(max_calls: int) -> None:
    from app.config import get_settings
    from app.llm.factory import make_llm, provider_key_name
    from app.observability.tracing import make_tracer
    from evals.harness import HarnessError

    settings = get_settings().model_copy(update={"llm_max_calls_per_process": max_calls})
    tracer = make_tracer(settings)
    llm = make_llm(settings, tracer)
    if llm is None:
        raise HarnessError(f"job matcher evals need {provider_key_name(settings)} (real model)")
    RUNTIME.update(llm=llm, tracer=tracer, settings=settings)


def _jobs(keys: list[str]) -> list[Any]:
    from app.agents.job_matcher import JobForMatch
    from evals.agents import _rubric

    out = []
    for k in keys:
        base = "analyst" if k == "analyst_twin" else k
        r = _rubric(base)
        musts = [c["text"] for c in r["criteria"] if c["kind"] == "must_have"]
        title = TWIN_TITLE if k == "analyst_twin" else r["title"]
        out.append(JobForMatch(uuid.uuid5(uuid.NAMESPACE_URL, k), title, "Sydney NSW", musts))
    return out


async def _redacted(cv: dict[str, Any]) -> tuple[str | None, float]:
    from app.agents.cv_parser import parse_cv
    from app.intake.redact import final_redact
    from evals.agents import _extract_and_redact

    if cv["file"] in _REDACTED:
        return _REDACTED[cv["file"]][0], 0.0
    _ex, pre = await _extract_and_redact(cv)
    if pre is None:
        return None, 0.0
    parsed = await parse_cv(RUNTIME["llm"], pre_redacted_text=pre.text, candidate_id="eval")
    text = final_redact(pre, [(s.text, s.kind) for s in parsed.output.personal_spans]).text
    _REDACTED[cv["file"]] = (text, parsed.cost_usd)
    return text, 0.0  # the parser cost is phase 2's; the bar is the matcher's


async def _one(cv: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    from app.agents.job_matcher import choose, match_job
    from app.llm.client import LLMAuthError, LLMBudgetExceeded, LLMError, LLMProviderError
    from evals.harness import HarnessError

    try:
        text, _ = await _redacted(cv)
        if text is None:
            return {"status": "unreadable", "job": None, "cost_usd": 0.0}
        jobs = _jobs(keys)
        r = await match_job(RUNTIME["llm"], jobs=jobs, cv_text=text, candidate_id="eval")
    except LLMBudgetExceeded as exc:
        raise HarnessError(f"eval stopped by the call ceiling: {exc}") from exc
    except (LLMAuthError, LLMProviderError) as exc:
        raise HarnessError(
            f"model provider unavailable, eval not measured: {str(exc)[:300]}"
        ) from exc
    except LLMError as exc:
        return {"status": "error", "job": None, "error": str(exc)[:300], "cost_usd": 0.0}
    s = RUNTIME["settings"]
    pick = choose(r.output, threshold=s.match_threshold, gap=s.match_gap)
    by_id = {str(uuid.uuid5(uuid.NAMESPACE_URL, k)): k for k in keys}
    return {
        "status": "matched",
        "job": by_id[str(pick.job_id)] if pick.job_id else None,
        "fits": {by_id.get(f.job_id, f.job_id): round(f.fit, 2) for f in r.output.fits},
        "why": pick.why,
        "cost_usd": r.cost_usd,
    }


async def job_matcher_v1(case_input: dict[str, Any]) -> dict[str, Any]:
    try:
        if case_input.get("pair"):
            return {
                "a": await _one(case_input["a"], case_input["jobs"]),
                "b": await _one(case_input["b"], case_input["jobs"]),
            }
        return await _one(case_input["cv"], case_input["jobs"])
    finally:
        tracer = RUNTIME.get("tracer")
        if tracer is not None:
            tracer.flush()
