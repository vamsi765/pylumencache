"""Fallback: later transports are used only while the earlier ones are down."""
import asyncio

import pytest

from pylumencache import LumenCache, NotConnectedError, SetLight, UnsupportedError
from pylumencache.domain.events import DeviceSeen
from pylumencache.transports.fallback import FallbackTransport


class Stub:
    """A transport that connects and drops when told to."""

    def __init__(self, name, raw=True):
        self.name, self.running, self.connected = name, False, False
        self.sent, self.starts, self.stops = [], 0, 0
        self._listeners, self._connection = [], []
        if not raw:
            self.send_raw = None

    def add_listener(self, callback):
        self._listeners.append(callback)
        return lambda: self._listeners.remove(callback)

    def add_connection_listener(self, callback):
        self._connection.append(callback)
        return lambda: self._connection.remove(callback)

    async def start(self):
        self.running = True
        self.starts += 1

    async def stop(self):
        self.running = False
        self.stops += 1
        self.set_connected(False)

    async def wait_connected(self, timeout=None):
        pass

    async def send(self, command):
        self.sent.append(command)

    async def send_raw(self, message):
        self.sent.append(message)

    def set_connected(self, value):
        if value != self.connected:
            self.connected = value
            for callback in list(self._connection):
                callback(value)

    def emit(self, event):
        for callback in list(self._listeners):
            callback(event)


def run(coro_fn):
    asyncio.run(asyncio.wait_for(coro_fn(), 5))


async def settle():
    await asyncio.sleep(0.05)


def test_only_the_first_is_started_while_it_connects():
    async def scenario():
        a, b = Stub("a"), Stub("b")
        fallback = FallbackTransport([a, b], fail_after=0.02)
        await fallback.start()
        assert (a.running, b.running) == (True, False)
        a.set_connected(True)
        await settle()
        await fallback.wait_connected(1)
        assert (a.running, b.running) == (True, False)
        assert fallback.active is a
        await fallback.stop()
    run(scenario)


def test_the_second_starts_only_after_the_first_stays_down():
    async def scenario():
        a, b = Stub("a"), Stub("b")
        fallback = FallbackTransport([a, b], fail_after=0.1)
        await fallback.start()
        await asyncio.sleep(0.03)
        assert not b.running   # not yet
        await asyncio.sleep(0.15)
        assert b.running
        b.set_connected(True)
        assert fallback.active is b and fallback.connected
        await fallback.stop()
    run(scenario)


def test_a_connection_that_drops_then_returns_in_time_does_not_start_the_second():
    async def scenario():
        a, b = Stub("a"), Stub("b")
        fallback = FallbackTransport([a, b], fail_after=0.15)
        await fallback.start()
        a.set_connected(True)
        await settle()
        a.set_connected(False)
        await asyncio.sleep(0.05)
        a.set_connected(True)
        await asyncio.sleep(0.25)
        assert not b.running
        await fallback.stop()
    run(scenario)


def test_the_second_is_stopped_when_the_first_comes_back():
    async def scenario():
        a, b = Stub("a"), Stub("b")
        fallback = FallbackTransport([a, b], fail_after=0.02)
        await fallback.start()
        await settle()
        b.set_connected(True)
        assert b.running and fallback.active is b
        a.set_connected(True)   # the first keeps trying in the background and gets through
        await settle()
        assert fallback.active is a
        assert not b.running and b.stops == 1
        await fallback.stop()
    run(scenario)


def test_it_falls_back_again_after_going_back():
    async def scenario():
        a, b = Stub("a"), Stub("b")
        fallback = FallbackTransport([a, b], fail_after=0.02)
        await fallback.start()
        await settle()
        a.set_connected(True)
        await settle()
        a.set_connected(False)
        await settle()
        assert b.starts == 2 and b.running   # started again after the first dropped
        await fallback.stop()
    run(scenario)


