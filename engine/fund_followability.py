"""13F Fund Followability — DISPLAY-TIER ONLY.

Extends engine.manager_trades with four new lenses:
  * SLEEVE scoring  (new-position vs add-to-position excess + hit rate)
  * ROTATION IQ     (sector-rotation call quality, filing-date anchored)
  * FRONT-RUN       (crowd follow-through rate on a fund's NEW positions)
  * FOLLOW SCORE    (0-100 composite; follow/watch/fade/insufficient tier)

AXIS PURITY (SM2-R3): this module operates on the 13F axis ONLY. Insider
transactions, short-interest, and 13D/G ownership data must NEVER be blended
into any score computed here.

HONESTY:
  - Every score carries its n (observations) — no score without a sample size.
  - Filing lag of ~45 days is acknowledged: excess returns are measured FROM
    the public filing date (look-ahead-free), never from period_end.
  - Nulls are printed, not hidden — "insufficient" tier is a legitimate output.
  - The word "validated" does not appear here (CI-guarded repo-wide).

DISPLAY: these outputs power scoreboards and a display page. They feed no
calibrated key, Neural Web organ, allocation, or gate. WA-R2/NEXTL-U13
(13F as positive signal struck) are untouched — this is a track-record
context panel, not a signal.

NAMING (blocklist-guarded): "ownership_pressure", "sponsorship", "breakaway"
are forbidden. Public API uses: follow_score, rotation_iq, front_run, fade.
"""
from __future__ import annotations

import logging
import math
import statistics
from pathlib import Path
from typing import Callable

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sector ETF map (SM2 spec — MUST NOT be extended without a ruling).
# These are the only sector ETFs used in rotation IQ scoring.
# ---------------------------------------------------------------------------
SECTOR_ETF: dict[str, str] = {
    "Financials": "XLF",
    "Financial": "XLF",
    "Financial Services": "XLF",
    "Technology": "XLK",
    "Information Technology": "XLK",
    "Industrials": "XLI",
    "Health Care": "XLV",
    "Healthcare": "XLV",
    "Consumer Discretionary": "XLY",
    "Consumer Cyclical": "XLY",
    "Consumer Staples": "XLP",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Materials": "XLB",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
    "Communications": "XLC",
}

BENCHMARK = "SPY"

# ---------------------------------------------------------------------------
# Follow-score component weights (must sum to 1.0).
# edge       40%  — median buy excess (filing-anchored, SPY-relative)
# consistency 20% — fraction of quarter_history quarters with median > 0
# durability  25% — h126 excess vs h21; positive h126 means edge survives lag
# sell        15% — sell_skill (sell directed toward laggards)
# ---------------------------------------------------------------------------
_W_EDGE = 0.40
_W_CONSIST = 0.20
_W_DURABLE = 0.25
_W_SELL = 0.15

# minimum priced buys for a follow_score to exist
_MIN_BUYS = 4
# minimum quarters of quarter_history with >= 2 buys for consistency leg
_MIN_QH_FOR_CONSIST = 4
# n_penalty denominator: scale-in penalty disappears above this many buys
_PENALTY_DENOM = 12

# tanh mapping scale: maps excess-return floats to 0-100 range
# score = 50 + 50 * tanh(k * x); k chosen so x=5pp => ~87/100, x=-5pp => ~13/100
FOLLOW_VERSION = "4.review-fixes.2026-07-18"  # bump on any scoring-logic change (busts builder cache)
_TANH_K = 2.0 / 5.0  # 0.4 — so tanh(2 * excess/5) at excess=5pp gives tanh(2)≈0.96

# rotation IQ tanh scale: applied to the average signed sector-call excess (in pp units,
# so 5pp excess => score ~87). Documents the exact formula used.
_RIQ_TANH_K = 2.0 / 5.0  # same scale as edge; "5pp = very strong call"

# minimum absolute sector weight shift (pp) to count as a "call"
_RIQ_MIN_DELTA_PP = 1.0

# minimum n_calls for the RIQ score to be computed (a 1-2 call sample scoring
# 0-100 is noise); n is always printed regardless of this gate.
_RIQ_MIN_CALLS_FOR_SCORE = 3

# fixed horizon for forward-testing rotation calls (one quarter of sessions)
_ROT_HORIZON = 63

# ---------------------------------------------------------------------------
# Loader helpers (I/O isolated; injectable for tests)
# ---------------------------------------------------------------------------

