"""Logging utilities for the GenreFlow service."""

from __future__ import annotations

import inspect
import logging
from functools import wraps
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, overload

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DEFAULT_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

P = ParamSpec("P")
R = TypeVar("R")


def configure_logging(level: int = logging.INFO) -> None:
    """Initialize basic logging configuration if not already set."""
    logging.basicConfig(format=DEFAULT_LOG_FORMAT, datefmt=DEFAULT_LOG_DATE_FORMAT, level=level)


def _wrap_sync(
    func: Callable[P, R],
    logger: logging.Logger,
    level: int,
    log_message: str,
) -> Callable[P, R]:
    """Wrap a synchronous callable so each call is logged before it runs."""

    @wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        logger.log(level, log_message)
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            logger.exception("%s failed: %s", log_message, exc)
            raise

    return sync_wrapper


def _wrap_async(
    func: Callable[P, Coroutine[Any, Any, R]],
    logger: logging.Logger,
    level: int,
    log_message: str,
) -> Callable[P, Coroutine[Any, Any, R]]:
    """Wrap a coroutine function so each call is logged before it is awaited."""

    @wraps(func)
    async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        logger.log(level, log_message)
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            logger.exception("%s failed: %s", log_message, exc)
            raise

    return async_wrapper


# `logged` is three different signatures wearing one name, so it needs
# @overload to describe them: applied bare to a plain function it returns that
# same callable; applied bare above @classmethod/@staticmethod it returns the
# same kind of descriptor; called with keyword options it returns the decorator.
@overload
def logged(_func: staticmethod[P, R], /) -> staticmethod[P, R]: ...


@overload
def logged(_func: classmethod[Any, P, R], /) -> classmethod[Any, P, R]: ...


@overload
def logged(_func: Callable[P, R], /) -> Callable[P, R]: ...


@overload
def logged(
    *,
    level: int = ...,
    name: str | None = ...,
    message: str | None = ...,
    enabled: bool = ...,
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def logged(
    _func: object | None = None,
    *,
    level: int = logging.DEBUG,
    name: str | None = None,
    message: str | None = None,
    enabled: bool = True,
) -> Any:
    """Log function entry, with an optional custom logger name and message.

    Works on plain functions, coroutine functions, and functions already
    wrapped in `classmethod` or `staticmethod`. Usable bare (`@logged`) or
    called with options (`@logged(level=logging.INFO)`).

    Args:
        _func: The callable to decorate when used bare; `None` when called
            with options.
        level: Level to log the entry line at.
        name: Logger name. Defaults to the decorated function's module.
        message: Message to log. Defaults to the function's name.
        enabled: When false, the function is returned unwrapped.

    Returns:
        The decorated callable, or the decorator itself when called with
        options.
    """

    def decorator(func: object) -> object:
        # Unwrap the descriptor, decorate the function inside it, then put it
        # back in the same kind of descriptor so the binding still works.
        if isinstance(func, classmethod | staticmethod):
            rewrapped: Any = decorator(func.__func__)
            return type(func)(rewrapped)
        if not enabled:
            return func
        # The dispatch below is the one genuinely dynamic part: which of the
        # two typed wrappers applies is only known at runtime.
        target: Any = func
        logger = logging.getLogger(name if name else target.__module__)
        log_message = message if message else target.__name__
        if inspect.iscoroutinefunction(target):
            return _wrap_async(target, logger, level, log_message)
        return _wrap_sync(target, logger, level, log_message)

    return decorator if _func is None else decorator(_func)
