import json
import logging
from typing import Any, Awaitable, Callable

from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)

ToolExecutor = Callable[[str, dict], Awaitable[Any]]


async def run_agent(
    system_prompt: str,
    user_message: str,
    tools: list[dict],
    tool_executor: ToolExecutor,
    max_iterations: int = 15,
) -> str:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required to run the 3-agent pipeline")

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    messages: list = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    for iteration in range(max_iterations):
        kwargs: dict = {"model": settings.OPENAI_MODEL, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            return msg.content or ""

        logger.info("iter %d: executing %d tool call(s)", iteration + 1, len(msg.tool_calls))

        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            try:
                fn_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            result = await tool_executor(fn_name, fn_args)
            result_text = json.dumps(result) if not isinstance(result, str) else result
            messages.append(
                {"role": "tool", "tool_call_id": tool_call.id, "content": result_text}
            )

    return "[ERROR] Agent exceeded max iterations without producing a final answer."


def extract_json(raw: str) -> dict:
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_output": raw, "parse_error": "Could not parse structured JSON from agent"}
