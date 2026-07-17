"""CSP-W6 — Forward-ledger heartbeat.

Silent ledger freezes become same-night escalations.

On every trading day where the site has republished (detected via the
--render-happened flag passed by the workflow), asserts that each registered
forward ledger's newest asof has advanced compared to the snapshot taken
during the previous run.  When a ledger is stalled while the site republished,
appends a row type_=ledger_stall to the fail-streak ledger via the shared
push_ops_alert machinery (same W6b spine as check_builder_failstreaks.py) and
emits a ::warning:: annotation to the GitHub Actions step summary.

Design principles (house laws):
 - Detection only, never a gate: this script always exits 0 (CSP-R1 forbids
   fail-dark — detection and disclosure, never fail-dark).
 - Sole-advancer: data/ci/ledger_heartbeat_state.json is the SINGLE state file
   for this check; no other script may write it.  It stores the previous-run
   snapshot of each ledger's newest asof, keyed by the ledger path (relative to
   repo root).
 - Idempotent per asof: same-calendar-day re-runs do NOT double-append to the
   fail-streak ledger or double-alert (dedup keyed on today_str per ledger).
 - Trading-day aware: weekends and US market holidays are skipped entirely (no
   stall detection, no state mutation on non-trading days).
 - Fail-open: any read/parse error degrades gracefully; exit 0 always.
 - Render-happened flag: the workflow passes --render-happened when the site
   commit step ran for that date.  Without it, stall detection is suppressed
   (we only escalate when the site republished with stale content).
 - State file location convention: data/ci/ mirrors the fail-streak ledger
   location (data/ci/builder_failstreaks.json).
 - Atomic-ish write: tmp file then os.replace (same idiom as
   check_builder_failstreaks.py).

Ledger manifest (extend this constant; add a comment when adding):
_LEDGER_MANIFEST is the authoritative list.  Each entry is a repo-root-relative
path to a JSONL forward ledger.  The asof field is the first key tried; fallback
tries 'date', then 'logged_at'.  A ledger that does not exist yet (e.g.
leadership_crack/forward_log.jsonl before W6 ships) is silently skipped — a
missing file is never escalated as a stall (it may simply not have been built yet).

Background (#2738 fail-streak pattern, CSP-W6):
The 2026-07-16 collect-cancel-while-always() incident showed that a silent
ledger freeze on a republish night looks identical to a healthy run at a glance.
This script makes that class of freeze same-night visible without gating or
blocking any pipeline step.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    from lib.logging import get_logger
    log = get_logger(__name__)
except Exception:  # noqa: BLE001
    import logging
    log = logging.getLogger(__name__)

# ── Ledger manifest ────────────────────────────────────────────────────────
# Registry extension: add an entry here when a new forward ledger is created.
# Each path is relative to the repo root.  The script silently skips missing
# files, so entries can be pre-registered before the building pipeline ships.
_LEDGER_MANIFEST: list[dict[str, str]] = [
    {
        "path": "data/risk_radar/forward_log.jsonl",
        "label": "risk_radar",
        # NOTE: extend the list below as new forward ledgers are created;
        # add a short label for use in escalation messages.
    },
    {
        "path": "data/market_state/forward_log.jsonl",
        "label": "market_state",
    },
    {
        "path": "data/mag7_regime/ledger.jsonl",
        "label": "mag7_regime",
    },
    {
        "path": "data/leadership_crack/forward_log.jsonl",
        "label": "leadership_crack",
        # NOTE: may not exist until CSP-W1 ships; silently skipped until then.
    },
    {
        "path": "data/deterioration_cascade/forward_log.jsonl",
        "label": "deterioration_cascade",
        # NOTE: may not exist until CSP-W1/W2 ships; silently skipped until then.
    },
    # ── Add new ledgers below this line ────────────────────────────────────
]

# State file location (mirrors data/ci/ convention from #2738).
_STATE_FILE = "data/ci/ledger_heartbeat_state.json"

# asof field candidates — tried in order for each JSONL row.
_ASOF_FIELDS = ("asof", "date", "logged_at")


# ── helpers ────────────────────────────────────────────────────────────────


def _root_dir() -> Path:
    """Repo root (two parents above scripts/)."""
    return Path(__file__).resolve().parent.parent


def _is_trading_day(d: date) -> bool:
    """True when d is a US equity market session (NYSE/Nasdaq)."""
    try:
        from lib.nyse_calendar import is_session  # noqa: PLC0415
        return is_session(d)
    except Exception:  # noqa: BLE001
        # Fallback: weekdays only (no holiday awareness).
        # This is safe to degrade to because false positives (running on a
        # holiday) produce at most a benign "no stall" log line.
        return d.weekday() < 5


def _latest_asof(jsonl_path: Path) -> str | None:
    """Return the newest asof string from the JSONL file, or None on any error.

    Reads the last up to 20 lines (tail-scan) to find the newest asof without
    loading the entire file — forward ledgers can grow large over months.
    """
    if not jsonl_path.exists():
        return None
    try:
        content = jsonl_path.read_text(encoding="utf-8", errors="replace")
        lines = [l for l in content.splitlines() if l.strip()]
        if not lines:
            return None
        # Scan the last 20 rows for the freshest asof value.
        best: str | None = None
        for raw in lines[-20:]:
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            for field in _ASOF_FIELDS:
                val = row.get(field)
                if val and isinstance(val, str):
                    # Normalise to date-only prefix for comparison.
                    day_str = val[:10]
                    if best is None or day_str > best:
                        best = day_str
                    break
        return best
    except Exception as exc:  # noqa: BLE001
        log.warning("check_ledger_advance: cannot read %s (%s)", jsonl_path, exc)
        return None


def _load_state(state_path: Path) -> dict[str, Any]:
    """Load the heartbeat state file; return skeleton on any error."""
    skeleton: dict[str, Any] = {
        "schema": "ledger_heartbeat_state.v1",
        "updated_utc": None,
        "last_check_date": None,
        "ledgers": {},
    }
    if not state_path.exists():
        return skeleton
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            log.warning("check_ledger_advance: state file is not a dict — starting fresh")
            return skeleton
        if "ledgers" not in data or not isinstance(data["ledgers"], dict):
            data["ledgers"] = {}
        return data
    except Exception as exc:  # noqa: BLE001
        log.warning("check_ledger_advance: state file unreadable (%s) — starting fresh", exc)
        return skeleton


def _save_state(state_path: Path, data: dict[str, Any]) -> None:
    """Atomic-ish write: tmp in same dir then os.replace (fail-open)."""
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=state_path.parent,
            prefix=".ledger_heartbeat_tmp_",
            suffix=".json",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
                fh.write("\n")
            os.replace(tmp_path, state_path)
        except Exception:  # noqa: BLE001
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:  # noqa: BLE001
        log.warning("check_ledger_advance: could not save state (%s) — fail-open", exc)


def _dispatch_stall_alert(stalled: list[dict[str, Any]], root: Path) -> None:
    """Dispatch a combined ops alert through the W6b spine (fail-open).

    Reuses the same push_ops_alert path as check_builder_failstreaks.py so the
    escalation lands in the same ops-push channel without forking the spine.
    """
    if not stalled:
        return
    header = "Forward-ledger stall(s) — site republished with frozen ledger content"
    bullets = []
    for s in stalled:
        bullets.append(
            f"• {s['label']} ({s['path']}): asof unchanged at {s['prev_asof']!r} "
            f"(stalled since {s['stalled_since']})"
        )
    message = header + "\n" + "\n".join(bullets)

    try:
        from engine.alert_triage import push_ops_alert  # noqa: PLC0415
        push_ops_alert(
            source="ledger_heartbeat",
            type_="ledger_stall",
            message=message,
            severity="major",
            lane="ledger_heartbeat",
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "check_ledger_advance: push_ops_alert failed (%s) — fail-open, no-op",
            exc,
        )


def _emit_warning_annotation(stalled: list[dict[str, Any]]) -> None:
    """Write ::warning:: GitHub Actions annotations for stalled ledgers."""
    for s in stalled:
        title = (
            f"LEDGER STALL: {s['label']} asof frozen at {s['prev_asof']!r} "
            f"while site republished"
        )
        body = (
            f"Forward ledger {s['path']} did not advance on {s['today']}; "
            f"site committed fresh pages against stale ledger content. "
            f"Stalled since {s['stalled_since']}."
        )
        print(f"::warning title={title}::{body}")


def _append_step_summary(stalled: list[dict[str, Any]]) -> None:
    """Append a markdown section to GITHUB_STEP_SUMMARY if set."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not summary_path:
        return
    try:
        lines = ["", "### ⚠ Forward-ledger stalls (CSP-W6 heartbeat)", ""]
        for s in stalled:
            lines.append(
                f"- **{s['label']}**: asof frozen at `{s['prev_asof']}`, "
                f"stalled since {s['stalled_since']} — {s['path']}"
            )
        lines.append("")
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    except Exception as exc:  # noqa: BLE001
        log.warning("check_ledger_advance: could not write step summary (%s)", exc)


