"""The agent: a plain tool-calling loop ending in a `final_answer` call (ADR-0001, ADR-0007)."""

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from eval_harness.config import AgentSettings
from eval_harness.final_answer import FINAL_ANSWER_TOOL, FinalAnswer, parse_final_answer
from eval_harness.openrouter import ChatResponse, ModelInfo, OpenRouterClient
from eval_harness.refs import article_key
from eval_harness.trace import Trace, retrieved_articles

PROVIDERS_NEEDING_CACHE_CONTROL = ("anthropic/", "qwen/")
FINISH_REMINDER = "Finish by calling the final_answer tool."


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    run: Callable[[dict[str, Any]], Any]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def run_agent(
    client: OpenRouterClient,
    *,
    model: ModelInfo,
    system_prompt: str,
    user_input: str,
    tools: list[Tool],
    settings: AgentSettings,
    provider: dict[str, Any],
    trace: Trace,
    on_response: Callable[[ChatResponse], None],
) -> FinalAnswer:
    """Run one case. Returns the final answer, or `FinalAnswer.limit()` when a cap is hit."""
    tools_by_name = {tool.name: tool for tool in tools}
    stable_prefix = _stable_prefix(model, system_prompt, tools, settings, provider)
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_input}]

    for turn in range(1, settings.max_turns + 1):
        payload = {**stable_prefix, "messages": [*stable_prefix["messages"], *messages]}
        trace.add("request", turn=turn, payload=payload)
        started = time.monotonic()
        response = client.chat(payload)
        trace.add(
            "response",
            turn=turn,
            latency_s=round(time.monotonic() - started, 3),
            finish_reason=response.finish_reason,
            provider=response.provider,
            message=response.message,
            usage=response.usage,
        )
        on_response(response)

        if response.finish_reason == "length":
            trace.add("limit", reason="max_tokens", turn=turn)
            return FinalAnswer.limit()

        messages.append(response.message)
        tool_calls = response.message.get("tool_calls") or []
        if not tool_calls:
            messages.append({"role": "user", "content": FINISH_REMINDER})
            continue

        for call in tool_calls:
            name = call["function"]["name"]
            arguments: Any = call["function"]["arguments"]
            try:
                arguments = json.loads(arguments or "{}")
                if name == "final_answer":
                    final = parse_final_answer(arguments)
                    _refuse_unread_citations(final, trace)
                    trace.add("final_answer", turn=turn, **asdict(final))
                    return final
                if name not in tools_by_name:
                    raise ValueError(f"unknown tool {name!r}")
                result = {"result": tools_by_name[name].run(arguments)}
            except (ValueError, TypeError, KeyError) as exc:
                result = {"error": str(exc)}
            trace.add(
                "tool_call", turn=turn, id=call["id"], name=name, arguments=arguments, **result
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

    trace.add("limit", reason="max_turns", turn=settings.max_turns)
    return FinalAnswer.limit()


def _refuse_unread_citations(final: FinalAnswer, trace: Trace) -> None:
    cited = {article_key(c.instrument, c.article) for c in final.citations}
    unread = sorted(cited - retrieved_articles(trace.steps))
    if unread:
        raise ValueError(
            f"you cited articles you have not read in this conversation: {', '.join(unread)}. "
            "Read them with your tools or remove them from the citations, then call "
            "final_answer again."
        )


def _stable_prefix(
    model: ModelInfo,
    system_prompt: str,
    tools: list[Tool],
    settings: AgentSettings,
    provider: dict[str, Any],
) -> dict[str, Any]:
    """Everything that is identical across turns and cases, so providers can cache it."""
    system_part: dict[str, Any] = {"type": "text", "text": system_prompt}
    if model.id.startswith(PROVIDERS_NEEDING_CACHE_CONTROL):
        system_part["cache_control"] = {"type": "ephemeral"}
    prefix: dict[str, Any] = {
        "model": model.id,
        "messages": [{"role": "system", "content": [system_part]}],
        "tools": [*(tool.schema() for tool in tools), FINAL_ANSWER_TOOL],
        "max_tokens": settings.max_tokens,
        "provider": provider,
    }
    if "temperature" in model.supported_parameters:
        prefix["temperature"] = 0
    if "reasoning" in model.supported_parameters:
        prefix["reasoning"] = {"effort": settings.reasoning_effort}
    return prefix
