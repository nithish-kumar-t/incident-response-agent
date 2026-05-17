import json
import logging
from abc import ABC, abstractmethod
from typing import Callable, Awaitable, Any

from openai import AsyncOpenAI
from config import settings

logger = logging.getLogger(__name__)

# Single shared client — change LLM_BASE_URL / LLM_API_KEY / LLM_MODEL in .env to switch providers
_client = AsyncOpenAI(
    base_url=settings.LLM_BASE_URL,
    api_key=settings.LLM_API_KEY,
)

ToolExecutor = Callable[[str, dict], Awaitable[Any]]


async def run_llm_agent(
    system_prompt: str,
    user_message: str,
    tools: list[dict],
    tool_executor: ToolExecutor,
    max_iterations: int = 10,
) -> str:
    """
    Runs an LLM agent loop with tool calling.
    Works with Ollama (default) or any OpenAI-compatible provider.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    for iteration in range(max_iterations):
        kwargs = {"model": settings.LLM_MODEL, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await _client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            return msg.content or ""

        logger.info("Iteration %d: executing %d tool call(s)", iteration + 1, len(msg.tool_calls))

        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            result = await tool_executor(fn_name, fn_args)
            result_str = json.dumps(result) if not isinstance(result, str) else result
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_str})

    return "[ERROR] Agent exceeded max iterations without producing a final answer."


def extract_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON from LLM output."""
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_output": raw, "parse_error": "Could not parse JSON from agent output"}


class BaseAgent(ABC):
    name: str
    description: str

    @abstractmethod
    def run(self, context: dict) -> str:
        """Run the agent with alert context. Returns analysis string."""
        pass
