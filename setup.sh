#!/usr/bin/env bash
# Post-deployment setup: Register BRANCHPOINT MCP server with TrueForge
set -euo pipefail

echo "======================================"
echo "BRANCHPOINT + TrueForge Setup"
echo "======================================"
echo

# Determine URLs based on environment
if [ "${RAILWAY_ENVIRONMENT:-}" = "production" ]; then
  # Running on Railway
  TF="http://trueforge:8790"
  BACKEND_MCP="http://backend:8000/mcp"
  echo "Environment: Railway"
else
  # Running locally
  TF="${TRUEFORGE_URL:-http://localhost:8790}"
  BACKEND_MCP="${BACKEND_MCP_URL:-http://backend:8000/mcp}"
  echo "Environment: Local"
fi

echo "TrueForge: $TF"
echo "Backend MCP: $BACKEND_MCP"
echo

# Wait for TrueForge to be ready
echo "Waiting for TrueForge..."
for i in {1..30}; do
  if curl -f -sS "$TF/api/v1/capabilities" > /dev/null 2>&1; then
    echo "✓ TrueForge is ready"
    break
  fi
  if [ $i -eq 30 ]; then
    echo "✗ TrueForge did not become ready"
    exit 1
  fi
  sleep 2
done

echo

# Check model provider
echo "Checking model provider..."
MODELS=$(curl -sS "$TF/api/v1/models" | jq '.data | length')
if [ "$MODELS" = "0" ] || [ "$MODELS" = "null" ]; then
  echo "✗ No model provider configured"
  echo "Set OPENAI_API_KEY in your .env file"
  exit 1
fi
echo "✓ Model provider configured: $MODELS model(s)"
curl -sS "$TF/api/v1/models" | jq -r '.data[] | "  - \(.id)"'
echo

# Register MCP server
echo "Registering BRANCHPOINT MCP server..."
RESULT=$(curl -sS -X PUT "$TF/api/v1/settings/mcp-servers" \
  -H 'content-type: application/json' \
  -d "{\"manifest\":{\"type\":\"remote\",\"name\":\"branchpoint\",\"url\":\"$BACKEND_MCP\",\"description\":\"BRANCHPOINT counterfactual safety layer\"}}")

if echo "$RESULT" | jq -e '.data' > /dev/null 2>&1; then
  echo "✓ MCP server registered"
else
  echo "✗ MCP registration failed"
  echo "$RESULT"
  exit 1
fi
echo

# Verify tools are visible
echo "Verifying MCP tools..."
TOOLS=$(curl -sS "$TF/api/v1/mcp-servers/branchpoint/tools" | jq '.data | length')
if [ "$TOOLS" = "17" ]; then
  echo "✓ All 17 MCP tools are visible"
else
  echo "⚠ Expected 17 tools, got $TOOLS"
fi
echo

echo "======================================"
echo "✓ Setup Complete"
echo "======================================"
echo
echo "Access TrueForge UI:"
if [ "${RAILWAY_ENVIRONMENT:-}" = "production" ]; then
  echo "  Railway will provide a public URL"
else
  echo "  http://localhost:8790"
fi
echo
echo "Test backend health:"
if [ "${RAILWAY_ENVIRONMENT:-}" = "production" ]; then
  echo "  Railway will provide a public URL/health"
else
  echo "  http://localhost:8000/health"
fi
