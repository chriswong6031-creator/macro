"""Per-stock Southbound Stock-Connect holdings — Hong Kong's marginal-buyer signal.

Southbound Connect (港股通) is mainland money buying HK-listed shares — the single
most-watched HK capital flow. Per research/CHINA_HK_STOCK_SIGNALS.md (Phase 4, flagged
but never built) it is "a China-specific *smart-money* signal with no US analog, free
from Eastmoney". HK has NO idiosyncratic stock-selection alpha (residual momentum is
DEAD here — its long-short Sharpe is negative on a 40-year panel), so the honest
per-name edges are STRUCTURAL: global-risk beta, A/H value, and THIS — where the
dominant marginal buyer is putting its money.

Source — the Eastmoney datacenter report ``RPT_MUTUAL_STOCK_HOLDRANKS`` (the same
``datacenter-web.eastmoney.com`` host the China leaderboard in ``build_china`` already
uses). Per HK name, for the latest disclosed Connect-holdings date:

  HOLD_MARKET_CAP        mainland holding value (HKD)                   ownership LEVEL
  HOLD_SHARES_RATIO      % of issued shares held via Connect            ownership LEVEL
  FREE_SHARES_RATIO      % of the FREE FLOAT held via Connect           ownership LEVEL
  HOLD_MARKETCAP_CHG5/10 5- / 10-day change in holding value (%)        accumulation MOMENTUM
  ADD_SHARES_AMP         today's share-count change amplitude (%)       net-buying intensity

The per-name signal is a cross-sectional z of recent ACCUMULATION (is mainland money
adding to this name vs the rest of the HK universe?) tilted by ownership conviction —
framed as a flow CONFIRMER / context leg, NEVER a standalone alpha. Flow-following
carries crowding + reversal risk: size to it, don't chase it.

Architecture: best-effort build-time fetch (like ``build_china._leaderboard``), with
every successful snapshot persisted long-form to ``data/hk_southbound/holdings.parquet``
so a per-name flow history accrues for future deep-history validation. ``latest_*``
reads the store first and only fetches when the store is missing/stale, so a flaky
Eastmoney backend degrades to the last good snapshot instead of dropping the signal.
"""
from __future__ import annotations

import json
import logging
from datetime import date as _date
import time

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

_DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_H = {"User-Agent": _UA, "Referer": "https://data.eastmoney.com/"}
# southbound legs: 003 = 港股通(沪), 004 = 港股通(深) — mainland -> HK
_SB_TYPES = ("003", "004")
_GROUP = "hk_southbound"
_NAME = "holdings"

NOTE = ("Per HK name: how much of it the mainland Connect crowd holds (% of free "
        "float) and whether it is ADDING (5-/10-day change in holding value). HK's "
        "dominant marginal buyer — a flow confirmer for sizing, not a standalone alpha.")


def _normalize(secucode: str) -> str | None:
    """Eastmoney ``00700.HK`` (5-digit) -> our universe ``0700.HK`` (4-digit + .HK)."""
    if not secucode or "." not in secucode:
        return None
    num = secucode.split(".")[0].lstrip("0") or "0"
    if not num.isdigit():
        return None
    return f"{int(num):04d}.HK"


def _store_path():
    d = config.data_dir() / _GROUP
    return d / f"{_NAME}.parquet"


# ── fetch ───────────────────────────────────────────────────────────────────
def _fetch_page(page: int, retries: int, timeout: int) -> list[dict]:
    import requests
    flt = '(MUTUAL_TYPE in ("%s"))(INTERVAL_TYPE="1")' % '","'.join(_SB_TYPES)
    p = {"reportName": "RPT_MUTUAL_STOCK_HOLDRANKS", "columns": "ALL",
         "pageSize": 500, "pageNumber": page, "sortColumns": "HOLD_DATE",
         "sortTypes": -1, "filter": flt}
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(_DC, params=p, headers=_H, timeout=timeout)
            return (r.json().get("result") or {}).get("data") or []
        except Exception as e:  # noqa: BLE001 — Eastmoney closes flaky connections
            last = e
            time.sleep(1.5 * (attempt + 1))
    log.warning("hk_southbound: page %d failed after %d tries (%s)", page, retries, last)
    return []


