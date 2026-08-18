"""Unit tests for the repository-scoped LangGraph traversal tools."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.graph import (
    CODEBASE_STRUCTURE_QUERY,
    FUNCTIONS_IN_FILE_QUERY,
    OUTGOING_DEPENDENCIES_QUERY,
    _get_code_agent,
    list_codebase_structure,
    list_functions_in_file,
    query_outgoing_dependencies,
)


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
            {"target_name": "prepare", "target_file": "src/client.py"},
            {"target_name": "http_call", "target_file": None},
        ],
    )

    assert output == (
        "Outgoing dependencies for send:\n"
        "- prepare (src/client.py)\n"
        "- http_call (external/unknown)"
    )
    run_query.assert_awaited_once_with(
        OUTGOING_DEPENDENCIES_QUERY,
        repo_name="owner/repository",
        func_name="send",
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
    ]
    _get_code_agent.cache_clear()
