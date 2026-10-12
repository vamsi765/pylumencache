"""What a command or a state change is about: a zone, or a single fixture.

A target is a value. Two targets are equal when they have the same kind and key, whatever
Python class describes them: `Light(14) == Fixture(14)`. So a command to `Fixture(14)` reaches
the state stored for `Light(14)`, and either works as a dictionary key.

`Fixture` is a base class to extend. A fixture is whatever is attached to the system and
switched or dimmed as one unit: a light, a fan, an outlet, a charger. A subclass states what
the fixture can do with class attributes, and the code that shows or controls it asks the
class rather than checking a model name.

Code that handles every target takes a `Target`, reads its `kind` and `key`, or dispatches on its
class. It never compares strings.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, eq=False)
class Target:
    """A zone or a fixture. Use `Zone`, `Fixture` or a subclass of `Fixture`, not this class."""

    key: int   # the zone number, or the fixture's GID
    kind: ClassVar[str]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Target):
            return NotImplemented
        return (self.kind, self.key) == (other.kind, other.key)

    def __hash__(self) -> int:
        return hash((self.kind, self.key))


class Zone(Target):
    """A group of fixtures that is switched together. Its members cannot be read from the system."""

    kind: ClassVar[str] = "zone"


class Fixture(Target):
    """A single device, addressed by the GID of its socket card. The base for every kind of fixture.

    The attributes say what the fixture can do. They are what is known from its type, not what
    the system reports, and a subclass changes only what differs.
    """

    kind: ClassVar[str] = "fixture"
    dimmable: ClassVar[bool] = True   # can be set to a level between off and full
    color_temperature: ClassVar[bool] = False   # has a tunable white range


class Light(Fixture):
    """A light of one color, dimmed by brightness."""


class TunableLight(Light):
    """A light with tunable white: brightness and color temperature."""

    color_temperature: ClassVar[bool] = True
