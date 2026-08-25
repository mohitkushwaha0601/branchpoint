"""Process-wide singletons for demo infrastructure.

FastAPI, the MCP server, and every Phase 1 port adapter must share one
:class:`DemoProductionEngine` and one :class:`CapabilityStore` — otherwise a
mutation made through one surface would be invisible to another. Every
consumer resolves its instance through these ``@lru_cache`` factories, which
guarantees a single process-wide instance regardless of caller.
"""

from functools import lru_cache

from app.infrastructure.demo.capability import CapabilityStore
from app.infrastructure.demo.engine import DemoProductionEngine


@lru_cache
def get_demo_engine() -> DemoProductionEngine:
    """Return the process-wide demo production engine."""
    return DemoProductionEngine()


@lru_cache
def get_capability_store() -> CapabilityStore:
    """Return the process-wide commit capability store."""
    return CapabilityStore()
