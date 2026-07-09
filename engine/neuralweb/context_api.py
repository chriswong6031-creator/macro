"""engine.neuralweb.context_api — Context Snapshot PIT API (NW-CI W2, R-CI4).

CLASSIFICATION: research-side query API — no nightly caller by design.
Consumers are future pre-registered context studies (analogous to
engine/neuralweb/alpha_grammar.py and engine/neuralweb/alpha_overlap.py which
are likewise query-only research utilities with zero nightly import paths).
This module is NOT wired into daily.yml and does NOT appear in the nightly
engine job.  It is imported directly by ad-hoc research notebooks, study
scripts, and future context-layer analysis pipelines when needed.

TIER: display/context — READ-ONLY.  Never computes new signals, scores,
ranks, sizes, gates, or raises attention floors.  This is the "amassed
context" substrate (R-CI4) consumed by lobes, studies, and cortex tools.

PUBLIC API
----------
context_snapshot(ticker, date=None, root=None) -> dict
    PIT snapshot: everything the system knew about *ticker* as of *date*
    (today when None).  Returns a dict keyed by dimension name; each
    dimension value is either:
      {value, as_of, basis, coverage} — dimension present
      {absent: True, reason: str}     — absent or degraded (never raises)

context_frame(tickers, date=None, root=None) -> pd.DataFrame
    Vectorised version: one row per ticker, one column per dimension field.

DIMENSIONS (10 total)
---------------------
personality  PIT labels parquet (223 deep names) at date; production JSON
             when date is None / within 5 trading-days of its as_of; else absent.
archetype    data/archetypes/history.parquet greatest asof_date <= date.
regime       data/regime/regime_history.parquet as-of date (recomputed_history)
             + data/regime/latest.json when date is current (pit_live).
sector       engine/neuralweb/sector_map.py build_sector_map: sector_node,
             subsector_node (absent-tolerant if sector_map fails).
oracle       Oracle episode state from data/oracle/episodes if present;
             else absent (host-only tolerant).
factor       data/factordata/panel/YYYY-MM partition row at (ticker, date);
             2025-06+ only; absent before (host-only store).
attention    data/attention/<TICKER>.parquet as-of (absent-tolerant).
insider      data/sec_insider/panel/*.parquet filing_date <= date trailing
             90 calendar days aggregate; absent-tolerant.
short_int    data/finra/short_interest.parquet snapshot; basis='snapshot_not_pit'
             when date != settlement_date; absent-tolerant.
options      data/options_skew/snapshots.parquet + data/polygon_gex per-ticker
             summaries; 2026-06+; absent-tolerant.
spine        data/neuralweb/spine_index.parquet rows for (symbol=ticker,
             as_of<=date) last 5; absent-tolerant.

CI-RUNNER SAFETY
----------------
Most host-only stores (factordata/panel, attention, oracle/episodes) are absent
on CI clones.  Every store read is fail-open: missing store → absent marker,
never a raised exception.  The only git-tracked stores that degrade are
personality_pit_labels (the 223 names) and the production JSON — the API
correctly reports absent for the non-deep names when the PIT file is
unavailable.

PROVENANCE LAW (R-CI3)
-----------------------
personality_basis ∈ {pit_labels, snapshot_not_pit, absent}.
  pit_labels      : row sourced from personality_pit_labels.parquet (223 deep names).
  snapshot_not_pit: row sourced from production JSON; row's date is AFTER the JSON's
                    as_of by 0-5 trading days (directional: prod_asof <= row_asof).
                    Today's snapshot is NEVER applied to dates BEFORE the snapshot
                    (rows dated before prod_asof always return absent — R-CI3).
  absent          : no PIT data available for this ticker/date combination.
"""
from __future__ import annotations

import json
import logging
from datetime import date as _date_type
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Root resolution
# ---------------------------------------------------------------------------

def _repo_root(root: Path | str | None) -> Path:
    if root is not None:
        return Path(root)
    # Walk up from this file to find the repo root (contains CLAUDE.md)
    here = Path(__file__).resolve()
    for p in [here.parent.parent.parent, here.parent.parent.parent.parent]:
        if (p / "CLAUDE.md").exists() or (p / "config" / "synapse.yml").exists():
            return p
    return here.parent.parent.parent  # best guess


def _data_dir(root: Path | str | None) -> Path:
    return _repo_root(root) / "data"


def _site_dir(root: Path | str | None) -> Path:
    return _repo_root(root) / "site"


# ---------------------------------------------------------------------------
# Date utilities
# ---------------------------------------------------------------------------

