"""engine/opex_risk.py — OPEX window risk read (Layer 3 of RIC P2).

LEAF module: reads Layer-2 surface aggregates + existing engine artifacts and
composes a plain-word OPEX-window risk snapshot.

STANDING LAWS (RIC-R2/R3, §2):
  - This is DISPLAY CONTEXT ONLY.  The snapshot() output must NEVER be passed to
    engine/risk_radar.py _SCARES, never read by compute(), never used as a sizing
    input.  Violation = immediate kill ruling.
  - Risk level = literal UNWEIGHTED state count (n_hot / n_applicable, the
    mtf_upturn K-of-N idiom).  No per-state weights exist (frozen at W0).  No
    0-100 composite score.  This is NOT the commodity_confluence weighted score.
  - Event/OPEX proximity states are context only; the one lawful future risk-channel
    candidate (dealer_load_extreme, calendar-agnostic) lives in a separate Lane-(ii)
    pre-registration and is NOT wired here.
  - "validated" must not appear in user-facing text (CI-enforced).

State table (from masterplan §3 Layer-3):
  concentration_hot    Layer 2   front7_abs_charm/gex_share percentile vs OWN
                                 root-class history >= P80
  dealer_load_extreme  Layer 2   |net_vex| or |net_cex| percentile >= P90
                                 (magnitude; sign-agnostic; CALENDAR-AGNOSTIC)
  gamma_regime         gex board long/short/flip-proximity (context flags)
  pin_proximity        W1        opex_days<=5 + long gamma + wall<=2%
  vanna_relief_active  W1        RUL-OVC-1 holdability state (symmetry caveat)
  vanna_drag                     inverse of vanna_relief_active
  window_phase         opex.py   opex_week/post_opex/mid_cycle + is_quad (context)
  event_collision      [SLOT]    NULL placeholder — arrives with W4 event_window.py;
                                 kept so the stack degrades gracefully: W4 plugs in
                                 without changing the caller interface.

DEALER-SIGN PASSPORT (printed on every snapshot):
  The sign of net_vex / net_cex (and any charm/vanna aggregate) reflects an
  UNOBSERVABLE dealer-position convention.  SqueezeMetrics and comparable providers
  apply a long-call+1/short-put+1 convention that is widely used but structurally
  unverifiable from public data.  Every sign-dependent reading carries this caveat.
  The |·|-magnitude constructions (dealer_load_extreme, concentration_hot) are
  preferred precisely because they are sign-agnostic.

POST-OPEX WEAKNESS WATCH:
  The −0.9% post-OPEX-week effect (Stivers-Sun 2013, 1988-2010) is Era3-only
  (post-2010 data shows decay; the "March worst" claim is WRONG per the domain
  research pack).  This watch item is printed with its honest era-status and never
  treated as a directional call.  It is context / framing only (RO-3 / F-21).

SURFACE DATA AVAILABILITY:
  data/options_surface/{root_class}.parquet are committed small-aggregate files
  written by scripts/build_options_surface.py on the theta-ops launchd lane.
  The backfill is IN PROGRESS as of this PR.  Partial / absent data → null states;
  n_applicable shrinks; the snapshot degrades gracefully.  NEVER raises on absence.

FORWARD LEDGER:
  data/opex_windows/forward_log.jsonl — see log_window() below.
  Sole advancer: COLLECT_LANE=nightly (daily.yml engine job).
  Off-lane reads are permitted; off-lane appends are blocked (keep-FIRST idempotent).

Grading rulers (FROZEN in this PR, per the masterplan §3):
  forward_5d_rv   : realized vol (annualized) over the 5 calendar days after the
                    window entry date, vs trailing_rv (90-day window ending T-5).
  forward_10d_rv  : realized vol over 10 calendar days post-entry vs trailing_rv.
  max_dd_post10d  : max drawdown (peak-to-trough) in the 10 calendar days following
                    the expiration date.  Drawdown is measured peak-to-trough on
                    daily closes, sign-negative if spot drops.
  range_compression: (high-low) / ATR(20) in the 5 days BEFORE expiration vs the
                     20-day trailing ATR.  Captures pin/compression behavior.
  Grading targets are VOL/PATH objects; no directional return targets (RO-3/F-21).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from engine import opex as _opex_cal
from lib import config

log = logging.getLogger(__name__)

# ── Percentile thresholds (masterplan §3, frozen) ─────────────────────────────
_CONCENTRATION_PCTILE = 80   # P80 vs own root-class history
_DEALER_LOAD_PCTILE = 90     # P90 for |net_vex| or |net_cex|
_FLIP_PROXIMITY_PCT = 5.0    # dist_to_flip_pct <= this = flip-proximity context

# ── Surface parquet paths ─────────────────────────────────────────────────────
_SURFACE_ROOT_CLASSES = ("index_etf", "sector_etf", "industry_etf")
_PRIMARY_ROOT_CLASS = "index_etf"     # SPX/SPY complex — primary for W3


def _surface_path(root_class: str, data_root: Path | None = None) -> Path:
    base = data_root if data_root is not None else config.data_dir()
    return base / "options_surface" / f"{root_class}.parquet"


def _read_surface(root_class: str, data_root: Path | None = None) -> pd.DataFrame | None:
    """Read the Layer-2 surface parquet for a root_class.  Returns None when
    absent or unreadable (backfill in progress / theta-ops lane not yet run).
    NEVER raises."""
    p = _surface_path(root_class, data_root)
    if not p.exists():
        log.debug("opex_risk: surface parquet absent: %s", p)
        return None
    try:
        df = pd.read_parquet(p)
        if df.empty:
            return None
        return df
    except Exception as e:  # noqa: BLE001
        log.warning("opex_risk: surface read failed for %s: %s", root_class, e)
        return None


def _percentile_rank(series: pd.Series, value: float) -> float | None:
    """Return the percentile rank of `value` in `series` (0-100 scale).
    Returns None when the series has fewer than 20 usable observations."""
    s = series.dropna()
    if len(s) < 20:
        return None
    return float(100.0 * (s < value).mean())


# ── Schema detection / root filtering ─────────────────────────────────────────

# Default target roots for the index_etf class (SPX complex preferred; SPY fallback).
# These are the roots we trust as the canonical "own root-class history" per the
# masterplan §3 docstring ("percentile vs OWN root-class history").
_INDEX_ETF_TARGETS = ("SPX", "SPXW", "SPY")


def _filter_and_sort(
    df: pd.DataFrame,
    target_roots: tuple[str, ...] = _INDEX_ETF_TARGETS,
) -> pd.DataFrame | None:
    """Return the rows for `target_roots`, sorted by date, or None when unavailable.

    Handles BOTH schemas:
      - Production schema (build_options_surface.py): multi-root long frame,
        RangeIndex, string `root` column, string `date` column, written index=False.
      - Legacy / test DatetimeIndex schema: single-root, DatetimeIndex, no `root` col.

    For the production schema the function filters to `target_roots` and picks the
    root with the most recent date (SPX runs to 2026; SPY store ended 2022-12-30 so
    SPX wins automatically).  Percentile math is then computed against that root's
    own history only, which is what the docstring specifies.
    """
    if df is None or df.empty:
        return None

    has_root_col = "root" in df.columns
    has_date_col = "date" in df.columns

    if has_root_col and has_date_col:
        # Production schema: multi-root, RangeIndex, string date column.
        # Filter to target roots, pick the one with the most recent date.
        sub = df[df["root"].isin(target_roots)].copy()
        if sub.empty:
            # Fall back to whatever roots exist
            sub = df.copy()
        # Sort by date (string ISO sorts correctly)
        sub = sub.sort_values("date").reset_index(drop=True)
        # Pick the best root: highest max date wins
        best_root = (
            sub.groupby("root")["date"].max().sort_values(ascending=False).index[0]
        )
        return sub[sub["root"] == best_root].reset_index(drop=True)
    else:
        # Legacy / test schema: DatetimeIndex, single root.
        return df.sort_index().reset_index(drop=True)


# ── concentration_hot ─────────────────────────────────────────────────────────

def _concentration_hot(
    df: pd.DataFrame | None,
    target_roots: tuple[str, ...] = _INDEX_ETF_TARGETS,
) -> bool | None:
    """front7_abs_charm_share OR front7_abs_gex_share percentile vs own
    root-class history >= P80.  Returns None when surface data absent.

    Handles the production multi-root parquet schema (build_options_surface.py:
    RangeIndex, string `date` column) by filtering to `target_roots` and computing
    the percentile against that root's own history — not the mixed multi-root pool.
    """
    if df is None:
        return None
    # Need at least 20 rows of history
    charm_col = "front7_abs_charm_share"
    gex_col = "front7_abs_gex_share"
    for col in (charm_col, gex_col):
        if col not in df.columns:
            return None
    # Filter to target root and sort by date (handles both schemas)
    root_df = _filter_and_sort(df, target_roots)
    if root_df is None or root_df.empty:
        return None
    latest = root_df.iloc[-1]
    charm_latest = latest.get(charm_col) if charm_col in root_df.columns else None
    gex_latest = latest.get(gex_col) if gex_col in root_df.columns else None
    if charm_latest is None and gex_latest is None:
        return None
    # Percentile rank of latest vs own root history (excluding latest row)
    hist = root_df.iloc[:-1]
    any_computed = False
    hot = False
    if charm_latest is not None and charm_col in hist.columns:
        pct = _percentile_rank(hist[charm_col], float(charm_latest))
        if pct is not None:
            any_computed = True
            if pct >= _CONCENTRATION_PCTILE:
                hot = True
    if gex_latest is not None and gex_col in hist.columns:
        pct = _percentile_rank(hist[gex_col], float(gex_latest))
        if pct is not None:
            any_computed = True
            if pct >= _CONCENTRATION_PCTILE:
                hot = True
    # Return None when history is too short to compute any percentile
    return hot if any_computed else None


# ── dealer_load_extreme ───────────────────────────────────────────────────────

def _dealer_load_extreme(
    df: pd.DataFrame | None,
    target_roots: tuple[str, ...] = _INDEX_ETF_TARGETS,
) -> bool | None:
    """|net_vex| OR |net_cex| percentile >= P90 (magnitude, sign-agnostic).
    CALENDAR-AGNOSTIC: fires whenever dealer books are extreme, OPEX or not.
    Returns None when surface data absent.

    Handles the production multi-root parquet schema (build_options_surface.py:
    RangeIndex, string `date` column) by filtering to `target_roots` and computing
    the percentile against that root's own history — not the mixed multi-root pool.
    """
    if df is None:
        return None
    vex_col, cex_col = "net_vex", "net_cex"
    has_vex = vex_col in df.columns
    has_cex = cex_col in df.columns
    if not has_vex and not has_cex:
        return None
    # Filter to target root and sort by date (handles both schemas)
    root_df = _filter_and_sort(df, target_roots)
    if root_df is None or root_df.empty:
        return None
    latest = root_df.iloc[-1]
    hist = root_df.iloc[:-1]
    any_computed = False
    extreme = False
    if has_vex:
        v = latest.get(vex_col)
        if v is not None and not (isinstance(v, float) and np.isnan(v)):
            pct = _percentile_rank(hist[vex_col].abs(), abs(float(v)))
            if pct is not None:
                any_computed = True
                if pct >= _DEALER_LOAD_PCTILE:
                    extreme = True
    if has_cex:
        v = latest.get(cex_col)
        if v is not None and not (isinstance(v, float) and np.isnan(v)):
            pct = _percentile_rank(hist[cex_col].abs(), abs(float(v)))
            if pct is not None:
                any_computed = True
                if pct >= _DEALER_LOAD_PCTILE:
                    extreme = True
    return extreme if any_computed else None


# ── gamma_regime (context flag from gex board artifacts) ──────────────────────

def _gamma_regime_context(gex_summary_path: Path | None = None) -> dict | None:
    """Read the current gamma regime + flip-proximity from the gex board artifact
    (site/gex/<TICKER>.json or site/vol/regime.json['opex']).  Returns a plain-word
    context dict, never a hot/cold verdict — gamma_regime is CONTEXT only (RUL-OVC-6).
    Returns None when the artifact is unavailable."""
    if gex_summary_path is None:
        # Default: try site/vol/regime.json which is always present
        site_dir = config.ROOT / config.load().get("storage", {}).get("site_dir", "site")
        gex_summary_path = site_dir / "vol" / "regime.json"
    if not gex_summary_path.exists():
        return None
    try:
        payload = json.loads(gex_summary_path.read_text())
        # vol/regime.json has no embedded GEX summary — try the gex board artifact
        # (site/gex/SPY.json or similar) if this is the vol path
        return None   # gex board not required for W3; null = context unavailable
    except Exception as e:  # noqa: BLE001
        log.debug("opex_risk: gamma_regime read failed: %s", e)
        return None


def _gamma_regime_from_surface(
    df: pd.DataFrame | None,
    target_roots: tuple[str, ...] = _INDEX_ETF_TARGETS,
) -> dict | None:
    """Extract gamma_regime context from the surface parquet (net_gex_bn sign).
    Uses _filter_and_sort to correctly handle the production multi-root schema."""
    if df is None:
        return None
    if "net_gex_bn" not in df.columns:
        return None
    root_df = _filter_and_sort(df, target_roots)
    if root_df is None or root_df.empty:
        return None
    latest = root_df.iloc[-1]
    net_gex = latest.get("net_gex_bn")
    if net_gex is None or (isinstance(net_gex, float) and np.isnan(net_gex)):
        return None
    regime = "long" if float(net_gex) > 0 else "short"
    return {"regime": regime, "net_gex_bn": float(net_gex)}


# ── pin_proximity (W1 construction) ───────────────────────────────────────────

def _pin_proximity_from_entry_state(
    options_entry_state: pd.DataFrame | None,
    primary_tickers: tuple[str, ...] = ("SPY", "SPX", "SPXW", "QQQ"),
) -> bool | None:
    """Read pin_risk from the options_entry_state table for the SPX/SPY complex.
    opex_days<=5 + long gamma + wall<=2% (per options_entry_state.py definition).
    Returns True if ANY primary ticker shows pin_risk=True.
    Returns None when the table is absent or no primary ticker is present."""
    if options_entry_state is None or options_entry_state.empty:
        return None
    pin_col = "pin_risk"
    ticker_col = "ticker"
    if pin_col not in options_entry_state.columns or ticker_col not in options_entry_state.columns:
        return None
    mask = options_entry_state[ticker_col].isin(primary_tickers)
    sub = options_entry_state[mask]
    if sub.empty:
        return None
    pins = sub[pin_col].dropna()
    if pins.empty:
        return None
    return bool(pins.any())


# ── vanna_relief_active / vanna_drag (W1 holdability state) ───────────────────

def _vanna_state_from_entry_state(
    options_entry_state: pd.DataFrame | None,
    primary_tickers: tuple[str, ...] = ("SPY", "SPX", "SPXW"),
) -> tuple[bool | None, bool | None]:
    """Return (vanna_relief_active, vanna_drag) for the SPX/SPY complex.

    vanna_relief_active = True when opt_vanna_relief is True for ANY primary ticker.
    vanna_drag          = True when opt_vanna_relief is False for ALL applicable tickers.

    SYMMETRY CAVEAT (RUL-OVC-1, printed here and in snapshot()):
      vanna_relief (vol falling + positive vanna notional) historically supports
      upside continuation.  The vanna_DRAG side (vol rising + positive vanna notional
      mechanically suppresses rally attempts) is LESS WELL DOCUMENTED.  The drag
      direction prints as a watch item, not an authority call.  Both are
      holdability/de-escalation reads only (RO-3); neither is a directional buy/sell.

    Returns (None, None) when the table or columns are absent."""
    if options_entry_state is None or options_entry_state.empty:
        return None, None
    # opt_vanna_relief is the W1 stamp column; fall back to vanna_hedge_5d + iv30_5d_chg
    vr_col = "opt_vanna_relief"
    ticker_col = "ticker"
    if ticker_col not in options_entry_state.columns:
        return None, None
    mask = options_entry_state[ticker_col].isin(primary_tickers)
    sub = options_entry_state[mask]
    if sub.empty:
        return None, None
    if vr_col not in sub.columns:
        return None, None
    vals = sub[vr_col].dropna()
    if vals.empty:
        return None, None
    relief_active = bool(vals.any())
    drag = bool((~vals.astype(bool)).all())
    return relief_active, drag


# ── window_phase (engine/opex.py) ─────────────────────────────────────────────

def _window_phase(spy_close: pd.Series | None) -> dict:
    """Current OPEX phase snapshot from engine/opex.py.
    Returns a safe partial dict on failure."""
    null = {
        "phase": None, "td_to_opex": None, "td_since_opex": None,
        "in_opex_week": None, "is_quad_cycle": None,
    }
    if spy_close is None or len(spy_close) < 500:
        return null
    try:
        snap = _opex_cal.snapshot(spy_close)
        if not snap.get("available"):
            return null
        return {
            "phase": snap.get("phase"),
            "td_to_opex": snap.get("td_to_opex"),
            "td_since_opex": snap.get("td_since_opex"),
            "in_opex_week": snap.get("in_opex_week"),
            "is_quad_cycle": snap.get("is_quad_cycle"),
        }
    except Exception as e:  # noqa: BLE001
        log.debug("opex_risk: window_phase failed: %s", e)
        return null


# ── Level words ───────────────────────────────────────────────────────────────

def _level_word(n_hot: int) -> str:
    """0-2 → quiet · 3-4 → elevated · 5+ → heavy"""
    if n_hot <= 2:
        return "quiet"
    if n_hot <= 4:
        return "elevated"
    return "heavy"


def _level_word_zh(n_hot: int) -> str:
    if n_hot <= 2:
        return "平静"
    if n_hot <= 4:
        return "偏高"
    return "重度"


# ── Main snapshot ─────────────────────────────────────────────────────────────

def snapshot(
    spy_close: pd.Series | None = None,
    options_entry_state: pd.DataFrame | None = None,
    data_root: Path | None = None,
) -> dict:
    """Compose the OPEX window risk snapshot.

    Args:
        spy_close:           SPY daily close series (for opex.py phase tags).
                             May be None → window_phase nulls out.
        options_entry_state: DataFrame from engine/options_entry_state.build()
                             (for pin_risk + vanna_relief reads).
                             May be None → those states null out.
        data_root:           Override for data/ root path (tests).

    Returns a dict with keys:
        schema          "opex_risk.v1"
        asof            ISO date string
        n_hot           int — count of hot (True) states in applicable states
        n_applicable    int — count of states where data was available
        level           "quiet" | "elevated" | "heavy"
        level_zh        Chinese level word
        states          dict of per-state results (bool | None for event_collision)
        window_phase    dict from engine/opex.py
        glance_en       Tier-1 stance sentence (EN)
        glance_zh       Tier-1 stance sentence (ZH)
        doctrine        Standing law reminder
        dealer_sign_passport  Caveat on dealer-sign unobservability
        vanna_symmetry_caveat Caveat on vanna_drag directionality
        post_opex_watch       Era3-only post-OPEX weakness watch item

    Never raises.  Partial data → states null, n_applicable shrinks.
    """
    try:
        return _snapshot_inner(spy_close, options_entry_state, data_root)
    except Exception as e:  # noqa: BLE001
        log.warning("opex_risk.snapshot failed: %s", e)
        return {
            "schema": "opex_risk.v1",
            "asof": str(date.today()),
            "n_hot": 0,
            "n_applicable": 0,
            "level": "quiet",
            "level_zh": "平静",
            "states": {},
            "window_phase": {},
            "glance_en": "OPEX risk read unavailable — surface data absent.",
            "glance_zh": "OPEX风险读取不可用 — 数据缺失。",
            "doctrine": _DOCTRINE,
            "dealer_sign_passport": _DEALER_SIGN_PASSPORT,
            "vanna_symmetry_caveat": _VANNA_SYMMETRY_CAVEAT,
            "post_opex_watch": _POST_OPEX_WATCH,
            "error": str(e),
        }


def _snapshot_inner(
    spy_close: pd.Series | None,
    options_entry_state: pd.DataFrame | None,
    data_root: Path | None,
) -> dict:
    # ── Layer-2 surface reads ──────────────────────────────────────────────
    idx_df = _read_surface(_PRIMARY_ROOT_CLASS, data_root)
    # Also read sector_etf for a broader dealer_load signal if index_etf absent
    sec_df = _read_surface("sector_etf", data_root) if idx_df is None else None
    primary_df = idx_df if idx_df is not None else sec_df

    # ── Per-state computation ──────────────────────────────────────────────
    states: dict[str, bool | None] = {}

    # 1. concentration_hot
    states["concentration_hot"] = _concentration_hot(primary_df)

    # 2. dealer_load_extreme (CALENDAR-AGNOSTIC)
    states["dealer_load_extreme"] = _dealer_load_extreme(primary_df)

    # 3. gamma_regime (context flag — gex sign from surface)
    gr = _gamma_regime_from_surface(primary_df)
    states["gamma_regime"] = None   # context flag, not a hot/cold boolean
    gamma_regime_ctx = gr           # kept for glance copy

    # 4. pin_proximity (W1 construction from options_entry_state)
    states["pin_proximity"] = _pin_proximity_from_entry_state(options_entry_state)

    # 5. vanna_relief_active / vanna_drag (W1 holdability)
    relief, drag = _vanna_state_from_entry_state(options_entry_state)
    states["vanna_relief_active"] = relief
    states["vanna_drag"] = drag

    # 6. window_phase (context from engine/opex.py — not scored)
    wp = _window_phase(spy_close)
    states["window_phase"] = None   # context, excluded from n_hot count

    # 7. event_collision — NULL SLOT (W4 plugs in engine/event_window.py)
    # W4 will set this via the caller interface; for now it is always None.
    # The slot is preserved so W4 can add it without changing downstream callers.
    states["event_collision"] = None   # NULL — W4 not yet built

    # ── K-of-N count (unweighted, availability-normalized) ─────────────────
    # Only states that are NOT pure context flags count toward n_hot/n_applicable.
    # gamma_regime and window_phase are context-only (excluded by design).
    # event_collision is a null slot (excluded until W4).
    _SCORED_STATES = (
        "concentration_hot",
        "dealer_load_extreme",
        "pin_proximity",
        "vanna_relief_active",
        "vanna_drag",
    )
    n_hot = 0
    n_applicable = 0
    for k in _SCORED_STATES:
        v = states.get(k)
        if v is None:
            continue        # data absent → doesn't count in denominator
        n_applicable += 1
        if v:
            n_hot += 1

    level = _level_word(n_hot)
    level_zh = _level_word_zh(n_hot)

    # ── Glance copy (Tier-1, stance-verb, plain words) ─────────────────────
    phase = wp.get("phase")  # None when SPY series unavailable — glance says "Options cycle", never fabricates a phase
    td_to = wp.get("td_to_opex")
    is_quad = bool(wp.get("is_quad_cycle"))
    glance_en, glance_zh = _make_glance(
        level, phase, td_to, is_quad, n_hot, n_applicable,
        gamma_regime_ctx, states,
    )

    return {
        "schema": "opex_risk.v1",
        "asof": str(date.today()),
        "n_hot": n_hot,
        "n_applicable": n_applicable,
        "level": level,
        "level_zh": level_zh,
        "states": states,
        "window_phase": wp,
        "glance_en": glance_en,
        "glance_zh": glance_zh,
        "doctrine": _DOCTRINE,
        "dealer_sign_passport": _DEALER_SIGN_PASSPORT,
        "vanna_symmetry_caveat": _VANNA_SYMMETRY_CAVEAT,
        "post_opex_watch": _POST_OPEX_WATCH,
    }


def _make_glance(
    level: str,
    phase: str,
    td_to: int | None,
    is_quad: bool,
    n_hot: int,
    n_applicable: int,
    gamma_ctx: dict | None,
    states: dict,
) -> tuple[str, str]:
    """Compose the Tier-1 stance sentence.

    Design Doctrine Laws 1-3:
      - MUST carry a stance verb (Watch / Hold / Ease off)
      - Plain words only — no internal state names exposed
      - Technicals go to hover / Tier-2 (not here)
    """
    # Phase word
    phase_words = {
        "opex_week": "Expiration week",
        "post_opex": "Post-expiration window",
        "mid_cycle": "Mid-cycle",
    }
    phase_en = phase_words.get(phase, "Options cycle")
    quad_tag = " (quad-witching)" if is_quad else ""
    td_tag = f" — {td_to}d to expiry" if td_to is not None else ""

    # Availability note
    if n_applicable == 0:
        avail_en = "Surface data building — readings pending."
        avail_zh = "数据积累中，信号待定。"
        return (
            f"{phase_en}{quad_tag}{td_tag}. {avail_en} Watch, don't chase.",
            f"{phase_en}{quad_tag}{td_tag}。{avail_zh}观望，不追涨。",
        )

    # Stance verb by level
    stance_map = {
        "quiet": ("Low dealer pressure — hold positions, stay patient.", "低经销商压力 — 持仓，保持耐心。"),
        "elevated": ("Dealer load rising — watch for sticky tape. Watch, don't chase.", "经销商负载上升 — 注意粘性价格行为。观望，不追涨。"),
        "heavy": ("Heavy dealer concentration — expect compressed range into expiry. Ease off new entries.", "经销商集中度高 — 到期前价格区间料趋窄。减少新进场。"),
    }
    stance_en, stance_zh = stance_map.get(level, stance_map["quiet"])

    # Context chips
    chips_en, chips_zh = [], []
    # Plain words only at Tier-1 (Design Doctrine) — the internal state names
    # (vanna_relief, dealer_load_extreme, ...) stay in the Tier-2 state stack.
    if states.get("pin_proximity"):
        chips_en.append("price may stick near big strikes")
        chips_zh.append("价格或被大额行权价吸住")
    if states.get("vanna_relief_active"):
        chips_en.append("hedging flows easing — positions sit easier")
        chips_zh.append("对冲压力缓解 — 持仓更稳")
    elif states.get("vanna_drag"):
        chips_en.append("hedging flows dragging")
        chips_zh.append("对冲压力拖累")
    if states.get("dealer_load_extreme"):
        chips_en.append("dealer books stretched")
        chips_zh.append("做市商持仓拉满")
    if states.get("concentration_hot"):
        chips_en.append("expiry-week exposure crowded")
        chips_zh.append("到期周敞口拥挤")

    chip_str_en = (", ".join(chips_en) + ". ") if chips_en else ""
    chip_str_zh = ("，".join(chips_zh) + "。") if chips_zh else ""

    avail_note = f" ({n_hot}/{n_applicable} signals active)" if n_applicable > 0 else ""
    en = f"{phase_en}{quad_tag}{td_tag}. {chip_str_en}{stance_en}{avail_note}"
    zh = f"{phase_en}{quad_tag}{td_tag}。{chip_str_zh}{stance_zh}（{n_hot}/{n_applicable}项信号激活）"
    return en, zh


# ── Standing-law strings ───────────────────────────────────────────────────────

_DOCTRINE = (
    "OPEX window risk read — display/context only (RIC-R2/R3). "
    "Level = unweighted count of hot states (n_hot/n_applicable). "
    "Framing: vol/holdability/turn-WATCH only. "
    "NEVER read by compute(), never in _SCARES, never sizes or gates anything. "
    "Event/OPEX proximity states are display context, not risk elevations."
)

_DEALER_SIGN_PASSPORT = (
    "ASSUMPTION: net_vex/net_cex sign reflects the standard long-call+1/short-put+1 "
    "dealer convention (SqueezeMetrics / similar). This convention is structurally "
    "UNOBSERVABLE from public data. |·|-magnitude constructions are used where possible "
    "(concentration_hot, dealer_load_extreme) precisely because they are sign-agnostic. "
    "Any sign-dependent reading (vanna_hedge_5d, signed_vanna_pressure) carries this "
    "unobservable-assumption passport and must not be promoted to authority."
)

_VANNA_SYMMETRY_CAVEAT = (
    "VANNA SYMMETRY CAVEAT (RUL-OVC-1): vanna_relief (vol falling + positive vanna "
    "notional) has documented historical support for upside continuation in the "
    "index-ETF complex. The INVERSE state (vanna_drag: vol rising + positive vanna) "
    "is mechanically plausible but LESS WELL DOCUMENTED — it prints as a watch item, "
    "not an authority call. Both states are holdability/de-escalation reads only (RO-3). "
    "Neither is a directional buy or sell."
)

_POST_OPEX_WATCH = (
    "POST-OPEX WEAKNESS WATCH (Era3-only): The −0.9% post-OPEX-week return effect "
    "(Stivers-Sun 2013, 1988-2010) is ERA-SPLIT — it decayed post-2010 and the "
    "'March worst' claim is WRONG (post-March-OPEX is actually among the stronger months "
    "per the RIC domain research pack). This watch item is printed honestly with its "
    "era-status: an accruing observation, not a durable signal. Framing: vol/path only, "
    "never directional return (RO-3/F-21)."
)


# ── Forward ledger (data/opex_windows/forward_log.jsonl) ─────────────────────

def ledger_lane_armed() -> bool:
    """True only on the nightly ledger-advancing collect lane.
    Mirrors engine/market_state_audit.ledger_lane_armed() exactly."""
    lane = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return lane.lower() == "nightly"


def _ledger_path(data_root: Path | None = None) -> Path:
    base = data_root if data_root is not None else config.data_dir()
    p = base / "opex_windows" / "forward_log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_ledger(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return rows


def _write_ledger(p: Path, rows: list[dict]) -> None:
    p.write_text(
        "\n".join(json.dumps(r, separators=(",", ":"), default=str) for r in rows) + "\n"
    )


def log_window(
    snap: dict,
    data_root: Path | None = None,
) -> bool:
    """Stamp one row per monthly OPEX window at T−5 before expiration.

    Keep-FIRST idempotent: the key is (window_month = YYYY-MM of the expiration).
    Once a row is written for a given month, subsequent calls in the same month
    are no-ops.  This means the T−5 snapshot is the PERMANENT record for that
    window; intraday re-runs do not overwrite it.

    Lane gate: only advances on COLLECT_LANE=nightly.  Off-lane = read-only,
    returns False without writing.

    GRADING RULERS (frozen in this PR — do NOT change without a new PR):
      forward_5d_rv   : 5-day realized vol (annualized) vs trailing_rv (90d)
      forward_10d_rv  : 10-day realized vol (annualized) vs trailing_rv
      max_dd_post10d  : max drawdown in the 10 calendar days after the expiry date
      range_compression: (high-low)/ATR(20) in 5d before expiry vs 20d trailing ATR
      Targets are VOL/PATH objects; NO directional return (RO-3/F-21).

    Schema (opex_window_log.v1):
      window_month    str   YYYY-MM of the monthly expiration cycle
      entry_date      str   ISO date this row was stamped (T-5 before expiry)
      expiry_date     str   ISO date of the monthly 3rd-Friday expiration
      n_hot           int   count of hot states at entry
      n_applicable    int   count of applicable states at entry
      level           str   "quiet"|"elevated"|"heavy"
      states          dict  per-state True/False/None snapshot
      window_phase    dict  opex phase context
      grading_rulers  dict  pre-declared ruler definitions (frozen)
      graded          null  set by the grader when maturity arrives
      logged_at       str   UTC ISO timestamp of this write
    """
    try:
        if not ledger_lane_armed():
            log.debug("opex_risk: log_window skipped — lane not armed")
            return False
        # Only stamp if we are T-5 or closer to the next expiry
        wp = snap.get("window_phase") or {}
        td_to = wp.get("td_to_opex")
        if td_to is None or td_to > 5:
            log.debug("opex_risk: log_window skipped — td_to_opex=%s (need <=5)", td_to)
            return False
        # Compute the window_month from the expiry date
        # We reconstruct the expiry from today + td_to_opex trading days
        # Simpler: use year+month of today if in opex_week, else the next expiry month
        today = date.today()
        # Estimate expiry: today + td_to calendar days (approximate; within 5 td it's close)
        # Use window_phase for the month key
        phase = wp.get("phase")
        if phase == "post_opex":
            # Already past — don't re-log (the T-5 window has passed)
            return False
        # window_month key: current month if in opex_week, next month otherwise
        # We use today + td_to to get an approximate expiry date for the month key
        approx_expiry = today
        if td_to is not None and td_to >= 0:
            from datetime import timedelta
            approx_expiry = today + timedelta(days=int(td_to) + 1)
        window_month = approx_expiry.strftime("%Y-%m")
        p = _ledger_path(data_root)
        rows = _read_ledger(p)
        # Keep-FIRST: skip if this window month already logged
        if any(r.get("window_month") == window_month for r in rows):
            log.debug("opex_risk: window %s already logged (keep-first)", window_month)
            return False
        # Build the ledger row
        entry: dict = {
            "schema": "opex_window_log.v1",
            "window_month": window_month,
            "entry_date": str(today),
            "expiry_date": str(approx_expiry),
            "n_hot": snap.get("n_hot"),
            "n_applicable": snap.get("n_applicable"),
            "level": snap.get("level"),
            "states": snap.get("states") or {},
            "window_phase": wp,
            "grading_rulers": {
                "forward_5d_rv": {
                    "description": "5-day realized vol (annualized, sqrt(252)*std(daily_ret)) "
                                   "over the 5 calendar days following entry_date, "
                                   "vs trailing_rv (90-day window ending T-5)",
                    "target_type": "vol",
                    "direction": "none",
                },
                "forward_10d_rv": {
                    "description": "10-day realized vol (annualized) post-entry vs trailing_rv",
                    "target_type": "vol",
                    "direction": "none",
                },
                "max_dd_post10d": {
                    "description": "Max drawdown (peak-to-trough on daily closes, sign-negative "
                                   "if spot falls) in the 10 calendar days after the expiry_date. "
                                   "Path object — not directional return (RO-3/F-21).",
                    "target_type": "path",
                    "direction": "none",
                },
                "range_compression": {
                    "description": "(5d pre-expiry daily high-low range) / ATR(20) vs 20d trailing "
                                   "ATR baseline.  Captures pin/compression behavior into expiry.",
                    "target_type": "path",
                    "direction": "none",
                },
            },
            "graded": None,
            "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        rows.append(entry)
        _write_ledger(p, rows)
        log.info("opex_risk: logged window %s (level=%s, n_hot=%s/%s)",
                 window_month, snap.get("level"), snap.get("n_hot"), snap.get("n_applicable"))
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("opex_risk: log_window failed: %s", e)
        return False
