"""Versioned prompts live in `app/prompts/<prompt-id>/<version>.md`. A change to a prompt
is a new file with a new version; old versions stay so past outputs stay explainable."""

from dataclasses import dataclass
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


@dataclass(frozen=True)
class PromptRef:
    id: str
    version: str

    @property
    def label(self) -> str:
        return f"{self.id}-{self.version}"


class PromptNotFound(Exception):
    pass


def load_prompt(ref: PromptRef) -> str:
    path = PROMPTS_DIR / ref.id / f"{ref.version}.md"
    if not path.is_file():
        raise PromptNotFound(f"no prompt file at {path}")
    return path.read_text(encoding="utf-8").strip()
