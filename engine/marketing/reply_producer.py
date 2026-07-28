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

Public API:
    DEFAULTS
    run_producer(*, cfg, press_cfg, root, store, now, ...) -> dict
    eligible_accounts(cfg, *, root, register) -> list[str]
    persona_beats(cfg, register, account) -> list[str]
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
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
}


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


def _recent_families(store: Path | str | None, account: str, limit: int) -> list[str]:
    """Families this desk used recently, oldest first (LRU rotation input)."""
    try:
        from engine.marketing import reply_queue as _rq  # noqa: PLC0415

        rows = [it for it in _rq.read_items(store)
                if str(it.get("account") or "") == account and it.get("family")]
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_producer._recent_families: %s", exc)
        return []
    return [str(it["family"]) for it in rows[-limit:]]


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
        ranked = _score.rank(
            pool,
            persona_beats=persona_beats(cfg, register, account),
            cfg=cfg, now=ts,
            relations=_score.load_relations(account, root),
        )
        eligible = [t for t in ranked if t.get("eligible")]
        result["eligible"] += len(eligible)

        recent = _recent_families(store, account, history_n)
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
            drafted = _drafter.draft_reply(
                account=account, target=target, facts=facts,
                recent_families=recent,
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
                "corpus": corpus,
                "our_handles": our_handles,
                "satire_blocklist": satire,
                "cfg": cfg,
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
                    tier=_tier_of(target),
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

            outcome = _rq.enqueue(item, store, cfg=cfg)
            if outcome.get("ok"):
                result["enqueued"] += 1
                made += 1
                recent.append(str(drafted.get("family") or ""))
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
    row = _labels._blank_row(  # noqa: SLF001 — the row constructor is the store's own shape
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

    row = _labels._blank_row(  # noqa: SLF001
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


__all__ = ["DEFAULTS", "run_producer", "eligible_accounts", "persona_beats"]
