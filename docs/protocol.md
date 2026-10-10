# ReNetA MQTT protocol (observed)

> **Version 0.0.1.** Written from one capture of one system (8 Oct 2026, 26 messages, taken after a system restart) plus the command codes in LumenCache's "Commands List" article. It is not an official specification. Anything marked 🔬 is unknown or an inference and must be confirmed (from a new capture or from LumenCache) before code depends on it. Identifiers are shown as placeholders such as `<hsn>`.

## 1. Connection

| Item | Observed |
|---|---|
| Broker | Hosted EMQX service, public hostname |
| Transport | MQTT over TLS, port 8883, valid certificate (verification on) |
| Authentication | Username and password issued by LumenCache |
| MQTT version | MQTT 5 works (the capture tool uses it) |
| Access scope | Read and write under the issued Prefix Topic. Subscribing to `<prefix>/#` is allowed. 🔬 Behavior outside the prefix is untested (expected: refused) |
| Client IDs | Must be unique per client. EMQX disconnects an existing client that uses the same ID |
| Other clients | A message published by a second client (MQTT Explorer) was received by the first, so several clients can connect. 🔬 Client and rate limits unknown |

## 2. Topic layout

Every topic sits under the **Prefix Topic** (`<prefix>`), a path of the form `platform:na/<state>/<id>`. 🔬 The `<state>` segment currently reads `unprovisioned`; whether it changes after provisioning is unknown. All topics below are relative to the prefix.

| Topic | Direction | Content |
|---|---|---|
| `cmd` | client to system | Commands (JSON). Observed: the hail `{"e":9,"g":0}` |
| `status` | system to client | Heartbeats, zone events, error reports |
| `errors` | system to client | Error reports (same payload as on `status`) |
| `meta` | system to client | System information |
| `dev/...` | system to client | One message per device (inventory) |

LumenCache's mobile setup tutorial lists `status`, `meta`, `events` and `cmd`. `events` did not appear in this capture (🔬 it may only carry events), and `errors` is not in the tutorial. The tutorial says the prefix must end with `/` in the mobile app; the integration joins prefix and topic with exactly one `/` either way. The tutorial describes `meta` as listing devices, but the capture shows devices under `dev/...`; what was observed is used here.

**Retention.** No message in the capture was retained. A client that connects after the system has published cannot learn the inventory by subscribing alone.

## 3. Message conventions

- Payloads are JSON objects.
- `e` is a numeric event or command code. `g` is a group/device ID (GID) or an address.
- The same code can appear as a command and as a status echo (see `e:56`).

Codes seen in the capture:

| `e` | Seen as | Meaning |
|---|---|---|
| 9 | command on `cmd` | Hail: `{"e":9,"g":0}` lists devices still at GID 0. 🔬 No reply was seen, which is consistent with no uncommissioned devices |
| 56 | status | Zone on/off/brightness/color event |
| 139 | status | Periodic PDM heartbeat and telemetry |
| 254 | status and `errors` | Error report |

### Documented commands

From LumenCache's Commands List. All are JSON published on `cmd`. The examples use GID 54 or zone 200 from that document. Note that parameter names differ between commands (`g` or `gid`, `z` or `zid`), so each command is built with exactly the names shown.

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

### Parameters

| Name | Meaning |
|---|---|
| `g` / `gid` | Device address (GID). Set with `e:32` |
| `z` / `zid` | Zone ID. Membership is set with `e:49` |
| `hsn` | Permanent per-device serial, used before the device has a GID |
| `bri` | Brightness, 0 to 100. 🔬 Whether decimals are accepted (the plan wants 0.1% steps) |
| `cct` | Color temperature in kelvin |
| `fade` | Transition time in milliseconds |
| `ma` | Drive current in milliamps |
| `store` | 1 saves the setting through a reboot; without it the setting reverts |
| `a` | Action code inside a multi-purpose command (`e:49`) |
| `c` | Sub-code (`e:15`: 0 reboot, 1 factory reset) |
| `cm` | Socket card mode (`e:18`) |

## 4. Inventory

The system publishes its inventory once, shortly after it connects to the broker. In the capture it took about 1.7 s, from the `meta` message to the last `dev/...` message. 🔬 Whether any command makes the system publish it again is unknown, and this is the most important open question for the integration (section 8).

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
| `gid` | Device ID. Unique across the system (1 to 15 in this capture) |
| `hsn` | Hardware serial number. Stable, so suited as the permanent device ID. Sockets use the PDM's serial plus a suffix (`_S1` to `_S8`) |
| `name` | Product or default name (`Reneta PP`, `PDM_RJ`, `Socket_1`, `SC-CC2-50W`, `SC-PV2-50W`, `SW-D`) |
| `cat` | Device category, see the table above |
| `parent` | GID of the parent device. The PowerPlane has 65535 (no parent) |
| `time` | 🔬 Unknown (a millisecond counter of some kind) |

Observations from this system:

