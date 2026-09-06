"""Single-name implied-volatility SKEW — the Xing-Zhang-Zhao (2010) cross-sectional
return predictor: steep OTM-put-over-ATM-call IV (informed put buying / crash fear)
historically preceded LOWER forward returns.

This computes skew = IV(25-delta OTM put) − IV(50-delta ATM call) at the ~30-day
expiry, per underlying, from the ThetaData chain store (engine/thetadata_store.py
`chain()`/`make_chain_provider()`) — columns underlying, expiry, K, T, iv, delta,
is_call, spot, oi, volume, asof.

The legacy `data/polygon_gex/chains/<date>.parquet` glob is RETIRED: it is reachable
only behind the explicit, off-by-default `OPTIONS_SKEW_LEGACY_CHAIN=1` env flag, and
is never used as an automatic fallback. As of 2026-08-13 the legacy store had reached
372 underlyings / 185,072 rows on its newest date — the earlier "~10 mega-cap
underlyings" claim here was stale; both that framing and F00B's "ThetaData canonical"
claim for this leg were superseded by the measured migration in MO-PAID-013.

HONEST STATE — DISPLAY-ONLY / NOT SCORED. This builds the SIGNAL + a forward-accruing
snapshot ledger + a dormant validation gate (scripts/validate_options_skew.py); the
gate stays closed — and the leg stays context — until the panel is wide and long
enough to earn a verdict. PURE compute; disk IO is isolated in snapshot()/load_*/
load_chain().
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

# Legacy polygon_gex chain glob — RETIRED. Only reachable when this env flag is
# explicitly set; never an automatic fallback from a ThetaData failure.
_LEGACY_CHAIN_ENV = "OPTIONS_SKEW_LEGACY_CHAIN"

# Strike-unit sanity bounds for K/spot moneyness — outside this band the strike
# column is not in the units this engine assumes (see load_chain step 7).
_MONEYNESS_MIN = 0.2
_MONEYNESS_MAX = 5.0

# A chain older than this many calendar days is published but flagged stale.
_STALE_DAYS = 5


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


def compute_skew(rows, drops: dict | None = None) -> dict | None:
    """Implied skew for one underlying's chain frame. PURE.
    Returns {underlying, asof, spot, tenor_days, otm_put_iv, atm_call_iv, skew, ...}.

    `drops` is an optional out-parameter dict the caller may pass so a rejected
    name can be classified by WHICH leg was unusable (never inferred after the
    fact) — compute_skew's own signature/return are otherwise unchanged."""
    try:
        if rows is None or getattr(rows, "empty", True):
            return None
        underlying = str(rows["underlying"].iloc[0]).upper() if "underlying" in rows.columns else None
        leg = _nearest_expiry(rows)
        if leg is None or leg.empty:
            if drops is not None and underlying:
                drops.setdefault("no_25d_put", []).append(underlying)
                drops.setdefault("no_atm_call", []).append(underlying)
            return None
        if len(leg) < 4:
            if drops is not None and underlying:
                drops.setdefault("insufficient_strikes", []).append(underlying)
            return None
        put = _iv_at_delta(leg, _PUT_DELTA, want_call=False)
        call = _iv_at_delta(leg, _CALL_DELTA, want_call=True)
        if put is None or call is None:
            if drops is not None and underlying:
                if put is None:
                    drops.setdefault("no_25d_put", []).append(underlying)
                if call is None:
                    drops.setdefault("no_atm_call", []).append(underlying)
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


def skew_map(chain, drops: dict | None = None) -> dict[str, dict]:
    """{underlying: skew metrics} over a full chain snapshot (many underlyings). PURE.

    `drops` (optional) collects per-underlying rejection reasons — see compute_skew."""
    out: dict[str, dict] = {}
    try:
        if chain is None or getattr(chain, "empty", True) or "underlying" not in chain.columns:
            return out
        for u, g in chain.groupby("underlying"):
            m = compute_skew(g, drops=drops)
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


def _legacy_enabled() -> bool:
    import os
    return os.environ.get(_LEGACY_CHAIN_ENV, "").strip() in ("1", "true", "TRUE", "yes")


def _legacy_chain():
    """RETIRED polygon_gex path. Only reachable when OPTIONS_SKEW_LEGACY_CHAIN=1."""
    import glob
    import pandas as pd
    files = sorted(glob.glob(str(config.data_dir() / "polygon_gex" / "chains" / "*.parquet")))
    return pd.read_parquet(files[-1]) if files else None


def _latest_store_date(td) -> str | None:
    """Max `date` across every {td}/greeks/*/*.parquet — same enumeration
    scripts/validate_options_skew.py uses to walk the store."""
    import pandas as pd
    base = td / "greeks"
    if not base.exists():
        return None
    dates: list[str] = []
    for root_dir in sorted(base.iterdir()):
        if not root_dir.is_dir():
            continue
        for f in sorted(root_dir.glob("*.parquet")):
            try:
                df = pd.read_parquet(f, columns=["date"])
                dates.extend(pd.to_datetime(df["date"]).dt.date.astype(str).unique().tolist())
            except Exception as e:  # noqa: BLE001
                log.debug("_latest_store_date read failed for %s (%s)", f, e)
    return max(dates) if dates else None


