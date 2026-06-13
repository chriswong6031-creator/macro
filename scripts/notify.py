"""Daily snapshot to Telegram and/or Discord.

Reads the engine's latest.json + run_status.json — it never recomputes
anything, so a notify failure can't affect data, and the engine can succeed
even if this script dies.

Secrets via env: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID, DISCORD_WEBHOOK_URL.
Absent secrets -> channel skipped with a log line, exit 0 (the dashboard is
the fallback surface). `--dry-run` prints the message instead of sending.

Usage: python -m scripts.notify [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("notify")

QUAD_EMOJI = {"Q1": "🟢", "Q2": "🟡", "Q3": "🔴", "Q4": "🔵"}
STATE_EMOJI = {"STABLE": "⚪", "WEAKENING": "🟠", "TRANSITIONING": "🔶",
               "NEW_REGIME": "🚨"}
SEV_EMOJI = {"act": "🚨", "warn": "⚠️", "info": "ℹ️"}


def load_latest() -> dict | None:
    p = config.data_dir() / "regime" / "latest.json"
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def health_line() -> str:
    status = store.read_status().get("sources", {})
    if not status:
        return "health: unknown"
    ok = [k for k, v in status.items() if v["status"] == "ok"]
    bad = {k: v["status"] for k, v in status.items() if v["status"] != "ok"}
    line = f"health: {len(ok)}/{len(status)} ok"
    if bad:
        line += " (" + ", ".join(f"{k}:{s}" for k, s in bad.items()) + ")"
    return line


def build_message(latest: dict, html: bool = True) -> str:
    b, e = ("<b>", "</b>") if html else ("**", "**")
    quad = latest["quad"]
    label = latest["quad_name"]
    if "/Recession" in latest.get("label", ""):
        label += " ⚠ RECESSION SIGNAL"
    elif "/Inflation-shock" in latest.get("label", ""):
        label += " ⚠ INFLATION SHOCK"
    lines = [
        f"{QUAD_EMOJI.get(quad, '')} {b}{label}{e} ({latest['date']})",
        f"confidence {latest['confidence']:.0%} | liquidity {latest['liquidity_overlay']} "
        f"| cycle {latest['cycle_tag']} | "
        f"{STATE_EMOJI.get(latest['transition_state'], '')} {latest['transition_state']}",
        f"G {latest['growth_score']:+.2f} / I {latest['inflation_score']:+.2f}",
    ]
    pb = latest.get("playbook") or {}
    if pb.get("dial"):
        lines.append(f"{b}posture: {pb['dial']['posture']}{e} — {pb['dial']['meaning']}")
    if pb.get("leaders"):
        lines.append(f"{b}confirmed leaders{e}: "
                     + ", ".join(x["ticker"] for x in pb["leaders"]))
    if pb.get("avoid"):
        lines.append("avoid: " + ", ".join(f"{x['ticker']} ({x['call'].lower()})"
                                           for x in pb["avoid"]))
    rs = latest.get("sector_rs", [])
    if rs:
        top = ", ".join(f"{r['ticker']} {r['mom_20d_pct']:+.1f}%" for r in rs[:5])
        bot = ", ".join(f"{r['ticker']} {r['mom_20d_pct']:+.1f}%" for r in rs[-5:])
        lines += [f"{b}top RS{e}: {top}", f"{b}bottom{e}: {bot}"]
    pc = latest.get("preference_check", {})
    if pc.get("disagreement_flag"):
        lines.append("⚠️ tape disagrees with framework-preferred sectors")
    flip = latest.get("flip_condition", {})
    if flip.get("component"):
        lines.append(f"fragile: {flip['axis']} axis via {flip['component']} "
                     f"(z {flip['z']} vs ±{flip['threshold']})")
    alerts = latest.get("alerts", [])
    if alerts:
        from engine.alerts import alert_view
        site_url = (config.load()["notify"].get("site_url") or "").rstrip("/")
        lines.append(f"{b}alerts{e}:")
        for a in alerts:
            v = alert_view(a["rule"], a["severity"], a["message"])
            # plain-English headline first, the precise numbers underneath, then a
            # deep-link straight to the scorecard the alert came from (if a public
            # site URL is configured). A bare URL renders clickably on both TG/Discord.
            line = f"{SEV_EMOJI.get(a['severity'], '')} {b}{v['plain_en']}{e}\n   {v['message']}"
            if v.get("edge_en"):
                line += f"\n   conviction: {v['edge_en']}"
            if site_url:
                anchor = f"#{v['anchor']}" if v["anchor"] else ""
                line += f"\n   → {site_url}/macro.html{anchor}"
            lines.append(line)
    lines.append(health_line())
    return "\n".join(lines)


def send_telegram(msg: str) -> bool:
    token = config.secret("TELEGRAM_BOT_TOKEN")
    chat = config.secret("TELEGRAM_CHAT_ID")
    if not (config.load()["notify"]["telegram"]["enabled"] and token and chat):
        log.info("telegram: skipped (disabled or secrets absent)")
        return False
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": msg, "parse_mode": "HTML",
                            "disable_web_page_preview": True}, timeout=30)
    if r.status_code != 200:
        log.error("telegram send failed: %s %s", r.status_code, r.text[:200])
        return False
    log.info("telegram: sent")
    return True


def send_discord(msg: str) -> bool:
    url = config.secret("DISCORD_WEBHOOK_URL")
    if not (config.load()["notify"]["discord"]["enabled"] and url):
        log.info("discord: skipped (disabled or secrets absent)")
        return False
    # discord uses markdown-ish formatting; strip telegram HTML tags
    plain = msg.replace("<b>", "**").replace("</b>", "**")
    r = requests.post(url, json={"content": plain[:1990]}, timeout=30)
    if r.status_code not in (200, 204):
        log.error("discord send failed: %s %s", r.status_code, r.text[:200])
        return False
    log.info("discord: sent")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    latest = load_latest()
    if latest is None:
        log.error("no regime/latest.json — run the engine first")
        return 1
    msg = build_message(latest)
    if args.dry_run:
        print("--- message preview ---")
        print(msg)
        return 0
    sent_tg = send_telegram(msg)
    sent_dc = send_discord(msg)
    if not (sent_tg or sent_dc):
        log.info("no channel configured — dashboard remains the only surface")
    return 0


if __name__ == "__main__":
    sys.exit(main())
