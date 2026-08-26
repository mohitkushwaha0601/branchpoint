# Railway Deployment Guide

## Prerequisites

1. Railway account
2. OpenAI API key with access to real models (gpt-4o, gpt-4-turbo, etc.)

## Setup Steps

### 1. Create .env file

```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY and POSTGRES_PASSWORD
```

### 2. Local Testing (Optional but Recommended)

```bash
# Start everything locally
docker-compose up -d

# Wait for services to be ready
sleep 20

# Run setup to register MCP
bash setup.sh

# Test backend
curl http://localhost:8000/health

# Access TrueForge UI
open http://localhost:8790

# Test agent run
curl -X POST http://localhost:8000/api/v1/agent-runs \
  -H 'content-type: application/json' \
  -d '{"objective":"Fix the checkout production incident."}'
```

### 3. Deploy to Railway

**Option A: CLI**
```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Create new project
railway init

# Link to this directory
railway link

# Set environment variables
railway variables set OPENAI_API_KEY=sk-proj-your-key
railway variables set POSTGRES_PASSWORD=your-secure-password
railway variables set BRANCHPOINT_MODEL=openai/gpt-4o

# Deploy
railway up
```

**Option B: GitHub Connection**
1. Push this code to GitHub
2. Create new Railway project
3. Connect GitHub repo
4. Railway auto-detects docker-compose.yml
5. Set environment variables in Railway UI:
   - `OPENAI_API_KEY`
   - `POSTGRES_PASSWORD`
   - `BRANCHPOINT_MODEL`
6. Deploy

### 4. Post-Deployment Setup

Once deployed, run setup from any service shell:

```bash
# In Railway, open shell for 'backend' service
bash /app/setup.sh
```

Or manually register MCP:
```bash
export TF="http://trueforge:8790"
curl -X PUT "$TF/api/v1/settings/mcp-servers" \
  -H 'content-type: application/json' \
  -d '{"manifest":{"type":"remote","name":"branchpoint","url":"http://backend:8000/mcp","description":"BRANCHPOINT"}}'
```

## Architecture

```
┌─────────────┐     ┌──────────┐     ┌───────────┐
│  PostgreSQL │────▶│   Redis  │────▶│ TrueForge │
└─────────────┘     └──────────┘     └─────┬─────┘
                                            │
                                            │ MCP Tools
                                            ▼
                                     ┌─────────────┐
                                     │   Backend   │
                                     └─────────────┘
```

- **PostgreSQL**: TrueForge session/turn storage
- **Redis**: TrueForge peering for multi-replica cancel
- **TrueForge**: Agent harness (port 8790)
- **Backend**: BRANCHPOINT safety layer (port 8000, serves /mcp)

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | - | OpenAI API key |
| `POSTGRES_PASSWORD` | Yes | - | PostgreSQL password |
| `BRANCHPOINT_MODEL` | Yes | openai/gpt-4o | Model to use (must be real) |
| `TRUEFORGE_PORT` | No | 8790 | TrueForge port |
| `BACKEND_PORT` | No | 8000 | Backend port |

## Troubleshooting

### "Model does not exist"
Fix: Use a real OpenAI model in `BRANCHPOINT_MODEL`:
- `openai/gpt-4o` ✓
- `openai/gpt-4-turbo` ✓
- `openai/gpt-4` ✓
- `openai/gpt-5.6-luna` ✗ (fake model)

### "MCP tools not visible"
1. Check backend is healthy: `curl http://backend:8000/health`
2. Re-run setup script
3. Check backend logs for MCP errors

### Services not starting
Check Railway logs for each service (postgres, redis, trueforge, backend)

## Testing After Deployment

```bash
# Get your Railway public URLs
BACKEND_URL="https://your-backend.railway.app"
TF_URL="https://your-trueforge.railway.app"  # if exposed

# Test backend
curl $BACKEND_URL/health

# Start agent run
curl -X POST $BACKEND_URL/api/v1/agent-runs \
  -H 'content-type: application/json' \
  -d '{"objective":"Fix the checkout production incident."}'

# Check TrueForge sessions (from backend shell)
curl -s http://trueforge:8790/api/v1/sessions | jq '.data[] | {id, created_at}'
```
