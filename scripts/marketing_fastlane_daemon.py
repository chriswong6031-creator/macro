"""scripts/marketing_fastlane_daemon.py — Runner for the marketing fast lanes.

Drives two intraday lanes:
    earnings  the original earnings fast lane (earnings_feed + fastlane.run_tick).
    press     PRESS-FEEDS B1 (D05 Addendum 2) — the Trump/markets wire spine:
              wire RSS (breaking_feed.poll_all) + press providers
              (press_providers.poll_all: trumpstruth mirror, twitterapi.io x_relay,
              CNN backfill) -> relevance -> corroboration -> summarize-with-citation
              -> emit kind="breaking" outbox items with scheduled_at="immediate".

Usage:
    python scripts/marketing_fastlane_daemon.py [--lane earnings|press|all] \
        [--once] [--dry-run] [--interval N]

Flags:
    --lane L     Which lane(s) to drive (default: earnings, for back-compat).
    --once       Run exactly one tick then exit (useful for cron / one-shot jobs).
    --dry-run    Compute the full tick (fetch, dedupe, score, corroborate, summarize,
                 card) but write NOTHING to disk. Prints a would-emit summary.
    --interval N Poll interval in seconds (default: 120).  Ignored with --once.

Kill-switches (BOTH gate press emission):
    MARKETING_FASTLANE_ENABLED != "1"  -> the whole daemon prints a note and exits
                                          0 immediately (no work at all).
    MARKETING_PUBLISH_ENABLED not set  -> the press lane still runs the pipeline
                                          but emits NOTHING to the outbox (a clean
                                          no-op tick). --dry-run forces this too.

Heartbeat:
    Each successful tick touches data/marketing/fastlane_heartbeat.txt with the
    current UTC timestamp.  --dry-run skips the heartbeat write.

Press-lane local state (gitignored — data/marketing/press/state.json):
    provider cursors / conditional-GET ETags / spend accounting / flagship counter
    / corroboration window / seen-ledger.  The poller makes ZERO repo/git writes.

No git writes.  No ledger advances.  The daemon is a fully intraday lane.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Repo root resolution (same pattern as test helpers)
# ─────────────────────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Cannot locate repo root from {p}")


ROOT = _repo_root()

# Add repo root to sys.path so engine.marketing imports work when the script is
# called directly (e.g., python scripts/marketing_fastlane_daemon.py).
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("fastlane_daemon")

_HEARTBEAT_PATH = ROOT / "data" / "marketing" / "fastlane_heartbeat.txt"
_KILL_SWITCH_ENV = "MARKETING_FASTLANE_ENABLED"
_DEFAULT_INTERVAL_S = 120

# Press-lane local-only state (gitignored). The poller writes ONLY here.
_PRESS_STATE_PATH = ROOT / "data" / "marketing" / "press" / "state.json"
_PRESS_SEEN_PATH = ROOT / "data" / "marketing" / "press" / "seen.json"
_PRESS_SEEN_CAP = 8000


# ─────────────────────────────────────────────────────────────────────────────
# Heartbeat
# ─────────────────────────────────────────────────────────────────────────────

def _touch_heartbeat(now: datetime) -> None:
    """Update the heartbeat file with current UTC timestamp."""
    try:
        _HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _HEARTBEAT_PATH.write_text(now.strftime("%Y-%m-%dT%H:%M:%SZ\n"), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[fastlane_daemon] heartbeat write failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Config + press-lane local state (gitignored; poller writes ONLY here)
# ─────────────────────────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict:
    try:
        import yaml  # noqa: PLC0415
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[fastlane_daemon] config load failed (%s): %s", path.name, exc)
        return {}


def _load_press_state() -> dict:
    if not _PRESS_STATE_PATH.exists():
        return {}
    try:
        import json  # noqa: PLC0415
        return json.loads(_PRESS_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_press_state(state: dict) -> None:
    """Atomic write of the press state (tmp + os.replace). Never git-tracked."""
    import json  # noqa: PLC0415
    _PRESS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _PRESS_STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(_PRESS_STATE_PATH)


def _load_press_seen() -> dict:
    if not _PRESS_SEEN_PATH.exists():
        return {}
    try:
        import json  # noqa: PLC0415
        return json.loads(_PRESS_SEEN_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_press_seen(seen: dict) -> None:
    import json  # noqa: PLC0415
    if len(seen) > _PRESS_SEEN_CAP:
        pairs = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:_PRESS_SEEN_CAP]
        seen = dict(pairs)
    _PRESS_SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _PRESS_SEEN_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(seen, indent=2), encoding="utf-8")
    tmp.replace(_PRESS_SEEN_PATH)


# ─────────────────────────────────────────────────────────────────────────────
# Single earnings tick (UNCHANGED behaviour)
# ─────────────────────────────────────────────────────────────────────────────

def _run_one_tick(*, dry_run: bool) -> dict:
    """Run one earnings fetch-and-process tick.  Returns the TickResult dict."""
    from engine.marketing.earnings_feed import fetch_events
    from engine.marketing.fastlane import run_tick

    now = datetime.now(timezone.utc)
    # Fetch events since a lookback window (last 30 minutes) — the seen-ledger
    # handles deduplication so overlap is safe.
    from datetime import timedelta
    since = now - timedelta(minutes=30)

    events = fetch_events(since)
    result = run_tick(events, root=ROOT, now=now, dry_run=dry_run)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Single press tick (PRESS-FEEDS B1)
# ─────────────────────────────────────────────────────────────────────────────

def _run_press_tick(*, dry_run: bool) -> dict:
    """Run one press-lane tick: poll wire RSS + press providers, then process.

    Emission is DOUBLE-gated: --dry-run OR MARKETING_PUBLISH_ENABLED-unset both
    force a no-op (pipeline runs, nothing written to the outbox). The poller
    writes ONLY to data/marketing/press/ (gitignored).
    """
    from engine.marketing import breaking_feed, press_providers
    from engine.marketing.press_lane import run_press_tick
    from engine.marketing.sentinel import publish_enabled

    now = datetime.now(timezone.utc)
    marketing_cfg = _load_yaml(ROOT / "config" / "marketing.yml")
    press_cfg = _load_yaml(ROOT / "config" / "press_sources.yml")

    # Persisted daemon-local state (cursors, ETags, spend, flagship counter, seen).
    state = _load_press_state()
    seen = _load_press_seen()

    # DRY-RUN must be non-consuming: an inspection run may never advance the wire
    # seen-ledger / provider cursors, or it would silently dedupe those items away
    # from the next LIVE run. Snapshot the wire ledger dir so we can restore it.
    _wire_ledger_snapshot = _snapshot_breaking_ledger() if dry_run else None

    # 1. Poll the wire RSS lane (breaking_feed owns its own local seen-ledger; we
    #    dedupe again below on the shared press seen so a wire item and a mirror
    #    item never double-emit). poll_all returns NEW wire items only.
    wire_items: list = []
    try:
        wire_items = breaking_feed.poll_all(ROOT, marketing_cfg.get("breaking", {}))
    except Exception as exc:  # noqa: BLE001
        logger.error("[press] wire poll_all error (continuing): %s", exc)

    # 2. Poll the press providers (mirror + x_relay). session_state carried inside
    #    the same press state dict, mutated in place, persisted below.
    provider_state = state.setdefault("providers", {})
    press_items: list = []
    try:
        press_items = press_providers.poll_all(ROOT, press_cfg, provider_state)
    except Exception as exc:  # noqa: BLE001
        logger.error("[press] provider poll_all error (continuing): %s", exc)

    all_items = list(wire_items) + list(press_items)

    # 3. Emission is only allowed when the outbox kill-switch is on AND not dry-run.
    emit_allowed = publish_enabled() and not dry_run
    effective_dry = not emit_allowed

    result = run_press_tick(
        all_items,
        root=ROOT,
        now=now,
        cfg=marketing_cfg,
        press_cfg=press_cfg,
        state=state,
        seen_ids=set(seen.keys()),
        dry_run=effective_dry,
    )

    # 4. Advance the seen-ledger for emitted items (only when we actually wrote).
    if emit_allowed:
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        for it in result.get("emitted", []):
            seen[str(it.get("id", ""))] = now_iso
        _save_press_seen(seen)

    # 5. Persist provider cursors / spend / flagship counter — but NOT in dry-run,
    #    which must leave zero footprint so it is non-consuming. NEVER a git write.
    if not dry_run:
        _save_press_state(state)
    else:
        _restore_breaking_ledger(_wire_ledger_snapshot)

    result["_emit_allowed"] = emit_allowed
    return result


def _snapshot_breaking_ledger() -> dict[str, str | None]:
    """Read the wire lane's local seen/state ledgers so a dry-run can restore them."""
    d = ROOT / "data" / "marketing" / "breaking"
    snap: dict[str, str | None] = {}
    for name in ("seen.json", "state.json"):
        p = d / name
        snap[name] = p.read_text(encoding="utf-8") if p.exists() else None
    return snap


