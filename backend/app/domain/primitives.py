"""Shared domain primitives: identifiers, time, and immutable model updates."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

#: Values that can be carried by evidence, checks, and event payloads.
type ScalarValue = bool | float | str | None


class DomainModel(BaseModel):
    """Immutable base for every domain value object."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    """Return a collision-resistant identifier namespaced by ``prefix``."""
    return f"{prefix}_{uuid4().hex[:12]}"


def evolve[ModelT: BaseModel](model: ModelT, **changes: object) -> ModelT:
    """Return a revalidated copy of ``model`` with ``changes`` applied.

    Unlike :meth:`pydantic.BaseModel.model_copy`, this re-runs validation, so a
    frozen domain object can never be evolved into an invalid state.
    """
    return type(model).model_validate({**dict(model), **changes})
