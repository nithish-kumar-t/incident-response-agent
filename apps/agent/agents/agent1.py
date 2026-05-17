"""
Agent 1 — Error Triage
1. Resolves the service's log paths and repo path from the service registry.
2. Classifies the error type and severity.
3. Takes predefined actions (log, alert, incident).
4. Passes resolved paths forward so Agent 2 knows exactly which files to read.
"""
import json
import logging
from datetime import datetime, timezone

from agents.base import run_agent, extract_json
from service_registry import get_service_config, list_services

logger = logging.getLogger(__name__)

_SYSTEM = """You are the Error Triage Agent (Agent 1) in an automated incident response pipeline.

Step-by-step responsibilities:
1. Call resolve_service_config with the service name to get its exact log file paths,
   repo path, and health URL. If the service is unknown, use the fallback paths from
   the error payload.
2. Classify the error as exactly one of:
   - "service_error": infrastructure outage, crash, DB failure, network issue,
     timeout, resource exhaustion, process killed
   - "api_error": HTTP 4xx/5xx, auth failure, malformed payload, rate limiting,
     downstream API contract violation
3. Assess severity: critical | high | medium | low
4. Take predefined actions:
   - Always call log_error first.
   - Call send_alert for high or critical severity.
   - Call create_incident for critical severity.
   - Call tag_error_type with 2-4 relevant tags.
5. Return ONLY a JSON object (no prose, no markdown fences):

{
  "error_type": "service_error" | "api_error",
  "severity": "critical" | "high" | "medium" | "low",
  "service_name": "<name>",
  "error_summary": "<one sentence>",
  "key_indicators": ["<indicator>", ...],
  "actions_taken": ["<description>", ...],
  "recommended_investigation": "<what Agent 2 should focus on>",
  "resolved_config": {
    "health_url": "<url>",
    "log_paths": {"service": "<path>", "error": "<path>", "api": "<path>"},
    "repo_path": "<absolute path to the service codebase>",
    "language": "<python|java|go|...>"
  }
}

The resolved_config block is critical — Agent 2 and Agent 3 will use it directly."""

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "resolve_service_config",
            "description": (
                "Look up the service registry to get this service's exact log file paths, "
                "repo path, and health endpoint URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {"type": "string"}
                },
                "required": ["service_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_error",
            "description": "Persist the error record to the incident tracking system.",
            "parameters": {
                "type": "object",
                "properties": {
                    "error_type": {"type": "string", "enum": ["service_error", "api_error"]},
                    "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                    "service_name": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["error_type", "severity", "service_name", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_alert",
            "description": "Notify the on-call team via the specified channel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "enum": ["slack", "pagerduty", "email"]},
                    "message": {"type": "string"},
                    "severity": {"type": "string"},
                },
                "required": ["channel", "message", "severity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_incident",
            "description": "Open a formal incident ticket in the incident management system.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "severity": {"type": "string"},
                    "service": {"type": "string"},
                },
                "required": ["title", "description", "severity", "service"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tag_error_type",
            "description": "Apply categorisation tags for metrics and routing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "error_type": {"type": "string"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "e.g. ['database', 'timeout', 'auth', 'rate-limit']",
                    },
                },
                "required": ["error_type", "tags"],
            },
        },
    },
]

_incident_counter = 0


async def _executor(fn_name: str, fn_args: dict) -> dict:
    global _incident_counter
    now = datetime.now(timezone.utc).isoformat()

    if fn_name == "resolve_service_config":
        svc = fn_args["service_name"]
        config = get_service_config(svc)
        if config:
            logger.info("[Agent1] Resolved config for '%s': %s", svc, config)
            return {"found": True, "service": svc, **config}
        known = list_services()
        logger.warning("[Agent1] Service '%s' not in registry. Known: %s", svc, known)
        return {
            "found": False,
            "service": svc,
            "message": f"Service not in registry. Known services: {known}. "
                       "Use paths from the error payload or config defaults.",
        }

    if fn_name == "log_error":
        log_id = f"ERR-{abs(hash(fn_args['message'])) % 100_000:05d}"
        logger.info("[Agent1] log_error → %s (%s/%s)", log_id, fn_args["severity"], fn_args["error_type"])
        return {"status": "logged", "log_id": log_id, "timestamp": now}

    if fn_name == "send_alert":
        logger.info("[Agent1] send_alert → %s via %s", fn_args["severity"], fn_args["channel"])
        return {"status": "alert_sent", "channel": fn_args["channel"], "timestamp": now}

    if fn_name == "create_incident":
        _incident_counter += 1
        iid = f"INC-{_incident_counter:04d}"
        logger.info("[Agent1] create_incident → %s: %s", iid, fn_args["title"])
        return {"status": "incident_created", "incident_id": iid, "timestamp": now}

    if fn_name == "tag_error_type":
        logger.info("[Agent1] tag_error_type → %s", fn_args["tags"])
        return {"status": "tagged", "applied_tags": fn_args["tags"]}

    return {"error": f"Unknown tool: {fn_name}"}


async def run(error_payload: dict) -> dict:
    user_msg = f"Incoming error report:\n{json.dumps(error_payload, indent=2)}"
    raw = await run_agent(_SYSTEM, user_msg, _TOOLS, _executor)
    return extract_json(raw)
