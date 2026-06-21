"""Special Situations desk — DISPLAY-ONLY page builder (site/special_situations.html).

Renders the event-driven special-situations desk from engine.special_situations
(SCORED=False). The daily step: refresh the EDGAR event store (collector), classify
the ambiguous filings from their text (text lane), then render the page grouped by
category + a landing-hub snapshot. Reuses the shared bilingual / theme conventions.

Run: python -m scripts.build_special_situations
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from engine import special_situations as sse
from lib import config
from scripts.build_vector import C

log = logging.getLogger(__name__)

# display order (lead with the highest-signal active categories)
CAT_ORDER = [
    "Activist Campaigns", "Acquisitions", "Going-Private", "Tender Offers",
    "Divestitures", "Spin-Offs", "New SpinCos", "Strategic Reviews",
    "Capital Returns", "Issuer Tenders", "Rights Offerings", "Restructuring",
    "Deal Terminations", "Liquidations", "Delistings", "SPACs",
    "Management Changes", "Other",
]
_GREEN = "#1FA971"
CAT_COLOR = {
    "Activist Campaigns": C["indigo"], "Acquisitions": C["blue"], "Going-Private": C["indigo"],
    "Tender Offers": C["blue"], "Divestitures": _GREEN, "Spin-Offs": _GREEN, "New SpinCos": _GREEN,
    "Strategic Reviews": C["amber"], "Capital Returns": _GREEN, "Issuer Tenders": _GREEN,
    "Rights Offerings": C["amber"], "Restructuring": C["amber"], "Deal Terminations": C["red"],
    "Liquidations": C["red"], "Delistings": C["red"], "SPACs": C["muted"],
    "Management Changes": C["muted"], "Other": C["muted"],
}
CAT_ZH = {
    "Activist Campaigns": "维权行动", "Acquisitions": "收购", "Going-Private": "私有化",
    "Tender Offers": "要约收购", "Divestitures": "剥离", "Spin-Offs": "分拆",
    "New SpinCos": "新分拆公司", "Strategic Reviews": "战略评估", "Capital Returns": "资本回报",
    "Issuer Tenders": "公司回购要约", "Rights Offerings": "配股", "Restructuring": "重组",
    "Deal Terminations": "交易终止", "Liquidations": "清算", "Delistings": "退市",
    "SPACs": "SPAC", "Management Changes": "管理层变动", "Other": "其他",
}
STAGE_ZH = {
    "initiated": "启动", "escalation": "升级", "live": "进行中", "announced": "已宣布",
    "vote-scheduled": "已定投票", "registered": "已登记", "terminated": "已终止",
    "filed": "已申报", "notice": "通知", "completed": "已完成", "change": "变动",
    "proxy-fight": "代理权之争", "target-response": "标的回应",
    "closed": "已成交", "terminated": "已终止", "de-SPAC": "去SPAC",
}


def _txt(v, dash: str = "—") -> str:
    """Clean a value for display: None / NaN / 'nan' -> dash."""
    if v is None:
        return dash
    if isinstance(v, float) and v != v:
        return dash
    s = str(v).strip()
    return dash if (not s or s.lower() == "nan") else s


def _arb_str(a: dict | None) -> str:
    """Compact merger-arb line: 'spread +8.3% · +24%/yr · ~120d · break -31%'."""
    if not a:
        return ""
    parts = [f"spread {a['gross_spread_pct']:+.1f}%"]
    if a.get("annualized_pct") is not None:
        parts.append(f"{a['annualized_pct']:+.0f}%/yr")
    if a.get("days_to_close"):
        parts.append(f"~{a['days_to_close']}d")
    if a.get("downside_on_break_pct") is not None:
        parts.append(f"break {a['downside_on_break_pct']:+.0f}%")
    return " · ".join(parts)


def _usd_m(mc) -> str:
    if mc is None:
        return "—"
    try:
        mc = float(mc)
    except (TypeError, ValueError):
        return "—"
    if mc != mc:  # NaN
        return "—"
    return f"${mc / 1000:.1f}B" if mc >= 1000 else f"${mc:.0f}M"


def build(refresh: bool = True) -> str:
    if refresh:
        from collectors import special_situations as col
        from collectors import special_news as colnews
        try:
            col.fetch_events()        # sweep new daily-index dates (bounded by watermark)
            col.enrich_text()         # cheap keyword pre-filter on deferred filings (cached)
            col.enrich_filers()       # P3.2 reporting-person from 13D cover pages (deterministic, no key)
            col.enrich_classify()     # P1.1 LLM-verify deferred filings: category/role/terms (gated; no-op without key)
            col.enrich_summaries()    # 88-word summary (+ deal terms, activist filer) for structured situations (gated)
            colnews.fetch_news_situations()  # P2.1 newswire form-absent categories (gated; no-op when off)
        except Exception as e:  # noqa: BLE001 — desk degrades to last-known on a fetch outage
            log.warning("special_situations refresh failed (rendering last-known): %s", e)

    snap = sse.desk_payload()

    groups_map: dict[str, list] = {}
    for s in snap.get("situations", []):
        groups_map.setdefault(s["category"], []).append(s)
    # CAT_ORDER first, then any leftover categories (never silently drop a category)
    ordered_cats = CAT_ORDER + [c for c in groups_map if c not in CAT_ORDER]
    groups = []
    for cat in ordered_cats:
        rows_src = groups_map.get(cat)
        if not rows_src:
            continue
        rows = [{
            "ticker": _txt(s.get("ticker")),
            "company": _txt(s.get("company")),
            "stage": s.get("stage") or "", "stage_zh": STAGE_ZH.get(s.get("stage"), s.get("stage") or ""),
            "form": s.get("form_type") or "", "date": s.get("date_filed") or "",
            "cross_border": bool(s.get("cross_border")), "mc": _usd_m(s.get("mc_musd")),
            "url": s.get("edgar_url") or s.get("source_url"),
            "summary": _txt(s.get("summary"), dash=""), "live": bool(s.get("live")),
            "low_conf": s.get("confidence") == "low", "arb": _arb_str(s.get("arb")),
            "n_amend": int(s.get("n_amendments") or 0), "terminal": s.get("terminal"),
        } for s in rows_src]
        groups.append({"cat": cat, "cat_zh": CAT_ZH.get(cat, cat),
                       "color": CAT_COLOR.get(cat, C["muted"]), "n": len(rows), "rows": rows})

    vm = {
        "groups": groups, "counts": snap.get("counts", {}), "coverage": snap.get("coverage", {}),
        "built": snap.get("built"), "total": len(snap.get("situations", [])), "n_cats": len(groups),
    }

    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        env.globals.update(td=lambda en: en, tr=lambda en: en)
    html = env.get_template("special_situations.html.j2").render(**vm, C=C)
    out = config.ROOT / "site" / "special_situations.html"
    out.write_text(html)

    # landing-hub snapshot
    cov = snap.get("coverage", {})
    counts = snap.get("counts", {})
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:3]
    snap_out = {
        "total": vm["total"], "n_categories": vm["n_cats"],
        "cross_border": cov.get("cross_border", 0),
        "top_categories": [{"category": c, "n": n} for c, n in top],
        "floor_musd": cov.get("floor_musd"),
        "built": snap.get("built"),
    }
    snap_dir = config.data_dir() / "regime"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "special_situations_latest.json").write_text(json.dumps(snap_out, indent=2))

    # Mastermind / cross-surface emit: per-ticker context (CONTEXT-only, by_ticker).
    # Consumed by the trading brain (via vendor/macro) and board chips.
    emit = sse.mastermind_emit()
    emit_dir = config.ROOT / "site" / "allocationdata"
    emit_dir.mkdir(parents=True, exist_ok=True)
    (emit_dir / "special_situations.json").write_text(json.dumps(emit))
    return str(out)


def main() -> int:
    # production entry (daily.yml): sweep new filings + text-classify + render.
    # For a quick dev re-render from the existing store, call build(refresh=False).
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out = build(refresh=True)
    print(f"[built] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
