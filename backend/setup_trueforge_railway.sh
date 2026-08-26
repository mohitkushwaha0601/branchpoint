#!/usr/bin/env bash
# TrueForge Setup for Railway Deployment
# Run these commands IN ORDER from your backend shell

set -euo pipefail

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# Adjust these if your Railway service names differ
export TF="http://trueforge.railway.internal:8080"
export BACKEND_MCP_URL="http://branchpoint-backend.railway.internal:8000/mcp"

# Set this to your actual model configuration
# Get available models from: curl -s $TF/api/v1/models | jq '.data[] | .id'
export BRANCHPOINT_MODEL="anthropic/claude-sonnet-4-5"  # CHANGE THIS to your configured model

echo "======================================"
echo "TRUEFORGE SETUP FOR RAILWAY"
echo "======================================"
echo "TrueForge: $TF"
echo "Backend MCP: $BACKEND_MCP_URL"
echo "Model: $BRANCHPOINT_MODEL"
echo

# ==============================================================================
# STEP 1: Verify TrueForge is reachable
# ==============================================================================
echo "=== STEP 1: TrueForge Health Check ==="
if ! curl -f -sS --max-time 5 "$TF/api/v1/capabilities" > /dev/null 2>&1; then
  echo "✗ FAILED: TrueForge is not reachable at $TF"
  echo
  echo "Troubleshooting:"
  echo "  1. Check TrueForge service is running in Railway"
  echo "  2. Verify internal service name (should be 'trueforge.railway.internal')"
  echo "  3. Check Railway networking allows inter-service communication"
  exit 1
fi
echo "✓ TrueForge is reachable"
echo

# ==============================================================================
# STEP 2: Verify model provider is configured
# ==============================================================================
echo "=== STEP 2: Model Provider Check ==="
MODELS=$(curl -sS "$TF/api/v1/models" | jq -r '.data // [] | length')

if [ "$MODELS" = "0" ] || [ -z "$MODELS" ]; then
  echo "✗ FAILED: No model provider configured in TrueForge"
  echo
  echo "You need to configure a model provider in TrueForge first."
  echo "This is typically done through TrueForge's UI or via Railway env vars."
  echo
  echo "Example (Anthropic):"
  echo "  Set ANTHROPIC_API_KEY in TrueForge Railway service environment"
  echo "  OR use TrueForge UI to add provider"
  echo
  echo "Then verify with:"
  echo "  curl -s $TF/api/v1/models | jq ."
  exit 1
fi

echo "✓ Model provider configured"
echo "Available models:"
curl -sS "$TF/api/v1/models" | jq -r '.data[] | "  - \(.id)"'
echo

# Verify our configured model exists
MODEL_EXISTS=$(curl -sS "$TF/api/v1/models" | jq -r --arg model "$BRANCHPOINT_MODEL" '.data[] | select(.id == $model) | .id')
if [ -z "$MODEL_EXISTS" ]; then
  echo "⚠ WARNING: Configured model '$BRANCHPOINT_MODEL' not found in available models"
  echo "Update BRANCHPOINT_MODEL in this script or your environment"
  echo
fi

# ==============================================================================
# STEP 3: Register BRANCHPOINT MCP server in TrueForge
# ==============================================================================
echo "=== STEP 3: MCP Server Registration ==="

# Check if already registered
REGISTERED=$(curl -sS "$TF/api/v1/settings/mcp-servers" 2>/dev/null | jq -r '.data[]? | select(.name == "branchpoint") | .name')

if [ "$REGISTERED" = "branchpoint" ]; then
  echo "✓ branchpoint MCP server already registered"
  echo "Current registration:"
  curl -sS "$TF/api/v1/settings/mcp-servers" | jq '.data[] | select(.name == "branchpoint")'
