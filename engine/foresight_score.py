"""Foresight investability rubric — Phase 5 of the Thematic Foresight Desk
(research/THEMATIC_FORESIGHT_DESK.md). The desk's single 0-100 number per theme.

Synthesizes the cascade's tiers into a transparent 7-axis investability score. It is NOT a
return forecast and NOT a sized position — it ranks "how much edge + quality is here", with
three honesty rules enforced in code so the number can never lie about what it doesn't know:

  1. TEXT-ONLY CAP — no physical bottleneck read (AWAITING/unknown) => the score is capped at
     50. The desk cannot call a theme high-conviction on demand/revisions alone; a scarce
     physical input is the durability filter.
  2. TIMING IS A GATE, NOT A BOOSTER — a late stage (RE-RATING / GLUT-RISK) caps the score.
     You cannot buy your way to a high score once the revisions have already broadened.
  3. ATTENTION LOWERS THE SCORE — the underpricing axis is INVERSE to attention (via
     earliness), so a theme everyone already owns / is loud about scores LOW on the axis that
     matters most for forward edge.

Axes (weights sum to 1.0): magnitude .15 · acceleration .20 · bottleneck .20 ·
pricing-power .15 · underpricing .15 · purity .08 · timing .07.

WEIGHTS ARE FIXED DEFAULTS; shadow-calibration pending (engine/foresight_grader forward-
grading ledger accrues from W0a; promotion requires BY-FDR significance per §3.2 of
research/FORESIGHT_DESK_UPGRADE_BY_FABLE.md). They are NOT yet tuned via ledgers.

ANTI-LAUNDERING (P1-C): any axis with no live input contributes NOTHING to the weighted
sum — the sum is renormalized over LIVE axes only. n_axes_live is surfaced in score_detail.
The 0.4/0.5 placeholder pattern is eliminated.
"""
from __future__ import annotations

import logging

from lib import config

log = logging.getLogger(__name__)

WEIGHTS = {"magnitude": 0.15, "acceleration": 0.20, "bottleneck": 0.20,
           "pricing_power": 0.15, "underpricing": 0.15, "purity": 0.08, "timing": 0.07}
TEXT_ONLY_CAP = 50.0
FINGERPRINT_CAP = 60.0   # annual XBRL fingerprint: higher than text-only but below FRED uncapped
STAGE_CAP = {"RE-RATING": 60.0, "GLUT-RISK": 40.0, "WATCH": 45.0, "UNKNOWN": 35.0}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _magnitude(r: dict) -> float | None:
    """Per-theme demand magnitude. None when no live input.

    Priority: divergence_share (per-name demand discrimination from W2b demand re-point)
    blended with capex_yoy (shared pool). If only capex_yoy is available and is the
    synthetic identical-for-all value (all themes = 69.0), the axis still returns a value
    but differentiation comes from divergence_share mixing. If neither is available → None.

    Formula: 0.5 * has_capex_link + 0.5 * divergence_share when both available;
    capex-only or divergence-only when one is absent."""
    capex = r.get("capex_yoy")
    div_share = r.get("divergence_share")  # None when < 3 covered members (W2b)

    if capex is None and div_share is None:
        return None

    parts = []
    if capex is not None:
        # has_capex_link: binary flag — is there real customer capex data?
        # clamp so 60% YoY → 1.0 (multi-year wave). Floor at 0.35.
        parts.append(0.5 * _clamp(capex / 60.0, 0.35, 1.0))
    else:
        parts.append(None)

    if div_share is not None:
        # divergence_share ∈ [0, 1]: fraction of members ahead of consensus.
        # Scales to [0.0, 0.5] contribution.
        parts.append(0.5 * float(div_share))
    else:
        parts.append(None)

    live = [p for p in parts if p is not None]
    if not live:
        return None
    # If both present: sum the halves (max ~1.0). If only one: renormalize so it can
    # still reach 1.0 by doubling its contribution.
    if len(live) == 2:
        return round(sum(live), 3)
    else:
        return round(live[0] * 2.0, 3)  # single-half → scale back to [0, 1]


