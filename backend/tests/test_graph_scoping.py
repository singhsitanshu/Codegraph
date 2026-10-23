"""Unit coverage for repository-scoped, micro-batched Neo4j writes."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db import (
    GRAPH_QUERY,
    NODE_CODE_QUERY,
    REPOSITORY_TOKEN_QUERY,
    fetch_repository_total_tokens,
)
from app.db.graph_ops import (
    DELETE_FILES_QUERY,
    DELETE_ORPHAN_EXTERNAL_FUNCTIONS_QUERY,
    DELETE_OUTGOING_CALLS_QUERY,
    DELETE_REPOSITORY_QUERY,
    DELETE_STALE_FUNCTIONS_QUERY,
    FETCH_EXISTING_DEFINITIONS_QUERY,
    MERGE_CALLS_QUERY,
    MERGE_EXTERNAL_CALLS_QUERY,
    MERGE_FILES_QUERY,
    MERGE_FUNCTIONS_QUERY,
    MERGE_REPOSITORY_TOKENS_QUERY,
    chunk_data,
    save_parsed_ast_to_neo4j,
)
from app.services.parser_service import CodeParser
from app.utils.entity_identity import generate_function_entity_id


REPO = "owner/repository-a"


def _mock_driver(existing_definitions=None):
    transaction = MagicMock()
    transaction.run = AsyncMock()
    transaction.run.return_value.consume = AsyncMock()
    session = MagicMock()

    async def execute_write(callback):
        await callback(transaction)

    session.execute_write = AsyncMock(side_effect=execute_write)
    read_result = MagicMock()
    read_result.data = AsyncMock(return_value=existing_definitions or [])
    session.run = AsyncMock(return_value=read_result)
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)
    driver = MagicMock()
    driver.session.return_value = session_context
    return driver, session, transaction


async def _fake_embeddings(texts: list[str]) -> list[list[float]]:
    return [[0.1, 0.2, 0.3] for _ in texts]


def _parse(file_path: str, source: str, repository: str = REPO) -> dict:
    return asyncio.run(
        CodeParser().parse_file(
            file_path,
            source.encode("utf-8"),
            repository=repository,
        )
    )


def _save(driver, parsed_data, repo_name=REPO, **kwargs):
    with (
        patch("app.db.graph_ops.get_neo4j_driver", return_value=driver),
        patch(
            "app.db.graph_ops.generate_embeddings",
            side_effect=_fake_embeddings,
        ) as embed_batch,
        patch(
            "app.db.graph_ops.run_leiden_clustering",
            new=AsyncMock(),
        ) as cluster_graph,
        patch(
            "app.db.graph_ops.label_and_store_communities",
            new=AsyncMock(),
        ) as label_communities,
    ):
        asyncio.run(save_parsed_ast_to_neo4j(parsed_data, repo_name, **kwargs))
    return embed_batch, cluster_graph, label_communities


def _batches(transaction, query):
    return [
        item
        for call in transaction.run.await_args_list
        if call.args[0] == query
        for item in call.kwargs["batch"]
    ]


def _functions_by_name(transaction):
    functions: dict[str, list[dict]] = {}
    for function in _batches(transaction, MERGE_FUNCTIONS_QUERY):
        functions.setdefault(function["qualified_name"], []).append(function)
    return functions


def test_graph_read_starts_from_repository_scoped_files() -> None:
    assert "MATCH (file:File {repo_name: $repo_name})" in GRAPH_QUERY
    assert "Function {repo_name: $repo_name}" in GRAPH_QUERY
    assert "(m {repo_name: $repo_name})" in GRAPH_QUERY
    assert "IN_COMMUNITY" in GRAPH_QUERY
    assert "n_community.name AS n_community_name" in GRAPH_QUERY
    assert "\nMATCH (n)\n" not in GRAPH_QUERY


def test_function_write_merges_by_entity_id_not_simple_name() -> None:
    assert (
        "MERGE (fn:Function {entity_id: func.entity_id, repo_name: $repo_name})"
        in MERGE_FUNCTIONS_QUERY
    )
    assert "name: func.name" not in MERGE_FUNCTIONS_QUERY
    assert "fn.raw_code = func.raw_code" in MERGE_FUNCTIONS_QUERY
    assert "fn.qualified_name = func.qualified_name" in MERGE_FUNCTIONS_QUERY
    assert "entity_id: call.caller_id" in MERGE_CALLS_QUERY
    assert "entity_id: call.target_id" in MERGE_CALLS_QUERY
    assert "entity_id: call.caller_id" in MERGE_EXTERNAL_CALLS_QUERY


def test_node_code_read_uses_graph_id_and_repository_scope() -> None:
    assert "elementId(function) = $node_id" in NODE_CODE_QUERY
    assert "repo_name: $repo_name" in NODE_CODE_QUERY
    assert "function.raw_code AS code" in NODE_CODE_QUERY


def test_chunk_data_uses_bounded_slices() -> None:
    chunks = list(chunk_data(list(range(205))))

    assert [len(chunk) for chunk in chunks] == [100, 100, 5]
    assert [item for chunk in chunks for item in chunk] == list(range(205))


def test_three_pass_write_receives_repository_scope() -> None:
    driver, session, transaction = _mock_driver()
    parsed_file = _parse(
        "src/example.py",
        "def example():\n    external_call()\n",
    )
    entity_id = parsed_file["functions"][0]["entity_id"]

    embed_batch, cluster_graph, label_communities = _save(
        driver,
        [parsed_file],
        replace_existing=True,
    )

    assert [call.args[0] for call in transaction.run.await_args_list] == [
        DELETE_REPOSITORY_QUERY,
        MERGE_FILES_QUERY,
        MERGE_FUNCTIONS_QUERY,
        MERGE_EXTERNAL_CALLS_QUERY,
    ]
    session.run.assert_not_awaited()
    assert transaction.run.await_args_list[1].kwargs["batch"] == [
        {"path": "src/example.py"}
    ]
    assert transaction.run.await_args_list[2].kwargs["batch"] == [
        {
            "entity_id": entity_id,
            "name": "example",
            "qualified_name": "example",
            "file_path": "src/example.py",
            "language": "python",
            "signature": "()",
            "definition_discriminator": "signature:();occurrence:1",
            "start_line": 1,
            "end_line": 2,
            "start_column": 0,
            "end_column": 19,
            "raw_code": "def example():\n    external_call()",
            "ambiguous_calls": [],
            "embedding": [0.1, 0.2, 0.3],
        }
    ]
    assert transaction.run.await_args_list[3].kwargs["batch"] == [
        {
            "caller_id": entity_id,
            "target_name": "external_call",
            "call_count": 1,
            "file_path": "src/example.py",
        }
    ]
    for call in transaction.run.await_args_list:
        assert call.kwargs["repo_name"] == REPO
        assert "$repo_name" in call.args[0]
    embed_batch.assert_awaited_once_with(
        ["Function: example\nFile: src/example.py"]
    )
    cluster_graph.assert_awaited_once_with(REPO)
    label_communities.assert_awaited_once_with(REPO)


def test_same_named_definitions_remain_separate_functions() -> None:
    driver, _, transaction = _mock_driver()
    parsed_data = [
        _parse(
            "src/a.py",
            "def helper():\n    pass\n\n"
            "def main():\n    helper()\n\n"
            "class Alpha:\n    def run(self):\n        pass\n",
        ),
        _parse(
            "src/b.py",
            "def helper():\n    pass\n\n"
            "class Beta:\n    def run(self):\n        helper()\n",
        ),
    ]

    _save(driver, parsed_data, replace_existing=True)

    functions = _functions_by_name(transaction)
    persisted = _batches(transaction, MERGE_FUNCTIONS_QUERY)
    assert len({function["entity_id"] for function in persisted}) == 5
    assert [function["file_path"] for function in functions["helper"]] == [
        "src/a.py",
        "src/b.py",
    ]
    assert {function["name"] for function in persisted} == {
        "helper",
        "main",
        "run",
    }
    assert set(functions) == {"helper", "main", "Alpha.run", "Beta.run"}

    a_helper, b_helper = functions["helper"]
    calls = _batches(transaction, MERGE_CALLS_QUERY)
    assert sorted(
        (call["caller_id"], call["target_id"], call["resolution"])
        for call in calls
    ) == sorted(
        [
            (functions["main"][0]["entity_id"], a_helper["entity_id"], "lexical_scope"),
            (functions["Beta.run"][0]["entity_id"], b_helper["entity_id"], "lexical_scope"),
        ]
    )


def test_call_resolution_prefers_scope_then_file_then_unique_name() -> None:
    driver, _, transaction = _mock_driver()
    parsed_data = [
        _parse(
            "src/service.py",
            "class Service:\n"
            "    def validate(self):\n"
            "        self.check()\n"
            "        self.check()\n"
            "        util()\n"
            "        shared()\n"
            "    def check(self):\n"
            "        pass\n",
        ),
        _parse("src/utils.py", "def util():\n    pass\n"),
        _parse("src/one.py", "def shared():\n    pass\n"),
        _parse("src/two.py", "def shared():\n    pass\n"),
    ]

    _save(driver, parsed_data, replace_existing=True)

    functions = _functions_by_name(transaction)
    validate = functions["Service.validate"][0]
    calls = {
        call["target_id"]: call
        for call in _batches(transaction, MERGE_CALLS_QUERY)
    }
    check_call = calls[functions["Service.check"][0]["entity_id"]]
    util_call = calls[functions["util"][0]["entity_id"]]
    assert (check_call["resolution"], check_call["call_count"]) == (
        "lexical_scope",
        2,
    )
    assert util_call["resolution"] == "repository_unique"
    assert all(
        call["target_id"] not in {f["entity_id"] for f in functions["shared"]}
        for call in calls.values()
    )
    assert validate["ambiguous_calls"] == ["shared"]
    assert _batches(transaction, MERGE_EXTERNAL_CALLS_QUERY) == []


def test_typescript_declaration_only_overloads_are_not_persisted() -> None:
    driver, _, transaction = _mock_driver()
    parsed_file = _parse(
        "src/format.ts",
        "function format(value: string): string;\n"
        "function format(value: number): string;\n"
        "function format(value: any): string { return String(value); }\n",
    )
    assert len(parsed_file["functions"]) == 3

    _save(driver, [parsed_file], replace_existing=True)

    persisted = _batches(transaction, MERGE_FUNCTIONS_QUERY)
    assert [function["signature"] for function in persisted] == ["(value: any)"]


def test_writer_generates_missing_entity_ids_with_the_cg002a_utility() -> None:
    driver, _, transaction = _mock_driver()
    parsed_file = asyncio.run(
        CodeParser().parse_file("src/example.py", b"def example():\n    pass\n")
    )
    assert "entity_id" not in parsed_file["functions"][0]

    _save(driver, [parsed_file], replace_existing=True)

    assert _batches(transaction, MERGE_FUNCTIONS_QUERY)[0]["entity_id"] == (
        generate_function_entity_id(
            REPO,
            "src/example.py",
            "python",
            "example",
            "signature:();occurrence:1",
        )
    )


def test_entity_id_scoped_to_another_repository_is_rejected() -> None:
    driver, session, _ = _mock_driver()
    parsed_file = _parse(
        "src/example.py",
        "def example():\n    pass\n",
        repository="someone/else",
    )

    with pytest.raises(ValueError, match="entity_id"):
        _save(driver, [parsed_file], replace_existing=True)
    session.execute_write.assert_not_awaited()


def test_absolute_parsed_paths_are_rejected_before_writing() -> None:
    driver, session, _ = _mock_driver()
    parsed_file = asyncio.run(
        CodeParser().parse_file("/tmp/checkout/example.py", b"def example(): pass\n")
    )

    with pytest.raises(ValueError, match="repository-relative"):
        _save(driver, [parsed_file], replace_existing=True)
    session.execute_write.assert_not_awaited()


def test_functions_without_identity_metadata_are_skipped() -> None:
    driver, _, transaction = _mock_driver()
    parsed_data = [
        {
            "file_path": "src/legacy.py",
            "defined_functions": ["legacy"],
            "functions": [{"name": "legacy", "raw_code": "def legacy(): pass"}],
            "outgoing_calls": ["other"],
        }
    ]

    _save(driver, parsed_data, replace_existing=True)

    assert [call.args[0] for call in transaction.run.await_args_list] == [
        DELETE_REPOSITORY_QUERY,
        MERGE_FILES_QUERY,
    ]


def test_large_repository_uses_one_transaction_per_micro_batch() -> None:
    driver, session, transaction = _mock_driver()
    parsed_data = [
        {
            "file_path": f"src/file_{index}.py",
            "functions": [
                {
                    "name": f"function_{index}",
                    "qualified_name": f"function_{index}",
                    "language": "python",
                    "definition_discriminator": "signature:();occurrence:1",
                    "raw_code": "",
                }
            ],
        }
        for index in range(205)
    ]

    embed_batch, cluster_graph, label_communities = _save(
        driver,
        parsed_data,
        repo_name="owner/large-repository",
        replace_existing=True,
    )

    # One replacement, three file chunks, three function chunks, no calls.
    assert session.execute_write.await_count == 7
    batch_calls = [
        call
        for call in transaction.run.await_args_list
        if "batch" in call.kwargs
    ]
    assert [len(call.kwargs["batch"]) for call in batch_calls] == [
        100,
        100,
        5,
        100,
        100,
        5,
    ]
    assert [
        len(call.args[0]) for call in embed_batch.await_args_list
    ] == [100, 100, 5]
    cluster_graph.assert_awaited_once_with("owner/large-repository")
    label_communities.assert_awaited_once_with("owner/large-repository")


def test_incremental_write_replaces_only_affected_files() -> None:
    existing_id = generate_function_entity_id(
        REPO, "src/other.py", "python", "shared", "signature:();occurrence:1"
    )
    driver, session, transaction = _mock_driver(
        [
            {
                "entity_id": existing_id,
                "name": "shared",
                "qualified_name": "shared",
                "file_path": "src/other.py",
            }
        ]
    )
    parsed_file = _parse("src/a.py", "def caller():\n    shared()\n")
    caller_id = parsed_file["functions"][0]["entity_id"]

    _save(
        driver,
        [parsed_file],
        deleted_file_paths=["src/gone.py", "src/a.py"],
    )

    session.run.assert_awaited_once_with(
        FETCH_EXISTING_DEFINITIONS_QUERY,
        repo_name=REPO,
        paths=["src/a.py", "src/gone.py"],
    )
    runs = transaction.run.await_args_list
    assert [call.args[0] for call in runs] == [
        DELETE_FILES_QUERY,
        DELETE_STALE_FUNCTIONS_QUERY,
        DELETE_OUTGOING_CALLS_QUERY,
        MERGE_FILES_QUERY,
        MERGE_FUNCTIONS_QUERY,
        MERGE_CALLS_QUERY,
        DELETE_ORPHAN_EXTERNAL_FUNCTIONS_QUERY,
    ]
    assert runs[0].kwargs["paths"] == ["src/gone.py"]
    assert runs[1].kwargs["paths"] == ["src/a.py", "src/gone.py"]
    assert runs[1].kwargs["entity_ids"] == [caller_id]
    assert runs[2].kwargs["paths"] == ["src/a.py"]
    assert runs[5].kwargs["batch"] == [
        {
            "caller_id": caller_id,
            "target_id": existing_id,
            "resolution": "repository_unique",
            "call_count": 1,
            "file_path": "src/a.py",
        }
    ]


def test_incremental_cleanup_queries_stay_repository_scoped() -> None:
    for query in (
        FETCH_EXISTING_DEFINITIONS_QUERY,
        DELETE_FILES_QUERY,
        DELETE_STALE_FUNCTIONS_QUERY,
        DELETE_OUTGOING_CALLS_QUERY,
        DELETE_ORPHAN_EXTERNAL_FUNCTIONS_QUERY,
    ):
        assert "{repo_name: $repo_name}" in query
    assert "fn.entity_id IS NULL" in DELETE_STALE_FUNCTIONS_QUERY


def test_external_targets_are_not_function_definitions() -> None:
    assert (
        "MERGE (target:ExternalFunction {name: call.target_name, "
        "repo_name: $repo_name})"
    ) in MERGE_EXTERNAL_CALLS_QUERY
    assert "target:Function" not in MERGE_EXTERNAL_CALLS_QUERY
    assert "target.is_external = true" in MERGE_EXTERNAL_CALLS_QUERY


def test_repository_replacement_includes_community_and_external_nodes() -> None:
    assert "node:Community" in DELETE_REPOSITORY_QUERY
    assert "node:Repository" in DELETE_REPOSITORY_QUERY
    assert "node:ExternalFunction" in DELETE_REPOSITORY_QUERY


def test_full_ingestion_stores_repository_token_baseline() -> None:
    driver, _, transaction = _mock_driver()
    parsed_data = [
        {
            "file_path": "src/example.py",
            "functions": [],
            "source_tokens": 37,
        },
        {
            "file_path": "src/helper.py",
            "functions": [],
            "source_tokens": 13,
        },
    ]

    _save(driver, parsed_data, repo_name="owner/repository", replace_existing=True)

    metadata_call = next(
        call
        for call in transaction.run.await_args_list
        if call.args[0] == MERGE_REPOSITORY_TOKENS_QUERY
    )
    assert metadata_call.kwargs == {
        "repo_name": "owner/repository",
        "total_tokens": 50,
        "tokenizer_model": "gpt-4o",
    }
    assert "MERGE (repository)-[:CONTAINS]->(f)" in MERGE_FILES_QUERY


def test_repository_token_baseline_read_is_scoped() -> None:
    result = MagicMock()
    result.single = AsyncMock(return_value={"total_tokens": 12_345})
    session = MagicMock()
    session.run = AsyncMock(return_value=result)
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)
    driver = MagicMock()
    driver.session.return_value = session_context

    with patch("app.db.get_neo4j_driver", return_value=driver):
        total = asyncio.run(
            fetch_repository_total_tokens("owner/repository")
        )

    assert total == 12_345
    session.run.assert_awaited_once_with(
        REPOSITORY_TOKEN_QUERY,
        repo_name="owner/repository",
    )


def test_incremental_write_keeps_repository_token_baseline() -> None:
    driver, _, transaction = _mock_driver()
    parsed_file = _parse("src/a.py", "def a():\n    pass\n")
    parsed_file["source_tokens"] = 9

    _save(driver, [parsed_file])

    assert MERGE_REPOSITORY_TOKENS_QUERY not in [
        call.args[0] for call in transaction.run.await_args_list
    ]