def fetch_snapshot(*, persist: bool = True, retries: int = 4, timeout: int = 25,
                   max_pages: int = 4) -> pd.DataFrame | None:
    """Latest per-stock southbound holdings cross-section, indexed by our ticker
    (e.g. ``0700.HK``). Rows are sorted HOLD_DATE-desc, so the latest date's full
    cross-section comes first; we collect pages until the date rolls back. Best-effort
    — returns None (never raises) when the backend is unreachable."""
    rows: list[dict] = []
    hold_date: str | None = None
    for page in range(1, max_pages + 1):
        data = _fetch_page(page, retries, timeout)
        if not data:
            break
        if hold_date is None:
            hold_date = max(x.get("HOLD_DATE") or "" for x in data)
        page_rows = [x for x in data if (x.get("HOLD_DATE") or "") == hold_date]
        rows.extend(page_rows)
        if len(page_rows) < len(data):     # this page rolled past the latest date
            break
    if not rows or not hold_date:
        log.warning("hk_southbound: no rows returned")
        return None

    def f(x, k):
        v = x.get(k)
        try:
            return float(v) if v is not None else np.nan
        except (TypeError, ValueError):
            return np.nan

    recs = {}
    for x in rows:
        t = _normalize(x.get("SECUCODE") or "")
        if not t or t in recs:                  # keep the first (each ticker once/date)
            continue
        recs[t] = {
            "name": x.get("SECURITY_NAME"),
            "hold_mktcap": f(x, "HOLD_MARKET_CAP"),     # mainland holding value (HKD)
            "hold_shares": f(x, "HOLD_SHARES"),
            "own_pct": f(x, "HOLD_SHARES_RATIO"),       # % of issued shares (ownership level)
            "free_pct": f(x, "FREE_SHARES_RATIO"),      # % of free float (often null)
            "chg5_v": f(x, "HOLD_MARKETCAP_CHG5"),      # 5d holding-VALUE change (HKD, abs)
            "chg10_v": f(x, "HOLD_MARKETCAP_CHG10"),    # 10d holding-VALUE change (HKD, abs)
            "add_amp": f(x, "ADD_SHARES_AMP"),          # today's % share-count change (pure flow)
            "close": f(x, "CLOSE_PRICE"),
        }
    if not recs:
        return None
    df = pd.DataFrame.from_dict(recs, orient="index")
    df.index.name = "ticker"
    df["date"] = pd.Timestamp(hold_date[:10])
    if persist:
        _persist(df)
    log.info("hk_southbound: %d names as of %s", len(df), hold_date[:10])
    return df



def _write_gap_audit(all_dates: list) -> None:
    """Write a gap-detection tripwire JSON to ``data/hk_southbound/backfill_gap_audit.json``.

    Flags any gap >3 business days between consecutive captured HOLD_DATEs.  Verdict is
    ``"OK"`` when no such gap exists, ``"GAPS_DETECTED"`` otherwise.  Called after every
    successful ``_persist`` write so the tripwire stays current.
    """
    try:
        dates_sorted = sorted(str(d)[:10] for d in all_dates if d)
        gaps = []
        for i in range(1, len(dates_sorted)):
            d0 = dates_sorted[i - 1]
            d1 = dates_sorted[i]
            bd = int(np.busday_count(d0, d1))
            if bd > 3:
                gaps.append({"from": d0, "to": d1, "bdays": bd})
        audit = {
            "updated": str(_date.today()),
            "n_dates": len(dates_sorted),
            "earliest": dates_sorted[0] if dates_sorted else None,
            "latest": dates_sorted[-1] if dates_sorted else None,
            "n_gaps": len(gaps),
            "gaps": gaps,
            "verdict": "GAPS_DETECTED" if gaps else "OK",
        }
        path = _store_path().parent / "backfill_gap_audit.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(audit, indent=2))
    except Exception as e:  # noqa: BLE001 -- tripwire write must never break collect
        log.debug("hk_southbound gap audit write skipped (%s)", e)