def _default_price_loader(ticker: str, data_root: Path | None = None) -> pd.Series | None:
    """Load the yahoo close series for one ticker from data/yahoo/<ticker>.parquet.
    Returns a DatetimeIndex-sorted Series[float] or None when absent/corrupt.
    Usable as the price_loader callable in tests via monkeypatching or direct override.
    """
    try:
        from lib import config as _cfg
        root = Path(data_root) if data_root else _cfg.data_dir()
    except Exception:  # noqa: BLE001
        if data_root:
            root = Path(data_root)
        else:
            return None
    p = root / "yahoo" / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p, columns=["close"])
        s = df["close"].dropna()
        s.index = pd.to_datetime(s.index)
        return s.sort_index()
    except Exception:  # noqa: BLE001
        return None


def load_books(
    slugs: list[str],
    data_root: Path | None = None,
) -> dict[str, dict[str, pd.DataFrame]]:
    """Load raw snapshots for a list of fund slugs.

    Returns {slug: {period_end_str: DataFrame}}.  Amendments sub-directory
    is excluded (only the original quarterly filings are used here).
    Callers can pass data_root to override the repo root for tests.
    """
    try:
        from lib import config as _cfg
        base = Path(data_root) if data_root else _cfg.data_dir() / "smart_money"
    except Exception:  # noqa: BLE001
        if data_root:
            base = Path(data_root) / "smart_money"
        else:
            return {}
    out: dict[str, dict[str, pd.DataFrame]] = {}
    for slug in slugs:
        d = base / slug
        if not d.is_dir():
            continue
        by_period: dict[str, pd.DataFrame] = {}
        for p in sorted(d.glob("*.parquet")):
            if "amendments" in str(p):
                continue
            try:
                df = pd.read_parquet(p)
                if not df.empty:
                    by_period[p.stem] = df
            except Exception:  # noqa: BLE001
                continue
        if by_period:
            out[slug] = by_period
    return out


# ---------------------------------------------------------------------------
# Price helper — excess return from filing date, fixed or live horizon
# ---------------------------------------------------------------------------

def _excess(
    ticker: str,
    entry_date: str,
    price_loader: Callable[[str], pd.Series | None],
    horizon: int | None = None,
) -> float | None:
    """SPY-relative excess return for ticker from filing date.

    horizon=None  => live-to-latest-close (variable hold).
    horizon=N     => exactly N sessions; returns None when window not elapsed.
    Returns None when ticker or SPY cannot be priced, or entry post-dates data.
    This is the same look-ahead-free convention as engine.manager_trades.ClosePanel.excess.
    """
    s = price_loader(ticker)
    spy = price_loader(BENCHMARK)
    if s is None or spy is None or len(s) == 0 or len(spy) == 0:
        return None
    e = pd.Timestamp(entry_date)
    after = s.index[s.index >= e]
    if len(after) == 0:
        return None
    pos0 = s.index.get_loc(after[0])
    if isinstance(pos0, slice):
        pos0 = pos0.start
    if horizon is not None:
        if pos0 + horizon >= len(s):
            return None
        end_pos = pos0 + horizon
    else:
        end_pos = len(s) - 1
    if end_pos <= pos0:
        return None
    p0, p1 = float(s.iloc[pos0]), float(s.iloc[end_pos])
    if p0 <= 0:
        return None
    d0, d1 = s.index[pos0], s.index[end_pos]
    stock = p1 / p0 - 1.0
    # benchmark window aligned to the same calendar span
    spy_after = spy.index[spy.index >= d0]
    spy_before = spy.index[spy.index <= d1]
    if len(spy_after) == 0 or len(spy_before) == 0:
        return None
    b0, b1 = float(spy.loc[spy_after[0]]), float(spy.loc[spy_before[-1]])
    if b0 <= 0:
        return None
    return stock - (b1 / b0 - 1.0)


# ---------------------------------------------------------------------------
# Sleeve scoring (METHOD 1)
# ---------------------------------------------------------------------------

