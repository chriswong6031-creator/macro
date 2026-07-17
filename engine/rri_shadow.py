"""RRI Stage-B shadow-accrual module.

Computes and logs three ACCRUE-verdict variants from the intl risk radar's
composite_series substrate for the 7 new-market profiles:

  s1_any95  — S1 floor-to-elevated when any comp-leg pctile >= 0.95, gate open
  s3_ret10  — S3 velocity leg added (−ret10, weight 0.6), re-blended composite
  s3_ret21  — S3 velocity leg added (−ret21, weight 0.6), re-blended composite

Shadow logs live at:
  data/risk_radar_intl/<market>_forward_log_<variant>.jsonl

They are idempotent by as-of (first-writer-wins), lane-gated (only the
nightly collect lane appends; the module also self-gates via
ledger_lane_armed()), and graded against the same rulers as the live audit
(R-A: >= 5% drawdown within h5/h10/h21 business days from the as-of close).

Spec: research/RRI_CRASH_ANTIFIRE_PROGRAM.md §2 (shadow-variant law / §6
(grammar); RRI_S1_LEG_FLOOR_ESCALATION_PREREG.md; RRI_S3_DRAWDOWN_VELOCITY_LEG_PREREG.md.
Stage-A verdicts: s1_any95=ACCRUE, s3_ret10=ACCRUE, s3_ret21=ACCRUE.

Budget law: composite_series is called ONCE per market; all 3 variants
derive from its (B, sub, comp, gate) output — no per-variant store reads.

Never raises into the build: every public function catches all exceptions
and logs.warning, matching the house idiom in risk_radar_intl.py and
risk_radar_intl_audit.py.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from engine.indicators import pct_rank_window
from lib import config

log = logging.getLogger(__name__)

# ── scope ────────────────────────────────────────────────────────────────────
# cn/hk/ca are byte-frozen legacy; this module is explicitly for the 7 new profiles only.
MARKETS = ("kr", "jp", "tw", "in", "au", "gb", "ez")

VARIANTS = ("s1_any95", "s3_ret10", "s3_ret21")

# S3 velocity leg spec (RRI_S3 prereg §3)
_S3_VEL_WEIGHT = 0.6          # junior-leg convention, identical to the FX leg weight
_S3_VEL_PCT_WIN = 504         # causal trailing-percentile window (matches composite_series)
_S3_VEL_WINDOWS = {"s3_ret10": 10, "s3_ret21": 21}   # −ret<n> windows per variant

# S1 floor threshold (RRI_S1 prereg §2)
_S1_FLOOR_THRESHOLD = 0.95    # any-leg >= 0.95 triggers the floor
_S1_FLOOR_STATE = "elevated"  # the floor value (never lifts to risk-off)

_STATE_ORDER = ["calm", "watch", "caution", "elevated", "risk-off"]

# Grading constants (mirrors risk_radar_intl_audit)
_HORIZONS = {"h5": 5, "h10": 10, "h21": 21}
_DD_THRESHOLDS = (0.05, 0.08)
_PRIMARY_DD = 0.05
_ALERT_STATES = ("elevated", "risk-off")


# ── IO helpers ────────────────────────────────────────────────────────────────

def _shadow_path(market: str, variant: str, root=None) -> Path:
    """data/risk_radar_intl/<market>_forward_log_<variant>.jsonl"""
    base = config.data_dir() if root is None else (Path(root) / "data")
    p = base / "risk_radar_intl" / f"{market}_forward_log_{variant}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return rows


def _write_jsonl(p: Path, rows: list[dict]) -> None:
    p.write_text(
        "\n".join(json.dumps(r, separators=(",", ":"), default=str) for r in rows) + "\n",
        encoding="utf-8",
    )


# ── variant construction helpers ──────────────────────────────────────────────

def _comp_leg_pctiles(sub: dict, profile) -> dict[str, float | None]:
    """Mean sub-leg percentile per comp_leg — exactly the value `compute()` stores
    in `comp_last` (mean of sub_codes percentile series, evaluated at the last bar).

    Returns {comp_key: float 0-1 | None}.
    """
    out: dict[str, float | None] = {}
    for comp_key, sub_codes, _w in profile.comp_legs:
        members = [sub[c].dropna() for c in sub_codes if c in sub and sub[c] is not None]
        if not members:
            out[comp_key] = None
            continue
        # mean across sub-legs at last bar (same as compute's pd.concat(...).mean(axis=1))
        vals = [float(s.iloc[-1]) for s in members if len(s)]
        out[comp_key] = float(np.mean(vals)) if vals else None
    return out


def _s1_any95_state(
    incumbent_state: str,
    incumbent_state_ungated: str,
    comp_leg_pcts: dict[str, float | None],
    gate_open: bool,
) -> str:
    """S1-floor construction (RRI_S1 prereg §2):
    If ANY comp-leg pctile >= 0.95 AND gate_open: floor state at _S1_FLOOR_STATE.
    The floor never lifts to risk-off; gate-closed cap law unchanged.

    Returns the variant state (string from _STATE_ORDER).
    """
    # start from the incumbent gated state (which already has the gate cap applied)
    state = incumbent_state
    if gate_open:
        leg_pctiles = [v for v in comp_leg_pcts.values() if v is not None]
        if leg_pctiles and max(leg_pctiles) >= _S1_FLOOR_THRESHOLD:
            # floor: ensure at least _S1_FLOOR_STATE
            idx_current = _STATE_ORDER.index(state) if state in _STATE_ORDER else 0
            idx_floor = _STATE_ORDER.index(_S1_FLOOR_STATE)
            state = _STATE_ORDER[max(idx_current, idx_floor)]
    return state


def _build_s3_composite(
    B: pd.Series,
    sub: dict,
    profile,
    ret_window: int,
) -> tuple[pd.Series | None, pd.Series | None]:
    """Rebuild composite_series with an added velocity leg.

    velocity = pct_rank_window( -close.pct_change(ret_window).dropna(), 504 )
    comp_legs_v3 = profile.comp_legs + [("velocity", ("dd_velocity",), 0.6)]

    Blend + trailing-504d re-percentile exactly as composite_series
    (fillna(0.5) at comp-leg level, den = notna*w, pct_rank_window on num/den dropna).

    Returns (comp_v3, gate_series) where comp_v3 is the re-percentiled composite
    (0-1) on B.index, and gate_series is the gate boolean (unchanged from the
    original _gate_series call — we reuse the gate from composite_series output).
    """
    from engine.risk_radar_intl import _band, _gate_series, _PCT_WIN

    # velocity sub-leg: −ret<n> causal trailing percentile
    ret = -B.pct_change(ret_window).dropna()
    if len(ret) < _S3_VEL_PCT_WIN // 2:
        return None, None
    vel = pct_rank_window(ret, _S3_VEL_PCT_WIN)   # 0-1, aligned on B.index where present

    # augmented sub dict (velocity added; does not overwrite existing legs)
    sub_aug = dict(sub)
    sub_aug["dd_velocity"] = vel

    # augmented comp_legs: incumbent + velocity
    comp_legs_v3 = list(profile.comp_legs) + [("velocity", ("dd_velocity",), _S3_VEL_WEIGHT)]

    # blend (exact replica of composite_series inner loop)
    num = den = None
    for comp_key, sub_codes, w in comp_legs_v3:
        members = [sub_aug[c] for c in sub_codes if c in sub_aug and sub_aug[c] is not None]
        if not members:
            continue
        ser = pd.concat(members, axis=1).mean(axis=1) if len(members) > 1 else members[0]
        col = ser.fillna(0.5) * w
        av = ser.notna().astype(float) * w
        num = col if num is None else num + col
        den = av if den is None else den + av

    if num is None or den is None:
        return None, None

    blend = (num / den.replace(0, np.nan)).dropna()
    if len(blend) < _PCT_WIN // 2:
        return None, None

    comp_v3 = pct_rank_window(blend, _PCT_WIN)
    return comp_v3, None   # gate reused from caller (unchanged by velocity leg)


# ── public API ────────────────────────────────────────────────────────────────

def shadow_snapshot(
    profile,
    B: "pd.Series",
    sub: "dict",
    comp: "pd.Series",
    gate: "pd.Series",
) -> "dict[str, dict]":
    """Compute today's shadow rows for all 3 ACCRUE variants for one profile.

    Accepts pre-computed (B, sub, comp, gate) from composite_series so the
    substrate is computed once per market, not per variant (budget law).

    Returns {variant: row_dict} — a dict with keys from VARIANTS.  Each row
    is JSON-safe and matches the schema documented in the module docstring.
    Never raises.
    """
    from engine.risk_radar_intl import _band, _BANDS

    rows: dict[str, dict] = {}
    try:
        if B is None or comp is None or gate is None or not len(B):
            return rows

        # Common values
        asof_str = str(pd.Timestamp(B.index[-1]).date())
        gate_open = bool(gate.iloc[-1]) if len(gate) else False
        logged_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        # Incumbent state from comp+gate (needed for s1 floor logic)
        top = float(comp.dropna().iloc[-1]) if len(comp.dropna()) else None
        if top is None:
            return rows

        top100 = top * 100.0
        bands = _BANDS
        state_ungated = _band(top100, bands)
        state_inc = state_ungated
        if not gate_open and _STATE_ORDER.index(state_ungated) > _STATE_ORDER.index("caution"):
            state_inc = "caution"

        # Comp-leg pctiles (used for s1_any95 trigger + leg payload)
        comp_leg_pcts = _comp_leg_pctiles(sub, profile)

        # ── s1_any95 ──────────────────────────────────────────────────────────
        try:
            s1_state = _s1_any95_state(state_inc, state_ungated, comp_leg_pcts, gate_open)
            leg_payload_s1 = {k: round(v, 4) if v is not None else None
                              for k, v in comp_leg_pcts.items()}
            rows["s1_any95"] = {
                "asof": asof_str,
                "market": profile.key,
                "variant": "s1_any95",
                "construction": "v2_s1_any95",
                "state": s1_state,
                "state_ungated": state_ungated,
                "top_score": round(top100),
                "alert": s1_state in _ALERT_STATES,
                "legs": leg_payload_s1,
                "gate_open": gate_open,
                "logged_at": logged_at,
                "graded": None,
            }
        except Exception as e:  # noqa: BLE001
            log.warning("rri_shadow s1_any95(%s) snapshot failed: %s", profile.key, e)

        # ── s3_ret10 and s3_ret21 ─────────────────────────────────────────────
        for variant, ret_window in _S3_VEL_WINDOWS.items():
            try:
                comp_v3, _ = _build_s3_composite(B, sub, profile, ret_window)
                if comp_v3 is None or comp_v3.dropna().empty:
                    continue
                top_v3_raw = float(comp_v3.dropna().iloc[-1])
                top_v3_100 = top_v3_raw * 100.0
                s3_state_ung = _band(top_v3_100, bands)
                s3_state = s3_state_ung
                if not gate_open and _STATE_ORDER.index(s3_state_ung) > _STATE_ORDER.index("caution"):
                    s3_state = "caution"

                # velocity last value (for the legs payload)
                ret = -B.pct_change(ret_window).dropna()
                if len(ret) < 2:
                    vel_last = None
                else:
                    vel = pct_rank_window(ret, _S3_VEL_PCT_WIN)
                    vel_last = float(vel.dropna().iloc[-1]) if len(vel.dropna()) else None

                leg_payload_s3 = {k: round(v, 4) if v is not None else None
                                  for k, v in comp_leg_pcts.items()}
                if vel_last is not None:
                    leg_payload_s3["velocity"] = round(vel_last, 4)

                rows[variant] = {
                    "asof": asof_str,
                    "market": profile.key,
                    "variant": variant,
                    "construction": f"v2_{variant}",
                    "state": s3_state,
                    "state_ungated": s3_state_ung,
                    "top_score": round(top_v3_100),
                    "alert": s3_state in _ALERT_STATES,
                    "legs": leg_payload_s3,
                    "gate_open": gate_open,
                    "logged_at": logged_at,
                    "graded": None,
                }
            except Exception as e:  # noqa: BLE001
                log.warning("rri_shadow %s(%s) snapshot failed: %s", variant, profile.key, e)

    except Exception as e:  # noqa: BLE001
        log.warning("rri_shadow shadow_snapshot(%s) outer failed: %s",
                    getattr(profile, "key", "?"), e)
    return rows


def log_shadow(market: str, rows: "dict[str, dict]", root=None) -> int:
    """Append shadow rows to their variant-specific forward logs.

    Idempotent by asof per variant file (first-writer-wins).
    Self-gates: returns 0 without writing if ledger_lane_armed() is False
    (defense in depth — callers should also check, but this ensures correctness
    regardless of call site discipline; mirrors the #2688/#2693 lane-gate class).

    Returns the count of rows actually appended (0 or 1 per variant).
    """
    try:
        from engine.risk_radar_intl_audit import ledger_lane_armed
        if not ledger_lane_armed():
            return 0
    except Exception as e:  # noqa: BLE001
        log.warning("rri_shadow log_shadow(%s): lane-gate check failed (%s); skipping", market, e)
        return 0

    n = 0
    for variant, row in rows.items():
        if variant not in VARIANTS:
            continue
        try:
            asof = row.get("asof")
            if not asof:
                continue
            p = _shadow_path(market, variant, root)
            existing = _read_jsonl(p)
            if any(r.get("asof") == asof for r in existing):
                continue                # idempotent
            existing.append(row)
            _write_jsonl(p, existing)
            n += 1
        except Exception as e:  # noqa: BLE001
            log.warning("rri_shadow log_shadow(%s/%s) failed: %s", market, variant, e)
    return n


def grade_shadow(market: str, root=None) -> int:
    """Grade matured, ungraded shadow rows across all variants for one market.

    Uses the same forward-drawdown ruler as risk_radar_intl_audit._grade_entry:
    base price = close on as-of, outcome = min over next h5/h10/h21 business days,
    hit = min/base - 1 <= -5% (primary) or -8%.  Reuses the audit's bench reader.

    Returns total count of rows graded across all variant files.

    Self-gates: returns 0 without writing if ledger_lane_armed() is False.
    """
    try:
        from engine.risk_radar_intl_audit import ledger_lane_armed, _bench as _audit_bench
        if not ledger_lane_armed():
            return 0
    except Exception as e:  # noqa: BLE001
        log.warning("rri_shadow grade_shadow(%s): gate/bench import failed (%s); skipping", market, e)
        return 0

    total = 0
    try:
        # Resolve the profile to load the bench
        from engine.risk_radar_intl import PROFILES
        profile = PROFILES.get(market)
        if profile is None:
            log.warning("rri_shadow grade_shadow(%s): no profile found", market)
            return 0
        px = _audit_bench(profile)
        if px is None:
            return 0

        for variant in VARIANTS:
            try:
                p = _shadow_path(market, variant, root)
                existing = _read_jsonl(p)
                if not existing:
                    continue
                n_this = 0
                for row in existing:
                    if row.get("graded"):
                        continue
                    graded = _grade_shadow_entry(row, px)
                    if graded is not None:
                        row["graded"] = graded
                        n_this += 1
                if n_this:
                    _write_jsonl(p, existing)
                    total += n_this
            except Exception as e:  # noqa: BLE001
                log.warning("rri_shadow grade_shadow(%s/%s) failed: %s", market, variant, e)
    except Exception as e:  # noqa: BLE001
        log.warning("rri_shadow grade_shadow(%s) outer failed: %s", market, e)
    return total


def _grade_shadow_entry(entry: dict, px: pd.Series) -> dict | None:
    """Realized max-drawdown per horizon from as-of.  Mirrors
    risk_radar_intl_audit._grade_entry exactly.

    Returns None until the longest horizon (h21) has matured.
    """
    try:
        asof = pd.Timestamp(entry["asof"])
        loc = px.index.searchsorted(asof, side="right")
        maxH = max(_HORIZONS.values())
        if loc + maxH > len(px):
            return None
        base_px = float(px.iloc[max(0, loc - 1)])
        fwd_dd: dict[str, float | None] = {}
        hit: dict[str, dict] = {}
        for hk, hd in _HORIZONS.items():
            w = px.iloc[loc: loc + hd]
            dd = float(w.min() / base_px - 1.0) if len(w) else None
            fwd_dd[hk] = None if dd is None else round(dd, 4)
            hit[hk] = {f"dd{int(t * 100)}": (dd is not None and dd <= -t)
                       for t in _DD_THRESHOLDS}
        any_primary = any(fwd_dd[hk] is not None and fwd_dd[hk] <= -_PRIMARY_DD
                          for hk in _HORIZONS)
        st = entry.get("state")
        if st in _ALERT_STATES:
            outcome = "true_positive" if any_primary else "false_positive"
        elif st in ("watch", "caution"):
            outcome = "tp_watch" if any_primary else "tn_watch"
        else:
            outcome = "calm_dd" if any_primary else "calm_quiet"
        return {
            "base_px": round(base_px, 2),
            "fwd_dd": fwd_dd,
            "hit": hit,
            "outcome": outcome,
            "any_dd5_within_h21": bool(any_primary),
            "graded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    except Exception as e:  # noqa: BLE001
        log.warning("rri_shadow _grade_shadow_entry failed: %s", e)
        return None
