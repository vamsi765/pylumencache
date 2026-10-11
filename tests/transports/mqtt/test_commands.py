"""The command builders must reproduce every documented example in the spec."""
import re
from pathlib import Path

import pytest
import yaml

from pylumencache.transports.mqtt.wire import commands

SPEC = yaml.safe_load((Path(__file__).parents[3] / "docs" / "asyncapi.yaml").read_text(encoding="utf-8"))


def snake(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


def cases():
    for key, m in SPEC["components"]["messages"].items():
        if not m.get("x-documented"):
            continue
        for ex in m["examples"]:
            yield pytest.param(key, m, ex["payload"], id=f"{key}-{ex['payload']}")


@pytest.mark.parametrize("key,message,payload", list(cases()))
def test_builder_reproduces_example(key, message, payload):
    py_name = {w: snake(p["$ref"].rsplit("/", 1)[1]) for w, p in message["payload"]["properties"].items() if w != "e"}
    kwargs = {py_name[w]: v for w, v in payload.items() if w != "e"}
    assert getattr(commands, snake(key))(**kwargs) == payload


def test_brightness_out_of_range_is_refused():
    with pytest.raises(ValueError):
        commands.zone_control(zone_id=250, brightness=101)


def test_unset_arguments_are_left_out():
    assert commands.direct_control(gid=14, brightness=0) == {"e": 57, "g": 14, "bri": 0}
