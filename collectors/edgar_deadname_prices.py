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
dead-name prices carry a mild UP bias vs the true dead universe. That bias is now
PARTLY corrected: `collectors/edgar_delisting` reads the Ch.11 8-Ks (Item 1.03) to
flag bankruptcy delistings and imputes a −100% terminal close (source=
"imputed_bankruptcy") for the flagged names that have a price anchor, and
`price_coverage` reports the delisting-reason split + softens this caveat once the
imputation has run. The residual that remains (bankruptcy names with no recovered
price anchor; un-classified acquisition skew) stays explicit rather than silent.
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

# --- identity guards (a ticker string is a MUTABLE key) ------------------------
# Every fetcher here asks a vendor for a BARE TICKER STRING, so it gets whoever
# holds that string TODAY over whatever window we ask for. When the string changed
# hands, the reply welds two registrants into one key. Two bounds contain that:
TENURE_LOOKBACK_DAYS = 400   # pre-index history a rebalance lookback legitimately needs
SPLICE_GAP_DAYS = 45         # a hole this long is an identity seam, not a trading halt


def tenure_bounds(ticker: str, mem: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """(first_held, last_held) — the span over which THIS registrant held the string,
    read from the PIT membership. None when the name has no membership row."""
    sub = mem[mem["ticker"] == ticker]
    if sub.empty:
        return None
    start = pd.to_datetime(sub["start_date"]).min()
    end = pd.to_datetime(sub["end_date"]).max()
    if pd.isna(start):
        return None
    return start, end


def split_identity_seam(s: pd.Series, tenure_start: pd.Timestamp | None,
                        gap_days: int = SPLICE_GAP_DAYS) -> tuple[pd.Series, pd.Series]:
    """Split a fetched close series into (kept, foreign) at an identity seam.

    A segment is FOREIGN when it lies **entirely before** the name's tenure AND is
    separated from the tenure segment by a hole of >= `gap_days` — the signature of
    the string's PREVIOUS holder (FI = Frank's International welded to Fiserv across
    an empty 2022; ALTM = Altus Midstream welded to Arcadium Lithium across 2022-23).

    Deliberately narrow. A gap INSIDE the tenure is a corporate event, not a swap
    (EBIX/ENDP → OTC after Ch.11), and that price→0 tail is exactly the anti-
    survivorship data the panel needs — so it is never dropped. A merely-early
    segment with no gap is the SAME company trading before index inclusion, and is
    kept as legitimate lookback.
    """
    empty = pd.Series(dtype=float)
    if s is None or len(s) == 0 or tenure_start is None or pd.isna(tenure_start):
        return (s if s is not None else empty), empty
    s = s.sort_index()
    gaps = s.index.to_series().diff().dt.days
    # segment id increments at every hole >= gap_days
    seg = (gaps >= gap_days).fillna(False).cumsum().values
    keep_mask = pd.Series(True, index=s.index)
    for sid in pd.unique(seg):
        block = s.index[seg == sid]
        if block.max() < tenure_start:          # entirely before this holder's tenure
            keep_mask.loc[block] = False
    if keep_mask.all():
        return s, empty
    return s[keep_mask.values], s[~keep_mask.values]


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
    start = (pd.to_datetime(sub["start_date"]).min()
             - pd.Timedelta(days=TENURE_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
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
        # Stooq is unwindowed (full vendor history) and every source is fetched by
        # BARE STRING, so refuse any pre-tenure segment behind an identity seam
        # before it can reach the store.
        n_foreign = 0
        if s is not None:
            bounds = tenure_bounds(t, mem)
            s, foreign = split_identity_seam(s, bounds[0] if bounds else None)
            n_foreign = int(len(foreign))
            if n_foreign:
                print(f"::warning title=dead-name-splice::{t}: refused {n_foreign} pre-tenure "
                      f"bar(s) ending {foreign.index.max().date()} — string held by another "
                      f"registrant before {bounds[0].date()}", flush=True)
        seen[t] = {"at": now, "source": src if s is not None else None,
                   "n": int(len(s)) if s is not None else 0,
                   "refused_pre_tenure": n_foreign}
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


def _still_trading(tickers: set[str], fresh_days: int = 45) -> list[str]:
    """Dead-universe names that STILL have a live, advancing per-ticker store — i.e.
    names that left the S&P index but never died. Index-only, so it stays cheap."""
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=fresh_days)
    alive = []
    for t in sorted(tickers):
        for store in ("baskets/ohlcv", "stocks"):
            p = config.data_dir() / store / f"{t}.parquet"
            if not p.exists():
                continue
            try:
                idx = pd.to_datetime(pd.read_parquet(p, columns=[]).index)
            except Exception:  # noqa: BLE001 — corruption is audit_prices' beat
                continue
            if len(idx) and idx.max() >= cutoff:
                alive.append(t)
                break
    return alive


def _universe_basis_caveat(universe: list[str], with_px: set[str]) -> dict:
    """The caveat that outranks acquisition skew: this universe is an INDEX-EXIT set,
    not a death set. `dead_universe()` selects a CLOSED S&P membership, and a name
    leaves the index for a market-cap drop as readily as for a merger — so a sizeable
    minority of "dead" names are alive and still trading. Their recovered prices are
    genuine (their own tape, truncated at the fetch bound), but calling the resulting
    panel de-biased for SURVIVORSHIP overstates it: the alive cohort is not a
    survivorship correction, and the delisted cohort is what remains."""
    try:
        alive = _still_trading(set(universe))
        alive_px = sorted(set(alive) & with_px)
    except Exception:  # noqa: BLE001 — never let a caveat break the stamp
        return {"basis": "sp1500_pit_membership.end_date NOT NULL", "measured": False}
    n = len(universe) or 1
    return {
        "basis": "sp1500_pit_membership.end_date NOT NULL (INDEX EXIT, not death)",
        "measured": True,
        "n_universe": len(universe),
        "n_still_trading": len(alive),
        "still_trading_frac": round(len(alive) / n, 4),
        "n_still_trading_with_prices": len(alive_px),
        "caveat": (
            f"{len(alive)} of {len(universe)} names in this 'dead' universe "
            f"({round(100 * len(alive) / n, 1)}%) still have a live advancing price store: "
            "they were REMOVED FROM THE INDEX, not delisted. Their recovered rows are "
            "their own genuine prices (bounded by the fetch window, not by a death), so "
            "they must NOT be trimmed to a 'death date' — but neither do they correct "
            "survivorship. Any study calling this panel de-biased should partition "
            "index-exit-alive from truly-delisted before claiming a survivorship fix."),
    }


def _splice_quarantine_stamp() -> dict:
    """Identity splices removed by scripts/heal_dead_name_prices (bare-string fetches
    that welded a prior registrant onto the current one under one ticker key)."""
    p = config.data_dir() / "quarantine" / "dead_name_prices_spliced.json"
    if not p.exists():
        return {"applied": False, "n_names": 0, "n_rows": 0,
                "note": "no splice quarantine on record — run scripts/heal_dead_name_prices"}
    try:
        m = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {"applied": False, "n_names": 0, "n_rows": 0, "note": "manifest unreadable"}
    return {
        "applied": bool(m.get("applied")),
        "n_names": int(m.get("n_names_spliced") or 0),
        "n_rows": int(m.get("n_rows_quarantined") or 0),
        "names": [f["ticker"] for f in (m.get("findings") or [])],
        "manifest": "data/quarantine/dead_name_prices_spliced.json",
        "note": ("A ticker string is a mutable key: fetching by bare string can weld a "
                 "prior registrant's tape onto the current one. Refused rows are "
                 "quarantined, never deleted."),
    }


def price_coverage() -> dict:
    """Honest dead-name PRICE coverage + the delisting-reason breakdown + the
    residual-bias caveat (softened once bankruptcies are imputed). Writes
    data/edgar/_dead_name_price_coverage.json."""
    universe = dead_universe()
    cache = _load_cik_cache()
    resolved = {t for t, v in cache.items() if v.get("cik")}
    p = _prices_path()
    with_px = set()
    by_source: dict[str, int] = {}
    n_imputed_bk = 0
    if p.exists():
        df = pd.read_parquet(p, columns=["ticker", "source"])
        with_px = set(df["ticker"])
        for src, n in df.drop_duplicates("ticker")["source"].value_counts().items():
            by_source[str(src)] = int(n)
        n_imputed_bk = int(df[df["source"] == "imputed_bankruptcy"]["ticker"].nunique())
    n = len(universe)

    # delisting-reason split (acquisition / bankruptcy / unknown) from the Ch.11 8-K
    # feed (collectors/edgar_delisting). Late import avoids a module-load cycle.
    try:
        from collectors.edgar_delisting import delisting_breakdown
        reasons = delisting_breakdown(universe)
    except Exception:  # noqa: BLE001
        reasons = {"bankruptcy": 0, "acquisition": 0, "unknown": 0, "n_classified": 0}

    if n_imputed_bk:
        residual = (
            f"Acquisition skew is now PARTLY corrected: {n_imputed_bk} bankruptcy "
            "delistings (8-K Item 1.03) carry an imputed −100% terminal close "
            "(source=imputed_bankruptcy), so the price→0 tail is no longer a silent "
            "survivorship gap. RESIDUAL: bankruptcy names with no recovered price "
            "anchor can't be imputed (no from-price), and the recovered set still "
            "skews to ACQUISITIONS for names not yet reason-classified.")
    else:
        residual = (
            "Recovered names skew to ACQUISITIONS (price ran to a deal and stopped); "
            "the BANKRUPTCY tail (price→0) is under-served by free sources, so "
            "recovered prices keep a mild UP bias. Run collectors/edgar_delisting to "
            "impute −100% terminals from a delisting-reason feed (Ch.11 8-Ks, Item 1.03).")

    out = {
        "schema": "dead_name_price_coverage.v3",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_dead_universe": n,
        "n_cik_resolved": len(resolved & set(universe)),
        "n_with_prices": len(with_px & set(universe)),
        "price_coverage_frac": round(len(with_px & set(universe)) / n, 4) if n else 0.0,
        "by_source": by_source,
        "delisting_reason": reasons,
        "n_imputed_bankruptcies": n_imputed_bk,
        "residual_bias": residual,
        "universe_basis": _universe_basis_caveat(universe, with_px),
        "identity_splice_quarantine": _splice_quarantine_stamp(),
        "note": "yfinance ~0 on delisted; Stooq/Polygon are IP-gated → this accrues in CI.",
    }
    (config.data_dir() / "edgar" / "_dead_name_price_coverage.json").write_text(json.dumps(out, indent=1))
    return out
