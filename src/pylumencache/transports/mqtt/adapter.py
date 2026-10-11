"""Between the MQTT wire format and the domain: parsed messages to events, commands to messages."""
from __future__ import annotations

from typing import Any

from ...domain.commands import Command
from ...domain.events import DeviceAnnounced, DeviceSeen, Event, LightChanged
from .wire import commands
from .wire.codes import Code
from .wire.models import ControllerHeartbeat, PdmHeartbeat, PowerPlaneHeartbeat, SwitchHeartbeat, ZoneEvent
from .wire.parser import CommandEcho, DeviceAnnouncementAt, Message


def to_events(message: Message) -> list[Event]:
    """The events a message carries, if any. Messages with nothing for the domain give an empty list."""
    if isinstance(message, DeviceAnnouncementAt):
        d = message.device
        return [DeviceAnnounced(d.gid, message.path, d.name, d.hsn, d.cat, d.parent)]
    if isinstance(message, (PowerPlaneHeartbeat, PdmHeartbeat, ControllerHeartbeat, SwitchHeartbeat)):
        return [DeviceSeen(message.g, getattr(message, "hsn", None))]
    if isinstance(message, ZoneEvent) and message.z is not None:
        return [LightChanged(
            "zone", message.z,
            on=bool(message.on) if message.on is not None else None,
            brightness=message.bri, color_temperature=message.cct, source="event")]
    if isinstance(message, CommandEcho):
        return _from_command(message.payload)
    return []


def _from_command(cmd: dict[str, Any]) -> list[Event]:
    code = cmd.get("e")
    if code not in (Code.ZONE_CONTROL, Code.DIRECT_CONTROL):
        return []
    bri = cmd.get("bri")
    fields: dict[str, Any] = {
        "on": None if bri is None else bri > 0,
        "brightness": bri,
        "color_temperature": cmd.get("cct"),
        "fade": cmd.get("fade"),
    }
    if all(value is None for value in fields.values()):
        return []   # nothing to learn from a command that sets nothing
    if cmd.get("z") is not None:
        return [LightChanged("zone", cmd["z"], source="command", **fields)]
    if code == Code.DIRECT_CONTROL and cmd.get("g") is not None:
        return [LightChanged("fixture", cmd["g"], source="command", **fields)]
    return []


def to_message(command: Command) -> dict[str, Any]:
    """The JSON object to publish on `cmd` for a domain command."""
    if command.kind == "zone":
        return commands.zone_control(
            zone_id=command.key, brightness=command.brightness,
            color_temperature=command.color_temperature, fade=command.fade)
    return commands.direct_control(
        gid=command.key, brightness=command.brightness,
        color_temperature=command.color_temperature, fade=command.fade)
