import logging
import uuid
from datetime import datetime, timezone

from agents import agent1, agent2, agent3

logger = logging.getLogger(__name__)


async def run_pipeline(error_payload: dict) -> dict:
    pipeline_id = str(uuid.uuid4())[:8].upper()
    started_at = datetime.now(timezone.utc).isoformat()
    logger.info("[Pipeline %s] START — payload: %s", pipeline_id, error_payload)

    # ── Agent 1: triage ───────────────────────────────────────────────────────
    logger.info("[Pipeline %s] Agent 1 (Triage) running…", pipeline_id)
    a1 = await agent1.run(error_payload)
    logger.info("[Pipeline %s] Agent 1 done — type=%s severity=%s", pipeline_id,
                a1.get("error_type"), a1.get("severity"))

    # ── Agent 2: investigation (branches on error_type) ───────────────────────
    logger.info("[Pipeline %s] Agent 2 (Investigation/%s) running…",
                pipeline_id, a1.get("error_type", "?"))
    a2 = await agent2.run(a1)
    logger.info("[Pipeline %s] Agent 2 done — confidence=%s", pipeline_id, a2.get("confidence"))

    # ── Agent 3: code analysis ────────────────────────────────────────────────
    logger.info("[Pipeline %s] Agent 3 (Code Analysis) running…", pipeline_id)
    a3 = await agent3.run(a1, a2)
    logger.info("[Pipeline %s] Agent 3 done — depth=%s complexity=%s",
                pipeline_id, a3.get("analysis_depth"), a3.get("complexity_assessment"))

    return {
        "pipeline_id": pipeline_id,
        "status": "completed",
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "agent1_triage": a1,
        "agent2_investigation": a2,
        "agent3_code_analysis": a3,
    }
