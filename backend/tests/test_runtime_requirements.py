"""The production image installs only requirements-runtime.txt (backend/Dockerfile),
so every third-party import under app/ must be pinned there — otherwise the image
boots fine in CI (which installs requirements.txt) and fails in production."""

import ast
import re
import sys
from importlib.metadata import PackageNotFoundError, packages_distributions
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"

# Import name → distribution name where they differ and importlib has no map.
_KNOWN = {"psycopg": "psycopg", "jwt": "pyjwt", "argon2": "argon2-cffi", "slowapi": "slowapi"}
# Imports satisfied by a pinned package's own hard dependency.
_TRANSITIVE_OF = {"starlette": "fastapi"}


def _runtime_distributions() -> set[str]:
    pins = set()
    for line in (BACKEND / "requirements-runtime.txt").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            pins.add(re.split(r"[\[=<>!~ ]", line, maxsplit=1)[0].lower().replace("_", "-"))
    return pins


def _top_level_imports() -> set[str]:
    names: set[str] = set()
    for path in APP.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    stdlib = set(sys.stdlib_module_names)
    return {n for n in names if n not in stdlib and n != "app"}


def test_every_third_party_import_is_pinned_in_runtime_requirements():
    dist_map = packages_distributions()
    pinned = _runtime_distributions()
    missing = {}
    for module in sorted(_top_level_imports()):
        candidates = {d.lower().replace("_", "-") for d in dist_map.get(module, [])}
        if module in _KNOWN:
            candidates.add(_KNOWN[module])
        if module in _TRANSITIVE_OF:
            candidates.add(_TRANSITIVE_OF[module])
        if not candidates:
            raise PackageNotFoundError(f"cannot map import {module!r} to a distribution")
        if not candidates & pinned:
            missing[module] = sorted(candidates)
    assert not missing, f"imported by app/ but absent from requirements-runtime.txt: {missing}"
