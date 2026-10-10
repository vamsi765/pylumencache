#!/usr/bin/env python3
"""Record everything a LumenCache ReNetA MQTT broker publishes.

Read-only: it listens under your Prefix Topic. The optional --hail flag sends
one read-only command ({"e": 9, "g": 0}, which lists uncommissioned devices)
to <prefix>/cmd. It never sends control, commissioning, reboot or reset commands.

Setup:   pip install paho-mqtt
Run:     export LC_HOST=... LC_USER=... LC_PASS=... LC_TOPIC_PREFIX='...'
         python3 lumencache_capture.py --hail

While it runs, press a SW-D switch and change a light from the PowerPlane
display so that status and events messages show up in the capture.

Output:  capture.jsonl, one JSON object per message. Topics are written with
the prefix removed, so the file does not contain your identifier. Credentials
are never written. Review the file before sharing it.
"""
import argparse
import json
import os
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone

import paho.mqtt.client as mqtt


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
    p.add_argument("--duration", type=int, default=120, help="seconds to record")
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

    def on_message(_c, _u, msg):
        raw = msg.payload.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        topic = without_prefix(msg.topic)
        out.write(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "topic": topic,
            "retained": msg.retain,
            "payload": parsed if parsed is not None else raw,
        }) + "\n")
        out.flush()
        counts[topic] += 1
        print(f"{topic}{' (retained)' if msg.retain else ''}: {raw[:120]}")

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
        client.publish(under_prefix("cmd"), json.dumps({"e": 9, "g": 0}))

    end = time.time() + args.duration
    try:
        while time.time() < end and not failed.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass

    client.loop_stop()
    client.disconnect()
    out.close()
    print(f"\nDone. Wrote {sum(counts.values())} messages to {args.out}")
    for topic, n in counts.most_common():
        print(f"  {topic}: {n}")
    if not counts:
        print("  No messages arrived. Check --topic-prefix and trigger activity "
              "(press a switch) while it runs.")


if __name__ == "__main__":
    main()