- The PowerPlane (gid 1) has one PDM (gid 2), which has sockets gid 3 to 10 (eight ports). Socket cards gid 14 (SC-CC2) and gid 15 (SC-PV2) sit under sockets gid 4 and gid 6.
- One socket card (gid 11, SC-CC2) and both switches (gid 12 and 13) have `parent` 0 and appear at the top level of `dev/`. 🔬 Why is unknown (possibly not yet assigned to a parent).
- Socket gid 5 was announced twice with identical payloads. Consumers must upsert by `gid` (or `hsn`), not append.
- 🔬 The device list does not show which fixtures belong to which zone, nor which socket cards are CCT-capable.

## 5. Status messages

### 5.1 Heartbeat: `e:139`

Published roughly every 60 s by the PDM.

```json
{ "e": 139, "g": 2, "bay": 3, "hsn": "<hsn>", "swv": "01.00.12m", "hwv": "02.05", "time": 60182, "heap": 8480948, "temp": 31.5, "rh": 35.71 }
```

| Field | Meaning |
|---|---|
| `g` | GID of the reporting PDM |
| `hsn` | Serial of the PDM |
| `bay` | 🔬 Unknown (3 in the capture) |
| `swv`, `hwv` | Software and hardware version |
| `time` | Uptime in milliseconds. Increments by about 60 000 per minute in the capture |
| `heap` | Free memory (bytes). 🔬 Unit inferred |
| `temp`, `rh` | Temperature (°C) and relative humidity (%). 🔬 Units inferred |

The heartbeat is a liveness signal: if it stops, the system or the PDM is probably gone.

### 5.2 Zone event: `e:56`

```json
{ "e": 56, "z": 250, "on": 0, "dev": 12, "g": 65534 }
{ "e": 56, "z": 250, "on": 1, "bri": 100, "cct": 5000, "dev": 12, "g": 65534 }
```

| Field | Meaning |
|---|---|
| `z` | Zone ID (250 in the capture) |
| `on` | 0 off, 1 on |
| `bri`, `cct` | Present when turning on. `bri` is 0 to 100 (percent) and `cct` is in kelvin, as documented by LumenCache |
| `dev` | GID of the device that caused the event. 12 is a SW-D switch, so presses show up here. 🔬 Inferred |
| `g` | 65534 in all three messages. 🔬 Unknown (possibly a broadcast or zone address) |

Three presses of switch 12 gave off (12:26:19), on (12:26:25), off (12:26:39).

🔬 No per-fixture state message was seen. Changes appear at zone level only.

### 5.3 Error report: `e:254`

```json
{ "e": 254, "g": 100, "err": 38, "v": 254 }
```

Published on `status` and on `errors` (identical), about a second after the inventory. 🔬 `g` 100 is not a GID in the inventory. The meaning of error 38 and the full error code list are unknown.

## 6. Timeline of the capture

| Time (UTC) | Event |
|---|---|
| 12:22:30 | Test hail published by the capture tool (echoed back) |
| 12:23:48 | `meta` published (system connected after restart) |
| 12:23:49 to 12:23:50 | `dev/...` inventory (14 devices, one duplicate) |
| 12:23:51 | `e:254` error on `status` and `errors` |
| 12:24:35, 12:25:35, 12:26:35 | `e:139` heartbeat |
| 12:26:19, 12:26:25, 12:26:39 | `e:56` zone events from switch presses |

## 7. Open questions

IDs refer to the register in the implementation plan.

| ID | Question | Status |
|---|---|---|
| P-1 | Topic names | Mostly known (section 2). `events` not seen |
| P-2 | `status` schema | Partly known (`e:139`, `e:56`, `e:254`). Others unknown |
| P-3 | `meta` and device schema | Known (section 4). Some field meanings unknown |
| P-4 | Events (switch, fault, mismatch) | Switch presses seen as `e:56`. Faults and mismatches unknown |
| P-5 | Command acknowledgements and errors | Unknown. No command other than the hail has been sent |
| P-6 | Command to republish the inventory | Not documented. `e:13` (status pull) and `e:9` (lookup by GID) work per device; 🔬 whether their replies republish the `dev/...` messages |
| P-7 | Retained messages | Answered: none retained |
| P-8 | Brightness encoding | Known: `bri` 0 to 100. 🔬 Whether decimals are accepted |
| P-9 | Color temperature encoding | Known: `cct` in kelvin |
| P-10 | Fade encoding | Known: `fade` in milliseconds |
| P-11 | Zones | One zone (250) seen. How membership is read is unknown |
| P-12 | Client and rate limits | Unknown |
| P-13 | Status of non-lighting devices | PDM heartbeat known. Switches appear only as `dev` in zone events |
| P-14 | Firmware version | Known from the heartbeat (`swv`, `hwv`) |

## 8. What the integration depends on

- **Inventory after startup.** Nothing is retained, so when Home Assistant starts while the system is already connected, it receives no inventory. The integration needs a way to make the system republish it (P-6), or it must wait until the system next reconnects.
- **Stable IDs.** `hsn` for devices and `sys` for the system.
- **Liveness.** The 60 s heartbeat. 🔬 The number of missed beats before marking entities unavailable still has to be chosen.
- **State.** Zone events are the only state seen so far. Per-fixture state needs zone membership (`e:49`) and may need other messages.

## 9. Updating this document

After a firmware or backend update: record a new capture, scrub identifiers, diff it against the stored fixtures, and update this document and the fixtures from the result. Never commit a raw capture.
