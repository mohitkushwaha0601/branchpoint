# BRANCHPOINT Deployment Backend Smoke-Test Runbook

**Scope:** deployed backend **through the Daytona integration only**.

> **Do not use TrueForge/Harness Trace as deployment-health expectations yet.**
> TrueForge is currently being fixed separately. Endpoints/features added after the Daytona deployment version may legitimately be absent from the deployed environment.

This runbook is intended to answer one question:

> **Is the currently deployed BRANCHPOINT backend healthy and are the deployed APIs behaving correctly?**

---

## 0. Prerequisites

You need:

```bash
curl --version
jq --version
```

Set the deployed backend URL once:

```bash
export BP_BASE_URL="https://YOUR-BACKEND-DOMAIN"
```

For a local backend:

```bash
export BP_BASE_URL="http://127.0.0.1:8000"
```

Verify it:

```bash
echo "$BP_BASE_URL"
```

---

# 1. Service / process health

## 1.1 Health endpoint

```bash
curl -i -sS "$BP_BASE_URL/health"
```

Expected:

```text
HTTP/1.1 200
```

Pretty-print the response:

```bash
curl -sS "$BP_BASE_URL/health" | jq .
```

If `/health` is unavailable on this deployment, continue with OpenAPI and `/api/v1/demo/state` before declaring the service unhealthy.

---

## 1.2 OpenAPI is reachable

```bash
curl -i -sS "$BP_BASE_URL/openapi.json" | head -30
```

Expected:

```text
HTTP/1.1 200
```

List every deployed path:

```bash
curl -sS "$BP_BASE_URL/openapi.json" \
  | jq -r '.paths | keys[]' \
  | sort
```

List methods + paths:

```bash
curl -sS "$BP_BASE_URL/openapi.json" \
  | jq -r '
      .paths
      | to_entries[]
      | .key as $path
      | .value
      | to_entries[]
      | select(.key | IN("get","post","put","patch","delete"))
      | "\(.key | ascii_upcase) \($path)"
    ' \
  | sort
```

---

# 2. Deployment-scope sanity check

The deployed version is expected to be **through Daytona**.

Use this to see whether later TrueForge/Harness features are present:

```bash
curl -sS "$BP_BASE_URL/openapi.json" \
  | jq -r '.paths | keys[]' \
  | grep -Ei 'trueforge|harness|agent-runs' || true
```

For the current deployment smoke test:

- absence of `/api/v1/agent-runs` is **not** a deployment failure;
- absence of `/api/v1/runs/{run_id}/harness-trace` is **not** a deployment failure;
- do not use TrueForge failures to judge the Daytona deployment.

Check for deployed run/demo APIs:

```bash
curl -sS "$BP_BASE_URL/openapi.json" \
  | jq -r '.paths | keys[]' \
  | grep -E '/api/v1/(runs|demo)' \
  | sort
```

---

# 3. Demo reality

## 3.1 Read current demo state

```bash
curl -i -sS "$BP_BASE_URL/api/v1/demo/state"
```

Expected:

```text
HTTP/1.1 200
```

Pretty-print:

```bash
curl -sS "$BP_BASE_URL/api/v1/demo/state" | jq .
```

Useful compact view:

```bash
curl -sS "$BP_BASE_URL/api/v1/demo/state" \
  | jq '{
      deployment,
      feature_flag,
      capacity,
      metrics,
      orders,
      snapshot_at
    }'
```

---

## 3.2 Reset demo state

> Only run this against a demo/staging backend where reset is intended.

```bash
curl -i -sS -X POST "$BP_BASE_URL/api/v1/demo/reset"
```

Pretty-print:

```bash
curl -sS -X POST "$BP_BASE_URL/api/v1/demo/reset" | jq .
```

Re-read state:

```bash
curl -sS "$BP_BASE_URL/api/v1/demo/state" | jq .
```

---

# 4. Create a deterministic BRANCHPOINT run

This path does **not** require TrueForge.

```bash
curl -sS -X POST \
  "$BP_BASE_URL/api/v1/runs" \
  -H 'Content-Type: application/json' \
  -d '{
    "incident": {
      "title": "Checkout Regression",
      "goal": "Restore checkout error rate and latency without violating data integrity, payment retry, or schema compatibility invariants.",
      "severity": "CRITICAL",
      "description": "Deployment smoke-test incident.",
      "affected_services": [
        "checkout",
        "pricing-service"
      ],
      "metadata": {
        "source": "deployment-smoke-test"
      }
    }
  }' \
  | tee /tmp/branchpoint-smoke-run.json \
  | jq .
```

Capture the new run id:

```bash
export RUN_ID="$(jq -r '.run_id' /tmp/branchpoint-smoke-run.json)"
echo "RUN_ID=$RUN_ID"
```

