import argparse
import json
import os
from typing import Annotated

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict

from database import Neo4jDatabase


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


@tool
def get_function_callers(function_name: str) -> str:
    """Find functions that directly call the named or qualified Python function."""
    normalized_name = function_name.strip()
    if not normalized_name:
        return json.dumps({"function_name": function_name, "callers": []})

    with Neo4jDatabase() as database:
        callers = database.get_function_callers(normalized_name)

    return json.dumps(
        {"function_name": normalized_name, "callers": callers},
        default=str,
    )


SYSTEM_PROMPT = """You answer questions about a Python codebase call graph.
Use get_function_callers when the user asks which functions call another function.
Base code-graph claims on tool results. If no callers are returned, say that none
were found in the indexed graph; do not invent relationships.
"""


def build_agent():
    model = ChatAnthropic(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
        temperature=0,
    )
    tools = [get_function_callers]
    model_with_tools = model.bind_tools(tools)

    def call_model(state: AgentState) -> dict[str, list[AnyMessage]]:
        response = model_with_tools.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        )
        return {"messages": [response]}

    builder = StateGraph(AgentState)
    builder.add_node("agent", call_model)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        tools_condition,
        {"tools": "tools", END: END},
    )
    builder.add_edge("tools", "agent")
    return builder.compile()


def run_agent(user_query: str) -> str:
    graph = build_agent()
    result = graph.invoke({"messages": [HumanMessage(content=user_query)]})
    return str(result["messages"][-1].content)


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def stream_agent(user_query: str):
    """Yield only user-visible text chunks from the LangGraph execution."""
    graph = build_agent()
    for message, metadata in graph.stream(
        {"messages": [HumanMessage(content=user_query)]},
        stream_mode="messages",
    ):
        if metadata.get("langgraph_node") != "agent":
            continue
        text = _content_text(message.content)
        if text:
            yield text


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask questions about the call graph")
    parser.add_argument("query", help="Question for the call-graph agent")
    args = parser.parse_args()
    print(run_agent(args.query))


if __name__ == "__main__":
    main()
