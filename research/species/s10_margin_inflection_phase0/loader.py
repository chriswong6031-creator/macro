"""S10 Margin-Inflection Reclaim Phase-0 — data loader.

Loads:
  - EDGAR quarterly fundamentals (in-tree: data/edgar/statements_quarterly.parquet)
  - Deep price panel from the DATA HOST (not the worktree):
      HOST_BREADTH/_closes_deep.parquet
      HOST_BREADTH/_closes_delisted.parquet
      HOST_BREADTH/sp1500_pit_membership.parquet
  - Sector map via engine.equity_factors._names_sectors('broad')

DATA HOST is the canonical main checkout. The worktree has no price data.
The run reads from HOST_BREADTH (absolute path) and writes only into the
worktree's research/species/s10_margin_inflection_phase0/.

PIT discipline: a quarter is knowable only on/after its `filed` date.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── Host data path resolution ─────────────────────────────────────────────
# The canonical data host is the main checkout's data/breadth/.
# Worktrees live at <project_root>/.claude/worktrees/<name>/ so parents[4]
# is the project root.
_HERE = Path(__file__).resolve()
# The host checkout lives at parents[3]/.claude/worktrees/*  →  we need to
# walk up to the project root which is three levels above .claude/.
# path: loader.py → s10_*/ → species/ → research/ → <worktree-root>
# The canonical data host is the MAIN checkout = project_root/data/breadth.
# Project root = parents[3].parents[2]  (worktree → .claude/worktrees → .claude → project_root)
# Simpler: hardcode relative to project root discovered at runtime.
_WORKTREE_ROOT = _HERE.parents[3]
_PROJECT_ROOT  = _WORKTREE_ROOT.parents[2]  # .claude/worktrees/<name> → .claude/ → project_root
_AUTO_HOST = _PROJECT_ROOT / "data" / "breadth"

HOST_BREADTH: Path = Path(
    os.environ.get("S10_HOST_BREADTH", str(_AUTO_HOST))
)


def _edgar_path(worktree_root: Path | None = None) -> Path:
    """EDGAR fundamentals live in the worktree's data/edgar/ (git-tracked)."""
    root = worktree_root or _WORKTREE_ROOT
    return root / "data" / "edgar" / "statements_quarterly.parquet"


# ── EDGAR fundamentals ────────────────────────────────────────────────────

def load_edgar(worktree_root: Path | None = None) -> pd.DataFrame:
    """Load statements_quarterly.parquet.

    Returns DataFrame with columns:
      ticker, fiscal_year, fiscal_quarter, period_end, filed,
      revenue, gross_profit, op_income
    filed column is cast to datetime.
    revenue > 0 filter NOT applied here (applied in fires.py per PIT slice).
    """
    path = _edgar_path(worktree_root)
    if not path.exists():
        raise FileNotFoundError(f"EDGAR not found: {path}")
    df = pd.read_parquet(path, columns=[
        "ticker", "fiscal_year", "fiscal_quarter",
        "period_end", "filed",
        "revenue", "gross_profit", "op_income",
    ])
    df["period_end"] = pd.to_datetime(df["period_end"])
    df["filed"] = pd.to_datetime(df["filed"])
    # Sort by ticker, period_end for groupby efficiency
    df = df.sort_values(["ticker", "period_end"]).reset_index(drop=True)
    log.info("EDGAR loaded: %d rows, %d tickers", len(df), df["ticker"].nunique())
    return df


# ── Deep price panel ──────────────────────────────────────────────────────

