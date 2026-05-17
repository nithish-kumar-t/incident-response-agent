"""
Sends test requests to the running pipeline service and pretty-prints results.
Run:  python test_pipeline.py
"""
import json
import sys
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8000"


def post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "detail": e.read().decode()}
    except urllib.error.URLError as e:
        print(f"\n[ERROR] Could not connect to {BASE_URL}: {e.reason}")
        print("Make sure the server is running:  python main.py")
        sys.exit(1)


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def show(label: str, value):
    if isinstance(value, (dict, list)):
        print(f"\n--- {label} ---")
        print(json.dumps(value, indent=2))
    else:
        print(f"\n  {label}: {value}")


# ── Test 1: service_error — DB connection refused ─────────────────────────────
section("TEST 1 — service_error (DB connection refused)")
print("Sending request...")

result = post("/analyze", {
    "service_name": "payment-api",
    "error_message": "psycopg2.OperationalError: could not connect to server: Connection refused on port 5432",
    "error_code": "500",
    "environment": "production",
    "additional_context": {"request_id": "req-003", "endpoint": "POST /payments/charge"},
})

print(f"\nPipeline ID : {result.get('pipeline_id')}")
print(f"Status      : {result.get('status')}")
print(f"Started     : {result.get('started_at')}")
print(f"Completed   : {result.get('completed_at')}")

a1 = result.get("agent1_triage", {})
print(f"\n[Agent 1] error_type : {a1.get('error_type')}")
print(f"[Agent 1] severity   : {a1.get('severity')}")
print(f"[Agent 1] summary    : {a1.get('error_summary')}")
print(f"[Agent 1] actions    : {a1.get('actions_taken')}")
print(f"[Agent 1] log paths resolved: {(a1.get('resolved_config') or {}).get('log_paths')}")

a2 = result.get("agent2_investigation", {})
print(f"\n[Agent 2] confidence       : {a2.get('confidence')}")
print(f"[Agent 2] hypothesis       : {a2.get('root_cause_hypothesis')}")
print(f"[Agent 2] stack_trace found: {'yes' if a2.get('stack_trace') else 'no'}")
print(f"[Agent 2] inference        :\n  {a2.get('inference')}")

a3 = result.get("agent3_code_analysis", {})
print(f"\n[Agent 3] analysis_depth  : {a3.get('analysis_depth')}")
print(f"[Agent 3] complexity      : {a3.get('complexity_assessment')}")
print(f"[Agent 3] root_cause      : {a3.get('root_cause')}")
print(f"[Agent 3] fix_suggestion  : {a3.get('fix_suggestion')}")
show("[Agent 3] affected_code", a3.get("affected_code"))
show("[Agent 3] next_steps", a3.get("recommended_next_steps"))


# ── Test 2: api_error — 401 Unauthorized ─────────────────────────────────────
section("TEST 2 — api_error (401 Unauthorized on payment gateway)")
print("Sending request...")

result2 = post("/analyze", {
    "service_name": "payment-api",
    "error_message": "401 Unauthorized from Stripe API: No such API key: sk_live_***",
    "error_code": "401",
    "environment": "production",
    "additional_context": {
        "request_id": "req-099",
        "upstream": "stripe.com",
        "endpoint": "POST /v1/charges",
    },
})

a1b = result2.get("agent1_triage", {})
a2b = result2.get("agent2_investigation", {})
a3b = result2.get("agent3_code_analysis", {})

print(f"\n[Agent 1] error_type : {a1b.get('error_type')}")
print(f"[Agent 1] severity   : {a1b.get('severity')}")
print(f"\n[Agent 2] inference  :\n  {a2b.get('inference')}")
print(f"\n[Agent 3] root_cause : {a3b.get('root_cause')}")
print(f"[Agent 3] fix        : {a3b.get('fix_suggestion')}")

section("ALL TESTS COMPLETE")
