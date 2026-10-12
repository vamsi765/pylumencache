"""The facade: a model kept up to date by a transport, behind one object."""
import asyncio
import json
from pathlib import Path

import pytest

from pylumencache import LumenCache, NotConnectedError, SetLight, SystemModel, UnsupportedError
from pylumencache.transports.mqtt import MqttTransport
from pylumencache.transports.mqtt.fake import FakeController

FIXTURES = Path(__file__).parent / "fixtures"
RECORDS = [json.loads(line) for name in ("inventory.jsonl", "messages.jsonl")
           for line in (FIXTURES / name).read_text().splitlines()]


def run(coro_fn):
    asyncio.run(asyncio.wait_for(coro_fn(), 5))


def fake_cache(**kwargs):
    controller = FakeController(RECORDS, "p")
    return LumenCache(MqttTransport("fake", "p", client_factory=controller.factory), **kwargs)


def test_the_model_is_built_and_kept_up_to_date():
    async def scenario():
        cache = fake_cache()
        await cache.start()
        await cache.wait_connected(1)
        assert cache.connected
        while len(cache.model.devices) < 15:
            await asyncio.sleep(0.005)
        await cache.send(SetLight("fixture", 14, brightness=30, color_temperature=3000))
        while 14 not in cache.model.fixtures:
            await asyncio.sleep(0.005)
        await cache.stop()
        assert (cache.model.fixtures[14].brightness, cache.model.fixtures[14].color_temperature) == (30, 3000)
    run(scenario)


def test_a_given_model_is_used():
    model = SystemModel()
    assert fake_cache(model=model).model is model


def test_mqtt_builds_an_mqtt_transport():
    cache = LumenCache.mqtt("broker", "p", port=1883)
    assert isinstance(cache.transport, MqttTransport)
    assert not cache.connected


def test_sending_when_not_connected_is_refused():
    async def scenario():
        with pytest.raises(NotConnectedError):
            await fake_cache().send(SetLight("zone", 1, brightness=0))
    run(scenario)


def test_raw_commands_need_a_transport_that_has_them():
    class Bare:
        connected = False

        def add_listener(self, callback):
            return lambda: None

    async def scenario():
        with pytest.raises(UnsupportedError):
            await LumenCache(Bare()).send_raw({"e": 8})
    run(scenario)


def test_mqtt_and_fallback_declare_raw_commands_and_a_bare_transport_does_not():
    from pylumencache import RawCommandTransport
    from pylumencache.transports.fallback import FallbackTransport
    from pylumencache.transports.mqtt import MqttTransport

    async def scenario():
        mqtt = MqttTransport("host", "prefix")
        assert isinstance(mqtt, RawCommandTransport)
        assert isinstance(FallbackTransport([mqtt]), RawCommandTransport)
    run(scenario)
