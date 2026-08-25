"""One model variable, resolved centrally, shared by every agent.

``BRANCHPOINT_MODEL`` names the single fully-qualified model every
TrueForge-backed BRANCHPOINT agent runs on. There is deliberately no per-role
variable: a run whose planner and DOPPELGÄNGER silently ran on different models
would produce evidence nobody can reason about.

``BRANCHPOINT_TRUEFORGE_MODEL`` is the legacy name, still honoured while
deployments migrate, and only when the new one is unset.

Every ``Settings`` here is built with ``_env_file=None`` so a developer's local
``backend/.env`` cannot decide whether these pass.
"""

import pytest

from app.api.dependencies import build_agent_orchestrator
from app.core.config import ModelNotConfiguredError, Settings

#: Deliberately awkward: BRANCHPOINT treats the model name as opaque, so a
#: string it has no idea how to interpret must survive verbatim.
OPAQUE_FQN = "some-provider/Some.Model-v3:preview@2026-08"


def settings(**overrides) -> Settings:
    """Build settings from explicit values only — no ``.env``, no ambient env."""
    return Settings(_env_file=None, **overrides)


def wired_models(monkeypatch: pytest.MonkeyPatch, configured: Settings) -> tuple[str, str]:
    """Return the model each agent is actually wired with by the composition root.

    Reaches into the orchestrator's ports because that wiring *is* what these
    tests are about: it is the only place the resolved string is handed to the
    two adapters, and neither adapter may read the environment itself.
    """
    monkeypatch.setattr("app.core.config.get_settings", lambda: configured)
    orchestrator = build_agent_orchestrator()

    planner = orchestrator._planner
    adversary = orchestrator._adversarial_tester
    planner_model = planner.agent_spec()["model"]["name"]
    adversary_model = adversary.agent_spec("run_1", "world_1")["model"]["name"]
    return planner_model, adversary_model


# ----- resolution ------------------------------------------------------------


def test_branchpoint_model_is_read_from_its_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The variable is spelled ``BRANCHPOINT_MODEL``, exactly."""
    monkeypatch.setenv("BRANCHPOINT_MODEL", OPAQUE_FQN)

    assert settings().model == OPAQUE_FQN
    assert settings().resolve_model() == OPAQUE_FQN


def test_model_fqn_passes_through_unchanged() -> None:
    """No parsing, no splitting on ``/``, no provider allow-list."""
    assert settings(model=OPAQUE_FQN).resolve_model() == OPAQUE_FQN


def test_branchpoint_model_takes_precedence_over_the_legacy_variable() -> None:
    configured = settings(model="new/model", trueforge_model="legacy/model")

    assert configured.resolve_model() == "new/model"


def test_legacy_trueforge_model_still_works_when_branchpoint_model_is_absent() -> None:
    configured = settings(trueforge_model="legacy/model")

    assert configured.model == ""
    assert configured.resolve_model() == "legacy/model"


def test_a_blank_branchpoint_model_falls_back_rather_than_resolving_to_nothing() -> None:
    """An exported-but-empty variable is 'unset', not 'the empty model'."""
    configured = settings(model="   ", trueforge_model="legacy/model")

    assert configured.resolve_model() == "legacy/model"


def test_neither_variable_configured_is_a_clear_configuration_error() -> None:
    """Never a silent default: guessing a provider is worse than refusing."""
    with pytest.raises(ModelNotConfiguredError) as raised:
        settings().resolve_model()

    detail = str(raised.value)
    assert "BRANCHPOINT_MODEL" in detail
    assert "no model configured" in detail


# ----- wiring ----------------------------------------------------------------


def test_branchpoint_model_is_used_by_the_planner(monkeypatch: pytest.MonkeyPatch) -> None:
    planner_model, _ = wired_models(monkeypatch, settings(model=OPAQUE_FQN))

    assert planner_model == OPAQUE_FQN


def test_branchpoint_model_is_used_by_the_adversary(monkeypatch: pytest.MonkeyPatch) -> None:
    _, adversary_model = wired_models(monkeypatch, settings(model=OPAQUE_FQN))

    assert adversary_model == OPAQUE_FQN


def test_planner_and_adversary_receive_the_same_model(monkeypatch: pytest.MonkeyPatch) -> None:
    planner_model, adversary_model = wired_models(monkeypatch, settings(model=OPAQUE_FQN))

    assert planner_model == adversary_model == OPAQUE_FQN


def test_legacy_variable_reaches_both_agents_identically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Migration safety: a deployment still on the old name is not half-wired."""
    planner_model, adversary_model = wired_models(
        monkeypatch, settings(trueforge_model="legacy/model")
    )

    assert planner_model == adversary_model == "legacy/model"


def test_the_agent_orchestrator_refuses_to_build_with_no_model_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A half-configured orchestrator is never handed back to a caller."""
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings())

    with pytest.raises(ModelNotConfiguredError):
        build_agent_orchestrator()
