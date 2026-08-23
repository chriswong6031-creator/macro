"""Fixed production composition for the W1-A datapoint read layer.

There is no dynamic adapter discovery, import-string registry, persistent cache,
or user-selected source path here.  The seven frozen adapter IDs are wired to
their concrete owner readers in code.
"""
from __future__ import annotations

import os
from pathlib import Path

from .adapters.company_intelligence import CompanyIntelligenceAdapter
from .adapters.earnings import EarningsCalendarAdapter
from .adapters.industry import IndustryAdapter
from .adapters.quote import QuoteAdapter
from .adapters.stage import StageAdapter
from .adapters.technicals import TechnicalsAdapter
from .adapters.theme import ThemeAdapter
from .entity import DataOSIdentityNormalizer
from .projection import ThemeRightsProjector
from .resolver import DatapointResolver


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TERMINAL_DATA_DIR = Path("/opt/terminal/terminal/public/data")
DEFAULT_TERMINAL_HUB_URL = "http://127.0.0.1:3100"
EXACT_ADAPTER_IDS = (
    "quote",
    "technicals",
    "stage",
    "industry",
    "earnings_calendar",
    "company_intelligence",
    "theme",
)


def build_runtime(
    *,
    repo_root: str | Path | None = None,
    terminal_data_dir: str | Path | None = None,
    terminal_hub_url: str | None = None,
) -> DatapointResolver:
    """Build one stateless resolver over the fixed current owner graph.

    Optional arguments are constructor seams for repository tests and embedded
    callers.  The CLI exposes none of them.  Production defaults follow the
    existing Brain environment convention.
    """
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    terminal_dir = Path(
        terminal_data_dir
        if terminal_data_dir is not None
        else os.environ.get("TERMINAL_DATA_DIR", str(DEFAULT_TERMINAL_DATA_DIR))
    )
    hub_url = str(
        terminal_hub_url
        if terminal_hub_url is not None
        else os.environ.get("TERMINAL_HUB_URL", DEFAULT_TERMINAL_HUB_URL)
    )
    adapters = {
        "quote": QuoteAdapter(
            root=root,
            terminal_data_dir=terminal_dir,
            terminal_hub_url=hub_url,
        ),
        "technicals": TechnicalsAdapter(root=root),
        # Every symbol-reading non-quote owner uses the Data OS current STORE
        # catalog.  The dated `yahoo` namespace is historical naming evidence,
        # never the current artifact key.
        "stage": StageAdapter(repo_root=root, vendor="store"),
        "industry": IndustryAdapter(repo_root=root, vendor="store"),
        "earnings_calendar": EarningsCalendarAdapter(repo_root=root, vendor="store"),
        "company_intelligence": CompanyIntelligenceAdapter(repo_root=root, vendor="store"),
        "theme": ThemeAdapter(),
    }
    if tuple(adapters) != EXACT_ADAPTER_IDS:  # fail closed if a future edit drifts wiring
        raise RuntimeError("W1-A runtime adapter manifest drift")
    return DatapointResolver(
        identity_normalizer=DataOSIdentityNormalizer(root),
        adapters=adapters,
        rights_projector=ThemeRightsProjector(),
    )
