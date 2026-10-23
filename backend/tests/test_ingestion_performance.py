"""Guard ingestion scaling without timing-sensitive test assertions."""

import asyncio
from contextlib import aclosing
from unittest.mock import patch

from app.services.parser_service import CodeParser
from app.db.graph_ops import _embedded_function_batches, _resolve_calls


def test_call_resolution_does_not_rescan_definitions():
    class CountingDefinition(dict):
        name_reads = 0

        def __getitem__(self, key):
            if key == "name":
                type(self).name_reads += 1
            return super().__getitem__(key)

    definitions = [CountingDefinition(
        name="validate", qualified_name="validate", file_path=f"src/{i}.py",
        entity_id=f"fn:{i}",
    ) for i in range(1000)]
    callers = [
        dict(entity_id=f"caller:{i}", qualified_name="caller", file_path=f"src/{i % 1000}.py")
        for i in range(3000)
    ]
    calls, external, ambiguous = _resolve_calls(
        callers, {caller["entity_id"]: ["validate"] for caller in callers}, definitions
    )
    # Each definition is indexed once, however many calls are resolved.
    assert CountingDefinition.name_reads == len(definitions)
    assert len(calls) == 3000 and not external and not ambiguous
    assert all(call["target_id"] == f"fn:{i % 1000}" for i, call in enumerate(calls))
    assert {call["resolution"] for call in calls} == {"lexical_scope"}


def test_parser_does_not_check_every_function_body_for_each_call():
    count = 200
    source = "".join(
        f"def f{i}():\n    target{i}()\n    other{i}()\n" for i in range(count)
    ).encode()
    with patch.object(CodeParser, "_definition_body", wraps=CodeParser._definition_body) as body:
        parsed = asyncio.run(CodeParser().parse_file("src/large.py", source, repository="test/repo"))
    assert body.call_count <= 3 * count
    for i, function in enumerate(parsed["functions"]):
        assert [call["name"] for call in function["calls"]] == [f"target{i}", f"other{i}"]


def test_embedding_groups_keep_all_definitions_and_bound_parallel_requests():
    functions = [
        dict(entity_id=f"fn:{i}", qualified_name=f"f{i % 5}", file_path="a.py")
        for i in range(10)
    ]
    active = peak = 0
    requested = []

    async def generate(texts):
        nonlocal active, peak
        active += 1
        peak = max(active, peak)
        requested.extend(texts)
        await asyncio.sleep(0)
        active -= 1
        return [[float(text.split("\n")[0][-1])] for text in texts]

    async def collect():
        return [row async for batch in _embedded_function_batches(functions) for row in batch]

    with (
        patch("app.db.graph_ops.EMBEDDING_REQUEST_BATCH_SIZE", 2),
        patch("app.db.graph_ops.MAX_CONCURRENT_EMBEDDING_REQUESTS", 2),
        patch("app.db.graph_ops.generate_embeddings", side_effect=generate),
    ):
        embedded = asyncio.run(collect())
    assert peak == 2
    assert len(requested) == len(set(requested)) == 5
    assert {row["entity_id"] for row in embedded} == {f"fn:{i}" for i in range(10)}
    for row in embedded:
        assert row["embedding"] == [float(row["qualified_name"][-1])]


def test_failed_consumer_cancels_embedding_prefetch():
    functions = [dict(entity_id=f"fn:{i}", qualified_name=f"f{i}", file_path="a.py") for i in range(4)]
    active = 0

    async def generate(texts):
        nonlocal active
        active += 1
        try:
            if texts[0].startswith("Function: f0\n"):
                await asyncio.sleep(0)
                return [[0.1]]
            await asyncio.Event().wait()
        finally:
            active -= 1

    async def fail_write():
        async with aclosing(_embedded_function_batches(functions)) as batches:
            async for _ in batches:
                raise RuntimeError("database write failed")

    with (
        patch("app.db.graph_ops.EMBEDDING_REQUEST_BATCH_SIZE", 1),
        patch("app.db.graph_ops.generate_embeddings", side_effect=generate),
    ):
        try:
            asyncio.run(fail_write())
        except RuntimeError as exc:
            assert str(exc) == "database write failed"
        else:
            raise AssertionError("consumer should fail")
    assert active == 0