def _sleeve_scores(
    books: dict[str, pd.DataFrame],
    price_loader: Callable[[str], pd.Series | None],
    horizon: int = _ROT_HORIZON,
) -> dict[str, dict]:
    """Classify a fund's buys across its snapshot history as 'new' or 'add'.

    A ticker is 'new' if it was absent in the prior quarter's SH-type rows;
    'add' if already present (regardless of share-count delta).  This follows
    the 13F axis ONLY: we look only at what the fund reported holding.

    Returns {action: {n, median_excess, hit}} for keys 'new' and 'add'.
    Excess is measured from the public filing_date (look-ahead-free) at the
    fixed horizon (~one quarter of sessions).  Unpriceable tickers are skipped
    and excluded from n.
    """
    periods = sorted(books)
    by_sleeve: dict[str, list[float]] = {"new": [], "add": []}
    for i in range(1, len(periods)):
        prev_pe = periods[i - 1]
        cur_pe = periods[i]
        prev_df = books[prev_pe]
        cur_df = books[cur_pe]
        # get filing date from the current snapshot
        fd = ""
        if "filing_date" in cur_df.columns and len(cur_df):
            v = cur_df["filing_date"].iloc[0]
            fd = str(v) if v and str(v) != "nan" else ""
        if not fd:
            continue
        # prior-quarter held tickers (SH type, unique cusips)
        prev_eq = prev_df[prev_df["sh_type"] == "SH"] if "sh_type" in prev_df.columns else prev_df
        prev_cusips: set[str] = set(prev_eq["cusip"].astype(str).str.upper())
        # current-quarter SH rows
        cur_eq = cur_df[cur_df["sh_type"] == "SH"] if "sh_type" in cur_df.columns else cur_df
        # need ticker column (may or may not be pre-resolved)
        if "ticker" not in cur_eq.columns:
            continue
        seen: set[str] = set()
        for row in cur_eq[cur_eq["ticker"].notna()].itertuples(index=False):
            ticker = str(row.ticker).strip().upper()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            cusip = str(row.cusip).strip().upper() if "cusip" in cur_eq.columns else ""
            sleeve = "new" if cusip not in prev_cusips else "add"
            ex = _excess(ticker, fd, price_loader, horizon=horizon)
            if ex is not None:
                by_sleeve[sleeve].append(ex)
    result: dict[str, dict] = {}
    for sleeve, exs in by_sleeve.items():
        result[sleeve] = {
            "n": len(exs),
            "median_excess": round(statistics.median(exs), 4) if exs else None,
            "hit": round(sum(1 for x in exs if x > 0) / len(exs), 3) if exs else None,
        }
    return result


# ---------------------------------------------------------------------------
# Rotation IQ (METHOD 2)
# ---------------------------------------------------------------------------

def _resolve_sector(ticker: str, classifications: dict) -> str | None:
    """Return the sector string for a ticker, or None if unclassified."""
    tk = ticker.upper()
    entry = classifications.get(tk)
    if not entry or not isinstance(entry, dict):
        return None
    sec = entry.get("sector")
    if not sec or str(sec).lower() in ("none", "unclassified", ""):
        return None
    return str(sec)


def _sector_weights(
    snap: pd.DataFrame,
    classifications: dict,
) -> dict[str, float]:
    """Sector weight vector (% of total book, classified SH-type only) for one snapshot.

    Returns {sector: weight_pp} where weights sum to 100 over classified tickers.
    Unclassified tickers are excluded from the denominator as well as the numerator
    (so missing sector data doesn't dilute the weights of classified names).
    """
    eq = snap[snap["sh_type"] == "SH"] if "sh_type" in snap.columns else snap
    if eq.empty or "value_usd" not in eq.columns:
        return {}
    if "ticker" not in eq.columns:
        return {}
    agg: dict[str, float] = {}
    for row in eq[eq["ticker"].notna()].itertuples(index=False):
        ticker = str(row.ticker).strip().upper()
        if not ticker:
            continue
        sec = _resolve_sector(ticker, classifications)
        if sec is None:
            continue
        val = float(getattr(row, "value_usd", 0) or 0)
        agg[sec] = agg.get(sec, 0.0) + val
    total = sum(agg.values())
    if total <= 0:
        return {}
    return {sec: 100.0 * v / total for sec, v in agg.items()}


