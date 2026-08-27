"""Dormant validation gate for the options information-dislocation primitives.

Tests each PRE-REGISTERED primitive as a cross-sectional return predictor: per-date rank IC
of the NEUTRALISED value vs SPY-relative forward returns, at 5/10/21 days.

Two things make this gate honest rather than decorative:

  1. **The signs are pre-registered in the engine** (`options_dislocation.PREREG_SIGNS`),
     fixed before this gate could ever run on more data. A primitive that "works" with the
     opposite sign FAILS — it does not get re-labelled a discovery.
  2. **The power floor is a hard precondition, not a footnote.** 120 dates × 15 names, the
     same floor the skew/ivspread gates carry. Below it the verdict is
     `insufficient_history` regardless of how attractive the ICs look — and today they look
     attractive precisely because the panel is one short regime with overlapping windows.

BH-FDR is applied across the whole primitive × horizon family, because testing 7 primitives
at 3 horizons and reporting the best one is how a null becomes a headline.

Output: data/options_dislocation/validation_gate.json
Run: python -m scripts.validate_options_dislocation
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import options_dislocation as D  # noqa: E402
from engine import validation as V  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("validate_options_dislocation")

_HORIZONS = [5, 10, 21]
_MIN_DATES = 120           # trading-day floor for a return-predictor verdict
_MIN_NAMES = 15            # cross-sectional breadth floor per date
_T_BAR = 2.0
_FDR_ALPHA = 0.10


def _panel() -> pd.DataFrame:
    """Prefer the durable ledger (date-stable, survives chain pruning); fall back to a
    live rebuild when the ledger has not been written yet."""
    led = D.load_history()
    if led is not None and not led.empty:
        return led
    return D.build_panel()


def _fwd_ic(panel: pd.DataFrame, col: str, h: int) -> dict:
    """Per-date cross-sectional rank IC of `col` vs SPY-relative forward return over h
    dates, using the panel's own spots. Leak-free: the forward date is strictly after
    the signal date, and the signal is never used to pick its own comparison set."""
    if panel.empty or col not in panel.columns:
        return {"n_dates": 0}
    spot = panel.pivot_table(index="date", columns="underlying", values="spot").sort_index()
    sig = panel.pivot_table(index="date", columns="underlying", values=col).sort_index()
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
        if d0 not in sig.index:
            continue
        s0 = sig.loc[d0]
        names = [c for c in s0.index if c != "SPY"
                 and np.isfinite(s0.get(c, np.nan)) and np.isfinite(fwd.get(c, np.nan))]
        if len(names) < 10:      # validation.rank_ic returns NaN below 10 joint names
            continue
        ic = V.rank_ic(s0[names].values, fwd[names].values)
        if np.isfinite(ic):
            ics.append(ic)
    if not ics:
        return {"n_dates": 0}
    # hac_lags=h pins the Newey-West lag to the true overlap depth (daily-sampled
    # cross-sections vs an h-session forward window). The ppy//2 default was wrong at
    # BOTH ends: at h=21 it under-corrected the 21-deep overlap, while at h=5/10 it
    # requested lag ~n, where the Bartlett variance degenerates (gamma_0 cancels at
    # L=n-1) and t INFLATES — bigger lag is NOT automatically more conservative.
    # Verdicts stay behind _MIN_DATES=120, clear of both regimes.
    summ = V.ic_summary(np.array(ics), periods_per_year=max(1, 252 // h), hac_lags=h)

    def _f(k):
        v = summ.get(k)
        return round(float(v), 4) if isinstance(v, (int, float)) and np.isfinite(v) else None

    return {"n_dates": len(ics), "mean_ic": _f("mean_ic"), "hac_t": _f("t_hac")}


def _bh_fdr(pvals: dict[str, float], alpha: float) -> dict[str, bool]:
    """Benjamini-Hochberg over the whole primitive x horizon family."""
    items = [(k, v) for k, v in pvals.items() if v is not None and np.isfinite(v)]
    if not items:
        return {}
    items.sort(key=lambda kv: kv[1])
    m = len(items)
    passed, thresh = {k: False for k, _ in items}, 0
    for i, (_k, p) in enumerate(items, start=1):
        if p <= alpha * i / m:
            thresh = i
    for i, (k, _p) in enumerate(items, start=1):
        passed[k] = i <= thresh
    return passed


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    panel = _panel()
    n_dates = panel["date"].nunique() if not panel.empty else 0
    n_names = panel["underlying"].nunique() if not panel.empty else 0
    log.info("dislocation panel: %d dates x %d names (%d rows)", n_dates, n_names, len(panel))

    enough = n_dates >= _MIN_DATES and n_names >= _MIN_NAMES

    results, pvals = {}, {}
    for prim, want_sign in D.PREREG_SIGNS.items():
        col = f"n_{prim}"
        per_h = {}
        for h in _HORIZONS:
            r = _fwd_ic(panel, col, h)
            ic, t = r.get("mean_ic"), r.get("hac_t")
            r["sign_ok"] = bool(ic is not None and np.sign(ic) == want_sign)
            if t is not None and np.isfinite(t):
                # two-sided normal approximation; the HAC t already carries the overlap
                # correction, and BH below carries the multiplicity correction.
                pvals[f"{prim}@{h}"] = float(2.0 * (1.0 - V._norm_cdf(abs(t))))
            per_h[str(h)] = r
        results[prim] = {"prereg_sign": want_sign, "by_horizon": per_h}

    fdr = _bh_fdr(pvals, _FDR_ALPHA)
    for prim in results:
        for h in _HORIZONS:
            results[prim]["by_horizon"][str(h)]["fdr_pass"] = bool(fdr.get(f"{prim}@{h}", False))

    # A primitive is scored only if the panel clears the power floor AND it is sign-correct,
    # HAC-significant, and survives family-wide FDR at some horizon.
    scored_prims = sorted(
        p for p, r in results.items()
        if enough and any(
            v.get("sign_ok") and v.get("hac_t") is not None
            and abs(v["hac_t"]) >= _T_BAR and v.get("fdr_pass")
            and v.get("n_dates", 0) >= _MIN_DATES
            for v in r["by_horizon"].values()))

    scored = bool(scored_prims)
    status = ("ok" if enough else
              f"insufficient_history (have {n_dates}/{_MIN_DATES} dates, "
              f"{n_names}/{_MIN_NAMES} names)")

    gate = {
        "schema": "options_dislocation.gate.v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "scored": scored,
        "scored_primitives": scored_prims,
        "status": status,
        "weight": 1.0 if scored else 0.0,
        "n_dates": int(n_dates), "n_names": int(n_names),
        "min_dates": _MIN_DATES, "min_names": _MIN_NAMES,
        "fdr_alpha": _FDR_ALPHA,
        "neutralised_against": list(D._CONTROLS),
        "results": results,
        "note": (
            "sign-correct, HAC-significant, FDR-surviving primitives -> SCORED"
            if scored else
            "the chain panel is one short regime, far below the power floor -> display-only "
            "context, accruing toward a verdict. Every t-statistic below is computed on "
            "overlapping windows inside that single regime and must not be read as evidence."),
    }
    p = config.data_dir() / "options_dislocation"
    p.mkdir(parents=True, exist_ok=True)
    (p / "validation_gate.json").write_text(json.dumps(gate, indent=2))
    log.info("GATE scored=%s status=%s -> %s", scored, status, p / "validation_gate.json")


if __name__ == "__main__":
    main()
