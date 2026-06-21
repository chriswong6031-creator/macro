"""engine/vol_regime.py — the unified, VALIDATION-GATED index volatility-regime engine.

This is the piece that turns the options/vol surface from a set of scattered display
fields into ONE coherent, falsifiable, risk-on/off STATE that the macro engine,
baskets, and the Mastermind bot can actually act on. It composes the genuinely-robust
INDEX-LEVEL vol signals — the ones backed by decades of data we already hold and that
carry NO dealer-sign assumption — into a single de-correlated block:

  • TERM-STRUCTURE slope   VIX / VIX3M (and VIX9D / VIX front-end). Contango = calm /
                           risk-on; backwardation = stress. The single best-documented
                           vol regime estimator (Johnson 2017; the cleanest signal here).
  • CROSS-ASSET stress     MOVE (bond vol) level percentile — rates vol leads equity
                           stress (2022, 2023 regional banks). This series sat UNUSED.
  • VOLATILITY-RISK-PREMIUM VIX minus a HAR FORWARD realized-vol forecast (not lazy
                           trailing RV). High VRP -> constructive forward equity at the
                           1-3 month horizon (Bollerslev-Tauchen-Zhou 2009). Paired with
                           its rate-of-change so "rich-and-calm" (bullish) is separated
                           from "spiking-into-a-drawdown" (the same number, opposite read).

Plus two CONTEXT-ONLY (never scored) reads the literature says are NOT clean timers:
  • INSURANCE COST        CBOE SKEW reframed as a percentile of how expensive OTM-put
                          convexity is — a Universa-style "protection cheap vs dear"
                          risk-shape chip, NOT a buy/sell. (SKEW LEVEL is a near-perverse
                          crash timer — big corrections are ~2x more common when SKEW is
                          LOW — so it is deliberately kept out of the scored composite.)
  • VOL-TARGET SCALAR     target_vol / max(realized, implied) — a mechanical drawdown /
                          capital-efficiency sizing rule (subtract-only on gross), never
                          a return forecast.

THE FIREWALL (enforced in code, not convention): every leg ships CONTEXT/DISPLAY by
default. A leg only earns a non-zero SCORED weight when data/vol_regime/gate.json — written
by scripts/validate_vol_regime.py after a forward-IC + OOS-R2 + Clark-West + DSR +
subperiod-sign-stability pass on 1990+ history — marks it `scored: true` with a sign. No
gate file -> the composite is published for display but contributes 0 to any decision.
This is the doctrine the repo already lives by (validate-first; see DECISIONS.md,
engine/validation.py): index legs with long history are ELIGIBLE to be scored; anything
resting on a dealer-sign assumption or <1y history stays display/context forever.

All causal: every value at date t uses only data <= t. Pure functions over aligned daily
Series; no I/O except the optional read of the gate file. See engine/vol_forecast.py
(the HAR forward-vol forecaster reused for the VRP physical leg) and engine/conditions.py
(which consumes the snapshot into data/regime/latest.json).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from engine.vol_forecast import cone_vol_ann, realized_vol

log = logging.getLogger(__name__)

# The three SCORED-ELIGIBLE index legs (long history, no dealer-sign assumption) and
# the CONTEXT-only reads. Orientation of every scored leg: POSITIVE = risk-ON /
# constructive for forward equity, so the composite is a single signed risk-on score.
SCORED_LEGS = ("ts_slope", "move", "vrp")
# context/candidate legs (display only). `vvix` is the collect-first VVIX-VIX leg: it has
# 2006+ history (CBOE) so the validator evaluates it as a CANDIDATE, but it stays OUT of the
# validated scored composite until a deliberate promotion (so adding it never silently
# changes the gated 3-leg overlay). See scripts/validate_vol_regime.py + VOL_REGIME_DATA_ACCRUAL.md.
CONTEXT_LEGS = ("ts9", "skew_cost", "downside_vrp", "vvix")

DEFAULTS = dict(
    z_window_d=504,            # ~2y rolling window for leg z-scores (causal)
    pctile_lookback_d=504,     # ~2y percentile window for level reads
    realized_window_d=21,      # trailing RV window for the vol-target denominator
    har_lags=(2, 5, 22, 66),   # HAR predictor set for the VRP forward-RV forecast
    target_vol_pct=12.0, vt_floor=0.5, vt_cap=1.5,   # vol-target sizing scalar bounds
    leg_clip=2.5,              # clip each leg z before averaging (tame fat tails)
    # term-structure state bands (VIX/VIX3M)
    backwardation=1.00, near_backwardation=0.975, deep_contango=0.92,
    # confluence-flag thresholds
    move_stress_pctile=0.80, vrp_collapse_pctile=0.20, ts9_stress=1.05,
    # VVIX (vol-of-vol) state bands — framed by the MEASURED VVIX/VIX forward-vol relationship
    vvix_peak_pctile=0.90,      # absolute VVIX percentile -> capitulation "peak fear"
    vvix_rich_pctile=0.80,      # VVIX/VIX ratio percentile -> vol-of-vol rich (fear priced)
    vvix_cheap_pctile=0.20,     # VVIX/VIX ratio percentile -> vol-of-vol cheap (complacent)
    # continuous risk-on -> label bands (after /leg_clip normalisation to ~[-1,1])
    risk_on_band=0.30, risk_off_band=-0.30,
)

GATE_PATH = "vol_regime/gate.json"     # relative to the data dir; written by the validator


# --------------------------------------------------------------------------- #
# small causal helpers
# --------------------------------------------------------------------------- #
def _z(s: pd.Series, win: int) -> pd.Series:
    """Causal rolling z-score (mean/std over a trailing window; ddof=0)."""
    m = s.rolling(win, min_periods=max(20, win // 4)).mean()
    sd = s.rolling(win, min_periods=max(20, win // 4)).std(ddof=0)
    return (s - m) / sd.replace(0, np.nan)


def _pctile(s: pd.Series, win: int) -> pd.Series:
    """Causal trailing percentile rank of the current value within the window
    (0..1). Uses only data <= t, so it is point-in-time for a forward-return label."""
    return s.rolling(win, min_periods=max(40, win // 4)).apply(
        lambda a: (a[:-1] < a[-1]).mean() if len(a) > 1 else np.nan, raw=True)


def _clip(s: pd.Series, c: float) -> pd.Series:
    return s.clip(-c, c)


def _r(x, n=3):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, n) if np.isfinite(v) else None


# --------------------------------------------------------------------------- #
# the leg + composite frame
# --------------------------------------------------------------------------- #
def build_frame(vix: pd.Series, vix3m: pd.Series | None, vix9d: pd.Series | None,
                move: pd.Series | None, skew: pd.Series | None, spy: pd.Series | None,
                cfg: dict | None = None, vvix: pd.Series | None = None) -> pd.DataFrame:
    """Daily per-leg + composite frame. Every column is causal (data <= t). Missing
    inputs degrade gracefully — a leg simply drops out of the available set. Returns a
    DataFrame indexed by date with the raw reads, the signed risk-on legs (``leg_*``),
    the composite ``risk_score`` (in ~[-1,1], risk-on positive), confluence flags, and
    the mechanical ``vol_target_scalar``.

    ``vvix`` (CBOE vol-of-vol, 2006+) is OPTIONAL and trails cfg so existing positional
    callers are unaffected; when present it adds the CONTEXT/candidate VVIX-VIX leg."""
    cf = {**DEFAULTS, **(cfg or {})}
    zw, pw = int(cf["z_window_d"]), int(cf["pctile_lookback_d"])
    if vix is None or vix.dropna().empty:
        return pd.DataFrame()
    out = pd.DataFrame(index=vix.dropna().index)
    vix = vix.reindex(out.index).astype(float)
    out["vix"] = vix

    legs: dict[str, pd.Series] = {}

    # 1) TERM-STRUCTURE slope: VIX/VIX3M. Contango (<1) = calm; backwardation (>=1) = stress.
    if vix3m is not None:
        v3 = vix3m.reindex(out.index).astype(float)
        out["ts_slope"] = vix / v3
        legs["ts_slope"] = -_z(out["ts_slope"], zw)        # low slope (contango) -> risk-on +
    # near-term front-end: VIX9D/VIX (>1 = acute near stress) — CONTEXT only
    if vix9d is not None:
        v9 = vix9d.reindex(out.index).astype(float)
        out["ts9"] = v9 / vix
        legs["ts9"] = -_z(out["ts9"], zw)

    # 2) CROSS-ASSET stress: MOVE (bond vol) level. High MOVE = rates stress -> risk-off.
    if move is not None:
        mv = move.reindex(out.index).astype(float)
        out["move"] = mv
        out["move_pctile"] = _pctile(mv, pw)
        out["move_vix"] = mv / vix                          # bond-vs-equity vol ratio (context)
        legs["move"] = -_z(mv, zw)

    # 3) VOL-RISK-PREMIUM: VIX minus a HAR FORWARD realized-vol forecast (vol points).
    #    High VRP -> vol overpriced -> constructive forward equity (BTZ 2009).
    if spy is not None:
        sp = spy.reindex(out.index).astype(float)
        fcast_ann = cone_vol_ann(sp, lags=tuple(cf["har_lags"])) * 100.0   # forecast vol, %
        out["fcast_vol"] = fcast_ann
        out["vrp"] = vix - fcast_ann
        out["vrp_pctile"] = _pctile(out["vrp"], pw)
        out["vrp_chg_21d"] = out["vrp"].diff(21)
        legs["vrp"] = _z(out["vrp"], zw)                    # high VRP -> risk-on +
        # vol-target sizing scalar (mechanical; subtract-only on gross). Use the MAX of
        # realized and implied so the gross shrinks the moment EITHER vol rises.
        rv_ann = realized_vol(sp, int(cf["realized_window_d"])) * np.sqrt(252) * 100.0
        denom = pd.concat([rv_ann, vix], axis=1).max(axis=1)
        out["vol_target_scalar"] = (cf["target_vol_pct"] / denom).clip(cf["vt_floor"], cf["vt_cap"])

    # CONTEXT: SKEW as insurance-cost percentile (NOT scored — perverse as a timer).
    if skew is not None:
        sk = skew.reindex(out.index).astype(float)
        out["skew"] = sk
        out["skew_cost_pctile"] = _pctile(sk, pw)           # high = OTM-put convexity dear
        out["skew_chg_63d"] = sk.diff(63)                   # the validatable CHANGE form
        legs["skew_cost"] = _z(sk, zw)
        # downside-VRP proxy: SKEW-implied tail richness vs realized DOWN-semivol.
        if spy is not None:
            ret = spy.reindex(out.index).pct_change(fill_method=None)
            down = ret.where(ret < 0, 0.0)
            dsv = down.rolling(int(cf["realized_window_d"])).std(ddof=0) * np.sqrt(252) * 100.0
            out["down_semivol"] = dsv
            # insurance "expensiveness" relative to recent realized downside (>0 = dear)
            out["downside_vrp"] = (sk - 100.0) / 10.0 - (dsv / vix).fillna(0.0)
            legs["downside_vrp"] = out["downside_vrp"]

    # CONTEXT (collect-first candidate): VVIX vol-of-vol — the VVIX-VIX ratio (peak-fear vs
    # complacency). VVIX = 30d implied vol of VIX options (the vol of vol). The MEASURED
    # relationship over 2006+ (validator: HAC t~15, sign-stable, crisis-robust): a RICH VVIX/VIX
    # ratio precedes LOWER forward realized vol (fear already priced into vol-of-vol -> mean-
    # reversion, the "peak-fear" contrarian read), while a CHEAP ratio precedes HIGHER vol
    # (complacency = the genuine quiet-fragility tell). So the risk-on form is +z(ratio).
    # CAVEAT (why it stays a candidate): VVIX/VIX is partly the mechanical 1/VIX, so much of this
    # is plain vol persistence — promotion requires showing INCREMENTAL edge over the VIX level
    # and the scored legs. History reaches only 2006, so it ships CONTEXT: the validator scores
    # it as a candidate but it does NOT enter the validated composite until a deliberate promotion.
    if vvix is not None:
        vv = vvix.reindex(out.index).astype(float)
        out["vvix"] = vv
        out["vvix_vix"] = vv / vix                          # vol-of-vol relative to vol
        out["vvix_pctile"] = _pctile(vv, pw)                # absolute VVIX (peak-fear) gauge
        out["vvix_vix_pctile"] = _pctile(out["vvix_vix"], pw)   # ratio-richness percentile
        legs["vvix"] = _z(out["vvix_vix"], zw)              # high ratio -> lower fwd vol -> risk-on +

    # store signed legs
    for k, s in legs.items():
        out[f"leg_{k}"] = _clip(s, cf["leg_clip"])

    # COMPOSITE risk-on score: equal-weight mean of the AVAILABLE SCORED-ELIGIBLE legs,
    # normalised to ~[-1,1]. ONE de-correlated block (the legs all read the same vol
    # surface; a capped composite avoids the double-count the RORO leg pile-up risks).
    scored_cols = [f"leg_{k}" for k in SCORED_LEGS if f"leg_{k}" in out.columns]
    if scored_cols:
        block = out[scored_cols]
        # require >=2 legs present (or all, when fewer exist) so a stale partial date
        # — VIX prints before VIX3M/MOVE/SPY settle — can't collapse the composite onto
        # a single leg. This is the cadence-mismatch guard conditions.py also enforces.
        need = min(2, len(scored_cols))
        comp = (block.mean(axis=1) / cf["leg_clip"]).where(block.count(axis=1) >= need)
        out["risk_score"] = comp.clip(-1.0, 1.0)

    # CONFLUENCE flags (k-of-n fragility tells) — display + a context fragility count.
    flags = pd.DataFrame(index=out.index)
    if "ts_slope" in out:
        flags["backwardation"] = out["ts_slope"] >= cf["backwardation"]
    if "ts9" in out:
        flags["front_stress"] = out["ts9"] >= cf["ts9_stress"]
    if "move_pctile" in out:
        flags["move_stress"] = out["move_pctile"] >= cf["move_stress_pctile"]
    if "vrp_pctile" in out:
        flags["vrp_collapse"] = out["vrp_pctile"] <= cf["vrp_collapse_pctile"]
    if not flags.empty:
        for c in flags.columns:
            out[f"flag_{c}"] = flags[c]
        out["fragility_confluence"] = flags.fillna(False).sum(axis=1).astype(int)

    return out


# --------------------------------------------------------------------------- #
# state label
# --------------------------------------------------------------------------- #
def _regime_label(ts_slope, risk_score, fragility, cfg) -> str:
    """4-state regime from the term structure (the cleanest estimator) refined by the
    composite. Used as a STATE ESTIMATOR / kill-switch — never a 'sell contango' carry
    trade (that is the short-vol Volmageddon trade with a fat left tail)."""
    if ts_slope is not None and ts_slope >= cfg["backwardation"]:
        return "backwardation-stress"
    warn = ((ts_slope is not None and ts_slope >= cfg["near_backwardation"])
            or (risk_score is not None and risk_score <= cfg["risk_off_band"])
            or (fragility is not None and fragility >= 2))
    if warn:
        return "warning"
    if (ts_slope is not None and ts_slope < cfg["deep_contango"]
            and (risk_score is None or risk_score >= cfg["risk_on_band"])):
        return "calm-contango"
    return "normalizing"


# --------------------------------------------------------------------------- #
# gate (the firewall) — display by default, scored only when earned
# --------------------------------------------------------------------------- #
def load_gate(data_dir: Path | None = None) -> dict:
    """Read data/vol_regime/gate.json (written by scripts/validate_vol_regime.py).
    Absent / malformed -> a closed gate: NOTHING is scored. Shape:
      {"legs": {"ts_slope": {"scored": true, "sign": 1, "weight": 1.0, ...}, ...},
       "composite": {"scored": bool, "horizon_d": int, "ic": ..., "dsr": ...},
       "asof": "...", "note": "..."}"""
    try:
        from lib import config
        p = (data_dir or config.data_dir()) / GATE_PATH
        if p.exists():
            return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001 — a missing/broken gate must never break the build
        log.warning("vol_regime: gate read failed (%s) — defaulting to display-only", e)
    return {"legs": {}, "composite": {"scored": False}}


def asof_index(frame: pd.DataFrame):
    """The single coherent as-of date: the last row where ALL available scored legs are
    present (so the composite isn't read off a stale partial date), falling back to the
    last valid risk_score, then the last row."""
    if frame is None or len(frame.index) == 0:
        return None
    scored = [f"leg_{k}" for k in SCORED_LEGS if f"leg_{k}" in frame.columns]
    if scored:
        full = frame[scored].dropna(how="any")
        if len(full):
            return full.index[-1]
    if "risk_score" in frame.columns:
        rs = frame["risk_score"].dropna()
        if len(rs):
            return rs.index[-1]
    return frame.index[-1]


def scored_score(frame: pd.DataFrame, gate: dict | None = None, asof=None) -> float | None:
    """The risk-on score that is ALLOWED to move money: the gated composite, read off ONE
    coherent as-of row. Only legs the gate marks `scored` contribute, each times its
    validated sign and weight. Returns None when no leg is gate-approved (honest default)."""
    if frame is None or len(frame.index) == 0:
        return None
    gate = gate or load_gate()
    legs = (gate or {}).get("legs") or {}
    asof = asof if asof is not None else asof_index(frame)
    if asof is None:
        return None
    row = frame.loc[asof]
    parts, wsum = [], 0.0
    for k in SCORED_LEGS:
        col = f"leg_{k}"
        meta = legs.get(k) or {}
        if col in frame.columns and meta.get("scored"):
            v = row.get(col)
            if v is None or not np.isfinite(v):
                continue
            w = float(meta.get("weight", 1.0)); sign = float(meta.get("sign", 1.0))
            parts.append(sign * w * float(v) / DEFAULTS["leg_clip"]); wsum += w
    if not parts or wsum <= 0:
        return None
    return float(np.clip(sum(parts) / wsum, -1.0, 1.0))


# --------------------------------------------------------------------------- #
# snapshot (for latest.json + the page + Mastermind)
# --------------------------------------------------------------------------- #
def snapshot(frame: pd.DataFrame, cfg: dict | None = None, gate: dict | None = None) -> dict:
    """Latest-row reading for data/regime/latest.json's vol_regime block, the Options
    Desk hero, and the Mastermind context bus. Carries BOTH the display composite and
    the gated scored value, with explicit honesty fields so a consumer can never mistake
    a display read for a validated one."""
    cf = {**DEFAULTS, **(cfg or {})}
    if frame is None or len(frame.index) == 0:
        return {"available": False}
    gate = gate or load_gate()
    asof = asof_index(frame)
    if asof is None:
        return {"available": False}
    row = frame.loc[asof]

    def gv(col):
        if col not in frame.columns:
            return None
        v = row.get(col)
        try:
            return float(v) if v is not None and np.isfinite(float(v)) else None
        except (TypeError, ValueError):
            return None

    ts = gv("ts_slope")
    risk = gv("risk_score")
    frag = gv("fragility_confluence")
    regime = _regime_label(ts, risk, frag, cf)
    sc = scored_score(frame, gate, asof=asof)

    legs_out = {}
    for k in SCORED_LEGS + CONTEXT_LEGS:
        col = f"leg_{k}"
        if col in frame.columns:
            meta = (gate.get("legs") or {}).get(k) or {}
            legs_out[k] = {"z": _r(gv(col)),
                           "scored": bool(meta.get("scored")) and k in SCORED_LEGS,
                           "sign": meta.get("sign"),
                           "eligible": k in SCORED_LEGS}

    fired = [c.replace("flag_", "") for c in frame.columns
             if c.startswith("flag_") and bool(gv(c))]

    return {
        "available": True,
        "asof": str(pd.Timestamp(asof).date()),
        "regime": regime,
        "risk_score": _r(risk),                       # DISPLAY composite (~[-1,1])
        "scored_score": _r(sc),                       # GATED — None until earned
        "scored_active": sc is not None,
        # raw reads (all from the one coherent as-of row)
        "vix": _r(gv("vix"), 2),
        "ts_slope": _r(ts),
        "ts_slope_state": ("backwardation" if (ts is not None and ts >= cf["backwardation"])
                           else "near-flat" if (ts is not None and ts >= cf["near_backwardation"])
                           else "contango" if ts is not None else None),
        "ts9": _r(gv("ts9")),
        "move": _r(gv("move"), 1),
        "move_pctile": _r(gv("move_pctile")),
        "move_vix": _r(gv("move_vix")),
        "vrp": _r(gv("vrp"), 2),
        "vrp_pctile": _r(gv("vrp_pctile")),
        "vrp_chg_21d": _r(gv("vrp_chg_21d"), 2),
        "vrp_state": _vrp_state(gv("vrp_pctile"), gv("vrp_chg_21d")),
        "skew": _r(gv("skew"), 1),
        "skew_cost_pctile": _r(gv("skew_cost_pctile")),
        "insurance_cost": _cost_band(gv("skew_cost_pctile")),
        "downside_vrp": _r(gv("downside_vrp")),
        "vvix": _r(gv("vvix"), 1),
        "vvix_vix": _r(gv("vvix_vix")),
        "vvix_pctile": _r(gv("vvix_pctile")),
        "vvix_vix_pctile": _r(gv("vvix_vix_pctile")),
        "vvix_state": _vvix_state(gv("vvix_pctile"), gv("vvix_vix_pctile"), cf),
        "vol_target_scalar": _r(gv("vol_target_scalar"), 2),
        "fragility_confluence": None if frag is None else int(frag),
        "flags": fired,
        "legs": legs_out,
        "gate": {"scored_any": any(v.get("scored") for v in legs_out.values()),
                 "asof": gate.get("asof"), "note": gate.get("note")},
        "doctrine": ("Index vol-regime: validated on 1990+ history, no dealer-sign "
                     "assumption. Legs are SCORED only when the validation gate marks "
                     "them earned; otherwise display/context. A regime read, not an "
                     "intraday timer (delayed-EOD inputs)."),
    }


def _vrp_state(pctile, chg) -> str | None:
    if pctile is None:
        return None
    if chg is not None and chg < -2.0 and pctile < 0.5:
        return "collapsing (de-risk)"          # VRP falling = realized catching implied
    if pctile >= 0.80:
        return "rich (vol overpriced — constructive)"
    if pctile <= 0.20:
        return "thin (vol underpriced — fragile)"
    return "normal"


def _cost_band(pctile) -> str | None:
    if pctile is None:
        return None
    return ("expensive (fear already priced)" if pctile >= 0.80
            else "cheap (convexity on sale)" if pctile <= 0.20 else "normal")


def _vvix_state(vvix_pctile, ratio_pctile, cfg) -> str | None:
    """VVIX (vol-of-vol) state, framed by the MEASURED VVIX/VIX forward-vol relationship: a
    rich ratio historically precedes LOWER realized vol (fear already priced — contrarian-
    constructive), a cheap ratio precedes HIGHER vol (complacency — the quiet-fragility tell).
    An extreme ABSOLUTE VVIX flags capitulation peak-fear. Context only (candidate leg)."""
    if vvix_pctile is None and ratio_pctile is None:
        return None
    if vvix_pctile is not None and vvix_pctile >= cfg["vvix_peak_pctile"]:
        return "peak-fear (vol-of-vol extreme — capitulation, historically mean-reverts)"
    if ratio_pctile is not None and ratio_pctile >= cfg["vvix_rich_pctile"]:
        return "fear-priced (vol-of-vol rich vs vol — mild contrarian-constructive)"
    if ratio_pctile is not None and ratio_pctile <= cfg["vvix_cheap_pctile"]:
        return "complacent (vol-of-vol cheap vs vol — historically precedes rising vol)"
    return "normal"
