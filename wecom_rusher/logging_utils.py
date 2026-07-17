from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path


_SENSITIVE_FIELD = re.compile(
    r"(?i)(ocr\s+(?:candidate\s+)?title|card\s+title|title|group|name|message)"
    r"\s*[:=]\s*([^;,\r\n]+)"
)


def redact_message(message: str) -> str:
    return _SENSITIVE_FIELD.sub(lambda match: f"{match.group(1)}=<redacted>", message)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_message(record.getMessage())
        record.args = ()
        return True


def setup_file_logger(
    path: str | Path,
    *,
    logger_name: str = "wecom_join_helper",
    console: bool = False,
) -> logging.Logger:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    redactor = RedactingFilter()

    file_handler = RotatingFileHandler(
        target,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redactor)
    logger.addHandler(file_handler)

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.addFilter(redactor)
        logger.addHandler(console_handler)
    return logger
