"""Message codes (the `e` field). Generated from docs/asyncapi.yaml by tools/gen_protocol.py; do not edit."""
from enum import IntEnum


class Code(IntEnum):
    """Values of the `e` field.

    Where the YAML has several messages for one code (a command and its reply),
    the member is named after the first.
    """

    PING = 8
    HAIL = 9
    CONFIG = 10
    HEARTBEAT_REQUEST = 11
    STATUS_PULL = 13
    REBOOT_OR_RESET = 15
    CARD_MODE = 18
    SET_GID = 32
    CURRENT_AND_DEFAULTS = 36
    ZONE_MANAGEMENT = 49
    ZONE_CONTROL = 56
    DIRECT_CONTROL = 57
    HAIL_REPLY = 137
    SWITCH_CONFIG = 138
    HEARTBEAT = 139
    ERROR_REPORT = 254
