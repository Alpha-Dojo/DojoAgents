from __future__ import annotations

import logging
from typing import TextIO

from dojoagents.config.loader import ConfigStore
from dojoagents.config.models import (
    DEFAULT_LOG_DATE_FORMAT,
    DEFAULT_LOG_FORMAT,
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
