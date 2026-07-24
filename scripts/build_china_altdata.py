"""Build the standalone China Alternative-Data desk page + machine-readable emits.

Runs the per-ticker convergence kernel + the honest signal-lab scorecard, fuses in the
richer alt-data planes that already ran upstream in the nightly (participation "who controls
the tape" regime, special-situations catalysts, THS narrative-basket radar) plus the fast
keyless microstructure parsers (涨停池 limit-up pool + sector breadth), renders
site/china_altdata.html, and emits site/chinaaltdata/{by_ticker,mastermind,feed}.json (the
mastermind.json is the context lens the intel bus + future China Mastermind read).

Render-budget note: the heavy engines (participation tape, special-situations EDGAR scan,
narrative radar) are NOT recomputed here — they run earlier in the same nightly cluster and
we READ their emitted JSON. Only the cheap keyless parquet parsers are called live.

Callable standalone + importable (build()). CONTEXT-ONLY · never raises · never blocks render.
See research/CHINA_INTEL_POWERHOUSE.md §2.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from lib import config, site_assets
from lib.pages import write_page

log = logging.getLogger(__name__)

ASSETS = ("theme.css", "theme.js", "illus.css", "illus.js")

# ---------------------------------------------------------------------------- #
# Participation "tape" regime → plain-word label + stance + gauge position.
# Display mapping ONLY (context, never a size). The gauge is a positioning-cycle dial:
# score 0 = capitulation / fire-sale, 50 = neutral, 100 = euphoria. `tone` colours the
# arc via --up/--warn/--down (so it honours the ZH red=up swap). `stance_*` is the
# plain-word "so what do I do" the doctrine (Law 1) requires on every panel.
# ---------------------------------------------------------------------------- #
_REGIME = {
    "forced_deleveraging": dict(score=8, tone="red",
        en="Fire-sale", zh="恐慌抛售",
        stance_en="Stand aside — forced selling is still clearing.",
        stance_zh="观望——被迫抛售仍在出清。"),
    "distribution": dict(score=30, tone="red",
        en="Distribution", zh="派发出货",
        stance_en="Protect gains — smart money is selling into strength.",
        stance_zh="保护盈利——主力在拉高出货。"),
    "dormant": dict(score=44, tone="yellow",
        en="Dormant", zh="低迷休整",
        stance_en="Watch — don't chase. The tape is quiet.",
        stance_zh="观望，别追。市场清淡。"),
    "unclear": dict(score=50, tone="yellow",
        en="Mixed", zh="信号不明",
        stance_en="Watch — the signals don't agree yet.",
        stance_zh="观望——信号尚未一致。"),
    "institutional_accumulation": dict(score=62, tone="green",
        en="Accumulation", zh="机构吸筹",
        stance_en="Get ready — institutions are building quietly.",
        stance_zh="做好准备——机构正在悄悄吸筹。"),
    "retail_ignition": dict(score=74, tone="yellow",
        en="Retail ignition", zh="散户点火",
        stance_en="Watch — don't chase. Retail-led moves fade fast.",
        stance_zh="观望，别追。散户主导的行情消退很快。"),
    "margin_acceleration": dict(score=86, tone="red",
        en="Margin surge", zh="融资加速",
        stance_en="Watch — don't chase. Leverage is doing the buying.",
        stance_zh="观望，别追。买盘靠杠杆推动。"),
    "broad_mania": dict(score=95, tone="red",
        en="Euphoria", zh="全面狂热",
        stance_en="Protect gains — the crowd is all-in.",
        stance_zh="保护盈利——市场情绪全面亢奋。"),
}
_WHO = {
    "retail": ("Retail-led", "散户主导"), "institutional": ("Institution-led", "机构主导"),
    "margin": ("Leverage-led", "杠杆主导"), "state_proxy": ("State team", "国家队"),
    "offshore": ("Offshore / 南向", "南向 / 离岸"), "mixed": ("Mixed hands", "多方混杂"),
    "unclear": ("Unclear", "尚不明朗"),
}
_RISK = {
    "low": ("Calm", "平静", "green"), "normal": ("Normal", "正常", "muted"),
    "frothy": ("Frothy", "过热", "yellow"), "fire_sale": ("Fire-sale", "抛售", "red"),
}


def _site_dir() -> Path:
    sd = Path(config.load()["storage"]["site_dir"])
    return sd if sd.is_absolute() else (config.ROOT / sd)


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001 — missing/half-written upstream emit degrades to {}
        return {}


def _tape_read(part: dict) -> dict | None:
    """Map an upstream participation snapshot → the hero 'tape' read. Context only; None on miss."""
    if not part or not part.get("regime"):
        return None
    meta = _REGIME.get(part.get("regime"), _REGIME["unclear"])
    who = _WHO.get(part.get("who_controls", "unclear"), _WHO["unclear"])
    risk = _RISK.get(part.get("risk", "normal"), _RISK["normal"])
    return {
        "score": meta["score"], "tone": meta["tone"],
        "regime_en": meta["en"], "regime_zh": meta["zh"],
        "stance_en": meta["stance_en"], "stance_zh": meta["stance_zh"],
        "who_en": who[0], "who_zh": who[1],
        "risk_en": risk[0], "risk_zh": risk[1], "risk_tone": risk[2],
        "date": part.get("date"),
        "turnover_z20": part.get("turnover_z20"), "margin_chg_5d": part.get("margin_chg_5d"),
        "southbound_net": part.get("southbound_net"), "southbound_z": part.get("southbound_z"),
        "qvix": part.get("qvix"), "qvix_z": part.get("qvix_z"),
        "margin_to_mcap": part.get("margin_to_mcap"),
        "evidence": part.get("evidence") or [],
    }


def _zt_rows(zt: dict, names: dict, top_n: int = 14) -> list[dict]:
    """涨停池 limit-up pool → top names by consecutive boards then seal size."""
    rows = [{"ticker": t, "name": names.get(t, t), **(v or {})} for t, v in (zt or {}).items()]
    rows.sort(key=lambda r: (r.get("consec_boards") or 0, r.get("seal_fund_yi") or 0), reverse=True)
    return rows[:top_n]


def _zt_breadth_rows(ztb: dict, top_n: int = 12) -> list[dict]:
    """涨停 sector breadth → hottest sectors by count of limit-ups."""
    rows = [{"sector": s, **(v or {})} for s, v in (ztb or {}).items()]
    rows.sort(key=lambda r: (r.get("n_zt") or 0, r.get("consec_max") or 0), reverse=True)
    return rows[:top_n]


def _narr_rows(narr: dict, top_n: int = 12) -> list[dict]:
    """THS narrative baskets → top by 63-day momentum rank."""
    baskets = sorted((narr or {}).get("baskets") or [], key=lambda b: b.get("rank_63d", 9999))
    return baskets[:top_n]


def _tape_spark() -> str:
    """Trading-intensity trajectory (turnover z vs 20-day normal) as an ilx waterline.
    Reads the upstream tape.parquet (cheap; no recompute); '' on any miss — never raises."""
    try:
        import pandas as pd
        from lib import illus
        p = config.data_dir() / "china_participation" / "tape.parquet"
        if not p.exists():
            return ""
        s = pd.read_parquet(p)["turnover_z20"].dropna().tail(90)
        if len(s) < 8:
            return ""
        dates = [str(d)[:10] for d in s.index]
        vals = [round(float(v), 2) for v in s.values]
        return illus.illus({"dates": dates, "vals": vals}, kind="baseline", baseline=0.0,
                           accent="var(--info)", height=58, value_fmt="{:+.1f}",
                           aria_en="Trading intensity vs 20-day normal",
                           aria_zh="成交强度相对20日常态")
    except Exception:  # noqa: BLE001
        return ""


def build() -> dict | None:
    from engine import china_altdata as ad
    from engine import china_extras as ce
    from engine import china_signal_lab as lab

    bt = ad.by_ticker()
    mm = ad.mastermind(bt)
    scorecard = lab.build_china_scorecard()
    try:                                        # 券商金股 + 业绩预告 — GATED display panels ([]/{} without token)
        broker_gold = ce.broker_gold()
        guidance = ce.forecast_guidance()
        guidance_labels = {k: list(v) for k, v in ce.GUIDANCE_LABELS.items()}
    except Exception:  # noqa: BLE001
        broker_gold, guidance, guidance_labels = [], {}, {}
    try:
        from engine.china_crowding import FLAG_LABELS as _crowd_labels
        crowd_labels = {k: list(v) for k, v in _crowd_labels.items()}
    except Exception:  # noqa: BLE001
        crowd_labels = {}

    site = _site_dir()
    site.mkdir(parents=True, exist_ok=True)

    # ---- richer alt-data planes: READ upstream emits (render-budget) + cheap keyless parsers ----
    tape = _tape_read(_read_json(site / "chinastatedata" / "participation.json"))
    special = _read_json(site / "chinaspecialdata" / "special.json")
    narr_raw = _read_json(site / "factordata" / "china_narrative_radar.json")
    narr = _narr_rows(narr_raw)
    try:
        names = ad._name_map()
    except Exception:  # noqa: BLE001
        names = {}
    try:
        zt = _zt_rows(ce.zt_pool(), names)
        zt_breadth = _zt_breadth_rows(ce.zt_sector_breadth())
    except Exception:  # noqa: BLE001
        zt, zt_breadth = [], []

    env = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=False)
    from engine import i18n
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    html = env.get_template("china_altdata.html.j2").render(
        ad=bt, lab=scorecard, mm=mm, crowd_labels=crowd_labels, broker_gold=broker_gold,
        guidance=guidance, guidance_labels=guidance_labels,
        tape=tape, tape_spark=_tape_spark(), special=special, narr=narr,
        narr_asof=(narr_raw or {}).get("as_of"), zt=zt, zt_breadth=zt_breadth)
    write_page(site / "china_altdata.html", html)
    for a in ASSETS:
        src = config.ROOT / "templates" / a
        if src.exists() and not (site / a).exists():
            site_assets.copy_asset(a, src, site)
    log.info("wrote %s/china_altdata.html (%d KB)", site, len(html) // 1024)

    out = site / "chinaaltdata"
    out.mkdir(parents=True, exist_ok=True)
    (out / "by_ticker.json").write_text(
        json.dumps(bt or {}, ensure_ascii=False, separators=(",", ":"), default=str))
    (out / "mastermind.json").write_text(
        json.dumps(mm, ensure_ascii=False, separators=(",", ":"), default=str))
    (out / "feed.json").write_text(
        json.dumps(scorecard, ensure_ascii=False, separators=(",", ":"), default=str))
    log.info("wrote %s/chinaaltdata/{by_ticker,mastermind,feed}.json", site)
    return bt


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
