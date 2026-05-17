"""
Run this once before testing. It:
1. Creates mock log files under test_data/logs/
2. Creates a tiny git repo under test_data/repo/payment-api/ with realistic Python code
3. Patches service_registry.json to point at these local paths
"""
import json
import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent
LOGS_DIR = BASE / "test_data" / "logs" / "payment-api"
REPO_DIR = BASE / "test_data" / "repo" / "payment-api"


# ── 1. Mock log files ─────────────────────────────────────────────────────────

SERVICE_LOG = """\
2026-05-16 10:28:01,112 INFO  [payment-api] Starting up...
2026-05-16 10:28:02,340 INFO  [payment-api] Connected to redis://localhost:6379
2026-05-16 10:28:02,890 INFO  [payment-api] Listening on 0.0.0.0:8080
2026-05-16 10:30:15,001 INFO  [payment-api] POST /payments/charge 200 OK (42ms)
2026-05-16 10:31:05,220 INFO  [payment-api] POST /payments/charge 200 OK (39ms)
2026-05-16 10:35:42,891 ERROR [payment-api] Unhandled exception in request handler
Traceback (most recent call last):
  File "src/handlers/payment_handler.py", line 87, in process_payment
    conn = db.get_connection()
  File "src/db/connection_pool.py", line 52, in get_connection
    return self._pool.getconn(timeout=self.timeout)
  File "src/db/connection_pool.py", line 31, in __init__
    self._pool = psycopg2.pool.ThreadedConnectionPool(
      minconn=self.min_conn, maxconn=self.max_conn,
      host=self.host, port=self.port,
      database=self.database, user=self.user, password=self.password
    )
psycopg2.OperationalError: could not connect to server: Connection refused
\tIs the server running on host "localhost" and accepting
\tTCP/IP connections on port 5432?
2026-05-16 10:35:42,910 ERROR [payment-api] Returning 500 to client
2026-05-16 10:35:43,001 WARN  [payment-api] Retrying DB connection (attempt 1/3)
2026-05-16 10:35:44,002 WARN  [payment-api] Retrying DB connection (attempt 2/3)
2026-05-16 10:35:45,003 ERROR [payment-api] All DB connection retries exhausted
2026-05-16 10:35:45,010 ERROR [payment-api] Service entering degraded mode
"""

ERROR_LOG = """\
2026-05-16 10:35:42,891 CRITICAL payment-api psycopg2.OperationalError: could not connect to server: Connection refused
2026-05-16 10:35:45,010 CRITICAL payment-api All DB connection retries exhausted — service degraded
"""

API_LOG = """\
2026-05-16 10:30:15 POST /payments/charge 200 42ms req_id=req-001
2026-05-16 10:31:05 POST /payments/charge 200 39ms req_id=req-002
2026-05-16 10:35:42 POST /payments/charge 500 1203ms req_id=req-003
2026-05-16 10:35:46 POST /payments/charge 503 5ms req_id=req-004
2026-05-16 10:35:47 GET  /health           503 2ms  req_id=req-005
"""

API_ERROR_LOG_CONTENT = """\
2026-05-16 10:35:42 ERROR req_id=req-003 POST /payments/charge -> 500 InternalServerError
  upstream: psycopg2.OperationalError could not connect to server
2026-05-16 10:35:46 ERROR req_id=req-004 POST /payments/charge -> 503 ServiceUnavailable
  reason: DB connection pool exhausted
"""


# ── 2. Mock source code ───────────────────────────────────────────────────────

PAYMENT_HANDLER = """\
import logging
from src.db.connection_pool import ConnectionPool

logger = logging.getLogger(__name__)
db = ConnectionPool()


def process_payment(charge_request: dict) -> dict:
    \"\"\"Main payment processing entry point.\"\"\"
    logger.info("Processing charge: %s", charge_request.get("id"))

    # Line 87 — this is where the stack trace points
    conn = db.get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO charges (id, amount, status) VALUES (%s, %s, 'pending')",
                (charge_request["id"], charge_request["amount"]),
            )
            conn.commit()
        return {"status": "ok", "charge_id": charge_request["id"]}
    finally:
        db.return_connection(conn)
"""

