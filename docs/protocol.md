# ReNetA MQTT protocol (observed)

> **Version 0.1.0.** Written from several captures of one system plus the command codes in LumenCache's "Commands List" article. It is not an official specification. Anything marked 🔬 is unknown or an inference and must be confirmed (from a new capture or from LumenCache) before code depends on it. Identifiers are shown as placeholders such as `<hsn>`.

## 1. Connection

| Item | Observed |
|---|---|
| Broker | Hosted EMQX service, public hostname |
| Transport | MQTT over TLS, port 8883, valid certificate (verification on) |
| Authentication | Username and password issued by LumenCache |
| MQTT version | MQTT 5 works (the capture tool uses it) |
| Access scope | Read and write under the issued Prefix Topic. Subscribing to `<prefix>/#` is allowed. 🔬 Behavior outside the prefix is untested (expected: refused) |
| Client IDs | Must be unique per client. EMQX disconnects an existing client that uses the same ID |
| Echo | A client that is subscribed to a topic receives its own publishes back. Every command sent from the capture tool came back on `cmd` about 0.1 s later |
| Other clients | A message published by a second client (MQTT Explorer) was received by the first, so several clients can connect. 🔬 Client and rate limits unknown |

## 2. Topic layout

Every topic sits under the **Prefix Topic** (`<prefix>`), a path of the form `platform:na/<state>/<id>`. 🔬 The `<state>` segment currently reads `unprovisioned`; whether it changes after provisioning is unknown. All topics below are relative to the prefix.

| Topic | Direction | Content |
|---|---|---|
| `cmd` | client to system | Commands (JSON). Sent so far: `e:8`, `e:9`, `e:10`, `e:11`, `e:13`, `e:49`, `e:56` and `e:57`. Also carries the broker echo and an empty message, see below |
| `status` | system to client | Heartbeats, zone events, error reports |
| `errors` | system to client | Error reports (same payload as on `status`) |
| `meta` | system to client | System information, and the reply to a hail (`e:137`, section 5.4) |
| `dev/...` | system to client | One message per device (inventory) |

LumenCache's mobile setup tutorial lists `status`, `meta`, `events` and `cmd`. `events` did not appear in any capture (🔬 it may only carry events), and `errors` is not in the tutorial. The tutorial says the prefix must end with `/` in the mobile app; the integration joins prefix and topic with exactly one `/` either way. The tutorial describes `meta` as listing devices, but the capture shows devices under `dev/...`; what was observed is used here.

**Retention.** No message in any capture was retained, the inventory included. A client that connects after the system has published cannot learn the inventory by subscribing alone.

**What appears on `cmd` after a command.** Every command produced the same two messages, whatever the command or GID:

1. The command itself, echoed back by the broker, about 0.1 s later.
2. A message with an empty payload, 0.14 to 0.4 s after the echo.

This also happened for GID 54 and GID 0, which are not devices on this system, so the empty message is not a success acknowledgement. 🔬 What publishes it (the system, or the broker) and what it means are unknown. No error code or other reply has been seen for any command.

## 3. Message conventions

- Payloads are JSON objects.
- `e` is a numeric event or command code. `g` is a group/device ID (GID) or an address.
- The same code can appear as a command and as a status echo (see `e:56`).

Codes seen in the captures:

<!-- BEGIN GENERATED codes-seen: edit docs/asyncapi.yaml, then run tools/gen_protocol.py -->
| `e` | Seen as | Meaning |
|---|---|---|
| 8 | command on `cmd` | Only the echo and the empty message followed (section 6) |
| 9 | command on `cmd` | Hail: `{"e":9,"g":0}` lists devices still at GID 0. It answered once, as `e:137` on `meta` (section 5.4). `e:9` with a GID (54, 14) got no reply |
| 10 | command on `cmd` | Only the echo and the empty message followed (section 6) |
| 11 | command on `cmd` | Only the echo and the empty message followed (section 6) |
| 13 | command on `cmd` | Only the echo and the empty message followed (section 6) |
| 49 | command on `cmd` | `{"e":49,"g":2,"a":9}` (list zones) got no reply |
| 56 | status; command on `cmd` | Zone on/off/brightness/color event. Sent as a command to zone 250: no reply |
| 57 | command on `cmd` | Direct control. Sent to GIDs 100, 14, 10 and 0. To GID 100 the lights followed the command (confirmed by eye); the effect for the other GIDs is not reported. No state message or error was published |
| 137 | meta | Reply to a hail: a device at GID 0 (section 5.4) |
| 139 | status | Periodic heartbeat from the PowerPlane, the PDM and the controller (section 5.1) |
| 254 | status and `errors` | Error report. Seen once, shortly after a restart |
<!-- END GENERATED codes-seen -->

