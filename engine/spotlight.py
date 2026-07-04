"""Theme + sector SPOTLIGHT tilt — the bridge that aligns the US standout board with the
live thematic-basket recommendations (engine.theme_scoring) and the sector playbook
(engine.playbook). Pure geometry, no IO — the build script (scripts/build_stock_library)
does the heavy recompute once and calls compute() per name.

Honest scope: a SMALL, declared, clamped DISPLAY-tilt that re-orders names which are ALREADY
past the risk gates. It enters the Conviction *tailwind* axis (weight 0.10) as a z in [-1, 1],
so a full +1 spotlight moves the composite by at most ~0.03 z — enough to break ties toward
in-spotlight themes/sectors, never enough to outrun the subtract-only macro/idio risk taxes
(≤0.8 + ≤0.5 z) or the hard extension/cycle blocks. A hot theme can lift a name's RANK; it can
never rescue an extension/AVOID name onto the buy list. See stock_score._axis_tailwind for the
score path and stock_score._eff_spotlight for the "never reward a chase" over-extension clamp.

The membership map (basket -> theme) is HINDSIGHT-curated (data/baskets/membership.json), so
this is a narrative-coherence / legibility feature, not a validated standalone alpha source —
which is exactly why the magnitude is tiny and the leg is display-tagged.
"""
from __future__ import annotations

# GICS sector name (incl. yfinance + playbook display-name drift variants) -> SPDR sector ETF.
# Bridges the stock library's GICS strings ("Information Technology", and the drift cases
# "Technology"/"Communications") to the playbook's ticker-keyed stage table. An unmapped
# sector simply drops the sector channel (the theme channel still fires).
GICS_TO_ETF: dict[str, str] = {
    "Information Technology": "XLK", "Technology": "XLK", "Tech": "XLK",
    "Financials": "XLF", "Financial Services": "XLF", "Financial": "XLF",
    "Energy": "XLE",
    "Health Care": "XLV", "Healthcare": "XLV",
    "Industrials": "XLI", "Industrial": "XLI",
    "Consumer Discretionary": "XLY", "Consumer Cyclical": "XLY",
    "Consumer Staples": "XLP", "Consumer Defensive": "XLP",
    "Utilities": "XLU", "Utility": "XLU",
    "Materials": "XLB", "Basic Materials": "XLB",
    "Real Estate": "XLRE",
    "Communication Services": "XLC", "Communications": "XLC", "Communication": "XLC",
}

# theme recommendation (engine.theme_scoring._reco) -> directional tilt in [-1, 1].
_RECO_TILT = {"enter": 1.0, "accumulate": 0.7, "hold": 0.0, "trim": -0.7, "avoid": -1.0}
# sector RRG stage (engine.playbook.stage_table) -> directional tilt in [-1, 1].
_STAGE_TILT = {"leading": 0.8, "improving": 0.3, "weakening": -0.3, "lagging": -0.6}

# blend weights — the theme channel leads (it carries the macro+crowding-gated reco).
_W_THEME, _W_SECTOR = 0.60, 0.40
# Oracle rotation channel (engine.oracle.tilt) — smallest weight: its edge is
# display-with-edge tier (P3 adjudication R4), never dominant. The channel only
# enters blend() when a non-None oracle_t is passed, which only happens when
# config oracle.tilt_enabled is true — flag OFF leaves the arithmetic untouched.
_W_ORACLE = 0.25
# the scored-theme tilt = _RECO_W*reco + _SCORE_W*((score-50)/30); reco dominates, score breaks ties.
_RECO_W, _SCORE_W = 0.70, 0.30
# an extended/"don't chase" sector can never read better than this (mirrors the avoid list).
_EXTENDED_CAP = -0.5
# display multiplier half-range: mult = 1 + _MULT_SPAN*z  ->  ~[0.825, 1.175] ("~0.85-1.20").
_MULT_SPAN = 0.175
# |z| bands for the directional label / chip.
_DIR_BAND = 0.20


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def theme_tilt(reco: str | None, score: float | int | None) -> float | None:
    """Scored-theme tilt in [-1, 1]: reco verdict (macro+crowding-gated, so de-correlated
    from raw price momentum) blended with the 0-100 spotlight score. None when neither leg
    is available (the engine never reads a missing leg as neutral)."""
    r = _RECO_TILT.get(reco) if reco else None
    s = _clip((float(score) - 50.0) / 30.0) if score is not None else None
    if r is None and s is None:
        return None
    if r is None:
        return _clip(s)
    if s is None:
        return _clip(r)
    return _clip(_RECO_W * r + _SCORE_W * s)


