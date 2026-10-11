# pylumencache

Unofficial Python library for [LumenCache](https://www.lumencache.com) ReNetA lighting, which is controlled over a hosted MQTT broker. It is the protocol layer behind the [ha-lumencache](https://github.com/vamsi765/ha-lumencache) Home Assistant integration and has no Home Assistant dependency.

> **Unofficial.** This is an independent, community project. It is not made, endorsed or supported by LumenCache.

> **Status: pre-alpha.** The protocol was worked out from captures, and the library covers it: typed messages and commands, an async client, a system model and a fake controller. The API may change before the first release, and the library is not on PyPI yet.

## Contents

| Path | What it is |
|---|---|
| `docs/asyncapi.yaml` | The protocol, as an AsyncAPI 3.0 description. The single source of truth for message codes and payloads |
| `docs/protocol.md` | Prose notes and open questions. Its code tables are generated from the YAML |
| `src/pylumencache/` | The library. `protocol/` has `codes.py` (the `Code` enum), `commands.py` (one builder per documented command, such as `zone_control(zone_id=250, brightness=50)`) and `models.py` (a dataclass per received message), all generated from the YAML, and `parser.py` (`parse(topic, payload)` returns a typed message, or an `UnknownMessage` for anything unrecognised) |
| `src/pylumencache/client.py` | Async MQTT client: connects over TLS, keeps the connection up, delivers parsed messages to listeners and publishes commands |
| `src/pylumencache/inventory.py` | `SystemModel`: the device tree from `dev/...` announcements, heartbeats, and the last known state of zones and lights (from switch events and echoed commands). Saves to and loads from JSON, because the system does not retain its inventory |
| `src/pylumencache/fake.py` | `FakeController`: a fake ReNetA system that replays a capture, for developing and testing without lights (pass `controller.factory` as the client's `client_factory`) |
| `src/pylumencache/obfuscate.py` | `Obfuscator`: replaces ids, serials, free text and MACs with stable fakes. Used by the capture tool for its files and by `watch.py` for the screen |
| `tools/watch.py` | Prints every parsed message, from a real system or, with `--replay FILE`, from a capture. Ids are replaced with fakes unless `--no-obfuscate` |
| `tools/gen_protocol.py` | Regenerates the tables in `protocol.md` and `codes.py`, `commands.py` and `models.py`; `--check` fails when either is stale |
| `tools/capture.py` | Records and sends MQTT traffic |

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python3 tools/gen_protocol.py --check
ruff check . && mypy && pytest   # what CI runs
```

## Using the client

```python
import asyncio
from pylumencache.client import LumenCacheClient
from pylumencache.protocol import commands

async def main():
    client = LumenCacheClient("<host>", "<Prefix Topic>", username="<user>", password="<pass>")
    client.add_listener(print)               # receives typed messages, such as ZoneEvent or PdmHeartbeat
    await client.start()                     # connects in the background and reconnects if it drops
    await client.wait_connected(30)
    await client.send(commands.zone_control(zone_id=250, brightness=50, fade=800))
    await asyncio.sleep(60)
    await client.stop()

asyncio.run(main())
```

Listeners can be plain functions or coroutines; one that raises does not affect the others. `tools/watch.py` does the same from the command line.

## Capturing the protocol

The protocol is documented from real traffic, in `docs/protocol.md`, with the message definitions in `docs/asyncapi.yaml` (an AsyncAPI description; the code tables in the markdown are generated from it by `tools/gen_protocol.py`). `tools/capture.py` records everything the system publishes (read-only by default) and can also send commands by hand. After a firmware or backend update, re-capture and refresh the spec and fixtures:

```bash
# one-time setup: create a virtual environment and install the dependency
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[capture]"

export LC_HOST=<host> LC_USER=<user> LC_PASS=<pass> LC_TOPIC_PREFIX='<Prefix Topic>'
python3 tools/capture.py --hail         # record for 2 minutes
python3 tools/capture.py --interactive  # type commands, see replies live
```

While it runs, press a wall switch and change a light from the PowerPlane display, so `status` and `events` messages appear in the capture.

**What it does.** It connects to the broker over TLS (MQTT 5, port 8883), subscribes to everything under your Prefix Topic (`<prefix>/#`), and writes every message to a new `capture.<date>_<time>.jsonl` file. By default it is read-only: the only thing it can send is one optional hail (`{"e":9,"g":0}`, which lists uncommissioned devices) to `<prefix>/cmd` when you pass `--hail`. With `--interactive` it also sends what you type (see below), so it can change your lights and settings.

**Options**

| Option | Meaning |
|---|---|
| `--host`, `--port`, `--user`, `--password` | Connection details. Defaults come from `LC_HOST`, `LC_PORT` (8883), `LC_USER`, `LC_PASS`; prefer the environment variables so the password stays out of shell history |
| `--topic-prefix P` | The Prefix Topic from your LumenCache connection details (env `LC_TOPIC_PREFIX`). Required. Quote it in the shell |
| `--topic T` | Subscribe to `T` (relative to the prefix) instead of `<prefix>/#`; repeat for several. `+` matches one level, `#` matches everything below |
| `-i`, `--interactive` | Type JSON commands to send to `<prefix>/cmd`; ends at `--duration` or when you quit |
| `--hail` | Send the one read-only hail described above |
| `--duration N` | Seconds to run, interactive mode included (default 120). `0` runs until you stop it (Ctrl-C, or `quit` in interactive mode) |
| `--name NAME` | Start of the output file name (default `capture`). The file is `NAME.YYYY.MM.DD_HH_MM_SS.jsonl`, using the local start time, so every run gets its own file, for example `capture.2026.10.10_08_11_00.jsonl` |
| `--no-obfuscate` | Keep real ids, serials and addresses in the capture. Obfuscation is on by default (see Output) |

**Interactive mode.** After it connects, type one JSON command per line and press Enter, for example `{"e":8,"g":2}`. Each line is published to `<prefix>/cmd` exactly as typed; lines that are not a JSON object are refused and nothing is sent. Messages from the system print as they arrive, each with a time, and are also written to the capture file. Because the script subscribes to the whole prefix, your own commands come back from the broker as `cmd` messages, which confirms they were published. Type `quit` or press Ctrl-C to exit. The only guard is on factory reset (`e:15` with `c:1`): it asks you to type `RESET` first. Everything else, including commands that persist settings, is sent as typed.

**Output.** Each run writes a new file named `capture.YYYY.MM.DD_HH_MM_SS.jsonl` (local start time; `--name` replaces `capture`), so earlier captures are never overwritten. It has one JSON object per message with the timestamp, direction (`recv` for messages from the broker, `sent` for commands this script published), topic, retained flag, and the payload (parsed as JSON when possible). Topics are written with the prefix removed, so the file does not contain your identifier and the protocol spec and fixtures do not depend on one system's prefix. Credentials are never written.

**Obfuscation** is on by default and applies to the file, not the screen. System ids and device serials (`sys`, `hsn`) are replaced with stable fakes (`SYS0001`, `HSN0001`; the same real value always gets the same fake, and a socket's `_S1` suffix is kept, so relationships between messages survive), the free-text fields in `meta` (name, address, zip, phone, note) are blanked, MAC-shaped strings are masked, and the Prefix Topic is replaced by `<prefix>` wherever it appears in text. Commands you send are obfuscated the same way, so a `sent` line for a command that uses a real `hsn` shows the fake. The mapping is kept in memory only, so fakes are consistent within one capture and not between captures. Pass `--no-obfuscate` to keep the real values (for example to debug against your own system). Obfuscation is best effort: still review a capture for personal details before sharing it.

**Troubleshooting**

- *A subscription is refused:* the script prints the broker's reason. Check that `--topic-prefix` matches your Prefix Topic exactly, or use `--topic` for a topic you know you may read.
- *Cannot connect:* check host, port, username and password.
- *No messages arrive:* trigger activity while it runs (press a switch), and check the prefix.

## License

Apache License 2.0. See [LICENSE](LICENSE).
