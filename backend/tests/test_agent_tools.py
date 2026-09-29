"""Unit tests for the repository-scoped LangGraph traversal tools."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.graph import (
    ARCHITECTURAL_SUBSYSTEMS_QUERY,
    CALLERS_QUERY,
    CODE_AGENT_SYSTEM_PROMPT,
    CODEBASE_STRUCTURE_QUERY,
    EXTERNAL_DEPENDENCIES_QUERY,
    FUNCTIONS_IN_FILE_QUERY,
    OUTGOING_DEPENDENCIES_QUERY,
    SEMANTIC_CODE_SEARCH_QUERY,
    _get_code_agent,
    _tool_context_text,
    analyze_architectural_subsystems,
    ask_code_agent_with_metrics,
    list_external_dependencies,
    list_codebase_structure,
    list_functions_in_file,
    query_graph_blast_radius,
    query_outgoing_dependencies,
    semantic_code_search,
)


def test_code_agent_system_prompt_requires_structured_markdown() -> None:
    rendered_prompt = CODE_AGENT_SYSTEM_PROMPT.format(
        repo_name="owner/repository"
    )

    assert "expert Senior Staff Engineer" in rendered_prompt
    assert "Never output large walls of text" in rendered_prompt
    assert "Markdown headings (`##`)" in rendered_prompt
    assert "bullet points or numbered lists" in rendered_prompt
    assert "`api.py`" in rendered_prompt
    assert "```python" in rendered_prompt
    assert "owner/repository" in rendered_prompt
    assert "analyze_architectural_subsystems" in rendered_prompt
    assert "labeled architectural" in rendered_prompt
    assert "function count" in rendered_prompt


def test_agent_reads_only_completed_repository_graphs() -> None:
    for query in (
        CALLERS_QUERY, CODEBASE_STRUCTURE_QUERY, FUNCTIONS_IN_FILE_QUERY,
        OUTGOING_DEPENDENCIES_QUERY, EXTERNAL_DEPENDENCIES_QUERY,
        SEMANTIC_CODE_SEARCH_QUERY, ARCHITECTURAL_SUBSYSTEMS_QUERY,
    ):
        assert "graph_state: 'ready'" in query


def _invoke_tool(tool, arguments, records):
    result = MagicMock()
    result.data = AsyncMock(return_value=records)
    session = MagicMock()
    session.run = AsyncMock(return_value=result)
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)
    driver = MagicMock()
    driver.session.return_value = session_context

    with patch("app.agent.graph.get_neo4j_driver", return_value=driver):
        output = asyncio.run(tool.ainvoke(arguments))
    return output, session.run


def test_list_codebase_structure_returns_newline_separated_paths() -> None:
    output, run_query = _invoke_tool(
        list_codebase_structure,
        {"repo_name": " owner/repository "},
        [
            {"file_path": "src/a.py"},
            {"file_path": "src/b.py"},
        ],
    )

    assert output == "src/a.py\nsrc/b.py"
    run_query.assert_awaited_once_with(
        CODEBASE_STRUCTURE_QUERY,
        repo_name="owner/repository",
    )


def test_list_functions_in_file_formats_function_names() -> None:
    output, run_query = _invoke_tool(
        list_functions_in_file,
        {
            "repo_name": "owner/repository",
            "file_path": " src/client.py ",
        },
        [
            {"function_name": "build_request", "qualified_name": "Client.build_request", "start_line": 8},
            {"function_name": "send_request", "qualified_name": "Client.send_request", "start_line": 20},
        ],
    )

    assert output == (
        "Functions in src/client.py:\n"
        "- Client.build_request (line 8)\n"
        "- Client.send_request (line 20)"
    )
    run_query.assert_awaited_once_with(
        FUNCTIONS_IN_FILE_QUERY,
        repo_name="owner/repository",
        file_path="src/client.py",
    )


def test_query_outgoing_dependencies_formats_targets_and_locations() -> None:
    output, run_query = _invoke_tool(
        query_outgoing_dependencies,
        {
            "repo_name": "owner/repository",
            "function_name": " send ",
        },
        [
            {
                "target_name": "prepare",
                "target_file": "src/client.py",
                "caller_entity_id": "fn:v1:caller",
                "resolution_status": "inferred",
            },
            {
                "target_name": "serialize",
                "target_file": "src/serializer.py",
                "caller_entity_id": "fn:v1:caller",
                "resolution_status": "inferred",
            },
        ],
    )

    assert output == (
        "Outgoing dependencies for send:\n"
        "- prepare (src/client.py; inferred call)\n"
        "- serialize (src/serializer.py; inferred call)"
    )
    run_query.assert_awaited_once_with(
        OUTGOING_DEPENDENCIES_QUERY,
        repo_name="owner/repository",
        func_name="send",
    )


def test_blast_radius_returns_single_target_identity() -> None:
    output, run_query = _invoke_tool(
        query_graph_blast_radius,
        {
            "repo_name": "owner/repository",
            "function_name": "Exception",
        },
        [
            {
                "caller": "validate",
                "file_paths": ["src/validation.py"],
                "target_entity_id": "fn:v1:target",
                "target_is_external": False,
            }
        ],
    )

    payload = json.loads(output)
    assert payload["status"] == "found"
    assert payload["target_entity_id"] == "fn:v1:target"
    assert payload["target_is_external"] is False
    assert payload["callers"][0]["caller"] == "validate"
    run_query.assert_awaited_once_with(
        CALLERS_QUERY,
        repo_name="owner/repository",
        func_name="Exception",
    )


def test_blast_radius_reports_ambiguous_name_without_mixing_callers() -> None:
    output, _ = _invoke_tool(
        query_graph_blast_radius,
        {"repo_name": "owner/repository", "function_name": "validate"},
        [
            {"target_entity_id": "fn:v1:a", "target_qualified_name": "A.validate", "target_file": "src/a.py", "caller": "from_a"},
            {"target_entity_id": "fn:v1:b", "target_qualified_name": "B.validate", "target_file": "src/b.py", "caller": "from_b"},
        ],
    )
    payload = json.loads(output)
    assert payload["status"] == "ambiguous"
    assert payload["callers"] == []
    assert {c["entity_id"] for c in payload["candidates"]} == {"fn:v1:a", "fn:v1:b"}


def test_outgoing_dependencies_reports_ambiguous_caller() -> None:
    output, _ = _invoke_tool(
        query_outgoing_dependencies,
        {"repo_name": "owner/repository", "function_name": "validate"},
        [
            {"caller_entity_id": "fn:v1:a", "caller_qualified_name": "A.validate", "caller_file": "src/a.py", "target_name": "charge_card"},
            {"caller_entity_id": "fn:v1:b", "caller_qualified_name": "B.validate", "caller_file": "src/b.py", "target_name": "send_email"},
        ],
    )
    assert output.startswith("Ambiguous function name validate")
    assert "A.validate (src/a.py; fn:v1:a)" in output
    assert "B.validate (src/b.py; fn:v1:b)" in output
    assert "charge_card" not in output and "send_email" not in output


def test_list_external_dependencies_formats_repository_boundary() -> None:
    output, run_query = _invoke_tool(
        list_external_dependencies,
        {"repo_name": "owner/repository"},
        [
            {"function_name": "Exception", "syntax": "Exception", "file_path": "src/a.py", "resolution_status": "unresolved"},
            {"function_name": "requests_get", "syntax": "requests.get", "file_path": "src/b.py", "resolution_status": "ambiguous"},
        ],
    )

    assert output == (
        "Unresolved or external calls (target not confirmed):\n"
        "- Exception (src/a.py; unresolved)\n"
        "- requests.get (src/b.py; ambiguous)"
    )
    run_query.assert_awaited_once_with(
        EXTERNAL_DEPENDENCIES_QUERY,
        repo_name="owner/repository",
    )


def test_semantic_code_search_embeds_and_formats_scoped_matches() -> None:
    embedding = [0.1, 0.2, 0.3]
    result = MagicMock()
    result.data = AsyncMock(
        return_value=[
            {
                "function_name": "process_payment",
                "qualified_name": "Payments.process_payment",
                "file_path": "src/payments.py",
                "start_line": 12,
                "score": 0.91234,
            }
        ]
    )
    session = MagicMock()
    session.run = AsyncMock(return_value=result)
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)
    driver = MagicMock()
    driver.session.return_value = session_context
    embed_query = AsyncMock(return_value=embedding)

    with (
        patch("app.agent.graph.get_neo4j_driver", return_value=driver),
        patch("app.agent.graph.generate_embedding", new=embed_query),
    ):
        output = asyncio.run(
            semantic_code_search.ainvoke(
                {
                    "query": "take a customer payment",
                    "repo_name": " owner/repository ",
                    "top_k": 5,
                }
            )
        )

    assert output == (
        'Semantic code matches for "take a customer payment":\n'
        "- Payments.process_payment (src/payments.py:12) — similarity 0.9123"
    )
    embed_query.assert_awaited_once_with("take a customer payment")
    session.run.assert_awaited_once_with(
        SEMANTIC_CODE_SEARCH_QUERY,
        query_vector=embedding,
        repo_name="owner/repository",
        top_k=5,
    )
    assert "SEARCH node IN" in SEMANTIC_CODE_SEARCH_QUERY
    assert "VECTOR INDEX function_embeddings" in SEMANTIC_CODE_SEARCH_QUERY
    assert "SCORE AS score" in SEMANTIC_CODE_SEARCH_QUERY
    assert "db.index.vector.queryNodes" not in SEMANTIC_CODE_SEARCH_QUERY


def test_analyze_architectural_subsystems_returns_scoped_communities() -> None:
    records = [
        {
            "id": 4,
            "module_title": "Database Transactions",
            "module_description": "Coordinates database transaction state.",
            "function_count": 12,
        }
    ]
    output, run_query = _invoke_tool(
        analyze_architectural_subsystems,
        {"repo_name": " owner/repository "},
        records,
    )

    assert json.loads(output) == records
    run_query.assert_awaited_once_with(
        ARCHITECTURAL_SUBSYSTEMS_QUERY,
        repo_name="owner/repository",
    )


def test_code_agent_registers_all_repository_tools() -> None:
    _get_code_agent.cache_clear()
    compiled_agent = object()

    with (
        patch("app.agent.graph.ChatAnthropic", return_value=MagicMock()),
        patch(
            "app.agent.graph.create_react_agent",
            return_value=compiled_agent,
        ) as create_agent,
    ):
        assert _get_code_agent() is compiled_agent

    registered_tools = create_agent.call_args.kwargs["tools"]
    assert [registered_tool.name for registered_tool in registered_tools] == [
        "query_graph_blast_radius",
        "list_codebase_structure",
        "list_functions_in_file",
        "query_outgoing_dependencies",
        "list_external_dependencies",
        "semantic_code_search",
        "analyze_architectural_subsystems",
    ]
    _get_code_agent.cache_clear()


def test_tool_context_includes_only_context_sent_by_graph_tools() -> None:
    messages = [
        SimpleNamespace(type="human", content="question"),
        SimpleNamespace(type="tool", content="first graph result"),
        SimpleNamespace(type="ai", content="planning"),
        SimpleNamespace(type="tool", content={"community": 4}),
    ]

    assert _tool_context_text(messages) == (
        'first graph result\n{"community": 4}'
    )


def test_code_agent_reports_graph_context_efficiency() -> None:
    messages = [SimpleNamespace(type="tool", content="scoped context")]

    with (
        patch(
            "app.agent.graph._run_code_agent",
            new=AsyncMock(return_value=("Structured answer", messages)),
        ),
        patch(
            "app.agent.graph.fetch_repository_total_tokens",
            new=AsyncMock(return_value=1_000),
        ) as fetch_total,
        patch("app.agent.graph.count_tokens", return_value=125) as count,
    ):
        result = asyncio.run(
            ask_code_agent_with_metrics(
                "Explain the architecture",
                " owner/repository ",
            )
        )

    assert result == {
        "answer": "Structured answer",
        "metrics": {
            "full_repo_tokens": 1_000,
            "context_tokens": 125,
            "tokens_saved": 875,
            "efficiency_percentage": 87.5,
        },
    }
    count.assert_called_once_with("scoped context")
    fetch_total.assert_awaited_once_with("owner/repository")
