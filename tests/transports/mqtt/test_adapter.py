"""Wire messages to domain events, and domain commands to wire messages."""
import pytest

from pylumencache.domain.commands import SetFixture
from pylumencache.domain.events import DeviceAnnounced, DeviceSeen, FixtureChanged
from pylumencache.domain.targets import Fixture, Zone
from pylumencache.transports.mqtt.adapter import to_events, to_message
from pylumencache.transports.mqtt.wire.parser import parse


def events(topic, payload):
    return to_events(parse(topic, payload))


def test_an_announcement_becomes_a_device():
    payload = {"gid": 14, "hsn": "HSN1", "name": "SC-CC2-50W", "cat": 37, "parent": 4}
    assert events("dev/pp:1/pdm:2/skt:4/scard:14", payload) == [
        DeviceAnnounced(14, "pp:1/pdm:2/skt:4/scard:14", "SC-CC2-50W", "HSN1", 37, 4)]


def test_heartbeats_become_sightings_with_the_serial_when_there_is_one():
    pp = {"e": 139, "g": 1, "hsn": "HSN9", "swv": "1", "hwv": "1", "time": 5, "heap": 6}
    assert events("status", pp) == [DeviceSeen(1, "HSN9")]
    controller = {"e": 139, "g": 100, "opc": 2, "mode": 3, "12v": 1, "term": 1, "heap": 9,
                  "txrx": [0, 0, 0, 0], "uptime": 5, "temp": 29.5}
    assert events("status", controller) == [DeviceSeen(100, None)]


def test_a_switch_zone_event_is_a_reported_light_change():
    payload = {"e": 56, "z": 250, "on": 1, "bri": 100, "cct": 5000, "dev": 12, "g": 65534}
    assert events("status", payload) == [FixtureChanged(Zone(250), True, 100, 5000, None, "event")]


def test_an_echoed_zone_command_is_a_command_change():
    assert events("cmd", {"e": 56, "z": 250, "bri": 50, "cct": 4000, "fade": 800}) == [
        FixtureChanged(Zone(250), True, 50, 4000, 800, "command")]


def test_zero_brightness_means_off():
    assert events("cmd", {"e": 56, "z": 250, "bri": 0})[0].on is False


def test_direct_control_targets_a_fixture_or_a_zone():
    assert events("cmd", {"e": 57, "g": 14, "bri": 60, "cct": 3000}) == [
        FixtureChanged(Fixture(14), True, 60, 3000, None, "command")]
    assert events("cmd", {"e": 57, "z": 250, "bri": 10}) == [FixtureChanged(Zone(250), True, 10, None, None, "command")]


@pytest.mark.parametrize("cmd", [{"e": 8, "g": 2}, {"e": 56, "z": 250}, {"e": 57, "g": 14}, {"e": 15, "g": 2, "c": 0}])
def test_commands_that_set_no_state_give_no_events(cmd):
    assert events("cmd", cmd) == []


def test_unknown_and_empty_messages_give_no_events():
    assert events("cmd", "") == []
    assert events("whatever", "not json") == []


def test_set_light_becomes_a_zone_or_direct_control_command():
    assert to_message(SetFixture(Zone(250), 50, 4000, 800)) == {"e": 56, "z": 250, "bri": 50, "cct": 4000, "fade": 800}
    assert to_message(SetFixture(Fixture(14), 0)) == {"e": 57, "g": 14, "bri": 0}
