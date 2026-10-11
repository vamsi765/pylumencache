"""Command builders. Generated from docs/asyncapi.yaml by tools/gen_protocol.py; do not edit.

Each function returns the JSON object to publish on the `cmd` topic. Arguments left as
None are left out of the message. Argument names follow the parameter names in
docs/protocol.md; the wire key is shown in each docstring.
"""
from __future__ import annotations

from .codes import Code


def _check_range(name: str, value, low, high) -> None:
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}, got {value}")


def ping(*, gid: int | None = None) -> dict:
    """Ping (e:8).

    Wire keys: gid -> g.
    """
    msg: dict = {"e": Code.PING.value}
    if gid is not None:
        msg["g"] = gid
    return msg


def hail(*, gid: int | None = None) -> dict:
    """Hail / GID lookup (e:9).

    Wire keys: gid -> g.
    """
    msg: dict = {"e": Code.HAIL.value}
    if gid is not None:
        msg["g"] = gid
    return msg


def config(*, gid: int | None = None) -> dict:
    """Config (e:10).

    Wire keys: gid -> g.
    """
    msg: dict = {"e": Code.CONFIG.value}
    if gid is not None:
        msg["g"] = gid
    return msg


def heartbeat_request(*, gid: int | None = None) -> dict:
    """Heartbeat request (e:11).

    Wire keys: gid -> g.
    """
    msg: dict = {"e": Code.HEARTBEAT_REQUEST.value}
    if gid is not None:
        msg["g"] = gid
    return msg


def status_pull(*, gid: int | None = None) -> dict:
    """Status pull (e:13).

    Wire keys: gid -> g.
    """
    msg: dict = {"e": Code.STATUS_PULL.value}
    if gid is not None:
        msg["g"] = gid
    return msg


def reboot_or_reset(*, gid: int | None = None, sub_code: int | None = None, store: int | None = None) -> dict:
    """Reboot / factory reset (e:15).

    Wire keys: gid -> g, sub_code -> c, store -> store.
    """
    msg: dict = {"e": Code.REBOOT_OR_RESET.value}
    if gid is not None:
        msg["g"] = gid
    if sub_code is not None:
        msg["c"] = sub_code
    if store is not None:
        msg["store"] = store
    return msg


def card_mode(*, gid: int | None = None, card_mode: int | None = None) -> dict:
    """Card mode (e:18).

    Wire keys: gid -> g, card_mode -> cm.
    """
    msg: dict = {"e": Code.CARD_MODE.value}
    if gid is not None:
        msg["g"] = gid
    if card_mode is not None:
        msg["cm"] = card_mode
    return msg


def set_gid(*, gid: int | None = None, hsn: str | None = None, store: int | None = None) -> dict:
    """Set GID (e:32).

    Wire keys: gid -> gid, hsn -> hsn, store -> store.
    """
    msg: dict = {"e": Code.SET_GID.value}
    if gid is not None:
        msg["gid"] = gid
    if hsn is not None:
        msg["hsn"] = hsn
    if store is not None:
        msg["store"] = store
    return msg


def current_and_defaults(*, gid: int | None = None, drive_current: int | None = None, store: int | None = None) -> dict:
    """Current and defaults (e:36).

    Wire keys: gid -> g, drive_current -> ma, store -> store.
    """
    msg: dict = {"e": Code.CURRENT_AND_DEFAULTS.value}
    if gid is not None:
        msg["g"] = gid
    if drive_current is not None:
        msg["ma"] = drive_current
    if store is not None:
        msg["store"] = store
    return msg


def zone_management(*, gid: int | None = None, action: int | None = None, zone_id: int | None = None, brightness: float | None = None, color_temperature: int | None = None, store: int | None = None) -> dict:
    """Zone management (e:49).

    Wire keys: gid -> g, action -> a, zone_id -> zid, brightness -> bri, color_temperature -> cct, store -> store.
    """
    if brightness is not None:
        _check_range("brightness", brightness, 0, 100)
    msg: dict = {"e": Code.ZONE_MANAGEMENT.value}
    if gid is not None:
        msg["g"] = gid
    if action is not None:
        msg["a"] = action
    if zone_id is not None:
        msg["zid"] = zone_id
    if brightness is not None:
        msg["bri"] = brightness
    if color_temperature is not None:
        msg["cct"] = color_temperature
    if store is not None:
        msg["store"] = store
    return msg


def zone_control(*, zone_id: int | None = None, brightness: float | None = None, color_temperature: int | None = None, fade: int | None = None) -> dict:
    """Zone control (e:56).

    Wire keys: zone_id -> z, brightness -> bri, color_temperature -> cct, fade -> fade.
    """
    if brightness is not None:
        _check_range("brightness", brightness, 0, 100)
    msg: dict = {"e": Code.ZONE_CONTROL.value}
    if zone_id is not None:
        msg["z"] = zone_id
    if brightness is not None:
        msg["bri"] = brightness
    if color_temperature is not None:
        msg["cct"] = color_temperature
    if fade is not None:
        msg["fade"] = fade
    return msg


def direct_control(*, gid: int | None = None, brightness: float | None = None, color_temperature: int | None = None, fade: int | None = None, zone_id: int | None = None) -> dict:
    """Direct control (e:57).

    Wire keys: gid -> g, brightness -> bri, color_temperature -> cct, fade -> fade, zone_id -> z.
    """
    if brightness is not None:
        _check_range("brightness", brightness, 0, 100)
    msg: dict = {"e": Code.DIRECT_CONTROL.value}
    if gid is not None:
        msg["g"] = gid
    if brightness is not None:
        msg["bri"] = brightness
    if color_temperature is not None:
        msg["cct"] = color_temperature
    if fade is not None:
        msg["fade"] = fade
    if zone_id is not None:
        msg["z"] = zone_id
    return msg
