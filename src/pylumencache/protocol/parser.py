"""Turn a message received from the broker into a typed object.

Never raises on odd input: anything that is not recognised comes back as an
UnknownMessage that still carries the topic and the payload.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .codes import Code
from .models import (
    ControllerHeartbeat,
    DeviceAnnouncement,
    ErrorReport,
    HailReply,
    PdmHeartbeat,
    PowerPlaneHeartbeat,
    SwitchConfig,
    SwitchHeartbeat,
    ZoneEvent,
)

Heartbeat = PowerPlaneHeartbeat | PdmHeartbeat | ControllerHeartbeat | SwitchHeartbeat


@dataclass(frozen=True)
class Empty:
    """An empty payload. The system sends one after each command it handled on `cmd`."""

    topic: str


@dataclass(frozen=True)
class CommandEcho:
    """A command published on `cmd`, echoed back by the broker (ours or another client's)."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class SystemInfo:
    """System information from `meta`: the system id and the nested `meta` object, as sent."""

    sys: str
    meta: dict[str, Any]
    extra: dict[str, Any]


@dataclass(frozen=True)
class DeviceAnnouncementAt:
    """A device announcement together with the device path it was published under."""

    path: str
    device: DeviceAnnouncement


@dataclass(frozen=True)
class UnknownMessage:
    topic: str
    payload: Any


Message = (
    Heartbeat | ZoneEvent | ErrorReport | HailReply | SwitchConfig | SystemInfo
    | DeviceAnnouncementAt | CommandEcho | Empty | UnknownMessage
)


def relative_topic(prefix: str, topic: str) -> str:
    """Remove the Prefix Topic from a full topic. Raises ValueError if it does not start with it."""
    start = prefix.rstrip("/") + "/"
    if not topic.startswith(start):
        raise ValueError(f"topic {topic!r} is not under the prefix")
    return topic[len(start):]


def _heartbeat(data: dict[str, Any]) -> Heartbeat:
    if "uirgb" in data:
        return SwitchHeartbeat.from_dict(data)
    if "opc" in data:
        return ControllerHeartbeat.from_dict(data)
    if "bay" in data:
        return PdmHeartbeat.from_dict(data)
    return PowerPlaneHeartbeat.from_dict(data)


def _by_code(data: dict[str, Any]) -> Message | None:
    e = data.get("e")
    if e == Code.HEARTBEAT:
        return _heartbeat(data)
    if e == Code.ZONE_CONTROL:
        return ZoneEvent.from_dict(data)
    if e == Code.ERROR_REPORT:
        return ErrorReport.from_dict(data)
    if e == Code.HAIL_REPLY:
        return HailReply.from_dict(data)
    if e == Code.SWITCH_CONFIG:
        return SwitchConfig.from_dict(data)
    return None


def parse(topic: str, payload: bytes | str | dict[str, Any]) -> Message:
    """Parse one message. `topic` is relative to the Prefix Topic (`status`, `dev/pp:1/...`)."""
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError:
            return UnknownMessage(topic, payload)
    if isinstance(payload, str):
        if payload == "":
            return Empty(topic)
        try:
            payload = json.loads(payload)
        except ValueError:
            return UnknownMessage(topic, payload)
    if not isinstance(payload, dict):
        return UnknownMessage(topic, payload)

    area, _, rest = topic.partition("/")
    try:
        if area == "cmd":
            return CommandEcho(payload)
        if area == "dev" and rest:
            return DeviceAnnouncementAt(rest, DeviceAnnouncement.from_dict(payload))
        if area == "meta" and "sys" in payload and "e" not in payload:
            extra = {k: v for k, v in payload.items() if k not in ("sys", "meta")}
            return SystemInfo(payload["sys"], payload.get("meta", {}), extra)
        if area in ("status", "errors", "meta"):
            found = _by_code(payload)
            if found is not None:
                return found
    except (KeyError, TypeError):   # a required field is missing
        pass
    return UnknownMessage(topic, payload)
