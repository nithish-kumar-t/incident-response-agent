# Incident Response Agent

An automated incident triage demo for local microservices.

The project runs sample FastAPI services, monitors them with Prometheus, routes alerts through Alertmanager, collects logs with Loki/Promtail, and asks a local Ollama model to summarize what happened when an alert fires.

## What Runs

```text
Prometheus scrapes service metrics
        |
        v
Alertmanager receives firing alerts
        |
        v
incident-agent-workflow receives POST /alerts
        |
        +--> queries Prometheus for metrics
        +--> queries Loki for recent logs
        +--> sends context to Ollama
        |
        v
analysis is written to apps/incident-agent-workflow/logs/workflow.log
```

For deeper architecture diagrams, see [architecture.md](architecture.md).

## Services

| Service | URL | Purpose |
| --- | --- | --- |
| `weather-app1` | http://localhost:8000 | Demo weather API with Prometheus metrics |
| `mongo-api-service` | http://localhost:9000 | Demo CRUD API backed by MongoDB |
| `incident-agent-workflow` | http://localhost:9100 | Alert webhook and Ollama analysis workflow |
| `Prometheus` | http://localhost:9090 | Metrics scraping and alert rule evaluation |
| `Alertmanager` | http://localhost:9093 | Alert routing to the agent workflow |
| `Grafana` | http://localhost:3000 | Metrics and log exploration |
| `Loki` | http://localhost:3100 | Log storage queried by Grafana and the agent |
| `MongoDB` | `localhost:27017` | Database for `mongo-api-service` |

Grafana credentials are `admin` / `admin`.

## Repository Layout

```text
.
|-- docker-compose.yml                  # Full local stack
|-- architecture.md                     # System diagrams and design notes
|-- apps/
|   |-- weather-app1/                   # FastAPI weather service, port 8000
|   |-- mongo-api-service/              # FastAPI + MongoDB service, port 9000
|   |-- incident-agent-workflow/        # Alert webhook + Ollama analysis, port 9100
|   |-- agent/                          # Optional host-run OpenAI pipeline
|   |-- notifier/                       # Optional email notifier, disabled by default
|   |-- log_watcher.py                  # Optional log scanner/report generator
|   `-- report_generator.py
`-- monitoring/
    |-- prometheus.yml                  # Prometheus config
    |-- targets.docker.yml              # Docker scrape targets
    |-- alert-rules.yml                 # Alert definitions
    |-- alertmanager.yml                # Alert routing
    |-- loki-config.yml
    |-- promtail-config.yml
    `-- grafana/provisioning/           # Grafana datasources
```

## Prerequisites

- Docker and Docker Compose
- Ollama running on your host machine
- The `mistral-nemo` model pulled locally

```bash
ollama pull mistral-nemo
ollama serve
```

If Ollama is already running, `ollama serve` may report that the port is in use. That is fine.

## Setup

Create the Mongo API environment file:

```bash
cat > apps/mongo-api-service/.env <<'EOF'
MONGO_URI=mongodb://mongo:27017
MONGO_DB=servicedb
APP_NAME=Mongo API Service
LOG_FILE=/app/logs/service.log
EOF
```

The Compose file expects this file to exist.

## Run The Full Stack

From the repository root:

```bash
docker compose up -d --build
```

Check container status:

```bash
docker compose ps
```

Stop everything:

```bash
docker compose down
```

To also remove the local Docker volumes:

```bash
docker compose down -v
```

## Quick Verification

Check the app services:

```bash
curl http://localhost:8000/
curl http://localhost:9000/health
curl http://localhost:9100/health
```

Check Prometheus targets:

```text
http://localhost:9090/targets
```

Every target in `monitoring/targets.docker.yml` should show as `UP`.

Create a Mongo item:

```bash
curl -X POST http://localhost:9000/items/ \
  -H "Content-Type: application/json" \
  -d '{"name":"demo","description":"test item","value":42}'
```

Query the weather API:

```bash
curl "http://localhost:8000/weather/latitude=41.8781&longitude=-87.6298"
```

## Trigger A Test Alert

You can send an Alertmanager-style payload directly to the workflow service:

```bash
curl -X POST http://localhost:9100/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "alerts": [
      {
        "status": "firing",
        "labels": {
          "alertname": "ServiceDown",
          "service": "weather-app1"
        },
        "annotations": {
          "summary": "weather-app1 is not responding"
        }
      }
    ]
  }'
