from __future__ import annotations

import asyncio
import operator
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict

import logfire
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from openai import pydantic_function_tool
from openai.types.chat import (
    ChatCompletionMessageFunctionToolCall,
    ChatCompletionMessageParam,
)
from pydantic import ValidationError

from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import GroundedAnswer
from app.assistant.tools import run_tool, tool_definitions
from app.config import settings
from app.grounding.validator import GroundingError, validate_grounded_answer

_INSTRUCTIONS_PATH = Path(__file__).resolve().parent / "instructions.md"
_ANSWER_TOOL = "submit_answer"


class AgentInput(TypedDict):
    messages: list[ChatCompletionMessageParam]


class AgentOutput(TypedDict):
    grounded_answer: GroundedAnswer


class AgentState(TypedDict, total=False):
    messages: Annotated[list[ChatCompletionMessageParam], operator.add]
    tool_calls: list[ChatCompletionMessageFunctionToolCall]
    request_count: int
    tool_call_count: int
    output_retry_count: int
    grounded_answer: GroundedAnswer | None


class AgentLimitError(Exception):
    """Raised when a turn exceeds its model-request or retrieval-tool budget."""


def load_instructions() -> str:
    return _INSTRUCTIONS_PATH.read_text(encoding="utf-8")


async def _call_model(
    state: AgentState, runtime: Runtime[DocumentAgentDeps]
) -> AgentState:
    requests = state.get("request_count", 0)
    if requests >= settings.agent_max_requests:
        raise AgentLimitError("Maximum model requests exceeded")

    # Reasoning models reject temperature; standard chat models reject reasoning_effort.
    model_options = (
        {"reasoning_effort": settings.agent_reasoning_effort}
        if settings.openai_chat_model.startswith(("gpt-5", "o1", "o3", "o4"))
        else {"temperature": settings.agent_temperature}
    )
    with logfire.span("agent_model_request", model=settings.openai_chat_model):
        completion = await runtime.context.client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[
                {"role": "system", "content": load_instructions()},
                *state["messages"],
            ],
            tools=[
                *tool_definitions(),
                pydantic_function_tool(
                    GroundedAnswer,
                    name=_ANSWER_TOOL,
                    description="Submit the final answer with filing citations or explain insufficient evidence.",
                ),
            ],
            tool_choice="required",
            **model_options,
        )
    message = completion.choices[0].message
    assistant_message = message.model_dump(
        include={"role", "content", "tool_calls"}, exclude_none=True
    )
    if not message.tool_calls and message.content is None:
        # Correction requests still need a valid assistant message after a refusal.
        assistant_message["content"] = message.refusal or ""
    return {
        "messages": [assistant_message],
        "tool_calls": message.tool_calls or [],
        "request_count": requests + 1,
    }


def _route_model(state: AgentState) -> Literal["tools", "validate"]:
    if any(call.function.name != _ANSWER_TOOL for call in state["tool_calls"]):
        return "tools"
    return "validate"


async def _run_tools(
    state: AgentState, runtime: Runtime[DocumentAgentDeps]
) -> AgentState:
    calls = [call for call in state["tool_calls"] if call.function.name != _ANSWER_TOOL]
    count = state.get("tool_call_count", 0) + len(calls)
    if count > settings.agent_max_tool_calls:
        raise AgentLimitError("Maximum retrieval tool calls exceeded")

    writer = get_stream_writer()
    with logfire.span("agent_retrieval_tools", tool_count=len(calls)):
        results = await asyncio.gather(
            *(
                run_tool(
                    call.function.name,
                    call.function.arguments,
                    runtime.context,
                    status_writer=writer,
                )
                for call in calls
            )
        )
    return {
        "messages": [
            {"role": "tool", "tool_call_id": call.id, "content": result}
            for call, result in zip(calls, results, strict=True)
        ],
        "tool_call_count": count,
    }


def _route_tools(state: AgentState) -> Literal["model", "validate"]:
    if any(call.function.name == _ANSWER_TOOL for call in state["tool_calls"]):
        return "validate"
    return "model"


def _validate_answer(
    state: AgentState, runtime: Runtime[DocumentAgentDeps]
) -> AgentState:
    writer = get_stream_writer()
    writer("Drafting grounded answer…")
    writer("Validating citations…")
    calls = [call for call in state["tool_calls"] if call.function.name == _ANSWER_TOOL]
    try:
        if len(calls) != 1:
            raise GroundingError(
                "Call submit_answer exactly once with a structured answer"
            )
        answer = GroundedAnswer.model_validate_json(calls[0].function.arguments)
        with logfire.span("agent_validate_answer"):
            validate_grounded_answer(answer, runtime.context.registry)
    except (GroundingError, ValidationError) as error:
        retries = state.get("output_retry_count", 0)
        if retries >= settings.agent_output_retries:
            raise GroundingError(str(error)) from error
        feedback = f"Answer validation failed: {error}. Correct the answer and call submit_answer again."
        messages = (
            [
                {"role": "tool", "tool_call_id": call.id, "content": feedback}
                for call in calls
            ]
            if calls
            else [{"role": "user", "content": feedback}]
        )
        return {
            "messages": messages,
            "output_retry_count": retries + 1,
            "grounded_answer": None,
        }
    return {"grounded_answer": answer}


def _route_validation(state: AgentState) -> Literal["model", "__end__"]:
    return END if state.get("grounded_answer") is not None else "model"


def graph_config(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    # One request can visit model, tools, and validation before the next request.
    return {
        "recursion_limit": 3 * settings.agent_max_requests + 1,
        "metadata": metadata or {},
    }


def _build_agent() -> CompiledStateGraph:
    graph = StateGraph(
        AgentState,
        context_schema=DocumentAgentDeps,
        input_schema=AgentInput,
        output_schema=AgentOutput,
    )
    graph.add_node("model", _call_model)
    graph.add_node("tools", _run_tools)
    graph.add_node("validate", _validate_answer)
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", _route_model)
    graph.add_conditional_edges("tools", _route_tools)
    graph.add_conditional_edges("validate", _route_validation)
    return graph.compile(name="document_agent")


document_agent = _build_agent()