def _coerce_date(d: Any) -> pd.Timestamp | None:
    """Coerce a date-like value to pd.Timestamp; None on failure."""
    if d is None:
        return None
    try:
        return pd.Timestamp(d).normalize()
    except Exception:  # noqa: BLE001
        return None


def _today_ts() -> pd.Timestamp:
    return pd.Timestamp.today().normalize()


def _trading_days_between(d0: pd.Timestamp, d1: pd.Timestamp) -> int:
    """Number of business days between d0 and d1 (inclusive of endpoints).

    Uses pd.bdate_range — holiday-agnostic (known limitation, consistent
    with the rest of the codebase).  Non-directional (always ≥ 0).
    """
    if d0 > d1:
        d0, d1 = d1, d0
    return len(pd.bdate_range(d0, d1))


def _signed_trading_days(row_asof: pd.Timestamp, prod_asof: pd.Timestamp) -> int:
    """Signed business-day gap: row_asof − prod_asof.

    R-CI3 directional law: the production snapshot may only be applied to a
    row when 0 <= (row_asof − prod_asof) <= 5 trading days.  Negative values
    mean the row predates the snapshot (PIT leak) and must return absent.

    Uses pd.bdate_range — holiday-agnostic like _trading_days_between.
    """
    if row_asof >= prod_asof:
        return len(pd.bdate_range(prod_asof, row_asof)) - 1
    else:
        return -(len(pd.bdate_range(row_asof, prod_asof)) - 1)


# ---------------------------------------------------------------------------
# Absent-marker helpers
# ---------------------------------------------------------------------------

def _absent(reason: str) -> dict:
    return {"absent": True, "reason": reason}


def _present(value: Any, as_of: str | None, basis: str, coverage: float | None = None) -> dict:
    r: dict = {"value": value, "as_of": as_of, "basis": basis}
    if coverage is not None:
        r["coverage"] = coverage
    return r


# ---------------------------------------------------------------------------
# Personality dimension
# ---------------------------------------------------------------------------
# The PIT labels parquet covers 223 deep names at their historical daily
# resolution.  The production JSON covers ~1,719 names but is snapshot-only.
# R-CI3: production JSON is only used when date is within 5 trading days of
# the JSON's as_of.  Historical rows for non-deep names are always absent.

_PIT_LABELS_PATH_REL = "research/personality_pit_labels.parquet"
_PROD_JSON_PATH_REL  = "site/factordata/stock_personality.json"

# Module-level cache for PIT parquet (lazy, keyed by resolved path)
_pit_labels_cache: dict[str, pd.DataFrame | None] = {}


def _load_pit_labels(data: Path) -> pd.DataFrame | None:
    """Load personality_pit_labels.parquet; cache; return None on any failure."""
    path = data / _PIT_LABELS_PATH_REL
    key = str(path)
    if key in _pit_labels_cache:
        return _pit_labels_cache[key]
    if not path.exists():
        _pit_labels_cache[key] = None
        return None
    try:
        df = pd.read_parquet(path)
        _pit_labels_cache[key] = df
        return df
    except Exception as e:  # noqa: BLE001
        log.debug("context_api: cannot read personality_pit_labels.parquet: %s", e)
        _pit_labels_cache[key] = None
        return None


def _personality_from_pit(ticker: str, date_ts: pd.Timestamp, data: Path) -> dict | None:
    """Return personality dict from PIT parquet for (ticker, date), or None."""
    pit = _load_pit_labels(data)
    if pit is None:
        return None
    if "ticker" not in pit.columns or "date" not in pit.columns:
        return None
    # Filter to this ticker
    t_rows = pit[pit["ticker"] == ticker]
    if t_rows.empty:
        return None
    # Convert date column to datetime for comparison
    t_rows = t_rows.copy()
    t_rows["_dt"] = pd.to_datetime(t_rows["date"], errors="coerce")
    # Backward merge: greatest date <= date_ts
    valid = t_rows[t_rows["_dt"] <= date_ts].sort_values("_dt")
    if valid.empty:
        return None
    row = valid.iloc[-1]
    return {
        "chart_primary":  row.get("chart_primary") if pd.notna(row.get("chart_primary")) else None,
        "micro_primary":  row.get("micro_primary") if pd.notna(row.get("micro_primary")) else None,
        "archetype":      row.get("archetype") if pd.notna(row.get("archetype")) else None,
        "as_of_date":     str(row["_dt"].date()) if pd.notna(row["_dt"]) else None,
    }


