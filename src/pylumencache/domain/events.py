"""What a transport tells the domain model, independent of any wire format."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .targets import Target

Source = Literal["event", "command", "unknown"]


@dataclass(frozen=True)
class DeviceAnnounced:
    """A device exists. `path` is where the system placed it in its device tree."""

    gid: int
    path: str
    name: str | None = None
    hsn: str | None = None
    category: int | None = None
    parent: int | None = None


@dataclass(frozen=True)
class DeviceSeen:
    """A device showed signs of life. `hsn` is its serial number, when the message carried it."""

    gid: int
    hsn: str | None = None


@dataclass(frozen=True)
class FixtureChanged:
    """A zone or fixture changed state. None means the message did not say.

    `source` is "event" when the system reported it and "command" when it is a command as
    sent, which the system does not confirm.
    """

    target: Target
    on: bool | None = None
    brightness: float | None = None   # percent, 0 to 100
    color_temperature: int | None = None   # kelvin
    fade: int | None = None   # ms
    source: Source = "unknown"


Event = DeviceAnnounced | DeviceSeen | FixtureChanged
