#!/usr/bin/env bash
# Railway-specific initialization for TrueForge
# Configures model provider and registers BRANCHPOINT MCP server

set -euo pipefail

TRUEFORGE_URL="${TRUEFORGE_URL:-http://localhost:8790}"
BACKEND_URL="${BACKEND_URL:-http://backend:8000}"

echo "==> Waiting for TrueForge to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0

until curl -sf "${TRUEFORGE_URL}/api/v1/capabilities" > /dev/null 2>&1; do
  RETRY_COUNT=$((RETRY_COUNT + 1))
  if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
    echo "ERROR: TrueForge did not become ready after ${MAX_RETRIES} attempts"
    exit 1
  fi
  echo "TrueForge not ready yet (attempt ${RETRY_COUNT}/${MAX_RETRIES}), retrying..."
  sleep 2
done

echo "==> TrueForge is ready!"

# Configure model provider if OpenAI API key is available
if [ -n "${OPENAI_API_KEY:-}" ]; then
  echo "==> Configuring OpenAI model provider..."
  
  HTTP_STATUS=$(curl -w "%{http_code}" -o /tmp/model_provider_response.json \
    -X PUT "${TRUEFORGE_URL}/api/v1/settings/model-providers" \
    -H 'content-type: application/json' \
    -d '{
      "manifest": {
        "type": "openai",
        "name": "openai",
        "auth": {
          "type": "api_key",
          "api_key": "'"${OPENAI_API_KEY}"'"
        }
      }
    }')
  
  if [ "$HTTP_STATUS" -ge 200 ] && [ "$HTTP_STATUS" -lt 300 ]; then
    echo "Model provider configured successfully"
  else
    echo "WARNING: Failed to configure model provider (HTTP ${HTTP_STATUS})"
    cat /tmp/model_provider_response.json || true
  fi
else
  echo "==> Skipping model provider configuration (OPENAI_API_KEY not set)"
  echo "    Set OPENAI_API_KEY environment variable to enable model access"
fi

# Register BRANCHPOINT MCP server
echo "==> Registering BRANCHPOINT MCP server at ${BACKEND_URL}/mcp..."

cat > /tmp/mcp_config.json <<EOF
{
  "manifest": {
    "type": "remote",
    "name": "branchpoint",
    "url": "${BACKEND_URL}/mcp",
    "description": "BRANCHPOINT counterfactual safety layer: read demo production reality, inspect counterfactual worlds, reproduce structured counterexamples, and (only with human approval) commit the recommended world to reality."
  }
}
EOF

HTTP_STATUS=$(curl -w "%{http_code}" -o /tmp/mcp_register_response.json \
  -X PUT "${TRUEFORGE_URL}/api/v1/settings/mcp-servers" \
  -H 'content-type: application/json' \
  --data @/tmp/mcp_config.json)

if [ "$HTTP_STATUS" -ge 200 ] && [ "$HTTP_STATUS" -lt 300 ]; then
  echo "BRANCHPOINT MCP server registered successfully"
else
  echo "WARNING: Failed to register MCP server (HTTP ${HTTP_STATUS})"
  cat /tmp/mcp_register_response.json || true
fi

# Verify MCP tools are visible
echo "==> Verifying MCP tools..."
HTTP_STATUS=$(curl -w "%{http_code}" -o /tmp/tools_response.json \
  -sf "${TRUEFORGE_URL}/api/v1/mcp-servers/branchpoint/tools")

if [ "$HTTP_STATUS" -ge 200 ] && [ "$HTTP_STATUS" -lt 300 ]; then
  TOOL_COUNT=$(python3 -c "
import json
with open('/tmp/tools_response.json') as f:
    data = json.load(f)
    tools = data.get('data', {})
    if isinstance(tools, dict):
        tools = tools.get('tools', [])
    print(len(tools))
" 2>/dev/null || echo "0")
  
  echo "SUCCESS: ${TOOL_COUNT} BRANCHPOINT tools are now available"
else
  echo "WARNING: Could not verify tools (HTTP ${HTTP_STATUS})"
fi

# Check model availability
echo "==> Checking available models..."
HTTP_STATUS=$(curl -w "%{http_code}" -o /tmp/models_response.json \
  -sf "${TRUEFORGE_URL}/api/v1/models")

if [ "$HTTP_STATUS" -ge 200 ] && [ "$HTTP_STATUS" -lt 300 ]; then
  MODEL_COUNT=$(python3 -c "
import json
with open('/tmp/models_response.json') as f:
    data = json.load(f)
    models = data.get('data', [])
    print(len(models))
" 2>/dev/null || echo "0")
  
  if [ "$MODEL_COUNT" = "0" ]; then
    echo "WARNING: No models configured. Set ANTHROPIC_API_KEY and redeploy."
  else
    echo "SUCCESS: ${MODEL_COUNT} model(s) available"
  fi
else
  echo "WARNING: Could not check models (HTTP ${HTTP_STATUS})"
fi

echo ""
echo "==> TrueForge initialization complete!"
echo ""
echo "Environment summary:"
echo "  TrueForge URL: ${TRUEFORGE_URL}"
echo "  Backend URL: ${BACKEND_URL}"
echo "  Model provider: ${OPENAI_API_KEY:+Configured}${OPENAI_API_KEY:-NOT CONFIGURED}"
echo ""
echo "TrueForge is ready to accept agent runs."