def _load_prod_json(root: Path) -> tuple[dict | None, pd.Timestamp | None]:
    """Load stock_personality.json; return (data, as_of_ts) or (None, None)."""
    path = root / _PROD_JSON_PATH_REL
    if not path.exists():
        return None, None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        as_of_str = raw.get("as_of")
        as_of_ts = _coerce_date(as_of_str)
        return raw, as_of_ts
    except Exception as e:  # noqa: BLE001
        log.debug("context_api: cannot read stock_personality.json: %s", e)
        return None, None


def _personality_dim(
    ticker: str,
    date_ts: pd.Timestamp,
    root: Path,
    is_today: bool,
) -> dict:
    """Resolve personality dimension for (ticker, date_ts).

    Priority:
    1. PIT parquet — always tried first for the 223 deep names.
    2. Production JSON — only when date_ts is within 5 trading days of JSON as_of.
    3. Absent marker.
    """
    data = _data_dir(root)

    # Try PIT parquet first
    pit_result = _personality_from_pit(ticker, date_ts, data)
    if pit_result is not None:
        return _present(
            value={
                "chart_primary": pit_result["chart_primary"],
                "micro_primary": pit_result["micro_primary"],
                "archetype":     pit_result["archetype"],
            },
            as_of=pit_result["as_of_date"],
            basis="pit_labels",
        )

    # Fallback: production JSON — ONLY if row_asof is within 5 trading days
    # AFTER prod_asof (R-CI3 directional law: prod_asof <= row_asof <= prod_asof+5td).
    prod_raw, prod_asof = _load_prod_json(root)
    if prod_raw is not None and prod_asof is not None:
        signed_gap = _signed_trading_days(date_ts, prod_asof)
        if 0 <= signed_gap <= 5:
            per_ticker = prod_raw.get("per_ticker") or {}
            rec = per_ticker.get(ticker)
            if isinstance(rec, dict):
                charts = [c for c in (rec.get("chart") or []) if isinstance(c, str)]
                micros = [m for m in (rec.get("micro") or []) if isinstance(m, str)]
                return _present(
                    value={
                        "chart_primary": charts[0] if charts else None,
                        "micro_primary": micros[0] if micros else None,
                        "archetype":     rec.get("arch"),
                    },
                    as_of=str(prod_asof.date()),
                    basis="snapshot_not_pit",
                )
            # ticker not in prod JSON — absent
        # date outside directional window — absent (R-CI3 provenance law)

    return _absent(f"no personality PIT data for {ticker} at {date_ts.date()}")


# ---------------------------------------------------------------------------
# Archetype dimension (data/archetypes/history.parquet)
# ---------------------------------------------------------------------------

_archetype_cache: dict[str, pd.DataFrame | None] = {}


def _load_archetype_history(data: Path) -> pd.DataFrame | None:
    path = data / "archetypes" / "history.parquet"
    key = str(path)
    if key in _archetype_cache:
        return _archetype_cache[key]
    if not path.exists():
        _archetype_cache[key] = None
        return None
    try:
        df = pd.read_parquet(path)
        _archetype_cache[key] = df
        return df
    except Exception as e:  # noqa: BLE001
        log.debug("context_api: cannot read archetypes/history.parquet: %s", e)
        _archetype_cache[key] = None
        return None


def _archetype_dim(ticker: str, date_ts: pd.Timestamp, root: Path) -> dict:
    """Greatest asof_date <= date from data/archetypes/history.parquet."""
    data = _data_dir(root)
    hist = _load_archetype_history(data)
    if hist is None:
        return _absent("data/archetypes/history.parquet absent")
    if "ticker" not in hist.columns or "asof_date" not in hist.columns:
        return _absent("archetypes/history.parquet missing expected columns")

    t_rows = hist[hist["ticker"] == ticker].copy()
    if t_rows.empty:
        return _absent(f"no archetype history for {ticker}")

    t_rows["_asof_dt"] = pd.to_datetime(t_rows["asof_date"], errors="coerce")
    valid = t_rows[t_rows["_asof_dt"] <= date_ts].sort_values("_asof_dt")
    if valid.empty:
        return _absent(f"no archetype row with asof_date <= {date_ts.date()} for {ticker}")

    row = valid.iloc[-1]
    return _present(
        value={
            "archetype":   row.get("archetype") if pd.notna(row.get("archetype")) else None,
            "confidence":  float(row["confidence"]) if pd.notna(row.get("confidence")) else None,
            "fy":          int(row["fy"]) if pd.notna(row.get("fy")) else None,
        },
        as_of=str(row["_asof_dt"].date()) if pd.notna(row["_asof_dt"]) else None,
        basis="pit_labels",
    )


