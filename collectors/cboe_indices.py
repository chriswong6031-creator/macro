"""CBOE index collectors — the keyless daily CSVs CBOE's CDN serves with deep history.

CBOE's CDN exposes a family of clean, keyless `*_History.csv` files (DATE, VALUE) under
`/api/global/us_indices/daily_prices/`. Two of them feed the vol surface:

  • SKEW — the implied probability of an outsized (tail) S&P 500 move priced into OTM
    options: a "how fearful is the left tail" gauge complementing VIX (at-the-money vol).
    History back to 1990. SKEW ~ 100 means a near-lognormal (low tail) distribution; rising
    SKEW (130-150) means the market is paying up for crash protection.

  • VVIX — "vol-of-vol": the 30-day implied vol of VIX options. It spikes when the market
    pays up for protection AGAINST a vol spike (tail-of-the-tail demand). History back to
    2006/2007. Feeds engine/vol_regime's VVIX-VIX decoupling / peak-fear leg.

Both are stored under the existing `cboe` group so engine/conditions.py and
engine/vol_regime.py can read them alongside GEX / put-call. One fetch returns the WHOLE
file, so a single run both BACKFILLS the full history and accrues the new day — there is no
separate backfill step (store.upsert merges; rows on disk are never dropped).

VSB W1 (research/VOL_SUPPRESSION_AI_BIFURCATION_MASTERPLAN_BY_FABLE.md) adds the
implied-correlation / dispersion / short-tenor family via CboeCorVolAdapter: COR1M,
COR3M, DSPX, VIX1D, VIXEQ — same CDN, same one-fetch-carries-all-history contract.
These were previously (COR1M/COR3M) yahoo vol-group tickers, but yfinance serves no
real history for ^COR1M/^COR3M (a single zero-ish row), and collectors/yahoo._extract
silently drops a ticker Yahoo returns nothing for — the store sat at a 1-row stub with
no alarm. check_cor_vol_freshness() is the store-level tripwire against that mode.
"""
from __future__ import annotations

import io
import logging
from datetime import timedelta

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

UA = "Mozilla/5.0 (macro-dashboard research)"
# fallback if config.yml's cboe section lacks the key (the URL is the analog of skew_url)
VVIX_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VVIX_History.csv"


