import logging
import sys

from pythonjsonlogger import jsonlogger

from app.core.config import get_settings


def setup_logging() -> None:
    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s %(module)s %(funcName)s"
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
    # httpx logs full request URLs at INFO; Daikin's token endpoint accepts
    # credentials in the query string, so those URLs must never reach logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
