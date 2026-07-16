"""Validation gate for the single-name IV-skew leg (Xing-Zhang-Zhao return predictor).

Reconstructs a skew panel from the dated per-strike chain snapshots
(data/polygon_gex/chains/<date>.parquet), computes SPY-relative forward returns per
(date, underlying) using each snapshot's spot, and tests the cross-sectional
hypothesis: HIGH put-over-call skew → LOWER forward returns (a NEGATIVE rank IC).

The gate opens (scored=True) only when the panel clears a real power floor — ≥120
entry dates and ≥15 underlyings per date — with a sign-correct, HAC-significant IC.
Today the chain store holds ~10 mega-caps over a handful of days, so the honest
output is status="insufficient_history", scored=False. Re-run as the GEX desk's
chain snapshots accrue; the apparatus is leak-free and forward-compatible.

Output: data/options_skew/validation_gate.json

Refactoring note (Phase-B gate re-run harness):
  build_panel() accepts an optional `chain_provider` argument for injecting an
  alternative per-date chain-frame source (e.g. the ThetaData historical store).
  Default (chain_provider=None) is byte-identical to the original: reads from
  the durable snapshot ledger + polygon_gex chains, exactly as before.
  Pass a callable (date_str, root) -> pd.DataFrame | None to use a different store.
  The entrypoint main() is unchanged; use --store thetadata to switch.
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import options_skew as S  # noqa: E402
from engine import validation as V  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("validate_skew")

_HORIZONS = [5, 10, 21]
_MIN_DATES = 120              # trading-day history floor for a return-predictor verdict
_MIN_NAMES = 15              # cross-sectional breadth floor per date
_T_BAR = 2.0


def build_panel(
    chain_provider: Callable[[str, str], "pd.DataFrame | None"] | None = None,
) -> pd.DataFrame:
    """skew per (date, underlying) + that day's spot.

    Default (chain_provider=None): reads from the durable snapshot ledger
    (engine.options_skew — date-stable, dedup'd, survives chain pruning),
    supplemented by any dated chain snapshots not yet in the ledger.
    Byte-identical to the original implementation when no provider is passed.

    When chain_provider is supplied (Phase-B re-run harness):
      The provider is called as provider(date_str, root) for each
      (date, root) combination in the alternative store. Results are merged
      with the same dedup logic (ledger wins on conflicts). This keeps the
      existing polygon_gex path untouched and adds the injected source.
    """
    rows, seen = [], set()
    led = S.load_history()
    if led is not None and not led.empty:
        for r in led.itertuples(index=False):
            key = (str(r.date), str(r.underlying))
            if key not in seen:
                rows.append({"date": str(r.date), "underlying": str(r.underlying),
                             "skew": float(r.skew), "spot": float(r.spot)})
                seen.add(key)
    for f in sorted(glob.glob(str(config.data_dir() / "polygon_gex" / "chains" / "*.parquet"))):
        d = Path(f).stem                           # chain filename == its as-of date
        try:
            chain = pd.read_parquet(f)
        except Exception:  # noqa: BLE001
            continue
        for u, m in S.skew_map(chain).items():
            if (d, u) not in seen:
                rows.append({"date": d, "underlying": u, "skew": m["skew"], "spot": m["spot"]})
                seen.add((d, u))

    # Injected provider (Phase-B ThetaData path) — appends to the same panel
    if chain_provider is not None:
        # WP-RESOLVER: a provider run is meaningless without a store → required=True.
        # Resolved OUTSIDE the try below so the failure raises instead of being
        # swallowed into a warning (fail-loud contract for validators).
        from engine.thetadata_store import resolve_thetadata_store  # noqa: PLC0415
        td_store = resolve_thetadata_store(
            required=True, purpose="validate_options_skew chain_provider panel")
        try:
            from engine.thetadata_store import universe as td_universe  # noqa: PLC0415
            roots = td_universe(store=td_store)
            for root in roots:
                base = td_store / "greeks" / root
                if not base.exists():
                    continue
                for f in sorted(base.glob("*.parquet")):
                    try:
                        df = pd.read_parquet(f, columns=["date"])
                        for d in pd.to_datetime(df["date"]).dt.date.astype(str).unique():
                            chain_frame = chain_provider(d, root)
                            if chain_frame is None or chain_frame.empty:
                                continue
                            for u, m in S.skew_map(chain_frame).items():
                                if (d, u) not in seen:
                                    rows.append({"date": d, "underlying": u,
                                                 "skew": m["skew"], "spot": m["spot"]})
                                    seen.add((d, u))
                    except Exception as e:  # noqa: BLE001
                        log.debug("provider chain %s/%s: %s", root, f, e)
        except Exception as e:  # noqa: BLE001
            log.warning("chain_provider integration failed: %s", e)

    return pd.DataFrame(rows)


def _fwd_ic(panel: pd.DataFrame, h: int) -> dict:
    """Per-date cross-sectional rank IC of skew vs SPY-relative fwd return over h days,
    using the panel's own spots (leak-free: future date strictly after the signal date)."""
    if panel.empty:
        return {"n_dates": 0}
    spot = panel.pivot_table(index="date", columns="underlying", values="spot")
    skew = panel.pivot_table(index="date", columns="underlying", values="skew")
    spot = spot.sort_index()
    skew = skew.sort_index()
    dates = list(spot.index)
    spy = spot["SPY"] if "SPY" in spot.columns else None
    ics = []
    for i, d0 in enumerate(dates):
        if i + h >= len(dates):
            break
        d1 = dates[i + h]
        fwd = spot.loc[d1] / spot.loc[d0] - 1.0
        if spy is not None:
            fwd = fwd - (spy.loc[d1] / spy.loc[d0] - 1.0)
        sig = skew.loc[d0]
        names = [c for c in sig.index if c != "SPY"
                 and np.isfinite(sig.get(c, np.nan)) and np.isfinite(fwd.get(c, np.nan))]
        if len(names) >= 10:                       # validation.rank_ic returns NaN below 10 joint names
            ic = V.rank_ic(sig[names].values, fwd[names].values)
            if np.isfinite(ic):
                ics.append(ic)
    if not ics:
        return {"n_dates": 0}
    summ = V.ic_summary(np.array(ics), periods_per_year=max(1, 252 // h))
    # ic_summary() returns "t_hac" (Newey-West HAC t-stat) — NOT "t" or "hac_t".
    # Using the wrong key silently produces NaN t-stats and a dead gate verdict.
    return {"n_dates": len(ics), "mean_ic": round(float(summ.get("mean_ic", float("nan"))), 4),
            "hac_t": round(float(summ.get("t_hac", float("nan"))), 2)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default=None,
                        choices=["thetadata"],
                        help="Chain provider: 'thetadata' injects the ThetaData store. "
                             "Default (omitted): uses polygon_gex chains (original behaviour).")
    args, _ = parser.parse_known_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    chain_provider = None
    if args.store == "thetadata":
        # WP-RESOLVER: resolve ONCE up front (required=True — the validator is
        # meaningless without a store) and hand the SAME store to the provider,
        # so the provider reads exactly the store the panel enumerates.
        from engine.thetadata_store import (  # noqa: PLC0415
            make_chain_provider, resolve_thetadata_store,
        )
        td_store = resolve_thetadata_store(
            required=True, purpose="validate_options_skew --store thetadata")
        chain_provider = make_chain_provider(store=td_store, require_iv=True)
        log.info("Using ThetaData chain provider (--store thetadata, store=%s)", td_store)

    panel = build_panel(chain_provider=chain_provider)
    n_dates = panel["date"].nunique() if not panel.empty else 0
    n_names = panel["underlying"].nunique() if not panel.empty else 0
    log.info("skew panel: %d dates × %d underlyings (%d rows)", n_dates, n_names, len(panel))

    ic = {h: _fwd_ic(panel, h) for h in _HORIZONS}
    enough = n_dates >= _MIN_DATES and n_names >= _MIN_NAMES
    # the predictor sign is NEGATIVE (high skew → low fwd return)
    scored = bool(enough and any(
        v.get("n_dates", 0) >= _MIN_DATES and v.get("mean_ic", 0) < 0
        and abs(v.get("hac_t", 0)) >= _T_BAR for v in ic.values()))
    status = ("ok" if enough else
              f"insufficient_history (have {n_dates}/{_MIN_DATES} dates, "
              f"{n_names}/{_MIN_NAMES} names)")

    gate = {
        "schema": "options_skew.gate.v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "scored": scored, "status": status, "weight": 1.0 if scored else 0.0,
        "n_dates": int(n_dates), "n_names": int(n_names),
        "min_dates": _MIN_DATES, "min_names": _MIN_NAMES,
        "ic_by_horizon": ic,
        "note": ("skew is a sign-correct, HAC-significant cross-sectional return predictor "
                 "→ SCORED" if scored else
                 "the chain panel is too narrow/short to validate skew as a return predictor "
                 "→ display-only context, accruing toward a verdict"),
    }
    p = config.data_dir() / "options_skew"
    p.mkdir(parents=True, exist_ok=True)
    (p / "validation_gate.json").write_text(json.dumps(gate, indent=2))
    log.info("GATE scored=%s status=%s -> %s", scored, status, p / "validation_gate.json")


if __name__ == "__main__":
    main()