The value must not be empty or `null`.

Quick assertion:

```bash
test -n "$RUN_ID" && test "$RUN_ID" != "null" \
  && echo "PASS: run created: $RUN_ID" \
  || echo "FAIL: run id missing"
```

---

# 5. Run APIs

## 5.1 List runs

```bash
curl -i -sS "$BP_BASE_URL/api/v1/runs"
```

Pretty-print:

```bash
curl -sS "$BP_BASE_URL/api/v1/runs" | jq .
```

Confirm the newly-created run is present:

```bash
curl -sS "$BP_BASE_URL/api/v1/runs" \
  | jq --arg run_id "$RUN_ID" \
    '.runs[] | select(.run_id == $run_id)'
```

---

## 5.2 Get one run

```bash
curl -i -sS "$BP_BASE_URL/api/v1/runs/$RUN_ID"
```

Pretty-print:

```bash
curl -sS "$BP_BASE_URL/api/v1/runs/$RUN_ID" | jq .
```

Useful compact view:

```bash
curl -sS "$BP_BASE_URL/api/v1/runs/$RUN_ID" \
  | jq '{
      run_id,
      status,
      incident,
      selected_world_id,
      commit_id,
      commit_status,
      verification_status,
      failure_reason
    }'
```

---

## 5.3 Unknown-run behavior

This should not return `200`:

```bash
curl -i -sS \
  "$BP_BASE_URL/api/v1/runs/run_does_not_exist"
```

Expected:

```text
404
```

---

# 6. Execute deterministic demo worlds

This drives the deployed deterministic flow without TrueForge.

```bash
curl -i -sS -X POST \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/execute-demo-worlds"
```

Pretty-print:

```bash
curl -sS -X POST \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/execute-demo-worlds" \
  | jq .
```

Then inspect the run:

```bash
curl -sS "$BP_BASE_URL/api/v1/runs/$RUN_ID" | jq .
```

Expected lifecycle should progress through the deterministic BRANCHPOINT reasoning flow and normally stop at the approval gate rather than committing automatically.

Compact status:

```bash
curl -sS "$BP_BASE_URL/api/v1/runs/$RUN_ID" \
  | jq '{
      run_id,
      status,
      worlds,
      comparison,
      approval,
      selected_world_id
    }'
```

---

# 7. Worlds

## 7.1 All worlds for the run

```bash
curl -i -sS \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/worlds"
```

Pretty-print:

```bash
curl -sS \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/worlds" \
  | jq .
```

Compact world verdict view:

```bash
curl -sS \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/worlds" \
  | jq '
      if type == "array" then .
      elif has("worlds") then .worlds
      else .
      end
    '
```

---

# 8. Comparison / recommendation

```bash
curl -i -sS \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/comparison"
```

Pretty-print:

```bash
curl -sS \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/comparison" \
  | jq .
```

Useful values to inspect:

- recommended world
- eligible worlds
- rejected/vetoed worlds
- reasons
- comparison summary

---

# 9. Run event timeline

```bash
curl -i -sS \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/events"
```

Pretty-print:

```bash
curl -sS \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/events" \
  | jq .
```

Compact event type/timestamp view:

```bash
curl -sS \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/events" \
  | jq '
      if type == "array" then .
      elif has("events") then .events
      else .
      end
    '
```

Search the event payload for important lifecycle terms:

```bash
curl -sS \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/events" \
  | jq . \
  | grep -Ei \
    'observe|plan|world|counterexample|veto|approval|sandbox|daytona|commit|verify' \
  || true
```

---

# 10. Daytona / sandbox evidence check

The Daytona integration may not have a dedicated public REST endpoint.

The safest deployed check is therefore:

1. inspect the OpenAPI contract for sandbox/daytona endpoints;
2. inspect run events for sandbox lifecycle information;
3. do not assume a missing dedicated `/daytona` endpoint means integration failure.

Search OpenAPI:

```bash
curl -sS "$BP_BASE_URL/openapi.json" \
  | jq -r '.paths | keys[]' \
  | grep -Ei 'daytona|sandbox' || true
```

Search this run's event timeline:

```bash
curl -sS \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/events" \
  | jq . \
  | grep -Ei 'daytona|sandbox' \
  || true
```

If the deployed Daytona path produces structured sandbox events, inspect them without relying on exact event names:

```bash
curl -sS \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/events" \
  | jq '
      .. |
      objects |
      select(
        ((.type? // .event_type? // .name? // "") | tostring | ascii_downcase)
        | contains("sandbox")
      )
    ' \
  2>/dev/null
```

> If no sandbox event appears in the deterministic demo flow, check the exact deployed OpenAPI/events contract before calling the integration broken. Daytona may be exercised only by a separate integration path.

---

# 11. Commit capability

Check the current run before approval:

