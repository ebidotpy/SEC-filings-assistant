from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import GroundedAnswer
from app.assistant.tools import read_chunk, read_surrounding_chunks, search_filings
from app.config import settings
from app.grounding.validator import GroundingError, validate_grounded_answer

_INSTRUCTIONS_PATH = Path(__file__).resolve().parent / "instructions.md"


def load_instructions() -> str:
    return _INSTRUCTIONS_PATH.read_text(encoding="utf-8")


def _build_agent() -> Agent[DocumentAgentDeps, GroundedAnswer]:
    model = OpenAIChatModel(
        settings.openai_chat_model,
        provider=OpenAIProvider(api_key=settings.openai_api_key),
    )
    agent: Agent[DocumentAgentDeps, GroundedAnswer] = Agent(
        model,
        name="document_agent",
        deps_type=DocumentAgentDeps,
        output_type=GroundedAnswer,
        instructions=load_instructions(),
        # Single retry knob in this pydantic-ai version; governs how many times a
        # failed output validation (ModelRetry) is fed back for self-correction.
        retries=settings.agent_output_retries,
        model_settings=OpenAIChatModelSettings(
            openai_reasoning_effort=settings.agent_reasoning_effort,
        ),
    )
    agent.tool(search_filings)
    agent.tool(read_chunk)
    agent.tool(read_surrounding_chunks)

    @agent.output_validator
    def _enforce_grounding(
        ctx: RunContext[DocumentAgentDeps],
        output: GroundedAnswer,
    ) -> GroundedAnswer:
        try:
            validate_grounded_answer(output, ctx.deps.registry)
        except GroundingError as error:
            raise ModelRetry(str(error)) from error
        return output

    return agent


document_agent = _build_agent()


def usage_limits() -> UsageLimits:
    return UsageLimits(
        request_limit=settings.agent_max_requests,
        tool_calls_limit=settings.agent_max_tool_calls,
    )