class CboeSkewAdapter(Adapter):
    name = "cboe_skew"
    group = "cboe"
    stale_after_days = 5

    def __init__(self) -> None:
        self.cfg = config.load()["cboe"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        r = self.http_get(self.cfg["skew_url"], retries=self.cfg.get("retries", 3),
                          timeout=60, headers={"User-Agent": "Mozilla/5.0 (macro-dashboard research)"})
        df = pd.read_csv(io.StringIO(r.text))
        if df.shape[1] < 2 or df.columns[0].upper() != "DATE":
            raise ValueError(f"unexpected SKEW response: cols={list(df.columns)}")
        df.columns = ["date", "skew", *df.columns[2:]]
        df["date"] = pd.to_datetime(df["date"], format="%m/%d/%Y", errors="coerce")
        df["skew"] = pd.to_numeric(df["skew"], errors="coerce")
        df = df[["date", "skew"]].dropna().set_index("date")
        return {"skew": df}


class CboeVvixAdapter(Adapter):
    """CBOE VVIX — the vol-of-vol index (implied vol of VIX options), 2006/2007+.

    A direct analog of CboeSkewAdapter: the keyless VVIX_History.csv (DATE, VVIX) carries
    the FULL history, so each daily run backfills + accrues in one shot (full_history is a
    no-op — there is nothing extra to fetch). This is the LONG-history source that retires
    the ~26-row data/yahoo/_VVIX series (yfinance only began carrying ^VVIX in 2026), and is
    what engine/vol_regime.py reads for its VVIX-VIX decoupling / peak-fear leg.

    Graceful: a moved/blocked endpoint raises and the runner degrades the source (the vol
    regime simply drops the VVIX leg) — it never breaks the daily build.
    """
    name = "cboe_vvix"
    group = "cboe"
    stale_after_days = 5

    def __init__(self) -> None:
        self.cfg = config.load()["cboe"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        url = self.cfg.get("vvix_url", VVIX_URL)
        r = self.http_get(url, retries=self.cfg.get("retries", 3),
                          timeout=60, headers={"User-Agent": UA})
        df = pd.read_csv(io.StringIO(r.text))
        if df.shape[1] < 2 or df.columns[0].upper() != "DATE":
            raise ValueError(f"unexpected VVIX response: cols={list(df.columns)}")
        df.columns = ["date", "vvix", *df.columns[2:]]
        df["date"] = pd.to_datetime(df["date"], format="%m/%d/%Y", errors="coerce")
        df["vvix"] = pd.to_numeric(df["vvix"], errors="coerce")
        df = df[["date", "vvix"]].dropna().set_index("date")
        return {"vvix": df}


# ---------------------------------------------------------------- VSB W1 cor/vol family
_HISTORY_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{sym}_History.csv"

# series name (store: data/cboe/<name>.parquet) -> CDN symbol. Two CSV shapes exist:
# DATE,OPEN,HIGH,LOW,CLOSE (COR1M/COR3M 2006->, VIX1D 2022->) and DATE,<VALUE>
# (DSPX/VIXEQ 2014->); _parse_history handles both, storing `close` either way.
COR_VOL_SERIES: dict[str, str] = {
    "cor1m": "COR1M",   # CBOE 1-month implied correlation (COR floor / unclench watch)
    "cor3m": "COR3M",   # CBOE 3-month implied correlation
    "dspx": "DSPX",     # CBOE S&P 500 Dispersion Index
    "vix1d": "VIX1D",   # 1-day SPX implied vol (0DTE-era tenor)
    "vixeq": "VIXEQ",   # equal-weight S&P 500 VIX — concentration-vs-breadth vol axis
}


def _parse_history(text: str, series: str) -> pd.DataFrame:
    """Parse one CDN *_History.csv into a date-indexed frame with a `close` column
    (plus open/high/low when the file carries OHLC). Raises on any unexpected shape —
    the adapter must fail LOUD, never persist a malformed frame."""
    df = pd.read_csv(io.StringIO(text))
    if df.shape[1] < 2 or df.columns[0].strip().upper() != "DATE":
        raise ValueError(f"unexpected {series} response: cols={list(df.columns)}")
    df.columns = [c.strip().lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"], format="%m/%d/%Y", errors="coerce")
    if {"open", "high", "low", "close"}.issubset(df.columns):
        keep = ["open", "high", "low", "close"]
    elif df.shape[1] == 2:
        df = df.rename(columns={df.columns[1]: "close"})
        keep = ["close"]
    else:
        raise ValueError(f"unexpected {series} column shape: {list(df.columns)}")
    for c in keep:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    out = df.dropna(subset=["date", "close"]).set_index("date")[keep]
    if out.empty:
        raise ValueError(f"{series}: no parseable rows")
    return out


class CboeCorVolAdapter(Adapter):
    """CBOE implied-correlation + dispersion + short-tenor vol family (VSB W1).

    COR1M/COR3M (2006->), DSPX/VIXEQ (2014->), VIX1D (2022->) from the same keyless
    CDN *_History.csv family as SKEW/VVIX. Persist-only: NO engine legs, NO display
    surface read these yet (W3+ consumes them display-tier; any authority use waits
    on the pre-registered gauntlet). Each series is fetched strictly — one failed or
    malformed series raises, so the runner marks the whole source failed and the
    breaker/health surface sees it. The complementary store-level guard is
    check_cor_vol_freshness() below (catches "adapter never even ran")."""
    name = "cboe_cor_vol"
    group = "cboe"
    stale_after_days = 5

    def __init__(self) -> None:
        self.cfg = config.load()["cboe"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        for series, sym in COR_VOL_SERIES.items():
            r = self.http_get(_HISTORY_URL.format(sym=sym),
                              retries=self.cfg.get("retries", 3),
                              timeout=60, headers={"User-Agent": UA})
            frames[series] = _parse_history(r.text, series)
        return frames


def check_cor_vol_freshness(max_lag_sessions: int = 3, min_rows: int = 100) -> list[dict]:
    """Store-level freshness/row-floor tripwire for the cor/vol family (VSB W1a).

    detect_stale_series only inspects frames a fetch RETURNED, so a series that never
    lands in the store at all — the exact ^COR1M/^COR3M failure (yahoo._extract drops
    a no-data ticker with only a log line) — is invisible to it. This check reads the
    STORE against the NYSE session calendar (the SPY freshness-gate idiom from
    lib/nyse_calendar: only the exchange calendar knows a session is missing), so it
    fires no matter WHY the series stopped: adapter deregistered, breaker wedged,
    endpoint moved, or a 1-row stub. Warn/alert only — it writes run_status
    stale_series entries and logs; it NEVER fails the lane."""
    from collectors.base import _write_stale_series
    from lib import nyse_calendar, store

    expected = nyse_calendar.expected_last_session()
    problems: list[dict] = []
    for series in COR_VOL_SERIES:
        df = store.read("cboe", series)
        rows = 0 if df is None else len(df)
        last = None if (df is None or df.empty) else pd.Timestamp(df.index.max()).date()
        if last is not None:
            # sessions missing from the store: NYSE sessions in (last, expected]
            lag, d = 0, last + timedelta(days=1)
            while d <= expected and lag <= max_lag_sessions + 1:
                if nyse_calendar.is_session(d):
                    lag += 1
                d += timedelta(days=1)
        reason = None
        if df is None:
            reason = "missing from store"
        elif rows < min_rows:
            reason = f"row floor: {rows} < {min_rows} (stub — the ^COR1M failure mode)"
        elif lag > max_lag_sessions:
            reason = f"stale: last obs {last} is >{max_lag_sessions} sessions behind {expected}"
        if reason:
            entry = {"group": "cboe", "series": series, "rows": rows,
                     "last_obs": str(last) if last else None,
                     "cadence_days": 1, "age_days": (expected - last).days if last else None,
                     "reason": reason}
            problems.append(entry)
            log.warning("cor/vol freshness: %s — %s", series, reason)
    if problems:
        _write_stale_series(problems)
    else:
        log.info("cor/vol freshness: all %d series fresh (last expected session %s)",
                 len(COR_VOL_SERIES), expected)
    return problems
