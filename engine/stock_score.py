"""Unified per-stock **Conviction Profile** — one engine, four markets.

This is the cross-market home of the "Standout individual stocks" verdict. It does
NOT invent a new statistical edge; it is a TRANSPARENT DECOMPOSITION of the legs we
already compute (validated and context alike), composed *around* — never replacing —
the calibrated ``engine/cycles.analyze`` ladder. The honest product is a *profile*
(four sub-axes you can read), not a single precise number.

Design contract (see ``research/STOCK_CONVICTION_DESIGN.md`` v2):

* **Four axes**, each a signed z built from ALREADY cross-sectionally standardized
  legs (so this module never re-standardizes — that is the panel builder's job):
    - ``selection``  — "will it go higher": the market's validated selection leg
      (US/CA residual alpha · CN reversal context · HK relative-strength screen).
    - ``entry``      — "how good is the entry": cycle entry/urgency + pullback vs
      extended + drawdown-from-high + RSI + an extension PENALTY (parabolic only).
    - ``tailwind``   — "how much higher": host-sector RS + thematic-basket strength
      (a declared sector-level TILT, small weight, never blended as within-sector).
    - ``quality``    — "how good is the business": SUE + insider (validated) and the
      orthogonalized factor composite + ex-US fundamental priors (context), CAPPED
      by the accounting-quality verdict.

* **The cycle state is a HARD VERB MODIFIER, not a side note.** A name in a
  downtrend/exit/avoid (or a parabolic blow-off) has its entry axis capped and can
  NEVER read "Buy/Add" — the headline verb says "strong name, wrong tape" instead.
  This is what actually kills the dashboard-vs-detail mismatch.

* **Honesty gates.** The 0-100 ``score`` is a DISPLAY skin (within-market percentile
  or a logistic), never a probability and never compared across markets as if equal.
  A per-market ``trust_tier`` states what the number means (US/CA weak-context · CN
  reversal-validated · HK no-edge screen). The SHIPPED board rank stays each market's
  validated leg unless a deep-CI Phase-0 persists ``gate: GO`` — this module's
  composite is display/ordering context by default.

Everything here is pure (per-name funcs are pure-python; the panel helper uses
pandas) so it is trivially unit-testable and reused by every ``build_*_library``.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# market constants
# ----------------------------------------------------------------------------
MARKETS = ("US", "CN", "HK", "CA")

# fallback on-card label for the EDGE axis per market (see _sel_kind for the dynamic,
# leg-aware label). v2: the US/CA EDGE is the VALIDATED event core (earnings surprise +
# insider buying + analyst revisions) — residual momentum is demoted to a light context
# leg because on clean PIT large-cap data it does not predict (research/STOCK_CONVICTION_V2).
_SEL_KIND = {
    "US": ("event edge", "事件驱动优势"),
    "CA": ("event edge", "事件驱动优势"),
    "CN": ("mean-reversion", "均值回归"),
    "HK": ("relative strength", "相对强度"),
}

# EDGE evidence weights (US/CA), anchored on the deep-PIT IC audit: SUE (IC .039, the only
# FDR survivor, L/S Sharpe 1.26) > insider net-buy (.029, FDR-adjacent) > analyst-revision
# momentum (literature IC ~.23, locally accruing) > residual momentum (.012, FAILS FDR -> a
# light directional context only). Renormalized over whichever legs are present per name.
_EDGE_W = {"sue": 0.40, "insider": 0.30, "revision": 0.20, "mom": 0.10}

# REGIME-CONDITIONAL momentum weight (research/STOCK_CONVICTION_V2 §3 + the regime audit in
# scripts/conviction_v2_regime.py). The deep+PIT S&P panel (2008-2026, 63d) shows residual
# momentum's forward edge is STRONGLY regime-switching — sector-neutral rank-IC +0.030 in a
# calm/risk-on tape (SPY>200dma & low realized-vol) but -0.028 in a down tape and -0.017 in
# high-vol — while the SUE event edge is regime-ROBUST (+0.002..+0.006 everywhere). Switching
# momentum→SUE by regime lifts overall IC 0.0098→0.0192 and the long-only top-decile to
# 15.4% ann / Sortino 1.01 / maxDD -35% (vs SPY 13.4% / -47%). This is literature-grounded,
# not data-mined: Daniel-Moskowitz (2016) "Momentum Crashes" show momentum suffers severe
# crashes in panic/bear states and that scaling exposure by bear-state + variance ~doubles
# its Sharpe. So we scale ONLY the momentum (context) leg by the live `calm` score in [0,1]:
# near 0 in stress (momentum ~pulled out, SUE/insider dominate), up to _MOM_W_CALM in calm.
# `calm=None` (no live regime, ex-US, unit tests) keeps the v2 base weight -> behaviour
# unchanged. The validated SUE/insider/revision core is NEVER scaled down.
_MOM_W_CALM = 0.28      # calm/risk-on tape: residual momentum earns real weight (IC ~+0.03)
_MOM_W_STRESS = 0.04    # down-trend / high-vol: momentum IC flips negative -> near-zero weight

# PEAD freshness — DISPLAY-ONLY (the decay was retired; see below). SUE earnings drift fades
# over ~60-90d, so v3 weighted the SUE leg by exp(-days_since_filing / 45). That helped on the
# SYNTHETIC asof (period_end+60d), but once collectors/edgar_eps.py supplied the REAL filing
# date (~26d earlier, per-name staggered) the re-validation (scripts/pead_freshness_phase0.py,
# deep+PIT, τ swept 45/63/90) was decisive: the decay raises cross-sectional IC at every τ
# (0.0079->0.009+) but CONSISTENTLY LOWERS the long-only top-decile (13.6% flat -> 12.7-12.9%
# decayed, Sharpe .80 -> .73-.75) — recency-bias contaminates the extreme top decile (the names
# the board actually shows) with noisy just-reported surprises. The robust win is the REAL DATES
# improving the FLAT SUE's PIT (IC 0.0065->0.0079, long-only 13.3->13.6%, maxDD -38.1->-36.0%).
# So we score FLAT SUE and surface freshness (sue_fresh_days) as DISPLAY context only — never a
# score weight. (Kept honest per the no-overfit discipline: the better data overrode the
# synthetic-tuned weighting.)


def _edge_weights(calm: float | None) -> dict:
    """The EDGE evidence weights with the momentum leg scaled by the live `calm` regime
    score in [0,1] (1 = calm/risk-on, 0 = stress). `calm is None` -> the v2 base weights
    (mom 0.10), so every caller that does not supply a regime is byte-identical to v2."""
    if calm is None:
        return dict(_EDGE_W)
    c = float(np.clip(calm, 0.0, 1.0))
    w = dict(_EDGE_W)
    w["mom"] = _MOM_W_STRESS + (_MOM_W_CALM - _MOM_W_STRESS) * c
    return w


def _regime_tilt(market: str, calm: float | None) -> dict | None:
    """Display banner: which regime tilt the EDGE axis is currently applying (research §6).
    Only US conditions on the live tape (the validated finding); other markets / no-regime
    return None so the UI shows nothing. `calm` in [0,1]: high = trend up + low vol."""
    if market.upper() != "US" or calm is None:
        return None
    c = float(np.clip(calm, 0.0, 1.0))
    if c >= 0.75:
        return {"state": "calm", "css": "rg-calm",
                "en": "Calm / risk-on tape — trend momentum up-weighted",
                "zh": "平稳／风险偏好行情 — 上调趋势动量权重"}
    if c <= 0.25:
        return {"state": "stress", "css": "rg-stress",
                "en": "Stressed tape — momentum pulled back, earnings edge leads",
                "zh": "承压行情 — 下调动量，盈利事件优势主导"}
    return {"state": "mixed", "css": "rg-mixed",
            "en": "Mixed tape — balanced momentum / earnings edge",
            "zh": "混合行情 — 动量与盈利优势均衡"}

# Per-market TRUST TIER — bound to the validated record, NOT to the live number.
# This is the cross-market honesty badge (research §6.4). `gate_go` flips US/CA/CN
# to "validated rank" only when the deep-CI Phase-0 said so.
def trust_tier(market: str, gate_go: bool = False) -> dict:
    m = (market or "").upper()
    if m == "HK":
        return {"tier": "screen", "en": "No stock-selection edge — relative-strength / exposure screen",
                "zh": "无选股优势 — 相对强度／敞口筛选", "css": "tt-screen"}
    if m == "CN":
        return {"tier": "reversal", "en": "Reversal context — validated but high-variance, not a buy list",
                "zh": "均值回归参考 — 已验证但高波动，非买入清单", "css": "tt-reversal"}
    if m == "CA":
        # no event feeds on the TSX -> residual-momentum prior, never claimed as validated.
        return {"tier": "context", "en": "Residual-momentum prior — unvalidated, not a standalone edge",
                "zh": "残差动量先验 — 未验证，非独立超额收益", "css": "tt-context"}
    # US — v2 EDGE = validated event signals (SUE is the FDR survivor; insider is
    # FDR-adjacent; analyst revisions are literature-strong and locally accruing).
    if gate_go:
        return {"tier": "validated", "en": "Event edge (earnings + insider + revisions) cleared Phase-0",
                "zh": "事件驱动优势（盈利＋内部人＋评级调整）已通过 Phase-0", "css": "tt-go"}
    return {"tier": "event-edge",
            "en": "Event edge: earnings surprise + insider buying (SUE FDR-validated) · revisions accruing",
            "zh": "事件驱动优势：盈利超预期＋内部人买入（SUE 已通过 FDR）· 评级调整累积中", "css": "tt-context"}

# Per-market DISPLAY weights for the composite roll-up (labeled uncalibrated PRIOR;
# the SHIPPED rank does not use these unless gate GO). Default behaviour is
# equal-weight over the axes that are actually present (research §4).
# v2: EDGE-dominant — the validated event core (selection) carries the most weight; entry
# is timing context; quality is durability; tailwind is a small sector tilt.
_WEIGHT_PRIOR = {
    "US": {"selection": 0.45, "entry": 0.15, "tailwind": 0.10, "quality": 0.30},
    "CA": {"selection": 0.45, "entry": 0.18, "tailwind": 0.12, "quality": 0.25},
    "CN": {"selection": 0.42, "entry": 0.25, "tailwind": 0.13, "quality": 0.20},
    "HK": {"selection": 0.35, "entry": 0.25, "tailwind": 0.20, "quality": 0.20},
}

# cycle states that BLOCK a buy verb + cap the entry axis (research §6.3).
_CYCLE_BLOCK_STATES = {"DECLINE", "ROLLING OVER", "TOP WATCH"}
_BLOCK_URGENCY = {"exit", "avoid"}

_PARABOLIC = "parabolic"
_ENTRY_CAP_Z = -0.2          # entry axis cannot exceed this when cycle-blocked
_AXIS_Z_CLIP = 3.0


def _f(x) -> float | None:
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _mean_avail(vals: list[float | None]) -> float | None:
    xs = [v for v in vals if v is not None]
    return float(np.mean(xs)) if xs else None


def _clipz(z: float | None) -> float | None:
    if z is None:
        return None
    return float(np.clip(z, -_AXIS_Z_CLIP, _AXIS_Z_CLIP))


def _logistic_0_100(z: float | None, k: float = 0.62) -> int | None:
    """Monotone DISPLAY skin only (research §2): signed z -> 0..100. Never fed to
    IC/Sharpe/calibration and never compared across markets as if equal."""
    if z is None:
        return None
    return int(round(100.0 / (1.0 + math.exp(-k * z))))


# ----------------------------------------------------------------------------
# axis sub-scores (per-name; legs are already cross-sectional z's)
# ----------------------------------------------------------------------------
def _sel_kind(market: str, present: list[str]) -> tuple[str, str]:
    """The on-card label for the EDGE axis, derived from the legs that ACTUALLY
    contributed — so the validated event edge is named honestly and a residual-momentum
    fallback is never mislabeled."""
    if any(k in present for k in ("sue", "insider", "revision")):
        return ("earnings · insider · revisions", "盈利 · 内部人 · 评级调整")
    if "rev_z" in present:
        return ("mean-reversion", "均值回归")
    if "rs" in present:
        return ("relative strength", "相对强度")
    if "alpha" in present:
        return ("residual momentum", "残差动量")
    return _SEL_KIND.get(market, ("edge", "优势"))


_BASIS_LABEL = {"sue": ("SUE", "盈利超预期", "validated"), "insider": ("insider", "内部人", "validated"),
                "revision": ("revisions", "评级调整", "literature"), "alpha": ("momentum", "动量", "context"),
                "rev_z": ("reversal", "均值回归", "validated"), "rs": ("rel. strength", "相对强度", "screen")}


def _edge_basis(rec: dict, market: str) -> list[dict]:
    """Per-leg EDGE contributions for the display BASIS panel — which legs are firing and
    how strongly, each tagged validated / literature / context / screen — so an operator
    (and the future AI layer) can see WHY the edge score is what it is."""
    m = market.upper()
    out: list[dict] = []

    def add(key: str, val: float | None, fresh: float | None = None) -> None:
        if val is None:
            return
        lab = _BASIS_LABEL.get(key, (key, key, "context"))
        chip = {"leg": key, "label": lab[0], "label_zh": lab[1], "tier": lab[2],
                "z": round(float(val), 2)}
        if fresh is not None:                     # DISPLAY-only filing recency (not scored)
            chip["fresh_days"] = int(round(fresh))
        out.append(chip)
    if m == "US":
        s = _f(rec.get("sue"))
        add("sue", float(np.clip(s, -3, 3)) if s is not None else None,
            fresh=_f(rec.get("sue_fresh_days")))
        i = _f(rec.get("insider_bps")); add("insider", float(np.clip(i / 30.0, -1.5, 1.5)) if i is not None else None)
        r = _f(rec.get("revision_z")); add("revision", float(np.clip(r, -3, 3)) if r is not None else None)
        a = _f(rec.get("alpha")); add("alpha", float(np.clip(a, -3, 3)) if a is not None else None)
    elif m == "CN":
        add("rev_z", _f(rec.get("rev_z"))); add("revision", _f(rec.get("revision_z"))); add("alpha", _f(rec.get("alpha")))
    elif m == "CA":
        add("alpha", _f(rec.get("alpha")))
    else:
        add("rs", _f(rec.get("rs_z")) if _f(rec.get("rs_z")) is not None else _f(rec.get("alpha")))
    return out


def _axis_selection(rec: dict, market: str, calm: float | None = None) -> tuple[float | None, list[str]]:
    """The EDGE axis — the VALIDATED, event-driven predictive core that DRIVES the rank
    (research/STOCK_CONVICTION_V2). Returns (z, present_legs).

    * US/CA — evidence-weighted blend of SUE (FDR survivor) + insider net-buying +
      analyst-revision momentum + a LIGHT residual-momentum context (momentum alone is
      ~noise on clean PIT large-cap data, so it earns only the 0.10 context weight). The
      momentum weight is REGIME-CONDITIONAL via `calm` (see `_edge_weights`): it rises in a
      calm/risk-on tape where momentum predicts and is pulled toward zero in stress where it
      crashes — the validated lift in the regime audit. `calm=None` keeps the v2 base weight.
    * CN — A-share momentum is dead; the validated effect is short-term REVERSAL, so the
      edge is reversal-led + revisions, residual momentum a light context.
    * HK — no validated stock-selection edge: relative strength only, framed as a screen.
    """
    m = market.upper()
    present: list[str] = []
    if m == "US":
        # the validated event edge: SUE + insider + revisions exist for US (EDGAR / Form-4 /
        # yfinance). Residual momentum is a LIGHT context leg (regime-scaled), and a CONFIDENCE
        # FLOOR dampens a US name with NO event signal toward zero — it must not rank like a
        # name carrying a real earnings/insider/revision edge.
        ew = _edge_weights(calm)
        legs: dict[str, float] = {}
        sue = _f(rec.get("sue"))
        if sue is not None:                       # FLAT SUE — freshness is display-only (the
            legs["sue"] = float(np.clip(sue, -3, 3)); present.append("sue")  # decay hurt the LO board
        ins = _f(rec.get("insider_bps"))
        if ins is not None:                       # net Form-4 buying, bps of mcap
            legs["insider"] = float(np.clip(ins / 30.0, -1.5, 1.5)); present.append("insider")
        rev = _f(rec.get("revision_z"))
        if rev is not None:                       # analyst estimate-revision momentum z
            legs["revision"] = float(np.clip(rev, -3, 3)); present.append("revision")
        mom = _f(rec.get("alpha"))                # residual momentum — LIGHT, regime-scaled context
        if mom is not None:
            legs["mom"] = float(np.clip(mom, -3, 3)); present.append("alpha")
        if not legs:
            return None, present
        num = sum(ew[k] * v for k, v in legs.items())
        den = max(sum(ew[k] for k in legs), 0.5)   # confidence floor (see above)
        return _clipz(num / den), present
    if m == "CA":
        # Canada has NO event feeds (no EDGAR / Form-4 / revision data on the TSX), so
        # residual momentum is its best-available selection leg — kept at full strength and
        # framed as an UNVALIDATED prior (gate stays NEUTRAL; the board keeps the alpha rank).
        z = _f(rec.get("alpha"))
        if z is not None:
            present.append("alpha")
        return _clipz(z), present
    if m == "CN":
        z = _f(rec.get("rev_z"))                  # validated A-share reversal
        a = _f(rec.get("alpha"))                  # residual momentum: light context
        rev = _f(rec.get("revision_z"))
        legs: list[tuple[float, float]] = []
        if z is not None:
            legs.append((z, 0.55)); present.append("rev_z")
        if rev is not None:
            legs.append((float(np.clip(rev, -3, 3)), 0.25)); present.append("revision")
        if a is not None:
            legs.append((float(np.clip(a, -3, 3)), 0.20)); present.append("alpha")
        if not legs:
            return None, present
        num = sum(v * w for v, w in legs); den = sum(w for _, w in legs)
        return _clipz(num / den), present
    # HK — relative strength only, framed as a screen
    z = _f(rec.get("rs_z"))
    if z is None:
        z = _f(rec.get("alpha"))      # build may pass the RS z in the alpha slot
    if z is not None:
        present.append("rs")
    return _clipz(z), present


# urgency -> entry tilt
_URG_Z = {"now": 1.0, "imminent": 0.9, "soon": 0.4, "hold": 0.05,
          "later": -0.2, "caution": -0.6, "exit": -1.2, "avoid": -1.2}
_ENTRY_TAG_Z = {"pullback": 0.6, "extended": -0.6}
_EXT_PENALTY = {"parabolic": -1.0, "stretched": -0.3}


def _drawdown_hump(off_high_pct: float | None) -> float | None:
    """A mild pullback from the 52w high is the constructive entry; a brand-new high
    is slightly worse (chasing) and a deep crash is worse still. off_high_pct is the
    (negative) % below the 52w high."""
    if off_high_pct is None:
        return None
    x = off_high_pct
    if x >= -2:           # at / making new highs
        return -0.15
    if -12 <= x < -2:     # the sweet spot: orderly pullback
        return 0.45
    if -22 <= x < -12:
        return 0.1
    if -40 <= x < -22:
        return -0.35
    return -0.7           # >40% off the high — broken


def _rsi_band(rsi: float | None) -> float | None:
    if rsi is None:
        return None
    if 40 <= rsi <= 62:
        return 0.25
    if rsi >= 75:
        return -0.45
    if rsi <= 25:
        return -0.2
    return 0.0


# ABSOLUTE trend-extension brake — distance above the 200dma (research: the CASY failure).
# The own-history ext_z (engine/extension) z-scores stretch vs the name's OWN trailing year,
# so a PERSISTENT leader that is always ~30% above its 200dma reads ~0 (not extended vs
# itself) and slips the parabolic flag. So we ALSO read the RAW stretch above the 200dma.
# DATA (deep+PIT 18y, top-momentum-decile, forward 5/10/21d, returns clipped): names <25%
# above their 200dma are HEALTHY (good median, shallow drawdown), but the >~35% cohort has the
# WORST median forward return AND the deepest drawdowns at every horizon (the fat-tailed-mean
# "lottery" chase). Drawdown is already elevated from ~25%. So we leave the healthy ≤_STRETCH_WARN
# zone untouched and risk-conservatively HARD-BLOCK the chase at _STRETCH_BLOCK (cap the entry,
# "don't chase" verb) — trading a little late-momentum upside for avoiding the drawdown, which
# is the board's risk-discipline mandate. The own-history parabolic flag (ext_z>2, validated
# -94% DD) still blocks independently.
_STRETCH_WARN = 25.0       # % above 200dma where the graduated entry penalty begins (≤ this = healthy)
_STRETCH_BLOCK = 30.0      # % above 200dma => over-extended chase (cap entry + "don't chase")


def _stretch_penalty(pct_vs_200: float | None) -> float | None:
    if pct_vs_200 is None:
        return None
    x = float(pct_vs_200)
    if x <= _STRETCH_WARN:
        return 0.0
    if x <= _STRETCH_BLOCK:                 # 18..30 -> 0..-0.9
        return -(x - _STRETCH_WARN) / (_STRETCH_BLOCK - _STRETCH_WARN) * 0.9
    return float(np.clip(-0.9 - (x - _STRETCH_BLOCK) / 10.0 * 0.3, -1.2, -0.9))


def _overextended(rec: dict) -> bool:
    """True when price is far enough above its 200dma to be a chase (CASY: +35%)."""
    pv = _f((rec.get("tech") or {}).get("pct_vs_200dma"))
    return pv is not None and pv >= _STRETCH_BLOCK


def _axis_entry(rec: dict) -> tuple[float | None, list[str], bool]:
    """Entry/timing axis + whether the cycle/extension BLOCKS a buy (caps the axis)."""
    present: list[str] = []
    lad = rec.get("ladder") or {}
    entry = (lad.get("entry") or {})
    tech = rec.get("tech") or {}
    ext = rec.get("ext") or {}

    parts: list[float | None] = []
    urg = entry.get("urgency")
    if urg in _URG_Z:
        parts.append(_URG_Z[urg]); present.append("urgency")
    tag = rec.get("alpha_entry")
    if tag in _ENTRY_TAG_Z:
        parts.append(_ENTRY_TAG_Z[tag]); present.append("pullback/extended")
    dh = _drawdown_hump(_f(tech.get("off_52w_high_pct")))
    if dh is not None:
        parts.append(dh); present.append("off-high")
    rb = _rsi_band(_f(tech.get("rsi14")))
    if rb is not None:
        parts.append(rb); present.append("rsi")
    grade = ext.get("grade")
    if grade in _EXT_PENALTY:               # own-history extension PENALTY (never a positive add)
        parts.append(_EXT_PENALTY[grade]); present.append("extension")
    sp = _stretch_penalty(_f(tech.get("pct_vs_200dma")))   # absolute distance above the 200dma
    if sp is not None and sp < 0:
        parts.append(sp); present.append("over-200dma")

    z = _mean_avail(parts)
    # hard-block: downtrend / topping / exit / avoid / parabolic / OVER-EXTENDED (a chase)
    state = (lad.get("state") or "").upper()
    blocked = (state in _CYCLE_BLOCK_STATES or urg in _BLOCK_URGENCY
               or grade == _PARABOLIC or _overextended(rec))
    if blocked and z is not None:
        z = min(z, _ENTRY_CAP_Z)
    # scale the small tilts up toward ~unit z for the composite
    return _clipz(z * 1.6 if z is not None else None), present, blocked


def _axis_tailwind(rec: dict) -> tuple[float | None, list[str]]:
    """Sector + thematic-basket tailwind — a declared SECTOR-LEVEL tilt (small)."""
    present: list[str] = []
    parts: list[float | None] = []
    srs = rec.get("sector_rs") or {}
    pct = _f(srs.get("pct"))
    if pct is not None:                      # 0..100 sector-RS percentile
        parts.append((pct - 50.0) / 25.0); present.append("sector-RS")
    bk = rec.get("basket") or {}
    rel = _f(bk.get("rel20"))                # basket 20d return vs benchmark (%)
    if rel is not None:
        parts.append(float(np.clip(rel / 6.0, -1.0, 1.0))); present.append("theme")
    return _clipz(_mean_avail(parts)), present


def _axis_quality(rec: dict, market: str) -> tuple[float | None, list[str], dict]:
    """DURABILITY — will the business survive the hold (NOT 'will it go up' — the
    earnings/insider edge moved to the EDGE axis in v2). Gross profitability (Novy-Marx,
    the cleanest durable-business leg = the factor 'profitability' = GP/assets) + the
    orthogonal factor composite + ex-US fundamental priors, CAPPED by the accounting
    verdict (accruals are decayed as a return leg → used only as a filter)."""
    present: list[str] = []
    parts: list[float | None] = []

    # prefer a precomputed orthogonal composite; else mean of the durable factor legs
    # (profitability first — gross profitability is the validated durability proxy).
    qc = _f(rec.get("quality_context_z"))
    if qc is None:
        fac = rec.get("factor") or {}
        qc = _mean_avail([_f(fac.get(k)) for k in
                          ("profitability", "quality", "value", "low_vol")])
    if qc is not None:
        parts.append(float(np.clip(qc, -3, 3))); present.append("factors")

    # ex-US fundamental priors (Piotroski/Altman/valuation), clearly context
    fp = _f((rec.get("fund_priors") or {}).get("z"))
    if fp is not None:
        parts.append(float(np.clip(fp, -3, 3))); present.append("priors")

    z = _mean_avail(parts)
    flags = {"accounting": None}
    acct = (rec.get("accounting") or {}).get("verdict")
    if acct:
        flags["accounting"] = acct
        if acct == "warn" and z is not None:        # hard cap, never a positive add
            z = min(z, -0.5)
        elif acct == "watch" and z is not None:
            z = min(z, 0.3)
    return _clipz(z), present, flags


# ----------------------------------------------------------------------------
# verdict verb — the explicit disagreement table (research §6.3)
# ----------------------------------------------------------------------------
def _tier(z: float | None) -> str:
    if z is None:
        return "na"
    if z >= 1.0:
        return "high"
    if z >= 0.25:
        return "mid"
    if z <= -0.5:
        return "low"
    return "flat"


def verdict(axes: dict, rec: dict, market: str, *, cycle_blocked: bool) -> dict:
    """Map the axes + cycle state to a single honest headline verb (EN + 中文),
    plus drivers/cautions. First-match-wins; the cycle block and accounting/parabolic
    flags OVERRIDE any 'Buy' wording so a card never says BUY next to EXIT."""
    m = market.upper()
    sel = axes.get("selection", {}).get("z")
    ent = axes.get("entry", {}).get("z")
    qual = axes.get("quality", {})
    qz = qual.get("z")
    acct = (qual.get("flags") or {}).get("accounting")
    grade = (rec.get("ext") or {}).get("grade")
    lad = rec.get("ladder") or {}
    state = (lad.get("state") or "").upper()
    sel_t = _tier(sel)

    drivers: list[str] = []
    cautions: list[str] = []
    if sel_t in ("high", "mid"):
        drivers.append((axes.get("selection", {}).get("kind")) or _SEL_KIND.get(m, ("edge", "优势"))[0])
    if _tier(ent) in ("high", "mid"):
        drivers.append("entry")
    if _tier(qz) in ("high", "mid"):
        drivers.append("quality")
    if _tier(axes.get("tailwind", {}).get("z")) in ("high", "mid"):
        drivers.append("tailwind")
    if acct == "warn":
        cautions.append("accounting warn")
    elif acct == "watch":
        cautions.append("accounting watch")
    if grade == _PARABOLIC:
        cautions.append("parabolic — extended")
    _ovx = _overextended(rec)
    if _ovx:
        _pv = _f((rec.get("tech") or {}).get("pct_vs_200dma"))
        cautions.append(f"extended +{_pv:.0f}% over 200dma — chasing" if _pv is not None
                        else "extended over 200dma — chasing")
    if cycle_blocked:
        cautions.append("cycle: " + (lad.get("label") or state or "weak tape"))

    # ---- HK: never a buy verb. Screen / exposure language only. -------------
    if m == "HK":
        if sel_t == "high":
            return _v("Relative-strength standout — screen, not a validated pick",
                      "相对强度突出 — 筛选项，非已验证买入", drivers, cautions)
        if sel_t in ("mid", "flat"):
            return _v("Exposure name — context only", "敞口标的 — 仅供参考", drivers, cautions)
        return _v("Lagging — relative weakness", "落后 — 相对弱势", drivers, cautions)

    # ---- cycle hard-block: never 'Buy' regardless of the composite ----------
    if cycle_blocked:
        # a parabolic blow-off / over-extended chase is blocked — the specific message
        if (grade == _PARABOLIC or _ovx) and sel_t in ("high", "mid"):
            return _v("Extended — don't chase; wait for a pullback",
                      "过度拉升 — 勿追高；等待回撤", drivers, cautions)
        if sel_t == "high":
            return _v("Strong name · wrong tape — wait for a base",
                      "强势个股 · 趋势不利 — 等待筑底", drivers, cautions)
        if sel_t in ("mid", "flat"):
            return _v("Hold off — timing against you", "暂缓 — 时机不利", drivers, cautions)
        return _v("Avoid — downtrend", "回避 — 下行趋势", drivers, cautions)

    # ---- accounting / extension overrides on otherwise-constructive names ----
    if acct == "warn" and sel_t in ("high", "mid"):
        return _v("Leader · accounting warning — verify before buying",
                  "领先 · 财务质量警示 — 买入前先核实", drivers, cautions)
    if grade == _PARABOLIC and sel_t in ("high", "mid"):
        return _v("Extended — don't chase; wait for a pullback",
                  "过度拉升 — 勿追高；等待回撤", drivers, cautions)

    # ---- the constructive cases --------------------------------------------
    ent_ok = (ent is not None and ent > 0)
    if sel_t == "high" and ent_ok:
        if _tier(qz) == "low":                 # strong edge but weak fundamentals — flag the risk
            cautions.append("weak fundamentals")
            return _v("Leader · weak fundamentals — higher-risk",
                      "领先 · 基本面偏弱 — 风险偏高", drivers, cautions)
        return _v("High-conviction — leader with a good entry",
                  "高确信 — 领先且入场点良好", drivers, cautions)
    if sel_t == "high" and ent is None:        # absent entry data is NOT 'poor entry'
        return _v("Leader · entry unknown — confirm timing",
                  "领先 · 入场时机未知 — 请确认", drivers, cautions)
    if sel_t == "high" and not ent_ok:
        return _v("Leader · poor entry — wait for a base",
                  "领先 · 入场点欠佳 — 等待筑底", drivers, cautions)
    if sel_t == "mid" and ent_ok:
        return _v("Constructive — building a base", "建设性 — 正在筑底", drivers, cautions)
    if sel_t == "low":
        return _v("Lagging — relative weakness", "落后 — 相对弱势", drivers, cautions)
    return _v("Neutral — no clear edge", "中性 — 无明显优势", drivers, cautions)


def _v(en: str, zh: str, drivers: list[str], cautions: list[str]) -> dict:
    return {"verdict": en, "verdict_zh": zh,
            "drivers": drivers, "cautions": cautions}


# ----------------------------------------------------------------------------
# the public per-name entry point
# ----------------------------------------------------------------------------
_BANDS = [(80, "high", "High conviction", "高确信"),
          (60, "constructive", "Constructive", "建设性"),
          (40, "neutral", "Neutral", "中性"),
          (0, "low", "Low", "偏弱")]


def _band(score: int | None) -> dict:
    if score is None:
        return {"band": "na", "en": "—", "zh": "—"}
    for lo, key, en, zh in _BANDS:
        if score >= lo:
            return {"band": key, "en": en, "zh": zh}
    return {"band": "low", "en": "Low", "zh": "偏弱"}


def conviction_profile(rec: dict, market: str, *, ctx: dict | None = None) -> dict:
    """Build the full Conviction block for one name (research §6.1).

    ``rec`` is a NORMALIZED dict (each build_*_library maps its data into it; missing
    legs are simply absent — never silently neutral). ``ctx`` may carry a precomputed
    cross-sectional ``score_pct`` (within-market percentile, preferred for display) and
    the deep-CI ``gate_go`` flag. Returns the block both surfaces render.
    """
    ctx = ctx or {}
    m = (market or "US").upper()
    calm = _f((ctx.get("regime") or {}).get("calm"))   # live calm/risk-on score in [0,1]

    sel_z, sel_present = _axis_selection(rec, m, calm)
    ent_z, ent_present, blocked = _axis_entry(rec)
    tw_z, tw_present = _axis_tailwind(rec)
    q_z, q_present, q_flags = _axis_quality(rec, m)

    axes = {
        "selection": {"z": sel_z, "pct": _logistic_0_100(sel_z), "present": sel_present,
                      "kind": _sel_kind(m, sel_present)[0],
                      "kind_zh": _sel_kind(m, sel_present)[1],
                      "basis": _edge_basis(rec, m)},
        "entry": {"z": ent_z, "pct": _logistic_0_100(ent_z), "present": ent_present,
                  "blocked": blocked},
        "tailwind": {"z": tw_z, "pct": _logistic_0_100(tw_z), "present": tw_present},
        "quality": {"z": q_z, "pct": _logistic_0_100(q_z), "present": q_present,
                    "flags": q_flags},
    }

    # composite roll-up (DISPLAY only). Equal-weight over present axes, nudged by the
    # per-market prior; the SHIPPED rank does not use this unless gate GO.
    w = _WEIGHT_PRIOR.get(m, _WEIGHT_PRIOR["US"])
    num = den = 0.0
    for k in ("selection", "entry", "tailwind", "quality"):
        z = axes[k]["z"]
        if z is not None:
            num += w[k] * z
            den += w[k]
    comp_z = (num / den) if den > 0 else None

    # score: prefer the within-market percentile passed by the panel builder; else
    # the logistic skin (per-name fallback, flagged approximate).
    score = ctx.get("score_pct")
    if score is None:
        score = _logistic_0_100(comp_z)
    score = int(round(score)) if score is not None else None

    vb = verdict(axes, rec, m, cycle_blocked=blocked)
    band = _band(score)

    # provenance — what is present vs missing, never read missing as neutral.
    all_legs = {"selection": sel_present, "entry": ent_present,
                "tailwind": tw_present, "quality": q_present}
    present = sorted({leg for ls in all_legs.values() for leg in ls})
    n_axes = sum(1 for k in axes if axes[k]["z"] is not None)

    return {
        "score": score,
        "band": band["band"], "band_en": band["en"], "band_zh": band["zh"],
        "composite_z": round(comp_z, 3) if comp_z is not None else None,
        "verdict": vb["verdict"], "verdict_zh": vb["verdict_zh"],
        "drivers": vb["drivers"], "cautions": vb["cautions"],
        "trust_tier": trust_tier(m, bool(ctx.get("gate_go"))),
        "regime": _regime_tilt(m, calm),
        "axes": axes,
        "n_axes": n_axes,
        "cycle_blocked": blocked,
        "provenance": {"present": present, "n_axes": n_axes,
                       "as_of": ctx.get("as_of"),
                       "uncalibrated": not bool(ctx.get("gate_go"))},
    }


# ----------------------------------------------------------------------------
# cross-sectional panel helper (build scripts + Phase-0)
# ----------------------------------------------------------------------------
def _winsor_z(s: pd.Series, cap: float = 3.0) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    mu, sd = s.mean(), s.std(ddof=0)
    if not sd or np.isnan(sd):
        return pd.Series(np.nan, index=s.index)
    return ((s - mu) / sd).clip(-cap, cap)


def sector_neutral_z(s: pd.Series, sector: pd.Series, cap: float = 3.0,
                     min_sector: int = 6) -> pd.Series:
    """Winsorized z WITHIN each GICS sector (mirrors residual_alpha / top_picks_phase0
    so every leg shares the unit-variance sector-neutral scale). Sectors with fewer
    than ``min_sector`` names fall back to the cross-sectional z."""
    s = pd.to_numeric(s, errors="coerce")
    out = pd.Series(np.nan, index=s.index, dtype=float)
    big = sector.value_counts()
    for sec, idx in s.groupby(sector).groups.items():
        sub = s.loc[idx]
        out.loc[idx] = (_winsor_z(sub, cap) if big.get(sec, 0) >= min_sector
                        else (sub - s.mean()) / (s.std(ddof=0) or 1.0))
    return out.clip(-cap, cap)


def score_percentiles(comp_z: pd.Series) -> pd.Series:
    """Within-market cross-sectional percentile (0..100) of the composite z — the
    HONEST display score (comparable within a market, not across)."""
    return (comp_z.rank(pct=True) * 100.0).round()


# ----------------------------------------------------------------------------
# normalization — map an assembled per-stock record + cross-sectional legs into
# the engine's contract. Keeps every build_*_library thin and uniform.
# ----------------------------------------------------------------------------
def normalize_rec(record: dict, market: str, *, rs_z: float | None = None,
                  rev_z: float | None = None, sue: float | None = None,
                  sue_fresh_days: float | None = None,
                  insider_bps: float | None = None, revision_z: float | None = None,
                  quality_context_z: float | None = None,
                  fund_priors_z: float | None = None,
                  sector_rs: dict | None = None, basket: dict | None = None,
                  asym: dict | None = None, ext: dict | None = None) -> dict:
    """Build the normalized ``rec`` the engine consumes from a per-stock library
    ``record`` (the dict written to ``<mkt>stockdata/<T>.json``) plus the
    cross-sectional legs the build joins in. Missing legs stay absent (None) —
    never silently neutral. ``record`` shapes differ by market (US carries
    ``factors.legs`` + ``accounting_quality``; ex-US carry only ``alpha``/``ladder``/
    ``tech``), so all market-specific legs arrive as keyword args."""
    a = record.get("alpha") or {}
    fac = record.get("factors") or {}
    legs = fac.get("legs") or {}
    return {
        "ticker": record.get("ticker"), "name": record.get("name"),
        "name_zh": record.get("name_zh"), "sector": record.get("sector"),
        "alpha": a.get("alpha"), "alpha_entry": a.get("entry"),
        "rev_pctile": a.get("rev_pctile"),
        "rs_z": rs_z, "rev_z": rev_z,
        "rs": a.get("rs"), "rs3m": a.get("rs3m"),
        "rs6m": a.get("rs6m"), "rs12m": a.get("rs12m"),
        "ladder": record.get("ladder") or {},
        "tech": record.get("tech") or {},
        "ext": ext if ext is not None else record.get("ext"),
        "sector_rs": sector_rs, "basket": basket,
        "factor": {"value": legs.get("value"), "profitability": legs.get("profitability"),
                   "quality": legs.get("quality"), "low_vol": legs.get("low_vol")} if legs else None,
        "quality_context_z": quality_context_z,
        "sue": sue, "sue_fresh_days": sue_fresh_days,
        "insider_bps": insider_bps, "revision_z": revision_z,
        "fund_priors": {"z": fund_priors_z} if fund_priors_z is not None else None,
        "asym": asym,                      # downside-asymmetry DISPLAY read (risk shape, not scored)
        "accounting": record.get("accounting_quality"),
    }


def attach_panel_scores(profiles: dict[str, dict]) -> None:
    """Given {ticker: conviction_block} for ONE market, set each block's display
    ``score`` to the within-market cross-sectional percentile of its ``composite_z``
    (the honest, comparable-within-market skin) and refresh the band. Mutates in
    place. Blocks with no composite keep their per-name logistic fallback."""
    zs = {t: b.get("composite_z") for t, b in profiles.items()
          if b.get("composite_z") is not None}
    if len(zs) < 5:
        return
    s = pd.Series(zs)
    pct = score_percentiles(s)
    for t, p in pct.items():
        blk = profiles[t]
        blk["score"] = int(p)
        bnd = _band(int(p))
        blk["band"], blk["band_en"], blk["band_zh"] = bnd["band"], bnd["en"], bnd["zh"]
