#!/usr/bin/env python3
"""Talk to a LumenCache ReNetA system over MQTT: record what it publishes, watch it live, and send commands.

Setup:   pip install -e .      (from the repository root)
Run:     export LC_HOST=<host> LC_USER=<user> LC_PASS=<pass> LC_TOPIC_PREFIX='<Prefix Topic>'
         python3 tools/console.py record --hail       # write a capture file, 2 minutes
         python3 tools/console.py watch               # print parsed messages, 1 minute
         python3 tools/console.py watch -i            # the same, and type commands to send

Both subcommands listen under your Prefix Topic. They are read-only unless you pass --hail, which
sends one hail ({"e": 9, "g": 0}, listing uncommissioned devices), or -i / --interactive, where each
line you type must be a JSON command and is published to <prefix>/cmd. Commands can change your lights
and settings. The only guard is a confirmation for factory reset.

record   Writes <name>.YYYY.MM.DD_HH_MM_SS.jsonl (local start time; --name sets <name>, default "capture"),
         a new file per run. One JSON object per message, with "dir" set to "recv" or "sent" (commands this
         script published; the broker also echoes them back as "recv" on cmd). Topics are written without the
         prefix, so the file does not contain your identifier. Credentials are never written.
         The screen shows the messages as received.
watch    Prints each message as a typed object (heartbeat, zone event, ...).

Obfuscation is on by default: system ids and device serials (sys, hsn) become stable fakes, the free-text
fields in meta (name, address, phone, note) are blanked, and MAC-shaped strings are masked. For record it
applies to the file (the screen shows real values); for watch it applies to the screen. Pass --no-obfuscate to
keep the real values. Still review a capture before sharing it.

With --replay FILE, either subcommand talks to a fake system that replays a capture instead of a real one,
and needs no LC_* variables.
"""
import argparse
import asyncio
import contextlib
import json
import logging
import os
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

from pylumencache.obfuscate import Obfuscator
from pylumencache.transport import NotConnectedError
from pylumencache.transports.mqtt import MqttTransport
from pylumencache.transports.mqtt.fake import FakeController
from pylumencache.transports.mqtt.wire import commands

try:
    import readline  # noqa: F401 - line editing and history for --interactive
except ImportError:  # e.g. Windows without pyreadline
    readline = None  # type: ignore[assignment]

try:
    import termios
except ImportError:  # Windows
    termios = None  # type: ignore[assignment]

PROMPT = "> "
CONNECT_TIMEOUT = 30   # seconds
HAIL_DELAY = 2.0   # seconds after connecting, so the inventory arrives first
DEFAULT_DURATION = {"record": 120.0, "watch": 60.0}