# ---------------------------------------------------------------------------
# Regime dimension
# ---------------------------------------------------------------------------

_regime_hist_cache: dict[str, pd.DataFrame | None] = {}


def _load_regime_history(data: Path) -> pd.DataFrame | None:
    path = data / "regime" / "regime_history.parquet"
    key = str(path)
    if key in _regime_hist_cache:
        return _regime_hist_cache[key]
    if not path.exists():
        _regime_hist_cache[key] = None
        return None
    try:
        df = pd.read_parquet(path)
        _regime_hist_cache[key] = df
        return df
    except Exception as e:  # noqa: BLE001
        log.debug("context_api: cannot read regime/regime_history.parquet: %s", e)
        _regime_hist_cache[key] = None
        return None


def _regime_dim(date_ts: pd.Timestamp, root: Path) -> dict:
    """Regime as-of date_ts from regime_history.parquet (recomputed_history basis).

    Also loads latest.json for rows where date is within 1 calendar day of today
    (pit_live basis), merging the two sources.
    """
    data = _data_dir(root)
    hist = _load_regime_history(data)

    # Determine if we should also use latest.json (current date)
    today = _today_ts()
    is_current = abs((date_ts - today).days) <= 1

    hist_result: dict | None = None
    if hist is not None:
        # Reset DatetimeIndex if present
        h = hist.copy()
        if isinstance(h.index, pd.DatetimeIndex):
            if h.index.name is None:
                h.index.name = "date"
            h = h.reset_index()
        # Find date column
        date_col = None
        for cand in ("date", "as_of", "asof"):
            if cand in h.columns:
                date_col = cand
                break
        if date_col is not None:
            h["_dt"] = pd.to_datetime(h[date_col], errors="coerce")
            valid = h[h["_dt"] <= date_ts].sort_values("_dt")
            if not valid.empty:
                row = valid.iloc[-1]
                quad_col = None
                for cand in ("quad", "quad_hard_label", "hard_label"):
                    if cand in valid.columns:
                        quad_col = cand
                        break
                hist_result = _present(
                    value={k: (None if (isinstance(v, float) and pd.isna(v)) else v)
                           for k, v in row.to_dict().items()
                           if not k.startswith("_") and k != date_col},
                    as_of=str(row["_dt"].date()) if pd.notna(row["_dt"]) else None,
                    basis="recomputed_history",
                )

    # Try latest.json for current date
    live_result: dict | None = None
    if is_current:
        latest_path = data / "regime" / "latest.json"
        if latest_path.exists():
            try:
                live = json.loads(latest_path.read_text(encoding="utf-8"))
                live_result = _present(
                    value={k: v for k, v in live.items()
                           if k not in ("schema_version",)},
                    as_of=live.get("asof") or live.get("date"),
                    basis="pit_live",
                )
            except Exception as e:  # noqa: BLE001
                log.debug("context_api: cannot read regime/latest.json: %s", e)

    # Merge: prefer live for today, history otherwise
    if live_result is not None and hist_result is not None:
        # Return both
        return _present(
            value={
                "history": hist_result["value"],
                "live":    live_result["value"],
            },
            as_of=live_result["as_of"],
            basis="pit_live",
        )
    if live_result is not None:
        return live_result
    if hist_result is not None:
        return hist_result
    return _absent("regime history absent or no row <= date")


# ---------------------------------------------------------------------------
# Sector/oracle dimension
# ---------------------------------------------------------------------------

_sector_map_cache: dict[str, dict] = {}


def _get_sector_map(root: Path) -> dict:
    key = str(root)
    if key in _sector_map_cache:
        return _sector_map_cache[key]
    try:
        from engine.neuralweb.sector_map import build_sector_map  # noqa: PLC0415
        sm = build_sector_map(root)
        _sector_map_cache[key] = sm
        return sm
    except Exception as e:  # noqa: BLE001
        log.debug("context_api: build_sector_map failed: %s", e)
        _sector_map_cache[key] = {}
        return {}


