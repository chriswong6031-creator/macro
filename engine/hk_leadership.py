"""HK Leadership Participation Organ — display-tier sibling of hk_washout_watch.

Surfaces COHORT-LEVEL evidence when the fixed mega-cap leaders are broadly
participating (fraction above rising 10d MA ≥ 0.60 after crossing from < 0.30
within 10 sessions). Not a validated buy signal; present-tense descriptor only.

DOCTRINE
--------
- DISPLAY-ONLY / CONTEXT. Southbound cohort flow is WHO the marginal buyer is,
  never a gate on visibility or confirmer of direction (HKRV-R2/R3).
- AUTHORITY FENCE (HKRV-R5): nothing feeds rank/size/gate/K-counts.
- ADDITIVE + FAIL-OPEN: never raises; never mutates the board dict.
- EVENT (IHM §2.3): thrust fires when cohesion crosses from < 0.30 to >= 0.60
  within 10 sessions — not a standing state, an EVENT.
- Forward ledger gated on CN_LANE=asia (house law: nightly sole advancer).

OUTPUT KEYS
-----------
state              : 'leaders_participating' | 'quiet'
thrust_date        : ISO date of the most recent thrust event, or None
cohesion_now       : fraction of cohort above rising 10d MA (0.0–1.0)
cohesion_10d_ago   : same metric 10 sessions ago (used for the cross test)
broad_breadth_pct  : pct_above_50 from hk_breadth/breadth.parquet, or None
breadth_confirming : bool — broad_breadth_pct >= 35
sb_cohort_flow     : PLAIN SUM of per-name chg5 (pct of mktcap) over the cohort.
                     Units: sum of individual %-of-mktcap values (NOT a single unified pct).
                     CONTEXT ONLY — never a gate.  See also sb_cohort_flow_pct_mean.
sb_cohort_flow_pct_mean : mean of the same per-name pct values (honest unit).
                     Same context-only status.  Populated when >= 1 cohort name has data.
members            : list of {ticker, above_rising_ma10, sb_chg5}
display_only       : True (always)
copy_en            : plain-English present-tense descriptor
copy_zh            : Chinese present-tense descriptor
study_n            : 15  (Study-B receipt)
study_hsi_fwd40_mean: -1.73 (Study-B receipt)
study_note         : brief note on the study
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default cohort (spec §1)
# ---------------------------------------------------------------------------

DEFAULT_COHORT: list[str] = [
    "0700.HK",  # Tencent
    "9988.HK",  # Alibaba
    "3690.HK",  # Meituan
    "1810.HK",  # Xiaomi
    "9618.HK",  # JD.com
    "1024.HK",  # Kuaishou
    "2318.HK",  # Ping An
    "0941.HK",  # China Mobile
    "1211.HK",  # BYD
    "9888.HK",  # Baidu
]

# ---------------------------------------------------------------------------
# Thresholds (spec §2)
# ---------------------------------------------------------------------------

COHORT_MIN_LISTED   = 5      # require >= 5 names with price data
MA10_WINDOW         = 10     # 10-day moving average
THRUST_LOW          = 0.30   # cohesion was below this 10 sessions ago
THRUST_HIGH         = 0.60   # cohesion now at or above this (cross event)
BREADTH_CONFIRM_PCT = 35.0   # broad breadth confirming threshold (pct_above_50 >= 35)
THRUST_LOOKBACK     = 10     # number of sessions to look back for the cross
REARM_SCAN_SESSIONS = 40     # trailing sessions scanned (dated) for the ledger re-arm gate

# ---------------------------------------------------------------------------
# Lane guard (mirrors hk_washout_watch._ledger_advance_enabled)
# ---------------------------------------------------------------------------

def _ledger_advance_enabled() -> bool:
    """True only when running in the asia-close nightly lane (CN_LANE=asia)."""
    return os.environ.get("CN_LANE", "").lower() == "asia"


# ---------------------------------------------------------------------------
# Ledger helpers (mirrors hk_washout_watch pattern exactly)
# ---------------------------------------------------------------------------

_LEDGER_DIR  = "hk_impulse"
_LEDGER_FILE = "leadership_ledger.jsonl"


def _ledger_path(data_root: Path | None = None) -> Path:
    from lib import config
    root = data_root if data_root is not None else config.data_dir()
    return root / _LEDGER_DIR / _LEDGER_FILE


def load_ledger(data_root: Path | None = None) -> list[dict]:
    """Load all ledger rows. Returns [] if file missing/corrupt."""
    p = _ledger_path(data_root)
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _write_ledger(rows: list[dict], data_root: Path | None = None) -> None:
    """Write ledger atomically via temp-file + os.replace."""
    p = _ledger_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(r, default=str) for r in rows)
    if content:
        content += "\n"
    fd, tmp_path = tempfile.mkstemp(dir=p.parent, prefix=".leadership_ledger_tmp_")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(content)
        os.replace(tmp_path, p)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def stamp_ledger(
    thrust_date: str,
    cohesion_now: float,
    cohesion_10d_ago: float,
    as_of: str | None = None,
    data_root: Path | None = None,
    cohesion_by_date: dict[str, float] | None = None,
) -> int:
    """Append one row per new thrust date (idempotent on date).

    Episode arming: after a stamped thrust, suppress further stamps until
    cohesion has printed at least one bar BELOW THRUST_LOW (0.30) DATED
    AFTER the last stamped row.  ``cohesion_by_date`` maps 'YYYY-MM-DD' ->
    cohesion for the trailing REARM_SCAN_SESSIONS sessions.  A dip that
    merely sits inside the thrust-detection window but predates the last
    stamp does NOT re-arm (that is the same episode still in view — the
    bug the window-based v1 gate had).  When None/empty, the gate is
    skipped (fail-open: stamp).

    Gated by CN_LANE=asia. Never raises. Returns count of appended rows.
    """
    if not _ledger_advance_enabled():
        log.debug("hk_leadership.stamp_ledger: skipped (CN_LANE != asia)")
        return 0
    today_str = as_of or date.today().isoformat()
    try:
        rows = load_ledger(data_root)
        existing_dates = {r.get("date") for r in rows}
        if today_str in existing_dates:
            return 0
        # Episode re-arm gate: suppress unless cohesion dipped below THRUST_LOW
        # on a bar DATED AFTER the last stamped row — prevents autocorrelated
        # nightly re-stamps while the originating dip is still inside the
        # thrust-detection window (same episode).
        if rows and cohesion_by_date:
            last_date = max(str(r.get("date") or "") for r in rows)
            re_armed = any(
                v is not None and v < THRUST_LOW
                for d, v in cohesion_by_date.items() if str(d) > last_date
            )
            if not re_armed:
                log.debug(
                    "hk_leadership.stamp_ledger: suppressed (no dip < %.2f dated "
                    "after last stamp %s — same episode)", THRUST_LOW, last_date,
                )
                return 0
        rows.append({
            "date":              today_str,
            "thrust_date":       thrust_date,
            "cohesion_now":      round(float(cohesion_now), 3),
            "cohesion_10d_ago":  round(float(cohesion_10d_ago), 3),
            # Asymmetric outcome fields — blank at fire time, graded forward:
            "fwd_hsi_40d":       None,
            "fwd_large_cap_40d": None,
            "graded_at":         None,
        })
        _write_ledger(rows, data_root)
        return 1
    except Exception as e:  # noqa: BLE001
        log.warning("hk_leadership.stamp_ledger failed: %s", e)
        return 0


# ---------------------------------------------------------------------------
# MA helpers
# ---------------------------------------------------------------------------

def _rising_ma10(series: pd.Series) -> bool:
    """True when the 10-day MA is rising (today's MA > yesterday's MA)."""
    s = series.dropna()
    if len(s) < MA10_WINDOW + 1:
        return False
    ma = s.rolling(MA10_WINDOW).mean()
    return bool(float(ma.iloc[-1]) > float(ma.iloc[-2]))


def _above_rising_ma10(close: pd.Series) -> bool:
    """True when the last close is above a rising 10-day MA."""
    s = close.dropna()
    if len(s) < MA10_WINDOW + 1:
        return False
    ma = s.rolling(MA10_WINDOW).mean().dropna()
    if len(ma) < 2:
        return False
    ma_rising = float(ma.iloc[-1]) > float(ma.iloc[-2])
    above = float(s.iloc[-1]) > float(ma.iloc[-1])
    return bool(above and ma_rising)


def _cohesion_at(closes_map: dict[str, pd.Series], as_of_idx: int = -1) -> float | None:
    """Fraction of cohort names that are above their rising 10d MA at the given index.

    ``as_of_idx`` is the position in each series (default -1 = latest bar;
    pass -11 to get 10 sessions ago). Returns None when fewer than COHORT_MIN_LISTED
    names have enough data at that position.
    """
    above = 0
    total = 0
    for ticker, s in closes_map.items():
        s_clean = s.dropna()
        # We need at least MA10_WINDOW + 1 bars available up to as_of_idx
        # Build a sub-slice ending at the target position
        if as_of_idx < 0:
            end_pos = len(s_clean) + as_of_idx + 1
        else:
            end_pos = as_of_idx + 1
        if end_pos < MA10_WINDOW + 1:
            continue
        sub = s_clean.iloc[:end_pos]
        ma = sub.rolling(MA10_WINDOW).mean()
        if ma.iloc[-1] != ma.iloc[-1]:  # NaN
            continue
        if len(ma.dropna()) < 2:
            continue
        ma_rising = float(ma.iloc[-1]) > float(ma.dropna().iloc[-2])
        above_ma = float(sub.iloc[-1]) > float(ma.iloc[-1])
        if ma_rising and above_ma:
            above += 1
        total += 1
    if total < COHORT_MIN_LISTED:
        return None
    return above / total


# ---------------------------------------------------------------------------
# Broad breadth reader (fail-open)
# ---------------------------------------------------------------------------

def _read_broad_breadth(data_root: Path | None = None) -> float | None:
    """Read pct_above_50 from data/hk_breadth/breadth.parquet. Returns None on any error."""
    try:
        from lib import config, store
        breadth_df = store.read("hk_breadth", "breadth")
        if breadth_df is None or "pct_above_50" not in breadth_df.columns:
            return None
        s = breadth_df["pct_above_50"].dropna()
        if s.empty:
            return None
        return float(s.iloc[-1])
    except Exception as e:  # noqa: BLE001
        log.debug("hk_leadership: broad breadth read failed (%s)", e)
        return None


# ---------------------------------------------------------------------------
# Southbound cohort flow reader (fail-open)
# ---------------------------------------------------------------------------

def _read_sb_cohort_flow(cohort: list[str]) -> dict[str, float | None]:
    """Read chg5 per cohort ticker from the southbound holdings store.

    Returns {ticker: chg5_pct or None}. CONTEXT only — never a gate.
    """
    out: dict[str, float | None] = {t: None for t in cohort}
    try:
        from engine.hk_southbound_stocks import latest_holdings
        snap = latest_holdings()
        if snap is None or snap.empty:
            return out
        for t in cohort:
            if t not in snap.index:
                continue
            chg5_v = snap.at[t, "chg5_v"] if "chg5_v" in snap.columns else None
            hold = snap.at[t, "hold_mktcap"] if "hold_mktcap" in snap.columns else None
            if chg5_v is not None and hold is not None and float(hold) > 0:
                out[t] = round(float(chg5_v) / float(hold) * 100.0, 2)
    except Exception as e:  # noqa: BLE001
        log.debug("hk_leadership: southbound cohort flow read failed (%s)", e)
    return out


# ---------------------------------------------------------------------------
# Copy builders (present-tense, HKRV-R2/R3)
# ---------------------------------------------------------------------------

def _build_copy(
    state: str,
    cohesion_now: float,
    breadth_confirming: bool,
    thrust_date: str | None,
) -> tuple[str, str]:
    """Build honest present-tense descriptors (COPY LAW: no predictive language).

    Returns (copy_en, copy_zh).
    """
    if state == "leaders_participating":
        if breadth_confirming:
            en = (
                "The mega-cap leaders are broadly participating; broad breadth is "
                "confirming participation. Historically this pattern accompanied "
                "leader gains, not broad-index advances."
            )
            zh = (
                "大市值龙头股普遍上涨；宽度指标同步确认参与态势。"
                "历史上此形态伴随龙头涨幅，但未必带动大盘整体上行。"
            )
        else:
            en = (
                "The mega-cap leaders are participating; broad breadth has "
                "not confirmed. Historically this pattern accompanied leader "
                "gains, not broad-index advances."
            )
            zh = (
                "大市值龙头股参与上涨，但整体市场宽度尚未跟进确认。"
                "历史上此形态伴随龙头涨幅，但未必带动大盘整体上行。"
            )
    else:
        en = "Leader cohort participation is subdued; no broad thrust detected."
        zh = "龙头股整体参与度偏弱，暂未出现普涨信号。"
    return en, zh


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def compute(
    closes_map: dict[str, pd.Series] | None = None,
    cohort: list[str] | None = None,
    as_of: str | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Compute the HK Leadership Participation organ.

    Parameters
    ----------
    closes_map:
        Dict of {ticker: close_series} for the cohort names. When None the
        organ attempts to load from the hk_breadth close cache. Each series
        must be date-indexed. Missing or thin names degrade gracefully.
    cohort:
        List of HK tickers to watch (default: DEFAULT_COHORT).
    as_of:
        ISO date string for the ledger stamp.
    data_root:
        Override data root (for testing).

    Returns
    -------
    dict matching the spec output shape. Never raises.
    """
    try:
        return _compute_inner(closes_map, cohort or DEFAULT_COHORT, as_of, data_root)
    except Exception as e:  # noqa: BLE001
        log.error("hk_leadership.compute crashed (%s) — returning quiet state", e)
        return _empty_result()