# --- command line ------------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--host", default=os.environ.get("LC_HOST"))
    common.add_argument("--port", type=int, default=int(os.environ.get("LC_PORT", "8883")))
    common.add_argument("--user", default=os.environ.get("LC_USER"))
    common.add_argument("--password", default=os.environ.get("LC_PASS"))
    common.add_argument("--topic-prefix", default=os.environ.get("LC_TOPIC_PREFIX"),
                        help="your Prefix Topic (env LC_TOPIC_PREFIX)")
    common.add_argument("--topic", action="append", default=[],
                        help="subscribe to this topic (relative to the prefix) instead of #; repeat for several")
    common.add_argument("--no-verify-tls", action="store_true", help="do not verify the broker certificate")
    common.add_argument("-i", "--interactive", action="store_true",
                        help="type JSON commands to send to <prefix>/cmd; ends at --duration or when you quit")
    common.add_argument("--hail", action="store_true", help='send one read-only hail {"e":9,"g":0}')
    common.add_argument("--duration", type=float, default=None,
                        help="seconds to run, interactive mode included (record 120, watch 60; 0 = until you stop it)")
    common.add_argument("--no-obfuscate", dest="obfuscate", action="store_false",
                        help="keep real ids, serials and addresses (default: replace them with stable fakes)")
    common.add_argument("--replay", metavar="FILE", help="use a fake system that replays a capture file")
    common.add_argument("-v", "--verbose", action="store_true", help="also log every message received and sent")

    parser = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        epilog="""\
examples:
  console.py record --help            all options of one command (also: console.py watch --help)
  console.py record --hail            write a capture file
  console.py watch                    print parsed messages as they arrive
  console.py watch -i                 the same, and type JSON commands to send
  console.py record -i                record, and also send commands (they are recorded too)
  console.py watch --replay FILE -i   practise against a fake system that replays a capture""",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser(
        "record", parents=[common], help="write what the system publishes to a file",
        description="Write every message the system publishes to a new capture file, and show it on screen.",
        epilog="""\
examples:
  console.py record --hail            write a capture file, with one read-only hail
  console.py record -i                also type commands to send (they are recorded too)
  console.py record --name before     start the file name with "before"

For the other command, see: console.py watch --help""",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    record.add_argument("--name", default="capture",
                        help="start of the output file name: <name>.YYYY.MM.DD_HH_MM_SS.jsonl")
    sub.add_parser(
        "watch", parents=[common], help="print parsed messages as they arrive",
        description="Print each message as a typed object, such as ZoneEvent(...) or PdmHeartbeat(...).",
        epilog="""\
examples:
  console.py watch                    print parsed messages for a minute
  console.py watch -i                 also type JSON commands to send
  console.py watch --replay FILE -i   practise against a fake system that replays a capture

For the other command, see: console.py record --help""",
        formatter_class=argparse.RawDescriptionHelpFormatter)

    args = parser.parse_args(argv)
    if args.duration is None:
        args.duration = DEFAULT_DURATION[args.command]
    if args.replay:
        args.topic_prefix = "replay"
    elif not (args.host and args.user and args.password and args.topic_prefix):
        parser.error("host, user, password and topic prefix are required "
                     "(flags or LC_HOST / LC_USER / LC_PASS / LC_TOPIC_PREFIX)")
    args.topic_prefix = args.topic_prefix.strip().rstrip("/")
    return args


def build_transport(args: argparse.Namespace) -> MqttTransport:
    topics = tuple(args.topic) or ("#",)
    if args.replay:
        controller = FakeController.from_file(args.replay, args.topic_prefix)
        return MqttTransport("replay", args.topic_prefix, topics=topics, client_factory=controller.factory)
    return MqttTransport(
        args.host, args.topic_prefix, port=args.port, username=args.user, password=args.password,
        verify_tls=not args.no_verify_tls, topics=topics)


# --- output --------------------------------------------------------------------------------------

class Screen:
    """Prints from the event loop without wrecking a half-typed command."""

    def __init__(self) -> None:
        self.at_prompt = threading.Event()   # set while the input thread waits at "> "

    def say(self, text: str) -> None:
        if readline is not None and self.at_prompt.is_set():
            # readline does not know the line was cleared, so redraw the prompt and the typed text
            sys.stdout.write("\r\033[K" + text + "\n" + PROMPT + readline.get_line_buffer())
            sys.stdout.flush()
        else:
            print(text)


class Recorder:
    """Appends messages to the capture file, obfuscated unless told otherwise."""

    def __init__(self, path: str, obfuscator: Obfuscator | None) -> None:
        self.path, self._obfuscator = path, obfuscator
        self.counts: Counter[str] = Counter()
        self._out = open(path, "x", encoding="utf-8")

    def write(self, direction: str, topic: str, retained: bool, payload: Any) -> None:
        if self._obfuscator is not None:
            payload = self._obfuscator.payload(payload)
        self._out.write(json.dumps({
            "ts": datetime.now(UTC).isoformat(),
            "dir": direction,
            "topic": topic,
            "retained": retained,
            "payload": payload,
        }) + "\n")
        self._out.flush()

    def close(self) -> None:
        self._out.close()


def raw_printer(screen: Screen, recorder: Recorder | None,
                obfuscator: Obfuscator | None = None) -> Callable[[str, bytes | str, bool], None]:
    """A raw listener shared by both commands: show each message as received, and record it if asked to.

    The screen is obfuscated only when an obfuscator is given (watch); record obfuscates its file instead.
    """
    def on_raw(topic: str, payload: bytes | str, retained: bool) -> None:
        text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if recorder is not None:
            recorder.write("recv", topic, retained, parsed if parsed is not None else text)
            recorder.counts[topic] += 1
        if obfuscator is not None and parsed is not None:
            text = json.dumps(obfuscator.payload(parsed), separators=(",", ":"))
        screen.say(f"{time.strftime('%H:%M:%S')} {topic}{' (retained)' if retained else ''}: {text}")
    return on_raw


def summary(recorder: Recorder, connected_once: bool) -> None:
    print(f"\nDone. Wrote {sum(recorder.counts.values())} messages to {recorder.path}")
    for topic, n in recorder.counts.most_common():
        print(f"  {topic}: {n}")
    if not recorder.counts and connected_once:
        print("  Connected, but nothing was published under this prefix.\n  Either the system is not connected to "
              "this broker, or it publishes under a different prefix\n  (for example if it was provisioned after "
              "this prefix was issued).")
    elif not recorder.counts:
        print("  Never connected. Check host, port and credentials.")


# --- sending ---------------------------------------------------------------------------------

def parse_command(line: str) -> dict[str, Any] | None:
    """The command typed on a line, or None (after saying why) if it is not a JSON object."""
    try:
        command = json.loads(line)
    except ValueError as exc:
        print(f"  Not valid JSON ({exc}). Nothing sent.")
        return None
    if not isinstance(command, dict):
        print('  A command is a JSON object, like {"e":8,"g":2}. Nothing sent.')
        return None
    return command


def confirmed(command: dict[str, Any]) -> bool:
    """Factory reset (e:15 with c:1) needs RESET typed first. Everything else is sent as typed."""
    if command.get("e") == 15 and command.get("c") == 1:
        answer = input(f"  This factory-resets GID {command.get('g')}. Type RESET to confirm: ")
        if answer.strip() != "RESET":
            print("  Cancelled. Nothing sent.")
            return False
    return True


async def send(transport: MqttTransport, recorder: Recorder | None, command: dict[str, Any]) -> None:
    try:
        await transport.send_raw(command)
    except NotConnectedError:
        print("  Could not send: not connected.")
        return
    if recorder is not None:
        recorder.write("sent", "cmd", False, command)
    print("  Sent to cmd.")


@contextlib.contextmanager
def terminal_restored() -> Iterator[None]:
    """Put the terminal back as it was. readline switches it to raw mode while a prompt waits, and the
    program can end (timeout, Ctrl-C) with the prompt still waiting, which would leave the shell without echo."""
    saved = None
    if termios is not None and sys.stdin.isatty():
        with contextlib.suppress(termios.error, OSError, ValueError):
            saved = termios.tcgetattr(sys.stdin.fileno())
    try:
        yield
    finally:
        if saved is not None:
            with contextlib.suppress(termios.error, OSError, ValueError):
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, saved)


