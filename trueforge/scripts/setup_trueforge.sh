#!/usr/bin/env bash
# Register BRANCHPOINT with a running TrueForge instance.
#
# Verified against TrueForge 0.1.4 (npx @truefoundry/trueforge@0.1.4).
# Requires: BRANCHPOINT backend on :8000, TrueForge on :8790.
set -euo pipefail

TRUEFORGE_URL="${TRUEFORGE_URL:-http://127.0.0.1:8790}"
BRANCHPOINT_MCP_URL="${BRANCHPOINT_MCP_URL:-http://127.0.0.1:8000/mcp}"
CONFIG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../config" && pwd)"

echo "==> TrueForge capabilities"
curl -sf "${TRUEFORGE_URL}/api/v1/capabilities" || {
  echo "TrueForge is not reachable at ${TRUEFORGE_URL}. Start it with: npx @truefoundry/trueforge@0.1.4"
  exit 1
}
echo

echo "==> Registering BRANCHPOINT MCP server"
python3 - "$CONFIG_DIR/branchpoint-mcp-server.json" "$BRANCHPOINT_MCP_URL" <<'PY' > /tmp/bp_mcp_body.json
import json, sys
body = json.load(open(sys.argv[1]))
body.pop("_comment", None)
body["manifest"]["url"] = sys.argv[2]
json.dump(body, sys.stdout)
PY
curl -sf -X PUT "${TRUEFORGE_URL}/api/v1/settings/mcp-servers" \
  -H 'content-type: application/json' --data @/tmp/bp_mcp_body.json > /dev/null
echo "registered."

echo "==> Tools TrueForge can now see"
curl -sf "${TRUEFORGE_URL}/api/v1/mcp-servers/branchpoint/tools" | python3 -c "
import json,sys
tools = json.load(sys.stdin)['data']
if isinstance(tools, dict): tools = tools.get('tools', tools)
for t in tools:
    a = t.get('annotations') or {}
    kind = 'DESTRUCTIVE' if a.get('destructiveHint') else 'read-only  '
    print(f'  [{kind}] {t[\"name\"]}')
print(f'  {len(tools)} tools total')
"

echo
echo "==> Model provider"
MODELS=$(curl -sf "${TRUEFORGE_URL}/api/v1/models" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['data']))")
if [ "$MODELS" = "0" ]; then
  cat <<'MSG'
  No model provider is configured yet. Add one (key never touches BRANCHPOINT):

    curl -X PUT http://127.0.0.1:8790/api/v1/settings/model-providers \
      -H 'content-type: application/json' \
      -d '{"manifest":{"type":"anthropic","name":"anthropic","auth":{"type":"api_key","api_key":"'"$ANTHROPIC_API_KEY"'"}}}'

  Then check the exact model FQN with:
    curl -s http://127.0.0.1:8790/api/v1/models | python3 -m json.tool

  and export it for the backend:
    export BRANCHPOINT_TRUEFORGE_MODEL="<provider>/<model>"
MSG
else
  echo "  ${MODELS} model(s) available."
fi
