# ha-lumencache

Control a [LumenCache](https://www.lumencache.com) ReNetA lighting system entirely from Home Assistant, with no need to talk to MQTT yourself.

> **Unofficial.** This is an independent, community project. It is not made, endorsed or supported by LumenCache. "LumenCache" and "ReNetA" are names of their respective owners.

> **Status: planning / pre-alpha.** Nothing is released yet. This README describes what the project is being built to do; items marked *(planned)* do not exist yet. Follow the [roadmap](#roadmap) for progress.

## What it does

ha-lumencache sits between Home Assistant and your ReNetA system's MQTT broker. It translates Home Assistant actions into ReNetA commands, listens to the system's `status`, `meta` and `events` topics, and keeps an accurate live picture of every light, zone and switch.

Goals:

- **Complete wrapper.** Every ReNetA function is reachable from Home Assistant, including commissioning and configuration, so you rarely need the PowerPlane display or raw MQTT.
- **Built to last.** Typed protocol layer, tested against recorded real traffic, documented, and versioned.
- **Native feel.** Standard Home Assistant `light` entities that work with automations, scenes, groups, voice assistants and Adaptive Lighting.

## Features *(planned)*

- Fixtures and zones as `light` entities, with brightness, color temperature and fade.
- Brightness down to the system's 0.1% minimum through a precise service and the card.
- **Brightness × color-temperature card**: a 2D pad where one axis is color temperature and the other is brightness, chosen independently, with a fade input below.
- **Turn-on restores the last settings.** Each fixture keeps its current and last brightness, color temperature and fade. Turning a light on with no parameters restores the last values instead of jumping to 100%. The first-ever turn-on uses the highest brightness and highest color temperature.
- Zone control and zone membership management.
- Wall-switch (SW-D) events as Home Assistant `event` entities for use in automations.
- Diagnostics: connection status, faults, socket card / SIB mismatch reports, a diagnostics download with credentials removed, and Home Assistant repair issues.
- Commissioning tools as services: find uncommissioned devices, assign group IDs, set drive current, set socket card mode.
- A guarded **factory reset** in a "Danger zone" (see [Safety](#safety)).
- Several ReNetA systems at once. Each system is independent and is added separately; with only one system, no selector is shown anywhere.

## How it works

```
Home Assistant (e.g. in Docker)
 ├─ lumencache-card            Lovelace card (2D brightness × color pad)
 ├─ custom_components/lumencache   thin integration: config flow, entities, services
 └─ pylumencache               protocol library, no Home Assistant dependency
      │  MQTT over TLS (port 8883)
      ▼
ReNetA system → PDMs → SIBs / socket cards → fixtures
```

Design points:

- The integration uses its **own MQTT client** to the ReNetA broker. It does not use, and does not interfere with, Home Assistant's built-in MQTT integration.
- Entities are **created dynamically** from the system's `meta` data and keyed by hardware identity, so reassigning group IDs does not break entities.
- Each ReNetA system gets its own client and state; one system going offline does not affect another.
- The system's own memory of each light's previous settings is mirrored where it can be read. The integration keeps its own copy only as a fallback.

## Requirements

- Home Assistant (container, OS or supervised installs all work; the integration is a custom component and needs no add-on).
- A ReNetA system reachable from Home Assistant, with MQTT enabled.
- MQTT credentials for the system. LumenCache issues them on request.

## Installation *(planned)*

Through [HACS](https://hacs.xyz), as a custom repository at first:

1. In HACS, open the menu and choose **Custom repositories**.
2. Add `https://github.com/<owner>/ha-lumencache` with category **Integration**.
3. Install **LumenCache**, then restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → LumenCache**.

The card is served by the integration itself, so there is no separate card install.

## Configuration *(planned)*

Setup is done in the UI:

1. Enter the system's host, port (default `8883`), username, password and **Prefix Topic** (the value LumenCache gives you, a topic path such as `platform:na/.../<id>`), and choose the TLS option (certificate verification is on by default).
2. The integration connects, reads the system's device list and creates the entities.
3. Optionally, use the integration's options to rename fixtures, assign areas, set color temperature ranges, and set the default fade time.

To add another ReNetA system, repeat step 1. Each system keeps its own options.

## Entities *(planned)*

| What | Home Assistant entity |
|---|---|
| Fixture or socket card | `light` (brightness, and color temperature for CCT fixtures) |
| Zone | `light` (derived group state) |
| Wall switch (SW-D) | `event` (click, multi-click, long press) |
| System connection | `binary_sensor` (connectivity) |
| Port, SIB and fault status | diagnostic `sensor` / `binary_sensor` |
| Reboot | `button` |

## Services *(planned)*

| Service | Purpose |
|---|---|
| `lumencache.set_light` | Precise brightness (0.1% steps), color temperature and fade, for lights or zones |
| `lumencache.add_to_zone`, `remove_from_zone`, `list_device_zones` | Zone membership: add (with optional zone defaults), remove, and list a device's zones |
| `lumencache.hail` | Look up what is at a GID (the default, GID 0, lists devices not yet commissioned) |
| `lumencache.query_device` | Ask a device to ping, send its heartbeat, report its status, or dump its configuration |
| `lumencache.assign_gid` | Commission a device (optionally persist) |
| `lumencache.set_drive_current` | Set drive current and defaults (optionally persist) |
| `lumencache.set_socket_mode` | Change a socket card's operating mode |
| `lumencache.reboot` | Reboot a device (by GID) |
| `lumencache.factory_reset` | Factory reset a device (by GID), behind safeguards |
| `lumencache.send_raw` | Send any ReNetA command, as a fallback |

System-level services take an optional `system` field. With one system it is filled in automatically; with several it is required.

The standard `light.turn_on` / `light.turn_off` services also work, so voice assistants and existing automations behave normally.

## The brightness × color card *(planned)*

```yaml
type: custom:lumencache-card
entity: light.living_room
send_mode: live              # live (throttled) or on_release
brightness_curve: perceptual # perceptual (log) or linear
show_fade: true
fade_presets: [0, 1, 3, 10]
```

- X axis: color temperature, warm to cool, limited to the fixture's own range.
- Y axis: brightness. The perceptual curve makes the 0.1% to 5% range usable.
- Below the pad: a fade time in seconds, with preset chips.
- Use `entities:` to control several lights at once, including lights from different systems.
- Works for fixtures and zones, follows external changes (wall switches, other clients), and has a visual editor.

## Multiple systems

Each fixture and zone belongs to exactly one ReNetA system, and systems are fully independent. To control lights from two systems together, combine their entities in Home Assistant with light groups, scenes, automations, or the card with several entities. The integration does not span systems.

## Safety

- Commands that persist to the system (`store`) are **off by default** and must be requested explicitly.
- **Factory reset** is available but deliberately hard to reach: the service is admin-only and needs a confirm flag plus the exact device (its GID and name), because the command acts on one device; its button entity is in the configuration category and disabled by default; and the card's device panel shows it in a collapsed "Danger zone" with a red button and a typed-name confirmation.
- Credentials are stored only in the Home Assistant config entry, never in logs or diagnostics.
- TLS verification is on by default.

## Development

### Repository layout *(planned)*

```
ha-lumencache/
├─ packages/pylumencache/     protocol library, CLI, tests
├─ custom_components/lumencache/   Home Assistant integration (and bundled card)
├─ card/                      Lovelace card source (TypeScript + Lit)
├─ tools/fake_controller/     fake ReNetA system that replays recorded traffic
├─ fixtures/                  captured real payloads (redacted)
├─ docs/                      protocol, architecture, user guide, troubleshooting
└─ .devcontainer/, .github/workflows/
```

### Principles

- Every command and incoming message is a typed model; unknown fields and messages are preserved, never fatal.
- Protocol quirks live in one folder, so a firmware change touches one place.
- `mypy --strict`, `ruff`, `pytest`, `hassfest` and HACS validation run in CI.
- Tests use recorded real traffic and a fake controller, so most development never touches live lights. Live tests on real hardware follow a safety checklist (one known-good fixture; no factory reset).
- The card has unit tests for its coordinate math plus a small Playwright suite against a mocked `hass` object.

### Capturing the protocol

The protocol is documented from real traffic, in `docs/protocol.md`, with the message definitions in `docs/asyncapi.yaml` (an AsyncAPI description; the code tables in the markdown are generated from it by `tools/gen_protocol.py`). The library's CLI includes a capture command (`lumencache capture`, *planned*) that records everything the system publishes, read-only by default, and a diff command that compares a new capture with the stored fixtures. After a firmware or backend update, re-capture, diff, and refresh the spec and fixtures.

Until the CLI exists, `tools/lumencache_capture.py` does the same job, and can also send commands by hand:

```bash
# one-time setup: create a virtual environment and install the dependency
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install paho-mqtt

export LC_HOST=<host> LC_USER=<user> LC_PASS=<pass> LC_TOPIC_PREFIX='<Prefix Topic>'
python3 tools/lumencache_capture.py --hail         # record for 2 minutes
python3 tools/lumencache_capture.py --interactive  # type commands, see replies live
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

## Roadmap

1. **Discovery**: protocol captured and written up.
2. **Library core**: typed models, async client, CLI with capture and diff, tests.
3. **Dev environment**: fake controller and devcontainer.
4. **Integration MVP**: config flow, lights with brightness, color temperature and fade, last-value restore.
5. **Card v1**: the 2D pad and fade input.
6. **Zones and events**: zone lights, membership services, switch events.
7. **Commissioning and configuration services**, including guarded factory reset.
8. **Diagnostics and repairs.**
9. **Hardening and first release** (HACS).

## Contributing

Issues and pull requests are welcome once the project leaves the planning stage. Please keep changes typed and tested, and do not include credentials, MAC addresses or other identifying data in fixtures or issue reports.

## License

Apache License 2.0. See [LICENSE](LICENSE).
