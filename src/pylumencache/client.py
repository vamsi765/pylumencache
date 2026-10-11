"""Asynchronous MQTT client for a ReNetA system.

Connects to the hosted broker over TLS (MQTT 5), subscribes to everything under the
Prefix Topic, turns each received message into a typed object with the parser, and
hands it to the registered listeners. Commands are published to `<prefix>/cmd`.
The connection is kept up: if it drops, the client reconnects with a growing delay.
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
from collections.abc import Callable
from typing import Any

import aiomqtt

from .protocol.parser import Message, parse, relative_topic

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 8883
RECONNECT_DELAYS = (1, 2, 5, 10, 30, 60)   # seconds; the last one repeats


class NotConnectedError(ConnectionError):
    """A command was sent while the client was not connected."""


class LumenCacheClient:
    """One connection to one ReNetA system.

    Typical use::

        client = LumenCacheClient("broker.example.com", "<Prefix Topic>", username=..., password=...)
        client.add_listener(on_message)      # called with each parsed message
        await client.start()
        await client.wait_connected()
        await client.send(commands.zone_control(zone_id=250, brightness=50))
        ...
        await client.stop()
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
        reconnect_delays: tuple[float, ...] = RECONNECT_DELAYS,
        client_factory: Callable[[], Any] | None = None,   # builds a connection like aiomqtt.Client; for tests
    ) -> None:
        self._prefix = prefix.rstrip("/")
        self._host, self._port, self._username, self._password = host, port, username, password
        self._verify_tls = verify_tls
        self._delays = reconnect_delays
        self._factory = client_factory or self._default_factory
        self._client: Any = None
        self._task: asyncio.Task[None] | None = None
        self._connected = asyncio.Event()
        self._listeners: list[Callable[[Message], Any]] = []
        self._connection_listeners: list[Callable[[bool], Any]] = []
        self._pending: set[asyncio.Future[Any]] = set()   # async listeners still running

    # --- public API -----------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def add_listener(self, callback: Callable[[Message], Any]) -> Callable[[], None]:
        """Call `callback(message)` for every received message. Returns a function that removes it."""
        self._listeners.append(callback)
        return lambda: self._listeners.remove(callback)

    def add_connection_listener(self, callback: Callable[[bool], Any]) -> Callable[[], None]:
        """Call `callback(True)` when connected and `callback(False)` when the connection is lost."""
        self._connection_listeners.append(callback)
        return lambda: self._connection_listeners.remove(callback)

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

    async def wait_connected(self, timeout: float | None = None) -> None:
        await asyncio.wait_for(self._connected.wait(), timeout)

    async def send(self, message: dict[str, Any]) -> None:
        """Publish a command (for example from pylumencache.protocol.commands) to `<prefix>/cmd`."""
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
                    await client.subscribe(f"{self._prefix}/#")
                    _LOGGER.info("Connected to %s:%s and subscribed to the system's topics", self._host, self._port)
                    self._client = client
                    attempt = 0
                    self._set_connected(True)
                    async for raw in client.messages:
                        self._dispatch(str(raw.topic), raw.payload)
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

    def _set_connected(self, value: bool) -> None:
        if value == self._connected.is_set():
            return
        self._connected.set() if value else self._connected.clear()
        for callback in list(self._connection_listeners):
            self._call(callback, value)

    def _dispatch(self, topic: str, payload: bytes | str) -> None:
        try:
            relative = relative_topic(self._prefix, topic)
        except ValueError:
            _LOGGER.debug("Ignoring a message outside the system's topics")
            return
        message = parse(relative, payload)
        _LOGGER.debug("Received %s on %s", type(message).__name__, relative)
        for callback in list(self._listeners):
            self._call(callback, message)

    def _call(self, callback: Callable[..., Any], *args: Any) -> None:
        """Run a listener; one that fails must not stop the others or the connection."""
        try:
            result = callback(*args)
        except Exception:
            _LOGGER.exception("A listener raised an exception")
            return
        if asyncio.iscoroutine(result):
            task = asyncio.ensure_future(result)
            self._pending.add(task)
            task.add_done_callback(self._async_listener_done)

    def _async_listener_done(self, task: asyncio.Future[Any]) -> None:
        self._pending.discard(task)
        if not task.cancelled() and task.exception() is not None:
            _LOGGER.error("An async listener raised an exception", exc_info=task.exception())