def _empty_result() -> dict[str, Any]:
    return {
        "state":              "quiet",
        "thrust_date":        None,
        "cohesion_now":       None,
        "cohesion_10d_ago":   None,
        "broad_breadth_pct":  None,
        "breadth_confirming": False,
        "sb_cohort_flow":          None,
        "sb_cohort_flow_pct_mean": None,
        "members":            [],
        "display_only":       True,
        "copy_en":            "Leader cohort participation is subdued; no broad thrust detected.",
        "copy_zh":            "龙头股整体参与度偏弱，暂未出现普涨信号。",
        "study_n":            15,
        "study_hsi_fwd40_mean": -1.73,
        "study_note": (
            "Study B: 15 prior cohesion-thrust events on the HSI large-cap cohort "
            "(2018–2025); mean HSI forward 40-session return = -1.73% (leaders "
            "outperformed broad index in 11/15 episodes). Display-only accrual; "
            "not a validated promotable signal."
        ),
    }


def _load_closes_from_cache(cohort: list[str]) -> dict[str, pd.Series]:
    """Attempt to load close series from the hk_breadth close cache and hk_stocks store."""
    out: dict[str, pd.Series] = {}
    try:
        from lib import config, store
        cache_path = config.data_dir() / "hk_breadth" / "_closes_cache.parquet"
        if cache_path.exists():
            closes_df = pd.read_parquet(cache_path)
            for t in cohort:
                if t in closes_df.columns:
                    s = closes_df[t].dropna()
                    if len(s) >= MA10_WINDOW + 2:
                        out[t] = s
    except Exception as e:  # noqa: BLE001
        log.debug("hk_leadership: breadth cache load failed (%s)", e)
    # Fill gaps from hk_stocks deep store
    try:
        from lib import store
        for t in cohort:
            if t in out:
                continue
            df = store.read("hk_stocks", t)
            if df is not None and "close" in df.columns:
                s = pd.to_numeric(df["close"], errors="coerce").dropna()
                if len(s) >= MA10_WINDOW + 2:
                    out[t] = s
    except Exception as e:  # noqa: BLE001
        log.debug("hk_leadership: hk_stocks load failed (%s)", e)
    return out


