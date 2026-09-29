"""LangGraph ReAct agent for code-graph questions."""

import json
import logging
from functools import lru_cache
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.config import settings
from app.db import fetch_repository_total_tokens, get_neo4j_driver
from app.services.embedding_service import generate_embedding
from app.utils.tokens import count_tokens


logger = logging.getLogger(__name__)


CALLERS_QUERY = """
MATCH (repository:Repository {repo_name: $repo_name, graph_state: 'ready'})
MATCH (target:Function {name: $func_name, repo_name: $repo_name})
OPTIONAL MATCH (caller:Function {repo_name: $repo_name})-[:CALLS]->(target)
OPTIONAL MATCH (file:File {repo_name: $repo_name})-[:DEFINES]->(caller)
RETURN target.entity_id AS target_entity_id,
       target.qualified_name AS target_qualified_name,
       target.file_path AS target_file,
       caller.name AS caller,
       caller.entity_id AS caller_entity_id,
       caller.qualified_name AS caller_qualified_name,
       collect(DISTINCT file.path) AS file_paths,
       coalesce(target.is_external, false) AS target_is_external
ORDER BY target.file_path, target.qualified_name, caller
"""

CODEBASE_STRUCTURE_QUERY = """
MATCH (repository:Repository {repo_name: $repo_name, graph_state: 'ready'})
MATCH (f:File {repo_name: $repo_name})
RETURN f.path AS file_path
ORDER BY f.path
"""

FUNCTIONS_IN_FILE_QUERY = """
MATCH (repository:Repository {repo_name: $repo_name, graph_state: 'ready'})
MATCH (f:File {path: $file_path, repo_name: $repo_name})-[:DEFINES]->
      (fn:Function)
RETURN fn.name AS function_name,
       fn.qualified_name AS qualified_name,
       fn.entity_id AS entity_id,
       fn.start_line AS start_line
ORDER BY fn.start_line, fn.name
"""

OUTGOING_DEPENDENCIES_QUERY = """
MATCH (repository:Repository {repo_name: $repo_name, graph_state: 'ready'})
MATCH (caller:Function {name: $func_name, repo_name: $repo_name})
OPTIONAL MATCH (caller)-[call:CALLS]->(target:Function {repo_name: $repo_name})
RETURN caller.entity_id AS caller_entity_id,
       caller.qualified_name AS caller_qualified_name,
       caller.file_path AS caller_file,
       target.name AS target_name,
       target.qualified_name AS target_qualified_name,
       target.file_path AS target_file,
       call.resolution_status AS resolution_status
ORDER BY caller.file_path, caller.qualified_name, target.name
"""

EXTERNAL_DEPENDENCIES_QUERY = """
MATCH (repository:Repository {repo_name: $repo_name, graph_state: 'ready'})
MATCH (call:UnresolvedCall {repo_name: $repo_name})
RETURN call.name AS function_name,
       call.syntax AS syntax,
       call.file_path AS file_path,
       call.resolution_status AS resolution_status
ORDER BY call.file_path, call.start_line, call.start_column
"""

SEMANTIC_CODE_SEARCH_QUERY = """
MATCH (node:Function)
  SEARCH node IN (
    VECTOR INDEX function_embeddings
    FOR $query_vector
    LIMIT $top_k
  ) SCORE AS score
WHERE node.repo_name = $repo_name
  AND EXISTS {
    MATCH (repository:Repository {repo_name: $repo_name, graph_state: 'ready'})
  }
RETURN node.name AS function_name,
       node.qualified_name AS qualified_name,
       node.entity_id AS entity_id,
       node.file_path AS file_path,
       node.start_line AS start_line,
       score
ORDER BY score DESC
"""

