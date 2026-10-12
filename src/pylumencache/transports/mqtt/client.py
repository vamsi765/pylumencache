"""MQTT transport for a ReNetA system.

Connects to the hosted broker over TLS (MQTT 5), subscribes to everything under the
Prefix Topic, turns each received message into a typed object with the parser, and
hands the domain events it carries to the registered listeners. Commands are published
to `<prefix>/cmd`. The connection is kept up: if it drops, the transport reconnects
with a growing delay.
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
from collections.abc import Callable, Sequence
from typing import Any

import aiomqtt

from ...domain.commands import Command
from ...listeners import Listeners
from ...transport import BaseTransport, NotConnectedError
from .adapter import to_events, to_message
from .wire.parser import Message, parse, relative_topic

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 8883
RECONNECT_DELAYS = (1, 2, 5, 10, 30, 60)   # seconds; the last one repeats


class MqttTransport(BaseTransport):
    """One MQTT connection to one ReNetA system. Implements pylumencache.transport.Transport.

    Typical use::

        transport = MqttTransport("broker.example.com", "<Prefix Topic>", username=..., password=...)
        transport.add_listener(on_event)     # called with each domain event
        await transport.start()
        await transport.wait_connected()
        await transport.send(SetFixture(Zone(250), brightness=50))
        ...
        await transport.stop()
    """

    def __init__(
        self,
        host: str,
        prefix: str,
        *,
        port: int = DEFAULT_PORT,
        username: str | None = None,
        password: str | None = None,
        verify_tls: bool = True,
        topics: Sequence[str] = ("#",),   # what to subscribe to, relative to the prefix
        reconnect_delays: tuple[float, ...] = RECONNECT_DELAYS,
        client_factory: Callable[[], Any] | None = None,   # builds a connection like aiomqtt.Client; for tests
    ) -> None:
        super().__init__()
        self._prefix = prefix.rstrip("/")
        self._host, self._port, self._username, self._password = host, port, username, password
        self._verify_tls = verify_tls
        self._topics = tuple(topics)
        self._delays = reconnect_delays
        self._factory = client_factory or self._default_factory
        self._client: Any = None
        self._task: asyncio.Task[None] | None = None
        self._message_listeners = Listeners()
        self._raw_listeners = Listeners()

    # --- public API -----------------------------------------------------

    def add_message_listener(self, callback: Callable[[Message], Any]) -> Callable[[], None]:
        """Call `callback(message)` for every received message, parsed but not interpreted (MQTT only)."""
        return self._message_listeners.add(callback)

    def add_raw_listener(self, callback: Callable[[str, bytes | str, bool], Any]) -> Callable[[], None]:
        """Call `callback(topic, payload, retained)` for every message under the prefix, before parsing.

        The topic is relative to the prefix. For recording traffic (MQTT only).
        """
        return self._raw_listeners.add(callback)

    async def start(self) -> None:
        """Start connecting in the background. Returns at once; use wait_connected() to wait."""
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="lumencache-client")

    async def stop(self) -> None:
        if self._task is not None:
            _LOGGER.info("Disconnecting from %s:%s", self._host, self._port)
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def send(self, command: Command) -> None:
        """Publish a domain command to `<prefix>/cmd`."""
        await self.send_raw(to_message(command))

    async def send_raw(self, message: dict[str, Any]) -> None:
        """Publish any command (for example from wire.commands) to `<prefix>/cmd` (MQTT only)."""
        if self._client is None:
            raise NotConnectedError("not connected to the broker")
        await self._client.publish(f"{self._prefix}/cmd", json.dumps(message, separators=(",", ":")))
        _LOGGER.debug("Sent %s", message)

    # --- internals ------------------------------------------------------

    def _default_factory(self) -> aiomqtt.Client:
        context = ssl.create_default_context()
        if not self._verify_tls:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        return aiomqtt.Client(
            self._host,
            self._port,
            username=self._username,
            password=self._password,
            protocol=aiomqtt.ProtocolVersion.V5,
            tls_context=context,
        )

    async def _run(self) -> None:
        attempt = 0
        while True:
            try:
                _LOGGER.info("Connecting to %s:%s", self._host, self._port)
                async with self._factory() as client:
                    for topic in self._topics:
                        await client.subscribe(f"{self._prefix}/{topic.lstrip('/')}")
                    _LOGGER.info("Connected to %s:%s and subscribed to the system's topics", self._host, self._port)
                    self._client = client
                    attempt = 0
                    self._set_connected(True)
                    async for raw in client.messages:
                        payload = raw.payload
                        if isinstance(payload, bytearray):
                            payload = bytes(payload)
                        if isinstance(payload, (bytes, str)):   # the broker can also send an empty or numeric payload
                            self._dispatch(str(raw.topic), payload, bool(getattr(raw, "retain", False)))
                _LOGGER.warning("Connection to %s:%s closed by the broker", self._host, self._port)
            except asyncio.CancelledError:
                raise
            except (aiomqtt.MqttError, OSError) as err:
                _LOGGER.warning("Connection to %s:%s failed: %s", self._host, self._port, err)
            finally:
                self._client = None
                self._set_connected(False)
            delay = self._delays[min(attempt, len(self._delays) - 1)]
            attempt += 1
            _LOGGER.info("Reconnecting to %s:%s in %s s", self._host, self._port, delay)
            await asyncio.sleep(delay)

    def _dispatch(self, topic: str, payload: bytes | str, retained: bool = False) -> None:
        try:
            relative = relative_topic(self._prefix, topic)
        except ValueError:
            _LOGGER.debug("Ignoring a message outside the system's topics")
            return
        self._raw_listeners.call(relative, payload, retained)
        message = parse(relative, payload)
        _LOGGER.debug("Received %s on %s", type(message).__name__, relative)
        self._message_listeners.call(message)
        for event in to_events(message):
            self._emit(event)
