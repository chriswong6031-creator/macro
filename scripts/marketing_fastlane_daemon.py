"""scripts/marketing_fastlane_daemon.py — Runner for the marketing fast lanes.

Drives three intraday lanes:
    earnings  the original earnings fast lane (earnings_feed + fastlane.run_tick).
    press     PRESS-FEEDS B1 (D05 Addendum 2) — the Trump/markets wire spine:
              wire RSS (breaking_feed.poll_all) + press providers
              (press_providers.poll_all: trumpstruth mirror, twitterapi.io x_relay,
              CNN backfill) -> relevance -> corroboration -> summarize-with-citation
              -> persist the Intelligence Desk + live rail; optionally emit
              kind="breaking" outbox items with scheduled_at="immediate".
    reply     XG-W6 reply-desk PRODUCER — reply_producer.run_producer:
              twitterapi.io discovery (reply sub-budget, since-id cursors) ->
              deterministic scorer -> per-persona drafter -> the nine critics ->
              reply_queue.enqueue. NOTHING SENDS: output lands in the M0 queue for
              operator review, and only reply_export at M1+ hands anything to the
              desktop lane. This lane runs HERE, on the wire daemon's host, and
              never on the render path.

Usage:
    python scripts/marketing_fastlane_daemon.py [--lane earnings|press|reply|all] \
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
    MARKETING_PUBLISH_ENABLED not set  -> the press lane still reads, scores, and
                                          advances the live Intelligence Desk, but
                                          emits NOTHING to the social outbox.
                                          --dry-run forces outbound off too.

Reply-lane arming (separate from the two above — the producer bills
twitterapi.io, so it does not inherit the wire lane's switch):
    reply_desk.producer.enabled: true in config/marketing.yml, AND
    TWITTERAPI_IO_KEY in the environment. Absent either, the lane is a clean
    no-op. Sending is a further, independent step (the mode dial).

Heartbeat:
    Each successful tick touches data/marketing/fastlane_heartbeat.txt with the
    current UTC timestamp.  --dry-run skips the heartbeat write.

Press-lane local state (gitignored — data/marketing/press/):
    provider cursors / conditional-GET ETags / spend accounting / flagship counter
    / corroboration window / seen-ledger / the B4c zh translation cache.  The poller
    makes ZERO repo/git writes and advances NO forward ledger (the zh pass therefore
    keeps its cache here rather than in the git-tracked news-translation cache, and
    suppresses the lib.ai_costs append that the nightly is the sole advancer of).

No git writes.  No ledger advances.  The daemon is a fully intraday lane.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
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

# Press-lane state/cursors live under this gitignored directory. Runtime-facing
# desk/rail snapshots use /var/lib/macro-live on the VPS (with this same directory
# as the development fallback); neither location is a tracked forward ledger.
_PRESS_STATE_PATH = ROOT / "data" / "marketing" / "press" / "state.json"
_PRESS_SEEN_PATH = ROOT / "data" / "marketing" / "press" / "seen.json"
_PRESS_SEEN_CAP = 8000

#: How long an item stays "already seen" (M9). The size cap is not a horizon —
#: 8,000 entries on a busy wire day can span 48 hours, and an item that falls
#: out of the ring is eligible again: re-summarized on a billed call and posted
#: a second time as if it were new. Three weeks comfortably outlives every
#: corroboration and story-lock window this lane uses, and 8,000 entries of that
#: age is a file measured in hundreds of kilobytes.
_PRESS_SEEN_RETENTION_DAYS = 21

# XG-W5: the golden-set / eval corpus. Every item that reached the press lane
# lands here with its deterministic `_components` — the labeling exporter and the
# precision@20 harness both read it (engine/marketing/golden_set.py).
# data/marketing/press/ is GITIGNORED, so this is host state exactly like the
# cursors and the seen ledger: the poller makes zero git writes, and the nightly
# stays the sole advancer of every tracked ledger.
_PRESS_CORPUS_PATH = ROOT / "data" / "marketing" / "press" / "ingest_corpus.jsonl"
# Review F-17: both caps are CONFIG KEYS (breaking.scoring.corpus_sink), with
# these as the fallbacks a config-less checkout uses. Rolling is size-gated —
# checking "over N lines?" by reading the file would re-read tens of MB every
# 120 seconds — and the roll itself is STREAMING (see _roll_press_corpus), so
# even the rare roll never materialises the whole file inside the live tick.
_PRESS_CORPUS_CAP = 20000
_PRESS_CORPUS_MAX_BYTES = 64 * 1024 * 1024


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


def _roll_press_corpus(keep: int) -> None:
    """Truncate the corpus to its newest `keep` rows — STREAMING, two passes.

    Review F-17: the first cut did ``read_text().splitlines()`` and then joined
    the tail, which materialises the entire file PLUS a list of every line PLUS
    the rebuilt tail — three copies of a 64 MB file inside the live press tick.
    Pass one counts lines; pass two copies the tail out line by line. Peak
    memory is one line, whatever the file size.
    """
    with _PRESS_CORPUS_PATH.open("r", encoding="utf-8") as fh:
        total = sum(1 for _ in fh)
    skip = max(0, total - keep)
    tmp = _PRESS_CORPUS_PATH.with_suffix(".tmp")
    with _PRESS_CORPUS_PATH.open("r", encoding="utf-8") as src, \
            tmp.open("w", encoding="utf-8") as dst:
        for index, line in enumerate(src):
            if index >= skip:
                dst.write(line)
    tmp.replace(_PRESS_CORPUS_PATH)
    logger.info("[press] corpus rolled %d -> %d rows", total, min(total, keep))


def _append_press_corpus(rows: list, *, cfg: dict | None = None) -> int:
    """Append this tick's scoring-brain corpus rows; roll past the byte ceiling.

    Fail-soft: the corpus is a labeling/evaluation convenience, so a write error
    logs and the tick continues. NEVER runs in a dry-run (the caller gates it) —
    an inspection run must stay non-consuming.
    """
    if not rows:
        return 0
    import json  # noqa: PLC0415

    sink = (((cfg or {}).get("breaking") or {}).get("scoring") or {}).get("corpus_sink") or {}
    keep = int(sink.get("max_rows", _PRESS_CORPUS_CAP))
    max_bytes = int(sink.get("max_bytes", _PRESS_CORPUS_MAX_BYTES))
    try:
        _PRESS_CORPUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _PRESS_CORPUS_PATH.open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        if _PRESS_CORPUS_PATH.stat().st_size > max_bytes:
            _roll_press_corpus(keep)
        return len(rows)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[press] corpus append failed (continuing): %s", exc)
        return 0


def _seen_age_days(stamp: object, now: datetime) -> float:
    """Age of a seen-ledger entry in days. An unreadable stamp reads as AGE 0.

    Deliberately the safe direction: an entry we cannot date is an entry we
    cannot prove is expired, and keeping it costs a line of JSON while dropping
    it costs a duplicate post and a second billed summarizer call.
    """
    try:
        when = datetime.strptime(str(stamp)[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return 0.0
    return max((now - when).total_seconds() / 86400.0, 0.0)


def _save_press_seen(seen: dict, *, now: datetime | None = None) -> None:
    """Persist the seen ledger: age-bounded first, size-capped second (M9).

    THE CAP ALONE WAS NOT A HORIZON. Keeping the newest 8,000 entries says
    nothing about how far back they reach: on a busy wire day the ring can span
    two days, and an item that scrolls off is not "old", it is ELIGIBLE AGAIN —
    re-summarized (billed) and re-posted as new. The dedupe window a wire lane
    needs is a TIME window, so entries are kept until they are
    `_PRESS_SEEN_RETENTION_DAYS` old and only then dropped.

    When the size cap would evict something younger than that window the cap is
    too small for this feed's volume, and that is a configuration fact somebody
    has to see: the eviction still happens (the file stays bounded) but it
    annotates at LINE START with the count and the youngest age it dropped.
    """
    import json  # noqa: PLC0415

    now = now or datetime.now(timezone.utc)
    kept = {k: v for k, v in seen.items()
            if _seen_age_days(v, now) <= _PRESS_SEEN_RETENTION_DAYS}
    if len(kept) > _PRESS_SEEN_CAP:
        pairs = sorted(kept.items(), key=lambda kv: str(kv[1]), reverse=True)
        evicted = pairs[_PRESS_SEEN_CAP:]
        young = [kv for kv in evicted
                 if _seen_age_days(kv[1], now) < _PRESS_SEEN_RETENTION_DAYS]
        kept = dict(pairs[:_PRESS_SEEN_CAP])
        if young:
            youngest = min(_seen_age_days(v, now) for _, v in young)
            print(f"::warning title=press-seen-cap-under-retention::"
                  f"{len(young)} seen entries evicted before the "
                  f"{_PRESS_SEEN_RETENTION_DAYS}d dedupe window (youngest "
                  f"{youngest:.1f}d); raise _PRESS_SEEN_CAP or those items can "
                  f"re-post as new", flush=True)
    _PRESS_SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _PRESS_SEEN_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(kept, indent=2), encoding="utf-8")
    tmp.replace(_PRESS_SEEN_PATH)


# ─────────────────────────────────────────────────────────────────────────────
# Single earnings tick (UNCHANGED behaviour)
# ─────────────────────────────────────────────────────────────────────────────

def _run_one_tick(*, dry_run: bool, armed: bool = True, spool: bool = True) -> dict:
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
    since = now - timedelta(minutes=30)

    events = fetch_events(since) if armed else []
    # Card footer posture (publish.chart_cta_enabled) — the fast lane emits an
    # outbound card like every other lane, so it must not keep pitching a trial
    # button after the operator turned the CTA off network-wide.
    from engine.marketing.chart_render import chart_cta_enabled  # noqa: PLC0415
    _cfg = _load_yaml(ROOT / "config" / "marketing.yml")
    _cta = chart_cta_enabled(_cfg)
    # cfg is threaded through (XG-W2) so the lane can resolve wire routing, the
    # one-owner lock window and the cross-account near-dup threshold from config
    # rather than from in-code fallbacks.
    # spool=True (XG-W2): the daemon's emissions go to the GITIGNORED
    # data/marketing/outbox/items-host.jsonl, never the git-TRACKED
    # items.jsonl. This daemon runs on the VPS, whose checkout is refreshed
    # by a 3-minute `git pull`; dirtying a tracked file there would conflict
    # that pull. House law: the poller makes zero git writes.
    result = run_tick(events, root=ROOT, now=now, dry_run=dry_run, cta=_cta,
                      cfg=_cfg, spool=spool)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Single reply-producer tick (XG-W6)
# ─────────────────────────────────────────────────────────────────────────────

def _run_reply_tick(*, dry_run: bool) -> dict:
    """Run one reply-desk producer tick: discover -> score -> draft -> critics -> enqueue.

    NOTHING SENDS. The producer fills the M0 queue; the mode dial and
    ``reply_export`` decide, separately and later, whether anything ever leaves.

    Zero repo writes: the queue and the discovery cursors live in host state
    (``~/.mastermind/reply_desk``), and the only in-checkout write is the
    gitignored labels host spool.

    ``--dry-run`` maps to the producer's ``offline=True``, which is the dry-run
    law for a BILLED provider: zero network, zero spend, and therefore zero
    targets. The tick still reports what it would have done with an empty
    target list rather than simulating one.
    """
    from engine.marketing.reply_producer import run_producer

    now = datetime.now(timezone.utc)
    marketing_cfg = _load_yaml(ROOT / "config" / "marketing.yml")
    press_cfg = _load_yaml(ROOT / "config" / "press_sources.yml")

    return run_producer(
        cfg=marketing_cfg,
        press_cfg=press_cfg,
        root=ROOT,
        # store=None resolves to the reply desk's own host-state root
        # (MASTERMIND_REPLY_DESK_DIR, else ~/.mastermind/reply_desk).
        store=None,
        now=now,
        offline=bool(dry_run),
    )


def _log_reply_tick(result: dict, now: datetime, *, dry_run: bool) -> None:
    tag = " [DRY-RUN]" if dry_run else ""
    if not result.get("enabled"):
        logger.info("[reply]%s tick skipped — %s", tag,
                    result.get("note") or "producer disabled")
        return
    logger.info(
        "[reply]%s tick | targets=%d eligible=%d drafted=%d critic_rejected=%d "
        "enqueued=%d abstained=%d halted=%s spend=%s",
        tag, result.get("targets", 0), result.get("eligible", 0),
        result.get("drafted", 0), result.get("critic_rejected", 0),
        result.get("enqueued", 0), result.get("abstained", 0),
        result.get("halted") or [], result.get("spend") or {},
    )
    for refusal in (result.get("refused") or [])[:5]:
        logger.info("[reply] refused: %s", refusal)


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
    # dry-run. This controls WRITES to the social outbox, not intelligence reads.
    # Explicit --dry-run is the only mode that takes the billed twitterapi.io lane
    # offline, because a non-consuming inspection cannot persist its spend. A
    # normal outbound-dark tick still polls within the configured hard budget and
    # advances the Intelligence Desk.
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
    #    --dry-run keeps the BILLED twitterapi.io lane off the network. Publishing
    #    being disabled does NOT disable intelligence collection: the live desk
    #    and its capped read budget are separate from outbound X authorization.
    provider_state = state.setdefault("providers", {})
    press_items: list = []
    try:
        # offline keys on the EXPLICIT dry-run only. `effective_dry` folds the
        # outbox arm in, and routing it here made the publish switch disable
        # intelligence COLLECTION — the exact defect the intelligence-desk
        # session fixed on main (its scan test pins the literal below).
        press_items = press_providers.poll_all(
            ROOT, press_cfg, provider_state, offline=dry_run, now=now
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
        # See the earnings lane above: daemon-side emissions spool to the
        # gitignored sibling so the VPS checkout stays clean.
        spool=True,
    )

    # NOTE (m5): single-daemon deployment assumption. The seen-ledger + provider
    # state are read-modify-written non-atomically across this function; two
    # concurrent daemons on the same data/marketing/press/ dir could race. The
    # systemd unit runs exactly ONE instance, so this is safe by deployment — do
    # not add cross-process locking without also changing that assumption.

    # 4. Advance the seen-ledger. Use run_press_tick's returned _seen (the full
    #    set AFTER the tick, including MIRROR-COLLAPSED emission keys — M1), not
    #    out_item["id"], so cross-tick mirror dedupe persists.
    #
    #    PERSISTED ON EVERY REAL TICK, armed or not (M8). This used to require
    #    `emit_allowed`, i.e. the publish kill switch — which is DARK by default.
    #    A disarmed tick still polls, still scores, and still pays the billed
    #    summarizer for every item, so gating the ledger on the switch meant the
    #    lane re-summarized the same wire items every two minutes, forever,
    #    while nothing posted. The switch decides whether we PUBLISH; it has
    #    never had anything to say about whether we already did the work.
    #
    #    The one exception stays: an explicit `--dry-run` is an inspection and
    #    must be non-consuming, or it would dedupe items away from the next live
    #    run. A cold-start prime writes for the same reason it always did.
    if not dry_run:
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        for key in result.get("_seen", []):
            seen.setdefault(str(key), now_iso)
        _save_press_seen(seen, now=now)

    # 4b. XG-W5 scoring-brain corpus. Every item the lane saw this tick, with its
    #     deterministic `_components`, appended to the GITIGNORED host-local
    #     corpus that feeds the labeling exporter and the precision@20 harness.
    #     Skipped in dry-run for the same non-consuming reason as everything else.
    if not dry_run:
        _append_press_corpus(result.get("corpus", []), cfg=marketing_cfg)

    # 5. Persist provider cursors / spend / flagship counter — but NOT in dry-run,
    #    which must leave zero footprint so it is non-consuming. NEVER a git write.
    if not dry_run:
        _save_press_state(state)
    else:
        _restore_breaking_ledger(_wire_ledger_snapshot)

    # 6. Intelligence Desk — merge this tick's story packets into the host-local
    #    SQLite store and atomically publish live/intelligence.json. This advances
    #    while outbound X is dark; only explicit --dry-run is non-consuming.
    if not dry_run:
        try:
            from engine.marketing.intelligence_desk import (  # noqa: PLC0415
                update_intelligence_desk,
            )
            intelligence_cfg = (
                ((press_cfg or {}).get("wire") or {}).get("intelligence") or {}
            )
            desk_packets = result.get("intelligence", [])
            # V2 §D — ENRICH BEFORE TRANSLATE BEFORE MERGE. The order is load
            # bearing: the LLM pass may replace `why_it_matters_en`, and the zh
            # pass has to see that replacement to buy the matching twin.
            #
            # The phrasing pass lives HERE and not in run_press_tick because that
            # function also runs inside GitHub Actions
            # (scripts/marketing_press_wire.py), where the intelligence list is
            # discarded — model spend there would buy nothing at all.
            _attach_desk_llm(desk_packets, intelligence_cfg, now)
            _attach_desk_context(desk_packets, intelligence_cfg, now)
            # Bilingual BEFORE the merge, so the store persists the twin with the
            # English it was translated from (the merge drops a zh whose original
            # moved on). Budgeted, cached, and fail-soft — see _attach_desk_zh.
            _attach_desk_zh(desk_packets, intelligence_cfg)
            snapshot = update_intelligence_desk(
                desk_packets,
                root=ROOT,
                now=now,
                cfg=intelligence_cfg,
            )
            result["_intelligence_health"] = snapshot.get("health", {})
        except Exception as exc:  # noqa: BLE001
            logger.error("[press] intelligence desk sink error (continuing): %s", exc)

    # 7. B4a wires.json sink — write the news.html live-wire rail payload from
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

# M1: rolling-window cap. Each press tick's rail carries only THIS tick's newly
# seen items above the floor, so a quiet tick's rail is near-empty. The sink must
# therefore MERGE the tick's items into the persisted window and cap the result,
# not overwrite — otherwise the wire rail blanks the moment nothing new crosses.
_DEFAULT_WIRES_RAIL_MAX = 50
# Age bound as well as a count bound: the count alone lets a quiet feed serve
# days-old items as if they were the live wire.
_DEFAULT_WIRES_MAX_AGE_H = 48.0


def _wires_sink_target(press_cfg: dict) -> "Path | None":
    """First writable sink path: the VPS live dir when present, else the dev path.

    Returned so the READ (existing window) and the WRITE (merged window) use the
    SAME file — reading one candidate and writing another would lose history.
    """
    wire_cfg = (press_cfg or {}).get("wire", {}) if isinstance(press_cfg, dict) else {}
    candidates = list(wire_cfg.get("wires_sink_paths") or _WIRES_SINK_PATHS)
    for cand in candidates:
        p = Path(cand)
        if not p.is_absolute():
            p = ROOT / cand
        # Choose a candidate whose parent dir exists OR can be created.
        if p.parent.exists():
            return p
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
        except OSError:
            continue
    return None


def _read_existing_wires(target: Path) -> list[dict]:
    """Read the persisted wires.v1 items list (fail-soft).

    Missing file OR corrupt/unexpected JSON => [] (start fresh, log a warning) so a
    single bad write never wedges the rolling window. Never raises.
    """
    if not target.exists():
        return []
    try:
        import json  # noqa: PLC0415
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[press] wires.json unreadable (%s: %s) — starting a fresh window",
            target, exc,
        )
        return []
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    # Keep only well-shaped dict items carrying an id (defensive against a
    # partially-corrupt file that still parsed as JSON).
    return [it for it in items if isinstance(it, dict) and it.get("id")]


def _wire_sort_key(item: dict) -> str:
    """Sort key for newest-first ordering: the item's ts (published_at ISO). A
    missing/blank ts sorts oldest (empty string < any real ISO timestamp)."""
    return str(item.get("ts") or "")


def _merge_wires_window(
    existing: list[dict],
    new_items: list,
    rail_max: int,
    wire_cfg: dict | None = None,
    *,
    now: datetime | None = None,
) -> list[dict]:
    """Merge this tick's rail items into the persisted window (M1).

    `now` IS THE TICK'S CLOCK, passed in by the caller. This function used to
    re-read ``datetime.now`` for the age cutoff even though ``_write_wires_sink``
    already holds the tick's `now` and stamps it into the payload — so the sink
    aged items against a different instant than the one it published, and a test
    or fixture pinned to a past date silently lost every item once wall-clock
    drifted past ``rail_max_age_h``. (That is the class of scheduled red the
    house calls a fixture-date + wall-clock bomb; it detonated here on
    2026-07-29 against 2026-07-27 fixtures at a 48h horizon.) None falls back to
    the wall clock for the ad-hoc callers that have no tick.

    - Merge by item id; a NEW item wins field-by-field, but a field the new copy
      LACKS keeps the persisted value. The one that matters is `zh`: an item that
      re-arrives on a later tick (a recomposed body, a tape stamp attached late)
      arrives untranslated, and a blind replace would drop a translation we have
      already paid for and re-buy it next tick.
    - Sort newest-first by ts.
    - Drop items older than max_age_h. Without this the window is bounded only by
      COUNT, so a quiet feed keeps serving days-old items forever — and the rail
      would present them as the current wire.
    - Cap at rail_max (keep the newest).
    """
    by_id: dict[str, dict] = {}
    for it in existing:
        if isinstance(it, dict) and it.get("id"):
            by_id[str(it["id"])] = it
    for it in new_items or []:
        if not isinstance(it, dict) or not it.get("id"):
            continue
        key = str(it["id"])
        old = by_id.get(key)
        by_id[key] = {**old, **it} if isinstance(old, dict) else it

    merged = sorted(by_id.values(), key=_wire_sort_key, reverse=True)

    cfg = wire_cfg or {}
    try:
        max_age_h = float(cfg.get("rail_max_age_h", _DEFAULT_WIRES_MAX_AGE_H))
    except (TypeError, ValueError):
        max_age_h = _DEFAULT_WIRES_MAX_AGE_H
    if max_age_h > 0:
        # `now` is threaded from the tick clock (tests freeze it) — computing it
        # here from the wall clock made every frozen-fixture suite a date bomb:
        # tests/test_marketing_press_copy.py went red at 2026-07-29T12:00Z when
        # its 2026-07-27T12:0x fixtures crossed the 48h window (the documented
        # fixture-date-plus-wall-clock-gate class; detonated on ci-pack-3).
        reference_now = now or datetime.now(timezone.utc)
        if reference_now.tzinfo is None:
            reference_now = reference_now.replace(tzinfo=timezone.utc)
        cutoff = reference_now.astimezone(timezone.utc) - timedelta(hours=max_age_h)

        def _fresh(it: dict) -> bool:
            raw = str(it.get("ts") or "")
            if not raw:
                return True          # unparseable ts: keep, the count cap still bounds it
            try:
                ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return True
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts >= cutoff

        merged = [it for it in merged if _fresh(it)]

    if rail_max > 0:
        merged = merged[:rail_max]
    return merged


# B4c: where the wire lane's translation cache lives. The shared news-translation
# cache (data/news_translation/cache/) is git-TRACKED and the nightly commits it;
# this daemon runs against a deployed checkout that update.sh hard-resets every
# few minutes, so writing there both dirties the work-tree (D05 W0 zero-repo-
# writes law) and throws the cache away on the next reset. data/marketing/press/
# is gitignored and is already this lane's own state directory.
_WIRES_ZH_CACHE = "data/marketing/press/zh_cache"

# One batch per tick, matching news_translate's own batch_size. The tick budget is
# ~75s and the heartbeat only touches AFTER it returns, so the zh pass may never
# be the thing that makes a healthy daemon look dead. Items past the cap keep
# their English text and the client's plain 英文原文 marker, and roll into the
# next tick — the rolling window means they are still there.
_WIRES_ZH_PER_TICK = 16
_WIRES_ZH_TIMEOUT_S = 20.0


def _zh_cfg(wire_cfg: dict) -> dict:
    """Translation config for the wire lane — nothing it writes lands in the repo.

    `cache_dir` is made ABSOLUTE under the gitignored lane directory, and
    `usage_sink: none` suppresses the lib.ai_costs append: data/ai_costs/usage.jsonl
    is a forward ledger that the nightly is the sole advancer of, and an intraday
    poller must not append to it. The spend is surfaced instead in this lane's own
    log line and in the wires payload meta, both of which are host state.
    """
    from lib import config as _config  # noqa: PLC0415
    base = dict(_config.load().get("news_translation", {}) or {})
    base.update({
        "cache_dir": str((ROOT / _WIRES_ZH_CACHE).resolve()),
        "usage_sink": "none",
        "usage_lane": "press-wire-zh",
        "timeout_s": float(wire_cfg.get("zh_timeout_s", _WIRES_ZH_TIMEOUT_S)),
        "max_retries": 0,
        # Wire bodies run to the wire_deep budget (~700 chars); the shared default
        # of 360 would truncate them mid-sentence.
        "max_chars": int(wire_cfg.get("zh_max_chars", 700)),
    })
    return base


def _attach_zh(new_items: list, wire_cfg: dict,
               have_zh: set[str] | frozenset[str] = frozenset()) -> tuple[int, int]:
    """B4c: give this tick's NEW rail items a Chinese twin, in place (fail-soft).

    The news.html rail is a bilingual surface, but wire copy arrives in English.
    Only items entering the window this tick are translated. `have_zh` carries the
    ids the PERSISTED window already has a twin for, and they are skipped: an item
    re-arrives on later ticks (a recomposed body, a tape stamp attached late) with
    no `zh` on it, and without this it would be re-sent every tick for as long as
    it stays in the window — the merge would then throw the freshly-bought
    translation away in favour of the persisted one. The text-hash cache usually
    absorbs that, but "usually free" is not a budget, and one cache wipe would turn
    it into a real per-tick bill.

    The trailing " · <tape_stamp>" is stripped before translating: the stamp is a
    language-neutral "LABEL ±X.X%" that the rail re-renders from the structured
    field with its own bilingual gloss, so sending it to the model would both cost
    tokens and produce a mangled duplicate.

    Fail-soft is the whole contract: translate_to_zh returns None per item when
    the feature is disabled, unkeyed, rate-limited or malformed, and the item then
    simply ships without `zh`. The client renders the English with a plain
    "英文原文" marker rather than passing English off as translated, so a dead
    translator degrades to honest disclosure, never to a blank rail.

    Returns (filled, attempted) for the caller's log/meta line.
    """
    # Default OFF in code: deleting the config key must DISARM the spend, never
    # silently arm it. config/press_sources.yml carries the explicit `true`.
    if not new_items or not wire_cfg.get("zh_enabled", False):
        return (0, 0)
    pending = [it for it in new_items
               if isinstance(it, dict) and it.get("en") and not it.get("zh")
               and str(it.get("id", "")) not in have_zh]
    if not pending:
        return (0, 0)
    try:
        per_tick = int(wire_cfg.get("zh_per_tick", _WIRES_ZH_PER_TICK))
    except (TypeError, ValueError):
        per_tick = _WIRES_ZH_PER_TICK
    if per_tick > 0:
        pending = pending[:per_tick]

    def _strip_stamp(it: dict) -> str:
        text = str(it.get("en") or "")
        stamp = str(it.get("tape_stamp") or "")
        tail = " · " + stamp
        return text[:-len(tail)] if stamp and text.endswith(tail) else text

    cfg = _zh_cfg(wire_cfg)
    try:
        from engine.news_translate import translate_to_zh  # noqa: PLC0415
        out = translate_to_zh([_strip_stamp(it) for it in pending], cfg)
    except Exception as exc:  # noqa: BLE001 — a translator fault never breaks the sink
        logger.warning("[press] wires zh translation skipped (%s: %s)",
                       type(exc).__name__, exc)
        return (0, len(pending))
    filled = 0
    for it, zh in zip(pending, out or [], strict=False):
        zh_s = str(zh).strip() if zh else ""
        if zh_s and zh_s != _strip_stamp(it).strip():
            it["zh"] = zh_s
            filled += 1
    if filled < len(pending):
        # One line, not one per item: a keyless host would otherwise log a wall.
        logger.info("[press] wires zh: %d/%d translated (the rest ship as English "
                    "with the 英文原文 marker)", filled, len(pending))
    return (filled, len(pending))


def _zh_preflight(wire_cfg: dict) -> None:
    """One notice when the zh pass is armed but cannot possibly run.

    DEEPSEEK_API_KEY is not provisioned in the VPS unit today, so without this the
    lane is silently English-only forever and looks like a rail bug rather than a
    missing secret.
    """
    if not wire_cfg.get("zh_enabled", False):
        return
    cfg = _zh_cfg(wire_cfg)
    if not cfg.get("enabled"):
        logger.info("[press] wires zh armed but news_translation.enabled is false "
                    "— items ship English-only")
        return
    from lib import config as _config  # noqa: PLC0415
    if not _config.secret(cfg.get("api_key_env", "DEEPSEEK_API_KEY")):
        logger.warning("[press] wires zh armed but %s is not set on this host "
                       "— items ship English-only (see docs/marketing_publisher_runbook.md)",
                       cfg.get("api_key_env", "DEEPSEEK_API_KEY"))


def _attach_desk_llm(packets: list, intelligence_cfg: dict,
                     now: datetime) -> dict:
    """V2 §D.1/D.2: let the model PHRASE this tick's confirmed stories (in place).

    Thin, fail-soft wrapper around engine.marketing.intelligence_llm. The engine
    computed every fact; the model only words them, and every gate hit hands the
    story back its deterministic draft and canned why. DAEMON-ONLY by design —
    run_press_tick also executes in GitHub Actions, where the desk list is thrown
    away.

    An enrichment fault must NEVER stop the desk sink: the whole point of the
    desk is that it keeps collecting while the extras degrade.
    """
    try:
        from engine.marketing.intelligence_llm import attach_llm_drafts  # noqa: PLC0415
        return attach_llm_drafts(
            packets,
            intelligence_cfg if isinstance(intelligence_cfg, dict) else {},
            root=ROOT,
            now=now,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[press] desk phrasing skipped (%s: %s)",
                       type(exc).__name__, exc)
        return {}


def _attach_desk_context(packets: list, intelligence_cfg: dict,
                         now: datetime) -> int:
    """V2 §D.3: join story tickers against the committed engine artifacts.

    Congress / insider / earnings facts, counted from artifact rows and phrased
    by a fixed bilingual template. NO LLM anywhere in that module: these lines
    are engine facts, each carrying the artifact's own as_of, and a stale
    artifact yields no line rather than a stale one.
    """
    try:
        from engine.marketing.intelligence_context import (  # noqa: PLC0415
            attach_engine_context,
        )
        return attach_engine_context(
            packets,
            intelligence_cfg if isinstance(intelligence_cfg, dict) else {},
            root=ROOT,
            now=now,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[press] desk engine context skipped (%s: %s)",
                       type(exc).__name__, exc)
        return 0


# Desk packets are heavier than rail lines (a headline AND a brief each), and the
# desk is a durable layer — an untranslated packet is still there next tick. A
# smaller per-tick budget than the rail's is therefore the right default.
_DESK_ZH_PER_TICK = 10


def _attach_desk_zh(packets: list, intelligence_cfg: dict) -> tuple[int, int]:
    """Give this tick's Intelligence Desk packets Chinese twins, in place.

    The SAME seam as the rail's `_attach_zh`: engine.news_translate.translate_to_zh
    through `_zh_cfg` (host-local cache dir, no ai_costs append, no repo write).
    The story layer shipped English-only on a bilingual-by-law site while the
    cached translator sat one function away.

    Fail-soft end to end: no key / disabled / rate-limited / malformed returns None
    per item and the packet simply ships without `headline_zh`, which the client
    renders as English with the plain 英文原文 marker. The desk merge additionally
    DROPS a zh twin whose English original moved on, so a stale pair is never
    served.

    Budget: `zh_per_tick` PACKETS per tick (not strings — a packet costs one to
    three translations). The text-hash cache absorbs the repeats of a story that
    stays on the desk for hours.

    V2 §D: a packet whose `why_it_matters_en` was PHRASED by the LLM pass
    (`_why_phrased`) also gets its why translated here, on the same seam and the
    same budget. Ordering guarantees the phrasing already happened — see the
    step-6 hook order. A packet whose why is still the canned per-class line is
    NOT re-translated: that line already ships with a house zh twin.

    Returns (packets_filled, packets_attempted) for the caller's log line.
    """
    cfg_in = intelligence_cfg if isinstance(intelligence_cfg, dict) else {}
    # Default OFF in code, exactly like the rail: deleting the config key must
    # DISARM the spend, never silently arm it.
    if not packets or not cfg_in.get("zh_enabled", False):
        return (0, 0)

    def _wants_zh(packet: object) -> bool:
        if not isinstance(packet, dict):
            return False
        if str(packet.get("headline") or "").strip() and not packet.get("headline_zh"):
            return True
        return bool(packet.get("_why_phrased")
                    and str(packet.get("why_it_matters_en") or "").strip())

    pending = [p for p in packets if _wants_zh(p)]
    if not pending:
        return (0, 0)
    try:
        per_tick = int(cfg_in.get("zh_per_tick", _DESK_ZH_PER_TICK))
    except (TypeError, ValueError):
        per_tick = _DESK_ZH_PER_TICK
    if per_tick > 0:
        pending = pending[:per_tick]

    texts: list[str] = []
    slots: list[tuple[dict, str]] = []
    for packet in pending:
        head = str(packet.get("headline") or "").strip()
        brief = str(packet.get("brief") or "").strip()
        if head and not packet.get("headline_zh"):
            texts.append(head)
            slots.append((packet, "headline_zh"))
            # `_plain_brief` returns the headline verbatim when there is no body;
            # paying twice for one string is not a budget.
            if brief and brief != head and not packet.get("brief_zh"):
                texts.append(brief)
                slots.append((packet, "brief_zh"))
        why = str(packet.get("why_it_matters_en") or "").strip()
        if packet.get("_why_phrased") and why:
            # The canned zh twin stays in place until this lands, so a failed or
            # unbudgeted translation degrades to the generically-true house line
            # for the event class rather than to a blank.
            texts.append(why)
            slots.append((packet, "why_it_matters_zh"))

    try:
        # `_zh_cfg` reads config.yml and coerces `zh_timeout_s` / `zh_max_chars`,
        # so it belongs INSIDE the guard: it is the one line of this pass that can
        # raise on a mistyped config value, and step 6 wraps all three enrichment
        # stages in a single try — an escape here skips `update_intelligence_desk`
        # itself, freezing the desk snapshot every tick behind a heartbeat that
        # keeps ticking. The other two stages (`_attach_desk_llm`,
        # `_attach_desk_context`) already swallow everything; this one must too.
        cfg = _zh_cfg(cfg_in)
        from engine.news_translate import translate_to_zh  # noqa: PLC0415
        out = translate_to_zh(texts, cfg)
    except Exception as exc:  # noqa: BLE001 — a translator fault never breaks the desk
        logger.warning("[press] desk zh translation skipped (%s: %s)",
                       type(exc).__name__, exc)
        return (0, len(pending))

    # Count PACKETS that gained a twin, not fields: a story whose headline was
    # already translated and that only needed a why twin still counts as served,
    # and the log line would otherwise read "0/1" on a perfectly good pass.
    served: set[int] = set()
    for (packet, field), zh, source_text in zip(slots, out or [], texts,
                                                strict=False):
        zh_s = str(zh).strip() if zh else ""
        if zh_s and zh_s != source_text.strip():
            packet[field] = zh_s
            served.add(id(packet))
    filled = len(served)
    for packet in pending:
        # One translation covers both fields when the brief IS the headline.
        if (packet.get("headline_zh") and not packet.get("brief_zh")
                and str(packet.get("brief") or "").strip()
                == str(packet.get("headline") or "").strip()):
            packet["brief_zh"] = packet["headline_zh"]
    if filled < len(pending):
        logger.info("[press] desk zh: %d/%d stories translated (the rest ship as "
                    "English with the 英文原文 marker)", filled, len(pending))
    return (filled, len(pending))


def _write_wires_sink(rail_items: list, press_cfg: dict, now: datetime) -> None:
    """Atomically publish the wires.v1 rolling-window rail payload (M1).

    Reads the persisted window, MERGES this tick's rail items (merge by id, new
    wins), sorts newest-first, caps at rail_max_items, then atomic-writes (tmp +
    fsync + os.replace via vps_live_orchestrator.atomic_write_json). A quiet tick
    (zero new items) therefore leaves the existing window intact rather than
    blanking it. Corrupt/missing existing file => fresh window (fail-soft, logged).
    This is a display-tier live artifact (like site/live/quotes.json), never a
    repo/git write.
    """
    target = _wires_sink_target(press_cfg)
    if target is None:
        return

    wire_cfg = (press_cfg or {}).get("wire", {}) if isinstance(press_cfg, dict) else {}
    try:
        rail_max = int(wire_cfg.get("rail_max_items", _DEFAULT_WIRES_RAIL_MAX))
    except (TypeError, ValueError):
        rail_max = _DEFAULT_WIRES_RAIL_MAX

    # B4c: translate before the merge, so a persisted item keeps the `zh` it was
    # given on the tick it arrived and is never re-translated.
    # Read the persisted window BEFORE translating: it tells the zh pass which ids
    # already have a twin we paid for, so a re-arriving item is never re-sent.
    existing = _read_existing_wires(target)
    have_zh = {str(it.get("id")) for it in existing if isinstance(it, dict) and it.get("zh")}

    _zh_preflight(wire_cfg)
    zh_filled, zh_tried = _attach_zh(rail_items, wire_cfg, have_zh)

    # ONE CLOCK PER TICK: the same `now` that stamps `updated_at` below ages the
    # window, so the payload can never claim a freshness it did not apply.
    merged = _merge_wires_window(
        existing, rail_items, rail_max, wire_cfg, now=now
    )

    payload = {
        "schema": "wires.v1",
        "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": merged,
    }
    if zh_tried:
        # Lane spend/effort visible in host state, since this lane deliberately
        # does not append to the nightly-owned data/ai_costs ledger.
        payload["zh"] = {"translated": zh_filled, "attempted": zh_tried}
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

def _src(item: dict) -> dict:
    """An outbox item's `source` record, always a dict.

    XG-W2 moved the rich per-item record from `provenance` (now a lane slug
    string) to `source`. Defensive against BOTH shapes so a log helper can never
    raise: an exception here is caught by the tick loop's broad except, which
    then SKIPS _touch_heartbeat — a formatting bug would present as a frozen
    heartbeat, i.e. as a dead daemon.
    """
    src = item.get("source")
    if isinstance(src, dict):
        return src
    legacy = item.get("provenance")
    return legacy if isinstance(legacy, dict) else {}


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
            # XG-W2 item shape: `provenance` is a lane SLUG string and the rich
            # event record moved to `source`; `text` is the flattened post
            # string with the two halves kept as top-level headline/body.
            # Reading either as a dict raises AttributeError, and the tick loop's
            # broad except would swallow it AND skip _touch_heartbeat — a log
            # helper must never be able to freeze the heartbeat.
            logger.info(
                "[fastlane] [DRY-RUN] would emit %s | %s | %s",
                item.get("id", "?"),
                _src(item).get("ticker", "?"),
                str(item.get("headline") or item.get("text") or "")[:60],
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
    # Desk health rides the SAME line: a desk that stopped merging (or a store
    # that quarantined itself) used to be invisible in the tick log, so the only
    # signal was a stale live/intelligence.json nobody was watching. `.get` all
    # the way down — this helper runs before the heartbeat touch, so a missing
    # key here would present as a dead daemon.
    health = result.get("_intelligence_health")
    desk = ""
    if isinstance(health, dict):
        desk = " | desk active=%s confirmed=%s drafts=%s" % (
            health.get("active_stories", "?"),
            health.get("confirmed", "?"),
            health.get("draft_ready", "?"),
        )
    logger.info(
        "[press] tick%s | emitted=%d skipped=%d digest=%d blocked=%d%s | %s",
        dry_tag, emitted_n, skipped_n, digest_n, blocked_n, desk, ts,
    )
    for item in result.get("emitted", []):
        # XG-W2 item shape — see _src(). This loop runs on EVERY emitting tick
        # (not just dry-run), so it is the hot path: a dict accessor on the now-
        # string `provenance`/`text` raised AttributeError, the tick loop's broad
        # except swallowed it, and _touch_heartbeat never ran. A frozen heartbeat
        # reads as a dead daemon, which is the worst possible way for a log-line
        # bug to surface.
        src = _src(item)
        logger.info(
            "[press] %s emit %s | sal=%s %s | %s",
            "would" if not emit_allowed else "did",
            item.get("id", "?"),
            src.get("salience", "?"),
            src.get("corroboration_gate", "?"),
            str(item.get("headline") or item.get("text") or "")[:60],
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
        choices=("earnings", "press", "reply", "all"),
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
    parser.add_argument(
        "--no-spool",
        dest="spool",
        action="store_false",
        default=True,
        help=(
            "Emit to the git-TRACKED outbox (data/marketing/outbox/items.jsonl) "
            "instead of the host spool. For the GitHub Actions lane, which "
            "commits what it queues; the VPS daemon keeps the spool default "
            "because dirtying a tracked file there conflicts its 3-minute pull."
        ),
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
                result = _run_one_tick(dry_run=args.dry_run, armed=armed, spool=args.spool)
                _log_tick(result, now, dry_run=args.dry_run)
            if args.lane in ("press", "all"):
                press_result = _run_press_tick(dry_run=args.dry_run)
                _log_press_tick(press_result, now, dry_run=args.dry_run)
            if args.lane in ("reply", "all"):
                # XG-W6 reply-desk producer. Its own config gate
                # (reply_desk.producer.enabled) keeps it dark by default, so
                # `--lane all` on an unarmed deployment is a logged no-op rather
                # than a surprise spend against the twitterapi.io bucket.
                reply_result = _run_reply_tick(dry_run=args.dry_run)
                _log_reply_tick(reply_result, now, dry_run=args.dry_run)
            if not args.dry_run:
                _touch_heartbeat(now)
        except Exception as exc:  # noqa: BLE001
            # A DAEMON THAT SWALLOWS EVERY TICK LOOKS IDENTICAL TO A QUIET DAY.
            # Continuing is right — one bad poll must not kill the loop — but the
            # only trace was a `logger.error`, and this repo's builders log with a
            # prefixing format, so GitHub drops it from the Actions summary and
            # the workflow still exits 0. A lane erroring on EVERY pass would show
            # up as nothing at all.
            #
            # Demonstrated the hard way (2026-07-31): adding a `spool` kwarg to
            # _run_one_tick without updating a stub made every tick raise
            # TypeError here, and the visible result was simply zero posts.
            print(f"::warning title=marketing-fastlane-tick-error::"
                  f"lane={args.lane} tick raised and was skipped: "
                  f"{type(exc).__name__}: {exc}. The loop continues, so a lane "
                  f"failing every pass reports no posts rather than an error.",
                  flush=True)
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
