"""Agents the harness can run, by name and version.

- `dummy`: deterministic stand-in (no model) so the harness itself can be proven.
  `v1-regressed` is a planted regression that mislabels two answers (three of the ten
  cases in dummy-v1, because two cases normalise to the same answer); it exists only for
  the harness self test.
- `rubric_builder` v1: the real phase 1 agent with the real model. Needs
  ANTHROPIC_API_KEY; a per run call ceiling stops runaway spend.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

AgentFn = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]

_TABLE = {
    "yes": "eligible",
    "yes, citizen": "eligible",
    "australian citizen": "eligible",
    "permanent resident": "eligible",
    "yes, permanent resident": "eligible",
    "no": "not_eligible",
    "need sponsorship": "not_eligible",
    "no, i need sponsorship": "not_eligible",
}


def _normalise(answer: str) -> str:
    return " ".join(answer.lower().strip().rstrip(".!").split())


def dummy_v1(case_input: dict[str, Any]) -> dict[str, Any]:
    key = _normalise(str(case_input.get("answer", "")))
    return {"label": _TABLE.get(key, "unknown")}


def dummy_v1_regressed(case_input: dict[str, Any]) -> dict[str, Any]:
    out = dummy_v1(case_input)
    key = _normalise(str(case_input.get("answer", "")))
    if key in {"permanent resident", "need sponsorship"}:  # planted bug
        out["label"] = "unknown"
    return out


_RUNTIME: dict[str, Any] = {}


def prepare_runtime(agent: str, *, max_calls: int) -> None:
    """Build the real model client once per check, with a call ceiling."""
    if agent not in ("rubric_builder", "cv_parser"):
        return
    from app.config import get_settings
    from app.llm.factory import make_llm, provider_key_name
    from app.observability.tracing import make_tracer
    from evals.harness import HarnessError

    settings = get_settings().model_copy(update={"llm_max_calls_per_process": max_calls})
    tracer = make_tracer(settings)
    llm = make_llm(settings, tracer)
    if llm is None:
        raise HarnessError(f"{agent} evals need {provider_key_name(settings)} (real model)")
    _RUNTIME["llm"] = llm
    _RUNTIME["tracer"] = tracer


async def rubric_builder_v1(case_input: dict[str, Any]) -> dict[str, Any]:
    from app.agents.rubric_builder import build_rubric
    from app.llm.client import LLMAuthError, LLMBudgetExceeded, LLMError, LLMProviderError
    from evals.harness import HarnessError

    try:
        r = await build_rubric(
            _RUNTIME["llm"],
            title=case_input["title"],
            location=case_input["location"],
            work_arrangement=case_input["work_arrangement"],
            salary_min=case_input["salary_min"],
            salary_max=case_input["salary_max"],
            description=case_input["description"],
        )
    except LLMBudgetExceeded as exc:
        raise HarnessError(f"eval stopped by the call ceiling: {exc}") from exc
    except (LLMAuthError, LLMProviderError) as exc:
        # The provider could not be reached or refused the account (key, billing, outage):
        # nothing about the agent was measured, so this is a harness error, never a score.
        raise HarnessError(
            f"model provider unavailable, eval not measured: {str(exc)[:300]}"
        ) from exc
    except LLMError as exc:  # invalid output after retries, or a refusal: a real agent failure
        return {
            "valid": False,
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            "criteria": [],
            "flags": [],
            "cost_usd": 0.0,
        }
    finally:
        tracer = _RUNTIME.get("tracer")
        if tracer is not None:
            tracer.flush()
    return {
        "valid": True,
        "criteria": [c.model_dump() for c in r.output.criteria],
        "flags": [f.model_dump() for f in r.output.flags],
        "cost_usd": r.cost_usd,
        "attempts": r.attempts,
        "model": r.model,
        "prompt_version": r.prompt_version,
        "latency_ms": r.latency_ms,
    }


async def cv_parser_v1(case_input: dict[str, Any]) -> dict[str, Any]:
    """The phase 2 parse path without the database: extract, pre redact, parse, final
    redact. Records the exact text sent to the model for the data minimisation bar."""
    from pathlib import Path

    from app.agents.cv_parser import parse_cv
    from app.intake.extract import extract
    from app.intake.redact import final_redact, pre_redact
    from app.llm.client import LLMAuthError, LLMBudgetExceeded, LLMError, LLMProviderError
    from evals.harness import DATASETS, HarnessError

    path = Path(DATASETS) / case_input["file"]
    media = (
        "application/pdf"
        if path.suffix == ".pdf"
        else ("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    )
    ex = await extract(path.read_bytes(), media)
    if ex.status != "ok":
        return {
            "status": ex.status,
            "model_calls": 0,
            "redacted_text": None,
            "sent_text": None,
            "profile": None,
            "cost_usd": 0.0,
        }
    it = case_input["intake"]
    pre = pre_redact(ex.text, name=it["name"], email=it["email"], phone=it["phone"])
    try:
        r = await parse_cv(_RUNTIME["llm"], pre_redacted_text=pre.text, candidate_id="eval")
    except LLMBudgetExceeded as exc:
        raise HarnessError(f"eval stopped by the call ceiling: {exc}") from exc
    except (LLMAuthError, LLMProviderError) as exc:
        raise HarnessError(
            f"model provider unavailable, eval not measured: {str(exc)[:300]}"
        ) from exc
    except LLMError as exc:
        return {
            "status": "failed",
            "error": type(exc).__name__,
            "model_calls": 1,
            "redacted_text": None,
            "sent_text": pre.text,
            "profile": None,
            "cost_usd": 0.0,
        }
    finally:
        tracer = _RUNTIME.get("tracer")
        if tracer is not None:
            tracer.flush()
    final = final_redact(pre, [(sp.text, sp.kind) for sp in r.output.personal_spans])
    return {
        "status": "parsed",
        "model_calls": r.attempts,
        "redacted_text": final.text,
        "sent_text": pre.text,
        "profile": r.output.model_dump(mode="json", exclude={"personal_spans"}),
        "cost_usd": r.cost_usd,
        "prompt_version": r.prompt_version,
        "model": r.model,
        "latency_ms": r.latency_ms,
    }


AGENTS: dict[str, dict[str, AgentFn]] = {
    "dummy": {"v1": dummy_v1, "v1-regressed": dummy_v1_regressed},
    "rubric_builder": {"v1": rubric_builder_v1},
    "cv_parser": {"v1": cv_parser_v1},
}


def get_agent(name: str, version: str) -> AgentFn:
    from evals.harness import HarnessError

    try:
        return AGENTS[name][version]
    except KeyError as exc:
        raise HarnessError(f"unknown agent {name} {version}") from exc
