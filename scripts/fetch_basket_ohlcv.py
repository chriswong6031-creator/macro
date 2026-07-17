"""Fetch the baskets-only DEEP OHLCV store the consolidated-index engines render over.

Sibling of scripts/fetch_basket_extras.py. That store is CLOSE-ONLY (the EW level +
perf table need only closes). The consolidated-index engines (engine/basket_index ->
engine/basket_mtf + engine/basket_tape) need full OHLCV per member to build a real
basket CANDLE: open/high/low/close for ATR/Bollinger/vol-hole and VOLUME for whale
accumulation, Chaikin money-flow (net inflow/outflow) and dollar-volume. Only ~21% of
members had volume on disk (data/stocks/*.parquet); the rest were close-only — so this
backfills the gap for EVERY member.

    data/baskets/ohlcv/<TICKER>.parquet   per-ticker [open,high,low,close,volume], deep

Kept SEPARATE from the breadth/factor universe (the free-S&P-1500 invariant) and from
data/stocks (the US-stock-library deep store) so neither is polluted by off-index basket
names. engine/basket_index PREFERS this store, then falls back to data/stocks (already
OHLCV) and the yahoo store (close+volume) for names it lacks — so a flaky pull degrades
gracefully rather than dropping a basket.

Keyless (yfinance), batched, auto-adjusted. Additive and non-fatal: each ticker's fresh
pull is MERGED onto its prior parquet (prior backfills any row the pull missed), so a
flaky day can never drop a member or break the daily build. Wired into scripts/collect.py
after fetch_basket_extras.

Usage:
    python -m scripts.fetch_basket_ohlcv [--limit N]               # the basket membership
    python -m scripts.fetch_basket_ohlcv --tickers NVDA,ANET,...   # an explicit list
    python -m scripts.fetch_basket_ohlcv --finviz idx_ndx,idx_rut  # every name in a
                                                                   # data/finviz_screener/<flt>.json
    python -m scripts.fetch_basket_ohlcv --finviz ... --members    # index universes UNIONED
                                                                   # with the basket membership
    python -m scripts.fetch_basket_ohlcv --census                  # no fetch; per-member
                                                                   # staleness tripwire only
The explicit/finviz modes back the NDX/Russell subsector desks (the deep store
engine/basket_index prefers also serves their EW subsector indices). An explicit universe
REPLACES the membership default — pass --members to union it back in. The nightly call
must keep membership covered (2026-07-16 incident: PR #776 switched collect.py to
--finviz-only and 528 member files silently froze at 2026-06-29 for 11 sessions while the
aggregate as_of stayed fresh off the NDX/RUT names; check_membership_staleness below is
the per-member tripwire that makes that failure mode visible).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("fetch_basket_ohlcv")

# Deep enough that the MONTHLY MTF timeframe (engine.cycles needs ~900 trading days ≈
# 3.6y of month-end bars) resolves for any member with a long-enough listing.
START = "2014-01-01"
RETRIES = 4
BACKOFF_S = 3.0
BATCH = 40                  # tickers per yfinance download call (5 OHLCV fields each)
COLS = ["open", "high", "low", "close", "volume"]

# membership ticker -> the symbol yfinance actually resolves it under (renames where
# Yahoo only keeps the OLD symbol's series). Fetched under the value, stored under the key.
ALIASES = {"FI": "FISV"}    # Fiserv renamed FISV->FI in 2023; Yahoo still serves the FISV series


def _membership_tickers() -> list[str]:
    p = config.data_dir() / "baskets" / "membership.json"
    if not p.exists():
        return []
    mem = json.loads(p.read_text())
    bdict = mem.get("baskets") or {}
    items = bdict.values() if isinstance(bdict, dict) else bdict
    out: set[str] = set()
    for b in items:
        for m in b.get("members", []):
            t = m.get("ticker")
            if t:
                out.add(t)
    return sorted(out)


def _finviz_tickers(filters: list[str]) -> list[str]:
    """Every ticker in the given data/finviz_screener/<flt>.json classification files."""
    out: set[str] = set()
    base = config.data_dir() / "finviz_screener"
    for flt in filters:
        p = base / f"{flt}.json"
        if not p.exists():
            log.warning("finviz classification missing: %s", p)
            continue
        for r in (json.loads(p.read_text()).get("rows") or []):
            t = r.get("ticker")
            if t:
                out.add(t)
    return sorted(out)


def _resolve_universe(explicit: list[str], fv: list[str], with_members: bool) -> list[str]:
    """The tickers a run maintains. Membership is the default universe; an explicit
    --tickers/--finviz set replaces it unless with_members unions it back in."""
    pool: set[str] = set(explicit) | set(fv)
    if with_members or not pool:
        pool |= set(_membership_tickers())
    return sorted(pool)


# ------------------------------------------------------------------ staleness tripwire
STALE_SESSIONS = 3          # warn when a member's last row lags the store max by more


def _last_row_date(p: Path) -> date | None:
    """Last-row date of a per-ticker parquet from the footer (last row group, date column
    only) — cheap enough to census the whole store nightly."""
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(p)
    names = pf.schema_arrow.names
    dc = next((c for c in ("date", "Date", "timestamp", "__index_level_0__") if c in names), None)
    if dc is None:
        return None
    tbl = pf.read_row_group(pf.metadata.num_row_groups - 1, columns=[dc])
    v = tbl.column(0)[-1].as_py()
    return v.date() if isinstance(v, datetime) else (v if isinstance(v, date) else None)


def _sessions_behind(behind: date, ref: date) -> int:
    """NYSE sessions strictly after `behind`, up to and including `ref`."""
    from lib import nyse_calendar
    n, d = 0, behind + timedelta(days=1)
    while d <= ref:
        if nyse_calendar.is_session(d):
            n += 1
        d += timedelta(days=1)
    return n


def check_membership_staleness(odir: Path | None = None, members: list[str] | None = None,
                               threshold: int = STALE_SESSIONS, ops_alert: bool = True) -> dict:
    """Per-member freshness tripwire over the deep OHLCV store. WARN-ONLY — never raises,
    never blocks. Compares every active basket member's last-row date to the store-wide
    max and flags any lag > threshold sessions, plus members with no file at all.

    Exists because the whole-store check (build_baskets._check_basket_store_staleness,
    M7C-R8) is blind to a frozen SUBSET: 2026-07-16, #776 dropped the membership universe
    from the nightly pull and 528 member files froze for 11 sessions while the aggregate
    as_of stayed fresh — basket candles silently rendered from partial membership.
    Writes data/quality/basket_ohlcv_freshness.json and returns the payload."""
    payload: dict = {"status": "error", "checked_at": datetime.now(timezone.utc).isoformat(),
                     "threshold_sessions": threshold}
    try:
        odir = odir or (config.data_dir() / "baskets" / "ohlcv")
        members = _membership_tickers() if members is None else members
        last: dict[str, date] = {}
        for p in odir.glob("*.parquet"):
            try:
                d = _last_row_date(p)
                if d is not None:
                    last[p.stem] = d
            except Exception as e:  # noqa: BLE001 — one bad file must not kill the census
                log.warning("staleness census: unreadable %s: %s", p.name, e)
        if not last:
            payload["status"] = "no_store"
            _write_freshness_marker(payload)
            return payload
        store_max = max(last.values())
        stale: dict[str, dict] = {}
        behind_ok = 0
        missing = sorted(t for t in members if t not in last)
        for t in members:
            d = last.get(t)
            if d is None or d >= store_max:
                continue
            lag = _sessions_behind(d, store_max)
            if lag > threshold:
                stale[t] = {"last": d.isoformat(), "sessions_behind": lag}
            elif lag > 0:
                behind_ok += 1
        payload.update({
            "status": "stale" if (stale or missing) else "ok",
            "store_max": store_max.isoformat(), "n_members": len(members),
            "n_stale": len(stale), "n_behind_within_threshold": behind_ok,
            "stale": dict(sorted(stale.items(), key=lambda kv: -kv[1]["sessions_behind"])),
            "missing": missing,
        })
        if stale or missing:
            worst = max(stale.items(), key=lambda kv: kv[1]["sessions_behind"]) if stale else None
            msg = (f"basket OHLCV store: {len(stale)} active members stale >{threshold} sessions "
                   f"vs store max {store_max}"
                   + (f" (worst {worst[0]} @ {worst[1]['last']}, {worst[1]['sessions_behind']} behind)" if worst else "")
                   + (f"; {len(missing)} members with no file: {', '.join(missing[:8])}" if missing else "")
                   + " — the per-member pull is failing or the nightly call lost membership "
                     "coverage; see data/quality/basket_ohlcv_freshness.json")
            print(f"::warning ::{msg}", flush=True)
            log.warning(msg)
            if ops_alert:
                try:
                    from engine.alert_triage import push_ops_alert  # noqa: PLC0415
                    push_ops_alert(source="fetch_basket_ohlcv", type_="basket_member_ohlcv_stale",
                                   message=msg, severity="major", lane="collect", window_hours=20)
                except Exception as e:  # noqa: BLE001 — fail-open, the ::warning stands
                    log.debug("staleness census: push_ops_alert unavailable (%s)", e)
    except Exception as e:  # noqa: BLE001 — tripwire must never crash the collect lane
        log.warning("basket OHLCV staleness census failed: %s", e)
        payload["error"] = str(e)
    _write_freshness_marker(payload)
    return payload


def _write_freshness_marker(payload: dict) -> None:
    try:
        p = config.data_dir() / "quality" / "basket_ohlcv_freshness.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=2))
    except Exception as e:  # noqa: BLE001 — the marker is advisory, never the gate
        log.warning("freshness marker write failed: %s", e)


def _scrub_placeholder_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Zero/negative "prices" are vendor placeholders, not trades (e.g. DEC shipped ~3y of
    all-zero OHLC rows with nonzero volume from before its US listing). Mask them to NaN —
    the same guard engine/basket_index applies at read time — and drop rows left with no
    price at all. Runs on the MERGED frame so a refresh purges prior garbage instead of
    re-persisting it via combine_first."""
    px = [c for c in ("open", "high", "low", "close") if c in df.columns]
    df[px] = df[px].where(df[px] > 0)
    return df[df[px].notna().any(axis=1)]


