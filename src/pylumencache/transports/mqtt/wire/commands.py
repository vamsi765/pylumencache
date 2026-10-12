"""Command builders. Generated from docs/asyncapi.yaml by tools/gen_protocol.py; do not edit.

Each function returns the JSON object to publish on the `cmd` topic. Arguments left as
None are left out of the message. Argument names follow the parameter names in
docs/protocol.md; the wire key is shown in each docstring.
"""
from __future__ import annotations

from typing import Any

from .codes import Code


def _check_range(name: str, value: float, low: float, high: float) -> None:
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}, got {value}")


def _message(code: Code, fields: dict[str, Any]) -> dict[str, Any]:
    """The message for `code` with the fields that were given, in order."""
    return {"e": code.value, **{wire: value for wire, value in fields.items() if value is not None}}


def ping(*, gid: int | None = None) -> dict[str, Any]:
    """Ping (e:8).

    Wire keys: gid -> g.
    """
    return _message(Code.PING, {"g": gid})


def hail(*, gid: int | None = None) -> dict[str, Any]:
    """Hail / GID lookup (e:9).

    Wire keys: gid -> g.
    """
    return _message(Code.HAIL, {"g": gid})


def config(*, gid: int | None = None) -> dict[str, Any]:
    """Config (e:10).

    Wire keys: gid -> g.
    """
    return _message(Code.CONFIG, {"g": gid})


def heartbeat_request(*, gid: int | None = None) -> dict[str, Any]:
    """Heartbeat request (e:11).

    Wire keys: gid -> g.
    """
    return _message(Code.HEARTBEAT_REQUEST, {"g": gid})


def status_pull(*, gid: int | None = None) -> dict[str, Any]:
    """Status pull (e:13).

    Wire keys: gid -> g.
    """
    return _message(Code.STATUS_PULL, {"g": gid})


def reboot_or_reset(*, gid: int | None = None, sub_code: int | None = None, store: int | None = None) -> dict[str, Any]:
    """Reboot / factory reset (e:15).

    Wire keys: gid -> g, sub_code -> c, store -> store.
    """
    return _message(Code.REBOOT_OR_RESET, {"g": gid, "c": sub_code, "store": store})


def card_mode(*, gid: int | None = None, card_mode: int | None = None) -> dict[str, Any]:
    """Card mode (e:18).

    Wire keys: gid -> g, card_mode -> cm.
    """
    return _message(Code.CARD_MODE, {"g": gid, "cm": card_mode})


def set_gid(*, gid: int | None = None, hsn: str | None = None, store: int | None = None) -> dict[str, Any]:
    """Set GID (e:32).

    Wire keys: gid -> gid, hsn -> hsn, store -> store.
    """
    return _message(Code.SET_GID, {"gid": gid, "hsn": hsn, "store": store})


def current_and_defaults(*, gid: int | None = None, drive_current: int | None = None, store: int | None = None) -> dict[str, Any]:
    """Current and defaults (e:36).

    Wire keys: gid -> g, drive_current -> ma, store -> store.
    """
    return _message(Code.CURRENT_AND_DEFAULTS, {"g": gid, "ma": drive_current, "store": store})


def zone_management(*, gid: int | None = None, action: int | None = None, zone_id: int | None = None, brightness: float | None = None, color_temperature: int | None = None, store: int | None = None) -> dict[str, Any]:
    """Zone management (e:49).

    Wire keys: gid -> g, action -> a, zone_id -> zid, brightness -> bri, color_temperature -> cct, store -> store.
    """
    if brightness is not None:
        _check_range("brightness", brightness, 0, 100)
    return _message(Code.ZONE_MANAGEMENT, {"g": gid, "a": action, "zid": zone_id, "bri": brightness, "cct": color_temperature, "store": store})


def zone_control(*, zone_id: int | None = None, brightness: float | None = None, color_temperature: int | None = None, fade: int | None = None) -> dict[str, Any]:
    """Zone control (e:56).

    Wire keys: zone_id -> z, brightness -> bri, color_temperature -> cct, fade -> fade.
    """
    if brightness is not None:
        _check_range("brightness", brightness, 0, 100)
    return _message(Code.ZONE_CONTROL, {"z": zone_id, "bri": brightness, "cct": color_temperature, "fade": fade})


def direct_control(*, gid: int | None = None, brightness: float | None = None, color_temperature: int | None = None, fade: int | None = None, zone_id: int | None = None) -> dict[str, Any]:
    """Direct control (e:57).

    Wire keys: gid -> g, brightness -> bri, color_temperature -> cct, fade -> fade, zone_id -> z.
    """
    if brightness is not None:
        _check_range("brightness", brightness, 0, 100)
    return _message(Code.DIRECT_CONTROL, {"g": gid, "bri": brightness, "cct": color_temperature, "fade": fade, "z": zone_id})
