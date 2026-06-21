"""Dead-name PRICE recovery — Phase 1A of research/INSTITUTIONAL_ROADMAP.md.

Phase 1B (collectors/edgar_deadnames) recovered dead-name FUNDAMENTALS, but factor
ICs and forward returns also need PRICES, and the live close cache serves only
currently-listed names (0/1,083 dead). This recovers daily closes for the resolved
dead tickers so the merged panel can finally compute dead-name market caps and
forward returns — turning the survivor-only ICs into a de-biased read.

PRICES ARE THE WALL. yfinance serves ~0 delisted names; Stooq and Polygon DO (Stooq
free daily CSV, Polygon aggregates for delisted) but are IP-gated — blocked from
some build IPs, reachable from CI. So this is a resumable, drip-capped, RESILIENT
collector: it attempts Stooq → Polygon → yfinance per name, caches what it gets, and
no-ops gracefully where every source is blocked. NOTHING depends on it (the paper:
"do not let the keystone depend on it").

HONEST RESIDUAL BIAS (stamped on the coverage artifact): the names free sources DO
serve skew to ACQUISITIONS (the price ran up to a deal and stopped — a realized
winner), while the BANKRUPTCY tail (price → 0) is under-served. So recovered
dead-name prices still carry a mild UP bias vs the true dead universe; a −100%
bankruptcy imputation would need a delisting-reason feed (Ch.11 8-Ks) we don't yet
wire. The price_coverage ratio + this caveat make the residual explicit rather than
silent.
"""
from __future__ import annotations

import io
import json
import logging
import time
from datetime import datetime, timezone

import pandas as pd

from collectors.edgar_deadnames import _load_cik_cache, dead_universe
from lib import config

log = logging.getLogger(__name__)

REFRESH_DAYS = 90          # delisted history is static; refresh rarely
_UA = {"User-Agent": "Mozilla/5.0 (macro-dashboard research)"}


# --------------------------------------------------------------------------- #
# per-source daily-close fetchers (each returns a tz-naive close Series or None)
# --------------------------------------------------------------------------- #
def _stooq_daily(ticker: str) -> pd.Series | None:
    """Stooq free daily CSV. Retains many delisted US names; HTML-blocks some IPs."""
    import requests
    sym = ticker.lower().replace(".", "-")
    try:
        r = requests.get(f"https://stooq.com/q/d/l/?s={sym}.us&i=d", headers=_UA, timeout=25)
        txt = r.text.strip()
        if r.status_code != 200 or not txt.lower().startswith("date"):
            return None                    # HTML block page / empty
        df = pd.read_csv(io.StringIO(txt))
        if "Close" not in df or len(df) < 2:
            return None
        s = pd.Series(df["Close"].values, index=pd.to_datetime(df["Date"]))
        return s[~s.index.duplicated(keep="last")].sort_index()
    except Exception as e:  # noqa: BLE001
        log.debug("stooq %s: %s", ticker, e)
        return None


def _polygon_daily(ticker: str, start: str, end: str) -> pd.Series | None:
    """Polygon daily aggregates — serves delisted tickers when a key is present."""
    import os
    key = os.environ.get("POLYGON_API_KEY")
    try:
        key = key or (config.load().get("polygon") or {}).get("api_key") \
            or (config.load().get("keys") or {}).get("polygon")
    except Exception:  # noqa: BLE001
        pass
    if not key:
        return None
    import requests
    url = (f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"
           f"?adjusted=true&sort=asc&limit=50000&apiKey={key}")
    try:
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            return None
        res = r.json().get("results") or []
        if len(res) < 2:
            return None
        s = pd.Series([b["c"] for b in res],
                      index=pd.to_datetime([b["t"] for b in res], unit="ms"))
        return s[~s.index.duplicated(keep="last")].sort_index()
    except Exception as e:  # noqa: BLE001
        log.debug("polygon %s: %s", ticker, e)
        return None


def _yf_daily(ticker: str, start: str, end: str) -> pd.Series | None:
    """yfinance fallback — rarely resolves delisted names, but free when it does."""
    try:
        import warnings
        warnings.filterwarnings("ignore")
        logging.getLogger("yfinance").setLevel(logging.CRITICAL)   # mute per-name delisted spam
        import yfinance as yf
        h = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
        if h is None or h.empty or "Close" not in h:
            return None
        s = h["Close"]
        s.index = pd.to_datetime(s.index).tz_localize(None)
        return s[~s.index.duplicated(keep="last")].sort_index()
    except Exception as e:  # noqa: BLE001
        log.debug("yfinance %s: %s", ticker, e)
        return None


