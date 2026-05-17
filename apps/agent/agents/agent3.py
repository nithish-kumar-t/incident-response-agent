"""
Agent 3 — Code Analysis
Receives Agent 2's inference + raw stack trace. Uses the repo_path from
resolved_config to read only the exact files and line ranges implicated by
the stack trace, then pinpoints the root cause.

If scope is too broad (>5 files or multiple subsystems), switches to suggesting
concrete alternative investigation strategies.
"""
import asyncio
import json
import logging

from agents.base import run_agent, extract_json
from tools.git import (
    list_repo_files,
    read_file_lines,
    grep_codebase,
    get_git_log,
    parse_stack_trace_locations,
)

logger = logging.getLogger(__name__)

_SYSTEM = """You are the Code Analysis Agent (Agent 3) in an automated incident response pipeline.

You have:
- Agent 1's triage (service name, error type, resolved_config with repo_path)
- Agent 2's investigation (inference, raw stack_trace, suggested_files_to_check)

Your job is to pinpoint the exact root cause in the source code. Work step by step:

STEP 1 — Parse the stack trace:
  Call parse_stack_trace to extract file:line locations from the raw stack trace text.

STEP 2 — Read exact code locations:
  For each location from the stack trace (up to 5), call read_file_lines with a
  ±20-line window around the implicated line. This shows the exact code that was
  executing when the error occurred.

STEP 3 — Trace deeper if needed (max 2 hops):
  If the root cause is not at the stack trace location itself (e.g. the issue is in
  a called function), call grep_codebase to find its definition, then read_file_lines
  on that location.

STEP 4 — Check recent changes:
  Call get_git_log for the most implicated file to see if a recent commit introduced the bug.

COMPLEXITY RULE — strictly enforced:
  If tracing the cause requires >5 distinct files or spans >2 subsystems, stop deep
  analysis. Set complexity_assessment to "too_complex" and populate alternative_solutions
  with concrete, actionable options (e.g. "add distributed tracing", "run profiler X",
  "isolate component Y and reproduce"). Do NOT produce vague guesses.

Return ONLY a JSON object (no prose, no markdown fences):
{
  "analysis_depth": "deep" | "shallow",
  "complexity_assessment": "manageable" | "too_complex",
  "stack_trace_locations": [
    {"file": "<repo-relative path>", "line": <n>}
  ],
  "files_analyzed": ["<path>", ...],
  "root_cause": "<specific finding at file:line, or 'undetermined — see alternative_solutions'>",
  "affected_code": [
    {
      "file": "<path>",
      "line": <n>,
      "snippet": "<the problematic line(s)>",
      "issue": "<why this is wrong>"
    }
  ],
  "fix_suggestion": "<specific code-level fix if manageable>",
  "alternative_solutions": [
    "<actionable alternative 1 if too_complex>",
    "..."
  ],
  "recommended_next_steps": ["<step1>", "<step2>", ...]
}"""

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "parse_stack_trace",
            "description": (
                "Parse a raw stack trace string and extract all file:line references. "
                "Always call this first before reading any files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stack_trace": {
                        "type": "string",
                        "description": "The raw stack trace text from Agent 2's output",
                    }
                },
                "required": ["stack_trace"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file_lines",
            "description": (
                "Read a specific range of lines from a source file in the service's repo. "
                "Use this to view the exact code at a stack trace location. "
                "Always pass the repo_path from resolved_config."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the service repo (from resolved_config.repo_path)",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Repo-relative path to the file",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "First line to read (use stack_trace line minus ~20 for context)",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Last line to read (use stack_trace line plus ~20 for context)",
                    },
                },
                "required": ["repo_path", "file_path", "start_line", "end_line"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_codebase",
            "description": (
                "Search the entire codebase for a pattern (function name, class, variable, "
                "error string). Use this to find the definition of something implicated by "
                "the stack trace."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the service repo (from resolved_config.repo_path)",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Regex or keyword to search for in the source code",
                    },
                    "extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "File extensions to limit search to, e.g. ['py', 'java', 'go']",
                        "default": [],
                    },
                },
                "required": ["repo_path", "pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_git_log",
            "description": "Get recent commit history for a specific file to spot recent regressions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "file_path": {
                        "type": "string",
                        "description": "Repo-relative file path (empty for full repo log)",
                        "default": "",
                    },
                    "n": {"type": "integer", "description": "Number of commits (default 10)", "default": 10},
                },
                "required": ["repo_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_repo_files",
            "description": "List files in the repo (use only if you need to discover structure first).",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "directory": {"type": "string", "default": ""},
                    "branch": {"type": "string", "default": "HEAD"},
                },
                "required": ["repo_path"],
            },
        },
    },
]