CONNECTION_POOL = """\
import psycopg2
import psycopg2.pool
import os


class ConnectionPool:
    def __init__(self):
        self.host     = os.getenv("DB_HOST", "localhost")
        self.port     = int(os.getenv("DB_PORT", "5432"))
        self.database = os.getenv("DB_NAME", "payments")
        self.user     = os.getenv("DB_USER", "app")
        self.password = os.getenv("DB_PASS", "")
        self.min_conn = int(os.getenv("DB_POOL_MIN", "2"))
        self.max_conn = int(os.getenv("DB_POOL_MAX", "10"))
        # BUG: no connect_timeout set — hangs indefinitely if DB is unreachable
        self._pool = psycopg2.pool.ThreadedConnectionPool(   # line 31
            minconn=self.min_conn,
            maxconn=self.max_conn,
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            # connect_timeout=5  <-- should be here
        )

    def get_connection(self):
        # Line 52 — called from payment_handler.py:87
        return self._pool.getconn(timeout=self.timeout)

    @property
    def timeout(self):
        return int(os.getenv("DB_POOL_TIMEOUT", "30"))

    def return_connection(self, conn):
        self._pool.putconn(conn)
"""


def run(cmd: list[str], cwd: Path):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [WARN] {' '.join(cmd)}: {result.stderr.strip()}")
    return result


def main():
    print("=== Setting up test environment ===\n")

    # ── Log files ──────────────────────────────────────────────────────────────
    print("1. Creating mock log files...")
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    (LOGS_DIR / "app.log").write_text(SERVICE_LOG, encoding="utf-8")
    (LOGS_DIR / "error.log").write_text(ERROR_LOG, encoding="utf-8")
    (LOGS_DIR / "access.log").write_text(API_LOG, encoding="utf-8")
    (LOGS_DIR / "api_error.log").write_text(API_ERROR_LOG_CONTENT, encoding="utf-8")
    print(f"   Logs written to: {LOGS_DIR}\n")

    # ── Mini git repo ──────────────────────────────────────────────────────────
    print("2. Creating mock git repo...")
    src = REPO_DIR / "src"
    (src / "handlers").mkdir(parents=True, exist_ok=True)
    (src / "db").mkdir(parents=True, exist_ok=True)
    (src / "handlers" / "payment_handler.py").write_text(PAYMENT_HANDLER, encoding="utf-8")
    (src / "db" / "connection_pool.py").write_text(CONNECTION_POOL, encoding="utf-8")
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "handlers" / "__init__.py").write_text("", encoding="utf-8")
    (src / "db" / "__init__.py").write_text("", encoding="utf-8")

    run(["git", "init"], REPO_DIR)
    run(["git", "config", "user.email", "test@test.com"], REPO_DIR)
    run(["git", "config", "user.name", "Test"], REPO_DIR)
    run(["git", "add", "."], REPO_DIR)
    run(["git", "commit", "-m", "initial commit"], REPO_DIR)
    print(f"   Repo created at: {REPO_DIR}\n")

    # ── Patch service_registry.json ────────────────────────────────────────────
    print("3. Patching service_registry.json with local paths...")
    registry_path = BASE / "service_registry.json"
    with open(registry_path, encoding="utf-8") as f:
        registry = json.load(f)

    registry["payment-api"] = {
        "health_url": "http://localhost:9999/health",   # intentionally unreachable (service is "down")
        "log_paths": {
            "service": str(LOGS_DIR / "app.log"),
            "error":   str(LOGS_DIR / "error.log"),
            "api":     str(LOGS_DIR / "api_error.log"),
        },
        "repo_path": str(REPO_DIR),
        "language":  "python",
    }

    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
    print(f"   Registry updated.\n")

    print("=== Done! ===")
    print("\nNext steps:")
    print("  1. Add your OpenAI key to .env  (copy .env.example → .env)")
    print("  2. pip install -r requirements.txt")
    print("  3. python main.py                  (starts the server on :8000)")
    print("  4. python test_pipeline.py         (sends test requests)")


if __name__ == "__main__":
    main()
