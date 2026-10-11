#!/usr/bin/env python3
"""Regenerate the code tables in docs/protocol.md and the code constants in
src/pylumencache/transports/mqtt/wire/codes.py commands.py and models.py from docs/asyncapi.yaml.

docs/asyncapi.yaml (an AsyncAPI 3.0 document) is the source for message codes,
payload shapes and observations. The tables between the GENERATED markers in
docs/protocol.md and the whole of codes.py, commands.py and models.py are written by this script; the rest
of protocol.md is hand-written. The script also checks the source: no key that YAML read as a
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

try:  # jsonschema 4.18 and later
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT7
except ImportError:
    Registry = None

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "docs" / "asyncapi.yaml"
DOC_PATH = ROOT / "docs" / "protocol.md"
CODES_PATH = ROOT / "src" / "pylumencache" / "transports" / "mqtt" / "wire" / "codes.py"
COMMANDS_PATH = ROOT / "src" / "pylumencache" / "transports" / "mqtt" / "wire" / "commands.py"
MODELS_PATH = ROOT / "src" / "pylumencache" / "transports" / "mqtt" / "wire" / "models.py"
PY_TYPES = {"integer": "int", "number": "float", "string": "str"}

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


def codes_module(spec: dict) -> str:
    """Python source for the Code enum: one member per `e` code, named after its first message."""
    members = {}
    for m in messages(spec):
        members.setdefault(m["x-code"], m)
    lines = [
        '"""Message codes (the `e` field). Generated from docs/asyncapi.yaml by tools/gen_protocol.py; do not edit."""',
        "from enum import IntEnum",
        "",
        "",
        "class Code(IntEnum):",
        '    """Values of the `e` field.',
        "",
        "    Where the YAML has several messages for one code (a command and its reply),",
        "    the member is named after the first.",
        '    """',
        "",
    ]
    for code_, m in members.items():
        name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", next(
            k for k, v in spec["components"]["messages"].items() if v is m)).upper()
        lines.append(f"    {name} = {code_}")
    return "\n".join(lines) + "\n"


