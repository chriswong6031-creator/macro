"""China Subsector Rotation — the A-share twin of engine/subsector_rotation.py.

Feeds the SAME rotation machinery (``_rotation_metrics`` — cross-sectional RS vs the
median, RRG quadrants, velocity/acceleration) with two China basket sets so the desk
mirrors the US Subsectors ⇄ Themes toggle:

  • **Subsectors** = the 同花顺 (Tonghuashun / THS) concept boards, filtered to the
    ``n_members >= 6`` **reliable** set (~233) — the same broad-universe read
    subsectors_china.html shows, but read for rotation.
  • **Themes** = our curated A-share thematic baskets (baskets_china.html).

Both already carry a multi-horizon ``perf`` snapshot (1d/5d/20d/60d/mtd/ytd) plus a
normalized chart level series; we map those to the engine's horizon grid and derive
6M/1Y from the level series. Offline-safe — the committed basket JSONs are the source.
"""
from __future__ import annotations

from engine.subsector_rotation import MOM_HORIZONS, _rotation_metrics

# CN perf horizon (in the basket JSON) → the rotation engine's horizon grid.
_MAP = {"1D": "1d", "1W": "5d", "1M": "20d", "3M": "60d", "MTD": "mtd", "YTD": "ytd"}
_MIN_BREADTH = 6  # "reliable" THS concept: >= 6 priced members (drops the thin tail)


def _lookback_ret(series, n_days: int):
    """~n-trading-day return from a normalized level series (skips leading nulls)."""
    if not series:
        return None
    vals = [(i, v) for i, v in enumerate(series) if v is not None]
    if len(vals) < 2:
        return None
    last_i, last_v = vals[-1]
    target = last_i - n_days
    prior = None
    for i, v in vals:
        if i <= target:
            prior = v
        else:
            break
    if prior is None or prior == 0:
        return None
    return round((last_v / prior - 1.0) * 100.0, 2)


def _perf_map(basket: dict, series) -> dict:
    """Map a basket's perf (fractions) → the engine's %-scale horizon grid."""
    p = basket.get("perf") or {}

    def r(h):
        v = (p.get(h) or {}).get("ret")
        return round(v * 100.0, 2) if v is not None else None

    out = {k: r(v) for k, v in _MAP.items()}
    out["6M"] = _lookback_ret(series, 126)
    out["1Y"] = _lookback_ret(series, 252)
    return out


def _members(basket: dict, top: int = 8) -> list[dict]:
    rows = []
    for m in (basket.get("members") or []):
        r20 = m.get("ret_20d")
        rows.append({"t": m.get("symbol"),
                     "1W": None,  # THS member rows carry only 20d / ytd
                     "1M": round(r20 * 100.0, 2) if r20 is not None else None,
                     "name": m.get("name")})
    rows.sort(key=lambda m: (m["1M"] if m["1M"] is not None else -1e9), reverse=True)
    return rows[:top]


def compute_china_rotation(ths_json: dict, curated_json: dict, *,
                           generated_utc: str | None = None, asof: str | None = None) -> dict:
    ths_baskets = ths_json.get("baskets") or []
    ths_chart = (ths_json.get("chart") or {}).get("baskets") or {}
    cur_baskets = curated_json.get("baskets") or []
    cur_chart = (curated_json.get("chart") or {}).get("baskets") or {}
    asof = asof or ths_json.get("as_of") or ""

    # ---- SUBSECTORS: reliable THS concepts (>= 6 priced members) ----
    reliable = [b for b in ths_baskets if (b.get("n_members") or 0) >= _MIN_BREADTH and b.get("id")]
    sub_perf = {b["id"]: _perf_map(b, ths_chart.get(b["id"])) for b in reliable}
    sub_met = _rotation_metrics(sub_perf)
    subsectors = []
    for b in reliable:
        k = b["id"]
        subsectors.append({
            "key": k, "name": b.get("name") or k, "name_zh": b.get("name_zh") or b.get("name") or k,
            "theme": b.get("category") or "", "theme_zh": b.get("category_zh") or b.get("category") or "",
            "n_members": b.get("n_members") or 0,
            "members": _members(b),
            **sub_met[k],
        })
    subsectors.sort(key=lambda s: s["emerging_score"], reverse=True)
    for i, s in enumerate(subsectors):
        s["rank"] = i + 1

    # ---- THEMES: curated thematic baskets ----
    th_perf = {b["id"]: _perf_map(b, cur_chart.get(b["id"])) for b in cur_baskets if b.get("id")}
    th_met = _rotation_metrics(th_perf)
    themes = []
    for b in cur_baskets:
        k = b.get("id")
        if not k:
            continue
        mem = b.get("members") or []
        themes.append({
            "theme": b.get("name") or k, "theme_zh": b.get("name_zh") or b.get("name") or k,
            "key": k, "n_subs": b.get("n_members") or 0,
            "top_sub": (mem[0].get("name") if mem else None),
            "top_sub_zh": (mem[0].get("name") if mem else None),
            "category": b.get("category"), "category_zh": b.get("category_zh"),
            **th_met[k],
        })
    themes.sort(key=lambda t: t["emerging_score"], reverse=True)

    # ---- highlights (subsectors only, mirrors the US engine) ----
    emerging = [s["key"] for s in sorted(subsectors, key=lambda s: s["emerging_score"], reverse=True)
                if s["n_members"] >= _MIN_BREADTH and s["rs_mom"] > 0
                and (s["accel"] is None or s["accel"] >= 0)][:12]
    fading = [s["key"] for s in sorted(subsectors, key=lambda s: s["rs_mom"])
              if s["n_members"] >= _MIN_BREADTH and s["rs_ratio"] > 0 and s["rs_mom"] < 0][:12]
    leaders = [s["key"] for s in sorted(subsectors, key=lambda s: s["rs_ratio"], reverse=True)][:12]
    laggards = [s["key"] for s in sorted(subsectors, key=lambda s: s["rs_ratio"])][:12]

    return {
        "asof": asof, "generated_utc": generated_utc or "",
        "source": "tonghuashun_concept_boards + curated_baskets",
        "benchmark_label": "CSI 300", "benchmark_label_zh": "沪深300", "region": "china",
        "timeframes": ["1D", "1W", "1M", "MTD", "3M", "6M", "1Y", "YTD"],
        "mom_horizons": MOM_HORIZONS,
        "subsectors": subsectors, "themes": themes,
        "highlights": {"emerging": emerging, "fading": fading, "leaders": leaders, "laggards": laggards},
        "n_subsectors": len(subsectors), "n_themes": len(themes),
    }
