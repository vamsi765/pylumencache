#!/usr/bin/env python3
"""Record what a LumenCache ReNetA MQTT broker publishes, and optionally send commands.

Default: it only listens, under your Prefix Topic. The optional --hail flag sends
one read-only command ({"e": 9, "g": 0}, which lists uncommissioned devices)
to <prefix>/cmd.

With --interactive, it also sends what you type: each line must be a JSON
command and is published to <prefix>/cmd exactly as typed. Commands can change
your lights and settings. The only guard is a confirmation for factory reset.

Setup:   pip install paho-mqtt
Run:     export LC_HOST=... LC_USER=... LC_PASS=... LC_TOPIC_PREFIX='...'
         python3 lumencache_capture.py --hail            # record for 2 minutes
         python3 lumencache_capture.py --interactive     # type commands

Output:  capture.jsonl, one JSON object per message, with "dir" set to "recv" or
         "sent" (commands this script published; the broker may also echo them back
         as "recv" on cmd). Topics are written with the prefix removed, so the file
         does not contain your identifier. Credentials are never written.
"""
import argparse
import json
import os
import signal
import sys
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

try:
    import readline  # noqa: F401 - line editing and history for --interactive
except ImportError:  # e.g. Windows without pyreadline
    readline = None

PROMPT = "> "


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--host", default=os.environ.get("LC_HOST"))
    p.add_argument("--port", type=int, default=int(os.environ.get("LC_PORT", "8883")))
    p.add_argument("--user", default=os.environ.get("LC_USER"))
    p.add_argument("--password", default=os.environ.get("LC_PASS"))
    p.add_argument("--topic-prefix", default=os.environ.get("LC_TOPIC_PREFIX"),
                   help="your Prefix Topic (env LC_TOPIC_PREFIX)")
    p.add_argument("--topic", action="append", default=[],
                   help="subscribe to this topic (relative to the prefix) instead of "
                        "<prefix>/#; repeat for several")
    p.add_argument("-i", "--interactive", action="store_true",
                   help="type JSON commands to send to <prefix>/cmd; ends at --duration or when you quit")
    p.add_argument("--duration", type=int, default=120,
                   help="seconds to run, interactive mode included (default 120; 0 = until you stop it)")
    p.add_argument("--out", default="capture.jsonl")
    p.add_argument("--hail", action="store_true", help='send read-only {"e":9,"g":0}')
    args = p.parse_args()

    if not (args.host and args.user and args.password and args.topic_prefix):
        p.error("host, user, password and topic prefix are required "
                "(flags or LC_HOST / LC_USER / LC_PASS / LC_TOPIC_PREFIX)")

    prefix = args.topic_prefix.strip().rstrip("/")

    def under_prefix(topic: str) -> str:
        return f"{prefix}/{topic.lstrip('/')}"

    def without_prefix(topic: str) -> str:
        return topic[len(prefix) + 1:] if topic.startswith(prefix + "/") else topic

    filters = [under_prefix(t) for t in args.topic] or [under_prefix("#")]

    counts: Counter = Counter()
    pending: dict = {}            # subscribe request id -> topic filter
    granted: list = []
    refused: list = []
    ready = threading.Event()
    failed = threading.Event()
    out = open(args.out, "w", encoding="utf-8")

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"lumencache-capture-{uuid.uuid4().hex[:8]}",
        protocol=mqtt.MQTTv5,
    )
    client.username_pw_set(args.user, args.password)
    client.tls_set()

    def on_connect(c, _u, _f, reason_code, _p):
        if reason_code.is_failure:
            print(f"Connection refused: {reason_code}")
            print("  Check username and password. If the message mentions the protocol "
                  "version, the broker may not support MQTT 5.")
            failed.set()
            return
        print(f"Connected to {args.host}:{args.port}")
        for f in filters:
            _result, mid = c.subscribe(f)
            pending[mid] = f
            print(f"Subscribing to '{without_prefix(f)}' under the prefix")

    def on_subscribe(_c, _u, mid, reason_codes, _p):
        topic = without_prefix(pending.pop(mid, "?"))
        for rc in reason_codes:
            if rc.is_failure:
                refused.append(topic)
                print(f"  REFUSED '{topic}': {rc}")
                print("    Check that --topic-prefix matches your Prefix Topic exactly, "
                      "or use --topic to name a topic you may read.")
            else:
                granted.append(topic)
                print(f"  OK '{topic}'")
        if not pending:
            ready.set()

    write_lock = threading.Lock()
    at_prompt = threading.Event()  # set while the main thread waits at "> "

    def say(text: str) -> None:
        """Print from the MQTT thread without wrecking a half-typed command."""
        if readline is not None and at_prompt.is_set():
            # readline does not know we cleared the line, so redraw prompt and
            # the half-typed text ourselves (redisplay() alone repaints nothing)
            sys.stdout.write("\r\033[K" + text + "\n" + PROMPT + readline.get_line_buffer())
            sys.stdout.flush()
        else:
            print(text)

    def record(direction: str, topic: str, retained: bool, payload) -> None:
        """Append one line to the capture. dir is "recv" (from the broker) or "sent"."""
        with write_lock:
            out.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "dir": direction,
                "topic": topic,
                "retained": retained,
                "payload": payload,
            }) + "\n")
            out.flush()

    def on_message(_c, _u, msg):
        raw = msg.payload.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        topic = without_prefix(msg.topic)
        record("recv", topic, msg.retain, parsed if parsed is not None else raw)
        counts[topic] += 1
        say(f"{time.strftime('%H:%M:%S')} {topic}{' (retained)' if msg.retain else ''}: {raw}")

    def send(line: str) -> None:
        """Publish one typed command to <prefix>/cmd, exactly as typed."""
        try:
            command = json.loads(line)
        except ValueError as exc:
            print(f"  Not valid JSON ({exc}). Nothing sent.")
            return
        if not isinstance(command, dict):
            print('  A command is a JSON object, like {"e":8,"g":2}. Nothing sent.')
            return
        if command.get("e") == 15 and command.get("c") == 1:
            answer = input(f"  This factory-resets GID {command.get('g')}. "
                           "Type RESET to confirm: ")
            if answer.strip() != "RESET":
                print("  Cancelled. Nothing sent.")
                return
        info = client.publish(under_prefix("cmd"), line)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            print(f"  Could not send: {mqtt.error_string(info.rc)}")
        else:
            record("sent", "cmd", False, command)
            print("  Sent to cmd.")

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    try:
        client.connect(args.host, args.port, keepalive=60)
    except Exception as exc:  # noqa: BLE001 - report any connection problem plainly
        print(f"Could not connect: {exc}")
        print("  Check host, port and network access.")
        return
    client.loop_start()

    if ready.wait(timeout=15) and granted and args.hail:
        time.sleep(2)
        print('Sending read-only hail {"e":9,"g":0} to topic "cmd" under the prefix')
        client.publish(under_prefix("cmd"), '{"e":9,"g":0}')
        record("sent", "cmd", False, {"e": 9, "g": 0})

    timed_out = threading.Event()

    def time_up() -> None:
        timed_out.set()
        # a real SIGINT is needed: interrupt_main() does not wake a blocked input()
        os.kill(os.getpid(), signal.SIGINT)

    if args.interactive and not failed.is_set():
        if args.duration > 0:
            timer = threading.Timer(args.duration, time_up)
            timer.daemon = True
            timer.start()
        print('\nInteractive. Type a JSON command and press Enter to send it to "cmd", '
              'for example {"e":8,"g":2}.\nMessages from the system print as they '
              "arrive. To exit either type quit or press Ctrl-C"
              + (f" or timeouts in {args.duration}s.\n" if args.duration > 0 else ".\n"))
        try:
            while not failed.is_set():
                at_prompt.set()
                try:
                    line = input(PROMPT).strip()
                finally:
                    at_prompt.clear()
                if line.lower() in ("quit", "exit"):
                    print(f"\nGoodbye!")
                    break
                if line:
                    send(line)
        except EOFError:
            pass
        except KeyboardInterrupt:
            print(f"\nProcess interrupted by user.")
        if timed_out.is_set():
            print(f"\nReached timeout duration ({args.duration}s).")
        elif args.duration > 0:
            timer.cancel()
    else:
        end = time.time() + args.duration if args.duration > 0 else None
        try:
            while (end is None or time.time() < end) and not failed.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

    client.loop_stop()
    client.disconnect()
    out.close()
    print(f"\nDone. Wrote the following {sum(counts.values())} messages to {args.out}")
    for topic, n in counts.most_common():
        print(f"  {topic}: {n}")
    if not counts and granted:
        print("  The broker accepted the subscription, but nothing was published under "
              "this prefix.\n  Either the system is not connected to this broker, or it "
              "publishes under a different prefix\n  (for example if it was provisioned "
              "after this prefix was issued).")
    elif not counts and not refused:
        print("  No subscription was confirmed. Check host, port and credentials.")


if __name__ == "__main__":
    main()
