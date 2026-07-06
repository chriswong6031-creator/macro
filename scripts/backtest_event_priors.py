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
- M4 (CORRECTED): earnings is null-printed. eps_quarterly.parquet asof_date is
  period_end + exactly 60 calendar days for every row — a mechanical placeholder,
  NOT a real SEC filed date or earnings-announcement date. Computing priors against
  this synthetic date is methodologically unsound (the event window does not align
  with the actual announcement reaction). Earnings will be re-enabled once a real
  announcement/filing date source is wired (e.g. EDGAR 8-K filing timestamps).
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


def load_earnings_events() -> list[tuple[str, str, str]]:
    """Earnings event loader — GATED (null-print) until a real PIT date is available.

    eps_quarterly.parquet asof_date is period_end + exactly 60 calendar days for
    every row: a synthetic mechanical placeholder. Inspection of the 65208-row store
    shows min=median=max=60 days offset, confirming the date is never the actual
    SEC filed date or earnings-announcement date. Running an event study against this
    placeholder produces a window that starts 60d after period end — a systematic
    mis-alignment with no relationship to actual announcement reactions.

    Returns [] unconditionally. compute_prior_for_type will emit insufficient=True
    null-print. Re-enable once EDGAR 8-K filing timestamps or a vendor announcement-
    date feed is wired into eps_quarterly (replace asof_date with that field).
    """
    return []


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

    # --- earnings (M4: null-print — asof_date is period_end+60d placeholder, not real PIT) ---
    print("[event_priors] earnings: null-print (asof_date=period_end+60d placeholder, not real announcement date)")
    earn_prior = compute_prior_for_type(
        "earnings", [], closes, spy,
        null_reason=(
            "asof_date in eps_quarterly.parquet is period_end + exactly 60 calendar days "
            "(verified: min=median=max=60d offset across all rows). This is a synthetic "
            "placeholder, not a real SEC filing date or earnings-announcement date. "
            "Re-enable once EDGAR 8-K timestamps or a vendor announcement-date feed is wired."
        ),
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
