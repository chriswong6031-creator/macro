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

import functools
import json
import math
from typing import Any

import numpy as np
import pandas as pd

from engine import i18n as _i18n  # bilingual glossary for caution labels
from engine import valuation as _valuation  # forward-aware non-veto valuation haircut

# ----------------------------------------------------------------------------
# market constants
# ----------------------------------------------------------------------------
MARKETS = ("US", "CN", "HK", "CA", "INTL")

# fallback on-card label for the EDGE axis per market (see _sel_kind for the dynamic,
# leg-aware label). v2: the US/CA EDGE leads with the event-evidence core (insider net-buying
# — the lone borderline cross-sectional FDR survivor — + earnings surprise + analyst revisions)
# — residual momentum is demoted to a light context leg because on clean PIT large-cap data it
# does not predict (research/STOCK_CONVICTION_V2; SUE deep-history reconciliation in
# reports/sue-deep-history-phase0.md).
_SEL_KIND = {
    "US": ("event edge", "事件驱动优势"),
    "CA": ("event edge", "事件驱动优势"),
    "CN": ("mean-reversion", "均值回归"),
    "HK": ("flow · value · exposure", "资金 · 价值 · 敞口"),
    # Intl (ex-US developed/EM ADRs) has no event feeds either — same residual-momentum
    # prior as the TSX, framed as an unvalidated context leg (see trust_tier / _axis_selection).
    "INTL": ("residual momentum", "残差动量"),
}

# EDGE evidence weights (US/CA). The SHALLOW 2023-2025 audit ranked SUE first (IC .039, lone
# FDR survivor), but the DEEP 2011-2026 re-test (reports/sue-deep-history-phase0.md) COLLAPSED
# SUE's cross-sectional edge to ~0 (IC .039->.0006, HAC t 2.85->0.06, fails BH-FDR). The lone
# (borderline) cross-sectional FDR survivor is now insider net-buying (q~0.10, mid-cap habitat
# — a confirmer, not a standalone sizer; engine/signal_lab.py, factors.html), so insider LEADS
# the blend. SUE is kept as a per-name PEAD CONFLUENCE leg, not the dominant anchor: the deep
# collapse is cross-sectional + survivorship-biased (an optimistic bound), and PEAD as a
# per-name event effect can persist where the rank-IC is thin — but it no longer outweighs the
# leg that actually survives FDR. Revision is literature-strong; residual momentum is light,
# regime-scaled context. None is a standalone alpha -> this is a DISPLAY/confluence composite,
# never a validated sizer. Renormalized over whichever legs are present per name.
# v2.2 (de-anchored from the AVGO/NVDA two-name calibration): the prior v2.1 reweight set SUE 0.18
# / revision 0.32 by rebuilding until two NAMED tickers cleared a target band — a single-name fit.
# Re-derived here from the IC EVIDENCE ALONE: SUE's cross-sectional edge is ~ZERO on deep PIT
# history (reports/sue-deep-history-phase0.md, IC .039->.0005, HAC t 0.06, L/S Sharpe ~0) and the
# repo's own verdict DEMOTES SUE scored->display/confirmer. So SUE drops to a light CONFIRMER FLOOR
# (0.10, not scored alpha), and the freed weight goes to INSIDER (the lone borderline FDR survivor),
# which takes the clear top weight (0.50). Analyst REVISIONS stay a strong co-lead at their prior
# level (0.30 — deliberately NOT raised, since raising them would just re-boost the same two names);
# momentum stays the light, regime-scaled context leg (0.10). Calibrated to the IC hierarchy, not to
# any ticker's score. Sums to 1.0; renormalized over whichever legs are present.
_EDGE_W = {"insider": 0.50, "sue": 0.10, "revision": 0.30, "mom": 0.10}

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
        return {"tier": "screen",
                "en": "No selection alpha — southbound-flow + A/H-value + global-exposure screen",
                "zh": "无选股阿尔法 — 南向资金＋A/H价值＋全球敞口筛选", "css": "tt-screen"}
    if m == "CN":
        return {"tier": "reversal", "en": "Reversal context — validated but high-variance, not a buy list",
                "zh": "均值回归参考 — 已验证但高波动，非买入清单", "css": "tt-reversal"}
    if m == "CA":
        # SEDI insider is collected and displayed, accruing toward validation (~2028);
        # residual-momentum prior is unvalidated pending Phase-0 C7 keystone test.
        return {"tier": "context",
                "en": (
                    "SEDI insider collected + displayed, ACCRUING toward validation (~2028), not scored; "
                    "residual-momentum prior UNVALIDATED pending Phase-0 C7 keystone test (masterplan §4.1 C7)"
                ),
                "zh": (
                    "SEDI 内部人数据已采集并展示，积累验证中（~2028），暂不纳入评分；"
                    "残差动量先验未经验证，待 Phase-0 C7 关键测试（规划书 §4.1 C7）"
                ),
                "css": "tt-context"}
    if m == "INTL":
        # no ex-US event feeds either -> same residual-momentum prior as the TSX.
        return {"tier": "context", "en": "Residual-momentum prior (ex-US) — unvalidated, not a standalone edge",
                "zh": "残差动量先验（非美股）— 未验证，非独立超额收益", "css": "tt-context"}
    # US — v2 EDGE = event-evidence signals. Insider net-buying is the lone (borderline)
    # cross-sectional FDR survivor; SUE's cross-sectional edge COLLAPSED on deep history
    # (reports/sue-deep-history-phase0.md) so it is kept as PEAD context, not a validated leg;
    # analyst revisions are literature-strong and locally accruing.
    if gate_go:
        return {"tier": "validated", "en": "Event edge (insider + earnings + revisions) cleared Phase-0",
                "zh": "事件驱动优势（内部人＋盈利＋评级调整）已通过 Phase-0", "css": "tt-go"}
    return {"tier": "event-edge",
            "en": "Event edge: insider buying (lone FDR survivor) + earnings-surprise PEAD context + revisions — a confluence read, not a standalone alpha",
            "zh": "事件驱动优势：内部人买入（唯一通过 FDR 的因子）＋盈利超预期 PEAD 背景＋评级调整 — 综合参考，非独立超额收益", "css": "tt-context"}

# Per-market DISPLAY weights for the composite roll-up (labeled uncalibrated PRIOR;
# the SHIPPED rank does not use these unless gate GO). Default behaviour is
# equal-weight over the axes that are actually present (research §4).
# v2: EDGE-dominant — the validated event core (selection) carries the most weight; entry
# is timing context; quality is durability; tailwind is a small sector tilt.
#
# W9-B DEMOTE (2026-07-03, #1143): US thematic-basket tailwind axis carries no forward
# clean15 information (negative tercile spreads, both deep-panel and OOS, sign-unstable).
# Weight set to 0.0 for US only — axis fields remain in the profile for display context;
# no rank/ordering contribution. Non-US markets unaffected (untested on those panels).
_WEIGHT_PRIOR = {
    "US": {"selection": 0.45, "entry": 0.15, "tailwind": 0.0, "quality": 0.30},
    "CA": {"selection": 0.45, "entry": 0.18, "tailwind": 0.12, "quality": 0.25},
    "CN": {"selection": 0.42, "entry": 0.25, "tailwind": 0.13, "quality": 0.20},
    "HK": {"selection": 0.35, "entry": 0.25, "tailwind": 0.20, "quality": 0.20},
    "INTL": {"selection": 0.45, "entry": 0.18, "tailwind": 0.12, "quality": 0.25},
}

