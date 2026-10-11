import importlib.util
from pathlib import Path

TOOLS = Path(__file__).parent.parent / "tools"


def load_tool(name: str):
    """Import a script from tools/ as a module."""
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
