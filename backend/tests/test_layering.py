"""Import direction between backend layers."""

import ast
from pathlib import Path

import pytest


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize(
    "path",
    sorted((APP_ROOT / "db").glob("*.py")),
    ids=lambda path: path.name,
)
def test_persistence_does_not_import_higher_layers(path: Path) -> None:
    higher_layers = ("app.services", "app.agent", "app.api", "app.main")

    imported = _imported_modules(path)

    assert not {
        module
        for module in imported
        if module.startswith(higher_layers)
    }


def test_agent_reads_the_graph_through_query_modules() -> None:
    imported = _imported_modules(APP_ROOT / "agent" / "graph.py")

    assert "app.db.driver" not in imported
    assert "neo4j" not in imported