def test_events_come_only_from_the_transport_in_use():
    async def scenario():
        a, b = Stub("a"), Stub("b")
        fallback = FallbackTransport([a, b], fail_after=0.02)
        got = []
        fallback.add_listener(got.append)
        await fallback.start()
        await settle()
        b.set_connected(True)
        b.emit(DeviceSeen(2))
        a.set_connected(True)
        b.emit(DeviceSeen(3))   # b is on its way out
        a.emit(DeviceSeen(1))
        assert got == [DeviceSeen(2), DeviceSeen(1)]
        await fallback.stop()
    run(scenario)


def test_connection_listeners_hear_about_the_whole_not_each_transport():
    async def scenario():
        a, b = Stub("a"), Stub("b")
        fallback = FallbackTransport([a, b], fail_after=0.02)
        states = []
        fallback.add_connection_listener(states.append)
        await fallback.start()
        await settle()
        a.set_connected(True)
        b.set_connected(True)
        a.set_connected(False)   # b takes over: still connected
        b.set_connected(False)
        assert states == [True, False]
        await fallback.stop()
    run(scenario)


def test_commands_go_to_the_transport_in_use():
    async def scenario():
        a, b = Stub("a"), Stub("b")
        fallback = FallbackTransport([a, b], fail_after=0.02)
        command = SetLight("zone", 250, 50)
        with pytest.raises(NotConnectedError):
            await fallback.send(command)
        await fallback.start()
        await settle()
        b.set_connected(True)
        await fallback.send(command)
        a.set_connected(True)
        await fallback.send(command)
        assert (len(a.sent), len(b.sent)) == (1, 1)
        await fallback.stop()
    run(scenario)


def test_raw_commands_skip_transports_that_have_none():
    async def scenario():
        a, b = Stub("a", raw=False), Stub("b")
        fallback = FallbackTransport([a, b])
        a.set_connected(True)
        b.set_connected(True)
        await fallback.send_raw({"e": 8})
        assert b.sent == [{"e": 8}] and a.sent == []
        b.set_connected(False)
        with pytest.raises(UnsupportedError):
            await fallback.send_raw({"e": 8})
    run(scenario)


def test_the_order_is_the_order_given():
    async def scenario():
        a, b = Stub("a"), Stub("b")
        fallback = FallbackTransport([b, a], fail_after=10)
        await fallback.start()
        assert (b.running, a.running) == (True, False)
        assert fallback.transports == (b, a)
        await fallback.stop()
        assert not b.running
    run(scenario)


def test_stop_stops_everything_that_was_started():
    async def scenario():
        a, b = Stub("a"), Stub("b")
        fallback = FallbackTransport([a, b], fail_after=0.02)
        await fallback.start()
        await settle()
        await fallback.stop()
        assert not a.running and not b.running
        assert not fallback.connected
    run(scenario)


def test_at_least_one_transport_is_needed():
    with pytest.raises(ValueError):
        FallbackTransport([])


def test_the_facade_builds_one_and_the_model_follows_the_active_transport():
    async def scenario():
        a, b = Stub("a"), Stub("b")
        cache = LumenCache.with_fallback([a, b], fail_after=0.02)
        await cache.start()
        await settle()
        b.set_connected(True)
        b.emit(DeviceSeen(7))
        assert 7 in cache.model.last_seen and cache.connected
        await cache.stop()
    run(scenario)


def test_coroutine_listeners_get_events_and_connection_changes():
    async def scenario():
        first = Stub("first")
        cache = FallbackTransport([first])
        events, states = [], []

        async def on_event(event):
            events.append(event)

        async def on_connection(up):
            states.append(up)

        cache.add_listener(on_event)
        cache.add_connection_listener(on_connection)
        first.set_connected(True)
        first.emit(DeviceSeen(1))
        await asyncio.sleep(0)
        assert events == [DeviceSeen(1)] and states == [True]
    run(scenario)
