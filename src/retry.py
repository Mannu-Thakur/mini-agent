"""Retry and fallback logic for LLM and tool calls.

Retries only on transient errors (rate limits, server errors, timeouts).
Input errors (ValueError, TypeError) are never retried.
"""

import time
from src import logger

_RETRYABLE_CODES = {429, 500, 502, 503, 504}


def _is_retryable(exc):
    msg = str(exc).lower()
    for code in _RETRYABLE_CODES:
        if str(code) in str(exc):
            return True
    return any(kw in msg for kw in (
        "timeout", "rate limit", "rate_limit",
        "connection", "temporarily", "overloaded",
    ))


def retry_llm_call(llm, messages, *, max_retries=3, backoff_base=1.0):
    """llm.invoke() with automatic retry on transient errors."""
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return llm.invoke(messages)
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries and _is_retryable(exc):
                wait = backoff_base * (2 ** (attempt - 1))
                logger.log_retry("llm_call", attempt, max_retries, exc)
                time.sleep(wait)
            else:
                break
    raise last_exc


def retry_llm_stream(llm, messages, *, max_retries=3, backoff_base=1.0):
    """llm.stream() with automatic retry on transient errors."""
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return llm.stream(messages)
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries and _is_retryable(exc):
                wait = backoff_base * (2 ** (attempt - 1))
                logger.log_retry("llm_stream", attempt, max_retries, exc)
                time.sleep(wait)
            else:
                break
    raise last_exc


def retry_tool_call(fn, arg, *, max_retries=2):
    """Retry tool function on network errors only."""
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn(arg)
        except (ValueError, TypeError, KeyError):
            raise  # input errors — don't retry
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                logger.log_retry("tool_call", attempt, max_retries, exc)
                time.sleep(0.5)
            else:
                break
    raise last_exc
