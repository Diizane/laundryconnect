"""Structured JSON logging.

Every log record is emitted as a single JSON line including the current
request ID (when inside a request). Sensitive values must never be logged;
`SENSITIVE_KEYS` is a guard for structured extras, not a substitute for
care at call sites — see docs/SECURITY.md.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Keys that must never appear in log output, defence in depth against
# accidentally logging credential material via `extra={...}`.
SENSITIVE_KEYS = frozenset(
    {"password", "secret", "token", "cookie", "authorization", "credential", "api_key"}
)

_STANDARD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
    "taskName",
    "message",
    "asctime",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)

        # Include structured extras, redacting anything that looks sensitive.
        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRS or key.startswith("_"):
                continue
            if any(sensitive in key.lower() for sensitive in SENSITIVE_KEYS):
                payload[key] = "[REDACTED]"
            else:
                payload[key] = value

        return json.dumps(payload, default=str)


def configure_logging(log_level: str = "INFO") -> None:
    """Configure root logging to emit JSON lines to stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level.upper())

    # Uvicorn's access log duplicates our request logging; keep error logs.
    logging.getLogger("uvicorn.access").disabled = True
