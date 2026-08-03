"""scripts/press_x_stream_rules.py — manage the twitterapi.io push-lane rules.

The XS push lane (engine/marketing/press_stream.py) consumes a websocket fed
by SERVER-SIDE filter rules. This script is the only thing that writes those
rules — arming spend is an operator action, never a daemon side effect.

Usage (key read from $TWITTERAPI_IO_KEY unless x_stream.key_env says otherwise):
    python -m scripts.press_x_stream_rules --status   # list remote rules
    python -m scripts.press_x_stream_rules --plan     # show desired rules, no writes
    python -m scripts.press_x_stream_rules --sync     # converge remote onto config + activate
    python -m scripts.press_x_stream_rules --off      # deactivate every mmx-press rule (spend kill)

--sync adds missing rules, updates drifted ones, activates ours (is_effect=1)
and DELETES stale mmx-press-* rules, so removing a handle from the register
stops its billing on the next sync. Rules without our tag prefix are never
touched. --off keeps the inventory but flips is_effect=0 on all of it.

Exit codes: 0 clean, 1 any rule operation errored (partial syncs say so).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_cfg() -> dict:
    import yaml
    return yaml.safe_load(
        (ROOT / "config" / "press_sources.yml").read_text(encoding="utf-8")
    ) or {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--status", action="store_true", help="list remote rules")
    mode.add_argument("--plan", action="store_true",
                      help="print the desired rule set from config; no writes")
    mode.add_argument("--sync", action="store_true",
                      help="converge remote rules onto config and activate")
    mode.add_argument("--off", action="store_true",
                      help="deactivate every prefixed rule (spend kill switch)")
    args = parser.parse_args(argv)

    from engine.marketing import press_stream as ps

    press_cfg = _load_cfg()
    cfg = ps.stream_cfg(press_cfg)
    satire = list(press_cfg.get("satire_blocklist") or [])
    if not cfg:
        print("press_sources.yml carries no x_stream block — nothing to manage")
        return 1

    if args.plan:
        rules = ps.chunk_rules(cfg, satire_blocklist=satire)
        for rule in rules:
            print(f"{rule['tag']:<18} every {rule['interval_seconds']:>5}s  {rule['value']}")
        print(f"{len(rules)} rule(s) for "
              f"{len(ps.handle_register(cfg))} registered handle(s)")
        return 0

    if args.status:
        rules = ps.list_remote_rules(cfg)
        if not rules:
            print("no remote rules")
            return 0
        for rule in rules:
            print(json.dumps(rule))
        return 0

    report = ps.sync_rules(cfg, satire_blocklist=satire,
                           deactivate_only=args.off)
    for verb in ("created", "updated", "deleted", "deactivated", "unchanged"):
        for tag in report.get(verb, []):
            print(f"{verb}: {tag}")
    for err in report.get("errors", []):
        print(f"ERROR: {err}", file=sys.stderr)
    return 1 if report.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
