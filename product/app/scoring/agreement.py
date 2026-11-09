"""Overrides and the recruiter agreement rate (phase 4 design section 6; master plan 7.2).

An override is a decision against the agent's band: shortlisting a reject, or rejecting an
advance. Maybe (and no score) is never an override. The rate counts only decisions on an
advance or reject recommendation.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

Recommended = Literal["advance", "maybe", "reject", "none"]
Choice = Literal["shortlist", "reject"]
MIN_OVERRIDE_REASON = 10


def is_override(recommended: str, decision: str) -> bool:
    return (recommended == "reject" and decision == "shortlist") or (
        recommended == "advance" and decision == "reject"
    )


def check_reason(recommended: str, decision: str, reason: str) -> None:
    """Raise ValueError when an override has no real reason."""
    if is_override(recommended, decision) and len(reason.strip()) < MIN_OVERRIDE_REASON:
        raise ValueError(
            f"this goes against the {recommended} recommendation: give a reason of at least "
            f"{MIN_OVERRIDE_REASON} characters"
        )


@dataclass(frozen=True)
class Agreement:
    decided: int
    counted: int  # decisions on an advance or reject recommendation
    agreed: int
    overrides: int
    maybe_or_none: int

    @property
    def rate(self) -> float | None:
        return round(self.agreed / self.counted, 3) if self.counted else None

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "decided": self.decided,
            "counted": self.counted,
            "agreed": self.agreed,
            "overrides": self.overrides,
            "maybe_or_none": self.maybe_or_none,
            "rate": self.rate,
        }


def agreement(pairs: Iterable[tuple[str, str]]) -> Agreement:
    """`pairs` are (recommended, decision)."""
    decided = counted = agreed = overrides = other = 0
    for rec, dec in pairs:
        decided += 1
        if rec not in ("advance", "reject"):
            other += 1
            continue
        counted += 1
        if is_override(rec, dec):
            overrides += 1
        else:
            agreed += 1
    return Agreement(decided, counted, agreed, overrides, other)
