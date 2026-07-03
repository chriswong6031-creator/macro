"""Canadian insider transactions (SEDI) via yfinance — display-only context.

The Canada parallel of the US SEC Form-4 insider work (collectors/sec_insider.py),
but the data path is completely different. SEDI (sedi.ca, Canada's insider-filing
system) has NO free machine-readable feed and is CAPTCHA-walled, and every paid
vendor's insider product is US-SEC-only. The one free, programmatic path is
yfinance's undocumented Yahoo `quoteSummary` endpoint: `get_insider_transactions()`
returns SEDI-sourced, dated insider filings for many .TO names — no key, no auth.
Verified live on yfinance 1.4.1 (~150-row cap per name, ~9/13 coverage on a liquid
sample; ENB/ABX/BCE/CP came back empty -- coverage is best-effort PER TICKER).

We keep only PERSONAL OPEN-MARKET trades -- rows whose text says "Acquisition /
Disposition in the public market" filed by a person ("Director of Issuer", "Senior
Officer of Issuer", ...) -- and DROP issuer rows (Position == "Issuer" = company
buybacks) and option exercises / grants / redemptions, then summarise the net
buy/sell lean over a trailing window plus the most-recent filings.

IMPORTANT -- this is CONTEXT, NOT A SIGNAL. SEDI gives insiders up to ~5 calendar
days to file, so the trade is already days old when it publishes, and TSX insider
breadth is thin -- so net buying/selling is a conviction tell, not a timing trigger
(no Phase-0 cross-sectional validation yet). Mirrors the best-effort drip-cache
pattern of engine/canada_fundamentals.py (fetch_earnings / earnings_map); cached
under data/canada_insider/. yfinance is pinned at 1.4.1 (these undocumented
properties have regressed between versions).

## Persistence (append-only fix -- Slice G, 2026-07-03)

The previous cache used ONE row per ticker, storing the full payload as a JSON blob.
Each re-fetch REPLACED the blob -- because yfinance caps at ~150 rows per name, any
transaction older than the 150-row window was permanently lost after the next refresh
cycle, so history evaporated.

The new store is a **long-form transactions table**: one row per transaction.

    data/canada_insider/transactions.parquet
      columns: ticker, date, insider, role, personal (bool), action, shares, value,
               insider_key, shares_key, value_key
      dedup key: (ticker, date, insider_key, shares_key, value_key)

Each incremental fetch appends new rows and deduplicates on the composite key, so
history accumulates indefinitely even when yfinance only returns the most-recent
~150 rows.

**Backward compatibility**: the legacy `data/canada_insider/insider.parquet` (one
JSON-blob row per ticker) is migrated to transactions.parquet on the first write.
`insider_map()` returns the same dict shape as before -- callers in
scripts/build_canada_library.py are unchanged.

**Free-mirror spike (2026-07-03)**: canadianinsider.com and INK Research were probed
for multi-year SEDI history.  Verdict: both are paid-only (2y/5y charting tiers);
no free bulk download or programmatic API found. SEDI.ca is CAPTCHA-walled. C2 come-
back date (~2028) stands.
"""
from __future__ import annotations

import json
import logging
import time

import pandas as pd

from lib import config

log = logging.getLogger("canada_insider")

# ---------------------------------------------------------------------------
# Store paths
# ---------------------------------------------------------------------------

# Legacy blob-format cache (one JSON blob per ticker) -- auto-migrated on first write.
# Kept for >=1 month to allow safe rollback; phase out 2026-08-03.
_LEGACY_CACHE = config.data_dir() / "canada_insider" / "insider.parquet"

# New append-only transactions store (one row per transaction, deduped).
CACHE = config.data_dir() / "canada_insider" / "transactions.parquet"

# Deduplication key -- tolerates None/NaN in insider/shares/value by coercing to str.
_DEDUP_COLS = ("ticker", "date", "insider_key", "shares_key", "value_key")

# Re-fetch a cached name when its most-recent transaction date is older than this.
INSIDER_MAX_AGE_DAYS = 12

# Defaults if the config block is absent (degrade-don't-crash).
_DEFAULTS = {"window_days": 180, "max_new_per_build": 40, "recent_n": 6, "min_shares": 0}


def _cfg() -> dict:
    try:
        c = (config.load().get("canada", {}) or {}).get("insider", {}) or {}
    except Exception:  # noqa: BLE001
        c = {}
    return {**_DEFAULTS, **c}


def _num(v):
    try:
        if v in (None, "", "--", "\u2014"):
            return None
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _is_company(position: str) -> bool:
    return (position or "").strip().lower() == "issuer"


def _role(position: str) -> str:
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
    t = (text or "").lower()
    if "public market" in t:
        if "acquisition" in t or "purchase" in t:
            return "buy"
        if "disposition" in t or "sale" in t or "sold" in t:
            return "sell"
    return "other"


def _normalize_df(df) -> list[dict]:
    """Map a yfinance get_insider_transactions() DataFrame to a list of normalised
    row dicts. Pure (no I/O) so it is unit-testable with a synthetic frame."""
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
    """Net open-market personal-insider buy/sell lean over a trailing window."""
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


# ---------------------------------------------------------------------------
# Append-only store helpers
# ---------------------------------------------------------------------------

def _make_dedup_key(row: dict) -> tuple:
    return (
        str(row.get("ticker", "")),
        str(row.get("date", "")),
        str(row.get("insider") or "None"),
        str(row.get("shares") or "None"),
        str(row.get("value") or "None"),
    )


