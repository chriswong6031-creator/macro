"""China Income Vector — onshore-RMB allocation deep-dive page builder.

Renders site/china_allocation.html from engine.china_allocation (the statically-
diversified income+gold+bond strategy that, unlike the US trend-timer, reduces A-share
drawdown and lifts Sharpe through DIVERSIFICATION, not momentum). Reached from the blue
allocation button on the "MAJOR CHINA INDEXES" panel, exactly like spvector.html on the
US side. Self-contained shell cloned from spvector.html.j2 (own CSS from the build_vector
palette, the unified nav, theme.js); reuses the build_vector Plotly size-helpers.

Also writes data/china_regime/china_alloc_latest.json — the compact card the China macro
build reads for the index-health allocation button (mirrors data/regime/spvector_latest.json).
Honest by design: the page LEADS with the validated diversified blend and SHOWS the tested
momentum overlay failing, so the "why we don't time it" finding is transparent.

Run: python -m scripts.build_china_allocation
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import plotly.graph_objects as go

from engine import china_allocation as ca
from lib import config
from scripts.build_vector import _html, PLOT, C

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# charts (built straight from the {dates, vals} curve lists, downsampled)
# --------------------------------------------------------------------------- #
def _chart_growth(curves: dict) -> str:
    d = curves.get("dates", [])
    if not d:
        return ""
    st = 5
    x = d[::st]
    fig = go.Figure()
    if curves.get("csi300"):
        fig.add_trace(go.Scatter(x=x, y=curves["csi300"][::st], name="CSI 300 buy & hold",
                                 line={"color": C["priceln"], "width": 1.4}))
    if curves.get("income"):
        fig.add_trace(go.Scatter(x=x, y=curves["income"][::st], name="Income core only",
                                 line={"color": C["amber"], "width": 1.3}))
    fig.add_trace(go.Scatter(x=x, y=curves["strat"][::st], name="China Income Vector",
                             line={"color": C["blue"], "width": 2.2}))
    fig.update_yaxes(type="log")
    fig.update_layout(**{**PLOT, "height": 320})
    return _html(fig)


def _chart_dd(curves: dict) -> str:
    d = curves.get("dates", [])
    if not d:
        return ""
    st = 5
    x = d[::st]
    fig = go.Figure()
    if curves.get("dd_csi300"):
        fig.add_trace(go.Scatter(x=x, y=curves["dd_csi300"][::st], name="CSI 300 buy & hold",
                                 fill="tozeroy", line={"color": C["priceln"], "width": 1},
                                 fillcolor="rgba(154,164,178,0.22)"))
    fig.add_trace(go.Scatter(x=x, y=curves["dd_strat"][::st], name="China Income Vector",
                             fill="tozeroy", line={"color": C["blue"], "width": 1.6},
                             fillcolor="rgba(40,95,255,0.12)"))
    fig.update_layout(**{**PLOT, "height": 320})
    return _html(fig)


# --------------------------------------------------------------------------- #
# view-model
# --------------------------------------------------------------------------- #
def _split_segments(variant_key: str) -> list[dict]:
    """Ordered allocation-bar segments (income, growth, gold, bond) for one variant."""
    w = ca.VARIANTS[variant_key]["weights"]
    segs = []
    for key in ("income", "growth", "gold", "bond"):
        if key in w and w[key] > 0:
            m = ca.SLEEVES[key]
            segs.append({"key": key, "name_en": m["name_en"], "name_zh": m["name_zh"],
                         "color": m["color"], "pct": round(100 * w[key])})
    return segs


def _variant_rows(snap: dict) -> list[dict]:
    rows = []
    for key, spec in ca.VARIANTS.items():
        bt = snap["variants"].get(key, {})
        rows.append({
            "key": key, "label_en": spec["label_en"], "label_zh": spec["label_zh"],
            "blurb_en": spec["blurb_en"], "blurb_zh": spec["blurb_zh"],
            "weights": {k: round(100 * v) for k, v in spec["weights"].items()},
            "segments": _split_segments(key),
            "cagr": bt.get("cagr"), "sharpe": bt.get("sharpe"), "maxdd": bt.get("maxdd"),
            "vol": bt.get("vol"), "years": bt.get("years"),
            "is_default": key == snap["default_variant"],
        })
    return rows


def build() -> str:
    from jinja2 import Environment, FileSystemLoader

    snap = ca.snapshot()
    default = snap["default_variant"]
    bt = snap["variants"][default]
    bench_csi = bt.get("bench_csi300", {})
    bench_inc = bt.get("bench_income", {})

    vm = {
        "as_of": snap["as_of"],
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "default_variant": default,
        "default_label_en": ca.VARIANTS[default]["label_en"],
        "default_label_zh": ca.VARIANTS[default]["label_zh"],
        "split": _split_segments(default),
        "card": snap["card"],
        "stat": {"cagr": bt.get("cagr"), "sharpe": bt.get("sharpe"), "sortino": bt.get("sortino"),
                 "maxdd": bt.get("maxdd"), "vol": bt.get("vol"), "years": bt.get("years"),
                 "final_mult": bt.get("final_mult"), "start": bt.get("start"),
                 "bootstrap": bt.get("bootstrap", {})},
        "bench_csi": bench_csi, "bench_inc": bench_inc,
        "variants": _variant_rows(snap),
        "sleeves": snap["current"]["sleeves"],
        "momentum": snap["momentum_ab"],
        "alt_cores": [{"ticker": k, **v} for k, v in snap["alt_cores"].items()],
        "episodes": bt.get("bear_episodes", []),
        "charts": {"growth": _chart_growth(snap["curves"]), "dd": _chart_dd(snap["curves"])},
    }

    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001 — i18n absent -> English-only, still builds
        env.globals.update(td=lambda en: en, tr=lambda en: en)
    html = env.get_template("china_allocation.html.j2").render(**vm, C=C)
    out = config.ROOT / "site" / "china_allocation.html"
    out.write_text(html)

    # compact card for the China macro index-health allocation button
    card = snap["card"]
    snap_out = {"date": snap["as_of"], **card,
                "bench_csi_sharpe": bench_csi.get("sharpe"), "bench_csi_maxdd": bench_csi.get("maxdd")}
    snap_dir = config.data_dir() / "china_regime"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "china_alloc_latest.json").write_text(json.dumps(snap_out, indent=2))
    return str(out)


def main() -> int:
    out = build()
    print(f"[built] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
