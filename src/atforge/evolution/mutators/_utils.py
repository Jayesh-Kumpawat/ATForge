"""Shared LLM parsing and retry utilities for evolution mutators."""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Callable

import structlog
from pydantic import BaseModel

from atforge.llm.types import LlmRequest, LlmResponse

log = structlog.get_logger(__name__)


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _brace_match(text: str) -> str:
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def _parse_json(raw: str) -> dict:
    clean = _strip_fences(raw)
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return json.loads(_brace_match(clean))


def call_llm_with_schema[T: BaseModel](
    llm: Callable[[LlmRequest], LlmResponse],
    request: LlmRequest,
    schema: type[T],
    *,
    max_retries: int = 3,
) -> T | None:
    """Call LLM, validate response against Pydantic schema, retry with correction on failure.

    Returns None only after all retries exhausted. Never raises.
    """
    last_error = ""
    for attempt in range(max_retries):
        req = request
        if attempt > 0:
            correction = (
                f"CORRECTION (attempt {attempt + 1}): previous response was invalid: {last_error}. "
                f"Reply ONLY with the JSON object, no extra text."
            )
            req = dataclasses.replace(
                request,
                prompt=f"{request.prompt}\n\n{correction}",
                trace_name=f"{request.trace_name}_retry{attempt}" if request.trace_name else None,
            )
        try:
            resp = llm(req)
            data = _parse_json(resp.text)
            return schema.model_validate(data)
        except Exception as exc:
            last_error = str(exc)[:120]
            log.warning(
                "llm_schema_retry",
                attempt=attempt,
                schema=schema.__name__,
                error=last_error,
            )
    log.warning("llm_schema_exhausted", schema=schema.__name__, max_retries=max_retries)
    return None
