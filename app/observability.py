"""Logging helpers for request and application diagnostics."""

import logging
import re
from typing import Any

LOGGER_NAME = "schedzo"


class QueryStringRedactionFilter(logging.Filter):
    """Remove query parameters from Uvicorn access-log request targets."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            arguments = list(record.args)
            if isinstance(arguments[2], str):
                arguments[2] = arguments[2].split("?", maxsplit=1)[0]
                record.args = tuple(arguments)
        return True


def configure_logging() -> None:
    """Configure a useful fallback when the process runner has no logging setup."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger(LOGGER_NAME).setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    access_logger = logging.getLogger("uvicorn.access")
    if not any(
        isinstance(log_filter, QueryStringRedactionFilter)
        for log_filter in access_logger.filters
    ):
        access_logger.addFilter(QueryStringRedactionFilter())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def monzo_error_details(response: Any) -> tuple[str, str]:
    """Extract bounded, non-credential fields from a Monzo error response."""
    try:
        payload = response.json()
    except (ValueError, TypeError):
        return "unknown", "unknown"

    if not isinstance(payload, dict):
        return "unknown", "unknown"

    code = payload.get("code", payload.get("error", "unknown"))
    code = _safe_log_value(code)
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", code):
        code = "unknown"
    return code, "upstream_error"


def _safe_log_value(value: Any) -> str:
    if not isinstance(value, (str, int, float, bool)):
        return "unknown"
    return str(value).replace("\r", "\\r").replace("\n", "\\n")[:300]
