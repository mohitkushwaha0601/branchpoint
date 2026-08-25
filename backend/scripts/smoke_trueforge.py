#!/usr/bin/env python3
"""Real TrueForge integration smoke test.

Excluded from the default pytest run on purpose: the later stages require a
running TrueForge with a configured model provider, which means real (paid)
model calls. Nothing here is mocked — that is the whole point.

    uv run python scripts/smoke_trueforge.py                # checks + hero flow
    uv run python scripts/smoke_trueforge.py --checks-only  # no model calls
    uv run python scripts/smoke_trueforge.py --require-sandbox  # assert sandbox use
    uv run python scripts/smoke_trueforge.py --approve-commit   # DEMO REALITY ONLY

Stages 1-4 need no model and run anywhere TrueForge is up. Stages 5-14 need a
model provider and stop at AWAITING_APPROVAL with reality untouched. Stages
15-22 mutate demo reality and only run behind an explicit flag; the script
always resets demo reality on the way out.

Stage 14 reports what TrueForge itself recorded about the DOPPELGÄNGER's
sandbox. It is informational by default (the sandbox is opt-in) and becomes an
assertion under ``--require-sandbox``, which is how the one live
sandbox-enabled run is proven. Because that proof needs the live hero flow,
``--require-sandbox`` refuses to run alongside ``--checks-only`` and fails
rather than skips when no model provider is configured.

Nothing in the commit stages touches ``DemoProductionEngine`` directly. The
approval goes through the real HTTP endpoint, which commits through the real
destructive MCP tool behind the real capability gate — faking any of it would
make these assertions worthless.
"""

import argparse
import asyncio
import sys

import httpx

from app.infrastructure.trueforge.client import TrueForgeClient
from app.infrastructure.trueforge.models import (
    EVENT_SANDBOX_CREATED,
    EVENT_TOOL_RESPONSE,
    TOOL_INFO_TYPE_MCP,
    ToolCallView,
    TurnEvent,
)
from app.mcp.server import DESTRUCTIVE_TOOL_NAMES, READ_ONLY_TOOL_NAMES

BACKEND_URL = "http://127.0.0.1:8000"
TRUEFORGE_URL = "http://localhost:8790"

#: Name fragments identifying TrueForge's own sandbox execution tools. Used
#: only to *label* what a recorded tool call was; the proof itself is always a
#: TrueForge event, never a name.
SANDBOX_EXEC_TOOL_HINTS = ("exec", "shell", "bash", "run_code", "run_command", "python")

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


async def stage_model_available(client: TrueForgeClient, require_sandbox: bool = False) -> bool:
    """Gate for every model-dependent stage.

    Skipping the model-dependent stages is normal — most of this script is
    useful without a provider. It is *not* normal under ``--require-sandbox``:
    the sandbox assertion lives in stage 14, stage 14 needs the live hero flow,
    and a run that quietly skipped the thing it was asked to prove must not
    exit 0.
    """
    try:
        models = await client.list_models()
    except Exception as exc:
        record("5. model provider configured", FAIL, str(exc)[:120])
        return False

    if not models:
        record(
            "5-14. model-dependent stages",
            FAIL if require_sandbox else SKIP,
            "no model provider configured in TrueForge; see trueforge/README.md"
            + (" — --require-sandbox cannot be proven without one" if require_sandbox else ""),
        )
        return False
    record("5. model provider configured", PASS, f"{len(models)} model(s)")
    return True


async def stage_hero_flow(
    http: httpx.AsyncClient,
    client: TrueForgeClient,
    approve_commit: bool,
    require_sandbox: bool,
) -> bool:
    """6-14. Start a real agent run and inspect what the agents actually did."""
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

    # Re-read the run: the bindings now carry each adversary's last turn id,
    # which is what stage 14 follows into TrueForge's event log.
    agent_run = (await http.get(f"{BACKEND_URL}/api/v1/agent-runs/{run_id}")).json()
    ok = await stage_sandbox_observability(client, agent_run["sessions"], require_sandbox)

    if not approve_commit:
        record(
            "15-22. destructive commit",
            SKIP,
            "not approved in an unattended run; pass --approve-commit for demo reality only",
        )
        return ok

    return await _stage_commit(http, run_id, recommended) and ok


