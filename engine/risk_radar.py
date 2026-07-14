"""Risk Radar v2 — a regime-typed, EVIDENCE-GATED, genuinely-leading market-risk engine.

WHY THIS REPLACES risk_state v1
-------------------------------
A 68-event backtest (research/RISK_ENGINE_V2_FINDINGS.md) proved the v1 composite
REACTS: its one real edge (the abs>=60 band, 2.9x lift 2006-2019) is DEAD in the
modern era (0.68x in 2020-2026) — overfit to the old regime — and its keystone
breadth leg self-cancels the instant price drops. Re-scoring ~20 candidates under a
STRICT bar (day-level forward lift + frequency-matched permutation + a 2020+ holdout)
killed the popular signals (VIX-term ROC, SKEW, VVIX, put/call-proxy, VRP = noise).

ONLY a handful survive, and they cluster by SCARE PHYSICS — which is why this engine
is REGIME-TYPED. Each scare-type's sub-score is built ONLY from signals that passed
the strict bar, weighted by their measured 2020+ lift:

  credit   — HY OAS 21d ROC (raw spread velocity; 1.94x, ERA-ROBUST. NB the credit
             *composite* drawdown_risk LAGS; the raw ROC leads — different things).
  rates    — MOVE (rate-vol) level (1.83x in 2020+; regime-dependent).
  bubble   — SPY parabolicity (dist > 200dma) + leadership concentration (SMH/SPY);
             2.06x in 2020+ — the strongest MODERN-era precursor (the 2026-06 case).
  growth   — defensives outperforming (XLU/SPY) + cyclical/defensive rolldown
             (XLY/XLP); 1.7-1.9x in 2020+.
  vol      — VIX9D/VIX3M term level (WEAK, 1.44x) — the only backtestable vol leg.
             The genuinely-leading vol/positioning precursors (put/call, dealer GEX,
             implied correlation) are NOT in deep history yet -> Tier-B (display +
             escalator-only) until their collectors accrue, then gated like the rest.

HONESTY: the surviving edge is MODEST — ~1.5-2x conditional lift, not a forecast.
Elevated => ~20-26% chance of a >=8% drawdown onset within ~3 weeks vs ~12% base,
with real false positives. So the engine is LOUD + EARLY (high recall, by request)
but every alert carries its MEASURED lift/lead, a forward-outcome log grades every
call, and an Opus review loop (engine/risk_radar_review.py) retunes the thresholds
from its own mistakes. The de-risk response is SIZING, not selection. The validated
regime quad is untouched.

All signals are CAUSAL/leak-free (trailing-window percentiles). No public function
raises into the build.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from engine.indicators import pct_rank_window
from lib import config, store

log = logging.getLogger(__name__)

_PCT_WIN = 504          # ~2y trailing causal percentile window
_PCT_MINP = 63
_FLOW_MIN_HISTORY = 252  # put/call & GEX legs stay INERT until this many rows accrue (deep history
                         # is not freely available, so they validate FORWARD via the Opus loop)

# --- VSB W6 Tier-B leg constants (calibration-overlay-able) -----------------
# corr_floor_break: COR1M floor-then-spike CONFIRMER.
#   _CORR_WINDOW:        rolling window for 20-session min (the "floor" base)
#   _CORR_HIST_WIN:      trailing history window for percentile distributions
#   _CORR_HIST_MINP:     min rows before any percentile is computed
#   _CORR_BASE_PCT_THR:  base must be in the BOTTOM N% of its 252d distribution to qualify
#   _CORR_RISE_PCT_THR:  rise must be in the TOP M% of the 252d rise distribution to qualify
#   _CORR_MIN_HISTORY:   minimum rows in the COR1M series before the leg activates
_CORR_WINDOW = 20          # rolling window for base = min(prior 20 sessions)
_CORR_HIST_WIN = 252       # trailing distribution window for base-pctile and rise-pctile
_CORR_HIST_MINP = 63       # min valid obs before pctile is usable
_CORR_BASE_PCT_THR = 10.0  # bottom 10th pctile of 252d trailing base = "extreme floor"
_CORR_RISE_PCT_THR = 90.0  # top 90th pctile of 252d trailing rises = "significant spike"
_CORR_MIN_HISTORY = 252    # inert until this many COR1M rows are available

# ai_breadth_divergence: |spread_50| extreme vs its own trailing 252d 90th-pctile.
_AI_BREADTH_MIN_HISTORY = 252  # inert while obs < 252 (young series; expected for months)
_AI_BREADTH_HIST_WIN = 252     # trailing distribution window for abs(spread_50) pctile
_AI_BREADTH_PCT_THR = 90.0     # |spread_50| must exceed its own 90th trailing pctile to fire

# --- C3 global-breadth Tier-B leg (INTL Fix Masterplan §5 C3, CONFIRMED #938) --------------
# % of the country ETFs in data/intl_etf/ above their 200dma → causal 504d percentile of
# (-breadth), so HIGH value = LOW breadth = danger (the same "risk-rising" convention as
# every other leg here). This is the exact validated C3 construction (DSR 0.9326, orthogonality
# 62% surviving-fraction vs SPY/HY/curve; reports/intl-global-breadth-phase0.md). It rides as
# Tier-B (display/escalator-only) — it never ORIGINATES a US state; it can only escalate a hot
# Tier-A read, then a FORWARD-outcome log grades it before it is ever trusted (measured-weights,
# not priors — masterplan §4.1). READ NOTE: risk_radar imports NOTHING from the intl modules
# (leaf-purity in intl_feed is a separate contract); it reads data/intl_etf/ directly through
# lib.config, exactly as it reads every other leg through lib.store.
_GB_ETF_DIR = "intl_etf"      # data/intl_etf/*.parquet — the W0 country-ETF substrate (23 ETFs)
_GB_MA_WIN = 200              # 200dma per the C3 spec
_GB_PANEL_MIN = 10            # <10 alive ETFs on the last date → the leg zeroes itself (thin-panel)
_GB_STALE_DAYS = 8            # last ETF obs older than this → the leg zeroes itself (stale store)
_GB_VALIDATION_REF = ("C3 global-breadth barometer — reports/intl-global-breadth-phase0.md "
                      "(CONFIRMED #938: DSR 0.9326, orthogonality 62% vs SPY/HY/curve, cap 0.20 "
                      "de-risk-only). Tier-B: display/escalator-only, forward-graded before trusted.")

# Per-leg calibration FROM THE STRICT RE-VALIDATION (research/RISK_ENGINE_V2_FINDINGS.md §8).
# lift_2020 = measured day-level forward-lift in the 2020-2026 holdout at thr_pct; lead_d = typical
# lead. These are DISPLAYED next to every alert (honest odds) and are the starting calibration the
# Opus review loop (data/risk_radar/calibration.json) is allowed to retune within bounds.
_LEG_CALIB = {
    # lift_2020 = measured day-level forward-lift in the 2020+ holdout (committed gate,
    # engine.risk_radar_backtest.gate_report, thr_pct). VALIDATED = lift_2020 >= 1.2.
    "credit_oas_roc":   {"lift_2020": 1.23, "lift_full": 1.76, "lead_d": 10, "thr_pct": 0.90, "era_robust": True},
    "credit_hyg_tlt":   {"lift_2020": 0.50, "lift_full": 0.83, "lead_d": 8,  "thr_pct": 0.90, "era_robust": False},
    "rates_move":       {"lift_2020": 1.52, "lift_full": 1.83, "lead_d": 15, "thr_pct": 0.90, "era_robust": False},
    "rates_realrate":   {"lift_2020": 1.02, "lift_full": 1.44, "lead_d": 12, "thr_pct": 0.90, "era_robust": False},
    "bubble_ext":       {"lift_2020": 2.34, "lift_full": 1.00, "lead_d": 10, "thr_pct": 0.90, "era_robust": False},
    "bubble_leadership":{"lift_2020": 0.38, "lift_full": 0.85, "lead_d": 12, "thr_pct": 0.90, "era_robust": False},
    "growth_defensives":{"lift_2020": 1.62, "lift_full": 0.78, "lead_d": 12, "thr_pct": 0.90, "era_robust": False},
    "growth_cyc_def":   {"lift_2020": 1.63, "lift_full": 1.41, "lead_d": 12, "thr_pct": 0.90, "era_robust": False},
    "vol_term":         {"lift_2020": 0.44, "lift_full": 0.85, "lead_d": 8,  "thr_pct": 0.90, "era_robust": False},
    # Tier-B flow legs — accruing forward, NOT yet backtestable (lift_2020 unknown -> stays unvalidated
    # until the Opus loop gates them on realized outcomes once mature). thr_pct provisional.
    "vol_putcall":      {"lift_2020": None, "lift_full": None, "lead_d": 5, "thr_pct": 0.85, "era_robust": False, "accruing": True},
    "vol_gex":          {"lift_2020": None, "lift_full": None, "lead_d": 3, "thr_pct": 0.85, "era_robust": False, "accruing": True},
    # Tier-B GLOBAL breadth leg — CONFIRMED as a de-risk edge in its OWN phase-0 (C3, DSR 0.9326
    # vs SPX, orthogonal to the domestic legs), but its lift AS A US-RADAR LEG has not yet been
    # graded on this engine's forward-outcome log — so it enters accruing (lift_2020 unknown),
    # display/escalator-only, never a US-state originator, until the audit loop matures it.
    "global_breadth":   {"lift_2020": None, "lift_full": None, "lead_d": 21, "thr_pct": 0.70, "era_robust": False, "accruing": True},
    # --- VSB W6 Tier-B accruing legs (masterplan §5/W6 + §6) -----------------------------------
    # corr_floor_break: implied-correlation floor-then-spike detector (COR1M, data/cboe/cor1m.parquet).
    # CONFIRMER of a break in progress, NOT a lead — correlation begins rising after hedging demand
    # already built. Tier-B / vol scare. lift_2020=None (accruing; forward-graded via Opus loop).
    # Detection: (base_pctile <= 10th AND rise_pctile >= 90th) over trailing 252d distributions.
    # Percentile thresholds live in _CORR_FLOOR_BASE_PCT / _CORR_FLOOR_RISE_PCT (overlay-able).
    "corr_floor_break":     {"lift_2020": None, "lift_full": None, "lead_d": 0,  "thr_pct": 0.85,
                             "era_robust": False, "accruing": True, "display_only": True,
                             "note": "CONFIRMER (not lead): COR1M extreme-low floor then spike; "
                                     "deeplink vol scare. Forward-graded before trusted. "
                                     "display_only=True: STRUCTURALLY UNABLE to move scare tier "
                                     "until gauntlet-promoted (VSB W6 doctrine)."},
    # ai_breadth_divergence: |spread_50| extreme (AI-cohort vs non-AI pct-above-50dma spread).
    # Source: data/breadth/breadth_split.parquet 'spread_50'. Inert while obs < 252 (young series).
    # Tier-B / internals scare. lift_2020=None (accruing).
    "ai_breadth_divergence":{"lift_2020": None, "lift_full": None, "lead_d": 5,  "thr_pct": 0.85,
                             "era_robust": False, "accruing": True, "display_only": True,
                             "note": "AI vs non-AI breadth extreme divergence; Tier-B internals. "
                                     "Inert while data/breadth/breadth_split.parquet obs < 252. "
                                     "display_only=True: STRUCTURALLY UNABLE to move scare tier "
                                     "until gauntlet-promoted (VSB W6 doctrine)."},
    # --- RRX masterplan §4B W3 Tier-B accruing legs (scripts/study_rrx_tierb_phase0.py) ----------
    # nh_contraction: pct_rank_window(-nh_share_21d, 504) on near-high (SPY >= 0.98×252d-max) days,
    # 0.0 elsewhere.  Phase-0 measured: lift_full=0.275, lift_2020=0.000, fire_rate=0.0107,
    # perm_p=0.978 — NULL at strict bar (near-high mask + contraction combo rarely fires in 2020+
    # holdout). Q4 52wk-window seasonality caveat on nh window. 2010/2011 false-negatives on record.
    # Realistic ceiling: permanent confluence input under the 'internals' Tier-B scare; can escalate
    # a hot Tier-A bubble read but CANNOT originate state. Come-back 2026-10-15.
    "nh_contraction":   {"lift_2020": 0.0,   "lift_full": 0.275, "lead_d": 15, "thr_pct": 0.85, "era_robust": False, "accruing": True},
    # jpy_carry: -(DEXJPUS/DEXJPUS.shift(10)-1) gated to 0 when DEXJPUS >= 50d MA → causal 504d pctile.
    # Phase-0 measured: lift_full=1.188, measured_lift_2020=1.450, fire_rate=0.0961, perm_p=0.036 — PASS.
    # lift_2020 kept None (matching all other Tier-B accruing legs) so _is_validated returns False
    # and jpy_carry stays out of the CI validated-leg gate — its accruing=True / Tier-B status means
    # it must never be able to red the validated-leg evidence gate via a future live-data shift.
    # Measured 1.45 recorded above as measured_lift_2020 (non-gating).
    # Joins the 'global' scare (weight 0.3) as a complementary carry-stress channel alongside
    # global_breadth (weight 0.7). 2022 sign-inversion documented: in a pure Fed-hike regime,
    # USD/JPY weakness ≠ risk-off — WHY it is Tier-B escalator-only (never originates state).
    "jpy_carry":        {"lift_2020": None,  "measured_lift_2020": 1.450, "lift_full": 1.188, "lead_d": 5,  "thr_pct": 0.85, "era_robust": False, "accruing": True},
}
_VALIDATED_MIN = 1.20   # a leg is a real LEADING leg only if its 2020+ lift clears this


def _is_validated(leg: str, calib: dict | None = None) -> bool:
    lc = (calib or {"legs": _LEG_CALIB})["legs"].get(leg, {})
    return float(lc.get("lift_2020") or 0.0) >= _VALIDATED_MIN


# scare-type -> {tier, legs:[(leg, weight)]}. Sub-score = weighted mean of leg causal-percentiles*100.
# Tier A = has >=1 VALIDATED leading leg, drives the loud alert. Tier B = display/escalator-only
# (no leg clears the strict bar yet — e.g. vol needs deep options-flow data; it can escalate a hot
# Tier-A state but never originate one). Weak legs kept as low-weight corroborators, not drivers.
_SCARES = {
    "credit":  {"tier": "A", "legs": [("credit_oas_roc", 0.85), ("credit_hyg_tlt", 0.15)]},
    "rates":   {"tier": "A", "legs": [("rates_move", 0.80), ("rates_realrate", 0.20)]},
    "bubble":  {"tier": "A", "legs": [("bubble_ext", 0.85), ("bubble_leadership", 0.15)]},
    "growth":  {"tier": "A", "legs": [("growth_defensives", 0.50), ("growth_cyc_def", 0.50)]},
    # vol = Tier-B (display/escalator-only). vol_term is weak; vol_putcall/vol_gex are INERT until
    # mature then auto-join (they're absent from leading_signals() until >=_FLOW_MIN_HISTORY rows).
    # VSB W6 ADDITIVE: corr_floor_break (weight 1.0) added; existing leg weights UNCHANGED.
    # subscore_series renormalizes over AVAILABLE legs — corr_floor_break is absent when
    # data/cboe/cor1m.parquet is missing (degrade-don't-crash).
    "vol":     {"tier": "B", "legs": [("vol_term", 0.5), ("vol_putcall", 0.3), ("vol_gex", 0.2),
                                      ("corr_floor_break", 1.0)]},
    # global = Tier-B (display/escalator-only). The C3 global-breadth barometer (INTL-38): the US
    # book's window into the cross-market breadth channel. It carries a de-risk edge ORTHOGONAL to
    # the domestic legs (C3 verdict), but rides Tier-B so it can only escalate a hot Tier-A read,
    # never originate a US state on its own — and it accrues a forward-outcome log first. Its single
    # leg is absent from leading_signals() when data/intl_etf is stale (>8d) or thin (<10 ETFs).
    # RRX §4B W3: jpy_carry (weight 0.3) added as a carry-stress channel alongside global_breadth
    # (weight 0.7). Both Tier-B accruing; jpy_carry PASS at phase-0 (lift_2020=1.45, p=0.036).
    "global":  {"tier": "B", "legs": [("global_breadth", 0.7), ("jpy_carry", 0.3)]},
    # internals = Tier-B (display/escalator-only). NH-contraction at fresh highs: index near 252d
    # high while the fraction of members making new 52wk highs contracts vs recent peaks. Distinct
    # from the killed continuous breadth_div self-canceller — this is event-conditioned narrowing.
    # RRX masterplan §4B R1. Phase-0 NULL (lift_2020=0.0, perm_p=0.978) — retained as confluence
    # input per context-accrual law (kills are construction-specific; null ≠ worthless). Can escalate
    # a hot Tier-A bubble read but CANNOT originate state. Come-back 2026-10-15.
    # VSB W6 ADDITIVE: ai_breadth_divergence (weight 1.0) added alongside nh_contraction (1.0).
    # subscore_series renormalizes over AVAILABLE legs by the sum of their weights — both legs carry
    # weight 1.0; the sub-score is their available-weighted mean. ai_breadth_divergence is inert
    # while obs < 252 (absent from leading_signals); nh_contraction behavior is UNCHANGED when
    # ai_breadth_divergence is absent (the renormalization only applies to present legs).
    "internals": {"tier": "B", "legs": [("nh_contraction", 1.0), ("ai_breadth_divergence", 1.0)]},
}
_SCARE_LABEL = {
    "credit":    ("Credit stress", "信用压力"),
    "rates":     ("Rates / inflation shock", "利率/通胀冲击"),
    "bubble":    ("Bubble / blow-off unwind", "泡沫/见顶回吐"),
    "growth":    ("Growth scare / defensive rotation", "增长恐慌/防御轮动"),
    "vol":       ("Volatility event", "波动率事件"),
    "global":    ("Global breadth breakdown", "全球广度破位"),
    # RRX masterplan §4B R1 — Tier-B accruing; display/escalator only
    "internals": ("Breadth internals deterioration", "内部广度恶化"),
}

# LOUD + EARLY tiers on the 0-100 sub-score scale. CALIBRATED via a band sweep vs forward
# drawdowns (the naive 45/58/70/85 fired ~81% of days in 2020+ = useless precision; the MAX-of-4
# sub-score inflates the scale). 65/78/87/93 cuts the 2020+ fire-rate ~81%->45% while LIFTING
# precision (0.21->0.30) and keeping high recall (~0.75) — F1 0.35->0.43. Interim default;
# the FP/sensitivity tuning workflow + the Opus self-correction loop refine per scare-type via
# data/risk_radar/calibration.json. Still loud+early (watch/caution fire early; elevated = the
# loud banner).
_DEFAULT_BANDS = {"watch": 55.0, "caution": 68.0, "elevated": 78.0, "risk_off": 88.0}
_STATE_ORDER = ["calm", "watch", "caution", "elevated", "risk-off"]
_ALERT_FROM = "elevated"            # loud banner fires at/above this

# ESCALATING calibrated probability: P(SPY >= 5% pullback within H business days | state),
# MEASURED on 2006-2026 (full-history blended with the 2020+ holdout, monotonic at the top
# where the edge is real; lower bands ~= base ~17.8% @ h21). The probability RISES as the
# state climbs AND as more scare-types fire together (conjunction) — proven in
# research/RISK_ENGINE_V2_FINDINGS.md / /tmp/riskbt/escalation.py. The Opus review loop is
# allowed to retune this surface from the realized forward-outcome log.
_PROB_CAL = {
    # bumped at elevated/risk-off to match the now-context-GATED state (3x more informative; tuning §)
    "h5":  {"calm": 0.02, "watch": 0.02, "caution": 0.03, "elevated": 0.05, "risk-off": 0.08},
    "h10": {"calm": 0.06, "watch": 0.06, "caution": 0.08, "elevated": 0.12, "risk-off": 0.17},
    "h21": {"calm": 0.13, "watch": 0.13, "caution": 0.16, "elevated": 0.25, "risk-off": 0.33},
}
_PROB_BASE = {"h5": 0.036, "h10": 0.086, "h21": 0.178}   # unconditional base rates
# extra probability when MANY scare-types fire together (independent monotonic effect, measured),
# applied per hot Tier-A scare beyond the first, scaled by horizon, capped.
_CONJ_BUMP = {"h5": 0.012, "h10": 0.020, "h21": 0.030}
# SINGLE SOURCE (P2-B' risk unification, audit #4): the shared-band magnitudes (caution /
# elevated / risk_off / floor) are DERIVED from engine.regime_one.RISK_STATE_GROSS, the one
# versioned table, so risk_radar can never emit a competing gross for a shared state. It adds
# ONLY 'watch'=0.97 above the shared four (its own earliest tier). Byte-identical to the prior
# literal {watch:0.97, caution:0.90, elevated:0.78, risk_off:0.60, floor:0.50}.
def _gross_from_source() -> dict:
    from engine.regime_one import RISK_STATE_GROSS, _GROSS_FLOOR
    return {"watch": 0.97, "caution": RISK_STATE_GROSS["caution"],
            "elevated": RISK_STATE_GROSS["elevated"], "risk_off": RISK_STATE_GROSS["risk-off"],
            "floor": _GROSS_FLOOR}


_GROSS = _gross_from_source()

_DISCLAIMER = ("Evidence-gated leading-risk radar (research/RISK_ENGINE_V2_FINDINGS.md). "
               "Edge is MODEST (~1.5-2x conditional lift, not a forecast) and LOUD+EARLY by "
               "design — every alert prints its measured lift/lead, a forward-outcome log grades "
               "every call, and the Opus review loop retunes from its mistakes. De-risk = sizing, "
               "not selection; the validated regime quad is untouched.")


# --- config / calibration overlay --------------------------------------------
def _calib(root=None) -> dict:
    """Merge the baked calibration with the Opus-tuned overlay (data/risk_radar/calibration.json),
    which the self-correction loop writes within bounds. Overlay can adjust bands + per-leg thr_pct
    + scare weights; never adds/removes legs."""
    base = {"bands": dict(_DEFAULT_BANDS), "legs": {k: dict(v) for k, v in _LEG_CALIB.items()},
            "scares": {k: {"tier": v["tier"], "legs": list(v["legs"])} for k, v in _SCARES.items()},
            "prob_cal": {h: dict(v) for h, v in _PROB_CAL.items()}, "alert_from": _ALERT_FROM}
    try:
        from pathlib import Path
        base_dir = config.data_dir() if root is None else (Path(root) / "data")
        p = base_dir / "risk_radar" / "calibration.json"
        if p.exists():
            ov = json.loads(p.read_text())
            base["bands"].update(ov.get("bands") or {})
            for leg, d in (ov.get("legs") or {}).items():
                if leg in base["legs"]:
                    base["legs"][leg].update(d)
            for h, d in (ov.get("prob_cal") or {}).items():
                if h in base["prob_cal"]:
                    base["prob_cal"][h].update(d)
            base["alert_from"] = ov.get("alert_from", base["alert_from"])
    except Exception as e:  # noqa: BLE001
        log.warning("risk_radar: calibration overlay read failed: %s", e)
    return base


# --- leading signal series (causal, leak-free) -------------------------------
def _s(group, name, col="close"):
    df = store.read(group, name)
    if df is None:
        return None
    c = col if col in df.columns else df.columns[0]
    x = df[c].dropna()
    x.index = pd.to_datetime(x.index)
    return x.sort_index()


def _roc(s, n):
    return (s / s.shift(n) - 1.0) if s is not None else None


def _global_breadth_raw() -> pd.Series | None:
    """Causal global-breadth series: fraction of the data/intl_etf/ country ETFs above their
    200dma on each date (NaN where fewer than _GB_PANEL_MIN ETFs are alive). This is the exact
    validated C3 construction (reports/intl-global-breadth-phase0.md). Reads the parquet store
    directly through lib.config — NO import of any intl module (risk_radar is a leaf w.r.t. them).
    Returns None (leg absent) when the store is missing, thin, or stale so the leg fails soft."""
    try:
        etf_dir = config.data_dir() / _GB_ETF_DIR
        if not etf_dir.exists():
            return None
        frames: list[pd.Series] = []
        for p in sorted(etf_dir.glob("*.parquet")):
            try:
                df = pd.read_parquet(p, columns=["close"])
            except Exception:  # noqa: BLE001 — a bad file drops out of the panel, never crashes
                continue
            s = df["close"].dropna()
            if len(s) < _GB_MA_WIN:
                continue
            s.index = pd.to_datetime(s.index)
            ma = s.rolling(_GB_MA_WIN, min_periods=int(_GB_MA_WIN * 0.75)).mean()
            frames.append((s > ma).astype(float))
        if not frames:
            return None
        panel = pd.concat(frames, axis=1, sort=False)
        panel.index = pd.to_datetime(panel.index)
        panel = panel.sort_index()
        alive = panel.notna().sum(axis=1)
        # STALE guard: if the last observation is older than the SLA, the leg zeroes itself
        # (the store went stale; do not carry a frozen breadth read forward into a live radar).
        last_obs = panel.index.max()
        if (pd.Timestamp.today().normalize() - last_obs).days > _GB_STALE_DAYS:
            return None
        # THIN-PANEL guard: on the LAST date we need >=_GB_PANEL_MIN alive ETFs, else the read is
        # too sparse to trust — zero the whole leg (never emit a value off a shrunken panel).
        if int(alive.iloc[-1]) < _GB_PANEL_MIN:
            return None
        breadth = panel.mean(axis=1).where(alive >= _GB_PANEL_MIN)   # NaN before the panel fills
        return breadth.dropna()
    except Exception as e:  # noqa: BLE001 — additive; a store hiccup must not break the radar
        log.warning("risk_radar global-breadth leg read failed: %s", e)
        return None


# --- VSB W6 helpers ----------------------------------------------------------

def _midrank_pctile_series(series: pd.Series, window: int) -> pd.Series:
    """Trailing midrank percentile: (count_less + 0.5*count_equal) / n * 100.

    Tie-robust: a frozen/constant feed scores 50 (neutral) rather than 100.
    Mirrors engine/vol_velocity._trailing_pctile exactly — use that function when
    importing it cleanly.  This replicates the same kernel for in-file use.
    See engine/vol_velocity._trailing_pctile for the canonical reference.
    """
    if len(series) < window:
        return pd.Series(np.nan, index=series.index)
    return series.rolling(window, min_periods=window).apply(
        lambda w: (float(np.sum(w < w[-1])) + 0.5 * float(np.sum(w == w[-1])))
        / len(w) * 100,
        raw=True,
    )


def detect_corr_floor_break(
    cor1m: pd.Series,
    *,
    corr_window: int = _CORR_WINDOW,
    hist_win: int = _CORR_HIST_WIN,
    base_pct_thr: float = _CORR_BASE_PCT_THR,
    rise_pct_thr: float = _CORR_RISE_PCT_THR,
) -> bool:
    """Return True when the COR1M floor-then-spike condition fires on the LATEST row.

    CONFIRMER (not lead): this detects a break already in progress — correlation
    begins rising after hedging demand has built.  Do NOT use it as a leading indicator.

    Condition (ALL relative, zero absolute anchors):
      base[t]   = min(COR1M over prior 20 sessions)    <- rolling 20-session floor
      rise[t]   = COR1M[t] - base[t]                  <- how much it rose off the floor
      base_pctile = midrank percentile of base over trailing 252d
      rise_pctile = midrank percentile of rise over trailing 252d

    FIRE when: base_pctile <= base_pct_thr   (extreme-low floor, bottom N%)
           AND rise_pctile >= rise_pct_thr   (significant spike off that floor, top M%)

    Both thresholds are calibration-overlay-able via the constants above.
    Absent-safe: returns False if series is too short or all-NaN.
    """
    s = cor1m.dropna()
    if len(s) < _CORR_MIN_HISTORY:
        return False
    # base = min over prior 20 sessions (trailing, causal)
    base = s.rolling(corr_window, min_periods=corr_window).min()
    # rise = latest close minus its own floor
    rise = s - base
    # midrank percentiles over trailing hist_win
    base_pct = _midrank_pctile_series(base, hist_win)
    rise_pct = _midrank_pctile_series(rise, hist_win)
    bp = base_pct.dropna()
    rp = rise_pct.dropna()
    if bp.empty or rp.empty:
        return False
    return bool(bp.iloc[-1] <= base_pct_thr and rp.iloc[-1] >= rise_pct_thr)


def build_corr_floor_break(cor1m: pd.Series) -> pd.Series:
    """COR1M floor-then-spike Tier-B leg (VSB W6).

    Returns a causal binary-valued series (0.0 or 1.0) on the COR1M index.
    A value of 1.0 means the CONFIRMER condition fires on that day.

    NOTE: this series is 0/1 — it is NOT a causal percentile like most radar legs.
    It plugs into leading_signals() and the subscore treats 1.0 as the fully-hot
    reading (equivalent to pctile=1.0 on the 0-1 scale used by pcol()).  The
    Tier-B / accruing status (lift_2020=None) means it can NEVER originate state.

    CONFIRMER (not lead): correlation begins rising AFTER hedging demand builds.
    This is a confirms-stress-underway signal, not a precursor.
    """
    s = cor1m.dropna()
    if len(s) < _CORR_MIN_HISTORY:
        return pd.Series(dtype=float, name="corr_floor_break")
    base = s.rolling(_CORR_WINDOW, min_periods=_CORR_WINDOW).min()
    rise = s - base
    base_pct = _midrank_pctile_series(base, _CORR_HIST_WIN)
    rise_pct = _midrank_pctile_series(rise, _CORR_HIST_WIN)
    cond = (base_pct <= _CORR_BASE_PCT_THR) & (rise_pct >= _CORR_RISE_PCT_THR)
    return cond.astype(float).rename("corr_floor_break")


def build_ai_breadth_divergence(spread_50: pd.Series) -> pd.Series:
    """AI breadth divergence Tier-B leg (VSB W6).

    |spread_50| >= its own trailing-252d 90th midrank percentile of |spread_50|.

    spread_50 = ai_pct50 - nonai_pct50 (% of AI vs non-AI stocks above 50dma).
    A large absolute divergence (either direction) signals an unusual cohort split.

    INERT while obs < _AI_BREADTH_MIN_HISTORY (252) — expected for months as the
    series is newly computed nightly.  Returns empty Series when inert.

    Returns a causal binary-valued series (0.0 or 1.0).
    """
    s = spread_50.dropna()
    if len(s) < _AI_BREADTH_MIN_HISTORY:
        # young series — inert and silent (no log spam)
        return pd.Series(dtype=float, name="ai_breadth_divergence")
    abs_s = s.abs()
    abs_pct = _midrank_pctile_series(abs_s, _AI_BREADTH_HIST_WIN)
    # fire when |spread_50| >= its own 90th trailing pctile
    cond = abs_pct >= _AI_BREADTH_PCT_THR
    return cond.astype(float).rename("ai_breadth_divergence")


def build_nh_contraction(spy: pd.Series, breadth_df: "pd.DataFrame") -> "pd.Series":
    """NH-contraction Tier-B leg (RRX masterplan §4B R1).

    pct_rank_window(-nh_share_21d, 504) on near-high days (SPY >= 0.98 * rolling 252d max),
    0.0 elsewhere. Near-high mask makes the signal event-conditioned — it fires only when the
    index is at/near a 252d high while internal breadth (% of members at new 52wk highs) is
    contracting, a topping narrowing read.

    Caveats: Q4 52wk-window seasonality — nh counts are naturally elevated in Q4 (bias toward
    false-silence during genuine market topping). 2010/2011 false-negatives on record (Fed-put
    support). Phase-0 measured NULL (lift_2020=0.0, perm_p=0.978) — retained as confluence
    input. Tier-B: display/escalator only under 'internals' scare; CANNOT originate state.

    Single source: scripts/study_rrx_tierb_phase0.py imports this function — no study/engine drift.
    """
    idx = spy.index
    nh = breadth_df["nh"].astype(float).reindex(idx).ffill()
    nm = breadth_df["n_members"].astype(float).reindex(idx).ffill().replace(0, float("nan"))
    nh_share = nh / nm
    nh_share_21d = nh_share.rolling(21, min_periods=10).mean()
    # near-high mask: causal (trailing only)
    roll_max_252 = spy.rolling(252, min_periods=126).max()
    near_high = spy >= 0.98 * roll_max_252
    neg_nh_share = -nh_share_21d
    pctile = pct_rank_window(neg_nh_share, _PCT_WIN)
    leg = pctile.where(near_high, other=0.0)
    return leg.rename("nh_contraction")


def build_jpy_carry(spy: pd.Series, dexjpus: "pd.Series") -> "pd.Series":
    """JPY carry-unwind stress Tier-B leg (RRX masterplan §4B R3).

    -(DEXJPUS/DEXJPUS.shift(10) - 1) gated to 0.0 when DEXJPUS >= 50d MA → causal 504d pctile.
    DEXJPUS = JPY per USD (higher = weaker yen). Falling USD/JPY = yen strengthening = forced
    JPY-funded carry unwind. Negated so RISING stress = RISING percentile (risk-rising convention).
    The 50d-MA regime gate strips safe-haven false positives when USD/JPY is already elevated.

    Caveat: 2022 sign-inversion — in a pure Fed-hiking regime USD/JPY weakness ≠ risk-off (the
    carry was crowded long-USD there). That is WHY this is Tier-B escalator-only; most potent
    with VIX also rising. Phase-0 PASS: lift_2020=1.45, perm_p=0.036, fire_rate=0.096.

    Single source: scripts/study_rrx_tierb_phase0.py imports this function — no study/engine drift.
    """
    idx = spy.index
    x = dexjpus.reindex(idx).ffill()
    ma50 = x.rolling(50, min_periods=25).mean()
    roc10 = x / x.shift(10) - 1.0
    stress = (-roc10).where(x < ma50, other=0.0)
    pctile = pct_rank_window(stress, _PCT_WIN)
    return pctile.rename("jpy_carry")


def leading_signals() -> pd.DataFrame:
    """DataFrame of causal 0-1 'risk-rising' percentiles, one column per leg, on the SPY trading
    calendar. Slower (FRED) series are ffilled onto trading days = causal (carries past forward).
    Every column is a trailing-504d causal percentile so legs are comparable + leak-free."""
    spy = _s("yahoo", "SPY")
    if spy is None or len(spy) < 300:
        return pd.DataFrame()
    idx = spy.index
    out = pd.DataFrame(index=idx)

    def pcol(series):
        if series is None:
            return None
        return pct_rank_window(series.reindex(idx).ffill(), _PCT_WIN)

    # credit
    hy = _s("fred", "BAMLH0A0HYM2", "hy_oas")
    if hy is not None:
        out["credit_oas_roc"] = pcol(hy.diff(21))
    hyg, tlt = _s("yahoo", "HYG"), _s("yahoo", "TLT")
    if hyg is not None and tlt is not None:
        out["credit_hyg_tlt"] = pcol(-(_roc(hyg / tlt, 20)))   # HY underperforming duration = risk
    # rates / inflation
    mv = _s("yahoo", "_MOVE")
    if mv is not None:
        out["rates_move"] = pcol(mv)
    rr = _s("fred", "DFII10", "us10y_real")
    if rr is not None:
        out["rates_realrate"] = pcol(rr.diff(5))               # real-rate jump = duration shock
    # bubble / blow-off
    ext = spy / spy.rolling(200, min_periods=120).mean() - 1.0
    out["bubble_ext"] = pct_rank_window(ext, _PCT_WIN)
    smh = _s("yahoo", "SMH")
    if smh is not None:
        lead = (smh / smh.shift(63)) / (spy / spy.shift(63)) - 1.0   # leadership concentration froth
        out["bubble_leadership"] = pcol(lead)
    # growth / rotation
    xlu, xlp, xly = _s("yahoo", "XLU"), _s("yahoo", "XLP"), _s("yahoo", "XLY")
    if xlu is not None:
        out["growth_defensives"] = pcol(_roc(xlu / spy, 20))   # defensives outperforming = risk
    if xly is not None and xlp is not None:
        out["growth_cyc_def"] = pcol(-(_roc(xly / xlp, 20)))   # cyclical/defensive rolldown = risk
    # vol (weak; the only backtestable vol leg)
    vix, v3m, v9d = _s("yahoo", "_VIX"), _s("yahoo", "_VIX3M"), _s("yahoo", "_VIX9D")
    term = None
    if v9d is not None and v3m is not None:
        term = (v9d / v3m)
    elif vix is not None and v3m is not None:
        term = (vix / v3m)
    if term is not None:
        out["vol_term"] = pcol(term)
    # Tier-B FLOW legs (put/call, dealer GEX): deep history is NOT freely available (CBOE CDN + Yahoo
    # both block it), so these accrue FORWARD via the live collectors and are INERT until mature
    # (>= _FLOW_MIN_HISTORY rows), after which the forward-outcome log + the Opus loop gate them like
    # any other leg. Rising equity put/call = hedging demand building; falling/negative net GEX =
    # dealer short-gamma (reflexive air-pocket). Both leak-free causal percentiles.
    pc = store.read("cboe", "putcall")
    if pc is not None and len(pc) >= _FLOW_MIN_HISTORY and "equity_pc_ratio" in pc.columns:
        out["vol_putcall"] = pcol(pc["equity_pc_ratio"].astype(float))
    gx = store.read("cboe", "gex")
    if gx is not None and len(gx) >= _FLOW_MIN_HISTORY and "net_gex_bn" in gx.columns:
        out["vol_gex"] = pcol(-gx["net_gex_bn"].astype(float))   # negative net GEX = dealer short-gamma
    # Tier-B GLOBAL breadth leg (C3, INTL-38): % of country ETFs > 200dma → causal 504d percentile
    # of (-breadth), so a global breadth COLLAPSE reads high on the same risk-rising scale. Absent
    # (leg simply not added) when the intl_etf store is missing/stale/thin — degrade-don't-crash,
    # exactly like the flow legs above. pcol() ffills the (daily) ETF breadth onto the SPY calendar
    # and takes the causal 504d percentile, matching the C3 spec.
    gb = _global_breadth_raw()
    if gb is not None and len(gb) >= _PCT_MINP:
        out["global_breadth"] = pcol(-gb)
    # --- RRX §4B W3 Tier-B accruing legs (scripts/study_rrx_tierb_phase0.py) -----------------
    # jpy_carry: JPY carry-unwind stress → 'global' scare (weight 0.3 alongside global_breadth 0.7).
    # Phase-0 PASS (lift_2020=1.45, perm_p=0.036). 2022 sign-inversion caveat → Tier-B only.
    # Absent (degrade-don't-crash) when FRED DEXJPUS store is missing.
    dex_df = store.read("fred", "DEXJPUS")
    if dex_df is not None and len(dex_df) >= _PCT_MINP:
        dex_col = dex_df.columns[0]
        dex_s = dex_df[dex_col].dropna()
        dex_s.index = pd.to_datetime(dex_s.index)
        jpy_leg = build_jpy_carry(spy, dex_s)
        jpy_leg_clean = jpy_leg.dropna()
        if len(jpy_leg_clean) >= _PCT_MINP:
            out["jpy_carry"] = jpy_leg.reindex(idx)
    # nh_contraction: breadth internals deterioration at fresh index highs → 'internals' scare.
    # Phase-0 NULL (lift_2020=0.0, perm_p=0.978) — accruing confluence input, Tier-B only.
    # Absent (degrade-don't-crash) when breadth.parquet is missing or lacks 'nh'/'n_members'.
    b_df = store.read("breadth", "breadth")
    if b_df is not None and "nh" in b_df.columns and "n_members" in b_df.columns:
        b_df.index = pd.to_datetime(b_df.index)
        nhc_leg = build_nh_contraction(spy, b_df)
        nhc_leg_clean = nhc_leg.dropna()
        if len(nhc_leg_clean) >= _PCT_MINP:
            out["nh_contraction"] = nhc_leg.reindex(idx)
    # --- VSB W6 Tier-B accruing legs ---------------------------------------------------
    # corr_floor_break: COR1M floor-then-spike CONFIRMER → 'vol' scare.
    # CONFIRMER not lead — fires when correlation starts rising off an extreme low floor.
    # Absent (degrade-don't-crash) when data/cboe/cor1m.parquet is missing or too short.
    try:
        cor1m_df = pd.read_parquet(config.data_dir() / "cboe" / "cor1m.parquet")
        cor1m_s = cor1m_df["close"].dropna()
        cor1m_s.index = pd.to_datetime(cor1m_s.index)
        if len(cor1m_s) >= _CORR_MIN_HISTORY:
            cfb_leg = build_corr_floor_break(cor1m_s)
            cfb_clean = cfb_leg.dropna()
            if len(cfb_clean) >= _CORR_HIST_MINP:
                out["corr_floor_break"] = cfb_leg.reindex(idx)
    except Exception as e:  # noqa: BLE001 — additive; missing file must not break the radar
        log.debug("risk_radar corr_floor_break leg unavailable: %s", e)
    # ai_breadth_divergence: |spread_50| extreme → 'internals' scare.
    # Inert while obs < 252 (young series, expected for months); absent when file missing.
    try:
        bs_path = config.data_dir() / "breadth" / "breadth_split.parquet"
        if bs_path.exists():
            bs_df = pd.read_parquet(bs_path)
            if "spread_50" in bs_df.columns:
                sp50 = bs_df["spread_50"].dropna()
                sp50.index = pd.to_datetime(sp50.index)
                ai_leg = build_ai_breadth_divergence(sp50)
                ai_clean = ai_leg.dropna()
                if len(ai_clean) >= _CORR_HIST_MINP:
                    out["ai_breadth_divergence"] = ai_leg.reindex(idx)
    except Exception as e:  # noqa: BLE001 — additive; missing file must not break the radar
        log.debug("risk_radar ai_breadth_divergence leg unavailable: %s", e)
    return out


def subscore_series(sigs: pd.DataFrame | None = None, calib: dict | None = None) -> pd.DataFrame:
    """Daily 0-100 sub-score per scare-type = weighted mean of available leg percentiles * 100.
    For backtest + history. Renormalizes over available legs."""
    if sigs is None:
        sigs = leading_signals()
    calib = calib or _calib()
    if sigs is None or sigs.empty:
        return pd.DataFrame()
    out = pd.DataFrame(index=sigs.index)
    for scare, spec in calib["scares"].items():
        num = den = None
        for leg, w in spec["legs"]:
            if leg not in sigs.columns:
                continue
            col = sigs[leg].fillna(0.0) * float(w)
            avail = sigs[leg].notna().astype(float) * float(w)
            num = col if num is None else (num + col)
            den = avail if den is None else (den + avail)
        if num is not None:
            out[scare] = (num / den.replace(0, np.nan) * 100.0)
    return out


# --- context gate (the verified #1 false-positive lever) ---------------------
# The LOUD banner (elevated+) fires only when the BROAD market is actually breaking:
# SPY < 200dma AND %>200dma breadth in a low causal percentile (<=0.40). Measured (tuning
# workflow, research/RISK_RADAR_TUNING.md): H21 banner precision 0.085->0.249 (2.9x), fire-rate
# 80%->17%, STRONGER out-of-sample, permutation p=0.0. Below the gate the state is capped at
# 'caution' (the early/quiet tier still shows) — narrow events stay quiet until the broad tape
# confirms (loudly catching narrow events needs the options-flow data of task D). Leak-free/causal.
_GATE_BREADTH_PCT = 0.40


def context_gate_series(idx=None) -> pd.Series:
    """Daily bool: is a LOUD alert permitted (broad market breaking)? True = SPY<200dma AND breadth
    weak. Causal. If idx is given, reindexed onto it (ffill the slower breadth)."""
    spy = _s("yahoo", "SPY")
    if spy is None:
        return pd.Series(dtype=bool) if idx is None else pd.Series(False, index=idx)
    below = spy < spy.rolling(200, min_periods=120).mean()
    gate = below
    b = store.read("breadth", "breadth")
    if b is not None and "pct_above_200" in b.columns:
        bp = pct_rank_window(b["pct_above_200"].astype(float), _PCT_WIN)
        bp.index = pd.to_datetime(bp.index)
        base = below.index if idx is None else idx
        gate = below.reindex(base).fillna(False) & (bp.reindex(base).ffill() <= _GATE_BREADTH_PCT)
    if idx is not None:
        gate = gate.reindex(idx).fillna(False)
    return gate.astype(bool)


def context_gate_live() -> dict:
    """Live context-gate read for compute(): {met, spy_below_200dma, breadth_weak}."""
    out = {"met": False, "spy_below_200dma": None, "breadth_weak": None}
    try:
        spy = _s("yahoo", "SPY")
        if spy is not None and len(spy) >= 200:
            ma = spy.rolling(200, min_periods=120).mean()
            out["spy_below_200dma"] = bool(spy.iloc[-1] < ma.iloc[-1])
        b = store.read("breadth", "breadth")
        if b is not None and "pct_above_200" in b.columns:
            bp = pct_rank_window(b["pct_above_200"].astype(float), _PCT_WIN).dropna()
            out["breadth_weak"] = bool(bp.iloc[-1] <= _GATE_BREADTH_PCT) if len(bp) else None
        out["met"] = bool(out["spy_below_200dma"]) and bool(out["breadth_weak"])
    except Exception as e:  # noqa: BLE001
        log.warning("risk_radar context gate failed: %s", e)
    return out


def flow_status() -> dict:
    """Accrual status of the Tier-B options-flow legs (put/call, dealer GEX). Deep history is not
    freely available, so they accrue forward via the live collectors and ACTIVATE (auto-join the vol
    scare-type, then get gated by the Opus loop) once both reach _FLOW_MIN_HISTORY rows."""
    def _rows(g, n):
        try:
            df = store.read(g, n)
            return 0 if df is None else int(len(df))
        except Exception:  # noqa: BLE001
            return 0
    pc, gx = _rows("cboe", "putcall"), _rows("cboe", "gex")
    return {"min_history": _FLOW_MIN_HISTORY, "putcall_rows": pc, "gex_rows": gx,
            "mature": bool(min(pc, gx) >= _FLOW_MIN_HISTORY),
            "note": ("options-flow vol legs (put/call, GEX) accrue forward — deep history is "
                     "unavailable freely; they activate + self-validate via the Opus loop when mature")}


# --- live snapshot -----------------------------------------------------------
def _band(score: float, bands: dict) -> str:
    if score is None or (isinstance(score, float) and np.isnan(score)):
        return "calm"
    if score >= bands["risk_off"]:
        return "risk-off"
    if score >= bands["elevated"]:
        return "elevated"
    if score >= bands["caution"]:
        return "caution"
    if score >= bands["watch"]:
        return "watch"
    return "calm"


def compute(sigs: pd.DataFrame | None = None, calib: dict | None = None, asof=None,
            gate: dict | None = None) -> dict:
    """Live regime-typed risk snapshot. Pure-ish (reads store via leading_signals if sigs is None).
    Returns the risk_radar.v2 dict. Never raises."""
    calib = calib or _calib()
    bands = calib["bands"]
    if sigs is None:
        try:
            sigs = leading_signals()
        except Exception as e:  # noqa: BLE001
            log.error("risk_radar leading_signals failed: %s", e)
            sigs = pd.DataFrame()
    subs = subscore_series(sigs, calib)
    if subs is None or subs.empty:
        return {"schema": "risk_radar.v2", "state": None, "alert": False,
                "is_context_only": False, "degraded_reason": "no_signals",
                "disclaimer": _DISCLAIMER}
    row = subs.dropna(how="all").iloc[-1]
    ts = asof or subs.dropna(how="all").index[-1]
    sigrow = sigs.reindex([subs.dropna(how="all").index[-1]]).iloc[-1]

    # ELECTION-CYCLE MODULATOR (engine/election_cycle.py) — a calendar MODULATOR, never an
    # originating leg (the midterm edge is suggestive-not-significant; see that file's docstring
    # for the backtest). In the ONE non-collinear slice — a midterm Apr-Oct window while the tape
    # is still risk-ON — it LOWERS the early (watch/caution) bands a few points so the QUIET tiers
    # fire earlier (the measured ~1.25x cut). It NEVER touches the elevated/risk-off bands, so the
    # calendar can NEVER manufacture a loud banner (that still requires the broad tape to break).
    # Plus a small gross (sizing) trim across the window. Additive, never fatal.
    gate = gate if gate is not None else context_gate_live()
    cyc = None
    mod = {"band_delta": 0.0, "gross_mult": 1.0, "active": False, "risk_on_slice": False}
    try:
        from engine import election_cycle as _ec
        risk_on = (gate.get("spy_below_200dma") is False)
        cyc = _ec.context(asof=ts)
        mod = _ec.modulation(asof=ts, spy_risk_on=risk_on)
        if mod["band_delta"] > 0:
            d = mod["band_delta"]
            bands = {**bands, "watch": max(0.0, bands["watch"] - d),
                     "caution": max(0.0, bands["caution"] - d)}
        if cyc is not None:
            cyc["modulation"] = mod
    except Exception as e:  # noqa: BLE001 — modulator, never fatal
        log.warning("risk_radar election-cycle overlay failed: %s", e)

    scares = []
    for scare, spec in calib["scares"].items():
        if scare not in row or pd.isna(row[scare]):
            continue
        sc = float(row[scare])
        band = _band(sc, bands)
        firing = []
        for leg, w in spec["legs"]:
            v = sigrow.get(leg) if leg in sigrow.index else None
            lc = calib["legs"].get(leg, {})
            thr = float(lc.get("thr_pct", 0.90))
            if v is not None and not pd.isna(v) and v >= bands["watch"] / 100.0:
                f = {
                    "leg": leg, "pctile": round(float(v), 3),
                    "confirmed": bool(v >= thr),     # at/above the strict-bar threshold
                    "lift_2020": lc.get("lift_2020"), "lead_d": lc.get("lead_d"),
                    "era_robust": bool(lc.get("era_robust", False)),
                    "accruing": bool(lc.get("accruing", False)),
                }
                # the global-breadth leg carries its own validation provenance (C3) so the card can
                # print WHERE the edge was proved — honest labelling for a Tier-B accruing leg.
                if leg == "global_breadth":
                    f["validation_ref"] = _GB_VALIDATION_REF
                firing.append(f)
        firing.sort(key=lambda d: -d["pctile"])
        # lift-weighted score: a LEADING leg (high measured lift) outranks a coincident one
        # (e.g. the weak vol-level leg) when picking the dominant/named scare. Display keeps raw score.
        best_lift = max([float(l.get("lift_2020") or 1.0) for l in firing], default=1.0)
        scares.append({"scare": scare, "tier": spec["tier"],
                       "label_en": _SCARE_LABEL[scare][0], "label_zh": _SCARE_LABEL[scare][1],
                       "score": round(sc, 1), "band": band, "firing_legs": firing,
                       "lead_weighted": round(sc * best_lift, 1)})

    scares.sort(key=lambda d: -d["score"])
    tierA = [s for s in scares if s["tier"] == "A"]
    tierB = [s for s in scares if s["tier"] == "B"]
    # dominant/named scare from the VALIDATED (Tier-A) set, lift-weighted so leading > coincident
    dominant = max(tierA, key=lambda d: d["lead_weighted"]) if tierA else (scares[0] if scares else None)
    # state originates ONLY from Tier-A (validated) scares; loud+early = worst Tier-A band
    state = "calm"
    for s in tierA:
        if _STATE_ORDER.index(s["band"]) > _STATE_ORDER.index(state):
            state = s["band"]
    hotA = [s for s in tierA if s["score"] >= bands["caution"]]
    # ARMED + CONFIRM conjunction (verified; the naive >=2 count was REJECTED as noise): escalate
    # only when a VALIDATED leading leg is ARMED inside a hot Tier-A scare (its scare hot AND it has a
    # confirmed+validated firing leg) AND a SECOND Tier-A scare is at least at watch.
    armed = [s for s in hotA
             if any(l.get("confirmed") and _is_validated(l["leg"], calib) for l in s["firing_legs"])]
    second = [s for s in tierA if s["score"] >= bands["watch"]]
    conjunction = len(armed) >= 1 and len(second) >= 2
    esc = conjunction
    # Tier-B scares may escalate a hot Tier-A state, never originate one.  Two exclusion rules:
    # (1) A scare whose ALL firing legs carry lift_2020==0.0 (measured null — e.g. nh_contraction
    #     perm_p=0.978) is excluded from the escalation set until it accrues a real forward-graded
    #     lift.  This keeps phase-0 null legs display-only per the context-accrual law.
    #     Legs with lift_2020=None (unknown/accruing, e.g. vol flow legs, global_breadth) are
    #     NOT excluded by this rule alone — their lift is simply unmeasured, not measured-zero.
    # (2) VSB W6 doctrine — legs flagged display_only=True are STRUCTURALLY UNABLE to move a scare
    #     tier regardless of lift_2020.  This preserves the spec requirement ("lift_2020=None-style
    #     accruing registration so they can NEVER move a scare tier until gauntlet-promoted").
    #     display_only legs count toward the scare's display score but are EXCLUDED from the
    #     escalation computation.  When ALL remaining firing legs are display_only, the scare
    #     cannot escalate.  When some non-display_only legs are present, those govern escalation.
    def _tierb_can_escalate(scare_d: dict, calib: dict) -> bool:
        legs = scare_d["firing_legs"]
        if not legs:
            return False
        # Exclude display_only legs from escalation eligibility (VSB W6 doctrine)
        escalatable = [
            l for l in legs
            if not calib["legs"].get(l["leg"], {}).get("display_only", False)
        ]
        if not escalatable:
            # all firing legs are display_only — scare is structurally non-escalating
            return False
        # all remaining legs measured-zero → exclude from escalation
        if all(calib["legs"].get(l["leg"], {}).get("lift_2020") == 0.0 for l in escalatable):
            return False
        return True
    if state != "calm" and any(
        s["score"] >= bands["caution"] and _tierb_can_escalate(s, calib) for s in tierB
    ):
        esc = True
    state_ungated = state
    if esc and _STATE_ORDER.index(state) < _STATE_ORDER.index("risk-off") and state != "calm":
        state = _STATE_ORDER[_STATE_ORDER.index(state) + 1]
        state_ungated = state

    # CONTEXT GATE: the LOUD banner (elevated+) requires the broad tape to be breaking; otherwise cap
    # at 'caution' (the early/quiet tier still shows). Biggest verified FP-reduction lever.
    # (gate was computed above for the election-cycle overlay; reuse it.)
    if not gate.get("met") and _STATE_ORDER.index(state) > _STATE_ORDER.index("caution"):
        state = "caution"

    alert = _STATE_ORDER.index(state) >= _STATE_ORDER.index(calib.get("alert_from", _ALERT_FROM))
    gross = _gross_for(state)
    # Election-cycle sizing prior (de-risk = SIZING): trims gross modestly in the midterm window,
    # but NEVER de-grosses a calm book — calm = full gross is the radar's contract. The calendar
    # earns a trim only once the radar is already at watch+ (the band nudge surfaces that earlier).
    gross_applied = mod.get("gross_mult", 1.0) < 1.0 and state != "calm"
    if gross_applied:
        gross = round(max(_GROSS["floor"], gross * float(mod["gross_mult"])), 3)
    mod["gross_applied"] = bool(gross_applied)
    prob = _drawdown_prob(state, len(hotA), calib)
    head_en, head_zh = _headline(state, dominant, hotA)
    traj = trajectory(subs, calib)
    deesc = _deescalation(dominant["scare"] if dominant else None, subs, traj, prob)

    # cap_leadership is True from 'elevated'. THRESHOLD REVIEW (incident
    # synthesis.md §4 item 6, flagged NOT auto-decided): the opt-in knob below
    # extends the cap to 'caution' when the dominant scare is a growth/defensive
    # rotation with RISING pullback odds — the exact 07-01 tape. Default false
    # so leadership-capping behavior does not silently change firm-wide; the
    # incident is the falsifier for whoever owns the flip.
    cap_leadership = _STATE_ORDER.index(state) >= _STATE_ORDER.index("elevated")
    try:
        rcfg = (config.load().get("engine", {}) or {}).get("risk_radar", {}) or {}
        if (bool(rcfg.get("cap_leadership_on_rotation_caution", False))
                and state == "caution" and dominant and dominant["scare"] == "growth"
                and deesc.get("drawdown_prob_trend") == "rising"):
            cap_leadership = True
    except Exception as e:  # noqa: BLE001 — knob read must never break the radar
        log.warning("risk_radar cap_leadership knob read failed: %s", e)

    # RC-R11 WASHOUT COUNTER-READ (engine/oracle/washout_counterread.py) — a display-tier
    # CONTEXT chip beside the banner: a growth-scare extreme co-occurring with an index/cohort
    # depth extreme is a historically TWO-SIDED capitulation-zone reading (the growth scare
    # peaked 90.8 on the exact 2026-06-26 Mag-7 bottom). It NEVER suppresses the banner or
    # touches state/bands — pure context, like the election-cycle modulator. Additive, never fatal.
    counterread = None
    try:
        from engine.oracle import washout_counterread as _wc
        gs = next((s for s in scares if s.get("scare") == "growth"), None)
        counterread = _wc.compute(growth_score=(gs or {}).get("score"),
                                  growth_band=(gs or {}).get("band"),
                                  as_of=str(pd.Timestamp(ts).date()))
    except Exception as e:  # noqa: BLE001 — context organ, never fatal
        log.warning("risk_radar washout counter-read failed: %s", e)

    return {
        "schema": "risk_radar.v2",
        "asof": str(pd.Timestamp(ts).date()),
        "state": state,
        "alert": bool(alert),
        "dominant_scare": dominant["scare"] if dominant else None,
        "dominant_label_en": dominant["label_en"] if dominant else None,
        "dominant_label_zh": dominant["label_zh"] if dominant else None,
        "top_score": dominant["score"] if dominant else None,
        "conjunction": conjunction,
        "scares": scares,
        "headline_en": head_en,
        "headline_zh": head_zh,
        "drawdown_prob": prob,
        "conjunction": bool(conjunction),
        "context_gate": gate,
        "state_ungated": state_ungated,
        "flow_status": flow_status(),
        "gross_factor": gross,
        # de-escalation PATH (peaked? falling? how fast?) — leak-free, reuses the subscore history
        # already computed above; consumed by engine/risk_radar_recovery.py for the recovery panel.
        "trajectory": traj,
        # ONE risk voice per page (incident 2026-07-02 root-cause #10): the page's
        # "risk receding" verdict is DERIVED here, beside the scares it must agree
        # with — the recovery panel renders green only when eligible=true.
        "deescalation": deesc,
        "cycle_context": cyc,   # election-cycle MODULATOR (display + sizing; never originates an alert)
        "counterread": counterread,  # RC-R11 washout counter-read (display context; never suppresses)
        "favor_entries": _STATE_ORDER.index(state) >= _STATE_ORDER.index("caution"),
        "cap_leadership": bool(cap_leadership),
        "reader_contract": _READER[state],
        "is_context_only": False,
        "loud_early": True,
        "disclaimer": _DISCLAIMER,
    }


def _drawdown_prob(state: str, nhot: int, calib: dict | None = None) -> dict:
    """Calibrated, ESCALATING probability of a >=5% SPY pullback within 5/10/21 business days.
    Rises with the state (intensity) AND with conjunction (# Tier-A scares hot) — both measured.
    Returns per-horizon probabilities + the base rate + lift, with an honest one-line note."""
    cal = (calib or {}).get("prob_cal") or _PROB_CAL
    conj_extra = max(0, int(nhot) - 1)
    out = {}
    for h in ("h5", "h10", "h21"):
        base = cal.get(h, _PROB_CAL[h]).get(state, _PROB_BASE[h])
        p = min(0.95, base + conj_extra * _CONJ_BUMP[h])
        out[h] = round(p, 3)
    out["base_h5"] = _PROB_BASE["h5"]
    out["base_h10"] = _PROB_BASE["h10"]
    out["base_h21"] = _PROB_BASE["h21"]
    out["lift_h21"] = round(out["h21"] / _PROB_BASE["h21"], 2)
    out["conjunction_n"] = int(nhot)
    out["measure"] = ">=5% SPY pullback (empirical 2006-2026; rises with intensity + conjunction)"
    return out


def _gross_for(state: str) -> float:
    g = {"calm": 1.0, "watch": _GROSS["watch"], "caution": _GROSS["caution"],
         "elevated": _GROSS["elevated"], "risk-off": _GROSS["risk_off"]}.get(state, 1.0)
    return round(max(_GROSS["floor"], g), 3)


def _headline(state, dominant, hot):
    if state == "calm" or not dominant:
        return ("Risk radar: calm — no scare-type elevated.", "风险雷达：平静 — 无升级的风险类型。")
    name = dominant["label_en"]
    name_zh = dominant["label_zh"]
    legs = ", ".join(f"{l['leg']}({l['pctile']:.0%})" for l in dominant["firing_legs"][:3])
    conj = " + " + " × ".join(h["label_en"] for h in hot[:2]) if len(hot) >= 2 else ""
    en = (f"{state.upper()}: {name} ({dominant['score']:.0f}/100){conj}. Leading: {legs}."
          f" Modest odds (~1.5-2x) — de-risk, favor entries.")
    zh = f"{state.upper()}：{name}（{dominant['score']:.0f}/100）。降低风险敞口、择优入场。"
    return en, zh


_READER = {
    "calm": "Normal exposure.",
    "watch": "Note the building scare; normal-to-slightly-reduced exposure.",
    "caution": "Trim chasing; favor good entries over extended leaders; honor stops.",
    "elevated": "De-gross. Favor entries, cap leadership, honor stops. Don't add to froth.",
    "risk-off": "Protect capital: de-gross hard, raise cash, no new leadership chases.",
}


# --- de-escalation trajectory (powers the recovery panel; engine/risk_radar_recovery.py) -----
# The mirror of the rising-risk read: has the radar's intensity PEAKED and started falling, and
# how fast are the pullback odds rolling over? Everything here is a function of the SAME causal
# sub-score history (leak-free) — no new data, no new persistence.
_TRAJ_WINDOW = 30          # trading days of recent path we summarise
_TRAJ_SPARK = 24           # points drawn in the mini sparkline
_TRAJ_VEL_LB = 5           # ~1 trading week lookback for the velocity read
_TRAJ_ODDS_LB = 10         # lookback for the pullback-odds change


def _spark_points(vals, w: float = 96.0, h: float = 26.0, pad: float = 3.0):
    """SVG polyline 'x,y …' for a series scaled into a w×h box (y inverted), plus the (x,y) of the
    peak and the last point. Pure; returns ('', None, None) when degenerate."""
    n = len(vals)
    if n < 2:
        return "", None, None
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    innerw, innerh = w - 2 * pad, h - 2 * pad
    pts = []
    for i, v in enumerate(vals):
        x = pad + innerw * i / (n - 1)
        y = pad + innerh * (1.0 - (v - lo) / rng)
        pts.append((round(x, 1), round(y, 1)))
    peak_i = max(range(n), key=lambda i: vals[i])
    return (" ".join(f"{x},{y}" for x, y in pts),
            {"x": pts[peak_i][0], "y": pts[peak_i][1]}, {"x": pts[-1][0], "y": pts[-1][1]})


def _trajectory_from_series(win, states, odds, caution_band: float) -> dict:
    """Shared trajectory classifier used by BOTH the US (engine/risk_radar) and the international
    (engine/risk_radar_intl) radars, so the peaking/receding logic can never drift between them.
    Inputs: the recent intensity WINDOW (Series), the aligned daily gated STATE (list/Series or
    None), the aligned pullback-odds Series (or None), and this market's caution band. Pure."""
    cur = float(win.iloc[-1])
    peak = float(win.max())
    peak_days_ago = int(len(win) - 1 - int(win.to_numpy().argmax()))
    off_peak = round(peak - cur, 1)
    lb = min(_TRAJ_VEL_LB, len(win) - 1)
    velocity = round(cur - float(win.iloc[-1 - lb]), 1) if lb > 0 else 0.0   # pts over ~1 week
    st_list = list(states) if states is not None else None
    # did the radar reach a genuinely risky level recently (something to recede FROM)? Use the raw
    # intensity peak (so a context-GATED episode, loud banner never fired but risk real, still counts).
    reached_risk = bool(peak >= caution_band)
    if st_list is not None:
        reached_risk = reached_risk or any(
            _STATE_ORDER.index(s) >= _STATE_ORDER.index("caution") for s in st_list)
    rising = velocity >= 1.5
    falling = velocity <= -1.5
    if not reached_risk:
        phase = "calm"
    elif falling and off_peak >= 3.0:
        phase = "receding"
    elif rising:
        phase = "rising"
    elif off_peak < 4.0:
        phase = "peaking"
    else:
        phase = "flat"
    odds_now = round(float(odds.iloc[-1]), 3) if odds is not None else None
    odds_peak = round(float(odds.max()), 3) if odds is not None else None
    olb = (min(_TRAJ_ODDS_LB, len(odds) - 1) if odds is not None else 0)
    odds_delta = (round(float(odds.iloc[-1] - odds.iloc[-1 - olb]), 3)
                  if (odds is not None and olb > 0) else None)
    spark_vals = [round(float(v), 1) for v in win.tail(_TRAJ_SPARK).tolist()]
    pts, peak_xy, last_xy = _spark_points(spark_vals)
    return {
        "intensity": round(cur, 1), "peak": round(peak, 1), "peak_days_ago": peak_days_ago,
        "off_peak": off_peak, "velocity": velocity,   # pts over ~1wk (negative = receding)
        "phase": phase, "reached_risk": reached_risk,
        "state_now": (str(st_list[-1]) if st_list else None),
        "odds_now": odds_now, "odds_peak": odds_peak, "odds_delta": odds_delta,
        "spark": spark_vals, "spark_pts": pts, "spark_peak": peak_xy, "spark_last": last_xy,
        "spark_w": 96, "spark_h": 26, "window": int(len(win)),
    }


def trajectory(subs: pd.DataFrame | None = None, calib: dict | None = None,
               window: int = _TRAJ_WINDOW) -> dict | None:
    """Recent PATH of the radar — has its intensity peaked and turned down, and how fast are the
    pullback odds dropping? Powers the de-escalation / "risk-off may be ending" panel
    (engine/risk_radar_recovery.py). LEAK-FREE: every input is a causal trailing-window percentile
    (subscore_series). Returns None when there is too little history. NEVER raises into the build."""
    try:
        calib = calib or _calib()
        bands = calib["bands"]
        if subs is None:
            subs = subscore_series(leading_signals(), calib)
        if subs is None or subs.empty:
            return None
        tierA = [s for s, v in calib["scares"].items()
                 if v.get("tier") == "A" and s in subs.columns]
        if not tierA:
            return None
        # continuous intensity = the worst Tier-A sub-score each day (0-100). Smooth, so its recent
        # peak + slope is a far cleaner "is risk receding?" read than the 5-step gated state.
        intensity = subs[tierA].max(axis=1).dropna()
        if len(intensity) < 10:
            return None
        win = intensity.tail(window)
        # faithful daily gated+escalated STATE over the recent window (reuse the backtest replica;
        # lazy import avoids a module cycle) + the conjunction count, so the pullback-odds SERIES
        # matches what the card would have shown. Only the window is mapped to odds (not all history).
        states = odds = None
        try:
            from engine.risk_radar_backtest import state_series
            states = state_series(subs, calib).reindex(intensity.index).tail(window)
            nhot = sum((subs[s] >= bands["caution"]).astype(int) for s in tierA
                       ).reindex(intensity.index).fillna(0).astype(int).tail(window)
            odds = pd.Series(
                [_drawdown_prob(st, int(n), calib)["h21"] for st, n in zip(states, nhot)],
                index=win.index)
        except Exception:  # noqa: BLE001 — odds series is best-effort
            states = odds = None
        result = _trajectory_from_series(win, states, odds, bands["caution"])
        # RRX2 WA-3: drivers line — "which scares faded, what is still warm?"
        # Uses the same causal scare sub-score window (leak-free). peak=max of scare in window,
        # now=today's sub-score. Faded = peak>=50 AND (peak-now)>=10, sorted by drop desc, cap 3.
        # Warm = now >= watch band (55), cap 2. Reuses _SCARE_LABEL so labels stay in sync.
        try:
            watch_band = float(bands.get("watch", 55.0))
            drivers_faded = []
            drivers_warm = []
            for scare in subs.columns:
                sw = subs[scare].dropna().tail(window)
                if len(sw) < 3:
                    continue
                peak_val = float(sw.max())
                now_val = float(sw.iloc[-1])
                lbl = _SCARE_LABEL.get(scare, (scare, scare))
                entry = {"key": scare, "label_en": lbl[0], "label_zh": lbl[1],
                         "peak": round(peak_val, 1), "now": round(now_val, 1)}
                if peak_val >= 50 and (peak_val - now_val) >= 10:
                    drivers_faded.append(entry)
                if now_val >= watch_band:
                    drivers_warm.append(entry)
            drivers_faded.sort(key=lambda d: d["peak"] - d["now"], reverse=True)
            result["drivers"] = {
                "faded": drivers_faded[:3],
                "warm": drivers_warm[:2],
            }
        except Exception:  # noqa: BLE001 — drivers is display-only context, never fatal
            result["drivers"] = {"faded": [], "warm": []}
        return result
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("risk_radar trajectory failed: %s", e)
        return None


# every scare type here is a risk-off scare, but 'bubble' measures froth BUILDING
# (its recede is a cooling, not a threat escalating); the rotation/stress family
# below is what must gate an all-clear.
_RISK_OFF_SCARES = {"growth", "credit", "rates", "vol"}


def _deescalation(dominant: str | None, subs: pd.DataFrame | None,
                  traj: dict | None, prob: dict | None) -> dict:
    """ONE risk voice per page (2026-07-02 incident root-cause #10). Through the
    semis breakdown the de-escalation panel showed green 'risk receding' (the
    June vol scare fading) while this radar's own dominant growth scare sat at
    caution with h21 pullback odds RISING — two products, one page, opposite
    stories. The receding verdict now lives HERE, beside the scares it must
    agree with: eligible=false whenever the dominant scare is risk-off-flavored
    and the odds trend is rising (or the dominant sub-score itself is still
    climbing). The panel may still narrate what IS fading (receding_scare) as
    context — it may not present an all-clear. Pure; never raises.

    `deescalated` = the de-escalated-scares chip list (mirrors trajectory
    drivers.faded; from=peak, to=now sub-score). Context narration only — it is
    NOT gated on `eligible`, exactly like the rrx card's "What faded" line."""
    h21 = (prob or {}).get("h21")
    od = (traj or {}).get("odds_delta")
    trend = "unknown"
    if od is not None:
        trend = "rising" if od > 0.005 else ("falling" if od < -0.005 else "flat")
    receding_scare = None
    dominant_velocity = None
    try:
        if subs is not None and not subs.empty:
            best_off = None
            for s in subs.columns:
                w = subs[s].dropna().tail(_TRAJ_WINDOW)
                if len(w) < 10:
                    continue
                lb = min(_TRAJ_VEL_LB, len(w) - 1)
                vel = float(w.iloc[-1] - w.iloc[-1 - lb]) if lb > 0 else 0.0
                off = float(w.max()) - float(w.iloc[-1])
                if s == dominant:
                    dominant_velocity = round(vel, 1)
                # same receding thresholds as _trajectory_from_series
                if vel <= -1.5 and off >= 3.0 and (best_off is None or off > best_off):
                    best_off, receding_scare = off, s
    except Exception as e:  # noqa: BLE001 — context field, never fatal
        log.warning("deescalation per-scare read failed: %s", e)
    suppress = bool(dominant in _RISK_OFF_SCARES
                    and (trend == "rising" or (dominant_velocity or 0.0) >= 1.5))
    phase = (traj or {}).get("phase")
    eligible = bool(phase in ("peaking", "receding") and not suppress)
    if suppress:
        bits = [f"dominant scare = {dominant}"]
        if trend == "rising":
            bits.append("h21 drawdown_prob RISING")
        if (dominant_velocity or 0.0) >= 1.5:
            bits.append(f"{dominant} sub-score still climbing")
        reason = "; ".join(bits)
    elif eligible:
        reason = f"radar {phase} on the dominant scare; h21 drawdown_prob {trend}"
    else:
        reason = f"radar phase = {phase or 'unknown'} — nothing to recede from"
    deescalated = [
        {"key": d.get("key"), "label_en": d.get("label_en"), "label_zh": d.get("label_zh"),
         "from": d.get("peak"), "to": d.get("now")}
        for d in ((traj or {}).get("drivers") or {}).get("faded") or []
    ]
    return {
        "eligible": eligible,
        "reason": reason,
        "receding_scare": receding_scare,       # what IS fading (may differ from dominant)
        "dominant_velocity": dominant_velocity,  # pts over ~1wk on the dominant sub-score
        "drawdown_prob_h21": h21,
        "drawdown_prob_trend": trend,
        "deescalated": deescalated,             # chip list for the "What faded" box
    }


def snapshot(root=None) -> dict:
    """IO wrapper the engine persists to latest['risk_radar']. Never raises."""
    try:
        return compute()
    except Exception as e:  # noqa: BLE001
        log.error("risk_radar snapshot failed: %s", e)
        return {"schema": "risk_radar.v2", "state": None, "alert": False,
                "is_context_only": False, "degraded_reason": "compute_error",
                "disclaimer": _DISCLAIMER}
