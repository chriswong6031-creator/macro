"""Blast radius of the pick-lab session-anchor re-bucket (era pl-abs-session-2026-08-06).

Measures, per region (US / CN / HK), how many names' d2_* scalars change when the d2
grid moves from the loader-phased ``resample("2B")`` bins to the absolute session
anchor (``session_anchor.session_positions // 2``) — plus the HK 3-session site
(``d3_macd_xup_bars``, a LIVE gate input: hklab_1d_blastoff requires it null) — and
re-verifies start-invariance under the NEW anchor (leading-drop flips must be zero).

One-time diagnostic, run at ship time and committed to
``reports/pick_lab_anchor_blast_radius.{md,json}`` (the R-SQ4 pattern: the marker
stream re-draws ONCE, disclosed, era-stamped). Panels measured are the committed
stores each nightly producer reads — for HK the deep search panel, which is exactly
the production cache-miss path (`hk closes: breadth cache missing → deep panel only`).

Usage:  python3 scripts/measure_pick_lab_anchor_blast_radius.py
"""
from __future__ import annotations

import glob
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pick_lab.signals_1d import (   # noqa: E402
    ANCHOR_ERA, XBAR_WIN, _grid_scalars, _rsi_macd, _since, _xup, session_bucket_last,
)

REPO = Path(__file__).resolve().parents[1]
OUT_MD = REPO / "reports" / "pick_lab_anchor_blast_radius.md"
OUT_JSON = REPO / "reports" / "pick_lab_anchor_blast_radius.json"

_FLOAT_FIELDS = ("macd", "sig", "k", "d")
_EXACT_FIELDS = ("macd_xup_bars", "kd_xup_bars", "from_os", "ob")
#: Float moves below EWM-memory scale are not flips (the invariance battery's line).
_REL, _ABS = 1e-6, 1e-8


def _null(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v))


def _field_flip(a, b, field: str) -> bool:
    if _null(a) and _null(b):
        return False
    if _null(a) != _null(b):
        return True
    if field in _EXACT_FIELDS:
        return a != b
    return abs(a - b) > max(_ABS, _REL * abs(b))


def _panel_us() -> pd.DataFrame:
    cols = {}
    for f in sorted(glob.glob(str(REPO / "data" / "stocks" / "*.parquet"))):
        t = Path(f).stem
        try:
            cols[t] = pd.read_parquet(f, columns=["close"])["close"]
        except Exception:
            continue
    return pd.DataFrame(cols)


def _panel_cn() -> pd.DataFrame:
    return pd.read_parquet(REPO / "data" / "china_search" / "closes.parquet")


def _panel_hk() -> pd.DataFrame:
    return pd.read_parquet(REPO / "data" / "hk_search" / "closes_deep.parquet")


def _d2_scalars(panel: pd.DataFrame, *, anchored: bool, market: str,
                drop_leading: int = 0) -> dict[str, dict]:
    p = panel.sort_index()
    if drop_leading:
        p = p.iloc[drop_leading:]
    grid = (session_bucket_last(p, 2, market=market) if anchored
            else p.resample("2B").last())
    return {t: _grid_scalars(grid[t]) for t in p.columns}


def _d3_xup(panel: pd.DataFrame, *, anchored: bool, market: str,
            drop_leading: int = 0) -> dict[str, float | None]:
    """The build_hk_library d3 site's exact construction, both geometries."""
    p = panel.sort_index()
    if drop_leading:
        p = p.iloc[drop_leading:]
    grid = (session_bucket_last(p, 3, market=market) if anchored
            else p.resample("3B").last())
    out: dict[str, float | None] = {}
    for t in p.columns:
        c3 = grid[t].dropna()
        if len(c3) < 90:
            out[t] = None
            continue
        m3, s3 = _rsi_macd(c3)
        x3 = _since(_xup(m3, s3))
        v3 = float(x3.iloc[-1]) if pd.notna(x3.iloc[-1]) else None
        out[t] = v3 if (v3 is None or v3 <= XBAR_WIN) else None
    return out


def _diff_d2(old: dict[str, dict], new: dict[str, dict]) -> dict:
    per_field = {f: 0 for f in _FLOAT_FIELDS + _EXACT_FIELDS}
    flipped = []
    for t, o in old.items():
        n = new.get(t, {})
        hit = False
        for f in per_field:
            if _field_flip(o.get(f), n.get(f), f):
                per_field[f] += 1
                hit = True
        if hit:
            flipped.append(t)
    return {"names": len(old), "any_flip": len(flipped),
            "per_field": per_field, "flipped_sample": sorted(flipped)[:12]}


def _region(name: str, panel: pd.DataFrame, market: str) -> dict:
    old = _d2_scalars(panel, anchored=False, market=market)
    new = _d2_scalars(panel, anchored=True, market=market)
    d2 = _diff_d2(old, new)

    # Defect reproduction on the OLD geometry: a leading drop re-phases the bins.
    # Measured at k=1 AND k=2 — a panel whose first row happens to close a complete
    # 2B bin shows 0 at one parity while the other parity exposes the re-phase (the
    # mod-2 fingerprint), so a single-k zero must never read as "no defect".
    d2["old_geometry_leading_drop_flips"] = {
        f"k={k}": _diff_d2(old, _d2_scalars(panel, anchored=False, market=market,
                                            drop_leading=k))["any_flip"]
        for k in (1, 2)
    }

    # Invariance under the NEW geometry: leading drops must move nothing.
    inv = {}
    for k in (1, 2, 3):
        new_k = _d2_scalars(panel, anchored=True, market=market, drop_leading=k)
        inv[f"k={k}"] = _diff_d2(new, new_k)["any_flip"]
    d2["new_geometry_leading_drop_flips"] = inv
    return {"region": name, "market": market, "asof": str(panel.index.max().date()),
            "d2": d2}


