"""Intra-basket member-breadth DIVERGENCE — the classical early narrowing tell.

The equal-weight basket LEVEL stays pinned near its 252d high while the members
underneath quietly roll over one by one: the median member drawdown deepens under a
held level (GAP), the share above the 50dma cracks (PARTICIPATION), and the count
below the 50dma rises toward saturation (STEALTH). A within-basket port of the
froth_fragility Face-B mechanics (`_b_leaddist` magnitude gap + `_stealth_leaders`
one-by-one count), computed on the basket's own dated live-member close matrix.

HONEST BY CONSTRUCTION — display-only, `directional: False`. This repo's own research
says directional early leader-detection is a coin-flip (theme momentum rank-IC ~0;
CN drivers 0/152 vs FWER); the ONE validated channel is forward DRAWDOWN. So the
composite is a de-risk texture, and scripts.calibrate_baskets.run_breadth_divergence()
is its pre-registered Phase-0 kill-test (target = forward 21d BASKET drawdown, never
forward return). The Phase-0 verdict only controls the displayed GRADE (cited like
theme_scoring._signal_calibration — a US-proxy verdict, cross-market); the texture
ships display-only regardless. Every leg gates on the basket being PINNED (within
~6% of its 252d high) and returns 0 otherwise, so a visible decline can never fake
a "hidden top". Pure functions, never-raise, no network.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# --------------------------------------------------------- pre-registered constants
PIN_PROX = -0.06     # "pinned" = level within 6% of its 252d high (the froth Face-B prox
#                      gate, ~gate_high_prox 0.94). ALL legs gate on this: a basket that is
#                      visibly off its high is not a HIDDEN top — return 0, no false top.
GAP_LO, GAP_HI = 0.03, 0.20   # ramp span for (basket_off_high − member_dd_med): <3pp is
#                               noise → 0; a 20pp gap = leaders fully masking a rolled-over
#                               membership → 1 (same 3→20pp span as froth `_b_leaddist`).
PART_DROP_5D = -0.05          # Δ(% above 50dma) over 5d below −5pp = participation cracking…
PART_FLOOR = 0.50             # …or fewer than half the live members above their 50d.
STEALTH_SAT = 0.70            # ≥70% of members below the 50dma = saturation (the end-state).
STEALTH_MIN = 0.30            # the rising-count branch needs ≥~1/3 already below — a 1-name
#                               wiggle in a 30-name basket is not "rolling one by one"
#                               (mirrors the share floor in froth `_stealth_leaders`).
BAND_ELEV, BAND_HIGH = 0.35, 0.60   # same display bands as basket_score.rollover_risk.

# Hand leg weights — WHY: GAP is the continuous magnitude read (the Face-B core) and the
# only non-binary leg, so it carries half the mass; PARTICIPATION is the classical
# A/D-style confirmation; STEALTH is the noisiest (a binary count) so it gets the least.
# scripts.calibrate_baskets can OVERRIDE these with OOS-validated weights (read additively,
# exactly like basket_score._rollover_weights) — hand weights are the always-safe fallback.
_BD_HAND = (0.50, 0.30, 0.20)


def _calibration() -> dict:
    """The Phase-0 verdict block (additive enrichment; {} when absent)."""
    try:
        p = config.data_dir() / "strategies" / "baskets_calibration.json"
        d = json.loads(p.read_text()) if p.exists() else {}
        bf = d.get("breadth_divergence_fit") if isinstance(d, dict) else None
        return bf if isinstance(bf, dict) else {}
    except Exception:  # noqa: BLE001 — calibration is enrichment, never fatal
        return {}


def _bd_weights() -> tuple:
    """Leg weights: OOS-calibrated only when the Phase-0 verdict earned it, else hand."""
    bf = _calibration()
    w = bf.get("wired_weights")
    if bf.get("verdict") == "ship_sizing_leg" and isinstance(w, list) and len(w) == 3:
        try:
            return tuple(float(x) for x in w)
        except Exception:  # noqa: BLE001
            pass
    return _BD_HAND


_GRADES = {
    "ship_sizing_leg": ("backtested",
                        "Backtested de-risk texture — on the 27y US sector proxy, elevated "
                        "divergence preceded deeper forward 21d drawdowns out-of-sample and "
                        "added to rollover_risk (a risk timer, never a return forecast; "
                        "US-proxy verdict cited cross-market)."),
    "redundant_with_rollover": ("redundant_with_rollover",
                                "Measured on the 27y proxy but adds nothing over "
                                "rollover_risk out-of-sample — shown as texture only."),
}
_GRADE_DEFAULT = ("descriptive",
                  "Descriptive texture — no separately measured forward-drawdown edge on "
                  "the proxy; a narrowing lens, never a forecast.")


def series(mc_closes: pd.DataFrame, lvl: pd.Series) -> dict | None:
    """Per-bar SERIES of the divergence legs + composite (vectorized rolling; this is the
    raw accessor the Phase-0 kill-test consumes). All reads are causal (trailing windows
    only). Returns None when the inputs can't support a read. Never raises."""
    try:
        if mc_closes is None or lvl is None:
            return None
        C = mc_closes.dropna(axis=1, how="all")
        if C.empty or C.shape[1] < 3 or lvl.dropna().shape[0] < 60:
            return None
        idx = C.index
        # member legs (generalizes theme_scoring._breadth_leg to full series: 50d MA
        # min_periods=25; 252d hi/lo window min_periods=60 like _panel_breadth; NEAR=0.001)
        ma50 = C.rolling(50, min_periods=25).mean()
        ok50 = C.notna() & ma50.notna()
        pct50 = (C > ma50).where(ok50).mean(axis=1)
        below_n = (C < ma50).where(ok50).sum(axis=1)
        n50 = ok50.sum(axis=1)
        share_below = below_n / n50.replace(0, np.nan)
        roll_hi = C.rolling(252, min_periods=60).max()
        roll_lo = C.rolling(252, min_periods=60).min()
        nh = (C >= roll_hi * (1 - 1e-3)).sum(axis=1)
        nl = (C <= roll_lo * (1 + 1e-3)).sum(axis=1)
        n_live = C.notna().sum(axis=1).replace(0, np.nan)
        net_nh = (nh - nl) / n_live
        member_dd_med = (C / roll_hi - 1.0).median(axis=1)
        boh = (lvl / lvl.rolling(252, min_periods=60).max() - 1.0).reindex(idx)
        pinned = boh >= PIN_PROX                       # NaN boh compares False (not pinned)

        # leg1 GAP — continuous ramp on (basket_off_high − member_dd_med), pinned-gated
        gap = boh - member_dd_med
        v1 = boh.notna() & member_dd_med.notna()
        leg_gap = ((gap - GAP_LO) / (GAP_HI - GAP_LO)).clip(0.0, 1.0).where(pinned, 0.0).where(v1)
        # leg2 PARTICIPATION — falling share: Δpct50_5d < −5pp OR ≤ half above 50d, pinned-gated
        d5 = pct50.diff(5)
        v2 = pct50.notna() & boh.notna()
        leg_part = (((d5 < PART_DROP_5D) | (pct50 <= PART_FLOOR)) & pinned).astype(float).where(v2)
        # leg3 STEALTH — rising below-50dma count over 10d (with a ≥30% share floor) or ≥70%
        # saturation, pinned-gated (the froth `_stealth_leaders` shape, within the basket)
        rising = below_n > below_n.shift(10)
        v3 = share_below.notna() & boh.notna()
        leg_st = ((pinned & ((rising & (share_below >= STEALTH_MIN))
                             | (share_below >= STEALTH_SAT)))).astype(float).where(v3)

        W = _bd_weights()
        legs = pd.DataFrame({"gap": leg_gap, "participation": leg_part, "stealth": leg_st})
        wts = pd.Series({"gap": W[0], "participation": W[1], "stealth": W[2]})
        wmass = legs.notna().mul(wts, axis=1).sum(axis=1).replace(0, np.nan)
        risk = legs.fillna(0.0).mul(wts, axis=1).sum(axis=1) / wmass   # mean of AVAILABLE legs
        return {"risk": risk, "legs": legs, "pinned": pinned, "gap": gap,
                "pct_above_50": pct50, "d_pct50_5d": d5, "net_nh_ratio": net_nh,
                "member_dd_med": member_dd_med, "basket_off_high": boh,
                "share_below_50": share_below, "n_below_50": below_n, "n_50": n50}
    except Exception as e:  # noqa: BLE001 — pure texture, never fatal
        log.debug("breadth-divergence series failed: %s", e)
        return None


