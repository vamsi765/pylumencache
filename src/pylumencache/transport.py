"""The interface between the library and a way of reaching a ReNetA system.

A transport turns what its wire format carries into domain events and domain commands
into wire messages. Everything above it (the model, the facade, an integration) never
sees a topic, an event code or a URL.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Protocol

from .domain.commands import Command
from .domain.events import Event
from .listeners import Listeners


class NotConnectedError(ConnectionError):
    """A command was sent while the transport was not connected."""


class UnsupportedError(NotImplementedError):
    """The transport cannot do what was asked."""


class Transport(Protocol):
    @property
    def connected(self) -> bool: ...

    def add_listener(self, callback: Callable[[Event], Any]) -> Callable[[], None]:
        """Call `callback(event)` for each domain event. Returns a function that removes it."""
        ...

    def add_connection_listener(self, callback: Callable[[bool], Any]) -> Callable[[], None]:
        """Call `callback(True)` when connected and `callback(False)` when the connection is lost."""
        ...

    async def start(self) -> None:
        """Start connecting in the background. Returns at once."""
        ...

    async def stop(self) -> None: ...

    async def wait_connected(self, timeout: float | None = None) -> None: ...

    async def send(self, command: Command) -> None:
        """Raises NotConnectedError when not connected."""
        ...


class BaseTransport(ABC):
    """What every transport shares: the listeners and the connected state.

    A subclass reports what it hears with `_emit(event)` and what it is doing with
    `_set_connected(bool)`, and implements `start`, `stop` and `send`. Listeners are told about
    each in turn, and a listener that fails or is a coroutine is handled here, so no transport
    has to repeat it.
    """

    def __init__(self) -> None:
        self._listeners = Listeners()
        self._connection_listeners = Listeners()
        self._connected = asyncio.Event()

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def add_listener(self, callback: Callable[[Event], Any]) -> Callable[[], None]:
        """Call `callback(event)` for each domain event. Returns a function that removes it."""
        return self._listeners.add(callback)

    def add_connection_listener(self, callback: Callable[[bool], Any]) -> Callable[[], None]:
        """Call `callback(True)` when connected and `callback(False)` when the connection is lost."""
        return self._connection_listeners.add(callback)

    async def wait_connected(self, timeout: float | None = None) -> None:
        await asyncio.wait_for(self._connected.wait(), timeout)

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def send(self, command: Command) -> None: ...

    def _emit(self, event: Event) -> None:
        self._listeners.call(event)

    def _set_connected(self, value: bool) -> None:
        if value == self._connected.is_set():
            return
        self._connected.set() if value else self._connected.clear()
        self._connection_listeners.call(value)