async def stage_sandbox_observability(
    client: TrueForgeClient, sessions: list[dict], require_sandbox: bool
) -> bool:
    """14. Did a DOPPELGÄNGER session actually create and use a sandbox?

    Every claim here comes from TrueForge's own record of the session: the
    ``config.sandbox`` it was created with, its ``sandbox.created`` events, and
    the ``tool.response`` events answering its built-in ``exec`` calls. Model
    prose saying it ran something proves nothing and is never read.

    Informational by default, because the sandbox is opt-in and a DOPPELGÄNGER
    that did not need to run code is not a failure. Under ``--require-sandbox``
    it becomes the assertion that proves the live sandbox-enabled run.
    """
    stage = "14. DOPPELGÄNGER sandbox created and used (TrueForge events)"
    adversaries = [s for s in sessions if s["purpose"] == "ADVERSARY" and s.get("last_turn_id")]
    if not adversaries:
        record(stage, FAIL if require_sandbox else SKIP, "no adversary session with a turn")
        return not require_sandbox

    configured, created, execs = [], [], []
    for session in adversaries:
        session_id, turn_id = session["trueforge_session_id"], session["last_turn_id"]
        if await _session_sandbox_flag(client, session_id):
            configured.append(session_id)
        try:
            events = await client.list_turn_events(session_id, turn_id)
        except Exception as exc:
            record(stage, FAIL if require_sandbox else SKIP, f"{session_id}: {exc}"[:120])
            return not require_sandbox
        created += [
            event.sandbox_id
            for event in events
            if event.type == EVENT_SANDBOX_CREATED and event.sandbox_id
        ]
        execs += _sandbox_exec_responses(events)

    detail = (
        f"{len(adversaries)} adversary session(s), "
        f"spec sandbox on={len(configured)}, "
        f"sandbox.created={len(created)} {sorted(set(created))[:3]}, "
        f"exec tool.response={len(execs)}"
    )
    if created or execs:
        record(stage, PASS, detail)
        return True

    record(
        stage,
        FAIL if require_sandbox else SKIP,
        f"{detail}; no sandbox event — start the backend with "
        "BRANCHPOINT_TRUEFORGE_SANDBOX_ENABLED=true",
    )
    return not require_sandbox


async def _session_sandbox_flag(client: TrueForgeClient, session_id: str) -> bool | None:
    """Whether TrueForge records this session as configured with a sandbox.

    ``None`` when TrueForge does not echo the agent spec back on the session —
    unknown, which is reported as such and never counted as evidence either way.
    """
    try:
        return _find_sandbox_enabled(await client.get_session(session_id))
    except Exception:
        return None


def _find_sandbox_enabled(node: object) -> bool | None:
    """Find a ``sandbox.enabled`` flag anywhere in a session payload.

    Searched rather than read from a fixed path on purpose: the exact nesting of
    the stored agent spec is TrueForge's business, and a shape change here must
    degrade to "unknown", never to a wrong answer.
    """
    if isinstance(node, dict):
        sandbox = node.get("sandbox")
        if isinstance(sandbox, dict) and isinstance(sandbox.get("enabled"), bool):
            return bool(sandbox["enabled"])
        children: list[object] = list(node.values())
    elif isinstance(node, list):
        children = list(node)
    else:
        return None

    for child in children:
        found = _find_sandbox_enabled(child)
        if found is not None:
            return found
    return None


def _is_sandbox_exec(call: ToolCallView) -> bool:
    """Whether a recorded tool call is one of TrueForge's own sandbox exec tools.

    Anything TrueForge routed to an MCP server is excluded outright: BRANCHPOINT
    tools are not sandbox execution, whatever they are named.
    """
    info = call.tool_info
    if info is not None and info.type == TOOL_INFO_TYPE_MCP:
        return False
    name = (call.function.name if call.function else "").lower()
    return any(hint in name for hint in SANDBOX_EXEC_TOOL_HINTS)


def _sandbox_exec_responses(events: tuple[TurnEvent, ...]) -> list[str]:
    """Tool-call ids of sandbox exec calls TrueForge recorded a response for."""
    exec_calls = {
        call.id
        for event in events
        for call in event.tool_calls
        if call.id and _is_sandbox_exec(call)
    }
    return [
        event.tool_call_id
        for event in events
        if event.type == EVENT_TOOL_RESPONSE and event.tool_call_id in exec_calls
    ]