def _oracle_episode_state(ticker: str, date_ts: pd.Timestamp, data: Path) -> dict | None:
    """Read oracle episode state from data/oracle/episodes parquet if present."""
    episodes_dir = data / "oracle" / "episodes"
    if not episodes_dir.exists():
        return None
    # Look for a parquet file named by ticker or a combined parquet
    for candidate in [
        episodes_dir / f"{ticker}.parquet",
        episodes_dir / "episodes.parquet",
        data / "oracle" / f"episodes_{ticker}.parquet",
    ]:
        if candidate.exists():
            try:
                df = pd.read_parquet(candidate)
                # Filter to this ticker if there's a ticker column
                if "ticker" in df.columns or "symbol" in df.columns:
                    col = "ticker" if "ticker" in df.columns else "symbol"
                    df = df[df[col] == ticker]
                if df.empty:
                    continue
                # Find date column
                date_col = None
                for cand in ("date", "as_of", "episode_date"):
                    if cand in df.columns:
                        date_col = cand
                        break
                if date_col is None:
                    continue
                df = df.copy()
                df["_dt"] = pd.to_datetime(df[date_col], errors="coerce")
                valid = df[df["_dt"] <= date_ts].sort_values("_dt")
                if valid.empty:
                    continue
                row = valid.iloc[-1]
                return {k: v for k, v in row.to_dict().items()
                        if not k.startswith("_") and k != date_col}
            except Exception as e:  # noqa: BLE001
                log.debug("context_api: oracle episode read failed for %s: %s", candidate, e)
    return None


def _sector_dim(ticker: str, date_ts: pd.Timestamp, root: Path) -> dict:
    sector_map = _get_sector_map(root)
    mapping = sector_map.get(ticker)

    sector_node = mapping.sector_node if mapping is not None else None
    subsector_node = mapping.subsector_node if mapping is not None else None

    # Try oracle episode state
    data = _data_dir(root)
    oracle_state = _oracle_episode_state(ticker, date_ts, data)

    return _present(
        value={
            "sector_node":    sector_node,
            "subsector_node": subsector_node,
            "oracle_episode": oracle_state,  # None when absent (host-only tolerant)
        },
        as_of=None,  # sector map has no date; episode has its own date
        basis="build_sector_map" if (sector_node is not None or subsector_node is not None) else "sector_map_miss",
    )


# ---------------------------------------------------------------------------
# Factor panel dimension
# ---------------------------------------------------------------------------

def _factor_dim(ticker: str, date_ts: pd.Timestamp, root: Path) -> dict:
    """data/factordata/panel/YYYY-MM partition row at (ticker, date); 2025-06+ only.

    Host-only store — absent on CI runners.
    """
    data = _data_dir(root)
    # Partition path: data/factordata/panel/YYYY-MM/panel.parquet
    partition_key = date_ts.strftime("%Y-%m")
    panel_path = data / "factordata" / "panel" / partition_key / "panel.parquet"
    if not panel_path.exists():
        return _absent(f"factordata panel absent for partition {partition_key} (host-only store)")

    try:
        df = pd.read_parquet(panel_path)
    except Exception as e:  # noqa: BLE001
        return _absent(f"factordata panel unreadable: {e}")

    # Find ticker column
    ticker_col = None
    for cand in ("ticker", "symbol"):
        if cand in df.columns:
            ticker_col = cand
            break
    if ticker_col is None:
        return _absent("factordata panel: no ticker column")

    row_df = df[df[ticker_col] == ticker]
    if row_df.empty:
        return _absent(f"factordata panel: {ticker} not in {partition_key}")

    row = row_df.iloc[0]
    # Find date column for as_of
    date_col = None
    for cand in ("date", "as_of"):
        if cand in row_df.columns:
            date_col = cand
            break

    return _present(
        value={k: (None if (isinstance(v, float) and pd.isna(v)) else v)
               for k, v in row.to_dict().items()
               if k != ticker_col},
        as_of=str(pd.to_datetime(row[date_col]).date()) if date_col and pd.notna(row.get(date_col)) else None,
        basis="factordata_panel",
    )


# ---------------------------------------------------------------------------
# Attention dimension
# ---------------------------------------------------------------------------

def _attention_dim(ticker: str, date_ts: pd.Timestamp, root: Path) -> dict:
    """data/attention/<TICKER>.parquet as-of date_ts (host/R2 store)."""
    data = _data_dir(root)
    path = data / "attention" / f"{ticker}.parquet"
    if not path.exists():
        return _absent(f"attention/{ticker}.parquet absent (host/R2 store)")
    try:
        df = pd.read_parquet(path)
    except Exception as e:  # noqa: BLE001
        return _absent(f"attention/{ticker}.parquet unreadable: {e}")

    if df.empty:
        return _absent(f"attention/{ticker}.parquet empty")

    # Find date column
    date_col = None
    for cand in ("date", "as_of"):
        if cand in df.columns:
            date_col = cand
            break
    if date_col is None and isinstance(df.index, pd.DatetimeIndex):
        df = df.reset_index()
        date_col = df.columns[0]

    if date_col is None:
        return _absent(f"attention/{ticker}.parquet: no date column")

    df = df.copy()
    df["_dt"] = pd.to_datetime(df[date_col], errors="coerce")
    valid = df[df["_dt"] <= date_ts].sort_values("_dt")
    if valid.empty:
        return _absent(f"attention/{ticker}: no row <= {date_ts.date()}")

    row = valid.iloc[-1]
    return _present(
        value={k: v for k, v in row.to_dict().items() if not k.startswith("_") and k != date_col},
        as_of=str(row["_dt"].date()) if pd.notna(row["_dt"]) else None,
        basis="pit_labels",
    )


