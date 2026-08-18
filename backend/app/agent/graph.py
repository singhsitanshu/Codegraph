"""LangGraph ReAct agent for code-graph questions."""

import json
from functools import lru_cache
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.config import settings
from app.db import get_neo4j_driver


CALLERS_QUERY = """
MATCH (caller:Function {repo_name: $repo_name})-[:CALLS]->
      (target:Function {name: $func_name, repo_name: $repo_name})
OPTIONAL MATCH (file:File {repo_name: $repo_name})-[:DEFINES]->(caller)
RETURN DISTINCT caller.name AS caller,
       collect(DISTINCT file.path) AS file_paths
ORDER BY caller
LIMIT 100
"""

CODEBASE_STRUCTURE_QUERY = """
MATCH (f:File {repo_name: $repo_name})
RETURN f.path AS file_path
ORDER BY f.path
"""

FUNCTIONS_IN_FILE_QUERY = """
MATCH (f:File {path: $file_path, repo_name: $repo_name})-[:DEFINES]->
      (fn:Function)
RETURN fn.name AS function_name
ORDER BY fn.name
"""

OUTGOING_DEPENDENCIES_QUERY = """
MATCH (caller:Function {name: $func_name, repo_name: $repo_name})-[:CALLS]->
      (target:Function {repo_name: $repo_name})
RETURN target.name AS target_name, target.file AS target_file
ORDER BY target.name, target.file
"""


@tool
async def query_graph_blast_radius(repo_name: str, function_name: str) -> str:
    """Find direct callers of a function within one ``owner/repository`` graph."""

    normalized_repo_name = repo_name.strip()
    normalized_name = function_name.strip()
    if not normalized_repo_name or not normalized_name:
        return json.dumps(
            {
                "repo_name": normalized_repo_name,
                "function_name": normalized_name,
                "callers": [],
            }
        )

    async with get_neo4j_driver().session() as session:
        result = await session.run(
            CALLERS_QUERY,
            repo_name=normalized_repo_name,
            func_name=normalized_name,
        )
        records = await result.data()

    return json.dumps(
        {
            "repo_name": normalized_repo_name,
            "function_name": normalized_name,
            "callers": records,
        },
        default=str,
    )


@tool
async def list_codebase_structure(repo_name: str) -> str:
    """List every source file path in one ``owner/repository`` code graph."""

    normalized_repo_name = repo_name.strip()
    if not normalized_repo_name:
        return ""

    async with get_neo4j_driver().session() as session:
        result = await session.run(
            CODEBASE_STRUCTURE_QUERY,
            repo_name=normalized_repo_name,
        )
        records = await result.data()

    return "\n".join(
        record["file_path"]
        for record in records
        if isinstance(record.get("file_path"), str)
    )


@tool
async def list_functions_in_file(repo_name: str, file_path: str) -> str:
    """List functions defined in a file within one repository graph."""

    normalized_repo_name = repo_name.strip()
    normalized_file_path = file_path.strip()
    if not normalized_repo_name or not normalized_file_path:
        return "No functions found."

    async with get_neo4j_driver().session() as session:
        result = await session.run(
            FUNCTIONS_IN_FILE_QUERY,
            repo_name=normalized_repo_name,
            file_path=normalized_file_path,
        )
        records = await result.data()

    function_names = [
        record["function_name"]
        for record in records
        if isinstance(record.get("function_name"), str)
    ]
    if not function_names:
        return f"No functions found in {normalized_file_path}."
    return "\n".join(
        [
            f"Functions in {normalized_file_path}:",
            *(f"- {function_name}" for function_name in function_names),
        ]
    )


@tool
async def query_outgoing_dependencies(
    repo_name: str,
    function_name: str,
) -> str:
    """List functions called by a function within one repository graph."""

    normalized_repo_name = repo_name.strip()
    normalized_function_name = function_name.strip()
    if not normalized_repo_name or not normalized_function_name:
        return "No outgoing dependencies found."

    async with get_neo4j_driver().session() as session:
        result = await session.run(
            OUTGOING_DEPENDENCIES_QUERY,
            repo_name=normalized_repo_name,
            func_name=normalized_function_name,
        )
        records = await result.data()

    dependencies: list[str] = []
    for record in records:
        target_name = record.get("target_name")
        if not isinstance(target_name, str):
            continue
        target_file = record.get("target_file")
        location = target_file if isinstance(target_file, str) else "external/unknown"
        dependencies.append(f"- {target_name} ({location})")

    if not dependencies:
        return f"No outgoing dependencies found for {normalized_function_name}."
    return "\n".join(
        [
            f"Outgoing dependencies for {normalized_function_name}:",
            *dependencies,
        ]
    )


@lru_cache(maxsize=1)
def _get_code_agent() -> Any:
    """Create and cache the Sonnet 5 ReAct graph on first chat request."""

    llm = ChatAnthropic(
        model="claude-sonnet-5",
        api_key=settings.ANTHROPIC_API_KEY,
    )
    tools = [
        query_graph_blast_radius,
        list_codebase_structure,
        list_functions_in_file,
        query_outgoing_dependencies,
    ]
    return create_react_agent(llm, tools=tools)


def _message_text(content: object) -> str:
    """Normalize Anthropic string or content-block output to plain text."""

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return ""


async def ask_code_agent(user_message: str, repo_name: str) -> str:
    """Ask the code-graph agent a repository-scoped code question."""

    normalized_repo_name = repo_name.strip()
    if not normalized_repo_name:
        raise ValueError("repo_name must not be blank")

    result = await _get_code_agent().ainvoke(
        {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are analyzing only the GitHub repository "
                        f"'{normalized_repo_name}'. When calling graph tools, "
                        "always use that exact repository name. Do not mix "
                        "results from other repositories."
                    ),
                },
                {"role": "user", "content": user_message},
            ],
            "repo_name": normalized_repo_name,
        }
    )
    messages = result.get("messages", [])
    if not messages:
        raise RuntimeError("The code agent returned no messages")

    response = _message_text(messages[-1].content)
    if not response:
        raise RuntimeError("The code agent returned an empty response")
    return response
