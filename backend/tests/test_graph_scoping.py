"""Regression coverage for identity-based graph persistence."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db import GRAPH_QUERY, NODE_CODE_QUERY
from app.db.graph_ops import (
    CHECK_REPOSITORY_STATE_QUERY, DELETE_FILE_CALLS_QUERY,
    DELETE_FILE_FUNCTIONS_QUERY, DELETE_FILES_QUERY, DELETE_REPOSITORY_QUERY,
    MARK_REPOSITORY_BUILDING_QUERY, MARK_REPOSITORY_READY_QUERY,
    MERGE_CALLS_QUERY, MERGE_FILES_QUERY, MERGE_FUNCTIONS_QUERY,
    MERGE_REPOSITORY_TOKENS_QUERY, MERGE_UNRESOLVED_CALLS_QUERY,
    _extract_etl_records, chunk_data,
    save_parsed_ast_to_neo4j,
)
from app.services.parser_service import CodeParser

REPO = "owner/repository"


def parse(path, source):
    return asyncio.run(CodeParser().parse_file(path, source, repository=REPO))


def mock_driver(state=None):
    tx = MagicMock()
    result = MagicMock()
    result.consume = AsyncMock()
    result.single = AsyncMock(return_value=state)
    tx.run = AsyncMock(return_value=result)
    session = MagicMock()
    async def execute_write(callback):
        await callback(tx)
    session.execute_write = AsyncMock(side_effect=execute_write)
    session.run = AsyncMock(return_value=result)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    driver = MagicMock()
    driver.session.return_value = context
    return driver, session, tx


async def fake_embeddings(texts):
    return [[0.1, 0.2, 0.3] for _ in texts]


def persist(parsed, *, replace=True, deleted=None, state=None):
    driver, session, tx = mock_driver(state)
    with (
        patch("app.db.graph_ops.get_neo4j_driver", return_value=driver),
        patch("app.db.graph_ops.generate_embeddings", side_effect=fake_embeddings),
        patch("app.db.graph_ops.run_leiden_clustering", new=AsyncMock()),
        patch("app.db.graph_ops.label_and_store_communities", new=AsyncMock()),
    ):
        asyncio.run(save_parsed_ast_to_neo4j(
            parsed, REPO, replace_existing=replace, deleted_file_paths=deleted,
        ))
    return session, tx


def batch_for(tx, query):
    return [call.kwargs["batch"] for call in tx.run.await_args_list if call.args[0] == query]


def test_read_and_write_queries_preserve_identity_and_compatibility():
    assert "graph_state: 'ready'" in GRAPH_QUERY
    assert "HAS_UNRESOLVED_CALL" in GRAPH_QUERY
    assert "elementId(function) = $node_id" in NODE_CODE_QUERY
    assert "repo_name: $repo_name" in NODE_CODE_QUERY
    assert "graph_state: 'ready'" in NODE_CODE_QUERY
    assert "entity_id: func.entity_id" in MERGE_FUNCTIONS_QUERY
    assert "fn.raw_code = func.raw_code" in MERGE_FUNCTIONS_QUERY
    assert "MERGE (f)-[:DEFINES]->(fn)" in MERGE_FUNCTIONS_QUERY
    assert "entity_id: call.caller_id" in MERGE_CALLS_QUERY
    assert "entity_id: call.target_id" in MERGE_CALLS_QUERY
    assert "UnresolvedCall:ExternalFunction" in MERGE_UNRESOLVED_CALLS_QUERY


def test_same_names_scopes_overloads_and_repeats_remain_distinct():
    parsed = [
        parse("src/a.py", b"def validate(): pass\n"),
        parse("src/b.py", b"def validate(): pass\n"),
        parse("src/c.py", b"class A:\n def validate(self): pass\nclass B:\n def validate(self): pass\n"),
        parse("src/d.py", b"def f(x): pass\ndef f(x): pass\n"),
        parse("src/V.java", b"class V { void f(String x) {} void f(int x) {} }"),
        parse("src/v.ts", b"class V { f(x: string): void; f(x: number): void; f(x: any): void {} }"),
    ]
    files, funcs, _, _ = _extract_etl_records(parsed, REPO)
    assert len(files) == 6
    assert len(funcs) == sum(len(p["functions"]) for p in parsed)
    assert len({f["entity_id"] for f in funcs}) == len(funcs)
    assert len([f for f in funcs if f["file_path"] == "src/v.ts"]) == 3
    assert len([f for f in funcs if f["file_path"] == "src/V.java"]) == 2
    _, tx = persist(parsed)
    written = [f for batch in batch_for(tx, MERGE_FUNCTIONS_QUERY) for f in batch]
    assert {f["entity_id"] for f in written} == {f["entity_id"] for f in funcs}
    assert {f["file_path"] for f in written} == {f["file_path"] for f in funcs}


def test_call_attribution_and_unresolved_sites():
    parsed = parse("src/work.py", b"def helper(): pass\ndef first():\n helper()\ndef second():\n external()\noutside()\n")
    _, funcs, linked, unresolved = _extract_etl_records([parsed], REPO)
    ids = {f["name"]: f["entity_id"] for f in funcs}
    assert len(linked) == 1
    assert (linked[0]["caller_id"], linked[0]["target_id"]) == (ids["first"], ids["helper"])
    assert linked[0]["resolution_status"] == "inferred"
    assert {(c["name"], c["caller_id"]) for c in unresolved} == {
        ("external", ids["second"]), ("outside", None)
    }
    session, tx = persist([parsed])
    assert len(batch_for(tx, MERGE_CALLS_QUERY)[0]) == 1
    assert len(batch_for(tx, MERGE_UNRESOLVED_CALLS_QUERY)[0]) == 2
    assert session.run.await_args_list[-1].args[0] == MARK_REPOSITORY_READY_QUERY


def test_ambiguous_and_dynamic_targets_create_no_calls_edge():
    parsed = parse("src/work.py", b"def validate(): pass\ndef validate(): pass\ndef caller():\n validate()\n obj.validate()\n")
    _, _, linked, unresolved = _extract_etl_records([parsed], REPO)
    assert linked == []
    assert len(unresolved) == 2
    assert all(c["resolution_status"] == "ambiguous" for c in unresolved)
    assert len({c["call_id"] for c in unresolved}) == 2


def test_cross_file_name_without_binding_stays_unresolved():
    parsed = [parse("src/a.py", b"def caller():\n validate()\n"), parse("src/b.py", b"def validate(): pass\n")]
    _, _, linked, unresolved = _extract_etl_records(parsed, REPO)
    assert linked == []
    assert unresolved[0]["provenance"] == "insufficient_binding_evidence"


def test_full_write_marks_building_then_ready_and_scopes_all_writes():
    parsed = parse("src/work.py", b"def f(): pass\n")
    session, tx = persist([parsed])
    queries = [c.args[0] for c in tx.run.await_args_list]
    assert queries[:2] == [DELETE_REPOSITORY_QUERY, MARK_REPOSITORY_BUILDING_QUERY]
    assert queries[-2:] == [MERGE_FILES_QUERY, MERGE_FUNCTIONS_QUERY]
    assert session.run.await_args_list[-1].args[0] == MARK_REPOSITORY_READY_QUERY
    assert all(c.kwargs["repo_name"] == REPO for c in tx.run.await_args_list)


def test_incremental_deletes_all_affected_file_entities_before_rewrite():
    parsed = parse("src/new.py", b"def f(): pass\n")
    session, tx = persist([parsed], replace=False, deleted=["src/old.py"], state={"graph_state": "ready", "legacy_count": 0})
    assert session.run.await_args_list[0].args[0] == CHECK_REPOSITORY_STATE_QUERY
    assert [c.args[0] for c in tx.run.await_args_list[:4]] == [
        MARK_REPOSITORY_BUILDING_QUERY, DELETE_FILE_FUNCTIONS_QUERY,
        DELETE_FILE_CALLS_QUERY, DELETE_FILES_QUERY,
    ]
    assert all(c.kwargs["paths"] == ["src/new.py", "src/old.py"] for c in tx.run.await_args_list[1:4])
    assert session.run.await_args_list[-1].args[0] == MARK_REPOSITORY_READY_QUERY


def test_incremental_does_not_replace_full_repository_token_baseline():
    parsed = parse("src/new.py", b"def f(): pass\n")
    parsed["source_tokens"] = 7
    _, tx = persist([parsed], replace=False, state={"graph_state": "ready", "legacy_count": 0})
    assert MERGE_REPOSITORY_TOKENS_QUERY not in [c.args[0] for c in tx.run.await_args_list]


@pytest.mark.parametrize("state", [None, {"graph_state": None, "legacy_count": 1}, {"graph_state": "building", "legacy_count": 0}])
def test_incremental_requires_identity_based_ready_graph(state):
    driver, session, tx = mock_driver(state)
    with patch("app.db.graph_ops.get_neo4j_driver", return_value=driver):
        with pytest.raises(ValueError, match="rebuild"):
            asyncio.run(save_parsed_ast_to_neo4j([parse("src/f.py", b"def f(): pass\n")], REPO))
    tx.run.assert_not_awaited()
    session.run.assert_awaited_once()


def test_bad_parser_identity_is_rejected():
    parsed = parse("src/f.py", b"def f(): pass\n")
    parsed["functions"][0]["entity_id"] = "wrong"
    with pytest.raises(ValueError, match="canonical"):
        _extract_etl_records([parsed], REPO)


def test_chunk_data_is_bounded():
    assert [len(c) for c in chunk_data(list(range(205)))] == [100, 100, 5]