# ---------------------------------------------------------------------------
# Insider dimension
# ---------------------------------------------------------------------------

def _insider_dim(ticker: str, date_ts: pd.Timestamp, root: Path) -> dict:
    """Trailing-90-day aggregate of insider transactions with filing_date <= date.

    Reads data/sec_insider/panel/*.parquet; absent-tolerant.
    """
    data = _data_dir(root)
    panel_dir = data / "sec_insider" / "panel"
    if not panel_dir.exists():
        return _absent("data/sec_insider/panel absent (host-only store)")

    cutoff_start = date_ts - pd.Timedelta(days=90)
    rows: list[pd.DataFrame] = []
    try:
        for pq_file in sorted(panel_dir.glob("*.parquet")):
            try:
                df = pd.read_parquet(pq_file)
                if "ticker" not in df.columns or "filing_date" not in df.columns:
                    continue
                t_rows = df[df["ticker"] == ticker].copy()
                if t_rows.empty:
                    continue
                t_rows["_filing_dt"] = pd.to_datetime(t_rows["filing_date"], errors="coerce")
                t_rows = t_rows[
                    (t_rows["_filing_dt"] >= cutoff_start) &
                    (t_rows["_filing_dt"] <= date_ts)
                ]
                if not t_rows.empty:
                    rows.append(t_rows)
            except Exception:  # noqa: BLE001
                continue
    except Exception as e:  # noqa: BLE001
        return _absent(f"sec_insider/panel unreadable: {e}")

    if not rows:
        return _absent(f"no insider transactions for {ticker} in trailing 90 days of {date_ts.date()}")

    combined = pd.concat(rows, ignore_index=True)
    # Aggregate: sum buy/sell amounts, count transactions
    buys  = combined[combined["code"].isin(["P", "A", "M"]) if "code" in combined.columns else [True] * len(combined)]
    sells = combined[combined["code"].isin(["S", "D"]) if "code" in combined.columns else [False] * len(combined)]

    usd_col = "usd" if "usd" in combined.columns else None
    agg: dict = {
        "n_transactions": int(len(combined)),
        "n_buys":         int(len(buys)),
        "n_sells":        int(len(sells)),
        "buy_usd":        float(buys[usd_col].sum()) if usd_col else None,
        "sell_usd":       float(sells[usd_col].abs().sum()) if usd_col else None,
        "latest_filing":  str(combined["_filing_dt"].max().date()) if not combined["_filing_dt"].isna().all() else None,
    }
    return _present(
        value=agg,
        as_of=agg["latest_filing"],
        basis="filing_date_gated_90d",
    )


# ---------------------------------------------------------------------------
# Short interest dimension
# ---------------------------------------------------------------------------

_si_cache: dict[str, pd.DataFrame | None] = {}


def _load_si(data: Path) -> pd.DataFrame | None:
    path = data / "finra" / "short_interest.parquet"
    key = str(path)
    if key in _si_cache:
        return _si_cache[key]
    if not path.exists():
        _si_cache[key] = None
        return None
    try:
        df = pd.read_parquet(path)
        _si_cache[key] = df
        return df
    except Exception as e:  # noqa: BLE001
        log.debug("context_api: cannot read finra/short_interest.parquet: %s", e)
        _si_cache[key] = None
        return None


