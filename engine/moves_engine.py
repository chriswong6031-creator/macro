"""engine/moves_engine.py — the learned expected-move ("Moves") plane.

Voltick Gamma-Levels program, Phase B. Turns today's ATM IV into the move the options are
pricing — the 1-session expected-move band — and pairs it with the HISTORICAL containment
rate for that ticker: how often the next session's range actually stayed inside a band built
the same way, reconstructed from the deep greeks store by the levels Track Record driver
(scripts/build_levels_track_record.py → data/levels/grades.parquet).

The pairing is the whole point and the whole discipline: the band shown is built at the SAME
multiplier the containment was measured at, so "options price a ±X% move; a band like this has
contained the next-day range R% of the time (n sessions)" is a matched, honest statement —
never a naked projection dressed up with an unrelated hit-rate.

DISPLAY-TIER: the expected move is what the options imply under a lognormal 1-sigma scaling;
the containment is a measurement about the past, not a forecast. Positioning, not prophecy —
never a buy/sell, a target, or a win rate. Calibration is null (shown as "no graded history
yet") below MIN_CALIB_SESSIONS — a rate is never quoted on a handful of days. The learned
multiplier that targets ~2/3 containment rides along as a labeled note, not as the drawn band.

PURE: no I/O, no clock. The nightly options-hub builder loads today's spot + ATM IV and the
per-ticker graded history and calls moves_payload here — exactly as it calls compute_gex/vex.
"""
from __future__ import annotations

import math
from typing import Any

from engine.levels_grade import expected_move_band  # reuse the exact band the grader used

SCHEMA = "options_hub.moves/v1"
DEFAULT_BAND_MULT = 1.96      # the ~95% two-sided normal band the Track Record grades at
MIN_CALIB_SESSIONS = 8        # below this, calibration is null (too few to quote a rate)


def _num(x: Any) -> float | None:
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def expected_move(
    spot: float | None, atm_iv: float | None,
    band_mult: float = DEFAULT_BAND_MULT, horizon_days: float = 1.0,
) -> dict | None:
    """The expected-move band from ATM IV: ``{pct, lo, hi, band_mult, horizon_days}`` or None.

    Delegates the band math to engine.levels_grade.expected_move_band so the move shown here is
    identical to the one the Track Record grades. ``pct`` is the ± half-width as a percent of spot.
    """
    band = expected_move_band(spot, atm_iv, band_mult, horizon_days=horizon_days)
    s = _num(spot)
    if band is None or s is None or s <= 0:
        return None
    lo, hi = band
    half = (hi - lo) / 2.0
    return {
        "band_mult": round(float(band_mult), 4),
        "horizon_days": round(float(horizon_days), 4),
        "pct": round(half / s * 100.0, 4),
        "lo": round(lo, 4),
        "hi": round(hi, 4),
    }


def per_ticker_calibration(
    board_rows: list[dict] | None, ci_fn=None, min_sessions: int = MIN_CALIB_SESSIONS,
) -> dict | None:
    """Per-ticker 1-session band-containment from reconstructed graded boards.

    ``board_rows`` = list of ``{band_contained: bool|None, band_mult, session_date}`` — one row
    per graded board for this root (dedup by board upstream). Only rows where ``band_contained``
    is not None are counted. Returns None below ``min_sessions`` (honest — no rate on a handful
    of days) or when nothing is graded. ``ci_fn(k, n) -> (lo, hi)`` attaches a Wilson CI.
    """
    rows = [r for r in (board_rows or []) if r.get("band_contained") is not None]
    n = len(rows)
    if n < max(min_sessions, 1):
        return None
    hits = sum(1 for r in rows if r.get("band_contained"))
    mults = [m for r in rows if (m := _num(r.get("band_mult"))) is not None]
    dates = sorted(str(r.get("session_date")) for r in rows if r.get("session_date"))
    out: dict[str, Any] = {
        "contained_rate": round(hits / n, 4),
        "n_sessions": n,
        "hits": hits,
        "misses": n - hits,
        "band_mult": (round(sum(mults) / len(mults), 4) if mults else None),
        "since": (dates[0] if dates else None),
        "through": (dates[-1] if dates else None),
    }
    if ci_fn is not None:
        ci = ci_fn(hits, n)
        out["ci"] = ([round(ci[0], 4), round(ci[1], 4)] if ci else None)
    return out