def _membership_window(ticker: str, mem: pd.DataFrame) -> tuple[str, str]:
    """(start, end) date strings spanning the name's index membership + buffers, so
    we fetch enough history to bracket every rebalance it was alive for."""
    sub = mem[mem["ticker"] == ticker]
    if sub.empty:
        return "2005-01-01", datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (pd.to_datetime(sub["start_date"]).min() - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
    end = (pd.to_datetime(sub["end_date"]).max() + pd.Timedelta(days=60)).strftime("%Y-%m-%d")
    return start, end


def _prices_path():
    p = config.data_dir() / "edgar" / "dead_name_prices.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def fetch_dead_prices(force: bool = False, max_new: int = 150,
                      tickers: list[str] | None = None) -> pd.DataFrame:
    """Resumably recover daily closes for resolved dead tickers (Stooq → Polygon →
    yfinance), drip-capped. Writes the long table data/edgar/dead_name_prices.parquet
    (ticker, date, close, source) and a per-ticker fetch log. Resilient — names every
    source declines are recorded so they aren't re-hammered for REFRESH_DAYS."""
    cache = _load_cik_cache()
    resolved = [t for t, v in cache.items() if v.get("cik")]
    if tickers is not None:
        resolved = [t for t in resolved if t in tickers]
    if not resolved:
        log.warning("fetch_dead_prices: no resolved dead tickers — run resolve_dead_ciks first")
        return pd.DataFrame()

    mem = pd.read_parquet(config.data_dir() / "breadth" / "sp1500_pit_membership.parquet")
    out_p = _prices_path()
    existing = pd.read_parquet(out_p) if out_p.exists() else pd.DataFrame()
    seen_p = config.data_dir() / "edgar" / "_dead_name_prices_seen.json"
    seen = json.loads(seen_p.read_text()) if seen_p.exists() else {}

    def stale(t: str) -> bool:
        if force:
            return True
        ts = (seen.get(t) or {}).get("at")
        if not ts:
            return True
        try:
            return (datetime.now(timezone.utc) - pd.to_datetime(ts)).days > REFRESH_DAYS
        except Exception:  # noqa: BLE001
            return True

    todo = [t for t in resolved if stale(t)][:max_new]
    log.info("dead prices: %d resolved, fetching %d (cap %d)", len(resolved), len(todo), max_new)

    now = datetime.now(timezone.utc).isoformat()
    new_rows = []
    for t in todo:
        start, end = _membership_window(t, mem)
        s, src = _stooq_daily(t), "stooq"
        time.sleep(0.4)                        # Stooq is rate-touchy
        if s is None:
            s, src = _polygon_daily(t, start, end), "polygon"
        if s is None:
            s, src = _yf_daily(t, start, end), "yfinance"
        seen[t] = {"at": now, "source": src if s is not None else None,
                   "n": int(len(s)) if s is not None else 0}
        if s is not None and len(s) >= 2:
            for d, c in s.items():
                new_rows.append({"ticker": t, "date": d, "close": float(c), "source": src})

    fresh = pd.DataFrame(new_rows)
    if not existing.empty and not fresh.empty:
        existing = existing[~existing["ticker"].isin(fresh["ticker"].unique())]
        prices = pd.concat([existing, fresh], ignore_index=True)
    else:
        prices = fresh if not fresh.empty else existing
    if not prices.empty:
        prices = prices.sort_values(["ticker", "date"]).reset_index(drop=True)
        prices.to_parquet(out_p)
    seen_p.write_text(json.dumps(seen, indent=0, sort_keys=True))
    log.info("dead prices: %d ticker-days, %d names recovered",
             len(prices), prices["ticker"].nunique() if "ticker" in prices else 0)
    return prices


def dead_name_closes() -> pd.DataFrame:
    """Wide [date x ticker] closes for the recovered dead names — concat-ready with
    the survivor breadth close cache so a leak-free backtest can finally see the
    delisted cohort (truncate to `asof` per rebalance, exactly like survivors)."""
    p = _prices_path()
    if not p.exists():
        return pd.DataFrame()
    long = pd.read_parquet(p)
    if long.empty:
        return pd.DataFrame()
    return long.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()


def price_coverage() -> dict:
    """Honest dead-name PRICE coverage + the residual-bias caveat. Writes
    data/edgar/_dead_name_price_coverage.json."""
    universe = dead_universe()
    cache = _load_cik_cache()
    resolved = {t for t, v in cache.items() if v.get("cik")}
    p = _prices_path()
    with_px = set()
    by_source: dict[str, int] = {}
    if p.exists():
        df = pd.read_parquet(p, columns=["ticker", "source"])
        with_px = set(df["ticker"])
        for src, n in df.drop_duplicates("ticker")["source"].value_counts().items():
            by_source[str(src)] = int(n)
    n = len(universe)
    out = {
        "schema": "dead_name_price_coverage.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_dead_universe": n,
        "n_cik_resolved": len(resolved & set(universe)),
        "n_with_prices": len(with_px & set(universe)),
        "price_coverage_frac": round(len(with_px & set(universe)) / n, 4) if n else 0.0,
        "by_source": by_source,
        "residual_bias": "Recovered names skew to ACQUISITIONS (price ran to a deal and "
                         "stopped); the BANKRUPTCY tail (price→0) is under-served by free "
                         "sources, so recovered prices keep a mild UP bias. A −100% "
                         "bankruptcy imputation needs a delisting-reason feed (not wired).",
        "note": "yfinance ~0 on delisted; Stooq/Polygon are IP-gated → this accrues in CI.",
    }
    (config.data_dir() / "edgar" / "_dead_name_price_coverage.json").write_text(json.dumps(out, indent=1))
    return out
