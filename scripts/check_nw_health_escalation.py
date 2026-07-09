"""M3 escalation organ — persistent Neural Web health degradation detector.

Reads data/neuralweb/health.json and data/neuralweb/daily_brief_history.jsonl.
When a breach streak (consecutive degraded nights OR daily-cadence lobes
missing/stale beyond 1.5x SLA) reaches >=3 as_of days, dispatches an ops
alert via engine/alert_triage.push_ops_alert through the nw_health lane.

Design principles (house laws):
 - Fail-open: any read/parse failure degrades gracefully; exit 0 always.
 - Dispatch-always invariant: push_ops_alert is dispatch-always for ops
   lanes (W6b spine). Nightly while breached (pressure is intentional).
 - Maintenance vocabulary only: no trading verbs in composed messages.
 - Article 2: ops-tier alerting via ratified W6b spine only.

Run after build_neuralweb_health in the ENGINE job (daily.yml).
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from lib.logging import get_logger
    log = get_logger(__name__)
except Exception:  # noqa: BLE001
    import logging
    log = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────────────────────────
_STREAK_THRESHOLD = 3          # consecutive as_of days required to fire
_SLA_MULTIPLIER = 1.5          # 1.5× SLA marks a lobe as breach-eligible
_DAILY_CADENCES = frozenset({"daily", "daily-engine"})

# Trading-verb blacklist (mirrors engine/neuralweb/daily_brief.py TRADING_VERBS).
# Message assembly must not produce any of these words.
_TRADING_VERBS = frozenset({
    "buy", "sell", "hold", "add", "trim", "long", "short",
    "overweight", "underweight",
})

# ── helpers ────────────────────────────────────────────────────────────────


def _root_dir() -> Path:
    """Repo root (two parents above scripts/)."""
    return Path(__file__).resolve().parent.parent


def _load_health(root: Path) -> dict[str, Any] | None:
    """Load data/neuralweb/health.json; return None on any error."""
    path = root / "data" / "neuralweb" / "health.json"
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        log.warning("check_nw_health_escalation: health.json unreadable (%s)", exc)
        return None


def _load_brief_history(root: Path) -> list[dict[str, Any]]:
    """Load data/neuralweb/daily_brief_history.jsonl; return [] on any error."""
    path = root / "data" / "neuralweb" / "daily_brief_history.jsonl"
    rows: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception as exc:  # noqa: BLE001
        log.warning("check_nw_health_escalation: daily_brief_history.jsonl unreadable (%s)", exc)
    return rows


def _is_degraded_day(health: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return (degraded_flag, [lobe_ids that are breached]).

    Degraded when:
      (a) overall_status == 'degraded', OR
      (b) any daily-cadence lobe is missing or stale beyond 1.5× SLA.
    """
    reasons: list[str] = []
    if health.get("overall_status") == "degraded":
        reasons.append("overall_status=degraded")

    lobes = health.get("lobes", [])
    for lobe in lobes:
        if lobe.get("cadence") not in _DAILY_CADENCES:
            continue
        status = lobe.get("status", "")
        if status == "missing":
            reasons.append(f"lobe:{lobe.get('id','?')}:missing")
        elif status == "stale":
            # Double-check against 1.5× SLA if age is available
            age_h = lobe.get("age_hours")
            sla_h = lobe.get("freshness_sla_hours")
            if age_h is not None and sla_h is not None:
                if float(age_h) > float(sla_h) * _SLA_MULTIPLIER:
                    reasons.append(f"lobe:{lobe.get('id','?')}:stale_beyond_1.5x_sla")
            else:
                # No age info — trust the 'stale' label from health builder
                reasons.append(f"lobe:{lobe.get('id','?')}:stale")

    return bool(reasons), reasons


def _compute_streak(health: dict[str, Any], history: list[dict[str, Any]]) -> tuple[int, list[str]]:
    """Compute consecutive-night breach streak.

    Merge current health.json + daily_brief_history rows, then count the
    streak of most-recent consecutive degraded as_of dates.

    Returns (streak_length, combined_reason_labels).
    """
    # Build a dict: as_of_str → is_degraded for history rows
    history_map: dict[str, bool] = {}
    for row in history:
        as_of = row.get("as_of")
        status = row.get("status", "")
        if as_of:
            history_map[str(as_of)] = (status == "degraded")

    # Current health.json takes precedence
    current_as_of = health.get("as_of")
    current_degraded, current_reasons = _is_degraded_day(health)
    if current_as_of:
        history_map[str(current_as_of)] = current_degraded

    if not history_map:
        return 0, []

    # Sort dates descending and count the leading streak of degraded days
    try:
        sorted_dates = sorted(history_map.keys(), reverse=True)
    except Exception:  # noqa: BLE001
        return 0, []

    streak = 0
    for d in sorted_dates:
        if history_map[d]:
            streak += 1
        else:
            break

    return streak, current_reasons


