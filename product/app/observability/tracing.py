"""Tracing behind one small interface.

- NoopTracer: used when Langfuse keys are missing. The pipeline never depends on tracing.
- RecordingTracer: used in tests to assert every span carries the required fields.
- LangfuseTracer: real traces. Export failures are logged and dropped, never raised.

Step and generation spans must carry REQUIRED_SPAN_FIELDS (master-plan rule 10).
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

log = logging.getLogger(__name__)

SpanKind = Literal["span", "generation", "event"]
REQUIRED_SPAN_FIELDS = (
    "candidate_id",
    "prompt_version",
    "model",
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "latency_ms",
)


class SpanHandle(Protocol):
    def update(self, **fields: Any) -> None: ...


class Tracer(Protocol):
    def span(
        self, name: str, *, kind: SpanKind = "span", **fields: Any
    ) -> AbstractContextManager[SpanHandle]: ...

    def current_trace_id(self) -> str | None: ...

    def trace_url(self, trace_id: str | None) -> str | None: ...

    def flush(self) -> None: ...


@dataclass
class _Handle:
    fields: dict[str, Any] = field(default_factory=dict)

    def update(self, **fields: Any) -> None:
        self.fields.update(fields)


class NoopTracer:
    @contextmanager
    def span(self, name: str, *, kind: SpanKind = "span", **fields: Any) -> Iterator[SpanHandle]:
        yield _Handle(dict(fields))

    def current_trace_id(self) -> str | None:
        return None

    def trace_url(self, trace_id: str | None) -> str | None:
        return None

    def flush(self) -> None:
        return None


@dataclass
class RecordedSpan:
    name: str
    kind: SpanKind
    trace_id: str
    fields: dict[str, Any]


class RecordingTracer:
    """Keeps every finished span in memory. Latency is filled in automatically."""

    def __init__(self) -> None:
        self.spans: list[RecordedSpan] = []
        self._stack: list[str] = []

    @contextmanager
    def span(self, name: str, *, kind: SpanKind = "span", **fields: Any) -> Iterator[SpanHandle]:
        trace_id = self._stack[0] if self._stack else uuid.uuid4().hex
        self._stack.append(trace_id)
        handle = _Handle(dict(fields))
        start = time.perf_counter()
        try:
            yield handle
        finally:
            handle.fields.setdefault("latency_ms", round((time.perf_counter() - start) * 1000, 3))
            self._stack.pop()
            self.spans.append(RecordedSpan(name, kind, trace_id, handle.fields))

    def current_trace_id(self) -> str | None:
        return self._stack[0] if self._stack else None

    def trace_url(self, trace_id: str | None) -> str | None:
        return f"recording://{trace_id}" if trace_id else None

    def flush(self) -> None:
        return None


class LangfuseTracer:
    """Maps our span fields onto Langfuse observations (SDK v5)."""

    def __init__(self, public_key: str, secret_key: str, base_url: str, environment: str) -> None:
        from langfuse import Langfuse, is_langfuse_span

        # Export only spans we create. Langfuse also auto-captures the Anthropic SDK call as
        # its own generation, which would count every call's tokens and cost twice.
        self._client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            base_url=base_url,
            environment=environment,
            should_export_span=is_langfuse_span,
        )

    @contextmanager
    def span(self, name: str, *, kind: SpanKind = "span", **fields: Any) -> Iterator[SpanHandle]:
        handle = _Handle(dict(fields))
        start = time.perf_counter()
        try:
            cm: Any = (
                self._client.start_as_current_observation(name=name, as_type="generation")
                if kind == "generation"
                else self._client.start_as_current_observation(name=name, as_type="span")
            )
            obs = cm.__enter__()
        except Exception:  # tracing must never break the pipeline
            log.warning("langfuse: could not start span %s", name, exc_info=True)
            yield handle
            return
        error: BaseException | None = None
        try:
            yield handle
        except BaseException as exc:
            error = exc
            raise
        finally:
            handle.fields.setdefault("latency_ms", round((time.perf_counter() - start) * 1000, 3))
            try:
                obs.update(**self._to_langfuse(kind, handle.fields, error))
            except Exception:
                log.warning("langfuse: could not update span %s", name, exc_info=True)
            try:
                cm.__exit__(None, None, None)
            except Exception:
                log.warning("langfuse: could not end span %s", name, exc_info=True)

    @staticmethod
    def _to_langfuse(
        kind: SpanKind, f: dict[str, Any], error: BaseException | None
    ) -> dict[str, Any]:
        out: dict[str, Any] = {"metadata": {k: _jsonable(v) for k, v in f.items()}}
        if "prompt_version" in f:
            out["version"] = str(f["prompt_version"])
        if "input" in f:
            out["input"] = f["input"]
        if "output" in f:
            out["output"] = f["output"]
        if kind == "generation":
            if f.get("model"):
                out["model"] = f["model"]
            out["usage_details"] = {
                "input": int(f.get("input_tokens", 0)),
                "output": int(f.get("output_tokens", 0)),
            }
            out["cost_details"] = {"total": float(f.get("cost_usd", 0.0))}
        if error is not None:
            out["level"] = "ERROR"
            out["status_message"] = f"{type(error).__name__}: {error}"
        return out

    def current_trace_id(self) -> str | None:
        try:
            return self._client.get_current_trace_id()
        except Exception:
            return None

    def trace_url(self, trace_id: str | None) -> str | None:
        try:
            return self._client.get_trace_url(trace_id=trace_id)
        except Exception:
            return None

    def flush(self) -> None:
        try:
            self._client.flush()
        except Exception:
            log.warning("langfuse: flush failed", exc_info=True)


def _jsonable(value: Any) -> Any:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def make_tracer(settings: Any) -> Tracer:
    """Langfuse when both keys are set, otherwise a no-op tracer."""
    if settings.tracing_configured:
        try:
            return LangfuseTracer(
                settings.langfuse_public_key.get_secret_value(),
                settings.langfuse_secret_key.get_secret_value(),
                settings.langfuse_base_url,
                settings.environment,
            )
        except Exception:
            log.warning("langfuse: setup failed, tracing off", exc_info=True)
    return NoopTracer()
