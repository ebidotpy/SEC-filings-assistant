from __future__ import annotations

import logging
import os

import logfire
import structlog

from app.config import settings


def configure_logging() -> None:
    """Configure structlog for structured application logging to stdout."""
    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[settings.log_level.upper()]
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def configure_logfire() -> None:
    """Initialize Logfire for Pydantic AI agent debugging."""
    if settings.logfire_token is not None:
        os.environ["LOGFIRE_TOKEN"] = settings.logfire_token

    logfire.configure(
        send_to_logfire=settings.logfire_send_to_logfire,
        service_name=settings.logfire_service_name,
        environment=settings.logfire_environment,
    )

    if settings.logfire_instrument_pydantic_ai:
        logfire.instrument_pydantic_ai()

    if settings.logfire_instrument_system_metrics:
        logfire.instrument_system_metrics()
