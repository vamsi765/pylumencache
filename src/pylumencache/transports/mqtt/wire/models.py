"""Received messages. Generated from docs/asyncapi.yaml by tools/gen_protocol.py; do not edit.

Each class has from_dict(). Fields the spec does not list are kept in `extra`, and
optional fields are None when the message did not carry them. A missing required
field raises TypeError, which the parser turns into an UnknownMessage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Self


class WireMessage:
    """What every received message has in common: how it is built from the JSON object."""

    E: ClassVar[int | None]   # the value of `e`, when the message has one
    WIRE: ClassVar[dict[str, str]]   # wire key -> field name

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        values = {py: data[wire] for wire, py in cls.WIRE.items() if wire in data}
        extra = {k: v for k, v in data.items() if k not in cls.WIRE and k != "e"}
        return cls(**values, extra=extra)   # type: ignore[call-arg]


@dataclass(frozen=True)
class PowerPlaneHeartbeat(WireMessage):
    """Received message with e:139."""

    g: int
    hsn: str
    swv: str
    hwv: str
    time: int
    heap: int
    extra: dict[str, Any] = field(default_factory=dict)

    E = 139
    WIRE = {"g": "g", "hsn": "hsn", "swv": "swv", "hwv": "hwv", "time": "time", "heap": "heap"}


@dataclass(frozen=True)
class PdmHeartbeat(WireMessage):
    """Received message with e:139."""

    g: int
    bay: int
    hsn: str
    swv: str
    hwv: str
    time: int
    heap: int
    temp: float
    rh: float
    extra: dict[str, Any] = field(default_factory=dict)

    E = 139
    WIRE = {"g": "g", "bay": "bay", "hsn": "hsn", "swv": "swv", "hwv": "hwv", "time": "time", "heap": "heap", "temp": "temp", "rh": "rh"}


@dataclass(frozen=True)
class ControllerHeartbeat(WireMessage):
    """Received message with e:139."""

    g: int
    opc: int
    mode: int
    v12: int
    term: int
    heap: int
    txrx: list[int]
    uptime: int
    temp: float
    extra: dict[str, Any] = field(default_factory=dict)

    E = 139
    WIRE = {"g": "g", "opc": "opc", "mode": "mode", "12v": "v12", "term": "term", "heap": "heap", "txrx": "txrx", "uptime": "uptime", "temp": "temp"}


@dataclass(frozen=True)
class SwitchHeartbeat(WireMessage):
    """Received message with e:139."""

    g: int
    uirgb: str
    term: int
    heap: int
    txrx: list[int]
    uptime: int
    extra: dict[str, Any] = field(default_factory=dict)

    E = 139
    WIRE = {"g": "g", "uirgb": "uirgb", "term": "term", "heap": "heap", "txrx": "txrx", "uptime": "uptime"}


@dataclass(frozen=True)
class ZoneEvent(WireMessage):
    """Received message with e:56."""

    z: int | None = None
    on: int | None = None
    bri: float | None = None
    cct: int | None = None
    dev: int | None = None
    g: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    E = 56
    WIRE = {"z": "z", "on": "on", "bri": "bri", "cct": "cct", "dev": "dev", "g": "g"}


@dataclass(frozen=True)
class ErrorReport(WireMessage):
    """Received message with e:254."""

    g: int | None = None
    err: int | None = None
    v: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    E = 254
    WIRE = {"g": "g", "err": "err", "v": "v"}


@dataclass(frozen=True)
class HailReply(WireMessage):
    """Received message with e:137."""

    g: int | None = None
    hsn: str | None = None
    b: int | None = None
    pc: int | None = None
    cat: int | None = None
    hwm: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    E = 137
    WIRE = {"g": "g", "hsn": "hsn", "b": "b", "pc": "pc", "cat": "cat", "hwm": "hwm"}


@dataclass(frozen=True)
class DeviceAnnouncement(WireMessage):
    """Received message."""

    gid: int
    hsn: str | None = None
    name: str | None = None
    cat: int | None = None
    parent: int | None = None
    time: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    E = None
    WIRE = {"gid": "gid", "hsn": "hsn", "name": "name", "cat": "cat", "parent": "parent", "time": "time"}


@dataclass(frozen=True)
class SwitchConfig(WireMessage):
    """Received message with e:138."""

    g: int | None = None
    b: int | None = None
    cm: int | None = None
    pc: int | None = None
    hwm: str | None = None
    swv: str | None = None
    hwv: str | None = None
    hsn: str | None = None
    cat: int | None = None
    pbmod: int | None = None
    pbmak: int | None = None
    pbb: int | None = None
    pbmask: int | None = None
    rv: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    E = 138
    WIRE = {"g": "g", "b": "b", "cm": "cm", "pc": "pc", "hwm": "hwm", "swv": "swv", "hwv": "hwv", "hsn": "hsn", "cat": "cat", "pbmod": "pbmod", "pbmak": "pbmak", "pbb": "pbb", "pbmask": "pbmask", "rv": "rv"}