def load_chain(asof: str | None = None, store=None, roots: list[str] | None = None):
    """Load one dated cross-sectional chain frame from the ThetaData store.

    Returns (frame_or_None, state) where state is one of the typed §5 states
    (see build_snapshot). frame columns are exactly the schema
    make_chain_provider emits: underlying, expiry, K, T, iv, delta, is_call,
    spot, oi, volume, asof. PURE except for the store read; never raises.
    """
    import pandas as pd
    from engine.thetadata_store import resolve_thetadata_store, universe, make_chain_provider

    td = store if store is not None else resolve_thetadata_store(
        required=False, purpose="options_skew chain")
    if td is None:
        print("::warning title=options-skew-source::ThetaData store unresolved — "
              "skew emits null (set THETADATA_STORE)", flush=True)
        return None, "thetadata_store_unresolved"

    resolved_asof = asof or _latest_store_date(td)
    if not resolved_asof:
        return None, "no_iv_tier"

    use_roots = roots if roots is not None else universe(resolved_asof, store=td)
    if not use_roots:
        return None, "no_roots_for_date"

    provider = make_chain_provider(store=td, require_iv=True)
    frames = []
    for root in use_roots:
        f = provider(resolved_asof, root)
        if f is None or f.empty:
            continue
        frames.append(f)

    if not frames:
        return None, "no_chain_for_date"

    frame = pd.concat(frames, ignore_index=True)

    # Strike-unit sanity check — never rescale K ourselves; an unproven unit is
    # a null, not a guess (moneyness fallback in _iv_at_delta divides K/spot).
    try:
        mny = float(frame["K"].astype(float).median()) / float(frame["spot"].astype(float).median())
    except Exception:  # noqa: BLE001
        mny = float("nan")
    import math
    if math.isnan(mny) or not (_MONEYNESS_MIN <= mny <= _MONEYNESS_MAX):
        print("::warning title=options-skew-source::strike/spot moneyness "
              f"{mny!r} outside [{_MONEYNESS_MIN},{_MONEYNESS_MAX}] — unit unresolved",
              flush=True)
        return None, "strike_unit_unresolved"

    return frame, "ok"


def snapshot(today: date | None = None, chain=None) -> int:
    """Append today's per-underlying skew to the ledger (idempotent by (date, underlying)).
    Returns the number of rows added. This is what accrues the history a validation needs."""
    import pandas as pd
    today = today or date.today()
    if chain is None:
        chain = _legacy_chain() if _legacy_enabled() else load_chain()[0]
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
    if _legacy_enabled():
        chain, state = _legacy_chain(), "legacy_polygon"
    else:
        chain, state = load_chain()

    drops: dict[str, list] = {}
    names = skew_map(chain, drops=drops) if chain is not None else {}
    source = None if chain is None else ("legacy_polygon" if _legacy_enabled() else "thetadata")

    stale_days = None
    if state == "ok" and names:
        try:
            newest = max(m["asof"] for m in names.values())
            stale_days = (today - date.fromisoformat(newest)).days
            if stale_days > _STALE_DAYS:
                state = "stale_chain"
                print(f"::warning title=options-skew-stale::skew chain is {stale_days}d "
                      "old — publishing stale values", flush=True)
        except Exception as e:  # noqa: BLE001
            log.debug("staleness check failed (%s)", e)

    gate = load_gate() or {}
    ranked = sorted(names.values(), key=lambda m: m["skew"], reverse=True)

    disclaimer = ("Single-name IV skew (25Δ OTM put − 50Δ ATM call, ~30d). "
                  "DISPLAY-ONLY context: the chain panel is too narrow/short to "
                  "validate as a return predictor — accruing toward a verdict.")
    if state != "ok":
        disclaimer += " Source unavailable — no skew reading published for this date."

    return {
        "schema": SCHEMA, "is_context_only": True,
        "scored": bool(gate.get("scored")),
        "as_of": today.isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "names": names, "ranked": ranked, "n": len(names),
        "gate_status": gate.get("status", "measuring"),
        "source": source,
        "source_state": state,
        "source_detail": {
            "asof": (max(m["asof"] for m in names.values()) if names else None),
            "roots_seen": len(names) + sum(len(v) for v in drops.values()),
            "roots_with_iv": len(names),
            "names_dropped_no_25d_put": drops.get("no_25d_put", []),
            "names_dropped_no_atm_call": drops.get("no_atm_call", []),
            "stale_days": stale_days,
        },
        "disclaimer": disclaimer,
    }
