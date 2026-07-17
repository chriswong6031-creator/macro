"""Intraday live overlay -> site/live/overlay.json (+ site/live_config.js).

This is the SEPARATE intraday step (run from an intraday cron, e.g. every minute
during RTH), NOT part of the ~45-min nightly build. It:

  1. assembles a modest universe (Mastermind GTAA assets + China GTAA assets +
     the top-N US names by conviction from the search index + config extras),
  2. fetches a live last-price per symbol (engine.live_quotes; Polygon for US,
     Yahoo spark for the rest; graceful no-op offline),
  3. recomputes the cheap fast leaves + a divergence-vs-nightly-1-day-band flag
     for each (engine.live_overlay), with a limit-move outlier guard,
  4. mirrors the nightly Mastermind allocations marked to the live price (only
     when the leg's quote is fresh + a real trade),
  5. adds a live MARKET-CONTEXT block (SPY/QQQ/VIX) and a per-region SESSION
     (is-open) block so consumers can tell "stale because closed" from "feed broke",
  6. writes site/live/overlay.json (PIT-stamped, NaN-safe) + site/live_config.js.

Fail-safe: any source down -> the overlay still emits, the affected legs marked
``stale`` so consumers fall back to the nightly baseline. ``--offline`` forces
that path (no network) for local runs / tests.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from engine import live_overlay, live_quotes, technicals
from lib import config

log = logging.getLogger("live_overlay_build")


# --------------------------------------------------------------- universe ----

def _gtaa_assets() -> list[str]:
    out: list[str] = []
    try:
        from engine.masterminds import ASSETS
        out += list(ASSETS)
    except Exception as e:  # noqa: BLE001
        log.warning("masterminds ASSETS unavailable: %s", e)
    try:
        from engine.china_masterminds import ASSET_LABEL as CN
        out += list(CN.keys())
    except Exception as e:  # noqa: BLE001
        log.warning("china masterminds ASSET_LABEL unavailable: %s", e)
    return out


def _top_conviction(n: int) -> list[str]:
    p = config.ROOT / config.load()["storage"]["site_dir"] / "stockdata" / "index.json"
    if not p.exists() or n <= 0:
        return []
    try:
        rows = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return []
    rows = [r for r in rows if isinstance(r, dict) and r.get("t")]
    rows.sort(key=lambda r: abs(float(r.get("a") or 0)), reverse=True)
    return [r["t"] for r in rows[:n]]


def build_universe() -> list[str]:
    cfg = config.load().get("live") or {}
    uni = _gtaa_assets()
    uni += _top_conviction(int(cfg.get("top_conviction_n", 60)))
    uni += list(cfg.get("universe_extra") or [])
    seen, out = set(), []
    for t in uni:
        t = str(t).strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    cap = int(cfg.get("max_universe", 150))
    if len(out) > cap:
        log.warning("live universe %d exceeds max_universe %d — truncating", len(out), cap)
    return out[:cap]


# --------------------------------------------------------------- baselines ----

def _load_baseline(ticker: str, close) -> dict | None:
    """Nightly per-ticker record from site/stockdata/<T>.json when present, else a
    minimal baseline synthesised from the close series (so a GTAA asset with no
    single-stock page still gets tech + a prev_close to diverge against)."""
    p = config.ROOT / config.load()["storage"]["site_dir"] / "stockdata" / f"{ticker}.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            pass
    if close is not None and not close.empty:
        return {"ticker": ticker, "asof": str(close.index[-1].date()),
                "tech": technicals.snapshot(close)}
    return None


# ----------------------------------------------------------- allocations ----

def _usable_mark(quote, base_close, stale_after, max_chg, now):
    """(price, chg_pct, stale) for marking a GTAA leg to live — only a FRESH, real
    live trade that passes the limit-move guard is used; otherwise stale=True and
    no live price is carried, so a consumer never marks NAV off a stale/glitch tick."""
    st = live_overlay.staleness(quote, stale_after, now)
    if st["stale"] or not quote or quote.get("price") is None:
        return None, None, True
    price = float(quote["price"])
    ref = quote.get("prev_close") or base_close
    if ref and abs(price / float(ref) - 1) > max_chg / 100.0:
        return None, None, True            # outlier print
    chg = round((price / float(ref) - 1) * 100, 2) if ref else None
    return round(price, 4), chg, False


def _live_allocations(quotes, stale_after, max_chg, now) -> dict:
    """Mirror the nightly Mastermind allocations, each asset marked to a fresh live
    price. Reads the enriched masterminds_latest.json (v2 with per-card alloc)."""
    out: dict = {}
    sources = {"us": config.data_dir() / "regime" / "masterminds_latest.json",
               "china": config.data_dir() / "china_regime" / "china_masterminds_latest.json"}
    for region, path in sources.items():
        if not path.exists():
            continue
        try:
            snap = json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            continue
        cards_in = snap.get("cards", [])
        if cards_in and not any(c.get("alloc") for c in cards_in):
            log.warning("%s masterminds_latest.json carries no alloc (old v1 shape?) — "
                        "rebuild masterminds for live allocation marks", region)
        cards = []
        for c in cards_in:
            alloc = []
            for a in c.get("alloc", []) or []:
                base = live_overlay.read_close(a.get("asset", ""))
                base_close = float(base.iloc[-1]) if base is not None and not base.empty else None
                price, chg, stale = _usable_mark(quotes.get(a.get("asset")), base_close,
                                                 stale_after, max_chg, now)
                alloc.append({**a, "live_price": price, "chg_pct": chg, "stale": stale})
            cards.append({"key": c.get("key"), "name": c.get("name"),
                          "asof": c.get("asof"), "alloc": alloc})
        if cards:
            out[region] = {"built": snap.get("built"), "cards": cards}
    return out


# ------------------------------------------------------- market context ----

def _vix_band(v: float | None) -> str | None:
    if v is None:
        return None
    return "calm" if v < 15 else "normal" if v < 20 else "elevated" if v < 30 else "stress"


def _market_context(quotes, stale_after, max_chg, now) -> dict:
    """Cheap live macro read so the bot gets breadth-of-tape without N per-ticker
    calls: SPY/QQQ marked to live + a VIX level/band."""
    cfg = config.load().get("live") or {}
    out: dict = {}
    for sym in (cfg.get("market_context") or ["SPY", "QQQ", "^VIX"]):
        base = live_overlay.read_close(sym)
        base_close = float(base.iloc[-1]) if base is not None and not base.empty else None
        price, chg, stale = _usable_mark(quotes.get(sym), base_close, stale_after, max_chg, now)
        key = "VIX" if sym in ("^VIX", "_VIX") else sym
        shown = price if price is not None else (round(base_close, 4) if base_close else None)
        rec = {"price": shown, "chg_pct": chg, "stale": stale,
               "source": (quotes.get(sym) or {}).get("source")}
        if key == "VIX":
            rec["band"] = _vix_band(rec["price"])
        out[key] = rec
    return out


# --------------------------------------------------------------- config.js ----

def resolve_worker_url() -> str:
    """The live-quotes Worker URL, with an ENV OVERRIDE so the intraday layer can be
    turned on by setting a GitHub repo VARIABLE (LIVE_QUOTES_WORKER_URL) — no config.yml
    edit/commit needed — falling back to config.yml live.quotes_worker_url. A non-https
    value is rejected (logged + ignored) so a malformed variable can't break live.js."""
    cfg = config.load().get("live") or {}
    url = (os.environ.get("LIVE_QUOTES_WORKER_URL", "").strip()
           or str(cfg.get("quotes_worker_url", "") or "").strip())
    if url and not url.startswith("https://"):
        log.warning("live quotes worker URL ignored (must be https://): %r", url)
        return ""
    return url.rstrip("/")


