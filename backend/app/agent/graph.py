"""LangGraph ReAct agent for code-graph questions."""

import json
from functools import lru_cache
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.config import settings
from app.db import get_neo4j_driver
from app.services.embedding_service import generate_embedding


CALLERS_QUERY = """
MATCH (caller:Function {repo_name: $repo_name})-[:CALLS]->
      (target:Function {name: $func_name, repo_name: $repo_name})
OPTIONAL MATCH (file:File {repo_name: $repo_name})-[:DEFINES]->(caller)
RETURN DISTINCT caller.name AS caller,
       collect(DISTINCT file.path) AS file_paths,
       coalesce(target.is_external, false) AS target_is_external
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
RETURN target.name AS target_name,
       target.file AS target_file,
       target.is_external AS is_external
ORDER BY target.name, target.file
"""

EXTERNAL_DEPENDENCIES_QUERY = """
MATCH (fn:ExternalFunction {repo_name: $repo_name})
RETURN fn.name AS function_name
ORDER BY fn.name
"""

SEMANTIC_CODE_SEARCH_QUERY = """
CALL db.index.vector.queryNodes(
    'function_embeddings',
    $top_k,
    $query_vector
)
YIELD node, score
WHERE node.repo_name = $repo_name
RETURN node.name AS function_name,
       node.file_path AS file_path,
       score
ORDER BY score DESC
"""

ARCHITECTURAL_SUBSYSTEMS_QUERY = """
MATCH (f:Function {repo_name: $repo_name})
WHERE f.leiden_community IS NOT NULL
WITH f.leiden_community AS community,
     count(f) AS size,
     collect(f.name)[0..7] AS sample_functions
ORDER BY size DESC
LIMIT 10
RETURN community, size, sample_functions
"""

CODE_AGENT_SYSTEM_PROMPT = """You are an expert Senior Staff Engineer analyzing a codebase.
You MUST format your responses for maximum readability.
- Never output large walls of text.
- Use Markdown headings (`##`) to organize your thoughts.
- Use bullet points or numbered lists when listing functions, files, or steps.
- Enclose file names and function names in backticks (for example, `api.py` and `send()`).
- Use fenced code blocks with a language identifier (for example, ```python) when writing or displaying code snippets.
- Be concise, direct, and highly structured.

You are analyzing only the GitHub repository `{repo_name}`. When calling graph
tools, always use that exact repository name. Do not mix results from other
repositories.

When asked to explain the architecture or high-level structure of a repository,
use the `analyze_architectural_subsystems` tool. It returns mathematical clusters
(communities). Analyze the `sample_functions` in each community to deduce what
that subsystem does (for example, "Community 1 appears to handle Database I/O"),
and present a high-level architectural summary."""


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
                "target_is_external": False,
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
            "target_is_external": any(
                record.get("target_is_external") is True for record in records
            ),
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
        if record.get("is_external") is True:
            dependencies.append(f"- {target_name} (External/Built-in)")
            continue
        target_file = record.get("target_file")
        location = target_file if isinstance(target_file, str) else "unknown file"
        dependencies.append(f"- {target_name} ({location})")

    if not dependencies:
        return f"No outgoing dependencies found for {normalized_function_name}."
    return "\n".join(
        [
            f"Outgoing dependencies for {normalized_function_name}:",
            *dependencies,
        ]
    )


@tool
async def list_external_dependencies(repo_name: str) -> str:
    """List external, standard-library, or third-party repository calls."""

    normalized_repo_name = repo_name.strip()
    if not normalized_repo_name:
        return "No external dependencies found."

    async with get_neo4j_driver().session() as session:
        result = await session.run(
            EXTERNAL_DEPENDENCIES_QUERY,
            repo_name=normalized_repo_name,
        )
        records = await result.data()

    function_names = [
        record["function_name"]
        for record in records
        if isinstance(record.get("function_name"), str)
    ]
    if not function_names:
        return "No external dependencies found."
    return "\n".join(
        [
            "External dependencies:",
            *(f"- {function_name}" for function_name in function_names),
        ]
    )


@tool
async def semantic_code_search(
    query: str,
    repo_name: str,
    top_k: int = 5,
) -> str:
    """Find functions related to a natural-language query in one repository."""

    normalized_query = query.strip()
    normalized_repo_name = repo_name.strip()
    if not normalized_query or not normalized_repo_name:
        return "No semantic code matches found."

    normalized_top_k = max(1, min(top_k, 20))
    query_vector = await generate_embedding(normalized_query)
    async with get_neo4j_driver().session() as session:
        result = await session.run(
            SEMANTIC_CODE_SEARCH_QUERY,
            query_vector=query_vector,
            repo_name=normalized_repo_name,
            top_k=normalized_top_k,
        )
        records = await result.data()

    matches: list[str] = []
    for record in records:
        function_name = record.get("function_name")
        if not isinstance(function_name, str):
            continue
        file_path = record.get("file_path")
        location = file_path if isinstance(file_path, str) else "unknown file"
        score = record.get("score")
        score_text = (
            f"{float(score):.4f}"
            if isinstance(score, (int, float))
            else "unknown"
        )
        matches.append(
            f"- {function_name} ({location}) — similarity {score_text}"
        )

    if not matches:
        return f'No semantic code matches found for "{normalized_query}".'
    return "\n".join(
        [
            f'Semantic code matches for "{normalized_query}":',
            *matches,
        ]
    )


@tool
async def analyze_architectural_subsystems(repo_name: str) -> str:
    """Return the largest Leiden communities in one repository code graph."""

    normalized_repo_name = repo_name.strip()
    if not normalized_repo_name:
        return json.dumps([])

    async with get_neo4j_driver().session() as session:
        result = await session.run(
            ARCHITECTURAL_SUBSYSTEMS_QUERY,
            repo_name=normalized_repo_name,
        )
        records = await result.data()

    return json.dumps(records, default=str)


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
        list_external_dependencies,
        semantic_code_search,
        analyze_architectural_subsystems,
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
                    "content": CODE_AGENT_SYSTEM_PROMPT.format(
                        repo_name=normalized_repo_name
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
