"""Make captured traffic safe to share: stable fakes for ids, blanked free text.

Used by tools/console.py for the capture file and for the screen.
"""
from __future__ import annotations

import re
from typing import Any


class Obfuscator:
    """Make a capture safe to share: stable fakes for ids, blanked free text.

    Within one run the same real value always gets the same fake, so the
    relationships between messages survive. The mapping is kept in memory only.
    """

    ID_KEYS = {"hsn": "HSN", "sys": "SYS"}
    FREE_TEXT = {"name", "addr1", "addr2", "zip", "phone", "note"}
    FREE_TEXT_PARENTS = {"sys_info", "org_info"}   # inside "meta"; dev names stay
    SUFFIX = re.compile(r"^(.+?)(_S\d+)$")        # socket hsn = PDM hsn + _S1.._S8
    MAC = re.compile(r"\b[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}\b")

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.fakes: dict[tuple[str, str], str] = {}   # real value -> fake

    def _fake(self, kind: str, real: str) -> str:
        key = (kind, real)
        if key not in self.fakes:
            n = sum(1 for k in self.fakes if k[0] == kind) + 1
            self.fakes[key] = f"{kind}{n:04d}" if kind != "MAC" else \
                f"02:00:00:00:{n >> 8 & 255:02x}:{n & 255:02x}"
        return self.fakes[key]

    def _id(self, kind: str, value: Any) -> str:
        real = str(value)
        m = self.SUFFIX.match(real)
        if m:
            return self._fake(kind, m.group(1)) + m.group(2)
        return self._fake(kind, real)

    def text(self, value: str) -> str:
        """Scrub free-form text: the prefix, known ids and MAC-shaped strings."""
        value = value.replace(self.prefix, "<prefix>")
        for (kind, real), fake in sorted(self.fakes.items(), key=lambda kv: -len(kv[0][1])):
            if kind != "MAC" and real:
                value = value.replace(real, fake)
        return self.MAC.sub(lambda m: self._fake("MAC", m.group(0).lower()), value)

    def _learn(self, node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k in self.ID_KEYS and not isinstance(v, (dict, list)):
                    self._id(self.ID_KEYS[k], v)
                else:
                    self._learn(v)
        elif isinstance(node, list):
            for v in node:
                self._learn(v)

    def _walk(self, node: Any, parent: str | None = None, in_meta: bool = False) -> Any:
        if isinstance(node, dict):
            result: dict[str, Any] = {}
            for k, v in node.items():
                if k in self.ID_KEYS and not isinstance(v, (dict, list)):
                    result[k] = self._id(self.ID_KEYS[k], v)
                elif (in_meta and parent in self.FREE_TEXT_PARENTS
                      and k in self.FREE_TEXT and v not in ("", None)):
                    result[k] = ""
                else:
                    result[k] = self._walk(v, k, in_meta or k == "meta")
            return result
        if isinstance(node, list):
            return [self._walk(v, parent, in_meta) for v in node]
        if isinstance(node, str):
            return self.text(node)
        return node

    def payload(self, node: Any) -> Any:
        if isinstance(node, str):
            return self.text(node)
        self._learn(node)
        return self._walk(node)
