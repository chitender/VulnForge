import logging
import structlog

_SECRET_FIELDS = {"token", "password", "secret", "key", "dek", "ciphertext", "auth"}


def _redact_secrets(_, __, event_dict: dict) -> dict:
    for field in list(event_dict.keys()):
        if any(s in field.lower() for s in _SECRET_FIELDS):
            event_dict[field] = "[REDACTED]"
    return event_dict


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact_secrets,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
    )
