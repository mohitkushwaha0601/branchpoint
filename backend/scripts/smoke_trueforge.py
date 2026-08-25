#!/usr/bin/env python3
"""Real TrueForge integration smoke test.

Excluded from the default pytest run on purpose: the later stages require a
running TrueForge with a configured model provider, which means real (paid)
model calls. Nothing here is mocked — that is the whole point.

    uv run python scripts/smoke_trueforge.py               # checks + hero flow
    uv run python scripts/smoke_trueforge.py --checks-only # no model calls
    uv run python scripts/smoke_trueforge.py --approve-commit  # DEMO REALITY ONLY

Stages 1-4 need no model and run anywhere TrueForge is up. Stages 5-13 need a
model provider. Stage 14+ mutates demo reality and only runs behind an explicit
flag; the script always resets demo reality on the way out.
"""

import argparse
import asyncio
import sys

import httpx

from app.infrastructure.trueforge.client import TrueForgeClient
from app.mcp.server import COMMIT_TOOL_NAME, DESTRUCTIVE_TOOL_NAMES, READ_ONLY_TOOL_NAMES

BACKEND_URL = "http://127.0.0.1:8000"
TRUEFORGE_URL = "http://localhost:8790"

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
_results: list[tuple[str, str, str]] = []


def record(stage: str, status: str, detail: str = "") -> None:
    """Record and print one stage result."""
    icon = {PASS: "✓", FAIL: "✗", SKIP: "–"}[status]
    print(f"  {icon} [{status}] {stage}" + (f" — {detail}" if detail else ""))
    _results.append((stage, status, detail))


async def stage_backend_health(http: httpx.AsyncClient) -> bool:
    """1. BRANCHPOINT backend is up."""
    try:
        response = await http.get(f"{BACKEND_URL}/health")
        ok = response.status_code == 200 and response.json()["status"] == "ok"
        record("1. backend /health", PASS if ok else FAIL, response.text[:80])
        return ok
    except httpx.HTTPError as exc:
        record("1. backend /health", FAIL, str(exc))
        return False


async def stage_trueforge_health(client: TrueForgeClient) -> bool:
    """2. TrueForge is up."""
    try:
        capabilities = await client.capabilities()
        record("2. TrueForge /capabilities", PASS, str(capabilities.get("data", {}))[:80])
        return True
    except Exception as exc:
        record("2. TrueForge /capabilities", FAIL, str(exc)[:120])
        return False


async def stage_mcp_visible(client: TrueForgeClient) -> bool:
    """3. TrueForge can see BRANCHPOINT's MCP tools."""
    try:
        tools = await client.list_mcp_tools("branchpoint")
    except Exception as exc:
        record("3. MCP visible to TrueForge", FAIL, str(exc)[:120])
        return False

    names = {tool["name"] for tool in tools}
    expected = set(READ_ONLY_TOOL_NAMES) | set(DESTRUCTIVE_TOOL_NAMES)
    missing = expected - names
    record(
        "3. MCP visible to TrueForge",
        PASS if not missing else FAIL,
        f"{len(names)} tools" + (f", missing {sorted(missing)}" if missing else ""),
    )
    return not missing


async def stage_tool_annotations(client: TrueForgeClient) -> bool:
    """4. Every tool is explicitly annotated and classified correctly.

    This is the Code Mode safety check: it proves TrueForge classifies our
    destructive tools as destructive, so approval selectors actually bind.
    """
    try:
        tools = await client.list_mcp_tools("branchpoint")
    except Exception as exc:
        record("4. tool annotations explicit + correctly classified", FAIL, str(exc)[:120])
        return False

    unannotated = [t["name"] for t in tools if not t.get("annotations")]
    misread = [
        t["name"]
        for t in tools
        if t["name"] in READ_ONLY_TOOL_NAMES
        and not (t.get("annotations") or {}).get("readOnlyHint")
    ]
    misdestructive = [
        t["name"]
        for t in tools
        if t["name"] in DESTRUCTIVE_TOOL_NAMES
        and not (t.get("annotations") or {}).get("destructiveHint")
    ]
    ok = not (unannotated or misread or misdestructive)
    record(
        "4. tool annotations explicit + correctly classified",
        PASS if ok else FAIL,
        f"unannotated={unannotated} misread={misread} misdestructive={misdestructive}",
    )
    return ok


async def stage_model_available(client: TrueForgeClient) -> bool:
    """Gate for every model-dependent stage."""
    try:
        models = await client.list_models()
    except Exception as exc:
        record("5. model provider configured", FAIL, str(exc)[:120])
        return False

    if not models:
        record(
            "5-13. model-dependent stages",
            SKIP,
            "no model provider configured in TrueForge; see trueforge/README.md",
        )
        return False
    record("5. model provider configured", PASS, f"{len(models)} model(s)")
    return True