def _rotation_iq(
    books: dict[str, pd.DataFrame],
    classifications: dict,
    price_loader: Callable[[str], pd.Series | None],
    horizon: int = _ROT_HORIZON,
) -> dict:
    """Measure the quality of a fund's sector rotation calls.

    For each consecutive quarter pair (q_prev -> q_cur):
      1.  Compute sector weight vectors w_prev and w_cur (classified SH tickers,
          value_usd share).
      2.  delta = w_cur - w_prev in percentage-point terms.
      3.  A "call" is any sector with |delta| >= _RIQ_MIN_DELTA_PP.
      4.  Forward test: sector-ETF excess vs SPY over _ROT_HORIZON sessions
          starting at q_cur's filing_date (same look-ahead-free anchor).
          "into" call (delta > 0) hits when sector-ETF excess > 0 (SPY-relative
          return positive over the hold window).
          "out"  call (delta < 0) hits when sector-ETF excess < 0 (we avoided
          the sector that then lagged).
      5.  Signed excess for averaging: into calls keep the excess as-is; out calls
          negate it (so a correct out call contributes positive signed excess).

    hit_rate: |delta|-weighted share of calls where the direction was correct.
    score:    100 * (0.5 + 0.5 * tanh(_RIQ_TANH_K * weighted_mean_signed_excess))
              Bounded [0, 100]; 50 = neutral (no edge); above 50 = positive rotation IQ.
              The tanh mapping is chosen so +5pp mean signed excess => ~87/100 and
              -5pp => ~13/100 — a concrete, documented mapping that cannot be back-fitted.

    n_calls is the total number of (sector, quarter) calls tested.
    n_quarters is the number of consecutive-pair transitions tested.
    best_call carries the single highest-excess call for context display.
    """
    periods = sorted(books)
    all_weighted_hit: list[tuple[float, float]] = []  # (|delta|, 1.0 if hit else 0.0)
    all_weighted_excess: list[tuple[float, float]] = []  # (|delta|, signed_excess)
    n_calls = 0
    n_quarters = 0
    best_call: dict | None = None

    for i in range(1, len(periods)):
        prev_pe = periods[i - 1]
        cur_pe = periods[i]
        # get filing date from current quarter
        cur_df = books[cur_pe]
        fd = ""
        if "filing_date" in cur_df.columns and len(cur_df):
            v = cur_df["filing_date"].iloc[0]
            fd = str(v) if v and str(v) != "nan" else ""
        if not fd:
            continue
        w_prev = _sector_weights(books[prev_pe], classifications)
        w_cur = _sector_weights(cur_df, classifications)
        if not w_cur:
            continue
        # all sectors in either period
        all_secs = set(w_prev) | set(w_cur)
        transition_has_call = False
        for sec in all_secs:
            delta = w_cur.get(sec, 0.0) - w_prev.get(sec, 0.0)
            if abs(delta) < _RIQ_MIN_DELTA_PP:
                continue
            etf = SECTOR_ETF.get(sec)
            if etf is None:
                continue
            fwd = _excess(etf, fd, price_loader, horizon=horizon)
            if fwd is None:
                continue
            n_calls += 1
            transition_has_call = True
            # direction: into (delta>0) => hit if fwd>0; out (delta<0) => hit if fwd<0
            into = delta > 0
            hit = (fwd > 0) if into else (fwd < 0)
            signed_excess = fwd if into else -fwd  # both positive when correct
            abs_delta = abs(delta)
            all_weighted_hit.append((abs_delta, 1.0 if hit else 0.0))
            all_weighted_excess.append((abs_delta, signed_excess))
            if best_call is None or (fwd > (best_call.get("fwd_excess") or -999)):
                best_call = {
                    "sector": sec,
                    "period": cur_pe,
                    "delta_pp": round(delta, 2),
                    "fwd_excess": round(fwd, 4),
                }
        if transition_has_call:
            n_quarters += 1

    if not all_weighted_hit:
        return {
            "score": None,
            "hit_rate": None,
            "n_calls": 0,
            "n_quarters": 0,
            "best_call": None,
        }

    total_weight = sum(w for w, _ in all_weighted_hit)
    hit_rate = (sum(w * h for w, h in all_weighted_hit) / total_weight
                if total_weight > 0 else None)
    mean_signed_excess = (sum(w * e for w, e in all_weighted_excess) / total_weight
                          if total_weight > 0 else None)
    score: float | None = None
    # Gate: a 1-2 call sample scoring 0-100 is noise; n is always returned regardless.
    if mean_signed_excess is not None and n_calls >= _RIQ_MIN_CALLS_FOR_SCORE:
        # bounded [0, 100]; 50 = neutral; tanh maps ±5pp to ~±0.96 → score ~87 / ~13.
        # _excess() returns FRACTIONAL returns — convert to pp (*100) before the
        # pp-calibrated tanh (units bug fixed 2026-07-18; scores were pinned ~50).
        score = round(100.0 * (0.5 + 0.5 * math.tanh(_RIQ_TANH_K * mean_signed_excess * 100.0)), 1)
        score = max(0.0, min(100.0, score))

    return {
        "score": score,
        "hit_rate": round(hit_rate, 3) if hit_rate is not None else None,
        "n_calls": n_calls,
        "n_quarters": n_quarters,
        "best_call": best_call,
    }


# ---------------------------------------------------------------------------
# Front-run (METHOD 3)
# ---------------------------------------------------------------------------

def _holder_index(books_by_fund: dict[str, dict[str, pd.DataFrame]]) -> dict[str, dict[str, set]]:
    """One-pass cohort holder index: {period: {TICKER: {slugs holding it}}}.

    Built ONCE per compute_followability run and shared across the per-fund
    _front_run calls — the previous per-ticker cross-fund scan was
    O(funds^2 x periods x tickers) and cost ~2.5 min at the full roster.
    """
    idx: dict[str, dict[str, set]] = {}
    for f_slug, f_books in books_by_fund.items():
        for pe, df in f_books.items():
            if df is None or "ticker" not in getattr(df, "columns", []):
                continue
            eq = df[df["sh_type"] == "SH"] if "sh_type" in df.columns else df
            per = idx.setdefault(pe, {})
            for t in eq["ticker"].dropna().astype(str).str.strip().str.upper().unique():
                if t:
                    per.setdefault(t, set()).add(f_slug)
    return idx