else
  echo "Registering branchpoint MCP server..."
  
  REGISTER_RESULT=$(curl -sS -X PUT "$TF/api/v1/settings/mcp-servers" \
    -H 'content-type: application/json' \
    -d "{\"manifest\":{\"type\":\"remote\",\"name\":\"branchpoint\",\"url\":\"$BACKEND_MCP_URL\",\"description\":\"BRANCHPOINT counterfactual safety layer\"}}")
  
  if echo "$REGISTER_RESULT" | jq -e '.data' > /dev/null 2>&1; then
    echo "✓ MCP server registered successfully"
  else
    echo "✗ FAILED: MCP registration failed"
    echo "$REGISTER_RESULT"
    exit 1
  fi
fi
echo

# ==============================================================================
# STEP 4: Verify MCP tools are visible to TrueForge
# ==============================================================================
echo "=== STEP 4: MCP Tools Verification ==="

TOOLS_RESPONSE=$(curl -sS "$TF/api/v1/mcp-servers/branchpoint/tools" 2>&1)

if ! echo "$TOOLS_RESPONSE" | jq -e '.data' > /dev/null 2>&1; then
  echo "✗ FAILED: TrueForge cannot see MCP tools"
  echo
  echo "Raw response:"
  echo "$TOOLS_RESPONSE" | head -20
  echo
  echo "This means TrueForge cannot reach the backend MCP endpoint at:"
  echo "  $BACKEND_MCP_URL"
  echo
  echo "Troubleshooting:"
  echo "  1. Verify backend service is running and serving /mcp"
  echo "  2. Check internal service name is correct"
  echo "  3. Test backend health: curl -s http://branchpoint-backend.railway.internal:8000/health"
  echo "  4. Check Railway networking allows TrueForge -> Backend communication"
  exit 1
fi

TOOL_COUNT=$(echo "$TOOLS_RESPONSE" | jq '.data | length')
echo "✓ TrueForge can see $TOOL_COUNT MCP tools"

# Verify expected tool count
if [ "$TOOL_COUNT" != "17" ]; then
  echo "⚠ WARNING: Expected 17 tools, got $TOOL_COUNT"
fi

echo
echo "Read-only tools:"
echo "$TOOLS_RESPONSE" | jq -r '.data[] | select(.annotations.readOnlyHint == true) | "  - \(.name)"'
echo
echo "Destructive tools:"
echo "$TOOLS_RESPONSE" | jq -r '.data[] | select(.annotations.destructiveHint == true) | "  - \(.name)"'
echo

# ==============================================================================
# STEP 5: Set environment variable for backend
# ==============================================================================
echo "=== STEP 5: Backend Environment ==="

if [ -z "${BRANCHPOINT_MODEL:-}" ]; then
  echo "⚠ WARNING: BRANCHPOINT_MODEL not set in environment"
  echo "Set it in Railway backend service environment variables:"
  echo "  BRANCHPOINT_MODEL=$BRANCHPOINT_MODEL"
else
  echo "✓ BRANCHPOINT_MODEL is set to: $BRANCHPOINT_MODEL"
fi

if [ -z "${BRANCHPOINT_TRUEFORGE_BASE_URL:-}" ]; then
  echo "⚠ Set BRANCHPOINT_TRUEFORGE_BASE_URL in Railway environment:"
  echo "  BRANCHPOINT_TRUEFORGE_BASE_URL=$TF"
else
  echo "✓ BRANCHPOINT_TRUEFORGE_BASE_URL is set"
fi
echo

# ==============================================================================
# SUCCESS
# ==============================================================================
echo "======================================"
echo "✓ SETUP COMPLETE"
echo "======================================"
echo
echo "TrueForge integration is configured."
echo
echo "Next steps:"
echo "  1. Ensure these env vars are set in Railway backend service:"
echo "     BRANCHPOINT_MODEL=$BRANCHPOINT_MODEL"
echo "     BRANCHPOINT_TRUEFORGE_BASE_URL=$TF"
echo
echo "  2. Test with an agent run:"
echo "     curl -X POST http://your-backend.railway.app/api/v1/agent-runs \\"
echo "       -H 'content-type: application/json' \\"
echo "       -d '{\"objective\":\"Fix the checkout production incident.\"}'"
echo
echo "  3. Monitor with:"
echo "     curl -s $TF/api/v1/sessions | jq '.data[] | {id, created_at, status}'"
