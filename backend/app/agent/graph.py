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
MATCH (caller:Function)-[:CALLS]->(target:Function)
WHERE toLower(target.name) = toLower($function_name)
OPTIONAL MATCH (file:File)-[:DEFINES]->(caller)
RETURN DISTINCT caller.name AS caller,
       collect(DISTINCT file.path) AS file_paths
ORDER BY caller
LIMIT 100
"""


@tool
async def query_graph_blast_radius(function_name: str) -> str:
    """Find functions that directly call a named function in the code graph."""

    normalized_name = function_name.strip()
    if not normalized_name:
        return json.dumps({"function_name": function_name, "callers": []})

    async with get_neo4j_driver().session() as session:
        result = await session.run(
            CALLERS_QUERY,
            function_name=normalized_name,
        )
        records = await result.data()

    return json.dumps(
        {"function_name": normalized_name, "callers": records},
        default=str,
    )


@lru_cache(maxsize=1)
def _get_code_agent() -> Any:
    """Create and cache the Sonnet 5 ReAct graph on first chat request."""

    llm = ChatAnthropic(
        model="claude-sonnet-5",
        api_key=settings.ANTHROPIC_API_KEY,
    )
    return create_react_agent(llm, tools=[query_graph_blast_radius])


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


async def ask_code_agent(user_message: str) -> str:
    """Ask the code-graph agent a question and return its final text response."""

    result = await _get_code_agent().ainvoke(
        {"messages": [{"role": "user", "content": user_message}]}
    )
    messages = result.get("messages", [])
    if not messages:
        raise RuntimeError("The code agent returned no messages")

    response = _message_text(messages[-1].content)
    if not response:
        raise RuntimeError("The code agent returned an empty response")
    return response
