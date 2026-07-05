"""Prediction-markets collector — market-implied odds + flow for macro events.

Keyless Polymarket Gamma API ("fully public, no auth"): the market-implied
probabilities for the macro questions that pair with our regime/catalyst reads —
the next Fed decision (cut/hold/hike), how many cuts this year, recession, etc.

Event titles rotate ("Fed Decision in June" → "July"), so we MATCH by a configured
title substring and pick the nearest-expiry / highest-volume event dynamically. Each
run appends a dated SNAPSHOT to data/prediction_markets/snapshots.parquet
(append-only) — so a probability + flow history accrues and the leg becomes
backtestable later (the feed itself is snapshot-only). Private-use dashboard, so
re-displaying the probabilities is fine; framed as market-expectation CONTEXT, never
a score.

Schema (append-safe — new nullable float columns added 2026-07-05):
  snapshot_date, source, event_key, event_title, end_date, outcome, prob
  [new] volume24hr    — event-level 24-hour volume (USD notional, Gamma API field)
  [new] volume_total  — event-level all-time cumulative volume
  [new] liquidity     — event-level liquidity (open interest proxy, Gamma API field)
  [new] open_interest — event-level open interest (Gamma API field openInterest)
  [new] mkt_volume24hr — per-outcome sub-market 24-hr volume

Kalshi note: api.elections.kalshi.com returns market data keyless (HTTP 200, no
auth header required as of 2026-07-05). It is NOT integrated in this PR because
Kalshi's market taxonomy diverges from our Polymarket event_key scheme, and a
key-matched config approach requires operator opt-in on the event mapping.  The
endpoint is confirmed working; a follow-up PR can add a KalshiAdapter with the
same snapshot pattern.
"""
from __future__ import annotations

import json
import logging
from datetime import date

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

GAMMA = "https://gamma-api.polymarket.com/events"


