"""W3 Event Intelligence — catalyst-taxonomy event-study priors.

Pre-registered design: research/SIGNAL_COMMONS_MASTERPLAN_BY_FABLE.md §3 W3.
Audit/review: design-review verdict on 2026-07-05.

Uses the hincl HAC/BH-FDR/DSR/split-half/survivorship harness (NOT the
P5.1 raw-median aggregator). All priors are display-only context (SCORED=False,
is_context_only=True). Persists to data/special_situations/event_priors/<type>.json
so the existing workflow ``git add data/special_situations`` stages them (B3 fix).

Open-question conservative defaults applied:
- M2: sp_index_changes ships as null-print (insufficient-history) until K>=floor.
- M1: gov-contract awards ships as null-only stub (no awardee-ticker source).
- M4 (RE-ENABLED 2026-08-05): earnings was null-printed because eps_quarterly.parquet
  asof_date is period_end + exactly 60 calendar days for every row — a mechanical
  placeholder, NOT a real announcement date. That gate named its own unblock ("EDGAR
  8-K filing timestamps"), and data/edgar/earnings_8k_dates.parquet now supplies it:
  98,975 Item-2.02 rows, 1,314 names, 2004-08..2026-07, each with the SEC acceptance
  timestamp. asof_date is still unusable and is still not read here.
  Day-0 comes from the acceptance time in ET (after-the-close filings are priced by
  the NEXT session); subtypes are day-0 reaction bands, since every name reports every
  quarter and an unconditional earnings prior is ~a market average. See
  research/entry_stack/W4_EARNINGS_REACTION_PRIOR.md for the phase-0 measurement,
  including the non-earnings placebo that the construction is graded against.
- M5 (NEW): clinical halts are null-printed. last_update (ClinicalTrials.gov)
  is the latest administrative record touch — any later edit, results posting, or
  contact change — NOT the date the halt became public. The halt CAR window anchored
  on last_update is systematically mis-aligned (starts AFTER the reaction, not at it).
  Halts will be re-enabled once anchored on the first date why_stopped/is_halt became
  true in the ClinicalTrials.gov history.
- n-floor: EVENT_FLOOR=8 pooled (matches hincl NW K>=8).
- IPO lockup: uses actual per-deal lockup_days where available, falls back to
  standard 90d/180d windows tagged separately.

DSR trial-ledger budget pre-declared:
  event types: clinicaltrials, openfda, sp_index_changes, ipo_lockup, earnings
  anchors: 1 per type (first_post / status_date / announce_date / lockup_expiry / asof_date)
  horizons: 3 (5D, 20D, 60D)
  Subtypes create separate slices (NOT separate DSR trials — slices within a
  family trial). Total DSR trials = 5 event-types × 3 horizons = 15, padded to
  20 for future extension. Gov-contract = 0 (no computation, null stub).

Run: python -m scripts.backtest_event_priors
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Iterator

import numpy as np
import pandas as pd

from engine.validation import (
    newey_west_tstat,
    benjamini_hochberg,
    deflated_sharpe,
    ret_moments,
)
from engine.trial_ledger import TrialLedger
from lib import config

# ---------------------------------------------------------------------------
# DSR / trial-ledger pre-declaration (m4 fix: pre-declare before any compute)
# 5 event types × 3 horizons = 15 active trials, padded to 20 for buffer.
# ---------------------------------------------------------------------------
N_TRIALS = 20
FAMILY = "event_priors"
_LED = TrialLedger.with_declared_budget(N_TRIALS, FAMILY)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HORIZONS = [5, 20, 60]          # trading-day windows
PRIMARY_H = 20                   # BH-FDR gating horizon
PRE_WINDOW = 10                  # pre-event excess window (days before event)
SUSP_MAX = 5                     # max sessions to find first valid print
EVENT_FLOOR = 8                  # minimum studiable episodes for a non-null prior (matches hincl NW K>=8)

# Output directory: UNDER data/special_situations/ so ``git add data/special_situations``
# covers everything (B3 fix).
_OUT_DIR = config.data_dir() / "special_situations" / "event_priors"

# ---------------------------------------------------------------------------
# Price utilities (generalised from backtest_special_situations.py)
# ---------------------------------------------------------------------------

def _us_closes() -> pd.DataFrame:
    """S&P 1500 breadth close caches + existing bt_prices backfill."""
    frames = []
    for g in ("breadth", "midcap_breadth", "smallcap_breadth"):
        p = config.data_dir() / g / "_closes_cache.parquet"
        if p.exists():
            frames.append(pd.read_parquet(p))
    btp = config.data_dir() / "special_situations" / "bt_prices.parquet"
    if btp.exists():
        frames.append(pd.read_parquet(btp))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, axis=1, sort=False)
    df.index = pd.to_datetime(df.index)
    return df.loc[:, ~df.columns.duplicated()].sort_index()


def _deep_closes(closes: pd.DataFrame) -> pd.DataFrame:
    """The breadth caches UNIONED with the deep per-ticker store (data/stocks/*.parquet).

    The shared `_us_closes()` panel is a rolling cache — ~2023-06 onward.  That depth is
    fine for the rare event types (an FDA approval is studied near the event), but an
    earnings prior computed on three years of one bull tape is an era sample, not a
    prior: the whole point of the 2004-2026 Item-2.02 store is to span several regimes.
    data/stocks carries split-adjusted closes back to the 1980s for ~235 names.

    The deep names are a SUBSET of the breadth columns, so a column-wise append adds
    nothing — what has to grow is the INDEX.  `combine_first` does exactly that: the
    breadth value wins wherever it exists, and the deep store fills the earlier dates
    (and any deep-only name).  Verified 2026-08-05: on the 345-session overlap the two
    stores agree to 0.000000 relative error on AAPL/MSFT/JPM/XOM/NVDA — same
    split-adjustment basis, so the splice cannot manufacture a return at the seam.
    A mismatch there WOULD have: re-check if either store's adjustment policy changes.

    Restricted to names that actually carry earnings events, so the union stays a
    ~1.3k-column frame rather than a 2.5k one.  Absent store -> `closes` unchanged.
    """
    root = config.data_dir() / "stocks"
    if not root.exists():
        return closes
    cols: dict[str, pd.Series] = {}
    for f in sorted(root.glob("*.parquet")):
        try:
            d = pd.read_parquet(f)
        except Exception:  # noqa: BLE001
            continue
        if "close" not in d.columns or d.empty:
            continue
        s = d["close"].astype(float)
        s.index = pd.to_datetime(s.index)
        cols[f.stem.upper()] = s[~s.index.duplicated(keep="last")]
    if not cols:
        return closes
    deep = pd.DataFrame(cols).sort_index()
    if closes.empty:
        return deep
    out = closes.combine_first(deep).sort_index()
    return out.dropna(axis=1, how="all")


def _fetch_event_prices(tickers: list[str], closes: pd.DataFrame,
                        start: str = "2020-01-01") -> pd.DataFrame:
    """Backfill adjusted closes for event tickers not in the breadth caches (yfinance).
    Returns the closes panel extended with the newly fetched tickers.
    Non-priced tickers are imputed as CAR=0 in the survivorship floor (B4 fix)."""
    have = set(closes.columns)
    need = [t for t in tickers if t not in have and t and "." not in t]
    if not need:
        return closes
    try:
        import yfinance as yf
        frames = []
        for i in range(0, len(need), 60):
            batch = need[i:i + 60]
            try:
                dl = yf.download(batch, start=start, auto_adjust=True, progress=False, threads=True)
                cl = dl["Close"] if "Close" in dl else dl
                if isinstance(cl, pd.Series):
                    cl = cl.to_frame(batch[0])
                frames.append(cl)
            except Exception:  # noqa: BLE001
                pass
        if frames:
            extra = pd.concat(frames, axis=1)
            extra = extra.loc[:, ~extra.columns.duplicated()]
            extra.index = pd.to_datetime(extra.index)
            closes = pd.concat([closes, extra], axis=1, sort=False)
            closes = closes.loc[:, ~closes.columns.duplicated()].sort_index()
    except ImportError:
        pass
    return closes


def _spy_series(closes: pd.DataFrame) -> pd.Series | None:
    if "SPY" in closes.columns:
        return closes["SPY"]
    try:
        from lib import store
        s = store.read("yahoo", "SPY")
        return s["close"] if s is not None and "close" in s else None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Core CAR / pre-drift engine (excess vs SPY)
# ---------------------------------------------------------------------------

def car_for_event(ticker: str, event_date: pd.Timestamp,
                  closes: pd.DataFrame, spy: pd.Series | None, h: int,
                  pre: int = PRE_WINDOW) -> tuple[float | None, float | None, bool]:
    """Excess cumulative log-return vs SPY over [event_date, event_date+h].
    Also computes pre-event excess log-CAR over [-pre, 0] (the 'already-reacted' metric).
    Returns (excess_car, pre_drift, studiable).

    Suspension rule: need a valid ticker print within SUSP_MAX sessions after
    event_date; the same must hold for SPY. Requires >= h/2 valid bars in window."""
    if ticker not in closes.columns:
        return None, None, False
    s = closes[ticker].dropna()
    if s.empty:
        return None, None, False
    cal = closes.index
    pos = cal.searchsorted(event_date, side="left")
    if pos >= len(cal):
        return None, None, False

    # find first valid ticker print at/after event within SUSP_MAX
    fill_pos: int | None = None
    for k in range(0, SUSP_MAX + 1):
        if pos + k >= len(cal):
            break
        day = cal[pos + k]
        if day in s.index and np.isfinite(s.get(day, np.nan)):
            fill_pos = pos + k
            break
    if fill_pos is None:
        return None, None, False

    end_pos = fill_pos + h
    if end_pos >= len(cal):
        return None, None, False

    win_days = cal[fill_pos:end_pos + 1]
    sub = s.reindex(win_days).dropna()

    # SPY window
    if spy is not None:
        spy_sub = spy.reindex(win_days).dropna()
        common = sub.index.intersection(spy_sub.index)
    else:
        common = sub.index

    if len(common) < max(3, h // 2):
        return None, None, False

    sub_c = sub.reindex(common)
    excess_car: float
    if spy is not None:
        spy_c = spy_sub.reindex(common)
        excess_car = float(
            np.log(sub_c.iloc[-1] / sub_c.iloc[0])
            - np.log(spy_c.iloc[-1] / spy_c.iloc[0])
        )
    else:
        excess_car = float(np.log(sub_c.iloc[-1] / sub_c.iloc[0]))

    # pre-event drift
    pre_lo = max(0, fill_pos - pre)
    pdays = cal[pre_lo:fill_pos + 1]
    ps = s.reindex(pdays).dropna()
    pre_drift: float | None = None
    if spy is not None and len(pdays) >= 3:
        pi = spy.reindex(pdays).dropna()
        pc = ps.index.intersection(pi.index)
        if len(pc) >= 3:
            pre_drift = float(
                np.log(ps.reindex(pc).iloc[-1] / ps.reindex(pc).iloc[0])
                - np.log(pi.reindex(pc).iloc[-1] / pi.reindex(pc).iloc[0])
            )
    elif len(pdays) >= 3 and len(ps) >= 3:
        pre_drift = float(np.log(ps.iloc[-1] / ps.iloc[0]))

    return excess_car, pre_drift, True


def max_drawdown_in_window(ticker: str, event_date: pd.Timestamp,
                           closes: pd.DataFrame, h: int) -> float | None:
    """Max drawdown (always <= 0) within [event_date, event_date+h] from the entry close."""
    if ticker not in closes.columns:
        return None
    s = closes[ticker].dropna()
    if s.empty:
        return None
    cal = closes.index
    pos = cal.searchsorted(event_date, side="left")
    fill_pos: int | None = None
    for k in range(0, SUSP_MAX + 1):
        if pos + k >= len(cal):
            break
        day = cal[pos + k]
        if day in s.index and np.isfinite(s.get(day, np.nan)):
            fill_pos = pos + k
            break
    if fill_pos is None:
        return None
    end_pos = fill_pos + h
    if end_pos >= len(cal):
        return None
    win_days = cal[fill_pos:end_pos + 1]
    sub = s.reindex(win_days).dropna()
    if len(sub) < 2:
        return None
    p0 = sub.iloc[0]
    if p0 <= 0:
        return None
    peak = p0
    dd = 0.0
    for p in sub.iloc[1:]:
        if np.isnan(p):
            continue
        peak = max(peak, p)
        dd = min(dd, (p - peak) / peak)
    return float(dd * 100)  # as pct, always <= 0


# ---------------------------------------------------------------------------
# Episode aggregation (HAC t / CI / DSR / split-half / survivorship floor)
# ---------------------------------------------------------------------------

def _num(v) -> float | None:
    """Cast to python native float, normalise NaN/inf to None (qledger hazard guard)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if (f != f or np.isinf(f)) else f  # NaN or inf -> None


def aggregate_episodes(events: list[tuple[str, pd.Timestamp]],
                       closes: pd.DataFrame, spy: pd.Series | None,
                       h: int, event_type: str) -> dict:
    """Aggregate a list of (ticker, event_date) pairs into a prior cell dict.

    Survivorship floor: tickers absent from closes (or not studiable) are
    counted as n_imputed_zero and their CAR is imputed as 0 in the surv-lb
    estimate (B4 fix). The point estimate uses ONLY studiable episodes.
    """
    all_tickers = {t for t, _ in events}
    studiable_tickers: set[str] = set()
    ep_records: list[tuple[pd.Timestamp, str, float, float | None]] = []

    for tkr, ev_date in events:
        ev_ts = pd.Timestamp(ev_date).normalize()
        car, pre_drift, ok = car_for_event(tkr, ev_ts, closes, spy, h)
        if ok:
            ep_records.append((ev_ts, tkr, car, pre_drift))
            studiable_tickers.add(tkr)

    n_imputed = len(all_tickers - studiable_tickers)

    if not ep_records:
        return {
            "h": h, "n_events": 0, "n_studiable": 0,
            "n_imputed_zero": int(n_imputed), "insufficient": True,
        }

    edf = pd.DataFrame(ep_records, columns=["episode", "ticker", "car", "pre_drift"])
    # episode-level = average across same-date events (dedupe intraday)
    epi_car = edf.groupby("episode")["car"].mean().sort_index()
    epi_pre = edf.groupby("episode")["pre_drift"].mean()
    x = epi_car.to_numpy(float)
    K = len(x)

    insufficient = K < EVENT_FLOOR

    # HAC / Newey-West t-stat
    nw: dict
    if K >= EVENT_FLOOR:
        nw = newey_west_tstat(x, lags=4)
    else:
        nw = {"mean": float(np.mean(x)) if K else None,
              "se": None, "t": None, "p": None, "n": K}

    # block-bootstrap CI (hincl shape)
    ci = _block_mean_ci(x) if K >= 4 else None

    # DSR
    dsr_val = None
    mom = ret_moments(pd.Series(x))
    if K >= 3 and mom is not None and not insufficient:
        sr, sk, ku, _ = mom
        try:
            dsr_val = deflated_sharpe(sr, sk, ku, T=K, ledger=_LED, family=FAMILY)
        except Exception:  # noqa: BLE001
            dsr_val = None

    # split-half chronological
    sh_same: bool | None = None
    if K >= 4:
        h1 = x[:K // 2]
        h2 = x[K // 2:]
        sh_same = bool(
            np.sign(np.mean(h1)) == np.sign(np.mean(h2)) and np.mean(h1) != 0
        )

    # survivorship lower bound
    x_lb = np.concatenate([x, np.zeros(n_imputed)]) if n_imputed else x
    lb_mean = float(np.mean(x_lb))
    lb_nw: dict
    if len(x_lb) >= EVENT_FLOOR:
        lb_nw = newey_west_tstat(x_lb, lags=4)
    else:
        lb_nw = {"t": None}

    # win rate and pre-drift summary
    win_rate = float((x > 0).mean()) if K else None
    pre_mean = _num(epi_pre.mean()) if epi_pre.notna().any() else None

    # max drawdown (per-episode mean of per-ticker drawdowns)
    dd_vals = [max_drawdown_in_window(tkr, ev_ts, closes, h)
               for tkr, ev_ts in events
               if tkr in studiable_tickers]
    dd_vals_f = [v for v in dd_vals if v is not None]
    max_dd_mean = _num(float(np.mean(dd_vals_f))) if dd_vals_f else None

    return {
        "h": int(h),
        "n_events": int(len(ep_records)),
        "n_studiable": int(K),
        "n_imputed_zero": int(n_imputed),
        "insufficient": bool(insufficient),
        "med_excess_pct": _num(float(np.median(x) * 100)) if K else None,
        "mean_excess_pct": _num(float(np.mean(x) * 100)) if K else None,
        "win_rate": _num(win_rate),
        "max_dd_mean_pct": max_dd_mean,
        "pre_drift_pct": _num(pre_mean * 100) if pre_mean is not None else None,
        "hac_t": _num(nw.get("t")),
        "hac_p": _num(nw.get("p")),
        "ci90": ci,
        "dsr": _num((dsr_val or {}).get("dsr")) if isinstance(dsr_val, dict) else _num(dsr_val),
        "split_half_same_sign": sh_same,
        "surv_lb_mean_pct": _num(lb_mean * 100),
        "surv_lb_hac_t": _num(lb_nw.get("t")),
    }


def _block_mean_ci(x: np.ndarray, block: int = 4, B: int = 5000, seed: int = 7) -> list | None:
    """Block-bootstrap 90% CI of the MEAN (lifted verbatim from hincl_event_study.py)."""
    x = np.asarray(x, float)
    n = len(x)
    if n < 4:
        return None
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    grid = np.arange(block)
    means = np.empty(B)
    for k in range(B):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + grid[None, :]).ravel()[:n] % n
        means[k] = x[idx].mean()
    return [round(float(np.percentile(means, p)), 5) for p in (5, 50, 95)]


# ---------------------------------------------------------------------------
# Event loaders — each returns [(ticker, event_date_PIT, subtype)]
# ---------------------------------------------------------------------------

def load_clinicaltrials() -> list[tuple[str, str, str]]:
    """Phase-3 starts (first_post) only.

    HALT EVENTS ARE EXCLUDED (M5): last_update is the latest administrative
    record touch on ClinicalTrials.gov (any later edit: results posting, contact
    change, etc.), NOT the date the halt became public. Anchoring the CAR window
    on last_update can start the measurement window well after the actual halt
    reaction, systematically mis-aligning the study. Halts will be re-enabled once
    anchored on the halt-disclosure date (first update where why_stopped/is_halt
    became true in the ClinicalTrials.gov change history).

    Note on operator precedence (fixed): the previous filter
      df[df["is_halt"] == True & df["last_update"].notna()]
    was a latent bug: `&` binds tighter than `==`, so it evaluated as
      df["is_halt"] == (True & df["last_update"].notna())
    which happened to work only because last_update was a str column with no NaN.
    Corrected form would be (df["is_halt"] == True) & df["last_update"].notna().
    Moot now that halt events are gated out entirely.
    """
    p = config.data_dir() / "clinicaltrials" / "trials.parquet"
    if not p.exists():
        return []
    df = pd.read_parquet(p)
    df = df[df["ticker"].notna() & df["ticker"].str.strip().ne("")]
    events: list[tuple[str, str, str]] = []
    # Phase-3 start: first_post (PIT — the date the trial was first posted publicly)
    phase3 = df[df["phases"].isin(["PHASE3", "PHASE2,PHASE3"]) & df["first_post"].notna()]
    for _, r in phase3.iterrows():
        events.append((str(r["ticker"]).upper().strip(), str(r["first_post"]), "phase3_start"))
    # Halt events excluded — see docstring (M5). Correct filter if re-enabling:
    # halts = df[(df["is_halt"] == True) & df["last_update"].notna()]  # noqa: E712
    return events


def load_openfda() -> list[tuple[str, str, str]]:
    """FDA approvals and label expansions. PIT anchor: status_date (YYYYMMDD -> ISO)."""
    p = config.data_dir() / "openfda" / "approvals.parquet"
    if not p.exists():
        return []
    df = pd.read_parquet(p)
    df = df[df["ticker"].notna() & df["status_date"].notna()]
    events: list[tuple[str, str, str]] = []
    for _, r in df.iterrows():
        raw = str(r["status_date"]).strip()
        # parse YYYYMMDD -> YYYY-MM-DD
        try:
            dt = pd.to_datetime(raw, format="%Y%m%d")
            date_str = str(dt.date())
        except Exception:  # noqa: BLE001
            continue
        subtype = str(r.get("kind", "approval"))
        events.append((str(r["ticker"]).upper().strip(), date_str, subtype))
    return events


def load_sp_index_changes() -> list[tuple[str, str, str]]:
    """S&P index adds/removes. PIT anchor: announce_date (NOT effective_date — M4 compliance).
    28 rows as of 2026-07-05 — well below floor; will emit null-print (M2 resolution)."""
    p = config.data_dir() / "sp_index_changes" / "changes.parquet"
    if not p.exists():
        return []
    df = pd.read_parquet(p)
    df = df[df["ticker"].notna() & df["announce_date"].notna()]
    events: list[tuple[str, str, str]] = []
    for _, r in df.iterrows():
        subtype = f"{r.get('action', 'change')}_{r.get('index', 'sp')}"
        events.append((str(r["ticker"]).upper().strip(),
                       str(pd.Timestamp(r["announce_date"]).date()), subtype))
    return events


def load_ipo_lockup() -> list[tuple[str, str, str]]:
    """IPO lockup expirations. PIT anchor: priced_date + lockup_days (or 90/180 standard).
    Uses actual per-deal lockup_days where available (from prospectus); falls back to
    standard 90d/180d windows as separate subtypes."""
    lockups_p = config.data_dir() / "ipo" / "lockups.parquet"
    cal_p = config.data_dir() / "ipo" / "calendar.parquet"
    if not lockups_p.exists():
        return []
    lockups = pd.read_parquet(lockups_p)
    events: list[tuple[str, str, str]] = []

    if cal_p.exists():
        cal = pd.read_parquet(cal_p)
        priced_map: dict[str, str] = {}
        for _, r in cal.iterrows():
            tkr = str(r.get("ticker", "") or "").strip().upper()
            pd_val = r.get("priced_date")
            if tkr and pd_val and pd.notna(pd_val):
                priced_map[tkr] = str(pd.Timestamp(pd_val).date())
    else:
        priced_map = {}

    for tkr_raw, row in lockups.iterrows():
        tkr = str(tkr_raw).upper().strip()
        # use priced_date from calendar; fallback to filing_date from lockups
        priced_raw = priced_map.get(tkr) or str(row.get("filing_date", "") or "")
        if not priced_raw or priced_raw == "nan":
            continue
        try:
            priced_ts = pd.Timestamp(priced_raw)
        except Exception:  # noqa: BLE001
            continue
        ld = row.get("lockup_days")
        if ld is not None and pd.notna(ld) and ld > 0:
            # actual per-deal lockup
            expiry = priced_ts + pd.Timedelta(days=int(ld))
            subtype = f"lockup_{int(ld)}d"
            events.append((tkr, str(expiry.date()), subtype))
        else:
            # standard fallbacks: both 90d and 180d (tagged separately)
            for window in (90, 180):
                expiry = priced_ts + pd.Timedelta(days=window)
                events.append((tkr, str(expiry.date()), f"lockup_std_{window}d"))
    return events


# Reaction bands, in units of the name's OWN trailing daily vol (see load_earnings_events).
# Fixed thresholds, not in-sample quantiles: a prior is only useful if the band a live
# event falls into can be computed the same way on the night it prints.
_REACTION_BANDS: tuple[tuple[str, float, float], ...] = (
    ("reaction_strong_up", 2.0, float("inf")),
    ("reaction_up", 0.5, 2.0),
    ("reaction_flat", -0.5, 0.5),
    ("reaction_down", -2.0, -0.5),
    ("reaction_strong_down", float("-inf"), -2.0),
)
_REACTION_VOL_WIN = 60      # sessions of trailing vol used to standardise the reaction
_REACTION_MIN_VOL = 1e-6


def reaction_band(r0z: float) -> str | None:
    """Map a vol-standardised day-0 reaction to its band name. None if not finite."""
    if r0z is None or not np.isfinite(r0z):
        return None
    for name, lo, hi in _REACTION_BANDS:
        if lo <= r0z < hi:
            return name
    return None


def earnings_day0(filing_date: pd.Timestamp, acceptance_dt: str,
                  cal: pd.DatetimeIndex) -> pd.Timestamp | None:
    """The first session that can PRICE an Item-2.02 filing.

    EDGAR gives the acceptance timestamp in UTC; the market that reacts is ET.  An
    8-K accepted at 20:15 UTC (16:15 ET) is an after-the-close release — the session
    that prices it is the NEXT one, and anchoring the study on the filing date would
    put the whole reaction outside the window.  Conversely a 06:45 ET release is
    priced by the filing date's own session.

    premarket  (< 09:30 ET)      -> day0 = the filing_date session
    afterhours (>= 16:00 ET)     -> day0 = the next session
    intraday   (09:30-16:00 ET)  -> day0 = the filing_date session (partially priced;
                                    carried as its own subtype so it can be inspected)

    Returns None when the timestamp is unusable or the calendar has no session left.
    """
    if not acceptance_dt or not str(acceptance_dt).strip():
        return None
    try:
        acc = pd.Timestamp(acceptance_dt)
        acc = acc.tz_localize("UTC") if acc.tzinfo is None else acc.tz_convert("UTC")
        acc_et = acc.tz_convert("America/New_York")
    except Exception:  # noqa: BLE001
        return None
    minutes = acc_et.hour * 60 + acc_et.minute
    after_hours = minutes >= 16 * 60
    side = "right" if after_hours else "left"
    pos = cal.searchsorted(pd.Timestamp(filing_date).normalize(), side=side)
    if pos >= len(cal):
        return None
    return cal[pos]


def earnings_session_rule(acceptance_dt: str) -> str | None:
    """premarket | intraday | afterhours from the ET acceptance time (None if unusable)."""
    if not acceptance_dt or not str(acceptance_dt).strip():
        return None
    try:
        acc = pd.Timestamp(acceptance_dt)
        acc = acc.tz_localize("UTC") if acc.tzinfo is None else acc.tz_convert("UTC")
        acc_et = acc.tz_convert("America/New_York")
    except Exception:  # noqa: BLE001
        return None
    minutes = acc_et.hour * 60 + acc_et.minute
    if minutes < 9 * 60 + 30:
        return "premarket"
    if minutes >= 16 * 60:
        return "afterhours"
    return "intraday"


def load_earnings_events(closes: pd.DataFrame | None = None,
                         spy: pd.Series | None = None) -> list[tuple[str, str, str]]:
    """Earnings announcements, anchored on REAL SEC Item-2.02 acceptance timestamps.

    M4 RE-ENABLED (was null-printed).  The original gate was correct and its stated
    unblock condition is now met: ``eps_quarterly.parquet.asof_date`` is a synthetic
    period_end + 60d placeholder and remains unusable, but
    ``data/edgar/earnings_8k_dates.parquet`` (collectors/edgar_earnings_8k.py, 98,975
    Item-2.02 rows / 1,314 names / 2004-08..2026-07) carries the real filing date AND
    the acceptance timestamp.  That store did not exist when M4 was written.

    SUBTYPE = the day-0 reaction band, not the event kind.  Every name reports every
    quarter, so an unconditional "earnings prior" is close to a market average and says
    nothing.  What carries information is the SIZE of the move the print produced,
    measured in units of the name's own normal daily move (r0z) — the free stand-in for
    the options-implied expected move, which this repo has for ETFs only
    (data/options_surface/ is index/sector/industry ETFs, no single names).

    NO LOOK-AHEAD: r0z is the day0 close-to-close excess return over the trailing-60d
    vol ending day0-1, so it is fully known at the day0 close — and ``car_for_event``
    starts its window AT the day0 close.  The conditioning variable is never inside the
    measured return.

    SURVIVORSHIP: the studiable set is whatever is in the close panel, which is current
    membership. ``aggregate_episodes`` carries the n_imputed_zero floor for the rest.

    Returns [] (-> honest null-print) when the store is absent or unreadable.
    """
    p = config.data_dir() / "edgar" / "earnings_8k_dates.parquet"
    if not p.exists():
        return []
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return []
    need = {"ticker", "filing_date", "acceptance_datetime"}
    if df.empty or not need <= set(df.columns):
        return []
    if closes is None or closes.empty:
        return []

    cal = closes.index
    events: list[tuple[str, str, str]] = []
    df = df[df["ticker"].notna() & df["filing_date"].notna()]

    for tkr, grp in df.groupby("ticker"):
        tkr = str(tkr).upper().strip()
        if tkr not in closes.columns:
            continue
        s = closes[tkr].dropna()
        if len(s) < _REACTION_VOL_WIN + 2:
            continue
        ret = s.pct_change()
        vol = ret.rolling(_REACTION_VOL_WIN).std()
        sret = (spy.reindex(s.index).pct_change() if spy is not None
                else pd.Series(0.0, index=s.index))
        exret = ret - sret.fillna(0.0)

        for _, r in grp.iterrows():
            try:
                fd = pd.Timestamp(r["filing_date"]).normalize()
            except Exception:  # noqa: BLE001
                continue
            rule = earnings_session_rule(r.get("acceptance_datetime"))
            d0 = earnings_day0(fd, r.get("acceptance_datetime"), cal)
            if d0 is None or rule is None:
                continue
            # r0z needs the name to actually have printed on day0 and to have a
            # trailing vol ending the session BEFORE it.
            if d0 not in exret.index:
                continue
            i = s.index.get_loc(d0)
            if not isinstance(i, int) or i < 1:
                continue
            v = vol.iloc[i - 1]
            r0 = exret.iloc[i]
            if not np.isfinite(v) or v <= _REACTION_MIN_VOL or not np.isfinite(r0):
                continue
            band = reaction_band(float(r0) / float(v))
            if band is None:
                continue
            subtype = band if rule != "intraday" else f"{band}_intraday"
            events.append((tkr, str(d0.date()), subtype))

    return events


def _gov_contract_stub() -> dict:
    """M1 resolution: gov-contract awards has no awardee-ticker mapping in sam_gov.
    Returns a null-only stub dict with a printed reason."""
    return {
        "event_type": "gov_contract",
        "schema": "ss_event_priors.v2",
        "is_context_only": True,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "insufficient": True,
        "null_reason": (
            "No awardee-ticker mapping available: sam_gov data is theme-level "
            "(keyed by basket_id, no individual company tickers). Gov-contract "
            "event study deferred to W6 data-gap pass."
        ),
        "priors": {},
    }


# ---------------------------------------------------------------------------
# Per-event-type prior computation
# ---------------------------------------------------------------------------

def compute_prior_for_type(
    event_type: str,
    events_raw: list[tuple[str, str, str]],
    closes: pd.DataFrame,
    spy: pd.Series | None,
    *,
    null_reason: str | None = None,
) -> dict:
    """Compute a full prior dict for one event type across all subtypes and horizons.
    Persists n + CI + null prints. Sub-floor priors carry insufficient=True."""
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    base = {
        "event_type": event_type,
        "schema": "ss_event_priors.v2",
        "is_context_only": True,
        "generated_at": generated_at,
    }

    if null_reason:
        base["insufficient"] = True
        base["null_reason"] = null_reason
        base["priors"] = {}
        return base

    if not events_raw:
        base["insufficient"] = True
        base["null_reason"] = "No events found in data sources."
        base["priors"] = {}
        return base

    # Backfill prices for event tickers not in breadth caches (IPO/FDA small-caps; B4 fix)
    event_tickers = list({t for t, _, _ in events_raw})
    closes_ext = _fetch_event_prices(event_tickers, closes)

    # Group by subtype
    from collections import defaultdict
    subtype_events: dict[str, list[tuple[str, pd.Timestamp]]] = defaultdict(list)
    for tkr, date_str, subtype in events_raw:
        try:
            ts = pd.Timestamp(date_str)
        except Exception:  # noqa: BLE001
            continue
        subtype_events[subtype].append((tkr, ts))

    # Also pool all subtypes together
    all_events: list[tuple[str, pd.Timestamp]] = []
    for evlist in subtype_events.values():
        all_events.extend(evlist)

    priors: dict = {}

    # Pooled priors across all subtypes
    pooled: dict = {}
    for h in HORIZONS:
        cell = aggregate_episodes(all_events, closes_ext, spy, h, event_type)
        pooled[f"h{h}d"] = cell
    priors["_pooled"] = pooled

    # Per-subtype priors
    for subtype, evlist in subtype_events.items():
        st_priors: dict = {}
        for h in HORIZONS:
            cell = aggregate_episodes(evlist, closes_ext, spy, h, event_type)
            st_priors[f"h{h}d"] = cell
        priors[subtype] = st_priors

    # BH-FDR across primary-horizon p-values (per-subtype + pooled)
    pvals: dict[str, float] = {}
    for key, hp in priors.items():
        cell_primary = hp.get(f"h{PRIMARY_H}d", {})
        p = cell_primary.get("hac_p")
        m = cell_primary.get("mean_excess_pct", 0) or 0
        if p is not None:
            p1 = (p / 2.0) if m > 0 else (1 - p / 2.0)
            pvals[key] = p1
    bh = benjamini_hochberg(pvals, alpha=0.10) if pvals else {}

    base["priors"] = priors
    base["bh_fdr"] = {k: _num(v) if not isinstance(v, dict) else v for k, v in bh.items()}
    base["n_events_total"] = int(len(all_events))
    base["subtypes"] = list(subtype_events.keys())
    return base


# ---------------------------------------------------------------------------
# Persist
# ---------------------------------------------------------------------------

def persist_prior(data: dict) -> pathlib.Path:
    """Write prior JSON (numpy-safe). Returns output path."""
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    et = data.get("event_type", "unknown")
    out = _OUT_DIR / f"{et}.json"
    out.write_text(json.dumps(data, indent=2, default=lambda o: _num(o) if isinstance(o, (np.integer, np.floating)) else str(o)))
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("[event_priors] loading US close panel…")
    closes = _us_closes()
    if closes.empty:
        print("[event_priors] ERROR: no close caches on disk — cannot compute priors")
        return 1
    spy = _spy_series(closes)
    print(f"[event_priors] panel: {closes.shape[1]} tickers, "
          f"{closes.index.min().date()} → {closes.index.max().date()}, "
          f"SPY={'found' if spy is not None else 'MISSING'}")

    results: dict[str, dict] = {}

    # --- clinicaltrials ---
    print("[event_priors] loading clinicaltrials…")
    ct_events = load_clinicaltrials()
    print(f"  {len(ct_events)} events loaded")
    ct_prior = compute_prior_for_type("clinicaltrials", ct_events, closes, spy)
    results["clinicaltrials"] = ct_prior
    p = persist_prior(ct_prior)
    print(f"  wrote {p}")

    # --- openfda ---
    print("[event_priors] loading openfda…")
    fda_events = load_openfda()
    print(f"  {len(fda_events)} events loaded")
    fda_prior = compute_prior_for_type("openfda", fda_events, closes, spy)
    results["openfda"] = fda_prior
    p = persist_prior(fda_prior)
    print(f"  wrote {p}")

    # --- sp_index_changes (M2: will likely be null-print; machinery in place) ---
    print("[event_priors] loading sp_index_changes…")
    sp_events = load_sp_index_changes()
    print(f"  {len(sp_events)} events loaded (floor={EVENT_FLOOR}; will null-print if K<{EVENT_FLOOR})")
    sp_prior = compute_prior_for_type("sp_index_changes", sp_events, closes, spy)
    results["sp_index_changes"] = sp_prior
    p = persist_prior(sp_prior)
    print(f"  wrote {p}")

    # --- ipo_lockup ---
    print("[event_priors] loading ipo_lockup…")
    ipo_events = load_ipo_lockup()
    print(f"  {len(ipo_events)} events loaded")
    ipo_prior = compute_prior_for_type("ipo_lockup", ipo_events, closes, spy)
    results["ipo_lockup"] = ipo_prior
    p = persist_prior(ipo_prior)
    print(f"  wrote {p}")

    # --- earnings (M4 RE-ENABLED: real Item-2.02 acceptance timestamps) ---
    print("[event_priors] loading earnings (EDGAR 8-K Item 2.02 acceptance timestamps)…")
    earn_closes = _deep_closes(closes)
    earn_spy = _spy_series(earn_closes)
    earn_events = load_earnings_events(earn_closes, earn_spy)
    print(f"  {len(earn_events)} events loaded "
          f"(panel {earn_closes.shape[1]} tickers, "
          f"{earn_closes.index.min().date()} → {earn_closes.index.max().date()})")
    earn_prior = compute_prior_for_type(
        "earnings", earn_events, earn_closes, earn_spy,
        null_reason=(
            None if earn_events else
            "data/edgar/earnings_8k_dates.parquet absent, unreadable, or joined to no "
            "priced name. Run `python -m collectors.edgar_earnings_8k` to build it. "
            "(eps_quarterly.parquet.asof_date remains a synthetic period_end+60d "
            "placeholder and is NOT usable as an announcement anchor.)"
        ),
    )
    earn_prior["anchor"] = "edgar_8k_item_2.02_acceptance_datetime"
    earn_prior["subtype_basis"] = (
        "day-0 excess return vs SPY / trailing-60d daily vol ending day0-1 (r0z); "
        "fixed bands, known at the day0 close, CAR window starts at that same close"
    )
    earn_prior["survivorship_note"] = (
        "Studiable names are current index membership — every absolute level is "
        "survivor-biased upward. Read the BAND SPREAD, not the level."
    )
    results["earnings"] = earn_prior
    p = persist_prior(earn_prior)
    print(f"  wrote {p}")

    # --- gov_contract stub (M1) ---
    print("[event_priors] gov_contract: null stub (no awardee-ticker source)")
    gov_prior = _gov_contract_stub()
    results["gov_contract"] = gov_prior
    p = persist_prior(gov_prior)
    print(f"  wrote {p}")

    # Summary
    print("\n[event_priors] summary:")
    for et, prior in results.items():
        n_ev = prior.get("n_events_total", 0)
        pooled = (prior.get("priors") or {}).get("_pooled", {})
        cell20 = pooled.get("h20d", {})
        insuf = prior.get("insufficient") or cell20.get("insufficient")
        k = cell20.get("n_studiable", 0)
        t = cell20.get("hac_t")
        print(f"  {et}: n_events={n_ev} K={k} hac_t={t} insufficient={insuf}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
