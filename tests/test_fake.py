"""The fake controller, and the whole stack running on it."""
import asyncio
import json
from pathlib import Path

from pylumencache.client import LumenCacheClient
from pylumencache.fake import FakeController
from pylumencache.inventory import SystemModel
from pylumencache.protocol import commands
from pylumencache.protocol.parser import CommandEcho, Empty, HailReply, SwitchConfig, UnknownMessage

FIXTURES = Path(__file__).parent / "fixtures"
RECORDS = [json.loads(line) for name in ("inventory.jsonl", "messages.jsonl")
           for line in (FIXTURES / name).read_text().splitlines()]


def run(coro_fn):
    asyncio.run(asyncio.wait_for(coro_fn(), 5))


async def started(controller):
    client, got = LumenCacheClient("fake", "p", client_factory=controller.factory), []
    client.add_listener(got.append)
    await client.start()
    await client.wait_connected(1)
    return client, got


async def until(predicate):
    while not predicate():
        await asyncio.sleep(0.005)


def test_replays_the_recorded_system_into_a_model():
    async def scenario():
        controller = FakeController(RECORDS, "p")
        client, got = await started(controller)
        model = SystemModel()
        model.attach(client)
        await until(lambda: len(model.devices) == 15 and {1, 2, 100, 12} <= set(model.heartbeats))
        await client.stop()
        assert not any(isinstance(m, UnknownMessage) for m in got)
        assert model.zones[250].source == "event"
    run(scenario)


def test_a_command_is_echoed_and_answered_with_an_empty_reply():
    async def scenario():
        client, got = await started(FakeController(RECORDS, "p"))
        await client.send(commands.zone_control(zone_id=250, brightness=40))
        await until(lambda: any(isinstance(m, CommandEcho) for m in got) and any(isinstance(m, Empty) for m in got))
        await client.stop()
        echo = next(m for m in got if isinstance(m, CommandEcho))
        assert echo.payload == {"e": 56, "z": 250, "bri": 40}
    run(scenario)


def test_the_model_follows_commands_sent_through_the_fake():
    async def scenario():
        client, _ = await started(FakeController(RECORDS, "p"))
        model = SystemModel()
        model.attach(client)
        await client.send(commands.direct_control(gid=14, brightness=30, color_temperature=3000))
        await until(lambda: 14 in model.fixtures)
        await client.stop()
        assert (model.fixtures[14].brightness, model.fixtures[14].color_temperature) == (30, 3000)
    run(scenario)


def test_hail_and_config_get_the_recorded_answers():
    async def scenario():
        client, got = await started(FakeController(RECORDS, "p"))
        await client.send(commands.hail(gid=0))
        await client.send(commands.config(gid=12))
        await until(lambda: {HailReply, SwitchConfig} <= {type(m) for m in got})
        await client.stop()
    run(scenario)


def test_a_reconnect_replays_the_system_again():
    async def scenario():
        client, got = await started(FakeController(RECORDS, "p"))
        await until(lambda: any(type(m).__name__ == "PdmHeartbeat" for m in got))
        await client.stop()
        again, got2 = await started(FakeController(RECORDS, "p"))
        await until(lambda: any(type(m).__name__ == "PdmHeartbeat" for m in got2))
        await again.stop()
    run(scenario)
