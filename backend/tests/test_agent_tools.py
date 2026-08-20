"""Unit tests for the repository-scoped LangGraph traversal tools."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.graph import (
    CALLERS_QUERY,
    CODE_AGENT_SYSTEM_PROMPT,
    CODEBASE_STRUCTURE_QUERY,
    EXTERNAL_DEPENDENCIES_QUERY,
    FUNCTIONS_IN_FILE_QUERY,
    OUTGOING_DEPENDENCIES_QUERY,
    _get_code_agent,
    list_external_dependencies,
    list_codebase_structure,
    list_functions_in_file,
    query_graph_blast_radius,
    query_outgoing_dependencies,
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
        query_outgoing_dependencies,
        {
            "repo_name": "owner/repository",
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


def test_blast_radius_surfaces_external_target_status() -> None:
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
        list_external_dependencies,
        {"repo_name": "owner/repository"},
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
    ]
    _get_code_agent.cache_clear()