def _acceleration(r: dict) -> float | None:
    """Acceleration signal. None when no live input at all."""
    parts = []
    dband = r.get("demand_band")
    parts.append({"ACCELERATING": 1.0, "STEADY": 0.6, "COOLING": 0.25,
                  "CONTRACTING": 0.1}.get(dband)) if dband else None
    bstate = r.get("broadening_state")
    if bstate:
        parts.append({"RISING": 0.9, "FLAT_LOW": 0.5, "ROLLING": 0.35,
                      "MIXED": 0.45}.get(bstate, 0.5))
    if r.get("bottleneck_regime"):
        parts.append(0.85)
    parts = [p for p in parts if p is not None]
    if not parts:
        return None
    base = sum(parts) / len(parts)
    # T3 guidance tilt is a LEADING acceleration precursor — management raising guidance
    # front-runs the revision wave; a cut decelerates. Applied as a bounded bonus/drag on
    # the context mean (NOT an averaged member, which could let a RAISE LOWER acceleration
    # on an already-hot theme). NEUTRAL / absent never moves the axis.
    guband = r.get("guidance_band")
    base += {"BROAD-RAISE": 0.10, "RAISING": 0.06, "CUTTING": -0.15}.get(guband, 0.0)
    # Leading alt-data confirmers (insider clusters / award accel) — INVERSE-TO-BREADTH and
    # CORRELATION-PENALIZED: a confirmer while revisions are still flat is a pre-revision tell;
    # the same confirmer once breadth is broad is just crowding, so the bonus scales to ~0 as
    # breadth rises and is capped (the channels are partly one 'informed attention' factor).
    n_conf = r.get("n_altdata_leading") or 0
    if n_conf:
        breadth = r.get("revision_breadth") or 0.0
        inv = max(0.0, 1.0 - max(0.0, breadth))
        base += min(0.12, 0.05 * n_conf) * inv
    return round(_clamp(base, 0.0, 1.0), 3)


def _bottleneck(r: dict) -> float | None:
    """None when there is NO physical read (AWAITING or text-only) — triggers the
    text-only cap (TEXT_ONLY_CAP=50).

    Text-only bands (TIGHT (text) / TIGHTENING (text)) return None so the cap always
    binds for unconfirmed language signals — the house rule: text-only capped without a
    physical correlate. Only numeric FRED legs (TIGHT / SOLD_OUT / TIGHTENING / NEUTRAL /
    LOOSE) count as physical confirmation.

    Fingerprint bands (TIGHT (fingerprint) / TIGHTENING (fingerprint)) return a moderate
    value (TIGHT→0.6, TIGHTENING→0.4) so the bottleneck axis is not zero for annual XBRL.
    However physical_confirmed stays False (checked via bottleneck_fingerprint_only in
    score_row), and FINGERPRINT_CAP=60 applies instead of TEXT_ONLY_CAP=50.
    Fingerprint axis values: TIGHT (fingerprint) → 0.6, TIGHTENING (fingerprint) → 0.4.
    """
    band = r.get("bottleneck_band")
    # Text-only bands and AWAITING_DATA are not physical confirmation → None → cap fires
    if r.get("bottleneck_text_only") or band in ("TIGHT (text)", "TIGHTENING (text)"):
        return None
    # Fingerprint-only bands: annual XBRL — real physical data but annual cadence, not real-time.
    # Returns a moderate axis value; physical_confirmed remains False (see score_row).
    if band in ("TIGHT (fingerprint)", "TIGHTENING (fingerprint)"):
        base = {"TIGHT (fingerprint)": 0.6, "TIGHTENING (fingerprint)": 0.4}.get(band, 0.4)
        if r.get("bottleneck_regime"):
            base = min(1.0, base + 0.1)
        return base
    base = {"SOLD_OUT": 1.0, "TIGHT": 0.8, "TIGHTENING": 0.55,
            "NEUTRAL": 0.35, "LOOSE": 0.1}.get(band)
    if base is None:
        return None
    if r.get("bottleneck_regime"):
        base = min(1.0, base + 0.1)
    return base


