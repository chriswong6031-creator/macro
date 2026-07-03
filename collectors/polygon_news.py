"""Polygon ticker-news SENTIMENT collector — uses the POLYGON key the repo already has.

Polygon's /v2/reference/news returns per-article `insights` with a per-ticker sentiment
(positive/negative/neutral) the repo's financial_news pipeline currently discards. This rolls
the recent articles up to a per-ticker bullish ratio and stores a daily snapshot, feeding the
convergence kernel's low-weight `news_sentiment` channel (editorial-tape lean, abundant but
noisy — context, never a standalone signal).

W0.6d (Setup-Species data plane): tier-1 widening (120→500) behind a runtime budget check.
  Tier-0 (baseline): up to MAX_TICKERS_T0 (120) narrative-basket members — existing behavior.
  Tier-1 (widening):  up to MAX_TICKERS_T1 (500) names by breadth-universe liquidity rank
                      (SP500 members first, then SP400, then SP600 = large→mid→small).
  Tier-2 (future):    up to MAX_TICKERS_T2 (1500) — constant defined but NOT yet activated;
                      flip by changing ACTIVE_TIER = 2 when the budget allows.

Budget check: we measure per-call latency on the first BUDGET_PROBE_N calls, then project
the incremental cost of moving from T0 to T1 (or T1 to T2).  If the projected addition
exceeds BUDGET_MAX_MINUTES, widening is aborted for this run and the adapter falls back to
the next lower tier.  The budget check is per-run — a fast API session auto-enables widening
without code changes.

Queried over the selected watchlist (1 call/ticker). Output:
data/polygon/news_sentiment.parquet — append-only daily snapshots. GATED: no POLYGON/MASSIVE
key -> 'blocked', non-fatal.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pandas as pd

from collectors.base import Adapter, is_connection_error
from collectors.universe import basket_members
from lib import config

log = logging.getLogger(__name__)

# ── tier caps ────────────────────────────────────────────────────────────────
MAX_TICKERS_T0 = 120    # baseline (narrative-basket members)
MAX_TICKERS_T1 = 500    # W0.6d tier-1: breadth-universe liquidity rank
MAX_TICKERS_T2 = 1500   # future tier-2 (defined; NOT active)

# Active tier: 0=baseline, 1=widened-500, 2=full-1500.
# W0.6d activates tier-1.  Set ACTIVE_TIER = 2 when the budget analysis supports it.
ACTIVE_TIER = 1

# Budget guard: if projecting T1 incremental fetch time exceeds this, fall back to T0.
BUDGET_MAX_MINUTES = 5.0
BUDGET_PROBE_N = 5     # how many calls to time before projecting

PACE_S = 0.15
MIN_ARTICLES = 5


def _breadth_universe_ranked() -> list[str]:
    """SP1500 members ranked by liquidity tier: SP500 (large) → SP400 (mid) → SP600 (small).

    Uses the three breadth/constituents.parquet files which already reflect SP1500
    membership.  SP500 (data/breadth/) comes first, then midcap (data/midcap_breadth/),
    then smallcap (data/smallcap_breadth/).  Within each tier the order is alphabetical
    (stable across runs).

    Returns: deduplicated list, large-cap first.
    """
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
    return ranked


def _watchlist(tier: int) -> list[str]:
    """Build the watchlist for the given tier.

    Tier 0: narrative-basket members (up to MAX_TICKERS_T0), existing behavior.
    Tier 1: breadth-universe liquidity rank (up to MAX_TICKERS_T1), large-cap first.
    Tier 2: same ranked list, up to MAX_TICKERS_T2.

    The basket-member set is always included in T1/T2 as well (they are a subset or
    are inserted at the front — they overlap with the breadth universe for the most
    liquid names).
    """
    if tier == 0:
        return basket_members(cap=MAX_TICKERS_T0)

    cap = MAX_TICKERS_T1 if tier == 1 else MAX_TICKERS_T2

    # Start with basket members (narrative priority), then fill from breadth rank
    base = basket_members()
    base_set = set(base)
    ranked = [t for t in _breadth_universe_ranked() if t not in base_set]

    combined = base + ranked
    return combined[:cap]


def parse_sentiment(results: list[dict], ticker: str) -> dict | None:
    """Pure: roll a ticker's news `insights` sentiment into pos/neg/neutral counts."""
    pos = neg = neu = 0
    for art in results or []:
        for ins in art.get("insights", []) or []:
            if str(ins.get("ticker", "")).upper() != ticker.upper():
                continue
            s = str(ins.get("sentiment", "")).lower()
            if s == "positive":
                pos += 1
            elif s == "negative":
                neg += 1
            elif s == "neutral":
                neu += 1
    total = pos + neg + neu
    if total == 0:
        return None
    return {"ticker": ticker, "articles": total, "bullish": pos, "bearish": neg, "neutral": neu,
            "bull_ratio": round(pos / total, 2), "net": pos - neg}


