"""The system model: inventory from announcements, and state from events."""
import json
from pathlib import Path

import pytest

from pylumencache.domain.events import DeviceAnnounced, DeviceSeen, LightChanged
from pylumencache.domain.model import Category, Change, Device, LightState, SystemModel

FIXTURES = Path(__file__).parents[1] / "fixtures"


def load(name):
    return [json.loads(line) for line in (FIXTURES / name).read_text().splitlines()]


def announced(topic, payload):
    """A DeviceAnnounced from a recorded `dev/...` message (the path is the topic without `dev/`)."""
    return DeviceAnnounced(
        payload["gid"], topic.removeprefix("dev/"), payload.get("name"), payload.get("hsn"),
        payload.get("cat"), payload.get("parent"))


def command(key, kind="zone", **fields):
    return LightChanged(kind, key, source="command", **fields)


@pytest.fixture
def model():
    m = SystemModel()
    for rec in load("inventory.jsonl"):
        m.apply(announced(rec["topic"], rec["payload"]))
    return m


def test_inventory_is_built_from_announcements(model):
    assert sorted(model.devices) == list(range(1, 16))
    assert model.devices[14].path == "pp:1/pdm:2/skt:4/scard:14"
    assert model.devices[14].kind is Category.SOCKET_CARD
    assert [d.gid for d in model.children(2)] == [3, 4, 5, 6, 7, 8, 9, 10]


def test_unknown_category_is_kept_as_a_number():
    assert Device(gid=1, path="x:1", category=99).kind == 99


def test_announcing_again_without_changes_notifies_nobody():
    m, seen = SystemModel(), []
    m.add_listener(seen.append)
    event = DeviceAnnounced(12, "sw:12", "SW-D", None, 40, 0)
    m.apply(event)
    m.apply(event)
    assert seen == [Change("device", 12)]


def test_seen_fills_in_a_serial_the_announcement_lacked(model):
    assert model.devices[1].hsn is None
    model.apply(DeviceSeen(1, "HSN9999"))
    assert model.devices[1].hsn == "HSN9999"
    assert model.seconds_since_seen(1) < 5
    assert model.seconds_since_seen(2) is None


def test_a_device_outside_the_inventory_is_still_recorded_as_seen(model):
    model.apply(DeviceSeen(100))
    assert 100 in model.last_seen and 100 not in model.devices


def test_reported_zone_state_is_stored():
    m = SystemModel()
    m.apply(LightChanged("zone", 250, True, 100, 5000, None, "event"))
    assert m.zones[250] == LightState(True, 100, 5000, None, "event")
    m.apply(LightChanged("zone", 250, False, source="event"))
    assert m.zones[250] == LightState(False, 100, 5000, None, "event")   # last brightness is kept


def test_a_later_event_keeps_the_fields_it_did_not_carry():
    m = SystemModel()
    m.apply(command(250, on=True, brightness=50, color_temperature=4000, fade=800))
    m.apply(command(250, on=True, brightness=20))
    assert m.zones[250] == LightState(True, 20, 4000, 800, "command")


def test_on_without_brightness_forgets_a_zero_brightness():
    m = SystemModel()
    m.apply(command(250, on=False, brightness=0))
    assert m.zones[250].on is False
    m.apply(LightChanged("zone", 250, on=True, source="event"))
    assert m.zones[250].on is True and m.zones[250].brightness is None


def test_zones_and_fixtures_are_kept_apart():
    m = SystemModel()
    m.apply(command(14, "fixture", on=True, brightness=60, color_temperature=3000))
    m.apply(command(250, on=True, brightness=10))
    assert m.fixtures[14].brightness == 60 and 14 not in m.zones
    assert m.zones[250].brightness == 10


def test_listeners_hear_about_changes_and_can_fail_or_leave():
    m, seen = SystemModel(), []

    def broken(_):
        raise RuntimeError("bad")

    m.add_listener(broken)
    remove = m.add_listener(seen.append)
    m.apply(command(250, on=True, brightness=50))
    remove()
    m.apply(command(250, on=True, brightness=60))
    assert seen == [Change("zone", 250)]


def test_round_trip_through_json(model):
    model.apply(command(250, on=True, brightness=50, color_temperature=4000, fade=800))
    model.apply(command(14, "fixture", on=True, brightness=5))
    copy = SystemModel.from_dict(json.loads(json.dumps(model.to_dict())))
    assert copy.devices == model.devices
    assert copy.zones == model.zones and copy.fixtures == model.fixtures


def test_attaches_to_anything_with_add_listener():
    class Source:
        def add_listener(self, callback):
            self.callback = callback
            return lambda: None

    m, source = SystemModel(), Source()
    m.attach(source)
    source.callback(command(1, on=True, brightness=5))
    assert 1 in m.zones
