"""The client against a fake broker connection (no network)."""
import asyncio
import json
from types import SimpleNamespace

import aiomqtt
import pytest

from pylumencache.client import LumenCacheClient, NotConnectedError
from pylumencache.protocol import commands
from pylumencache.protocol.parser import CommandEcho, Empty, ErrorReport, ZoneEvent

PREFIX = "platform:na/example"


class FakeConnection:
    """Stands in for aiomqtt.Client. Feed it with put(); put(error) makes the connection drop."""

    def __init__(self, fail_to_connect=False):
        self.fail_to_connect = fail_to_connect
        self.subscribed, self.published = [], []
        self._queue = asyncio.Queue()

    def put(self, topic, payload):
        self._queue.put_nowait(SimpleNamespace(topic=topic, payload=payload))

    def drop(self):
        self._queue.put_nowait(aiomqtt.MqttError("connection lost"))

    async def __aenter__(self):
        if self.fail_to_connect:
            raise aiomqtt.MqttError("refused")
        return self

    async def __aexit__(self, *exc):
        return False

    async def subscribe(self, topic):
        self.subscribed.append(topic)

    async def publish(self, topic, payload):
        self.published.append((topic, payload))

    @property
    def messages(self):
        async def gen():
            while True:
                item = await self._queue.get()
                if isinstance(item, Exception):
                    raise item
                yield item
        return gen()


def make_client(*connections):
    """A client that hands out the given fake connections in order."""
    queue = list(connections)
    return LumenCacheClient("broker", PREFIX + "/", reconnect_delays=(0.01,), client_factory=lambda: queue.pop(0))


def run(coro_fn):
    asyncio.run(asyncio.wait_for(coro_fn(), 5))


def test_subscribes_to_the_prefix_and_delivers_parsed_messages():
    async def scenario():
        conn = FakeConnection()
        client, got = make_client(conn), []
        client.add_listener(got.append)
        await client.start()
        await client.wait_connected(1)
        conn.put(f"{PREFIX}/status", b'{"e":56,"z":250,"on":0,"dev":12,"g":65534}')
        conn.put(f"{PREFIX}/cmd", b"")
        conn.put(f"{PREFIX}/cmd", b'{"e":57,"g":14}')
        while len(got) < 3:
            await asyncio.sleep(0.01)
        await client.stop()
        assert conn.subscribed == [f"{PREFIX}/#"]
        assert [type(m) for m in got] == [ZoneEvent, Empty, CommandEcho]
    run(scenario)


def test_send_publishes_compact_json_to_cmd():
    async def scenario():
        conn = FakeConnection()
        client = make_client(conn)
        await client.start()
        await client.wait_connected(1)
        await client.send(commands.zone_control(zone_id=250, brightness=50, fade=800))
        await client.stop()
        topic, payload = conn.published[0]
        assert topic == f"{PREFIX}/cmd"
        assert payload == '{"e":56,"z":250,"bri":50,"fade":800}'
    run(scenario)


def test_send_when_not_connected_is_refused():
    async def scenario():
        with pytest.raises(NotConnectedError):
            await make_client().send({"e": 8})
    run(scenario)


def test_reconnects_after_the_connection_drops():
    async def scenario():
        first, second = FakeConnection(), FakeConnection()
        client, states, got = make_client(first, second), [], []
        client.add_connection_listener(states.append)
        client.add_listener(got.append)
        await client.start()
        await client.wait_connected(1)
        first.drop()
        while states != [True, False, True]:
            await asyncio.sleep(0.01)
        second.put(f"{PREFIX}/errors", b'{"e":254,"g":100,"err":38,"v":254}')
        while not got:
            await asyncio.sleep(0.01)
        await client.stop()
        assert isinstance(got[0], ErrorReport)
        assert second.subscribed == [f"{PREFIX}/#"]   # subscribes again on the new connection
    run(scenario)


def test_failed_connection_is_retried():
    async def scenario():
        client = make_client(FakeConnection(fail_to_connect=True), FakeConnection())
        await client.start()
        await client.wait_connected(1)
        assert client.connected
        await client.stop()
        assert not client.connected
    run(scenario)


def test_listener_errors_do_not_stop_delivery():
    async def scenario():
        conn = FakeConnection()
        client, got = make_client(conn), []

        def broken(_):
            raise RuntimeError("bad listener")

        async def async_listener(message):
            got.append(("async", message))

        client.add_listener(broken)
        client.add_listener(async_listener)
        client.add_listener(lambda m: got.append(("sync", m)))
        await client.start()
        await client.wait_connected(1)
        conn.put(f"{PREFIX}/cmd", b"")
        while len(got) < 2:
            await asyncio.sleep(0.01)
        await client.stop()
        assert {kind for kind, _ in got} == {"async", "sync"}
        assert client.connected is False
    run(scenario)


def test_messages_outside_the_prefix_are_ignored_and_listeners_can_be_removed():
    async def scenario():
        conn = FakeConnection()
        client, got = make_client(conn), []
        remove = client.add_listener(got.append)
        await client.start()
        await client.wait_connected(1)
        conn.put("other/status", b'{"e":254}')
        conn.put(f"{PREFIX}/cmd", b"")
        while not got:
            await asyncio.sleep(0.01)
        assert len(got) == 1
        remove()
        conn.put(f"{PREFIX}/cmd", b"")
        await asyncio.sleep(0.05)
        await client.stop()
        assert len(got) == 1
    run(scenario)


@pytest.mark.parametrize("verify", [True, False])
def test_default_connection_uses_tls(verify):
    import ssl

    async def scenario():
        client = LumenCacheClient("broker", PREFIX, username="u", password="p", verify_tls=verify)
        conn = client._default_factory()   # built, not connected
        assert isinstance(conn, aiomqtt.Client)
        assert conn._client._ssl_context.verify_mode == (ssl.CERT_REQUIRED if verify else ssl.CERT_NONE)
    run(scenario)