def resolve_snapshot_url() -> str:
    """The static live-quotes SNAPSHOT URL (the keyless, no-Worker fallback that
    live.js fetches when no Worker is configured). ENV override
    LIVE_QUOTES_SNAPSHOT_URL wins over config.yml live.snapshot_url; a non-https
    value is rejected so a malformed variable can't break live.js. Default points
    at the `live-data` branch raw.githubusercontent path the live-quotes Action
    force-pushes (CORS '*', ~5-min CDN cache)."""
    cfg = config.load().get("live") or {}
    url = (os.environ.get("LIVE_QUOTES_SNAPSHOT_URL", "").strip()
           or str(cfg.get("snapshot_url", "") or "").strip())
    # Allow a SAME-ORIGIN relative path (e.g. "live/quotes.json" — China-safe, no
    # raw.githubusercontent) OR an absolute https URL. Reject only an absolute URL
    # with a non-https scheme (malformed / mixed-content), which would break live.js.
    if url and "://" in url and not url.startswith("https://"):
        log.warning("live snapshot URL ignored (must be https:// or same-origin relative): %r", url)
        return ""
    return url


def write_live_config(site_dir) -> None:
    """Tiny browser config the static pages' live.js reads. Written by BOTH this
    intraday build and the nightly build_site, so it always reflects config.yml /
    the LIVE_QUOTES_WORKER_URL + LIVE_QUOTES_SNAPSHOT_URL env overrides."""
    cfg = config.load().get("live") or {}
    js = (f"window.LIVE_QUOTES_URL={json.dumps(resolve_worker_url())};"
          f"window.LIVE_SNAPSHOT_URL={json.dumps(resolve_snapshot_url())};"
          f"window.LIVE_POLL_SEC={int(cfg.get('poll_seconds', 60))};"
          f"window.LIVE_STALE_MIN={int(cfg.get('stale_after_min', 20))};"
          # HONEST FRESHNESS: vendor delay floor + caption so live.js never claims
          # "real-time" on the 15-min-delayed Standard plan. Set delayed_min: 0 to
          # restore the green "live" pulse once a real-time/websocket plan is live.
          f"window.LIVE_DELAYED_MIN={int(cfg.get('delayed_min', 0))};"
          f"window.LIVE_FEED_LABEL={json.dumps(str(cfg.get('feed_label', '') or ''))};"
          f"window.LIVE_FEED_LABEL_ZH={json.dumps(str(cfg.get('feed_label_zh', '') or ''))};"
          f"window.LIVE_ENABLED={json.dumps(bool(cfg.get('enabled', True)))};\n")
    (site_dir / "live_config.js").write_text(js)


