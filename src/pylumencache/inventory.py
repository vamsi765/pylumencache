"""What is in the system and what state it is in, built from received messages.

The system does not report the state of a light when asked, and it does not keep its
inventory on the broker (nothing is retained). So the model learns from what passes by:

* devices come from `dev/...` announcements, which the system publishes once after it
  connects. Use to_dict()/from_dict() to keep them across restarts;
* a zone or light changes state when a wall switch reports it (ZoneEvent) or when any
  client, including this one, publishes a control command (the broker echoes it back).
  Those states are the commands as sent. The system does not confirm that they happened;
* heartbeats show which devices are alive.

Fixtures that belong to a zone are not updated when the zone changes, because the
membership of a zone cannot be read from the system.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import IntEnum
from typing import Any

from .protocol.codes import Code
from .protocol.models import (
    ControllerHeartbeat,
    PdmHeartbeat,
    PowerPlaneHeartbeat,
    SwitchHeartbeat,
    ZoneEvent,
)
from .protocol.parser import CommandEcho, DeviceAnnouncementAt, Message

_LOGGER = logging.getLogger(__name__)

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
    source: str = "unknown"   # "event" (reported by a switch) or "command" (as sent, not confirmed)


@dataclass(frozen=True)
class Change:
    """Passed to listeners. `kind` is "device", "zone", "fixture" or "heartbeat"; `key` is the id."""

    kind: str
    key: int


@dataclass
class SystemModel:
    devices: dict[int, Device] = field(default_factory=dict)
    zones: dict[int, LightState] = field(default_factory=dict)
    fixtures: dict[int, LightState] = field(default_factory=dict)
    heartbeats: dict[int, Any] = field(default_factory=dict)   # GID -> latest heartbeat message
    heartbeat_times: dict[int, float] = field(default_factory=dict)   # GID -> time.monotonic()
    _listeners: list[Callable[[Change], Any]] = field(default_factory=list, repr=False)

    # --- reading -----------------------------------------------------------

    def children(self, gid: int) -> list[Device]:
        return [d for d in self.devices.values() if d.parent == gid]

    def seconds_since_heartbeat(self, gid: int) -> float | None:
        seen = self.heartbeat_times.get(gid)
        return None if seen is None else time.monotonic() - seen

    # --- updating ----------------------------------------------------------

    def add_listener(self, callback: Callable[[Change], Any]) -> Callable[[], None]:
        self._listeners.append(callback)
        return lambda: self._listeners.remove(callback)

    def attach(self, client) -> Callable[[], None]:
        """Feed the model from a LumenCacheClient. Returns a function that detaches it."""
        return client.add_listener(self.apply)

    def apply(self, message: Message) -> None:
        """Update from one parsed message. Messages that carry nothing for the model are ignored."""
        if isinstance(message, DeviceAnnouncementAt):
            self._device(message)
        elif isinstance(message, (PowerPlaneHeartbeat, PdmHeartbeat, ControllerHeartbeat, SwitchHeartbeat)):
            self._heartbeat(message)
        elif isinstance(message, ZoneEvent):
            self._set_state(self.zones, "zone", message.z, LightState(
                on=bool(message.on) if message.on is not None else None,
                brightness=message.bri, color_temperature=message.cct, source="event"))
        elif isinstance(message, CommandEcho):
            self._command(message.payload)

    def _notify(self, kind: str, key: int) -> None:
        for callback in list(self._listeners):
            try:
                callback(Change(kind, key))
            except Exception:   # a listener must not break the model
                _LOGGER.exception("A model listener raised an exception")

    def _device(self, message: DeviceAnnouncementAt) -> None:
        d = message.device
        known = self.devices.get(d.gid)
        device = Device(d.gid, message.path, d.name, d.hsn or (known.hsn if known else None), d.cat, d.parent)
        if device != known:
            self.devices[d.gid] = device
            self._notify("device", d.gid)

    def _heartbeat(self, hb) -> None:
        self.heartbeats[hb.g] = hb
        self.heartbeat_times[hb.g] = time.monotonic()
        device = self.devices.get(hb.g)
        serial = getattr(hb, "hsn", None)
        if device and serial and not device.hsn:   # the PowerPlane's announcement has no serial
            self.devices[hb.g] = Device(device.gid, device.path, device.name, serial, device.category, device.parent)
            self._notify("device", hb.g)
        self._notify("heartbeat", hb.g)

    def _command(self, cmd: dict) -> None:
        code = cmd.get("e")
        if code not in (Code.ZONE_CONTROL, Code.DIRECT_CONTROL):
            return
        bri = cmd.get("bri")
        state = LightState(on=None if bri is None else bri > 0, brightness=bri,
                           color_temperature=cmd.get("cct"), fade=cmd.get("fade"), source="command")
        if state == LightState(source="command"):
            return   # nothing to learn from a command that sets nothing
        if cmd.get("z") is not None:
            self._set_state(self.zones, "zone", cmd["z"], state)
        elif code == Code.DIRECT_CONTROL and cmd.get("g") is not None:
            self._set_state(self.fixtures, "fixture", cmd["g"], state)

    def _set_state(self, table: dict, kind: str, key: int, new: LightState) -> None:
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

    def to_dict(self) -> dict:
        """JSON-able copy of the devices and the last known states (not heartbeats)."""
        return {
            "devices": [asdict(d) for d in self.devices.values()],
            "zones": {str(k): asdict(v) for k, v in self.zones.items()},
            "fixtures": {str(k): asdict(v) for k, v in self.fixtures.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> SystemModel:
        model = cls()
        model.devices = {d["gid"]: Device(**d) for d in data.get("devices", [])}
        model.zones = {int(k): LightState(**v) for k, v in data.get("zones", {}).items()}
        model.fixtures = {int(k): LightState(**v) for k, v in data.get("fixtures", {}).items()}
        return model