def _load_transactions() -> pd.DataFrame:
    """Load the transactions store, migrating from legacy blob format if needed."""
    if CACHE.exists():
        try:
            return pd.read_parquet(CACHE)
        except Exception as e:  # noqa: BLE001
            log.warning("canada_insider: transactions store read failed (%s), re-migrating", e)

    if _LEGACY_CACHE.exists():
        log.info("canada_insider: migrating legacy insider.parquet to transactions.parquet")
        try:
            legacy = pd.read_parquet(_LEGACY_CACHE)
            all_rows: list[dict] = []
            for _, r in legacy.iterrows():
                ticker = str(r.get("ticker", ""))
                try:
                    rows = json.loads(r.get("payload") or "[]")
                except (json.JSONDecodeError, TypeError):
                    rows = []
                for row in rows:
                    row["ticker"] = ticker
                    key = _make_dedup_key(row)
                    all_rows.append({
                        **row,
                        "insider_key": key[2],
                        "shares_key": key[3],
                        "value_key": key[4],
                    })
            if all_rows:
                df = pd.DataFrame(all_rows)
                df = df.drop_duplicates(subset=list(_DEDUP_COLS))
                CACHE.parent.mkdir(parents=True, exist_ok=True)
                df.to_parquet(CACHE, index=False)
                log.info("canada_insider: migrated %d rows from %d tickers",
                         len(df), legacy["ticker"].nunique())
                return df
        except Exception as e:  # noqa: BLE001
            log.warning("canada_insider: legacy migration failed: %s", e)

    return pd.DataFrame(columns=[
        "ticker", "date", "insider", "role", "personal", "action", "shares", "value",
        "insider_key", "shares_key", "value_key",
    ])


def _save_transactions(df: pd.DataFrame) -> None:
    df = df.drop_duplicates(subset=list(_DEDUP_COLS), keep="last")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE, index=False)


def _latest_date_per_ticker(df: pd.DataFrame) -> dict:
    if df.empty or "ticker" not in df.columns or "date" not in df.columns:
        return {}
    return (
        df.dropna(subset=["date"])
        .groupby("ticker")["date"]
        .max()
        .to_dict()
    )


# ---------------------------------------------------------------------------
# fetch (yfinance) -- append-only
# ---------------------------------------------------------------------------

def fetch_insider(tickers: list, max_new=None) -> int:
    """Drip yfinance get_insider_transactions() into the append-only transactions store.

    Returns how many tickers were (re)fetched.
    """
    import yfinance as yf

    cfg = _cfg()
    cap = int(max_new if max_new is not None else cfg["max_new_per_build"])

    existing = _load_transactions()
    latest_per_ticker = _latest_date_per_ticker(existing)

    fresh_cut = (pd.Timestamp.now() - pd.Timedelta(days=INSIDER_MAX_AGE_DAYS)).strftime(
        "%Y-%m-%d"
    )
    todo = [
        t for t in tickers
        if t.endswith(".TO")
        and not (t in latest_per_ticker and latest_per_ticker[t] >= fresh_cut)
    ][:cap]

    if not todo:
        return 0

    existing_keys: set = set()
    if not existing.empty:
        for col in _DEDUP_COLS:
            if col not in existing.columns:
                existing[col] = "None"
        existing_keys = set(
            zip(
                existing["ticker"].astype(str),
                existing["date"].astype(str),
                existing["insider_key"].astype(str),
                existing["shares_key"].astype(str),
                existing["value_key"].astype(str),
            )
        )

    new_rows: list[dict] = []
    n = 0
    for t in todo:
        try:
            df_yf = yf.Ticker(t).get_insider_transactions()
            rows = _normalize_df(df_yf)
            for row in rows:
                row["ticker"] = t
                key = _make_dedup_key(row)
                if key not in existing_keys:
                    new_rows.append({
                        **row,
                        "insider_key": key[2],
                        "shares_key": key[3],
                        "value_key": key[4],
                    })
                    existing_keys.add(key)
            n += 1
            time.sleep(0.05)
        except Exception as e:  # noqa: BLE001
            log.debug("canada_insider %s failed: %s", t, e)

    if new_rows:
        combined = pd.concat(
            [existing, pd.DataFrame(new_rows)],
            ignore_index=True,
        )
        _save_transactions(combined)
        log.info("canada_insider: appended %d new rows from %d tickers", len(new_rows), n)

    return n


def insider_map() -> dict:
    """{ticker: insider summary} from the transactions store.

    Returns the same shape as the legacy implementation so callers in
    scripts/build_canada_library.py are unchanged.
    """
    df = _load_transactions()
    if df.empty:
        return {}

    cfg = _cfg()
    window, recent_n = int(cfg["window_days"]), int(cfg["recent_n"])
    min_shares = float(cfg["min_shares"] or 0)

    out: dict = {}
    for ticker, grp in df.groupby("ticker"):
        grp_clean = grp.drop(
            columns=[c for c in ("insider_key", "shares_key", "value_key")
                     if c in grp.columns],
            errors="ignore",
        )
        rows = grp_clean.to_dict("records")
        summ = _summarize(rows, window_days=window, recent_n=recent_n, min_shares=min_shares)
        if summ:
            dates = [r.get("date", "") for r in rows if r.get("date")]
            summ["asof"] = max(dates) if dates else None
            out[str(ticker)] = summ
    return out
