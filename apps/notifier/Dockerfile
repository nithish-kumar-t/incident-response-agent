FROM python:3.12-slim

WORKDIR /app

COPY apps/notifier/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/notifier/main.py .
COPY apps/notifier/emailer.py .
COPY apps/notifier/config.py .

EXPOSE 8002

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
