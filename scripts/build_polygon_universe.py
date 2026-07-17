"""scripts/build_polygon_universe.py — Polygon reference-universe cache.

Builds data/polygon_universe/reference.parquet: per-ticker GICS sector + USD market cap,
consumed by the charting-app's ingest/build_universe.py to enrich the nightly heatmap
manifest (~8.7k names) with real sector grouping and cap sizing.

SECTOR SOURCES (priority order):
  1. data/breadth/constituents.parquet    — S&P 500 GICS labels (best provenance)
  2. data/baskets/membership.json         — us_sector_* basket labels for other names

MARKET CAP SOURCE:
  Polygon /v3/reference/tickers/{ticker} -> market_cap field.
  Per-ticker rate-limited fetch; checkpointed to survive interruption.
  Rate limit: 5 req/s (free/starter), 50 req/s (pro). We use 5 req/s conservatively.
  The checkpoint is SAME-DAY resume state only: a run interrupted mid-fetch
  resumes where it left off, but a checkpoint from a previous day is discarded
  so market caps are re-fetched fresh (a non-expiring checkpoint froze caps at
  their first-fetch values — the July-2026 frozen-cache bug).

CACHE POLICY:
  Refresh if the parquet is absent OR its `asof` column is >= STALE_DAYS
  calendar days old (default 1 — nightly refresh, ~2 min of rate-limited
  fetches for ~500 names). Freshness is judged from the asof COLUMN, never
  file mtime: CI checkouts rewrite files with mtime = checkout time, so a
  committed months-old cache always looks brand-new by mtime and the rebuild
  short-circuits forever. Same-day re-runs exit immediately (idempotent).
  A --force flag resets the checkpoint and rebuilds from scratch.

DISPLAY-TIER ONLY: this script populates reference data (sector, market cap) for
grouping and tile-sizing. No scoring, no money-path.

OI TIMING LAW: not applicable (reference data only, no options OI).

Usage:
    python -m scripts.build_polygon_universe             # build/refresh cache
    python -m scripts.build_polygon_universe --force     # force rebuild
    python -m scripts.build_polygon_universe --dry-run   # audit without writing

The cache path may be overridden with POLYGON_UNIVERSE_CACHE env var.
The Polygon key is read from POLYGON_API_KEY or MASSIVE_API_KEY (env or
flow-ops-wt/.env via lib.config.secret).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib import config  # noqa: E402

log = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────────────────────────────

STALE_DAYS = 1               # refresh nightly; same-day re-runs no-op (asof-date based)
_RATE_LIMIT_DELAY = 0.22     # 4-5 req/s (conservative for free/starter tier)
_BATCH_LOG = 50              # log progress every N tickers fetched

# GICS sector labels from the us_sector_* baskets (mirrors build_flow_desk.py)
_SECTOR_BASKET_MAP: dict[str, str] = {
    "us_sector_tech":          "Information Technology",
    "us_sector_financials":    "Financials",
    "us_sector_health":        "Health Care",
    "us_sector_discretionary": "Consumer Discretionary",
    "us_sector_comm":          "Communication Services",
    "us_sector_industrials":   "Industrials",
    "us_sector_staples":       "Consumer Staples",
    "us_sector_energy":        "Energy",
    "us_sector_utilities":     "Utilities",
    "us_sector_realestate":    "Real Estate",
    "us_sector_materials":     "Materials",
}


# ── cache path ──────────────────────────────────────────────────────────────────

def _cache_path() -> Path:
    override = os.environ.get("POLYGON_UNIVERSE_CACHE", "")
    if override:
        return Path(override)
    return config.data_dir() / "polygon_universe" / "reference.parquet"


def _checkpoint_path() -> Path:
    return _cache_path().parent / "reference_checkpoint.json"


# ── freshness check ────────────────────────────────────────────────────────────

def is_fresh(p: Path, stale_days: int = STALE_DAYS) -> bool:
    """True if the parquet exists and its newest `asof` date is < stale_days old.

    Judged from the asof COLUMN, never file mtime — on CI runners a checkout
    rewrites files (mtime = checkout time), so mtime can only ever look TOO NEW,
    which silently freezes the committed cache forever. An unreadable file or
    missing/empty asof column counts as stale (rebuild).
    """
    if not p.exists():
        return False
    try:
        asof = pd.read_parquet(p, columns=["asof"])["asof"].dropna()
        if asof.empty:
            return False
        newest = max(date.fromisoformat(str(v)) for v in asof.unique())
    except Exception as e:  # noqa: BLE001
        log.warning("build_polygon_universe: cannot read asof from %s (%s) — treating as stale", p, e)
        return False
    return (date.today() - newest).days < stale_days


# ── GICS sector sources ────────────────────────────────────────────────────────

def _load_sp500_gics() -> dict[str, str]:
    """S&P 500 GICS sectors from data/breadth/constituents.parquet. Best provenance."""
    p = config.data_dir() / "breadth" / "constituents.parquet"
    if not p.exists():
        log.warning("build_polygon_universe: breadth/constituents.parquet not found")
        return {}
    try:
        df = pd.read_parquet(p, columns=["sector"])
        return {str(t): str(sec) for t, sec in df["sector"].items() if pd.notna(sec)}
    except Exception as e:  # noqa: BLE001
        log.warning("build_polygon_universe: failed to load SP500 sectors: %s", e)
        return {}


def _load_basket_gics() -> dict[str, str]:
    """GICS sectors from us_sector_* baskets (covers names outside SP500)."""
    bpath = config.data_dir() / "baskets" / "membership.json"
    if not bpath.exists():
        return {}
    try:
        baskets = json.loads(bpath.read_text()).get("baskets", {})
    except Exception as e:  # noqa: BLE001
        log.warning("build_polygon_universe: baskets load failed: %s", e)
        return {}
    out: dict[str, str] = {}
    for basket_key, sector_label in _SECTOR_BASKET_MAP.items():
        bdata = baskets.get(basket_key, {})
        for m in bdata.get("members", []):
            t = m.get("ticker")
            if t and not m.get("removed"):
                out.setdefault(str(t), sector_label)  # first basket wins
    return out


def build_gics_map() -> dict[str, str]:
    """Merge SP500 (higher authority) + baskets. Returns {ticker: gics_sector}."""
    gics: dict[str, str] = _load_basket_gics()
    # SP500 overrides baskets (better provenance)
    gics.update(_load_sp500_gics())
    log.info("build_polygon_universe: GICS map = %d tickers (SP500+baskets)", len(gics))
    return gics


# ── Polygon market cap fetch ───────────────────────────────────────────────────

def _polygon_key() -> str | None:
    return config.secret("POLYGON_API_KEY") or config.secret("MASSIVE_API_KEY")


def _fetch_mcap(ticker: str, key: str, base_url: str) -> float | None:
    """Fetch market_cap for one ticker from Polygon /v3/reference/tickers/{ticker}.
    Returns None on any failure (caller degrades gracefully)."""
    import urllib.request
    import urllib.error

    # Polygon uses '.' for class-B shares (BRK.B -> BRK.B)
    poly_ticker = ticker.replace("-", ".")
    url = f"{base_url}/v3/reference/tickers/{poly_ticker}?apiKey={key}"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read())
        res = (data or {}).get("results") or {}
        mc = res.get("market_cap")
        return float(mc) if mc is not None else None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None   # not found — normal for non-US/delisted
        log.debug("build_polygon_universe: %s HTTP %d", ticker, e.code)
        return None
    except Exception as e:  # noqa: BLE001
        log.debug("build_polygon_universe: %s fetch error: %s", ticker, e)
        return None


def fetch_mcaps(
    tickers: list[str],
    checkpoint: dict[str, float | None],
    *,
    dry_run: bool = False,
) -> dict[str, float | None]:
    """Fetch market caps for tickers not already in checkpoint.
    Rate-limited (0.22s/request). Returns merged checkpoint + new results.
    checkpoint maps ticker -> market_cap (None = confirmed missing)."""
    key = _polygon_key()
    if not key:
        log.warning("build_polygon_universe: no Polygon key (POLYGON_API_KEY / MASSIVE_API_KEY)")
        return checkpoint

    cfg = config.load()
    base_url = cfg.get("polygon", {}).get("base_url", "https://api.polygon.io").rstrip("/")

    pending = [t for t in tickers if t not in checkpoint]
    log.info("build_polygon_universe: %d tickers to fetch (already have %d in checkpoint)",
             len(pending), len(checkpoint))

    if dry_run:
        log.info("build_polygon_universe: --dry-run, skipping %d fetches", len(pending))
        return checkpoint

    out = dict(checkpoint)
    fetched = 0
    for i, ticker in enumerate(pending):
        mc = _fetch_mcap(ticker, key, base_url)
        out[ticker] = mc
        fetched += 1
        if fetched % _BATCH_LOG == 0:
            log.info("build_polygon_universe: fetched %d / %d caps", fetched, len(pending))
            _save_checkpoint(out)   # incremental — a killed run resumes here same-day
        time.sleep(_RATE_LIMIT_DELAY)

    log.info("build_polygon_universe: mcap fetch done. have=%d non-null=%d",
             len(out), sum(1 for v in out.values() if v))
    return out


# ── checkpoint helpers ─────────────────────────────────────────────────────────

def _load_checkpoint() -> dict[str, float | None]:
    """Same-day resume state ONLY: {"asof": "YYYY-MM-DD", "caps": {ticker: cap|null}}.

    A checkpoint from a previous day (or the legacy flat {ticker: cap} format)
    is discarded so every refresh re-fetches live market caps — carrying caps
    across days froze them at their first-fetch values forever.
    """
    p = _checkpoint_path()
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text())
        if raw.get("asof") != date.today().isoformat():
            log.info("build_polygon_universe: discarding stale/legacy checkpoint (asof=%s)",
                     raw.get("asof"))
            return {}
        caps = raw.get("caps") or {}
        return {k: (float(v) if v is not None else None) for k, v in caps.items()}
    except Exception as e:  # noqa: BLE001
        log.warning("build_polygon_universe: checkpoint load failed: %s", e)
        return {}


def _save_checkpoint(cp: dict[str, float | None]) -> None:
    p = _checkpoint_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"asof": date.today().isoformat(), "caps": cp},
                            separators=(",", ":")))


# ── main build ─────────────────────────────────────────────────────────────────

def build(
    *,
    force: bool = False,
    dry_run: bool = False,
    stale_days: int = STALE_DAYS,
) -> pd.DataFrame:
    """Build / refresh reference.parquet. Returns the final DataFrame.

    Columns: ticker (index), gics_sector (str|None), market_cap_usd (float|None), asof (str).
    """
    cache = _cache_path()

    if not force and is_fresh(cache, stale_days):
        log.info("build_polygon_universe: cache fresh (%s), skip rebuild", cache)
        return pd.read_parquet(cache)

    # 1. Build GICS map from local data (no API calls)
    gics = build_gics_map()

    # 2. Load checkpoint of already-fetched market caps
    checkpoint = {} if force else _load_checkpoint()

    # 3. Decide which tickers to fetch caps for:
    #    - all tickers with a known GICS label (the ones the heatmap cares about)
    #    - exclude crypto / international suffixes (no /reference endpoint data)
    #    - accept both hyphen form (BRK-B, BF-B stored in constituents.parquet) and
    #      dot form (BRK.B) — _fetch_mcap normalises '-' -> '.' before calling Polygon
    import re
    us_like = [t for t in gics if re.match(r"^[A-Z]{1,5}([.\-][AB])?$", t)]
    log.info("build_polygon_universe: %d US-like tickers in GICS map", len(us_like))

    # 4. Fetch market caps (rate-limited, checkpointed)
    mcaps = fetch_mcaps(us_like, checkpoint, dry_run=dry_run)

    # 5. Save checkpoint (even if dry_run so we don't lose existing data)
    if not dry_run:
        _save_checkpoint(mcaps)

    # 6. Build DataFrame
    all_tickers = sorted(set(gics) | set(mcaps))
    rows = []
    today = date.today().isoformat()
    for t in all_tickers:
        rows.append({
            "ticker":          t,
            "gics_sector":     gics.get(t),
            "market_cap_usd":  mcaps.get(t),
            "asof":            today,
        })
    df = pd.DataFrame(rows).set_index("ticker")
    log.info(
        "build_polygon_universe: reference rows=%d gics_non_null=%d mcap_non_null=%d",
        len(df),
        int(df["gics_sector"].notna().sum()),
        int(df["market_cap_usd"].notna().sum()),
    )

    if dry_run:
        log.info("build_polygon_universe: --dry-run, skipping write")
        return df

    # 7. No-regress guard: never overwrite a good cache with a materially worse one.
    #    If an existing parquet has more non-null market caps than the new frame
    #    (allowing a 10% tolerance for delists), keep the existing one.
    new_non_null = int(df["market_cap_usd"].notna().sum())
    if cache.exists():
        try:
            prev = pd.read_parquet(cache, columns=["market_cap_usd"])
            prev_non_null = int(prev["market_cap_usd"].notna().sum())
            if prev_non_null > 0 and new_non_null < prev_non_null * 0.9:
                log.warning(
                    "build_polygon_universe: REGRESSION GUARD — new frame has %d non-null "
                    "market caps vs %d in existing cache (%.0f%%). Keeping existing cache.",
                    new_non_null, prev_non_null,
                    100.0 * new_non_null / prev_non_null,
                )
                return pd.read_parquet(cache)
        except Exception as e:  # noqa: BLE001
            log.warning("build_polygon_universe: could not read previous cache for guard: %s", e)

    # 8. Write atomically via temp file
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp.parquet")
    df.to_parquet(tmp)
    tmp.rename(cache)
    log.info("build_polygon_universe: wrote %s (%d rows)", cache, len(df))
    return df


# ── CLI ────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Build Polygon reference-universe cache")
    ap.add_argument("--force",     action="store_true", help="force rebuild even if cache is fresh")
    ap.add_argument("--dry-run",   action="store_true", help="audit without writing")
    ap.add_argument("--stale-days", type=int, default=STALE_DAYS,
                    help=f"cache staleness ceiling in calendar days (default {STALE_DAYS})")
    args = ap.parse_args(argv)

    df = build(force=args.force, dry_run=args.dry_run, stale_days=args.stale_days)

    # Summary output
    print(f"\nPolygon reference universe: {len(df)} tickers")
    print(f"  gics_sector non-null : {int(df['gics_sector'].notna().sum())}")
    print(f"  market_cap non-null  : {int(df['market_cap_usd'].notna().sum())}")
    if "gics_sector" in df.columns:
        vc = df["gics_sector"].value_counts()
        print("  by sector:")
        for sec, n in vc.items():
            print(f"    {sec:35s} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
