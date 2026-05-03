"""Central logging setup for the Flask backend.

Single point of truth for log format, level, and handler configuration.
Importing `configure_logging()` once at startup gives every module that
calls `logging.getLogger(__name__)` a sensible default handler — no more
ad-hoc `print()` calls scattered across request paths.

Format includes a `cid` (correlation id) field so chat-stream events can
be traced end-to-end. The id is read from a contextvar so background pump
threads inherit it via `copy_current_request_context`.
"""

import logging
import os
import sys
from contextvars import ContextVar

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")


class _CorrelationFilter(logging.Filter):
  """Inject the current correlation id into every log record."""

  def filter(self, record: logging.LogRecord) -> bool:
    record.cid = correlation_id.get()
    return True


_DEFAULT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s [cid=%(cid)s] %(message)s"


def configure_logging() -> None:
  """Idempotent: safe to call multiple times. Reads LOG_LEVEL from env."""
  level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
  level = getattr(logging, level_name, logging.INFO)
  root = logging.getLogger()
  if any(getattr(handler, "_atomic_chat_handler", False) for handler in root.handlers):
    root.setLevel(level)
    return
  handler = logging.StreamHandler(sys.stderr)
  handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
  handler.addFilter(_CorrelationFilter())
  handler._atomic_chat_handler = True  # marker for idempotency
  root.handlers.clear()
  root.addHandler(handler)
  root.setLevel(level)


def set_correlation_id(value: str) -> None:
  """Bind a correlation id for the current async/thread context."""
  correlation_id.set(value or "-")