# cycle states that BLOCK a buy verb + cap the entry axis (research §6.3).
# Cross-ref: engine/cycles.py _ALIGN_BAD_STATES gates the bottoming-alignment strip.
# The two sets intentionally diverge on COUNTERTREND BOUNCE: _ALIGN_BAD_STATES includes it
# (no alignment signal), while _CYCLE_BLOCK_STATES does NOT (the name is scoreable but cannot
# enter the buy strip).  Update both sets together whenever the cycle ontology changes.
_CYCLE_BLOCK_STATES = {"DECLINE", "ROLLING OVER", "TOP WATCH"}
_BLOCK_URGENCY = {"exit", "avoid"}

_PARABOLIC = "parabolic"
_ENTRY_CAP_Z = -0.2          # entry axis cannot exceed this when cycle-blocked
_ENTRY_CONFIRM_CAP = 0.5     # max |additive nudge| from the technical confirmers (trend/squeeze/GEX)
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
    if market.upper() == "HK":            # HK edge = southbound flow + A/H value + beta-neutral RS
        return _SEL_KIND["HK"]
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
    elif m in ("CA", "INTL"):
        add("alpha", _f(rec.get("alpha")))
    else:
        add("rs", _f(rec.get("rs_z")) if _f(rec.get("rs_z")) is not None else _f(rec.get("alpha")))
    return out


