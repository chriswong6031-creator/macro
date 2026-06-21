"""Canadian insider transactions (SEDI) via yfinance — display-only context.

The Canada parallel of the US SEC Form-4 insider work (collectors/sec_insider.py),
but the data path is completely different. SEDI (sedi.ca, Canada's insider-filing
system) has NO free machine-readable feed and is CAPTCHA-walled, and every paid
vendor's insider product is US-SEC-only. The one free, programmatic path is
yfinance's undocumented Yahoo `quoteSummary` endpoint: `get_insider_transactions()`
returns SEDI-sourced, dated insider filings for many .TO names — no key, no auth.
Verified live on yfinance 1.4.1 (~150-row cap per name, ~9/13 coverage on a liquid
sample; ENB/ABX/BCE/CP came back empty — coverage is best-effort PER TICKER).

We keep only PERSONAL OPEN-MARKET trades — rows whose text says "Acquisition /
Disposition in the public market" filed by a person ("Director of Issuer", "Senior
Officer of Issuer", …) — and DROP issuer rows (Position == "Issuer" = company
buybacks) and option exercises / grants / redemptions, then summarise the net
buy/sell lean over a trailing window plus the most-recent filings.

IMPORTANT — this is CONTEXT, NOT A SIGNAL. SEDI gives insiders up to ~5 calendar
days to file, so the trade is already days old when it publishes, and TSX insider
breadth is thin — so net buying/selling is a conviction tell, not a timing trigger
(no Phase-0 cross-sectional validation yet). Mirrors the best-effort drip-cache
pattern of engine/canada_fundamentals.py (fetch_earnings / earnings_map); cached
under data/canada_insider/. yfinance is pinned at 1.4.1 (these undocumented
properties have regressed between versions).
"""
from __future__ import annotations

import json
import logging
import time

import pandas as pd

from lib import config

log = logging.getLogger("canada_insider")

CACHE = config.data_dir() / "canada_insider" / "insider.parquet"

# Re-fetch a cached name when its snapshot is older than this (days). Recent filings
# don't change, so a slow cadence is fine and keeps the per-build yfinance drip small.
INSIDER_MAX_AGE_DAYS = 12

# Defaults if the config block is absent (degrade-don't-crash).
_DEFAULTS = {"window_days": 180, "max_new_per_build": 40, "recent_n": 6, "min_shares": 0}


def _cfg() -> dict:
    try:
        c = (config.load().get("canada", {}) or {}).get("insider", {}) or {}
    except Exception:  # noqa: BLE001 — additive, never fatal
        c = {}
    return {**_DEFAULTS, **c}


def _num(v):
    try:
        if v in (None, "", "--", "—"):
            return None
        f = float(v)
        return f if f == f else None      # drop NaN
    except (TypeError, ValueError):
        return None


def _is_company(position: str) -> bool:
    """True when the filer is the ISSUER itself (a buyback), not a person. yfinance
    uses Position == "Issuer" for the company and "<role> of Issuer" for people."""
    return (position or "").strip().lower() == "issuer"


def _role(position: str) -> str:
    """Normalise the SEDI position string to a short role label."""
    p = (position or "").lower()
    if "director" in p:
        return "Director"
    if "officer" in p:
        return "Officer"
    if "10%" in p or "10 percent" in p or "ten percent" in p:
        return "10% owner"
    if p.strip() == "issuer":
        return "Issuer"
    return "Insider"


def _row_action(text: str) -> str:
    """Classify a transaction by its yfinance free-text. Only OPEN-MARKET trades
    ("…in the public market") count as buy/sell; everything else (option exercises,
    grants, redemptions, issuer repurchases) is "other" and dropped from the lean."""
    t = (text or "").lower()
    if "public market" in t:
        if "acquisition" in t or "purchase" in t:
            return "buy"
        if "disposition" in t or "sale" in t or "sold" in t:
            return "sell"
    return "other"


