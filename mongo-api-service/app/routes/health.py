from fastapi import APIRouter
from datetime import datetime, timezone

from app.database import client, get_db
from app.config import settings
from app.logger import get_logger

router = APIRouter(tags=["health"])
log = get_logger(__name__)

START_TIME = datetime.now(timezone.utc)


@router.get("/health")
async def health():
    """Liveness probe — returns 200 if the service is running."""
    return {"status": "ok", "service": settings.APP_NAME}


@router.get("/health/ready")
async def readiness():
    """Readiness probe — checks MongoDB connectivity."""
    try:
        await client.admin.command("ping")
        db = get_db()
        stats = await db.command("dbStats")
        mongo_ok = True
        collections = stats.get("collections", 0)
    except Exception as exc:
        log.error(f"Readiness check failed: {exc}")
        mongo_ok = False
        collections = None

    uptime_seconds = (datetime.now(timezone.utc) - START_TIME).total_seconds()

    status = "ready" if mongo_ok else "degraded"
    return {
        "status": status,
        "uptime_seconds": round(uptime_seconds, 1),
        "mongo": {
            "connected": mongo_ok,
            "database": settings.MONGO_DB,
            "collections": collections,
        },
    }