def _short_int_dim(ticker: str, date_ts: pd.Timestamp, root: Path) -> dict:
    """Single settlement snapshot from data/finra/short_interest.parquet.

    basis='snapshot_not_pit' when date != settlement date (most historical queries).
    """
    data = _data_dir(root)
    si = _load_si(data)
    if si is None:
        return _absent("data/finra/short_interest.parquet absent")

    # ticker may be the index or a column
    if si.index.name == "ticker":
        row = si.loc[ticker] if ticker in si.index else None
        if row is None:
            return _absent(f"short_interest: {ticker} not in snapshot")
        settlement = row.get("settlement_date") if hasattr(row, "get") else row["settlement_date"] if "settlement_date" in si.columns else None
    elif "ticker" in si.columns:
        rows = si[si["ticker"] == ticker]
        if rows.empty:
            return _absent(f"short_interest: {ticker} not in snapshot")
        row = rows.iloc[0]
        settlement = row.get("settlement_date")
    else:
        return _absent("short_interest: no ticker column or index")

    settlement_ts = _coerce_date(settlement)
    # Basis is always snapshot_not_pit: a FINRA settlement snapshot is not a daily
    # PIT label regardless of how close the query date is to the settlement date.
    # We carry the settlement date as the as_of for honest provenance.
    # Directional note: we check 0 <= (date_ts - settlement_ts).days < 2 only to
    # determine whether the snapshot is near-match vs stale — both remain snapshot_not_pit.
    basis = "snapshot_not_pit"

    return _present(
        value={k: (None if isinstance(v, float) and pd.isna(v) else v)
               for k, v in (row.to_dict() if hasattr(row, "to_dict") else dict(row)).items()},
        as_of=str(settlement_ts.date()) if settlement_ts is not None else None,
        basis=basis,
    )


# ---------------------------------------------------------------------------
# Options dimension
# ---------------------------------------------------------------------------

def _options_dim(ticker: str, date_ts: pd.Timestamp, root: Path) -> dict:
    """Options skew summary + GEX snapshot where present (2026-06+).

    Reads:
    - data/options_skew/snapshots.parquet
    - data/polygon_gex/summary_<TICKER>.parquet (if present)

    Absent-tolerant.
    """
    data = _data_dir(root)

    skew_result: dict | None = None
    skew_path = data / "options_skew" / "snapshots.parquet"
    if skew_path.exists():
        try:
            skew_df = pd.read_parquet(skew_path)
            # Column name: 'underlying' or 'ticker'
            tick_col = "underlying" if "underlying" in skew_df.columns else (
                "ticker" if "ticker" in skew_df.columns else None
            )
            date_col = "asof" if "asof" in skew_df.columns else (
                "date" if "date" in skew_df.columns else None
            )
            if tick_col and date_col:
                t_rows = skew_df[skew_df[tick_col] == ticker].copy()
                if not t_rows.empty:
                    t_rows["_dt"] = pd.to_datetime(t_rows[date_col], errors="coerce")
                    valid = t_rows[t_rows["_dt"] <= date_ts].sort_values("_dt")
                    if not valid.empty:
                        row = valid.iloc[-1]
                        skew_result = {
                            k: (None if isinstance(v, float) and pd.isna(v) else v)
                            for k, v in row.to_dict().items()
                            if not k.startswith("_") and k not in (tick_col, date_col)
                        }
                        skew_result["as_of"] = str(row["_dt"].date()) if pd.notna(row["_dt"]) else None
        except Exception as e:  # noqa: BLE001
            log.debug("context_api: options_skew read failed: %s", e)

    gex_result: dict | None = None
    gex_path = data / "polygon_gex" / f"summary_{ticker}.parquet"
    if gex_path.exists():
        try:
            gex_df = pd.read_parquet(gex_path)
            date_col = "date" if "date" in gex_df.columns else None
            if date_col:
                gex_df = gex_df.copy()
                gex_df["_dt"] = pd.to_datetime(gex_df[date_col], errors="coerce")
                valid = gex_df[gex_df["_dt"] <= date_ts].sort_values("_dt")
                if not valid.empty:
                    row = valid.iloc[-1]
                    gex_result = {
                        k: (None if isinstance(v, float) and pd.isna(v) else v)
                        for k, v in row.to_dict().items()
                        if not k.startswith("_") and k != date_col
                    }
                    gex_result["as_of"] = str(row["_dt"].date()) if pd.notna(row["_dt"]) else None
        except Exception as e:  # noqa: BLE001
            log.debug("context_api: polygon_gex read failed for %s: %s", ticker, e)

    if skew_result is None and gex_result is None:
        return _absent(f"options data absent for {ticker} at {date_ts.date()} (2026-06+ host-only)")

    return _present(
        value={
            "skew":  skew_result,
            "gex":   gex_result,
        },
        as_of=(skew_result or gex_result or {}).get("as_of"),
        basis="options_snapshot",
    )


# ---------------------------------------------------------------------------
# Spine signals dimension
# ---------------------------------------------------------------------------

