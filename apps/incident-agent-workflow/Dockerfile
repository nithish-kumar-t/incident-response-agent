FROM python:3.12-slim

WORKDIR /app

# weasyprint needs pango + cairo for PDF rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libcairo-gobject2 \
    libgdk-pixbuf-xlib-2.0-0 \
    libfontconfig1 \
    shared-mime-info \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY apps/incident-agent-workflow/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/incident-agent-workflow/main.py .
COPY apps/incident-agent-workflow/config.py .
COPY apps/incident-agent-workflow/pipeline.py .
COPY apps/incident-agent-workflow/service_registry.py .
COPY apps/incident-agent-workflow/service_registry.json .
COPY apps/incident-agent-workflow/agents/ ./agents/
COPY apps/incident-agent-workflow/tools/ ./tools/
COPY apps/incident-agent-workflow/reports/ ./reports/
COPY apps/incident-agent-workflow/llm/ ./llm/

RUN mkdir -p /app/logs

EXPOSE 9100

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9100"]
