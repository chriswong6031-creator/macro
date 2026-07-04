"""Build the Impulse Tracker page (site/impulse.html) + its data (site/factordata/
impulse.json).

Loads the wide close + volume caches (the S&P-1500 breadth universe — the practical
"all US equities" set), runs engine.impulse over the full cross-section, and buckets
the names into action lanes:

  buy       EARLY_IGNITION + liquid — impulse JUST turning up, volume confirming, the
            move not yet run → an entry still exists. The headline grid.
  igniting  accelerating but already past the freshest entry (momentum building).
  extended  EXTENDED_RUN — accelerating but already ran; no entry, wait for a pullback.
  coiling   quiet base with volume starting to perk — pre-ignition watch.
  fading    acceleration rolling over / down-trend — exit / avoid.

Self-contained builder (the build_allocation pattern): it both computes the JSON and
renders the HTML, so it is resilient and runnable on its own
(`python -m scripts.build_impulse`). Additive + never fatal. Display/context only —
nothing here feeds a score elsewhere (engine.impulse honesty gate).
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader

from engine import i18n, impulse
from lib import config
from lib.pages import write_page

log = logging.getLogger("build_impulse")

# tiers whose wide caches together form the US cross-section
_TIERS = ("breadth", "midcap_breadth", "smallcap_breadth")
# display caps per lane (the page offers "show more" beyond the first rows)
_CAPS = {"buy": 60, "igniting": 24, "extended": 18, "coiling": 18, "fading": 12}


# --------------------------------------------------------------------------- #
#  data loading
# --------------------------------------------------------------------------- #
def _load_panel(kind: str) -> pd.DataFrame:
    """Merge the per-tier wide caches into one panel. ``kind`` ∈ {_closes_cache,
    _volume_cache}. Priority = tier order (a ticker is taken from the first cache
    that carries it). Duplicate columns dropped."""
    frame: pd.DataFrame | None = None
    for tier in _TIERS:
        p = config.data_dir() / tier / f"{kind}.parquet"
        if not p.exists():
            continue
        try:
            d = pd.read_parquet(p)
        except Exception as e:  # noqa: BLE001 — one corrupt cache must not kill the page
            log.warning("%s/%s unreadable (%s) — skipped", tier, kind, e)
            continue
        d = d.loc[:, ~d.columns.duplicated()]
        if frame is None:
            frame = d
        else:
            new = [c for c in d.columns if c not in frame.columns]
            frame = frame.join(d[new], how="outer")
    if frame is None:
        return pd.DataFrame()
    return frame.sort_index().loc[:, lambda x: ~x.columns.duplicated()]


def _meta_map() -> dict[str, dict]:
    """ticker → {name, sector} from the per-tier constituents files."""
    out: dict[str, dict] = {}
    for tier in _TIERS:
        p = config.data_dir() / tier / "constituents.parquet"
        if not p.exists():
            continue
        try:
            m = pd.read_parquet(p)
        except Exception as e:  # noqa: BLE001
            log.warning("%s constituents unreadable (%s)", tier, e)
            continue
        for tk, row in m.iterrows():
            out.setdefault(str(tk), {"name": str(row.get("name", tk)),
                                     "sector": str(row.get("sector", ""))})
    return out


def _regime() -> dict:
    """Calm/stress read from the engine's vol_regime (data/regime/latest.json).
    Momentum's forward edge decays in stress, so the page surfaces this and flags
    reduced confidence — it does not silently kill the list.

    Migration (W1 PR2): try world_state.vol first; fall back to the legacy
    direct read of data/regime/latest.json['vol_regime'].  Arithmetic is
    unchanged — the field names and thresholds are identical.
    """
    out = {"state": "unknown", "label": "Regime unknown", "label_zh": "市场状态未知",
           "vix": None, "risk_score": None, "calm": True}
    try:
        # --- W1 PR2 migration path ---
        from engine.neuralweb.read import load_world_state, get as ws_get
        ws = load_world_state()
        if ws is not None:
            vr = ws.get("vol") or {}
        else:
            # Legacy fallback: direct read of data/regime/latest.json
            d = json.loads((config.data_dir() / "regime" / "latest.json").read_text())
            vr = d.get("vol_regime") or {}

        rs = vr.get("risk_score")
        vix = vr.get("vix")
        out["vix"] = vix
        out["risk_score"] = rs
        if rs is None:
            return out
        if rs < 0.33:
            out.update(state="calm", calm=True,
                       label="Calm tape — momentum edge intact",
                       label_zh="平静行情 — 动量优势完好")
        elif rs < 0.60:
            out.update(state="mixed", calm=True,
                       label="Mixed tape — partial confidence",
                       label_zh="混合行情 — 部分可信")
        else:
            out.update(state="stress", calm=False,
                       label="Stressed tape — momentum decays, reduced confidence",
                       label_zh="承压行情 — 动量衰减，信心下降")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("regime read failed (%s)", e)
    return out


# --------------------------------------------------------------------------- #
#  presentation helpers
# --------------------------------------------------------------------------- #
def _spark_svg(vals, color: str = "var(--link)", w: int = 240, h: int = 40) -> str:
    """Tiny inline sparkline (area + line + last dot) — mirrors build_stock_library.
    _spark_svg / build_site._mini_svg."""
    vals = [float(v) for v in vals if v is not None and v == v]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n, pad = len(vals), h * 0.12

    def xy(i, v):
        return (i / (n - 1) * w, (h - pad) - ((v - lo) / rng) * (h - 2 * pad) + pad)

    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(i, v) for i, v in enumerate(vals)))
    lx, ly = xy(n - 1, vals[-1])
    return (f'<svg class="nch" viewBox="0 0 {w} {h}" preserveAspectRatio="none" '
            f'width="100%" height="{h}">'
            f'<polyline points="0,{h} {pts} {w},{h}" fill="{color}" opacity="0.12" stroke="none"/>'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.7" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.6" fill="{color}"/></svg>')


_STATE_COLOR = {impulse.EARLY_IGNITION: "var(--up)", impulse.IGNITING: "var(--up)",
                impulse.COILING: "var(--link)", impulse.EXTENDED_RUN: "var(--warn)",
                impulse.FADING: "var(--down)", impulse.NEUTRAL: "var(--muted)"}


def _f(x, default=None):
    """Finite float or default (NaN/Inf → default)."""
    try:
        v = float(x)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def _note(state: str, r: pd.Series) -> tuple[str, str]:
    """A short, number-bearing reason string (en, zh) per state."""
    az = _f(r.get("accel_z"), 0.0)
    vv = _f(r.get("vol_vel"))
    ru = _f(r.get("runup_20"), 0.0) * 100
    d50 = _f(r.get("dist_50"), 0.0) * 100
    vvp = (vv - 1) * 100 if vv is not None else None
    vtxt = f"volume {vvp:+.0f}%" if vvp is not None else "volume n/a"
    vtxt_zh = f"量{vvp:+.0f}%" if vvp is not None else "量缺失"
    if state == impulse.EARLY_IGNITION:
        return (f"Igniting now — accel z {az:+.1f}, {vtxt}, only {ru:+.0f}% over 20d. Entry still open.",
                f"刚刚点火 — 加速度 z {az:+.1f}，{vtxt_zh}，20日仅 {ru:+.0f}%。入场窗口仍开。")
    if state == impulse.IGNITING:
        return (f"Accelerating — accel z {az:+.1f}. Up {ru:+.0f}% in 20d; past the freshest entry.",
                f"加速中 — 加速度 z {az:+.1f}。20日 {ru:+.0f}%；已过最佳入场点。")
    if state == impulse.EXTENDED_RUN:
        return (f"Already ran {ru:+.0f}% (20d), {d50:+.0f}% over the 50d avg. No entry — wait for a pullback.",
                f"已上涨 {ru:+.0f}%（20日），高出50日均线 {d50:+.0f}%。无入场点 — 等回调。")
    if state == impulse.COILING:
        return (f"Coiled base — flat price, {vtxt}. Watch for ignition.",
                f"蓄势基底 — 价格走平，{vtxt_zh}。留意点火。")
    if state == impulse.FADING:
        return (f"Rolling over — accel z {az:+.1f}, trend weakening. Avoid.",
                f"动能转弱 — 加速度 z {az:+.1f}，趋势走弱。回避。")
    return ("No clear impulse.", "无明显冲量。")


def _card(tk: str, r: pd.Series, closes: pd.DataFrame, meta: dict) -> dict:
    """Display dict for one ticker."""
    state = r["state"]
    m = meta.get(tk, {})
    series = closes[tk].dropna().tail(46).tolist() if tk in closes.columns else []
    note_en, note_zh = _note(state, r)
    return {
        "ticker": tk,
        "name": m.get("name", tk),
        "sector": m.get("sector", ""),
        "price": _f(r.get("price")),
        "impulse_score": int(_f(r.get("impulse_score"), 0)),
        "state": state,
        "just_starting": bool(r.get("just_starting", False)),
        "days_igniting": int(_f(r.get("days_igniting"), 0)),
        "accel_z": _f(r.get("accel_z")),
        "vel_pct": _f(r.get("vel_pct")),
        "impulse_macd": _f(r.get("impulse_macd")),
        "eff_ratio": _f(r.get("eff_ratio")),
        "trend_vel": _f(r.get("trend_vel")),
        "runup_5": _f(r.get("runup_5")),
        "runup_20": _f(r.get("runup_20")),
        "dist_50": _f(r.get("dist_50")),
        "dist_200": _f(r.get("dist_200")),
        "off_high": _f(r.get("off_high")),
        "rvol": _f(r.get("rvol")),
        "vol_vel": _f(r.get("vol_vel")),
        "adv20": _f(r.get("adv20")),
        "spark_svg": _spark_svg(series, _STATE_COLOR.get(state, "var(--link)")),
        "note": note_en,
        "note_zh": note_zh,
    }


def _json_safe(o):
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_safe(v) for v in o]
    return o


# --------------------------------------------------------------------------- #
#  the build
# --------------------------------------------------------------------------- #
def compute() -> dict:
    """Run the engine and assemble the lane buckets + meta. Returns the JSON dict
    (also used directly by the renderer)."""
    cfg = impulse.ImpulseConfig.from_config(config.load().get("impulse"))
    closes = _load_panel("_closes_cache")
    volumes = _load_panel("_volume_cache")
    if closes.empty:
        log.warning("no close caches found — impulse page degrades to empty")
        return {"status": "no_data"}

    res = impulse.score_panel(closes, volumes, cfg=cfg)
    if res.empty:
        return {"status": "no_scored"}
    meta = _meta_map()
    as_of = closes.index.max()

    def _lane(mask: pd.Series, cap: int) -> list[dict]:
        sub = res[mask].head(cap)
        return [_card(tk, r, closes, meta) for tk, r in sub.iterrows()]

    liquid = res["liquid"].fillna(False)
    buy = _lane((res["state"] == impulse.EARLY_IGNITION) & liquid, _CAPS["buy"])
    igniting = _lane((res["state"] == impulse.IGNITING) & liquid, _CAPS["igniting"])
    extended = _lane(res["state"] == impulse.EXTENDED_RUN, _CAPS["extended"])
    # coiling sorted by volume velocity (strongest base-with-volume first)
    coil = res[(res["state"] == impulse.COILING) & liquid].copy()
    coil = coil.sort_values("vol_vel", ascending=False).head(_CAPS["coiling"])
    coiling = [_card(tk, r, closes, meta) for tk, r in coil.iterrows()]
    fading = _lane(res["state"] == impulse.FADING, _CAPS["fading"])

    regime = _regime()
    n_buy = int(((res["state"] == impulse.EARLY_IGNITION) & liquid).sum())
    payload = {
        "as_of": as_of.strftime("%Y-%m-%d") if pd.notna(as_of) else None,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "status": "ok",
        "regime": regime,
        "universe": int(len(res)),
        "with_volume": int(res["vol_vel"].notna().sum()),
        "n_buy": n_buy,
        "counts": {
            "buy": n_buy,
            "igniting": int(((res["state"] == impulse.IGNITING) & liquid).sum()),
            "extended": int((res["state"] == impulse.EXTENDED_RUN).sum()),
            "coiling": int((res["state"] == impulse.COILING).sum()),
            "fading": int((res["state"] == impulse.FADING).sum()),
        },
        "buy": buy,
        "igniting": igniting,
        "extended": extended,
        "coiling": coiling,
        "fading": fading,
        "cfg": cfg.as_dict(),
    }
    return payload


def render(payload: dict, site=None) -> None:
    site = site or (config.ROOT / "site")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = env.get_template("impulse.html.j2").render(d=payload, built=built)
    write_page(site / "impulse.html", html)
    log.info("wrote %s (%.0f KB)", site / "impulse.html",
             (site / "impulse.html").stat().st_size / 1024)


def build(write: bool = True) -> dict:
    payload = compute()
    if write and payload.get("status") == "ok":
        site = config.ROOT / "site"
        (site / "factordata").mkdir(parents=True, exist_ok=True)
        (site / "factordata" / "impulse.json").write_text(
            json.dumps(_json_safe(payload), separators=(",", ":"), allow_nan=False))
        log.info("wrote impulse.json (%d buy of %d universe · regime=%s)",
                 payload.get("n_buy", 0), payload.get("universe", 0),
                 (payload.get("regime") or {}).get("state"))
        render(payload, site)
    elif write:
        # degrade-safe: still render an honest "no data" page rather than 404
        try:
            render(payload, config.ROOT / "site")
        except Exception as e:  # noqa: BLE001
            log.warning("impulse render skipped (%s)", e)
    return payload


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s :: %(message)s")
    try:
        build()
        return 0
    except Exception as e:  # noqa: BLE001 — additive, never aborts the daily run
        log.error("build_impulse failed: %s", e)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
