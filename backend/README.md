# BRANCHPOINT Backend

BRANCHPOINT is a counterfactual execution and adversarial verification layer for autonomous agents. Candidate actions are tested in isolated worlds, attacked by DOPPELGÄNGER agents, compared using executable evidence, and only then eligible for human-approved execution against reality.

> **No consequential action reaches reality until it survives an adversarial counterfactual and receives explicit approval.**

## Local development

Requires Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```bash
cd backend

uv sync

uv run uvicorn app.main:app --reload
```

The health endpoint is available at:

```text
http://localhost:8000/health
```

Run the automated checks with:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Docker deployment

Build the image from the `backend` directory:

```bash
docker build -t branchpoint-backend:latest .
```

Run the container:

```bash
docker run --rm -p 8000:8000 --name branchpoint-backend branchpoint-backend:latest
```

Health check endpoint:

```text
http://localhost:8000/health
```

## Architecture

- `api/` exposes the HTTP interface and delegates application work.
- `application/` will coordinate use cases and workflows.
- `domain/` will hold pure business models and invariants, without framework or infrastructure dependencies.
- `infrastructure/` will contain adapters for external systems such as TrueForge, MCP, sandboxing, and persistence.

Product logic and external integrations are intentionally deferred until their contracts are defined.
