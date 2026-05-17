import os
from agents.base import BaseAgent
from llm.ollama_client import send_prompt
from config import settings


class LogAnalyzerAgent(BaseAgent):
    name = "Log Analyzer"
    description = "Reads recent logs from the affected service and asks the LLM to explain what went wrong."

    def run(self, context: dict) -> str:
        service = context.get("service", "unknown")
        alert_name = context.get("alertname", "unknown")
        summary = context.get("summary", "")

        logs = self._read_logs(service)
        prompt = self._build_prompt(service, alert_name, summary, logs)
        return send_prompt(prompt)

    def _read_logs(self, service: str) -> str:
        log_path = settings.SERVICE_LOG_FILES.get(service)

        if not log_path:
            return f"No log file configured for service '{service}'."

        if not os.path.exists(log_path):
            return f"Log file not found at {log_path}."

        with open(log_path, "r") as f:
            lines = f.readlines()

        tail = lines[-settings.LOG_TAIL_LINES:]
        return "".join(tail)

    def _build_prompt(self, service: str, alert_name: str, summary: str, logs: str) -> str:
        return f"""You are an incident response agent analyzing a production alert.

Alert: {alert_name}
Service: {service}
Summary: {summary}

Recent logs from {service}:
---
{logs}
---

Analyze the logs and answer:
1. What went wrong?
2. When did it start?
3. What is the likely root cause?
4. What should the on-call engineer check first?

Be concise and specific."""
