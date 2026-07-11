"""scripts/metabolism_dispatch.py — Key dispatcher for the Metabolism V2-B pool.

PURPOSE
-------
Picks the best available OAuth key for a metabolism stage by reading the
key_pool belief-state (key_ledger.jsonl).  Returns the capability_id of the
chosen key so the CALLER reads os.environ[secret_ref] — the dispatcher never
touches token values.

POOL POLICY: LRU / lowest 5h-window load among present, non-cooling keys.
With 1 key present, it works — just serializes.
With all keys cooling, journals an 'all_keys_cooling' no-op, sends one
operator notify, and exits 0 (stateless — next cron wakes; dispatcher resumes
when now >= earliest_reset without a live timer).

is_paused() check is the FIRST operation (R-AUT-2); unset AUTONOMY_PAUSED
means paused — clean exit.

REDLINE: pick_key() returns a capability_id string (NOT a token value).
The caller maps capability_id → secret_ref via key_pool.get_secret_ref() and
reads os.environ[secret_ref] independently.

IMMUTABLE: config/metabolism_schedule.yml is read by this dispatcher for the
time-of-day spread table.  The schedule file is in the IMMUTABLE set (R-V2-8)
and is registered in check_self_mod_fence.py + check_grader_manifest.py.  The
dispatcher NEVER modifies the schedule.

STATELESS-CATTLE: no persistent sessions.  All state in key_ledger.jsonl.

Usage (programmatic):
    from scripts.metabolism_dispatch import pick_key
    cap_id = pick_key()
    if cap_id is None:
        sys.exit(0)  # paused or all-cooling or no keys
    ref = key_pool.get_secret_ref(cap_id)
    # caller reads os.environ[ref] — dispatcher never does

Usage (CLI):
    python3 scripts/metabolism_dispatch.py --stage sense
    # Prints: CHOSEN_KEY=claude_code_oauth_1
    # Sets exit 0 on success, exit 1 on hard error, exit 0 on paused/freeze.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger(__name__)

_SCHEDULE_REL = "config/metabolism_schedule.yml"
_FREEZE_JOURNAL_REL = "data/metabolism/journal"


def _load_schedule(root: Path | None = None) -> dict:
    """Load config/metabolism_schedule.yml.  Returns {} on error (NEVER-RAISE)."""
    try:
        import yaml
        base = root or _ROOT
        p = base / _SCHEDULE_REL
        with open(p) as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_dispatch._load_schedule: %s", exc)
        return {}


def _stage_allowed_now(stage: str, schedule: dict) -> bool:
    """Return True if the stage is allowed at the current UTC hour per schedule.

    If no schedule entry is found, the stage is allowed (fail-open).
    """
    try:
        hour = datetime.now(timezone.utc).hour
        windows = schedule.get("dispatch_windows", [])
        for window in windows:
            stages = window.get("stages", [])
            if stage not in stages:
                continue
            hours = window.get("utc_hours", [])
            if not hours:
                return True
            if hour in hours:
                return True
            return False  # stage found in table but not in this hour window
        return True  # not in table → allowed
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_dispatch._stage_allowed_now: %s", exc)
        return True


def pick_key(
    stage: str = "",
    root: Path | None = None,
    notify_on_freeze: bool = True,
    exclude: set[str] | None = None,
) -> str | None:
    """Pick the best available key for the given stage.

    Strategy: LRU / lowest 5h-window session count, excluding cooling keys.

    Parameters
    ----------
    stage : str
        The metabolism stage requesting a key (used for schedule gating).
    root : Path | None
        Repo root for test isolation.
    notify_on_freeze : bool
        If True and all keys are cooling, sends one operator notify.
    exclude : set[str] | None
        Capability ids to skip (keys already tried and failed in THIS
        invocation — enables retry-with-next-key without re-picking a key
        whose failure has not yet landed in the ledger).

    Returns
    -------
    str | None
        The capability_id of the chosen key, or None if:
          - AUTONOMY_PAUSED (clean no-op)
          - No present keys
          - All keys cooling (after freeze no-op emitted)

    REDLINE: returns capability_id only, never a token value.
    NEVER raises.
    """
    try:
        from scripts.metabolism_guard import is_paused
        if is_paused():
            log.info("metabolism_dispatch: AUTONOMY_PAUSED — no-op")
            return None
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_dispatch: is_paused check failed (%s) — treating as paused", exc)
        return None

    try:
        from engine.neuralweb.key_pool import (
            discover_present_keys,
            window_load,
            is_cooling,
            all_cooling_freeze_info,
        )

        present = discover_present_keys(root)
        if exclude:
            present = [k for k in present if k not in exclude]
        if not present:
            log.info("metabolism_dispatch: no present keys — no-op")
            return None

        # Check schedule for stage time-of-day gating
        schedule = _load_schedule(root)
        if stage and not _stage_allowed_now(stage, schedule):
            log.info(
                "metabolism_dispatch: stage '%s' not allowed at current UTC hour per schedule",
                stage,
            )
            return None

        # Filter out cooling keys
        available = [k for k in present if not is_cooling(k, root)]

        if not available:
            # All keys cooling — emit freeze no-op + notify
            freeze = all_cooling_freeze_info(present, root)
            earliest = freeze.get("earliest_reset", "")
            log.warning(
                "metabolism_dispatch: all keys cooling — freeze no-op; "
                "earliest_reset=%s",
                earliest,
            )
            _emit_freeze_journal(stage, freeze, root)
            if notify_on_freeze:
                _notify_freeze(earliest, freeze, root)
            return None

        # Pick least-loaded key by 5h window sessions (LRU)
        chosen = min(available, key=lambda k: window_load(k, root))
        return chosen

    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_dispatch.pick_key: %s", exc)
        return None


def _emit_freeze_journal(
    stage: str,
    freeze_info: dict,
    root: Path | None = None,
) -> None:
    """Append an all_keys_cooling journal entry (NEVER-RAISE)."""
    try:
        base = root or _ROOT
        journal_dir = base / _FREEZE_JOURNAL_REL
        journal_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        entry = {
            "schema": "metabolism.dispatch_freeze.v1",
            "ts": ts,
            "event": "all_keys_cooling",
            "stage": stage,
            "earliest_reset": freeze_info.get("earliest_reset", ""),
            "key_reset_hints": freeze_info.get("key_reset_hints", {}),
        }
        filename = f"freeze_{ts.replace(':', '-').replace('+', 'Z')}.json"
        (journal_dir / filename).write_text(
            json.dumps(entry, indent=2), encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_dispatch._emit_freeze_journal: %s", exc)


def _notify_freeze(
    earliest_reset: str,
    freeze_info: dict,
    root: Path | None = None,
) -> None:
    """Send one deduped operator notify about the freeze (NEVER-RAISE)."""
    try:
        msg = (
            f"[Metabolism] All OAuth keys cooling — dispatch frozen. "
            f"Earliest reset: {earliest_reset}. "
            f"Resets: {freeze_info.get('key_reset_hints', {})}"
        )
        # Use scripts/notify.py pattern: send via Telegram/Discord if secrets present
        # Dry-run if no notification secret is configured.
        telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        telegram_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
        discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")

        if telegram_token and telegram_chat:
            import requests
            url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
            requests.post(url, json={"chat_id": telegram_chat, "text": msg},
                          timeout=10)
        elif discord_webhook:
            import requests
            requests.post(discord_webhook, json={"content": msg}, timeout=10)
        else:
            log.info("metabolism_dispatch notify (no channel configured): %s", msg)
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_dispatch._notify_freeze: %s", exc)


def main(argv: list[str] | None = None) -> int:
    """CLI: picks a key and prints CHOSEN_KEY=<cap_id> (or CHOSEN_KEY=none)."""
    ap = argparse.ArgumentParser(
        description="Metabolism V2-B key dispatcher — picks the lowest-load available key."
    )
    ap.add_argument("--stage", default="", help="Metabolism stage name (for schedule gating).")
    ap.add_argument("--no-notify", action="store_true", help="Suppress freeze notify.")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    chosen = pick_key(stage=args.stage, notify_on_freeze=not args.no_notify)
    if chosen:
        print(f"CHOSEN_KEY={chosen}")
        return 0
    else:
        print("CHOSEN_KEY=none")
        return 0  # exit 0 — paused/freeze is a clean no-op, not an error


if __name__ == "__main__":
    sys.exit(main())
