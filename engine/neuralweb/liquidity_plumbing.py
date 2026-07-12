"""engine.neuralweb.liquidity_plumbing — NW Liquidity Plumbing lobe (Phase 0+1).

DISPLAY / SHADOW tier. DE-ESCALATION-ONLY authority. Zero scored surfaces.
This lobe EXPOSES liquidity context — it never originates a signal, raises a
score/rank, or fires a hard gate. The ONLY entry-tailwind reference is the
already-measured cycle-ladder 21d nudge (engine/cycles.py stays untouched).

Phase 0+1: quantity + quality + RRP + TGA + auctions + fed-stance context.
  RLT-R4: treasury.tga_impulse sub-block: episode detector (drawdown or build
  >= $75bn within <= 10 business sessions, or >= $120bn cumulative from last
  quarter-end), with direction/magnitude_bn/days/since/quarter_end_adjacent
  and plain-word summaries. Names the event; does NOT upgrade quality.
Phase 3 (funding): EFFR/SOFR/SOFR-99pctl minus IORB spreads INTEGRATED
  (level + 20d delta + expanding percentile + descriptive
  reserve_scarcity_state). SRF take-up and discount-window primary credit
  stay null — no collector for them yet (gaps[] entry).
Phase 3 (reserves): fed.reserve_balances_bn from data/fred/WRESBAL.parquet
  (fail-open: null + gaps[] entry until the collector has run once).
Phase 5: H.4.1 swap lines + FIMA — ALL null here.

Components readout: per-component {level_bn, d20_bn, d65_bn, pctile} for
walcl/rrp/tga (+reserves when present) plus a 90-calendar-day netliq
sparkline — display-only, derived from fed_net_liquidity.parquet.

House-law constraints (non-negotiable, CI-enforced):
- tier = shadow, weights = none
- The word "validated" must not appear in any user-facing string (CI-guarded)
- Fail-open: missing source → gaps[] entry + null the block, still emit valid JSON
- Fed/Treasury "condition/steer" liquidity, NOT "control markets"
- Swap-line usage = stress backstop, NOT clean risk-on

Data sources (existing only — no new collectors):
  quantity  : data/macro/fed_net_liquidity.parquet (daily, cols: netliq_bn etc.)
  quality   : data/regime/latest.json :: liquidity_quality (incl. stress_overlay)
  overlay   : data/regime/latest.json :: liquidity_overlay
  fed stance: data/regime/latest.json :: fed_stance
  conditions: data/regime/latest.json :: conditions
  treasury  : data/treasury/net_issuance.parquet, data/treasury/tga.parquet
  auctions  : data/treasury_auctions/auctions.parquet
  funding   : data/nyfed/effr.parquet, data/fred/IORB.parquet,
              data/fred/SOFR.parquet, data/ofr/FNYR-SOFR_99Pctl-A.parquet
  reserves  : data/fred/WRESBAL.parquet (fail-open until first collect)

Public API:
  compute(regime_latest, netliq_frame, treasury_frames, auction_snapshot, config) -> dict
  snapshot(root=None) -> dict   (reads stores, calls compute, returns UNSTAMPED dict)

The CLI (scripts/build_liquidity_plumbing.py) calls snapshot(), stamps via
engine.neuralweb.envelope.stamp(), and atomically writes
data/neuralweb/liquidity_plumbing.json.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema / authority constants
# ---------------------------------------------------------------------------

_SCHEMA = "neuralweb.liquidity_plumbing.v1"

_AUTHORITY = {
    "entry_tailwind": "measured_near_term_only",
    "score_raise": False,
    "score_lower": "buy_setup_caution_only_where_existing_engine_allows",
    "explain": True,
    "attend": True,
    "deescalate": True,
    "hard_gate": False,
}

# Integration status per phase — additive minor field (schema stays v1).
# p3_reserve_balances is resolved dynamically in compute() to reflect actual load state.
_PHASE_STATUS_BASE = {
    "p0_p1_quantity_quality": "integrated",
    "p3_funding_spreads": "integrated",
    "p3_srf_discount_window": "pending_collection",
    "p5_swap_lines": "integrated_ird_w1",   # SWPT/WLCFLL from fred adapter (IRD-W1)
    "p5_fima_repo": "pending_no_free_breakout",  # no free per-facility source
}

# Kept for backward-compat references (degraded_payload, tests); compute() builds its own copy.
_PHASE_STATUS = {
    **_PHASE_STATUS_BASE,
    "p3_reserve_balances": "fail_open_until_wresbal_collected",
}

# 20-trading-day and 65-trading-day lookback windows (business-daily index)
_D20_ROWS = 20
_D65_ROWS = 65

# Sparkline window — calendar days of netliq_bn tail for display
_SPARKLINE_CAL_DAYS = 90

# Reserve-scarcity descriptive thresholds (basis points vs IORB).
# Descriptive vocabulary only — comfortable / normalizing / tightening /
# scarce / unknown. Never a command, never a gate.
#   EFFR at/above IORB (Sep-2019 signature)            → scarce
#   SOFR ≥ +10bp over IORB (repo squeeze)               → scarce
#   both EFFR and SOFR within 5bp below IORB            → tightening
#   EFFR within 5bp of IORB, or spreads drifting up
#   ≥ +2bp over 20 business days                        → normalizing
#   otherwise (spreads comfortably below IORB, flat)    → comfortable
_SCARCE_EFFR_BP = 0.0
_SCARCE_SOFR_BP = 10.0
_NEAR_IORB_BP = -5.0
_DRIFT_D20_BP = 2.0


# ---------------------------------------------------------------------------
# Series / spread helpers (module-level so tests can target them directly)
# ---------------------------------------------------------------------------

def _to_series(frame: pd.DataFrame | None) -> pd.Series | None:
    """First column of a single-column parquet frame as a sorted, datetime-indexed
    Series (accepts either a datetime index or a 'date' column). None-safe."""
    if frame is None or getattr(frame, "empty", True):
        return None
    try:
        df = frame.copy()
        if "date" in df.columns:
            df = df.set_index("date")
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        s = df[df.columns[0]].dropna()
        return s if not s.empty else None
    except Exception as exc:  # noqa: BLE001
        log.warning("liquidity_plumbing._to_series: unreadable frame — %s", exc)
        return None


def _spread_bp(rate: pd.Series | None, anchor: pd.Series | None) -> pd.Series | None:
    """(rate − anchor) × 100 in basis points, on intersecting dates only."""
    if rate is None or anchor is None:
        return None
    sp = ((rate - anchor) * 100.0).dropna()
    return sp if not sp.empty else None


def _level_d20_pctile(
    series: pd.Series | None, ndigits: int = 2
) -> tuple[float | None, float | None, float | None]:
    """(latest level, 20-row delta, expanding percentile of the latest level).

    Percentile = share of the full history ≤ the latest value (same expanding
    convention as netliq_pctile_expanding). Any missing piece → None.
    """
    if series is None or series.empty:
        return None, None, None
    level = float(round(series.iloc[-1], ndigits))
    d20: float | None = None
    if len(series) > _D20_ROWS:
        d20 = float(round(series.iloc[-1] - series.iloc[-_D20_ROWS - 1], ndigits))
    pctile = float(round((series <= series.iloc[-1]).mean(), 4))
    return level, d20, pctile


def _component_stats(series: pd.Series | None, ndigits: int = 1) -> dict[str, Any]:
    """Per-component display stats: {level_bn, d20_bn, d65_bn, pctile}."""
    out: dict[str, Any] = {"level_bn": None, "d20_bn": None, "d65_bn": None, "pctile": None}
    if series is None or series.empty:
        return out
    level, d20, pctile = _level_d20_pctile(series, ndigits=ndigits)
    out["level_bn"] = level
    out["d20_bn"] = d20
    out["pctile"] = pctile
    if len(series) > _D65_ROWS:
        out["d65_bn"] = float(round(series.iloc[-1] - series.iloc[-_D65_ROWS - 1], ndigits))
    return out


def _derive_reserve_scarcity_state(
    effr_bp: float | None,
    sofr_bp: float | None,
    effr_d20_bp: float | None,
    sofr_d20_bp: float | None,
) -> str:
    """Descriptive reserve-scarcity read from IORB spreads (see threshold table).

    Vocabulary is frozen and descriptive-only: comfortable | normalizing |
    tightening | scarce | unknown. This never gates, sizes, or escalates.
    """
    if effr_bp is None and sofr_bp is None:
        return "unknown"
    if (effr_bp is not None and effr_bp >= _SCARCE_EFFR_BP) or (
        sofr_bp is not None and sofr_bp >= _SCARCE_SOFR_BP
    ):
        return "scarce"
    if (
        effr_bp is not None
        and effr_bp >= _NEAR_IORB_BP
        and sofr_bp is not None
        and sofr_bp >= _NEAR_IORB_BP
    ):
        return "tightening"
    drifting_up = any(
        d is not None and d >= _DRIFT_D20_BP for d in (effr_d20_bp, sofr_d20_bp)
    )
    if (effr_bp is not None and effr_bp >= _NEAR_IORB_BP) or drifting_up:
        return "normalizing"
    return "comfortable"

# ---------------------------------------------------------------------------
# Headline state derivation table (contract §headline.state)
# ---------------------------------------------------------------------------

def _derive_headline_state(
    quality_label: str | None,
    rrp_exhausted: bool | None,
    stress_confirming: bool | None,
    fed_share: float | None,
    overlay: str | None,
    degraded: bool,
) -> str:
    """Derive the headline.state label from quality + RRP + overlay.

    Contract table (v1.1 — amended by RLT-R13, 2026-07-12):
      benign-expansion                                    → benign_liquidity_tailwind
      stress-expansion & confirming_stress                → stress_liquidity_expansion
      stress-expansion & !confirming_stress & mechanical
                       (fed_share<0.5)                   → mechanical_liquidity_tailwind
        (RRP exhaustion no longer gates mechanical — it becomes a plain-word
        caveat in the summary instead of forcing stress classification)
      stress-expansion & !confirming_stress
                       & fed_share≥0.5                   → benign_liquidity_tailwind
      stress-expansion & !confirming_stress
                       & fed_share unknown               → stress_liquidity_expansion
        (composition unattributable — stay conservative)
      neutral                                             → neutral_with_buffer
      neutral-hollow                                      → neutral_hollow
      contracting                                         → orderly_drain
      unknown | degraded                                  → data_degraded

    Funding/foreign-dollar states (reserve_scarcity_warning,
    foreign_dollar_stress) CANNOT fire in Phase 1 — never emit them.
    """
    if degraded or not quality_label or quality_label == "unknown":
        return "data_degraded"

    label = quality_label
    if label == "benign-expansion":
        return "benign_liquidity_tailwind"
    if label == "stress-expansion":
        if stress_confirming:
            return "stress_liquidity_expansion"
        mechanical = fed_share is not None and fed_share < 0.5
        if mechanical:
            return "mechanical_liquidity_tailwind"
        if fed_share is None:
            # composition unattributable — stay conservative
            return "stress_liquidity_expansion"
        return "benign_liquidity_tailwind"
    if label == "neutral":
        return "neutral_with_buffer"
    if label == "neutral-hollow":
        return "neutral_hollow"
    if label == "contracting":
        return "orderly_drain"
    # fallback
    return "data_degraded"


# ---------------------------------------------------------------------------
# TGA impulse detector (RLT-R4)
# ---------------------------------------------------------------------------

# Episode thresholds (RLT-R4 ruling text)
_TGA_THRESHOLD_FAST_BN: float = 75.0    # >= $75bn within <= 10 business sessions
_TGA_THRESHOLD_FAST_SESSIONS: int = 10
_TGA_THRESHOLD_QE_BN: float = 120.0     # >= $120bn from the last quarter-end date
_TGA_QE_ADJ_WINDOW_BD: int = 7          # episode start within 7 business days of quarter end


def _quarter_end_dates(year: int) -> list[date]:
    """Return the four calendar quarter-end dates for a given year (Mar 31, Jun 30, Sep 30, Dec 31).

    Uses simple month-boundary rule as specified in the lane brief — no external calendar import.
    """
    from calendar import monthrange
    ends = []
    for month in (3, 6, 9, 12):
        last_day = monthrange(year, month)[1]
        ends.append(date(year, month, last_day))
    return ends


def _is_quarter_end_adjacent(episode_start: date, tga_index: "pd.DatetimeIndex") -> bool:
    """True if episode_start is within _TGA_QE_ADJ_WINDOW_BD business sessions after any
    calendar quarter end (Mar 31, Jun 30, Sep 30, Dec 31) across a 2-year window.

    Business sessions counted by position in the TGA business-daily index.
    """
    # Gather candidate quarter-end dates from the year before through the year of episode_start
    candidate_qe: list[date] = []
    for yr in (episode_start.year - 1, episode_start.year):
        candidate_qe.extend(_quarter_end_dates(yr))

    ep_ts = pd.Timestamp(episode_start)
    for qe in candidate_qe:
        qe_ts = pd.Timestamp(qe)
        if qe_ts > ep_ts:
            continue
        # Count business sessions between qe_ts and ep_ts in the TGA index
        sessions_after = int(((tga_index >= qe_ts) & (tga_index <= ep_ts)).sum()) - 1
        # sessions_after == 0 means same day (qe == episode_start); count 0 as adjacent
        if 0 <= sessions_after <= _TGA_QE_ADJ_WINDOW_BD:
            return True
    return False


def _derive_tga_impulse(tga_series_bn: "pd.Series | None") -> dict[str, Any]:
    """Detect a named TGA drawdown or build episode (RLT-R4).

    Returns a tga_impulse sub-block with:
      active (bool): episode is firing
      direction ('drawdown'|'build'|null): which way TGA moved
      magnitude_bn (float|null): total $ bn moved during episode
      days (int|null): number of business sessions in episode
      since (str|null): ISO date of episode start
      quarter_end_adjacent (bool): episode start within 7 BD after a calendar quarter end
      summary_en (str): plain-word EN summary
      summary_zh (str): plain-word ZH equivalent

    Episode rule (RLT-R4):
      - drawdown or build of >= $75bn within <= 10 business sessions, OR
      - >= $120bn cumulative move measured from the last quarter-end date

    The impulse NAMES the event; it never upgrades quality or authority.
    """
    _null: dict[str, Any] = {
        "active": False,
        "direction": None,
        "magnitude_bn": None,
        "days": None,
        "since": None,
        "quarter_end_adjacent": False,
        "summary_en": "No TGA impulse detected.",
        "summary_zh": "未检测到TGA冲量。",
    }

    if tga_series_bn is None or tga_series_bn.empty or len(tga_series_bn) < 2:
        return dict(_null)

    try:
        s = tga_series_bn.sort_index()
        latest_val = float(s.iloc[-1])
        latest_date = s.index[-1].date()

        # --- Quarter-end cumulative episode: >= $120bn from last quarter-end date ---
        # Evaluated FIRST so that a QE-anchored episode (e.g. Jun-30 spike) is not
        # pre-empted by a trailing 10-BD window that anchors the start before the
        # quarter-end date, which would under-report magnitude and drop the seasonal
        # attribution (quarter_end_adjacent=False when the real anchor is Jun-30).
        today = latest_date
        candidate_qe: list[date] = []
        for yr in (today.year - 1, today.year):
            candidate_qe.extend(_quarter_end_dates(yr))
        past_qe = [d for d in candidate_qe if d <= today]
        qe_result: dict[str, Any] | None = None
        if past_qe:
            last_qe = max(past_qe)
            qe_ts = pd.Timestamp(last_qe)
            qe_slice = s[s.index >= qe_ts]
            if len(qe_slice) >= 2:
                qe_start_val = float(qe_slice.iloc[0])
                move = latest_val - qe_start_val
                if abs(move) >= _TGA_THRESHOLD_QE_BN:
                    direction = "drawdown" if move < 0 else "build"
                    magnitude_bn = float(round(abs(move), 1))
                    episode_start = qe_slice.index[0].date()
                    days = len(qe_slice) - 1
                    qe_adj = _is_quarter_end_adjacent(episode_start, s.index)
                    summary_en, summary_zh = _tga_impulse_summary(
                        direction, magnitude_bn, episode_start, qe_adj
                    )
                    qe_result = {
                        "active": True,
                        "direction": direction,
                        "magnitude_bn": magnitude_bn,
                        "days": days,
                        "since": str(episode_start),
                        "quarter_end_adjacent": qe_adj,
                        "summary_en": summary_en,
                        "summary_zh": summary_zh,
                    }

        # --- Fast episode: >= $75bn within <= 10 business sessions ---
        # Only fires when no QE-cumulative episode already covers the same direction
        # (avoids truncating the seasonal attribution for near-QE episodes).
        lookback = s.iloc[-(_TGA_THRESHOLD_FAST_SESSIONS + 1):]
        fast_result: dict[str, Any] | None = None
        if len(lookback) >= 2:
            start_val = float(lookback.iloc[0])
            move = latest_val - start_val  # positive = build, negative = drawdown
            if abs(move) >= _TGA_THRESHOLD_FAST_BN:
                direction = "drawdown" if move < 0 else "build"
                # Suppress if QE episode already covers this direction — prefer the
                # seasonally-anchored, larger-magnitude read.
                if qe_result is None or qe_result["direction"] != direction:
                    magnitude_bn = float(round(abs(move), 1))
                    episode_start = lookback.index[0].date()
                    days = len(lookback) - 1
                    qe_adj = _is_quarter_end_adjacent(episode_start, s.index)
                    summary_en, summary_zh = _tga_impulse_summary(
                        direction, magnitude_bn, episode_start, qe_adj
                    )
                    fast_result = {
                        "active": True,
                        "direction": direction,
                        "magnitude_bn": magnitude_bn,
                        "days": days,
                        "since": str(episode_start),
                        "quarter_end_adjacent": qe_adj,
                        "summary_en": summary_en,
                        "summary_zh": summary_zh,
                    }

        # Prefer QE-anchored result (larger magnitude, seasonal context).
        if qe_result is not None:
            return qe_result
        if fast_result is not None:
            return fast_result

    except Exception as exc:  # noqa: BLE001
        log.warning("liquidity_plumbing._derive_tga_impulse: error — %s", exc)

    return dict(_null)


def _tga_impulse_summary(
    direction: str, magnitude_bn: float, since: date, qe_adj: bool
) -> tuple[str, str]:
    """Plain-word EN+ZH summary for a TGA impulse episode.

    Vocabulary rules: no jargon, no promises, no 'validated'. Describes the
    mechanism plainly (Treasury spending down its account puts cash into the
    system; Treasury building it up absorbs cash).
    """
    mag_str = f"${magnitude_bn:.0f}B"
    since_str = since.strftime("%b %-d")
    since_zh = f"{since.month}月{since.day}日"
    if direction == "drawdown":
        en = (
            f"Treasury spent down {mag_str} of its cash account since {since_str} — "
            "that cash re-enters the financial system (supportive while it lasts)."
        )
        zh = (
            f"自{since_zh}起，美国财政部已动用现金账户中的{mag_str} — "
            "这部分资金重新流入金融体系（短期内具支撑性）。"
        )
    else:
        en = (
            f"Treasury rebuilt its cash account by {mag_str} since {since_str} — "
            "that cash is absorbed from the financial system (mild headwind while it lasts)."
        )
        zh = (
            f"自{since_zh}起，美国财政部已向现金账户补充{mag_str} — "
            "这部分资金从金融体系中吸收（短期内为温和阻力）。"
        )
    if qe_adj:
        en += " Quarter-end seasonal pattern may be a contributing factor."
        zh += " 季末季节性规律可能是促成因素之一。"
    return en, zh


def _headline_summary(
    state: str,
    quality_label: str | None = None,
    overlay: str | None = None,
    *,
    mechanical: bool | None = None,
    rrp_exhausted: bool | None = None,
    stress_confirming: bool | None = None,
) -> str:
    """One plain sentence, flag-accurate and quality-caveated. No naked probabilities.

    RRP exhaustion is a forward hazard caveat (appended when rrp_exhausted=True),
    never a present-stress assertion. Summaries reflect what the engine has
    already resolved — no OR-disjunctions printed when the branch is known.
    """
    _rrp_caveat = (
        " RRP buffer is empty — the next liquidity drain hits bank reserves directly."
        if rrp_exhausted is True else ""
    )

    if state == "benign_liquidity_tailwind":
        return (
            "Fed balance-sheet expansion is the primary driver of improving net "
            "liquidity; conditions may support existing buy setups (quality "
            "caveat: context-tier only, cycle-ladder 21d odds basis)."
            + _rrp_caveat
        )
    if state == "mechanical_liquidity_tailwind":
        base = (
            "Net liquidity is expanding on Treasury/RRP plumbing (e.g. the Treasury "
            "spending down its cash account), not Fed asset growth — a real but "
            "transient tailwind."
        )
        if stress_confirming is False:
            base += " Credit and funding stress gauges are not confirming stress."
        return base + _rrp_caveat
    if state == "stress_liquidity_expansion":
        if stress_confirming:
            return (
                "Net liquidity is technically expanding but credit/funding stress "
                "gauges are confirming stress — expansion quality is poor; treat "
                "with caution, not as a clean tailwind." + _rrp_caveat
            )
        # fed_share unknown → conservative path
        return (
            "Net liquidity is expanding but its composition cannot be attributed — "
            "treated conservatively, not as a clean tailwind." + _rrp_caveat
        )
    if state == "neutral_with_buffer":
        return (
            "Net liquidity is broadly neutral with RRP buffer intact; no "
            "directional signal for buy setups at this time."
        )
    if state == "neutral_hollow":
        return (
            "Net liquidity is neutral but RRP exhausted or composition is "
            "mechanical — buffer is hollow; net-neutral read with limited "
            "downside cushion." + _rrp_caveat
        )
    if state == "orderly_drain":
        return (
            "Net liquidity is contracting in an orderly manner; conditions "
            "may steer toward headwind for buy setups (existing engine limits apply)."
        )
    if state == "data_degraded":
        return (
            "Liquidity data is degraded or source is unavailable; "
            "plumbing context is not reliable for this cycle."
        )
    return "Liquidity plumbing context unavailable."


# ---------------------------------------------------------------------------
# Pure compute — takes already-loaded frames/dicts
# ---------------------------------------------------------------------------

def compute(
    regime_latest: dict,
    netliq_frame: pd.DataFrame | None,
    treasury_frames: dict,
    auction_snapshot: pd.DataFrame | None,
    config: dict | None = None,
    funding_frames: dict | None = None,
    reserves_frame: pd.DataFrame | None = None,
    swap_frames: dict | None = None,
) -> dict:
    """Pure compute — derives the full lobe payload from pre-loaded inputs.

    Parameters
    ----------
    regime_latest:
        Parsed data/regime/latest.json (may be empty dict if missing).
    netliq_frame:
        DataFrame from data/macro/fed_net_liquidity.parquet (may be None).
        Expected columns: date, netliq_bn, walcl_bn, rrp_bn, tga_bn,
        netliq_pctile_expanding. Derives 20d and 65d diffs from netliq_bn tail.
    treasury_frames:
        Dict with keys "net_issuance" and/or "tga", each a DataFrame or None.
    auction_snapshot:
        DataFrame from data/treasury_auctions/auctions.parquet (may be None).
    config:
        Optional config overrides (currently unused).
    funding_frames:
        Optional dict of single-column rate frames (Phase 3 spreads), keys:
        "effr" (data/nyfed/effr.parquet), "iorb" (data/fred/IORB.parquet),
        "sofr" (data/fred/SOFR.parquet),
        "sofr_p99" (data/ofr/FNYR-SOFR_99Pctl-A.parquet). Any may be None —
        the affected spread nulls out with a gaps[] entry.
    reserves_frame:
        Optional DataFrame from data/fred/WRESBAL.parquet (H.4.1 reserve
        balances, $bn weekly). None → fed.reserve_balances_bn stays null
        with a gaps[] entry.
    swap_frames:
        Optional dict for Phase-5 swap-line inputs (IRD-W1), keys:
        "swap_lines_tot" (data/fred/SWPT.parquet, $M weekly),
        "fed_facility_loans" (data/fred/WLCFLL.parquet, $M weekly).
        None or absent keys → foreign_dollar.swap_lines_bn null with a gaps[] entry.

    Returns
    -------
    Unstamped dict matching the contract schema exactly. Always valid JSON-able.
    """
    gaps: list[str] = []

    # ------------------------------------------------------------------
    # 0. Normalize regime_latest — must be a dict; None/non-dict → empty
    # ------------------------------------------------------------------
    if not isinstance(regime_latest, dict):
        if regime_latest is not None:
            log.warning(
                "liquidity_plumbing.compute: regime_latest is %s, expected dict — "
                "treating as missing",
                type(regime_latest).__name__,
            )
        regime_latest = {}

    # Normalize treasury_frames — must be a dict; None → empty dict
    if not isinstance(treasury_frames, dict):
        treasury_frames = {}

    # ------------------------------------------------------------------
    # 1. Extract regime sub-keys (fail-open)
    # ------------------------------------------------------------------
    lq: dict = regime_latest.get("liquidity_quality") or {}
    overlay_raw = regime_latest.get("liquidity_overlay")
    # liquidity_overlay is a plain string in latest.json
    overlay: str = overlay_raw if isinstance(overlay_raw, str) else "unknown"
    fed_stance: dict = regime_latest.get("fed_stance") or {}
    conditions: dict = regime_latest.get("conditions") or {}

    if not lq:
        gaps.append("liquidity_quality missing from regime/latest.json")
    if not fed_stance:
        gaps.append("fed_stance missing from regime/latest.json")

    # ------------------------------------------------------------------
    # 2. Quality block (from regime liquidity_quality)
    # ------------------------------------------------------------------
    quality_label: str | None = lq.get("label")
    quality_fed_share: float | None = (lq.get("composition") or {}).get("fed_share")
    quality_mechanical: bool | None = (lq.get("composition") or {}).get("mechanical")
    quality_rrp_exhausted: bool | None = lq.get("rrp_exhausted")
    # stress_overlay may be a dict (real data: has "confirming_stress" key) or
    # a plain bool (synthetic test fixtures pass stress_overlay=True/False directly).
    _so = lq.get("stress_overlay")
    if isinstance(_so, dict):
        quality_stress_confirming: bool | None = _so.get("confirming_stress")
    elif isinstance(_so, bool):
        quality_stress_confirming = _so
    else:
        quality_stress_confirming = None
    regime_degraded: bool = bool(lq.get("degraded", False)) if lq else True
    lq_asof: str | None = lq.get("asof")

    # Carry the regime stress overlay through instead of dropping it (the
    # engine/regime.liquidity_quality co-check: HY-OAS level/z + NFCI trend).
    stress_overlay_out: dict[str, Any] = {
        "hy_oas_pct": None,
        "hy_oas_z": None,
        "nfci": None,
        "nfci_trend": None,
        "confirming_stress": quality_stress_confirming,
    }
    if isinstance(_so, dict):
        for k in ("hy_oas_pct", "hy_oas_z", "nfci", "nfci_trend"):
            stress_overlay_out[k] = _so.get(k)

    quality_block: dict[str, Any] = {
        "label": quality_label,
        "fed_share": quality_fed_share,
        "mechanical": quality_mechanical,
        "stress_confirming": quality_stress_confirming,
        "stress_overlay": stress_overlay_out,
        "walcl_stale_days": lq.get("walcl_stale_days") if lq else None,
    }

    # ------------------------------------------------------------------
    # 3. Quantity block (from netliq_frame daily parquet)
    # ------------------------------------------------------------------
    netliq_bn: float | None = None
    netliq_chg_20d_bn: float | None = None
    netliq_chg_65d_bn: float | None = None
    netliq_pctile_expanding: float | None = None
    frame_asof: str | None = None
    frame_degraded = False

    if netliq_frame is None or netliq_frame.empty:
        gaps.append(
            "data/macro/fed_net_liquidity.parquet missing or empty — "
            "quantity levels/changes unavailable"
        )
        frame_degraded = True
    else:
        try:
            # date column is a regular column (reset_index style from build_netliq_daily)
            df = netliq_frame.copy()
            if "date" in df.columns:
                df = df.set_index("date")
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()

            nl_series: pd.Series = df["netliq_bn"].dropna()
            if nl_series.empty:
                gaps.append("netliq_bn column is all-null in fed_net_liquidity.parquet")
                frame_degraded = True
            else:
                netliq_bn = float(round(nl_series.iloc[-1], 3))
                frame_asof = str(nl_series.index[-1].date())

                # 20d and 65d diffs from the netliq_bn tail
                if len(nl_series) > _D20_ROWS:
                    v = nl_series.iloc[-1] - nl_series.iloc[-_D20_ROWS - 1]
                    netliq_chg_20d_bn = float(round(v, 3))
                else:
                    gaps.append(
                        f"netliq_bn has only {len(nl_series)} rows — 20d diff unavailable"
                    )

                if len(nl_series) > _D65_ROWS:
                    v = nl_series.iloc[-1] - nl_series.iloc[-_D65_ROWS - 1]
                    netliq_chg_65d_bn = float(round(v, 3))
                else:
                    gaps.append(
                        f"netliq_bn has only {len(nl_series)} rows — 65d diff unavailable"
                    )

                if "netliq_pctile_expanding" in df.columns:
                    pct_series = df["netliq_pctile_expanding"].dropna()
                    if not pct_series.empty:
                        netliq_pctile_expanding = float(round(pct_series.iloc[-1], 6))
                    else:
                        gaps.append("netliq_pctile_expanding is all-null")
                else:
                    gaps.append("netliq_pctile_expanding column absent from parquet")
        except Exception as exc:  # noqa: BLE001
            log.warning("liquidity_plumbing: error reading netliq_frame — %s", exc)
            gaps.append(f"netliq_frame read error: {exc}")
            frame_degraded = True

    quantity_block: dict[str, Any] = {
        "netliq_bn": netliq_bn,
        "netliq_chg_20d_bn": netliq_chg_20d_bn,
        "netliq_chg_65d_bn": netliq_chg_65d_bn,
        "netliq_pctile_expanding": netliq_pctile_expanding,
        "overlay": overlay,
    }

    # ------------------------------------------------------------------
    # 4. Fed block (WALCL from netliq_frame + regime fed_stance)
    # ------------------------------------------------------------------
    assets_bn: float | None = None
    assets_chg_20d_bn: float | None = None
    walcl_stale_days: int | None = lq.get("walcl_stale_days") if lq else None
    fed_asof: str | None = frame_asof  # WALCL asof == netliq_frame asof

    if netliq_frame is not None and not netliq_frame.empty and not frame_degraded:
        try:
            df_w = netliq_frame.copy()
            if "date" in df_w.columns:
                df_w = df_w.set_index("date")
            df_w.index = pd.to_datetime(df_w.index)
            df_w = df_w.sort_index()

            walcl_series = df_w["walcl_bn"].dropna()
            if not walcl_series.empty:
                assets_bn = float(round(walcl_series.iloc[-1], 3))
                if len(walcl_series) > _D20_ROWS:
                    v = walcl_series.iloc[-1] - walcl_series.iloc[-_D20_ROWS - 1]
                    assets_chg_20d_bn = float(round(v, 3))
        except Exception as exc:  # noqa: BLE001
            log.warning("liquidity_plumbing: WALCL extraction error — %s", exc)
            gaps.append(f"WALCL extraction error: {exc}")

    policy_stance: str | None = fed_stance.get("stance")
    administered_rate_posture: str | None = fed_stance.get("guidance")

    # Reserve balances (WRESBAL, $bn weekly). Fail-open: the parquet only
    # exists once the FRED collector has run with WRESBAL in its series list.
    reserve_balances_bn: float | None = None
    reserves_series_bn = _to_series(reserves_frame)
    _reserves_loaded: bool = False
    if reserves_series_bn is None:
        gaps.append(
            "data/fred/WRESBAL.parquet missing or empty — reserve_balances_bn "
            "unavailable until the next FRED collect"
        )
    else:
        # WRESBAL is published in $bn; guard against a millions-denominated
        # store (WALCL is stored in millions) — reserves have never exceeded
        # $50tn, so >50,000 can only be millions.
        if float(reserves_series_bn.iloc[-1]) > 50_000:
            reserves_series_bn = reserves_series_bn / 1000.0
        reserve_balances_bn = float(round(reserves_series_bn.iloc[-1], 3))
        _reserves_loaded = True

    fed_block: dict[str, Any] = {
        "assets_bn": assets_bn,
        "assets_chg_20d_bn": assets_chg_20d_bn,
        "reserve_balances_bn": reserve_balances_bn,
        "walcl_stale_days": walcl_stale_days,
        "policy_stance": policy_stance,
        "administered_rate_posture": administered_rate_posture,
        "asof": fed_asof,
    }

    # ------------------------------------------------------------------
    # 5. RRP block (from netliq_frame + regime quality)
    # ------------------------------------------------------------------
    rrp_bn_val: float | None = None
    rrp_chg_20d_bn: float | None = None

    if netliq_frame is not None and not netliq_frame.empty and not frame_degraded:
        try:
            df_r = netliq_frame.copy()
            if "date" in df_r.columns:
                df_r = df_r.set_index("date")
            df_r.index = pd.to_datetime(df_r.index)
            df_r = df_r.sort_index()

            rrp_series = df_r["rrp_bn"].dropna()
            if not rrp_series.empty:
                rrp_bn_val = float(round(rrp_series.iloc[-1], 3))
                if len(rrp_series) > _D20_ROWS:
                    v = rrp_series.iloc[-1] - rrp_series.iloc[-_D20_ROWS - 1]
                    rrp_chg_20d_bn = float(round(v, 3))
        except Exception as exc:  # noqa: BLE001
            log.warning("liquidity_plumbing: RRP extraction error — %s", exc)
            gaps.append(f"RRP extraction error: {exc}")

    # Buffer state from regime (authoritative) or from rrp_bn_val
    rrp_exhausted_flag = bool(quality_rrp_exhausted) if quality_rrp_exhausted is not None else None
    if rrp_exhausted_flag is True:
        buffer_state = "exhausted"
    elif rrp_bn_val is not None:
        # Heuristic fallback when regime quality is absent
        buffer_state = "exhausted" if rrp_bn_val < 100 else "adequate"
    else:
        buffer_state = "unknown"

    rrp_block: dict[str, Any] = {
        "rrp_bn": rrp_bn_val,
        "rrp_chg_20d_bn": rrp_chg_20d_bn,
        "buffer_state": buffer_state,
    }

    # ------------------------------------------------------------------
    # 6. Treasury block
    # ------------------------------------------------------------------
    tga_bn_val: float | None = None
    tga_chg_20d_bn: float | None = None
    net_issuance_20d_bn: float | None = None
    treasury_asof: str | None = None
    _tga_series_bn: pd.Series | None = None  # kept for impulse detector

    tga_frame: pd.DataFrame | None = treasury_frames.get("tga")
    net_issuance_frame: pd.DataFrame | None = treasury_frames.get("net_issuance")

    if tga_frame is None or tga_frame.empty:
        gaps.append("data/treasury/tga.parquet missing or empty — TGA levels unavailable")
    else:
        try:
            tga_df = tga_frame.copy()
            tga_df.index = pd.to_datetime(tga_df.index)
            tga_df = tga_df.sort_index()
            # Column is tga_mn (millions); convert to billions
            col = tga_df.columns[0]
            tga_series = (tga_df[col] / 1000.0).dropna()
            if not tga_series.empty:
                _tga_series_bn = tga_series  # save for impulse detector
                tga_bn_val = float(round(tga_series.iloc[-1], 3))
                treasury_asof = str(tga_series.index[-1].date())
                if len(tga_series) > _D20_ROWS:
                    v = tga_series.iloc[-1] - tga_series.iloc[-_D20_ROWS - 1]
                    tga_chg_20d_bn = float(round(v, 3))
                else:
                    gaps.append(
                        f"tga.parquet has only {len(tga_series)} rows — 20d diff unavailable"
                    )
        except Exception as exc:  # noqa: BLE001
            log.warning("liquidity_plumbing: TGA frame error — %s", exc)
            gaps.append(f"tga.parquet read error: {exc}")

    if net_issuance_frame is None or net_issuance_frame.empty:
        gaps.append(
            "data/treasury/net_issuance.parquet missing or empty — "
            "net issuance 20d unavailable"
        )
    else:
        try:
            ni_df = net_issuance_frame.copy()
            ni_df.index = pd.to_datetime(ni_df.index)
            ni_df = ni_df.sort_index()
            # Column is net_issuance_mn (millions); convert to billions
            col = ni_df.columns[0]
            ni_series = (ni_df[col] / 1000.0).dropna()
            if not ni_series.empty:
                # Sum of last 20 observations (rolling net issuance)
                tail20 = ni_series.tail(_D20_ROWS)
                net_issuance_20d_bn = float(round(tail20.sum(), 3))
                if treasury_asof is None:
                    treasury_asof = str(ni_series.index[-1].date())
        except Exception as exc:  # noqa: BLE001
            log.warning("liquidity_plumbing: net_issuance frame error — %s", exc)
            gaps.append(f"net_issuance.parquet read error: {exc}")

    # RLT-R4: TGA impulse detector — episode naming, never quality upgrade
    tga_impulse_block = _derive_tga_impulse(_tga_series_bn)
    if _tga_series_bn is None:
        gaps.append(
            "tga_impulse: TGA series unavailable — impulse detector inactive"
        )

    treasury_block: dict[str, Any] = {
        "tga_bn": tga_bn_val,
        "tga_chg_20d_bn": tga_chg_20d_bn,
        "net_issuance_20d_bn": net_issuance_20d_bn,
        "expected_tga_pressure": "unknown_until_financing_estimates_parser",
        "coupon_supply_pressure": "context_only",
        "tga_impulse": tga_impulse_block,
        "asof": treasury_asof,
    }

    # ------------------------------------------------------------------
    # 7. Funding block (Phase 3 — IORB spreads integrated; SRF/DW pending)
    # ------------------------------------------------------------------
    ff = funding_frames if isinstance(funding_frames, dict) else {}
    rate_effr = _to_series(ff.get("effr"))
    rate_iorb = _to_series(ff.get("iorb"))
    rate_sofr = _to_series(ff.get("sofr"))
    rate_sofr_p99 = _to_series(ff.get("sofr_p99"))

    if rate_iorb is None:
        gaps.append(
            "data/fred/IORB.parquet missing or empty — all IORB funding "
            "spreads unavailable"
        )
    else:
        _missing_rates = {
            "effr": (rate_effr, "data/nyfed/effr.parquet"),
            "sofr": (rate_sofr, "data/fred/SOFR.parquet"),
            "sofr_p99": (rate_sofr_p99, "data/ofr/FNYR-SOFR_99Pctl-A.parquet"),
        }
        for name, (series, path_str) in _missing_rates.items():
            if series is None:
                gaps.append(
                    f"{path_str} missing or empty — {name}-minus-IORB spread unavailable"
                )

    effr_sp = _spread_bp(rate_effr, rate_iorb)
    sofr_sp = _spread_bp(rate_sofr, rate_iorb)
    sofr_p99_sp = _spread_bp(rate_sofr_p99, rate_iorb)

    effr_bp, effr_d20_bp, effr_pctile = _level_d20_pctile(effr_sp)
    sofr_bp, sofr_d20_bp, sofr_pctile = _level_d20_pctile(sofr_sp)
    sofr_p99_bp, sofr_p99_d20_bp, sofr_p99_pctile = _level_d20_pctile(sofr_p99_sp)

    funding_asof: str | None = None
    _spread_last_dates = [
        sp.index[-1] for sp in (effr_sp, sofr_sp, sofr_p99_sp) if sp is not None
    ]
    if _spread_last_dates:
        funding_asof = str(max(_spread_last_dates).date())

    # SRF take-up + discount-window primary credit need a NEW collection —
    # deliberately not added here; stay null with an honest gap.
    gaps.append(
        "SRF take-up and discount-window primary credit not collected yet — "
        "srf_takeup_bn / discount_window_primary_credit_bn stay null"
    )

    funding_block: dict[str, Any] = {
        "effr_minus_iorb_bp": effr_bp,
        "effr_minus_iorb_d20_bp": effr_d20_bp,
        "effr_minus_iorb_pctile": effr_pctile,
        "sofr_minus_iorb_bp": sofr_bp,
        "sofr_minus_iorb_d20_bp": sofr_d20_bp,
        "sofr_minus_iorb_pctile": sofr_pctile,
        "sofr_99pctl_minus_iorb_bp": sofr_p99_bp,
        "sofr_99pctl_minus_iorb_d20_bp": sofr_p99_d20_bp,
        "sofr_99pctl_minus_iorb_pctile": sofr_p99_pctile,
        "srf_takeup_bn": None,
        "discount_window_primary_credit_bn": None,
        "reserve_scarcity_state": _derive_reserve_scarcity_state(
            effr_bp, sofr_bp, effr_d20_bp, sofr_d20_bp
        ),
        "asof": funding_asof,
    }

    # ------------------------------------------------------------------
    # 7b. Components block — per-component display stats + netliq sparkline
    # ------------------------------------------------------------------
    components_block: dict[str, Any] = {
        "walcl": _component_stats(None),
        "rrp": _component_stats(None),
        "tga": _component_stats(None),
        "netliq_sparkline_90d": [],
    }
    if netliq_frame is not None and not netliq_frame.empty and not frame_degraded:
        try:
            df_c = netliq_frame.copy()
            if "date" in df_c.columns:
                df_c = df_c.set_index("date")
            df_c.index = pd.to_datetime(df_c.index)
            df_c = df_c.sort_index()

            for comp, col in (("walcl", "walcl_bn"), ("rrp", "rrp_bn"), ("tga", "tga_bn")):
                if col in df_c.columns:
                    components_block[comp] = _component_stats(df_c[col].dropna())
                else:
                    gaps.append(f"{col} column absent from fed_net_liquidity.parquet")

            spark_series = df_c["netliq_bn"].dropna() if "netliq_bn" in df_c.columns else None
            if spark_series is not None and not spark_series.empty:
                cutoff = spark_series.index[-1] - pd.Timedelta(days=_SPARKLINE_CAL_DAYS)
                tail = spark_series[spark_series.index >= cutoff]
                components_block["netliq_sparkline_90d"] = [
                    {"d": str(ix.date()), "v": float(round(v, 1))}
                    for ix, v in tail.items()
                ]
        except Exception as exc:  # noqa: BLE001
            log.warning("liquidity_plumbing: components extraction error — %s", exc)
            gaps.append(f"components extraction error: {exc}")
    else:
        gaps.append("components block unavailable — fed_net_liquidity.parquet missing/degraded")

    if reserves_series_bn is not None:
        components_block["reserves"] = _component_stats(reserves_series_bn)

    # ------------------------------------------------------------------
    # 8. Foreign dollar block (Phase 5 — swap lines filled from SWPT/WLCFLL)
    # ------------------------------------------------------------------
    # IRD-R5: swap lines are CONFIRMATION tier (grade severity after price signals fire;
    # no alert keys off them). FIMA repo has no free per-facility breakout —
    # no free per-facility breakout; aggregate rides H.4.1 repo line.
    _swap_frames = swap_frames if isinstance(swap_frames, dict) else {}
    swap_lines_bn: float | None = None
    facility_loans_bn: float | None = None
    swap_asof: str | None = None

    swap_raw = _to_series(_swap_frames.get("swap_lines_tot"))
    if swap_raw is None:
        gaps.append(
            "data/fred/SWPT.parquet missing or empty — swap_lines_bn unavailable "
            "(IRD-R5: confirmation tier; collect with FredAdapter once)"
        )
    else:
        # SWPT is published in $M (millions); convert to $bn
        latest_val = float(swap_raw.iloc[-1])
        swap_lines_bn = float(round(latest_val / 1000.0, 3)) if latest_val > 0 else 0.0
        swap_asof = str(swap_raw.index[-1].date())

    facility_raw = _to_series(_swap_frames.get("fed_facility_loans"))
    if facility_raw is not None:
        latest_fac = float(facility_raw.iloc[-1])
        facility_loans_bn = float(round(latest_fac / 1000.0, 3)) if latest_fac > 0 else 0.0
        if swap_asof is None:
            swap_asof = str(facility_raw.index[-1].date())
    else:
        gaps.append(
            "data/fred/WLCFLL.parquet missing or empty — facility_loans_bn unavailable"
        )

    # Determine state label. A standing sub-$1bn balance is operational residue
    # (small routine FX ops), not a draw — calling it "low_draw" would cry wolf
    # on a confirmation-tier gauge (IRD-R5), so the quiescent floor is 1bn.
    if swap_lines_bn is not None:
        if swap_lines_bn > 100:
            _swap_state = "elevated_draw"
        elif swap_lines_bn > 1:
            _swap_state = "low_draw"
        else:
            _swap_state = "quiescent"
    else:
        _swap_state = "data_unavailable"

    foreign_dollar_block: dict[str, Any] = {
        "swap_lines_bn": swap_lines_bn,
        "facility_loans_bn": facility_loans_bn,
        "fima_repo_bn": None,  # no free per-facility breakout; aggregate rides H.4.1 repo line
        "state": _swap_state,
        "note": (
            "IRD-R5: swap-line levels are confirmation tier — they grade severity "
            "after price signals fire, never trigger alerts. "
            "FIMA repo: no free per-facility breakout; aggregate rides H.4.1 repo line."
        ),
        "asof": swap_asof,
    }

    # ------------------------------------------------------------------
    # 9. Entry-effect block (cycle-ladder 21d basis only — no new signal)
    # ------------------------------------------------------------------
    # Determine direction and quality from headline state
    headline_state = _derive_headline_state(
        quality_label=quality_label,
        rrp_exhausted=quality_rrp_exhausted,
        stress_confirming=quality_stress_confirming,
        fed_share=quality_fed_share,
        overlay=overlay,
        degraded=regime_degraded or frame_degraded,
    )

    if headline_state in ("benign_liquidity_tailwind", "mechanical_liquidity_tailwind"):
        entry_direction = "tailwind"
        entry_quality = (
            "benign" if headline_state == "benign_liquidity_tailwind"
            else "low_quality_tailwind"
        )
    elif headline_state in ("stress_liquidity_expansion",):
        entry_direction = "tailwind"
        entry_quality = "low_quality_tailwind"
    elif headline_state in ("orderly_drain",):
        entry_direction = "headwind"
        entry_quality = "contraction"
    elif headline_state in ("neutral_with_buffer", "neutral_hollow"):
        entry_direction = "neutral"
        entry_quality = "neutral"
    else:
        entry_direction = "unknown"
        entry_quality = "unknown"

    entry_effect_block: dict[str, Any] = {
        "direction": entry_direction,
        "quality": entry_quality,
        "measured_basis": "cycle_ladder_21d_odds",
        "use": "support existing buy setup, never originate one",
    }

    # ------------------------------------------------------------------
    # 10. Top-level asof: prefer frame_asof, fall back to lq_asof or today
    # ------------------------------------------------------------------
    asof_str: str = (
        frame_asof
        or lq_asof
        or str(date.today())
    )

    # ------------------------------------------------------------------
    # 11. Degraded flag
    # ------------------------------------------------------------------
    degraded_flag = bool(
        regime_degraded
        or frame_degraded
        or quality_label is None
        or quality_label == "unknown"
    )

    # ------------------------------------------------------------------
    # 12. Assemble headline
    # ------------------------------------------------------------------
    headline_block: dict[str, Any] = {
        "state": headline_state,
        "summary": _headline_summary(
            headline_state,
            quality_label,
            overlay,
            mechanical=quality_mechanical,
            rrp_exhausted=quality_rrp_exhausted,
            stress_confirming=quality_stress_confirming,
        ),
    }

    # ------------------------------------------------------------------
    # 13. Assemble full payload (UNSTAMPED)
    # ------------------------------------------------------------------
    # Build dynamic phase_status: p3_reserve_balances reflects actual load state
    _phase_status: dict[str, Any] = {
        **_PHASE_STATUS_BASE,
        "p3_reserve_balances": (
            "integrated" if _reserves_loaded
            else "fail_open_until_wresbal_collected"
        ),
    }

    payload: dict[str, Any] = {
        "schema": _SCHEMA,
        "asof": asof_str,
        "phase_status": _phase_status,
        "authority": _AUTHORITY,
        "headline": headline_block,
        "fed": fed_block,
        "treasury": treasury_block,
        "rrp": rrp_block,
        "quantity": quantity_block,
        "quality": quality_block,
        "funding": funding_block,
        "components": components_block,
        "foreign_dollar": foreign_dollar_block,
        "entry_effect": entry_effect_block,
        "gaps": gaps,
        "degraded": degraded_flag,
    }

    return payload


# ---------------------------------------------------------------------------
# Degraded fallback payload — the ONE all-null shape (snapshot + CLI share it)
# ---------------------------------------------------------------------------

def degraded_payload(gaps: list[str], summary: str = "Build error — see gaps.") -> dict:
    """Minimal valid all-null payload for absolute fail-open paths."""
    return {
        "schema": _SCHEMA,
        "asof": str(date.today()),
        "phase_status": _PHASE_STATUS,
        "authority": _AUTHORITY,
        "headline": {"state": "data_degraded", "summary": summary},
        "fed": {
            "assets_bn": None, "assets_chg_20d_bn": None,
            "reserve_balances_bn": None, "walcl_stale_days": None,
            "policy_stance": None, "administered_rate_posture": None,
            "asof": None,
        },
        "treasury": {
            "tga_bn": None, "tga_chg_20d_bn": None,
            "net_issuance_20d_bn": None,
            "expected_tga_pressure": "unknown_until_financing_estimates_parser",
            "coupon_supply_pressure": "context_only",
            "tga_impulse": {
                "active": False, "direction": None, "magnitude_bn": None,
                "days": None, "since": None, "quarter_end_adjacent": False,
                "summary_en": "No TGA impulse detected.", "summary_zh": "未检测到TGA冲量。",
            },
            "asof": None,
        },
        "rrp": {"rrp_bn": None, "rrp_chg_20d_bn": None, "buffer_state": "unknown"},
        "quantity": {
            "netliq_bn": None, "netliq_chg_20d_bn": None,
            "netliq_chg_65d_bn": None, "netliq_pctile_expanding": None,
            "overlay": "unknown",
        },
        "quality": {
            "label": None, "fed_share": None,
            "mechanical": None, "stress_confirming": None,
            "stress_overlay": {
                "hy_oas_pct": None, "hy_oas_z": None, "nfci": None,
                "nfci_trend": None, "confirming_stress": None,
            },
            "walcl_stale_days": None,
        },
        "funding": {
            "effr_minus_iorb_bp": None,
            "effr_minus_iorb_d20_bp": None,
            "effr_minus_iorb_pctile": None,
            "sofr_minus_iorb_bp": None,
            "sofr_minus_iorb_d20_bp": None,
            "sofr_minus_iorb_pctile": None,
            "sofr_99pctl_minus_iorb_bp": None,
            "sofr_99pctl_minus_iorb_d20_bp": None,
            "sofr_99pctl_minus_iorb_pctile": None,
            "srf_takeup_bn": None,
            "discount_window_primary_credit_bn": None,
            "reserve_scarcity_state": "unknown",
            "asof": None,
        },
        "components": {
            "walcl": _component_stats(None),
            "rrp": _component_stats(None),
            "tga": _component_stats(None),
            "netliq_sparkline_90d": [],
        },
        "foreign_dollar": {
            "swap_lines_bn": None, "facility_loans_bn": None, "fima_repo_bn": None,
            "state": "data_unavailable",
            "note": (
                "IRD-R5: swap-line levels are confirmation tier. "
                "FIMA repo: no free per-facility breakout; aggregate rides H.4.1 repo line."
            ),
            "asof": None,
        },
        "entry_effect": {
            "direction": "unknown", "quality": "unknown",
            "measured_basis": "cycle_ladder_21d_odds",
            "use": "support existing buy setup, never originate one",
        },
        "gaps": list(gaps),
        "degraded": True,
    }


# ---------------------------------------------------------------------------
# Snapshot — reads stores, calls compute, returns UNSTAMPED dict
# ---------------------------------------------------------------------------

def snapshot(root: str | Path | None = None) -> dict:
    """Read all data stores, call compute(), return the UNSTAMPED lobe dict.

    Fail-open: any missing or unreadable source adds a gaps[] entry and nulls
    that block; still returns a valid, JSON-serialisable dict.

    Parameters
    ----------
    root:
        Repo root path. Defaults to two levels above this file
        (engine/neuralweb/ → engine/ → repo root).
    """
    if root is None:
        root = Path(__file__).resolve().parent.parent.parent
    root = Path(root).resolve()

    gaps_pre: list[str] = []

    # 1. regime/latest.json
    regime_path = root / "data" / "regime" / "latest.json"
    regime_latest: dict = {}
    if not regime_path.exists():
        log.warning("liquidity_plumbing.snapshot: regime/latest.json not found at %s", regime_path)
        gaps_pre.append("data/regime/latest.json not found")
    else:
        try:
            regime_latest = json.loads(regime_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("liquidity_plumbing.snapshot: failed to parse latest.json — %s", exc)
            gaps_pre.append(f"data/regime/latest.json parse error: {exc}")

    # 2. fed_net_liquidity.parquet
    netliq_path = root / "data" / "macro" / "fed_net_liquidity.parquet"
    netliq_frame: pd.DataFrame | None = None
    if not netliq_path.exists():
        log.warning("liquidity_plumbing.snapshot: fed_net_liquidity.parquet not found")
        gaps_pre.append("data/macro/fed_net_liquidity.parquet not found")
    else:
        try:
            netliq_frame = pd.read_parquet(netliq_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("liquidity_plumbing.snapshot: failed to read netliq parquet — %s", exc)
            gaps_pre.append(f"data/macro/fed_net_liquidity.parquet read error: {exc}")

    # 3. Treasury frames
    treasury_frames: dict[str, pd.DataFrame | None] = {}

    net_issuance_path = root / "data" / "treasury" / "net_issuance.parquet"
    if not net_issuance_path.exists():
        log.warning("liquidity_plumbing.snapshot: net_issuance.parquet not found")
        gaps_pre.append("data/treasury/net_issuance.parquet not found")
        treasury_frames["net_issuance"] = None
    else:
        try:
            treasury_frames["net_issuance"] = pd.read_parquet(net_issuance_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("liquidity_plumbing.snapshot: failed to read net_issuance — %s", exc)
            gaps_pre.append(f"data/treasury/net_issuance.parquet read error: {exc}")
            treasury_frames["net_issuance"] = None

    tga_path = root / "data" / "treasury" / "tga.parquet"
    if not tga_path.exists():
        log.warning("liquidity_plumbing.snapshot: tga.parquet not found")
        gaps_pre.append("data/treasury/tga.parquet not found")
        treasury_frames["tga"] = None
    else:
        try:
            treasury_frames["tga"] = pd.read_parquet(tga_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("liquidity_plumbing.snapshot: failed to read tga.parquet — %s", exc)
            gaps_pre.append(f"data/treasury/tga.parquet read error: {exc}")
            treasury_frames["tga"] = None

    # 4. Auctions parquet (display-only context)
    auctions_path = root / "data" / "treasury_auctions" / "auctions.parquet"
    auction_snapshot: pd.DataFrame | None = None
    if not auctions_path.exists():
        log.warning("liquidity_plumbing.snapshot: auctions.parquet not found")
        gaps_pre.append("data/treasury_auctions/auctions.parquet not found")
    else:
        try:
            auction_snapshot = pd.read_parquet(auctions_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("liquidity_plumbing.snapshot: failed to read auctions — %s", exc)
            gaps_pre.append(f"data/treasury_auctions/auctions.parquet read error: {exc}")

    # 5. Funding rate stores (Phase 3 spreads). Missing files are logged here
    #    but the gaps[] entries come from compute() — these inputs are context
    #    extras, so their absence must NOT force the whole artifact degraded
    #    the way a missing core source (regime/netliq) does.
    funding_frames: dict[str, pd.DataFrame | None] = {}
    for key, rel in (
        ("effr", ("data", "nyfed", "effr.parquet")),
        ("iorb", ("data", "fred", "IORB.parquet")),
        ("sofr", ("data", "fred", "SOFR.parquet")),
        ("sofr_p99", ("data", "ofr", "FNYR-SOFR_99Pctl-A.parquet")),
    ):
        p = root.joinpath(*rel)
        if not p.exists():
            log.warning("liquidity_plumbing.snapshot: %s not found", p)
            funding_frames[key] = None
            continue
        try:
            funding_frames[key] = pd.read_parquet(p)
        except Exception as exc:  # noqa: BLE001
            log.warning("liquidity_plumbing.snapshot: failed to read %s — %s", p, exc)
            funding_frames[key] = None

    # 6. Reserve balances (WRESBAL — absent until the FRED collector has run
    #    with WRESBAL in its series list; compute() adds the gap)
    reserves_frame: pd.DataFrame | None = None
    wresbal_path = root / "data" / "fred" / "WRESBAL.parquet"
    if not wresbal_path.exists():
        log.warning("liquidity_plumbing.snapshot: WRESBAL.parquet not found (expected until next collect)")
    else:
        try:
            reserves_frame = pd.read_parquet(wresbal_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("liquidity_plumbing.snapshot: failed to read WRESBAL — %s", exc)

    # 6b. Phase-5 swap lines (IRD-W1): SWPT + WLCFLL from FRED adapter.
    #     Fail-open: absent until the FRED collector has run with new series in config.
    swap_frames: dict[str, pd.DataFrame | None] = {}
    for key, fname in (
        ("swap_lines_tot", "SWPT.parquet"),
        ("fed_facility_loans", "WLCFLL.parquet"),
    ):
        p = root / "data" / "fred" / fname
        if not p.exists():
            log.warning("liquidity_plumbing.snapshot: %s not found (absent until next FRED collect)", fname)
            swap_frames[key] = None
        else:
            try:
                swap_frames[key] = pd.read_parquet(p)
            except Exception as exc:  # noqa: BLE001
                log.warning("liquidity_plumbing.snapshot: failed to read %s — %s", fname, exc)
                swap_frames[key] = None

    # 7. Call compute
    try:
        payload = compute(
            regime_latest=regime_latest,
            netliq_frame=netliq_frame,
            treasury_frames=treasury_frames,
            auction_snapshot=auction_snapshot,
            config=None,
            funding_frames=funding_frames,
            reserves_frame=reserves_frame,
            swap_frames=swap_frames,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("liquidity_plumbing.snapshot: compute() raised — %s", exc)
        # Absolute fail-open: return a minimal valid payload
        return degraded_payload(
            gaps_pre + [f"compute() error: {exc}"],
            summary="Compute error — see gaps.",
        )

    # Prepend any pre-compute gaps
    if gaps_pre:
        payload["gaps"] = gaps_pre + payload.get("gaps", [])
    if gaps_pre:
        payload["degraded"] = True

    return payload
