"""Logging helpers that keep credentials out of systemd journal output."""

from __future__ import annotations

import logging
import re


_TELEGRAM_BOT_URL = re.compile(
    r"(?P<prefix>https?://api\.telegram\.org/bot)[^/\s\"']+",
    re.IGNORECASE,
)


def redact_sensitive_urls(message: str) -> str:
    """Replace Telegram Bot API credentials embedded in request URLs."""
    return _TELEGRAM_BOT_URL.sub(r"\g<prefix>[REDACTED]", message)


class SensitiveUrlFilter(logging.Filter):
    """Redact secrets after a log record's %-formatting has been applied."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
        except Exception:
            return True

        redacted = redact_sensitive_urls(rendered)
        if redacted != rendered:
            record.msg = redacted
            record.args = ()
        return True


def install_sensitive_log_filter() -> None:
    """Install one shared filter on app/network loggers and root handlers."""
    log_filter = SensitiveUrlFilter()

    for logger_name in ("httpx", "httpcore", "catcam.notify"):
        logger = logging.getLogger(logger_name)
        if not any(isinstance(item, SensitiveUrlFilter) for item in logger.filters):
            logger.addFilter(log_filter)

    for handler in logging.getLogger().handlers:
        if not any(isinstance(item, SensitiveUrlFilter) for item in handler.filters):
            handler.addFilter(log_filter)