### Documented commands

From LumenCache's Commands List. All are JSON published on `cmd`. The examples use GID 54 or zone 200 from that document. Note that parameter names differ between commands (`g` or `gid`, `z` or `zid`), so each command is built with exactly the names shown.

<!-- BEGIN GENERATED documented-commands: edit docs/asyncapi.yaml, then run tools/gen_protocol.py -->
| `e` | Command | Documented example | Notes |
|---|---|---|---|
| 8 | Ping | `{"e":8,"g":54}` | "Are you there" check for a GID |
| 9 | Hail / GID lookup | `{"e":9,"g":54}` | Returns what device sits at that GID. With `g:0`, lists devices still at GID 0 by `hsn` |
| 10 | Config | `{"e":10,"g":54}` | Dumps the device's current configuration. 🔬 Reply format |
| 11 | Heartbeat request | `{"e":11,"g":54}` | Checks the device is still checking in |
| 13 | Status pull | `{"e":13,"g":54}` | Forces the device to report status now, instead of waiting for the automatic push on `status` |
| 15 | Reboot / factory reset | `{"e":15,"g":54,"c":0}` reboot; `{"e":15,"g":54,"c":1,"store":1}` factory reset | `c` is the sub-code. Destructive |
| 18 | Card mode | `{"e":18,"g":54,"cm":3}` | Sets a socket card's operating mode. 🔬 Mode values |
| 32 | Set GID | `{"e":32,"gid":60,"hsn":"<hsn>","store":1}` | Gives that `hsn` the address 60 |
| 36 | Current and defaults | `{"e":36,"g":54,"ma":700,"store":1}` | Sets drive current in mA. The text also mentions stored warm, cool, brightness and CCT defaults. 🔬 Their field names |
| 49 | Zone management | `{"e":49,"g":54,"a":5,"zid":200,"bri":75,"cct":3000,"store":1}` | `a` is the action: 5 add (with optional zone defaults `bri` and `cct`), 6 delete, 9 list zones (example `{"e":49,"g":54,"a":9}`). The text also mentions "inspect". 🔬 Other actions, and how to list the members of a zone |
| 56 | Zone control | `{"e":56,"z":200,"bri":50,"cct":4000,"fade":800}` | Whole zone at once. The tutorial's sliders send `{"e":56,"z":<zone>,"bri":<0-100>}`, and `bri` 0 turns the zone off |
| 57 | Direct control | `{"e":57,"g":54,"bri":100,"cct":3000,"fade":1000}` | One socket card |
<!-- END GENERATED documented-commands -->

### Parameters

<!-- BEGIN GENERATED parameters: edit docs/asyncapi.yaml, then run tools/gen_protocol.py -->
| Name | Meaning |
|---|---|
| `g` / `gid` | Device address (GID). Set with `e:32` |
| `z` / `zid` | Zone ID. Membership is set with `e:49` |
| `hsn` | Permanent per-device serial, used before the device has a GID |
| `bri` | Brightness, 0 to 100. A decimal (12.5) sent to GID 100 was accepted and the light dimmed from 50 (confirmed by eye); whether the 0.1% steps the plan wants are honored cannot be told by eye. 🔬 Out-of-range values (500 was sent) are unconfirmed |
| `cct` | Color temperature in kelvin |
| `fade` | Transition time in milliseconds |
| `ma` | Drive current in milliamps |
| `store` | 1 saves the setting through a reboot; without it the setting reverts |
| `a` | Action code inside a multi-purpose command (`e:49`) |
| `c` | Sub-code (`e:15`: 0 reboot, 1 factory reset) |
| `cm` | Socket card mode (`e:18`) |
<!-- END GENERATED parameters -->

