"""W6a: Push priority alerts via configured channels (Telegram/Discord).

CLI entry point for `engine.alert_triage.push_priority_alerts()`.
Config-gated OFF by default via `alert_push.enabled=false` in config.yml —
enabling is an OPERATOR + Article-2 event.

Usage:
    python -m scripts.push_alerts

Returns 0 always (resilient — never blocks the daily build).
"""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)


def main() -> None:
    try:
        import yaml
        from pathlib import Path
        _cfg_path = Path(__file__).parent.parent / "config.yml"
        _raw_cfg = yaml.safe_load(_cfg_path.read_text(encoding="utf-8")) if _cfg_path.exists() else {}
        _push_cfg = _raw_cfg.get("alert_push") or {}
        from engine.alert_triage import push_priority_alerts
        sent = push_priority_alerts(
            threshold=_push_cfg.get("threshold", 60),
            window_hours=_push_cfg.get("window_hours", 6),
        )
        if sent:
            log.info("push_priority_alerts: dispatched %d alert(s)", len(sent))
        else:
            log.debug("push_priority_alerts: no alerts dispatched (disabled, below threshold, or deduped)")
    except Exception as exc:  # noqa: BLE001
        # Resilient: never blocks the daily build
        log.warning("push_priority_alerts failed (non-fatal): %s", exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    main()
