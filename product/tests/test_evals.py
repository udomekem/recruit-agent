"""The eval harness gates correctly: pass, planted regression, determinism, harness errors."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from evals.harness import HarnessError, run_check, run_suite

PRODUCT = Path(__file__).resolve().parents[1]


def _cli(*args: str) -> int:
    return subprocess.run(
        [sys.executable, "-m", "evals", "run", "--no-langfuse", *args],
        cwd=PRODUCT,
        capture_output=True,
        text=True,
    ).returncode


def test_dummy_agent_passes_every_case() -> None:
    [r] = run_check(
        "x",
        {
            "dataset": "dummy-v1",
            "agent": "dummy",
            "agent_version": "v1",
            "metric": "exact_match",
            "threshold": 1.0,
        },
    )
    assert r.status == "PASS" and r.value == 1.0 and r.failing_cases == []


def test_planted_regression_fails_and_names_the_cases() -> None:
    [r] = run_check(
        "x",
        {
            "dataset": "dummy-v1",
            "agent": "dummy",
            "agent_version": "v1-regressed",
            "metric": "exact_match",
            "threshold": 1.0,
        },
    )
    assert r.status == "FAIL" and r.value == pytest.approx(0.7)
    assert {f["id"] for f in r.failing_cases} == {"dummy-004", "dummy-005", "dummy-007"}


def test_determinism_three_runs_identical() -> None:
    [r] = run_check(
        "x",
        {
            "dataset": "dummy-v1",
            "agent": "dummy",
            "agent_version": "v1",
            "metric": "determinism",
            "threshold": 1.0,
            "runs": 3,
        },
    )
    assert r.status == "PASS" and r.runs == 3


def test_fast_suite_gate_passes() -> None:
    report = run_suite("fast")
    assert report.gate == "PASS" and report.outcome == "PASS"


def test_cli_exit_codes() -> None:
    assert _cli("--suite", "fast") == 0
    assert _cli("--suite", "selftest") == 0  # gate FAIL was expected: the harness caught it
    assert _cli("--suite", "does-not-exist") == 2


def test_selftest_fails_if_regression_goes_unnoticed(tmp_path: Path) -> None:
    suites = tmp_path / "suites.toml"
    suites.write_text(
        '[suites.selftest]\nchecks=["c"]\nexpect_gate="FAIL"\n'
        '[checks.c]\ndataset="dummy-v1"\nagent="dummy"\nagent_version="v1"\n'
        'metric="exact_match"\nthreshold=1.0\n'
    )
    report = run_suite("selftest", suites_path=suites)
    assert report.gate == "PASS" and report.outcome == "FAIL"


def test_malformed_dataset_is_a_harness_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import evals.harness as h

    (tmp_path / "bad-v1.jsonl").write_text('{"id": "x", "agent": "dummy"}\n')
    monkeypatch.setattr(h, "DATASETS", tmp_path)
    with pytest.raises(HarnessError, match="malformed"):
        h.load_dataset("bad-v1")


# ---- rubric metrics (no model: hand made outputs) ---------------------------------

from evals.harness import Case  # noqa: E402
from evals.rubric_metrics import (  # noqa: E402
    consistency,
    discriminatory_flagged,
    injection_planted,
    precision,
    protected_criteria,
    recall,
)


def _case(**exp: object) -> Case:
    expected = {
        "must_haves": [
            {"id": "sql", "phrases": ["sql"]},
            {"id": "ba", "phrases": ["business analys"]},
        ],
        "nice_to_haves": [{"id": "agile", "phrases": ["agile"]}],
        "forbidden_terms": [],
        "min_flags": 0,
    }
    expected.update(exp)
    return Case(
        id="c1",
        agent="rubric_builder",
        tags=["normal"],
        input={},
        expected=expected,
        label_source="hand",
    )


def _out(*musts: str, nice: tuple[str, ...] = (), flags: int = 0) -> dict[str, object]:
    crits = [{"id": f"m{i}", "kind": "must_have", "text": t} for i, t in enumerate(musts)]
    crits += [{"id": f"n{i}", "kind": "nice_to_have", "text": t} for i, t in enumerate(nice)]
    return {"valid": True, "criteria": crits, "flags": [{}] * flags, "cost_usd": 0.01}


def test_recall_and_precision_from_phrases() -> None:
    case = _case()
    runs = [[_out("Working knowledge of SQL", "Agile experience", "Team player")]]
    r, _, failing = recall([case], runs)
    assert r == 0.5 and failing[0]["missed_must_haves"] == ["ba"]
    p, _, _ = precision([case], runs)
    assert abs(p - 2 / 3) < 1e-9  # agile counts (labelled nice to have), "team player" does not


def test_recall_is_worst_run_and_consistency_compares_runs() -> None:
    case = _case()
    good = _out("SQL skills", "3 years as a Business Analyst")
    half = _out("SQL skills")
    r, spread, _ = recall([case], [[good], [half]])
    assert r == 0.5 and spread == 0.5
    c, _, _ = consistency([case], [[good], [half]])
    assert c == 0.5


def test_protected_and_injection_counts() -> None:
    disc = _case(forbidden_terms=["young"], min_flags=1)
    disc.tags = ["discriminatory"]
    inj = _case(forbidden_terms=["sam"])
    inj.tags = ["injection"]
    runs = [[_out("Young and keen", flags=0), _out("Applicant named Sam Taylor")]]
    n, _, _ = protected_criteria([disc, inj], runs)
    assert n >= 1
    m, _, _ = injection_planted([disc, inj], runs)
    assert m == 1
    f, _, _ = discriminatory_flagged([disc, inj], runs)
    assert f == 0.0


def test_draft_labels_cannot_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import evals.harness as h

    row = {
        "id": "x1",
        "agent": "dummy",
        "input": {"answer": "yes"},
        "expected": {"label": "eligible"},
        "label_source": "draft",
    }
    (tmp_path / "d-v1.jsonl").write_text(json.dumps(row) + chr(10))
    monkeypatch.setattr(h, "DATASETS", tmp_path)
    [r] = h.run_check(
        "c",
        {
            "dataset": "d-v1",
            "agent": "dummy",
            "agent_version": "v1",
            "metric": "exact_match",
            "threshold": 1.0,
        },
    )
    assert r.value == 1.0 and r.status == "FAIL" and "not reviewed" in r.note


def test_max_direction_bar(tmp_path: Path) -> None:
    from evals.harness import _bars

    assert _bars("c", {"bars": {"mean_cost_usd": {"max": 0.05}}}) == {
        "mean_cost_usd": ("max", 0.05)
    }
    with pytest.raises(HarnessError):
        _bars("c", {"bars": {"x": {"around": 1}}})


def test_provider_outage_is_a_harness_error_not_a_score(monkeypatch: pytest.MonkeyPatch) -> None:
    """Found on the first real rubric run: a billing 400 was scored as 45 invalid outputs."""
    import asyncio

    import evals.agents as agents
    from app.llm.client import LLMProviderError

    async def boom(*a: object, **k: object) -> object:
        raise LLMProviderError("request rejected: 400: credit balance is too low")

    monkeypatch.setattr("app.agents.rubric_builder.build_rubric", boom)
    agents._RUNTIME["llm"] = object()
    with pytest.raises(HarnessError, match="provider unavailable"):
        asyncio.run(
            agents.rubric_builder_v1(
                {
                    "title": "x",
                    "location": "x",
                    "work_arrangement": "x",
                    "salary_min": 1,
                    "salary_max": 2,
                    "description": "x",
                }
            )
        )
