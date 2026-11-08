"""Agents the harness can run, by name and version.

- `dummy`: deterministic stand-in (no model) so the harness itself can be proven.
  `v1-regressed` is a planted regression that mislabels two answers (three of the ten
  cases in dummy-v1, because two cases normalise to the same answer); it exists only for
  the harness self test.
- `rubric_builder` v1: the real phase 1 agent with the real model. Needs
  ANTHROPIC_API_KEY; a per run call ceiling stops runaway spend.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
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


def prepare_runtime(agent: str, *, max_calls: int, version: str = "v1") -> None:
    """Build the real model client once per check, with a call ceiling."""
    if agent not in ("rubric_builder", "cv_parser", "cv_scorer") or version in NO_MODEL:
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


# ---- phase 3: CV scorer (whole path), planted regression, answer scorer ---------------

NO_MODEL = {"v1-planted-lift"}
_RUBRICS: dict[str, Any] = {}


def _rubric(job: str) -> dict[str, Any]:
    if not _RUBRICS:
        import json
        from pathlib import Path

        from evals.harness import DATASETS

        _RUBRICS.update(json.loads((Path(DATASETS) / "score-rubrics-v1.json").read_text()))
    return dict(_RUBRICS[job])


async def _extract_and_redact(one: dict[str, Any]) -> tuple[Any, Any]:
    from pathlib import Path

    from app.intake.extract import extract
    from app.intake.redact import pre_redact
    from evals.harness import DATASETS

    path = Path(DATASETS) / one["file"]
    media = (
        "application/pdf"
        if path.suffix == ".pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    ex = await extract(path.read_bytes(), media)
    if ex.status != "ok":
        return ex, None
    it = one["intake"]
    return ex, pre_redact(ex.text, name=it["name"], email=it["email"], phone=it["phone"])


def _card(one: dict[str, Any], verdicts: Mapping[str, str], injection: bool, hidden: int) -> Any:
    from app.scoring.answers import score_answers
    from app.scoring.formula import score_card
    from evals.score_inputs import questions

    rubric = _rubric(one["job"])
    answers = score_answers(questions(one.get("answers")), salary_max=rubric["salary_max"])
    return score_card(
        rubric["criteria"], verdicts, answers, injection_suspected=injection, hidden_chars=hidden
    )


async def _score_one_v1(one: dict[str, Any]) -> dict[str, Any]:
    """The phase 3 path without the database: extract (hidden text removed), pre redact,
    parse, final redact, score against the fixed rubric, then code computes the card."""
    from app.agents.cv_parser import parse_cv
    from app.agents.cv_scorer import injection_phrases, score_cv
    from app.intake.redact import final_redact, normalise
    from app.llm.client import LLMAuthError, LLMBudgetExceeded, LLMError, LLMProviderError
    from evals.harness import HarnessError

    ex, pre = await _extract_and_redact(one)
    if pre is None:
        return {"status": ex.status, "cost_usd": 0.0}
    llm = _RUNTIME["llm"]
    cost = 0.0
    try:
        parsed = await parse_cv(llm, pre_redacted_text=pre.text, candidate_id="eval")
        cost += parsed.cost_usd
        final = final_redact(pre, [(s.text, s.kind) for s in parsed.output.personal_spans])
        criteria = _rubric(one["job"])["criteria"]
        as_of = _RUBRICS.get("as_of")  # loaded by _rubric() above
        r = await score_cv(
            llm,
            redacted_text=final.text,
            criteria=criteria,
            candidate_id="eval",
            today=(int(as_of[0]), int(as_of[1])) if as_of else None,
        )
        cost += r.cost_usd
    except LLMBudgetExceeded as exc:
        raise HarnessError(f"eval stopped by the call ceiling: {exc}") from exc
    except (LLMAuthError, LLMProviderError) as exc:
        raise HarnessError(
            f"model provider unavailable, eval not measured: {str(exc)[:300]}"
        ) from exc
    except LLMError as exc:  # synthetic CVs only, so the detail may be kept here
        return {
            "status": "failed",
            "error": f"{type(exc).__name__}: {str(exc)[:400]}",
            "cost_usd": cost,
        }
    finally:
        tracer = _RUNTIME.get("tracer")
        if tracer is not None:
            tracer.flush()
    verdicts = {j.criterion_id: j.verdict for j in r.output.judgements}
    quotes = [j.quote for j in r.output.judgements if j.verdict != "not_met"]
    text_n = normalise(final.text)
    injection = r.output.injection_suspected or injection_phrases(final.text)
    card = _card(one, verdicts, injection, ex.hidden_chars)
    return {
        "status": "scored",
        "total": card.total,
        "band": card.band,
        "verdicts": verdicts,
        "quotes_found": sum(normalise(q) in text_n for q in quotes),
        "quotes_total": len(quotes),
        "injection": injection,
        "model_injection": r.output.injection_suspected,
        "hidden_chars": ex.hidden_chars,
        "flags": sorted({f.kind for f in card.flags}),
        "cost_usd": cost,
        "attempts": r.attempts,
        "model": r.model,
        "prompt_version": r.prompt_version,
    }


async def _score_one_planted(one: dict[str, Any]) -> dict[str, Any]:
    """Harness self test only (no model): every criterion half met, plus a planted bug that
    adds lift when the copy contains an injection phrase, and never flags it."""
    from app.agents.cv_scorer import injection_phrases

    ex, pre = await _extract_and_redact(one)
    if pre is None:
        return {"status": ex.status, "cost_usd": 0.0}
    criteria = _rubric(one["job"])["criteria"]
    verdicts = dict.fromkeys((c["id"] for c in criteria), "partly_met")
    if injection_phrases(pre.text):  # planted bug
        verdicts = dict.fromkeys(verdicts, "met")
    card = _card(one, verdicts, False, 0)
    return {
        "status": "scored",
        "total": card.total,
        "band": card.band,
        "verdicts": verdicts,
        "quotes_found": 0,
        "quotes_total": 0,
        "injection": False,
        "hidden_chars": 0,
        "flags": [],
        "cost_usd": 0.0,
    }


def _scorer(one_fn: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]) -> AgentFn:
    async def run(case_input: dict[str, Any]) -> dict[str, Any]:
        import asyncio

        if case_input.get("pair"):
            a, b = await asyncio.gather(one_fn(case_input["a"]), one_fn(case_input["b"]))
            return {"a": a, "b": b, "cost_usd": a["cost_usd"] + b["cost_usd"], "docs": 2}
        return {**(await one_fn(case_input)), "docs": 1}

    return run


def answer_scorer_v1(case_input: dict[str, Any]) -> dict[str, Any]:
    """Form coercion then the answer scorer, as the application does (no model)."""
    from app.domain.questions import coerce_answer, standard_questions
    from app.scoring.answers import QuestionInput, score_answer

    spec = next(
        q for q in standard_questions("Sydney NSW", "onsite") if q.key == case_input["question"]
    )
    raw = case_input["raw"]
    try:
        value = None if raw is None else coerce_answer(spec.answer_type.value, spec.choices, raw)
    except ValueError:
        return {"outcome": "refused"}
    rule = spec.knockout_rule.model_dump() if spec.knockout_rule else None
    res = score_answer(
        QuestionInput(spec.key, spec.prompt, spec.answer_type.value, rule, value),
        salary_max=int(case_input["salary_max"]),
    )
    return {"outcome": res.outcome}


AGENTS: dict[str, dict[str, AgentFn]] = {
    "dummy": {"v1": dummy_v1, "v1-regressed": dummy_v1_regressed},
    "rubric_builder": {"v1": rubric_builder_v1},
    "cv_parser": {"v1": cv_parser_v1},
    "cv_scorer": {"v1": _scorer(_score_one_v1), "v1-planted-lift": _scorer(_score_one_planted)},
    "answer_scorer": {"v1": answer_scorer_v1},
}


def get_agent(name: str, version: str) -> AgentFn:
    from evals.harness import HarnessError

    try:
        return AGENTS[name][version]
    except KeyError as exc:
        raise HarnessError(f"unknown agent {name} {version}") from exc
