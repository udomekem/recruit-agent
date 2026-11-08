"""Eval harness (spec: stages/04-evals/references/eval-harness-spec.md).

Exit codes: 0 every bar passed (or, for a suite with expect_gate = "FAIL", the gate failed
as expected); 1 a bar failed (or a self test gate unexpectedly passed); 2 the harness
itself errored (bad dataset, unknown agent, crash). A harness error is never a PASS.

A check runs one agent version over one dataset `runs` times, once, and scores every
metric in its `bars` from those same runs (real model agents are never re-run per
metric). Bars are `{min = x}` (higher is better) or `{max = x}` (lower is better).
A check whose dataset still has `draft` labels cannot PASS: labels must be reviewed.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import subprocess
import tomllib
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, ValidationError

ROOT = Path(__file__).resolve().parent
DATASETS = ROOT / "datasets"
REPORTS = ROOT / "reports"
SUITES = ROOT / "suites.toml"

Status = Literal["PASS", "FAIL"]
Direction = Literal["min", "max"]
Runs = list[list[dict[str, Any]]]
MetricFn = Callable[[list["Case"], Runs], tuple[float, float, list[dict[str, Any]]]]


class HarnessError(Exception):
    pass


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    agent: str
    tags: list[str] = []
    input: dict[str, Any]
    expected: dict[str, Any]
    label_source: Literal["draft", "hand", "rule", "judge"]
    notes: str = ""
    pair_id: str | None = None
    reviewed_by: str | None = None
    reviewed_at: str | None = None


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
    direction: Direction = "min"
    note: str = ""
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
    spend_usd: float = 0.0
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)


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


# ---- metrics -------------------------------------------------------------------------


def _exact(output: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(output.get(k) == v for k, v in expected.items())


def exact_match(cases: list[Case], runs: Runs) -> tuple[float, float, list[dict[str, Any]]]:
    per_run = [
        sum(_exact(o, c.expected) for o, c in zip(r, cases, strict=True)) / len(cases) for r in runs
    ]
    failing = [
        {"id": c.id, "expected": c.expected, "got": runs[0][i], "notes": c.notes}
        for i, c in enumerate(cases)
        if not _exact(runs[0][i], c.expected)
    ]
    return min(per_run), max(per_run) - min(per_run), failing


def determinism(cases: list[Case], runs: Runs) -> tuple[float, float, list[dict[str, Any]]]:
    if len(runs) < 2:
        raise HarnessError("determinism needs runs >= 2")
    stable = [all(r[i] == runs[0][i] for r in runs) for i in range(len(cases))]
    failing = [
        {"id": c.id, "outputs": [r[i] for r in runs]} for i, c in enumerate(cases) if not stable[i]
    ]
    return sum(stable) / len(cases), 0.0, failing


def metrics() -> dict[str, MetricFn]:
    from evals.cv_metrics import METRICS as CV
    from evals.rubric_metrics import METRICS as RUBRIC
    from evals.score_metrics import METRICS as SCORE

    return {"exact_match": exact_match, "determinism": determinism, **RUBRIC, **CV, **SCORE}


# ---- running -------------------------------------------------------------------------


def _bars(name: str, spec: dict[str, Any]) -> dict[str, tuple[Direction, float]]:
    if "bars" in spec:
        out: dict[str, tuple[Direction, float]] = {}
        for metric, bar in spec["bars"].items():
            if not isinstance(bar, dict) or len(bar) != 1 or next(iter(bar)) not in ("min", "max"):
                raise HarnessError(
                    f"check {name}: bar for {metric} must be {{min = x}} or {{max = x}}"
                )
            direction = cast(Direction, next(iter(bar)))
            out[metric] = (direction, float(bar[direction]))
        return out
    if "metric" in spec and "threshold" in spec:
        return {spec["metric"]: ("min", float(spec["threshold"]))}
    raise HarnessError(f"check {name} needs `bars` or `metric` and `threshold`")


async def _run_agent(
    fn: Callable[..., Any], cases: list[Case], n_runs: int, concurrency: int
) -> Runs:
    sem = asyncio.Semaphore(concurrency)

    async def one(case: Case) -> dict[str, Any]:
        async with sem:
            out = fn(case.input)
            if inspect.isawaitable(out):
                out = await out
            return cast(dict[str, Any], out)

    runs: Runs = []
    for _ in range(n_runs):
        runs.append(list(await asyncio.gather(*(one(c) for c in cases))))
    return runs


def run_check(name: str, spec: dict[str, Any], report: Report | None = None) -> list[CheckResult]:
    from evals.agents import get_agent, prepare_runtime

    try:
        dataset, agent, version = spec["dataset"], spec["agent"], spec["agent_version"]
        n_runs = int(spec.get("runs", 1))
    except KeyError as exc:
        raise HarnessError(f"check {name} is missing {exc}") from exc
    bars = _bars(name, spec)
    known = metrics()
    for m in bars:
        if m not in known:
            raise HarnessError(f"check {name}: unknown metric {m}")
    cases = load_dataset(dataset)
    wrong = [c.id for c in cases if c.agent != agent]
    if wrong:
        raise HarnessError(f"check {name}: cases {wrong} belong to another agent")
    fn = get_agent(agent, version)
    prepare_runtime(agent, max_calls=int(spec.get("max_calls", 200)), version=version)
    try:
        runs = asyncio.run(_run_agent(fn, cases, n_runs, int(spec.get("concurrency", 1))))
    except HarnessError:
        raise
    except Exception as exc:
        raise HarnessError(f"check {name}: agent crashed: {type(exc).__name__}: {exc}") from exc

    draft = [c.id for c in cases if c.label_source == "draft"]
    note = f"labels not reviewed ({len(draft)} draft cases): gate cannot pass" if draft else ""
    if report is not None:
        report.outputs[name] = {
            "dataset": dataset,
            "agent": agent,
            "version": version,
            "by_case": {c.id: runs[0][i] for i, c in enumerate(cases)},
        }
        report.spend_usd += sum(float(o.get("cost_usd") or 0.0) for run in runs for o in run)

    results = []
    for metric, (direction, threshold) in bars.items():
        value, spread, failing = known[metric](cases, runs)
        ok = value >= threshold if direction == "min" else value <= threshold
        results.append(
            CheckResult(
                name=name if len(bars) == 1 else f"{name}:{metric}",
                dataset=dataset,
                agent=agent,
                agent_version=version,
                metric=metric,
                threshold=threshold,
                value=round(value, 6),
                runs=n_runs,
                spread=round(spread, 6),
                status="PASS" if ok and not draft else "FAIL",
                direction=direction,
                note=note,
                failing_cases=failing,
            )
        )
    return results


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
        better = delta > 0 if c.direction == "min" else delta < 0
        change = "same" if delta == 0 else "improvement" if better else "regression"
        rows.append(
            {
                "check": c.name,
                "baseline": b["value"],
                "now": c.value,
                "delta": delta,
                "change": change,
            }
        )
    rows.sort(key=lambda r: r["change"] != "regression")
    return rows


def run_suite(suite_name: str, *, suites_path: Path = SUITES) -> Report:
    suites = load_suites(suites_path)
    suite = suites.get("suites", {}).get(suite_name)
    if suite is None:
        raise HarnessError(f"unknown suite {suite_name}")
    checks_spec = suites.get("checks", {})
    sha, dirty = _git()
    now = datetime.now(UTC)
    report = Report(
        suite=suite_name,
        run_id=now.strftime("%Y%m%dT%H%M%SZ"),
        started_at=now.isoformat(),
        git_sha=sha,
        git_dirty=dirty,
        expect_gate=suite.get("expect_gate", "PASS"),
        gate="FAIL",
        outcome="FAIL",
        checks=[],
    )
    for name in suite["checks"]:
        if name not in checks_spec:
            raise HarnessError(f"suite {suite_name} names unknown check {name}")
        report.checks += run_check(name, checks_spec[name], report)
    report.gate = "PASS" if all(r.status == "PASS" for r in report.checks) else "FAIL"
    report.outcome = "PASS" if report.gate == report.expect_gate else "FAIL"
    report.baseline_comparison = compare(report, REPORTS / f"baseline-{suite_name}.json")
    return report


# ---- reporting -----------------------------------------------------------------------


def to_markdown(r: Report) -> str:
    lines = [
        f"# Eval report: {r.suite}",
        "",
        f"Run {r.run_id} · git {r.git_sha}{' (dirty)' if r.git_dirty else ''} · "
        f"gate **{r.gate}** (expected {r.expect_gate}) · outcome **{r.outcome}**"
        + (f" · model spend ${r.spend_usd:.4f}" if r.spend_usd else ""),
        "",
        "| Check | Agent | Dataset | Metric | Bar | Result (spread, runs) | Status |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in r.checks:
        bar = f"≥ {c.threshold:g}" if c.direction == "min" else f"≤ {c.threshold:g}"
        lines.append(
            f"| {c.name} | {c.agent} {c.agent_version} | {c.dataset} | {c.metric} | {bar} | "
            f"{c.value:.4g} ({c.spread:.3g}, {c.runs}) | {c.status} |"
        )
    notes = sorted({c.note for c in r.checks if c.note})
    if notes:
        lines += ["", "## Notes", "", *[f"- {n}" for n in notes]]
    lines += ["", "## Failing cases", ""]
    failing = [(c.name, f) for c in r.checks for f in c.failing_cases]
    lines += [f"- `{name}` {json.dumps(f, ensure_ascii=False)}" for name, f in failing] or ["None."]
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


def _public(r: Report) -> dict[str, Any]:
    d = asdict(r)
    d.pop("outputs", None)
    return d


def write(report: Report, out_dir: Path = REPORTS) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{report.suite}-{report.run_id}-{report.git_sha}"
    j, m = out_dir / f"{stem}.json", out_dir / f"{stem}.md"
    j.write_text(json.dumps(_public(report), indent=2, ensure_ascii=False))
    m.write_text(to_markdown(report))
    (out_dir / f"latest-{report.suite}.json").write_text(
        json.dumps(_public(report), indent=2, ensure_ascii=False)
    )
    (out_dir / f"latest-{report.suite}.md").write_text(to_markdown(report))
    if any(c.agent != "dummy" for c in report.checks):  # keep real model outputs for review
        (out_dir / f"{stem}-outputs.json").write_text(
            json.dumps(report.outputs, indent=2, ensure_ascii=False)
        )
    return j, m


def push_to_langfuse(report: Report, settings: Any) -> list[str]:
    """Record each check as a Langfuse dataset experiment using the outputs already
    produced (no extra model calls). Best effort: never changes the gate."""
    from langfuse import Evaluation, Langfuse

    from evals.cv_metrics import item_score as cv_item_score
    from evals.rubric_metrics import item_score

    client = Langfuse(
        public_key=settings.langfuse_public_key.get_secret_value(),
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        base_url=settings.langfuse_base_url,
        environment=settings.environment,
    )
    urls = []
    for check, info in report.outputs.items():
        ds_name = f"recruit-agent/{info['dataset']}"
        try:
            client.get_dataset(ds_name)
        except Exception:
            client.create_dataset(name=ds_name, description=f"synthetic eval set {info['dataset']}")
        cases = {c.id: c for c in load_dataset(info["dataset"])}
        for case in cases.values():
            client.create_dataset_item(
                dataset_name=ds_name,
                input=case.input,
                expected_output=case.expected,
                metadata={"case_id": case.id, "tags": case.tags, "label_source": case.label_source},
                id=f"{info['dataset']}-{case.id}",
            )
        by_case = info["by_case"]

        def task(*, item: Any, _by: dict[str, Any] = by_case, **_: Any) -> Any:
            return _by[(item.metadata or {})["case_id"]]

        def score(
            *,
            output: Any,
            expected_output: Any,
            metadata: Any = None,
            _cases: dict[str, Case] = cases,
            _agent: str = info["agent"],
            **_: Any,
        ) -> Evaluation:
            case = _cases[(metadata or {})["case_id"]]
            if _agent == "dummy":
                return Evaluation(
                    name="exact_match", value=1.0 if _exact(output, expected_output) else 0.0
                )
            if _agent == "cv_parser":
                return Evaluation(name="field_accuracy", value=cv_item_score(case, output))
            if _agent in ("cv_scorer", "answer_scorer"):
                from evals.score_metrics import item_score as score_item

                return Evaluation(name="agreement", value=score_item(case, output))
            return Evaluation(name="must_have_recall", value=item_score(case, output))

        result = client.get_dataset(ds_name).run_experiment(
            name=check,
            run_name=f"{check}-{report.git_sha}-{report.run_id}",
            task=cast(Any, task),
            evaluators=[cast(Any, score)],
            metadata={
                "agent_version": info["version"],
                "git_sha": report.git_sha,
                "suite": report.suite,
            },
        )
        if result.dataset_run_url:
            urls.append(result.dataset_run_url)
    client.flush()
    return urls
