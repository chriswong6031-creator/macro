"""ONE-SHOT off-render script: backfill Polygon /v2/reference/news article counts
per ticker per day, 2016-01-01 -> present.

Output: data/narrative/polygon_news_counts.parquet
  columns: ticker (str), date (str YYYY-MM-DD), n_articles (int)

Usage:
  python -m scripts.backfill_polygon_news_counts            # real run (needs POLYGON_API_KEY)
  python -m scripts.backfill_polygon_news_counts --smoke    # mock run (no key needed)
  python -m scripts.backfill_polygon_news_counts --ticker AAPL,NVDA  # subset

State file (resumable): data/narrative/.polygon_backfill_state.json
  {ticker: last_cursor_or_date_str}

Budget: respects 429 (exponential backoff). Default pace 0.2s/call; --pace to override.

DO NOT run this from the nightly render path — it is hours-long.
POLYGON_API_KEY must be set in the environment or config.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

BACKFILL_START = "2016-01-01"
_OUT_FILE = "polygon_news_counts.parquet"
_STATE_FILE = ".polygon_backfill_state.json"
_POLYGON_NEWS_URL = "https://api.polygon.io/v2/reference/news"
_COLS = ["ticker", "date", "n_articles"]


# ── Universe ──────────────────────────────────────────────────────────────────

def _backfill_universe(repo_root: Path, extra_tickers: list[str] | None = None) -> list[str]:
    """SP1500 large-cap slice + basket members (same as Edgar8kVelocityAdapter)."""
    from lib import config  # noqa: PLC0415
    ranked: list[str] = []
    seen: set[str] = set()
    for grp in ("breadth", "midcap_breadth", "smallcap_breadth"):
        p = config.data_dir() / grp / "constituents.parquet"
        if not p.exists():
            continue
        try:
            tickers = sorted(pd.read_parquet(p).index.astype(str))
        except Exception:  # noqa: BLE001
            continue
        for t in tickers:
            if t not in seen:
                seen.add(t)
                ranked.append(t)
    mem_path = config.data_dir() / "baskets" / "membership.json"
    if mem_path.exists():
        try:
            mem = json.loads(mem_path.read_text()).get("baskets", {})
            for b in mem.values():
                for m in b.get("members", []):
                    t = m.get("ticker")
                    if t and not m.get("removed") and t not in seen:
                        seen.add(t)
                        ranked.append(t)
        except Exception:  # noqa: BLE001
            pass
    if extra_tickers:
        for t in extra_tickers:
            if t not in seen:
                ranked.append(t)
    return ranked


# ── State helpers ─────────────────────────────────────────────────────────────

def _state_path(out_dir: Path) -> Path:
    return out_dir / _STATE_FILE


def _load_state(out_dir: Path) -> dict[str, str]:
    sp = _state_path(out_dir)
    if not sp.exists():
        return {}
    try:
        return json.loads(sp.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _save_state(out_dir: Path, state: dict[str, str]) -> None:
    _state_path(out_dir).write_text(json.dumps(state, indent=2))


# ── Polygon news fetcher ──────────────────────────────────────────────────────

def _fetch_news_counts_for_ticker(
    ticker: str,
    api_key: str,
    published_after: str = BACKFILL_START,
    pace_s: float = 0.2,
    max_pages: int = 2000,
) -> dict[str, int]:
    """Paginate Polygon /v2/reference/news for one ticker.

    Returns {date_str: n_articles}. Uses cursor-based pagination.
    Raises on unrecoverable errors; caller handles per-ticker failures.
    """
    import requests  # noqa: PLC0415

    counts: dict[str, int] = {}
    url = _POLYGON_NEWS_URL
    params: dict = {
        "ticker": ticker,
        "published_utc.gte": published_after,
        "order": "asc",
        "limit": 1000,
        "apiKey": api_key,
    }
    pages = 0
    while pages < max_pages:
        backoff = 1.0
        for attempt in range(5):
            try:
                import requests as _req  # noqa: PLC0415
                r = _req.get(url, params=params, timeout=30)
                if r.status_code == 429:
                    log.warning("polygon_backfill: 429 on %s — sleeping %.0fs", ticker, backoff)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 60)
                    continue
                r.raise_for_status()
                data = r.json()
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == 4:
                    raise
                log.warning("polygon_backfill: %s attempt %d failed: %s", ticker, attempt, exc)
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)

        results = data.get("results") or []
        for item in results:
            pub = (item.get("published_utc") or "")[:10]
            if pub:
                counts[pub] = counts.get(pub, 0) + 1

        next_url = data.get("next_url")
        if not next_url:
            break

        # Polygon next_url already includes the cursor; we replace url+params
        url = next_url + f"&apiKey={api_key}"
        params = {}  # next_url carries all params
        pages += 1
        time.sleep(pace_s)

    return counts


# ── Upsert ────────────────────────────────────────────────────────────────────

def _upsert_counts(
    out_path: Path,
    ticker: str,
    counts: dict[str, int],
) -> None:
    """Append/update rows for this ticker in the parquet. Dedup on (ticker, date)."""
    new_rows = [{"ticker": ticker, "date": d, "n_articles": n} for d, n in counts.items()]
    if not new_rows:
        return
    new_df = pd.DataFrame(new_rows, columns=_COLS)

    if out_path.exists():
        try:
            existing = pd.read_parquet(out_path)
            # Drop existing rows for this ticker (will be replaced by the full sweep)
            existing = existing[existing["ticker"] != ticker]
            combined = pd.concat([existing, new_df], ignore_index=True)
        except Exception as exc:  # noqa: BLE001
            log.warning("polygon_backfill: corrupt store, rebuilding: %s", exc)
            combined = new_df
    else:
        combined = new_df

    combined = combined.sort_values(["ticker", "date"]).reset_index(drop=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(out_path, index=False)


# ── Smoke-mode mock ───────────────────────────────────────────────────────────

def _smoke_run(out_path: Path, tickers: list[str]) -> None:
    """Mock run: write synthetic data for the first 3 tickers, no network calls."""
    log.info("polygon_backfill: SMOKE MODE — writing synthetic data for %s", tickers[:3])
    rows = []
    for tk in tickers[:3]:
        for yr in range(2016, 2017):
            for mo in range(1, 3):
                d = f"{yr}-{mo:02d}-15"
                rows.append({"ticker": tk, "date": d, "n_articles": 5})
    df = pd.DataFrame(rows, columns=_COLS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    log.info("polygon_backfill: smoke complete — %d rows to %s", len(df), out_path)


# ── Main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true",
                    help="Mock run: write synthetic data, no network calls")
    ap.add_argument("--ticker", default="",
                    help="Comma-separated ticker subset (default: full universe)")
    ap.add_argument("--pace", type=float, default=0.2,
                    help="Seconds between Polygon calls (default: 0.2)")
    ap.add_argument("--start", default=BACKFILL_START,
                    help=f"published_utc.gte date (default: {BACKFILL_START})")
    args = ap.parse_args(argv)

    import sys  # noqa: PLC0415
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from lib import config  # noqa: PLC0415

    out_dir = config.data_dir() / "narrative"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / _OUT_FILE

    repo_root = Path(config.ROOT)

    # Resolve ticker list
    if args.ticker:
        tickers = [t.strip().upper() for t in args.ticker.split(",") if t.strip()]
    else:
        tickers = _backfill_universe(repo_root)

    if not tickers:
        log.error("polygon_backfill: empty universe — cannot run")
        return 1

    log.info("polygon_backfill: universe=%d tickers, start=%s", len(tickers), args.start)

    if args.smoke:
        _smoke_run(out_path, tickers)
        return 0

    # Real run: needs API key
    api_key = os.environ.get("POLYGON_API_KEY") or (
        (config.load() or {}).get("polygon", {}).get("api_key")
    )
    if not api_key:
        log.error("polygon_backfill: POLYGON_API_KEY not set — cannot run (use --smoke for a dry run)")
        return 1

    state = _load_state(out_dir)
    completed = {t for t, v in state.items() if v == "done"}
    remaining = [t for t in tickers if t not in completed]
    log.info("polygon_backfill: %d/%d tickers remaining", len(remaining), len(tickers))

    for i, ticker in enumerate(remaining):
        try:
            counts = _fetch_news_counts_for_ticker(
                ticker, api_key, published_after=args.start, pace_s=args.pace
            )
            _upsert_counts(out_path, ticker, counts)
            state[ticker] = "done"
            _save_state(out_dir, state)
            log.info("polygon_backfill: [%d/%d] %s — %d dates", i + 1, len(remaining), ticker, len(counts))
        except Exception as exc:  # noqa: BLE001
            log.warning("polygon_backfill: %s failed (will retry next run): %s", ticker, exc)
            state[ticker] = f"error:{datetime.now(timezone.utc).date()}"
            _save_state(out_dir, state)

    log.info("polygon_backfill: complete — %s", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
