from __future__ import annotations

import logging
import json
import re
from typing import Any, TextIO
from urllib.parse import urlsplit, urlunsplit

from dojoagents.config.loader import ConfigStore
from dojoagents.config.models import (
    DEFAULT_LOG_DATE_FORMAT,
    LoggingConfig,
)

DEFAULT_DATE_FORMAT = DEFAULT_LOG_DATE_FORMAT
_LOGGER_NAME = "dojoagents"
_HANDLER_MARKER = "_dojoagents_managed_handler"


def _level_number(level: str) -> int:
    value = logging.getLevelName(level.upper())
    if not isinstance(value, int):
        raise ValueError(f"Invalid log level: {level}")
    return value


def _managed_handler(logger: logging.Logger) -> logging.Handler | None:
    for handler in logger.handlers:
        if getattr(handler, _HANDLER_MARKER, False):
            return handler
    return None


def configure_logging(
    config: LoggingConfig | None = None,
    *,
    stream: TextIO | None = None,
) -> logging.Logger:
    config = config or LoggingConfig()
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(_level_number(config.level))
    logger.propagate = False

    handler = _managed_handler(logger)
    if handler is None:
        handler = logging.StreamHandler(stream)
        setattr(handler, _HANDLER_MARKER, True)
        logger.addHandler(handler)
    elif stream is not None and hasattr(handler, "setStream"):
        handler.setStream(stream)

    handler.setLevel(_level_number(config.level))
    handler.setFormatter(logging.Formatter(config.format, config.date_format))
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    if not name:
        return logging.getLogger(_LOGGER_NAME)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")


LOGGER = configure_logging(ConfigStore().snapshot().logging)


def log_debug_configuration(event: str, configuration: Any, *, logger: logging.Logger = LOGGER) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return

    def redact(value: Any) -> Any:
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                normalized = str(key).lower()
                safe_budget = normalized in {"max_tokens", "max_input_tokens", "max_output_tokens", "token_budget"} and (item is None or isinstance(item, (int, float)))
                sensitive = any(
                    part in normalized for part in ("api_key", "apikey", "token", "secret", "password", "credential", "access_key", "private_key", "authorization", "cookie", "dsn")
                )
                if "headers" in normalized or normalized in {"env", "environment", "args"} or normalized.endswith("_env") or (sensitive and not safe_budget):
                    result[key] = "***"
                else:
                    result[key] = redact(item)
            return result
        if isinstance(value, (list, tuple)):
            return [redact(item) for item in value]
        if isinstance(value, str):
            from dojoagents.agent.redact import redact_sensitive_text

            def redact_url(match: re.Match) -> str:
                try:
                    parts = urlsplit(match[0])
                    return urlunsplit(parts._replace(netloc=parts.netloc.rsplit("@", 1)[-1], query="", fragment=""))
                except ValueError:
                    return "<invalid URL>"

            return re.sub(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s<>\"']+", redact_url, redact_sensitive_text(value))
        return value

    # Multiline JSON keeps non-sensitive fields visible through per-line Run redaction.
    lines = json.dumps(redact(configuration), ensure_ascii=False, indent=2, default=str).splitlines()
    logger.debug("%s", "\n".join(f"{event} configuration={line}" for line in lines))