def _compute_inner(
    closes_map: dict[str, pd.Series] | None,
    cohort: list[str],
    as_of: str | None,
    data_root: Path | None,
) -> dict[str, Any]:
    empty = _empty_result()

    # Load closes if not provided
    if closes_map is None:
        closes_map = _load_closes_from_cache(cohort)

    # Filter to cohort with enough data
    cohort_closes: dict[str, pd.Series] = {}
    for t in cohort:
        s = closes_map.get(t)
        if s is not None:
            s_clean = s.dropna()
            if len(s_clean) >= MA10_WINDOW + 2:
                cohort_closes[t] = s_clean

    if len(cohort_closes) < COHORT_MIN_LISTED:
        log.debug("hk_leadership: only %d listed names (need %d) — quiet",
                  len(cohort_closes), COHORT_MIN_LISTED)
        return empty

    # Current cohesion
    cohesion_now = _cohesion_at(cohort_closes, as_of_idx=-1)
    if cohesion_now is None:
        return empty

    # Cohesion 10 sessions ago (for reporting; also used as the fallback min estimate)
    cohesion_10d_ago = _cohesion_at(cohort_closes, as_of_idx=-1 - THRUST_LOOKBACK)
    # When history is too shallow, treat old cohesion as 0 (conservative default)
    if cohesion_10d_ago is None:
        cohesion_10d_ago = 0.0

    # Thrust event: min cohesion within the THRUST_LOOKBACK window < 0.30 AND
    # current >= 0.60 (F4-a fix: scan true within-window extremes, not just endpoint).
    # This catches crosses where the low occurred mid-window, not exactly LOOKBACK bars ago.
    cohesion_min_window = cohesion_10d_ago  # fallback if scan fails
    scanned: list[float] = []
    cohesion_by_date: dict[str, float] = {}  # dated trail for the ledger re-arm gate
    try:
        ref = max(cohort_closes.values(), key=lambda x: len(x.dropna())).dropna()
        n_scan = min(REARM_SCAN_SESSIONS, len(ref))
        for lag in range(0, n_scan):
            c = _cohesion_at(cohort_closes, as_of_idx=-1 - lag)
            if c is None:
                continue
            if 1 <= lag <= THRUST_LOOKBACK:
                scanned.append(c)
            cohesion_by_date[str(ref.index[-1 - lag].date())] = c
        if scanned:
            cohesion_min_window = min(scanned)
    except Exception:  # noqa: BLE001
        pass  # fall back to two-endpoint check
    thrust_fired = (
        cohesion_min_window < THRUST_LOW
        and cohesion_now >= THRUST_HIGH
    )

    # Broad breadth context
    broad_breadth_pct = _read_broad_breadth(data_root)
    breadth_confirming = bool(
        broad_breadth_pct is not None and broad_breadth_pct >= BREADTH_CONFIRM_PCT
    )

    # Per-member detail (above_rising_ma10, sb_chg5)
    sb_flow_map = _read_sb_cohort_flow(cohort)
    members: list[dict] = []
    for t in cohort:
        s = cohort_closes.get(t)
        if s is not None:
            above = _above_rising_ma10(s)
        else:
            above = False
        members.append({
            "ticker":          t,
            "above_rising_ma10": above,
            "sb_chg5":         sb_flow_map.get(t),
        })

    # Southbound cohort net flow context.
    # sb_cohort_flow: plain sum of per-name %-of-mktcap values.
    #   Units: sum of individual %-of-mktcap (NOT a single unified portfolio pct).
    #   CONTEXT ONLY — never a gate.  Reviewer-flagged unit note (F4-b).
    # sb_cohort_flow_pct_mean: mean of the same values — honest single-pct read.
    #   Populated when >= 1 cohort name has data.
    chg5_vals = [m["sb_chg5"] for m in members if m["sb_chg5"] is not None]
    sb_cohort_flow = round(sum(chg5_vals), 2) if chg5_vals else None
    sb_cohort_flow_pct_mean = round(sum(chg5_vals) / len(chg5_vals), 2) if chg5_vals else None

    # State assignment
    state = "leaders_participating" if cohesion_now >= THRUST_HIGH else "quiet"

    # Copy builders
    thrust_date_str: str | None = None
    if thrust_fired:
        thrust_date_str = as_of or date.today().isoformat()

    copy_en, copy_zh = _build_copy(state, cohesion_now, breadth_confirming, thrust_date_str)

    result: dict[str, Any] = {
        "state":              state,
        "thrust_date":        thrust_date_str,
        "cohesion_now":       round(cohesion_now, 3),
        "cohesion_10d_ago":   round(cohesion_10d_ago, 3),
        "broad_breadth_pct":  round(broad_breadth_pct, 1) if broad_breadth_pct is not None else None,
        "breadth_confirming": breadth_confirming,
        "sb_cohort_flow":          sb_cohort_flow,
        "sb_cohort_flow_pct_mean": sb_cohort_flow_pct_mean,
        "members":            members,
        "display_only":       True,
        "copy_en":            copy_en,
        "copy_zh":            copy_zh,
        "study_n":            15,
        "study_hsi_fwd40_mean": -1.73,
        "study_note": (
            "Study B: 15 prior cohesion-thrust events on the HSI large-cap cohort "
            "(2018–2025); mean HSI forward 40-session return = -1.73% (leaders "
            "outperformed broad index in 11/15 episodes). Display-only accrual; "
            "not a validated promotable signal."
        ),
    }

    # Forward ledger stamp (gated on CN_LANE=asia + thrust event only)
    if thrust_fired and thrust_date_str:
        try:
            n = stamp_ledger(
                thrust_date=thrust_date_str,
                cohesion_now=cohesion_now,
                cohesion_10d_ago=cohesion_10d_ago,
                as_of=as_of,
                data_root=data_root,
                cohesion_by_date=cohesion_by_date or None,
            )
            if n:
                log.info("hk_leadership: stamped thrust event to ledger (as_of=%s)", thrust_date_str)
        except Exception as ex:  # noqa: BLE001 — ledger write never breaks the render
            log.warning("hk_leadership: ledger stamp failed (%s)", ex)

    return result
