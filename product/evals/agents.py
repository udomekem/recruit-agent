"""Agents the harness can run, by name and version.

Phase 0 has one deterministic stand-in (no model) so the harness itself can be proven:
`dummy` maps a right-to-work style answer to a label. `v1-regressed` is a planted
regression that mislabels two answers (three of the ten cases in dummy-v1, because two
cases normalise to the same answer); it exists only for the harness self test.
Real agents register here from phase 1 on.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

AgentFn = Callable[[dict[str, Any]], dict[str, Any]]

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


AGENTS: dict[str, dict[str, AgentFn]] = {
    "dummy": {"v1": dummy_v1, "v1-regressed": dummy_v1_regressed},
}
