"""The eval harness gates correctly: pass, planted regression, determinism, harness errors."""

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
    r = run_check(
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
    r = run_check(
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
    r = run_check(
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
