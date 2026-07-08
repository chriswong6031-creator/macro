"""collectors/yf_analyst.py — US analyst price-target + rating collector (free yfinance).

DESIGN
------
Fetches yfinance .info fields for the NW candidate universe (~250 names drawn
from the same standouts ∪ altdata ∪ radar sources that mastermind_context.py
uses) and writes data/analyst/targets.parquet.

AUTHORITY CONTRACT
------------------
This artifact is DISPLAY/CONTEXT ONLY. Analyst targets are PIT-snapshot data —
yfinance .info returns the current consensus at fetch time; there is no
historical series. Every row carries provenance_note='yfinance_info_pit_snapshot'
so downstream consumers understand the point-in-time nature.

EPISTEMICS
----------
- allowed_behavior: annotate_only
- No field may feed board_rank, eq_score, position_sizing, or any scored surface.
- Analyst RATING is descriptive context (not an origination).
- 'validated' is never used in any text field.

RATE-LIMIT POLICY
-----------------
- workers <= 2  (single-threaded by default, --workers 2 maximum)
- delay 1-3 seconds jitter between fetches
- graceful per-ticker failure (401/429 → honest-null row, not abort)
- incremental (--stale-days N): skips tickers with a fresh row already in parquet
- never runs in the render path — builder reads the committed parquet

COLUMNS
-------
ticker, target_mean, target_high, target_low, implied_upside_pct,
target_dispersion, recommendation, num_analysts, current_price, as_of,
provenance_note

USAGE
-----
  python -m collectors.yf_analyst               # fetch stale names (default: --stale-days 2)
  python -m collectors.yf_analyst --stale-days 7
  python -m collectors.yf_analyst --dry-run 5   # fetch first 5 tickers, print, no write
  python -m collectors.yf_analyst --workers 2   # parallel (max 2)
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ── Output path ──────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
_OUT_PATH = _REPO_ROOT / "data" / "analyst" / "targets.parquet"

# ── Rate-limit policy ─────────────────────────────────────────────────────────
_DELAY_MIN_S = 1.0
_DELAY_MAX_S = 3.0
_MAX_WORKERS = 2  # absolute cap — never exceed 2

# ── Provenance tag ────────────────────────────────────────────────────────────
_PROVENANCE = "yfinance_info_pit_snapshot"

# ── yfinance .info fields we need ─────────────────────────────────────────────
_YF_TARGET_MEAN    = "targetMeanPrice"
_YF_TARGET_HIGH    = "targetHighPrice"
_YF_TARGET_LOW     = "targetLowPrice"
_YF_RECOMMEND_KEY  = "recommendationKey"
_YF_NUM_ANALYSTS   = "numberOfAnalystOpinions"
_YF_CURRENT_PRICE  = "currentPrice"

# Column schema (order is stable)
_COLUMNS = [
    "ticker",
    "target_mean",
    "target_high",
    "target_low",
    "implied_upside_pct",
    "target_dispersion",
    "recommendation",
    "num_analysts",
    "current_price",
    "as_of",
    "provenance_note",
]


# ── Candidate universe ────────────────────────────────────────────────────────

def _load_candidate_universe(repo: Path) -> list[str]:
    """Mirror the mastermind_context.py candidate universe derivation.

    Returns sorted list of tickers: standouts (buy/watch/laggards) ∪
    altdata/mastermind (signals + broken_signals) ∪ radar_ticker (all tickers
    listed, unfiltered — we fetch targets for all even if their NW context
    is WATCH-only, because analyst targets have negligible cost and the
    builder applies the actionable filter at read time).

    Capped at 250 names to stay within rate-limit budget. Fails open on any
    read error (uses whatever subset is available).
    """
    tickers: set[str] = set()

    # Standouts
    standouts_path = repo / "site" / "factordata" / "us_standouts.json"
    try:
        if standouts_path.exists():
            ss = json.loads(standouts_path.read_text(encoding="utf-8"))
            if isinstance(ss, dict):
                for key in ("buy", "watch", "laggards"):
                    lst = ss.get(key) or []
                    for item in lst:
                        t = item.get("ticker") if isinstance(item, dict) else str(item)
                        if t:
                            tickers.add(t)
    except Exception as exc:  # noqa: BLE001
        log.warning("yf_analyst: standouts read failed — %s", exc)

    # Altdata mastermind
    altdata_path = repo / "site" / "altdata" / "mastermind.json"
    try:
        if altdata_path.exists():
            am = json.loads(altdata_path.read_text(encoding="utf-8"))
            if isinstance(am, dict):
                for key in ("signals", "broken_signals"):
                    lst = am.get(key) or []
                    for item in lst:
                        if isinstance(item, dict):
                            t = item.get("ticker") or item.get("symbol")
                            if t:
                                tickers.add(t)
    except Exception as exc:  # noqa: BLE001
        log.warning("yf_analyst: altdata read failed — %s", exc)

    # Radar tickers (all listed, actionability filter is in the builder)
    radar_path = repo / "site" / "basketdata" / "radar_ticker.json"
    try:
        if radar_path.exists():
            rt = json.loads(radar_path.read_text(encoding="utf-8"))
            if isinstance(rt, dict):
                for item in (rt.get("tickers") or []):
                    t = item.get("ticker") if isinstance(item, dict) else None
                    if t:
                        tickers.add(t)
    except Exception as exc:  # noqa: BLE001
        log.warning("yf_analyst: radar_ticker read failed — %s", exc)

    result = sorted(tickers)[:250]
    log.info("yf_analyst: candidate universe = %d tickers", len(result))
    return result


# ── Staleness check ───────────────────────────────────────────────────────────

def _load_existing(path: Path) -> pd.DataFrame | None:
    """Load existing parquet; return None on any failure."""
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        log.warning("yf_analyst: cannot read existing parquet — %s", exc)
        return None


def _stale_tickers(
    all_tickers: list[str],
    existing: pd.DataFrame | None,
    stale_days: int,
) -> list[str]:
    """Return tickers that need refreshing (absent or older than stale_days)."""
    if existing is None or existing.empty or "ticker" not in existing.columns:
        return all_tickers

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if "as_of" in existing.columns:
        fresh = set(
            existing.loc[
                existing["as_of"] >= _days_ago_str(stale_days),
                "ticker",
            ].tolist()
        )
    else:
        fresh = set()

    return [t for t in all_tickers if t not in fresh]


def _days_ago_str(days: int) -> str:
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return cutoff.strftime("%Y-%m-%d")


# ── Per-ticker fetch ──────────────────────────────────────────────────────────

def _fetch_one(ticker: str, as_of: str) -> dict[str, Any]:
    """Fetch yfinance .info for one ticker. Returns an honest-null row on any failure."""
    row: dict[str, Any] = {
        "ticker": ticker,
        "target_mean": None,
        "target_high": None,
        "target_low": None,
        "implied_upside_pct": None,
        "target_dispersion": None,
        "recommendation": None,
        "num_analysts": None,
        "current_price": None,
        "as_of": as_of,
        "provenance_note": _PROVENANCE,
    }
    try:
        import yfinance as yf  # noqa: PLC0415
        info = yf.Ticker(ticker).info or {}

        target_mean    = info.get(_YF_TARGET_MEAN)
        target_high    = info.get(_YF_TARGET_HIGH)
        target_low     = info.get(_YF_TARGET_LOW)
        recommend_key  = info.get(_YF_RECOMMEND_KEY)
        num_analysts   = info.get(_YF_NUM_ANALYSTS)
        current_price  = info.get(_YF_CURRENT_PRICE)

        # Coerce to float / None
        def _f(v: Any) -> float | None:
            if v is None:
                return None
            try:
                fv = float(v)
                return None if (math.isnan(fv) or math.isinf(fv)) else fv
            except (TypeError, ValueError):
                return None

        target_mean   = _f(target_mean)
        target_high   = _f(target_high)
        target_low    = _f(target_low)
        current_price = _f(current_price)
        num_analysts  = int(num_analysts) if num_analysts is not None else None

        # Compute upstream metrics (guard zero/negative denominators)
        implied_upside_pct: float | None = None
        if target_mean is not None and current_price is not None and current_price > 0:
            implied_upside_pct = round(
                (target_mean - current_price) / current_price * 100.0, 2
            )

        target_dispersion: float | None = None
        if (
            target_high is not None
            and target_low is not None
            and target_mean is not None
            and target_mean > 0
        ):
            target_dispersion = round(
                (target_high - target_low) / target_mean, 4
            )

        row.update({
            "target_mean":          target_mean,
            "target_high":          target_high,
            "target_low":           target_low,
            "implied_upside_pct":   implied_upside_pct,
            "target_dispersion":    target_dispersion,
            "recommendation":       recommend_key if recommend_key else None,
            "num_analysts":         num_analysts,
            "current_price":        current_price,
        })
        log.debug(
            "yf_analyst: %s → mean=%.2f upside=%.1f%% rec=%s n=%s",
            ticker,
            target_mean or float("nan"),
            implied_upside_pct or float("nan"),
            recommend_key,
            num_analysts,
        )

    except Exception as exc:  # noqa: BLE001
        # 401 / 429 / network errors → honest-null row (all fields stay None)
        err_str = str(exc)
        if "401" in err_str or "429" in err_str:
            log.info("yf_analyst: %s rate-limited (%s) — honest-null row", ticker, exc)
        else:
            log.warning("yf_analyst: %s fetch failed — %s", ticker, exc)

    return row


# ── Writer ─────────────────────────────────────────────────────────────────────

def _upsert_and_write(new_rows: list[dict], existing: pd.DataFrame | None, path: Path) -> None:
    """Merge new rows over existing parquet (keep-LAST per ticker)."""
    new_df = pd.DataFrame(new_rows, columns=_COLUMNS)
    if existing is not None and not existing.empty:
        # Drop old rows for tickers we just refreshed
        refreshed = set(r["ticker"] for r in new_rows)
        old = existing[~existing["ticker"].isin(refreshed)]
        combined = pd.concat([old, new_df], ignore_index=True)
    else:
        combined = new_df

    # Enforce column order + dtypes
    combined = combined[_COLUMNS]
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(path, index=False)
    log.info("yf_analyst: wrote %d rows to %s", len(combined), path)


# ── Main entry point ──────────────────────────────────────────────────────────

def run(
    repo: Path | None = None,
    out_path: Path | None = None,
    stale_days: int = 2,
    workers: int = 1,
    dry_run_n: int = 0,
) -> list[dict]:
    """Run the collector. Returns list of new rows fetched.

    Parameters
    ----------
    repo        : repo root (default: auto-detect from this file)
    out_path    : output parquet path (default: data/analyst/targets.parquet)
    stale_days  : skip tickers with an existing row fresher than this many days
    workers     : number of parallel fetchers (capped at _MAX_WORKERS=2)
    dry_run_n   : if > 0, fetch only first N tickers and return without writing
    """
    repo = repo or _REPO_ROOT
    out_path = out_path or _OUT_PATH
    workers = min(max(1, workers), _MAX_WORKERS)

    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    all_tickers = _load_candidate_universe(repo)
    if not all_tickers:
        log.warning("yf_analyst: empty candidate universe — nothing to fetch")
        return []

    existing = _load_existing(out_path)
    to_fetch = _stale_tickers(all_tickers, existing, stale_days)

    if not to_fetch:
        log.info("yf_analyst: all %d tickers are fresh (stale_days=%d)", len(all_tickers), stale_days)
        return []

    log.info(
        "yf_analyst: fetching %d/%d tickers (stale_days=%d, workers=%d)",
        len(to_fetch), len(all_tickers), stale_days, workers,
    )

    if dry_run_n > 0:
        to_fetch = to_fetch[:dry_run_n]
        log.info("yf_analyst: DRY RUN — limiting to %d tickers", len(to_fetch))

    new_rows: list[dict] = []

    if workers == 1:
        for ticker in to_fetch:
            row = _fetch_one(ticker, as_of)
            new_rows.append(row)
            delay = random.uniform(_DELAY_MIN_S, _DELAY_MAX_S)
            time.sleep(delay)
    else:
        # workers=2 mode: interleave with per-submit delay to avoid bursts
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for i, ticker in enumerate(to_fetch):
                if i > 0:
                    time.sleep(random.uniform(_DELAY_MIN_S / workers, _DELAY_MAX_S / workers))
                fut = pool.submit(_fetch_one, ticker, as_of)
                futures[fut] = ticker
            for fut in as_completed(futures):
                try:
                    row = fut.result()
                    new_rows.append(row)
                except Exception as exc:  # noqa: BLE001
                    log.warning("yf_analyst: future failed for %s — %s", futures[fut], exc)

    if dry_run_n > 0:
        log.info("yf_analyst: DRY RUN results:")
        for r in new_rows:
            log.info("  %s → mean=%s upside=%s rec=%s n_analysts=%s",
                     r["ticker"], r["target_mean"], r["implied_upside_pct"],
                     r["recommendation"], r["num_analysts"])
        return new_rows

    if new_rows:
        _upsert_and_write(new_rows, existing, out_path)
    else:
        log.warning("yf_analyst: no rows fetched")

    return new_rows


# ── CLI ────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fetch yfinance analyst targets for the NW candidate universe"
    )
    p.add_argument(
        "--stale-days", type=int, default=2,
        help="Skip tickers already fetched within this many days (default: 2)",
    )
    p.add_argument(
        "--workers", type=int, default=1,
        help=f"Parallel workers (max {_MAX_WORKERS}, default: 1)",
    )
    p.add_argument(
        "--dry-run", type=int, default=0, dest="dry_run_n",
        metavar="N",
        help="Fetch first N tickers, print results, do NOT write parquet",
    )
    p.add_argument(
        "--out", type=Path, default=None,
        help=f"Output parquet path (default: {_OUT_PATH})",
    )
    p.add_argument(
        "--repo", type=Path, default=None,
        help="Repo root override",
    )
    p.add_argument("--verbose", "-v", action="store_true")
    return p


if __name__ == "__main__":
    import sys
    parser = _build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    rows = run(
        repo=args.repo,
        out_path=args.out,
        stale_days=args.stale_days,
        workers=args.workers,
        dry_run_n=args.dry_run_n,
    )
    if args.dry_run_n:
        import pprint
        pprint.pprint(rows)
    sys.exit(0)
