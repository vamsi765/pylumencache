"""The spec is valid and the generated files match it."""
import copy
from pathlib import Path

import pytest
import yaml
from conftest import load_tool

pytest.importorskip("jsonschema")
gen = load_tool("gen_protocol")
SPEC = yaml.safe_load(gen.SPEC_PATH.read_text(encoding="utf-8"))


def test_spec_has_no_problems():
    assert gen.check_spec(SPEC) == []


@pytest.mark.parametrize("path,build", [
    (gen.DOC_PATH, lambda: gen.render(gen.DOC_PATH.read_text(encoding="utf-8"), SPEC)),
    (gen.CODES_PATH, lambda: gen.codes_module(SPEC)),
    (gen.COMMANDS_PATH, lambda: gen.commands_module(SPEC)),
    (gen.MODELS_PATH, lambda: gen.models_module(SPEC)),
])
def test_generated_file_is_up_to_date(path: Path, build):
    assert path.read_text(encoding="utf-8") == build(), "run: python3 tools/gen_protocol.py"


def test_unquoted_yaml_boolean_key_is_reported():
    broken = yaml.safe_load("components:\n  messages: {}\nx:\n  on: 1\n")
    assert any("on" in p or "True" in p for p in gen.check_spec(broken))


def test_example_that_breaks_its_schema_is_reported():
    broken = copy.deepcopy(SPEC)
    broken["components"]["messages"]["zoneControl"]["examples"][0]["payload"]["bri"] = 500
    assert any("zoneControl" in p for p in gen.check_spec(broken))
