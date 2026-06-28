"""Single-name implied-volatility SKEW — the Xing-Zhang-Zhao (2010) cross-sectional
return predictor: steep OTM-put-over-ATM-call IV (informed put buying / crash fear)
historically preceded LOWER forward returns.

This computes skew = IV(25-delta OTM put) − IV(50-delta ATM call) at the ~30-day
expiry, per underlying, from the per-strike chain snapshots the GEX desk already
persists (data/polygon_gex/chains/<date>.parquet — K, T, iv, delta, is_call, spot).

HONEST STATE — DISPLAY-ONLY / NOT SCORED. The chain store covers only ~10 mega-cap
underlyings with a handful of dated snapshots, which is far below the breadth (a real
cross-section) and history (~120 trading days) a return-predictor validation needs.
So this builds the SIGNAL + a forward-accruing snapshot ledger + a dormant validation
gate (scripts/validate_options_skew.py); the gate stays closed — and the leg stays
context — until the panel is wide and long enough to earn a verdict. PURE compute;
disk IO is isolated in snapshot()/load_*.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "options_skew.v1"
_TARGET_DAYS = 30.0            # ~1-month tenor (Xing-Zhang-Zhao)
_MIN_DAYS = 7.0
_PUT_DELTA = -0.25            # OTM put target
_CALL_DELTA = 0.50           # ATM call target


def _nearest_expiry(rows, target_days: float = _TARGET_DAYS, min_days: float = _MIN_DAYS):
    """The single expiry whose tenor is closest to `target_days` (≥ min_days). Returns
    a filtered frame or None. `rows` is one underlying's chain (column T in YEARS)."""
    try:
        df = rows.copy()
        df["_days"] = df["T"].astype(float) * 365.0
        cand = df[df["_days"] >= min_days]
        if cand.empty:
            cand = df[df["_days"] > 0]        # all short-dated → take the longest LIVE expiry
        if cand.empty:                        # only expired/0DTE rows → no usable tenor
            return None
        target_exp = cand.loc[(cand["_days"] - target_days).abs().idxmin(), "expiry"]
        return df[df["expiry"] == target_exp]
    except Exception as e:  # noqa: BLE001
        log.debug("nearest expiry failed (%s)", e)
        return None


def _iv_at_delta(leg, target_delta: float, want_call: bool):
    """IV of the option whose delta is closest to target (delta-first), falling back to
    moneyness if delta is unusable. Returns (iv, used_delta, K) or None."""
    import pandas as pd
    sub = leg[(leg["is_call"] == want_call) & (leg["iv"] > 0.0)]
    if sub.empty:
        return None
    d = pd.to_numeric(sub["delta"], errors="coerce")
    if d.notna().sum() >= 1 and d.abs().between(0.02, 0.98).any():
        sub = sub.assign(_dd=(d - target_delta).abs())
        r = sub.loc[sub["_dd"].idxmin()]
        return float(r["iv"]), float(r["delta"]), float(r["K"])
    # moneyness fallback: 25-delta put ≈ K/S 0.95, ATM call ≈ K/S 1.0
    spot = float(sub["spot"].iloc[0])
    if spot <= 0:
        return None
    target_mny = 1.0 if want_call else 0.95
    sub = sub.assign(_mm=(sub["K"].astype(float) / spot - target_mny).abs())
    r = sub.loc[sub["_mm"].idxmin()]
    return float(r["iv"]), float("nan"), float(r["K"])


def compute_skew(rows) -> dict | None:
    """Implied skew for one underlying's chain frame. PURE.
    Returns {underlying, asof, spot, tenor_days, otm_put_iv, atm_call_iv, skew, ...}."""
    try:
        if rows is None or getattr(rows, "empty", True):
            return None
        leg = _nearest_expiry(rows)
        if leg is None or leg.empty:
            return None
        put = _iv_at_delta(leg, _PUT_DELTA, want_call=False)
        call = _iv_at_delta(leg, _CALL_DELTA, want_call=True)
        if put is None or call is None:
            return None
        otm_put_iv, _, _ = put
        atm_call_iv, _, _ = call
        skew = otm_put_iv - atm_call_iv
        spot = float(leg["spot"].iloc[0])
        tenor = float(leg["T"].astype(float).iloc[0] * 365.0)
        asof = leg["asof"].iloc[0]
        asof = str(asof.date()) if hasattr(asof, "date") else str(asof)[:10]
        return {
            "underlying": str(leg["underlying"].iloc[0]).upper(),
            "asof": asof, "spot": round(spot, 4),
            "tenor_days": round(tenor, 1),
            "otm_put_iv": round(otm_put_iv, 4),
            "atm_call_iv": round(atm_call_iv, 4),
            "skew": round(skew, 4),
            "n_strikes": int(len(leg)),
        }
    except Exception as e:  # noqa: BLE001
        log.debug("compute_skew failed (%s)", e)
        return None


