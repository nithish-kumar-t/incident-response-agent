FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY apps/mongo-api-service/app/ app/

# The /app/logs directory is a mount point — create it so the container
# starts cleanly even if Docker hasn't mounted the volume yet.
RUN mkdir -p /app/logs

EXPOSE 9000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
