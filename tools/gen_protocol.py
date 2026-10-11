#!/usr/bin/env python3
"""Regenerate the code tables in docs/protocol.md from docs/asyncapi.yaml.

docs/asyncapi.yaml (an AsyncAPI 3.0 document) is the source for message codes,
payload shapes and observations. The tables between the GENERATED markers in
docs/protocol.md are written by this script; the rest of that document is
hand-written. The script also checks the source: no key that YAML read as a
boolean (such as an unquoted `on`), and every message example must match its
payload schema.

Setup:   pip install pyyaml jsonschema
Run:     python3 tools/gen_protocol.py            # rewrite the tables
         python3 tools/gen_protocol.py --check    # exit 1 if they are out of date (for CI)
"""
import argparse
import json
import re
import sys
from pathlib import Path

import yaml

try:
    import jsonschema
except ImportError:  # validation of examples is skipped without it
    jsonschema = None

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "docs" / "asyncapi.yaml"
DOC_PATH = ROOT / "docs" / "protocol.md"

BLOCK = re.compile(
    r"(<!-- BEGIN GENERATED (?P<name>[\w-]+)[^\n]*-->\n)(?P<body>.*?)(<!-- END GENERATED (?P=name) -->)",
    re.S,
)


def code(text) -> str:
    return f"`{text}`"


def payload(p) -> str:
    return code(json.dumps(p, separators=(",", ":"), ensure_ascii=False))


def table(header: list, rows: list) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def messages(spec: dict) -> list:
    """Messages that have an `e` code, in code order (definition order within a code)."""
    found = [m for m in spec["components"]["messages"].values() if "x-code" in m]
    return sorted(found, key=lambda m: m["x-code"])


def codes_seen(spec: dict) -> str:
    rows = [(m["x-code"], m["x-seen"]["as"], m["x-seen"]["text"]) for m in messages(spec) if "x-seen" in m]
    return table(["`e`", "Seen as", "Meaning"], rows)


def documented(spec: dict) -> str:
    rows = []
    for m in messages(spec):
        if not m.get("x-documented"):
            continue
        examples = "; ".join(
            payload(e["payload"]) + (f" {e['name']}" if e.get("name") else "") for e in m["examples"]
        )
        rows.append((m["x-code"], m["summary"], examples, m["description"]))
    return table(["`e`", "Command", "Documented example", "Notes"], rows)


def parameters(spec: dict) -> str:
    rows = [(" / ".join(code(n) for n in s["x-names"]), s["description"])
            for s in spec["components"]["schemas"].values() if "x-names" in s]
    return table(["Name", "Meaning"], rows)


def tried(spec: dict) -> str:
    rows = [(code(f"e:{m['x-code']}"), t["sent"], t["result"])
            for m in messages(spec) for t in m.get("x-tried", [])]
    return table(["Command", "Sent", "Result"], rows)


RENDERERS = {
    "codes-seen": codes_seen,
    "documented-commands": documented,
    "parameters": parameters,
    "commands-tried": tried,
}


def non_string_keys(node, path="") -> list:
    """YAML 1.1 turns on/off/yes/no into booleans; report any key that is not text."""
    bad = []
    if isinstance(node, dict):
        for k, v in node.items():
            if not isinstance(k, str):
                bad.append(f"{path}/{k!r}")
            bad += non_string_keys(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            bad += non_string_keys(v, f"{path}[{i}]")
    return bad


def check_spec(spec: dict) -> list:
    problems = [f"key is not text (quote it): {p}" for p in non_string_keys(spec)]

    seen_codes = {}
    for name, m in spec["components"]["messages"].items():
        if "x-seen" in m:
            if m["x-code"] in seen_codes:
                problems.append(f"e:{m['x-code']} has x-seen on both {seen_codes[m['x-code']]} and {name}")
            seen_codes[m["x-code"]] = name

    if jsonschema is not None:
        resolver = jsonschema.RefResolver.from_schema(spec)
        for name, m in spec["components"]["messages"].items():
            validator = jsonschema.Draft7Validator(m["payload"], resolver=resolver)
            for ex in m.get("examples", []):
                for err in validator.iter_errors(ex["payload"]):
                    problems.append(f"example of message {name} does not match its payload: {err.message}")
    return problems


def render(doc: str, spec: dict) -> str:
    seen = set()

    def swap(m: re.Match) -> str:
        name = m.group("name")
        if name not in RENDERERS:
            sys.exit(f"Unknown generated block '{name}' in {DOC_PATH.name}")
        seen.add(name)
        return m.group(1) + RENDERERS[name](spec) + m.group(4)

    out = BLOCK.sub(swap, doc)
    missing = set(RENDERERS) - seen
    if missing:
        sys.exit(f"{DOC_PATH.name} has no GENERATED block for: {', '.join(sorted(missing))}")
    version = str(spec["info"]["version"])
    banner = re.search(r"\*\*Version ([\w.]+)\.\*\*", out)
    if not banner or banner.group(1) != version:
        sys.exit(f"The version in {DOC_PATH.name} ({banner and banner.group(1)}) does not match "
                 f"{SPEC_PATH.name} ({version})")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--check", action="store_true", help="fail if docs/protocol.md is out of date")
    args = p.parse_args()

    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    problems = check_spec(spec)
    if problems:
        print(f"{SPEC_PATH.name} has problems:")
        for line in problems:
            print(f"  {line}")
        sys.exit(1)
    if jsonschema is None:
        print("Note: jsonschema is not installed, so message examples were not validated.")

    current = DOC_PATH.read_text(encoding="utf-8")
    updated = render(current, spec)

    if updated == current:
        print("docs/protocol.md is up to date.")
    elif args.check:
        print("docs/protocol.md is out of date. Run: python3 tools/gen_protocol.py")
        sys.exit(1)
    else:
        DOC_PATH.write_text(updated, encoding="utf-8")
        print("Updated docs/protocol.md.")


if __name__ == "__main__":
    main()