ARCHITECTURAL_SUBSYSTEMS_QUERY = """
MATCH (repository:Repository {repo_name: $repo_name, graph_state: 'ready'})
MATCH (c:Community {repo_name: $repo_name})
OPTIONAL MATCH (f:Function {repo_name: $repo_name})-[:IN_COMMUNITY]->(c)
RETURN c.community_id AS id,
       c.name AS module_title,
       c.description AS module_description,
       count(f) AS function_count
ORDER BY function_count DESC
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
use the `analyze_architectural_subsystems` tool. It returns labeled architectural
modules with a title, description, and function count. Use those stored labels
to present a high-level architectural summary."""


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

    targets = {
        record.get("target_entity_id")
        for record in records
        if isinstance(record.get("target_entity_id"), str)
    }
    if len(targets) > 1:
        return json.dumps(
            {
                "repo_name": normalized_repo_name,
                "function_name": normalized_name,
                "status": "ambiguous",
                "candidates": list(
                    {
                        record["target_entity_id"]: {
                            "entity_id": record["target_entity_id"],
                            "qualified_name": record.get("target_qualified_name"),
                            "file_path": record.get("target_file"),
                        }
                        for record in records
                        if record.get("target_entity_id") in targets
                    }.values()
                ),
                "callers": [],
            },
            default=str,
        )
    return json.dumps(
        {
            "repo_name": normalized_repo_name,
            "function_name": normalized_name,
            "status": "found" if targets else "not_found",
            "target_entity_id": next(iter(targets), None),
            "target_is_external": any(
                record.get("target_is_external") is True for record in records
            ),
            "callers": [record for record in records if record.get("caller")],
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

    functions = [
        record for record in records
        if isinstance(record.get("function_name"), str)
    ]
    if not functions:
        return f"No functions found in {normalized_file_path}."
    return "\n".join(
        [
            f"Functions in {normalized_file_path}:",
            *(
                f"- {record.get('qualified_name') or record['function_name']} "
                f"(line {record.get('start_line') or '?'})"
                for record in functions
            ),
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

    callers = {
        record.get("caller_entity_id")
        for record in records
        if isinstance(record.get("caller_entity_id"), str)
    }
    if len(callers) > 1:
        candidates = {
            (
                record.get("caller_qualified_name") or normalized_function_name,
                record.get("caller_file") or "unknown file",
                record["caller_entity_id"],
            )
            for record in records
            if record.get("caller_entity_id") in callers
        }
        return (
            f"Ambiguous function name {normalized_function_name}; "
            "this name-only tool cannot select one definition. Candidates: "
            + ", ".join(
                f"{name} ({path}; {entity_id})"
                for name, path, entity_id in sorted(candidates)
            )
        )
    dependencies: list[str] = []
    for record in records:
        target_name = record.get("target_name")
        if not isinstance(target_name, str):
            continue
        target_file = record.get("target_file")
        location = target_file if isinstance(target_file, str) else "unknown file"
        provenance = record.get("resolution_status") or "unknown"
        dependencies.append(f"- {target_name} ({location}; {provenance} call)")

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

    call_records = [
        record for record in records
        if isinstance(record.get("function_name"), str)
    ]
    if not call_records:
        return "No unresolved or external calls found."
    return "\n".join(
        [
            "Unresolved or external calls (target not confirmed):",
            *(
                f"- {record.get('syntax') or record['function_name']} "
                f"({record.get('file_path') or 'unknown file'}; "
                f"{record.get('resolution_status') or 'unresolved'})"
                for record in call_records
            ),
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
        qualified_name = record.get("qualified_name") or function_name
        line = record.get("start_line") or "?"
        matches.append(
            f"- {qualified_name} ({location}:{line}) — similarity {score_text}"
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


def _tool_context_text(messages: list[Any]) -> str:
    """Join the graph tool outputs that were actually supplied to the LLM."""

    context_parts: list[str] = []
    for message in messages:
        if getattr(message, "type", None) != "tool":
            continue
        content = getattr(message, "content", "")
        if isinstance(content, str):
            context_parts.append(content)
        elif content is not None:
            context_parts.append(json.dumps(content, default=str))
    return "\n".join(context_parts)


async def _run_code_agent(
    user_message: str,
    repo_name: str,
) -> tuple[str, list[Any]]:
    """Run the repository-scoped agent and return its answer and trace."""

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
    return response, messages


async def ask_code_agent(user_message: str, repo_name: str) -> str:
    """Ask the code-graph agent a repository-scoped code question."""

    response, _ = await _run_code_agent(user_message, repo_name)
    return response


async def ask_code_agent_with_metrics(
    user_message: str,
    repo_name: str,
) -> dict[str, Any]:
    """Answer a question and report Graph-RAG context token efficiency."""

    normalized_repo_name = repo_name.strip()
    response, messages = await _run_code_agent(
        user_message,
        normalized_repo_name,
    )
    graph_context = _tool_context_text(messages)
    context_tokens = count_tokens(graph_context)
    total_repo_tokens = await fetch_repository_total_tokens(
        normalized_repo_name
    )

    if total_repo_tokens > 0:
        tokens_saved = total_repo_tokens - context_tokens
        efficiency_percentage = round(
            tokens_saved / total_repo_tokens * 100,
            2,
        )
    else:
        tokens_saved = 0
        efficiency_percentage = 0.0

    metrics: dict[str, int | float] = {
        "full_repo_tokens": total_repo_tokens,
        "context_tokens": context_tokens,
        "tokens_saved": tokens_saved,
        "efficiency_percentage": efficiency_percentage,
    }
    logger.info(
        "Graph-RAG efficiency for %s: full_repo_tokens=%d, "
        "context_tokens=%d, tokens_saved=%d, efficiency_percentage=%.2f",
        normalized_repo_name,
        total_repo_tokens,
        context_tokens,
        tokens_saved,
        efficiency_percentage,
    )
    return {"answer": response, "metrics": metrics}
