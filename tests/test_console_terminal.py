"""Interactive mode must leave the terminal as it found it, however it ends."""
import os
import signal
import sys
import time
from pathlib import Path

import pytest

pty = pytest.importorskip("pty")
termios = pytest.importorskip("termios")

ROOT = Path(__file__).parent.parent
REPLAY = ROOT / "tests" / "fixtures" / "messages.jsonl"


def run_on_a_terminal(args, *, interrupt_after=None, type_text=None):
    """Run console.py on a pseudo-terminal. Returns the terminal's local flags after it exits, and its status."""
    pid, fd = pty.fork()
    if pid == 0:
        os.execv(sys.executable, [sys.executable, str(ROOT / "tools" / "console.py"), *args])
    try:
        time.sleep(1.0)   # connected, and waiting at the prompt
        if type_text is not None:
            os.write(fd, type_text.encode())
        if interrupt_after is not None:
            os.kill(pid, signal.SIGINT)
        status, deadline = None, time.time() + 15
        while status is None and time.time() < deadline:
            try:
                os.read(fd, 4096)
            except OSError:
                pass
            done, raw = os.waitpid(pid, os.WNOHANG)
            if done:
                status = raw
            else:
                time.sleep(0.05)
        assert status is not None, "console.py did not exit"
        return termios.tcgetattr(fd)[3], status
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os.close(fd)


def echoing(flags):
    return bool(flags & termios.ECHO) and bool(flags & termios.ICANON)


@pytest.mark.parametrize("how", ["timeout", "quit", "ctrl-c"])
def test_the_terminal_is_restored(how):
    args = ["watch", "--replay", str(REPLAY), "-i", "--duration", "2" if how == "timeout" else "20"]
    flags, _ = run_on_a_terminal(
        args,
        interrupt_after=1 if how == "ctrl-c" else None,
        type_text="quit\n" if how == "quit" else None,
    )
    assert echoing(flags)
