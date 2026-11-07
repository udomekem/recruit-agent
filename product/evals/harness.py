"""Eval harness (spec: stages/04-evals/references/eval-harness-spec.md).

Exit codes: 0 every bar passed (or, for a suite with expect_gate = "FAIL", the gate failed
as expected); 1 a bar failed (or a self test gate unexpectedly passed); 2 the harness
itself errored (bad dataset, unknown agent, crash). A harness error is never a PASS.
"""

from __future__ import annotations

import json
import subprocess
import tomllib
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from evals.agents import AGENTS, AgentFn

ROOT = Path(__file__).resolve().parent
DATASETS = ROOT / "datasets"
REPORTS = ROOT / "reports"
SUITES = ROOT / "suites.toml"

Status = Literal["PASS", "FAIL"]


class HarnessError(Exception):
    pass


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    agent: str
    tags: list[str] = []
    input: dict[str, Any]
    expected: dict[str, Any]
    label_source: Literal["hand", "rule", "judge"]
    notes: str = ""
    pair_id: str | None = None


@dataclass
class CheckResult:
    name: str
    dataset: str
    agent: str
    agent_version: str
    metric: str
    threshold: float
    value: float
    runs: int
    spread: float
    status: Status
    failing_cases: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Report:
    suite: str
    run_id: str
    started_at: str
    git_sha: str
    git_dirty: bool
    expect_gate: Status
    gate: Status
    outcome: Status
    checks: list[CheckResult]
    baseline_comparison: list[dict[str, Any]] = field(default_factory=list)
    langfuse_runs: list[str] = field(default_factory=list)


def load_dataset(name: str) -> list[Case]:
    path = DATASETS / f"{name}.jsonl"
    if not path.is_file():
        raise HarnessError(f"dataset not found: {path}")
    cases: list[Case] = []
    seen: set[str] = set()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = Case.model_validate(json.loads(line))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HarnessError(f"{path.name} line {n} is malformed: {exc}") from exc
        if case.id in seen:
            raise HarnessError(f"{path.name} line {n}: duplicate case id {case.id}")
        seen.add(case.id)
        cases.append(case)
    if not cases:
        raise HarnessError(f"{path.name} has no cases")
    return cases


def load_suites(path: Path = SUITES) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise HarnessError(f"cannot read {path}: {exc}") from exc


def _agent(name: str, version: str) -> AgentFn:
    try:
        return AGENTS[name][version]
    except KeyError as exc:
        raise HarnessError(f"unknown agent {name} {version}") from exc


def _exact(output: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(output.get(k) == v for k, v in expected.items())


METRICS: dict[
    str,
    Callable[[list[Case], list[list[dict[str, Any]]]], tuple[float, float, list[dict[str, Any]]]],
] = {}


def _metric(name: str) -> Callable[[Any], Any]:
    def register(fn: Any) -> Any:
        METRICS[name] = fn
        return fn

    return register


@_metric("exact_match")
def exact_match(
    cases: list[Case], runs: list[list[dict[str, Any]]]
) -> tuple[float, float, list[dict[str, Any]]]:
    per_run = [
        sum(_exact(o, c.expected) for o, c in zip(r, cases, strict=True)) / len(cases) for r in runs
    ]
    failing = [
        {"id": c.id, "expected": c.expected, "got": runs[0][i], "notes": c.notes}
        for i, c in enumerate(cases)
        if not _exact(runs[0][i], c.expected)
    ]
    return min(per_run), max(per_run) - min(per_run), failing


@_metric("determinism")
def determinism(
    cases: list[Case], runs: list[list[dict[str, Any]]]
) -> tuple[float, float, list[dict[str, Any]]]:
    if len(runs) < 2:
        raise HarnessError("determinism needs runs >= 2")
    stable = [all(r[i] == runs[0][i] for r in runs) for i in range(len(cases))]
    failing = [
        {"id": c.id, "outputs": [r[i] for r in runs]} for i, c in enumerate(cases) if not stable[i]
    ]
    return sum(stable) / len(cases), 0.0, failing


def run_check(name: str, spec: dict[str, Any]) -> CheckResult:
    try:
        dataset, agent, version, metric = (
            spec["dataset"],
            spec["agent"],
            spec["agent_version"],
            spec["metric"],
        )
        threshold, n_runs = float(spec["threshold"]), int(spec.get("runs", 1))
    except KeyError as exc:
        raise HarnessError(f"check {name} is missing {exc}") from exc
    if metric not in METRICS:
        raise HarnessError(f"check {name}: unknown metric {metric}")
    cases = load_dataset(dataset)
    wrong_agent = [c.id for c in cases if c.agent != agent]
    if wrong_agent:
        raise HarnessError(f"check {name}: cases {wrong_agent} belong to another agent")
    fn = _agent(agent, version)
    runs: list[list[dict[str, Any]]] = []
    for _ in range(n_runs):
        try:
            runs.append([fn(c.input) for c in cases])
        except Exception as exc:
            raise HarnessError(f"check {name}: agent crashed: {type(exc).__name__}: {exc}") from exc
    value, spread, failing = METRICS[metric](cases, runs)
    return CheckResult(
        name=name,
        dataset=dataset,
        agent=agent,
        agent_version=version,
        metric=metric,
        threshold=threshold,
        value=round(value, 6),
        runs=n_runs,
        spread=round(spread, 6),
        status="PASS" if value >= threshold else "FAIL",
        failing_cases=failing,
    )


def _git() -> tuple[str, bool]:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=True,
                cwd=ROOT,
            ).stdout.strip()
        )
        return sha, dirty
    except (OSError, subprocess.CalledProcessError):
        return "unknown", False