def skew_map(chain) -> dict[str, dict]:
    """{underlying: skew metrics} over a full chain snapshot (many underlyings). PURE."""
    out: dict[str, dict] = {}
    try:
        if chain is None or getattr(chain, "empty", True) or "underlying" not in chain.columns:
            return out
        for u, g in chain.groupby("underlying"):
            m = compute_skew(g)
            if m is not None:
                out[str(u).upper()] = m
    except Exception as e:  # noqa: BLE001
        log.debug("skew_map failed (%s)", e)
    return out


# --------------------------------------------------------------------------- #
# Disk: forward-accruing snapshot ledger (the apparatus that earns a verdict over time)
# --------------------------------------------------------------------------- #
def _snap_path():
    p = config.data_dir() / "options_skew"
    p.mkdir(parents=True, exist_ok=True)
    return p / "snapshots.parquet"


def _latest_chain():
    import glob
    import pandas as pd
    files = sorted(glob.glob(str(config.data_dir() / "polygon_gex" / "chains" / "*.parquet")))
    return pd.read_parquet(files[-1]) if files else None


def snapshot(today: date | None = None, chain=None) -> int:
    """Append today's per-underlying skew to the ledger (idempotent by (date, underlying)).
    Returns the number of rows added. This is what accrues the history a validation needs."""
    import pandas as pd
    today = today or date.today()
    if chain is None:
        chain = _latest_chain()
    if chain is None:
        return 0
    # key each row by the chain's OWN as-of date, not wall-clock `today` — a stale chain
    # must not be recorded under today's date (that would duplicate content across two date
    # keys and corrupt any forward-IC computed off the ledger).
    rows = [{"date": (m.get("asof") or today.isoformat()), **m}
            for m in skew_map(chain).values()]
    if not rows:
        return 0
    fresh = pd.DataFrame(rows)
    p = _snap_path()
    if p.exists():
        prev = pd.read_parquet(p)
        key = set(zip(prev["date"], prev["underlying"]))
        fresh = fresh[~fresh.apply(lambda r: (r["date"], r["underlying"]) in key, axis=1)]
        if fresh.empty:
            return 0
        combined = pd.concat([prev, fresh], ignore_index=True)
    else:
        combined = fresh
    combined.to_parquet(p)
    return int(len(fresh))


def load_history():
    import pandas as pd
    p = _snap_path()
    return pd.read_parquet(p) if p.exists() else None


def load_gate() -> dict | None:
    """The validation verdict (scripts/validate_options_skew.py). None → 'measuring'."""
    try:
        import json
        p = config.data_dir() / "options_skew" / "validation_gate.json"
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def build_snapshot(today: date | None = None) -> dict:
    """Display payload: latest skew per name + the (likely-dormant) gate. CONTEXT-ONLY."""
    today = today or date.today()
    chain = _latest_chain()
    names = skew_map(chain) if chain is not None else {}
    gate = load_gate() or {}
    ranked = sorted(names.values(), key=lambda m: m["skew"], reverse=True)
    return {
        "schema": SCHEMA, "is_context_only": True,
        "scored": bool(gate.get("scored")),
        "as_of": today.isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "names": names, "ranked": ranked, "n": len(names),
        "gate_status": gate.get("status", "measuring"),
        "disclaimer": ("Single-name IV skew (25Δ OTM put − 50Δ ATM call, ~30d). "
                       "DISPLAY-ONLY context: the chain panel is too narrow/short to "
                       "validate as a return predictor — accruing toward a verdict."),
    }
