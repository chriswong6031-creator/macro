"""Deterministic SEC/XBRL Fundamental Forensics kernel (fixture slice v1)."""
from .models import FindingState, KnowledgeClock, RunResult, VintagePolicy
from .normalize import ForensicsRegistry, load_registry, registry_from_dict
from .pipeline import run_fixture_slice

__all__ = [
    "FindingState",
    "ForensicsRegistry",
    "KnowledgeClock",
    "RunResult",
    "VintagePolicy",
    "load_registry",
    "registry_from_dict",
    "run_fixture_slice",
]
