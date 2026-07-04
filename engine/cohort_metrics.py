"""Cohort-context metrics for the Setup-Species program (W0.4).

Spec: research/SETUP_SPECIES_MASTERPLAN_BY_FABLE.md §3.3

WHAT THIS MODULE COMPUTES (display-only, never touches blend_sorted/scores):
  For each ticker in the ~500 sector-mapped priced names:

  peer_washout_pct  — share of cohort members in multi-TF washout
                      (reuses coiled.washout_ctx per member)
  peer_reclaim_pct  — share with a fresh bottom-turn event:
                      fresh T1-T3 cascade cross OR 10dMA reclaim while washed out
                      (second derivative of a bottom)
  peer_macd_turn_pct — share with fresh T1-T3 cascade crosses
                       (reuses member tier states from subsector_confluence output)

  Rubber-Band Score — knife-vs-cohort-liquidation discriminator:
      z of target's 252d-trailing drawdown within its cohort's drawdown distribution
      × cohort cohesion (group_flow._mean_pairwise_corr change primitive)
      × peer_washout_pct
      High cohort washout + typical-for-cohort target drawdown + rising cohesion
      → rubber band (high score); lone extreme drawdown + low cohort washout → knife.

  within-cohort RS rank — 20d return rank within sector cohort, appended daily to
      data/cohort_metrics/<YYYY-MM-DD>.parquet  (S7 dependency, series idempotent)

COVERAGE LAW (pre-registered §3.3):
  A cohort metric is computed ONLY when ≥70% of members have computable state.
  Every peer_* field is stamped with coverage_pct + n_covered/n_members.
  Below threshold → NULL, never a partial percentage.

PERFORMANCE:
  Member T1-T3 tier states are read from the already-computed subsector_confluence
  JSON (avoids recomputing the full cascade for 500 names).  Per-ticker price loads
  are cached in-process (basket_index._load_member_ohlcv has its own LRU cache).
  Washout/reclaim/drawdown require price series — these are loaded once per ticker.
  Cohesion requires a DataFrame of member returns — built from cached close series.

WIRING:
  Called by scripts/build_cohort_metrics.py (nightly, display-only).
  Emits site/factordata/cohort_metrics.json + data/cohort_metrics/<date>.parquet.
  New data paths are NOT gitignored; the build script adds them to the sentinel
  git-add set.

GOTCHA:
  Heavy per-ticker stores may be absent locally (R2 data plane).
  Every price load is wrapped with a None-guard; absent stores yield None coverage.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Optional
import datetime

import numpy as np
import pandas as pd

from engine import coiled as _coiled
from engine import basket_index
from engine.group_flow import _mean_pairwise_corr

log = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────
COVERAGE_THRESHOLD = 0.70   # §3.3 coverage law: ≥70% required
MIN_MEMBERS        = 5      # minimum cohort size to compute any metric
DD_LOOKBACK        = 252    # trailing window for drawdown computation (1 year)
COHESION_WINDOW    = 40     # mean pairwise corr window (mirrors group_flow default)
COHESION_PREV_WIN  = 20     # prior window for cohesion change
RS_WIN             = 20     # return window for within-cohort RS rank

# T1-T3 are "fresh turn" tiers (T4 = earliest/forming, excluded from reclaim count)
FRESH_TIERS = ("T1", "T2", "T3")


# ── helpers ────────────────────────────────────────────────────────────────────

def _close(ticker: str) -> Optional[pd.Series]:
    """Load close series for ticker; return None on any failure or absence.

    W1.5 (§7): falls back to the massive whole-market store
    (data/massive_stock_day/<T>.parquet, ~20k names × 5y) when the adjusted
    stores don't carry the name. The massive closes are RAW (unadjusted)
    day-aggregate prints — a split inside the lookback would fabricate a
    capitulation — so the fallback carries a hard SPLIT GUARD: any
    close-to-close jump beyond ±ln(1.8) marks the series None (not-covered).
    Split-suspect names stay honestly uncovered (the ≥70% coverage law counts
    them) instead of poisoning cohort state. Per-TF warm-up verification is
    inherent: every state function returns None below its own depth
    requirement (washout_ctx ≥308 bars, etc.) and coverage_pct says so.
    """
    try:
        df = basket_index._load_member_ohlcv(ticker)
        if df is not None and "close" in df.columns:
            c = df["close"].dropna()
            if len(c) > 0:
                return c
    except Exception:  # noqa: BLE001
        pass
    # --- W1.5 massive-store fallback (unadjusted; split-guarded) ---
    try:
        from lib import config as _config  # noqa: PLC0415
        fp = Path(_config.data_dir()) / "massive_stock_day" / f"{ticker}.parquet"
        if not fp.exists():
            return None
        c = pd.read_parquet(fp)["close"].dropna().sort_index()
        if len(c) < 2:
            return None
        r = np.abs(np.log(c.values[1:] / c.values[:-1]))
        if np.nanmax(r) > np.log(1.8):
            return None            # split-suspect — uncovered, never poisoned
        return c
    except Exception:  # noqa: BLE001
        return None


def _drawdown_252(close: pd.Series) -> Optional[float]:
    """Current drawdown from 252-bar trailing high.  Returns None if too short."""
    try:
        c = close.dropna()
        if len(c) < 20:
            return None
        n = min(DD_LOOKBACK, len(c))
        hi = float(c.iloc[-n:].max())
        if hi <= 0:
            return None
        return float(c.iloc[-1] / hi - 1.0)
    except Exception:  # noqa: BLE001
        return None


def _above_ma10(close: pd.Series) -> bool:
    """True if the latest close is above the 10-bar MA.  Safe: returns False on shortfall."""
    try:
        c = close.dropna()
        if len(c) < 10:
            return False
        ma10 = float(c.iloc[-10:].mean())
        return bool(c.iloc[-1] > ma10)
    except Exception:  # noqa: BLE001
        return False


def _ret_n(close: pd.Series, n: int) -> Optional[float]:
    """n-bar return (close[-1] / close[-n-1] - 1).  None if too short."""
    try:
        c = close.dropna()
        if len(c) < n + 1:
            return None
        return float(c.iloc[-1] / c.iloc[-(n + 1)] - 1.0)
    except Exception:  # noqa: BLE001
        return None


def _coverage_null(n_covered: int, n_members: int) -> dict:
    """Return the null payload (coverage law not met)."""
    pct = round(100.0 * n_covered / n_members, 1) if n_members > 0 else 0.0
    return {
        "peer_washout_pct": None,
        "peer_reclaim_pct": None,
        "peer_macd_turn_pct": None,
        "rubber_band_score": None,
        "coverage_pct": pct,
        "n_covered": n_covered,
        "n_members": n_members,
        "coverage_law": "BELOW_THRESHOLD",
    }


# ── per-member state builder ──────────────────────────────────────────────────

def _member_state(ticker: str, tier_from_json: Optional[str]) -> Optional[dict]:
    """Build the point-in-time state dict for one member.

    Returns None if the close series is absent (treated as not-covered).
    Fields:
      washout   bool     — coiled.washout_ctx result
      reclaim   bool     — washout AND above 10d MA
      macd_turn bool     — fresh T1/T2/T3 tier (from subsector_confluence JSON or own gate)
      drawdown  float    — current 252d-trailing drawdown (≤0)
      ret20     float    — 20d return (for RS rank)
      close     pd.Series — retained for cohesion computation
    """
    close = _close(ticker)
    if close is None:
        return None

    # washout_ctx (coiled definition — multi-TF washout)
    washout = _coiled.washout_ctx(close)
    washout_bool = bool(washout) if washout is not None else None

    # 10d MA reclaim (close is above 10d MA) — only meaningful in washout
    above_ma = _above_ma10(close)

    # reclaim: washed out AND above 10d MA (the bottom_radar._capitulation reclaim half)
    reclaim = (washout_bool is True) and above_ma

    # MACD turn: fresh T1-T3 — try the pre-computed tier from subsector_confluence first.
    # A ticker outside every subsector group has tier None = UNKNOWN, and stays None so
    # the per-metric coverage gate excludes it from peer_macd_turn_pct (counting unknown
    # as False would mechanically depress the metric across every widened cohort —
    # W1 S1 interim widening adds ~1,070 unknown-tier names).
    macd_turn = (tier_from_json in FRESH_TIERS) if tier_from_json is not None else None

    # drawdown from 252d high
    dd = _drawdown_252(close)

    # 20d return for RS rank
    ret20 = _ret_n(close, RS_WIN)

    return {
        "washout": washout_bool,
        "reclaim": reclaim,
        "macd_turn": macd_turn,
        "drawdown": dd,
        "ret20": ret20,
        "close": close,
    }


# ── cohesion computation ───────────────────────────────────────────────────────

def _cohesion_chg(members_state: dict[str, dict]) -> Optional[float]:
    """Mean pairwise correlation change (current - prior window).

    Mirrors group_flow.fingerprint_at's cohesion_chg primitive.
    Returns None when insufficient history or coverage.
    """
    try:
        closes: dict[str, pd.Series] = {}
        for t, s in members_state.items():
            c = s.get("close")
            if c is not None and len(c) >= COHESION_WINDOW + COHESION_PREV_WIN:
                closes[t] = c

        if len(closes) < 3:
            return None

        # align to common index
        df = pd.DataFrame({t: c for t, c in closes.items()})
        rets = df.pct_change(fill_method=None)

        n = len(rets)
        if n < COHESION_WINDOW + COHESION_PREV_WIN:
            return None

        cur  = _mean_pairwise_corr(rets.iloc[-COHESION_WINDOW:])
        prev = _mean_pairwise_corr(rets.iloc[-(COHESION_WINDOW + COHESION_PREV_WIN):-COHESION_PREV_WIN])
        if cur is None or prev is None:
            return None
        return float(cur - prev)
    except Exception:  # noqa: BLE001
        return None


# ── rubber-band score ─────────────────────────────────────────────────────────

def _rubber_band_score(
    target_dd: float,
    cohort_dds: list[float],
    cohesion_chg: Optional[float],
    peer_washout_pct: float,
) -> Optional[float]:
    """Compute the Rubber-Band Score for a single target.

    Formula (§3.3):
      z(target_dd in cohort DD distribution) × cohesion_chg × peer_washout_pct

    z is signed: negative dd (deep drawdown) vs cohort median → z is negative
    if target is MORE drawn-down than cohort median.

    High cohort washout + target drawdown TYPICAL for cohort + rising cohesion
    → high (positive) rubber-band score.

    Extreme outlier drawdown (much worse than cohort) + low peer_washout_pct
    → negative/low score (idiosyncratic knife).

    Returns None if insufficient data.
    """
    try:
        if len(cohort_dds) < 3:
            return None

        arr = np.array(cohort_dds, dtype=float)
        arr = arr[np.isfinite(arr)]
        if len(arr) < 3:
            return None

        mu  = float(np.mean(arr))
        std = float(np.std(arr, ddof=0))
        if std == 0 or not np.isfinite(std):
            z = 0.0
        else:
            z = float((target_dd - mu) / std)

        # cohesion_chg: None → treat as 0 (no cohesion signal)
        cohesion = float(cohesion_chg) if cohesion_chg is not None else 0.0

        score = z * cohesion * peer_washout_pct
        return round(float(score), 4) if np.isfinite(score) else None
    except Exception:  # noqa: BLE001
        return None


# ── per-cohort aggregation ────────────────────────────────────────────────────

def _compute_cohort(
    sector: str,
    tickers: list[str],
    tier_map: dict[str, Optional[str]],
) -> dict[str, dict]:
    """Compute all cohort metrics for a single sector cohort.

    Returns a dict keyed by ticker.  Each value is the metric payload for that ticker.
    Tickers with no price data are excluded from cohort aggregation (counted in n_members
    but not n_covered for coverage law purposes).
    """
    n_members = len(tickers)
    if n_members < MIN_MEMBERS:
        # Too thin to form a cohort — all get null
        null = _coverage_null(0, n_members)
        null["coverage_law"] = "THIN_COHORT"
        return {t: null for t in tickers}

    # Build per-member state (load closes once)
    states: dict[str, dict] = {}
    for t in tickers:
        tier = tier_map.get(t)   # may be None (not in any subsector group)
        s = _member_state(t, tier)
        if s is not None:
            states[t] = s

    n_covered = len(states)

    # Coverage law
    if n_covered < math.ceil(COVERAGE_THRESHOLD * n_members):
        null = _coverage_null(n_covered, n_members)
        return {t: null for t in tickers}

    # Aggregate peer metrics (exclude the target from its own cohort — self-exclusion)
    washout_flags = {t: s["washout"] for t, s in states.items()}
    reclaim_flags = {t: s["reclaim"] for t, s in states.items()}
    macd_flags    = {t: s["macd_turn"] for t, s in states.items()}
    dd_vals       = {t: s["drawdown"] for t, s in states.items()}
    ret20_vals    = {t: s["ret20"] for t, s in states.items()}

    # Cohesion (full cohort, not self-excluded — pairwise corr is symmetric)
    cohesion = _cohesion_chg(states)

    # RS rank: within-cohort rank of 20d return (0..1, 1 = best performer)
    ret20_valid = {t: v for t, v in ret20_vals.items() if v is not None}
    if ret20_valid:
        sr = pd.Series(ret20_valid).rank(pct=True)
        rs_rank_map = sr.to_dict()
    else:
        rs_rank_map = {}

    result: dict[str, dict] = {}

    for t in tickers:
        if t not in states:
            # Not covered — emit null
            result[t] = _coverage_null(n_covered, n_members)
            result[t]["rs_rank"] = None
            continue

        # Peer set = all covered members EXCEPT self
        peers = {pt: states[pt] for pt in states if pt != t}
        n_peers = len(peers)

        if n_peers < MIN_MEMBERS - 1:
            # After self-exclusion the cohort is too thin
            result[t] = _coverage_null(n_covered, n_members)
            result[t]["coverage_law"] = "THIN_COHORT_AFTER_SELF_EXCL"
            result[t]["rs_rank"] = rs_rank_map.get(t)
            continue

        # peer_washout_pct
        wo_covered = [(pt, washout_flags[pt]) for pt in peers if washout_flags[pt] is not None]
        wo_pct: Optional[float] = None
        if len(wo_covered) >= math.ceil(COVERAGE_THRESHOLD * n_peers):
            wo_pct = round(float(np.mean([v for _, v in wo_covered])), 4)

        # peer_reclaim_pct
        re_covered = [(pt, reclaim_flags[pt]) for pt in peers if reclaim_flags[pt] is not None]
        re_pct: Optional[float] = None
        if len(re_covered) >= math.ceil(COVERAGE_THRESHOLD * n_peers):
            re_pct = round(float(np.mean([v for _, v in re_covered])), 4)

        # peer_macd_turn_pct
        mt_covered = [(pt, macd_flags[pt]) for pt in peers if macd_flags[pt] is not None]
        mt_pct: Optional[float] = None
        if len(mt_covered) >= math.ceil(COVERAGE_THRESHOLD * n_peers):
            mt_pct = round(float(np.mean([v for _, v in mt_covered])), 4)

        # Rubber-Band Score
        target_dd = dd_vals[t]
        peer_dds  = [dd_vals[pt] for pt in peers if dd_vals[pt] is not None]
        rbs: Optional[float] = None
        if (target_dd is not None
                and wo_pct is not None
                and len(peer_dds) >= math.ceil(COVERAGE_THRESHOLD * n_peers)):
            rbs = _rubber_band_score(target_dd, peer_dds, cohesion, wo_pct)

        cov_pct = round(100.0 * n_covered / n_members, 1)
        result[t] = {
            "sector": sector,
            "peer_washout_pct": wo_pct,
            "peer_reclaim_pct": re_pct,
            "peer_macd_turn_pct": mt_pct,
            "rubber_band_score": rbs,
            "cohesion_chg": round(cohesion, 4) if cohesion is not None else None,
            "drawdown_252d": round(target_dd * 100, 2) if target_dd is not None else None,
            "rs_rank": round(rs_rank_map.get(t, None), 3) if rs_rank_map.get(t) is not None else None,
            "ret20": round(ret20_vals.get(t, None) * 100, 2) if ret20_vals.get(t) is not None else None,
            "coverage_pct": cov_pct,
            "n_covered": n_covered,
            "n_members": n_members,
            "coverage_law": "OK",
        }

    return result


# ── public API ─────────────────────────────────────────────────────────────────

def _site_dir() -> Path:
    """Return the site/ directory path via lib.config (the canonical pattern)."""
    from lib import config  # local import to avoid circular at module level  # noqa: PLC0415
    return config.ROOT / config.load()["storage"]["site_dir"]


def _data_dir() -> Path:
    """Return the data/ directory path via lib.config."""
    from lib import config  # noqa: PLC0415
    return config.data_dir()


def load_tier_map() -> dict[str, Optional[str]]:
    """Read per-member T1-T4 tier states from the already-computed subsector_confluence
    JSON.  Avoids recomputing the full cascade for ~500 names.

    Returns dict[ticker -> tier_cascade | None].  Tickers absent from any subsector group
    are not in the returned dict (callers treat missing key as None).
    """
    try:
        p = _site_dir() / "marketdata" / "subsector_confluence.json"
        if not p.exists():
            log.warning("cohort_metrics: subsector_confluence.json missing — tier_map empty")
            return {}
        with open(p) as f:
            data = json.load(f)
        tier_map: dict[str, Optional[str]] = {}
        for sub in data.get("subsectors", []):
            for m in sub.get("members", []):
                t = m.get("ticker")
                if t:
                    tier_map[t] = m.get("stock_tier")  # may be None
        log.debug("cohort_metrics: tier_map loaded (%d tickers)", len(tier_map))
        return tier_map
    except Exception as exc:  # noqa: BLE001
        log.warning("cohort_metrics: failed to load tier_map: %s", exc)
        return {}


# W1 S1 interim widening (§7): GICS → cohort-vocabulary translation. The subsector
# map speaks Yahoo-style sectors ("Basic Materials", "Consumer Cyclical"); the broad
# GICS map speaks S&P style ("Materials", "Consumer Discretionary"). Widened names
# MUST join their siblings' cohorts, not fragment into parallel same-meaning cohorts
# (measured: only 147/428 strings agree raw).
_GICS_TO_COHORT = {
    "Materials": "Basic Materials",
    "Consumer Discretionary": "Consumer Cyclical",
    "Consumer Staples": "Consumer Defensive",
    "Information Technology": "Technology",
    "Health Care": "Healthcare",
    "Financials": "Financial Services",
    # identity for the rest
    "Energy": "Energy", "Industrials": "Industrials", "Utilities": "Utilities",
    "Real Estate": "Real Estate", "Communication Services": "Communication Services",
}


def load_sector_map(widen: bool = True) -> dict[str, str]:
    """Read ticker→sector mapping from subsector_confluence.json, then (W1 S1
    interim widening, §7) extend with ALREADY-PRICED names the subsector groups
    don't carry.

    Widening rules (the interim contract):
      * candidates come from the broad GICS map (equity_factors._names_sectors);
      * ONLY names present in the broad close cache are added ("already-priced
        unmapped names only" — no new fetches, and unpriced names would crater
        the ≥70% coverage law and null whole cohorts);
      * sector strings translate into the existing cohort vocabulary
        (_GICS_TO_COHORT) so widened names join their siblings' cohorts;
      * subsector-mapped names always win (keep-FIRST — no re-mapping).

    Returns dict[ticker -> sector].
    """
    try:
        p = _site_dir() / "marketdata" / "subsector_confluence.json"
        if not p.exists():
            return {}
        with open(p) as f:
            data = json.load(f)
        sector_map: dict[str, str] = {}
        for sub in data.get("subsectors", []):
            sector = sub.get("sector", "Unknown")
            for m in sub.get("members", []):
                t = m.get("ticker")
                if t:
                    sector_map[t] = sector
    except Exception:  # noqa: BLE001
        return {}
    if not widen or not sector_map:
        return sector_map
    try:
        from engine.equity_factors import _closes, _names_sectors  # noqa: PLC0415
        priced = set(_closes("broad").columns)
        # W1.5: the massive whole-market store extends "already-priced" to every
        # name it carries (the split guard in _close() governs actual coverage).
        try:
            from lib import config as _config  # noqa: PLC0415
            msd = Path(_config.data_dir()) / "massive_stock_day"
            if msd.is_dir():
                priced |= {f.stem for f in msd.glob("*.parquet")}
        except Exception:  # noqa: BLE001
            pass
        n_before = len(sector_map)
        for t, (_name, gics) in _names_sectors("broad").items():
            if t in sector_map or t not in priced:
                continue
            cohort = _GICS_TO_COHORT.get(gics)
            if cohort:
                sector_map[t] = cohort
        log.info("cohort_metrics: S1 interim widening %d -> %d names "
                 "(already-priced only)", n_before, len(sector_map))
    except Exception as exc:  # noqa: BLE001 — widening is additive, never fatal
        log.warning("cohort_metrics: widening skipped (%s)", exc)
    return sector_map


def compute(
    sector_map: Optional[dict[str, str]] = None,
    tier_map: Optional[dict[str, Optional[str]]] = None,
) -> dict:
    """Compute all cohort metrics for the ~500 sector-mapped priced names.

    Returns the full payload dict:
      {
        "as_of": "YYYY-MM-DD",
        "universe": "sp500_subsectors",
        "coverage_law_threshold_pct": 70,
        "n_tickers": int,
        "cohort_null_count": int,
        "metrics": { ticker: { peer_washout_pct, peer_reclaim_pct, ... } }
      }

    Never raises (additive / display-only).
    """
    try:
        if sector_map is None:
            sector_map = load_sector_map()
        if tier_map is None:
            tier_map = load_tier_map()

        if not sector_map:
            log.warning("cohort_metrics: sector_map is empty — no metrics computed")
            return {"ok": False, "reason": "sector_map empty", "metrics": {}}

        # Group tickers by sector
        by_sector: dict[str, list[str]] = {}
        for t, sec in sector_map.items():
            by_sector.setdefault(sec, []).append(t)

        log.info("cohort_metrics: computing for %d sectors, %d tickers",
                 len(by_sector), len(sector_map))

        all_metrics: dict[str, dict] = {}
        for sector, tickers in by_sector.items():
            cohort = _compute_cohort(sector, tickers, tier_map)
            all_metrics.update(cohort)

        n_null = sum(1 for v in all_metrics.values() if v.get("coverage_law") != "OK")
        today  = datetime.date.today().isoformat()

        return {
            "ok": True,
            "as_of": today,
            "universe": "sp500_subsectors",
            "coverage_law_threshold_pct": int(COVERAGE_THRESHOLD * 100),
            "n_tickers": len(all_metrics),
            "cohort_null_count": n_null,
            "metrics": all_metrics,
        }

    except Exception as exc:  # noqa: BLE001
        log.error("cohort_metrics.compute failed: %s", exc, exc_info=True)
        return {"ok": False, "reason": str(exc), "metrics": {}}


def append_rs_rank_series(metrics: dict, date: Optional[str] = None) -> Path | None:
    """Persist within-cohort RS rank as a dated parquet row under data/cohort_metrics/.

    Append-style: writes a NEW file per date (idempotent — skips if today's file exists).
    This is the S7 dependency (RS-Before-Price phase-0 requires a series, not a snapshot).

    Returns the path written, or None if skipped / failed.
    """
    try:
        data_dir = _data_dir() / "cohort_metrics"
        data_dir.mkdir(parents=True, exist_ok=True)

        as_of = date or metrics.get("as_of") or datetime.date.today().isoformat()
        out_path = data_dir / f"{as_of}.parquet"

        if out_path.exists():
            log.debug("cohort_metrics: RS rank series for %s already exists — skip", as_of)
            return out_path

        rows = []
        for ticker, m in metrics.get("metrics", {}).items():
            rs = m.get("rs_rank")
            sector = m.get("sector")
            if rs is None:
                continue
            rows.append({
                "date": as_of,
                "ticker": ticker,
                "sector": sector,
                "rs_rank": rs,
                "ret20": m.get("ret20"),
            })

        if not rows:
            log.warning("cohort_metrics: no RS rank rows for %s — not writing parquet", as_of)
            return None

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df.to_parquet(out_path, index=False)
        log.info("cohort_metrics: wrote RS rank series → %s (%d rows)", out_path, len(df))
        return out_path

    except Exception as exc:  # noqa: BLE001
        log.error("cohort_metrics.append_rs_rank_series failed: %s", exc)
        return None


def write_json(metrics: dict, out_path: Optional[Path] = None) -> Path | None:
    """Write the cohort metrics payload to site/factordata/cohort_metrics.json.

    Strips the per-member close Series before serialising (not JSON-serialisable).
    Returns the path written, or None on failure.
    """
    try:
        if out_path is None:
            out_path = _site_dir() / "factordata" / "cohort_metrics.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # The metrics dict may contain pd.Series in the 'close' field from _member_state —
        # those are never included in the public payload (only used for cohesion computation
        # inside _compute_cohort).  Strip any stray non-serialisable values.
        def _clean(v):
            if isinstance(v, float):
                return None if (not np.isfinite(v)) else round(v, 6)
            return v

        clean: dict = {}
        for ticker, m in metrics.get("metrics", {}).items():
            clean[ticker] = {k: _clean(v) for k, v in m.items() if k != "close"}

        payload = {k: v for k, v in metrics.items() if k != "metrics"}
        payload["metrics"] = clean

        with open(out_path, "w") as f:
            json.dump(payload, f, indent=None, separators=(",", ":"))

        log.info("cohort_metrics: wrote JSON → %s (%d tickers)", out_path,
                 len(clean))
        return out_path

    except Exception as exc:  # noqa: BLE001
        log.error("cohort_metrics.write_json failed: %s", exc)
        return None