## 4. Inventory

The system publishes its inventory once, shortly after it connects to the broker. After a restart or reboot it takes 1.3 to 1.7 s from the `meta` message to the last `dev/...` message: `meta` comes about 11 s after boot, then 15 devices (GIDs 1 to 15) follow, with no duplicates after the latest reboot. A restart or reboot is the only trigger seen so far. 🔬 Whether any command makes the system publish it again is unknown, and this is the most important open question for the integration (section 9).

### 4.1 `meta`

```json
{
  "sys": "<sys>",
  "meta": {
    "plt": "",
    "cat": 0,
    "sys_info": { "sys": "<sys>", "name": "", "addr1": "", "addr2": "", "zip": "", "phone": "", "note": "", "cat": 2 },
    "org_info": { "org": 65535, "name": "", "cat": 1 }
  }
}
```

- `sys` is the system ID, a likely unique ID for the system. 🔬 Confirm it never changes.
- The name and address fields were empty on this system. Treat them as personal data when they are filled in.
- 🔬 Meaning of `plt`, `cat` (0, 2, 1) and `org` (65535).

### 4.2 `dev/...` topics

The topic path mirrors the wiring. Each path segment is `<type>:<gid>`; split on `/`, then on `:`.

| Type | Device | `cat` | Example topic |
|---|---|---|---|
| `pp` | PowerPlane | 32 | `dev/pp:1` |
| `pdm` | PDM (distribution module) | 35 | `dev/pp:1/pdm:2` |
| `skt` | Socket (PDM port) | 36 | `dev/pp:1/pdm:2/skt:4` |
| `scard` | Socket card | 37 | `dev/pp:1/pdm:2/skt:4/scard:14` |
| `sw` | Wall switch (SW-D) | 40 | `dev/sw:12` |

Payload:

```json
{ "gid": 14, "hsn": "<hsn>", "name": "SC-CC2-50W", "cat": 37, "parent": 4, "time": 1505366 }
```

| Field | Meaning |
|---|---|
| `gid` | Device ID. Unique across the system (1 to 15) |
| `hsn` | Hardware serial number. Stable, so suited as the permanent device ID. Sockets use the PDM's serial plus a suffix (`_S1` to `_S8`) |
| `name` | Product or default name (`Reneta PP`, `PDM_RJ`, `Socket_1`, `SC-CC2-50W`, `SC-PV2-50W`, `SW-D`) |
| `cat` | Device category, see the table above |
| `parent` | GID of the parent device. The PowerPlane has 65535 (no parent) |
| `time` | 🔬 Unknown. It is not a clock: socket card 14 keeps the same value (1505366) across restarts |

Observations from this system:

- The PowerPlane (gid 1) has one PDM (gid 2), which has sockets gid 3 to 10 (eight ports). Socket cards gid 14 (SC-CC2) and gid 15 (SC-PV2) sit under sockets gid 4 and gid 6.
- One socket card (gid 11, SC-CC2) and both switches (gid 12 and 13) have `parent` 0 and appear at the top level of `dev/`. 🔬 Why is unknown (possibly not yet assigned to a parent).
- The PowerPlane's `dev/pp:1` message has no `hsn`, although its heartbeat does (section 5.1). The PowerPlane therefore cannot be matched to its serial from the inventory alone.
- Socket gid 5 was announced twice with identical payloads. Consumers must upsert by `gid` (or `hsn`), not append.
- 🔬 The device list does not show which fixtures belong to which zone, nor which socket cards are CCT-capable.

## 5. Status messages

### 5.1 Heartbeat: `e:139`

Three sources send `e:139` on `status`, and each has its own shape and rhythm:

| `g` | Source | Interval | Fields |
|---|---|---|---|
| 1 | PowerPlane | 5 min. After a boot the first one arrives 300 s later | `e g hsn swv hwv time heap` |
| 2 | PDM | 60 s | `e g bay hsn swv hwv time heap temp rh` |
| 100 | Controller. 🔬 Inferred; GID 100 is not in the inventory | Not periodic: after a boot, and in the minutes after a light command. Gaps widen (15, 20, 20, 25, 30 s). None in 7 minutes of idle and query commands | `e g opc mode 12v term heap txrx uptime temp` |

PDM example:

```json
{ "e": 139, "g": 2, "bay": 3, "hsn": "<hsn>", "swv": "01.00.12m", "hwv": "02.05", "time": 60182, "heap": 8480948, "temp": 31.5, "rh": 35.71 }
```

PowerPlane example:

```json
{ "e": 139, "g": 1, "hsn": "<hsn>", "swv": "01.00.02", "hwv": "01.00", "time": 300737, "heap": 6181804 }
```

Controller example:

```json
{ "e": 139, "g": 100, "opc": 2, "mode": 3, "12v": 1, "term": 1, "heap": 13416, "txrx": [165, 0, 278, 165], "uptime": 75, "temp": 30.6 }
```

| Field | Meaning |
|---|---|
| `g` | GID of the reporting PowerPlane or PDM; 100 for the controller |
| `hsn` | Serial of the reporting device |
| `bay` | 🔬 Unknown (3 in every PDM heartbeat) |
| `swv`, `hwv` | Software and hardware version. PDM: 01.00.12m and 02.05. PowerPlane: 01.00.02 and 01.00 |
| `time` | Uptime in milliseconds (PowerPlane and PDM). Confirmed: the PDM value matched the real time since the reboot to within 15 s after 8.5 hours |
| `uptime` | Uptime in seconds (controller). Confirmed: 75 at 81 s after the boot time that the other heartbeats imply |
| `heap` | Free memory (bytes). 🔬 Unit inferred |
| `temp`, `rh` | Temperature (°C) and relative humidity (%). 🔬 Units inferred |
| `opc`, `mode`, `12v`, `term` | 🔬 Unknown (2, 3, 1 and 1 in every controller heartbeat) |
| `txrx` | 🔬 Unknown. Four counters; the first and fourth were always equal, and they were non-zero right after commands and zero when idle, so they may count traffic since the last heartbeat |

The heartbeats are liveness signals: if one stops, the system or that device is probably gone. The controller sends nothing when idle, so it cannot be used as a liveness signal; the PDM's 60 s is the steadier one.

🔬 In one capture the PowerPlane's `time` was 4 h 30 min while the PDM's was 8 h 33 min, so the PowerPlane restarted about 4 h after the system reboot. Nobody power-cycled it, so it restarted by itself. 🔬 Cause unknown (a watchdog or crash reset is possible); the PDM did not restart.

### 5.2 Zone event: `e:56`

```json
{ "e": 56, "z": 250, "on": 0, "dev": 12, "g": 65534 }
{ "e": 56, "z": 250, "on": 1, "bri": 100, "cct": 5000, "dev": 12, "g": 65534 }
```

| Field | Meaning |
|---|---|
| `z` | Zone ID (250) |
| `on` | 0 off, 1 on |
| `bri`, `cct` | Present when turning on. `bri` is 0 to 100 (percent) and `cct` is in kelvin, as documented by LumenCache |
| `dev` | GID of the device that caused the event. 12 is a SW-D switch, so presses show up here. 🔬 Inferred |
| `g` | 65534 in all three messages. 🔬 Unknown (possibly a broadcast or zone address) |

Three presses of switch 12 gave off, on (6 s later), off (14 s after that).

After a reboot, five events from switch 12 followed the same pattern (off, on, off, on, off). Both "on" events carried `bri` 100 and `cct` 5000. The last command sent by hand before them was `e:57` with `cct` 5000 and `bri` 0. That is consistent with the system remembering the last color temperature but not a brightness of 0. 🔬 Confirm with a test that changes `cct` to another value first.

🔬 No per-fixture state message was seen. Changes appear at zone level only.