def breadth_divergence(mc_closes: pd.DataFrame, lvl: pd.Series) -> dict:
    """Snapshot texture (mirrors basket_score.rollover_risk's dict shape) + the raw fields
    the forward log stamps. Degrades to a None-risk read on any shortfall; never raises."""
    grade, note = _GRADES.get(_calibration().get("verdict"), _GRADE_DEFAULT)
    out = {"risk": None, "band": None, "band_zh": None, "reasons": [], "directional": False,
           "basket_off_high": None, "member_dd_med": None, "pct_above_50": None,
           "share_below_50": None, "pinned": None, "grade": grade, "grade_note": note}
    try:
        S = series(mc_closes, lvl)
        if S is None or not np.isfinite(S["risk"].iloc[-1]):
            return out
        r = float(S["risk"].iloc[-1])
        last = {k: S[k].iloc[-1] for k in ("basket_off_high", "member_dd_med", "pct_above_50",
                                           "share_below_50", "gap", "d_pct50_5d",
                                           "n_below_50", "n_50")}
        pinned = bool(S["pinned"].iloc[-1])
        legs = S["legs"].iloc[-1]
        reasons: list[str] = []
        if pd.notna(legs["gap"]) and legs["gap"] > 0:
            reasons.append(f"basket {last['basket_off_high']:+.0%} off 252d high vs median "
                           f"member {last['member_dd_med']:+.0%} "
                           f"({100 * float(last['gap']):.0f}pp gap)")
        if pd.notna(legs["participation"]) and legs["participation"] > 0:
            d5s = f", Δ5d {100 * float(last['d_pct50_5d']):+.0f}pp" \
                if pd.notna(last["d_pct50_5d"]) else ""
            reasons.append(f"participation cracking ({last['pct_above_50']:.0%} above 50d{d5s})")
        if pd.notna(legs["stealth"]) and legs["stealth"] > 0:
            reasons.append(f"{int(last['n_below_50'])}/{int(last['n_50'])} members below 50d "
                           f"under a pinned basket")
        band, band_zh = (("high", "高") if r >= BAND_HIGH
                         else ("elevated", "升高") if r >= BAND_ELEV else ("low", "低"))
        out.update({"risk": round(r, 3), "band": band, "band_zh": band_zh,
                    "reasons": reasons[:4], "pinned": pinned,
                    "basket_off_high": round(float(last["basket_off_high"]), 4)
                    if pd.notna(last["basket_off_high"]) else None,
                    "member_dd_med": round(float(last["member_dd_med"]), 4)
                    if pd.notna(last["member_dd_med"]) else None,
                    "pct_above_50": round(float(last["pct_above_50"]), 3)
                    if pd.notna(last["pct_above_50"]) else None,
                    "share_below_50": round(float(last["share_below_50"]), 3)
                    if pd.notna(last["share_below_50"]) else None})
        return out
    except Exception as e:  # noqa: BLE001
        log.debug("breadth-divergence snapshot failed: %s", e)
        return out


