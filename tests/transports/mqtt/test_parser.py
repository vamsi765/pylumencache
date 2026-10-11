"""Parsing of received messages: spec examples, recorded traffic, and bad input."""
import json
from pathlib import Path

import pytest
import yaml

from pylumencache.transports.mqtt.wire import parser
from pylumencache.transports.mqtt.wire.parser import parse

ROOT = Path(__file__).parents[3]
SPEC = yaml.safe_load((ROOT / "docs" / "asyncapi.yaml").read_text(encoding="utf-8"))
FIXTURE_FILE = Path(__file__).parents[2] / "fixtures" / "messages.jsonl"
FIXTURES = [json.loads(line) for line in FIXTURE_FILE.read_text().splitlines()]

# Where each received message is published, and the class the parser should give it.
SPEC_MESSAGES = {
    "zoneEvent": ("status", "ZoneEvent"),
    "errorReport": ("status", "ErrorReport"),
    "hailReply": ("meta", "HailReply"),
    "switchConfig": ("meta", "SwitchConfig"),
    "systemInfo": ("meta", "SystemInfo"),
    "deviceAnnouncement": ("dev/pp:1/pdm:2", "DeviceAnnouncementAt"),
}
HEARTBEAT_CLASSES = {
    "g:1": "PowerPlaneHeartbeat", "bay": "PdmHeartbeat", "opc": "ControllerHeartbeat", "uirgb": "SwitchHeartbeat",
}


def spec_examples():
    for key, (topic, cls) in SPEC_MESSAGES.items():
        for ex in SPEC["components"]["messages"][key]["examples"]:
            yield pytest.param(topic, ex["payload"], cls, id=f"{key}-{ex['payload']}"[:60])
    for ex in SPEC["components"]["messages"]["heartbeat"]["examples"]:
        p = ex["payload"]
        cls = next((c for k, c in HEARTBEAT_CLASSES.items() if k in p), "PowerPlaneHeartbeat")
        yield pytest.param("status", p, cls, id=f"heartbeat-{cls}-{p['g']}")


@pytest.mark.parametrize("topic,payload,cls", list(spec_examples()))
def test_spec_example_parses_to_its_class(topic, payload, cls):
    assert type(parse(topic, payload)).__name__ == cls


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f"{f['expect']}-{f['topic']}")
def test_recorded_message_parses_to_its_class_without_leftovers(fixture):
    msg = parse(fixture["topic"], json.dumps(fixture["payload"]))
    assert type(msg).__name__ == fixture["expect"]
    leftovers = getattr(msg, "extra", None) or getattr(getattr(msg, "device", None), "extra", None)
    assert not leftovers, "the spec is missing fields the system sent"


def test_every_kind_of_message_has_a_fixture():
    wanted = {c for _, c in SPEC_MESSAGES.values() if c != "SystemInfo"} | set(HEARTBEAT_CLASSES.values())
    assert {f["expect"] for f in FIXTURES} >= wanted


def test_field_values_and_renamed_field():
    ctrl = parse("status", {"e": 139, "g": 100, "opc": 2, "mode": 3, "12v": 1, "term": 1, "heap": 9,
                            "txrx": [0, 0, 1, 0], "uptime": 5, "temp": 29.5})
    assert (ctrl.g, ctrl.v12, ctrl.txrx, ctrl.temp) == (100, 1, [0, 0, 1, 0], 29.5)


def test_optional_fields_are_none_when_absent():
    event = parse("status", {"e": 56, "z": 250, "on": 0, "dev": 12, "g": 65534})
    assert (event.on, event.bri, event.cct) == (0, None, None)


def test_unknown_fields_are_kept():
    event = parse("status", {"e": 56, "z": 250, "on": 1, "novel": "x"})
    assert event.extra == {"novel": "x"}


def test_device_path_is_kept():
    msg = parse("dev/pp:1/pdm:2/skt:4/scard:14", {"gid": 14, "name": "SC-CC2-50W", "cat": 37, "parent": 4})
    assert (msg.path, msg.device.gid, msg.device.parent) == ("pp:1/pdm:2/skt:4/scard:14", 14, 4)


def test_system_info_keeps_the_nested_meta():
    msg = parse("meta", {"sys": "S", "meta": {"cat": 0}})
    assert (msg.sys, msg.meta) == ("S", {"cat": 0})


def test_command_echo_and_empty_reply():
    assert parse("cmd", {"e": 57, "g": 14}) == parser.CommandEcho({"e": 57, "g": 14})
    assert parse("cmd", b"") == parser.Empty("cmd")


def test_bytes_are_decoded():
    assert type(parse("status", b'{"e":254,"g":100,"err":38,"v":254}')).__name__ == "ErrorReport"


@pytest.mark.parametrize("topic,payload", [
    ("status", {"e": 999}),                      # code we have never seen
    ("status", {"e": 139, "g": 1}),              # heartbeat missing required fields
    ("status", {"no": "code"}),
    ("status", "not json"),
    ("status", b"\xff\xfe"),
    ("status", [1, 2]),
    ("elsewhere", {"e": 139}),
])
def test_unrecognised_input_is_returned_as_unknown(topic, payload):
    msg = parse(topic, payload)
    assert isinstance(msg, parser.UnknownMessage) and msg.topic == topic


def test_relative_topic():
    assert parser.relative_topic("platform:na/x", "platform:na/x/dev/pp:1") == "dev/pp:1"
    with pytest.raises(ValueError):
        parser.relative_topic("platform:na/x", "other/dev")