def _axis_selection(rec: dict, market: str, calm: float | None = None) -> tuple[float | None, list[str]]:
    """The EDGE axis — the VALIDATED, event-driven predictive core that DRIVES the rank
    (research/STOCK_CONVICTION_V2). Returns (z, present_legs).

    * US/CA — evidence-weighted blend LED by insider net-buying (the lone borderline FDR
      survivor) + earnings-surprise SUE (a per-name PEAD confluence leg — its cross-sectional
      edge collapsed on deep history, reports/sue-deep-history-phase0.md) + analyst-revision
      momentum + a LIGHT residual-momentum context (momentum alone is ~noise on clean PIT
      large-cap data, so it earns only the 0.10 context weight). The
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
        # the event-evidence edge: insider (lone FDR survivor) + SUE (PEAD context) + revisions
        # exist for US (Form-4 / EDGAR / yfinance). Residual momentum is a LIGHT context leg
        # (regime-scaled), and a CONFIDENCE FLOOR dampens a US name with NO event signal toward
        # zero — it must not rank like a name carrying a real insider/earnings/revision edge.
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
    if m in ("CA", "INTL"):
        # Canada/Intl have NO event feeds (no EDGAR / Form-4 / revision data ex-US), so
        # residual momentum is the best-available selection leg — kept at full strength and
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


# ---- theme/sector SPOTLIGHT tilt (engine.spotlight) -------------------------
# A declared, clamped narrative nudge that aligns the board with the live thematic-basket
# recommendation + sector playbook. Enters ONLY the tailwind axis (weight 0.10) — so a full
# +1 tilt moves comp_z by at most ~0.03 z, dominated ~20x by the macro/idio risk taxes and
# fully orthogonal to the entry hard-block. Below the knee (BOTH channels out of play) it
# also steps suggested SIZE down — asymmetric: a positive tilt never inflates size.
_OOP_KNEE = 0.40          # blended spotlight z below -this => start trimming suggested size
_OOP_SIZE_MAX = 0.5       # max risk_total contribution from the out-of-play size trim
# Damp the tilt INTO the tailwind axis so it stays "subtle": with the tailwind weight 0.10
# and (typically) a single-part axis, a full +/-1 tilt then moves comp_z by only ~+/-0.04 z
# — a within-tier re-order, dominated ~20x by the macro/idio risk taxes. The UNDAMPED z is
# still what the display chip + the out-of-play size trim read (those are deliberately legible).
_SPOTLIGHT_LEG_GAIN = 0.4

# VALIDATED scored de-risk from the name's primary NARRATIVE BASKET (allocation trend-gate).
# The narrative-rotation backtest (27y, clean sectors) found the ONE repeatable edge is
# DRAWDOWN control via the absolute-trend gate — momentum RANK is ~0 alpha. So a name whose
# basket is BELOW its long trend (or fading/deteriorating) is SIZED DOWN; a crowded basket is
# capped. Subtract-only: this NEVER re-ranks selection, only the suggested size (the honest
# "lean into the trending narratives, de-risk the broken ones" the user asked for).
_BASKET_RISK_MAX = 0.5    # max risk_total contribution from a below-trend / deteriorating basket


def _basket_risk(rec: dict) -> tuple[float, dict | None]:
    """(haircut in [0, _BASKET_RISK_MAX], bilingual caution|None) from rec['basket_alloc']."""
    ba = rec.get("basket_alloc")
    if not ba:
        return 0.0, None
    label = (ba.get("label") or "").lower()
    below = (ba.get("above_trend") is False) or (ba.get("eligible") is False)
    nm = ba.get("name") or "its narrative basket"
    if below:
        return _BASKET_RISK_MAX, {
            "en": f"Narrative basket ({nm}) is below its long-term trend — validated drawdown "
                  "gate: size down (the AI-buildout tape is rewarding leaders, not this one).",
            "zh": f"所属叙事篮子（{ba.get('name_zh') or nm}）已跌破长期趋势 — 已验证的回撤门槛：减小仓位。"}
    if label in ("fading", "deteriorating"):
        zh = "衰退" if label == "fading" else "恶化"
        return _BASKET_RISK_MAX * 0.7, {
            "en": f"Narrative basket ({nm}) is {label} — validated risk gate: trim / size down.",
            "zh": f"所属叙事篮子（{ba.get('name_zh') or nm}）正在{zh} — 已验证风险门槛：减仓。"}
    if ba.get("crowded"):
        return _BASKET_RISK_MAX * 0.4, {
            "en": f"Narrative basket ({nm}) is crowded / extended — cap size, don't add aggressively.",
            "zh": f"所属叙事篮子（{ba.get('name_zh') or nm}）拥挤／过度拉伸 — 控制仓位，勿激进加仓。"}
    return 0.0, None


def _eff_spotlight(rec: dict, *, blocked: bool = False) -> dict | None:
    """The spotlight tilt AS IT ENTERS THE SCORE: a positive theme/sector tailwind is
    NEUTRALIZED when the entry gate BLOCKS the name — over-extended (a chase), or a broken
    tape (downtrend / rolling-over / top-watch / parabolic / exit-urgency). A hot theme must
    never reward a chase or a broken tape; the risk taxes already tax it and the narrative can't
    pull it back up. A negative (out-of-play) tilt is left intact. None when absent / has no z."""
    sp = rec.get("spotlight")
    if not sp:
        return None
    z = _f(sp.get("z"))
    if z is None:
        return None
    if z > 0 and (blocked or _overextended(rec)):
        why = "stock-extended" if _overextended(rec) else "cycle-blocked"
        return {**sp, "z": 0.0, "mult": 1.0, "dir": "neutral", "clamped": why}
    return sp


# ---- macro/event RISK OVERLAY (T3) -----------------------------------------
# A high-VIX / turning-point / drawdown-risk tape should tax a CHASE — but NOT a washed-out
# reversal (that is exactly what works in stress, China's edge). So the haircut is
# stress × aggressiveness: it punishes buying an extended momentum leader INTO a stressed
# tape, and barely touches a constructive/washed-out name. Two-sided on sector (unlike the
# legacy MRS tax that exempted defensive leaders). `stress=0` (calm tape) => zero effect, so
# the overlay is silent in a normal week and only bites when the macro tape is genuinely hot.
_RISK_TAX_MAX = 0.8        # max composite_z subtracted from a full-stress, full-chase name
_RISK_VETO_STRESS = 0.5    # stress >= this AND aggressive => verb can't read "high-conviction"


def _clip01(x: float | None) -> float:
    return float(np.clip(x if x is not None else 0.0, 0.0, 1.0))


def _aggressiveness(rec: dict) -> float:
    """How much this name is a CHASE (what a stressed tape punishes): distance above the
    200dma + own-history extension grade. 0 = constructive / washed-out, 1 = parabolic."""
    pv = _f((rec.get("tech") or {}).get("pct_vs_200dma"))
    agg = _clip01(((pv or 0.0) - 10.0) / 30.0)     # +10% over 200dma -> 0, +40% -> 1
    grade = (rec.get("ext") or {}).get("grade")
    if grade == _PARABOLIC:
        agg = max(agg, 0.9)
    elif grade == "stretched":
        agg = max(agg, 0.5)
    return _clip01(agg)


def _macro_stress(overlay: dict | None) -> float:
    return _clip01(_f((overlay or {}).get("stress")))


def _risk_tax(overlay: dict | None, rec: dict) -> float:
    """Subtract-only composite haircut = _RISK_TAX_MAX · macro_stress · aggressiveness."""
    s = _macro_stress(overlay)
    return _RISK_TAX_MAX * s * _aggressiveness(rec) if s > 0 else 0.0


# ---- lottery / recent single-day spike penalty (T5; Bali-Cakici-Whitelaw) ----
# VALIDATED (deep+PIT 18y, scripts/risk_penalty_phase0): a top-momentum name whose biggest
# single-day pop in the last 21d is extreme has a NEGATIVE median fwd-21d return (-2.6%), ~2x
# the drawdown, and a sub-coin-flip hit rate — the radioactive lottery tail. Deciles 1-8 are
# flat, so it is a TAIL penalty (kicks in only at the extreme), never a positive add.
_LOTTERY_WARN = 12.0       # recent 21d single-day max return % where the penalty begins
_LOTTERY_HARD = 20.0       # >= this = radioactive one-day spike -> full penalty


def _lottery_penalty(rec: dict) -> float:
    mx = _f(rec.get("lottery_max"))
    if mx is None or mx <= _LOTTERY_WARN:
        return 0.0
    return float(np.clip(-(mx - _LOTTERY_WARN) / (_LOTTERY_HARD - _LOTTERY_WARN) * 0.9, -1.0, 0.0))


# ---- idiosyncratic RISK axis + suggested position size (T5) -----------------
# Compose the per-name risk descriptors (each VALIDATED as risk, not return) into one 0..1
# idio-risk, then a SUBTRACT-ONLY tax on the composite (never divide — comp_z is a signed z
# near 0, so 1/risk would explode/invert and destroy the honest tiering) + a bounded 1/risk
# suggested position size. Extension dominates (the only hard per-name DD finding); gex is a
# noisy single-name sign so it is small. risk_idio re-orders WITHIN a tier, never alone flips
# a leader to low (cap 0.5 < macro 0.8 < a typical band gap).
_IDIO_W = {"ext": 0.38, "cycle": 0.27, "lottery": 0.20, "gex": 0.10, "fragility": 0.05}
_IDIO_TAX_MAX = 0.5
_KNIFE_R = {"none": 0.0, "watch": 0.2, "elevated": 0.55, "high": 0.85}


@functools.lru_cache(maxsize=1)
def _gex_gate_scored() -> bool:
    """GEX may enter the per-stock SCORE only after scripts/validate_gex.py writes
    data/gex/gate.json with scored=true (the gamma regime beat a forward realized-vol
    null on its own accrued history). Absent / closed -> display-only, honoring the repo's
    validate-before-weight doctrine (cf. engine/vol_regime.load_gate). Cached: the gate
    cannot change mid-build. Until it opens, GEX carries zero weight and zero entry tilt."""
    try:
        from lib import config
        p = config.data_dir() / "gex" / "gate.json"
        if p.exists():
            return bool(json.loads(p.read_text()).get("scored", False))
    except Exception:  # noqa: BLE001 — a missing/broken gate must never break scoring
        pass
    return False


@functools.lru_cache(maxsize=1)
def _iv_spread_gate_scored() -> bool:
    """IV-spread confirmer may enter the score only after validate_options_ivspread.py
    writes data/options_ivspread/validation_gate.json with scored=true. Until then
    it is display-only. Cached: gate cannot change mid-build."""
    try:
        from lib import config
        p = config.data_dir() / "options_ivspread" / "validation_gate.json"
        if p.exists():
            return bool(json.loads(p.read_text()).get("scored", False))
    except Exception:  # noqa: BLE001
        pass
    return False


def _risk_idio(rec: dict) -> tuple[float, dict]:
    """0..1 idiosyncratic risk + the present components (renormalized over what is present)."""
    comps: dict[str, float] = {}
    ext = rec.get("ext") or {}
    ez = _f(ext.get("ext_z")); pv = _f((rec.get("tech") or {}).get("pct_vs_200dma"))
    if ez is not None or pv is not None:
        rex = max(_clip01((ez - 0.5) / 1.5) if ez is not None else 0.0,
                  _clip01((pv - 25.0) / 20.0) if pv is not None else 0.0)
        if ext.get("grade") == _PARABOLIC:
            rex = max(rex, 0.9)
        elif ext.get("grade") == "stretched":
            rex = max(rex, 0.5)
        comps["ext"] = rex
    kn = (rec.get("ladder") or {}).get("bc_knife")
    if kn in _KNIFE_R:
        comps["cycle"] = _KNIFE_R[kn]
    lm = _f(rec.get("lottery_max"))
    if lm is not None:
        comps["lottery"] = _clip01((lm - _LOTTERY_WARN) / (_LOTTERY_HARD - _LOTTERY_WARN))
    # GEX as a REALIZED-VOL / gap-risk read (distinct from the directional confirmer): short
    # gamma or a vol-hole EXPANSION = amplified moves = higher gap risk; a deep long-gamma pin =
    # suppressed vol = low risk; a coiled band is armed gap risk. Reads the joined confirmer
    # levels (rich), else the raw gamma sign (back-compat). A neutral regime is no longer silent.
    # GATED (validate-before-weight): contributes to the score only once validate_gex.py opens
    # data/gex/gate.json; until then GEX stays display-only and never touches the tiering.
    if _gex_gate_scored():
        _gc_lv = (rec.get("gex_confirm") or {}).get("levels") or {}
        _regime = _gc_lv.get("regime") or (rec.get("gex") or {}).get("gamma_regime")
        _vh = _gc_lv.get("vol_hole_state")
        if _vh == "EXPANSION" or _regime == "short":
            comps["gex"] = 0.6
        elif _vh in ("COILED_UP", "COILED_DOWN"):
            comps["gex"] = 0.4
        elif _regime == "long":
            comps["gex"] = 0.1
        elif _regime is not None or _vh is not None:
            comps["gex"] = 0.3
    if rec.get("fragility"):
        comps["fragility"] = 0.5
    if not comps:
        return 0.0, {}
    num = sum(_IDIO_W[k] * v for k, v in comps.items())
    den = sum(_IDIO_W[k] for k in comps)
    return _clip01(num / den), {k: round(v, 2) for k, v in comps.items()}


# ---- forward EVENT-calendar risk (T7) --------------------------------------
# A name with a BINARY event imminent (its next earnings report) carries gap risk no setup
# can price away — so SIZE DOWN ahead of it. This is RISK management, not a return forecast
# (and not a composite/rank tax — the risk is transient, gone after the print): it feeds the
# suggested SIZE + a caution + (the day before) blocks a "high-conviction" verb. Graceful:
# `earnings_days` absent -> 0 (no effect), so it lights up only where the calendar is known.
def _event_risk(rec: dict) -> float:
    d = _f(rec.get("earnings_days"))
    if d is None or d < 0 or d > 8:
        return 0.0
    return 0.8 if d <= 1 else 0.5 if d <= 3 else 0.3 if d <= 5 else 0.15


_SIZE_BUCKETS = [(0.66, "quarter", 25), (0.40, "half", 50), (0.20, "three-quarter", 75)]
# canonical size ladder, for mapping a conviction-capped pct back to a bucket label
_PCT_BUCKET = {0: "avoid", 25: "quarter", 50: "half", 75: "three-quarter", 100: "full"}
# The cycle/timing call is the BINDING cap on size. A partial-conviction entry
# (HALF SIZE = the daily turn is in but the weekly hasn't confirmed) — or a
# not-yet-triggered watch/wait — must never display a fuller size than the entry
# itself implies, even when the name's risk budget alone would allow more. This is
# the contradiction users hit: "Suggested size · Full size 100%" beside a
# "HALF SIZE" entry tag. Subtract-only, like every other size gate here.
# Keyed on the entry TAG (not urgency — urgency is many-to-one over cap tiers: 'now' spans both
# the uncapped BUY NOW and the capped HALF SIZE, 'caution' spans TAKE PROFITS/DON'T CHASE/etc., so
# an urgency key would either cap full-size buys or miss DON'T CHASE). Every cap SUBTRACTS from full;
# BUY NOW/HOLD are intentionally uncapped (full conviction), SELL-REDUCE/AVOID size to 0 via the
# blocked gate. "DON'T CHASE" is the extension-gate override tag (engine/cycles.py:1028) — a
# missed-entry chase that is NOT cycle-blocked, so without an explicit cap its risk budget could
# read fuller than the timing warrants. (See test_entry_size_cap_covers_all_tags.)
_ENTRY_SIZE_CAP = {"HALF SIZE": 50, "BUY SOON": 50, "WATCH": 50, "WAIT": 25,
                   "TAKE PROFITS": 25, "UNCONFIRMED — HIGH RISK": 25, "DON'T CHASE": 25}


def _suggested_size(risk_total: float, *, blocked: bool, market: str,
                    validated: bool, conviction_cap: int | None = None) -> dict:
    """Bounded, monotone-decreasing-in-risk position-size guidance. All gates SUBTRACT from
    full; none inflate. Honest: 'context' (risk-budgeting), not a claimed alpha bet.

    ``conviction_cap`` is the cycle/timing read's ceiling (e.g. a weekly-unconfirmed
    HALF SIZE → 50): the risk budget can size DOWN from it but never above it, so the
    suggested size and the entry call can't contradict each other."""
    if blocked:
        return {"bucket": "avoid", "pct": 0, "risk": round(risk_total, 2),
                "note": "cycle/extension blocks a buy"}
    bucket, pct = "full", 100
    for thr, b, p in _SIZE_BUCKETS:
        if risk_total >= thr:
            bucket, pct = b, p
            break
    if market.upper() == "HK" and pct > 50:          # HK is a screen, never a full buy
        bucket, pct = "half", 50
    out = {"bucket": bucket, "pct": pct, "risk": round(risk_total, 2),
           "tier": "validated" if validated else "context"}
    # the cycle/timing read caps the size: never show a fuller position than the
    # entry call (e.g. a weekly-unconfirmed HALF SIZE) actually warrants.
    if conviction_cap is not None and pct > conviction_cap:
        out["bucket"] = _PCT_BUCKET.get(conviction_cap, out["bucket"])
        out["pct"] = conviction_cap
        out["capped_by_entry"] = True
    return out