def _persist(df: pd.DataFrame) -> None:
    """Append the snapshot long-form to ``data/hk_southbound/holdings.parquet`` keyed by
    (date, ticker), keeping prior dates — a per-name flow history accrues over time.
    Best-effort: a write failure never breaks the build (the signal still uses the
    in-memory snapshot). After each successful write, updates the gap-detection tripwire."""
    try:
        path = _store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        new = df.reset_index().set_index(["date", "ticker"]).sort_index()
        if path.exists():
            old = pd.read_parquet(path)
            if not isinstance(old.index, pd.MultiIndex):
                old = None
            else:
                merged = new.combine_first(old)
                merged = merged[~merged.index.duplicated(keep="first")].sort_index()
                merged.to_parquet(path)
                _write_gap_audit(list(merged.index.get_level_values("date").unique()))
                return
        new.to_parquet(path)
        _write_gap_audit(list(new.index.get_level_values("date").unique()))
    except Exception as e:  # noqa: BLE001 — persistence is additive, never fatal
        log.debug("hk_southbound persist skipped (%s)", e)


def latest_holdings(*, allow_fetch: bool = True) -> pd.DataFrame | None:
    """The latest stored southbound cross-section (index = ticker). Reads the persisted
    parquet first; falls back to a live fetch when the store is missing. Returns None if
    neither yields data so callers silently omit the panel."""
    path = _store_path()
    if path.exists():
        try:
            hist = pd.read_parquet(path)
            if isinstance(hist.index, pd.MultiIndex) and len(hist):
                last = hist.index.get_level_values("date").max()
                snap = hist.xs(last, level="date").copy()
                snap["date"] = last
                return snap
        except Exception as e:  # noqa: BLE001
            log.debug("hk_southbound store unreadable (%s)", e)
    return fetch_snapshot() if allow_fetch else None


# ── per-name signal ───────────────────────────────────────────────────────────
def _zscore(s) -> pd.Series:
    if s is None or not isinstance(s, pd.Series):
        return pd.Series(dtype=float)
    s = pd.to_numeric(s, errors="coerce")
    mu, sd = s.mean(), s.std(ddof=0)
    if not sd or np.isnan(sd):
        return pd.Series(0.0, index=s.index)
    return ((s - mu) / sd).clip(-3.0, 3.0)


# the holding-VALUE change is in absolute HKD (and price-contaminated). Normalize to a %
# of the holding (so a mega-cap and a mid-cap are comparable) and clip the share-flow
# amplitude (micro-caps / share-base 'repairs' throw absurd ADD_SHARES_AMP outliers).
def _value_pct(chg_abs: pd.Series, hold: pd.Series) -> pd.Series:
    """abs holding-value change -> % change in the holding (base = value BEFORE the change)."""
    base = pd.to_numeric(hold, errors="coerce") - pd.to_numeric(chg_abs, errors="coerce")
    pct = pd.to_numeric(chg_abs, errors="coerce") / base.where(base.abs() > 1e6) * 100.0
    return pct.clip(-60.0, 60.0)


