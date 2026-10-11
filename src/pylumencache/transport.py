"""The interface between the library and a way of reaching a ReNetA system.

A transport turns what its wire format carries into domain events and domain commands
into wire messages. Everything above it (the model, the facade, an integration) never
sees a topic, an event code or a URL.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from .domain.commands import Command
from .domain.events import Event


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
