"""Winner Autopsy Lab — I/O + CLI wrapper.

Program: Long-Hold Thesis lobe, Winner Autopsy department.
Masterplan: research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
Rulings: WA-R3 (vocabulary), WA-R5 (display-only ceiling), WA-R9 (ledger law).

Modes
-----
default (nightly):
    Computes current watch states + winner_autopsy_panel.json + refreshes manifest.
    Does NOT advance breakaway_watch_history (use --write-history for that).
--write-history:
    Appends watch rows to data/research/breakaway_watch_history.parquet, keep-FIRST
    per (ticker, snapshot_date). NIGHTLY ONLY — sole-advancer law.
--backfill:
    Full historical episode census over all names + label_outcomes + control counts.
    Writes data/research/winner_episodes.parquet + manifest.
--dry-run:
    Compute but do not write any output files.
--smoke:
    First 200 names only (fast smoke-test). HARD-EXITS rc=2 if combined with
    --write-history (sole-advancer guard, thesis-funnel precedent).

Usage:
    python scripts/research/build_winner_autopsy.py
    python scripts/research/build_winner_autopsy.py --dry-run --smoke
    python scripts/research/build_winner_autopsy.py --backfill
    python scripts/research/build_winner_autopsy.py --write-history   # nightly only
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Repo root + path bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA = _REPO_ROOT / "data"
_YAHOO_DIR = _DATA / "yahoo"

# Massive store: repo-local first, Mac-host fallback
_MASSIVE_DIR_LOCAL = _DATA / "massive_stock_day"
_MASSIVE_DIR_MAC = Path(
    "/Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day"
)

_DEAD_NAME_PRICES_PATH = _DATA / "edgar" / "dead_name_prices.parquet"
_TICKER_SECTORS_PATH = _DATA / "breadth" / "ticker_sectors.parquet"
_PIT_PATH = _DATA / "breadth" / "sp1500_pit_membership.parquet"
_REGISTRY_PATH = _DATA / "experiments" / "registry_seed.json"
_CASES_GLOB = str(_REPO_ROOT / "research" / "winners" / "cases" / "*.md")

# B-family feature stores
_MATERIAL_8K_PATH = _DATA / "edgar" / "material_8k_events.parquet"
_STATEMENTS_PATH = _DATA / "edgar" / "statements.parquet"
_INDEX_CHANGES_PATH = _DATA / "sp_index_changes" / "changes.parquet"

_OUT_DIR = _DATA / "research"
_EPISODES_PATH = _OUT_DIR / "winner_episodes.parquet"
_WATCH_PATH = _OUT_DIR / "breakaway_watch.parquet"
_WATCH_HISTORY_PATH = _OUT_DIR / "breakaway_watch_history.parquet"
_PANEL_PATH = _OUT_DIR / "winner_autopsy_panel.json"
_EPISODES_MANIFEST_PATH = _OUT_DIR / "winner_episodes_manifest.json"
_AUTOPSY_MANIFEST_PATH = _OUT_DIR / "winner_autopsy_manifest.json"


# ---------------------------------------------------------------------------
# Price loader helpers (mirrors long_hold_label_panel.py §4 pattern)
# ---------------------------------------------------------------------------

def _find_massive_dir() -> Path | None:
    """Find the massive_stock_day directory. Returns None if unreachable."""
    for candidate in [_MASSIVE_DIR_LOCAL, _MASSIVE_DIR_MAC]:
        if candidate.exists():
            parquets = list(candidate.glob("*.parquet"))
            if parquets:
                log.info("Massive store found at %s (%d files)", candidate, len(parquets))
                return candidate
    log.warning(
        "::warning:: no name prices — massive store not found at %s or %s",
        _MASSIVE_DIR_LOCAL,
        _MASSIVE_DIR_MAC,
    )
    return None


def _load_yahoo_bars(smoke_limit: int | None = None) -> dict[str, pd.DataFrame]:
    """Load yahoo parquets as bars dicts {ticker: DataFrame(close, volume)}.

    yahoo parquets have cols: close_price, close, volume.
    We map 'close' as the price column. No high/low in yahoo.

    Parameters
    ----------
    smoke_limit:
        If set, stop loading after this many non-benchmark tickers (for smoke
        runs where full loading would be prohibitively slow). Benchmark ETFs
        (SPY, XL*) are always loaded regardless of the limit.
    """
    # Benchmark tickers are always needed (bench series)
    _BENCH_TICKERS = frozenset({
        "SPY", "XLE", "XLK", "XLF", "XLV", "XLI", "XLY",
        "XLP", "XLU", "XLB", "XLRE", "XLC", "XBI",
    })
    bars: dict[str, pd.DataFrame] = {}
    if not _YAHOO_DIR.exists():
        log.warning("yahoo dir not found: %s", _YAHOO_DIR)
        return bars
    n_non_bench = 0
    for p in sorted(_YAHOO_DIR.glob("*.parquet")):
        ticker = p.stem
        if ticker.startswith("_"):
            continue
        is_bench = ticker in _BENCH_TICKERS
        if smoke_limit is not None and not is_bench and n_non_bench >= smoke_limit:
            continue
        try:
            df = pd.read_parquet(p)
            if "close" not in df.columns:
                continue
            df2 = pd.DataFrame(index=df.index)
            df2["close"] = df["close"]
            if "volume" in df.columns:
                df2["volume"] = df["volume"]
            df2 = df2.dropna(subset=["close"]).sort_index()
            if len(df2) > 0:
                bars[ticker] = df2
                if not is_bench:
                    n_non_bench += 1
        except Exception as exc:  # noqa: BLE001
            log.debug("yahoo load fail %s: %s", ticker, exc)
    log.info("Loaded %d yahoo bars (smoke_limit=%s)", len(bars), smoke_limit)
    return bars


def _load_massive_bars(massive_dir: Path) -> dict[str, pd.DataFrame]:
    """Load massive_stock_day parquets as bars {ticker: DataFrame(close,volume,high,low)}.

    massive parquets have cols: open, high, low, close, volume, transactions.
    Index = date UTC midnight.
    """
    bars: dict[str, pd.DataFrame] = {}
    for p in sorted(massive_dir.glob("*.parquet")):
        ticker = p.stem
        if ticker.startswith("_"):
            continue
        try:
            df = pd.read_parquet(p)
            if "close" not in df.columns:
                continue
            cols = ["close"]
            for c in ["volume", "high", "low"]:
                if c in df.columns:
                    cols.append(c)
            df2 = df[cols].dropna(subset=["close"]).sort_index()
            if len(df2) > 0:
                bars[ticker] = df2
        except Exception as exc:  # noqa: BLE001
            log.debug("massive load fail %s: %s", ticker, exc)
    log.info("Loaded %d massive bars", len(bars))
    return bars


def _load_dead_name_bars() -> dict[str, pd.DataFrame]:
    """Load dead_name_prices.parquet as bars {ticker: DataFrame(close, volume)}."""
    bars: dict[str, pd.DataFrame] = {}
    if not _DEAD_NAME_PRICES_PATH.exists():
        return bars
    try:
        df = pd.read_parquet(_DEAD_NAME_PRICES_PATH)
        if df.empty:
            return bars
        if "ticker" not in df.columns or "close" not in df.columns:
            return bars
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        for ticker, grp in df.groupby("ticker"):
            g = grp.set_index("date").sort_index()
            g = g[~g.index.duplicated(keep="last")]
            sub = pd.DataFrame({"close": g["close"]})
            if "volume" in g.columns:
                sub["volume"] = g["volume"]
            sub = sub.dropna(subset=["close"])
            if len(sub) >= 2:
                bars[str(ticker)] = sub
    except Exception as exc:  # noqa: BLE001
        log.warning("dead_name bars load fail: %s", exc)
    log.info("Loaded %d dead-name bars", len(bars))
    return bars


def _merge_bars(
    yahoo_bars: dict[str, pd.DataFrame],
    massive_bars: dict[str, pd.DataFrame],
    dead_name_bars: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """Merge price sources with priority: yahoo > massive > dead_name.

    Returns (merged_bars, source_map {ticker: source_label}).
    """
    merged: dict[str, pd.DataFrame] = {}
    source_map: dict[str, str] = {}

    all_tickers = (
        set(yahoo_bars.keys())
        | set(massive_bars.keys())
        | set(dead_name_bars.keys())
    )

    for ticker in all_tickers:
        if ticker in yahoo_bars:
            merged[ticker] = yahoo_bars[ticker]
            source_map[ticker] = "yahoo"
        elif ticker in massive_bars:
            merged[ticker] = massive_bars[ticker]
            source_map[ticker] = "massive"
        elif ticker in dead_name_bars:
            merged[ticker] = dead_name_bars[ticker]
            source_map[ticker] = "dead_name"

    return merged, source_map


def _load_bench_closes(bars: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
    """Extract benchmark ETF close series from bars."""
    from engine.winner_autopsy import _GICS_ETF, BENCH  # noqa: PLC0415

    bench_tickers = set(_GICS_ETF.values()) | {BENCH}
    bench_closes: dict[str, pd.Series] = {}
    for etf in bench_tickers:
        if etf in bars:
            bench_closes[etf] = bars[etf]["close"].dropna().sort_index()
    return bench_closes


def _load_sector_of() -> dict[str, str]:
    """Load ticker -> sector mapping from ticker_sectors.parquet."""
    if not _TICKER_SECTORS_PATH.exists():
        log.warning("ticker_sectors not found: %s", _TICKER_SECTORS_PATH)
        return {}
    try:
        df = pd.read_parquet(_TICKER_SECTORS_PATH)
        if "ticker" not in df.columns or "sector" not in df.columns:
            return {}
        return dict(zip(df["ticker"].astype(str), df["sector"].astype(str)))
    except Exception as exc:  # noqa: BLE001
        log.warning("ticker_sectors load fail: %s", exc)
        return {}


def _load_pit_membership() -> pd.DataFrame | None:
    """Load sp1500_pit_membership.parquet."""
    if not _PIT_PATH.exists():
        return None
    try:
        df = pd.read_parquet(_PIT_PATH)
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("pit_membership load fail: %s", exc)
        return None


def _load_clocks() -> list[dict[str, Any]]:
    """Load winner-autopsy / long_hold clocks from registry_seed.json."""
    if not _REGISTRY_PATH.exists():
        return []
    try:
        data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        exps = data.get("experiments", [])
        clocks = []
        for e in exps:
            eid = str(e.get("id", "")).lower()
            owner = str(e.get("owner", "")).lower()
            if "winner" in eid or "winner" in owner or "long_hold" in eid or "long_hold" in owner:
                clocks.append({
                    "id": e.get("id", ""),
                    "come_back_on": str(e.get("come_back_on", "")),
                    "note": str(e.get("name", "")),
                    "status": str(e.get("status", "accruing")),
                })
        return clocks
    except Exception as exc:  # noqa: BLE001
        log.warning("clocks load fail: %s", exc)
        return []


# ---------------------------------------------------------------------------
# B-family store loaders
# ---------------------------------------------------------------------------

def _load_material_8k_events() -> pd.DataFrame | None:
    """Load data/edgar/material_8k_events.parquet for B1 feature extraction."""
    if not _MATERIAL_8K_PATH.exists():
        log.warning("material_8k_events not found: %s", _MATERIAL_8K_PATH)
        return None
    try:
        df = pd.read_parquet(_MATERIAL_8K_PATH)
        log.info("Loaded material_8k_events: %d rows", len(df))
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("material_8k_events load fail: %s", exc)
        return None


def _load_annual_statements() -> pd.DataFrame | None:
    """Load data/edgar/statements.parquet (annual grain) for B2 feature extraction."""
    if not _STATEMENTS_PATH.exists():
        log.warning("statements.parquet not found: %s", _STATEMENTS_PATH)
        return None
    try:
        df = pd.read_parquet(_STATEMENTS_PATH)
        log.info("Loaded annual statements: %d rows", len(df))
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("annual statements load fail: %s", exc)
        return None


def _load_index_changes() -> pd.DataFrame | None:
    """Load data/sp_index_changes/changes.parquet for B4 feature extraction."""
    if not _INDEX_CHANGES_PATH.exists():
        log.warning("index_changes not found: %s", _INDEX_CHANGES_PATH)
        return None
    try:
        df = pd.read_parquet(_INDEX_CHANGES_PATH)
        log.info("Loaded index_changes: %d rows", len(df))
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("index_changes load fail: %s", exc)
        return None


def _join_b_features(
    episodes_df: pd.DataFrame,
    events_df: pd.DataFrame | None,
    statements_df: pd.DataFrame | None,
    index_changes_df: pd.DataFrame | None,
) -> pd.DataFrame:
    """Join B1/B2/B4 feature columns onto episodes_df.

    Preserves row order and count exactly (natural key join by position).
    Returns a new DataFrame with B-family columns appended.

    Feature-coverage block (non-null counts) is NOT written here — it goes
    in _build_feature_coverage_block() for inclusion in the panel JSON.
    """
    from engine.winner_autopsy import (  # noqa: PLC0415
        extract_b1_hardening_ladder,
        extract_b2_self_funding,
        extract_b4_index_provenance,
        _empty_b1,
        _empty_b2,
        _empty_b4,
    )

    n = len(episodes_df)
    b1_rows: list[dict[str, Any]] = []
    b2_rows: list[dict[str, Any]] = []
    b4_rows: list[dict[str, Any]] = []

    for _, ep in episodes_df.iterrows():
        ticker = str(ep["ticker"])
        t0 = pd.Timestamp(ep["t0"])

        if events_df is not None:
            b1 = extract_b1_hardening_ladder(ticker, t0, events_df)
        else:
            b1 = _empty_b1()

        if statements_df is not None:
            b2 = extract_b2_self_funding(ticker, t0, statements_df)
        else:
            b2 = _empty_b2()

        if index_changes_df is not None:
            b4 = extract_b4_index_provenance(ticker, t0, index_changes_df)
        else:
            b4 = _empty_b4()

        b1_rows.append(b1)
        b2_rows.append(b2)
        b4_rows.append(b4)

    b1_df = pd.DataFrame(b1_rows)
    b2_df = pd.DataFrame(b2_rows)
    b4_df = pd.DataFrame(b4_rows)

    out = episodes_df.copy()
    for col in b1_df.columns:
        out[col] = b1_df[col].values
    for col in b2_df.columns:
        out[col] = b2_df[col].values
    for col in b4_df.columns:
        out[col] = b4_df[col].values

    log.info(
        "_join_b_features: %d rows, added %d B-family columns",
        n,
        len(b1_df.columns) + len(b2_df.columns) + len(b4_df.columns),
    )
    return out


def _build_feature_coverage_block(episodes_df: pd.DataFrame) -> dict[str, Any]:
    """Build the feature_coverage block for the panel JSON.

    Reports non-null counts per B-family column, split at the 2024-01-01 boundary
    (WA-R7: B2 is a fundamental-family column — episodes with t0 >= 2024 are in the
    A2 firewall until A2 commits and MUST be reported separately).
    """
    b_cols = [
        # B1
        "hard_event_count_126d", "soft_event_count_126d",
        "soft_then_hard", "days_soft_to_hard",
        "hard_event_reversed", "b1_coverage",
        # B2
        "self_funded_at_t0", "b2_cfo_y0", "b2_cfo_y1",
        "b2_capex_y0", "b2_capex_y1", "b2_revenue_y0", "b2_revenue_y1",
        # B4
        "index_announce_within_63d_pre_t0", "index_announce_within_63d_post_t0",
        "b4_coverage",
    ]

    available_cols = [c for c in b_cols if c in episodes_df.columns]
    if not available_cols or episodes_df.empty:
        return {"available": False, "notes": ["B-family columns not yet computed"]}

    t0_col = pd.to_datetime(episodes_df["t0"]) if "t0" in episodes_df.columns else pd.Series(dtype="datetime64[ns]")
    cutoff_2024 = pd.Timestamp("2024-01-01")

    pre_2024_mask = t0_col < cutoff_2024
    post_2024_mask = t0_col >= cutoff_2024

    coverage: dict[str, Any] = {"available": True, "columns": {}}
    for col in available_cols:
        series = episodes_df[col]
        n_total = int(series.notna().sum())
        n_pre = int(series[pre_2024_mask].notna().sum()) if pre_2024_mask.any() else 0
        n_post = int(series[post_2024_mask].notna().sum()) if post_2024_mask.any() else 0
        coverage["columns"][col] = {
            "non_null_total": n_total,
            "non_null_pre_2024": n_pre,
            "non_null_post_2024_a2_firewall": n_post,
        }

    coverage["notes"] = [
        "B2 (self_funded_at_t0 and legs): fundamental-family column — "
        "non_null_post_2024_a2_firewall rows must NOT appear in cross-case "
        "aggregate tables until A2 commits (WA-R7).",
        "B1 era_cutoff=2014-01-01 (LHB-R5/WA-R4): pre-era rows are None.",
        "B4 archive_start=2026-06-11: almost all episodes are None (pre_archive).",
        "hard_event_count_126d omits Item 2.02 (earnings) — see extract_b1_hardening_ladder docstring.",
    ]
    return coverage


# ---------------------------------------------------------------------------
# Panel JSON builder
# ---------------------------------------------------------------------------

def _build_census_block(episodes_df: pd.DataFrame | None) -> dict[str, Any]:
    """Build the census block for winner_autopsy_panel.json."""
    if episodes_df is None or episodes_df.empty:
        return {
            "available": False,
            "n_episodes": 0,
            "date_range": [None, None],
            "universe_n_tickers": 0,
            "price_source_coverage": {"yahoo": 0, "massive": 0, "dead_name": 0, "none": 0},
            "outcome_label_counts": {
                "durable_winner": 0, "clean_hold": 0,
                "blow_off": 0, "failed": 0, "unmatured": 0,
            },
            "by_era": [],
            "notes": [
                "descriptive only; base rates not verdicts (WA-R5)",
                "winner_episodes.parquet not yet generated — run --backfill",
            ],
        }

    n_eps = len(episodes_df)
    t0_col = pd.to_datetime(episodes_df["t0"]) if "t0" in episodes_df.columns else pd.Series(dtype="datetime64[ns]")
    date_range = [
        t0_col.min().date().isoformat() if not t0_col.empty else None,
        t0_col.max().date().isoformat() if not t0_col.empty else None,
    ]

    n_tickers = int(episodes_df["ticker"].nunique()) if "ticker" in episodes_df.columns else 0

    # Price source coverage
    src_counts: dict[str, int] = {"yahoo": 0, "massive": 0, "dead_name": 0, "none": 0}
    if "price_source" in episodes_df.columns:
        for src, cnt in episodes_df["price_source"].value_counts().items():
            key = str(src) if str(src) in src_counts else "none"
            src_counts[key] = int(cnt)

    # Outcome label counts
    label_counts: dict[str, int] = {
        "durable_winner": 0, "clean_hold": 0, "blow_off": 0, "failed": 0, "unmatured": 0
    }
    if "outcome_label" in episodes_df.columns:
        for lbl, cnt in episodes_df["outcome_label"].value_counts().items():
            if str(lbl) in label_counts:
                label_counts[str(lbl)] = int(cnt)

    # By era
    by_era: list[dict[str, Any]] = []
    eras = [
        ("2014-2017", 2014, 2017),
        ("2018-2020", 2018, 2020),
        ("2021-2024", 2021, 2024),
        ("2025+", 2025, 9999),
    ]
    if not t0_col.empty:
        years = t0_col.dt.year
        for era_label, yr_start, yr_end in eras:
            mask = (years >= yr_start) & (years <= yr_end)
            sub = episodes_df[mask]
            n = len(sub)
            # MINOR-5: count distinct MONTHS (not days) to avoid anti-conservative
            # day-count per ticker-cluster time-confound law (repo law DT-R14).
            n_clusters = (
                int(pd.to_datetime(sub["t0"]).dt.to_period("M").nunique())
                if "t0" in sub.columns else 0
            )

            dw_rate = None
            bo_rate = None
            if n > 0 and "outcome_label" in sub.columns:
                labeled = sub[sub["outcome_label"] != "unmatured"]
                if len(labeled) > 0:
                    dw_rate = round(
                        float((labeled["outcome_label"] == "durable_winner").mean()), 4
                    )
                    bo_rate = round(
                        float((labeled["outcome_label"] == "blow_off").mean()), 4
                    )
            by_era.append({
                "era": era_label,
                "n_episodes": n,
                "n_month_clusters": n_clusters,
                "durable_winner_rate": dw_rate,
                "blow_off_rate": bo_rate,
            })

    return {
        "available": True,
        "n_episodes": n_eps,
        "date_range": date_range,
        "universe_n_tickers": n_tickers,
        "price_source_coverage": src_counts,
        "outcome_label_counts": label_counts,
        "by_era": by_era,
        "notes": [
            "descriptive only; base rates not verdicts (WA-R5)",
            "survivorship: episodes on dead names carry survivorship_biased=true",
            "gap_leg_crossed=true for episodes whose forward window crosses 2021-10-25..2025-01-02",
            "basis_mismatch: massive-sourced episodes mix raw name return vs total-return benchmark ETF (bias ≈ dividend-yield differential; material at 126d/252d horizons)",
        ],
    }


def _build_cases_block(
    episodes_df: pd.DataFrame | None,
) -> dict[str, Any]:
    """Parse all case files and build the cases block."""
    from engine.winner_autopsy import parse_case_file, reconcile_case  # noqa: PLC0415

    case_files = sorted(glob.glob(_CASES_GLOB))
    items: list[dict[str, Any]] = []

    for cf in case_files:
        try:
            case = parse_case_file(cf)
        except Exception as exc:  # noqa: BLE001
            log.warning("cases block: skipping %s — parse error: %s", cf, exc)
            continue

        # Reconcile
        if episodes_df is not None and not episodes_df.empty:
            rec = reconcile_case(case, episodes_df)
        else:
            rec = {"case_joined": False, "engine_t0": None, "reconcile": "engine_no_onset"}

        # Count catalysts safely
        ladder = case.get("catalyst_ladder", [])
        n_catalysts = len(ladder) if isinstance(ladder, list) else 0

        rel_path = str(Path(cf).relative_to(_REPO_ROOT))
        items.append({
            "ticker": str(case.get("ticker", "")),
            "episode_year": int(case.get("episode_year", 0)),
            "case_type": str(case.get("case_type", "")),
            "mechanism": str(case.get("mechanism", "")),
            "thesis_one_liner": str(case.get("thesis_one_liner", "")),
            "n_catalysts": n_catalysts,
            "case_t0": str(case.get("t0_hypothesis", "")),
            "engine_t0": rec.get("engine_t0"),
            "case_joined": bool(rec.get("case_joined", False)),
            "reconcile": str(rec.get("reconcile", "engine_no_onset")),
            "file": rel_path,
        })

    return {"n_cases": len(items), "items": items}


def _build_watch_block(
    watch_df: pd.DataFrame | None,
    as_of: str,
) -> dict[str, Any]:
    """Build the watch block for the panel JSON."""
    if watch_df is None or watch_df.empty:
        return {
            "available": False,
            "as_of": as_of,
            "state_counts": {
                "breakaway": 0, "emerging": 0, "digestion": 0,
                "continuation": 0, "failed": 0,
            },
            "top": [],
        }

    state_counts: dict[str, int] = {
        "breakaway": 0, "emerging": 0, "digestion": 0,
        "continuation": 0, "failed": 0,
    }
    if "state" in watch_df.columns:
        for s, cnt in watch_df["state"].value_counts().items():
            if str(s) in state_counts:
                state_counts[str(s)] = int(cnt)

    # Top rows: all non-none states, sorted by excess_21d_pp desc
    non_none = watch_df[watch_df["state"] != "none"] if "state" in watch_df.columns else watch_df
    if not non_none.empty and "excess_21d_pp" in non_none.columns:
        non_none = non_none.sort_values("excess_21d_pp", ascending=False, na_position="last")

    top: list[dict[str, Any]] = []
    for _, row in non_none.iterrows():
        hazards = row.get("hazards", [])
        if not isinstance(hazards, list):
            hazards = []
        top.append({
            "ticker": str(row.get("ticker", "")),
            "sector": str(row.get("sector", "")),
            "benchmark": str(row.get("benchmark", "")),
            "state": str(row.get("state", "none")),
            "excess_21d_pp": (
                round(float(row["excess_21d_pp"]), 2)
                if pd.notna(row.get("excess_21d_pp")) else None
            ),
            "excess_42d_pp": (
                round(float(row["excess_42d_pp"]), 2)
                if pd.notna(row.get("excess_42d_pp")) else None
            ),
            "new_high_63d": bool(row.get("new_high_63d", False)),
            "dollar_vol_z21": (
                round(float(row["dollar_vol_z21"]), 2)
                if pd.notna(row.get("dollar_vol_z21")) else None
            ),
            "days_in_state": int(row.get("days_in_state", 0)),
            "gex_state": None,  # Tier-2 accruing; not yet available
            "hazards": hazards,
            "context": {"context_only": True, "note": ""},
        })

    return {
        "available": True,
        "as_of": as_of,
        "state_counts": state_counts,
        "top": top,
    }


def _write_panel(
    census_block: dict[str, Any],
    cases_block: dict[str, Any],
    watch_block: dict[str, Any],
    clocks: list[dict[str, Any]],
    feature_coverage_block: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Build and optionally write winner_autopsy_panel.json."""
    panel: dict[str, Any] = {
        "schema": "winner_autopsy_panel.v1",
        "generated_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "display_only": True,
        "horizon_role": "hold_thesis",
        "census": census_block,
        "cases": cases_block,
        "watch": watch_block,
        "clocks": clocks,
    }
    if feature_coverage_block is not None:
        panel["feature_coverage"] = feature_coverage_block

    if not dry_run:
        _OUT_DIR.mkdir(parents=True, exist_ok=True)
        _PANEL_PATH.write_text(json.dumps(panel, indent=2, default=str))
        log.info("Wrote %s", _PANEL_PATH)

    return panel