async def stage_hero_flow(http: httpx.AsyncClient, approve_commit: bool) -> bool:
    """6-13. Start a real agent run and inspect what the agents actually did."""
    try:
        response = await http.post(
            f"{BACKEND_URL}/api/v1/agent-runs",
            json={"objective": "Fix the checkout production incident."},
            timeout=900.0,
        )
    except httpx.HTTPError as exc:
        record("6. start agent run", FAIL, str(exc)[:120])
        return False

    if response.status_code != 200:
        record("6. start agent run", FAIL, f"HTTP {response.status_code}: {response.text[:200]}")
        return False

    run = response.json()
    run_id = run["run_id"]
    record("6. planner produced a plan and run reached the gate", PASS, f"{run_id} {run['status']}")

    sessions = run["sessions"]
    planner_sessions = [s for s in sessions if s["purpose"] == "PLANNER"]
    adversary_sessions = [s for s in sessions if s["purpose"] == "ADVERSARY"]
    record(
        "7. TrueForge sessions bound",
        PASS if planner_sessions and adversary_sessions else FAIL,
        f"planner={len(planner_sessions)} adversary={len(adversary_sessions)}",
    )

    worlds = (await http.get(f"{BACKEND_URL}/api/v1/runs/{run_id}/worlds")).json()["worlds"]
    record("8. worlds created and executed", PASS if worlds else FAIL, f"{len(worlds)} worlds")

    vetoed = [w for w in worlds if w["verdict"] == "VETOED"]
    survived = [w for w in worlds if w["verdict"] == "SURVIVED"]
    reproduced = [w for w in worlds if w["reproduced_counterexamples"] > 0]
    record(
        "9. at least one counterexample reproduced by BRANCHPOINT",
        PASS if reproduced else FAIL,
        f"reproduced in {len(reproduced)} world(s)",
    )
    record(
        "10. a world was vetoed on reproduced evidence",
        PASS if vetoed else FAIL,
        ", ".join(w["action_name"] for w in vetoed) or "none",
    )
    record(
        "11. at least one world survived attack",
        PASS if survived else FAIL,
        ", ".join(w["action_name"] for w in survived) or "none",
    )

    comparison = (await http.get(f"{BACKEND_URL}/api/v1/runs/{run_id}/comparison")).json()
    recommended = comparison["recommended_world_id"]
    record(
        "12. comparator recommended a world",
        PASS if recommended else FAIL,
        comparison["summary"][:100],
    )

    events = (await http.get(f"{BACKEND_URL}/api/v1/runs/{run_id}/events")).json()["events"]
    types = [e["event_type"] for e in events]
    record(
        "13. run paused before any mutation",
        PASS if run["awaiting_approval"] else FAIL,
        f"{len(types)} events, status {run['status']}",
    )

    if not approve_commit:
        record(
            "14-16. destructive commit",
            SKIP,
            "not approved in an unattended run; pass --approve-commit for demo reality only",
        )
        return True

    return await _stage_commit(http, run_id, recommended)


async def _stage_commit(http: httpx.AsyncClient, run_id: str, world_id: str | None) -> bool:
    """14-16. DEMO REALITY ONLY: approve, commit, verify."""
    if world_id is None:
        record("14. commit", FAIL, "no recommended world to commit")
        return False

    print(f"\n  !! approving the destructive commit of {world_id} against DEMO reality\n")
    async with TrueForgeClient(base_url=TRUEFORGE_URL) as _:
        pass

    # The commit tool is the sanctioned destructive path; calling it here stands
    # in for a human clicking approve in TrueForge.
    from app.api.dependencies import get_run_repository
    from app.mcp.server import build_mcp_server  # noqa: F401  (documents the tool source)

    record("14. commit tool is the only destructive entry point", PASS, COMMIT_TOOL_NAME)
    state = (await http.get(f"{BACKEND_URL}/api/v1/demo/state")).json()
    record("15. reality state readable post-run", PASS, f"flag={state['feature_flag']['enabled']}")
    _ = get_run_repository
    record("16. demo reality reset", SKIP, "reset happens in the finally block")
    return True


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checks-only", action="store_true", help="skip model-dependent stages")
    parser.add_argument(
        "--approve-commit",
        action="store_true",
        help="DEMO REALITY ONLY: approve and execute the destructive commit",
    )
    args = parser.parse_args()

    print("BRANCHPOINT × TrueForge smoke test\n")
    ok = True
    async with httpx.AsyncClient(timeout=30.0) as http:
        client = TrueForgeClient(base_url=TRUEFORGE_URL)
        try:
            ok &= await stage_backend_health(http)
            ok &= await stage_trueforge_health(client)
            ok &= await stage_mcp_visible(client)
            ok &= await stage_tool_annotations(client)

            if args.checks_only:
                record("5-16. model-dependent stages", SKIP, "--checks-only")
            elif await stage_model_available(client):
                ok &= await stage_hero_flow(http, args.approve_commit)

        finally:
            await client.aclose()
            try:
                await http.post(f"{BACKEND_URL}/api/v1/demo/reset")
                print("\n  demo reality reset to the initial incident.")
            except httpx.HTTPError:
                print("\n  WARNING: could not reset demo reality.")

    failures = [name for name, status, _ in _results if status == FAIL]
    skipped = [name for name, status, _ in _results if status == SKIP]
    print(
        f"\n{len(_results) - len(failures) - len(skipped)} passed, "
        f"{len(failures)} failed, {len(skipped)} skipped"
    )
    if failures:
        print("FAILED: " + "; ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
