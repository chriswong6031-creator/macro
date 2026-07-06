"""Long-Hold W1 — Phase-1 dead-name price acquisition via Polygon REST.

Ruled by LH-W1-1 (DEAD_NAME_SPIKE.md Phase-1 plan): acquire post-anchor dead-name
prices via the Polygon REST API (MASSIVE_API_KEY), prioritized as:
  1. 35+ names about to exit the rolling 5-year window (delist 2021-07-06 to 2022-07-05)
  2. 140 honest-OOS-window dead tickers (fired in 2021-07-06 → 2021-10-25)
  3. Remaining post-2021-07-06 dead tickers

Auth: MASSIVE_API_KEY is Polygon-compatible. The collector aliases it to
POLYGON_API_KEY so edgar_deadname_prices._polygon_daily() picks it up.

Output:
  data/edgar/dead_name_prices.parquet  — (ticker, date, close, source)
  data/edgar/_dead_name_coverage.json  — updated coverage manifest
  data/edgar/_dead_name_px_polygon.json — per-ticker fetch log for this pass

Usage:
    python -m scripts.research.fetch_dead_name_prices_polygon
    python -m scripts.research.fetch_dead_name_prices_polygon --max-new 50
    python -m scripts.research.fetch_dead_name_prices_polygon --tickers ATVI TWTR
    python -m scripts.research.fetch_dead_name_prices_polygon --dry-run

The script is RESUMABLE: tickers already in dead_name_prices.parquet (any source)
are skipped unless --force is passed. The per-ticker log tracks attempted/succeeded.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lib import config  # noqa: E402

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
POLYGON_BASE = "https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"
POLYGON_PARAMS = "?adjusted=true&sort=asc&limit=50000&apiKey={key}"

ANCHOR_DATE = "2021-07-06"   # Polygon rolling window start (5-year from today)
EXPIRY_CUTOFF = "2022-07-05"  # Delist <= this → exits REST window in <12 months

# Gap window (massive store gap; mirrors long_hold_label_panel constants)
GAP_START = pd.Timestamp("2021-10-25")
GAP_END = pd.Timestamp("2025-01-02")
OOS_WINDOW_START = pd.Timestamp("2021-07-06")
OOS_WINDOW_END = pd.Timestamp("2021-10-25")

REQUEST_RATE = 2.0   # req/sec (Polygon free tier allows ~5/s; conservative)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _prices_path() -> Path:
    p = config.data_dir() / "edgar" / "dead_name_prices.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _log_path() -> Path:
    return config.data_dir() / "edgar" / "_dead_name_px_polygon.json"


def _coverage_path() -> Path:
    return config.data_dir() / "edgar" / "_dead_name_coverage.json"


# ---------------------------------------------------------------------------
# Polygon fetch (direct; no CIK required)
# ---------------------------------------------------------------------------

def _polygon_key() -> str | None:
    """Resolve Polygon key: POLYGON_API_KEY → MASSIVE_API_KEY → config."""
    key = os.environ.get("POLYGON_API_KEY") or os.environ.get("MASSIVE_API_KEY")
    if key:
        return key
    try:
        cfg = config.load()
        key = (cfg.get("polygon") or {}).get("api_key") or (cfg.get("keys") or {}).get("polygon")
    except Exception:  # noqa: BLE001
        pass
    return key or None


def _polygon_fetch(ticker: str, start: str, end: str, key: str) -> pd.Series | None:
    """Fetch adjusted daily bars from Polygon REST for a ticker, start→end.

    Returns a tz-naive daily close Series (date → close) or None on failure.
    """
    url = (POLYGON_BASE.format(ticker=ticker, start=start, end=end)
           + POLYGON_PARAMS.format(key=key))
    try:
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            log.debug("polygon %s: HTTP %d", ticker, r.status_code)
            return None
        body = r.json()
        results = body.get("results") or []
        if len(results) < 2:
            log.debug("polygon %s: too few bars (%d)", ticker, len(results))
            return None
        s = pd.Series(
            [b["c"] for b in results],
            index=pd.to_datetime([b["t"] for b in results], unit="ms").tz_localize(None),
        )
        return s[~s.index.duplicated(keep="last")].sort_index()
    except Exception as exc:  # noqa: BLE001
        log.debug("polygon %s: %s", ticker, exc)
        return None


# ---------------------------------------------------------------------------
# Dead-universe helpers (does NOT require CIK resolution)
# ---------------------------------------------------------------------------

def _load_pit_membership() -> pd.DataFrame:
    p = config.data_dir() / "breadth" / "sp1500_pit_membership.parquet"
    m = pd.read_parquet(p)
    m["end_date"] = pd.to_datetime(m["end_date"])
    m["start_date"] = pd.to_datetime(m["start_date"])
    return m


def _dead_universe() -> list[str]:
    """Dead-only tickers (never re-listed; end_date present, start_date never null)."""
    m = _load_pit_membership()
    return sorted(set(m[m["end_date"].notna()]["ticker"]) - set(m[m["end_date"].isna()]["ticker"]))


def _post_anchor_dead_tickers(dead: list[str]) -> list[str]:
    """Tickers whose LATEST end_date is >= the Polygon rolling anchor."""
    m = _load_pit_membership()
    dead_m = m[m["ticker"].isin(dead) & m["end_date"].notna()]
    latest = dead_m.groupby("ticker")["end_date"].max()
    return sorted(latest[latest >= pd.Timestamp(ANCHOR_DATE)].index)


def _delist_date_map(tickers: list[str]) -> dict[str, str]:
    """Map ticker → delist_date string for date-range requests."""
    m = _load_pit_membership()
    dead_m = m[m["ticker"].isin(tickers) & m["end_date"].notna()]
    latest = dead_m.groupby("ticker")["end_date"].max()
    return {t: latest[t].strftime("%Y-%m-%d") for t in tickers if t in latest}


def _oos_dead_tickers(dead: list[str]) -> list[str]:
    """Dead tickers that fired in the honest-OOS window (2021-07-06 → 2021-10-25)."""
    fires_path = config.data_dir() / "research" / "gate_fires_baskets.parquet"
    if not fires_path.exists():
        log.warning("gate_fires_baskets.parquet not found; cannot determine OOS dead tickers")
        return []
    fires = pd.read_parquet(fires_path, columns=["ticker", "date"])
    fires["date"] = pd.to_datetime(fires["date"])
    oos = fires[(fires["date"] >= OOS_WINDOW_START) & (fires["date"] <= OOS_WINDOW_END)]
    return sorted(set(oos["ticker"]) & set(dead))


# ---------------------------------------------------------------------------
# Prioritization
# ---------------------------------------------------------------------------

def _build_priority_list(dead: list[str], post_anchor: list[str]) -> list[str]:
    """Return post-anchor dead tickers in priority order per DEAD_NAME_SPIKE.md:
    P1: about to exit rolling window (delist 2021-07-06 → 2022-07-05)
    P2: honest-OOS-window dead tickers not in P1
    P3: remaining post-anchor tickers
    """
    m = _load_pit_membership()
    dead_m = m[m["ticker"].isin(post_anchor) & m["end_date"].notna()]
    latest = dead_m.groupby("ticker")["end_date"].max()

    p1 = sorted(t for t in post_anchor
                if t in latest and latest[t] <= pd.Timestamp(EXPIRY_CUTOFF))
    oos = set(_oos_dead_tickers(dead))
    p2 = sorted(t for t in post_anchor if t in oos and t not in set(p1))
    p3 = sorted(t for t in post_anchor if t not in set(p1) and t not in set(p2))

    log.info(
        "Priority breakdown: P1 (rolling-expiry)=%d, P2 (OOS-honest)=%d, P3 (rest)=%d",
        len(p1), len(p2), len(p3),
    )
    return p1 + p2 + p3


# ---------------------------------------------------------------------------
# Main fetch logic
# ---------------------------------------------------------------------------

def fetch(
    *,
    max_new: int = 418,
    tickers: list[str] | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """Fetch adjusted daily bars for post-anchor dead tickers via Polygon REST.

    Returns a summary dict. Writes parquet + JSON if not dry_run.
    """
    key = _polygon_key()
    if not key:
        log.error(
            "No Polygon key found. Set POLYGON_API_KEY or MASSIVE_API_KEY in env "
            "or source the project .env before running this script."
        )
        return {"error": "no_api_key", "fetched": 0}

    log.info("Polygon key resolved (len=%d)", len(key))

    dead = _dead_universe()
    post_anchor = _post_anchor_dead_tickers(dead)
    log.info("Dead universe: %d tickers; post-anchor: %d", len(dead), len(post_anchor))

    delist_map = _delist_date_map(post_anchor)

    if tickers is not None:
        # Explicit list: validate against post_anchor universe
        todo_ordered = [t for t in tickers if t in set(post_anchor)]
        skipped_not_postanchor = [t for t in tickers if t not in set(post_anchor)]
        if skipped_not_postanchor:
            log.warning(
                "Skipping %d tickers not in post-anchor universe: %s",
                len(skipped_not_postanchor), skipped_not_postanchor,
            )
    else:
        todo_ordered = _build_priority_list(dead, post_anchor)

    # Load existing prices to skip already-fetched tickers
    prices_path = _prices_path()
    existing_df = pd.read_parquet(prices_path) if prices_path.exists() else pd.DataFrame()
    already_have = set(existing_df["ticker"].unique()) if not existing_df.empty else set()
    log.info("Already in parquet: %d tickers", len(already_have))

    # Load per-ticker fetch log
    log_path = _log_path()
    fetch_log: dict = json.loads(log_path.read_text()) if log_path.exists() else {}

    if force:
        todo = todo_ordered[:max_new]
    else:
        todo = [t for t in todo_ordered if t not in already_have][:max_new]

    log.info("Will fetch: %d tickers (cap=%d, force=%s)", len(todo), max_new, force)

    if dry_run:
        log.info("DRY RUN — no requests made")
        return {
            "dry_run": True,
            "todo_count": len(todo),
            "already_have": len(already_have),
            "post_anchor_total": len(post_anchor),
            "todo_sample": todo[:10],
        }

    # --- Fetch loop ---
    new_rows: list[dict] = []
    n_success, n_fail = 0, 0
    now_utc = datetime.now(timezone.utc).isoformat()

    for i, ticker in enumerate(todo):
        delist = delist_map.get(ticker, "2026-12-31")
        s = _polygon_fetch(ticker, ANCHOR_DATE, delist, key)
        time.sleep(1.0 / REQUEST_RATE)

        if s is not None and len(s) >= 2:
            n_success += 1
            fetch_log[ticker] = {
                "at": now_utc,
                "source": "polygon",
                "n": int(len(s)),
                "start": str(s.index[0].date()),
                "end": str(s.index[-1].date()),
            }
            for d, c in s.items():
                new_rows.append({
                    "ticker": ticker,
                    "date": d,
                    "close": float(c),
                    "source": "polygon",
                })
            log.info("[%d/%d] %s: %d bars (%s → %s)",
                     i + 1, len(todo), ticker, len(s),
                     s.index[0].date(), s.index[-1].date())
        else:
            n_fail += 1
            fetch_log[ticker] = {"at": now_utc, "source": None, "n": 0}
            log.warning("[%d/%d] %s: no data from Polygon", i + 1, len(todo), ticker)

    # --- Merge with existing ---
    fresh = pd.DataFrame(new_rows)
    if not fresh.empty:
        # Normalize timestamps to midnight (Polygon API returns ms-UTC which encodes
        # as 04:00:00 for NYSE close date; date-normalize to match massive_stock_day)
        fresh["date"] = pd.to_datetime(fresh["date"].dt.date if hasattr(fresh["date"], "dt") else fresh["date"])
        fresh["date"] = pd.to_datetime(fresh["date"].apply(
            lambda x: x.date() if hasattr(x, "date") else x))
    if not existing_df.empty and not fresh.empty:
        # Replace rows for tickers we just re-fetched (if force)
        existing_df = existing_df[~existing_df["ticker"].isin(fresh["ticker"].unique())]
        prices = pd.concat([existing_df, fresh], ignore_index=True)
    else:
        prices = fresh if not fresh.empty else existing_df

    if not prices.empty:
        prices = prices.sort_values(["ticker", "date"]).reset_index(drop=True)
        prices.to_parquet(prices_path, index=False)
        log.info("Wrote %s: %d rows, %d tickers",
                 prices_path, len(prices), prices["ticker"].nunique())

    # --- Write fetch log ---
    log_path.write_text(json.dumps(fetch_log, indent=1, sort_keys=True))

    # --- Update coverage JSON ---
    n_with_prices = prices["ticker"].nunique() if not prices.empty else 0
    coverage = {
        "schema": "dead_name_coverage.v2",
        "generated_utc": now_utc,
        "n_dead_universe": len(dead),
        "n_cik_resolved": 15,  # unchanged — this script does not resolve CIKs
        "n_with_prices": n_with_prices,
        "price_coverage_frac": round(n_with_prices / len(dead), 4) if dead else 0.0,
        "post_anchor_n": len(post_anchor),
        "post_anchor_fetched": n_success,
        "post_anchor_failed": n_fail,
        "by_source": {"polygon": n_success},
        "note": (
            "Price coverage via Polygon REST (MASSIVE_API_KEY). "
            "Coverage is limited to post-2021-07-06 dead names (~418 tickers). "
            "Pre-2021-07 dead names (665 tickers) are unreachable via Polygon; "
            "they are survivorship-biased and stamped UPPER BOUND in all analyses. "
            "Coverage for 756d gate: need >= 542/1083 (50%); current = "
            f"{n_with_prices}/{len(dead)} ({round(n_with_prices / len(dead) * 100, 1) if dead else 0}%). "
        ),
    }
    _coverage_path().write_text(json.dumps(coverage, indent=1))

    summary = {
        "n_todo": len(todo),
        "n_success": n_success,
        "n_fail": n_fail,
        "n_prices_total_tickers": n_with_prices,
        "coverage_frac": coverage["price_coverage_frac"],
        "post_anchor_total": len(post_anchor),
        "dead_universe_total": len(dead),
    }
    log.info("Done: %s", summary)
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch dead-name prices from Polygon REST (MASSIVE_API_KEY).")
    parser.add_argument("--max-new", type=int, default=418,
                        help="Max new tickers to fetch (default=418 = full post-anchor set)")
    parser.add_argument("--tickers", nargs="*", default=None,
                        help="Explicit ticker list (overrides max-new)")
    parser.add_argument("--force", action="store_true",
                        help="Re-fetch even if already in parquet")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without making requests")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )

    result = fetch(
        max_new=args.max_new,
        tickers=args.tickers,
        force=args.force,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("error") is None else 1


if __name__ == "__main__":
    sys.exit(main())
