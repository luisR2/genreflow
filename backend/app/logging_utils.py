"""Logging utilities for the GenreFlow service."""

import inspect
import logging
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DEFAULT_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

P = ParamSpec("P")
R = TypeVar("R")


def configure_logging(level: int = logging.INFO) -> None:
    """Initialize basic logging configuration if not already set."""
    logging.basicConfig(format=DEFAULT_LOG_FORMAT, datefmt=DEFAULT_LOG_DATE_FORMAT, level=level)


def logged(
    _func: Callable[P, R] | classmethod | staticmethod | None = None,
    *,
    level: int = logging.DEBUG,
    name: str | None = None,
    message: str | None = None,
    enabled: bool = True,
) -> Callable[P, R]:
    """Decorator to log function entry with optional custom logger and message."""

    def decorator(func: Callable[P, R] | classmethod | staticmethod) -> Callable[P, R]:
        if isinstance(func, (classmethod, staticmethod)):
            wrapped = decorator(func.__func)  # type: ignore[attr-defined]
            return type(func)(wrapped)  # type: ignore[return-value]
        if not enabled:
            return func
        log_name = name if name else func.__module__
        logger = logging.getLogger(log_name)
        log_message = message if message else func.__name__
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                logger.log(level, log_message)
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    logger.exception("%s failed: %s", log_message, exc)
                    raise

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            logger.log(level, log_message)
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                logger.exception("%s failed: %s", log_message, exc)
                raise

        return sync_wrapper

    return decorator if _func is None else decorator(_func)