def _download_ohlcv(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Per-ticker OHLCV frames, deep from START. Reuses the breadth yfinance pattern
    (crumb/cookie auth that works headless), batched with retry+backoff. group_by=ticker
    so each name comes back as its own Open/High/Low/Close/Volume block."""
    import yfinance as yf
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), BATCH):
        batch = tickers[i:i + BATCH]
        for attempt in range(RETRIES):
            try:
                df = yf.download(batch, start=START, auto_adjust=True, progress=False,
                                 group_by="ticker", threads=True)
                if df is None or df.empty:
                    raise RuntimeError("empty frame")
                # Single-ticker downloads come back flat (no ticker level) — normalise.
                if not isinstance(df.columns, pd.MultiIndex):
                    df.columns = pd.MultiIndex.from_product([[batch[0]], df.columns])
                for t in batch:
                    if t not in df.columns.get_level_values(0):
                        continue
                    sub = df[t][["Open", "High", "Low", "Close", "Volume"]].copy()
                    sub.columns = COLS
                    sub = sub.dropna(how="all")
                    if not sub.empty:
                        out[t] = sub.sort_index()
                break
            except Exception as e:  # noqa: BLE001
                wait = BACKOFF_S * (2 ** attempt)
                log.warning("batch %d/%d (%s…) attempt %d failed (%s); retry in %.0fs",
                            i // BATCH + 1, (len(tickers) - 1) // BATCH + 1, batch[0],
                            attempt + 1, e, wait)
                time.sleep(wait)
        else:
            log.error("batch starting %s failed after %d retries — leaving to prior store", batch[0], RETRIES)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap tickers (debug)")
    ap.add_argument("--tickers", default="", help="explicit comma-separated ticker list")
    ap.add_argument("--finviz", default="", help="comma-separated finviz_screener filters "
                                                 "(e.g. idx_ndx,idx_rut) to pull every member of")
    ap.add_argument("--members", action="store_true",
                    help="union the basket membership into an explicit --tickers/--finviz "
                         "universe (it is the default only when neither is given)")
    ap.add_argument("--census", action="store_true",
                    help="skip fetching; run only the per-member staleness tripwire")
    args = ap.parse_args(argv)

    odir = config.data_dir() / "baskets" / "ohlcv"
    odir.mkdir(parents=True, exist_ok=True)

    if args.census:
        payload = check_membership_staleness(odir)
        log.info("staleness census: %s (store max %s, %s stale, %s missing)",
                 payload.get("status"), payload.get("store_max"),
                 payload.get("n_stale"), len(payload.get("missing") or []))
        return 0

    explicit = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    fv = _finviz_tickers([f.strip() for f in args.finviz.split(",") if f.strip()]) if args.finviz else []
    members = _resolve_universe(explicit, fv, args.members)
    if args.limit:
        members = members[:args.limit]
    if not members:
        log.info("no members to fetch (need data/baskets/membership.json or --tickers/--finviz)")
        return 0

    log.info("fetching deep OHLCV for %d members", len(members))
    fetch_syms = [ALIASES.get(t, t) for t in members]
    rev = {ALIASES.get(t, t): t for t in members}        # yahoo symbol -> membership ticker
    try:
        fresh = _download_ohlcv(fetch_syms)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("OHLCV fetch failed entirely, keeping prior store: %s", e)
        return 0

    wrote, kept, blank = 0, 0, []
    for t in members:
        sym = ALIASES.get(t, t)
        new = fresh.get(sym)
        out_p = odir / f"{t}.parquet"
        prior = pd.read_parquet(out_p) if out_p.exists() else None
        if new is None or new.empty:
            if prior is None:
                blank.append(t)
            else:
                kept += 1            # flaky pull — prior store stands
            continue
        new = new.rename_axis("Date")
        merged = new if prior is None else new.combine_first(prior)
        merged.index = pd.DatetimeIndex(merged.index)
        merged.index.name = "Date"
        merged = merged.sort_index()[COLS]
        merged = _scrub_placeholder_prices(merged)
        merged.to_parquet(out_p)
        wrote += 1
    if blank:
        log.warning("no data (and no prior) for %d: %s", len(blank), ", ".join(blank))
    log.info("basket OHLCV store: wrote/updated %d, kept-prior %d, missing %d -> %s",
             wrote, kept, len(blank), odir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
