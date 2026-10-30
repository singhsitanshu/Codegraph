"""Unit tests for the repository-scoped LangGraph traversal tools."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.agent.graph import (
    ARCHITECTURE_TOOL_NAME,
    CODE_AGENT_SYSTEM_PROMPT,
    CodeAgentAnswer,
    GraphRagMetrics,
    _run_code_agent,
    _tool_context_text,
    ask_code_agent_with_metrics,
    build_repository_tools,
)
from app.db.code_queries import (
    ARCHITECTURAL_SUBSYSTEMS_QUERY,
    CALLERS_QUERY,
    CODEBASE_STRUCTURE_QUERY,
    EXTERNAL_DEPENDENCIES_QUERY,
    FUNCTIONS_IN_FILE_QUERY,
    OUTGOING_DEPENDENCIES_QUERY,
    SEMANTIC_CODE_SEARCH_QUERY,
)
from app.utils.embeddings import FUNCTION_EMBEDDING_INDEX


REPO = "owner/repository"
TOOLS = {
    graph_tool.name: graph_tool for graph_tool in build_repository_tools(REPO)
}


def test_code_agent_system_prompt_requires_structured_markdown() -> None:
    rendered_prompt = CODE_AGENT_SYSTEM_PROMPT.format(repo_name=REPO)

    assert "expert Senior Staff Engineer" in rendered_prompt
    assert "Never output large walls of text" in rendered_prompt
    assert "Markdown headings (`##`)" in rendered_prompt
    assert "bullet points or numbered lists" in rendered_prompt
    assert "`api.py`" in rendered_prompt
    assert "```python" in rendered_prompt
    assert "owner/repository" in rendered_prompt
    assert f"`{ARCHITECTURE_TOOL_NAME}` tool" in rendered_prompt
    assert ARCHITECTURE_TOOL_NAME in TOOLS
    assert "labeled architectural" in rendered_prompt
    assert "function count" in rendered_prompt


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

    with patch("app.db.code_queries.get_neo4j_driver", return_value=driver):
        output = asyncio.run(tool.ainvoke(arguments))
    return output, session.run


def test_list_codebase_structure_returns_newline_separated_paths() -> None:
    output, run_query = _invoke_tool(
        TOOLS["list_codebase_structure"],
        {},
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
        TOOLS["list_functions_in_file"],
        {
            "file_path": " src/client.py ",
        },
        [
            {"function_name": "build_request"},
            {"function_name": "send_request"},
        ],
    )

    assert output == (
        "Functions in src/client.py:\n"
        "- build_request\n"
        "- send_request"
    )
    run_query.assert_awaited_once_with(
        FUNCTIONS_IN_FILE_QUERY,
        repo_name="owner/repository",
        file_path="src/client.py",
    )


def test_query_outgoing_dependencies_formats_targets_and_locations() -> None:
    output, run_query = _invoke_tool(
        TOOLS["query_outgoing_dependencies"],
        {
            "function_name": " send ",
        },
        [
            {
                "target_name": "prepare",
                "target_file": "src/client.py",
                "is_external": False,
            },
            {
                "target_name": "http_call",
                "target_file": None,
                "is_external": True,
            },
        ],
    )

    assert output == (
        "Outgoing dependencies for send:\n"
        "- prepare (src/client.py)\n"
        "- http_call (External/Built-in)"
    )
    run_query.assert_awaited_once_with(
        OUTGOING_DEPENDENCIES_QUERY,
        repo_name="owner/repository",
        func_name="send",
    )


def test_query_outgoing_dependencies_separates_same_named_definitions() -> None:
    output, _ = _invoke_tool(
        TOOLS["query_outgoing_dependencies"],
        {"function_name": "run"},
        [
            {
                "caller_name": "Alpha.run",
                "caller_file": "src/a.py",
                "target_name": "prepare",
                "target_file": "src/a.py",
                "is_external": False,
            },
            {
                "caller_name": "Beta.run",
                "caller_file": "src/b.py",
                "target_name": "print",
                "target_file": None,
                "is_external": True,
            },
        ],
    )

    assert output == (
        "Outgoing dependencies for 2 definitions named run:\n"
        "Alpha.run (src/a.py):\n"
        "  - prepare (src/a.py)\n"
        "Beta.run (src/b.py):\n"
        "  - print (External/Built-in)"
    )


def test_blast_radius_surfaces_external_target_status() -> None:
    output, run_query = _invoke_tool(
        TOOLS["query_graph_blast_radius"],
        {
            "function_name": "Exception",
        },
        [
            {
                "caller": "validate",
                "file_paths": ["src/validation.py"],
                "target_is_external": True,
            }
        ],
    )

    payload = json.loads(output)
    assert payload["target_is_external"] is True
    assert payload["callers"][0]["target_is_external"] is True
    run_query.assert_awaited_once_with(
        CALLERS_QUERY,
        repo_name="owner/repository",
        func_name="Exception",
    )


def test_list_external_dependencies_formats_repository_boundary() -> None:
    output, run_query = _invoke_tool(
        TOOLS["list_external_dependencies"],
        {},
        [
            {"function_name": "Exception"},
            {"function_name": "requests_get"},
        ],
    )

    assert output == (
        "External dependencies:\n"
        "- Exception\n"
        "- requests_get"
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
                "file_path": "src/payments.py",
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
        patch("app.db.code_queries.get_neo4j_driver", return_value=driver),
        patch("app.agent.graph.generate_embedding", new=embed_query),
    ):
        output = asyncio.run(
            TOOLS["semantic_code_search"].ainvoke(
                {
                    "query": "take a customer payment",
                            "top_k": 5,
                }
            )
        )

    assert output == (
        'Semantic code matches for "take a customer payment":\n'
        "- process_payment (src/payments.py) — similarity 0.9123"
    )
    embed_query.assert_awaited_once_with("take a customer payment")
    session.run.assert_awaited_once_with(
        SEMANTIC_CODE_SEARCH_QUERY,
        query_vector=embedding,
        repo_name="owner/repository",
        top_k=5,
    )
    assert "SEARCH node IN" in SEMANTIC_CODE_SEARCH_QUERY
    assert (
        f"VECTOR INDEX {FUNCTION_EMBEDDING_INDEX}" in SEMANTIC_CODE_SEARCH_QUERY
    )
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
        TOOLS["analyze_architectural_subsystems"],
        {},
        records,
    )

    assert json.loads(output) == records
    run_query.assert_awaited_once_with(
        ARCHITECTURAL_SUBSYSTEMS_QUERY,
        repo_name="owner/repository",
    )


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("query_graph_blast_radius", {"function_name": "  "}),
        ("list_functions_in_file", {"file_path": ""}),
        ("query_outgoing_dependencies", {"function_name": " "}),
        ("semantic_code_search", {"query": "  "}),
        ("semantic_code_search", {"query": "payments", "top_k": 0}),
        ("semantic_code_search", {"query": "payments", "top_k": 21}),
    ],
)
def test_tools_reject_invalid_llm_arguments_before_querying(
    tool_name, arguments
) -> None:
    driver = MagicMock()
    with (
        patch("app.db.code_queries.get_neo4j_driver", return_value=driver),
        pytest.raises(ValidationError),
    ):
        asyncio.run(TOOLS[tool_name].ainvoke(arguments))
    driver.session.assert_not_called()


def test_code_agent_runs_with_tools_bound_to_the_requested_repository() -> None:
    compiled_agent = MagicMock()
    compiled_agent.ainvoke = AsyncMock(
        return_value={"messages": [SimpleNamespace(content="Answer")]}
    )

    with (
        patch("app.agent.graph._get_code_model", return_value=MagicMock()),
        patch(
            "app.agent.graph.create_react_agent",
            return_value=compiled_agent,
        ) as create_agent,
    ):
        response, _ = asyncio.run(_run_code_agent("Explain it", REPO))

    assert response == "Answer"
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
    output, run_query = _invoke_tool(
        registered_tools[1],
        {},
        [{"file_path": "src/a.py"}],
    )
    assert output == "src/a.py"
    run_query.assert_awaited_once_with(
        CODEBASE_STRUCTURE_QUERY,
        repo_name=REPO,
    )


@pytest.mark.parametrize("graph_tool", TOOLS.values(), ids=TOOLS.keys())
def test_model_cannot_choose_the_repository_scope(graph_tool) -> None:
    assert "repo_name" not in graph_tool.tool_call_schema.model_json_schema()[
        "properties"
    ]


def test_model_supplied_repository_name_is_ignored() -> None:
    _, run_query = _invoke_tool(
        TOOLS["list_external_dependencies"],
        {"repo_name": "attacker/other-repository"},
        [],
    )

    run_query.assert_awaited_once_with(
        EXTERNAL_DEPENDENCIES_QUERY,
        repo_name=REPO,
    )


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
            "app.db.code_queries.fetch_repository_total_tokens",
            new=AsyncMock(return_value=1_000),
        ) as fetch_total,
        patch("app.agent.graph.count_tokens", return_value=125) as count,
    ):
        result = asyncio.run(
            ask_code_agent_with_metrics(
                "Explain the architecture",
                "owner/repository",
            )
        )

    assert result == CodeAgentAnswer(
        answer="Structured answer",
        metrics=GraphRagMetrics(full_repo_tokens=1_000, context_tokens=125),
    )
    assert result.metrics.as_dict() == {
        "full_repo_tokens": 1_000,
        "context_tokens": 125,
        "tokens_saved": 875,
        "efficiency_percentage": 87.5,
    }
    count.assert_called_once_with("scoped context")
    fetch_total.assert_awaited_once_with("owner/repository")


def test_metrics_without_a_repository_baseline_report_no_savings() -> None:
    metrics = GraphRagMetrics(full_repo_tokens=0, context_tokens=125)

    assert metrics.as_dict() == {
        "full_repo_tokens": 0,
        "context_tokens": 125,
        "tokens_saved": 0,
        "efficiency_percentage": 0.0,
    }