def _restore_breaking_ledger(snap: dict[str, str | None] | None) -> None:
    """Restore the wire lane ledgers snapshotted before a dry-run poll (idempotent)."""
    if snap is None:
        return
    d = ROOT / "data" / "marketing" / "breaking"
    for name, content in snap.items():
        p = d / name
        try:
            if content is None:
                if p.exists():
                    p.unlink()
            else:
                p.write_text(content, encoding="utf-8")
        except OSError:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Log line formatter
# ─────────────────────────────────────────────────────────────────────────────

def _log_tick(result: dict, now: datetime, *, dry_run: bool) -> None:
    dry_tag = " [DRY-RUN]" if dry_run else ""
    emitted_n = len(result.get("emitted", []))
    skipped_n = len(result.get("skipped", []))
    quarantined_n = len(result.get("quarantined", []))
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    logger.info(
        "[fastlane] tick%s | emitted=%d skipped=%d quarantined=%d | %s",
        dry_tag,
        emitted_n,
        skipped_n,
        quarantined_n,
        ts,
    )
    if dry_run and emitted_n:
        for item in result["emitted"]:
            logger.info(
                "[fastlane] [DRY-RUN] would emit %s | %s | %s",
                item.get("id", "?"),
                item.get("provenance", {}).get("ticker", "?"),
                (item.get("text") or {}).get("headline", "")[:60],
            )


