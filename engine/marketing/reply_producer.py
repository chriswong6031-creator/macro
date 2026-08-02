"""engine/marketing/reply_producer.py — the reply desk's PRODUCER (XG-W6).

XG-W4 built every piece and deliberately shipped no connective tissue; its own
``reply_queue`` docstring says so:

    "The connective tissue that walks discovery output through the scorer and
     drafter and enqueues survivors is NOT in this wave — it lands in XG-W6."

This module is that tissue:

    discovery -> score -> draft -> critics -> enqueue

and nothing beyond it. **Nothing here sends.** The mode dial is untouched by
this wave: output lands in the M0 queue, where an operator sees it in the admin
rail, and only ``reply_export`` at M1+ hands anything to the desktop lane.

**It builds ON the store's guarantee, never around it.**
``reply_queue.validate_critic_stamp`` refuses any item without a full passing
critic stamp. This producer therefore does not decide what "cleared the critics"
means — it runs ``reply_critics.screen`` and hands the resulting stamp to
``make_item``. If a future edit here dropped the critic call, ``enqueue`` would
reject every item rather than admit unscreened drafts. That is the intended
failure mode and ``tests/test_marketing_reply_producer.py`` pins it.

**Where it runs.** ``scripts/marketing_fastlane_daemon.py --lane reply`` — the
same daemon and the same host as the wire lane (VPS), never the render path.
It makes ZERO repo writes: discovery cursors and this lane's spend live in host
state, the queue lives in host state, and the only in-repo write is the
gitignored labels host spool.

**Spend.** Reuses XG-W4's accounting wholesale: ``reply_discovery.run_tick``
loads/saves the host spend counter, reads the wire's spend off disk
(``load_wire_spend``), and enforces both the reply sub-cap and the shared
twitterapi.io bucket stop. This module adds no second budget and no second
counter — a lane with two budgets has none.

**Halted accounts produce nothing.** ``health_monitor.is_halted`` is checked
per account before any billed request is made for it, so a halted desk costs
neither money nor drafts while it is dark.

**A SILENT DESK IS THE FAILURE MODE.** Every gate above is a legal reason to
produce nothing, and until XG-W7 they were all indistinguishable from each
other AND from a dead daemon: the tick logged one INFO line of zeroes and moved
on. Four separate switches (the systemd lane, ``producer.enabled``, the author
register, ``TWITTERAPI_IO_KEY``) each fail that way, which is how a desk stays
dark for months while an operator believes it is armed. So this module now
carries its own observability:

    * ``heartbeat_path``/``read_heartbeat`` — a host-state artifact written on
      every live tick, carrying the tick counter, the consecutive-empty run and
      the last tick's stage counts. A frozen file means the daemon is dead; a
      climbing ``consecutive_empty`` means it is alive and finding nothing.
    * a start-of-line ``::warning title=reply-desk-silent::`` after
      ``silent_tick_warn_after`` consecutive ticks that enqueued nothing, whose
      text names the FIRST stage that zeroed rather than reporting the zero.
    * ``preflight()`` — an offline, zero-spend, zero-write readiness readout an
      operator runs BEFORE arming (``--lane reply --preflight``), so the
      placeholder register and the missing API key are found by a command
      instead of by a week of quiet.

Public API:
    DEFAULTS
    run_producer(*, cfg, press_cfg, root, store, now, ...) -> dict
    preflight(*, cfg, press_cfg, root, store, now) -> dict
    heartbeat_path(store) -> Path
    read_heartbeat(store) -> dict
    eligible_accounts(cfg, *, root, register) -> list[str]
    persona_beats(cfg, register, account) -> list[str]
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

log = logging.getLogger(__name__)

#: EVERY THRESHOLD IS A CONFIG KEY (charter §8). ``config/marketing.yml``
#: ``reply_desk.producer:`` overrides these.
DEFAULTS: dict[str, Any] = {
    # Dark until the operator arms it, like every other emitting lane here.
    "enabled": False,
    # Per tick, per account. Small: the charter's quality bar is 15-20 replies
    # a DAY, and the daemon ticks many times an hour.
    "max_drafts_per_account_per_tick": 3,
    # Ceiling on how many scored targets are drafted before giving up on a
    # tick. Drafting is cheap, but critics are not free and a pathological
    # target list must not spin the tick.
    "max_draft_attempts_per_account": 12,
    # How many recent items to read back for the family rotation.
    "family_history": 20,
    # Alternates per draft (reply_drafter composes from DIFFERENT families).
    "n_alts": 2,
    # Outcome polling (the reply half of the labels loop). How far back to look
    # for sent replies worth re-polling, and the per-night request ceiling.
    "outcome_lookback_days": 7,
    "max_outcome_polls_per_night": 40,
    # Seconds between reply-lane ticks. THE DAEMON READS THIS: the wire lane's
    # 75 s hot-poll window is wrong for a lane whose own charter window is 5-15
    # minutes, and a single `--interval` on one process cannot serve both — which
    # is why the reply lane gets its own systemd unit rather than `--lane all`.
    "tick_interval_s": 300,
    # How many consecutive ticks may enqueue NOTHING before the lane announces
    # itself. 12 ticks at the 300 s default is one hour of silence. A quiet desk
    # is legal (Law 1: value before activity); an hour of it with no diagnosis is
    # the failure this whole wave exists to end.
    "silent_tick_warn_after": 12,
}

#: Heartbeat schema. Versioned because the operator's monitoring reads this file
#: and a shape change must be visible rather than inferred.
HEARTBEAT_SCHEMA = "marketing.reply.producer_heartbeat/v1"


def _cfg(cfg: dict | None) -> dict:
    raw = (((cfg or {}).get("reply_desk") or {}).get("producer") or {})
    return {**DEFAULTS, **raw}


def _int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _iso(dt: datetime) -> str:
    ts = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Account + beat resolution
# ---------------------------------------------------------------------------
def eligible_accounts(
    cfg: dict | None,
    *,
    root: Path | str | None = None,
    register: dict | None = None,
) -> list[str]:
    """Desks that may produce replies: ENABLED in desk_network AND in the register.

    Both halves are required. An enabled desk with no curated authors has
    nothing to reply to; a curated desk that is switched off must not produce,
    because the operator switched it off.
    """
    try:
        from engine.marketing import accounts as _accounts  # noqa: PLC0415

        enabled = {
            str(a.get("id"))
            for a in _accounts.effective_accounts(cfg or {}, root)
            if a.get("enabled") and a.get("id")
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_producer.eligible_accounts: account resolution failed: %s", exc)
        return []
    registered = set((register or {}).get("accounts") or {})
    return sorted(enabled & registered)


def persona_beats(cfg: dict | None, register: dict | None, account: str) -> list[str]:
    """The beats used for the scorer's beat-fit feature.

    Register beats first (the operator curated them for exactly this desk),
    falling back to the desk_network entry's beats.
    """
    block = ((register or {}).get("accounts") or {}).get(account) or {}
    beats = [str(b) for b in (block.get("beats") or [])]
    if beats:
        return beats
    for acct in ((cfg or {}).get("desk_network") or {}).get("accounts") or []:
        if isinstance(acct, dict) and str(acct.get("id")) == account:
            return [str(b) for b in (acct.get("beats") or [])]
    return []


def _default_facts_for(root: Path | str | None) -> Callable[[str, dict], dict]:
    """Own-feed facts, whose numbers are already whitelisted.

    ``market_facts`` is stdlib-only and fail-soft (missing artifacts yield an
    empty fact list), which is exactly right: with no facts the drafter returns
    an empty draft and the producer ABSTAINS. Law 1 — value before activity — so
    an empty gift is a legal answer, not an error to route around.
    """
    def _facts(account: str, target: dict) -> dict:  # noqa: ARG001
        try:
            from engine.marketing import market_facts as _mf  # noqa: PLC0415

            return _mf.merge_facts(
                _mf.macro_facts(root), _mf.sector_facts(root),
                _mf.breadth_facts(root), _mf.event_facts(root),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("reply_producer: fact build failed for %r: %s", account, exc)
            return {"facts": [], "numbers_whitelist": []}
    return _facts


def _recent_values(store: Path | str | None, account: str, limit: int,
                   key: str) -> list[str]:
    """This desk's recent values of one rotation axis, oldest first.

    THE ANTI-SAMENESS AXES WERE DECORATIVE IN PRODUCTION UNTIL THIS EXISTED
    (XG-W4b §F.5). ``reply_drafter.draft_reply`` has carried ``recent_warmth``
    and ``recent_tails`` since the warmth and tail builds, and ``_produce_once``
    passed neither — so both LRUs saw an empty window on every single call and
    only the stable hash actually ran live. Measured on HEAD with the shipped
    tables: ``_select_warmth`` collapsed kelly's whole fourteen-family register
    onto exactly TWO warmth moves (``concede_and_hold`` on eight families,
    ``verdict_first`` on six) out of the five-to-six admissible per family,
    because ``rotate_warmth(None, allowed=pool)`` always returns the first
    unseen entry and every entry is unseen when the window is empty. Feeding a
    one-item window back in opens the same register to six distinct moves.

    A rotation axis the producer cannot read back is an axis that resets every
    night, which is exactly the shape the tail build's own docstring warns
    about — so the queue item has to CARRY the value (see the stamp beside
    ``score_features`` in ``_produce_once``) and this has to read it back.

    Falsy values are skipped on purpose: ``warmth=None`` ("no warmth move was
    admissible") and ``tail=""`` ("closed on nothing") are legal outcomes, not
    uses, and counting them as recent would push a real move out of the window
    to make room for an absence.
    """
    try:
        from engine.marketing import reply_queue as _rq  # noqa: PLC0415

        rows = [it for it in _rq.read_items(store)
                if str(it.get("account") or "") == account and it.get(key)]
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_producer._recent_values(%r): %s", key, exc)
        return []
    return [str(it[key]) for it in rows[-limit:]]


def _recent_families(store: Path | str | None, account: str, limit: int) -> list[str]:
    """Families this desk used recently, oldest first (LRU rotation input)."""
    return _recent_values(store, account, limit, "family")


def _recent_warmth(store: Path | str | None, account: str, limit: int) -> list[str]:
    """Warmth moves this desk used recently, oldest first (SECOND rotation axis)."""
    return _recent_values(store, account, limit, "warmth")


def _recent_tails(store: Path | str | None, account: str, limit: int) -> list[str]:
    """Doorway TEMPLATES this desk closed on recently (THIRD rotation axis).

    Templates rather than rendered sentences, because the rendering changes with
    the subject and the mechanism — a history of finished copy could never match
    what ``select_tail`` is choosing between.
    """
    return _recent_values(store, account, limit, "tail")


def _recent_shape_copy(store: Path | str | None, account: str,
                       limit: int) -> list[str]:
    """Head/closer TEMPLATES this desk used recently (FOURTH axis, XG-W4b).

    THE SHAPE ITSELF IS NOT ROTATED least-recently-used and this window is not
    shape ids — a rotation over shapes is a CYCLE, and four accounts sharing an
    audience stepping through five shapes in lockstep is the exact signature the
    deficit-weighted draw exists to avoid. What rotates is the shape's COPY: the
    ``addition`` heads and the ``fragment_exchange`` closers, drawn by the same
    hash-plus-LRU selector (``reply_drafter.pick_from_pool``) the doorway tails
    use, off the same kind of window.

    Templates rather than rendered sentences, for the same reason ``_recent_tails``
    stores templates: the rendering changes with the gift.
    """
    return _recent_values(store, account, limit, "shape_copy")


def _day_counts(store: Path | str | None, account: str, as_of: str,
                key: str) -> dict[str, int]:
    """This desk's counts of one drawn axis SO FAR TODAY. The sampler's control loop.

    WITHOUT THIS THE SAMPLER IS INERT, not merely unbalanced: every draw would
    see an empty realised share, so the deficit term collapses to the target
    weight plus a constant floor and the day never corrects itself. The measured
    mix would then be the raw prior with no control loop at all, and a desk that
    drew six mini-essays in a row would keep drawing them at the same odds.

    Scoped to (account, as_of): the day is the loop, and yesterday's counts
    correcting today's draw is a control system integrating over the wrong
    window.
    """
    try:
        from engine.marketing import reply_queue as _rq  # noqa: PLC0415

        rows = [it for it in _rq.read_items(store)
                if str(it.get("account") or "") == account
                and str(it.get("as_of") or "") == str(as_of)
                and it.get(key)]
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_producer._day_counts(%r): %s", key, exc)
        return {}
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row[key])
        counts[value] = counts.get(value, 0) + 1
    return counts




def _allowed_families(account: str, *, root: Path | str | None, cfg: dict | None) -> list[str] | None:
    """A learned restriction on reply families, when learning is ARMED.

    Returns None (no restriction) whenever consumption is disarmed, which is the
    default — ``learned_rules.active_for`` handles the flag, so this call site is
    real but dark until an operator flips ``learning.learned_rules.enabled``.
    """
    try:
        from engine.marketing import learned_rules as _lr  # noqa: PLC0415
        from engine.marketing import reply_drafter as _rd  # noqa: PLC0415

        rules = _lr.active_for("reply_family", account=account, root=root, cfg=cfg)
        allowed: list[str] = []
        for rule in rules:
            value = rule.get("value")
            if isinstance(value, list):
                allowed.extend(str(v) for v in value)
        allowed = [f for f in allowed if f in _rd.FAMILIES]
        return allowed or None
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_producer._allowed_families: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Heartbeat + the silent-desk warning (XG-W7)
# ---------------------------------------------------------------------------
def heartbeat_path(store: Path | str | None = None) -> Path:
    """Where the producer's liveness artifact lives.

    HOST STATE, beside the queue — never the repo checkout. The wire lane's
    ``data/marketing/fastlane_heartbeat.txt`` is a bare timestamp shared by every
    lane in that process, so it cannot answer "is the REPLY lane alive" and it
    cannot say anything about why the lane is quiet. This one is per-lane, and it
    carries the counts rather than only the clock: a frozen file means the daemon
    is dead, a climbing ``consecutive_empty`` means it is alive and finding
    nothing, and those two need opposite responses.
    """
    from engine.marketing import reply_queue as _rq  # noqa: PLC0415

    return _rq.state_dir(store) / "producer_heartbeat.json"


def read_heartbeat(store: Path | str | None = None) -> dict:
    """Last heartbeat, or {} when the lane has never ticked. Never raises."""
    path = heartbeat_path(store)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_producer.read_heartbeat: %s", exc)
        return {}
    return payload if isinstance(payload, dict) else {}


def _silence_diagnosis(result: dict[str, Any]) -> str:
    """Name the FIRST stage that zeroed, not the fact that the total is zero.

    Ordered by pipeline position, so the reason returned is the earliest one that
    actually explains the silence. Reporting "enqueued=0" is what the tick log
    already did, and it is exactly the report that let four different dark
    switches look identical for months.
    """
    if not result.get("enabled"):
        return ("reply_desk.producer.enabled is false in config/marketing.yml — the "
                "daemon lane is running but the producer is a no-op. This is the "
                "switch an operator most often believes is already flipped.")
    if result.get("note") and not result.get("accounts"):
        # Register invalid, discovery lane off, or every desk halted/ineligible.
        return str(result["note"])
    curated = result.get("curated_authors") or {}
    if curated and not sum(curated.values()):
        return ("config/reply_targets.yml has no ENABLED authors for any live desk "
                "(the shipped file is all PLACEHOLDER_* at enabled:false) — only "
                "inbound mentions of our own handles can produce a target, so the "
                "curated-timeline half of discovery is structurally dark. Curating "
                "the register is operator editorial work, not a code change.")
    if not result.get("targets"):
        return ("discovery returned zero targets — check TWITTERAPI_IO_KEY is set in "
                "the lane's environment (an unset key skips the poll and bills "
                "nothing, which reads as a quiet day), and check the discovery "
                "sub-cap has not stopped the lane")
    if not result.get("eligible"):
        return (f"{result.get('targets')} target(s) polled, none cleared "
                "reply_desk.score_params.min_score — the desks are being shown posts "
                "outside the reply window or off-beat")
    if not result.get("drafted"):
        return (f"{result.get('abstained')} abstention(s) and no draft — the own-feed "
                "fact list is empty, so every gift was empty (Law 1: value before "
                "activity). Check engine/marketing/market_facts.py inputs.")
    if result.get("critic_rejected"):
        return (f"every draft was rejected by the critics "
                f"({result.get('critic_rejected')} rejection(s)) — read the labels "
                "spool's abstention rows for which critic bound")
    if result.get("refused"):
        return ("every item was refused at enqueue (thread already owned by a sibling "
                "desk, or a duplicate id) — see the refused list in the tick log")
    return "no stage reported a zero, which means this diagnosis is incomplete"


def _write_heartbeat(store: Path | str | None, result: dict[str, Any], *,
                     conf: dict, now: datetime) -> dict:
    """Advance and persist the heartbeat; announce a persistently silent desk.

    Returns the heartbeat written (or the prior one on a write failure), so a
    caller — and the tests — can read the counter without a second file read.

    NEVER RAISES. A heartbeat that can take down a tick is worse than no
    heartbeat: the artifact exists to prove the lane is alive, and a crash here
    would make the lane look dead in exactly the way it is meant to disprove.
    """
    prior = read_heartbeat(store)
    enqueued = int(result.get("enqueued") or 0)
    empty_run = 0 if enqueued else int(prior.get("consecutive_empty") or 0) + 1
    beat = {
        "schema": HEARTBEAT_SCHEMA,
        "at": _iso(now),
        "enabled": bool(result.get("enabled")),
        "tick": int(prior.get("tick") or 0) + 1,
        "consecutive_empty": empty_run,
        "last_enqueued_at": (_iso(now) if enqueued else prior.get("last_enqueued_at")),
        "last": {
            "accounts": list(result.get("accounts") or []),
            "halted": list(result.get("halted") or []),
            "curated_authors": dict(result.get("curated_authors") or {}),
            "targets": int(result.get("targets") or 0),
            "eligible": int(result.get("eligible") or 0),
            "drafted": int(result.get("drafted") or 0),
            "abstained": int(result.get("abstained") or 0),
            "critic_rejected": int(result.get("critic_rejected") or 0),
            "enqueued": enqueued,
            "refused": len(result.get("refused") or []),
            "note": result.get("note"),
        },
        "spend": dict(result.get("spend") or {}),
        "diagnosis": None if enqueued else _silence_diagnosis(result),
    }

    threshold = max(1, _int(conf.get("silent_tick_warn_after"), 12))
    # Announce ON the threshold and then once per further full run, never on
    # every tick: a warning that repeats 288 times a day is a warning nobody
    # reads, which is the same outcome as not warning at all.
    if empty_run and empty_run % threshold == 0:
        last_seen = beat["last_enqueued_at"] or "never"
        print(
            f"::warning title=reply-desk-silent::the reply desk has enqueued nothing "
            f"for {empty_run} consecutive ticks (last enqueue: {last_seen}) — "
            f"{beat['diagnosis']}",
            flush=True,
        )

    try:
        path = heartbeat_path(store)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(beat, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_producer: heartbeat write failed: %s", exc)
        return prior
    return beat


# ---------------------------------------------------------------------------
# Preflight — the readiness readout an operator runs BEFORE arming
# ---------------------------------------------------------------------------
def preflight(
    *,
    cfg: dict | None,
    press_cfg: dict | None = None,
    root: Path | str | None = None,
    store: Path | str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Answer "would a tick produce anything, and if not, why" — offline.

    ZERO network, ZERO spend, ZERO writes. Every check reads config, the
    register, the halt registry, or the process environment.

    The four arming switches each fail silently and independently (§module
    docstring), so this returns an ORDERED ``blockers`` list — the things that
    make a draft impossible — separately from ``warnings``, which are things
    that degrade quality but still produce drafts. An operator arming the desk
    reads the first blocker, fixes it, and re-runs.
    """
    from engine.marketing import health_monitor as _health  # noqa: PLC0415
    from engine.marketing import reply_discovery as _discovery  # noqa: PLC0415
    from engine.marketing import reply_queue as _rq  # noqa: PLC0415

    ts = now or datetime.now(timezone.utc)
    conf = _cfg(cfg)
    rd_cfg = ((press_cfg or {}).get("reply_discovery") or {})
    key_env = str(rd_cfg.get("key_env") or "TWITTERAPI_IO_KEY")

    register = _discovery.load_register(root)
    reg_errors = _discovery.validate_register(register) if register else []
    want = eligible_accounts(cfg, root=root, register=register)
    halts = _health.load_halts(root)

    accounts: list[dict[str, Any]] = []
    for account in want:
        accounts.append({
            "id": account,
            "mode": _rq.resolve_mode(cfg, account),
            "curated_authors": len(_discovery.register_for_account(register, account)),
            "halted": bool(_health.is_halted(account, halts=halts)),
        })
    curated_total = sum(int(a["curated_authors"]) for a in accounts)

    voice_cfg = bool((((cfg or {}).get("reply_desk") or {}).get("voice") or {}).get("enabled"))
    checks: dict[str, Any] = {
        "at": _iso(ts),
        "producer_enabled": bool(conf.get("enabled")),
        "desk_enabled": bool(((cfg or {}).get("reply_desk") or {}).get("enabled", True)),
        "discovery_enabled": bool(rd_cfg.get("enabled")),
        "api_key_env": key_env,
        "api_key_present": bool(os.environ.get(key_env, "").strip()),
        "daemon_switch": os.environ.get("MARKETING_FASTLANE_ENABLED") == "1",
        "register_errors": reg_errors,
        "accounts": accounts,
        "curated_authors_total": curated_total,
        "tick_interval_s": max(1, _int(conf.get("tick_interval_s"), 300)),
        "silent_tick_warn_after": max(1, _int(conf.get("silent_tick_warn_after"), 12)),
        "store": str(_rq.state_dir(store)),
        "heartbeat": read_heartbeat(store),
        "voice_config_enabled": voice_cfg,
        "voice_env_enabled": bool(os.environ.get("MARKETING_LLM_ENABLED", "").strip()
                                  not in ("", "0", "false", "False")),
    }

    blockers: list[str] = []
    warnings: list[str] = []
    if not checks["daemon_switch"]:
        blockers.append(
            "MARKETING_FASTLANE_ENABLED != '1' — main() exits 0 before any lane runs. "
            "The reply lane does not inherit the wire's ARMING (its config gate is "
            "separate) but it does share this process switch. Set it in "
            "/etc/macro-live.env.")
    if not checks["producer_enabled"]:
        blockers.append("reply_desk.producer.enabled is false in config/marketing.yml.")
    if not checks["discovery_enabled"]:
        blockers.append("reply_discovery.enabled is false in config/press_sources.yml.")
    if reg_errors:
        blockers.append(f"config/reply_targets.yml is invalid: {reg_errors[:3]}")
    if not want:
        blockers.append(
            "no eligible desks — an account must be BOTH enabled in "
            "marketing.yml desk_network AND present in config/reply_targets.yml.")
    elif all(a["halted"] for a in accounts):
        blockers.append(f"every eligible desk is HALTED: {[a['id'] for a in accounts]}")
    if not checks["api_key_present"]:
        blockers.append(
            f"{key_env} is unset — reply_discovery.fetch() skips the poll and bills "
            "nothing, which is indistinguishable from a quiet day in the tick log.")
    if not curated_total:
        warnings.append(
            "config/reply_targets.yml has zero ENABLED authors — only inbound "
            "mentions can produce a target. The curated-timeline half of discovery "
            "is dark until you replace the PLACEHOLDER_* entries (editorial work).")
    if voice_cfg and not checks["voice_env_enabled"]:
        warnings.append(
            "reply_desk.voice.enabled is true but MARKETING_LLM_ENABLED is unset — "
            "every reply ships the deterministic template. Look for "
            "'::warning title=reply_voice_mute::' in the lane's logs.")
    modes = {a["id"]: a["mode"] for a in accounts}
    if modes and set(modes.values()) == {"M0"}:
        warnings.append(
            f"every desk is at M0 ({sorted(modes)}) — drafts will appear in the admin "
            "queue and NOTHING will export to the desktop lane. This is the intended "
            "launch state; §4 of the runbook is the flip.")

    return {"ready": not blockers, "blockers": blockers, "warnings": warnings,
            "checks": checks}


def format_preflight(report: dict[str, Any]) -> str:
    """Render ``preflight()`` for a terminal. Pure formatting, no I/O."""
    c = report.get("checks") or {}
    lines = [
        "reply desk preflight — " + str(c.get("at") or ""),
        f"  ready              : {'YES' if report.get('ready') else 'NO'}",
        f"  producer.enabled   : {c.get('producer_enabled')}",
        f"  reply_desk.enabled : {c.get('desk_enabled')}",
        f"  discovery.enabled  : {c.get('discovery_enabled')}",
        f"  {str(c.get('api_key_env') or 'API key'):<19}: "
        f"{'present' if c.get('api_key_present') else 'MISSING'}",
        f"  daemon switch      : "
        f"{'armed' if c.get('daemon_switch') else 'MARKETING_FASTLANE_ENABLED != 1'}",
        f"  tick interval      : {c.get('tick_interval_s')}s "
        f"(silent warning after {c.get('silent_tick_warn_after')} empty ticks)",
        f"  store              : {c.get('store')}",
    ]
    for account in (c.get("accounts") or []):
        lines.append(
            f"    - {account.get('id'):<10} mode={account.get('mode')} "
            f"curated_authors={account.get('curated_authors')}"
            + ("  HALTED" if account.get("halted") else ""))
    beat = c.get("heartbeat") or {}
    if beat:
        lines.append(
            f"  heartbeat          : tick={beat.get('tick')} "
            f"consecutive_empty={beat.get('consecutive_empty')} "
            f"last_enqueue={beat.get('last_enqueued_at') or 'never'}")
    else:
        lines.append("  heartbeat          : none — this lane has never ticked")
    for blocker in report.get("blockers") or []:
        lines.append(f"  BLOCKER  {blocker}")
    for warning in report.get("warnings") or []:
        lines.append(f"  warning  {warning}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The producer
# ---------------------------------------------------------------------------
def run_producer(
    *,
    cfg: dict | None,
    press_cfg: dict | None = None,
    root: Path | str | None = None,
    store: Path | str | None = None,
    now: datetime | None = None,
    offline: bool = False,
    accounts: Sequence[str] | None = None,
    facts_for: Callable[[str, dict], dict] | None = None,
    provider: Any = None,
) -> dict[str, Any]:
    """One producer tick, plus the heartbeat and the silent-desk announcement.

    The pipeline itself is ``_produce_once``; this wrapper owns observability so
    that EVERY early return in there — dark config, invalid register, no live
    accounts, discovery off — still advances the heartbeat and still gets a
    diagnosis. An early return that skipped the heartbeat would make the four
    dark switches look like a dead daemon, which is the confusion this wave is
    closing.

    ``offline=True`` writes NO heartbeat: the dry-run law for a billed provider
    is zero network and zero writes, and an offline tick returns zero targets by
    construction, so counting it as a silent tick would manufacture a false
    alarm out of an inspection command.
    """
    ts = now or datetime.now(timezone.utc)
    result = _produce_once(
        cfg=cfg, press_cfg=press_cfg, root=root, store=store, now=ts,
        offline=offline, accounts=accounts, facts_for=facts_for, provider=provider,
    )
    if not offline:
        result["heartbeat"] = _write_heartbeat(store, result, conf=_cfg(cfg), now=ts)
    return result


def _produce_once(
    *,
    cfg: dict | None,
    press_cfg: dict | None = None,
    root: Path | str | None = None,
    store: Path | str | None = None,
    now: datetime | None = None,
    offline: bool = False,
    accounts: Sequence[str] | None = None,
    facts_for: Callable[[str, dict], dict] | None = None,
    provider: Any = None,
) -> dict[str, Any]:
    """One producer tick: discover, score, draft, screen, enqueue.

    ``root`` is the repo checkout (config, facts, halt registry, labels host
    spool); ``store`` is the reply desk's host-state root. The two are different
    directories and conflating them is how a poller dirties the render tree.

    ``offline=True`` makes zero network calls and zero spend (the dry-run law
    for billed providers), which also means zero targets and therefore zero
    drafts — an offline tick reports what it WOULD have done with an empty
    target list, not a simulated one.

    Returns a counts dict; nothing is ever sent.
    """
    from engine.marketing import health_monitor as _health  # noqa: PLC0415
    from engine.marketing import persona_model as _persona_model  # noqa: PLC0415
    from engine.marketing import reply_critics as _critics  # noqa: PLC0415
    from engine.marketing import reply_discovery as _discovery  # noqa: PLC0415
    from engine.marketing import reply_drafter as _drafter  # noqa: PLC0415
    from engine.marketing import reply_queue as _rq  # noqa: PLC0415
    from engine.marketing import reply_score as _score  # noqa: PLC0415

    ts = now or datetime.now(timezone.utc)
    conf = _cfg(cfg)
    result: dict[str, Any] = {
        "at": _iso(ts), "enabled": bool(conf.get("enabled")), "offline": bool(offline),
        "accounts": [], "halted": [], "targets": 0, "eligible": 0, "drafted": 0,
        "abstained": 0, "critic_rejected": 0, "enqueued": 0, "refused": [],
        "spend": {}, "wire_spend": None,
        # {account: enabled curated authors}. Carried on EVERY tick because the
        # placeholder register is the single loudest reason this lane produces
        # nothing, and a count of zero here is the difference between "quiet day"
        # and "structurally dark". The silence diagnosis reads it.
        "curated_authors": {},
    }

    if not conf.get("enabled"):
        log.info("reply_producer: reply_desk.producer.enabled is false — dark no-op")
        result["note"] = "reply_desk.producer.enabled is false (dark by default)"
        return result

    register = _discovery.load_register(root)
    reg_errors = _discovery.validate_register(register) if register else []
    if reg_errors:
        for err in reg_errors[:5]:
            print(f"::warning title=reply-register-invalid::{err}", flush=True)
        result["note"] = "author register invalid — producing nothing"
        return result

    want = list(accounts) if accounts is not None else eligible_accounts(
        cfg, root=root, register=register)

    # HALT GATE — checked BEFORE any billed request for that desk, so a halted
    # account costs neither money nor drafts. One registry read for the whole
    # tick; per-account membership after that.
    halts = _health.load_halts(root)
    halted = [a for a in want if _health.is_halted(a, halts=halts)]
    live = [a for a in want if a not in set(halted)]
    result["halted"] = halted
    result["accounts"] = live
    result["curated_authors"] = {
        a: len(_discovery.register_for_account(register, a)) for a in live
    }
    if halted:
        print(
            f"::warning title=reply-producer-halted::skipping halted account(s) "
            f"{halted} — the other {len(live)} desk(s) continue normally",
            flush=True,
        )
    if not live:
        result["note"] = "no live accounts (all halted or none eligible)"
        return result

    if provider is None:
        provider = _discovery.build_provider(press_cfg, cfg, root=root)
    if provider is None:
        result["note"] = "reply discovery lane is off (press_sources.reply_discovery)"
        return result

    tick = _discovery.run_tick(provider, root=store, repo_root=root,
                              offline=offline, accounts=live, now=ts)
    targets = tick.get("targets") or []
    result["targets"] = len(targets)
    result["spend"] = tick.get("spend") or {}
    result["wire_spend"] = tick.get("wire_spend")

    by_account: dict[str, list[dict]] = {}
    for target in targets:
        by_account.setdefault(str(target.get("account") or ""), []).append(target)

    facts_builder = facts_for or _default_facts_for(root)
    per_tick = max(0, _int(conf.get("max_drafts_per_account_per_tick"), 3))
    max_attempts = max(1, _int(conf.get("max_draft_attempts_per_account"), 12))
    n_alts = max(0, _int(conf.get("n_alts"), 2))
    history_n = max(1, _int(conf.get("family_history"), 20))
    as_of = ts.strftime("%Y-%m-%d")

    # Fleet context the critics need. WITHOUT THESE THE BLOCKLIST CRITIC IS
    # INERT: `our_handles` is what enforces "zero cross-account engagement" and
    # `satire_blocklist` is the shared list the wire lane reads. A producer that
    # omitted them would pass drafts through a gate that had nothing to check.
    our_handles = _critics.our_handles(cfg)
    satire = list((press_cfg or {}).get("satire_blocklist") or [])
    corpus = _corpus(store)

    for account in live:
        pool = by_account.get(account) or []
        if not pool:
            continue
        # ONE relation read per account per tick, used TWICE. The scorer has
        # always read it for its `relationship_stage` feature; XG-W4b adds the
        # tone half — `persona_model.familiarity` derives the register tier from
        # the same rows. Two reads of an append-only ledger inside one tick
        # could disagree with each other, and a desk whose scorer and whose
        # register disagree about who it is talking to is worse than either.
        relations = _score.load_relations(account, root)
        ranked = _score.rank(
            pool,
            persona_beats=persona_beats(cfg, register, account),
            cfg=cfg, now=ts,
            relations=relations,
        )
        eligible = [t for t in ranked if t.get("eligible")]
        result["eligible"] += len(eligible)

        recent = _recent_families(store, account, history_n)
        # The two rotation windows XG-W4b arms. Read exactly the way `recent` is
        # — off the queue, per account, oldest first — because a window built
        # any other way is a window the enqueued record cannot reproduce.
        recent_warmth = _recent_warmth(store, account, history_n)
        recent_tails = _recent_tails(store, account, history_n)
        # The FOURTH axis (XG-W4b). `recent_shapes` rotates the shape's own copy
        # pools; `day_shapes` / `day_types` are the sampler's control loop and
        # are scoped to TODAY, which is why they are read separately rather than
        # counted off the rotation window.
        recent_shape_copy = _recent_shape_copy(store, account, history_n)
        day_shapes = _day_counts(store, account, as_of, "shape")
        day_types = _day_counts(store, account, as_of, "response_type")
        # `flat_confession` ("I was wrong about this one") is gated on a REAL
        # prior position and fails closed without one, so a producer that never
        # reported whether this desk has an opinion ledger denied itself the
        # move outright. `position_consistency` reads the same file.
        has_thesis = bool(_critics.load_theses(account, root))
        # A learned restriction, when learning is ARMED (default: None). The
        # family is still chosen by the drafter's own LRU rotation — the rule
        # narrows the pool, it never pins one family, because pinning is how one
        # winning move takes over and anti-sameness loses.
        allowed = _allowed_families(account, root=root, cfg=cfg)
        made = 0
        for target in eligible[:max_attempts]:
            if made >= per_tick:
                break
            facts = facts_builder(account, target)
            chart = target.get("chart")
            handle = str(target.get("author") or "").strip().lower().lstrip("@")
            rel_row = relations.get(handle)
            # THE REGISTER TIER, derived from our own ledger and nothing else.
            # At M0 relations.jsonl does not exist on any desk, so this is
            # `stranger` for every handle and the layer is INERT — which is the
            # correct shipping state, printed here rather than discovered later.
            # It warms as M1 approvals accumulate.
            fam_tier = _persona_model.familiarity(
                account, handle, relations=relations, now=ts, root=root)
            # The familiar-register openers this author has EARNED, or []. Every
            # AM-R1 precondition is evaluated here — recent contact inside 14
            # days, a stored topic that overlaps this parent, and the persona's
            # own guard sweep — so the gate runs in production rather than only
            # in a test, and a bug in it surfaces as an empty pool on a desk
            # that should have one. Composition belongs to the drafter (§F.3),
            # which reads this off the item and the ctx; at M0 it is always []
            # because no desk has a relation ledger yet.
            tone = _persona_model.tone_prefixes(
                account, fam_tier, parent_text=str(target.get("text") or ""),
                relations_row=rel_row, now=ts, root=root)
            # The QUEUE tier (relationship / conversion / breakout / inbound) is
            # a different axis and is what gates `relationship_only` — the
            # sympathy move on a curated relationship-tier author. The producer
            # has always computed it for `make_item` and never passed it to the
            # drafter, so `quiet_sympathy` was unreachable from this lane.
            queue_tier = _tier_of(target)
            # `recent_warmth`, `recent_tails`, `has_thesis` and `tier` are
            # keywords `draft_reply` HAS ALWAYS ACCEPTED AND THIS LANE NEVER
            # PASSED — that is the XG-W4b §F.5 defect, and it is why the two
            # anti-sameness axes shipped in the last two builds ran on an empty
            # history in production. Passed plainly, with no signature probe and
            # no defensive filter: if a later edit removes one of these the tick
            # must fail loudly on the first draft, because the silent version of
            # that failure is exactly what is being closed here.
            #
            # `relations_row` carries the register tier's evidence into the
            # composer; `fam_tier` itself is stamped on the critic ctx and the
            # queue item below, which is what an operator reads it back from.
            drafted = _drafter.draft_reply(
                account=account, target=target, facts=facts,
                recent_families=recent,
                recent_warmth=recent_warmth,
                recent_tails=recent_tails,
                recent_shapes=recent_shape_copy,
                # BOTH axes, nested, because one flat dict would have the shape
                # draw computing its realised share off a response-type
                # denominator (see `reply_drafter._day_slice`).
                day_counts={"shape": day_shapes, "response_type": day_types},
                relations_row=rel_row,
                as_of=as_of,
                has_thesis=has_thesis,
                tier=queue_tier,
                chart=chart, cfg=cfg, root=root, n_alts=n_alts,
                family=(_drafter.rotate_family(recent, allowed=allowed) if allowed else None),
            )
            draft = str(drafted.get("draft") or "").strip()
            if not draft:
                # Law 1: an empty gift is an abstention, not a failure.
                result["abstained"] += 1
                continue
            result["drafted"] += 1

            ctx = {
                "account": account,
                "root": root,
                "parent_text": target.get("text"),
                "parent_author": target.get("author"),
                "thread_authors": target.get("thread_authors") or [],
                "numbers_whitelist": drafted.get("numbers_whitelist") or [],
                # reply_value's long-form exemption keys on the drafting family
                # (micro_framework may run long; everything else may not). A ctx
                # without the family fails CLOSED — every >60-word draft would
                # be rejected regardless of family (E4 review flag, 2026-07-29).
                "family": drafted.get("family"),
                "corpus": corpus,
                "our_handles": our_handles,
                "satire_blocklist": satire,
                "cfg": cfg,
                # THE WARMTH CONTEXT THE CRITICS ALREADY EXPECT. `persona_label`
                # and the two-of-five element critic both carry a
                # `quiet_sympathy` exemption that is DOUBLE-gated on
                # `relationship_only` AND `warmth == "quiet_sympathy"` — either
                # alone is a hole wide enough to smuggle an elementless growth
                # reply through. A ctx that supplied neither made the exemption
                # unreachable and the sympathy reply un-shippable; a ctx that
                # supplied only one would make it a hole. Both, or nothing.
                "warmth": drafted.get("warmth"),
                "relationship_only": bool(
                    (drafted.get("components") or {}).get("relationship_only")),
                # THE SHAPE, and it is load-bearing rather than informational.
                # `reply_critics.short_form_engaged` FAILS CLOSED without it, so
                # a producer that omitted it would leave every `one_line` and
                # `fragment_exchange` draft to be rejected by `persona_label`
                # (`_referents("Yeah, but that is the problem.")` is empty) —
                # i.e. the whole short-form half of this build would draft and
                # then silently abstain, which is the hardest failure mode to
                # see from a counts dict.
                "shape": drafted.get("shape"),
                "response_type": drafted.get("response_type"),
                # Register context. Not a gate here — the critics may read it,
                # and an operator reading a rejection can see which register the
                # draft was written in.
                "familiarity": fam_tier,
                "tier": queue_tier,
                "relations_row": rel_row,
                "tone_prefixes": list(tone),
            }
            verdict, stamp = _critics.screen(draft, ctx)
            if verdict.get("verdict") != "pass":
                result["critic_rejected"] += 1
                _record_abstention(root, account=account, as_of=as_of, ts=ts,
                                   target=target, reason="critics",
                                   detail=verdict.get("rejected_by") or [])
                continue

            try:
                item = _rq.make_item(
                    account=account,
                    target_url=str(target.get("url") or ""),
                    parent_author=str(target.get("author") or ""),
                    parent_excerpt=str(target.get("text") or ""),
                    draft=draft,
                    alt_drafts=list(drafted.get("alt_drafts") or []),
                    tier=queue_tier,
                    score=float(target.get("score") or 0.0),
                    score_components=dict(target.get("score_components") or {}),
                    family=drafted.get("family"),
                    chart=chart,
                    thread_root_id=target.get("thread_root_id"),
                    target_status_id=target.get("status_id"),
                    as_of=as_of,
                    critics=stamp,
                    cfg=cfg,
                    now=ts,
                    provenance="reply_producer",
                )
            except ValueError as exc:
                result["refused"].append({"account": account, "reason": str(exc)})
                continue

            # The item carries the draft-time score features so the covariates
            # the parent adjustment needs survive the thread moving on.
            item["score_features"] = dict(target.get("score_features") or {})
            # …and the ROTATION AXES, for the same reason and with the same
            # mechanism. `family` has always been a first-class item field, so
            # its LRU worked; `warmth` and `tail` were not persisted anywhere,
            # so the two axes shipped in the last two builds drew from an empty
            # window on every producer run (see `_recent_values`). Stamped here
            # rather than passed into `make_item` because the shape lane owns
            # that signature this wave and two lanes editing one keyword list is
            # how a merge silently drops a field; `validate_item` checks NAMED
            # fields and admits unknown keys, so an item carrying these is valid
            # under the unchanged `marketing.reply/v1` schema and every already
            # queued item stays valid without them.
            item["warmth"] = drafted.get("warmth")
            item["tail"] = drafted.get("tail") or ""
            item["familiarity"] = fam_tier
            item["tone_prefixes"] = list(tone)
            # THE SHAPE AXIS, and its whole audit trail. `shape_roll` and
            # `type_roll` are the [0,1) draws; with them plus the day's counts an
            # operator re-derives the pick exactly instead of arguing with a coin
            # flip — which is the entire justification for a random draw sitting
            # in a deterministic pipeline. `shape` is also what `_day_counts` and
            # `reply_shape.shape_mix` read back, so an item that omitted it would
            # disarm both the control loop and the drift alarm.
            item["shape"] = drafted.get("shape") or ""
            item["shape_copy"] = drafted.get("shape_copy") or ""
            item["response_type"] = drafted.get("response_type") or ""
            item["shape_roll"] = float(drafted.get("shape_roll") or 0.0)
            item["type_roll"] = float(drafted.get("type_roll") or 0.0)

            outcome = _rq.enqueue(item, store, cfg=cfg)
            if outcome.get("ok"):
                result["enqueued"] += 1
                made += 1
                recent.append(str(drafted.get("family") or ""))
                # ALL THREE WINDOWS ADVANCE INSIDE THE TICK, not just the
                # family one. Without this, two targets drafted in the same tick
                # read the same pre-tick history and can draw the same warmth
                # move and the same doorway — the enqueued item is only visible
                # to `_recent_values` on the NEXT tick, so an in-tick collision
                # is exactly the case the queue read-back cannot cover.
                if drafted.get("warmth"):
                    recent_warmth.append(str(drafted["warmth"]))
                if drafted.get("tail"):
                    recent_tails.append(str(drafted["tail"]))
                # The shape's copy window and BOTH day counters advance in-tick
                # for the same reason: the enqueued item is only visible to the
                # queue readers on the NEXT tick, so without this two targets in
                # one tick see identical counts, get identical deficits, and the
                # day's control loop does not start working until tomorrow.
                if drafted.get("shape_copy"):
                    recent_shape_copy.append(str(drafted["shape_copy"]))
                if drafted.get("shape"):
                    day_shapes[str(drafted["shape"])] = day_shapes.get(
                        str(drafted["shape"]), 0) + 1
                if drafted.get("response_type"):
                    day_types[str(drafted["response_type"])] = day_types.get(
                        str(drafted["response_type"]), 0) + 1
                # Keep the near-dup critic honest WITHIN the tick: without this
                # the corpus is a snapshot from before the tick started, so two
                # targets on the same theme could both clear it and enqueue the
                # same sentence twice.
                corpus.append({"draft": draft, "account": account})
                _record_enqueued(root, item=item, target=target, ts=ts)
            else:
                result["refused"].append({
                    "account": account, "id": outcome.get("id"),
                    "reason": outcome.get("reason"), "owner": outcome.get("owner"),
                    "errors": outcome.get("errors"),
                })

    print(
        f"reply_producer: targets={result['targets']} eligible={result['eligible']} "
        f"drafted={result['drafted']} critic_rejected={result['critic_rejected']} "
        f"enqueued={result['enqueued']} abstained={result['abstained']} "
        f"halted={len(halted)}",
        flush=True,
    )
    return result


# ---------------------------------------------------------------------------
# Outcome polling — the reply half of the labels loop
# ---------------------------------------------------------------------------
def poll_reply_outcomes(
    *,
    cfg: dict | None,
    press_cfg: dict | None = None,
    root: Path | str | None = None,
    store: Path | str | None = None,
    now: datetime | None = None,
    offline: bool = False,
    provider: Any = None,
) -> dict[str, Any]:
    """Poll twitterapi.io for outcomes on replies we actually SENT.

    THE MISSING HALF OF THE LOOP. ``reply_discovery.poll_outcomes`` and
    ``reply_queue.record_outcome`` both shipped in XG-W4 with no production
    caller between them, so every reply label was permanently null and the
    parent adjustment had nothing to adjust. This is that caller.

    Charter §3: "author reply-back is the highest-value outcome", so that is
    what this reads — did the PARENT AUTHOR appear among the replies under our
    reply. Likes on our own reply are deliberately NOT invented here: the
    endpoint returns the replies under a post, not the post's own counters, and
    a fabricated zero would be indistinguishable from a measured one.

    **At M0 this is an honest no-op**: nothing has sent, so the sent set is
    empty, ``poll_outcomes`` short-circuits on an empty id list, and zero
    requests are billed. That is the expected state today, not a failure.

    Spend rides XG-W4's accounting unchanged — the same host state file, the
    same monthly counter, the same sub-cap and shared-bucket stop the discovery
    tick uses. No second budget.
    """
    from engine.marketing import reply_discovery as _discovery  # noqa: PLC0415
    from engine.marketing import reply_export as _export  # noqa: PLC0415
    from engine.marketing import reply_queue as _rq  # noqa: PLC0415

    ts = now or datetime.now(timezone.utc)
    conf = _cfg(cfg)
    lookback = max(1, _int(conf.get("outcome_lookback_days"), 7))
    max_polls = max(0, _int(conf.get("max_outcome_polls_per_night"), 40))
    result: dict[str, Any] = {
        "at": _iso(ts), "offline": bool(offline), "sent": 0, "polled": 0,
        "recorded": 0, "author_replied": 0, "spend": {}, "note": None,
    }

    state = _rq.fold_state(store)
    cutoff = (ts - timedelta(days=lookback)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Our OWN status ids, recovered from the desktop lane's receipt URL. That
    # receipt is the only record of where our reply actually landed.
    by_status: dict[str, dict] = {}
    for iid, item in state.get("items", {}).items():
        if state.get("status", {}).get(iid) != "sent":
            continue
        row = state.get("last", {}).get(iid) or {}
        receipt = row.get("receipt") if isinstance(row.get("receipt"), dict) else {}
        at = str(row.get("at") or "")
        if at and at < cutoff:
            continue
        sid = _rq.status_id_from_url(str(receipt.get("url") or ""))
        if sid:
            by_status[sid] = {
                "id": iid,
                "parent_author": str(item.get("parent_author") or ""),
                # Carried so an author reply-back can escalate the relation row
                # on the RIGHT desk. Relationship memory is per persona.
                "account": str(item.get("account") or ""),
            }
    result["sent"] = len(by_status)

    if not by_status:
        result["note"] = ("no sent replies in the window — at M0 this is the "
                          "expected state, and it bills nothing")
        return result
    if offline:
        result["note"] = "offline — zero network, zero spend"
        return result

    if provider is None:
        provider = _discovery.build_provider(press_cfg, cfg, root=root)
    if provider is None:
        result["note"] = "reply discovery lane is off (press_sources.reply_discovery)"
        return result

    session = _discovery.load_state(store)
    wire = _discovery.load_wire_spend(root, now=ts)
    status_ids = sorted(by_status)[:max_polls]
    try:
        observed = provider.poll_outcomes(
            session_state=session, status_ids=status_ids,
            offline=False, wire_spend_usd=wire, now=ts,
        )
    finally:
        # Persist even on the exception path: `session` is mutated in place as
        # requests are billed, so bailing without saving discards spend that WAS
        # charged — an under-count in the direction that costs money.
        _discovery.save_state(session, store)

    for entry in observed:
        sid = str(entry.get("status_id") or "")
        meta = by_status.get(sid)
        if meta is None:
            continue
        result["polled"] += 1
        parent = meta["parent_author"].lower().lstrip("@")
        replied = None
        if parent:
            # A KNOWN parent handle gives a real yes/no. Without one we cannot
            # tell "they did not answer" from "we do not know who they are", so
            # the outcome stays null rather than becoming a false negative.
            replied = any(
                str((raw.get("author") or raw.get("user") or {}).get("userName")
                    or (raw.get("author") or raw.get("user") or {}).get("screen_name")
                    or "").lower().lstrip("@") == parent
                for raw in (entry.get("raw") or []) if isinstance(raw, dict)
            )
        if replied is None:
            continue
        if _rq.record_outcome(meta["id"], root=store, author_replied=bool(replied)):
            result["recorded"] += 1
            if replied:
                result["author_replied"] += 1
                # THE LOOP CLOSES HERE. An author answering us is the highest-
                # value outcome in the charter, and it is also the only event
                # that can move a relation past "we spoke at them". Escalate the
                # persona's relation row so the NEXT tick's scorer ranks that
                # author higher (reply_score.load_relations reads it).
                _export.note_relation(
                    account=meta["account"], handle=meta["parent_author"],
                    stage="reciprocal", repo_root=root, now=ts,
                )

    month = ts.strftime("%Y-%m")
    result["spend"] = ((session.get(_discovery.STATE_NS) or {}).get("spend") or {}
                       ).get(month) or {}
    return result


def _tier_of(target: dict) -> str:
    """Map a discovery target's author tier onto a queue tier.

    Discovery labels our own mentions ``inbound``; the queue admits that tier
    verbatim. Anything unrecognised falls to ``conversion`` — the middle rung,
    not the top one, so an unknown author never inherits relationship priority.
    """
    from engine.marketing import reply_queue as _rq  # noqa: PLC0415

    tier = str(target.get("author_tier") or "").strip().lower()
    return tier if tier in _rq.TIERS else "conversion"


def _corpus(store: Path | str | None, limit: int = 200) -> list[dict]:
    """Our own recent reply drafts, for the near-dup critic.

    Deliberately FLEET-WIDE, not per account: text-similarity clustering across
    accounts is a documented linkage signal, so two desks shipping the same
    sentence has to be catchable. Rows keep their ``account`` so the critic can
    say WHICH desk the near-dup came from — "you already said this" and "your
    colleague already said this" call for different edits.
    """
    try:
        from engine.marketing import reply_queue as _rq  # noqa: PLC0415

        return [
            {"draft": str(it.get("draft") or ""), "account": str(it.get("account") or "")}
            for it in _rq.read_items(store)[-limit:]
        ]
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_producer._corpus: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Label observations (host spool only — zero tracked-repo writes intraday)
# ---------------------------------------------------------------------------
def _record_enqueued(root: Path | str | None, *, item: dict, target: dict,
                     ts: datetime) -> None:
    """Bank the draft-time covariates the parent adjustment will need later.

    Parent engagement and post age are only observable AT DRAFT TIME — by the
    time an outcome arrives the thread has moved and the numbers are different
    numbers. Writing them now is what makes a parent-adjusted label possible at
    all; recovering them later is not an option.
    """
    from engine.marketing import labels as _labels  # noqa: PLC0415

    feats = target.get("score_features") or {}
    ctx = feats.get("_context") if isinstance(feats, dict) else {}
    ctx = ctx if isinstance(ctx, dict) else {}
    row = _labels.new_row(
        surface="reply",
        subject_id=str(item.get("id") or ""),
        as_of=str(item.get("as_of") or ""),
        account=str(item.get("account") or ""),
        format="reply",
        register=_labels.register_for("reply", account=str(item.get("account") or ""), root=root),
        hook_family=str(item.get("family") or "unassigned"),
        observed={"stage": "enqueued", "tier": item.get("tier")},
        features={
            "score": item.get("score"),
            "tier": item.get("tier"),
            "has_chart": bool(item.get("chart")),
            "parent_engagement": ctx.get("engagement"),
            "post_age_min": ctx.get("age_min"),
            "thread_saturation": ctx.get("reply_count"),
        },
        label=None,
        observed_at=_iso(ts),
    )
    row["adjusted_reason"] = "enqueued_no_outcome_yet"
    _labels.record_observation(row, root=root)


def _record_abstention(root: Path | str | None, *, account: str, as_of: str,
                       ts: datetime, target: dict, reason: str,
                       detail: Any) -> None:
    """Log a producer-side abstention with its deterministic reason.

    NOT into the reply desk's taste corpus (``reply_queue.record_rejection``) —
    that corpus is the OPERATOR's taste, and mixing machine rejections into it
    would corrupt the one signal that says what a human wants this desk to
    sound like.
    """
    from engine.marketing import labels as _labels  # noqa: PLC0415

    row = _labels.new_row(
        surface="reply",
        subject_id=f"abstain-{account}-{target.get('status_id') or ''}",
        as_of=as_of,
        account=account,
        format="reply",
        register=_labels.register_for("reply", account=account, root=root),
        hook_family="abstained",
        observed={"stage": "abstained", "reason": reason, "detail": detail},
        features={"tier": target.get("author_tier")},
        label=None,
        weight=0.0,
        observed_at=_iso(ts),
    )
    row["adjusted_reason"] = f"abstained_{reason}"
    _labels.record_observation(row, root=root)


__all__ = ["DEFAULTS", "HEARTBEAT_SCHEMA", "run_producer", "poll_reply_outcomes",
           "preflight", "format_preflight", "heartbeat_path", "read_heartbeat",
           "eligible_accounts", "persona_beats"]