async def _executor(fn_name: str, fn_args: dict):
    if fn_name == "parse_stack_trace":
        locations = parse_stack_trace_locations(fn_args["stack_trace"])
        logger.info("[Agent3] parse_stack_trace → %d locations", len(locations))
        return {"locations": locations}

    if fn_name == "read_file_lines":
        return await asyncio.to_thread(
            read_file_lines,
            fn_args["repo_path"],
            fn_args["file_path"],
            fn_args["start_line"],
            fn_args["end_line"],
        )

    if fn_name == "grep_codebase":
        return await asyncio.to_thread(
            grep_codebase,
            fn_args["repo_path"],
            fn_args["pattern"],
            fn_args.get("extensions", []),
        )

    if fn_name == "get_git_log":
        return await asyncio.to_thread(
            get_git_log,
            fn_args["repo_path"],
            fn_args.get("file_path", ""),
            fn_args.get("n", 10),
        )

    if fn_name == "list_repo_files":
        return await asyncio.to_thread(
            list_repo_files,
            fn_args["repo_path"],
            fn_args.get("directory", ""),
            fn_args.get("branch", "HEAD"),
        )

    return {"error": f"Unknown tool: {fn_name}"}


async def run(agent1_result: dict, agent2_result: dict) -> dict:
    repo_path = (agent1_result.get("resolved_config") or {}).get("repo_path", "unknown")
    stack_trace = agent2_result.get("stack_trace", "")
    suggested = agent2_result.get("suggested_files_to_check", [])

    if stack_trace:
        how_to_start = (
            f"Stack trace is available. Follow STEP 1-4 from your instructions:\n"
            f"1. Call parse_stack_trace on the stack trace below.\n"
            f"2. Read each implicated file:line with read_file_lines (±20 lines).\n"
            f"3. Trace deeper with grep_codebase if the call site is not the root cause.\n"
            f"4. Call get_git_log on the most implicated file.\n"
            f"repo_path for ALL tool calls: {repo_path}"
        )
    else:
        suggested_str = ", ".join(suggested) if suggested else "(none provided)"
        how_to_start = (
            f"No stack trace is available. Do NOT give up — read the code directly:\n"
            f"1. Call list_repo_files to discover the structure at {repo_path}.\n"
            f"2. For each file in suggested_files_to_check ({suggested_str}), call "
            f"read_file_lines (lines 1-100 to start, then narrow down).\n"
            f"3. Call grep_codebase on the error keyword to find the exact location.\n"
            f"4. Call get_git_log to check for recent regressions.\n"
            f"repo_path for ALL tool calls: {repo_path}\n\n"
            f"You MUST call at least one of list_repo_files, read_file_lines, or grep_codebase "
            f"before producing your final JSON — do not return undetermined without reading code."
        )

    user_msg = (
        f"Agent 1 triage (repo_path = '{repo_path}'):\n{json.dumps(agent1_result, indent=2)}\n\n"
        f"Agent 2 investigation:\n{json.dumps(agent2_result, indent=2)}\n\n"
        f"Stack trace:\n{stack_trace or '(none)'}\n\n"
        f"{how_to_start}"
    )
    raw = await run_agent(_SYSTEM, user_msg, _TOOLS, _executor)
    return extract_json(raw)
