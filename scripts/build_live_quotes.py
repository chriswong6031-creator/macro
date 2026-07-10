"""scripts/build_live_quotes.py — lightweight intraday QUOTES-ONLY snapshot.

Writes a single ``quotes.json`` in the SAME contract the Cloudflare Worker
``/quotes`` endpoint serves, so the browser ``live.js`` treats a worker response
and this static snapshot identically:

    { "ts": <ms>, "asof": <iso>, "source": "snapshot",
      "quotes": { "AAPL": {"price":.., "ts":<ms>, "source":"yahoo|polygon",
                           "basis":"regular|trade|..", "prevClose":..,
                           "changePct":..}, ... },
      "meta": {"requested":N, "resolved":M, "polygon_status":".."} }

WHY this exists: a static GitHub-Pages site can't refresh its own prices. A tiny
GitHub Action runs this every few minutes during market hours and force-pushes the
JSON to a single-commit ``live-data`` branch; the page fetches it from
``raw.githubusercontent`` (CORS ``*``, ~5-min CDN cache), keyless. This is the
ZERO-DEPLOY live path that works WITHOUT the Cloudflare Worker. When the Worker IS
deployed it takes precedence (real-time US via Polygon) and this snapshot becomes
the off-worker fallback — both are wired in ``templates/live.js``.

Universe = every ``data-sym`` the built site emits (so whatever the pages render
goes live) UNION a CORE of US + international index symbols and US index futures.
Quotes-only: NO scipy, no overlay math — installs fast, runs in seconds.

Graceful: any feed down -> the symbol is simply absent and live.js keeps the baked
number. ``--offline`` writes an empty-quotes snapshot (ship-safe / tests).
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from engine import live_quotes
from lib import config

log = logging.getLogger("live_quotes_build")

# Mirror the Worker's SYMBOL_RE charset so a junk data-sym can never reach a feed
# (^VIX, GC=F, ES=F, 0700.HK, BRK-B, EURUSD=X). Slightly longer cap than the
# worker (20) to admit ^STOXX50E / EURUSD=X comfortably.
_SYMBOL_RE = re.compile(r"^[A-Z0-9^][A-Z0-9.=^-]{0,19}$")
_DATA_SYM_RE = re.compile(r'data-sym="([^"]+)"')

# CORE live universe — always fetched even if no page links them yet. Drives the
# landing Market clock rows + dashboard index/futures tiles. All keyless via Yahoo.
US_INDEXES = ["^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX", "^TNX"]
US_FUTURES = ["ES=F", "NQ=F", "YM=F", "RTY=F"]              # overnight, reference only
INTL_INDEXES = [
    "^HSI",        # Hang Seng (Hong Kong)
    "000001.SS",   # SSE Composite (Shanghai)
    "399001.SZ",   # SZSE Component (Shenzhen)
    "^GSPTSE",     # S&P/TSX Composite (Canada)
    "^N225",       # Nikkei 225 (Japan)
    "^FTSE",       # FTSE 100 (UK)
    "^GDAXI",      # DAX (Germany)
    "^FCHI",       # CAC 40 (France)
    "^STOXX50E",   # Euro Stoxx 50
    "^AXJO",       # ASX 200 (Australia)
    "^KS11",       # KOSPI (South Korea)
    "^TWII",       # TAIEX (Taiwan) — landing market-clock row
    "^BSESN",      # BSE Sensex (India)
]
CORE_ETFS = ["SPY", "QQQ", "DIA", "IWM"]
# Headline cross-asset set the dashboard market tiles reference,
# kept in CORE so they're live regardless of when the site's data-sym is scraped.
CORE_COMMODITIES = ["GC=F", "SI=F", "HG=F", "CL=F", "DX-Y.NYB"]
CORE_FX = ["EURUSD=X", "USDJPY=X", "GBPUSD=X", "AUDUSD=X", "USDCAD=X", "USDCNH=X"]
# Crypto trades 24/7, so it's the one CORE leg that stays meaningful on nights and
# weekends. Kept in CORE so the Bitcoin Vector header (data-sym="BTC-USD") is live
# regardless of when the site's data-sym is scraped; routed to Yahoo spark (crypto
# pair -> is_us_symbol False). The dedicated hourly btc-live Action keeps it fresh
# 24/7 (see .github/workflows/btc-live.yml).
CORE_CRYPTO = ["BTC-USD"]
CORE_SYMBOLS = (US_INDEXES + US_FUTURES + INTL_INDEXES + CORE_ETFS
                + CORE_COMMODITIES + CORE_FX + CORE_CRYPTO)


def scrape_site_symbols(site_dir: Path) -> list[str]:
    """Every distinct ``data-sym`` value the built site emits — i.e. exactly the
    symbols the pages will ask live.js to refresh. Validated against the feed
    charset so a malformed attribute can't poison a batch fetch."""
    found: set[str] = set()
    if not site_dir.is_dir():
        return []
    for html in sorted(site_dir.glob("*.html")):
        try:
            text = html.read_text(errors="ignore")
        except Exception:  # noqa: BLE001 — skip an unreadable page, never abort
            continue
        for raw in _DATA_SYM_RE.findall(text):
            s = raw.strip().upper()
            if _SYMBOL_RE.match(s):
                found.add(s)
    return sorted(found)


