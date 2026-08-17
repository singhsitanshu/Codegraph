import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

import tree_sitter_python
from tree_sitter import Language, Node, Parser

from database import Neo4jDatabase


PYTHON_LANGUAGE = Language(tree_sitter_python.language())


def node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8")


def callable_name(node: Node | None, source: bytes) -> str | None:
    """Return a readable name for direct and attribute calls."""
    if node is None:
        return None
    if node.type in {"identifier", "attribute"}:
        return node_text(node, source)
    # For expressions such as factory()(), preserve that a call exists without
    # pretending that static analysis can resolve its target.
    return node_text(node, source) or None


def analyze_python(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source = path.read_bytes()
    tree = Parser(PYTHON_LANGUAGE).parse(source)
    resolved_path = str(path.resolve())
    definitions: list[dict[str, Any]] = []
    raw_calls: list[tuple[str, str, int]] = []

    module_id = f"{resolved_path}::<module>"
    definitions.append(
        {
            "id": module_id,
            "name": "<module>",
            "qualified_name": "<module>",
            "file": resolved_path,
            "line": 1,
            "external": False,
        }
    )

    def walk(node: Node, scopes: tuple[str, ...], caller_id: str) -> None:
        next_scopes = scopes
        next_caller = caller_id

        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                next_scopes = (*scopes, node_text(name_node, source))

        if node.type in {"function_definition", "async_function_definition"}:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = node_text(name_node, source)
                qualified_name = ".".join((*scopes, name))
                next_caller = f"{resolved_path}::{qualified_name}"
                next_scopes = (*scopes, name)
                definitions.append(
                    {
                        "id": next_caller,
                        "name": name,
                        "qualified_name": qualified_name,
                        "file": resolved_path,
                        "line": node.start_point.row + 1,
                        "external": False,
                    }
                )

        if node.type == "call":
            target = callable_name(node.child_by_field_name("function"), source)
            if target:
                raw_calls.append((next_caller, target, node.start_point.row + 1))

        for child in node.named_children:
            walk(child, next_scopes, next_caller)

    walk(tree.root_node, (), module_id)

    by_qualified = {item["qualified_name"]: item for item in definitions}
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in definitions:
        by_name[item["name"]].append(item)

    edge_lines: dict[tuple[str, str], list[int]] = defaultdict(list)
    external_nodes: dict[str, dict[str, Any]] = {}
    for caller_id, target, line in raw_calls:
        short_name = target.rsplit(".", 1)[-1]
        candidates = by_name.get(short_name, [])
        if target in by_qualified:
            callee_id = by_qualified[target]["id"]
        elif len(candidates) == 1:
            callee_id = candidates[0]["id"]
        else:
            callee_id = f"external::{target}"
            external_nodes.setdefault(
                callee_id,
                {
                    "id": callee_id,
                    "name": short_name,
                    "qualified_name": target,
                    "file": None,
                    "line": None,
                    "external": True,
                },
            )
        edge_lines[(caller_id, callee_id)].append(line)

    calls = [
        {"caller_id": caller, "callee_id": callee, "locations": lines}
        for (caller, callee), lines in edge_lines.items()
    ]
    return [*definitions, *external_nodes.values()], calls


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a Python call graph to Neo4j")
    parser.add_argument("path", type=Path, help="Python file to analyze")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print results without writing to Neo4j"
    )
    args = parser.parse_args()

    if not args.path.is_file() or args.path.suffix != ".py":
        parser.error("path must point to an existing .py file")

    functions, calls = analyze_python(args.path)
    print(f"Functions: {functions}")
    print(f"Calls: {calls}")

    if not args.dry_run:
        with Neo4jDatabase() as database:
            database.verify_connectivity()
            database.write_call_graph(functions, calls)
        print("Call graph written to Neo4j")


if __name__ == "__main__":
    main()
