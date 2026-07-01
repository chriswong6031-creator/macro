"""China base-effect forward projection — the base-effect kernel on levels reconstructed from YoY.

China's CPI / PPI / industrial-production publish YoY only (no cumulative index — the `*_index`
columns in the store just restate YoY), so we rebuild a monthly LEVEL from the YoY series via
base_effect.level_from_yoy before running the SAME base-effect kernel the US uses
(engine/base_effect.compute_from_levels). China's PPI is heavily base-driven — the +0.5% -> +3.9%
swing is largely a base effect — so the forward base-effect read is arguably more informative here
than for the US.

DISPLAY-ONLY, same contract as engine/base_effect.py: zero axis weight, a forward-context leaf on
china latest.json, flagged revised=True (China macro is not point-in-time). See the US v0 for the
methodology (research/HEDGEYE_UPGRADE_MASTER_PLAN.md §A.1).
"""
from __future__ import annotations

from engine import base_effect as be
from lib import store

# china_macro store key -> YoY column. Inflation = CPI + core-ish PPI; growth = industrial prod.
_INFLATION = {"cpi": "cpi_yoy", "ppi": "ppi_yoy"}
_GROWTH = {"indpro": "indpro_yoy"}


def _level(key: str, col: str):
    df = store.read("china_macro", key)
    if df is None or getattr(df, "empty", True) or col not in df.columns:
        return None, True
    lvl = be.level_from_yoy(df[col])
    return (lvl if not lvl.empty else None), True   # revised=True — China macro is not PIT


def _actual_yoy(series_map: dict) -> tuple[float | None, dict]:
    """The ACTUAL latest YoY per series + the axis mean — to anchor the (smoothed, lagging)
    reconstructed path to reality without changing the base-effect deltas."""
    per, vals = {}, []
    for key, col in series_map.items():
        df = store.read("china_macro", key)
        if df is not None and col in df.columns and not df[col].dropna().empty:
            v = round(float(df[col].dropna().iloc[-1]), 3)
            per[key] = v
            vals.append(v)
    return (round(sum(vals) / len(vals), 3) if vals else None), per


def _anchor(axis: dict | None, actual: float | None, per: dict) -> None:
    """Shift the reconstructed YoY path so path[0] == the actual latest YoY. The smooth
    reconstruction (base_effect.level_from_yoy) tracks the trailing-12m average, so it lags; the
    base-effect SHAPE (the per-quarter accel/decel deltas) is what we keep, the anchor is reality."""
    if axis is None or actual is None or not axis.get("yoy_path") or axis["yoy_path"][0] is None:
        return
    shift = actual - axis["yoy_path"][0]
    axis["yoy_path"] = [round(v + shift, 3) if v is not None else None for v in axis["yoy_path"]]
    axis["current_yoy"] = actual
    end = axis["yoy_path"][-1]
    if end is not None:
        axis["forcing_intensity"] = round(abs(end - actual), 3)
    for k, v in per.items():
        if k in axis.get("series", {}):
            axis["series"][k]["current_yoy"] = v


def compute() -> dict | None:
    """China base-effect block for china latest.json (display-only), anchored to actual YoY."""
    growth_levels = {k: _level(k, c) for k, c in _GROWTH.items()}
    inflation_levels = {k: _level(k, c) for k, c in _INFLATION.items()}
    out = be.compute_from_levels(growth_levels, inflation_levels, as_of_str=None)
    if out is None:
        return None
    g_act, g_per = _actual_yoy(_GROWTH)
    i_act, i_per = _actual_yoy(_INFLATION)
    _anchor(out.get("growth"), g_act, g_per)
    _anchor(out.get("inflation"), i_act, i_per)
    if out.get("growth"):
        out["growth_note"] = be._note("growth", out["growth"])
    if out.get("inflation"):
        out["inflation_note"] = be._note("inflation", out["inflation"])
    return out


def main() -> int:  # pragma: no cover - manual inspection
    import json
    print(json.dumps(compute(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