def _log_press_tick(result: dict, now: datetime, *, dry_run: bool) -> None:
    """One structured line per press tick + a would-emit breakdown."""
    emit_allowed = bool(result.get("_emit_allowed", not dry_run))
    dry_tag = "" if emit_allowed else " [NO-OP]"
    emitted_n = len(result.get("emitted", []))
    skipped_n = len(result.get("skipped", []))
    digest_n = len(result.get("digest", []))
    blocked_n = len(result.get("blocked", []))
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    logger.info(
        "[press] tick%s | emitted=%d skipped=%d digest=%d blocked=%d | %s",
        dry_tag, emitted_n, skipped_n, digest_n, blocked_n, ts,
    )
    for item in result.get("emitted", []):
        prov = item.get("provenance", {})
        logger.info(
            "[press] %s emit %s | sal=%s %s | %s",
            "would" if not emit_allowed else "did",
            item.get("id", "?"),
            prov.get("salience", "?"),
            prov.get("corroboration_gate", "?"),
            (item.get("text") or {}).get("headline", "")[:60],
        )
    for d in result.get("digest", []):
        logger.info("[press] -> digest %s | %s", d.get("id", "?"), d.get("reason", ""))


# ─────────────────────────────────────────────────────────────────────────────
# main()
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """Entry point.  Returns exit code."""
    parser = argparse.ArgumentParser(
        description="Marketing real-time fast-lane daemon (earnings + press)."
    )
    parser.add_argument(
        "--lane",
        choices=("earnings", "press", "all"),
        default="earnings",
        help="Which lane(s) to drive (default: earnings, for back-compat).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single tick and exit.",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Compute but write nothing to disk.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=_DEFAULT_INTERVAL_S,
        help=f"Poll interval in seconds (default: {_DEFAULT_INTERVAL_S}).",
    )
    args = parser.parse_args(argv)

    # Kill-switch: unless we are in a pure --dry-run (which writes nothing and is
    # the operator's way to inspect the pipeline), a live run requires the fast
    # lane to be explicitly armed. A dry-run is a safe no-op regardless.
    if not args.dry_run and os.environ.get(_KILL_SWITCH_ENV) != "1":
        print(
            f"[fastlane_daemon] {_KILL_SWITCH_ENV} != '1' — fast lane disabled. "
            "Set the env var to enable (or pass --dry-run to inspect). Exiting 0.",
            file=sys.stdout,
        )
        return 0

    logger.info(
        "[fastlane_daemon] starting | lane=%s once=%s dry_run=%s interval=%ds",
        args.lane, args.once, args.dry_run, args.interval,
    )

    while True:
        now = datetime.now(timezone.utc)
        try:
            if args.lane in ("earnings", "all"):
                result = _run_one_tick(dry_run=args.dry_run)
                _log_tick(result, now, dry_run=args.dry_run)
            if args.lane in ("press", "all"):
                press_result = _run_press_tick(dry_run=args.dry_run)
                _log_press_tick(press_result, now, dry_run=args.dry_run)
            if not args.dry_run:
                _touch_heartbeat(now)
        except Exception as exc:  # noqa: BLE001
            logger.error("[fastlane_daemon] tick error (continuing): %s", exc)

        if args.once:
            break

        time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    sys.exit(main())