# ---- bounded technical CONFIRMERS for the entry axis (display/verifier, small by design) ----
# These are NOT selection alpha — they sharpen the ENTRY (timing) ONLY, only where the data
# exists, and never rescue a blocked name (the cycle/extension block cap still binds). Kept
# deliberately small so a confirmer can only NUDGE conviction, never manufacture it — the
# GEX / volatility-black-hole confirmer doctrine (research/US_STOCKS_OVERHAUL §3).
def _trend_quality_tilt(tech: dict | None) -> float | None:
    """ADX-confirmed trend quality: a strong directional trend supports the entry; a choppy,
    no-trend tape damps it. Needs ADX (OHLC names) → None for close-only names."""
    if not tech:
        return None
    adx = _f(tech.get("adx14"))
    if adx is not None and adx >= 25.0:
        d = tech.get("adx_trend")
        if d == "up":
            return 0.25
        if d == "down":
            return -0.25
    chop = _f(tech.get("chop14"))
    if chop is not None and chop >= 61.8:      # high choppiness = no trend = damp the entry
        return -0.15
    return None


def _vol_squeeze_tilt(vs: dict | None) -> float | None:
    """The single-stock volatility black hole as a TIMING tilt. Phase-0 (reports/
    US_STOCKS_SIGNALS_PHASE0.md) found the BARE squeeze has NO forward-move edge — only a
    VOLUME-CONFIRMED break is directional — so a still-coiled name gets NO tilt (display only);
    the tilt rewards a confirmed upside break / penalises a downside break, with late expansion
    a mild caution."""
    if not vs:
        return None
    state = vs.get("state")
    if state == "FIRED_UP":
        return 0.4 if vs.get("volume_confirmed") else 0.2
    if state == "FIRED_DOWN":
        return -0.4
    if state == "EXPANSION":
        return -0.15
    return None                       # COILED / COMPRESSED / NONE -> display only, no entry tilt


def _gex_confirm_tilt(gc: dict | None) -> float | None:
    """Dealer-gamma confirmer as a bounded entry tilt: CONFIRM nudges up, CAUTION nudges down,
    NEUTRAL/absent is no tilt. Bounded so options positioning can only verify, never pick."""
    if not gc:
        return None
    v = gc.get("verdict")
    if v == "confirm":
        return 0.3
    if v == "caution":
        return -0.3
    return None