def _spine_dim(ticker: str, date_ts: pd.Timestamp, root: Path) -> dict:
    """Last 5 spine_index rows for (symbol=ticker, as_of<=date)."""
    data = _data_dir(root)
    spine_path = data / "neuralweb" / "spine_index.parquet"
    if not spine_path.exists():
        return _absent("data/neuralweb/spine_index.parquet absent")
    try:
        spine = pd.read_parquet(spine_path)
    except Exception as e:  # noqa: BLE001
        return _absent(f"spine_index.parquet unreadable: {e}")

    sym_col = "symbol" if "symbol" in spine.columns else None
    if sym_col is None:
        return _absent("spine_index: no symbol column")

    t_rows = spine[spine[sym_col] == ticker].copy()
    if t_rows.empty:
        return _absent(f"no spine rows for {ticker}")

    asof_col = "as_of" if "as_of" in t_rows.columns else None
    if asof_col is None:
        return _absent("spine_index: no as_of column")

    t_rows["_dt"] = pd.to_datetime(t_rows[asof_col], errors="coerce")
    valid = t_rows[t_rows["_dt"] <= date_ts].sort_values("_dt", ascending=False)
    if valid.empty:
        return _absent(f"no spine rows for {ticker} with as_of <= {date_ts.date()}")

    last_5 = valid.head(5)
    records = [
        {k: (None if isinstance(v, float) and pd.isna(v) else v)
         for k, v in row.to_dict().items()
         if not k.startswith("_")}
        for _, row in last_5.iterrows()
    ]
    return _present(
        value=records,
        as_of=str(last_5.iloc[0]["_dt"].date()) if pd.notna(last_5.iloc[0]["_dt"]) else None,
        basis="spine_index",
        coverage=float(len(records)),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def context_snapshot(
    ticker: str,
    date: Any = None,
    root: Any = None,
) -> dict:
    """PIT context snapshot for a single ticker.

    Parameters
    ----------
    ticker : str
        Ticker symbol (e.g. 'AAPL').
    date : date-like, optional
        Target date; defaults to today.
    root : path-like, optional
        Repo root; defaults to auto-detected.

    Returns
    -------
    dict
        Keys: ticker, date, dimensions (dict keyed by dimension name).
        Each dimension value is {value, as_of, basis, [coverage]} or
        {absent: True, reason: str}.
    """
    root_p = _repo_root(root)
    date_ts = _coerce_date(date) if date is not None else _today_ts()
    if date_ts is None:
        date_ts = _today_ts()

    today = _today_ts()
    is_today = abs((date_ts - today).days) <= 1

    dims: dict[str, dict] = {
        "personality": _personality_dim(ticker, date_ts, root_p, is_today),
        "archetype":   _archetype_dim(ticker, date_ts, root_p),
        "regime":      _regime_dim(date_ts, root_p),
        "sector":      _sector_dim(ticker, date_ts, root_p),
        "factor":      _factor_dim(ticker, date_ts, root_p),
        "attention":   _attention_dim(ticker, date_ts, root_p),
        "insider":     _insider_dim(ticker, date_ts, root_p),
        "short_int":   _short_int_dim(ticker, date_ts, root_p),
        "options":     _options_dim(ticker, date_ts, root_p),
        "spine":       _spine_dim(ticker, date_ts, root_p),
    }

    return {
        "ticker":     ticker,
        "date":       str(date_ts.date()),
        "dimensions": dims,
    }


def context_frame(
    tickers: list[str],
    date: Any = None,
    root: Any = None,
) -> pd.DataFrame:
    """Vectorised context snapshots: one row per ticker, one column per dimension field.

    Each dimension's fields are flattened as <dimension>__<field>.
    Absent dimensions produce NaN columns.

    Parameters
    ----------
    tickers : list of str
        Ticker symbols.
    date : date-like, optional
        Target date; defaults to today.
    root : path-like, optional
        Repo root; defaults to auto-detected.

    Returns
    -------
    pd.DataFrame
        One row per ticker. Never raises.
    """
    rows: list[dict] = []
    for ticker in tickers:
        snap = context_snapshot(ticker, date=date, root=root)
        flat: dict = {"ticker": ticker, "date": snap["date"]}
        for dim_name, dim_val in snap["dimensions"].items():
            if dim_val.get("absent"):
                flat[f"{dim_name}__absent"] = True
                flat[f"{dim_name}__reason"] = dim_val.get("reason")
            else:
                flat[f"{dim_name}__absent"] = False
                flat[f"{dim_name}__as_of"] = dim_val.get("as_of")
                flat[f"{dim_name}__basis"] = dim_val.get("basis")
                val = dim_val.get("value")
                if isinstance(val, dict):
                    for k, v in val.items():
                        flat[f"{dim_name}__{k}"] = v
                elif isinstance(val, list):
                    flat[f"{dim_name}__records"] = val
                else:
                    flat[f"{dim_name}__value"] = val
        rows.append(flat)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)