def pick_learned_mult(learned_band_mult: dict | None, regime: str | None) -> float | None:
    """Regime-aware learned multiplier (the ±K·σ that historically contained ~2/3 of moves).

    ``learned_band_mult`` = ``{all, sticky, slippery, ...}`` (track_record.json). Prefer the
    regime cohort, fall back to ``all``, then None.
    """
    if not isinstance(learned_band_mult, dict):
        return None
    keys = ((regime,) if regime in ("sticky", "slippery") else ()) + ("all",)
    for key in keys:
        v = _num(learned_band_mult.get(key))
        if v is not None:
            return round(v, 4)
    return None


def moves_payload(
    root: str, asof: str, spot: float | None, atm_iv_pct: float | None,
    calibration: dict | None = None, learned_band_mult: dict | None = None,
    regime: str | None = None, band_mult: float = DEFAULT_BAND_MULT,
) -> dict:
    """Build the ``options_hub.moves/v1`` payload for one root.

    ``spot`` + ``atm_iv_pct`` are today's live inputs. IMPORTANT UNITS: ``atm_iv_pct`` is the
    vol-plane ATM IV expressed in PERCENT (e.g. 13.71 for 13.71% — options_hub.vol/v1's
    ``atm_iv``); the band math needs a decimal, so we convert internally. The payload stores it
    in percent for display-consistency with the vol plane.

    ``calibration`` is the per-ticker historical containment of the same-multiplier band
    (per_ticker_calibration). HONEST CAVEAT: the live band uses the 30-day ATM IV, while the
    reconstructed grading (data/levels/grades.parquet) built its bands from that day's
    chain-median IV — the SAME 1.96 multiplier, a comparable but not identical IV proxy. So this
    is two labeled facts (the move priced now / how a 1.96σ band has held historically), not a
    claim that the drawn band is the graded band. ``learned_band_mult`` is the regime-aware
    "to contain ~2/3 you needed ±K·σ" fact from the Track Record, a labeled note. Never raises.
    """
    iv_dec = (atm_iv_pct / 100.0) if _num(atm_iv_pct) is not None else None
    em = expected_move(spot, iv_dec, band_mult=band_mult)
    learned = pick_learned_mult(learned_band_mult, regime)
    return {
        "schema": SCHEMA,
        "asof": asof,
        "root": root,
        "spot_ref": _num(spot),
        "atm_iv": _num(atm_iv_pct),   # percent, matching options_hub.vol/v1
        "regime": regime,
        "expected_move": em,          # {pct, lo, hi, band_mult, horizon_days} | None (30-day ATM IV)
        "calibration": calibration,   # historical containment of the same-multiplier band | None
        "learned_band_mult": (
            {
                "value": learned,
                "target_containment": 0.667,
                "note": "smallest ±K·σ expected-move band that would have contained the next "
                        "session's range ~2/3 of the time historically, learned for this "
                        "regime; the drawn band above uses the standard 1.96 (~95%) multiplier.",
            }
            if learned is not None else None
        ),
        "convention": "expected move = spot ± spot·(atm_iv/100)·sqrt(h/252)·mult (lognormal 1σ, "
                      "30-day ATM IV); calibration is how often a same-multiplier band (built "
                      "from that day's chain-median IV) contained the next session's range — a "
                      "measurement about the past, comparable IV proxy not identical. Positioning, "
                      "not prophecy — not a buy/sell, a target, or a win rate. Misses are shown.",
    }