def sector_tilt(stage: str | None, extended: bool | None,
                pctile_252d: float | int | None) -> float | None:
    """Sector RRG-stage tilt in [-1, 1], mildly modulated by the 252d RS percentile.
    An `extended` sector (RS >= 92nd pctile — the playbook's DON'T-CHASE flag) is capped
    negative so the tilt can never reward chasing a crowded sector leader."""
    base = _STAGE_TILT.get(stage) if stage else None
    if base is None:
        return None
    pc = _clip((float(pctile_252d) - 50.0) / 25.0) if pctile_252d is not None else 0.0
    t = _clip(base + 0.20 * pc)
    if extended:
        t = min(t, _EXTENDED_CAP)
    return t


def blend(theme_t: float | None, sector_t: float | None, *,
          theme: dict | None = None, sector: dict | None = None,
          oracle_t: float | None = None) -> dict | None:
    """Combine the theme + sector (+ optional gated oracle) channels into one tilt block,
    or None if none fires. Weighted over the PRESENT channels only (a name with no sector
    mapping still gets the theme tilt at full weight, and vice versa). ``oracle_t`` is the
    dark Oracle rotation channel — callers pass non-None ONLY when oracle.tilt_enabled;
    when None the arithmetic is identical to the pre-oracle blend (the R5 flag-off
    byte-identical contract)."""
    num = den = 0.0
    if theme_t is not None:
        num += _W_THEME * theme_t
        den += _W_THEME
    if sector_t is not None:
        num += _W_SECTOR * sector_t
        den += _W_SECTOR
    if oracle_t is not None:
        num += _W_ORACLE * _clip(oracle_t)
        den += _W_ORACLE
    if den == 0.0:
        return None
    z = _clip(num / den)
    return {
        "z": round(z, 3),
        "mult": round(1.0 + _MULT_SPAN * z, 3),
        "dir": "tailwind" if z >= _DIR_BAND else ("out_of_play" if z <= -_DIR_BAND else "neutral"),
        "theme_z": round(theme_t, 3) if theme_t is not None else None,
        "sector_z": round(sector_t, 3) if sector_t is not None else None,
        "oracle_z": round(_clip(oracle_t), 3) if oracle_t is not None else None,
        "theme": theme,
        "sector": sector,
    }


def _theme_meta(slug: str | None, th: dict) -> dict:
    return {"slug": slug, "name": th.get("name"), "name_zh": th.get("name_zh"),
            "score": th.get("score"), "label": th.get("label"),
            "label_en": th.get("label_en"), "label_zh": th.get("label_zh"),
            "reco": th.get("reco"), "reco_en": th.get("reco_en"), "reco_zh": th.get("reco_zh")}


def compute(memberships: list[dict] | None, theme_by_id: dict[str, dict],
            sector_etf: str | None = None, sector_row: dict | None = None,
            oracle_t: float | None = None) -> dict | None:
    """Per-name spotlight block.

    ``memberships`` — the name's active baskets (list of {slug, ...}); the STRONGEST theme
        by |tilt| is chosen (mirrors _basket_tailwind_map's max-|rel20| convention, so the
        dominant narrative wins and a name incidentally tagged into a fading theme isn't
        diluted). ``theme_by_id`` — {slug: theme_intel theme dict}. ``sector_row`` — the
        playbook stage_table row for this name's sector ETF ({stage, extended, pctile_252d,
        name}). Returns None when neither channel produces a tilt.
    """
    theme_t = None
    theme_meta = None
    best_abs = 0.0          # only a DIRECTIONAL theme (|tilt| > 0) is ever selected; a pure
    for mem in (memberships or []):   # hold/neutral theme (tilt 0.0) is skipped so it can't
        th = theme_by_id.get(mem.get("slug"))   # crowd out the sector channel or, worse, emit a
        if not th:                              # z=0 block that suppresses the legacy fallback legs.
            continue
        tt = theme_tilt(th.get("reco"), th.get("score"))
        if tt is None:
            continue
        if abs(tt) > best_abs:
            best_abs, theme_t = abs(tt), tt
            theme_meta = _theme_meta(mem.get("slug"), th)

    sector_t = None
    sector_meta = None
    if sector_row:
        sector_t = sector_tilt(sector_row.get("stage"), sector_row.get("extended"),
                               sector_row.get("pctile_252d"))
        if sector_t is not None:
            sector_meta = {"etf": sector_etf, "name": sector_row.get("name"),
                           "stage": sector_row.get("stage"),
                           "extended": bool(sector_row.get("extended")),
                           "pctile_252d": sector_row.get("pctile_252d")}

    return blend(theme_t, sector_t, theme=theme_meta, sector=sector_meta, oracle_t=oracle_t)