# ------------------------------------------------------------------ build ----

def build(offline: bool = False, limit: int | None = None,
          site_dir: Path | None = None) -> dict:
    """site_dir overrides the output root (tests); default = the real site/ tree.
    Reads (stockdata baselines, universe) always come from the repo tree."""
    cfg = config.load().get("live") or {}
    now = datetime.now(timezone.utc)
    site = Path(site_dir) if site_dir is not None \
        else config.ROOT / config.load()["storage"]["site_dir"]
    write_live_config(site)

    if not cfg.get("enabled", True):
        log.info("live overlay disabled in config")
        return {"status": "disabled"}

    universe = build_universe()
    if limit:
        universe = universe[:limit]
    ctx_syms = list(cfg.get("market_context") or ["SPY", "QQQ", "^VIX"])
    stale_after = float(cfg.get("stale_after_min", 20))
    max_chg = float(cfg.get("max_chg_pct", live_overlay.DEFAULT_MAX_CHG_PCT))

    diag: dict = {}
    quotes = live_quotes.fetch_quotes(list(dict.fromkeys(universe + ctx_syms)),
                                      offline=offline, diag=diag)

    tickers: dict = {}
    fresh = 0
    for t in universe:
        close = live_overlay.read_close(t)
        baseline = _load_baseline(t, close)
        if baseline is None:
            continue
        rec = live_overlay.build_ticker_overlay(t, baseline, quotes.get(t), close,
                                                stale_after, now, max_chg_pct=max_chg)
        tickers[t] = rec
        if not rec.get("stale"):
            fresh += 1

    sessions = {r: live_overlay.market_session(r, now)
                for r in ("us", "cn", "hk", "ca", "jp", "kr", "tw", "gb", "eu")}
    ts_vals = [q["quote_ts"] for q in quotes.values() if q.get("quote_ts")]
    out = {
        "schema": "live.overlay.v2",
        "built": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "quote_ts_max": max(ts_vals) if ts_vals else None,
        "stale_after_min": stale_after, "max_chg_pct": max_chg,
        # vendor delay floor (15 = Polygon Standard / Yahoo spark) — the whole feed is
        # DELAYED, never real-time; 0 only after a real-time/websocket upgrade.
        "delayed_min": int(cfg.get("delayed_min", 0)),
        "feed": str(cfg.get("feed_label", "") or ""),
        "realtime": int(cfg.get("delayed_min", 0)) == 0,
        "sources": {"us": cfg.get("us_source", "polygon"),
                    "intl": cfg.get("intl_source", "yahoo"),
                    "polygon_key": bool(config.secret("POLYGON_API_KEY")
                                        or config.secret("MASSIVE_API_KEY")),
                    "polygon_status": diag.get("polygon_status", "unused")},
        "sessions": sessions,
        "market": _market_context(quotes, stale_after, max_chg, now),
        "n": len(tickers), "n_fresh": fresh, "n_quotes": len(quotes),
        "tickers": tickers,
        "allocations": _live_allocations(quotes, stale_after, max_chg, now),
    }
    try:
        out_dir = site / "live"
        out_dir.mkdir(parents=True, exist_ok=True)
        # allow_nan=False so a non-finite leak fails loudly in CI rather than
        # writing invalid JSON (NaN token) that breaks every strict consumer.
        (out_dir / "overlay.json").write_text(json.dumps(out, indent=2, allow_nan=False))
    except Exception as e:  # noqa: BLE001 — never abort the intraday loop on a write error
        log.error("live overlay write failed: %s", e)
        return {"status": "write_error", "error": str(e)}
    log.info("live overlay: %d names (%d fresh / %d quotes), polygon=%s, offline=%s",
             len(tickers), fresh, len(quotes), diag.get("polygon_status"), offline)
    return {"status": "ok", "n": len(tickers), "fresh": fresh, "quotes": len(quotes)}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true",
                    help="skip network; emit a stale overlay from baseline closes")
    ap.add_argument("--limit", type=int, default=None, help="cap the universe (debug)")
    args = ap.parse_args()
    print(build(offline=args.offline, limit=args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
