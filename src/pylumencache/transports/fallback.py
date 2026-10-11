"""Several transports in priority order, with the later ones used only when the earlier ones are down.

    FallbackTransport([first, second])

Only the first transport is started at first. If it is not connected after `fail_after`
seconds, the second is started as well, and so on down the list. The earlier transports keep
trying to connect in the background, and as soon as one of them connects, the transports
after it are stopped. So a later transport is connected only while every earlier one is down.

Events come from the highest-priority transport that is connected, and commands go to it, so
the model never sees two sources at once. "Down" means not connected: a transport that is
connected but silent counts as up. The order is the order of the list.

This module knows nothing about any particular transport.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from functools import partial
from typing import Any

from ..domain.commands import Command
from ..domain.events import Event
from ..transport import NotConnectedError, Transport, UnsupportedError

_LOGGER = logging.getLogger(__name__)

DEFAULT_FAIL_AFTER = 30.0   # seconds


class FallbackTransport:
    """Implements pylumencache.transport.Transport on top of an ordered list of transports."""

    def __init__(self, transports: Sequence[Transport], *, fail_after: float = DEFAULT_FAIL_AFTER) -> None:
        if not transports:
            raise ValueError("give at least one transport")
        self._transports = list(transports)
        self._fail_after = fail_after
        self._started = 0   # how many, from the front of the list, are running
        self._active: int | None = None
        self._task: asyncio.Task[None] | None = None
        self._connected = asyncio.Event()
        self._changed = asyncio.Event()
        self._listeners: list[Callable[[Event], Any]] = []
        self._connection_listeners: list[Callable[[bool], Any]] = []
        for index, transport in enumerate(self._transports):
            transport.add_listener(partial(self._forward, index))
            transport.add_connection_listener(partial(self._on_connection, index))

    # --- Transport ----------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    @property
    def transports(self) -> tuple[Transport, ...]:
        """The transports, in priority order."""
        return tuple(self._transports)

    @property
    def active(self) -> Transport | None:
        """The transport in use: the highest-priority one that is connected."""
        index = self._first_connected()
        return None if index is None else self._transports[index]

    def add_listener(self, callback: Callable[[Event], Any]) -> Callable[[], None]:
        self._listeners.append(callback)
        return lambda: self._listeners.remove(callback)

    def add_connection_listener(self, callback: Callable[[bool], Any]) -> Callable[[], None]:
        """Called with True when some transport connects and False when none is connected."""
        self._connection_listeners.append(callback)
        return lambda: self._connection_listeners.remove(callback)

    async def start(self) -> None:
        if self._task is None:
            self._started = 1
            await self._transports[0].start()
            self._task = asyncio.create_task(self._supervise(), name="lumencache-fallback")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        for transport in self._transports[:self._started]:
            await transport.stop()
        self._started = 0
        self._update()

    async def wait_connected(self, timeout: float | None = None) -> None:
        await asyncio.wait_for(self._connected.wait(), timeout)

    async def send(self, command: Command) -> None:
        await self._send_with(lambda transport: transport.send(command))

    async def send_raw(self, message: dict[str, Any]) -> None:
        """Send a command in a transport's own format, to the first connected transport that has one."""
        async def call(transport: Transport) -> None:
            send_raw = getattr(transport, "send_raw", None)
            if send_raw is None:
                raise UnsupportedError("this transport has no raw commands")
            await send_raw(message)

        await self._send_with(call)

    # --- internals ----------------------------------------------------------

    async def _send_with(self, call: Callable[[Transport], Any]) -> None:
        unsupported = False
        for transport in self._transports:
            if not transport.connected:
                continue
            try:
                await call(transport)
                return
            except UnsupportedError:
                unsupported = True
        if unsupported:
            raise UnsupportedError("no connected transport can do this")
        raise NotConnectedError("no transport is connected")

    def _first_connected(self) -> int | None:
        for index, transport in enumerate(self._transports):
            if transport.connected:
                return index
        return None

    def _forward(self, index: int, event: Event) -> None:
        if index != self._first_connected():
            return   # only the transport in use speaks; a lower-priority one is on its way out
        for callback in list(self._listeners):
            self._call(callback, event)

    def _on_connection(self, index: int, connected: bool) -> None:
        self._update()

    def _update(self) -> None:
        active = self._first_connected()
        if active != self._active:
            _LOGGER.info("Using transport %s", "none" if active is None else type(self._transports[active]).__name__)
            self._active = active
        self._changed.set()
        connected = active is not None
        if connected != self._connected.is_set():
            self._connected.set() if connected else self._connected.clear()
            for callback in list(self._connection_listeners):
                self._call(callback, connected)

    def _call(self, callback: Callable[..., Any], *args: Any) -> None:
        try:
            callback(*args)
        except Exception:
            _LOGGER.exception("A listener raised an exception")

    async def _supervise(self) -> None:
        """Start the next transport when all running ones stay down, stop the later ones when an earlier one is up."""
        while True:
            self._changed.clear()
            first = self._first_connected()
            if first is not None:
                while self._started > first + 1:
                    self._started -= 1
                    _LOGGER.info("Stopping %s, a higher-priority transport is connected",
                                 type(self._transports[self._started]).__name__)
                    await self._transports[self._started].stop()
                await self._changed.wait()
            elif self._started < len(self._transports):
                try:
                    await asyncio.wait_for(self._changed.wait(), self._fail_after)
                except TimeoutError:
                    transport = self._transports[self._started]
                    _LOGGER.warning("No transport connected after %s s, starting %s",
                                    self._fail_after, type(transport).__name__)
                    self._started += 1
                    await transport.start()
            else:
                await self._changed.wait()