### 5.3 Error report: `e:254`

```json
{ "e": 254, "g": 100, "err": 38, "v": 254 }
```

Published on `status` and on `errors` (identical), about a second after the inventory. 🔬 `g` 100 is not a GID in the inventory. The meaning of error 38 and the full error code list are unknown.

### 5.4 Uncommissioned device: `e:137`

The reply to a hail (`{"e":9,"g":0}`), published on `meta` about 0.6 s after the echo:

```json
{ "e": 137, "g": 0, "hsn": "<hsn>", "b": 0, "pc": 2, "cat": 37, "hwm": "90003-200__SC-PV2-50W" }
```

| Field | Meaning |
|---|---|
| `g` | 0: the device has no GID yet |
| `hsn` | Serial of the device |
| `cat` | 37, the socket card category (section 4.2) |
| `hwm` | Hardware model: part number and name |
| `b`, `pc` | 🔬 Unknown (0 and 2) |

One device answered. 🔬 It is not in the inventory under a GID of its own. The system has two SC-PV2-50W cards (GID 15 is one), so whether this is a third, unassigned one is unconfirmed.

## 6. Commands tried

Commands sent from the capture tool in interactive mode. All of them got the echo and the empty `cmd` message described in section 2. The table lists anything beyond that.

<!-- BEGIN GENERATED commands-tried: edit docs/asyncapi.yaml, then run tools/gen_protocol.py -->
| Command | Sent | Result |
|---|---|---|
| `e:8` | `g` 54, 2 and 14 | No reply |
| `e:9` | `g` 0 (hail) | One reply: `e:137` on `meta` (section 5.4). An earlier hail got no reply |
| `e:9` | `g` 54, twice; `g` 14 | No reply |
| `e:10` | `g` 54, 2 and 14 | No reply |
| `e:11` | `g` 54, 2 and 1 | No reply, and no extra heartbeat |
| `e:13` | `g` 54, 2 and 14 | No reply, and no extra status |
| `e:49` | `g` 2, `a` 9 (list zones) | No reply |
| `e:56` | `z` 250, `bri` 50, `cct` 4000, `fade` 800 | No reply and no `e:56` status event. 🔬 Effect on the lights not reported |
| `e:57` | `g` 100, 14, 10 and 0; `bri` 0, 10, 12.5, 50, 100 and 500; `cct` 2700 to 5000; `fade` 800 and 1000 | To GID 100 the lights changed to the commanded brightness (confirmed by eye), and 12.5 after 50 dimmed them. 🔬 Effect for GIDs 14, 10 and 0 not reported. No state message, no error |
<!-- END GENERATED commands-tried -->

So of the query commands only the hail answers. None of the others republished the inventory, even for real GIDs, so P-6 is still open. They may need something we have not sent, or answer on a path we do not see. GID 54 in the Commands List examples is not a device on this system (GIDs are 1 to 15, plus 100). Not tried: `e:36`, `e:32`, `e:18`, `e:15` (they change or persist settings).

## 7. Timelines

After a restart, relative to the `meta` message:

| Time since `meta` | Event |
|---|---|
| -78 s | Test hail published by the capture tool (echoed back) |
| 0 | `meta` published (system connected after restart) |
| +1 to +2 s | `dev/...` inventory (14 devices, one duplicate) |
| +3 s | `e:254` error on `status` and `errors` |
| +47 s, +107 s, +167 s | `e:139` heartbeat |
| +151 s, +157 s, +171 s | `e:56` zone events from switch presses |

After a reboot, relative to the reboot (approximate; the restart time is derived from the uptimes in the later heartbeats):

| Time since reboot | Event |
|---|---|
| -41 s | Last PDM heartbeat before the reboot (`time` 2.70 million ms) |
| 0 | System restarts |
| +11 s | `meta` published |
| +11 to +12 s | `dev/...` inventory, 15 devices in 1.25 s |
| +59 s | First PDM heartbeat, `time` 60168 |
| +78 s | First controller heartbeat, `uptime` 75 |
| +110 to +132 s | Five `e:56` events from switch 12 |
| +300 s | First PowerPlane heartbeat, `time` 300737 |

