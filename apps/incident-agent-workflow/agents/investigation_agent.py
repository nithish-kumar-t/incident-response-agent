"""
Investigation Agent — reads logs from the paths resolved by Triage Agent.
Branches on error_type: service errors check health + grep service logs;
API errors grep error and api logs. Passes the raw stack trace to Code Analysis Agent.
"""
import asyncio
import json
import logging

import httpx

from agents.base import run_llm_agent, extract_json
from tools.logs import read_log_file, grep_log_file, extract_stack_trace

logger = logging.getLogger(__name__)

_SYSTEM_SERVICE = """You are the Investigation Agent for a SERVICE ERROR.

You have received the resolved log paths and health URL for this specific service from the Triage Agent.
Use them directly — do NOT guess or substitute paths.

Step-by-step:
1. Call check_service_health to get live status.
2. Call grep_log_file on the service log path with the core error keyword
   (e.g. "Connection refused", "OOM", "segfault") to find exact matching lines.
3. Call extract_stack_trace on the same log path to capture the full exception block.
4. If an error log path was provided, call grep_log_file on it too for corroboration.
5. Synthesise all evidence into a clear inference and include the raw stack trace.

Return ONLY a JSON object (no prose, no markdown fences):
{
  "error_type": "service_error",
  "service_health": {"status": "<up|down|degraded>", "details": "<summary>"},
  "log_evidence": [
    {"log_path": "<path>", "line": <n>, "matched_line": "<text>", "context": "<surrounding lines>"}
  ],
  "stack_trace": "<raw stack trace text from the log, empty string if not found>",
  "root_cause_hypothesis": "<one sentence>",
  "affected_components": ["<component>", ...],
  "inference": "<detailed paragraph — what the logs reveal about the cause>",
  "confidence": "high" | "medium" | "low",
  "suggested_files_to_check": [
    "<repo-relative file path from stack trace or hypothesis>", ...
  ]
}"""

_SYSTEM_API = """You are the Investigation Agent for an API ERROR.

You have the resolved log paths for this specific service from the Triage Agent. Use them directly.

Step-by-step:
1. Call grep_log_file on the error log path with the HTTP status or exception keyword.
2. Call grep_log_file on the api log path with the endpoint or request pattern.
3. Call extract_stack_trace on whichever log had the clearest hit to get the full trace.
4. Identify which endpoint failed, what error was returned, and trace it to a cause.

Return ONLY a JSON object (no prose, no markdown fences):
{
  "error_type": "api_error",
  "error_log_evidence": [
    {"log_path": "<path>", "line": <n>, "matched_line": "<text>", "context": "<surrounding lines>"}
  ],
  "api_log_evidence": [
    {"log_path": "<path>", "line": <n>, "matched_line": "<text>", "context": "<surrounding lines>"}
  ],
  "stack_trace": "<raw stack trace text from the log, empty string if not found>",
  "root_cause_hypothesis": "<one sentence>",
  "affected_endpoints": ["<endpoint>", ...],
  "inference": "<detailed paragraph — what the logs reveal about the API failure cause>",
  "confidence": "high" | "medium" | "low",
  "suggested_files_to_check": [
    "<repo-relative file path from stack trace or hypothesis>", ...
  ]
}"""

_SHARED_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "grep_log_file",
            "description": (
                "Search a specific log file for an error pattern and return matching lines "
                "with surrounding context. Always use the exact path from resolved_config."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "log_path": {"type": "string", "description": "Absolute path to the log file"},
                    "pattern": {"type": "string", "description": "Regex or keyword to search for"},
                    "context_lines": {
                        "type": "integer",
                        "description": "Lines of context before/after each match (default 10)",
                        "default": 10,
                    },
                },
                "required": ["log_path", "pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_stack_trace",
            "description": (
                "Find the last occurrence of the error pattern in the log file and return "
                "the full stack trace block that follows it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "log_path": {"type": "string", "description": "Absolute path to the log file"},
                    "error_pattern": {
                        "type": "string",
                        "description": "Pattern that marks the start of the error (e.g. 'Traceback', 'Exception', 'ERROR')",
                    },
                    "max_trace_lines": {
                        "type": "integer",
                        "description": "Max lines to capture after the match (default 40)",
                        "default": 40,
                    },
                },
                "required": ["log_path", "error_pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_log_file",
            "description": "Read the last N lines of a log file (use when you want a broad tail view).",
            "parameters": {
                "type": "object",
                "properties": {
                    "log_path": {"type": "string", "description": "Absolute path to the log file"},
                    "lines": {"type": "integer", "description": "Number of tail lines (default 100)", "default": 100},
                },
                "required": ["log_path"],
            },
        },
    },
]

_SERVICE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_service_health",
            "description": "Call the live health-check endpoint and return its status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "health_url": {
                        "type": "string",
                        "description": "Full URL of the health endpoint from resolved_config",
                    }
                },
                "required": ["health_url"],
            },
        },
    },
] + _SHARED_TOOLS


async def _service_executor(fn_name: str, fn_args: dict):
    if fn_name == "check_service_health":
        url = fn_args["health_url"]
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                r = await client.get(url)
                try:
                    body = r.json()
                except Exception:
                    body = r.text[:500]
                return {"url": url, "status_code": r.status_code,
                        "healthy": 200 <= r.status_code < 300, "response": body}
            except httpx.ConnectError:
                return {"url": url, "healthy": False, "error": "connection refused — service is down"}
            except Exception as e:
                return {"url": url, "healthy": False, "error": str(e)}
    return await _shared_executor(fn_name, fn_args)


async def _api_executor(fn_name: str, fn_args: dict):
    return await _shared_executor(fn_name, fn_args)


async def _shared_executor(fn_name: str, fn_args: dict):
    if fn_name == "grep_log_file":
        return await asyncio.to_thread(
            grep_log_file, fn_args["log_path"], fn_args["pattern"],
            fn_args.get("context_lines", 10),
        )
    if fn_name == "extract_stack_trace":
        return await asyncio.to_thread(
            extract_stack_trace, fn_args["log_path"], fn_args["error_pattern"],
            fn_args.get("max_trace_lines", 40),
        )
    if fn_name == "read_log_file":
        return await asyncio.to_thread(
            read_log_file, fn_args["log_path"], fn_args.get("lines", 100),
        )
    return {"error": f"Unknown tool: {fn_name}"}


async def run(triage_result: dict) -> dict:
    error_type = triage_result.get("error_type", "service_error")
    context = json.dumps(triage_result, indent=2)

    base_msg = (
        f"Triage Agent result (includes resolved_config with exact log paths):\n{context}\n\n"
        "Use the log paths from resolved_config['log_paths'] — do not substitute or guess paths."
    )

    if error_type == "service_error":
        raw = await run_llm_agent(_SYSTEM_SERVICE, base_msg, _SERVICE_TOOLS, _service_executor)
    else:
        raw = await run_llm_agent(_SYSTEM_API, base_msg, _SHARED_TOOLS, _api_executor)

    return extract_json(raw)