def _front_run(
    slug: str,
    books: dict[str, pd.DataFrame],
    books_by_fund: dict[str, dict[str, pd.DataFrame]],
    price_loader: Callable[[str], pd.Series | None],
    horizon: int = _ROT_HORIZON,
    holder_idx: dict[str, dict[str, set]] | None = None,
) -> dict:
    """Measure crowd follow-through on this fund's NEW positions.

    For each NEW position of fund f at q_t (ticker absent in q_{t-1}), we check
    whether the cohort-wide count of OTHER funds holding that ticker INCREASED
    from q_t to q_{t+1} — i.e., "did the crowd follow this fund into the name?"

    crowd_follow_rate: share of tracked new positions where OTHER funds' holder
        count grew from q_t to q_{t+1}.  Only positions where q_{t+1} data is
        available cohort-wide are included.
    median_next_q_excess: median SPY-relative excess of these new positions
        from f's filing_date_t over the fixed horizon.  Unpriceable positions
        are counted out of n but not penalised.
    n_new_tracked: number of new positions included in the analysis.
    """
    my_periods = sorted(books)
    all_periods: set[str] = set(my_periods)
    for other_slug, other_books in books_by_fund.items():
        if other_slug != slug:
            all_periods |= set(other_books)
    all_periods_sorted = sorted(all_periods)

    crowd_results: list[float] = []   # 1.0 = crowd followed, 0.0 = did not
    excess_results: list[float] = []

    for i in range(1, len(my_periods)):
        prev_pe = my_periods[i - 1]
        cur_pe = my_periods[i]
        # find q_{t+1} — the next period after cur_pe in the global calendar
        try:
            idx_cur = all_periods_sorted.index(cur_pe)
        except ValueError:
            continue
        if idx_cur + 1 >= len(all_periods_sorted):
            continue
        next_pe = all_periods_sorted[idx_cur + 1]

        cur_df = books.get(cur_pe)
        prev_df = books.get(prev_pe)
        if cur_df is None or prev_df is None:
            continue
        fd = ""
        if "filing_date" in cur_df.columns and len(cur_df):
            v = cur_df["filing_date"].iloc[0]
            fd = str(v) if v and str(v) != "nan" else ""
        if not fd:
            continue

        # my new positions at q_t = tickers in cur but not prev (SH type)
        prev_eq = prev_df[prev_df["sh_type"] == "SH"] if "sh_type" in prev_df.columns else prev_df
        prev_cusips: set[str] = set(prev_eq["cusip"].astype(str).str.upper())
        cur_eq = cur_df[cur_df["sh_type"] == "SH"] if "sh_type" in cur_df.columns else cur_df
        if "ticker" not in cur_eq.columns:
            continue

        new_tickers: list[str] = []
        for row in cur_eq[cur_eq["ticker"].notna()].itertuples(index=False):
            ticker = str(row.ticker).strip().upper()
            if not ticker:
                continue
            cusip = str(row.cusip).strip().upper() if "cusip" in cur_eq.columns else ""
            if cusip not in prev_cusips:
                new_tickers.append(ticker)

        if not new_tickers:
            continue

        # count OTHER funds holding each ticker at q_t vs q_{t+1} — via the shared
        # holder index (built once per run); fall back to building it here when the
        # caller didn't supply one (tests / direct calls).
        if holder_idx is None:
            holder_idx = _holder_index(books_by_fund)
        at_qt = holder_idx.get(cur_pe, {})
        at_qnext = holder_idx.get(next_pe, {})
        for ticker in new_tickers:
            count_at_qt = len(at_qt.get(ticker, set()) - {slug})
            count_at_qnext = len(at_qnext.get(ticker, set()) - {slug})
            crowd_results.append(1.0 if count_at_qnext > count_at_qt else 0.0)
            ex = _excess(ticker, fd, price_loader, horizon=horizon)
            if ex is not None:
                excess_results.append(ex)

    n = len(crowd_results)
    return {
        "crowd_follow_rate": round(sum(crowd_results) / n, 3) if n > 0 else None,
        "n_new_tracked": n,
        "median_next_q_excess": (round(statistics.median(excess_results), 4)
                                  if excess_results else None),
    }


# ---------------------------------------------------------------------------
# Loser streak (METHOD 5)
# ---------------------------------------------------------------------------