```bash
curl -i -sS \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/commit-capability"
```

Pretty-print when the endpoint responds with JSON:

```bash
curl -sS \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/commit-capability" \
  | jq .
```

The backend must remain the enforcement boundary. A run that is not legitimately approved must not obtain a usable commit capability.

---

# 12. Approval endpoint contract

Because the exact approval request schema can differ between deployed revisions, inspect the deployed OpenAPI before sending an approval.

Show the approval operation:

```bash
curl -sS "$BP_BASE_URL/openapi.json" \
  | jq '.paths["/api/v1/runs/{run_id}/approval"]'
```

Resolve its request schema:

```bash
curl -sS "$BP_BASE_URL/openapi.json" \
  | jq '
      .paths["/api/v1/runs/{run_id}/approval"].post.requestBody
    '
```

List approval-related schemas:

```bash
curl -sS "$BP_BASE_URL/openapi.json" \
  | jq '
      .components.schemas
      | to_entries
      | map(select(.key | test("Approval|Approve|Human"; "i")))
      | from_entries
    '
```

> **Do not blindly POST approval in production/staging if that endpoint can trigger a real commit.**
> Validate its deployed schema and semantics first.

---

# 13. Rejection endpoint

The explicit human-rejection endpoint was added **after the Daytona deployment version**.

Check whether this deployment has it:

```bash
curl -sS "$BP_BASE_URL/openapi.json" \
  | jq -r '.paths | keys[]' \
  | grep '/rejection' || true
```

Its absence is **not a failure** for the Daytona-version deployment.

Do not use it as a deployment acceptance criterion yet.

---

# 14. Harness Trace / TrueForge

These are intentionally **OUT OF SCOPE** for this deployed revision.

Diagnostic only:

```bash
curl -sS "$BP_BASE_URL/openapi.json" \
  | jq -r '.paths | keys[]' \
  | grep -Ei 'harness-trace|agent-runs|trueforge' || true
```

If absent, record:

```text
EXPECTED FOR CURRENT DEPLOYMENT VERSION
```

Do not flag deployment red solely for these missing endpoints.

---

# 15. Check HTTP status codes quickly

## Health

```bash
curl -sS -o /dev/null -w 'health: %{http_code}\n' \
  "$BP_BASE_URL/health"
```

## Demo state

```bash
curl -sS -o /dev/null -w 'demo-state: %{http_code}\n' \
  "$BP_BASE_URL/api/v1/demo/state"
```

## Runs

```bash
curl -sS -o /dev/null -w 'runs: %{http_code}\n' \
  "$BP_BASE_URL/api/v1/runs"
```

## Current run

```bash
curl -sS -o /dev/null -w 'run: %{http_code}\n' \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID"
```

## Worlds

```bash
curl -sS -o /dev/null -w 'worlds: %{http_code}\n' \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/worlds"
```

## Comparison

```bash
curl -sS -o /dev/null -w 'comparison: %{http_code}\n' \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/comparison"
```

## Events

```bash
curl -sS -o /dev/null -w 'events: %{http_code}\n' \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/events"
```

---

# 16. CORS / frontend connectivity

Replace the origin with the deployed frontend URL:

```bash
export BP_FRONTEND_ORIGIN="https://YOUR-FRONTEND-DOMAIN"
```

Test a simple request carrying an Origin header:

```bash
curl -i -sS \
  -H "Origin: $BP_FRONTEND_ORIGIN" \
  "$BP_BASE_URL/api/v1/runs"
```

Inspect for an appropriate header such as:

```text
access-control-allow-origin
```

Test preflight:

```bash
curl -i -sS -X OPTIONS \
  "$BP_BASE_URL/api/v1/runs" \
  -H "Origin: $BP_FRONTEND_ORIGIN" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type"
```

---

# 17. Response-time check

```bash
curl -sS -o /dev/null \
  -w 'status=%{http_code} total=%{time_total}s connect=%{time_connect}s\n' \
  "$BP_BASE_URL/api/v1/runs"
```

Demo state:

```bash
curl -sS -o /dev/null \
  -w 'status=%{http_code} total=%{time_total}s connect=%{time_connect}s\n' \
  "$BP_BASE_URL/api/v1/demo/state"
```

---

# 18. Cold-start / repeated availability check

Useful for free/serverless deployments:

```bash
for i in 1 2 3 4 5; do
  date
  curl -sS -o /dev/null \
    -w 'status=%{http_code} total=%{time_total}s\n' \
    "$BP_BASE_URL/health"
  sleep 2
done
```

If `/health` is not deployed, use:

```bash
for i in 1 2 3 4 5; do
  date
  curl -sS -o /dev/null \
    -w 'status=%{http_code} total=%{time_total}s\n' \
    "$BP_BASE_URL/api/v1/runs"
  sleep 2
done
```