def _axis_entry(rec: dict) -> tuple[float | None, list[str], bool]:
    """Entry/timing axis + whether the cycle/extension BLOCKS a buy (caps the axis).

    Three-tier aggregation (the dilution fix): the BASE timing tilts (urgency, pullback tag,
    drawdown-from-high, RSI band) are AVERAGED; the bounded technical CONFIRMERS (trend-quality,
    vol-squeeze, GEX) are ADDED as one clipped ±0.5 nudge (so a CONFIRM always lifts and a
    CAUTION always trims, never diluted by — and never dominating — the base); the HARD penalties
    (own-history extension grade, the absolute over-200dma stretch, the radioactive one-day
    spike) are SUMMED on top, so a real penalty is never averaged away by a good urgency read."""
    present: list[str] = []
    lad = rec.get("ladder") or {}
    entry = (lad.get("entry") or {})
    tech = rec.get("tech") or {}
    ext = rec.get("ext") or {}

    base: list[float] = []
    urg = entry.get("urgency")
    if urg in _URG_Z:
        base.append(_URG_Z[urg]); present.append("urgency")
    tag = rec.get("alpha_entry")
    if tag in _ENTRY_TAG_Z:
        base.append(_ENTRY_TAG_Z[tag]); present.append("pullback/extended")
    dh = _drawdown_hump(_f(tech.get("off_52w_high_pct")))
    if dh is not None:
        base.append(dh); present.append("off-high")
    rb = _rsi_band(_f(tech.get("rsi14")))
    if rb is not None:
        base.append(rb); present.append("rsi")

    # bounded technical CONFIRMERS — one clipped additive nudge (never the selection edge)
    conf = 0.0
    tq = _trend_quality_tilt(tech)
    if tq is not None:
        conf += tq; present.append("trend-quality")
    vq = _vol_squeeze_tilt(rec.get("vol_squeeze"))
    if vq is not None:
        conf += vq; present.append("vol-squeeze")
    # GATED (validate-before-weight): the GEX entry tilt is applied only once data/gex/gate.json
    # is open; until then options positioning stays display-only and never nudges the entry axis.
    gq = _gex_confirm_tilt(rec.get("gex_confirm")) if _gex_gate_scored() else None
    if gq is not None:
        conf += gq; present.append("options")
    # NOTE: the forward-cone risk SHAPE (anticipation asymmetry) is deliberately NOT a scored entry
    # confirmer. It was added under the AVGO/NVDA alignment work but routes an explicitly "NO-GO for
    # size" / coin-flip-direction signal into the decision; it now lives ONLY as a display-only
    # honesty note in conviction_profile (surfacing a favourable cone without moving the score).
    conf = float(np.clip(conf, -_ENTRY_CONFIRM_CAP, _ENTRY_CONFIRM_CAP))

    hard: list[float] = []
    grade = ext.get("grade")
    if grade in _EXT_PENALTY:               # own-history extension PENALTY (never a positive add)
        hard.append(_EXT_PENALTY[grade]); present.append("extension")
    sp = _stretch_penalty(_f(tech.get("pct_vs_200dma")))   # absolute distance above the 200dma
    if sp is not None and sp < 0:
        hard.append(sp); present.append("over-200dma")
    lp = _lottery_penalty(rec)                             # recent radioactive one-day spike
    if lp < 0:
        hard.append(lp); present.append("lottery-spike")

    _has = bool(base) or conf != 0.0 or bool(hard)
    z = ((_mean_avail(base) or 0.0) + conf + sum(hard)) if _has else None
    # hard-block: downtrend / topping / exit / avoid / parabolic / OVER-EXTENDED (a chase)
    state = (lad.get("state") or "").upper()
    blocked = (state in _CYCLE_BLOCK_STATES or urg in _BLOCK_URGENCY
               or grade == _PARABOLIC or _overextended(rec))
    if blocked and z is not None:
        z = min(z, _ENTRY_CAP_Z)
    # scale the small tilts up toward ~unit z for the composite
    return _clipz(z * 1.6 if z is not None else None), present, blocked


def _axis_tailwind(rec: dict) -> tuple[float | None, list[str]]:
    """Sector + thematic tailwind — a declared SECTOR-LEVEL tilt (small weight 0.10).

    The SPOTLIGHT leg (engine.spotlight) is the scored theme-reco + sector-stage tilt in
    [-1, 1]; it is the modern channel and SUPERSEDES the raw basket.rel20 / sector-RS legs
    when present, so the macro+crowding-gated theme verdict isn't double-counted against the
    raw 20d momentum it replaces. The older legs remain as graceful fallbacks for markets /
    runs that pass no spotlight. The spotlight reaching here is already over-extension-clamped
    (see _eff_spotlight), so a hot theme can never reward a chase."""
    present: list[str] = []
    parts: list[float | None] = []
    sp = _f((rec.get("spotlight") or {}).get("z"))     # declared theme+sector tilt in [-1,1]
    if sp is not None:
        parts.append(float(np.clip(sp, -1.0, 1.0)) * _SPOTLIGHT_LEG_GAIN); present.append("spotlight")
    else:                                              # fallbacks (non-US / no theme intel)
        srs = rec.get("sector_rs") or {}
        pct = _f(srs.get("pct"))
        if pct is not None:                            # 0..100 sector-RS percentile
            parts.append((pct - 50.0) / 25.0); present.append("sector-RS")
        bk = rec.get("basket") or {}
        rel = _f(bk.get("rel20"))                      # basket 20d return vs benchmark (%)
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

    # prefer a precomputed orthogonal composite; else mean of the DURABILITY legs only.
    # FIX (AVGO/NVDA alignment): the fallback used to average in `value` (cheapness) and
    # `low_vol` (the low-volatility anomaly) — neither is durability. Blending them mis-scored
    # expensive, volatile GROWTH LEADERS (AVGO, NVDA) on the quality axis for being correctly
    # expensive/volatile (a value/vol read leaking into 'will the business survive'). The axis
    # now uses only profitability + the quality (ROE/accruals/leverage) composite, matching the
    # docstring's stated DURABILITY intent. (value/low_vol still live in the factor board.)
    qc = _f(rec.get("quality_context_z"))
    if qc is None:
        fac = rec.get("factor") or {}
        qc = _mean_avail([_f(fac.get(k)) for k in ("profitability", "quality")])
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


