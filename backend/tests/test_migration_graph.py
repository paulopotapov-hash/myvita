"""Structural guard over the Alembic revision graph (no database needed).

Both parents of the 2026-10 integration minted the same revision id for different
migrations; Alembic only warns about that and silently picks one. These checks
turn that into a hard failure.
"""

import re
from pathlib import Path

from alembic.script import ScriptDirectory

from tests.conftest import alembic_config

VERSIONS_DIR = Path(__file__).resolve().parents[1] / "migrations" / "versions"
_REVISION_LINE = re.compile(r'^revision(?::\s*str)?\s*=\s*["\']([0-9a-f]+)["\']', re.MULTILINE)


def test_every_migration_file_has_a_unique_revision_id():
    seen: dict[str, str] = {}
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        match = _REVISION_LINE.search(path.read_text())
        assert match, f"{path.name}: no `revision = ...` line"
        rev = match.group(1)
        assert rev not in seen, f"revision {rev} defined in both {seen[rev]} and {path.name}"
        assert path.name.startswith(rev + "_"), f"{path.name}: filename must start with its revision id {rev}"
        seen[rev] = path.name


def test_revision_graph_has_exactly_one_head():
    script = ScriptDirectory.from_config(alembic_config())
    heads = script.get_heads()
    # The merge revision e1f2a3b4c5d6 is followed by the integration Phase 4 migration,
    # then by clinical results / record visibility / notification events (P2.4-P2.6),
    # the released-result guard, the patient identifiers and address, the clinical history
    # the partial start date of declared medication, scheduling and the origin of the
    # automatic care assignment.
    assert heads == ["8e3f5a7c9b1d"], f"expected a single head, got {heads}"
    assert script.get_revision("8e3f5a7c9b1d").down_revision == "7d2e4b9a1c3f"
    assert script.get_revision("7d2e4b9a1c3f").down_revision == "5f3a9c1e7b2d"
    assert script.get_revision("5f3a9c1e7b2d").down_revision == "a0b1c2d3e4f5"
    assert script.get_revision("a0b1c2d3e4f5").down_revision == "9e0f1a2b3c4d"
    assert script.get_revision("9e0f1a2b3c4d").down_revision == "8d9e0f1a2b3c"
    assert script.get_revision("8d9e0f1a2b3c").down_revision == "7c8d9e0f1a2b"
    assert script.get_revision("7c8d9e0f1a2b").down_revision == "6b7c8d9e0f1a"
    assert script.get_revision("6b7c8d9e0f1a").down_revision == "5a6b7c8d9e0f"
    assert script.get_revision("5a6b7c8d9e0f").down_revision == "e1f2a3b4c5d6"
    # Walking the full graph raises on dangling down_revisions.
    all_revisions = list(script.walk_revisions())
    assert len({r.revision for r in all_revisions}) == len(all_revisions)