## 8. Open questions

IDs refer to the register in the implementation plan.

| ID | Question | Status |
|---|---|---|
| P-1 | Topic names | Mostly known (section 2). `events` never seen; `errors` seen only once, with the `e:254` report |
| P-2 | `status` schema | Partly known (`e:139` from three sources, `e:56`, `e:254`). Others unknown |
| P-3 | `meta` and device schema | Known (section 4). Some field meanings unknown |
| P-4 | Events (switch, fault, mismatch) | Switch presses seen as `e:56`. Faults and mismatches unknown |
| P-5 | Command acknowledgements and errors | Partly: every command gets an echo and an empty `cmd` message, even for GIDs that do not exist, so it is not a success signal. No error codes seen, even for `bri` 500 |
| P-6 | Command to republish the inventory | Not documented. A reboot republishes it. `e:8`, `e:9`, `e:10`, `e:11`, `e:13` and `e:49` with real GIDs got no reply and no inventory. Only the hail answers (`e:137`) |
| P-7 | Retained messages | Answered: none retained, in any capture |
| P-8 | Brightness encoding | Known: `bri` 0 to 100. A decimal (12.5) was accepted and dimmed the light. 🔬 Whether 0.1% resolution is honored |
| P-9 | Color temperature encoding | Known: `cct` in kelvin |
| P-10 | Fade encoding | Known: `fade` in milliseconds |
| P-11 | Zones | One zone (250) seen. How membership is read is unknown |
| P-12 | Client and rate limits | Unknown |
| P-13 | Status of non-lighting devices | The PowerPlane, the PDM and the controller send heartbeats. Switches and sockets do not; switches appear only in zone events |
| P-14 | Firmware version | Known from the heartbeat (`swv`, `hwv`) for the PowerPlane and the PDM. Not available for switches or cards |
| P-15 | What GID 100 is, and the fields `opc`, `mode`, `12v`, `term`, `txrx`. It also accepted `e:57` (section 6) | Unknown. New; not yet in the plan's register |
| P-16 | Why the PowerPlane restarted by itself about 4 h after the reboot, without the PDM (section 5.1) | Unknown. New; not yet in the plan's register |
| P-17 | What the empty message on `cmd` means | Unknown. New; not yet in the plan's register |
| P-18 | What `b` and `pc` mean in `e:137`, and whether the device it reported is unassigned | Unknown. New; not yet in the plan's register |
| P-19 | Effect of `e:56` on a zone, and of `bri` outside 0 to 100 | Not reported. New; not yet in the plan's register |

## 9. What the integration depends on

- **Inventory after startup.** A reboot republishes it, but nothing is retained, so when Home Assistant starts while the system is already connected, it receives no inventory. The integration needs a way to make the system republish it (P-6), or it must wait until the system next reconnects.
- **Stable IDs.** `hsn` for devices and `sys` for the system.
- **Liveness.** The PDM's 60 s heartbeat. The PowerPlane sends every 5 min and the controller only after boot and light commands (section 5.1). 🔬 The number of missed beats before marking entities unavailable still has to be chosen.
- **State.** Zone events are the only state seen so far. Per-fixture state needs zone membership (`e:49`) and may need other messages.

## 10. Updating this document

The message definitions (codes, payload shapes, what was seen and tried) live in `asyncapi.yaml` in this folder, an AsyncAPI 3.0 description. The code tables in this document are generated from it: edit the YAML, then run `python3 tools/gen_protocol.py` (needs `pip install pyyaml jsonschema`). `--check` fails if the tables are stale, if an example does not match its schema, or if a key such as an unquoted `on` was read as a boolean. The prose here stays hand-written.

After a firmware or backend update: record a new capture, scrub identifiers, diff it against the stored fixtures, and update this document and the fixtures from the result. Never commit a raw capture.

When comparing capture:

- The capture tool numbers fake serials (`HSN0001`, ...) in order of appearance, so the same device gets different fakes in different captures. Match devices by GID or name, not by fake serial.