def _share_flow_5d(tickers: list[str]) -> pd.Series | None:
    """Clean 5-day NET-SHARE flow (% change in Connect shares held), derived from the
    accrued snapshot history when ≥2 dates exist — price-independent, the purest
    accumulation read. None until the persisted history has depth (the live signal then
    falls back to today's ADD_SHARES_AMP + the value-change proxy)."""
    path = _store_path()
    if not path.exists():
        return None
    try:
        hist = pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(hist.index, pd.MultiIndex) or "hold_shares" not in hist.columns:
        return None
    shares = hist["hold_shares"].unstack("ticker").sort_index()
    if len(shares) < 2:
        return None
    win = min(5, len(shares) - 1)
    flow = (shares.iloc[-1] / shares.iloc[-1 - win] - 1.0) * 100.0
    flow = flow.reindex(tickers).clip(-60.0, 60.0)
    return flow if flow.notna().sum() >= 8 else None


def signal(tickers: list[str] | None = None, snap: pd.DataFrame | None = None) -> dict[str, dict]:
    """Per-ticker southbound smart-money signal, cross-sectionally standardized over the
    analyzable HK universe. ``accum_z`` measures whether the mainland Connect crowd is
    ADDING to this name vs the rest of the universe — a multi-day net-share flow once the
    snapshot history has depth, else today's % share-add amplitude blended with the 5-/10-
    day holding-value growth. ``own_pct`` is the Connect % of issued shares (ownership
    conviction, context). Returns {} when no snapshot is available.

    Restricting to ``tickers`` anchors the z to the large-cap universe so a thin-float
    micro-cap's repair print can't distort the standardization."""
    if snap is None:
        snap = latest_holdings()
    if snap is None or snap.empty:
        return {}
    df = snap.copy()
    if tickers is not None:
        df = df[df.index.isin(set(tickers))]
    if len(df) < 8:
        return {}
    add = pd.to_numeric(df.get("add_amp"), errors="coerce").clip(-30.0, 30.0)
    chg5p = _value_pct(df.get("chg5_v"), df["hold_mktcap"])
    chg10p = _value_pct(df.get("chg10_v"), df["hold_mktcap"])
    flow5 = _share_flow_5d(list(df.index))         # clean net-share flow when history is deep
    if flow5 is not None:
        # net-share flow leads (weight 2) once history is deep; renormalize the blend over
        # the legs PRESENT per name so a name missing flow5 isn't silently re-weighted.
        legs, weights = {"flow5": _zscore(flow5), "chg5p": _zscore(chg5p),
                         "add": _zscore(add)}, {"flow5": 2.0, "chg5p": 1.0, "add": 1.0}
        basis = "net-share flow (5d)"
    else:
        legs = {"add": _zscore(add), "chg5p": _zscore(chg5p), "chg10p": _zscore(chg10p)}
        weights = {"add": 1.0, "chg5p": 1.0, "chg10p": 1.0}
        basis = "holding growth (value + share-add)"
    zdf = pd.DataFrame(legs)
    w = pd.Series(weights)
    den = (zdf.notna() * w).sum(axis=1)
    accum = (zdf.fillna(0.0) * w).sum(axis=1) / den.where(den > 0)
    accum_z = _zscore(accum)
    own_z = _zscore(df.get("own_pct"))
    out: dict[str, dict] = {}
    for t in df.index:
        az = accum_z.get(t)
        if az is None or np.isnan(az):
            continue
        oz = own_z.get(t)
        op = df.at[t, "own_pct"]
        c5 = chg5p.get(t)
        lab = ("accumulating" if az >= 0.6 else "distributing" if az <= -0.6 else "steady")
        out[t] = {
            "accum_z": round(float(az), 2),
            "own_z": round(float(oz), 2) if oz is not None and not np.isnan(oz) else None,
            "own_pct": round(float(op), 1) if op is not None and not np.isnan(op) else None,
            "chg5_pct": round(float(c5), 1) if c5 is not None and not np.isnan(c5) else None,
            "hold_b": round(float(df.at[t, "hold_mktcap"]) / 1e9, 1)
                      if not np.isnan(df.at[t, "hold_mktcap"]) else None,
            "label": lab, "basis": basis,
        }
    return out


