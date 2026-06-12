"""Daily brief — a plain-English narrative, not a data dump.

Replaces the weekly report (the weekly's qualitative content — rotation
verdict, positioning extremes — is folded in here and refreshed daily).
Reads only stored outputs; compares against yesterday's saved snapshot to
write the "what changed" section; archives to reports/ and publishes to
site/brief.html.

Usage: python -m scripts.daily_brief
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("brief")

PREV_PATH_NAME = "brief_prev_state.json"


def _load_latest() -> dict:
    with open(config.data_dir() / "regime" / "latest.json") as fh:
        return json.load(fh)


def _load_prev() -> dict | None:
    p = config.data_dir() / "regime" / PREV_PATH_NAME
    if not p.exists():
        return None
    with open(p) as fh:
        return json.load(fh)


def _save_state(latest: dict) -> None:
    pb = latest.get("playbook") or {}
    state = {
        "date": latest["date"],
        "quad": latest["quad"],
        "quad_name": latest["quad_name"],
        "growth_score": latest["growth_score"],
        "inflation_score": latest["inflation_score"],
        "confidence": latest["confidence"],
        "transition_state": latest["transition_state"],
        "posture": (pb.get("dial") or {}).get("posture"),
        "stages": {r["ticker"]: {"stage": r["stage"], "heat": r["heat"],
                                 "progress": r.get("trigger_progress_pct")}
                   for r in pb.get("stages", [])},
    }
    with open(config.data_dir() / "regime" / PREV_PATH_NAME, "w") as fh:
        json.dump(state, fh, indent=1)


def what_changed(latest: dict, prev: dict | None) -> list[str]:
    if prev is None:
        return ["First brief — day-over-day change tracking starts tomorrow."]
    if prev.get("date") == latest["date"]:
        prev = None  # same-day rerun; nothing to diff against
        return ["No new trading day since the last brief."]
    out: list[str] = []
    pb = latest.get("playbook") or {}

    if prev["quad"] != latest["quad"]:
        out.append(f"**The regime changed**: {prev['quad_name']} → "
                   f"**{latest['quad_name']}**. Re-read the whole playbook today.")
    if prev["transition_state"] != latest["transition_state"]:
        out.append(f"The transition radar moved **{prev['transition_state']} → "
                   f"{latest['transition_state']}**.")
    g0, g1 = prev["growth_score"], latest["growth_score"]
    if abs(g1 - g0) >= 0.1:
        out.append(f"The growth dial {'firmed' if g1 > g0 else 'softened'} "
                   f"({g0:+.2f} → {g1:+.2f}).")
    i0, i1 = prev["inflation_score"], latest["inflation_score"]
    if abs(i1 - i0) >= 0.1:
        out.append(f"Inflation pressure {'rose' if i1 > i0 else 'eased'} "
                   f"({i0:+.2f} → {i1:+.2f}).")
    if prev.get("posture") and (pb.get("dial") or {}).get("posture") != prev["posture"]:
        out.append(f"**Posture changed**: {prev['posture']} → "
                   f"{(pb.get('dial') or {}).get('posture')}.")

    prev_stages = prev.get("stages", {})
    for r in pb.get("stages", []):
        t, name = r["ticker"], r["name"]
        ps = prev_stages.get(t, {})
        if ps.get("stage") and ps["stage"] != r["stage"]:
            arrow = {"improving": "🟦", "leading": "🟩",
                     "weakening": "🟨", "lagging": "🟥"}.get(r["stage"], "")
            out.append(f"{arrow} **{name}** rotated {ps['stage']} → **{r['stage']}**.")
        elif ps.get("heat") is not None and abs(r["heat"] - ps["heat"]) >= 8:
            d = "heated up" if r["heat"] > ps["heat"] else "cooled"
            out.append(f"{name} {d} ({ps['heat']} → {r['heat']} heat).")
        pg0, pg1 = ps.get("progress"), r.get("trigger_progress_pct")
        if pg0 is not None and pg1 is not None and pg1 - pg0 >= 10:
            out.append(f"{name} moved closer to its buy trigger "
                       f"({pg0:.0f}% → {pg1:.0f}% of the way there).")

    for a in latest.get("alerts", []):
        out.append(f"🔔 Alert fired: {a['message']}")
    if not out:
        out.append("A quiet day — no regime, posture, rotation-stage or alert changes.")
    return out


def crowd_extremes() -> list[str]:
    """Positioning percentiles in plain speech, extremes only."""
    from scripts.build_site import positioning_rows
    out = []
    try:
        from engine.inputs import build_features
        rows = positioning_rows(build_features())
    except Exception as e:  # noqa: BLE001
        log.warning("positioning unavailable: %s", e)
        return []
    for r in rows:
        try:
            p = float(r["pctile"])
        except (TypeError, ValueError):
            continue
        if p >= 90:
            out.append(f"**{r['name']}** is in its {p:.0f}th percentile — among the most "
                       f"crowded readings on record. Crowded trades reverse hard; don't "
                       f"join late.")
        elif p <= 10:
            out.append(f"**{r['name']}** is in its {p:.0f}th percentile — washed out. "
                       f"Everyone who wanted to sell likely has; squeezes start here.")
    return out


def build_markdown(latest: dict, prev: dict | None) -> str:
    pb = latest.get("playbook") or {}
    dial = pb.get("dial") or {}
    prog = pb.get("progress") or {}

    md = [f"# Daily brief — {latest['date']}", ""]

    # 1. today in one paragraph
    para = (f"The market regime is **{latest['quad_name']}** "
            f"({pb.get('headline', '').split('.')[0].split('—')[-1].strip()}), "
            f"with {latest['confidence']:.0%} of signals agreeing and the transition "
            f"radar reading **{latest['transition_state']}**. ")
    if prog:
        para += (f"This regime is **{prog['phase'].upper()}** in its typical lifespan "
                 f"({prog['age_days']} days in, median is {prog['median_days']}). ")
    para += (f"Fed liquidity is {latest['liquidity_overlay']}. "
             f"Bottom line: **{dial.get('posture', 'NEUTRAL')}** — "
             f"{dial.get('meaning', '')}")
    md += [para, ""]

    # 2. what changed
    md += ["## What changed since the last brief", ""]
    md += [f"- {line}" for line in what_changed(latest, prev)]
    md += [""]

    # 3. what to do
    md += ["## What to do with it", ""]
    for sign, r in dial.get("reasons", []):
        icon = {"+": "✅", "-": "⚠️", "i": "ℹ️"}.get(sign, "•")
        md.append(f"- {icon} {r}")
    leaders = pb.get("leaders", [])
    if leaders:
        md.append("- 📈 Confirmed leadership: "
                  + ", ".join(f"**{x['name']}** ({x['ticker']})" for x in leaders)
                  + " — the only places where strength is established and not stretched.")
    else:
        md.append("- 📈 No sector currently offers confirmed, non-stretched leadership — "
                  "stay close to the index rather than reaching.")
    avoid = pb.get("avoid", [])
    if avoid:
        md.append("- 🚫 Hands off: "
                  + "; ".join(f"**{x['name']}** ({x['call'].lower()})" for x in avoid))
    md += [""]

    # 4. what's brewing
    md += ["## What's brewing", ""]
    if pb.get("next_list"):
        n = pb["next_list"][0]
        md.append(f"- History says {latest['quad_name']} most often hands off to "
                  f"**{n['name']}** ({n['prob_pct']}% of past transitions"
                  + (f"; full odds: " + ", ".join(f"{x['name']} {x['prob_pct']}%"
                                                  for x in pb["next_list"]) + ")."))
    for x in pb.get("watchlist", []):
        md.append(f"- 👀 **{x['name']}** ({x['ticker']}): {x['why']}")
    for t in pb.get("triggers", []):
        md.append(f"- 🔍 {t}")
    md += [""]

    # 5. crowd extremes
    extremes = crowd_extremes()
    if extremes:
        md += ["## Crowd extremes worth knowing", ""]
        md += [f"- {e}" for e in extremes]
        md += [""]

    md += ["---",
           "*Generated automatically from the day's data. Heat, odds and percentile "
           "figures are measured base rates from 2007-2026 history, not predictions. "
           "Details and tooltips: [the dashboard](index.html).*"]
    return "\n".join(md)


def render_html(md_text: str, title: str) -> str:
    import markdown
    body = markdown.markdown(md_text, extensions=["tables"])
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>body{{background:#0f1115;color:#d7dce3;font:15px/1.65 -apple-system,'Segoe UI',sans-serif;
max-width:760px;margin:0 auto;padding:24px}}h1,h2{{color:#fff}}h2{{margin-top:28px}}
a{{color:#7aa7e0}}li{{margin:6px 0}}hr{{border:none;border-top:1px solid #2a2f3a;margin:24px 0}}
em{{color:#8b93a1}}</style>
</head><body><p><a href="index.html">&larr; dashboard</a></p>{body}</body></html>"""


def main() -> int:
    latest = _load_latest()
    prev = _load_prev()
    md = build_markdown(latest, prev)

    rdir = config.ROOT / config.load()["storage"]["reports_dir"]
    rdir.mkdir(exist_ok=True)
    (rdir / f"brief-{latest['date']}.md").write_text(md)
    site = config.ROOT / config.load()["storage"]["site_dir"]
    site.mkdir(exist_ok=True)
    (site / "brief.html").write_text(render_html(md, f"Daily brief {latest['date']}"))
    _save_state(latest)
    log.info("wrote reports/brief-%s.md and site/brief.html", latest["date"])
    print(md[:1200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
