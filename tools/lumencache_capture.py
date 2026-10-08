#!/usr/bin/env python3
"""Record everything a LumenCache ReNetA MQTT broker publishes.

Safe by default: it only listens. The optional --hail flag sends one
read-only command ({"e": 9, "g": 0}, which lists uncommissioned devices).
It never sends control, commissioning, reboot or reset commands.

Setup:   pip install paho-mqtt
Run:     export LC_HOST=... LC_USER=... LC_PASS=...
         python3 lumencache_capture.py --duration 180 --hail
While it runs, press a SW-D switch and change a light from the PowerPlane
display so that status and events messages show up in the capture.

Output:  capture.jsonl, one JSON object per message (credentials are never
written). Review it before sharing.
"""
import argparse
import json
import os
import ssl
import threading
import time
from collections import Counter
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

FALLBACK_TOPICS = ["status", "meta", "events", "cmd"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--host", default=os.environ.get("LC_HOST"))
    p.add_argument("--port", type=int, default=int(os.environ.get("LC_PORT", "8883")))
    p.add_argument("--user", default=os.environ.get("LC_USER"))
    p.add_argument("--password", default=os.environ.get("LC_PASS"))
    p.add_argument("--cafile", help="CA bundle, if the cert is not publicly trusted")
    p.add_argument("--insecure", action="store_true", help="skip TLS verification")
    p.add_argument("--duration", type=int, default=120, help="seconds to record")
    p.add_argument("--out", default="capture.jsonl")
    p.add_argument("--hail", action="store_true", help='send read-only {"e":9,"g":0}')
    p.add_argument("--cmd-topic", default="cmd", help="topic used for --hail")
    args = p.parse_args()

    if not (args.host and args.user and args.password):
        p.error("host, user and password are required (flags or LC_HOST/LC_USER/LC_PASS)")

    counts: Counter = Counter()
    ready = threading.Event()
    failed = threading.Event()
    out = open(args.out, "w", encoding="utf-8")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="lumencache-capture")
    client.username_pw_set(args.user, args.password)
    if args.insecure:
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)
    else:
        client.tls_set(ca_certs=args.cafile)

    def on_connect(c, _u, _f, reason_code, _p):
        if reason_code.is_failure:
            print(f"Connection refused: {reason_code}")
            failed.set()
            return
        print("Connected. Subscribing to #")
        c.subscribe("#")

    def on_subscribe(c, _u, _mid, reason_codes, _p):
        if any(rc.is_failure for rc in reason_codes):
            print("Wildcard subscribe refused; subscribing to known topics instead")
            for t in FALLBACK_TOPICS:
                c.subscribe(t)
        ready.set()

    def on_message(_c, _u, msg):
        raw = msg.payload.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        out.write(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "topic": msg.topic,
            "retained": msg.retain,
            "qos": msg.qos,
            "payload": parsed if parsed is not None else raw,
            "json": parsed is not None,
        }) + "\n")
        out.flush()
        counts[msg.topic] += 1
        print(f"{msg.topic}{' (retained)' if msg.retain else ''}: {raw[:120]}")

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    try:
        client.connect(args.host, args.port, keepalive=60)
    except Exception as exc:  # noqa: BLE001 - report any connection problem plainly
        print(f"Could not connect: {exc}")
        return
    client.loop_start()

    if failed.wait(timeout=0.1) is False and ready.wait(timeout=15) and args.hail:
        time.sleep(2)
        print('Sending read-only hail {"e":9,"g":0}')
        client.publish(args.cmd_topic, json.dumps({"e": 9, "g": 0}))

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


if __name__ == "__main__":
    main()