def market_summary(snap: pd.DataFrame | None = None, n: int = 6,
                   min_hold_b: float = 0.5) -> dict | None:
    """Top mainland ACCUMULATING / DISTRIBUTING HK names for the stocks-page flows desk —
    the market-wide 'where is southbound money going' read. Ranked by the % growth in
    mainland holding value over 5 days, among names with a meaningful (≥min_hold_b ¥B)
    holding so a micro-cap print can't top the board. Display-only."""
    if snap is None:
        snap = latest_holdings()
    if snap is None or snap.empty:
        return None
    df = snap.copy()
    df["chg5p"] = _value_pct(df.get("chg5_v"), df["hold_mktcap"])
    df["hold_b"] = pd.to_numeric(df["hold_mktcap"], errors="coerce") / 1e9
    rich = df.dropna(subset=["chg5p"])
    rich = rich[rich["hold_b"] >= min_hold_b]
    if len(rich) < 6:
        return None

    def rows(frame: pd.DataFrame) -> list[dict]:
        out = []
        for t, r in frame.iterrows():
            out.append({"ticker": t, "name": r.get("name"),
                        "chg5_pct": round(float(r["chg5p"]), 1),
                        "own_pct": round(float(r["own_pct"]), 1)
                                   if not np.isnan(r.get("own_pct", np.nan)) else None,
                        "hold_b": round(float(r["hold_b"]), 1)})
        return out
    buying = rich.sort_values("chg5p", ascending=False).head(n)
    selling = rich.sort_values("chg5p").head(n)
    return {"as_of": str(pd.Timestamp(df["date"].iloc[0]).date()) if "date" in df.columns else None,
            "n": int(len(df)), "n_sized": int(len(rich)), "note": NOTE,
            "buying": rows(buying), "selling": rows(selling)}


def sb_persist_map(tickers: list[str] | None = None,
                   min_sessions: int = 3) -> dict[str, bool]:
    """Per-ticker boolean: True when the name has had ≥ ``min_sessions`` consecutive
    positive net-share-flow sessions in the most recent trailing history.

    Uses the accrued ``data/hk_southbound/holdings.parquet`` (per-date, per-ticker
    hold_shares). Positive session = net share-add vs the prior date.  Returns {}
    when the store is missing / too thin (< min_sessions + 1 dates).

    Only the positional `tickers` filter is applied; all names are included when
    None.  Best-effort: returns {} on any read error so callers degrade gracefully."""
    path = _store_path()
    if not path.exists():
        return {}
    try:
        hist = pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(hist.index, pd.MultiIndex) or "hold_shares" not in hist.columns:
        return {}
    shares = hist["hold_shares"].unstack("ticker").sort_index()
    if len(shares) < min_sessions + 1:
        return {}
    if tickers is not None:
        shares = shares.reindex(columns=tickers)
    # daily net share change: positive = adding, negative = distributing
    daily_chg = shares.diff().tail(min_sessions + 1)
    if len(daily_chg) < min_sessions:
        return {}
    # the LAST min_sessions rows (drop the first which is NaN from diff)
    last_n = daily_chg.dropna(how="all").tail(min_sessions)
    out: dict[str, bool] = {}
    for t in last_n.columns:
        col = last_n[t].dropna()
        if len(col) >= min_sessions:
            out[t] = bool((col > 0).all())
        else:
            out[t] = False
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    snap = fetch_snapshot()
    if snap is None:
        print("fetch_snapshot(): None (Eastmoney unreachable)")
    else:
        print(f"southbound holdings: {len(snap)} names as of {snap['date'].iloc[0].date()}")
        sig = signal(snap=snap)
        print(f"signal: {len(sig)} names z-scored")
        ms = market_summary(snap)
        if ms:
            print(f"top accumulating (of {ms['n_sized']} sized names):")
            for r in ms["buying"][:5]:
                print(f"  {r['ticker']:>9} {r['name']:<16} hold¥{r['hold_b']}B  +{r['chg5_pct']}% (5d)  own {r['own_pct']}%")
