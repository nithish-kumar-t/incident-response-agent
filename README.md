# Incident Response Agent Local Services

This repo is organized for multiple local services plus one shared monitoring stack.

```text
apps/
  weather-app1/
    main.py
monitoring/
  docker-compose.yml
  prometheus.yml
  targets.yml
  README.md
requirements.txt
```

Put each new service under `apps/`:

```text
apps/service-app2/
apps/service-app3/
apps/service-app4/
```

Each service should expose `/metrics` if you want Prometheus and Grafana to monitor it.

Run the weather app:

```bash
cd apps/weather-app1
python3 -m uvicorn main:app --host 0.0.0.0 --port 8003
```

Run monitoring:

```bash
cd monitoring
docker compose up
```

Add or remove monitored services in `monitoring/targets.yml`.
