"""tools/console.py, run against the fake system (no network)."""
import json
from pathlib import Path

import pytest
from conftest import load_tool

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def console(monkeypatch):
    module = load_tool("console")
    monkeypatch.setattr(module, "HAIL_DELAY", 0)
    return module


@pytest.fixture
def replay(tmp_path):
    """One capture file made of the recorded inventory and messages."""
    path = tmp_path / "replay.jsonl"
    path.write_text("".join((FIXTURES / name).read_text() for name in ("inventory.jsonl", "messages.jsonl")))
    return str(path)


def records(tmp_path):
    (path,) = tmp_path.glob("cap.*.jsonl")
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_record_writes_every_message_and_the_hail(console, replay, tmp_path, capsys):
    code = console.main(["record", "--replay", replay, "--duration", "0.3", "--hail", "--name", str(tmp_path / "cap")])
    assert code == 0
    lines = records(tmp_path)
    assert {r["dir"] for r in lines} == {"recv", "sent"}
    assert any(r["topic"] == "status" for r in lines)
    sent = [r for r in lines if r["dir"] == "sent"]
    assert [r["payload"] for r in sent] == [{"e": 9, "g": 0}]
    assert "Done. Wrote" in capsys.readouterr().out


def real_serial_replay(tmp_path):
    path = tmp_path / "real.jsonl"
    heartbeat = {"e": 139, "g": 1, "hsn": "REAL-SERIAL-9", "swv": "1", "hwv": "1", "time": 5, "heap": 6}
    path.write_text(json.dumps({"topic": "status", "payload": heartbeat}) + "\n")
    return str(path)


def test_record_obfuscates_the_file_but_not_the_screen(console, tmp_path, capsys):
    replay = real_serial_replay(tmp_path)
    console.main(["record", "--replay", replay, "--duration", "0.3", "--name", str(tmp_path / "cap")])
    (path,) = tmp_path.glob("cap.*.jsonl")
    assert "REAL-SERIAL-9" not in path.read_text() and "HSN0001" in path.read_text()
    assert "REAL-SERIAL-9" in capsys.readouterr().out


def test_no_obfuscate_keeps_the_real_values(console, tmp_path):
    replay = real_serial_replay(tmp_path)
    console.main(["record", "--replay", replay, "--duration", "0.3", "--no-obfuscate", "--name", str(tmp_path / "cap")])
    (path,) = tmp_path.glob("cap.*.jsonl")
    assert "REAL-SERIAL-9" in path.read_text()


def test_watch_obfuscates_the_screen_unless_told_otherwise(console, tmp_path, capsys):
    replay = real_serial_replay(tmp_path)
    console.main(["watch", "--replay", replay, "--duration", "0.3"])
    assert "REAL-SERIAL-9" not in capsys.readouterr().out
    console.main(["watch", "--replay", replay, "--duration", "0.3", "--no-obfuscate"])
    assert "REAL-SERIAL-9" in capsys.readouterr().out


def test_watch_prints_valid_json(console, replay, capsys):
    assert console.main(["watch", "--replay", replay, "--duration", "0.3"]) == 0
    out = capsys.readouterr().out
    assert "connected" in out
    payloads = [line.split(": ", 1)[1] for line in out.splitlines() if " cmd" not in line and ": {" in line]
    assert payloads and all(isinstance(json.loads(p), dict) for p in payloads)


def test_a_second_run_never_overwrites_the_first(console, replay, tmp_path):
    first = tmp_path / "cap.2000.01.01_00_00_00.jsonl"
    first.write_text("keep")
    console.main(["record", "--replay", replay, "--duration", "0.2", "--name", str(tmp_path / "cap")])
    assert first.read_text() == "keep"


def test_credentials_are_required_without_replay(console, monkeypatch):
    for name in ("LC_HOST", "LC_USER", "LC_PASS", "LC_TOPIC_PREFIX"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit):
        console.parse_args(["watch"])


def test_typed_commands_must_be_json_objects(console, capsys):
    assert console.parse_command('{"e":8,"g":2}') == {"e": 8, "g": 2}
    assert console.parse_command("[1]") is None
    assert console.parse_command("nope") is None
    assert "Nothing sent" in capsys.readouterr().out


def test_factory_reset_needs_a_typed_confirmation(console, monkeypatch):
    reset = {"e": 15, "g": 2, "c": 1}
    monkeypatch.setattr("builtins.input", lambda _: "no")
    assert console.confirmed(reset) is False
    monkeypatch.setattr("builtins.input", lambda _: "RESET")
    assert console.confirmed(reset) is True
    assert console.confirmed({"e": 15, "g": 2, "c": 0}) is True   # a plain reboot is not guarded
