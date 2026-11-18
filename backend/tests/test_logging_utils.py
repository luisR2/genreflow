"""Tests for the @logged decorator in backend.app.logging_utils.

The decorator had no test coverage and no call sites, which is how a real bug
survived in it: the classmethod/staticmethod branch read `func.__func` instead
of `func.__func__` and raised AttributeError at decoration time, hidden behind
a `# type: ignore`. These tests exercise every branch so that cannot recur.
"""

import asyncio
import logging

import pytest

from backend.app.logging_utils import logged


def inspect_attr(cls: type, name: str) -> object:
    """Fetch the raw class attribute, bypassing the descriptor protocol."""
    return cls.__dict__[name]


def test_sync_function_returns_its_value_and_logs_entry(caplog):
    @logged
    def double(x: int) -> int:
        return x * 2

    with caplog.at_level(logging.DEBUG):
        assert double(21) == 42

    assert "double" in caplog.text


def test_metadata_is_preserved():
    @logged
    def named(x: int) -> int:
        """Docstring."""
        return x

    assert named.__name__ == "named"
    assert named.__doc__ == "Docstring."


def test_custom_logger_name_level_and_message(caplog):
    @logged(level=logging.INFO, name="genreflow.custom", message="analysing")
    def work() -> str:
        return "done"

    with caplog.at_level(logging.INFO, logger="genreflow.custom"):
        assert work() == "done"

    records = [r for r in caplog.records if r.name == "genreflow.custom"]
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    assert records[0].getMessage() == "analysing"


def test_default_logger_name_is_the_functions_module(caplog):
    @logged
    def work() -> None:
        return None

    with caplog.at_level(logging.DEBUG):
        work()

    assert any(r.name == __name__ for r in caplog.records)


def test_disabled_returns_the_function_untouched():
    def work() -> str:
        return "done"

    assert logged(enabled=False)(work) is work


def test_sync_exception_is_logged_and_reraised(caplog):
    @logged
    def boom() -> None:
        raise ValueError("nope")

    with caplog.at_level(logging.DEBUG), pytest.raises(ValueError, match="nope"):
        boom()

    assert any(r.levelno == logging.ERROR and r.exc_info for r in caplog.records)


def test_async_function_is_awaited_and_logged(caplog):
    @logged
    async def double(x: int) -> int:
        await asyncio.sleep(0)
        return x * 2

    with caplog.at_level(logging.DEBUG):
        assert asyncio.run(double(21)) == 42

    assert "double" in caplog.text


def test_async_exception_is_logged_and_reraised(caplog):
    @logged
    async def boom() -> None:
        await asyncio.sleep(0)
        raise ValueError("nope")

    with caplog.at_level(logging.DEBUG), pytest.raises(ValueError, match="nope"):
        asyncio.run(boom())

    assert any(r.levelno == logging.ERROR and r.exc_info for r in caplog.records)


# The two cases that used to raise AttributeError.


def test_staticmethod_stays_a_staticmethod_and_runs(caplog):
    class Service:
        @logged
        @staticmethod
        def double(x: int) -> int:
            return x * 2

    assert isinstance(inspect_attr(Service, "double"), staticmethod)
    with caplog.at_level(logging.DEBUG):
        assert Service.double(21) == 42
        assert Service().double(21) == 42

    assert "double" in caplog.text


def test_classmethod_stays_a_classmethod_and_binds_cls(caplog):
    class Service:
        factor = 2

        @logged
        @classmethod
        def scale(cls, x: int) -> int:
            return x * cls.factor

    assert isinstance(inspect_attr(Service, "scale"), classmethod)
    with caplog.at_level(logging.DEBUG):
        assert Service.scale(21) == 42
        assert Service().scale(21) == 42

    assert "scale" in caplog.text


def test_async_staticmethod_round_trips(caplog):
    class Service:
        @logged
        @staticmethod
        async def double(x: int) -> int:
            await asyncio.sleep(0)
            return x * 2

    with caplog.at_level(logging.DEBUG):
        assert asyncio.run(Service.double(21)) == 42

    assert "double" in caplog.text
