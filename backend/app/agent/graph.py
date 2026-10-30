"""LangGraph ReAct agent for code-graph questions."""

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import create_react_agent
from pydantic import Field, StringConstraints

from app.config import settings
from app.db import code_queries
from app.services.embedding_service import generate_embedding
from app.utils.repository import RepositoryName
from app.utils.tokens import count_tokens


logger = logging.getLogger(__name__)

# Tool arguments are chosen by the LLM, so each tool's argument schema validates
# them before the tool body runs. LangGraph's ToolNode reports a validation
# failure back to the model as a tool error instead of running the query.
ToolText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SearchResultLimit = Annotated[int, Field(ge=1, le=20)]


# The system prompt points Claude at this tool by name.
ARCHITECTURE_TOOL_NAME = "analyze_architectural_subsystems"

CODE_AGENT_SYSTEM_PROMPT = f"""You are an expert Senior Staff Engineer analyzing a codebase.
You MUST format your responses for maximum readability.
- Never output large walls of text.
- Use Markdown headings (`##`) to organize your thoughts.
- Use bullet points or numbered lists when listing functions, files, or steps.
- Enclose file names and function names in backticks (for example, `api.py` and `send()`).
- Use fenced code blocks with a language identifier (for example, ```python) when writing or displaying code snippets.
- Be concise, direct, and highly structured.

You are analyzing the GitHub repository `{{repo_name}}`. Every graph tool reads
that repository's code graph.

When asked to explain the architecture or high-level structure of a repository,
use the `{ARCHITECTURE_TOOL_NAME}` tool. It returns labeled architectural
modules with a title, description, and function count. Use those stored labels
to present a high-level architectural summary."""


def _string_values(records: list[dict[str, Any]], key: str) -> list[str]:
    """Return the string values of one column, skipping missing entries."""

    return [record[key] for record in records if isinstance(record.get(key), str)]


def build_repository_tools(repo_name: RepositoryName) -> list[BaseTool]:
    """Build the graph tools for one validated repository.

    The repository is bound here rather than exposed as a tool argument, so the
    model cannot choose which repository's graph a tool reads.
    """

    @tool
    async def query_graph_blast_radius(function_name: ToolText) -> str:
        """Find direct callers of a function in the repository graph."""

        records = await code_queries.fetch_callers(repo_name, function_name)

        return json.dumps(
            {
                "repo_name": repo_name,
                "function_name": function_name,
                "target_is_external": any(
                    record.get("target_is_external") is True
                    for record in records
                ),
                "callers": records,
            },
            default=str,
        )

    @tool
    async def list_codebase_structure() -> str:
        """List every source file path in the repository graph."""

        records = await code_queries.fetch_file_paths(repo_name)

        return "\n".join(_string_values(records, "file_path"))

    @tool
    async def list_functions_in_file(file_path: ToolText) -> str:
        """List functions defined in a file of the repository graph."""

        records = await code_queries.fetch_functions_in_file(repo_name, file_path)

        function_names = _string_values(records, "function_name")
        if not function_names:
            return f"No functions found in {file_path}."
        return "\n".join(
            [
                f"Functions in {file_path}:",
                *(f"- {function_name}" for function_name in function_names),
            ]
        )

    @tool
    async def query_outgoing_dependencies(function_name: ToolText) -> str:
        """List functions called by a function in the repository graph."""

        records = await code_queries.fetch_outgoing_dependencies(
            repo_name,
            function_name,
        )

        dependencies_by_caller: dict[tuple[object, object], list[str]] = {}
        for record in records:
            target_name = record.get("target_name")
            if not isinstance(target_name, str):
                continue
            dependencies = dependencies_by_caller.setdefault(
                (record.get("caller_name"), record.get("caller_file")), []
            )
            if record.get("is_external") is True:
                dependencies.append(f"- {target_name} (External/Built-in)")
                continue
            target_file = record.get("target_file")
            location = (
                target_file if isinstance(target_file, str) else "unknown file"
            )
            dependencies.append(f"- {target_name} ({location})")

        if not dependencies_by_caller:
            return f"No outgoing dependencies found for {function_name}."
        if len(dependencies_by_caller) == 1:
            return "\n".join(
                [
                    f"Outgoing dependencies for {function_name}:",
                    *next(iter(dependencies_by_caller.values())),
                ]
            )
        # Several definitions share this name; keep their dependencies apart.
        lines = [
            f"Outgoing dependencies for {len(dependencies_by_caller)} "
            f"definitions named {function_name}:"
        ]
        for (caller_name, caller_file), dependencies in (
            dependencies_by_caller.items()
        ):
            lines.append(f"{caller_name} ({caller_file or 'unknown file'}):")
            lines.extend(f"  {dependency}" for dependency in dependencies)
        return "\n".join(lines)

    @tool
    async def list_external_dependencies() -> str:
        """List external, standard-library, or third-party repository calls."""

        records = await code_queries.fetch_external_functions(repo_name)

        function_names = _string_values(records, "function_name")
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
        query: ToolText,
        top_k: SearchResultLimit = 5,
    ) -> str:
        """Find functions related to a natural-language query in the repository."""

        query_vector = await generate_embedding(query)
        records = await code_queries.search_functions_by_embedding(
            repo_name,
            query_vector,
            top_k,
        )

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
            return f'No semantic code matches found for "{query}".'
        return "\n".join(
            [
                f'Semantic code matches for "{query}":',
                *matches,
            ]
        )

    @tool(ARCHITECTURE_TOOL_NAME)
    async def analyze_architectural_subsystems() -> str:
        """Return the largest Leiden communities in the repository graph."""

        records = await code_queries.fetch_architectural_subsystems(repo_name)

        return json.dumps(records, default=str)

    return [
        query_graph_blast_radius,
        list_codebase_structure,
        list_functions_in_file,
        query_outgoing_dependencies,
        list_external_dependencies,
        semantic_code_search,
        analyze_architectural_subsystems,
    ]