def _loser_streak(quarter_history: list[dict]) -> int:
    """Count consecutive most-recent quarters with median_excess < 0.

    Works backwards from the last element of quarter_history (most recent).
    Returns 0 when there is no history or the latest quarter was positive.

    Note: the streak reads per-quarter open-ended cohort medians; the MOST RECENT
    quarters have short windows so the long-history bias is small there — documented
    tradeoff, bounded further by the 7-day cache age cap in Phase 4.5.
    """
    streak = 0
    for q in reversed(quarter_history):
        med = q.get("median_excess")
        if med is None:
            break
        if med < 0:
            streak += 1
        else:
            break
    return streak


# ---------------------------------------------------------------------------
# Component scoring helpers
# ---------------------------------------------------------------------------

def _tanh_map(value: float, k: float = _TANH_K) -> float:
    """Map a raw value to [0, 100] via 50 + 50*tanh(k*value).

    k=0.4 means ±5pp excess => score ~87/~13.  Bounded strictly [0,100].
    """
    return max(0.0, min(100.0, 50.0 + 50.0 * math.tanh(k * value)))


def _edge_component(median_buy_excess: float | None) -> float:
    """Edge: maps median_buy_excess (in fractional return units) to 0-100.

    Converts to percentage-point units first (* 100) then applies tanh mapping
    so +5pp median excess => ~87, −5pp => ~13, 0pp => 50.
    """
    if median_buy_excess is None:
        return 50.0  # neutral when no data — will be gated by n_buys check upstream
    # convert fractional to pp: 0.05 → 5pp
    return _tanh_map(median_buy_excess * 100.0)


def _consistency_component(quarter_history: list[dict]) -> float | None:
    """Consistency: fraction of quarter_history quarters with median_excess > 0.

    Requires at least _MIN_QH_FOR_CONSIST quarters.  Returns None when insufficient.
    """
    meds = [q.get("median_excess") for q in (quarter_history or [])
            if q.get("median_excess") is not None]
    if len(meds) < _MIN_QH_FOR_CONSIST:
        return None
    return round(sum(1 for m in meds if m > 0) / len(meds), 3)


def _durability_component(decay: dict | None) -> float:
    """Durability: does the edge survive the 13F lag (~3 months / h126)?

    Uses h126 median excess (h126-only; edge survives the ~3-month lag).
    Positive h126 scores high (edge persists past the lag window — the most
    important criterion for followability). Neutral (50) when h126 is missing.

    Formula: tanh_map(h126 * 100), same scale as edge component so scores
    are directly comparable across components.
    """
    if not decay:
        return 50.0
    h126 = (decay.get("h126") or {}).get("med")
    if h126 is None:
        return 50.0
    return _tanh_map(h126 * 100.0)


