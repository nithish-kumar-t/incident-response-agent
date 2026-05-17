from agents.base import BaseAgent
from llm.ollama_client import send_prompt


class LogAnalyzerAgent(BaseAgent):
    name = "Log Analyzer"
    description = "Analyzes Prometheus metrics and Loki logs to explain what went wrong."

    def run(self, context: dict) -> str:
        service = context.get("service", "unknown")
        alert_name = context.get("alertname", "unknown")
        summary = context.get("summary", "")
        prometheus_snapshot = context.get("prometheus_snapshot", {})
        recent_logs = context.get("recent_logs", [])

        prompt = self._build_prompt(service, alert_name, summary, prometheus_snapshot, recent_logs)
        return send_prompt(prompt)

    def _build_prompt(self, service, alert_name, summary, prometheus_snapshot, recent_logs) -> str:
        logs_text = "\n".join(recent_logs) if recent_logs else "No logs available."
        return f"""You are an incident response agent analyzing a production alert.

Alert: {alert_name}
Service: {service}
Summary: {summary}

Prometheus metrics:
{prometheus_snapshot}

Recent logs:
{logs_text}

Analyze and answer:
1. What went wrong?
2. What is the likely root cause?
3. What should the on-call engineer check first?

Be concise and specific."""
