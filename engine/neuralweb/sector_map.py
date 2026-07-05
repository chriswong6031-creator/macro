"""engine/neuralweb/sector_map.py — Stock-to-sector/subsector mapping for sponsorship connector.

Amendment 1, Lane B2 (§C3, RUL-16).  Display-only — consumed read-only by bottom_sensors.py.

Sources (all pre-existing repo stores — no new taxonomy built):
  1. data/breadth/constituents.parquet          S&P 500 GICS sector assignments
  2. data/midcap_breadth/constituents.parquet   S&P 400 GICS sector assignments
  3. data/smallcap_breadth/constituents.parquet S&P 600 GICS sector assignments
  4. data/sector_holdings/*.parquet             SPDR sector ETF holdings (supplemental)
  5. data/baskets/membership.json              Curated theme baskets → panel_m nodes

GICS sector name → panel_s ETF node:
  Materials              → XLB
  Communication Services → XLC
  Energy                 → XLE
  Financials             → XLF
  Industrials            → XLI
  Information Technology → XLK
  Consumer Staples       → XLP
  Real Estate            → XLRE
  Utilities              → XLU
  Health Care            → XLV
  Consumer Discretionary → XLY

Never raises.  Returns empty dicts on failure (sponsorship degrades to unavailable).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import NamedTuple

import pandas as pd

log = logging.getLogger(__name__)

# ── GICS sector name → panel_s ETF node (11 sectors) ────────────────────────
GICS_TO_ETF: dict[str, str] = {
    "Materials": "XLB",
    "Communication Services": "XLC",
    "Energy": "XLE",
    "Financials": "XLF",
    "Industrials": "XLI",
    "Information Technology": "XLK",
    "Consumer Staples": "XLP",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Health Care": "XLV",
    "Consumer Discretionary": "XLY",
}

_SECTOR_ETFS = list(GICS_TO_ETF.values())


class SectorMapping(NamedTuple):
    """Lookup result for one ticker."""
    sector_node: str | None    # panel_s ETF node (e.g. "XLK") or None
    subsector_node: str | None  # panel_m basket node or None


def build_sector_map(root: Path) -> dict[str, SectorMapping]:
    """Build ticker → SectorMapping from existing repo stores.

    Returns an empty dict on total failure (callers stamp sponsorship_state
    as 'unavailable' when lookup misses).

    Source priority (sector arm):
      1. data/breadth/constituents.parquet (S&P 500, 503 names)
      2. data/midcap_breadth/constituents.parquet (S&P 400, ~400 names)
      3. data/smallcap_breadth/constituents.parquet (S&P 600, ~600 names)
      4. data/sector_holdings/{ETF}.parquet (supplemental large-caps, ~220 names)
    Duplicate tickers: first hit wins (S&P 500 has the most authoritative sector
    assignments; sector_holdings is supplemental for names not in any S&P index).

    Source (subsector arm):
      data/baskets/membership.json: active members of baskets whose names appear
      as nodes in panel_m.  First basket wins per ticker.  Panel_m node set is
      the ground truth — baskets not in panel_m are ignored.
    """
    sector_map: dict[str, str] = {}   # ticker -> sector_node
    subsector_map: dict[str, str] = {}  # ticker -> subsector_node

    # ── 1. GICS breadth constituents ─────────────────────────────────────────
    breadth_paths = [
        root / "data" / "breadth" / "constituents.parquet",
        root / "data" / "midcap_breadth" / "constituents.parquet",
        root / "data" / "smallcap_breadth" / "constituents.parquet",
    ]
    for path in breadth_paths:
        if not path.exists():
            log.debug("breadth constituents not found: %s", path)
            continue
        try:
            df = pd.read_parquet(path)
            df.index.name = "symbol"
            df = df.reset_index()
            for _, row in df.iterrows():
                sym = str(row.get("symbol", "")).strip()
                sector_name = str(row.get("sector", "")).strip()
                etf = GICS_TO_ETF.get(sector_name)
                if sym and etf and sym not in sector_map:
                    sector_map[sym] = etf
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to load breadth constituents %s: %s", path, exc)

    # ── 2. Sector holdings ETFs (supplemental) ───────────────────────────────
    holdings_dir = root / "data" / "sector_holdings"
    for etf in _SECTOR_ETFS:
        path = holdings_dir / f"{etf}.parquet"
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path)
            for ticker in df["ticker"].dropna().unique():
                t = str(ticker).strip()
                if t and t not in sector_map:
                    sector_map[t] = etf
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to load sector holdings %s: %s", etf, exc)

    # ── 3. Baskets membership → subsector (panel_m nodes) ───────────────────
    baskets_path = root / "data" / "baskets" / "membership.json"
    if baskets_path.exists():
        try:
            with open(baskets_path) as fh:
                bdata = json.load(fh)
            baskets = bdata.get("baskets") or {}
            # We need the panel_m node set to filter relevant baskets.
            # Load it inline; if it fails we skip subsector mapping silently.
            panel_m_nodes = _load_panel_m_nodes(root)
            for basket_name, basket in baskets.items():
                if basket_name not in panel_m_nodes:
                    continue
                members = basket.get("members") or []
                for m in members:
                    if not isinstance(m, dict):
                        continue
                    ticker = (m.get("ticker") or "").strip()
                    removed = m.get("removed")
                    if ticker and not removed and ticker not in subsector_map:
                        subsector_map[ticker] = basket_name
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to load baskets membership for subsector map: %s", exc)

    # ── 4. Assemble final mapping ─────────────────────────────────────────────
    all_tickers = set(sector_map) | set(subsector_map)
    result: dict[str, SectorMapping] = {}
    for t in all_tickers:
        result[t] = SectorMapping(
            sector_node=sector_map.get(t),
            subsector_node=subsector_map.get(t),
        )

    log.info(
        "sector_map built: %d sector-mapped, %d subsector-mapped, %d total",
        len(sector_map), len(subsector_map), len(result),
    )
    return result


def _load_panel_m_nodes(root: Path) -> frozenset[str]:
    """Return the set of node names present in panel_m.  Empty frozenset on failure."""
    path = root / "data" / "oracle" / "panel_m.parquet"
    if not path.exists():
        log.debug("panel_m.parquet not found at %s", path)
        return frozenset()
    try:
        df = pd.read_parquet(path, columns=[])  # just load the index
        nodes = df.index.get_level_values("node").unique()
        return frozenset(str(n) for n in nodes)
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to load panel_m nodes: %s", exc)
        return frozenset()