def run_check(
    root: Path,
    state_path: Path,
    render_happened: bool,
    _now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Core logic: compare current ledger asof values vs saved snapshot.

    Parameters
    ----------
    root            Repo root path.
    state_path      Path to the heartbeat state JSON.
    render_happened True when the workflow's site-commit step ran for today.
                    Stall escalation is suppressed when False (no republish =
                    no stall to report).
    _now            Injectable datetime for tests (UTC).

    Returns
    -------
    List of stall dicts for each ledger whose asof did not advance on a
    render-happened trading day:
      {label, path, prev_asof, curr_asof, today, stalled_since}
    """
    now = _now if _now is not None else datetime.now(timezone.utc)
    today_str = now.date().isoformat()

    # Skip non-trading days entirely.
    if not _is_trading_day(now.date()):
        log.info(
            "check_ledger_advance: %s is not a trading day — skipping",
            today_str,
        )
        return []

    state = _load_state(state_path)
    ledger_state: dict[str, Any] = state.get("ledgers", {})

    stalled: list[dict[str, Any]] = []

    for entry in _LEDGER_MANIFEST:
        rel_path = entry["path"]
        label = entry["label"]
        full_path = root / rel_path

        curr_asof = _latest_asof(full_path)
        prev_entry = ledger_state.get(rel_path, {})
        prev_asof = prev_entry.get("asof") if isinstance(prev_entry, dict) else None
        last_check_date = prev_entry.get("last_check_date") if isinstance(prev_entry, dict) else None
        stalled_since = prev_entry.get("stalled_since") if isinstance(prev_entry, dict) else None

        log.info(
            "check_ledger_advance: %s: prev_asof=%r curr_asof=%r render_happened=%s",
            label, prev_asof, curr_asof, render_happened,
        )

        # Detect stall: ledger exists, we have a previous snapshot, asof has
        # not advanced, and the site republished today.
        is_stall = (
            render_happened
            and curr_asof is not None
            and prev_asof is not None
            and curr_asof <= prev_asof  # not advanced (equality = same value = stall)
            and last_check_date != today_str  # idempotent: same-day re-run = skip
        )

        if is_stall:
            stalled_since_val = stalled_since or prev_entry.get("last_check_date") or today_str
            stalled.append({
                "label": label,
                "path": rel_path,
                "prev_asof": prev_asof,
                "curr_asof": curr_asof,
                "today": today_str,
                "stalled_since": stalled_since_val,
            })
            log.warning(
                "check_ledger_advance: STALL detected — %s asof=%r unchanged "
                "(prev=%r, render_happened=True)",
                label, curr_asof, prev_asof,
            )

        # Update state for this ledger.
        new_entry: dict[str, Any] = {
            "asof": curr_asof,
            "last_check_date": today_str,
        }
        if is_stall:
            # Preserve stalled_since across consecutive stall days.
            new_entry["stalled_since"] = stalled_since or prev_entry.get("last_check_date") or today_str
        else:
            # Cleared on advance.
            new_entry["stalled_since"] = None

        ledger_state[rel_path] = new_entry

    # Persist updated state.
    state["ledgers"] = ledger_state
    state["updated_utc"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    state["last_check_date"] = today_str
    _save_state(state_path, state)
    log.info(
        "check_ledger_advance: state saved (%d ledgers, %d stalled)",
        len(_LEDGER_MANIFEST), len(stalled),
    )

    return stalled


def main(argv: list[str] | None = None) -> int:
    """Entry point. Always returns 0 (fail-open; CSP-R1: never fail-dark)."""
    parser = argparse.ArgumentParser(
        description=(
            "CSP-W6 forward-ledger heartbeat: detect ledger freezes on "
            "nights when the site republished."
        ),
    )
    parser.add_argument(
        "--render-happened",
        action="store_true",
        default=False,
        help=(
            "Pass when the workflow's site-commit step ran successfully for today. "
            "Without this flag, stall detection is suppressed (no republish = no stall)."
        ),
    )
    parser.add_argument(
        "--state-file",
        default=_STATE_FILE,
        help=f"Path to heartbeat state JSON (default: {_STATE_FILE}), "
             "resolved relative to repo root unless absolute.",
    )
    parser.add_argument(
        "--root", default=None,
        help="Repo root override (for tests).",
    )
    args = parser.parse_args(argv)

    try:
        root = Path(args.root).resolve() if args.root else _root_dir()

        state_raw = args.state_file
        if Path(state_raw).is_absolute():
            state_path = Path(state_raw)
        else:
            state_path = root / state_raw

        stalled = run_check(
            root=root,
            state_path=state_path,
            render_happened=args.render_happened,
        )

        if stalled:
            _emit_warning_annotation(stalled)
            _append_step_summary(stalled)
            _dispatch_stall_alert(stalled, root)
        else:
            log.info(
                "check_ledger_advance: all ledgers healthy (or render did not happen) — no alert"
            )

    except Exception as exc:  # noqa: BLE001
        log.warning("check_ledger_advance: unexpected error (%s) — fail-open", exc)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
