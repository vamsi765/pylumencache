"""Which kind of fixture a device is, from the model name it announced.

The socket card's model name tells how many channels it has: `SC-CC2` and `SC-PV2` are two
channels of tunable white, `SC-CC1` and `SC-PV1` are one channel of a single color. A power rating
may follow, as in `SC-CC2-50W`. The load
attached through a Smart Interface Block can change what a card really drives, and that
profile is not read yet, so this is the best guess from the card. A card that matches nothing
is a plain `Fixture`. Add your own models with `register_model`.
"""
from __future__ import annotations

import re

from .model import Device
from .targets import Fixture, Light, TunableLight

_RULES: list[tuple[re.Pattern[str], type[Fixture]]] = [
    (re.compile(r"^SC-(CC|PV)2(-.*)?$", re.IGNORECASE), TunableLight),
    (re.compile(r"^SC-(CC|PV)1(-.*)?$", re.IGNORECASE), Light),
]


def register_model(pattern: str, fixture_type: type[Fixture]) -> None:
    """Treat devices whose model name fully matches the regular expression `pattern` as `fixture_type`.

    Rules added later win over earlier ones, and over the built-in ones.
    """
    _RULES.insert(0, (re.compile(f"^(?:{pattern})$", re.IGNORECASE), fixture_type))


def fixture_type(device: Device) -> type[Fixture]:
    """The class that describes `device`: the first matching rule, or `Fixture` when none matches."""
    name = (device.name or "").strip()
    for pattern, kind in _RULES:
        if pattern.match(name):
            return kind
    return Fixture


def fixture_for(device: Device) -> Fixture:
    """The target for `device`, as an instance of its class."""
    return fixture_type(device)(device.gid)
