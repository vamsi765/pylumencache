"""The public entry point: one ReNetA system, reached through a transport.

    cache = LumenCache.mqtt("broker.example.com", "<Prefix Topic>", username=..., password=...)
    cache.model.add_listener(on_change)
    await cache.start()
    await cache.wait_connected()
    await cache.send(SetLight("zone", 250, brightness=50))

The facade owns the SystemModel and keeps it fed from the transport. A caller never needs
to know which transport is underneath.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from .domain.commands import Command
from .domain.model import SystemModel
from .transport import Transport, UnsupportedError
from .transports.fallback import DEFAULT_FAIL_AFTER, FallbackTransport


class LumenCache:
    def __init__(self, transport: Transport, model: SystemModel | None = None) -> None:
        self.transport = transport
        self.model = model if model is not None else SystemModel()
        self.model.attach(transport)

    @classmethod
    def mqtt(cls, host: str, prefix: str, *, model: SystemModel | None = None, **options: Any) -> LumenCache:
        """Over the hosted MQTT broker. `options` are those of MqttTransport (port, username, ...)."""
        from .transports.mqtt import MqttTransport
        return cls(MqttTransport(host, prefix, **options), model)

    @classmethod
    def with_fallback(
        cls,
        transports: Sequence[Transport],
        *,
        fail_after: float = DEFAULT_FAIL_AFTER,
        model: SystemModel | None = None,
    ) -> LumenCache:
        """Several transports in priority order. A later one is connected only while the earlier ones are down.

        `fail_after` is how many seconds without a connection before the next one is started.
        """
        return cls(FallbackTransport(transports, fail_after=fail_after), model)

    @property
    def connected(self) -> bool:
        return self.transport.connected

    def add_connection_listener(self, callback: Callable[[bool], Any]) -> Callable[[], None]:
        return self.transport.add_connection_listener(callback)

    async def start(self) -> None:
        await self.transport.start()

    async def stop(self) -> None:
        await self.transport.stop()

    async def wait_connected(self, timeout: float | None = None) -> None:
        await self.transport.wait_connected(timeout)

    async def send(self, command: Command) -> None:
        await self.transport.send(command)

    async def send_raw(self, message: dict[str, Any]) -> None:
        """Send a command in the transport's own format, as a fallback. Not every transport has one."""
        send_raw = getattr(self.transport, "send_raw", None)
        if send_raw is None:
            raise UnsupportedError("this transport has no raw commands")
        await send_raw(message)