# ---------------------------------------------------------------------------
# Manifest writers
# ---------------------------------------------------------------------------

def _write_episodes_manifest(
    episodes_df: pd.DataFrame | None,
    elapsed: float,
    source_map: dict[str, str],
    dry_run: bool = False,
) -> None:
    """Write winner_episodes_manifest.json."""
    src_cov: dict[str, int] = {"yahoo": 0, "massive": 0, "dead_name": 0, "none": 0}
    for src in source_map.values():
        key = src if src in src_cov else "none"
        src_cov[key] += 1

    n_gap = 0
    if episodes_df is not None and "gap_leg_crossed" in episodes_df.columns:
        n_gap = int(episodes_df["gap_leg_crossed"].sum())

    # MAJOR-3: count basis mismatches
    n_basis_mismatch = 0
    if episodes_df is not None and "basis_mismatch" in episodes_df.columns:
        n_basis_mismatch = int(episodes_df["basis_mismatch"].sum())

    manifest: dict[str, Any] = {
        "schema": "winner_episodes_manifest.v1",
        "as_of": date.today().isoformat(),
        "n_episodes": len(episodes_df) if episodes_df is not None else 0,
        "n_tickers_with_prices": len(source_map),
        "price_source_coverage": src_cov,
        "gap_window_episodes": n_gap,
        "basis_mismatch_count": n_basis_mismatch,
        "price_basis_note": (
            "massive_stock_day episodes use raw (unadjusted) name prices vs "
            "total-return (dividend-adjusted) benchmark ETFs from yahoo. "
            "Excess return is understated for massive-sourced names by approximately "
            "the name's dividend yield; material at 126d/252d horizons for "
            "high-yielding names."
        ),
        "elapsed_seconds": round(elapsed, 2),
        "survivorship_note": (
            "Episodes on tickers not in sp1500_pit_membership may be survivorship-biased. "
            "Dead names covered via data/edgar/dead_name_prices.parquet where available."
        ),
        "_display_only": True,
        "_horizon_role": "hold_thesis",
        "_version": "v1",
    }
    if not dry_run:
        _OUT_DIR.mkdir(parents=True, exist_ok=True)
        _EPISODES_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
        log.info("Wrote %s", _EPISODES_MANIFEST_PATH)


