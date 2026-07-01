"""Structured logging for the Mini Agent.

Console handler: human-readable, INFO level.
File handler:    JSON-lines to data/agent.log, DEBUG level, 5 MB rotation × 3 backups.
"""

import json
import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "data"
LOG_FILE = LOG_DIR / "agent.log"


def _setup():
    os.makedirs(LOG_DIR, exist_ok=True)
    lg = logging.getLogger("mini_agent")
    if lg.handlers:
        return lg
    lg.setLevel(logging.DEBUG)

    # Console — human-readable
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        "\033[90m%(asctime)s\033[0m %(levelname)s  %(message)s", datefmt="%H:%M:%S"
    ))
    lg.addHandler(ch)

    # File — JSON-lines, rotating
    fh = RotatingFileHandler(str(LOG_FILE), maxBytes=5_000_000, backupCount=3)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(message)s"))
    lg.addHandler(fh)

    return lg


_logger = _setup()


def _json_log(level, event, **data):
    _logger.log(level, json.dumps({"event": event, "ts": time.time(), **data}, default=str))


# ── Semantic log helpers ────────────────────────────────────────────────────

def log_turn(session_id, query, response_text, trace, duration_ms):
    _json_log(logging.INFO, "turn", session_id=session_id,
              query=query[:200], response=response_text[:200],
              steps=len(trace), duration_ms=round(duration_ms, 1))


def log_tool_call(tool_name, tool_input, output, duration_ms):
    _json_log(logging.DEBUG, "tool_call", tool=tool_name,
              input=tool_input[:200], output=output[:200],
              duration_ms=round(duration_ms, 1))


def log_llm_call(step, messages_count, duration_ms):
    _json_log(logging.DEBUG, "llm_call", step=step,
              messages=messages_count, duration_ms=round(duration_ms, 1))


def log_error(context, error):
    _json_log(logging.ERROR, "error", context=context, error=str(error))


def log_retry(context, attempt, max_retries, error):
    _json_log(logging.WARNING, "retry", context=context,
              attempt=attempt, max_retries=max_retries, error=str(error))


def log_info(msg, **data):
    _json_log(logging.INFO, msg, **data)
