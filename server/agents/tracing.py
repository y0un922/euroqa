"""Structlog-based tracing processor for the OpenAI Agents SDK.

Replaces the default OpenAI trace exporter with local structured logging,
so agent trace data is written to structlog (inheriting ``request_id``
from contextvars) instead of being sent to ``api.openai.com``.
"""

from __future__ import annotations

import time

import structlog
from agents.tracing import Span, Trace, TracingProcessor

logger = structlog.get_logger(__name__)

_OUTPUT_SUMMARY_MAX = 200


def _summarize_span_output(span: Span[object]) -> str:
    """Build a compact summary of a span's output for log readability."""
    span_data = span.span_data
    span_type = getattr(span_data, "type", "unknown")

    if span_type == "function":
        # Tool call -- show name + truncated output
        name = getattr(span_data, "name", "?")
        output = getattr(span_data, "output", None)
        output_str = str(output) if output is not None else ""
        if len(output_str) > _OUTPUT_SUMMARY_MAX:
            output_str = output_str[:_OUTPUT_SUMMARY_MAX] + "..."
        return f"tool={name} output={output_str}"

    if span_type in ("generation", "response"):
        output = getattr(span_data, "output", None)
        output_str = str(output) if output is not None else ""
        if len(output_str) > _OUTPUT_SUMMARY_MAX:
            output_str = output_str[:_OUTPUT_SUMMARY_MAX] + "..."
        model = getattr(span_data, "model", None)
        return f"model={model} output={output_str}"

    if span_type == "agent":
        name = getattr(span_data, "name", "?")
        return f"agent={name}"

    return str(span_type)


class StructlogTracingProcessor(TracingProcessor):
    """Log agent traces to structlog instead of exporting to OpenAI."""

    def __init__(self) -> None:
        self._trace_starts: dict[str, float] = {}
        self._span_starts: dict[str, float] = {}

    # -- Trace lifecycle ---------------------------------------------------

    def on_trace_start(self, trace: Trace) -> None:
        trace_id = trace.trace_id
        self._trace_starts[trace_id] = time.perf_counter()
        logger.info(
            "agent_trace_start",
            trace_id=trace_id,
            workflow_name=trace.name,
        )

    def on_trace_end(self, trace: Trace) -> None:
        trace_id = trace.trace_id
        start = self._trace_starts.pop(trace_id, None)
        duration_ms = int((time.perf_counter() - start) * 1000) if start else None
        logger.info(
            "agent_trace_end",
            trace_id=trace_id,
            duration_ms=duration_ms,
        )

    # -- Span lifecycle ----------------------------------------------------

    def on_span_start(self, span: Span[object]) -> None:
        span_id = span.span_id
        self._span_starts[span_id] = time.perf_counter()
        span_data = span.span_data
        span_type = getattr(span_data, "type", "unknown")
        logger.info(
            "agent_span_start",
            span_id=span_id,
            span_type=span_type,
        )

    def on_span_end(self, span: Span[object]) -> None:
        span_id = span.span_id
        start = self._span_starts.pop(span_id, None)
        duration_ms = int((time.perf_counter() - start) * 1000) if start else None
        span_data = span.span_data
        span_type = getattr(span_data, "type", "unknown")
        logger.info(
            "agent_span_end",
            span_id=span_id,
            span_type=span_type,
            duration_ms=duration_ms,
            output_summary=_summarize_span_output(span),
        )

    # -- Lifecycle ---------------------------------------------------------

    def shutdown(self) -> None:
        self._trace_starts.clear()
        self._span_starts.clear()

    def force_flush(self) -> None:
        pass