async def interactive(transport: MqttTransport, recorder: Recorder | None, screen: Screen) -> None:
    """Read commands on a daemon thread (a blocked input() must not keep the program alive) and send them."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    handled = threading.Event()

    def read() -> None:
        while True:
            screen.at_prompt.set()
            try:
                line = input(PROMPT).strip()
            except EOFError:
                line = "quit"
            finally:
                screen.at_prompt.clear()
            if line.lower() in ("quit", "exit"):
                loop.call_soon_threadsafe(queue.put_nowait, None)
                return
            command = parse_command(line) if line else None
            if command is None or not confirmed(command):
                continue
            handled.clear()
            loop.call_soon_threadsafe(queue.put_nowait, command)
            handled.wait()

    print('\nInteractive. Type a JSON command and press Enter to send it to "cmd", for example {"e":8,"g":2}.\n'
          "Messages from the system print as they arrive. Type quit or press Ctrl-C to exit.\n")
    with terminal_restored():
        threading.Thread(target=read, daemon=True, name="console-input").start()
        while (command := await queue.get()) is not None:
            await send(transport, recorder, command)
            handled.set()
        print("\nGoodbye!")


# --- the run ---------------------------------------------------------------------------------

async def run(args: argparse.Namespace) -> int:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s",
                        level=logging.DEBUG if args.verbose else logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    transport, screen = build_transport(args), Screen()
    recorder: Recorder | None = None
    if args.command == "record":
        stamp = datetime.now().strftime("%Y.%m.%d_%H_%M_%S")
        recorder = Recorder(f"{args.name}.{stamp}.jsonl", Obfuscator(args.topic_prefix) if args.obfuscate else None)
        print(f"Writing to {recorder.path}")
        transport.add_raw_listener(raw_printer(screen, recorder))
    else:
        obfuscator = Obfuscator(args.topic_prefix) if args.obfuscate else None
        transport.add_raw_listener(raw_printer(screen, None, obfuscator))
    transport.add_connection_listener(lambda up: screen.say("connected" if up else "disconnected"))

    connected_once = False
    await transport.start()
    try:
        try:
            await transport.wait_connected(CONNECT_TIMEOUT)
        except TimeoutError:
            print(f"Could not connect to {args.host or 'the fake system'}. "
                  "Check host, port, username and password (run with -v to see the reason).")
            return 1
        connected_once = True
        if args.hail:
            await asyncio.sleep(HAIL_DELAY)
            print('Sending read-only hail {"e":9,"g":0} to "cmd" under the prefix')
            await send(transport, recorder, commands.hail(gid=0))
        if args.interactive:
            try:
                await asyncio.wait_for(interactive(transport, recorder, screen), args.duration or None)
            except TimeoutError:
                print(f"\nReached timeout duration ({args.duration:g}s).")
        elif args.duration:
            await asyncio.sleep(args.duration)
        else:
            await asyncio.Event().wait()
        return 0
    finally:
        await transport.stop()
        if recorder is not None:
            recorder.close()
            summary(recorder, connected_once)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