def snake(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


def commands_module(spec: dict) -> str:
    """Python source for one builder function per documented command (`x-documented`)."""
    schemas = spec["components"]["schemas"]
    out = [
        '"""Command builders. Generated from docs/asyncapi.yaml by tools/gen_protocol.py; do not edit.',
        "",
        "Each function returns the JSON object to publish on the `cmd` topic. Arguments left as",
        "None are left out of the message. Argument names follow the parameter names in",
        "docs/protocol.md; the wire key is shown in each docstring.",
        '"""',
        "from __future__ import annotations",
        "",
        "from typing import Any",
        "",
        "from .codes import Code",
        "",
        "",
        "def _check_range(name: str, value: float, low: float, high: float) -> None:",
        "    if not low <= value <= high:",
        '        raise ValueError(f"{name} must be between {low} and {high}, got {value}")',
    ]
    for key, m in spec["components"]["messages"].items():
        if not m.get("x-documented"):
            continue
        params = []
        for wire, prop in m["payload"]["properties"].items():
            if wire == "e":
                continue
            ref = prop["$ref"].rsplit("/", 1)[1]
            params.append((wire, snake(ref), ref, schemas[ref]))
        sig = "".join(f"{py}: {PY_TYPES[sch['type']]} | None = None, " for _, py, _, sch in params)
        out += ["", "", f"def {snake(key)}({'*, ' if params else ''}{sig.rstrip(', ')}) -> dict[str, Any]:"]
        out.append(f'    """{m["summary"]} (e:{m["x-code"]}).')
        if params:
            out += ["", "    Wire keys: " + ", ".join(f"{py} -> {wire}" for wire, py, _, _ in params) + ".", ]
        out.append('    """')
        for _, py, _, sch in params:
            if "minimum" in sch:
                out += [f"    if {py} is not None:",
                        f"        _check_range(\"{py}\", {py}, {sch['minimum']}, {sch['maximum']})"]
        out.append(f"    msg: dict[str, Any] = {{\"e\": Code.{snake(key).upper()}.value}}")
        for wire, py, _, _ in params:
            out += [f"    if {py} is not None:", f"        msg[\"{wire}\"] = {py}"]
        out.append("    return msg")
    return "\n".join(out) + "\n"


def prop_type(schema: dict) -> str:
    if "enum" in schema or "const" in schema:
        return "int"
    if schema["type"] == "array":
        return f"list[{PY_TYPES[schema['items']['type']]}]"
    return PY_TYPES[schema["type"]]


def incoming_models(spec: dict) -> list:
    """(class name, schema) for each received message that has a fixed shape."""
    schemas = spec["components"]["schemas"]
    found = []
    for key, m in spec["components"]["messages"].items():
        payload_ = m["payload"]
        if m.get("x-documented") or m.get("x-model") is False or payload_.get("type") == "string":
            continue
        if "oneOf" in payload_:
            for alt in payload_["oneOf"]:
                ref = alt["$ref"].rsplit("/", 1)[1]
                found.append((ref, schemas[ref]))
        else:
            found.append((key[0].upper() + key[1:], payload_))
    return found


def models_module(spec: dict) -> str:
    """Python source for one dataclass per received message shape."""
    out = [
        '"""Received messages. Generated from docs/asyncapi.yaml by tools/gen_protocol.py; do not edit.',
        "",
        "Each class has from_dict(). Fields the spec does not list are kept in `extra`, and",
        "optional fields are None when the message did not carry them. A missing required",
        "field raises TypeError, which the parser turns into an UnknownMessage.",
        '"""',
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass, field",
        "from typing import Any",
    ]
    schemas = spec["components"]["schemas"]
    for cls, sch in incoming_models(spec):
        required = set(sch.get("required", []))
        fields = []   # (python name, wire name, type, required)
        for wire, prop in sch["properties"].items():
            if wire == "e":
                continue
            if "$ref" in prop:
                prop = {**schemas[prop["$ref"].rsplit("/", 1)[1]], **{k: v for k, v in prop.items() if k != "$ref"}}
            py = prop.get("x-py-name", wire)
            if not py.isidentifier():
                sys.exit(f"{cls}.{wire} is not a Python name: add x-py-name to it in {SPEC_PATH.name}")
            fields.append((py, wire, prop_type(prop), wire in required))
        fields.sort(key=lambda f: not f[3])   # required fields first
        code_ = sch["properties"].get("e", {}).get("const")
        with_code = f" with e:{code_}" if code_ is not None else ""
        out += ["", "", "@dataclass(frozen=True)", f"class {cls}:", f'    """Received message{with_code}."""', ""]
        for py, _, typ, req in fields:
            out.append(f"    {py}: {typ}" if req else f"    {py}: {typ} | None = None")
        out.append("    extra: dict[str, Any] = field(default_factory=dict)")
        out += ["", f"    E = {code_}",
                "    WIRE = {" + ", ".join(f'"{w}": "{py}"' for py, w, _, _ in fields) + "}",
                "", "    @classmethod", "    def from_dict(cls, data: dict[str, Any]) -> "+cls+":",
                "        values = {py: data[wire] for wire, py in cls.WIRE.items() if wire in data}",
                "        extra = {k: v for k, v in data.items() if k not in cls.WIRE and k != \"e\"}",
                "        return cls(**values, extra=extra)"]
    return "\n".join(out) + "\n"


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


def payload_validator(spec: dict, message: str):
    """A validator for one message's payload, resolving $refs against the whole spec."""
    if Registry is None:  # older jsonschema
        return jsonschema.Draft7Validator(spec["components"]["messages"][message]["payload"],
                                          resolver=jsonschema.RefResolver.from_schema(spec))
    registry = Registry().with_resource("urn:asyncapi", Resource(contents=spec, specification=DRAFT7))
    return jsonschema.Draft7Validator(
        {"$ref": f"urn:asyncapi#/components/messages/{message}/payload"}, registry=registry)


def check_spec(spec: dict) -> list:
    problems = [f"key is not text (quote it): {p}" for p in non_string_keys(spec)]

    seen_codes = {}
    for name, m in spec["components"]["messages"].items():
        if "x-seen" in m:
            if m["x-code"] in seen_codes:
                problems.append(f"e:{m['x-code']} has x-seen on both {seen_codes[m['x-code']]} and {name}")
            seen_codes[m["x-code"]] = name

    if jsonschema is not None:
        for name, m in spec["components"]["messages"].items():
            validator = payload_validator(spec, name)
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
    p.add_argument("--check", action="store_true", help="fail if the generated files are out of date")
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

    targets = [
        (DOC_PATH, render(DOC_PATH.read_text(encoding="utf-8"), spec)),
        (CODES_PATH, codes_module(spec)),
        (COMMANDS_PATH, commands_module(spec)),
        (MODELS_PATH, models_module(spec)),
    ]
    stale = False
    for path, updated in targets:
        name = path.relative_to(ROOT)
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if updated == current:
            print(f"{name} is up to date.")
        elif args.check:
            print(f"{name} is out of date. Run: python3 tools/gen_protocol.py")
            stale = True
        else:
            path.write_text(updated, encoding="utf-8")
            print(f"Updated {name}.")
    if stale:
        sys.exit(1)


if __name__ == "__main__":
    main()
