"""Build the Cross-Asset Vector page -> site/crossasset.html.

Standalone like build_commodities.py. Reads engine/cross_asset_trend.snapshot()
(TSMOM trend board + intermarket ratios + carry context) and the existing
correlation-regime leaf, and renders a REGIME/CONTEXT board. The trend factor is
academically contested and only modestly beats buy&hold after cost (verdict
CONTESTED, scripts/cross_asset_phase0.py), so the page frames it as a regime read,
never a strategy. UI only — never recomputes the validation.

W3-A: bumps flows schema to crossasset_flows.v2 (strictly additive over v1);
adds confirm, dollar, shadow, history accrual (COLLECT_LANE=nightly), and hero
composition per the CA-W3 bilingual matrix.

Usage: python -m scripts.build_crossasset
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_crossasset")


def _sparkline(vals, w: int = 180, h: int = 38, pad: int = 3) -> str:
    """SVG polyline points for a tiny sparkline from a list of values."""
    vals = [v for v in (vals or []) if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)
    return " ".join(f"{pad + i * (w - 2 * pad) / (n - 1):.1f},"
                    f"{pad + (h - 2 * pad) * (1 - (v - lo) / rng):.1f}"
                    for i, v in enumerate(vals))


# ---------------------------------------------------------------------------
# Hero composition — deterministic bilingual matrix (CA-W3 spec)
# ---------------------------------------------------------------------------
def _compose_hero(breadth: float | None, corr_verdict: str | None) -> dict:
    """Map (breadth_regime, concentration) -> hero dict per the CA-W3 matrix.

    breadth_regime: risk_on (>=0.34) | risk_off (<=-0.34) | mixed
    concentration: correlation verdict string (concentrated|converging|diversified|unknown)
    Returns: {tone, headline_en, headline_zh, stance_en, stance_zh, sub_en, sub_zh}
    """
    b = breadth if breadth is not None else 0.0
    breadth_regime = "risk_on" if b >= 0.34 else "risk_off" if b <= -0.34 else "mixed"
    concentration = corr_verdict if corr_verdict in ("concentrated", "converging", "diversified") else "unknown"

    # Matrix: (breadth_regime, concentration) -> (tone, headline_en, headline_zh, sub_en, sub_zh, stance_en, stance_zh)
    _M: dict[tuple[str, str], tuple[str, str, str, str, str, str, str]] = {
        ("risk_on",  "diversified"): (
            "green",
            "Risk appetite is broad — and healthy",
            "风险偏好广泛而健康",
            "Most assets are trending up, each for its own reasons.",
            "多数资产趋势向上，且各自独立驱动。",
            "Different markets are genuinely different bets right now.",
            "当前不同市场确实是不同的投资判断。",
        ),
        ("risk_on",  "converging"): (
            "amber",
            "Risk-on, with markets starting to move together",
            "风险偏好上升，市场开始同步",
            "Most assets are trending up, but they're increasingly the same trade.",
            "多数资产上行，但相似度在上升。",
            "Watch — holding several markets is starting to mean one bet.",
            "留意——同时持有多个市场正逐渐变成同一笔押注。",
        ),
        ("risk_on",  "concentrated"): (
            "amber",
            "Risk-on — but it's one crowded trade",
            "风险偏好高涨——但这是一笔拥挤的交易",
            "Most assets are rising together, driven by the same force.",
            "多数资产同涨，由同一股力量驱动。",
            "Careful: different markets are one bet right now — they can fall together too.",
            "小心：不同市场当前是同一笔押注——下跌时也会一起跌。",
        ),
        ("mixed",    "diversified"): (
            "amber",
            "No clear trend — markets are going their own ways",
            "没有明确趋势——各市场各走各路",
            "Trends are split across assets, with little shared direction.",
            "各资产趋势分化，缺乏共同方向。",
            "Nothing to chase — pick your spots market by market.",
            "无需追逐——逐个市场把握机会。",
        ),
        ("mixed",    "converging"): (
            "amber",
            "No clear trend, but markets are syncing up",
            "趋势不明，但市场正在同步",
            "Trends are split, yet assets increasingly move together.",
            "趋势分化，但资产联动在增强。",
            "Watch — don't chase; a single driver is taking over.",
            "观望勿追——单一驱动力正在接管。",
        ),
        ("mixed",    "concentrated"): (
            "amber",
            "Markets are one bet without a clear direction",
            "市场已成同一笔押注，方向却不明",
            "Assets are tightly linked but not trending — fragile either way.",
            "资产高度联动却无趋势——上下皆脆弱。",
            "Stand aside from stacking similar positions.",
            "避免叠加相似仓位。",
        ),
        ("risk_off", "diversified"): (
            "red",
            "Defensive trends are taking over",
            "防御性趋势正在主导",
            "More assets are falling than rising; havens are winning.",
            "下跌资产多于上涨，避险资产占优。",
            "Protect gains — favor the safe side of the board.",
            "保住盈利——偏向防御类资产。",
        ),
        ("risk_off", "converging"): (
            "red",
            "Risk-off is spreading across markets",
            "风险规避正在跨市场蔓延",
            "Defensive trends are broadening and assets are syncing up.",
            "防御趋势扩散，资产联动上升。",
            "Protect gains — reduce lookalike positions.",
            "保住盈利——减少相似仓位。",
        ),
        ("risk_off", "concentrated"): (
            "red",
            "Risk-off, and everything is falling together",
            "风险规避，且各资产同步下跌",
            "One force is dragging most assets down at once.",
            "同一股力量正同时拖累多数资产。",
            "Protect gains — diversification isn't protecting you right now.",
            "保住盈利——当前分散投资并不能保护你。",
        ),
    }

    key = (breadth_regime, concentration)
    if key not in _M:
        # unknown concentration: use breadth-only row (rows 1/4/7 adjusted)
        key = (breadth_regime, "diversified")

    tone, hl_en, hl_zh, sub_en, sub_zh, st_en, st_zh = _M[key]
    return {
        "tone": tone,
        "headline_en": hl_en,
        "headline_zh": hl_zh,
        "sub_en": sub_en,
        "sub_zh": sub_zh,
        "stance_en": st_en,
        "stance_zh": st_zh,
    }


# ---------------------------------------------------------------------------
# History accrual (CA-W3-R3) — nightly lane only, single writer
# ---------------------------------------------------------------------------
def _append_history(outdir: Path, asof: str | None, snap: dict,
                    corr_block: dict | None, leadlag_block: dict | None,
                    liq_block: dict | None, fund_block: dict | None,
                    confirm: dict | None, dollar: dict | None) -> None:
    """Append one row to data/crossasset/history.jsonl (nightly lane only).
    Dedup: skip if last line has same asof."""
    _lane = (os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")).lower()
    if _lane != "nightly":
        return
    hist_path = outdir / "history.jsonl"
    try:
        # dedup check
        if hist_path.exists():
            last_line = None
            with open(hist_path, "rb") as fh:
                # read last non-empty line efficiently
                fh.seek(0, 2)
                size = fh.tell()
                if size > 0:
                    fh.seek(max(0, size - 2048))
                    tail = fh.read().decode("utf-8", errors="replace")
                    lines = [l.strip() for l in tail.splitlines() if l.strip()]
                    if lines:
                        try:
                            last_line = json.loads(lines[-1])
                        except Exception:
                            last_line = None
            if last_line and last_line.get("asof") == asof:
                log.info("history.jsonl: asof %s already present — skipping dedup", asof)
                return

        row = {
            "asof": asof,
            "regime": snap.get("regime"),
            "breadth": snap.get("breadth"),
            "absorption_pctile": (corr_block or {}).get("absorption_pctile"),
            "absorption_ratio": (corr_block or {}).get("absorption_ratio"),
            "corr_verdict": (corr_block or {}).get("verdict"),
            "leadlag_verdict": (leadlag_block or {}).get("verdict"),
            "funding_state": (fund_block or {}).get("state"),
            "funding_score": (fund_block or {}).get("score"),
            "liq_state": (liq_block or {}).get("state"),
            "confirm_verdict": (confirm or {}).get("verdict"),
            "agree_pct": (confirm or {}).get("agree_pct"),
            "dollar_dir": (dollar or {}).get("usd_dir"),
            "logged_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(hist_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        log.info("history.jsonl: appended asof %s", asof)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("history.jsonl append failed: %s", e)


def main() -> int:
    from engine import cross_asset_trend as cat
    try:
        snap = cat.snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("cross-asset snapshot failed: %s", e)
        return 0
    if not snap:
        log.warning("cross-asset snapshot empty (need >=4 legs) — skipping page")
        return 0

    # global central-bank liquidity (additive macro-driver leaf; None if FRED data absent)
    try:
        from engine import global_liquidity
        liquidity = global_liquidity.snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("global liquidity snapshot failed: %s", e)
        liquidity = None

    # funding/repo plumbing stress (additive leaf; None if OFR data absent)
    try:
        from engine import funding_stress
        funding = funding_stress.snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("funding-stress snapshot failed: %s", e)
        funding = None

    # cross-asset lead/lag transmission read (additive leaf; HAC + FDR gated,
    # validated DISPLAY-only by scripts/cross_asset_leadlag_phase0.py — a regime
    # gauge, not a hedge ratio). None if <3 markets / too little overlap.
    try:
        from engine import cross_asset
        leadlag = cross_asset.leadlag_snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("lead/lag snapshot failed: %s", e)
        leadlag = None

    # Dollar factor — the forex Dollar Desk's cross-asset transmission (display-only,
    # contemporaneous). Degrades to None if build_forex hasn't written latest.json.
    try:
        from lib import forex_link
        _tr = forex_link.transmission()
        _rows = []
        for k in ("SPY", "EEM", "GC=F", "CL=F", "HG=F", "UST10", "BTC"):
            ac = forex_link.asset_corr(k, _tr)
            if ac:
                _rows.append({"label": ac["label"], "label_zh": ac["label_zh"],
                              "corr": ac["corr"], "stable": ac["stable"]})
        _rows.sort(key=lambda r: r["corr"])            # most negative (biggest headwind) first
        dollar_factor = {"rows": _rows, "usd_dir": _tr.get("usd_dir")} if _rows else None
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("dollar-factor read failed: %s", e)
        dollar_factor = None

    # ── W3-A: confirm block (data/regime/latest.json → cross_asset_confirm) ──
    confirm: dict | None = None
    try:
        _regime_path = config.data_dir() / "regime" / "latest.json"
        if _regime_path.exists():
            _regime_raw = json.loads(_regime_path.read_text())
            _cac = _regime_raw.get("cross_asset_confirm")
            if _cac is not None and isinstance(_cac, dict):
                confirm = {
                    "verdict": _cac.get("verdict"),
                    "agree_pct": _cac.get("agree_pct"),
                    "n_blind_flags": _cac.get("n_blind_flags"),
                    "flags_top": (_cac.get("caution_flags") or [])[:3],
                    "asof": _cac.get("asof"),
                }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("confirm block read failed: %s", e)
        confirm = None

    # ── W3-A: dollar block (data/forex/latest.json) ────────────────────────
    dollar: dict | None = None
    try:
        _forex_path = config.data_dir() / "forex" / "latest.json"
        if _forex_path.exists():
            _forex_raw = json.loads(_forex_path.read_text())
            _fx_tr = _forex_raw.get("transmission") or {}
            _fx_rr = _forex_raw.get("regime_radar") or {}
            # corr_top: sorted by |corr| desc, keep top 3
            _fx_corr = _fx_tr.get("corr") or {}
            _corr_sorted = sorted(
                [{"key": k, "corr": v} for k, v in _fx_corr.items() if v is not None],
                key=lambda x: abs(x["corr"]),
                reverse=True,
            )[:3]
            # fx_stress: dominant + top intensity key+val (None if absent)
            _fx_stress: dict | None = None
            _fx_intensity = _fx_rr.get("intensity") or {}
            if _fx_intensity:
                _top_key = max(_fx_intensity, key=lambda k: _fx_intensity[k] or 0)
                _top_val = _fx_intensity[_top_key]
                _fx_stress = {
                    "dominant": _fx_rr.get("dominant"),
                    "top_key": _top_key,
                    "top_val": _top_val,
                }
            dollar = {
                "usd_dir": _fx_tr.get("usd_dir"),
                "regime": _forex_raw.get("regime"),
                "risk": _forex_raw.get("risk"),
                "corr_top": _corr_sorted,
                "unstable_n": len(_fx_tr.get("unstable") or []),
                "fx_stress": _fx_stress,
            }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("dollar block read failed: %s", e)
        dollar = None

    # ── W3-A: shadow block (engine.crossasset_shadow.run()) ────────────────
    shadow: dict | None = None
    try:
        from engine import crossasset_shadow  # built by lane W3-B; tolerate ImportError
        shadow = crossasset_shadow.run()
    except Exception as e:  # noqa: BLE001 — additive, tolerate missing
        log.debug("crossasset_shadow unavailable: %s", e)
        shadow = None

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    from engine.i18n import td, tr
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(tr=tr, td=td)

    # ── hero composition ────────────────────────────────────────────────────
    _corr_snap = snap.get("correlation") or {}
    _corr_verdict = _corr_snap.get("verdict") if isinstance(_corr_snap, dict) else None
    hero = _compose_hero(snap.get("breadth"), _corr_verdict)

    # absorption weekly sparkline (from cross_asset.snapshot — already computed)
    _ar_spark_w = _corr_snap.get("absorption_spark_w") if isinstance(_corr_snap, dict) else None
    ar_spark = _sparkline(_ar_spark_w) if _ar_spark_w else ""

    html = env.get_template("crossasset.html.j2").render(
        # ── existing vars (unchanged) ──────────────────────────────────────
        as_of=snap.get("asof"), built=built, regime=snap.get("regime"),
        breadth=snap.get("breadth"), trend=snap.get("trend"), ratios=snap.get("ratios"),
        carry=snap.get("carry"), correlation=snap.get("correlation"), note=snap.get("note"),
        leadlag=leadlag, dollar_factor=dollar_factor,
        liquidity=liquidity, liq_spark=(_sparkline(liquidity["spark"]) if liquidity else ""),
        funding=funding, fund_spark=(_sparkline(funding["spark"]) if funding else ""),
        # ── W3-A NEW vars ─────────────────────────────────────────────────
        hero=hero, ar_spark=ar_spark,
        confirm=confirm, dollar=dollar, shadow=shadow,
    )
    site = config.ROOT / config.load()["storage"]["site_dir"]
    write_page(site / "crossasset.html", html)
    log.info("wrote %s/crossasset.html (%d KB)", site, len(html) // 1024)

    # hub feed (consumed by build_vector's hub card; runs before build_vector)
    outdir = config.data_dir() / "crossasset"
    outdir.mkdir(parents=True, exist_ok=True)

    # ── flows block (W3-A: schema crossasset_flows.v2, strictly additive over v1) ──
    _FLOWS_NOTE = (
        "display-only regime read; TSMOM fails DSR (cross-asset-phase0), "
        "lead/lag=lag-1 timezone (cross-asset-leadlag-phase0) — "
        "not a strategy/hedge-ratio"
    )

    # correlation sub-block: enriched with numerics + weekly spark
    _corr_raw = snap.get("correlation") or {}
    _corr_block: dict | None
    if isinstance(_corr_raw, dict) and _corr_raw.get("verdict") not in (None, "unknown"):
        _corr_block = {
            "verdict": _corr_raw.get("verdict"),
            "absorption_pctile": _corr_raw.get("absorption_pctile_5y"),
            "n_markets": len(_corr_raw.get("markets") or []) or None,
            "absorption_ratio": _corr_raw.get("absorption_ratio"),
            "mean_abs_corr": _corr_raw.get("mean_abs_corr"),
            "dominant_cluster": _corr_raw.get("dominant_cluster"),
            "spark_w": _corr_raw.get("absorption_spark_w") or [],
            "spark_asof": _corr_raw.get("absorption_spark_asof"),
        }
    else:
        _corr_block = None

    # trend_top: top 6 rows from snap.trend (tsmom panel rows)
    _trend_raw = snap.get("trend") or {}
    _trend_rows = (_trend_raw.get("rows") or [])[:6]
    _trend_top: list[dict] = [
        {"asset": r.get("key"), "trend": r.get("trend"), "z": r.get("score")}
        for r in _trend_rows
    ] if _trend_rows else []

    # trend_summary
    _trend_summary = {
        "n": _trend_raw.get("n", 0),
        "n_up": _trend_raw.get("n_up", 0),
        "n_down": _trend_raw.get("n_down", 0),
    }

    # intermarket: from snap.ratios (ratio_panel output); ADD pctile per row
    _ratios_raw = snap.get("ratios") or []
    _intermarket: list[dict] = [
        {
            "pair": r.get("key"),
            "ratio": r.get("value"),
            "trend": r.get("state"),
            "pctile": r.get("pctile"),
        }
        for r in _ratios_raw
    ] if _ratios_raw else []

    # carry: compact from snap.carry
    _carry_raw = snap.get("carry") or {}
    _carry_block: dict | None = None
    _carry_rows = _carry_raw.get("rows") or []
    if _carry_rows:
        _carry_block = {"rows": _carry_rows, "note": _carry_raw.get("note")}

    # leadlag: enriched with stable + lead_asset + n fields
    _leadlag_block: dict | None
    if leadlag is not None and isinstance(leadlag, dict):
        _ll_links = leadlag.get("links") or []
        _lead_asset_raw = leadlag.get("lead_asset")
        _lead_asset: dict | None = None
        if isinstance(_lead_asset_raw, dict):
            _lead_asset = {
                "name": _lead_asset_raw.get("name"),
                "n_followers": _lead_asset_raw.get("n_followers"),
            }
        _leadlag_block = {
            "verdict": leadlag.get("verdict"),
            "links": _ll_links[:6],
            "stable": leadlag.get("stability", {}).get("held_prior_window") if isinstance(leadlag.get("stability"), dict) else None,
            "lead_asset": _lead_asset,
            "n_significant": leadlag.get("n_significant"),
            "n_tested": leadlag.get("n_tested"),
        }
    else:
        _leadlag_block = {"verdict": None, "links": [], "stable": None, "lead_asset": None,
                          "n_significant": None, "n_tested": None}

    # global_liquidity: compact from global_liquidity.snapshot() + impulse_13w
    _liq_block: dict | None = None
    if liquidity is not None and isinstance(liquidity, dict):
        _liq_block = {
            "asof": liquidity.get("asof"),
            "state": liquidity.get("state"),
            "accel": liquidity.get("accel"),
            "total_usd_tn": liquidity.get("total_usd_tn"),
            "impulse_13w": liquidity.get("impulse_13w"),
        }

    # funding_stress: compact from funding_stress.snapshot()
    _fund_block: dict | None = None
    if funding is not None and isinstance(funding, dict):
        _fund_block = {
            "asof": funding.get("asof"),
            "state": funding.get("state"),
            "score": funding.get("score"),
            "spread_bp": funding.get("spread_bp"),
        }

    _flows_block = {
        "schema": "crossasset_flows.v2",
        "display_only": True,
        "regime": snap.get("regime"),
        "correlation": _corr_block,
        "breadth": snap.get("breadth"),
        "trend_top": _trend_top,
        "trend_summary": _trend_summary,
        "intermarket": _intermarket,
        "carry": _carry_block,
        "leadlag": _leadlag_block,
        "global_liquidity": _liq_block,
        "funding_stress": _fund_block,
        "confirm": confirm,
        "dollar": dollar,
        "shadow": shadow,
        "note": _FLOWS_NOTE,
    }

    # ISO asof (NEW — keep "date" display string for backward compat)
    _asof_iso = snap.get("asof")  # already ISO date string from tsmom_panel

    (outdir / "latest.json").write_text(json.dumps({
        # ── LEGACY KEYS (byte-identical to pre-R6 contract; do NOT rename) ──
        "date": snap.get("asof"), "regime": snap.get("regime"),
        "breadth": snap.get("breadth"), "favored": snap.get("favored", []),
        "correlation": (snap.get("correlation") or {}).get("verdict"),
        # ── R6 ADDITIVE FIELDS ──
        "asof": _asof_iso,
        "flows": _flows_block,
    }, indent=2, default=str))
    log.info("wrote data/crossasset/latest.json with flows.v2 block")

    # ── history accrual (CA-W3-R3) ─────────────────────────────────────────
    _append_history(outdir, _asof_iso, snap, _corr_block, _leadlag_block,
                    _liq_block, _fund_block, confirm, dollar)

    return 0


if __name__ == "__main__":
    sys.exit(main())
