"""A set of callbacks that are told about something, one failing without stopping the rest."""
from __future__ import annotations

import asyncio
import itertools
import logging
from collections.abc import Callable
from typing import Any

_LOGGER = logging.getLogger(__name__)


class Listeners:
    """Callbacks to call together. A callback may be a plain function or a coroutine function.

    A callback that raises is logged and does not stop the others. `add` returns a function that
    removes that registration; calling it again does nothing, and registering one callback twice
    gives two independent registrations.
    """

    def __init__(self) -> None:
        self._callbacks: dict[int, Callable[..., Any]] = {}
        self._ids = itertools.count()
        self._pending: set[asyncio.Future[Any]] = set()   # async callbacks still running

    def __len__(self) -> int:
        return len(self._callbacks)

    def add(self, callback: Callable[..., Any]) -> Callable[[], None]:
        key = next(self._ids)
        self._callbacks[key] = callback

        def remove() -> None:
            self._callbacks.pop(key, None)

        return remove

    def call(self, *args: Any) -> None:
        """Call every callback with `args`. An async one is scheduled on the running loop."""
        for callback in list(self._callbacks.values()):
            try:
                result = callback(*args)
            except Exception:
                _LOGGER.exception("A listener raised an exception")
                continue
            if asyncio.iscoroutine(result):
                task = asyncio.ensure_future(result)
                self._pending.add(task)
                task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Future[Any]) -> None:
        self._pending.discard(task)
        if not task.cancelled() and task.exception() is not None:
            _LOGGER.error("An async listener raised an exception", exc_info=task.exception())