# ------------------------------------------------------ achieved-lead-time forward log
LOG_COLS = ["date", "basket_id", "region", "risk", "band", "basket_off_high",
            "pct_above_50", "label_at_stamp"]


def _log_path():
    return config.data_dir() / "breadth_divergence" / "forward_log.parquet"


def log_stamp(basket_id: str, region: str, texture: dict | None, label: str | None,
              date, path=None) -> bool:
    """Append one row keyed (date, basket_id, region) whenever the band is elevated/high.
    KEEP-FIRST: a key already present is never restamped or overwritten (intraday rebuilds
    can't drift the stamp). Never raises; True only when a new row landed."""
    try:
        if not isinstance(texture, dict) or texture.get("band") not in ("elevated", "high"):
            return False
        p = path if path is not None else _log_path()
        row = {"date": str(pd.Timestamp(date).date()), "basket_id": str(basket_id),
               "region": str(region), "risk": texture.get("risk"), "band": texture.get("band"),
               "basket_off_high": texture.get("basket_off_high"),
               "pct_above_50": texture.get("pct_above_50"), "label_at_stamp": str(label)}
        if p.exists():
            df = pd.read_parquet(p)
            dup = ((df["date"] == row["date"]) & (df["basket_id"] == row["basket_id"])
                   & (df["region"] == row["region"]))
            if bool(dup.any()):
                return False
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)[LOG_COLS]
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            df = pd.DataFrame([row])[LOG_COLS]
        df.to_parquet(p, index=False)
        return True
    except Exception as e:  # noqa: BLE001 — accountability log is enrichment, never fatal
        log.debug("breadth-divergence stamp failed: %s", e)
        return False


