"""Subsector rotation & velocity — pure compute layer.

Turns Finviz's broad-universe **theme → subsector** performance snapshot
(``data/themes_heatmap/perf_snapshot.json``, 268 subsectors across 40 themes,
eight horizons) into a rotation read: which subsectors lead, which are turning,
and — the point — which are *accelerating* (an emerging-theme early-entry
signal). It is a separate lens from the 34 hand-curated thematic baskets: those
are our own equal-weight indices; this rides Finviz's own broad numbers (which
include names we hold no prices for), so it stays a display/context layer.

Design
------
* **Pure.** Takes the already-loaded snapshot dicts and returns a JSON-ready
  payload. All disk/network I/O lives in ``scripts/build_subsector_rotation.py``.
* **Relative-strength, cross-sectional.** Every metric is computed *across*
  subsectors at each horizon (the benchmark is the median subsector), so a
  reading says "leading/lagging vs the rest of the market," not vs an index we
  may not have.
* **RRG-style quadrants.** ``rs_ratio`` (leadership level) × ``rs_mom`` (is that
  leadership improving) → Leading / Weakening / Lagging / Improving. The
  *Improving* quadrant (laggards turning up) plus positive ``accel`` is the
  early-rotation watchlist.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np


def _load_names_zh() -> dict:
    """Chinese translations for theme / subsector display names (i18n). Optional —
    a missing file just leaves names in English (degrade-never-raise)."""
    try:
        p = Path(__file__).resolve().parent.parent / "data" / "themes_heatmap" / "names_zh.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        return {"themes": d.get("themes") or {}, "subsectors": d.get("subsectors") or {}}
    except Exception:  # noqa: BLE001
        return {"themes": {}, "subsectors": {}}


_NAMES_ZH = _load_names_zh()

# Finviz snapshot horizons (calendar MTD/YTD kept for display; the rolling ones
# drive momentum). Approx weeks per window normalise returns to a weekly pace.
HORIZONS = ["1D", "1W", "1M", "MTD", "3M", "6M", "1Y", "YTD"]
MOM_HORIZONS = ["1W", "1M", "3M", "6M", "1Y"]
WEEKS = {"1W": 1.0, "1M": 4.345, "3M": 13.04, "6M": 26.07, "1Y": 52.14}


def _zscore(values: dict[str, float]) -> dict[str, float]:
    """Cross-sectional z-score of a {key: value} map (robust to tiny n / 0 std)."""
    keys = [k for k, v in values.items() if v is not None and np.isfinite(v)]
    if len(keys) < 2:
        return {k: 0.0 for k in values}
    arr = np.array([values[k] for k in keys], dtype=float)
    mu, sd = float(arr.mean()), float(arr.std())
    if sd <= 1e-9:
        return {k: 0.0 for k in values}
    return {k: ((values[k] - mu) / sd if (values[k] is not None and np.isfinite(values[k])) else 0.0)
            for k in values}


def _nanmean(*xs: float | None) -> float | None:
    vals = [x for x in xs if x is not None and np.isfinite(x)]
    return float(np.mean(vals)) if vals else None


def _quadrant(rs_ratio: float, rs_mom: float) -> str:
    if rs_ratio >= 0:
        return "leading" if rs_mom >= 0 else "weakening"
    return "improving" if rs_mom >= 0 else "lagging"


def _rotation_metrics(perf_by_key: Mapping[str, Mapping[str, float]]) -> dict[str, dict]:
    """Core pipeline over {key: {horizon: pct}} → per-key rotation metrics.

    Reused for both subsectors and theme rollups.
    """
    keys = list(perf_by_key)
    # market = median subsector at each horizon → relative strength.
    median = {}
    for h in HORIZONS:
        col = [perf_by_key[k].get(h) for k in keys]
        col = [v for v in col if v is not None and np.isfinite(v)]
        median[h] = float(np.median(col)) if col else None

    rs = {k: {h: ((perf_by_key[k].get(h) - median[h])
                  if (perf_by_key[k].get(h) is not None and median.get(h) is not None) else None)
              for h in HORIZONS} for k in keys}
    # z-score each horizon's RS across keys (the RRG axes live in z-space).
    zrs = {h: _zscore({k: rs[k][h] for k in keys}) for h in HORIZONS}

    # weekly pace per horizon → acceleration (recent pace vs the 3-month pace).
    rate = {k: {h: (perf_by_key[k].get(h) / WEEKS[h]
                    if (h in WEEKS and perf_by_key[k].get(h) is not None) else None)
                for h in MOM_HORIZONS} for k in keys}
    accel_raw = {k: ((rate[k]["1W"] - rate[k]["3M"]) if (rate[k]["1W"] is not None and rate[k]["3M"] is not None)
                     else (rate[k]["1W"] - rate[k]["1M"]) if (rate[k]["1W"] is not None and rate[k]["1M"] is not None)
                     else None) for k in keys}
    z_accel = _zscore(accel_raw)

    out: dict[str, dict] = {}
    for k in keys:
        rs_ratio = _nanmean(zrs["1M"].get(k), zrs["3M"].get(k)) or 0.0
        rs_mom = (_nanmean(zrs["1W"].get(k), zrs["1M"].get(k)) or 0.0) \
            - (_nanmean(zrs["3M"].get(k), zrs["6M"].get(k)) or 0.0)
        # emerging = accelerating + relative strength improving + recent strength.
        emerging = 0.5 * z_accel.get(k, 0.0) + 0.8 * rs_mom + 0.3 * (zrs["1W"].get(k) or 0.0)
        out[k] = {
            "perf": {h: (round(perf_by_key[k].get(h), 2) if perf_by_key[k].get(h) is not None else None)
                     for h in HORIZONS},
            "rs": {h: (round(rs[k][h], 2) if rs[k][h] is not None else None) for h in MOM_HORIZONS},
            "rs_ratio": round(rs_ratio, 3),
            "rs_mom": round(rs_mom, 3),
            "accel": round(accel_raw[k], 3) if accel_raw[k] is not None else None,
            "z_accel": round(z_accel.get(k, 0.0), 3),
            "quadrant": _quadrant(rs_ratio, rs_mom),
            "emerging_score": round(emerging, 3),
        }
    return out


def compute_rotation(
    tree: Sequence[Mapping],
    subsector_perf: Mapping[str, Mapping[str, float]],
    member_perf: Mapping[str, Mapping[str, float]] | None = None,
    *,
    generated_utc: str | None = None,
    asof: str | None = None,
    top_members: int = 8,
) -> dict:
    """Assemble the subsector-rotation payload.

    Parameters
    ----------
    tree           : ``[{theme, subsectors:[{key,name,members:[...]}]}]`` — the
                     committed Finviz structure.
    subsector_perf : ``{subsector_key: {horizon: pct}}``.
    member_perf    : ``{ticker: {horizon: pct}}`` (optional, for member chips).
    """
    member_perf = member_perf or {}
    # flatten subsectors, attach theme; keep only those with a perf row.
    meta: dict[str, dict] = {}
    for th in tree:
        theme = str(th.get("theme") or th.get("key") or "").strip()
        for sub in th.get("subsectors", []):
            key = str(sub.get("key") or "").strip()
            if not key or key not in subsector_perf:
                continue
            members = [str(m).strip().upper() for m in (sub.get("members") or []) if str(m).strip()]
            meta[key] = {"name": str(sub.get("name") or key), "theme": theme, "members": members}

    sub_metrics = _rotation_metrics({k: subsector_perf[k] for k in meta})

    subsectors = []
    for key, m in meta.items():
        met = sub_metrics[key]
        # member chips: best/worst movers (1M) we have a quote for.
        mem_rows = []
        for t in m["members"]:
            mp = member_perf.get(t)
            if mp:
                mem_rows.append({"t": t, "1W": mp.get("1W"), "1M": mp.get("1M")})
        mem_rows.sort(key=lambda r: (r["1M"] if r["1M"] is not None else -1e9), reverse=True)
        subsectors.append({
            "key": key, "name": m["name"], "theme": m["theme"],
            "name_zh": _NAMES_ZH["subsectors"].get(m["name"], m["name"]),
            "theme_zh": _NAMES_ZH["themes"].get(m["theme"], m["theme"]),
            "n_members": len(m["members"]),
            "members": mem_rows[:top_members],
            **met,
        })
    subsectors.sort(key=lambda s: s["emerging_score"], reverse=True)
    for i, s in enumerate(subsectors):
        s["rank"] = i + 1

    # theme rollup: each theme = mean of its subsectors' perf per horizon.
    theme_keys = {}
    theme_perf: dict[str, dict[str, float]] = {}
    for th in tree:
        theme = str(th.get("theme") or "").strip()
        subs = [s["key"] for s in subsectors if s["theme"] == theme]
        if not subs:
            continue
        theme_keys[theme] = subs
        agg = {}
        for h in HORIZONS:
            vals = [subsector_perf[k].get(h) for k in subs
                    if subsector_perf[k].get(h) is not None and np.isfinite(subsector_perf[k].get(h))]
            agg[h] = float(np.mean(vals)) if vals else None
        theme_perf[theme] = agg
    theme_metrics = _rotation_metrics(theme_perf)
    themes = []
    sub_by_theme = {t: [s for s in subsectors if s["theme"] == t] for t in theme_keys}
    for theme, subs in theme_keys.items():
        met = theme_metrics[theme]
        ranked = sorted(sub_by_theme[theme], key=lambda s: s["emerging_score"], reverse=True)
        themes.append({
            "theme": theme, "theme_zh": _NAMES_ZH["themes"].get(theme, theme),
            "n_subs": len(subs),
            "top_sub": ranked[0]["name"] if ranked else None,
            "top_sub_zh": _NAMES_ZH["subsectors"].get(ranked[0]["name"], ranked[0]["name"]) if ranked else None,
            **met,
        })
    themes.sort(key=lambda t: t["emerging_score"], reverse=True)

    # highlights — only sensible candidates per bucket. A breadth floor keeps the
    # actionable emerging/fading calls off 1-2-member "subsectors" (those are a
    # stock or two, not a rotation) — signal hygiene, not a fitted parameter.
    MIN_BREADTH = 3
    emerging = [s["key"] for s in subsectors
                if s["n_members"] >= MIN_BREADTH and s["rs_mom"] > 0
                and (s["accel"] is None or s["accel"] >= 0)][:12]
    fading = [s["key"] for s in sorted(subsectors, key=lambda s: s["rs_mom"])
              if s["n_members"] >= MIN_BREADTH and s["rs_ratio"] > 0 and s["rs_mom"] < 0][:12]
    leaders = [s["key"] for s in sorted(subsectors, key=lambda s: s["rs_ratio"], reverse=True)][:12]
    laggards = [s["key"] for s in sorted(subsectors, key=lambda s: s["rs_ratio"])][:12]

    return {
        "asof": asof or "",
        "generated_utc": generated_utc or "",
        "source": "finviz-themes",
        "timeframes": HORIZONS,
        "mom_horizons": MOM_HORIZONS,
        "subsectors": subsectors,
        "themes": themes,
        "highlights": {"emerging": emerging, "fading": fading, "leaders": leaders, "laggards": laggards},
        "n_subsectors": len(subsectors),
        "n_themes": len(themes),
    }