def _write_autopsy_manifest(
    panel: dict[str, Any],
    elapsed: float,
    dry_run: bool = False,
) -> None:
    """Write winner_autopsy_manifest.json."""
    watch = panel.get("watch", {})
    cases = panel.get("cases", {})
    manifest: dict[str, Any] = {
        "schema": "winner_autopsy_manifest.v1",
        "as_of": date.today().isoformat(),
        "n_cases": cases.get("n_cases", 0),
        "watch_available": watch.get("available", False),
        "watch_as_of": watch.get("as_of", ""),
        "elapsed_seconds": round(elapsed, 2),
        "_display_only": True,
        "_horizon_role": "hold_thesis",
        "_version": "v1",
    }
    if not dry_run:
        _OUT_DIR.mkdir(parents=True, exist_ok=True)
        _AUTOPSY_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
        log.info("Wrote %s", _AUTOPSY_MANIFEST_PATH)


# ---------------------------------------------------------------------------
# History append
# ---------------------------------------------------------------------------

def _append_watch_history(watch_df: pd.DataFrame, snapshot_date: str) -> dict[str, Any]:
    """Append watch rows to breakaway_watch_history.parquet, keep-FIRST per (ticker, snapshot_date)."""
    if watch_df is None or watch_df.empty:
        return {"n_written": 0, "n_skipped": 0}

    df_new = watch_df.copy()
    df_new["snapshot_date"] = snapshot_date

    if _WATCH_HISTORY_PATH.exists():
        try:
            existing = pd.read_parquet(_WATCH_HISTORY_PATH)
            # Keep-FIRST: rows already in history for this snapshot_date are skipped
            if "snapshot_date" in existing.columns and "ticker" in existing.columns:
                existing_keys = set(
                    zip(
                        existing["ticker"].astype(str),
                        existing["snapshot_date"].astype(str),
                    )
                )
                new_rows = df_new[
                    ~df_new.apply(
                        lambda r: (str(r["ticker"]), str(r["snapshot_date"])) in existing_keys,
                        axis=1,
                    )
                ]
            else:
                new_rows = df_new
                existing = pd.DataFrame()
        except Exception as exc:  # noqa: BLE001
            log.warning("watch_history load fail: %s", exc)
            new_rows = df_new
            existing = pd.DataFrame()
    else:
        new_rows = df_new
        existing = pd.DataFrame()

    n_written = len(new_rows)
    n_skipped = len(df_new) - n_written

    if n_written > 0:
        combined = pd.concat([existing, new_rows], ignore_index=True)
        _OUT_DIR.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(_WATCH_HISTORY_PATH, index=False)
        log.info("watch_history: wrote=%d skipped=%d", n_written, n_skipped)

    return {"n_written": n_written, "n_skipped": n_skipped}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:  # noqa: C901
    parser = argparse.ArgumentParser(description="Winner Autopsy Lab builder")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute but do not write output files")
    parser.add_argument("--smoke", action="store_true",
                        help="First 200 names only (fast smoke-test)")
    parser.add_argument(
        "--write-history",
        action="store_true",
        help=(
            "Append watch rows to breakaway_watch_history.parquet (keep-FIRST per "
            "ticker+snapshot_date). NIGHTLY ONLY — sole-advancer law. Never combine "
            "with --smoke."
        ),
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help=(
            "Full historical episode census over all names. Writes "
            "winner_episodes.parquet and manifest. Off-render, on-demand."
        ),
    )
    parser.add_argument(
        "--features-only",
        action="store_true",
        help=(
            "Join B1/B2/B4 feature columns onto the EXISTING winner_episodes.parquet "
            "without recomputing episodes (no price stores required). Writes updated "
            "winner_episodes.parquet and feature_coverage block in panel JSON. "
            "Use when price stores are absent but B-family stores are available."
        ),
    )
    args = parser.parse_args(argv)

    # HARD-EXIT guard: --smoke + --write-history is forbidden (WA-R9 sole-advancer)
    if args.smoke and args.write_history:
        sys.stderr.write(
            "ERROR: --smoke and --write-history are mutually exclusive.\n"
            "A truncated 200-name smoke cross-section must never be written to the\n"
            "history store — keep-FIRST semantics would freeze it permanently at a\n"
            "partial universe, corrupting all longitudinal analysis (WA-R9).\n"
        )
        return 2

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    t_start = time.time()
    log.info(
        "build_winner_autopsy: starting "
        "(dry_run=%s smoke=%s backfill=%s write_history=%s features_only=%s)",
        args.dry_run, args.smoke, args.backfill, args.write_history,
        getattr(args, "features_only", False),
    )

    # ---- Import engine ----
    try:
        from engine.winner_autopsy import (  # noqa: PLC0415
            detect_episodes,
            label_outcomes,
            compute_watch_states,
            sample_controls,
            stamp,
            SCHEMA_EPISODES,
        )
    except ImportError as exc:
        log.error("Cannot import engine.winner_autopsy: %s", exc)
        return 1

    # ---- Load B-family feature stores (needed for backfill + features-only) ----
    features_only = getattr(args, "features_only", False)
    events_df = _load_material_8k_events()
    statements_df = _load_annual_statements()
    index_changes_df = _load_index_changes()

    # ---- features-only path ----
    if features_only:
        log.info("build_winner_autopsy: --features-only mode")
        if not _EPISODES_PATH.exists():
            log.error("--features-only requires existing %s", _EPISODES_PATH)
            return 1
        try:
            episodes_df = pd.read_parquet(_EPISODES_PATH)
            log.info("Loaded existing episodes: %d rows", len(episodes_df))
        except Exception as exc:  # noqa: BLE001
            log.error("Cannot load existing episodes: %s", exc)
            return 1

        n_before = len(episodes_df)
        episodes_df = _join_b_features(episodes_df, events_df, statements_df, index_changes_df)
        # Bump schema stamp
        episodes_df["_schema"] = SCHEMA_EPISODES
        episodes_df["_version"] = "v2"
        assert len(episodes_df) == n_before, (
            f"Row count changed during B-feature join: {n_before} -> {len(episodes_df)}"
        )

        if not args.dry_run:
            _OUT_DIR.mkdir(parents=True, exist_ok=True)
            episodes_df.to_parquet(_EPISODES_PATH, index=False)
            log.info("features-only: wrote %s (%d rows)", _EPISODES_PATH, len(episodes_df))

        feature_cov = _build_feature_coverage_block(episodes_df)
        # Print coverage summary
        if feature_cov.get("available") and "columns" in feature_cov:
            print("=== B-FEATURE COVERAGE ===")
            for col, counts in feature_cov["columns"].items():
                print(
                    f"  {col}: non_null_total={counts['non_null_total']}"
                    f"  pre_2024={counts['non_null_pre_2024']}"
                    f"  post_2024={counts['non_null_post_2024_a2_firewall']}"
                )
        return 0

    # ---- Load prices ----
    # In smoke mode, limit yahoo loading to 200 non-bench tickers to avoid
    # loading all 686 files (~47s on this host). Bench ETFs always loaded.
    yahoo_smoke_limit = 200 if args.smoke else None
    yahoo_bars = _load_yahoo_bars(smoke_limit=yahoo_smoke_limit)
    massive_dir = _find_massive_dir()
    massive_bars = _load_massive_bars(massive_dir) if massive_dir else {}
    dead_name_bars = _load_dead_name_bars()

    all_bars, source_map = _merge_bars(yahoo_bars, massive_bars, dead_name_bars)

    if not all_bars:
        log.warning("::warning:: no name prices found in any source — proceeding with degraded output")

    bench_closes = _load_bench_closes(all_bars)
    sector_of = _load_sector_of()
    pit_df = _load_pit_membership()
    clocks = _load_clocks()
    as_of_str = date.today().isoformat()

    # ---- Smoke: limit to first 200 names ----
    if args.smoke:
        sorted_names = sorted(k for k in all_bars if k not in bench_closes)[:200]
        smoke_bars = {k: all_bars[k] for k in sorted_names}
        smoke_bars.update({k: all_bars[k] for k in bench_closes if k in all_bars})
        working_bars = smoke_bars
        log.info("smoke mode: %d names", len(sorted_names))
    else:
        working_bars = all_bars
        log.info("full mode: %d names", len(all_bars))

    # ---- Backfill: full historical census ----
    episodes_df: pd.DataFrame | None = None
    feature_cov_block: dict[str, Any] | None = None

    if args.backfill:
        log.info("build_winner_autopsy: running full backfill census …")
        t_census = time.time()

        episodes_df = detect_episodes(working_bars, bench_closes, sector_of)

        if episodes_df is not None and not episodes_df.empty:
            # Annotate price_source
            episodes_df["price_source"] = episodes_df["ticker"].map(
                lambda t: source_map.get(t, "none")
            )

            # MAJOR-3: Disclose dividend-adjustment basis mismatch.
            # yahoo and dead_name sources are total-return (dividend-adjusted);
            # massive_stock_day is raw (unadjusted).  Benchmark ETFs are always
            # loaded from yahoo (total-return).  When a name is sourced from
            # massive, excess = raw_name - total_return_bench, understating true
            # excess by approximately the name's dividend yield.
            def _price_basis(src: str) -> str:
                return "raw" if src == "massive" else "total_return"

            episodes_df["price_basis"] = episodes_df["price_source"].map(_price_basis)
            episodes_df["benchmark_basis"] = "total_return"
            episodes_df["basis_mismatch"] = episodes_df["price_basis"] != episodes_df["benchmark_basis"]

            # Label outcomes
            outcome_rows: list[dict[str, Any]] = []
            for _, ep in episodes_df.iterrows():
                ticker = str(ep["ticker"])
                t0 = pd.Timestamp(ep["t0"])
                bench_etf = str(ep.get("benchmark", "SPY"))
                bench_s = bench_closes.get(bench_etf)
                if bench_s is None:
                    bench_s = bench_closes.get("SPY")
                if bench_s is None:
                    outcome_rows.append(label_outcomes(pd.Series(dtype=float), pd.Series(dtype=float), t0))
                    continue
                df_t = working_bars.get(ticker)
                if df_t is None:
                    outcome_rows.append(label_outcomes(pd.Series(dtype=float), pd.Series(dtype=float), t0))
                    continue
                close_s = df_t["close"].dropna().sort_index()
                outcomes = label_outcomes(close_s, bench_s, t0)
                outcome_rows.append(outcomes)

            if outcome_rows:
                outcomes_df = pd.DataFrame(outcome_rows)
                for col in outcomes_df.columns:
                    episodes_df[col] = outcomes_df[col].values

            # Control counts (not full sample — just count)
            if pit_df is not None:
                ctrl_counts: list[int] = []
                for _, ep in episodes_df.iterrows():
                    controls = sample_controls(ep, working_bars, sector_of, pit_df, k=20)
                    ctrl_counts.append(len(controls))
                episodes_df["n_controls"] = ctrl_counts

            # Join B-family feature columns (B1/B2/B4)
            n_before = len(episodes_df)
            episodes_df = _join_b_features(
                episodes_df, events_df, statements_df, index_changes_df
            )
            assert len(episodes_df) == n_before, (
                f"Row count changed during B-feature join: {n_before} -> {len(episodes_df)}"
            )
            feature_cov_block = _build_feature_coverage_block(episodes_df)

            # Stamp (v2 — schema bumped for B-family columns)
            episodes_df["_display_only"] = True
            episodes_df["_horizon_role"] = "hold_thesis"
            episodes_df["_version"] = "v2"
            episodes_df["_schema"] = SCHEMA_EPISODES

            log.info(
                "build_winner_autopsy: backfill complete: %d episodes in %.1fs",
                len(episodes_df),
                time.time() - t_census,
            )

        elapsed_census = time.time() - t_census
        _write_episodes_manifest(episodes_df, elapsed_census, source_map, dry_run=args.dry_run)

        if not args.dry_run and episodes_df is not None and not episodes_df.empty:
            _OUT_DIR.mkdir(parents=True, exist_ok=True)
            episodes_df.to_parquet(_EPISODES_PATH, index=False)
            log.info("Wrote %s (%d rows)", _EPISODES_PATH, len(episodes_df))

    else:
        # Default mode: try to load existing episodes for reconciliation
        if _EPISODES_PATH.exists():
            try:
                episodes_df = pd.read_parquet(_EPISODES_PATH)
                log.info("Loaded existing episodes: %d rows", len(episodes_df))
            except Exception as exc:  # noqa: BLE001
                log.warning("Cannot load existing episodes: %s", exc)
        # Rebuild feature coverage block for panel even in default mode
        if episodes_df is not None and not episodes_df.empty:
            feature_cov_block = _build_feature_coverage_block(episodes_df)

    # ---- Watch states (current) ----
    watch_df: pd.DataFrame | None = None
    if working_bars:
        try:
            watch_df = compute_watch_states(working_bars, bench_closes, sector_of)
            if watch_df is not None and not watch_df.empty:
                watch_df["snapshot_date"] = as_of_str
                watch_df["_display_only"] = True
                watch_df["_horizon_role"] = "hold_thesis"
                watch_df["_version"] = "v1"
                log.info("build_winner_autopsy: watch states computed: %d rows", len(watch_df))
            else:
                log.info("build_winner_autopsy: watch states: empty result")
        except Exception as exc:  # noqa: BLE001
            log.warning("watch states failed (non-fatal): %s", exc)

    # Write watch parquet
    if not args.dry_run and watch_df is not None and not watch_df.empty:
        _OUT_DIR.mkdir(parents=True, exist_ok=True)
        watch_df.to_parquet(_WATCH_PATH, index=False)
        log.info("Wrote %s", _WATCH_PATH)

    # ---- Panel JSON ----
    census_block = _build_census_block(episodes_df)
    cases_block = _build_cases_block(episodes_df)
    watch_block = _build_watch_block(watch_df, as_of_str)

    elapsed_total = time.time() - t_start
    panel = _write_panel(
        census_block, cases_block, watch_block, clocks,
        feature_coverage_block=feature_cov_block,
        dry_run=args.dry_run,
    )
    _write_autopsy_manifest(panel, elapsed_total, dry_run=args.dry_run)

    # ---- History append (sole-advancer; nightly only) ----
    if args.write_history:
        if watch_df is not None and not watch_df.empty:
            summary = _append_watch_history(watch_df, as_of_str)
            log.info(
                "watch_history: wrote=%d skipped=%d",
                summary["n_written"],
                summary["n_skipped"],
            )
        else:
            log.info("watch_history: nothing to append (watch_df empty)")

    # ---- Summary ----
    n_episodes = len(episodes_df) if episodes_df is not None and not episodes_df.empty else 0
    n_cases = cases_block.get("n_cases", 0)
    watch_avail = watch_block.get("available", False)
    log.info(
        "build_winner_autopsy: done in %.1fs — episodes=%d cases=%d watch_available=%s",
        elapsed_total,
        n_episodes,
        n_cases,
        watch_avail,
    )

    # Coverage warning if no name prices
    n_none = sum(1 for s in source_map.values() if s == "none")
    total_names = len(source_map)
    if total_names == 0 or (total_names - n_none) == 0:
        print("::warning:: no name prices found — winner_autopsy_panel.json written with degraded coverage")
    else:
        print(
            f"=== WINNER AUTOPSY ===\n"
            f"  episodes:  {n_episodes}\n"
            f"  cases:     {n_cases}\n"
            f"  watch:     {'available' if watch_avail else 'unavailable'}\n"
            f"  tickers:   {total_names}\n"
            f"  elapsed:   {elapsed_total:.1f}s\n"
            f"  as_of:     {as_of_str}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
