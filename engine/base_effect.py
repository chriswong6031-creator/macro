"""Comparative base-effect forward projection — the Hedgeye kernel, built honestly.

A year-over-year rate has a denominator (the "base") that is known exactly 12 months in
advance. Holding sequential momentum at a normal rate, the forward path of the YoY rate is
bent *deterministically* by that known base: tough comps a year ago force deceleration, easy
comps force acceleration. This is the piece the current regime engine lacks — it reads the
sign of a 20-day price slope (a coincident, first-derivative, market-proxy read), never the
forward second-derivative of the economic rate that Hedgeye's Quad is actually built on.

This module projects the forward YoY path for GROWTH (INDPRO, PAYEMS) and INFLATION (core
CPI `CPILFESL`, core PCE `PCEPILFE` — the Fed's target) under a flat/normal momentum
assumption, and emits the sign of the forward second derivative (accel/decel) for each of
the next three quarters, plus a momentum fan for display.

Point-in-time honesty: when `as_of` + a loaded ALFRED vintage frame are supplied and the
series has vintage coverage, levels are read as they were *known then* via
`collectors.fred.as_of_series`. Otherwise it falls back to the latest-revision level from the
local store, flagged `revised=True` — defensible for a deterministic base signal because the
base period is a settled historical print (see research/HEDGEYE_UPGRADE_MASTER_PLAN.md §2 S3;
per scripts/audit_alfred_depth.py, INDPRO/PAYEMS have vintages back to 1997 but core CPI/PCE
are not yet in the store).

DISPLAY-ONLY in v0: this carries ZERO axis weight in engine/axes.py. It is emitted as forward
context and appended to a forward-grading log; it becomes eligible for scored weight only
after scripts/validate_regime_fwd.py shows it reproduces the disclosed inversion statistic on
our own point-in-time data (calendar-gated — months of accrual, not a build cycle).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lib import store

# axis -> the level series it is built from
GROWTH_SIDS = ["INDPRO", "PAYEMS"]
INFLATION_SIDS = ["CPILFESL", "PCEPILFE"]   # core CPI, core PCE (the Fed's target)
_HUMAN = {"INDPRO": "industrial production", "PAYEMS": "payrolls",
          "CPILFESL": "core CPI", "PCEPILFE": "core PCE"}

HORIZON_M = 9        # project three quarters out
MOM_WIN = 6          # trailing months for the "normal momentum" estimate
_MIN_OBS = 30        # need enough monthly history to form YoY + momentum


def _level(sid: str, as_of=None, vintages=None) -> tuple[pd.Series | None, bool]:
    """Monthly SA level series and whether it is revised (not point-in-time). PIT via ALFRED
    vintage when `as_of` + `vintages` are supplied and the series has coverage; else the
    latest-revision level from the local FRED store (revised=True)."""
    if as_of is not None and vintages is not None:
        try:
            from collectors.fred import as_of_series
            v = as_of_series(sid, as_of, vintages)
            if v is not None:
                v = pd.Series(v).dropna()
                if len(v) > 24:
                    v.index = pd.to_datetime(v.index)
                    return v.sort_index(), False
        except Exception:  # noqa: BLE001 — PIT is best-effort; fall back to revised
            pass
    df = store.read("fred", sid)
    if df is None or getattr(df, "empty", True):
        return None, True
    s = df.iloc[:, 0].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index(), True


def _project(level: pd.Series, mom_shift: float = 0.0) -> dict | None:
    """Project the forward YoY path under a MoM log-momentum scenario and return the path
    (h=0..HORIZON_M) plus the ACCELERATION sign per month. "Acceleration" is the Hedgeye Quad
    axis: is the YoY *rate* rising (accelerating, +1) or falling (decelerating, -1)? That is the
    first difference of the YoY path, Δ(YoY) = g_t - g_{t-1} — which IS the second derivative of
    the *level* (g is itself the level's ~first derivative). NB: the second *difference* of the
    YoY path is one derivative too far and is coin-flip noisy near zero (plan critique §2.1), so
    we deliberately take the first difference. The base denominator L_{t-12+h} is known history
    for every h in [0, HORIZON_M] (base month <= anchor), so the sign is base-forced."""
    level = level.dropna()
    if len(level) < _MIN_OBS:
        return None
    logl = np.log(level.astype(float))
    mom = logl.diff().dropna()
    if len(mom) < MOM_WIN:
        return None
    m_hat = float(mom.iloc[-MOM_WIN:].mean()) + mom_shift   # normal momentum (+ scenario shift)
    anchor = level.index[-1]
    last_log = float(logl.iloc[-1])

    def base_log(h: int) -> float:
        bm = anchor + pd.DateOffset(months=h - 12)
        bm = pd.Timestamp(year=bm.year, month=bm.month, day=1)
        idx = logl.index[logl.index <= bm]
        return float(logl.loc[idx[-1]]) if len(idx) else float("nan")

    yoy: dict[int, float] = {}
    for h in range(0, HORIZON_M + 2):
        bl = base_log(h)
        yoy[h] = float("nan") if np.isnan(bl) else float(np.exp(last_log + h * m_hat - bl) - 1.0)

    accel: dict[int, int] = {}
    for h in range(1, HORIZON_M + 1):
        a, b = yoy.get(h - 1), yoy.get(h)
        if any(x is None or np.isnan(x) for x in (a, b)):
            accel[h] = 0
        else:
            accel[h] = int(np.sign(round(b - a, 8)))
    return {"m_hat": m_hat, "yoy": yoy, "accel": accel}


def _quarter_signs(accel: dict[int, int]) -> dict[str, int]:
    """Modal acceleration sign (+1 accel / -1 decel of the YoY rate) for each of the next three
    quarters (ties -> 0) — the base-forced Hedgeye Quad axis, one value per quarter."""
    out = {}
    for qi, months in enumerate([(1, 2, 3), (4, 5, 6), (7, 8, 9)], start=1):
        s = [accel.get(h, 0) for h in months]
        p, n = s.count(1), s.count(-1)
        out[f"q{qi}"] = 1 if p > n else (-1 if n > p else 0)
    return out


def _axis(levels: dict[str, tuple[pd.Series | None, bool]]) -> dict | None:
    """Aggregate the base-effect forward signal across the level series that define one axis.
    `levels` maps a series name to (monthly SA level series or None, revised flag). The US path
    builds these from FRED; other markets (China) reconstruct levels from YoY (level_from_yoy)."""
    per, any_revised, missing = [], False, []
    for name, (lvl, rev) in levels.items():
        if lvl is None:
            missing.append(name)
            continue
        flat = _project(lvl, 0.0)
        if flat is None:
            missing.append(name)
            continue
        mom = np.log(lvl.astype(float)).diff().dropna()
        sd = float(mom.iloc[-MOM_WIN:].std()) if len(mom) >= MOM_WIN else 0.0
        per.append({"sid": name, "revised": rev, "flat": flat,
                    "up": _project(lvl, +0.5 * sd), "dn": _project(lvl, -0.5 * sd),
                    "qsigns": _quarter_signs(flat["accel"])})
        any_revised = any_revised or rev
    if not per:
        return None

    # axis YoY path = mean projected YoY across the series, months 0..HORIZON_M, in percent
    path: list[float | None] = []
    for h in range(0, HORIZON_M + 1):
        vals = [x["flat"]["yoy"].get(h) for x in per]
        vals = [v for v in vals if v is not None and not np.isnan(v)]
        path.append(round(100.0 * float(np.mean(vals)), 3) if vals else None)

    # axis acceleration = sign of the first difference of the AVERAGED path (accel of the mean
    # rate), aggregated to modal sign per quarter — avoids the within-axis cancellation you get
    # from voting on per-series signs when INDPRO/PAYEMS (or CPI/PCE) disagree at the front.
    accel = {}
    for h in range(1, HORIZON_M + 1):
        a, b = path[h - 1], path[h]
        accel[h] = 0 if (a is None or b is None) else int(np.sign(round(b - a, 6)))
    qs = _quarter_signs(accel)

    cur, end = path[0], path[HORIZON_M]
    intensity = round(abs(end - cur), 3) if (cur is not None and end is not None) else None
    return {
        "q1": qs["q1"], "q2": qs["q2"], "q3": qs["q3"],
        "yoy_path": path, "current_yoy": cur, "forcing_intensity": intensity,
        "revised": any_revised, "missing": missing,
        "series": {x["sid"]: {"revised": x["revised"], **x["qsigns"],
                              "current_yoy": round(100.0 * x["flat"]["yoy"][0], 3)} for x in per},
    }


def _note(axis: str, a: dict) -> str:
    q1 = a["q1"]
    verb = {1: "acceleration", -1: "deceleration", 0: "a flat rate"}[q1]
    comp = {1: "easy comps", -1: "tough comps", 0: "neutral comps"}[q1]
    cur = a.get("current_yoy")
    path = a.get("yoy_path") or []
    end = path[-1] if path else None
    traj = f"; YoY {cur:.1f}%->{end:.1f}% over 3q" if (cur is not None and end is not None) else ""
    return f"{comp} a year ago -> base-forced {verb} in {axis} into Q1{traj}"


def level_from_yoy(yoy_pct: pd.Series, seed: float = 100.0) -> pd.Series:
    """Reconstruct a smooth monthly LEVEL index from a YoY-percent series — for markets that
    publish YoY only, no cumulative index (China CPI/PPI/IndPro). Spreads each year's YoY evenly
    across 12 months in log space: log L_t = log L_{t-1} + log(1+yoy_t/100)/12, so the level's
    trailing-12-month YoY tracks the input while the *monthly* path stays smooth. The naive exact
    chain (L_t = L_{t-12}*(1+yoy_t)) reproduces YoY exactly but its fabricated within-year path is
    jumpy — for a volatile series (China industrial production) that noise poisons the base-effect
    projection (a spurious ±20pp swing). Base-effect only needs the shape of the base path, so a
    smooth reconstruction is the right trade."""
    y = pd.Series(yoy_pct).dropna().astype(float).sort_index() / 100.0
    y.index = pd.to_datetime(y.index)
    y = y.resample("MS").last().ffill().dropna()   # contiguous monthly grid, bridge rare gaps
    if len(y) < 24:
        return pd.Series(dtype=float)
    logl = (np.log1p(y) / 12.0).cumsum() + np.log(seed)
    return np.exp(logl)


def compute_from_levels(growth_levels: dict | None, inflation_levels: dict | None,
                        as_of_str: str | None = None) -> dict | None:
    """Generic base-effect block from pre-built level dicts (name -> (level_series, revised)).
    The US `compute` reads FRED; China reconstructs levels from YoY and calls this directly."""
    growth = _axis(growth_levels) if growth_levels else None
    infl = _axis(inflation_levels) if inflation_levels else None
    if growth is None and infl is None:
        return None
    out: dict = {"horizon_m": HORIZON_M, "as_of": as_of_str}
    if growth is not None:
        out["growth"] = growth
        out["growth_note"] = _note("growth", growth)
    if infl is not None:
        out["inflation"] = infl
        out["inflation_note"] = _note("inflation", infl)
    out["revised"] = bool((growth or {}).get("revised", True) or (infl or {}).get("revised", True))
    return out


def compute(as_of=None, vintages=None) -> dict | None:
    """The full base-effect block for the US regime (display-only). Reads FRED levels; `as_of` +
    `vintages` enable point-in-time reads, omit them for latest-revision (flagged revised=True)."""
    growth_levels = {sid: _level(sid, as_of, vintages) for sid in GROWTH_SIDS}
    inflation_levels = {sid: _level(sid, as_of, vintages) for sid in INFLATION_SIDS}
    return compute_from_levels(growth_levels, inflation_levels,
                               str(as_of) if as_of is not None else None)


def grading_row(result: dict, asof: str) -> dict:
    """A row for the forward-grading log data/regime/base_effect_fwd.jsonl. The realized_*
    fields stay null until +63/+126d, when scripts/validate_regime_fwd.py fills them to test
    the disclosed inversion statistic on our own data."""
    g = (result or {}).get("growth") or {}
    i = (result or {}).get("inflation") or {}
    return {"asof": asof,
            "be_growth_2d_q1": g.get("q1"), "be_infl_2d_q1": i.get("q1"),
            "be_growth_intensity": g.get("forcing_intensity"),
            "be_infl_intensity": i.get("forcing_intensity"),
            "revised": (result or {}).get("revised", True),
            "realized_growth_2d_at_63d": None, "realized_infl_2d_at_63d": None}


def main() -> int:  # pragma: no cover - manual inspection
    import json
    r = compute()
    print(json.dumps(r, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