---

# 19. One-pass smoke sequence

Use this after setting `BP_BASE_URL`.

```bash
set -u

echo "===== 1. OPENAPI ====="
curl -sS -o /dev/null -w 'openapi: %{http_code}\n' \
  "$BP_BASE_URL/openapi.json"

echo
echo "===== 2. HEALTH ====="
curl -sS -o /dev/null -w 'health: %{http_code}\n' \
  "$BP_BASE_URL/health"

echo
echo "===== 3. DEMO STATE ====="
curl -sS -o /dev/null -w 'demo-state: %{http_code}\n' \
  "$BP_BASE_URL/api/v1/demo/state"

echo
echo "===== 4. CREATE RUN ====="
curl -sS -X POST \
  "$BP_BASE_URL/api/v1/runs" \
  -H 'Content-Type: application/json' \
  -d '{
    "incident": {
      "title": "Deployment Smoke Test",
      "goal": "Verify deterministic BRANCHPOINT backend functionality.",
      "severity": "CRITICAL",
      "description": "Automated deployment smoke test.",
      "affected_services": ["checkout", "pricing-service"],
      "metadata": {"source": "deployment-smoke-test"}
    }
  }' \
  | tee /tmp/branchpoint-smoke-run.json \
  | jq .

RUN_ID="$(jq -r '.run_id' /tmp/branchpoint-smoke-run.json)"
echo "RUN_ID=$RUN_ID"

echo
echo "===== 5. RUN EXISTS ====="
curl -sS -o /dev/null -w 'run: %{http_code}\n' \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID"

echo
echo "===== 6. EXECUTE DEMO WORLDS ====="
curl -sS -X POST \
  "$BP_BASE_URL/api/v1/runs/$RUN_ID/execute-demo-worlds" \
  | jq .

echo
echo "===== 7. WORLDS ====="
curl -sS "$BP_BASE_URL/api/v1/runs/$RUN_ID/worlds" | jq .

echo
echo "===== 8. COMPARISON ====="
curl -sS "$BP_BASE_URL/api/v1/runs/$RUN_ID/comparison" | jq .

echo
echo "===== 9. EVENTS ====="
curl -sS "$BP_BASE_URL/api/v1/runs/$RUN_ID/events" | jq .

echo
echo "===== 10. COMMIT CAPABILITY ====="
curl -i -sS "$BP_BASE_URL/api/v1/runs/$RUN_ID/commit-capability"

echo
echo "===== 11. DAYTONA/SANDBOX EVENT SEARCH ====="
curl -sS "$BP_BASE_URL/api/v1/runs/$RUN_ID/events" \
  | jq . \
  | grep -Ei 'daytona|sandbox' \
  || echo "No Daytona/sandbox event in this deterministic run."

echo
echo "===== 12. LATER FEATURES (DIAGNOSTIC ONLY) ====="
curl -sS "$BP_BASE_URL/openapi.json" \
  | jq -r '.paths | keys[]' \
  | grep -Ei 'harness-trace|agent-runs|trueforge|rejection' \
  || echo "Expected: later winning-pass routes are not deployed yet."

echo
echo "===== SMOKE COMPLETE ====="
```

---

# 20. Expected deployment acceptance checklist

For the **Daytona-version deployment**, mark the backend healthy when the applicable deployed routes satisfy these checks:

- [ ] Backend domain responds.
- [ ] OpenAPI returns 200.
- [ ] `/health` returns 200 if present in this revision.
- [ ] `/api/v1/demo/state` returns 200.
- [ ] `POST /api/v1/runs` creates a run.
- [ ] `GET /api/v1/runs/{run_id}` returns that run.
- [ ] `POST /api/v1/runs/{run_id}/execute-demo-worlds` completes successfully.
- [ ] World data is readable.
- [ ] Comparison/recommendation is readable.
- [ ] Event timeline is readable.
- [ ] Invalid run IDs return 404 rather than 500.
- [ ] Commit capability remains backend-gated.
- [ ] Demo reset behaves correctly if enabled in this environment.
- [ ] CORS permits the intended frontend origin.
- [ ] No repeated 5xx errors.
- [ ] Daytona/sandbox integration behaves according to the deployed integration path.
- [ ] Missing TrueForge/Harness Trace routes are **not** counted as failures for this deployed revision.

---

# 21. When deployment catches up

Once your friend deploys the later TrueForge/Harness winning-pass code, extend the deployment acceptance test with:

```text
POST /api/v1/agent-runs
GET  /api/v1/agent-runs/{run_id}
GET  /api/v1/runs/{run_id}/harness-trace
GET  /api/v1/runs/{run_id}/worlds/{world_id}
POST /api/v1/runs/{run_id}/rejection
```

Do not add these to the current deployment's pass/fail criteria until that version is actually deployed.
