import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Agent Pipeline Service",
    description=(
        "3-agent GPT-powered incident analysis pipeline.\n\n"
        "**Flow:** POST /analyze → Agent 1 (triage + service config resolution) "
        "→ Agent 2 (log grep + stack trace extraction) "
        "→ Agent 3 (exact file:line code analysis)"
    ),
    version="2.0.0",
)


class LogPathsOverride(BaseModel):
    """
    Optional per-request override of log file paths.
    If omitted, paths are resolved from service_registry.json.
    """
    service: str | None = Field(None, description="Path to the service's main app log")
    error: str | None = Field(None, description="Path to the service's error log")
    api: str | None = Field(None, description="Path to the service's API/access log")


class ErrorPayload(BaseModel):
    service_name: str = Field(
        ..., description="Name of the affected service (must match service_registry.json or supply log_paths)"
    )
    error_message: str = Field(..., description="Raw error message or exception text")
    timestamp: str | None = Field(None, description="ISO-8601 timestamp of the error")
    error_code: str | None = Field(None, description="HTTP status code or app error code")
    environment: str = Field("production", description="Environment: production, staging, dev")

    # Optional overrides — use when the service is not in the registry
    log_paths: LogPathsOverride | None = Field(
        None,
        description=(
            "Override log file paths for this request. "
            "Omit to auto-resolve from service_registry.json."
        ),
    )
    repo_path: str | None = Field(
        None,
        description="Override the repo path for Agent 3. Omit to use the registry value.",
    )

    additional_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra fields: stack traces, request IDs, user IDs, etc.",
    )


@app.get("/health", tags=["meta"])
def health():
    """Liveness check."""
    return {"status": "ok"}


@app.get("/services", tags=["meta"])
def list_services():
    """List services registered in service_registry.json."""
    from service_registry import list_services as _ls, get_service_config
    return {
        svc: get_service_config(svc)
        for svc in _ls()
    }


@app.post("/analyze", tags=["pipeline"])
async def analyze(payload: ErrorPayload):
    """
    Trigger the 3-agent analysis pipeline for an error event.

    Agent 1 resolves the service's log paths and repo from the registry,
    Agent 2 greps the exact logs and extracts the stack trace,
    Agent 3 reads the precise file:line in the codebase to find the root cause.
    """
    try:
        result = await run_pipeline(payload.model_dump())
        return result
    except Exception as exc:
        logging.exception("Pipeline failure")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
