"""Render a dataset as a Markdown page a human can review, and record their approval.

`python -m evals review rubric-v1` writes `evals/datasets/rubric-v1-review.md`.
`python -m evals approve rubric-v1 --by Mani --cases all` marks reviewed cases as `hand`.
The JSONL stays the single source; the page is generated from it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.harness import DATASETS, HarnessError, load_dataset


def _crit(items: list[dict[str, Any]]) -> list[str]:
    return [
        f"  - `{i['id']}` matches: {', '.join(repr(p) for p in i['phrases'])}" for i in items
    ] or ["  - (none)"]


def render(name: str) -> Path:
    cases = load_dataset(name)
    out = DATASETS / f"{name}-review.md"
    lines = [
        f"# Review: {name}",
        "",
        "Check each ad's labels. A label is right when a careful recruiter reading the ad would",
        "agree. For each criterion, the phrases are how a generated criterion is matched (any",
        "phrase found in its text, ignoring case and spacing). Mark each case OK or write the fix.",
        "",
        f"{len(cases)} cases. Status: "
        + ", ".join(f"{s}: {sum(c.label_source == s for c in cases)}" for s in ("draft", "hand")),
        "",
    ]
    for c in cases:
        inp, exp = c.input, c.expected
        lines += [
            f"## {c.id}: {inp.get('title')} ({', '.join(c.tags)}) · labels: {c.label_source}",
            "",
            f"{inp.get('location')} · {inp.get('work_arrangement')} · "
            f"${inp.get('salary_min'):,} to ${inp.get('salary_max'):,}",
            "",
            "```text",
            str(inp.get("description", "")),
            "```",
            "",
            "**Must haves**",
            *_crit(exp.get("must_haves", [])),
            "",
            "**Nice to haves**",
            *_crit(exp.get("nice_to_haves", [])),
            "",
            "**Must never appear in a criterion:** "
            + (", ".join(repr(t) for t in exp.get("forbidden_terms", [])) or "(none)"),
            f"**Flags expected (at least):** {exp.get('min_flags', 0)}",
            "",
            f"Notes: {c.notes or '(none)'}",
            "",
            "- [ ] OK   Fix: ",
            "",
        ]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def approve(name: str, by: str, case_ids: list[str] | None) -> int:
    path = DATASETS / f"{name}.jsonl"
    if not path.is_file():
        raise HarnessError(f"dataset not found: {path}")
    load_dataset(name)  # validates
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    wanted = set(case_ids) if case_ids else {r["id"] for r in rows}
    unknown = wanted - {r["id"] for r in rows}
    if unknown:
        raise HarnessError(f"unknown case ids: {sorted(unknown)}")
    now = datetime.now(UTC).date().isoformat()
    changed = 0
    for r in rows:
        if r["id"] in wanted and r["label_source"] != "hand":
            r["label_source"], r["reviewed_by"], r["reviewed_at"] = "hand", by, now
            changed += 1
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    return changed