def realized_fwd_dd(lvl: pd.Series, stamp_date, h: int = 21) -> float | None:
    """Realized forward h-day max drawdown for a stamp: ANCHOR = the stamp-date close (the
    bar at which the band was knowable), OUTCOME WINDOW = the h closes STRICTLY AFTER the
    stamp — the T+1-fill convention, identical to calibrate_baskets._fwd_dd (i+1..i+h).

    ⚠ MARKER-DATE GRADING IS FORBIDDEN (engine.signal_quality §W6-CN — the measured trap is
    +5.7pp/10d): never let the outcome window start at/before a bar whose close the stamp
    itself consumed. tests/test_basket_breadth_divergence.py pins that a marker-date
    variant of this anchor FAILS."""
    try:
        s = lvl.dropna()
        ts = pd.Timestamp(stamp_date)
        at = s.index[s.index <= ts]
        if len(at) == 0:
            return None
        anchor = float(s.loc[at[-1]])
        fwd = s.loc[s.index > ts]                     # strictly after the stamp
        if len(fwd) < h or anchor <= 0:
            return None
        return float(fwd.iloc[:h].min() / anchor - 1.0)
    except Exception:  # noqa: BLE001
        return None


def grade_forward_log(log_df: pd.DataFrame, levels: dict, labels: dict | None = None,
                      h: int = 21, dd_risk: float = -0.08) -> dict:
    """Achieved-lead-time report over the forward log (pure; the caller supplies data).
    Per stamp: realized fwd h-day drawdown (T+1 convention), lead_vs_guard_days = trading
    days until the theme's LABEL first flips to fading/deteriorating strictly after the
    stamp (None if it never did / no label history), plus the UNCONDITIONAL base rate
    P(fwd dd < dd_risk) over the same level histories as the control."""
    rows, dds, leads = [], [], []
    try:
        for _, r in log_df.iterrows():
            lv = (levels or {}).get(r["basket_id"])
            if lv is None:
                continue
            dd = realized_fwd_dd(lv, r["date"], h)
            lead = None
            lab = (labels or {}).get(r["basket_id"])
            if lab is not None:
                after = lab.loc[lab.index > pd.Timestamp(r["date"])]
                flip = after[after.isin(("fading", "deteriorating"))]
                if len(flip):
                    lead = int(after.index.get_loc(flip.index[0]) + 1)
            rows.append({**{k: r[k] for k in ("date", "basket_id", "region", "risk", "band")},
                         "fwd_dd": dd, "lead_vs_guard_days": lead})
            if dd is not None:
                dds.append(dd)
            if lead is not None:
                leads.append(lead)
        # unconditional control: pooled P(fwd dd < dd_risk) at every bar of every level
        base = []
        for lv in (levels or {}).values():
            s = lv.dropna()
            if len(s) < h + 2:
                continue
            fmin = s.iloc[::-1].rolling(h, min_periods=h).min().iloc[::-1].shift(-1)
            base.append(((fmin / s - 1.0) < dd_risk).dropna() if fmin.notna().any() else None)
        pooled = pd.concat([b for b in base if b is not None]) if any(
            b is not None for b in base) else pd.Series(dtype=float)
        return {"n": len(rows), "rows": rows,
                "med_fwd_dd": round(float(np.median(dds)), 4) if dds else None,
                "p_dd_lt_risk": round(float(np.mean([d < dd_risk for d in dds])), 3)
                if dds else None,
                "base_rate": round(float(pooled.mean()), 3) if len(pooled) else None,
                "med_lead_days": round(float(np.median(leads)), 1) if leads else None,
                "n_label_flipped": len(leads)}
    except Exception as e:  # noqa: BLE001
        log.debug("breadth-divergence grading failed: %s", e)
        return {"n": len(rows), "rows": rows, "error": str(e)}