def _pricing_power(r: dict) -> float | None:
    """Pricing-power axis — real inputs only; None when no input is available.

    Priority order (matches the code below):
    1. PPI YoY trend from bottleneck engine (ppi_yoy_latest, the leg4 physical FRED series).
    2. Tightness from the bottleneck engine (numeric physical read).
    3. Member gross-margin trend from edgar_facts cached artifact (data/edgar/statements.parquet),
       if ≥2 theme members have data. Computed as recent FY vs prior FY median change.
    4. None → axis drops out.

    The former 0.4 hardcoded default is eliminated per the P1-C anti-laundering rule.
    """
    # 1. PPI YoY trend (leg4 FRED series from bottleneck engine)
    ppi = r.get("ppi_yoy_latest")
    if ppi is not None:
        # PPI YoY: normalize around 0; +3% → 0.65, +10% → 1.0, negative → <0.4
        # Scaling: anchor at +3% YoY = moderate pricing power
        return round(_clamp(0.5 + float(ppi) / 20.0, 0.15, 1.0), 3)

    # 2. Tightness (from bottleneck engine numeric legs)
    t = r.get("tightness")
    if t is not None:
        return round(_clamp(0.5 + float(t) / 2.0, 0.15, 1.0), 3)

    # 3. Member gross-margin trend — read from cached edgar statements
    gm_trend = r.get("_gross_margin_trend")  # pre-computed in score_row
    if gm_trend is not None:
        return round(_clamp(0.5 + float(gm_trend) * 5.0, 0.15, 1.0), 3)

    return None


def _underpricing(r: dict) -> float | None:
    """INVERSE to attention — the attention-gap earliness composite (Q3 spec).

    De-circularization (P1-C): underpricing no longer equals 1−0.9·revision_breadth
    (circular: same variable that sets stage + cap). Instead it reads the earliness
    engine's output (a cross-sectional composite of coverage, news, ownership, tape).

    Priority:
    1. earliness from foresight_earliness engine (pre-computed in score_row).
    2. Fallback to revision-level label ONLY (never revision_breadth directly).
    3. None → axis drops out.

    Note: earliness ∈ [0, 1], 1 = least attention (early). Used directly as underpricing.
    """
    # n_legs_live gate (review Bug B iii): a composite carried by a single usable leg
    # must not be consumed at full confidence — below 2 legs, fall through to the
    # coarse revision-level fallback rather than publish a thin "measurement"
    earliness = r.get("_earliness")  # pre-computed in score_row
    n_legs = r.get("_earliness_n_legs")
    if earliness is not None and (n_legs is None or n_legs >= 2):
        return round(float(_clamp(float(earliness), 0.0, 1.0)), 3)

    # Fallback: revision level label (coarse, but different from breadth float)
    lvl = r.get("revision_level")
    if lvl is not None:
        return {"FLAT_LOW": 0.80, "POSITIVE": 0.35, "NEGATIVE": 0.55}.get(lvl)

    return None


def _purity(r: dict) -> float | None:
    """Demand purity (direct / lagged / indirect supply chain). None when unknown."""
    v = {"direct": 0.9, "lagged": 0.6, "indirect": 0.45}.get(r.get("demand_strength"))
    return v  # already None if key absent


def _timing(r: dict) -> float | None:
    """Timing axis — always derivable from stage (UNKNOWN → 0.3). Never None."""
    if r.get("entry_ready"):
        return 1.0
    return {"PRECIPICE": 0.9, "BROADENING": 0.7, "RE-RATING": 0.35,
            "GLUT-RISK": 0.1, "WATCH": 0.4, "UNKNOWN": 0.3}.get(r.get("stage"), 0.4)


# ---------------------------------------------------------------------------
# Gross-margin trend pre-computation (for _pricing_power fallback)
# ---------------------------------------------------------------------------

_EDGAR_CACHE: dict = {}   # module-level cache so we only read parquet once per process