def verdict(axes: dict, rec: dict, market: str, *, cycle_blocked: bool,
            risk_stress: float = 0.0, valuation: dict | None = None,
            validated: bool = False) -> dict:
    """Map the axes + cycle state to a single honest headline verb (EN + 中文),
    plus drivers/cautions. First-match-wins; the cycle block and accounting/parabolic
    flags OVERRIDE any 'Buy' wording so a card never says BUY next to EXIT. A stressed
    macro tape (risk_stress) vetoes a 'high-conviction' verb on an AGGRESSIVE entry."""
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
    # cautions carry BOTH languages ({"en","zh"}); _v() splits them into the
    # `cautions` / `cautions_zh` lists the templates render as l-en/l-zh spans.
    cautions: list[dict] = []

    def _cau(en: str, zh: str) -> None:
        cautions.append({"en": en, "zh": zh})

    if sel_t in ("high", "mid"):
        drivers.append((axes.get("selection", {}).get("kind")) or _SEL_KIND.get(m, ("edge", "优势"))[0])
    if _tier(ent) in ("high", "mid"):
        drivers.append("entry")
    if _tier(qz) in ("high", "mid"):
        drivers.append("quality")
    if _tier(axes.get("tailwind", {}).get("z")) in ("high", "mid"):
        drivers.append("tailwind")
    if acct == "warn":
        _cau("accounting warn", "财务质量警示")
    elif acct == "watch":
        _cau("accounting watch", "财务质量关注")
    if grade == _PARABOLIC:
        _cau("parabolic — extended", "抛物线急涨 — 过热")
    _ovx = _overextended(rec)
    if _ovx:
        _pv = _f((rec.get("tech") or {}).get("pct_vs_200dma"))
        _cau(f"extended +{_pv:.0f}% over 200dma — chasing" if _pv is not None
             else "extended over 200dma — chasing",
             f"高于200日均线 +{_pv:.0f}% — 追高" if _pv is not None
             else "高于200日均线 — 追高")
    # forward-aware valuation caveat — a non-veto chip, never a blocking verb. Only
    # the 'extreme' tail trips watch (and trailing-only names are light-touch), so a
    # growth leader cheap on forward earnings (NVDA) never reads 'expensive'.
    if valuation and valuation.get("watch"):
        _cau(f"richly valued — {valuation.get('note')}",
             f"估值偏高 — {valuation.get('note_zh') or valuation.get('note')}")
    _risk_veto = (risk_stress >= _RISK_VETO_STRESS and _aggressiveness(rec) >= 0.5)
    if _risk_veto:
        _cau("stressed tape — size down / confirm", "盘面承压 — 减仓／确认")
    _ed = _f(rec.get("earnings_days"))
    _earn_imminent = _ed is not None and 0 <= _ed <= 8
    if _earn_imminent:
        _cau(f"earnings in {int(_ed)}d — binary event, size down"
             if _ed >= 1 else "earnings imminent — binary event, size down",
             f"{int(_ed)}天后财报 — 二元事件，减仓"
             if _ed >= 1 else "财报临近 — 二元事件，减仓")
    if cycle_blocked:
        _lbl = lad.get("label") or state or "weak tape"
        _lbl_zh = "盘面疲弱" if _lbl == "weak tape" else _i18n.tr(_lbl)
        _cau("cycle: " + _lbl, "周期：" + _lbl_zh)

    # ---- HK: never a buy verb. Screen / exposure language only, but NAME the driver. ----
    if m == "HK":
        lead = rec.get("hk_edge_lead")            # the dominant HK-native leg (set by the build)
        # flow/value/exposure CONFIRMER language — never "buy", never a validated-pick claim.
        # "standout" is reserved for the relative-strength lead (a price-leadership descriptor).
        _HK_LEAD = {
            "southbound": ("Mainland is accumulating — flow screen",
                           "南向资金加仓 — 资金筛选"),
            "ah_value": ("Cheap H vs its A twin — value screen",
                         "H 较 A 股折价 — 价值筛选"),
            "bnrs": ("Relative-strength standout — screen, not a validated pick",
                     "相对强度突出 — 筛选项，非已验证买入"),
            "fit": ("Well-positioned for the regime — exposure screen",
                    "契合当前周期 — 敞口筛选"),
        }
        if sel_t == "low":
            return _v("Lagging — relative weakness", "落后 — 相对弱势", drivers, cautions)
        # only crown a named-lead screen when the overall selection actually leans positive
        # (high/mid) — a flat-conviction name isn't a "screen pick" on one soft leg alone.
        if sel_t in ("high", "mid") and lead in _HK_LEAD:
            en, zh = _HK_LEAD[lead]
            return _v(en, zh, drivers, cautions)
        if sel_t == "high":
            return _v("Relative-strength standout — screen, not a validated pick",
                      "相对强度突出 — 筛选项，非已验证买入", drivers, cautions)
        return _v("Exposure name — context only", "敞口标的 — 仅供参考", drivers, cautions)

    # ---- CN: a CYCLE-ANCHORED read (owner call). The A-share book's validated edge is
    # mean-reversion TIMING, which the cycle ladder already expresses (FRESH BUY fires off a
    # washout, TOP WATCH near a high). So the verb LEADS with the cycle/entry state — coherent
    # with the Entry gauge AND the sector-cycle basket read — and the reversal/selection z only
    # GRADES conviction (a confluence bonus); it never flips a clean buy to "lagging". This ends
    # the cn_brokers complaint: a hot basket's FRESH-BUY leaders read "Buy zone", not "Lagging —
    # relative weakness", and an overbought leader at a high reads "Extended", not "downtrend".
    if m == "CN":
        if cycle_blocked:
            # an UPSIDE extreme (overbought top / parabolic / far above the 200dma) is
            # "extended", NOT a downtrend; only a genuine DOWNSIDE tape avoids.
            extended = (state == "TOP WATCH" or grade == _PARABOLIC or _ovx
                        or rec.get("alpha_entry") == "extended")
            if extended:
                return _v("Extended — wait for a pullback", "过度拉伸 — 等待回撤", drivers, cautions)
            if state == "ROLLING OVER":
                return _v("Topping — take profits, don't add", "见顶回落 — 止盈勿加", drivers, cautions)
            return _v("Downtrend — avoid", "下行趋势 — 回避", drivers, cautions)
        rev_strong = sel_t in ("high", "mid")           # reversal/selection confluence
        if acct == "warn":
            return _v("Verify accounting before buying", "买入前先核实财务质量", drivers, cautions)
        if state in ("FRESH BUY", "TURN SIGNALED"):
            if _ed is not None and 0 <= _ed <= 1:        # binary event tomorrow
                return _v("Buy zone · earnings imminent — wait or size down",
                          "买入区 · 财报临近 — 等待或减小仓位", drivers, cautions)
            if _risk_veto:                               # QVIX-panic tape vetoes a clean chase
                return _v("Buy zone · stressed tape — smaller size, confirm",
                          "买入区 · 盘面承压 — 减小仓位并确认", drivers, cautions)
            if rev_strong:                               # cycle turn AND the reversal edge agree
                return _v("Reversal buy — washed out and turning up",
                          "反转买点 — 超跌企稳上行", drivers, cautions)
            return _v("Buy zone — cycle turning up", "买入区 — 周期上行", drivers, cautions)
        if state == "RALLY ON":
            return _v("Uptrend — hold, add on dips", "上行趋势 — 持有，回调加仓", drivers, cautions)
        if state == "BOTTOM WATCH":
            if rev_strong:
                return _v("Basing near a low — reversal setting up",
                          "底部区域 — 反转酝酿", drivers, cautions)
            return _v("Basing near a low — get ready", "底部区域 — 准备就绪", drivers, cautions)
        if state == "COUNTERTREND BOUNCE":
            return _v("Countertrend bounce — not a base yet", "反弹 — 尚未筑底", drivers, cautions)
        if rev_strong:                                   # no clear cycle state, but reversal likes it
            return _v("Reversal candidate — selection edge", "反转候选 — 选股优势", drivers, cautions)
        if sel_t == "low":                               # ran up — reversal edge spent (NOT "weak vs index")
            return _v("Ran hot — limited reversal edge", "涨幅已大 — 反转空间有限", drivers, cautions)
        return _v("Neutral — no clear edge", "中性 — 无明显优势", drivers, cautions)

    # ---- cycle hard-block: never 'Buy' regardless of the composite ----------
    if cycle_blocked:
        # WHY blocked? An UPSIDE extreme (overbought top / parabolic / far above the 200dma)
        # is "extended — wait for a pullback", NOT a downtrend. Only a genuine DOWNSIDE tape
        # (DECLINE / ROLLING OVER / exit-avoid urgency) reads "avoid/downtrend". Without this
        # split, a low-selection name at an overbought HIGH (TOP WATCH) was mislabeled "Avoid —
        # downtrend" — the exact opposite of its state (masked on US where momentum-selection and
        # the momentum cycle agree in sign; unmasked on a reversal-led book).
        extended = (state == "TOP WATCH" or grade == _PARABOLIC or _ovx
                    or rec.get("alpha_entry") == "extended")
        if extended:
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
        if _ed is not None and 0 <= _ed <= 1:  # binary event tomorrow — not high-CONVICTION
            return _v("Leader · earnings imminent — wait or size down",
                      "领先 · 财报临近 — 等待或减小仓位", drivers, cautions)
        if _risk_veto:                         # stressed tape vetoes a high-conviction CHASE
            return _v("Strong name · elevated-risk tape — smaller size, confirm",
                      "强势个股 · 高风险行情 — 减小仓位并确认", drivers, cautions)
        if _tier(qz) == "low":                 # strong edge but weak fundamentals — flag the risk
            _cau("weak fundamentals", "基本面偏弱")
            return _v("Leader · weak fundamentals — higher-risk",
                      "领先 · 基本面偏弱 — 风险偏高", drivers, cautions)
        if acct == "watch":                    # an accounting WATCH never reads a clean high-conviction
            return _v("Leader · accounting watch — confirm before adding",
                      "领先 · 财务质量关注 — 加仓前先确认", drivers, cautions)
        # Two-gauge wording: the conviction verb describes OWNERSHIP quality only —
        # the entry-timing claim ("good entry") now lives on the separate Entry gauge,
        # so this no longer mislabels a leader-with-a-bad-entry. And it is
        # VALIDATION-GATED: until the time-machine proves forward edge, it reads
        # 'high-confluence (context)', not the over-confident 'high-conviction'.
        if validated:
            return _v("High-conviction leader", "高确信 领先", drivers, cautions)
        return _v("High-confluence leader (context)",
                  "高共振 领先（参考）", drivers, cautions)
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


