"""M3 escalation organ — persistent Neural Web health degradation detector.

Reads data/neuralweb/health.json and data/neuralweb/nw_health_run_history.jsonl.
When a breach streak (consecutive degraded NIGHTLY RUNS) reaches >=3 nights,
dispatches an ops alert via engine/alert_triage.push_ops_alert through the
nw_health lane.

Design principles (house laws):
 - Streak keyed by NIGHTLY RUN DATE (health.produced_at), NOT by data-vintage
   (health.as_of).  When upstream data is stale, as_of freezes across many
   consecutive nights; the old daily_brief_history upsert-by-as_of approach
   collapsed N degraded nights to a single row (streak=1).  The run history
   file (nw_health_run_history.jsonl) is APPEND-only: one new row per nightly
   run, keyed by produced_at date.
 - Adjacency guard: streak requires calendar-consecutive run dates (each date
   must be exactly the prior date minus one day).  Gap-separated old degraded
   records never contribute to the current streak.
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
_STREAK_THRESHOLD = 3          # consecutive nightly runs required to fire
_SLA_MULTIPLIER = 1.5          # 1.5× SLA marks a lobe as breach-eligible
_DAILY_CADENCES = frozenset({"daily", "daily-engine"})
_RUN_HISTORY_FILE = "data/neuralweb/nw_health_run_history.jsonl"

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


def _load_run_history(root: Path) -> list[dict[str, Any]]:
    """Load data/neuralweb/nw_health_run_history.jsonl; return [] on any error.

    Each row: {"run_date": "YYYY-MM-DD", "degraded": bool, "produced_at": ISO}
    """
    path = root / _RUN_HISTORY_FILE
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
    except FileNotFoundError:
        pass  # First run; no history yet — not an error
    except Exception as exc:  # noqa: BLE001
        log.warning("check_nw_health_escalation: nw_health_run_history.jsonl unreadable (%s)", exc)
    return rows


def _append_run_record(
    root: Path,
    run_date: str,
    is_degraded: bool,
    reasons: list[str],
    produced_at: str,
) -> None:
    """Append one run record to nw_health_run_history.jsonl (fail-open).

    Ensures the file always ends with a newline before appending so that a
    missing trailing newline in an existing file does not merge two JSON records
    onto the same line (which would cause parse failures in _load_run_history).
    """
    path = root / _RUN_HISTORY_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        record = json.dumps({
            "run_date": run_date,
            "degraded": is_degraded,
            "produced_at": produced_at,
            "reasons_count": len(reasons),
        })
        # Probe the trailing byte with a separate binary handle: 'a'-mode
        # handles are write-only, so read(1) on one raises
        # io.UnsupportedOperation — which the fail-open except below would
        # swallow, silently dropping every append once the file exists.
        needs_newline = False
        try:
            if path.stat().st_size > 0:
                with open(path, "rb") as rb:
                    rb.seek(-1, 2)  # SEEK_END
                    needs_newline = rb.read(1) != b"\n"
        except FileNotFoundError:
            pass  # First run; file created by the append below
        with open(path, "a", encoding="utf-8") as fh:
            if needs_newline:
                fh.write("\n")
            fh.write(record + "\n")
    except Exception as exc:  # noqa: BLE001
        log.warning("check_nw_health_escalation: could not append run record (%s)", exc)


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


def _compute_streak(
    health: dict[str, Any],
    run_history: list[dict[str, Any]],
) -> tuple[int, list[str]]:
    """Compute consecutive-night breach streak from per-run records.

    Keyed by NIGHTLY RUN DATE (health.produced_at[:10]), not data-vintage
    (health.as_of).  When upstream data is stale, as_of freezes across many
    consecutive nights, causing an as_of-keyed history to collapse N runs to
    one row.  This function counts distinct degraded RUN DATES instead.

    Adjacency guard: a streak requires that each successive run date is exactly
    the prior date minus one calendar day.  A gap (e.g., months apart) resets
    the streak.

    Returns (streak_length, current_reasons).
    """
    # Build run_date → degraded map from history records.
    # run_history rows: {"run_date": "YYYY-MM-DD", "degraded": bool, ...}
    run_map: dict[str, bool] = {}
    for row in run_history:
        rd = row.get("run_date")
        if rd:
            # Normalize to first 10 chars (date only), last write wins
            run_map[str(rd)[:10]] = bool(row.get("degraded", False))

    # Current health.json — extract run date from produced_at
    current_degraded, current_reasons = _is_degraded_day(health)
    produced_at = health.get("produced_at", "")
    current_run_date = str(produced_at)[:10] if produced_at else ""
    if not current_run_date:
        # Fallback: if no produced_at, use today (should not happen in prod)
        current_run_date = date.today().isoformat()
    run_map[current_run_date] = current_degraded

    if not run_map:
        return 0, []

    # Sort run dates descending (all are YYYY-MM-DD, so lexical == date order)
    try:
        sorted_dates = sorted(run_map.keys(), reverse=True)
    except Exception:  # noqa: BLE001
        return 0, []

    # Count leading degraded run dates with strict calendar-adjacency guard.
    # Each successive entry must be exactly one calendar day before the previous.
    streak = 0
    prev_date: date | None = None
    for d_str in sorted_dates:
        try:
            d = date.fromisoformat(d_str)
        except ValueError:
            break  # Malformed date — stop streak
        if not run_map[d_str]:
            break  # Not degraded — streak ends
        if prev_date is not None and (prev_date - d).days != 1:
            break  # Gap in consecutive days — streak ends
        streak += 1
        prev_date = d

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

        # Determine current run metadata before loading history
        current_degraded, current_reasons = _is_degraded_day(health)
        produced_at = health.get("produced_at", "")
        current_run_date = str(produced_at)[:10] if produced_at else date.today().isoformat()

        # Append this run's record BEFORE computing streak so even first-run
        # history is available for recovery checks.  Fail-open: errors are
        # already swallowed inside _append_run_record.
        _append_run_record(
            root,
            run_date=current_run_date,
            is_degraded=current_degraded,
            reasons=current_reasons,
            produced_at=produced_at,
        )

        run_history = _load_run_history(root)

        streak, reasons = _compute_streak(health, run_history)
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