def compare(report: Report, baseline_path: Path) -> list[dict[str, Any]]:
    if not baseline_path.is_file():
        return []
    base = {c["name"]: c for c in json.loads(baseline_path.read_text())["checks"]}
    rows = []
    for c in report.checks:
        b = base.get(c.name)
        if b is None:
            rows.append({"check": c.name, "baseline": None, "now": c.value, "change": "new"})
            continue
        delta = round(c.value - b["value"], 6)
        change = "regression" if delta < 0 else "improvement" if delta > 0 else "same"
        rows.append(
            {
                "check": c.name,
                "baseline": b["value"],
                "now": c.value,
                "delta": delta,
                "change": change,
            }
        )
    rows.sort(key=lambda r: r["change"] != "regression")  # regressions first
    return rows


def run_suite(suite_name: str, *, suites_path: Path = SUITES) -> Report:
    suites = load_suites(suites_path)
    suite = suites.get("suites", {}).get(suite_name)
    if suite is None:
        raise HarnessError(f"unknown suite {suite_name}")
    checks_spec = suites.get("checks", {})
    results = []
    for name in suite["checks"]:
        if name not in checks_spec:
            raise HarnessError(f"suite {suite_name} names unknown check {name}")
        results.append(run_check(name, checks_spec[name]))
    sha, dirty = _git()
    now = datetime.now(UTC)
    gate: Status = "PASS" if all(r.status == "PASS" for r in results) else "FAIL"
    expect: Status = suite.get("expect_gate", "PASS")
    report = Report(
        suite=suite_name,
        run_id=now.strftime("%Y%m%dT%H%M%SZ"),
        started_at=now.isoformat(),
        git_sha=sha,
        git_dirty=dirty,
        expect_gate=expect,
        gate=gate,
        outcome="PASS" if gate == expect else "FAIL",
        checks=results,
    )
    report.baseline_comparison = compare(report, REPORTS / f"baseline-{suite_name}.json")
    return report


def to_markdown(r: Report) -> str:
    lines = [
        f"# Eval report: {r.suite}",
        "",
        f"Run {r.run_id} · git {r.git_sha}{' (dirty)' if r.git_dirty else ''} · "
        f"gate **{r.gate}** (expected {r.expect_gate}) · outcome **{r.outcome}**",
        "",
        "| Check | Agent | Dataset | Metric | Threshold | Result (spread) | Status |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in r.checks:
        lines.append(
            f"| {c.name} | {c.agent} {c.agent_version} | {c.dataset} | {c.metric} | "
            f"{c.threshold:.2f} | {c.value:.3f} ({c.spread:.3f}, {c.runs} runs) | {c.status} |"
        )
    lines += ["", "## Failing cases", ""]
    failing = [(c.name, f) for c in r.checks for f in c.failing_cases]
    lines += [f"- `{name}` {json.dumps(f)}" for name, f in failing] or ["None."]
    lines += ["", "## Compared with baseline", ""]
    if r.baseline_comparison:
        lines += ["| Check | Baseline | Now | Change |", "|---|---|---|---|"]
        lines += [
            f"| {b['check']} | {b['baseline']} | {b['now']} | {b['change']} |"
            for b in r.baseline_comparison
        ]
    else:
        lines.append("No baseline yet.")
    if r.langfuse_runs:
        lines += ["", "## Langfuse runs", "", *[f"- {u}" for u in r.langfuse_runs]]
    return "\n".join(lines) + "\n"


def write(report: Report, out_dir: Path = REPORTS) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{report.suite}-{report.run_id}-{report.git_sha}"
    j, m = out_dir / f"{stem}.json", out_dir / f"{stem}.md"
    j.write_text(json.dumps(asdict(report), indent=2))
    m.write_text(to_markdown(report))
    (out_dir / f"latest-{report.suite}.json").write_text(json.dumps(asdict(report), indent=2))
    (out_dir / f"latest-{report.suite}.md").write_text(to_markdown(report))
    return j, m


def push_to_langfuse(report: Report, settings: Any) -> list[str]:
    """Record each check as a Langfuse dataset experiment so runs compare over time.
    Best effort: never changes the gate."""
    from langfuse import Evaluation, Langfuse

    client = Langfuse(
        public_key=settings.langfuse_public_key.get_secret_value(),
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        base_url=settings.langfuse_base_url,
        environment=settings.environment,
    )
    urls = []
    for c in report.checks:
        ds_name = f"recruit-agent/{c.dataset}"
        try:
            client.get_dataset(ds_name)
        except Exception:
            client.create_dataset(name=ds_name, description=f"synthetic eval set {c.dataset}")
        for case in load_dataset(c.dataset):
            client.create_dataset_item(
                dataset_name=ds_name,
                input=case.input,
                expected_output=case.expected,
                metadata={"tags": case.tags, "label_source": case.label_source},
                id=f"{c.dataset}-{case.id}",
            )
        fn = _agent(c.agent, c.agent_version)

        def task(*, item: Any, _fn: AgentFn = fn, **_: Any) -> dict[str, Any]:
            return _fn(item.input)

        def exact(*, output: Any, expected_output: Any, **_: Any) -> Evaluation:
            return Evaluation(
                name="exact_match", value=1.0 if _exact(output, expected_output) else 0.0
            )

        result = client.get_dataset(ds_name).run_experiment(
            name=c.name,
            run_name=f"{c.name}-{report.git_sha}-{report.run_id}",
            task=cast(Any, task),
            evaluators=[cast(Any, exact)],
            metadata={
                "agent_version": c.agent_version,
                "git_sha": report.git_sha,
                "suite": report.suite,
            },
        )
        if result.dataset_run_url:
            urls.append(result.dataset_run_url)
    client.flush()
    return urls