```

Then watch the workflow logs:

```bash
docker compose logs -f incident-agent-workflow
```

Or read the log file directly:

```bash
tail -f apps/incident-agent-workflow/logs/workflow.log
```

Look for `ollama_analysis`. If Ollama is reachable, that log line contains the generated incident analysis.

## Active Alerts

Alert rules live in [monitoring/alert-rules.yml](monitoring/alert-rules.yml).

| Alert | Condition | Severity |
| --- | --- | --- |
| `ServiceDown` | Prometheus cannot scrape a target for 30 seconds | `critical` |
| `MongoDependencyDown` | `mongo-api-service` cannot ping MongoDB for 30 seconds | `critical` |
| `Service5xxErrors` | A service has non-zero 5xx rate for 30 seconds | `warning` |

Alertmanager routes alerts to:

```text
http://incident-agent-workflow:9100/alerts
```

## Logs And Metrics

Promtail ships these log files to Loki:

| Service label | Host log path |
| --- | --- |
| `weather-app1` | `apps/weather-app1/logs/*.log` |
| `mongo-api-service` | `apps/mongo-api-service/logs/*.log` |
| `incident-agent-workflow` | `apps/incident-agent-workflow/logs/*.log` |

Useful Grafana Loki queries:

```logql
{service="weather-app1"}
{service="mongo-api-service"}
{service="incident-agent-workflow"}
{service="incident-agent-workflow"} |= "ollama_analysis"
{service="mongo-api-service"} |= "ERROR"
```

Useful Prometheus queries:

```promql
up
sum by (service) (up)
sum by (service, handler, method, status) (rate(http_requests_total[1m]))
sum by (service) (rate(http_requests_total{status="5xx"}[2m]))
dependency_up{service="mongo-api-service", dependency="mongodb"}
```

## API Reference

### `weather-app1`

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/` | Basic service check |
| `GET` | `/weather/latitude={latitude}&longitude={longitude}` | Fetch weather data from Open-Meteo |
| `GET` | `/metrics` | Prometheus metrics |

### `mongo-api-service`

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Liveness check |
| `GET` | `/health/ready` | MongoDB readiness check |
| `POST` | `/items/` | Create item |
| `GET` | `/items/` | List items |
| `GET` | `/items/{item_id}` | Get item |
| `PUT` | `/items/{item_id}` | Update item |
| `DELETE` | `/items/{item_id}` | Delete item |
| `GET` | `/metrics` | Prometheus metrics |

### `incident-agent-workflow`

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Liveness check |
| `POST` | `/alerts` | Alertmanager webhook receiver |
| `GET` | `/metrics` | Prometheus metrics |

## Optional: Host-Run OpenAI Pipeline

The Docker stack uses Ollama through `incident-agent-workflow`. There is also a separate host-run pipeline under `apps/agent/` that uses OpenAI for deeper log and code analysis.

Run it only if you need that path:

```bash
cd apps/agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r ../../requirements.txt openai
export OPENAI_API_KEY=your_key_here
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

Port `8000` is already used by `weather-app1` when the Docker stack is running, so the example above starts the optional agent on `8001`.

Available endpoints:

```text
GET  http://localhost:8001/health
GET  http://localhost:8001/services
POST http://localhost:8001/analyze
```

`apps/log_watcher.py` is also optional and requires `python-docx` for Word report generation. It currently contains local machine paths, so update `LOG_SOURCES` or pass suitable arguments before using it. If you run the optional agent on port `8001`, pass `--agent-url http://localhost:8001`.

## Troubleshooting

**`incident-agent-workflow` logs `LLM error`**

Make sure Ollama is running on the host and the model exists:

```bash
ollama list
ollama pull mistral-nemo
```

The workflow container calls Ollama at:

```text
http://host.docker.internal:11434
```

**Prometheus target is `DOWN`**

Check the service container and logs:

```bash
docker compose ps
docker compose logs weather-app1
docker compose logs mongo-api-service
docker compose logs incident-agent-workflow
```

Then open:

```text
http://localhost:9090/targets
```

**Mongo API fails to start**

Confirm `apps/mongo-api-service/.env` exists and MongoDB is healthy:

```bash
docker compose ps mongo
docker compose logs mongo
```

**Grafana has no logs**

Check Promtail and Loki:

```bash
docker compose logs promtail
docker compose logs loki
```

Also confirm the app log files exist under `apps/*/logs/`.

## Add Another Monitored Service

1. Add the service under `apps/<service-name>/`.
2. Expose a `/metrics` endpoint.
3. Write logs to a file under `apps/<service-name>/logs/`.
4. Add the service to `docker-compose.yml`.
5. Add a scrape target to `monitoring/targets.docker.yml` with a `service` label.
6. Add the log mount and scrape config to `monitoring/promtail-config.yml`.
7. Add or update alert rules in `monitoring/alert-rules.yml`.

Keep the `service` label consistent across Prometheus and Loki. The agent uses that label to fetch the right metrics and logs for an alert.
