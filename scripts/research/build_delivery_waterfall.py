"""Fundamental Delivery Waterfall — off-render one-shot builder.

Program: Long-Hold Thesis lobe — LHB-W1 (A3 Delivery Waterfall).
Adjudication: research/LONG_HOLD_LOBE_BRAINSTORM_ADJUDICATION_BY_FABLE.md §LHB-R4.

Loads winner_episodes.parquet (Detector-D episodes), reuses the price loaders
from scripts.research.build_winner_autopsy (read-only; does NOT write any
winner-autopsy file), and calls engine.delivery_waterfall.compute_waterfall()
for each episode.

Outputs (this script is the sole writer of both):
  data/research/delivery_waterfall.parquet       — one row per (ticker, t0)
  data/research/delivery_waterfall_panel.json    — admin display slice

FIREWALL: horizon_role=hold_thesis.  These artifacts MUST NOT feed board
ordering, alert triage, top-setups gates, or push floor (LHB-R4 / LH-R1).
No outcome-label-conditioned aggregates of waterfall legs are produced —
counts and per-episode receipts only (WA-R7 fence).

CRITICAL: This script reads parquet — exit via lib.procutil.hard_exit()
to avoid Arrow ThreadPool static-destructor deadlock (#2196).

Usage:
    python scripts/research/build_delivery_waterfall.py
    python scripts/research/build_delivery_waterfall.py --smoke
    python scripts/research/build_delivery_waterfall.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Repo root bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lib import config  # noqa: E402
from lib.procutil import hard_exit  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paths (all via config.data_dir() — env-overridable)
# ---------------------------------------------------------------------------

def _data() -> Path:
    return config.data_dir()


def _episodes_path() -> Path:
    return _data() / "research" / "winner_episodes.parquet"


def _statements_path() -> Path:
    return _data() / "edgar" / "statements.parquet"


def _out_parquet() -> Path:
    return _data() / "research" / "delivery_waterfall.parquet"


def _out_panel() -> Path:
    return _data() / "research" / "delivery_waterfall_panel.json"


# ---------------------------------------------------------------------------
# Price loaders — READ-ONLY reuse from build_winner_autopsy
# (sole-writer law: known_extra_writers: [] — we never write winner-autopsy files)
# ---------------------------------------------------------------------------

def _import_price_loaders():
    """Import private loaders from build_winner_autopsy.  Read-only use only."""
    from scripts.research.build_winner_autopsy import (  # noqa: PLC0415
        _load_yahoo_bars,
        _load_massive_bars,
        _load_dead_name_bars,
        _merge_bars,
        _find_massive_dir,
    )
    return _load_yahoo_bars, _load_massive_bars, _load_dead_name_bars, _merge_bars, _find_massive_dir


def _load_prices(smoke: bool) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """Load and merge price bars.  Returns (bars, source_map)."""
    (
        _load_yahoo_bars,
        _load_massive_bars,
        _load_dead_name_bars,
        _merge_bars,
        _find_massive_dir,
    ) = _import_price_loaders()

    smoke_limit = 200 if smoke else None
    yahoo_bars = _load_yahoo_bars(smoke_limit=smoke_limit)
    massive_dir = _find_massive_dir()
    massive_bars = _load_massive_bars(massive_dir) if massive_dir else {}
    dead_bars = _load_dead_name_bars()
    bars, source_map = _merge_bars(yahoo_bars, massive_bars, dead_bars)
    return bars, source_map


# ---------------------------------------------------------------------------
# Episode loading
# ---------------------------------------------------------------------------

def _load_episodes(smoke: bool) -> pd.DataFrame | None:
    """Load winner_episodes.parquet.  Returns None on any error."""
    path = _episodes_path()
    if not path.exists():
        log.warning("winner_episodes not found: %s", path)
        return None
    try:
        df = pd.read_parquet(path)
        if df.empty:
            log.warning("winner_episodes is empty")
            return None
        # Natural key is (ticker, t0) — reset_index so we can iterate rows
        if "ticker" not in df.columns or "t0" not in df.columns:
            log.warning("winner_episodes missing ticker or t0 columns")
            return None
        df = df.reset_index(drop=True)
        df["t0"] = pd.to_datetime(df["t0"])
        if smoke:
            df = df.iloc[:200].copy()
            log.info("--smoke: using first %d episodes", len(df))
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("winner_episodes load fail: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Statements loading
# ---------------------------------------------------------------------------

def _load_statements() -> dict[str, pd.DataFrame]:
    """Load statements.parquet grouped by ticker.  Returns {} on error."""
    path = _statements_path()
    if not path.exists():
        log.warning("statements.parquet not found: %s", path)
        return {}
    try:
        df = pd.read_parquet(path)
        if df.empty or "ticker" not in df.columns:
            return {}
        result: dict[str, pd.DataFrame] = {}
        for ticker, grp in df.groupby("ticker"):
            result[str(ticker)] = grp.reset_index(drop=True)
        log.info("Loaded statements for %d tickers", len(result))
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("statements load fail: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Row flattener
# ---------------------------------------------------------------------------

def _flatten_row(r: dict) -> dict:
    """Flatten nested legs/legs_pct/raw dicts into a single row dict."""
    flat: dict = {}
    for k, v in r.items():
        if k in ("legs", "legs_pct", "raw") and isinstance(v, dict):
            prefix = k
            for sub_k, sub_v in v.items():
                flat[f"{prefix}__{sub_k}"] = sub_v
        elif k in ("refusal_reasons", "warnings") and isinstance(v, list):
            flat[k] = json.dumps(v)
        else:
            flat[k] = v
    return flat


# ---------------------------------------------------------------------------
# Panel JSON builder
# ---------------------------------------------------------------------------

def _build_panel(
    rows: list[dict],
    as_of: str,
    generated_at: str,
) -> dict:
    """Build the admin display panel JSON from compute_waterfall result dicts.

    WA-R7 + adjudication: NO outcome-label-conditioned aggregates of waterfall
    legs.  We never compute "median residual for durable_winner" or any similar
    grouping.  Counts and per-episode receipts ONLY.
    """
    n_episodes = len(rows)
    n_ok = sum(1 for r in rows if r.get("status") == "ok")
    n_refused = sum(1 for r in rows if r.get("status") == "refused")

    # Refusal reason breakdown
    by_refusal: dict[str, int] = Counter()
    for r in rows:
        if r.get("status") == "refused":
            reasons = r.get("refusal_reasons") or []
            if isinstance(reasons, str):
                try:
                    reasons = json.loads(reasons)
                except Exception:  # noqa: BLE001
                    reasons = [reasons]
            for reason in reasons:
                by_refusal[str(reason)] += 1

    # Path breakdown
    by_path: dict[str, int] = Counter()
    for r in rows:
        p = r.get("path")
        by_path[str(p) if p is not None else "null"] += 1

    # Display rows: ok-status, t0 >= 2023-01-01, newest first, capped at 80
    cutoff_t0 = pd.Timestamp("2023-01-01")
    display_rows = []
    for r in rows:
        if r.get("status") != "ok":
            continue
        try:
            t0_ts = pd.Timestamp(r.get("t0", ""))
        except Exception:  # noqa: BLE001
            continue
        if t0_ts < cutoff_t0:
            continue
        display_rows.append(r)
    display_rows.sort(key=lambda r: r.get("t0", ""), reverse=True)
    display_rows = display_rows[:80]

    panel_display_rows = []
    for r in display_rows:
        legs_pct = r.get("legs_pct") or {}
        if isinstance(legs_pct, str):
            try:
                legs_pct = json.loads(legs_pct)
            except Exception:  # noqa: BLE001
                legs_pct = {}
        warnings = r.get("warnings") or []
        if isinstance(warnings, str):
            try:
                warnings = json.loads(warnings)
            except Exception:  # noqa: BLE001
                warnings = []
        panel_display_rows.append({
            "ticker": r.get("ticker"),
            "t0": r.get("t0"),
            "path": r.get("path"),
            "dlog_price": r.get("dlog_price"),
            "legs_pct": legs_pct,
            "warnings": warnings,
            "price_source": r.get("price_source"),
            "basis_mismatch": r.get("basis_mismatch"),
        })

    # Refused examples: 10 most recent refused rows
    refused_rows = [r for r in rows if r.get("status") == "refused"]
    refused_rows.sort(key=lambda r: r.get("t0", ""), reverse=True)
    refused_examples = []
    for r in refused_rows[:10]:
        reasons = r.get("refusal_reasons") or []
        if isinstance(reasons, str):
            try:
                reasons = json.loads(reasons)
            except Exception:  # noqa: BLE001
                reasons = [reasons]
        refused_examples.append({
            "ticker": r.get("ticker"),
            "t0": r.get("t0"),
            "refusal_reasons": reasons,
        })

    return {
        "schema": "delivery_waterfall_panel.v1",
        "generated_at": generated_at,
        "as_of": as_of,
        "counts": {
            "n_episodes": n_episodes,
            "n_ok": n_ok,
            "n_refused": n_refused,
            "by_refusal_reason": dict(by_refusal),
            "by_path": dict(by_path),
        },
        "coverage_notes": [
            "display-only; MUST NOT feed board ordering, alert triage, top-setups, or push floor",
            "LHB-R4: refusal-first — raw components returned even on refusal",
            "no outcome-label aggregates: per-episode receipts only (WA-R7 + adjudication)",
            "split guard: share-count change >20% between endpoints triggers refusal",
        ],
        "rows": panel_display_rows,
        "refused_examples": refused_examples,
        "_display_only": True,
        "_horizon_role": "hold_thesis",
        "_version": "v1",
    }


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Build delivery_waterfall artifacts.")
    parser.add_argument("--smoke", action="store_true",
                        help="First 200 episodes only (fast smoke-test).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute but do not write output files.")
    args = parser.parse_args()

    t0_total = time.time()

    # Import the pure engine here (not at module level — keeps import sanity clean)
    from engine.delivery_waterfall import compute_waterfall  # noqa: PLC0415

    # ------------------------------------------------------------------
    # 1. Load episodes
    # ------------------------------------------------------------------
    log.info("Loading winner_episodes...")
    episodes_df = _load_episodes(smoke=args.smoke)
    if episodes_df is None:
        log.error("No episodes found — aborting.")
        return 1

    n_episodes_loaded = len(episodes_df)
    log.info("Loaded %d episodes", n_episodes_loaded)

    # ------------------------------------------------------------------
    # 2. Load prices
    # ------------------------------------------------------------------
    log.info("Loading prices...")
    bars, source_map = _load_prices(smoke=args.smoke)
    log.info("Loaded price bars for %d tickers", len(bars))

    # ------------------------------------------------------------------
    # 3. Load statements grouped by ticker
    # ------------------------------------------------------------------
    log.info("Loading statements...")
    stmt_by_ticker = _load_statements()

    # ------------------------------------------------------------------
    # 4. Compute waterfall for each episode
    # ------------------------------------------------------------------
    result_rows: list[dict] = []
    n_ok = 0
    n_refused = 0

    # Honesty-stamp columns to propagate from episodes (if present)
    _HONESTY_COLS = [
        "price_source", "basis_mismatch", "survivorship_biased", "gap_leg_crossed",
    ]

    for _, ep in episodes_df.iterrows():
        ticker = str(ep.get("ticker", ""))
        t0 = ep.get("t0")
        if not ticker or pd.isna(t0):
            continue

        # Get close series for ticker
        close_df = bars.get(ticker)
        if close_df is not None and "close" in close_df.columns:
            close_series = close_df["close"].dropna().sort_index()
        else:
            close_series = pd.Series(dtype=float)

        # Get statement rows for ticker
        stmt_df = stmt_by_ticker.get(ticker, pd.DataFrame())

        try:
            result = compute_waterfall(
                ticker=ticker,
                t0=t0,
                close=close_series,
                stmt_rows=stmt_df,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("compute_waterfall failed for %s t0=%s: %s", ticker, t0, exc)
            result = {
                "ticker": ticker,
                "t0": pd.Timestamp(t0).date().isoformat(),
                "as_of": None,
                "path": None,
                "status": "refused",
                "refusal_reasons": json.dumps(["compute_error"]),
                "warnings": json.dumps([str(exc)[:120]]),
                "dlog_price": None,
                "legs": {},
                "legs_pct": {},
                "raw": {},
                "anchor_lag_days": None,
                "_display_only": True,
                "_horizon_role": "hold_thesis",
                "_version": "v1",
                "_schema": "delivery_waterfall.v1",
            }

        # Propagate honesty stamps from the episode row
        for col in _HONESTY_COLS:
            val = ep.get(col)
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                result[col] = val

        if result.get("status") == "ok":
            n_ok += 1
        else:
            n_refused += 1

        result_rows.append(result)

    # ------------------------------------------------------------------
    # 5. Build outputs
    # ------------------------------------------------------------------
    generated_at = datetime.now(timezone.utc).isoformat()
    as_of_str = (
        pd.Timestamp.now().date().isoformat()
    )

    panel_dict = _build_panel(result_rows, as_of=as_of_str, generated_at=generated_at)

    # Summary
    top_reasons = sorted(
        panel_dict["counts"]["by_refusal_reason"].items(),
        key=lambda x: x[1],
        reverse=True,
    )
    print("=== DELIVERY WATERFALL ===")
    print(f"  episodes : {len(result_rows)}")
    print(f"  ok       : {n_ok}")
    print(f"  refused  : {n_refused}")
    print("  top refusal reasons:")
    for reason, cnt in top_reasons[:6]:
        print(f"    {reason}: {cnt}")
    print(f"  elapsed  : {time.time() - t0_total:.1f}s")

    if args.dry_run:
        log.info("--dry-run: skipping file writes.")
        return 0

    # ------------------------------------------------------------------
    # 6. Write parquet
    # ------------------------------------------------------------------
    flat_rows = [_flatten_row(r) for r in result_rows]
    out_df = pd.DataFrame(flat_rows)
    out_path_parquet = _out_parquet()
    out_path_parquet.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(out_path_parquet, index=False)
    log.info("Wrote %s (%d rows)", out_path_parquet, len(out_df))

    # ------------------------------------------------------------------
    # 7. Write panel JSON
    # ------------------------------------------------------------------
    out_path_panel = _out_panel()
    panel_bytes = json.dumps(panel_dict, indent=2, default=str)
    out_path_panel.write_text(panel_bytes)
    log.info("Wrote %s (%d bytes)", out_path_panel, len(panel_bytes))

    return 0


if __name__ == "__main__":
    hard_exit(main())