def _sell_component(sell_skill: float | None) -> float:
    """Sell skill: maps sell_skill to 0-100 via tanh.

    sell_skill in manager_trades = mean of (−since_excess) for sell/trim trades,
    so positive = the fund sold before underperformance, i.e. good discipline.
    Values are already in fractional return units; multiply by 100 before tanh.
    """
    if sell_skill is None:
        return 50.0
    return _tanh_map(sell_skill * 100.0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_EMPTY_SLEEVES = {
    "new": {"n": 0, "median_excess": None, "hit": None},
    "add": {"n": 0, "median_excess": None, "hit": None},
}
_EMPTY_RIQ = {
    "score": None,
    "hit_rate": None,
    "n_calls": 0,
    "n_quarters": 0,
    "best_call": None,
}
_EMPTY_FRONT_RUN = {
    "crowd_follow_rate": None,
    "n_new_tracked": 0,
    "median_next_q_excess": None,
}
_EMPTY_COMPONENTS = {
    "edge": 50.0, "consistency": 50.0, "durability": 50.0, "sell": 50.0,
    "n_penalty": 0.0,
}


def _empty_result() -> dict:
    return {
        "follow_score": None,
        "follow_tier": "insufficient",
        "components": dict(_EMPTY_COMPONENTS),
        "sleeves": {k: dict(v) for k, v in _EMPTY_SLEEVES.items()},
        "rotation_iq": dict(_EMPTY_RIQ),
        "front_run": dict(_EMPTY_FRONT_RUN),
        "loser_streak_q": 0,
    }


def compute_followability(
    tracker: dict,
    books_by_fund: dict[str, dict[str, pd.DataFrame]],
    classifications: dict,
    data_root: None | str | Path = None,
    price_loader: Callable[[str], pd.Series | None] | None = None,
) -> dict[str, dict]:
    """Compute per-fund followability scores from 13F filing data.

    Parameters
    ----------
    tracker:
        The dict returned by engine.manager_trades.compute_tracker() (contains
        by_fund[slug]['scorecard'] for each tracked fund — the source of
        n_buys, quarter_history, decay, sell_skill, buy_hit_rate).
    books_by_fund:
        {slug: {period_end_str: DataFrame}} of raw snapshots. Use load_books()
        to build this from disk. Each DataFrame is the unmodified parquet rows
        from data/smart_money/<slug>/<period>.parquet (requires 'ticker' column —
        pre-resolved by the caller or by manager_trades resolver; unresolved rows
        with no ticker are silently skipped in rotation/sleeve math).
    classifications:
        {ticker: {sector, ...}} map from engine.fund_intelligence.load_classifications().
        Tickers not in the map or with None/Unclassified sector are excluded from
        sector-rotation math (not a failure — just excluded from that component).
    data_root:
        Override for the data/ directory (used in tests without live data).
    price_loader:
        Optional injectable callable(ticker: str) -> pd.Series | None.
        Defaults to _default_price_loader using data_root.  MUST return a
        DatetimeIndex-sorted Series of close prices or None.

    Returns
    -------
    {slug: per-fund result dict} with ALL of the following keys always present
    (even when insufficient data): follow_score, follow_tier, components,
    sleeves, rotation_iq, front_run, loser_streak_q.

    follow_tier:
        "insufficient" — n_buys < _MIN_BUYS (4) or no priced data at all.
        "fade"         — loser_streak_q >= 3 (consistently loses; streak-only per
                         operator's literal criterion — review 2026-07-18: score-fade
                         arm struck; marquee low-turnover managers must not be excluded
                         from boards by the SPY-ruler score alone).
        "follow"       — follow_score >= 65 AND n_buys >= 8.
        "watch"        — all other cases with a valid score.

    DISPLAY-TIER ONLY. Never feed into calibrated keys, NW organs,
    allocations, or gates. (SM2-R3: 13F axis ONLY — no insider/short blending.)
    """
    if price_loader is None:
        _dr = Path(data_root) if data_root else None
        def price_loader(ticker: str, _root=_dr) -> pd.Series | None:
            return _default_price_loader(ticker, _root)

    # extract scorecard map from tracker (by_fund[slug]['scorecard'])
    by_fund: dict = tracker.get("by_fund", {}) if isinstance(tracker, dict) else {}
    all_slugs = set(books_by_fund) | set(by_fund)

    # pre-resolve ticker columns where missing (books may be raw snapshots)
    # — attempt to use manager_trades resolver; degrade to raw if unavailable
    _resolved_books: dict[str, dict[str, pd.DataFrame]] = {}
    for slug, periods in books_by_fund.items():
        resolved_periods: dict[str, pd.DataFrame] = {}
        for pe, df in periods.items():
            if "ticker" in df.columns:
                resolved_periods[pe] = df
            else:
                # attempt resolution via manager_trades helpers
                try:
                    from engine.smart_money import resolve_tickers, name_ticker_map, full_cusip_map
                    nm = name_ticker_map()
                    cm, _ = full_cusip_map()
                    resolved_periods[pe] = resolve_tickers(df, nm, cm)
                except Exception:  # noqa: BLE001
                    resolved_periods[pe] = df
        _resolved_books[slug] = resolved_periods

    # cohort holder index built ONCE (perf: the per-fund cross-scan was quadratic)
    try:
        holder_idx = _holder_index(_resolved_books)
    except Exception:  # noqa: BLE001
        holder_idx = None

    out: dict[str, dict] = {}
    for slug in all_slugs:
        try:
            out[slug] = _compute_one(
                slug=slug,
                scorecard=(by_fund.get(slug, {}) or {}).get("scorecard", {}),
                books=_resolved_books.get(slug, {}),
                books_by_fund=_resolved_books,
                classifications=classifications,
                price_loader=price_loader,
                holder_idx=holder_idx,
            )
        except Exception:  # noqa: BLE001 — per-fund isolation; one bad fund never fails others
            log.debug("fund_followability: compute failed for %s", slug, exc_info=True)
            out[slug] = _empty_result()
    return out


def _compute_one(
    slug: str,
    scorecard: dict,
    books: dict[str, pd.DataFrame],
    books_by_fund: dict[str, dict[str, pd.DataFrame]],
    classifications: dict,
    price_loader: Callable[[str], pd.Series | None],
    holder_idx: dict[str, dict[str, set]] | None = None,
) -> dict:
    """Compute followability for a single fund. Called once per fund; any
    exception is caught by compute_followability and returns _empty_result()."""

    n_buys: int = int(scorecard.get("n_buys") or 0)
    quarter_history: list[dict] = scorecard.get("quarter_history") or []
    decay: dict | None = scorecard.get("decay")
    sell_skill: float | None = scorecard.get("sell_skill")
    median_buy_excess: float | None = scorecard.get("median_buy_excess")

    # METHOD 5: loser streak (always computable from scorecard)
    loser_streak = _loser_streak(quarter_history)

    # METHOD 1: sleeves
    sleeves = dict(_EMPTY_SLEEVES)
    if books:
        try:
            raw = _sleeve_scores(books, price_loader)
            sleeves = raw
        except Exception:  # noqa: BLE001
            log.debug("sleeve_scores failed for %s", slug, exc_info=True)

    # METHOD 2: rotation IQ
    riq = dict(_EMPTY_RIQ)
    if books:
        try:
            riq = _rotation_iq(books, classifications, price_loader)
        except Exception:  # noqa: BLE001
            log.debug("rotation_iq failed for %s", slug, exc_info=True)

    # METHOD 3: front-run (holder_idx shared across funds — see _holder_index)
    fr = dict(_EMPTY_FRONT_RUN)
    if books:
        try:
            fr = _front_run(slug, books, books_by_fund, price_loader,
                            holder_idx=holder_idx)
        except Exception:  # noqa: BLE001
            log.debug("front_run failed for %s", slug, exc_info=True)

    # METHOD 4: follow score
    # Gate: need at least _MIN_BUYS (4) priced buys for any score
    if n_buys < _MIN_BUYS or median_buy_excess is None:
        return {
            "follow_score": None,
            "follow_tier": "insufficient",
            "components": dict(_EMPTY_COMPONENTS),
            "sleeves": sleeves,
            "rotation_iq": riq,
            "front_run": fr,
            "loser_streak_q": loser_streak,
        }

    # compute components.
    # EDGE RULER (adjudicated 2026-07-18): prefer the FIXED-HORIZON h63 decay median
    # (copy-the-buy-for-a-quarter measure) over the open-ended since-filing median —
    # the open-ended stat structurally punishes long-history funds (years of
    # compounding vs SPY), which measures fund quality, not followability. Fall back
    # to since-filing median only when h63 has n < 8; basis recorded for display.
    h63 = ((decay or {}).get("h63") or {})
    if h63.get("med") is not None and (h63.get("n") or 0) >= 8:
        edge_raw = _edge_component(h63["med"])
        edge_basis = "h63"
    else:
        edge_raw = _edge_component(median_buy_excess)
        edge_basis = "since_filing"
    consistency_raw = _consistency_component(quarter_history)
    durable_raw = _durability_component(decay)
    sell_raw = _sell_component(sell_skill)

    # consistency: if insufficient history, omit (use 50 neutral, but mark)
    consistency_val = consistency_raw if consistency_raw is not None else 50.0
    # components dict — round for display
    components = {
        "edge": round(edge_raw, 1),
        "edge_basis": edge_basis,
        "consistency": round(consistency_val * 100.0 if consistency_raw is not None
                             else consistency_val, 1),
        "durability": round(durable_raw, 1),
        "sell": round(sell_raw, 1),
        "n_penalty": round(min(1.0, n_buys / _PENALTY_DENOM), 3),
    }
    # consistency component is stored as 0-100 (fraction * 100)
    # recalculate for the weighted sum using the 0-100 scale
    edge_c = edge_raw  # already 0-100
    consist_c = consistency_val * 100.0 if consistency_raw is not None else 50.0
    durable_c = durable_raw  # already 0-100
    sell_c = sell_raw  # already 0-100

    raw_score = (_W_EDGE * edge_c + _W_CONSIST * consist_c
                 + _W_DURABLE * durable_c + _W_SELL * sell_c)
    n_penalty = min(1.0, n_buys / _PENALTY_DENOM)
    follow_score = round(raw_score * n_penalty, 1)
    follow_score = max(0.0, min(100.0, follow_score))

    # METHOD 4 tier assignment
    # review 2026-07-18: score-fade struck; fade = streak-only per operator's literal
    # criterion ("consistently loses"); low-copyability funds stay "watch" and are
    # naturally down-weighted by the quality term in boards — SPY-ruler score alone
    # must not exclude marquee low-turnover managers.
    if loser_streak >= 3:
        tier = "fade"
    elif follow_score >= 65 and n_buys >= 8:
        tier = "follow"
    else:
        tier = "watch"

    return {
        "follow_score": follow_score,
        "follow_tier": tier,
        "components": components,
        "sleeves": sleeves,
        "rotation_iq": riq,
        "front_run": fr,
        "loser_streak_q": loser_streak,
    }
