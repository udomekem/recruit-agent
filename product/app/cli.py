"""Command line entry points. `python -m app.cli smoke` makes one real model call."""

from __future__ import annotations

import argparse
import asyncio
import sys

from pydantic import BaseModel, Field

from app.config import get_settings
from app.llm.client import LLMClient, ModelTier
from app.llm.prompts import PromptRef
from app.llm.providers import AnthropicProvider
from app.observability.tracing import make_tracer

SMOKE_SENTENCE = "Northwind Talent screens synthetic candidates for a demo role."


class SmokeOutput(BaseModel):
    echo: str = Field(description="The sentence, exactly as written")
    word_count: int = Field(ge=0)


async def smoke() -> int:
    settings = get_settings()
    if settings.anthropic_api_key is None:
        print("ANTHROPIC_API_KEY is not set (product/.env)", file=sys.stderr)
        return 2
    settings.llm_max_calls_per_process = min(settings.llm_max_calls_per_process, 5)
    tracer = make_tracer(settings)
    client = LLMClient(
        AnthropicProvider(
            settings.anthropic_api_key.get_secret_value(), settings.llm_timeout_seconds
        ),
        tracer,
        settings,
    )
    trace_id = None
    with tracer.span(
        "smoke",
        candidate_id="none",
        prompt_version="smoke-echo-v1",
        model=settings.model_extraction,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
    ) as root:
        trace_id = tracer.current_trace_id()
        result = await client.run(
            prompt=PromptRef("smoke-echo", "v1"),
            tier=ModelTier.EXTRACTION,
            output_schema=SmokeOutput,
            instructions="Echo the sentence and count its words.",
            untrusted={"sentence": SMOKE_SENTENCE},
        )
        root.update(
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=result.cost_usd,
        )
    tracer.flush()
    print(f"output:  {result.output.model_dump()}")
    print(f"model:   {result.model}  prompt: smoke-echo v1  attempts: {result.attempts}")
    print(
        f"tokens:  {result.input_tokens} in / {result.output_tokens} out  "
        f"cost: ${result.cost_usd:.6f}  latency: {result.latency_ms:.0f} ms"
    )
    url = tracer.trace_url(trace_id)
    print(f"trace:   {url or 'tracing off (no Langfuse keys)'}")
    if result.output.echo.strip() != SMOKE_SENTENCE:
        print("echo mismatch", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("smoke", help="one real extraction-tier call through the LLM client")
    args = parser.parse_args()
    if args.cmd == "smoke":
        sys.exit(asyncio.run(smoke()))


if __name__ == "__main__":
    main()
