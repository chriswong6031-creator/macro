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
    """Return the regime quad dict that build_message() expects.

    Migration (W1 PR2): try world_state first; fall back to the legacy
    direct read of data/regime/latest.json.  build_message() accesses keys
    that live in world_state.regime plus a few extras (sector_rs, playbook,
    alerts, preference_check, flip_condition) that are top-level in
    latest.json.  When world_state is fresh we build a compatible dict from
    its sub-blocks; otherwise we return latest.json verbatim exactly as before.
    """
    from engine.neuralweb.read import load_world_state, get as ws_get
    ws = load_world_state()
    if ws is not None:
        reg_block = ws.get("regime") or {}
        # build_message() reads a flat dict; reconstruct it from world_state blocks.
        # Keys required: quad, quad_name, label, confidence, liquidity_overlay,
        # cycle_tag, transition_state, growth_score, inflation_score, date,
        # sector_rs, playbook, alerts, preference_check, flip_condition.
        # sector_rs lives in ws.regime (added in W1 PR2 _compose_regime).
        # playbook / alerts / preference_check / flip_condition are NOT in world_state
        # (they are latest.json-only fields) — fall back to raw file for those.
        # Full legacy fallback is cheap so we only skip it if ALL needed fields present.
        quad = reg_block.get("quad")
        if quad is not None:
            p = config.data_dir() / "regime" / "latest.json"
            raw: dict = {}
            if p.exists():
                try:
                    with open(p) as f:
                        raw = json.load(f)
                except Exception:  # noqa: BLE001
                    pass
            # Overlay world_state regime fields; keep raw file for non-regime fields.
            merged: dict = dict(raw)
            merged["quad"] = reg_block.get("quad")
            merged["quad_name"] = reg_block.get("quad_name")
            merged["label"] = reg_block.get("label")
            merged["confidence"] = reg_block.get("confidence")
            merged["liquidity_overlay"] = reg_block.get("liquidity_overlay")
            merged["cycle_tag"] = reg_block.get("cycle_tag")
            merged["transition_state"] = reg_block.get("transition_state")
            merged["growth_score"] = reg_block.get("growth_score")
            merged["inflation_score"] = reg_block.get("inflation_score")
            if reg_block.get("sector_rs") is not None:
                merged["sector_rs"] = reg_block.get("sector_rs")
            return merged

    # Legacy fallback: direct read of data/regime/latest.json
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
        from engine.alerts import alert_href, alert_view
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
                line += f"\n   → {site_url}/{alert_href(v['anchor'])}"
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
    # Fall back to the Watchlist webhook (the one channel that IS provisioned) so ops /
    # heartbeat alerts have a working transport even when no dedicated DISCORD_WEBHOOK_URL
    # secret is set. A workflow opts in by passing DISCORD_WEBHOOK_WATCHLIST in its env.
    url = config.secret("DISCORD_WEBHOOK_URL") or config.secret("DISCORD_WEBHOOK_WATCHLIST")
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