def _v(en: str, zh: str, drivers: list[str], cautions: list[dict]) -> dict:
    return {"verdict": en, "verdict_zh": zh, "drivers": drivers,
            "cautions": [c["en"] for c in cautions],
            "cautions_zh": [c["zh"] for c in cautions]}


# ----------------------------------------------------------------------------
# the public per-name entry point
# ----------------------------------------------------------------------------
_BANDS = [(80, "high", "High conviction", "高确信"),
          (60, "constructive", "Constructive", "建设性"),
          (40, "neutral", "Neutral", "中性"),
          (0, "low", "Low", "偏弱")]

# NON-US single-stock score is a WITHIN-MARKET percentile RANK (score_percentiles), so the band
# word must read as a RANK, never absolute conviction — otherwise the card shows "96/100 High
# conviction" next to an independently-derived "Neutral — no clear edge" verdict (the A-share
# complaint). Same band KEYS (so the CSS colour is unchanged), rank-framed WORDS. US keeps its
# absolute words (it has the name-rank lane + the rank honesty-note below).
_BANDS_RANK = [(80, "high", "Top rank", "板内领先"),
               (60, "constructive", "Upper rank", "板内偏上"),
               (40, "neutral", "Mid-pack", "板内居中"),
               (0, "low", "Lower rank", "板内偏弱")]