def _normalize_df(df) -> list[dict]:
    """Map a yfinance get_insider_transactions() DataFrame to a list of normalised
    row dicts. Pure (no I/O) so it is unit-testable with a synthetic frame. Columns
    seen on 1.4.1: Shares, Value, URL, Text, Insider, Position, Transaction,
    Start Date, Ownership (the date can also arrive as the index)."""
    if df is None or len(df) == 0:
        return []
    cols = {str(c).strip().lower(): c for c in df.columns}

    def col(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    c_date = col("start date", "startdate", "date")
    c_ins, c_pos, c_text = col("insider"), col("position"), col("text")
    c_sh, c_val = col("shares"), col("value")
    out: list[dict] = []
    for i in range(len(df)):
        r = df.iloc[i]
        raw_date = df.index[i] if c_date is None else r.get(c_date)
        ts = pd.to_datetime(raw_date, errors="coerce")
        if ts is None or pd.isna(ts):
            continue
        pos = str(r.get(c_pos) or "") if c_pos else ""
        text = str(r.get(c_text) or "") if c_text else ""
        ins = r.get(c_ins) if c_ins else None
        out.append({
            "date": ts.strftime("%Y-%m-%d"),
            "insider": str(ins).strip() if ins is not None and str(ins).strip() else None,
            "role": _role(pos),
            "personal": not _is_company(pos),
            "action": _row_action(text),
            "shares": _num(r.get(c_sh)) if c_sh else None,
            "value": _num(r.get(c_val)) if c_val else None,
        })
    return out


def _summarize(rows: list[dict], window_days: int = 180, recent_n: int = 6,
               min_shares: float = 0, now: "pd.Timestamp | None" = None) -> dict | None:
    """Net open-market personal-insider buy/sell lean over a trailing window, plus the
    most-recent filings. Pure (no I/O). None when there is nothing to show."""
    now = now if now is not None else pd.Timestamp.now()
    cut = (now - pd.Timedelta(days=window_days)).strftime("%Y-%m-%d")
    om = [r for r in rows
          if r.get("personal") and r.get("action") in ("buy", "sell")
          and r.get("date") and r["date"] >= cut
          and (min_shares <= 0 or (r.get("shares") or 0) >= min_shares)]
    if not om:
        return None

    buys = [r for r in om if r["action"] == "buy"]
    sells = [r for r in om if r["action"] == "sell"]

    def vsum(rs):
        vs = [r["value"] for r in rs if r.get("value") is not None]
        return round(sum(vs)) if vs else None

    def shsum(rs):
        ss = [r["shares"] for r in rs if r.get("shares") is not None]
        return int(sum(ss)) if ss else 0

    buy_value, sell_value = vsum(buys), vsum(sells)
    net_value = None
    if buy_value is not None or sell_value is not None:
        net_value = round((buy_value or 0) - (sell_value or 0))
    buy_sh, sell_sh = shsum(buys), shsum(sells)
    net_sh = buy_sh - sell_sh

    if buys and not sells:
        lean = "buying"
    elif sells and not buys:
        lean = "selling"
    else:
        basis = net_value if net_value not in (None, 0) else net_sh
        lean = "buying" if basis > 0 else "selling" if basis < 0 else "mixed"

    recent = sorted(om, key=lambda r: r["date"], reverse=True)[:recent_n]
    recent_out = [{"date": r["date"], "insider": r.get("insider"), "role": r.get("role"),
                   "action": r["action"],
                   "shares": int(r["shares"]) if r.get("shares") is not None else None,
                   "value": r.get("value")} for r in recent]
    return {
        "lean": lean, "window_days": int(window_days),
        "n_buys": len(buys), "n_sells": len(sells),
        "buy_value": buy_value, "sell_value": sell_value, "net_value": net_value,
        "buy_shares": buy_sh, "sell_shares": sell_sh, "net_shares": net_sh,
        "distinct_buyers": len({r["insider"] for r in buys if r.get("insider")}),
        "distinct_sellers": len({r["insider"] for r in sells if r.get("insider")}),
        "recent": recent_out,
    }


# ---------------------------------------------------------------- fetch (yfinance)

def fetch_insider(tickers: list[str], max_new: int | None = None) -> int:
    """Drip yfinance get_insider_transactions() into data/canada_insider/, capped +
    freshness-cached like fetch_earnings. Best-effort; one name down can't break the
    batch. Empty results are cached too, so perennially-uncovered names don't burn the
    per-build budget. Returns how many names were (re)fetched."""
    import yfinance as yf

    cfg = _cfg()
    cap = int(max_new if max_new is not None else cfg["max_new_per_build"])

    have: dict[str, dict] = {}
    if CACHE.exists():
        try:
            df = pd.read_parquet(CACHE)
            has_asof = "asof" in df.columns
            for _, r in df.iterrows():
                asof = str(r["asof"]) if has_asof and pd.notna(r["asof"]) else ""
                have[r["ticker"]] = {"payload": r["payload"], "asof": asof}
        except Exception as e:  # noqa: BLE001
            log.warning("canada insider cache read failed: %s", e)

    fresh_cut = (pd.Timestamp.now() - pd.Timedelta(days=INSIDER_MAX_AGE_DAYS)).strftime("%Y-%m-%d")
    todo = [t for t in tickers if t.endswith(".TO")
            and not (t in have and have[t]["asof"] >= fresh_cut)][:cap]
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    n = 0
    for t in todo:
        try:
            df = yf.Ticker(t).get_insider_transactions()
            rows = _normalize_df(df)
            have[t] = {"payload": json.dumps(rows, default=str), "asof": today}
            n += 1
            time.sleep(0.05)
        except Exception as e:  # noqa: BLE001 — one name down can't break the batch
            log.debug("canada insider %s failed: %s", t, e)
    if n:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        rows_out = [{"ticker": t, "payload": v["payload"], "asof": v["asof"]}
                    for t, v in have.items()]
        pd.DataFrame(rows_out).to_parquet(CACHE)
    return n


def insider_map() -> dict[str, dict]:
    """{ticker: insider summary} from the cache, for the per-stock display. Empty when
    the cache is absent (degrade-don't-crash). Names with no open-market personal
    filings in the window are omitted (the panel simply hides)."""
    if not CACHE.exists():
        return {}
    try:
        df = pd.read_parquet(CACHE)
    except Exception as e:  # noqa: BLE001
        log.warning("canada insider cache read failed: %s", e)
        return {}
    cfg = _cfg()
    window, recent_n = int(cfg["window_days"]), int(cfg["recent_n"])
    min_shares = float(cfg["min_shares"] or 0)
    has_asof = "asof" in df.columns
    out: dict[str, dict] = {}
    for _, r in df.iterrows():
        try:
            rows = json.loads(r["payload"])
        except Exception:  # noqa: BLE001
            continue
        summ = _summarize(rows, window_days=window, recent_n=recent_n, min_shares=min_shares)
        if summ:
            summ["asof"] = str(r["asof"]) if has_asof and pd.notna(r["asof"]) else None
            out[str(r["ticker"])] = summ
    return out