def _safe_float(val: object) -> float | None:
    """Convert a value that may be str/int/float/None to float or None."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def extract_outcomes(event: dict) -> list[dict]:
    """[{outcome, prob, mkt_volume24hr}] from a Polymarket event's sub-markets. PURE.
    Each sub-market's groupItemTitle is the outcome label and outcomePrices[0] is
    P(Yes) for that outcome. Multi-outcome events' probs sum to ~1.

    mkt_volume24hr is the per-outcome sub-market 24-hour volume (USD notional).
    Field verified on Gamma API 2026-07-05: markets[*].volume24hr (float).
    """
    out = []
    for m in event.get("markets", []) or []:
        op = m.get("outcomePrices")
        if isinstance(op, str):
            try:
                op = json.loads(op)
            except Exception:  # noqa: BLE001
                op = None
        if not op:
            continue
        label = m.get("groupItemTitle") or m.get("question") or ""
        try:
            prob = float(op[0])
        except (TypeError, ValueError, IndexError):
            continue
        mkt_vol24 = _safe_float(m.get("volume24hr"))
        out.append({"outcome": str(label)[:48], "prob": round(prob, 4),
                    "mkt_volume24hr": mkt_vol24})
    return out


def match_event(events: list[dict], match: str, pick: str = "nearest_end") -> dict | None:
    """Best active event whose title contains `match` (case-insensitive). PURE.
    pick='nearest_end' → soonest future endDate; 'max_volume' → highest volume."""
    cand = [e for e in events if match.lower() in (e.get("title", "") or "").lower()
            and (e.get("markets"))]
    if not cand:
        return None
    if pick == "max_volume":
        return max(cand, key=lambda e: float(e.get("volume") or e.get("volume24hr") or 0))
    today = date.today().isoformat()
    fut = [e for e in cand if (e.get("endDate", "") or "")[:10] >= today]
    pool = fut or cand
    return min(pool, key=lambda e: e.get("endDate", "") or "9999")


class PredictionMarketsAdapter(Adapter):
    name = "prediction_markets"
    group = "prediction_markets"
    stale_after_days = 3

    def __init__(self) -> None:
        self.cfg = config.load().get("prediction_markets", {}) or {}

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.cfg.get("enabled", True):
            raise RuntimeError("prediction_markets disabled in config")
        events_cfg = self.cfg.get("events", {}) or {}
        all_events = self._fetch_active()
        if not all_events:
            raise RuntimeError("no active Polymarket events fetched")
        today = date.today().isoformat()
        rows = []
        for key, spec in events_cfg.items():
            ev = match_event(all_events, spec.get("match", ""), spec.get("pick", "nearest_end"))
            if not ev:
                continue
            # Event-level volume/liquidity fields — verified on Gamma API 2026-07-05.
            # volume24hr: float (USD notional last 24h)
            # volume: float (all-time cumulative)
            # liquidity: float (open interest proxy / maker liquidity)
            # openInterest: float (open interest in USD)
            ev_vol24 = _safe_float(ev.get("volume24hr"))
            ev_vol = _safe_float(ev.get("volume"))
            ev_liq = _safe_float(ev.get("liquidity"))
            ev_oi = _safe_float(ev.get("openInterest"))
            for o in extract_outcomes(ev):
                rows.append({
                    "snapshot_date": today,
                    "source": "polymarket",
                    "event_key": key,
                    "event_title": str(ev.get("title", ""))[:80],
                    "end_date": (ev.get("endDate", "") or "")[:10],
                    "outcome": o["outcome"],
                    "prob": o["prob"],
                    # Flow fields (nullable; None for legacy rows loaded from old parquet)
                    "volume24hr": ev_vol24,
                    "volume_total": ev_vol,
                    "liquidity": ev_liq,
                    "open_interest": ev_oi,
                    "mkt_volume24hr": o["mkt_volume24hr"],
                })
        if not rows:
            raise RuntimeError("no configured events matched")
        self._append_snapshot(pd.DataFrame(rows))
        log.info("prediction_markets: %d outcome rows across %d events",
                 len(rows), len({r["event_key"] for r in rows}))
        s = pd.DataFrame({"events_ok": [len({r["event_key"] for r in rows})]},
                         index=[pd.Timestamp(today)])
        return {"prediction_markets_runs": s}

    def _fetch_active(self) -> list[dict]:
        """Fetch active Polymarket events with pagination.

        The Gamma API silently caps at 100 events per page regardless of the
        `limit` parameter.  Lower-volume events (e.g. the recession market,
        ~$1.6M total volume, volume24hr ~$12K) live well past position 100
        when results are sorted by volume24hr descending.  We paginate until
        we either get an empty page or reach the configured page cap (default 8
        pages = 800 events), which is ample to capture all macro events.
        """
        retries = int(self.cfg.get("retries", 3))
        page_size = 100    # Gamma's effective cap per page
        max_pages = int(self.cfg.get("fetch_max_pages", 8))
        all_events: list[dict] = []
        for page in range(max_pages):
            offset = page * page_size
            r = self.http_get(GAMMA, retries=retries,
                              params={"closed": "false", "active": "true",
                                      "limit": page_size, "offset": offset,
                                      "order": "volume24hr", "ascending": "false"})
            d = r.json()
            if not isinstance(d, list) or not d:
                break
            all_events.extend(d)
            if len(d) < page_size:
                break   # last page
        return all_events

    def _append_snapshot(self, new: pd.DataFrame) -> None:
        """Append-safe snapshot writer.

        Old rows that predate the flow columns will have NaN for the five new
        nullable float columns — concat + dedup preserves them untouched.
        """
        p = config.data_dir() / "prediction_markets" / "snapshots.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            try:
                old = pd.read_parquet(p)
                new = pd.concat([old, new], ignore_index=True)
            except Exception as e:  # noqa: BLE001
                log.warning("prediction snapshots unreadable (%s) — overwriting", e)
        new = new.drop_duplicates(subset=["snapshot_date", "event_key", "outcome"], keep="last")
        new.to_parquet(p, index=False)
