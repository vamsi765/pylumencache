#!/usr/bin/env python3
"""Connect with the library's client and print every parsed message. A live check of pylumencache.

Setup:   pip install -e .
Run:     export LC_HOST=<host> LC_USER=<user> LC_PASS=<pass> LC_TOPIC_PREFIX='<Prefix Topic>'
         python3 tools/watch.py [--hail] [--duration 60]

With --replay FILE it connects to a fake system that replays a capture instead of a real one, and
needs no LC_* variables. Read-only unless --hail is given, which sends one hail (e:9, g:0) to list
uncommissioned devices.
"""
import argparse
import asyncio
import logging
import os

from pylumencache.client import LumenCacheClient
from pylumencache.fake import FakeController
from pylumencache.protocol import commands


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--hail", action="store_true", help="send one hail after connecting")
    p.add_argument("--duration", type=float, default=60,
                   help="seconds to run before exiting (default 60); 0 runs until Ctrl-C")
    p.add_argument("--no-verify-tls", action="store_true", help="do not verify the broker certificate")
    p.add_argument("--replay", metavar="FILE", help="replay a capture file instead of connecting to a system")
    p.add_argument("-v", "--verbose", action="store_true", help="also log every message received and sent")
    args = p.parse_args()
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s",
                        level=logging.DEBUG if args.verbose else logging.INFO)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    if args.replay:
        controller = FakeController.from_file(args.replay, "replay")
        client = LumenCacheClient("replay", "replay", client_factory=controller.factory)
    else:
        client = real_client(args)
    return await run(client, args)


def real_client(args: argparse.Namespace) -> LumenCacheClient:
    return LumenCacheClient(
        os.environ["LC_HOST"],
        os.environ["LC_TOPIC_PREFIX"],
        port=int(os.environ.get("LC_PORT", 8883)),
        username=os.environ.get("LC_USER"),
        password=os.environ.get("LC_PASS"),
        verify_tls=not args.no_verify_tls,
    )


async def run(client: LumenCacheClient, args: argparse.Namespace) -> None:
    client.add_listener(print)
    client.add_connection_listener(lambda up: print("connected" if up else "disconnected"))
    await client.start()
    await client.wait_connected(30)
    if args.hail:
        await client.send(commands.hail(gid=0))
    try:
        if args.duration:
            await asyncio.sleep(args.duration)
        else:
            await asyncio.Event().wait()
    finally:
        await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
