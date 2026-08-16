"""Commercial-path sentinel — GATE-4 human-watched alarms.

Runs on the existing macro-sentinel.timer (every 30 minutes, same
EnvironmentFiles as the freshness dead-man switch). Evaluates the ledger
written by lib.commercial_path.emit and pages through the freshness
sentinel's Telegram / Discord / email transport. No new vendor.

Usage:
  python -m scripts.commercial_path_sentinel
  python -m scripts.commercial_path_sentinel --dry-run
  python -m scripts.commercial_path_sentinel --inject checkout_fail
  python -m scripts.commercial_path_sentinel --prove-all
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.commercial_path import (  # noqa: E402
    ALERT_KINDS,
    Alert,
    Thresholds,
    decide_alerts,
    evaluate,
    inject,
    load_events,
    load_state,
    save_state,
    state_dir,
)

# Reuse the freshness sentinel's transports — same env, same POST shape, same
# mailer. Importing the sibling is the reuse the launch gate asked for.
from scripts.freshness_sentinel import (  # noqa: E402
    notify_operator,
    send_discord,
    send_email,
    send_telegram,
)


def _now(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _transports(now: datetime):
    return [
        ("telegram", send_telegram),
        ("discord", send_discord),
        ("email", lambda m: send_email(
            m, now, subject="Mastermind commercial-path alert",
            template="commercial_path_sentinel",
        )),
    ]


def compose_messages(alerts: list[Alert], recoveries: list[str]) -> list[str]:
    messages = [a.message() for a in alerts]
    messages.extend(recoveries)
    return messages


def configured_channels() -> list[str]:
    names = []
    if (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip() and (
            os.environ.get("TELEGRAM_CHAT_ID") or "").strip():
        names.append("telegram")
    if (os.environ.get("DISCORD_WEBHOOK_URL") or os.environ.get("DISCORD_WEBHOOK_WATCHLIST") or "").strip():
        names.append("discord")
    if (os.environ.get("MAIL_SENTINEL_TO") or os.environ.get("MAIL_SUPPORT_TO") or "").strip():
        names.append("email")
    return names


def run(*, now: datetime, root: Path | None, dry_run: bool = False,
        transports=None) -> int:
    th = Thresholds.from_env()
    events = load_events(now=now, root=root)
    active = evaluate(events, now=now, thresholds=th)
    state = load_state(root)
    to_send, recoveries, new_state = decide_alerts(active, state, now=now, thresholds=th)
    messages = compose_messages(to_send, recoveries)

    for alert in active:
        print(f"{alert.kind}: ACTIVE — {alert.title}")
    if not active:
        print("commercial-path: all clear")

    delivered_any = False
    if dry_run:
        for msg in messages:
            print("--- dry-run alert ---")
            print(msg)
    else:
        fan = transports if transports is not None else _transports(now)
        for msg in messages:
            delivered = notify_operator(msg, now, transports=fan)
            if delivered:
                delivered_any = True
                print(f"commercial-path alert ({','.join(delivered)})")
            else:
                print("commercial-path: no transport delivered — "
                      "dashboard/unit status remains the fallback", file=sys.stderr)
        save_state(new_state, root)

    if active and not dry_run and messages and not delivered_any and not configured_channels():
        # Condition is real; channel credentials are the remaining gap.
        print("commercial-path: DELIVER=SKIP (no human-channel credentials)",
              file=sys.stderr)
    return 1 if active else 0


def prove_all(*, now: datetime, root: Path, send: bool) -> int:
    """Synthetic-inject every GATE-4 alert and report DETECT / MESSAGE / DELIVER.

    DETECT and MESSAGE must PASS. DELIVER is PASS only when a configured
    transport actually accepted the POST; SKIP when no credentials are
    present — never papered over as PASS.
    """
    th = Thresholds.from_env()
    channels = configured_channels()
    print("COMMERCIAL-PATH PROVE")
    print(f"  ledger: {state_dir(root)}")
    print(f"  channels configured: {', '.join(channels) or '(none)'}")
    worst = 0
    for kind in ALERT_KINDS:
        inject(kind, now=now, root=root, thresholds=th)
        events = load_events(now=now, root=root)
        active = evaluate(events, now=now, thresholds=th)
        hit = next((a for a in active if a.kind == kind), None)
        detect = "PASS" if hit is not None else "FAIL"
        message = "FAIL"
        body = ""
        if hit is not None:
            body = hit.message()
            message = "PASS" if body.startswith("COMMERCIAL PATH —") and hit.title else "FAIL"
        deliver = "SKIP (no human-channel credentials)"
        if hit is not None and send and channels:
            delivered = notify_operator(body, now, transports=_transports(now))
            deliver = f"PASS ({','.join(delivered)})" if delivered else "FAIL (transport rejected)"
        elif hit is not None and channels and not send:
            deliver = "SKIP (--prove-all does not send unless --send)"
        print(f"  {kind:<18} DETECT={detect}  MESSAGE={message}  DELIVER={deliver}")
        if detect != "PASS" or message != "PASS":
            worst = 2
        if deliver.startswith("FAIL"):
            worst = max(worst, 1)
        if hit is not None:
            print(f"    {body.splitlines()[0]}")
    if not channels:
        print("REMAINING: live delivery to Telegram/Discord/email — set "
              "TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID or DISCORD_WEBHOOK_URL "
              "(or MAIL_SENTINEL_TO) in /etc/macro-sentinel.env. "
              "Local transport construction is proven; the one remaining "
              "check is a credentialed send.")
    return worst


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Commercial-path sentinel (GATE-4)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--now", default=None, help="clock override, ISO-8601")
    ap.add_argument("--state-dir", default=None,
                    help="override MACRO_API_STATE_DIR/commercial_path parent")
    ap.add_argument("--inject", choices=ALERT_KINDS, default=None,
                    help="write a synthetic episode for one alert kind, then evaluate")
    ap.add_argument("--prove-all", action="store_true",
                    help="inject every kind; report DETECT/MESSAGE/DELIVER honestly")
    ap.add_argument("--send", action="store_true",
                    help="with --prove-all, actually POST to configured transports")
    args = ap.parse_args(argv)

    now = _now(args.now)
    root = None
    if args.state_dir:
        root = Path(args.state_dir)
    elif os.environ.get("COMMERCIAL_PATH_STATE_DIR"):
        root = Path(os.environ["COMMERCIAL_PATH_STATE_DIR"])

    if args.prove_all:
        if root is None:
            root = Path(os.environ.get("MACRO_API_STATE_DIR", "/tmp")) / "commercial_path_prove"
        return prove_all(now=now, root=root, send=args.send)

    if args.inject:
        inject(args.inject, now=now, root=root)
        print(f"injected {args.inject}")

    return run(now=now, root=root, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
