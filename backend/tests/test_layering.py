"""Import direction between persistence modules and the rest of the backend.

Code is grouped by feature, so each feature package mixes Neo4j query modules
with the application code that uses them. These rules keep the query modules
at the bottom: they may use the driver, settings, and shared constants, but
never application services, the agent, webhooks, or the ASGI entrypoint.
"""

import ast
from pathlib import Path

import pytest


APP_ROOT = Path(__file__).resolve().parents[1] / "app"

PERSISTENCE_MODULES = (
    "app.database.driver",
    "app.database.errors",
    "app.graph.schema",
    "app.graph.writer",
    "app.graph.queries",
    "app.communities.clustering",
    "app.communities.store",
    "app.agent.code_queries",
)

APPLICATION_MODULES = (
    "app.main",
    "app.webhooks",
    "app.agent.graph",
    "app.ingestion",
    "app.parsing",
    "app.embeddings.generation",
    "app.embeddings.cache",
    "app.graph.view",
    "app.communities.summarizer",
)


def _module_path(module: str) -> Path:
    return APP_ROOT.parent.joinpath(*module.split(".")).with_suffix(".py")


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(APP_ROOT.parent).with_suffix("").parts)


def _imports(path: Path) -> list[ast.Import | ast.ImportFrom]:
    return [
        node
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in _imports(path):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif node.module:
            modules.add(node.module)
            # ``from app.graph import view`` imports the module app.graph.view.
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def _opens_driver_sessions(path: Path) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "app.database.driver"
        and any(alias.name == "get_neo4j_driver" for alias in node.names)
        for node in _imports(path)
    )


@pytest.mark.parametrize("module", PERSISTENCE_MODULES)
def test_persistence_does_not_import_application_code(module: str) -> None:
    imported = _imported_modules(_module_path(module))

    assert not {
        name
        for name in imported
        if any(
            name == application or name.startswith(f"{application}.")
            for application in APPLICATION_MODULES
        )
    }


def test_every_module_using_the_driver_is_a_persistence_module() -> None:
    driver_users = {
        _module_name(path)
        for path in APP_ROOT.rglob("*.py")
        if _opens_driver_sessions(path)
    }

    assert driver_users <= set(PERSISTENCE_MODULES)


def test_agent_reads_the_graph_through_query_modules() -> None:
    imported = _imported_modules(_module_path("app.agent.graph"))

    assert "app.database.driver" not in imported
    assert "neo4j" not in imported