def top_conviction(site_dir: Path, n: int) -> list[str]:
    """Top-N US single names by |conviction| from the search index — so the most-
    viewed single-stock pages (whose data-sym is set client-side, not in static
    HTML) are covered by the snapshot even with no Worker. Lightweight: just JSON."""
    p = site_dir / "stockdata" / "index.json"
    if n <= 0 or not p.exists():
        return []
    try:
        rows = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return []
    rows = [r for r in rows if isinstance(r, dict) and r.get("t")]
    rows.sort(key=lambda r: abs(float(r.get("a") or 0)), reverse=True)
    return [r["t"] for r in rows[:n]]


def build_universe(site_dir: Path, extra: list[str] | None = None,
                   cap: int = 2200, top_n: int = 120) -> list[str]:
    """CORE index/futures symbols first (never dropped by the cap), then every
    site data-sym, then top-N US conviction names, then config/CLI extras.
    De-duped, charset-validated, capped.

    Cap raised from 800 → 2200 (2026-07-09): the full scraped universe is ~1942
    symbols (CORE 39 + site data-sym ~1918 + conviction overlap). A Yahoo-path
    timing run resolved 1938/1942 in 53 s wall-clock — well within the live-quotes
    workflow 8-min job timeout (~11 % utilisation). File size at full universe was
    275 KB (< 500 KB browser-fetch budget). At cap=800 only ~249/680 basket members
    survived alphabetical truncation; cap=2200 covers the whole scraped universe
    with ~250 symbol headroom for site growth."""
    ordered: list[str] = []
    seen: set[str] = set()
    for s in (CORE_SYMBOLS + scrape_site_symbols(site_dir)
              + top_conviction(site_dir, top_n) + list(extra or [])):
        s = str(s).strip().upper()
        if s and s not in seen and _SYMBOL_RE.match(s):
            seen.add(s)
            ordered.append(s)
    if len(ordered) > cap:
        log.warning("live-quotes universe %d exceeds cap %d — truncating "
                    "(CORE symbols are first, never dropped)", len(ordered), cap)
    return ordered[:cap]