class PolygonNewsAdapter(Adapter):
    name = "polygon_news"
    group = "polygon"
    stale_after_days = 3

    def __init__(self) -> None:
        cfg = config.load().get("polygon", {})
        self.base = str(cfg.get("base_url", "https://api.polygon.io")).rstrip("/")
        self.key = config.secret(cfg.get("api_key_env", "POLYGON_API_KEY")) or config.secret("MASSIVE_API_KEY")
        if not self.key:
            self.expected_failure = "POLYGON_API_KEY/MASSIVE_API_KEY not set"

    def _news(self, ticker: str) -> list[dict]:
        r = self.http_get(f"{self.base}/v2/reference/news",
                          params={"ticker": ticker, "limit": 50, "apiKey": self.key},
                          retries=2, timeout=30)
        return (r.json() or {}).get("results", [])

    def _budget_check(self, tier_0_watch: list[str], tier_target_watch: list[str]) -> int:
        """Probe call latency and decide the active tier for this run.

        Measures per-call latency on the first BUDGET_PROBE_N tickers of tier_0_watch,
        projects the incremental cost of fetching the extra (tier_target_watch minus
        tier_0_watch) tickers, and returns the tier we should use.

        Returns: effective tier (0 or ACTIVE_TIER).
        """
        if ACTIVE_TIER == 0:
            return 0

        t0_set = set(tier_0_watch)
        incremental = [t for t in tier_target_watch if t not in t0_set]
        if not incremental:
            return ACTIVE_TIER  # no extra cost

        # Measure latency on a short probe (the first BUDGET_PROBE_N names in T0)
        probe_tickers = tier_0_watch[:BUDGET_PROBE_N]
        latencies: list[float] = []
        for tk in probe_tickers:
            t_start = time.monotonic()
            try:
                self._news(tk)
                time.sleep(PACE_S)
            except Exception:  # noqa: BLE001
                pass
            latencies.append(time.monotonic() - t_start)

        if not latencies:
            log.warning("polygon_news budget_check: no latency samples, falling back to T0")
            return 0

        avg_latency = sum(latencies) / len(latencies)
        incremental_mins = len(incremental) * avg_latency / 60.0

        log.info(
            "polygon_news budget_check: avg_latency=%.2fs, incremental=%d tickers, "
            "projected=%.1f min (budget=%.1f min)",
            avg_latency, len(incremental), incremental_mins, BUDGET_MAX_MINUTES,
        )

        if incremental_mins > BUDGET_MAX_MINUTES:
            log.warning(
                "polygon_news: T%d widening ABORTED (projected +%.1f min > budget %.1f min) "
                "— falling back to T0 (%d tickers)",
                ACTIVE_TIER, incremental_mins, BUDGET_MAX_MINUTES, len(tier_0_watch),
            )
            return 0

        return ACTIVE_TIER

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.key:
            raise RuntimeError("POLYGON key not set")

        tier_0_watch = _watchlist(0)
        target_watch = _watchlist(ACTIVE_TIER) if ACTIVE_TIER > 0 else tier_0_watch

        # Budget check: measure latency and decide whether to widen
        effective_tier = self._budget_check(tier_0_watch, target_watch)
        watch = _watchlist(effective_tier) if effective_tier > 0 else tier_0_watch

        log.info("polygon_news: effective tier=%d, watch=%d tickers", effective_tier, len(watch))

        today = datetime.now(timezone.utc).date().isoformat()
        rows, errors = [], 0

        # If the budget probe already fetched some tickers, don't re-fetch them
        probe_fetched: set[str] = set(tier_0_watch[:BUDGET_PROBE_N]) if effective_tier > 0 else set()
        # We need to re-fetch them for sentiment (the probe only measured latency, discarded results)
        # So we keep track to avoid double-fetching in the main loop below — actually we DO need
        # the results, so we run a clean pass over the full watchlist without the probe.

        for tk in watch:
            try:
                roll = parse_sentiment(self._news(tk), tk)
                time.sleep(PACE_S)
            except Exception as e:  # noqa: BLE001
                if is_connection_error(e):
                    raise
                errors += 1
                log.debug("polygon_news %s: %s", tk, e)
                continue
            if roll:
                roll["snapshot_date"] = today
                roll["tier"] = effective_tier
                rows.append(roll)
        if not rows:
            raise RuntimeError(f"polygon_news: no sentiment rows ({len(watch)} watch, {errors} errors)")
        new = pd.DataFrame(rows)
        new["_first_seen"] = datetime.now(timezone.utc).isoformat()
        path = config.data_dir() / "polygon" / "news_sentiment.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        combined = pd.concat([pd.read_parquet(path), new], ignore_index=True) if path.exists() else new
        combined = combined.drop_duplicates(subset=["ticker", "snapshot_date"], keep="last").reset_index(drop=True)
        combined.to_parquet(path)
        log.info("polygon_news: tier=%d, %d tickers @ %s, %d total rows, %d errors",
                 effective_tier, len(rows), today, len(combined), errors)
        ingest = pd.DataFrame({"tickers": [len(rows)], "total_rows": [len(combined)],
                               "effective_tier": [effective_tier]},
                              index=[pd.Timestamp(today)])
        return {"polygon_news__ingest": ingest}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    PolygonNewsAdapter().fetch()
