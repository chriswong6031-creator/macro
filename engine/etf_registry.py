"""Fund registry for the ETF flow board — which KIND of fund each ticker is.

One pure reader over `config.yml`'s `etf_holdings.registry` block (W2, masterplan
§3). It exists because a fund's snapshot-to-snapshot share diffs carry different
information depending on how the fund is run (masterplan §2):

  active           a manager picks the names, so per-constituent share moves
                   beyond the fund's common scale factor are SELECTION.
  thematic_passive a bespoke theme/commodity basket: creations and redemptions
                   move every constituent roughly pro-rata, so the signal is FLOW.
  sector           tracks a conventional industry classification (S&P Select
                   Industry, Nasdaq/ICB industry). Also FLOW, but the basket is
                   not a curated theme, so a "new name" carries less meaning.

Deliberately dependency-free (config only, no engine imports) so any consumer —
signals, consensus, the coverage table — can read it without an import cycle.
Fail-soft by design: a fund missing from the registry block still comes back,
typed `thematic_passive` (the modal, least-claiming type), because a metadata
gap must never drop a fund off the board.
"""
from __future__ import annotations

import re

from lib import config

#: The only fund types the board understands. Anything else in config is ignored
#: in favour of DEFAULT_TYPE, so a typo degrades instead of poisoning the read.
FUND_TYPES: tuple[str, ...] = ("active", "thematic_passive", "sector")
DEFAULT_TYPE = "thematic_passive"
UNKNOWN_THEME = "unknown"


def _slug(text: str) -> str:
    """'Junior Gold Miners' -> 'junior-gold-miners' (theme fallback for a fund
    that has a universe `category` but no registry row yet)."""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", str(text).lower())).strip("-")


def fund_registry(cfg: dict | None = None) -> dict[str, dict[str, str]]:
    """Map every board fund to ``{type, sponsor, theme}``.

    Covers the `etf_holdings.universe`, the `holdings.watchlist` funds (ARKK/ARKW,
    collected into data/holdings/ rather than data/etf_holdings/) and any extra
    row in the registry block. Pass *cfg* to read an in-memory config instead of
    config.yml — the loader never mutates what it is given.
    """
    cfg = config.load() if cfg is None else cfg
    holdings_cfg = cfg.get("etf_holdings") or {}
    registry = holdings_cfg.get("registry") or {}
    specs: dict[str, dict] = {}
    for block in ((cfg.get("holdings") or {}).get("watchlist") or {},
                  holdings_cfg.get("universe") or {}):
        for ticker, spec in block.items():
            specs[str(ticker)] = spec if isinstance(spec, dict) else {}

    out: dict[str, dict[str, str]] = {}
    for ticker in list(specs) + [t for t in registry if t not in specs]:
        spec = specs.get(ticker) or {}
        row = registry.get(ticker) or {}
        if not isinstance(row, dict):
            row = {}
        ftype = row.get("type")
        if ftype not in FUND_TYPES:
            # No usable registry row: the universe's own `active` flag is the next
            # best evidence, else the least-claiming default.
            ftype = "active" if spec.get("active") else DEFAULT_TYPE
        theme = row.get("theme") or _slug(spec.get("category", "")) or UNKNOWN_THEME
        out[str(ticker)] = {
            "type": ftype,
            "sponsor": str(row.get("sponsor") or spec.get("sponsor") or "unknown"),
            "theme": str(theme),
        }
    return out
