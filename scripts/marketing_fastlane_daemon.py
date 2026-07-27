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

def _run_one_tick(*, dry_run: bool, armed: bool = True) -> dict:
    """Run one earnings fetch-and-process tick.  Returns the TickResult dict.

    armed=False (disarmed + --dry-run inspection, m1): earnings_feed.fetch_events
    is a network read — a DISARMED tick must NOT reach it. We process an EMPTY
    event batch instead so the pipeline still runs offline-safe (parity with the
    press lane, whose billed twitterapi.io fetch is likewise skipped offline). The
    dry-run kill-switch bypass is for inspecting the pipeline, not for making
    upstream data reads while dark.
    """
    from engine.marketing.earnings_feed import fetch_events
    from engine.marketing.fastlane import run_tick

    now = datetime.now(timezone.utc)
    # Fetch events since a lookback window (last 30 minutes) — the seen-ledger
    # handles deduplication so overlap is safe.
    from datetime import timedelta
    since = now - timedelta(minutes=30)

    events = fetch_events(since) if armed else []
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

    # COLD-START (m2): true first run = neither the state nor the seen ledger file
    # exists yet. The first batch is a full history snapshot (mirror archives,
    # twitterapi.io last_tweets with no cursor); we PRIME (seed cursors + seen,
    # emit nothing) rather than flood. Detect BEFORE loading, which creates dicts.
    cold_start = not _PRESS_STATE_PATH.exists() and not _PRESS_SEEN_PATH.exists()

    # Persisted daemon-local state (cursors, ETags, spend, flagship counter, seen).
    state = _load_press_state()
    seen = _load_press_seen()

    # M2: emission is only allowed when the outbox kill-switch is on AND not
    # dry-run. Compute this BEFORE polling so a dry-run/disarmed tick can run the
    # BILLED twitterapi.io lane OFFLINE — poll_all(offline=True) returns [] for it
    # without any network read (its spend is never persisted in dry-run, so a real
    # read would bill money the monthly cap counter never sees). Free RSS/JSON
    # mirror + wire lanes still fetch so the pipeline stays inspectable.
    emit_allowed = publish_enabled() and not dry_run
    effective_dry = not emit_allowed

    # DRY-RUN must be non-consuming: an inspection run may never advance the wire
    # seen-ledger / provider cursors, or it would silently dedupe those items away
    # from the next LIVE run. Snapshot the wire ledger dir so we can restore it.
    _wire_ledger_snapshot = _snapshot_breaking_ledger() if dry_run else None

    # 1. Poll the wire RSS lane (FREE; breaking_feed owns its own local seen-ledger;
    #    we dedupe again below on the shared press seen so a wire item and a mirror
    #    item never double-emit). poll_all returns NEW wire items only.
    wire_items: list = []
    try:
        wire_items = breaking_feed.poll_all(ROOT, marketing_cfg.get("breaking", {}))
    except Exception as exc:  # noqa: BLE001
        logger.error("[press] wire poll_all error (continuing): %s", exc)

    # 2. Poll the press providers (mirror + x_relay). session_state carried inside
    #    the same press state dict, mutated in place, persisted below. offline=
    #    effective_dry keeps the BILLED twitterapi.io lane off the network in a
    #    dry-run/disarmed tick (M2); the free mirror providers still fetch.
    provider_state = state.setdefault("providers", {})
    press_items: list = []
    try:
        press_items = press_providers.poll_all(
            ROOT, press_cfg, provider_state, offline=effective_dry
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[press] provider poll_all error (continuing): %s", exc)

    all_items = list(wire_items) + list(press_items)

    # 3. Run the tick. On cold-start we PRIME (emit nothing, seed seen/cursors).
    result = run_press_tick(
        all_items,
        root=ROOT,
        now=now,
        cfg=marketing_cfg,
        press_cfg=press_cfg,
        state=state,
        seen_ids=set(seen.keys()),
        dry_run=effective_dry,
        prime=cold_start,
    )

    # NOTE (m5): single-daemon deployment assumption. The seen-ledger + provider
    # state are read-modify-written non-atomically across this function; two
    # concurrent daemons on the same data/marketing/press/ dir could race. The
    # systemd unit runs exactly ONE instance, so this is safe by deployment — do
    # not add cross-process locking without also changing that assumption.

    # 4. Advance the seen-ledger. Use run_press_tick's returned _seen (the full
    #    set AFTER the tick, including MIRROR-COLLAPSED emission keys — M1), not
    #    out_item["id"], so cross-tick mirror dedupe persists. Written on a live
    #    emit OR a cold-start prime (priming must persist the seeded seen-set, else
    #    the next tick re-floods). NEVER in a dry-run — it must stay non-consuming.
    if (emit_allowed or cold_start) and not dry_run:
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        for key in result.get("_seen", []):
            seen.setdefault(str(key), now_iso)
        _save_press_seen(seen)

    # 5. Persist provider cursors / spend / flagship counter — but NOT in dry-run,
    #    which must leave zero footprint so it is non-consuming. NEVER a git write.
    if not dry_run:
        _save_press_state(state)
    else:
        _restore_breaking_ledger(_wire_ledger_snapshot)

    # 6. B4a wires.json sink — write the news.html live-wire rail payload from
    #    the tick's rail-eligible items. Written to the VPS public live dir (or a
    #    dev data dir), NEVER the repo/git tree. Skipped in dry-run (non-consuming).
    if not dry_run:
        try:
            _write_wires_sink(result.get("rail", []), press_cfg, now)
        except Exception as exc:  # noqa: BLE001
            logger.error("[press] wires.json sink error (continuing): %s", exc)

    result["_emit_allowed"] = emit_allowed
    return result


# Where the B4a rail payload is published. VPS public live dir first (served to
# registered users via the @reg_asset default-deny route — see site_access.yml),
# repo-relative dev fallback for local runs/tests. NEVER a git-tracked path.
_WIRES_SINK_PATHS: tuple[str, ...] = (
    "/var/lib/macro-live/public/live/wires.json",
    "data/marketing/press/wires.json",
)


def _write_wires_sink(rail_items: list, press_cfg: dict, now: datetime) -> None:
    """Atomically write the wires.v1 rail payload (tmp + fsync + os.replace).

    Uses vps_live_orchestrator.atomic_write_json (the orchestrator's atomic
    publish pattern). Picks the first WRITABLE candidate directory: the VPS live
    dir when it exists, else the repo-relative dev path. This is a display-tier
    live artifact (like site/live/quotes.json), never a repo/git write.
    """
    from pathlib import Path as _Path  # noqa: PLC0415

    wire_cfg = (press_cfg or {}).get("wire", {}) if isinstance(press_cfg, dict) else {}
    candidates = list(wire_cfg.get("wires_sink_paths") or _WIRES_SINK_PATHS)

    target: _Path | None = None
    for cand in candidates:
        p = _Path(cand)
        if not p.is_absolute():
            p = ROOT / cand
        # Choose a candidate whose parent dir exists OR can be created.
        if p.parent.exists():
            target = p
            break
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            target = p
            break
        except OSError:
            continue
    if target is None:
        return

    payload = {
        "schema": "wires.v1",
        "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": list(rail_items or []),
    }
    from scripts.vps_live_orchestrator import atomic_write_json  # noqa: PLC0415
    atomic_write_json(target, payload, mode=0o644)


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
    # DEFERRED (m4): digest items are LOGGED-ONLY in B1. There is NO next-morning
    # digest sink yet — a real digest surface (a queued digest ledger + a morning
    # roll-up post) is a chartered follow-on, not part of this spine. These lines
    # are the only record a digest-gated claim leaves; do not read them as "queued
    # for a digest that exists".
    for d in result.get("digest", []):
        logger.info("[press] -> digest (logged-only, no sink — m4) %s | %s",
                    d.get("id", "?"), d.get("reason", ""))


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
    armed = os.environ.get(_KILL_SWITCH_ENV) == "1"
    if not args.dry_run and not armed:
        print(
            f"[fastlane_daemon] {_KILL_SWITCH_ENV} != '1' — fast lane disabled. "
            "Set the env var to enable (or pass --dry-run to inspect). Exiting 0.",
            file=sys.stdout,
        )
        return 0

    logger.info(
        "[fastlane_daemon] starting | lane=%s once=%s dry_run=%s armed=%s interval=%ds",
        args.lane, args.once, args.dry_run, armed, args.interval,
    )

    while True:
        now = datetime.now(timezone.utc)
        try:
            if args.lane in ("earnings", "all"):
                # m1: a DISARMED --dry-run must NOT reach earnings_feed.fetch_events
                # (network). Passing armed gates the fetch to offline-safe when dark.
                result = _run_one_tick(dry_run=args.dry_run, armed=armed)
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

        # TODO (m6): a failed poll (network error caught above) still sleeps the
        # full interval — no backoff/jitter at the daemon level. The per-source
        # conditional-GET backoff (press_providers._conditional_get) softens this
        # for RSS/JSON, but a persistently failing tick burns the fixed interval.
        # Acceptable for B1; revisit with an adaptive interval if it matters.
        time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    sys.exit(main())