def _to_ms(quote_ts: str | None) -> int | None:
    """ISO8601 (engine.live_quotes ``quote_ts``) -> epoch milliseconds for the
    Worker-contract ``ts`` field live.js uses to age a quote."""
    if not quote_ts:
        return None
    try:
        dt = datetime.fromisoformat(quote_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:  # noqa: BLE001
        return None


def to_worker_quotes(raw: dict) -> dict:
    """engine.live_quotes {sym: {price, quote_ts, source, price_basis, prev_close,
    currency, delay_min, day_volume, day_high, day_low}} -> the Worker /quotes shape.

    New fields (IFT A1): vol, hi, lo — from the same Yahoo/Polygon batch response,
    zero extra requests.  Size estimate: +~68KB over full ~1942-symbol universe
    (343KB projected vs 500KB budget) — fields carried for all symbols.
    """
    out: dict[str, dict] = {}
    for sym, q in (raw or {}).items():
        if not q or q.get("price") is None:
            continue
        price = round(float(q["price"]), 4)
        prev = q.get("prev_close")
        prev = round(float(prev), 4) if prev is not None else None
        chg = round((price / prev - 1) * 100, 2) if prev else None
        entry: dict = {
            "price": price,
            "ts": _to_ms(q.get("quote_ts")),
            "source": q.get("source"),
            "basis": q.get("price_basis"),
            "prevClose": prev,
            "changePct": chg,
            "currency": q.get("currency"),
            "delayMin": q.get("delay_min"),     # measured age of THIS quote (honest, per-symbol)
        }
        # IFT A1: intraday volume + range from same batch response.
        # Keys kept short (vol/hi/lo) to minimise payload bytes.
        dv = q.get("day_volume")
        dh = q.get("day_high")
        dl = q.get("day_low")
        if dv is not None:
            entry["vol"] = dv
        if dh is not None:
            entry["hi"] = dh
        if dl is not None:
            entry["lo"] = dl
        out[sym] = entry
    return out


def _validate_symbols(syms: list[str]) -> list[str]:
    """De-dupe, upper-case and charset-validate an explicit symbol list (same gate
    build_universe applies) so a junk --symbols entry can never reach a feed."""
    ordered: list[str] = []
    seen: set[str] = set()
    for s in syms:
        s = str(s).strip().upper()
        if s and s not in seen and _SYMBOL_RE.match(s):
            seen.add(s)
            ordered.append(s)
    return ordered


def build(site_dir: Path, *, offline: bool = False, extra: list[str] | None = None,
          cap: int = 2200, symbols: list[str] | None = None) -> dict:
    now = datetime.now(timezone.utc)
    lcfg = config.load().get("live") or {}
    # symbols= builds an EXACT-universe snapshot (bypasses CORE + site scrape +
    # conviction) — used by the hourly 24/7 btc-live Action to refresh just the
    # crypto leg cheaply, without re-touching the equity universe.
    universe = (_validate_symbols(symbols) if symbols
                else build_universe(site_dir, extra=extra, cap=cap))
    diag: dict = {}
    raw = live_quotes.fetch_quotes(universe, offline=offline, diag=diag)
    quotes = to_worker_quotes(raw)
    return {
        "ts": int(now.timestamp() * 1000),
        "asof": now.isoformat(),
        "source": "snapshot",
        "quotes": quotes,
        "meta": {
            "requested": len(universe),
            "resolved": len(quotes),
            "polygon_status": diag.get("polygon_status"),
            "offline": bool(offline),
            # HONEST: this snapshot is ~15-min DELAYED (Polygon Standard / Yahoo spark),
            # not real-time. delayed_min=0 only after a real-time/websocket upgrade.
            "delayed_min": int(lcfg.get("delayed_min", 0)),
            "feed": str(lcfg.get("feed_label", "") or ""),
            "realtime": int(lcfg.get("delayed_min", 0)) == 0,
        },
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description="Build the live-quotes snapshot JSON.")
    ap.add_argument("--out", default="quotes.json", help="output JSON path")
    ap.add_argument("--site", default=None, help="built-site dir (default: config site_dir)")
    ap.add_argument("--offline", action="store_true", help="no network — empty snapshot")
    ap.add_argument("--max", type=int, default=2200, help="universe cap")
    ap.add_argument("--symbols", default=None,
                    help="comma-separated EXACT universe (bypass CORE+scrape+conviction); "
                         "e.g. 'BTC-USD' for the hourly crypto-only snapshot")
    args = ap.parse_args()

    site_dir = (Path(args.site) if args.site
                else config.ROOT / config.load()["storage"]["site_dir"])
    extra = list((config.load().get("live") or {}).get("snapshot_extra") or [])
    symbols = [s for s in (args.symbols or "").split(",") if s.strip()] or None
    snap = build(site_dir, offline=args.offline, extra=extra, cap=args.max,
                 symbols=symbols)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # allow_nan=False: a NaN would make the JSON unparseable in the browser.
    out.write_text(json.dumps(snap, separators=(",", ":"), allow_nan=False) + "\n")
    log.info("wrote %s — %d/%d symbols resolved (polygon=%s)", out,
             snap["meta"]["resolved"], snap["meta"]["requested"],
             snap["meta"]["polygon_status"])


if __name__ == "__main__":
    main()
