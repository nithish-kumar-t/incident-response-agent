# Incident Response Agent

An AI-powered incident response system. When Prometheus detects an issue, Alertmanager triggers the agent workflow which collects metrics and logs, then uses a local LLM (Ollama) to analyze the incident and produce an actionable report.

---

## Project Structure

```text
docker-compose.yml                        ← runs all services together
apps/
  weather-app1/                           ← FastAPI weather service (port 8000)
  mongo-api-service/                      ← FastAPI + MongoDB CRUD service (port 9000)
  incident-agent-workflow/                ← AI agent, receives alerts + calls Ollama (port 9100)
  agent/                                  ← standalone agent (host-only, port 8001)
monitoring/
  prometheus.yml                          ← scrape config + alertmanager config
  alert-rules.yml                         ← alert conditions (ServiceDown, 5xx errors, etc.)
  alertmanager.yml                        ← routes alerts to incident-agent-workflow
  loki-config.yml                         ← log storage config
  promtail-config.yml                     ← ships service logs to Loki
  targets.docker.yml                      ← Prometheus scrape targets (Docker stack)
  grafana/provisioning/                   ← auto-configures Grafana datasources
```

---

## How It Works

```
Service has an issue
       ↓
Prometheus detects metric threshold breach (every 5s scrape)
       ↓
Alertmanager fires → POST /alerts to incident-agent-workflow
       ↓
Agent queries Prometheus (metrics) + Loki (logs) for context
       ↓
Sends context to Ollama (local LLM, mistral-nemo)
       ↓
Ollama returns analysis: what went wrong, root cause, what to check
       ↓
Analysis written to apps/incident-agent-workflow/logs/workflow.log
```

---

## Prerequisites

- Docker + Docker Compose
- [Ollama](https://ollama.com/download) installed and running on your host
- `mistral-nemo` model pulled:

```bash
ollama pull mistral-nemo
```

---

## Setup

**1. Create the mongo-api-service environment file:**

```bash
# apps/mongo-api-service/.env
MONGO_URI=mongodb://mongo:27017
MONGO_DB=servicedb
APP_NAME=Mongo API Service
LOG_FILE=/app/logs/service.log
```

**2. Make sure Ollama is running on your host** (it starts automatically on Windows after install, or run `ollama serve`).

---

## Running Everything

From the project root:

```bash
docker compose up --build
```

All services start together:

| Service | URL |
|---|---|
| weather-app1 | http://localhost:8000 |
| mongo-api-service | http://localhost:9000 |
| incident-agent-workflow | http://localhost:9100 |
| Prometheus | http://localhost:9090 |
| Alertmanager | http://localhost:9093 |
| Grafana | http://localhost:3000 |
| Loki | http://localhost:3100 |

Grafana login: `admin` / `admin`

---

## Verifying It Works

**Check Prometheus targets are UP:**
```
http://localhost:9090/targets
```

**Manually fire a test alert:**
```bash
# Git Bash / Linux / Mac
curl -X POST http://localhost:9100/alerts \
  -H "Content-Type: application/json" \
  -d '{"alerts":[{"status":"firing","labels":{"alertname":"ServiceDown","service":"weather-app1"},"annotations":{"summary":"weather-app1 is not responding"}}]}'

# PowerShell
Invoke-WebRequest -Method POST http://localhost:9100/alerts \
  -ContentType "application/json" \
  -Body '{"alerts":[{"status":"firing","labels":{"alertname":"ServiceDown","service":"weather-app1"},"annotations":{"summary":"weather-app1 is not responding"}}]}'
```

**Watch the agent analyze the alert:**
```bash
docker logs incident-agent-workflow --follow
```

Or open the log file directly:
```
apps/incident-agent-workflow/logs/workflow.log
```

Look for lines starting with `ollama_analysis` — this is the LLM output.

---

## Active Alert Rules

| Alert | Condition | Severity |
|---|---|---|
| `ServiceDown` | Service unreachable for 30s | critical |
| `MongoDependencyDown` | MongoDB ping fails for 30s | critical |
| `Service5xxErrors` | Non-zero 5xx rate for 2 minutes | warning |

---

## Grafana — Viewing Logs

1. Go to `http://localhost:3000` → Explore → select **Loki**
2. Run LogQL queries:

```logql
{service="weather-app1"}
{service="mongo-api-service"}
{service="incident-agent-workflow"}
{service="weather-app1"} |= "ERROR"
```

---

## Adding a New Service

1. Create your service under `apps/your-service/` with a `/metrics` endpoint
2. Add a `Dockerfile`
3. Add it to `docker-compose.yml`
4. Add it to `monitoring/targets.docker.yml`:

```yaml
- targets:
    - your-service:PORT
  labels:
    service: your-service
    env: local-docker
```

5. Add its log path to `monitoring/promtail-config.yml` so logs ship to Loki

---

## Useful Queries

**PromQL (Prometheus):**
```promql
up
sum by (service) (rate(http_requests_total[1m]))
histogram_quantile(0.95, sum by (service, le) (rate(http_request_duration_seconds_bucket[5m])))
dependency_up{service="mongo-api-service", dependency="mongodb"}
```

**LogQL (Loki/Grafana):**
```logql
{service="mongo-api-service"} |= "ERROR"
{service="incident-agent-workflow"} |= "ollama_analysis"
```
