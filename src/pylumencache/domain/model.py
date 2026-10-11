"""What is in the system and what state it is in, built from domain events.

The system does not report the state of a light when asked, and it does not keep its
inventory on the broker (nothing is retained). So the model learns from what passes by:

* devices come from announcements, which the system publishes once after it connects.
  Use to_dict()/from_dict() to keep them across restarts;
* a zone or light changes state when a wall switch reports it or when any client,
  including this one, sends a control command that the transport sees. Those states are
  the commands as sent. The system does not confirm that they happened;
* signs of life show which devices are alive.

Fixtures that belong to a zone are not updated when the zone changes, because the
membership of a zone cannot be read from the system.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import IntEnum
from typing import Any, Protocol

from .events import DeviceAnnounced, DeviceSeen, Event, LightChanged

_LOGGER = logging.getLogger(__name__)


class EventSource(Protocol):
    def add_listener(self, callback: Callable[[Event], Any]) -> Callable[[], None]: ...

NO_PARENT = 65535


class Category(IntEnum):
    """Device category (`cat`). Other values are possible and are kept as plain integers."""

    POWERPLANE = 32
    PDM = 35
    SOCKET = 36
    SOCKET_CARD = 37
    WALL_SWITCH = 40


@dataclass(frozen=True)
class Device:
    gid: int
    path: str
    name: str | None = None
    hsn: str | None = None
    category: int | None = None
    parent: int | None = None   # a GID, NO_PARENT for none, 0 not yet assigned

    @property
    def kind(self) -> Category | int | None:
        if self.category is None:
            return None
        try:
            return Category(self.category)
        except ValueError:
            return self.category


@dataclass(frozen=True)
class LightState:
    """The last known state of a zone or fixture. None means not known."""

    on: bool | None = None
    brightness: float | None = None    # percent, 0 to 100
    color_temperature: int | None = None   # kelvin
    fade: int | None = None   # ms, from the last command
    source: str = "unknown"   # "event" (reported by the system) or "command" (as sent, not confirmed)


@dataclass(frozen=True)
class Change:
    """Passed to listeners. `kind` is "device", "zone", "fixture" or "seen"; `key` is the id."""

    kind: str
    key: int


@dataclass
class SystemModel:
    devices: dict[int, Device] = field(default_factory=dict)
    zones: dict[int, LightState] = field(default_factory=dict)
    fixtures: dict[int, LightState] = field(default_factory=dict)
    last_seen: dict[int, float] = field(default_factory=dict)   # GID -> time.monotonic() of the last sign of life
    _listeners: list[Callable[[Change], Any]] = field(default_factory=list, repr=False)

    # --- reading -----------------------------------------------------------

    def children(self, gid: int) -> list[Device]:
        return [d for d in self.devices.values() if d.parent == gid]

    def seconds_since_seen(self, gid: int) -> float | None:
        seen = self.last_seen.get(gid)
        return None if seen is None else time.monotonic() - seen

    # --- updating ----------------------------------------------------------

    def add_listener(self, callback: Callable[[Change], Any]) -> Callable[[], None]:
        self._listeners.append(callback)
        return lambda: self._listeners.remove(callback)

    def attach(self, source: EventSource) -> Callable[[], None]:
        """Feed the model from anything with `add_listener(callback)`, such as a Transport."""
        return source.add_listener(self.apply)

    def apply(self, event: Event) -> None:
        """Update from one event."""
        if isinstance(event, DeviceAnnounced):
            self._device(event)
        elif isinstance(event, DeviceSeen):
            self._seen(event)
        elif isinstance(event, LightChanged):
            table = self.zones if event.kind == "zone" else self.fixtures
            self._set_state(table, event.kind, event.key, LightState(
                event.on, event.brightness, event.color_temperature, event.fade, event.source))

    def _notify(self, kind: str, key: int) -> None:
        for callback in list(self._listeners):
            try:
                callback(Change(kind, key))
            except Exception:   # a listener must not break the model
                _LOGGER.exception("A model listener raised an exception")

    def _device(self, event: DeviceAnnounced) -> None:
        known = self.devices.get(event.gid)
        hsn = event.hsn or (known.hsn if known else None)
        device = Device(event.gid, event.path, event.name, hsn, event.category, event.parent)
        if device != known:
            self.devices[event.gid] = device
            self._notify("device", event.gid)

    def _seen(self, event: DeviceSeen) -> None:
        self.last_seen[event.gid] = time.monotonic()
        device = self.devices.get(event.gid)
        if device and event.hsn and not device.hsn:   # the PowerPlane's announcement has no serial
            self.devices[event.gid] = Device(
                device.gid, device.path, device.name, event.hsn, device.category, device.parent)
            self._notify("device", event.gid)
        self._notify("seen", event.gid)

    def _set_state(self, table: dict[int, LightState], kind: str, key: int, new: LightState) -> None:
        """Merge `new` into the stored state: fields the message did not carry keep their value."""
        old = table.get(key, LightState())
        merged = LightState(
            on=old.on if new.on is None else new.on,
            brightness=old.brightness if new.brightness is None else new.brightness,
            color_temperature=old.color_temperature if new.color_temperature is None else new.color_temperature,
            fade=old.fade if new.fade is None else new.fade,
            source=new.source,
        )
        if merged.on and merged.brightness == 0:
            merged = LightState(True, None, merged.color_temperature, merged.fade, merged.source)
        if merged != old:
            table[key] = merged
            self._notify(kind, key)

    # --- keeping it across restarts ---------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """JSON-able copy of the devices and the last known states (not heartbeats)."""
        return {
            "devices": [asdict(d) for d in self.devices.values()],
            "zones": {str(k): asdict(v) for k, v in self.zones.items()},
            "fixtures": {str(k): asdict(v) for k, v in self.fixtures.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SystemModel:
        model = cls()
        model.devices = {d["gid"]: Device(**d) for d in data.get("devices", [])}
        model.zones = {int(k): LightState(**v) for k, v in data.get("zones", {}).items()}
        model.fixtures = {int(k): LightState(**v) for k, v in data.get("fixtures", {}).items()}
        return model
