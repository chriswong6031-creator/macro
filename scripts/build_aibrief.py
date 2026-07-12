"""Build the consolidated AI Daily Brief page -> site/aibrief.html.

ONE static page that surfaces the three EXISTING AI briefs written by
engine/master_brain.py (site/master_brief.json, site/china_brief.json,
site/btc_brief.json — one shared schema). Three toggle tabs (Macro / China & HK /
Bitcoin) flip three .ai-brief[data-brief-src] panels that templates/aibrief.js
fetches + renders client-side, bilingually. This builder does LIGHT fail-open reads
of committed deterministic artifacts (market_plane, world_state, liquidity_plumbing,
release_forecast, track_record, theses) to power four new panels embedded at build
time. Every read is wrapped in try/except — any failure degrades to an absent/honest
marker and never breaks the build. Returns 0 on ANY error.

Usage: python -m scripts.build_aibrief   (run anytime; e.g. after master_brain)
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, site_assets  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_aibrief")

# Only the assets the shared nav + the briefs need: theme (vars + l-en/l-zh toggle
# CSS + nav styling), theme.js (wires theme/lang/search), aibrief.js (renders the
# three panels). The lens JSONs are produced by engine.master_brain, not here.
ASSETS = ("theme.css", "theme.js", "aibrief.js")

# Plain-word translations for liquidity states
_LIQUIDITY_PLAIN = {
    "stress_liquidity_expansion": (
        "Money is technically expanding but conditions are stressed — treat cautiously",
        "流动性技术上扩张但压力较大，谨慎对待",
    ),
    "clean_liquidity_expansion": (
        "Liquidity is expanding — a supportive backdrop",
        "流动性扩张，总体利好",
    ),
    "liquidity_contraction": (
        "Liquidity is tightening — a headwind for risk assets",
        "流动性收紧，对风险资产构成阻力",
    ),
    "neutral": (
        "Liquidity is roughly neutral",
        "流动性大体中性",
    ),
}

# Plain-word translations for cortex status
_CORTEX_PLAIN = {
    "degraded": (
        "Rate-limited overnight — ran on dashboards alone",
        "隔夜遭速率限制，仅依靠看板运行",
    ),
    "ok": (
        "Ran successfully",
        "已成功运行",
    ),
}


def _load_json_safe(path: Path) -> dict | list | None:
    """Load JSON from path; return None on any error."""
    try:
        return json.loads(path.read_bytes())
    except Exception as exc:  # noqa: BLE001
        log.debug("aibrief: could not read %s (%s)", path, exc)
        return None


def _gather_context_strip(data_dir: Path) -> dict:
    """Panel A: light fail-open reads for the context strip.

    Returns a dict with keys:
      regime_label_en, regime_label_zh, regime_asof
      contradiction_line_en, contradiction_line_zh
      contradiction_tip_en, contradiction_tip_zh
      liquidity_en, liquidity_zh
      cortex_en, cortex_zh, cortex_status
      strip_asof (earliest as_of among artifacts read)
      absent (bool) — True if ALL three reads failed
    """
    out: dict = {
        "absent": False,
        "regime_label_en": None,
        "regime_label_zh": None,
        "regime_asof": None,
        "contradiction_line_en": None,
        "contradiction_line_zh": None,
        "contradiction_tip_en": None,
        "contradiction_tip_zh": None,
        "liquidity_en": None,
        "liquidity_zh": None,
        "cortex_en": None,
        "cortex_zh": None,
        "cortex_status": None,
        "strip_asof": None,
    }

    ok_count = 0

    # 1. market_plane.json — regime verdict + cortex status
    mp = _load_json_safe(data_dir / "neuralweb" / "market_plane.json")
    if mp:
        verdict = mp.get("verdict") or {}
        out["regime_label_en"] = verdict.get("label_en") or "—"
        out["regime_label_zh"] = verdict.get("label_zh") or "—"
        out["regime_asof"] = mp.get("asof") or mp.get("produced_at", "")[:10]
        cortex = mp.get("cortex") or {}
        cstatus = cortex.get("status", "degraded")
        out["cortex_status"] = cstatus
        cpair = _CORTEX_PLAIN.get(cstatus, _CORTEX_PLAIN["degraded"])
        out["cortex_en"] = cpair[0]
        out["cortex_zh"] = cpair[1]
        ok_count += 1
        if out["strip_asof"] is None:
            out["strip_asof"] = out["regime_asof"]

    # 2. world_state.json — contradictions block for salient pair note
    ws = _load_json_safe(data_dir / "neuralweb" / "world_state.json")
    if ws:
        contra = ws.get("contradictions") or {}
        n = contra.get("n", 0)
        note = contra.get("note", "")
        by_sev = contra.get("by_severity") or {}
        n_tension = by_sev.get("tension", 0)

        # Translate the technical note into plain words for the glance tier
        if n > 0:
            if n_tension > 0:
                out["contradiction_line_en"] = (
                    "One tension worth knowing: bonds and stocks are telling "
                    "different stories."
                )
                out["contradiction_line_zh"] = (
                    "值得关注的一处矛盾：债券与股票传递出不同信号。"
                )
            else:
                out["contradiction_line_en"] = (
                    "The dashboards flag some mixed signals — nothing critical."
                )
                out["contradiction_line_zh"] = "各看板有些混合信号，尚不严重。"
        else:
            out["contradiction_line_en"] = "The main signals are pointing the same way."
            out["contradiction_line_zh"] = "主要信号方向一致。"

        # Full technical note goes in the hover receipt
        sev_summary = ", ".join(f"{k}: {v}" for k, v in by_sev.items()) if by_sev else ""
        out["contradiction_tip_en"] = (
            f"Contradiction count: {n}. By severity: {sev_summary}. "
            f"Technical note: {note[:200]}"
        ).strip()
        out["contradiction_tip_zh"] = out["contradiction_tip_en"]  # no ZH translation of raw note
        ok_count += 1

    # 3. liquidity_plumbing.json — headline.state in plain words
    lp = _load_json_safe(data_dir / "neuralweb" / "liquidity_plumbing.json")
    if lp:
        headline = lp.get("headline") or {}
        state = headline.get("state", "neutral")
        pair = _LIQUIDITY_PLAIN.get(state, _LIQUIDITY_PLAIN["neutral"])
        out["liquidity_en"] = pair[0]
        out["liquidity_zh"] = pair[1]
        lp_asof = lp.get("asof", "")
        if lp_asof and (not out["strip_asof"] or lp_asof < out["strip_asof"]):
            out["strip_asof"] = lp_asof[:10]
        ok_count += 1

    if ok_count == 0:
        out["absent"] = True

    return out


def _gather_forward_panel(data_dir: Path, today: date | None = None) -> dict:
    """Panel B: What's ahead — deterministic forward calendar.

    Returns a dict with keys:
      events: list of {date, label_en, label_zh, tip_en, tip_zh}
      rebal_note_en, rebal_note_zh
      absent (bool)
    """
    today = today or date.today()
    out: dict = {"absent": False, "events": [], "rebal_note_en": None, "rebal_note_zh": None}

    # 1. event_calendar — high-impact strip (bounded network IO, fail-open)
    try:
        from engine.event_calendar import high_impact_strip  # local import
        evs = high_impact_strip(today=today, horizon_days=14)
        for ev in evs:
            out["events"].append({
                "date": ev["date"],
                "label_en": ev.get("label", ev["type"]),
                "label_zh": ev.get("label_zh", ev["type"]),
                "tip_en": f"Time: {ev.get('time_et','?')} ET · Source: {ev.get('source','computed')}",
                "tip_zh": f"时间：{ev.get('time_et','?')} 东部时间",
            })
    except Exception as exc:  # noqa: BLE001
        log.debug("aibrief: event_calendar failed (%s)", exc)

    # 2. rebalance_calendar — quarter-end distance
    try:
        from engine.rebalance_calendar import tag as rbtag  # local import
        rb = rbtag(today)
        td = rb.get("td_to_quarter_end", 999)
        if abs(td) <= 3:
            if td == 0:
                out["rebal_note_en"] = "Today is quarter-end — index rebalancing in effect."
                out["rebal_note_zh"] = "今日为季末，指数再平衡生效。"
            elif td > 0:
                out["rebal_note_en"] = (
                    f"Quarter-end is {td} trading day{'s' if td != 1 else ''} away "
                    f"— watch for rebalancing flows."
                )
                out["rebal_note_zh"] = f"距季末还有 {td} 个交易日，关注再平衡资金流。"
            else:
                out["rebal_note_en"] = (
                    f"Quarter-end passed {abs(td)} trading day{'s' if abs(td) != 1 else ''} ago."
                )
                out["rebal_note_zh"] = f"季末已过 {abs(td)} 个交易日。"
    except Exception as exc:  # noqa: BLE001
        log.debug("aibrief: rebalance_calendar failed (%s)", exc)

    # 3. release_forecast/latest.json — top-3 upcoming, no Claims entries
    rf = _load_json_safe(data_dir / "release_forecast" / "latest.json")
    if rf:
        scoreboard_n = 0
        try:
            sb = _load_json_safe(data_dir / "release_forecast" / "scoreboard.json") or {}
            # n_graded across all releases
            for rel_data in (sb.get("by_release") or {}).values():
                scoreboard_n += rel_data.get("n_graded", 0)
        except Exception:  # noqa: BLE001
            pass

        upcoming = rf.get("upcoming") or []
        seen_dates: set[str] = set()  # deduplicate (same date may appear twice for cpi headline/core)
        added = 0
        for entry in upcoming:
            if added >= 3:
                break
            release = entry.get("release", "")
            # Skip Claims entries (killed model — ADB-R4)
            if "claims" in release.lower():
                continue
            rel_date = entry.get("release_date", entry.get("date", ""))
            if not rel_date:
                continue
            # Deduplicate by (release, date) — different release_types on same day count once
            dedup_key = f"{release}:{rel_date}"
            if dedup_key in seen_dates:
                continue
            seen_dates.add(dedup_key)

            label_en = release.upper()
            label_zh = release.upper()
            days_to = entry.get("days_to", "?")

            # Surprise skew — for hover receipt only
            skew = entry.get("surprise_skew") or {}
            skew_tag = skew.get("tag", "")  # 'cooler' / 'inline' / 'hotter'
            _SKEW_PLAIN = {
                "cooler": ("model leans cool", "模型偏向低于预期"),
                "inline": ("model leans in-line", "模型偏向符合预期"),
                "hotter": ("model leans hot", "模型偏向高于预期"),
            }
            skew_plain_en, skew_plain_zh = _SKEW_PLAIN.get(skew_tag, ("", ""))

            # Market-implied
            bench = entry.get("benchmark_set") or {}
            mkt = bench.get("market_implied") or {}
            mkt_implied = mkt.get("implied", "")

            no_record = "No accuracy record yet" if scoreboard_n == 0 else f"{scoreboard_n} graded"
            tip_en_parts = [f"In {days_to} day(s). {no_record}."]
            if skew_plain_en:
                tip_en_parts.append(skew_plain_en + ".")
            if mkt_implied:
                tip_en_parts.append(f"Market implied: {mkt_implied}.")
            tip_en = " ".join(tip_en_parts)
            tip_zh_parts = [f"距今 {days_to} 天。{no_record}。"]
            if skew_plain_zh:
                tip_zh_parts.append(skew_plain_zh + "。")
            tip_zh = " ".join(tip_zh_parts)

            out["events"].append({
                "date": rel_date,
                "label_en": label_en,
                "label_zh": label_zh,
                "tip_en": tip_en,
                "tip_zh": tip_zh,
                "is_forecast": True,
            })
            added += 1

    if not out["events"] and out["rebal_note_en"] is None:
        out["absent"] = True

    # Sort all events by date
    out["events"].sort(key=lambda e: e.get("date", ""))

    return out


def _gather_record_panel(data_dir: Path) -> dict:
    """Panel C: The brief's own record — track_record.json + open theses.

    n-floor LAW (ADB-R12c): if scored_total < 20, never render a numeric hit-rate
    on the visible tier; render the artifact's calibration_note instead.

    Returns a dict with keys:
      scored_total, calibration_note_en, calibration_note_zh
      show_rate (bool)  — False when n < 20
      open_leans: list of {subject, stance_en, stance_zh, falsifier_en}
      absent (bool)
    """
    out: dict = {
        "absent": False,
        "scored_total": 0,
        "calibration_note_en": None,
        "calibration_note_zh": None,
        "show_rate": False,
        "open_leans": [],
    }

    # track_record.json
    tr = _load_json_safe(data_dir / "master_brain" / "track_record.json")
    if tr is None:
        out["absent"] = True
        return out

    scored = tr.get("scored_total", 0)
    out["scored_total"] = scored
    out["show_rate"] = scored >= 20
    out["calibration_note_en"] = tr.get("calibration_note", "")
    out["calibration_note_zh"] = tr.get("calibration_note_zh", tr.get("calibration_note", ""))

    # open leans from theses.jsonl — last few rows
    _LEAN_PLAIN = {
        "overweight": ("leaning toward", "倾向看好"),
        "underweight": ("leaning away from", "倾向回避"),
        "avoid": ("leaning away from", "倾向回避"),
        "neutral": ("neutral on", "中性看待"),
        "buy": ("leaning toward", "倾向看好"),
        "sell": ("leaning away from", "倾向回避"),
    }
    try:
        theses_path = data_dir / "master_brain" / "theses.jsonl"
        if theses_path.exists():
            rows = theses_path.read_text(encoding="utf-8").strip().splitlines()
            # Take last 6 rows, filter to open
            for line in rows[-6:]:
                try:
                    t = json.loads(line)
                except Exception:
                    continue
                if t.get("status") not in ("open", None):
                    continue
                subject = t.get("subject", "")
                lean = t.get("lean", "neutral").lower()
                horizon_d = t.get("horizon_d", "")
                lean_en, lean_zh = _LEAN_PLAIN.get(lean, ("neutral on", "中性看待"))
                horizon_str_en = f" over the next {horizon_d} days" if horizon_d else ""
                horizon_str_zh = f"，未来 {horizon_d} 天" if horizon_d else ""
                stance_en = f"{lean_en.capitalize()} {subject}{horizon_str_en}."
                stance_zh = f"{lean_zh} {subject}{horizon_str_zh}。"
                falsifier = (t.get("falsifier") or {}).get("text", "")
                check_by = t.get("check_by", "")
                out["open_leans"].append({
                    "subject": subject,
                    "stance_en": stance_en,
                    "stance_zh": stance_zh,
                    "falsifier_en": falsifier,
                    "check_by": check_by,
                })
    except Exception as exc:  # noqa: BLE001
        log.debug("aibrief: theses read failed (%s)", exc)

    return out


def _gather_panels(data_dir: Path) -> dict:
    """Gather all server-side panel data; fully fail-open."""
    try:
        ctx_strip = _gather_context_strip(data_dir)
    except Exception as exc:  # noqa: BLE001
        log.warning("aibrief: context strip gather failed (%s)", exc)
        ctx_strip = {"absent": True}

    try:
        fwd_panel = _gather_forward_panel(data_dir)
    except Exception as exc:  # noqa: BLE001
        log.warning("aibrief: forward panel gather failed (%s)", exc)
        fwd_panel = {"absent": True, "events": [], "rebal_note_en": None, "rebal_note_zh": None}

    try:
        record_panel = _gather_record_panel(data_dir)
    except Exception as exc:  # noqa: BLE001
        log.warning("aibrief: record panel gather failed (%s)", exc)
        record_panel = {"absent": True}

    return {
        "ctx_strip": ctx_strip,
        "fwd_panel": fwd_panel,
        "record_panel": record_panel,
    }


def main() -> int:
    try:
        cfg = config.load()
        site = Path(cfg["storage"]["site_dir"])
        site.mkdir(parents=True, exist_ok=True)

        data_dir = Path(config.ROOT) / "data"

        env = Environment(loader=FileSystemLoader(
            str(Path(__file__).resolve().parent.parent / "templates")), autoescape=False)
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)

        as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        panels = _gather_panels(data_dir)
        html = env.get_template("aibrief.html.j2").render(as_of=as_of, **panels)
        write_page(site / "aibrief.html", html)

        for a in ASSETS:
            src = Path(config.ROOT) / "templates" / a
            if src.exists():
                site_assets.copy_asset(a, src, site)
        log.info("wrote %s/aibrief.html (%d KB)", site, len(html) // 1024)
    except Exception as e:  # noqa: BLE001 — additive, must never break the site build
        log.error("AI brief page build failed (%s); skipping", e)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