@lru_cache(maxsize=1)
def _get_code_model() -> ChatAnthropic:
    """Create and cache the Sonnet 5 chat model on first chat request."""

    return ChatAnthropic(
        model="claude-sonnet-5",
        api_key=settings.ANTHROPIC_API_KEY,
    )


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
    repo_name: RepositoryName,
) -> tuple[str, list[Any]]:
    """Run the repository-scoped agent and return its answer and trace."""

    code_agent = create_react_agent(
        _get_code_model(),
        tools=build_repository_tools(repo_name),
    )
    result = await code_agent.ainvoke(
        {
            "messages": [
                {
                    "role": "system",
                    "content": CODE_AGENT_SYSTEM_PROMPT.format(
                        repo_name=repo_name
                    ),
                },
                {"role": "user", "content": user_message},
            ],
        }
    )
    messages = result.get("messages", [])
    if not messages:
        raise RuntimeError("The code agent returned no messages")

    response = _message_text(messages[-1].content)
    if not response:
        raise RuntimeError("The code agent returned an empty response")
    return response, messages


@dataclass(frozen=True, slots=True)
class GraphRagMetrics:
    """Token cost of the graph context compared with the full repository.

    The savings are derived, so they always agree with the two measured counts.
    A repository without a stored baseline reports no savings.
    """

    full_repo_tokens: int
    context_tokens: int

    @property
    def tokens_saved(self) -> int:
        if self.full_repo_tokens <= 0:
            return 0
        return self.full_repo_tokens - self.context_tokens

    @property
    def efficiency_percentage(self) -> float:
        if self.full_repo_tokens <= 0:
            return 0.0
        return round(self.tokens_saved / self.full_repo_tokens * 100, 2)

    def as_dict(self) -> dict[str, int | float]:
        """Serialize the counts and savings for the chat API response."""

        return {
            "full_repo_tokens": self.full_repo_tokens,
            "context_tokens": self.context_tokens,
            "tokens_saved": self.tokens_saved,
            "efficiency_percentage": self.efficiency_percentage,
        }


@dataclass(frozen=True, slots=True)
class CodeAgentAnswer:
    """The agent's answer and the Graph-RAG metrics for producing it."""

    answer: str
    metrics: GraphRagMetrics


async def ask_code_agent_with_metrics(
    user_message: str,
    repo_name: RepositoryName,
) -> CodeAgentAnswer:
    """Answer a question and report Graph-RAG context token efficiency."""

    response, messages = await _run_code_agent(user_message, repo_name)
    context_tokens = count_tokens(_tool_context_text(messages))
    metrics = GraphRagMetrics(
        full_repo_tokens=await code_queries.fetch_repository_total_tokens(
            repo_name
        ),
        context_tokens=context_tokens,
    )
    logger.info(
        "Graph-RAG efficiency for %s: full_repo_tokens=%d, "
        "context_tokens=%d, tokens_saved=%d, efficiency_percentage=%.2f",
        repo_name,
        metrics.full_repo_tokens,
        metrics.context_tokens,
        metrics.tokens_saved,
        metrics.efficiency_percentage,
    )
    return CodeAgentAnswer(answer=response, metrics=metrics)