def _check_trading_verbs(text: str) -> list[str]:
    """Return any trading verbs found in text (case-insensitive word-boundary check)."""
    import re
    found = []
    lower = text.lower()
    for verb in _TRADING_VERBS:
        if re.search(rf"\b{re.escape(verb)}\b", lower):
            found.append(verb)
    return found


def _compose_message(streak: int, reasons: list[str], as_of: str) -> str:
    """Compose the ops alert message.

    Maintenance vocabulary only — no trading verbs.
    """
    # Deduplicate and shorten reason labels for readability
    lobe_names = sorted({
        r.split(":")[1] for r in reasons if r.startswith("lobe:")
    })
    overall_flag = any(r.startswith("overall_status") for r in reasons)

    lines = [
        f"[NW-HEALTH] Neural Web health: {streak}-night breach streak (as_of={as_of}).",
    ]
    if overall_flag:
        lines.append("  - overall_status: degraded")
    if lobe_names:
        lobe_list = ", ".join(lobe_names[:10])
        suffix = f" (+{len(lobe_names)-10} more)" if len(lobe_names) > 10 else ""
        lines.append(f"  - affected lobes: {lobe_list}{suffix}")
    lines.append(
        f"  Ops check: review data/neuralweb/health.json and producer logs "
        f"(streak={streak}, threshold={_STREAK_THRESHOLD})."
    )
    msg = "\n".join(lines)

    # Sanity-check: no trading verbs in composed message
    bad = _check_trading_verbs(msg)
    if bad:
        log.error(
            "check_nw_health_escalation: composed message contains trading verb(s) %s — "
            "replacing with sanitised fallback",
            bad,
        )
        msg = (
            f"[NW-HEALTH] Neural Web health status: {streak}-night breach streak "
            f"(as_of={as_of}). Ops check required. "
            f"Review data/neuralweb/health.json and producer logs."
        )
    return msg


def run(root: Path | None = None, _now: datetime | None = None) -> bool:
    """Main entry point. Returns True if alert was dispatched, False otherwise.

    Never raises: any exception degrades to a warning + return False (fail-open).
    """
    if root is None:
        root = _root_dir()

    try:
        health = _load_health(root)
        if health is None:
            log.warning("check_nw_health_escalation: no health.json — skipping")
            return False

        history = _load_brief_history(root)

        streak, reasons = _compute_streak(health, history)
        as_of = health.get("as_of", "unknown")

        log.info(
            "check_nw_health_escalation: streak=%d threshold=%d as_of=%s reasons=%d",
            streak, _STREAK_THRESHOLD, as_of, len(reasons),
        )

        if streak < _STREAK_THRESHOLD:
            log.info(
                "check_nw_health_escalation: streak %d < threshold %d — no alert",
                streak, _STREAK_THRESHOLD,
            )
            return False

        message = _compose_message(streak, reasons, as_of)

        try:
            from engine.alert_triage import push_ops_alert
            dispatched = push_ops_alert(
                source="nw_health",
                type_="health_breach_streak",
                message=message,
                severity="major",
                lane="nw_health",
                root=root,
                _now=_now,
            )
            if dispatched:
                log.info(
                    "check_nw_health_escalation: alert dispatched (streak=%d, as_of=%s)",
                    streak, as_of,
                )
            else:
                log.info(
                    "check_nw_health_escalation: alert suppressed by dedup window (streak=%d)",
                    streak,
                )
            return dispatched
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "check_nw_health_escalation: push_ops_alert failed (%s) — fail-open, no-op",
                exc,
            )
            return False

    except Exception as exc:  # noqa: BLE001
        log.warning("check_nw_health_escalation: unexpected error (%s) — fail-open", exc)
        return False


if __name__ == "__main__":
    run()
    sys.exit(0)
