"""What a caller asks of a system, independent of any wire format."""
from __future__ import annotations

from dataclasses import dataclass

from .targets import Target


@dataclass(frozen=True)
class SetFixture:
    """Set a zone or a fixture. A brightness of 0 turns it off."""

    target: Target
    brightness: float   # percent, 0 to 100
    color_temperature: int | None = None   # kelvin
    fade: int | None = None   # ms


Command = SetFixture