def main() -> None:
    results = {
        "era": ANCHOR_ERA,
        "boundary_date": "2026-08-06",
        "measured_on": str(date.today()),
        "regions": [],
    }

    for name, loader, market in (("US", _panel_us, "US"),
                                 ("CN", _panel_cn, "CN"),
                                 ("HK", _panel_hk, "HK")):
        panel = loader()
        results["regions"].append(_region(name, panel, market))

    # HK d3 site (live gate input for hklab_1d_blastoff: eligibility reads .isna()).
    hk = _panel_hk()
    d3_old = _d3_xup(hk, anchored=False, market="HK")
    d3_new = _d3_xup(hk, anchored=True, market="HK")
    d3_flips = [t for t in d3_old
                if not (_null(d3_old[t]) and _null(d3_new[t])) and d3_old[t] != d3_new[t]]
    null_transitions = [t for t in d3_old if _null(d3_old[t]) != _null(d3_new[t])]
    d3_k1 = _d3_xup(hk, anchored=True, market="HK", drop_leading=1)
    d3_inv = {"k=1": sum(
        1 for t in d3_new
        if not (_null(d3_new[t]) and _null(d3_k1[t])) and d3_new[t] != d3_k1[t])}
    # (single-k re-run kept cheap: the n=3 invariance battery already pins k=1..6 on fixtures)
    results["hk_d3"] = {
        "names": len(d3_old),
        "value_flips": len(d3_flips),
        "null_transitions": len(null_transitions),
        "null_transition_names": sorted(null_transitions),
        "new_geometry_leading_drop_flips": d3_inv,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2) + "\n")

    lines = [
        "# Pick-lab session-anchor blast radius",
        "",
        f"**Era:** `{results['era']}` · **boundary date:** {results['boundary_date']} · "
        f"measured {results['measured_on']} on the committed nightly panels "
        "(HK = deep search panel, the production cache-miss path).",
        "",
        "The d2 grid (all regions) and the HK 3-session `d3_macd_xup_bars` site moved from",
        "loader-phased `resample(\"nB\")` bins to `session_anchor.session_positions // n`.",
        "Old→new flip = any d2 scalar changed beyond EWM-memory scale (rel 1e-6).",
        "Snapshot rows are keep-first and never retro-edited: pre-era rows keep a null",
        "`pl_anchor_era`; the column fences the cohorts (R-SQ8 family).",
        "",
        "| region | names | d2 any-flip | old k=1/k=2 flips (defect) | new k=1/2/3 flips |",
        "|---|---:|---:|---:|---|",
    ]
    for r in results["regions"]:
        d2 = r["d2"]
        inv = d2["new_geometry_leading_drop_flips"]
        oldk = d2["old_geometry_leading_drop_flips"]
        lines.append(
            f"| {r['region']} (asof {r['asof']}) | {d2['names']} | {d2['any_flip']} "
            f"({100*d2['any_flip']/max(1,d2['names']):.0f}%) | "
            f"{oldk['k=1']} / {oldk['k=2']} | "
            f"{inv['k=1']} / {inv['k=2']} / {inv['k=3']} |")
    hk3 = results["hk_d3"]
    lines += [
        "",
        "**Per-field d2 flip counts:** " + " · ".join(
            f"{r['region']}: " + ", ".join(f"{f}={r['d2']['per_field'][f]}"
                                           for f in ("macd", "macd_xup_bars", "kd_xup_bars",
                                                     "from_os", "ob"))
            for r in results["regions"]),
        "",
        f"**HK d3 site (live gate input — hklab_1d_blastoff reads `.isna()`):** "
        f"{hk3['value_flips']}/{hk3['names']} values move, "
        f"{hk3['null_transitions']} cross null↔non-null "
        f"({', '.join(hk3['null_transition_names']) or 'none'}); "
        f"new-geometry k=1 leading-drop flips: {hk3['new_geometry_leading_drop_flips']['k=1']}.",
        "",
        "A 0 in one old-k column beside a full-panel re-draw is the parity artifact "
        "(the panel's first row closed a complete bin at that k), not absence of the "
        "defect — the production HK panel is the rolling breadth cache, whose start "
        "creeps forward every refresh, re-phasing the old bins build-to-build.",
        "",
        "The one-time re-draw is the cost of removing the loader-phase dependence "
        "(R-SQ4 pattern). No registered candidate book gates on d2_* "
        "(candidates.py reads d1_*; registry.py's only d2 knob is None) — repaired "
        "BEFORE any d2-gated book registers. The HK d3 change is disclosed above; "
        "`sessions_since_23d_cross` / `ret_since_23d_cross` derive from the repaired "
        "fields and inherit the fix.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines))
    print(f"wrote {OUT_MD.relative_to(REPO)} and {OUT_JSON.relative_to(REPO)}")
    print(json.dumps(results, indent=2)[:1200])


if __name__ == "__main__":
    main()
