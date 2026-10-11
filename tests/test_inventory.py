"""The system model: inventory from recorded announcements, and state from events and commands."""
import json
from pathlib import Path

import pytest

from pylumencache.inventory import Category, Change, Device, LightState, SystemModel
from pylumencache.protocol.parser import parse

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return [json.loads(line) for line in (FIXTURES / name).read_text().splitlines()]


@pytest.fixture
def model():
    m = SystemModel()
    for rec in load("inventory.jsonl"):
        m.apply(parse(rec["topic"], rec["payload"]))
    return m


def test_inventory_is_built_from_announcements(model):
    assert sorted(model.devices) == list(range(1, 16))
    assert model.devices[14].path == "dev/pp:1/pdm:2/skt:4/scard:14".removeprefix("dev/")
    assert model.devices[14].kind is Category.SOCKET_CARD
    assert [d.gid for d in model.children(2)] == [3, 4, 5, 6, 7, 8, 9, 10]


def test_unknown_category_is_kept_as_a_number():
    assert Device(gid=1, path="x:1", category=99).kind == 99


def test_announcing_again_without_changes_notifies_nobody():
    m, seen = SystemModel(), []
    m.add_listener(seen.append)
    message = parse("dev/sw:12", {"gid": 12, "name": "SW-D", "cat": 40, "parent": 0})
    m.apply(message)
    m.apply(message)
    assert seen == [Change("device", 12)]


def test_heartbeat_fills_in_a_serial_the_announcement_lacked(model):
    assert model.devices[1].hsn is None
    model.apply(parse("status", {"e": 139, "g": 1, "hsn": "HSN9999", "swv": "1", "hwv": "1", "time": 5, "heap": 6}))
    assert model.devices[1].hsn == "HSN9999"
    assert model.seconds_since_heartbeat(1) < 5
    assert model.seconds_since_heartbeat(2) is None


def test_heartbeat_from_a_node_outside_the_inventory_is_still_recorded(model):
    model.apply(parse("status", {"e": 139, "g": 100, "opc": 2, "mode": 3, "12v": 1, "term": 1, "heap": 9,
                                 "txrx": [0, 0, 0, 0], "uptime": 5, "temp": 29.5}))
    assert 100 in model.heartbeats and 100 not in model.devices


def test_switch_zone_event_sets_state():
    m = SystemModel()
    m.apply(parse("status", {"e": 56, "z": 250, "on": 1, "bri": 100, "cct": 5000, "dev": 12, "g": 65534}))
    assert m.zones[250] == LightState(True, 100, 5000, None, "event")
    m.apply(parse("status", {"e": 56, "z": 250, "on": 0, "dev": 12, "g": 65534}))
    assert m.zones[250] == LightState(False, 100, 5000, None, "event")   # last brightness is kept


def test_zone_command_echo_sets_state_and_keeps_unspecified_fields():
    m = SystemModel()
    m.apply(parse("cmd", {"e": 56, "z": 250, "bri": 50, "cct": 4000, "fade": 800}))
    m.apply(parse("cmd", {"e": 56, "z": 250, "bri": 20}))
    assert m.zones[250] == LightState(True, 20, 4000, 800, "command")


def test_zero_brightness_means_off():
    m = SystemModel()
    m.apply(parse("cmd", {"e": 56, "z": 250, "bri": 0}))
    assert m.zones[250].on is False


def test_on_event_without_brightness_forgets_a_zero_brightness():
    m = SystemModel()
    m.apply(parse("cmd", {"e": 56, "z": 250, "bri": 0}))
    m.apply(parse("status", {"e": 56, "z": 250, "on": 1}))
    assert m.zones[250].on is True and m.zones[250].brightness is None


def test_direct_control_targets_a_fixture_or_a_zone():
    m = SystemModel()
    m.apply(parse("cmd", {"e": 57, "g": 14, "bri": 60, "cct": 3000}))
    m.apply(parse("cmd", {"e": 57, "z": 250, "bri": 10}))
    assert m.fixtures[14].brightness == 60 and 14 not in m.zones
    assert m.zones[250].brightness == 10


@pytest.mark.parametrize("cmd", [{"e": 8, "g": 2}, {"e": 56, "z": 250}, {"e": 57, "g": 14}, {"e": 15, "g": 2, "c": 0}])
def test_commands_that_set_no_state_change_nothing(cmd):
    m = SystemModel()
    m.apply(parse("cmd", cmd))
    assert not m.zones and not m.fixtures


def test_listeners_hear_about_changes_and_can_fail_or_leave():
    m, seen = SystemModel(), []

    def broken(_):
        raise RuntimeError("bad")

    m.add_listener(broken)
    remove = m.add_listener(seen.append)
    m.apply(parse("cmd", {"e": 56, "z": 250, "bri": 50}))
    remove()
    m.apply(parse("cmd", {"e": 56, "z": 250, "bri": 60}))
    assert seen == [Change("zone", 250)]


def test_round_trip_through_json(model):
    model.apply(parse("cmd", {"e": 56, "z": 250, "bri": 50, "cct": 4000, "fade": 800}))
    model.apply(parse("cmd", {"e": 57, "g": 14, "bri": 5}))
    copy = SystemModel.from_dict(json.loads(json.dumps(model.to_dict())))
    assert copy.devices == model.devices
    assert copy.zones == model.zones and copy.fixtures == model.fixtures


def test_attaches_to_a_client():
    class FakeClient:
        def add_listener(self, callback):
            self.callback = callback
            return lambda: None

    m, client = SystemModel(), FakeClient()
    m.attach(client)
    client.callback(parse("cmd", {"e": 56, "z": 1, "bri": 5}))
    assert 1 in m.zones
