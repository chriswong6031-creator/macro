"""StockTwits public stream sentiment collector (keyless).

Endpoint: GET https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json

Per ticker per run, records:
  * n_messages    — count of messages in the response window (up to 30)
  * n_bullish     — count with entities.sentiment.basic == "Bullish"
  * n_bearish     — count with entities.sentiment.basic == "Bearish"
  * n_tagged      — total with any explicit sentiment tag
  * bull_ratio    — n_bullish / n_tagged (null when n_tagged == 0)
  * watchlist_count — followers of this symbol on StockTwits (from symbol.watchlist_count)
  * _collected    — UTC ISO timestamp

NOTE on bull_ratio semantics: the ~30 messages returned are the most-recent public posts,
covering an uncontrolled rolling window — minutes for heavily-traded tickers, potentially
weeks for quiet ones. bull_ratio is NOT a same-day sentiment count and must not be treated
as such by engine consumers; it reflects recency-weighted posting activity, not a calendar
period.

Output: data/stocktwits/sentiment.parquet (append-only, key-deduped on ticker+_collected_date)
PIT: keeps='first' dedup on (ticker, _collected_date) so one reading per day per ticker.

Budget: unauthenticated ~200 req/hour (~3.3/min). Cap universe to TOP_N=150 liquid names
(basket_members first; falls back to a hard cap). Rotate the offset daily so full universe
cycles even when >150 names exist. Stop on HTTP 429 with a log warning — no crash.

NEVER crashes the nightly: all exceptions caught per-ticker; connection errors propagate
(so the circuit breaker can trip if the host is down entirely).
"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from collectors.base import Adapter, is_connection_error
from collectors.universe import basket_members
from lib import config

log = logging.getLogger(__name__)

BASE = "https://api.stocktwits.com/api/2"
TOP_N = 150          # max symbols per run (unauthenticated rate limit ~200/hr)
PACE_S = 0.4         # 0.4s between calls => ~150 in ~60s, well under 200/hr
ROTATE_SALT = "stocktwits_v1"   # stable salt for daily offset rotation


def _today_offset(n_total: int, n_pick: int) -> int:
    """Deterministic daily offset so coverage rotates across the full universe."""
    day_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    h = int(hashlib.md5(f"{ROTATE_SALT}:{day_str}".encode()).hexdigest(), 16)
    if n_total <= n_pick:
        return 0
    return h % (n_total - n_pick + 1)


def parse_stream(data: dict, ticker: str) -> dict | None:
    """Pure: extract per-ticker row from a StockTwits symbol-stream response.

    Returns None if the response is structurally invalid (missing messages key).
    """
    msgs = data.get("messages")
    if msgs is None:
        return None
    n_total = len(msgs)
    n_bull = sum(
        1 for m in msgs
        if (m.get("entities") or {}).get("sentiment") and
        (m["entities"]["sentiment"] or {}).get("basic") == "Bullish"
    )
    n_bear = sum(
        1 for m in msgs
        if (m.get("entities") or {}).get("sentiment") and
        (m["entities"]["sentiment"] or {}).get("basic") == "Bearish"
    )
    n_tagged = n_bull + n_bear
    bull_ratio = round(n_bull / n_tagged, 4) if n_tagged > 0 else None
    wl = (data.get("symbol") or {}).get("watchlist_count")
    return {
        "ticker": ticker,
        "n_messages": n_total,
        "n_bullish": n_bull,
        "n_bearish": n_bear,
        "n_tagged": n_tagged,
        "bull_ratio": bull_ratio,
        "watchlist_count": wl,
    }


class StockTwitsAdapter(Adapter):
    name = "stocktwits"
    group = "stocktwits"
    stale_after_days = 2

    def __init__(self) -> None:
        # Keyless — no expected_failure; always attempts
        pass

    def _fetch_symbol(self, symbol: str) -> dict | None:
        """Fetch the public stream for one symbol. Returns raw response dict or None."""
        url = f"{BASE}/streams/symbol/{symbol}.json"
        headers = {"User-Agent": config.load()["sponsors"]["user_agent"]}
        try:
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code == 429:
                log.warning("stocktwits: HTTP 429 on %s — rate-limited; stopping run", symbol)
                return "rate_limited"  # type: ignore[return-value]
            if r.status_code == 404:
                log.debug("stocktwits: symbol %s not found (404)", symbol)
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            if is_connection_error(e):
                raise
            log.debug("stocktwits %s: %s", symbol, e)
            return None

    def _merge(self, new: pd.DataFrame) -> int:
        if new.empty:
            return 0
        new = new.copy()
        collected_ts = datetime.now(timezone.utc).isoformat()
        collected_date = collected_ts[:10]
        new["_collected"] = collected_ts
        new["_collected_date"] = collected_date
        path = config.data_dir() / self.group / "sentiment.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            combined = pd.concat([pd.read_parquet(path), new], ignore_index=True)
        else:
            combined = new
        # one reading per ticker per calendar day (keeps oldest — nightly idempotency)
        combined = combined.drop_duplicates(
            subset=["ticker", "_collected_date"], keep="first"
        ).reset_index(drop=True)
        combined.to_parquet(path)
        return len(new)

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        universe = basket_members()
        if not universe:
            raise ValueError("stocktwits: empty universe")
        # rotate daily so full coverage cycles
        # _today_offset caps at (n_total - TOP_N), so the slice always yields TOP_N items
        # (or fewer when the universe itself is smaller than TOP_N, which is fine).
        offset = _today_offset(len(universe), TOP_N)
        watch = universe[offset: offset + TOP_N]

        rows: list[dict] = []
        errors = 0
        rate_limited = False

        for tk in watch:
            raw = self._fetch_symbol(tk)
            if raw == "rate_limited":
                rate_limited = True
                break
            if raw is None:
                errors += 1
                time.sleep(PACE_S)
                continue
            row = parse_stream(raw, tk)
            if row:
                rows.append(row)
            time.sleep(PACE_S)

        n = self._merge(pd.DataFrame(rows)) if rows else 0
        if rate_limited:
            log.warning(
                "stocktwits: rate-limited after %d symbols; stored %d rows so far",
                len(rows), n,
            )
        else:
            log.info(
                "stocktwits: %d symbols polled, +%d rows, %d errors",
                len(watch), n, errors,
            )
        ingest = pd.DataFrame(
            {"new_rows": [n], "watch": [len(watch)], "rate_limited": [rate_limited]},
            index=[pd.Timestamp(datetime.now(timezone.utc).date())],
        )
        return {"stocktwits__ingest": ingest}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    StockTwitsAdapter().fetch()