def _gross_margin_trend(members: list[str]) -> float | None:
    """Median YoY gross-margin trend across theme members from edgar/statements.parquet.
    Returns None when < 2 members have data or the parquet is absent.
    Positive = improving margins; negative = compression."""
    global _EDGAR_CACHE  # noqa: PLW0603
    if not members:
        return None
    try:
        if "df" not in _EDGAR_CACHE:
            p = config.data_dir() / "edgar" / "statements.parquet"
            if not p.exists():
                _EDGAR_CACHE["df"] = None
            else:
                import pandas as pd
                df = pd.read_parquet(p)
                _EDGAR_CACHE["df"] = df
        df = _EDGAR_CACHE.get("df")
        if df is None or df.empty:
            return None
        import pandas as pd
        sub = df[df["ticker"].isin(members)]
        if sub.empty:
            return None
        # compute gross margin % per (ticker, FY)
        sub = sub.copy()
        mask = (sub["revenue"].notna()) & (sub["revenue"] != 0)
        sub = sub[mask]
        if sub.empty:
            return None
        if "gross_profit" in sub.columns:
            sub["gm_pct"] = sub["gross_profit"] / sub["revenue"]
        elif "cogs" in sub.columns:
            sub["gm_pct"] = (sub["revenue"] - sub["cogs"]) / sub["revenue"]
        else:
            return None
        sub = sub.dropna(subset=["gm_pct"])
        if sub.empty:
            return None
        # per-ticker YoY change in gm_pct (most recent FY vs prior FY)
        trends = []
        for tkr, grp in sub.groupby("ticker"):
            grp = grp.sort_values("fy")
            if len(grp) < 2:
                continue
            gm_recent = float(grp["gm_pct"].iloc[-1])
            gm_prior = float(grp["gm_pct"].iloc[-2])
            trends.append(gm_recent - gm_prior)
        if len(trends) < 2:
            return None
        import numpy as np
        return round(float(np.median(trends)), 4)
    except Exception as e:  # noqa: BLE001
        log.debug("gross_margin_trend failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Earliness lookup (pre-computed once per cascade run)
# ---------------------------------------------------------------------------

_EARLINESS_CACHE: dict | None = None


def _get_earliness(theme: str) -> tuple[float | None, int | None]:
    """Retrieve (earliness, n_legs_live) for a theme from the earliness engine.
    Loads once per process run; None-safe (engine absent or failed → (None, None))."""
    global _EARLINESS_CACHE  # noqa: PLW0603
    if _EARLINESS_CACHE is None:
        try:
            from engine.foresight_earliness import compute_foresight_earliness
            result = compute_foresight_earliness(write_log=False)
            _EARLINESS_CACHE = (result or {}).get("themes") or {}
        except Exception as e:  # noqa: BLE001
            log.debug("foresight_earliness load failed: %s", e)
            _EARLINESS_CACHE = {}
    t = _EARLINESS_CACHE.get(theme) or {}
    return t.get("earliness"), t.get("n_legs_live")


def score_row(r: dict, *, theme_members: list[str] | None = None) -> dict:
    """0-100 investability score + transparent axis breakdown + the caps that bound it.

    P1-C anti-laundering: axes with no live input are excluded from the weighted sum;
    the sum is renormalized over live axes only. n_axes_live exposed in score_detail.
    """
    theme = r.get("theme", "")

    # Pre-compute cross-axis inputs that require disk access (cached)
    r = dict(r)  # shallow copy so we don't mutate the cascade row
    if "_earliness" not in r:
        e_val, e_legs = _get_earliness(theme)
        r["_earliness"] = e_val
        r["_earliness_n_legs"] = e_legs
    if r["_earliness"] is None and theme_members:
        # earliness engine not available — _underpricing will fall back to revision_level
        pass
    # gross-margin trend for pricing_power fallback (members needed)
    if theme_members and r.get("ppi_yoy_latest") is None and r.get("tightness") is None:
        r.setdefault("_gross_margin_trend", _gross_margin_trend(theme_members))

    bn = _bottleneck(r)
    is_fingerprint_only = r.get("bottleneck_fingerprint_only", False)

    # Compute each axis; None = no live input → axis excluded from weighted sum
    raw_axes: dict[str, float | None] = {
        "magnitude":     _magnitude(r),
        "acceleration":  _acceleration(r),
        "bottleneck":    bn if bn is not None else None,  # None → excluded
        "pricing_power": _pricing_power(r),
        "underpricing":  _underpricing(r),
        "purity":        _purity(r),
        "timing":        _timing(r),
    }

    # bottleneck axis: when None (AWAITING / text-only), it triggers TEXT_ONLY_CAP but
    # contributes nothing to the base score (no 0.4 placeholder).
    # Renormalize weighted sum over live axes only.
    live_axes = {k: v for k, v in raw_axes.items() if v is not None}
    n_axes_live = len(live_axes)
    if n_axes_live == 0:
        base = 0.0
    else:
        total_weight = sum(WEIGHTS[k] for k in live_axes)
        base = sum(WEIGHTS[k] * v for k, v in live_axes.items()) / total_weight * 100.0

    base = round(base, 1)

    # For display: fill absent axes with None (not 0.4) so the UI can mark them absent
    display_axes = {k: (round(v, 2) if v is not None else None) for k, v in raw_axes.items()}

    caps = []
    score = base
    if bn is None:
        score = min(score, TEXT_ONLY_CAP)
        caps.append(f"text-only (no physical bottleneck) -> capped at {TEXT_ONLY_CAP:.0f}")
    elif is_fingerprint_only:
        # Fingerprint-only (annual XBRL): higher than text-only cap but below FRED uncapped.
        # physical_confirmed=False because annual cadence ≠ real-time FRED confirmation.
        if score > FINGERPRINT_CAP:
            score = FINGERPRINT_CAP
            caps.append(f"fingerprint-only (annual XBRL) -> capped at {FINGERPRINT_CAP:.0f}")
    scap = STAGE_CAP.get(r.get("stage"))
    if scap is not None and score > scap:
        score = scap
        caps.append(f"{r.get('stage')} (late) -> capped at {scap:.0f}")

    score = round(score, 1)
    if score >= 70:
        verdict = "high-conviction"
    elif score >= 55:
        verdict = "constructive"
    elif score >= 40:
        verdict = "watch"
    else:
        verdict = "low / late"

    # physical_confirmed: True only for FRED-backed reads, NOT fingerprint-only or text-only.
    physical_confirmed = bn is not None and not is_fingerprint_only

    return {
        "score": score,
        "base": base,
        "axes": display_axes,
        "n_axes_live": n_axes_live,
        "caps": caps,
        "verdict": verdict,
        "physical_confirmed": physical_confirmed,
        "earliness": r.get("_earliness"),
    }


def annotate(cascade: dict | None) -> dict | None:
    """Add a foresight_score to every cascade row and re-rank by it (highest edge+quality
    first). Additive — returns the cascade unchanged on any shortfall."""
    if not cascade or not cascade.get("themes"):
        return cascade
    # reset module-level caches for fresh cascade run
    global _EARLINESS_CACHE, _EDGAR_CACHE  # noqa: PLW0603
    _EARLINESS_CACHE = None
    _EDGAR_CACHE = {}
    try:
        cfg_themes = (config.load() or {}).get("themes") or {}
        for r in cascade["themes"]:
            theme = r.get("theme", "")
            members = list((cfg_themes.get(theme) or {}).get("tickers") or [])
            s = score_row(r, theme_members=members)
            r["score"] = s["score"]
            r["score_detail"] = s
        # rank by the rubric (score desc); stage rank breaks ties so a tied early theme wins
        from engine.foresight_cascade import _STAGE_RANK
        cascade["themes"].sort(key=lambda r: (-(r.get("score") or 0),
                                              _STAGE_RANK.get(r.get("stage"), 9)))
        cascade["scored"] = True
    except Exception as e:  # noqa: BLE001
        log.warning("foresight_score annotate failed: %s", e)
    return cascade


def reset_caches() -> None:
    """Reset module-level caches (useful for tests)."""
    global _EARLINESS_CACHE, _EDGAR_CACHE  # noqa: PLW0603
    _EARLINESS_CACHE = None
    _EDGAR_CACHE = {}