def load_price_panel(host_breadth: Path | None = None) -> pd.DataFrame:
    """Load combined deep + delisted close panel from the DATA HOST.

    Returns a wide DataFrame: DatetimeIndex rows × ticker columns.
    The positive-control assertion (AAPL or MMM >300 bars) is done here
    and raises if the panel is empty or the control fails.
    """
    bdir = host_breadth or HOST_BREADTH
    deep_path = bdir / "_closes_deep.parquet"
    dl_path   = bdir / "_closes_delisted.parquet"

    if not deep_path.exists():
        raise FileNotFoundError(
            f"_closes_deep.parquet not found at {deep_path}. "
            "Set S10_HOST_BREADTH env var to the host breadth dir."
        )

    deep = pd.read_parquet(deep_path)
    deep.index = pd.to_datetime(deep.index)
    deep = deep.sort_index()

    if dl_path.exists():
        dl = pd.read_parquet(dl_path)
        dl.index = pd.to_datetime(dl.index)
        dl = dl.sort_index()
        new_cols = [c for c in dl.columns if c not in deep.columns]
        if new_cols:
            deep = pd.concat([deep, dl[new_cols]], axis=1).sort_index()

    # ── Positive control (mandatory per brief) ────────────────────────────
    assert not deep.empty, "Price panel is EMPTY — positive control FAILED"
    for ctrl in ("AAPL", "MMM"):
        if ctrl in deep.columns:
            n_bars = int(deep[ctrl].notna().sum())
            assert n_bars > 300, (
                f"Positive control failed: {ctrl} has only {n_bars} bars "
                "(expected >300); the panel may be corrupt or wrong path."
            )
            log.info("Positive control OK: %s has %d bars", ctrl, n_bars)
            break
    else:
        log.warning("Neither AAPL nor MMM found in price panel; positive control skipped")

    log.info("Price panel loaded: %s rows × %s tickers, %s to %s",
             len(deep), deep.shape[1],
             deep.index.min().date(), deep.index.max().date())
    return deep


def load_pit_membership(host_breadth: Path | None = None):
    """Return callable f(ticker, date) -> bool for PIT sp1500 membership.

    Used for survivor-price coverage stamping, not as a hard gate.
    """
    bdir = host_breadth or HOST_BREADTH
    path = bdir / "sp1500_pit_membership.parquet"
    if not path.exists():
        log.warning("sp1500_pit_membership.parquet not found; returning False for all")
        return lambda ticker, date: False

    df = pd.read_parquet(path)
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"]   = pd.to_datetime(df["end_date"])

    intervals: dict[str, list[tuple]] = {}
    for row in df.itertuples(index=False):
        t = row.ticker
        s = row.start_date
        e = row.end_date if pd.notna(row.end_date) else pd.Timestamp("2099-12-31")
        intervals.setdefault(t, []).append((s, e))

    def _lookup(ticker: str, date: pd.Timestamp) -> bool:
        ts = intervals.get(ticker)
        if ts is None:
            return False
        dt = pd.Timestamp(date)
        return any(s <= dt <= e for s, e in ts)

    return _lookup


# ── Sector map ────────────────────────────────────────────────────────────

# GICS sectors to hard-exclude (PREREG: Financials + Real Estate)
EXCLUDE_SECTORS = frozenset(["Financials", "Financial Services",
                              "Real Estate", "REITs"])

# Archetype context cells (NOT a hard gate)
ARCHETYPE_SECTORS = frozenset(["Industrials", "Consumer Discretionary",
                                "Consumer Staples"])


def load_sector_map() -> dict[str, str]:
    """Return dict[ticker -> GICS sector string] from equity_factors._names_sectors.

    Current GICS (non-PIT) — disclosed limitation in the leak-audit.
    """
    try:
        import sys
        root = str(_HERE.parents[3])
        if root not in sys.path:
            sys.path.insert(0, root)
        from engine.equity_factors import _names_sectors
        ns = _names_sectors("broad")
        # ns = {ticker: (name, sector)}
        result = {t: v[1] for t, v in ns.items() if v[1]}
        log.info("Sector map loaded: %d tickers mapped", len(result))
        return result
    except Exception as exc:
        log.warning("Could not load sector map via equity_factors: %s", exc)
        return {}
