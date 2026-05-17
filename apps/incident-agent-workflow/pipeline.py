"""
Incident Response Pipeline — orchestrates the 3-agent workflow:
  1. TriageAgent    — classifies severity and resolves service config
  2. InvestigationAgent — reads logs, extracts stack traces
  3. CodeAnalysisAgent  — pinpoints root cause in source code
"""
import logging
import uuid
from datetime import datetime, timezone

from agents import triage_agent, investigation_agent, code_analysis_agent

logger = logging.getLogger(__name__)


async def run_pipeline(error_payload: dict) -> dict:
    pipeline_id = str(uuid.uuid4())[:8].upper()
    started_at = datetime.now(timezone.utc).isoformat()
    logger.info("[Pipeline %s] START — service=%s alert=%s",
                pipeline_id, error_payload.get("service"), error_payload.get("alertname"))

    # ── Triage ────────────────────────────────────────────────────────────────
    logger.info("[Pipeline %s] TriageAgent running…", pipeline_id)
    triage = await triage_agent.run(error_payload)
    logger.info("[Pipeline %s] TriageAgent done — type=%s severity=%s",
                pipeline_id, triage.get("error_type"), triage.get("severity"))

    # Guarantee resolved_config always carries repo_path + log_paths even when
    # the service is not in the registry (LLM may omit it in that case).
    rc = triage.get("resolved_config") or {}
    if not rc.get("repo_path"):
        rc["repo_path"] = error_payload.get("repo_path", "")
    if not rc.get("log_paths"):
        rc["log_paths"] = error_payload.get("log_paths", {})
    triage["resolved_config"] = rc

    # ── Investigation ─────────────────────────────────────────────────────────
    logger.info("[Pipeline %s] InvestigationAgent (%s) running…",
                pipeline_id, triage.get("error_type", "?"))
    investigation = await investigation_agent.run(triage)
    logger.info("[Pipeline %s] InvestigationAgent done — confidence=%s",
                pipeline_id, investigation.get("confidence"))

    # ── Code Analysis ─────────────────────────────────────────────────────────
    logger.info("[Pipeline %s] CodeAnalysisAgent running…", pipeline_id)
    code_analysis = await code_analysis_agent.run(triage, investigation)
    logger.info("[Pipeline %s] CodeAnalysisAgent done — depth=%s complexity=%s",
                pipeline_id, code_analysis.get("analysis_depth"), code_analysis.get("complexity_assessment"))

    return {
        "pipeline_id": pipeline_id,
        "status": "completed",
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "triage": triage,
        "investigation": investigation,
        "code_analysis": code_analysis,
    }