def _band(score: int | None, market: str = "US") -> dict:
    if score is None:
        return {"band": "na", "en": "—", "zh": "—"}
    bands = _BANDS if (market or "US").upper() == "US" else _BANDS_RANK
    for lo, key, en, zh in bands:
        if score >= lo:
            return {"band": key, "en": en, "zh": zh}
    lo, key, en, zh = bands[-1]
    return {"band": "low", "en": en, "zh": zh}


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
    # spotlight tilt — neutralize a positive tilt on any name the entry gate BLOCKS (over-extended,
    # downtrend/rolling-over/top-watch, parabolic, exit/avoid) before it reaches the tailwind axis:
    # a hot theme must never reward a chase OR a broken tape. Carry the effective block on rec so
    # the axis + the displayed conviction.spotlight + the size trim all read one consistent value.
    eff_sp = _eff_spotlight(rec, blocked=blocked)
    if eff_sp is not None:
        rec = {**rec, "spotlight": eff_sp}
    tw_z, tw_present = _axis_tailwind(rec)
    q_z, q_present, q_flags = _axis_quality(rec, m)
    # forward-aware valuation: a SUBTRACT-ONLY haircut on the quality axis (never a
    # bonus, never a veto). Keys on FORWARD P/E where present so a growth leader cheap
    # on forward earnings (NVDA ~16x fwd) is NOT penalized for a rich trailing multiple.
    val = _valuation.read(rec)
    if val:
        q_z = _valuation.apply_haircut(q_z, val)
        if q_z is not None:
            q_present = q_present or ["valuation"]
            if "valuation" not in q_present:
                q_present = [*q_present, "valuation"]

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

    # macro/event RISK OVERLAY (T3): subtract-only haircut on a CHASE into a stressed tape.
    overlay = ctx.get("risk_overlay") or {}
    stress = _macro_stress(overlay)
    rtax = _risk_tax(overlay, rec)
    # idiosyncratic RISK axis (T5): a second subtract-only haircut from the per-name risk
    # descriptors (extension / knife / lottery / gex / fragility). Re-orders WITHIN a tier.
    idio, idio_comps = _risk_idio(rec)
    idio_tax = _IDIO_TAX_MAX * idio
    if comp_z is not None:
        comp_z = float(np.clip(comp_z - rtax - idio_tax, -_AXIS_Z_CLIP, _AXIS_Z_CLIP))
    # forward EVENT risk (imminent earnings) — feeds SIZE only, not the composite rank (it is
    # transient). risk_total = worst-of the distinct failure modes (structural / macro / event).
    event = _event_risk(rec)
    if event > 0:
        idio_comps = {**(idio_comps or {}), "event": round(event, 2)}
    # out-of-play SIZE trim: when BOTH theme & sector lean out of play (blended spotlight z
    # below the knee), step suggested SIZE down (raise risk_total). Asymmetric — a positive
    # spotlight never raises size (the narrative can shrink a bet, never inflate it). Does NOT
    # touch comp_z, so it never re-ranks; it only sizes a surviving buy more conservatively.
    sp_z = _f((eff_sp or {}).get("z"))
    oop_risk = (_clip01((-sp_z - _OOP_KNEE) / (1.0 - _OOP_KNEE)) * _OOP_SIZE_MAX
                if (sp_z is not None and sp_z < -_OOP_KNEE) else 0.0)
    if oop_risk > 0:
        idio_comps = {**(idio_comps or {}), "out_of_play": round(oop_risk, 2)}
    # VALIDATED narrative-basket trend-gate de-risk (subtract-only; never re-ranks selection):
    # a name whose basket is below its long trend / fading / deteriorating is sized down.
    basket_hc, basket_cau = _basket_risk(rec)
    if basket_hc > 0:
        idio_comps = {**(idio_comps or {}), "basket_trend": round(basket_hc, 2)}
    risk_total = max(idio, stress * _aggressiveness(rec), event, oop_risk, basket_hc)

    # score: prefer the within-market percentile passed by the panel builder; else
    # the logistic skin (per-name fallback, flagged approximate).
    score = ctx.get("score_pct")
    if score is None:
        score = _logistic_0_100(comp_z)
    score = int(round(score)) if score is not None else None

    vb = verdict(axes, rec, m, cycle_blocked=blocked, risk_stress=stress,
                 valuation=val, validated=bool(ctx.get("gate_go")))
    if basket_cau:                       # surface the validated basket-trend de-risk as a caution
        vb["cautions"].append(basket_cau["en"])
        vb["cautions_zh"].append(basket_cau["zh"])
    band = _band(score, m)

    # --- honesty NOTES (AVGO/NVDA alignment): make the two places a user gets confused explicit.
    notes: list[dict] = []
    # (1) the SCORE is a within-board PERCENTILE rank; the VERDICT is an absolute-tier read. When a
    # name ranks top-of-board (band high/constructive) but the verb isn't "high-conviction" (its
    # selection z hasn't cleared the absolute bar — the NVDA 97-vs-"Constructive" case), say so, so
    # "97" is never misread as an absolute 97/100 conviction.
    # Fires when a top-of-board RANK is NOT a clean high-conviction buy: either the selection
    # z hasn't cleared the absolute bar (NVDA-97-vs-Constructive), OR the cycle blocks a buy
    # (a high-selection name in a bad tape — the exact case this used to exclude).
    if band["band"] in ("high", "constructive") and score is not None \
            and (_tier(sel_z) not in ("high",) or blocked):
        notes.append({
            "kind": "rank",
            "en": "Score is a within-board percentile RANK (top of today's board), not an absolute "
                  "0-100 conviction — the verdict reflects the absolute read"
                  + (", which here BLOCKS a buy (wait for a base)." if blocked else "."),
            "zh": "评分为板内百分位排名（今日榜单靠前），并非绝对的 0-100 确信度——结论反映绝对读数"
                  + ("，此处结论为暂不买入（等待筑底）。" if blocked else "。")})
    # (2) the forward risk-cone is favourable but the conviction score is muted — surface the
    # 'high upside / low downside' the factor axes don't capture (the AVGO complaint).
    _ah = ((rec.get("anticipation") or {}).get("horizons") or {}).get("medium") or {}
    _aidx = _f((rec.get("anticipation") or {}).get("anticipation_index"))
    _mfe, _dd = _f(_ah.get("mfe_med")), _f(_ah.get("dd_avg"))
    if (_aidx is not None and _aidx >= 65 and not _ah.get("thin") and _mfe and _dd and _dd != 0
            and (_mfe / abs(_dd)) >= 1.5 and (score is None or score < 65)):
        notes.append({
            "kind": "anticipation",
            "en": f"Forward risk cone is favourable (≈{_mfe:.0f}% median upside vs ≈{abs(_dd):.0f}% "
                  "average drawdown) — a constructive risk SHAPE the factor axes don't price.",
            "zh": f"前瞻风险锥形态有利（中位上行约 {_mfe:.0f}% 对平均回撤约 {abs(_dd):.0f}%）——"
                  "因子维度未计入的有利风险形态。"})

    # provenance — what is present vs missing, never read missing as neutral.
    all_legs = {"selection": sel_present, "entry": ent_present,
                "tailwind": tw_present, "quality": q_present}
    present = sorted({leg for ls in all_legs.values() for leg in ls})
    n_axes = sum(1 for k in axes if axes[k]["z"] is not None)

    return {
        "score": score,
        "band": band["band"], "band_en": band["en"], "band_zh": band["zh"],
        "composite_z": round(comp_z, 3) if comp_z is not None else None,
        "risk": {"total": round(risk_total, 2), "idio": round(idio, 2),
                 "components": idio_comps or None,
                 "macro_stress": round(stress, 2) if stress > 0 else None,
                 "macro_tax": round(rtax, 3) if rtax > 0 else None,
                 "idio_tax": round(idio_tax, 3) if idio_tax > 0 else None,
                 "drivers": overlay.get("drivers") if stress > 0 else None},
        "size": _suggested_size(
            risk_total, blocked=blocked, market=m,
            validated=bool(ctx.get("gate_go")),
            conviction_cap=_ENTRY_SIZE_CAP.get(
                ((rec.get("ladder") or {}).get("entry") or {}).get("tag"))),
        "verdict": vb["verdict"], "verdict_zh": vb["verdict_zh"],
        "drivers": vb["drivers"], "cautions": vb["cautions"],
        "cautions_zh": vb["cautions_zh"],
        "trust_tier": trust_tier(m, bool(ctx.get("gate_go"))),
        # validation status the card badge + Mastermind gating key on: 'positive_ic'
        # once the time-machine proves forward edge (gate GO), else 'neutral_ic' — the
        # honest "ensemble context, not a validated probability" state (P4 sets this).
        "validation_status": "positive_ic" if ctx.get("gate_go") else "neutral_ic",
        "regime": _regime_tilt(m, calm),
        "spotlight": eff_sp,          # theme+sector narrative tilt (display chip + tailwind leg)
        # primary NARRATIVE BASKET allocation/trend-gate state — de-blurs GICS for the card AND
        # for Mastermind (it sees "Memory leadership, in book" vs "Non-AI Software, below-trend"),
        # and drove the validated size de-risk above (idio_comps.basket_trend).
        "basket_alloc": rec.get("basket_alloc"),
        "axes": axes,
        # the two new VERIFIERS, surfaced for the card chips (display; they also fed a small
        # bounded tilt into the entry axis above — never the selection rank).
        # W6-US fix 4: attach gate_scored to GEX and IV-spread chips so the template can
        # hide them when the gate is scored:false (unvalidated — accruing history).
        "gex_confirm": {**(rec.get("gex_confirm") or {}),
                        "gate_scored": _gex_gate_scored()} if rec.get("gex_confirm") else None,
        "vol_squeeze": rec.get("vol_squeeze"),
        # Cremers-Weinbaum call−put IV-spread confirmer (directional options lean) — DISPLAY-ONLY
        # context; unlike the gex tilt it does NOT yet touch the score (gated on
        # validate_options_ivspread earning a verdict — the chain panel is still accruing).
        # W6-US fix 4: iv_spread gate_scored from its own validation_gate.json.
        "iv_spread_confirm": ({**(rec.get("iv_spread_confirm") or {}),
                               "gate_scored": _iv_spread_gate_scored()}
                              if rec.get("iv_spread_confirm") else None),
        "notes": notes or None,       # honesty notes: percentile-rank caveat + favourable-cone read
        "n_axes": n_axes,
        "cycle_blocked": blocked,
        # multi-timeframe bottoming-ALIGNMENT (engine.cycles.mtf_alignment) — the
        # standout-strip selection gate: aligned = weekly not-falling + 3-day nearing
        # a bullish cross + daily just-crossed/about-to. Surfaced here so every board's
        # rows carry it via the attached conviction (display chip + the buyable filter).
        "alignment": (rec.get("ladder") or {}).get("alignment"),
        "valuation_band": (val or {}).get("band"),
        "valuation_watch": bool((val or {}).get("watch")),
        "valuation_note": (val or {}).get("note"),
        "valuation_note_zh": (val or {}).get("note_zh"),
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
                  spotlight: dict | None = None, basket_alloc: dict | None = None,
                  asym: dict | None = None, ext: dict | None = None,
                  lottery_max: float | None = None,
                  earnings_days: float | None = None) -> dict:
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
        "sector_rs": sector_rs, "basket": basket, "spotlight": spotlight,
        "basket_alloc": basket_alloc,      # primary-basket allocation/trend-gate state (validated de-risk)
        "factor": {"value": legs.get("value"), "profitability": legs.get("profitability"),
                   "quality": legs.get("quality"), "low_vol": legs.get("low_vol")} if legs else None,
        "quality_context_z": quality_context_z,
        "sue": sue, "sue_fresh_days": sue_fresh_days, "lottery_max": lottery_max,
        "earnings_days": earnings_days,
        "insider_bps": insider_bps, "revision_z": revision_z,
        "fund_priors": {"z": fund_priors_z} if fund_priors_z is not None else None,
        "asym": asym,                      # downside-asymmetry DISPLAY read (risk shape, not scored)
        "accounting": record.get("accounting_quality"),
        # dealer-gamma + single-stock volatility black hole — VERIFIERS/CONFIRMERS (display +
        # bounded entry-timing tilt, never selection alpha). Previously `gex` was dropped here,
        # so the idio GEX leg was dead — these passthroughs revive + extend it.
        "gex": record.get("gex"),
        "gex_confirm": record.get("gex_confirm"),
        "vol_squeeze": record.get("vol_squeeze"),
        "iv_spread": record.get("iv_spread"),              # CW call−put IV spread (display)
        "iv_spread_confirm": record.get("iv_spread_confirm"),
        # forward anticipation cone — its risk-SHAPE asymmetry feeds a bounded entry tilt + a
        # display note (the 'high upside / low downside' the score used to ignore); direction is
        # never bet (p_up ~ coin-flip).
        "anticipation": record.get("anticipation"),
    }


def attach_panel_scores(profiles: dict[str, dict], market: str = "US") -> None:
    """Given {ticker: conviction_block} for ONE market, set each block's display
    ``score`` to the within-market cross-sectional percentile of its ``composite_z``
    (the honest, comparable-within-market skin) and refresh the band. Mutates in
    place. Blocks with no composite keep their per-name logistic fallback. ``market``
    selects the band wording — non-US gets rank-framed words (the score IS a rank)."""
    zs = {t: b.get("composite_z") for t, b in profiles.items()
          if b.get("composite_z") is not None}
    if len(zs) < 5:
        return
    s = pd.Series(zs)
    pct = score_percentiles(s)
    for t, p in pct.items():
        blk = profiles[t]
        blk["score"] = int(p)
        bnd = _band(int(p), market)
        blk["band"], blk["band_en"], blk["band_zh"] = bnd["band"], bnd["en"], bnd["zh"]