async def _stage_commit(http: httpx.AsyncClient, run_id: str, world_id: str | None) -> bool:
    """15-22. DEMO REALITY ONLY: approve, commit through TrueForge, verify."""
    if world_id is None:
        record("15-22. destructive commit", FAIL, "no recommended world to commit")
        return False

    print(f"\n  !! approving the destructive commit of {world_id} against DEMO reality\n")
    ok = True

    run = (await http.get(f"{BACKEND_URL}/api/v1/runs/{run_id}")).json()
    approval = run["approval"] or {}
    before = (await http.get(f"{BACKEND_URL}/api/v1/demo/state")).json()

    # The client confirms what it believes it is approving. It cannot name a
    # different action: these are checked against the binding, never applied.
    response = await http.post(
        f"{BACKEND_URL}/api/v1/runs/{run_id}/approval",
        json={
            "actor": "smoke-test-operator",
            "expected_world_id": approval.get("selected_world_id"),
            "expected_action_id": approval.get("action_id"),
            "expected_action_fingerprint": approval.get("action_fingerprint"),
        },
        timeout=900.0,
    )
    if response.status_code != 200:
        record(
            "15-22. destructive commit",
            FAIL,
            f"HTTP {response.status_code}: {response.text[:200]}",
        )
        return False
    decision = response.json()

    agent_run = (await http.get(f"{BACKEND_URL}/api/v1/agent-runs/{run_id}")).json()
    operator_sessions = [s for s in agent_run["sessions"] if s["purpose"] == "COMMIT_OPERATOR"]
    ok &= _record(
        "15. destructive TrueForge call reached the approval gate",
        bool(operator_sessions),
        ", ".join(s["trueforge_session_id"] for s in operator_sessions) or "no operator session",
    )

    committed = (await http.get(f"{BACKEND_URL}/api/v1/runs/{run_id}")).json()
    granted = committed["approval"] or {}
    ok &= _record(
        "16. explicit human approval recorded",
        granted.get("status") == "APPROVED" and granted.get("actor") == "smoke-test-operator",
        f"{granted.get('status')} by {granted.get('actor')}",
    )
    ok &= _record(
        "17. approval matches the recommended world, action, and fingerprint",
        granted.get("selected_world_id") == world_id
        and granted.get("action_id") == approval.get("action_id")
        and granted.get("action_fingerprint") == approval.get("action_fingerprint"),
        f"world={granted.get('selected_world_id')} action={granted.get('action_id')}",
    )

    ok &= _record(
        "18. exactly the approved action committed",
        committed["commit_status"] == "SUCCEEDED"
        and decision["action_id"] == approval.get("action_id"),
        f"{decision.get('action_name')} ({committed['commit_status']})",
    )

    events = (await http.get(f"{BACKEND_URL}/api/v1/runs/{run_id}/events")).json()["events"]
    types = [e["event_type"] for e in events]
    ok &= _record(
        "19. independent verification passed",
        committed["verification_status"] == "PASSED"
        and "VERIFICATION_STARTED" in types
        and "VERIFICATION_COMPLETED" in types,
        str(committed["verification_status"]),
    )
    ok &= _record(
        "20. run reached SUCCEEDED",
        committed["status"] == "SUCCEEDED" and "RUN_SUCCEEDED" in types,
        committed["status"],
    )

    after = (await http.get(f"{BACKEND_URL}/api/v1/demo/state")).json()
    ok &= _record(
        "21. reality matches the committed action",
        _reality_matches(before, after),
        f"flag {before['feature_flag']['enabled']} -> {after['feature_flag']['enabled']}, "
        f"version {before['deployment']['version']} -> {after['deployment']['version']}",
    )

    # A replay must not produce a second mutation. The approval endpoint is
    # idempotent, and no fresh capability can be issued for a finished run.
    replay = await http.post(
        f"{BACKEND_URL}/api/v1/runs/{run_id}/approval",
        json={"actor": "smoke-test-operator"},
        timeout=900.0,
    )
    capability = await http.post(f"{BACKEND_URL}/api/v1/runs/{run_id}/commit-capability")
    final = (await http.get(f"{BACKEND_URL}/api/v1/runs/{run_id}")).json()
    ok &= _record(
        "22. replayed commit rejected",
        capability.status_code == 409
        and final["commit_id"] == committed["commit_id"]
        and types.count("COMMIT_COMPLETED") == 1
        and replay.status_code == 200,
        f"capability HTTP {capability.status_code}, one commit {final['commit_id']}",
    )
    return ok


def _record(stage: str, passed: bool, detail: str = "") -> bool:
    """Record a boolean stage result and return it."""
    record(stage, PASS if passed else FAIL, detail)
    return passed


def _reality_matches(before: dict, after: dict) -> bool:
    """Whether observed reality changed in the way the committed action implies.

    Derived from the demo state endpoint, never from the engine object: this is
    an outside-in check that the mutation actually landed.
    """
    flag_changed = before["feature_flag"]["enabled"] and not after["feature_flag"]["enabled"]
    version_changed = before["deployment"]["version"] != after["deployment"]["version"]
    replicas_changed = before["capacity"]["replicas"] != after["capacity"]["replicas"]
    return flag_changed or version_changed or replicas_changed


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checks-only", action="store_true", help="skip model-dependent stages")
    parser.add_argument(
        "--require-sandbox",
        action="store_true",
        help=(
            "assert that a DOPPELGÄNGER session really created/used a TrueForge sandbox; "
            "pair with a backend started with BRANCHPOINT_TRUEFORGE_SANDBOX_ENABLED=true"
        ),
    )
    parser.add_argument(
        "--approve-commit",
        action="store_true",
        help="DEMO REALITY ONLY: approve and execute the destructive commit",
    )
    args = parser.parse_args()
    if args.checks_only and args.require_sandbox:
        # Stage 14 is the only place sandbox use is proven, and it needs the
        # live hero flow. Honouring both flags would exit 0 having asserted
        # nothing, which is exactly the outcome --require-sandbox exists to
        # rule out.
        parser.error(
            "--require-sandbox proves sandbox use from a live run's TrueForge events, "
            "so it cannot be combined with --checks-only"
        )

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
                record("5-22. model-dependent stages", SKIP, "--checks-only")
            elif await stage_model_available(client, args.require_sandbox):
                ok &= await stage_hero_flow(http, client, args.approve_commit, args.require_sandbox)

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
