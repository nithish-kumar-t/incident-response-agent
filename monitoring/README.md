# Local Monitoring

This folder owns the shared local monitoring stack for every app under `../apps`.

Run each local service so it listens on all host interfaces, not only localhost:

```bash
cd ../apps/weather-app1
python3 -m uvicorn main:app --host 0.0.0.0 --port 8085
```

Prometheus runs inside Docker. From inside Docker, `127.0.0.1` means the Prometheus
container itself, not your host machine. `host.docker.internal` points Prometheus
back to your host.

Add services to `targets.yml`:

```yaml
- targets:
    - host.docker.internal:8085
  labels:
    service: weather-app1
    env: local

- targets:
    - host.docker.internal:9000
  labels:
    service: another-api
    env: local
```

Start monitoring:

```bash
cd monitoring
docker compose up
```

Useful URLs:

```text
Prometheus: http://127.0.0.1:9090
Grafana:    http://127.0.0.1:3000
```

Useful PromQL:

```promql
up
sum by (service) (up)
sum by (service, handler, method, status) (rate(http_requests_total[1m]))
histogram_quantile(0.95, sum by (service, le) (rate(http_request_duration_seconds_bucket[5m])))
```

Useful error-focused PromQL:

```promql
sum by (service, handler, method, status) (rate(http_requests_total{status="4xx"}[5m]))
sum by (service, handler, method, status) (rate(http_requests_total{status="5xx"}[5m]))
sum by (service) (increase(http_requests_total{status="5xx"}[5m]))
```

For service logs, check the app log file:

```bash
tail -f ../apps/weather-app1/logs/app.log
```
