"""scripts/build_ext_quotes.py — Extended-hours quote publisher (Mac→R2 relay).

PURPOSE
-------
Polls Yahoo v8/finance/chart once per symbol during pre-market (04:00–09:30 ET)
and post-market (16:00–20:00 ET) windows to extract the latest extended-hours
print, then publishes the aggregated JSON to R2 at:

    live_flow/ext_quotes.json

The VPS hub fetches that file and uses it as the 'r2file' ext-quote source,
bypassing Yahoo 429s against DigitalOcean IPs.  This script runs on the Mac
(residential IP) where Yahoo returns 200s.

Grey-source note
----------------
Yahoo Finance v8/finance/chart is an undocumented, ToS-grey endpoint (same as
lib/yahoo.py uses for price lookups).  Data labelled source="yahoo-chart (grey)"
in the published payload.

SYMBOL STRATEGY
---------------
Static curated list of ~100 liquid US names (DEFAULT_SYMBOLS).  A static list
is used instead of reading the gitignored nightly manifest (site/stockdata/
index.json) because:
  - The manifest is gitignored and not present in the flow-ops-wt deployment.
  - The manifest is rebuilt nightly; the Mac would need a live checkout.
  - The static list covers the Macro Dashboard DEFAULT watchlist symbols + the
    top ~100 US liquid names by market-cap/trading interest that the hub users
    most commonly request in pre/post sessions.
  - The list can be updated without a nightly build cycle.

WINDOW LOGIC
------------
Outside the ext windows the script exits cleanly with rc=0 and does NOT publish
(the hub treats a stale R2 file as absent — staleness gate = 5 min in hub).

PACING
------
~0.8 req/s between symbol fetches.  Full 100-symbol cycle ≤ ~125 s (< 2.5 min).
Yahoo 429 → logged, symbol skipped; does not abort the cycle.

OUTPUT SCHEMA
-------------
{
  "schema": "flow.ext_quotes/v1",
  "asof_utc": "2026-07-10T12:34:56Z",
  "session_date": "2026-07-10",
  "source": "yahoo-chart (grey)",
  "quotes": {
    "AAPL": {"extPrice": 213.45, "extTs": 1752220400, "close": 212.30},
    ...
  }
}

Only symbols with a print NEWER than the regular-session close are emitted
(i.e. a real ext print exists).  extChg is NOT computed here; the hub owns
chg math vs its anchor close.

USAGE
-----
    python -m scripts.build_ext_quotes [--publish] [--smoke]

    --publish   Write to R2 (requires R2_* env vars).
    --smoke     Fetch first 3 symbols, print, exit 0 (no publish).
    (no flags)  Log-only dry-run; print payload to stdout.

ENVIRONMENT VARIABLES
---------------------
    R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET

AUTHORITY NOTE
--------------
All output is display-tier.  No signal, score, or escalation originates here.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, date, time as dtime, timezone
from pathlib import Path
from typing import Optional

# ── repo path ─────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.nyse_calendar import is_session, ET

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ext_quotes] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema / R2 constants
# ---------------------------------------------------------------------------

SCHEMA = "flow.ext_quotes/v1"
R2_KEY = "live_flow/ext_quotes.json"
SOURCE_LABEL = "yahoo-chart (grey)"

# Yahoo v8 chart endpoint (grey / undocumented — same as lib/yahoo.py).
# query1 is more permissive than query2 on residential IPs.
_YAHOO_CHART_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
    "?interval=1m&range=1d&includePrePost=true"
)
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
_ACCEPT = "application/json"
_ACCEPT_LANG = "en-US,en;q=0.9"

# Pacing: 0.8 req/s → 1.25 s between requests.
_PACE_S = 1.25
# HTTP timeout per request.
_TIMEOUT_S = 10

# ---------------------------------------------------------------------------
# Symbol universe
# ---------------------------------------------------------------------------
# Static curated ~100 US liquid names covering:
#   - Macro Dashboard DEFAULT watchlist symbols (SPY, QQQ, BTC-USD excluded —
#     BTC has no Yahoo ext-hours bar; index ETFs covered via separate entries)
#   - Top ~100 US names by market-cap / flow-desk importance
#   - Core sector ETFs used throughout the engine
# Update this list in-place as the universe evolves.

DEFAULT_SYMBOLS: list[str] = [
    # Index ETFs + sector ETFs
    "SPY", "QQQ", "IWM", "DIA", "RSP",
    "XLK", "XLF", "XLV", "XLE", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC",
    "SMH", "SOXX", "XBI", "KRE", "GLD", "SLV", "TLT", "HYG", "LQD",
    # Mega-cap tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AVGO",
    # Large-cap tech
    "AMD", "INTC", "QCOM", "ORCL", "CRM", "ADBE", "AMAT", "LRCX", "KLAC",
    "NOW", "SNOW", "PANW", "CRWD", "NET",
    # Financials
    "JPM", "BAC", "GS", "MS", "WFC", "C", "BLK", "SCHW", "AXP", "V", "MA",
    # Healthcare
    "JNJ", "UNH", "LLY", "PFE", "MRK", "ABBV", "BMY", "AMGN", "GILD",
    # Consumer
    "AMZN", "COST", "WMT", "HD", "TGT", "NKE", "MCD", "SBUX", "DIS", "NFLX",
    # Energy
    "XOM", "CVX", "COP", "EOG", "SLB",
    # Industrials / Materials
    "CAT", "DE", "HON", "BA", "GE", "RTX", "LMT", "NOC",
    # Communication
    "T", "VZ", "TMUS",
    # Other high-volume names
    "BABA", "TSM", "ASML", "ARM", "MRVL", "MU", "WDC",
    "PLTR", "RBLX", "RIVN", "LCID", "COIN",
    "BRK-B", "UBER", "LYFT", "ABNB", "SHOP",
    "ZM", "DOCU", "TWLO", "OKTA", "DDOG",
]
# De-duplicate while preserving order (e.g. AMZN appears twice in draft above).
DEFAULT_SYMBOLS = list(dict.fromkeys(DEFAULT_SYMBOLS))

# ---------------------------------------------------------------------------
# Window classification
# ---------------------------------------------------------------------------

# Extended hours windows (half-open intervals in ET).
_EXT_PRE_OPEN  = dtime(4, 0, 0)
_EXT_PRE_CLOSE = dtime(9, 30, 0)
_EXT_POST_OPEN = dtime(16, 0, 0)
_EXT_POST_CLOSE = dtime(20, 0, 0)


def is_ext_window_now(now_et: Optional[datetime] = None) -> bool:
    """Return True if current ET time is in the pre-market or post-market window."""
    if now_et is None:
        now_et = datetime.now(tz=ET)
    if not is_session(now_et.date()):
        return False
    t = now_et.time()
    return (_EXT_PRE_OPEN <= t < _EXT_PRE_CLOSE) or (_EXT_POST_OPEN <= t < _EXT_POST_CLOSE)


def classify_ext_session(now_et: Optional[datetime] = None) -> str:
    """Return 'pre', 'post', or 'none' based on current ET time."""
    if now_et is None:
        now_et = datetime.now(tz=ET)
    t = now_et.time()
    if _EXT_PRE_OPEN <= t < _EXT_PRE_CLOSE:
        return "pre"
    if _EXT_POST_OPEN <= t < _EXT_POST_CLOSE:
        return "post"
    return "none"


# ---------------------------------------------------------------------------
# Yahoo chart fetch
# ---------------------------------------------------------------------------

def _fetch_yahoo_chart(sym: str) -> Optional[dict]:
    """
    Fetch Yahoo v8/finance/chart for sym.
    Returns the raw JSON dict, or None on error / 429.
    Grey source — ToS-grey risk noted in module docstring.
    """
    url = _YAHOO_CHART_URL.format(sym=sym)
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA,
        "Accept": _ACCEPT,
        "Accept-Language": _ACCEPT_LANG,
    })
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            log.warning("yahoo 429 for %s — rate-limited, skipping", sym)
        else:
            log.debug("yahoo HTTP %d for %s", exc.code, sym)
        return None
    except Exception as exc:  # noqa: BLE001
        log.debug("yahoo fetch error for %s: %s", sym, exc)
        return None


def extract_ext_print(
    sym: str,
    chart_json: dict,
    session: str,
) -> Optional[dict[str, object]]:
    """
    Extract the latest extended-hours print from a Yahoo chart response.

    Returns {"extPrice": float, "extTs": int, "close": float} or None.
    Only emits when the ext print timestamp is NEWER than the regular-session
    close timestamp (i.e. a real ext print exists, not just the close bar).

    session: 'pre' | 'post'
    """
    try:
        result = (chart_json.get("chart") or {}).get("result") or []
        if not result:
            return None
        r = result[0]
        meta = r.get("meta") or {}
        timestamps = r.get("timestamp") or []
        quote_block = (r.get("indicators") or {}).get("quote") or [{}]
        closes = (quote_block[0] if quote_block else {}).get("close") or []

        if not timestamps:
            return None

        # Determine session boundaries.
        ctp = meta.get("currentTradingPeriod") or {}
        if session == "pre":
            sess_info = ctp.get("pre") or {}
        else:
            sess_info = ctp.get("post") or {}

        sess_start = sess_info.get("start")
        sess_end = sess_info.get("end")

        if not sess_start or not sess_end:
            return None

        # Regular session close timestamp (used to confirm ext print is newer).
        rth_info = ctp.get("regular") or {}
        rth_end_ts = rth_info.get("end")  # Unix seconds

        # Official regular-session close price from meta (most reliable).
        official_close = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
        if official_close is None:
            return None
        try:
            official_close = float(official_close)
        except (TypeError, ValueError):
            return None

        # Find last bar in the ext session window with a non-null close.
        last_ts: Optional[int] = None
        last_price: Optional[float] = None
        for i in range(len(timestamps) - 1, -1, -1):
            ts = timestamps[i]
            c = closes[i] if i < len(closes) else None
            if ts is None or c is None:
                continue
            try:
                ts = int(ts)
                c = float(c)
            except (TypeError, ValueError):
                continue
            if not (sess_start <= ts < sess_end):
                continue
            if not (c > 0):
                continue
            last_ts = ts
            last_price = c
            break

        if last_ts is None or last_price is None:
            return None

        # Guard: ext print must be newer than regular-session close.
        # This ensures we emit only real ext prints, not the closing bar.
        if rth_end_ts is not None:
            try:
                rth_end_ts = int(rth_end_ts)
                if last_ts <= rth_end_ts:
                    return None
            except (TypeError, ValueError):
                pass

        return {
            "extPrice": round(last_price, 4),
            "extTs": last_ts,
            "close": round(official_close, 4),
        }
    except Exception as exc:  # noqa: BLE001
        log.debug("extract_ext_print error for %s: %s", sym, exc)
        return None


# ---------------------------------------------------------------------------
# R2 client
# ---------------------------------------------------------------------------

def _r2_client():
    """Build a boto3 S3 client for R2, or None if creds are absent."""
    ep = os.environ.get("R2_ENDPOINT")
    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (ep and ak and sk):
        return None
    try:
        import boto3
        from botocore.config import Config
        kw = dict(
            region_name="auto",
            signature_version="s3v4",
            max_pool_connections=4,
            retries={"max_attempts": 3, "mode": "standard"},
        )
        try:
            cfg = Config(
                **kw,
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            )
        except TypeError:
            cfg = Config(**kw)
        return boto3.client(
            "s3",
            endpoint_url=ep,
            aws_access_key_id=ak,
            aws_secret_access_key=sk,
            config=cfg,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("ext_quotes: R2 client build failed: %s", exc)
        return None


def _publish_r2(payload_json: str) -> bool:
    """Write JSON string to R2 key live_flow/ext_quotes.json."""
    s3 = _r2_client()
    if s3 is None:
        log.warning("ext_quotes: R2 client unavailable — skipping publish")
        return False
    bucket = os.environ.get("R2_BUCKET", "mastermindx")
    try:
        s3.put_object(
            Bucket=bucket,
            Key=R2_KEY,
            Body=payload_json.encode("utf-8"),
            ContentType="application/json",
        )
        log.info("ext_quotes: published → R2 %s/%s", bucket, R2_KEY)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("ext_quotes: R2 publish failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_ext_quotes(
    symbols: Optional[list[str]] = None,
    publish: bool = False,
    smoke: bool = False,
) -> Optional[dict]:
    """
    Poll Yahoo for each symbol and build the ext_quotes payload.

    Returns the payload dict on success, None on global failure.
    Never raises — all errors are logged.

    Args:
        symbols: Override symbol list (default: DEFAULT_SYMBOLS).
        publish: If True, write to R2.
        smoke:   If True, only process first 3 symbols and return without publishing.
    """
    now_et = datetime.now(tz=ET)
    now_utc = datetime.now(tz=timezone.utc)
    session_date = now_et.date().isoformat()

    # Window guard.
    if not smoke and not is_ext_window_now(now_et):
        log.info(
            "ext_quotes: outside ext window (%s ET, session=%s) — exiting cleanly",
            now_et.strftime("%H:%M"),
            classify_ext_session(now_et),
        )
        return None

    session = classify_ext_session(now_et)
    if smoke:
        # In smoke mode we always attempt fetches regardless of window.
        session = session if session != "none" else "post"

    syms = symbols if symbols is not None else DEFAULT_SYMBOLS
    if smoke:
        syms = syms[:3]

    log.info(
        "ext_quotes: starting cycle session=%s syms=%d publish=%s smoke=%s",
        session, len(syms), publish, smoke,
    )

    quotes: dict[str, dict] = {}
    fetched = 0
    emitted = 0
    errors = 0

    for sym in syms:
        raw = _fetch_yahoo_chart(sym)
        fetched += 1
        if raw is None:
            errors += 1
        else:
            entry = extract_ext_print(sym, raw, session)
            if entry is not None:
                quotes[sym] = entry
                emitted += 1
                if smoke:
                    log.info("smoke [%s]: extPrice=%.4f extTs=%d close=%.4f",
                             sym, entry["extPrice"], entry["extTs"], entry["close"])
            else:
                log.debug("ext_quotes: %s — no ext print in %s session", sym, session)

        # Pacing: 0.8 req/s.
        if fetched < len(syms):
            time.sleep(_PACE_S)

    asof_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "schema": SCHEMA,
        "asof_utc": asof_utc,
        "session_date": session_date,
        "source": SOURCE_LABEL,
        "quotes": quotes,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))

    log.info(
        "ext_quotes: cycle done — fetched=%d emitted=%d errors=%d asof=%s",
        fetched, emitted, errors, asof_utc,
    )

    if smoke:
        print(payload_json)
        return payload

    if publish:
        _publish_r2(payload_json)
    else:
        # Dry-run: write to /tmp for inspection.
        out = Path("/tmp/ext_quotes_debug.json")
        out.write_text(payload_json)
        log.info("ext_quotes: dry-run written to %s", out)
        print(payload_json)

    return payload


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Extended-hours quote publisher.")
    parser.add_argument("--publish", action="store_true",
                        help="Publish to R2 (requires R2_* env vars).")
    parser.add_argument("--smoke", action="store_true",
                        help="Fetch first 3 symbols, print, exit (no publish).")
    args = parser.parse_args()

    result = build_ext_quotes(publish=args.publish, smoke=args.smoke)
    sys.exit(0 if result is not None or (not args.publish and not args.smoke) else 0)


if __name__ == "__main__":
    main()
