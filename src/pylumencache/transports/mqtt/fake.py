"""A fake ReNetA system for development and tests: replays recorded traffic.

FakeController stands in for the broker connection of MqttTransport, so the whole
stack (client, parser, model, and an integration on top) can run without a system or
a network, and without touching real lights::

    controller = FakeController.from_file("capture.jsonl", prefix)
    transport = MqttTransport("fake", prefix, client_factory=controller.factory)

It replays the recorded inventory and status messages when the client subscribes. A
command published to `cmd` is echoed back followed by an empty reply, as the real system
does, and a few commands get a recorded answer if there is one (see _answer). Zone and light
commands change nothing beyond the echo, which is what the real system's traffic shows too.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .wire.codes import Code


class FakeController:
    """Plays the part of aiomqtt.Client for one connection. Make a new one per connection (see factory)."""

    def __init__(self, records: Iterable[dict[str, Any]], prefix: str) -> None:
        self.prefix = prefix.rstrip("/")
        self._records = [r for r in records if r.get("dir", "recv") == "recv" and r["topic"] != "cmd"]
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._tasks: list[asyncio.Task[None]] = []
        self.published: list[tuple[str, str]] = []   # what the client sent: (topic, payload)

    @classmethod
    def from_file(cls, path: str | Path, prefix: str) -> FakeController:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        return cls((json.loads(line) for line in lines if line.strip()), prefix)

    def factory(self) -> FakeController:
        """For MqttTransport(client_factory=...): a new connection that replays the same records."""
        return FakeController(self._records, self.prefix)

    # --- what MqttTransport uses of aiomqtt.Client ------------------------------

    async def __aenter__(self) -> FakeController:
        return self

    async def __aexit__(self, *exc: object) -> None:
        for task in self._tasks:
            task.cancel()

    async def subscribe(self, topic: str) -> None:
        self._tasks.append(asyncio.create_task(self._replay()))

    async def publish(self, topic: str, payload: str) -> None:
        self.published.append((topic, payload))
        if topic != f"{self.prefix}/cmd":
            return
        self._emit("cmd", payload)
        self._emit("cmd", "")
        try:
            command = json.loads(payload)
        except ValueError:
            return
        if isinstance(command, dict):
            for record in self._answer(command):
                self._emit(record["topic"], record["payload"])

    @property
    def messages(self) -> Any:
        async def deliver() -> Any:
            while True:
                yield await self._queue.get()
        return deliver()

    # --- internals ------------------------------------------------------------------

    def _emit(self, topic: str, payload: Any) -> None:
        text = payload if isinstance(payload, str) else json.dumps(payload, separators=(",", ":"))
        self._queue.put_nowait(SimpleNamespace(topic=f"{self.prefix}/{topic}", payload=text.encode()))

    async def _replay(self) -> None:
        for record in self._startup():
            self._emit(record["topic"], record["payload"])
            await asyncio.sleep(0)

    def _startup(self) -> Iterator[dict[str, Any]]:
        """Inventory first (meta and dev/...), then status messages, as the real system does after a boot."""
        inventory = [r for r in self._records if r["topic"] == "meta" or r["topic"].startswith("dev/")]
        inventory = [r for r in inventory if not self._is_reply(r)]
        yield from inventory
        yield from (r for r in self._records if r["topic"] == "status")

    @staticmethod
    def _is_reply(record: dict[str, Any]) -> bool:
        payload = record["payload"]
        return isinstance(payload, dict) and payload.get("e") in (Code.HAIL_REPLY, Code.SWITCH_CONFIG)

    def _answer(self, command: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """Recorded replies to the commands that have one."""
        code, gid = command.get("e"), command.get("g")
        if code == Code.HAIL:
            yield from (r for r in self._records if self._is_reply(r) and r["payload"]["e"] == Code.HAIL_REPLY)
        elif code == Code.CONFIG:
            yield from (r for r in self._records if self._is_reply(r)
                        and r["payload"]["e"] == Code.SWITCH_CONFIG and r["payload"].get("g") == gid)
        elif code == Code.HEARTBEAT_REQUEST:
            yield from (r for r in self._records if r["topic"] == "status"
                        and isinstance(r["payload"], dict) and r["payload"].get("e") == Code.HEARTBEAT
                        and r["payload"].get("g") == gid)
        elif code == Code.REBOOT_OR_RESET and command.get("c") == 0:
            pass   # the real system showed no reaction to e:15 c:0 (see docs/protocol.md, P-20)


FakeFactory = Callable[[], FakeController]
