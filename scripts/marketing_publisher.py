"""scripts/marketing_publisher.py — D02 W1 live social publisher.

The missing publish half of the desk network: takes APPROVED, DUE items from
the outbox and posts them through a backend (Buffer today). Off the render
path; operator-run or nightly-cron; DARK BY DEFAULT.

Usage:
    # dry-run (default): print exactly what WOULD post, zero network calls
    python -m scripts.marketing_publisher
    python -m scripts.marketing_publisher --account flagship

    # discover Buffer channel ids (needs BUFFER_TOKEN in env)
    BUFFER_TOKEN=... python -m scripts.marketing_publisher --list-channels

    # LIVE post — requires BOTH flags together:
    MARKETING_PUBLISH_ENABLED=1 BUFFER_TOKEN=... \
        python -m scripts.marketing_publisher --live --account flagship

Guards (ALL must pass or the runner no-ops with a clear log line):
  * kill-switch  sentinel.publish_enabled() is true AND --live was passed
  * per-account daily cap  outbox.effective_cap(cfg), counting items already
                           `posted` today (as_of == today)
  * per-item     social_publisher.validate_postable() (280 cap, link policy,
                 empty text)

No-double-post guarantee:
  * validate fail          → item transitioned to `quarantined` (reason), never posted
  * before the network call → `approved → posting` (durable in-flight marker)
  * publish success         → `posting → posted`, Receipt recorded in the ledger
  * publish failure         → `posting → failed`, error recorded
  * item already `posting` at startup → REPORTED and LEFT AS-IS, never reposted
    (a crash mid-post must not double-post on the next run)

Backend + per-account channel id come from config/marketing.yml `publish:`; the
Buffer token from env BUFFER_TOKEN. Structured logging throughout.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger("marketing_publisher")


# ─────────────────────────────────────────────────────────────────────────────
# Bootstrapping helpers
# ─────────────────────────────────────────────────────────────────────────────

def _code_root() -> Path:
    """Directory containing engine/ — always where this script lives (../)."""
    return Path(__file__).resolve().parent.parent


def _data_root(root_arg: str | None) -> Path:
    return Path(root_arg) if root_arg is not None else _code_root()


def _ensure_importable() -> None:
    cr = _code_root()
    if str(cr) not in sys.path:
        sys.path.insert(0, str(cr))


def _load_marketing_cfg(root: Path) -> dict:
    """Load config/marketing.yml fail-soft; {} on any error."""
    try:
        import yaml  # noqa: PLC0415
        cfg_path = root / "config" / "marketing.yml"
        if cfg_path.exists():
            return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("could not load marketing.yml: %s", exc)
    return {}


def _publish_cfg(cfg: dict) -> dict:
    return (cfg.get("publish") or {}) if isinstance(cfg, dict) else {}


def _channel_id_for(pub_cfg: dict, account: str) -> str:
    return str((pub_cfg.get("channels") or {}).get(account, "") or "").strip()


def _links_allowed_for(pub_cfg: dict, account: str) -> bool:
    v = (pub_cfg.get("links_allowed") or {}).get(account, False)
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes"}


def _auto_approve_cfg(pub_cfg: dict) -> bool:
    """publish.auto_approve, parsed strictly (a quoted "false" must not enable)."""
    v = pub_cfg.get("auto_approve", False)
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes"}


def _auto_approve_pass(
    outbox, state: dict, pub_cfg: dict, *, cap: int, now: datetime, live: bool,
    account: str | None, posted_today: dict, validate_postable, root,
) -> list[str]:
    """Auto-advance queued → approved for items passing ALL publish gates.

    Gates (an item must clear every one to be auto-approved):
      * NOT held (a queued item whose latest operator decision is 'hold' stays put)
      * validate_postable() clean (280 cap, link policy, non-empty text)
      * a channel id is configured for its account
      * the account is under the per-account daily cap, counting BOTH items
        already posted today AND items this pass has already approved this run
        (so auto-approve never over-fills the queue past the cap)

    DRY-RUN safety: when ``live`` is False this makes NO ledger writes — it only
    logs and returns the ids it WOULD approve. The queued→approved transition is
    applied via outbox.transition() ONLY when ``live`` is True.

    Returns the list of item ids that were (or, in dry-run, would be) approved,
    in the deterministic order they were considered.
    """
    items_by_id = state["items"]
    statuses = state["status"]
    held = state.get("held") or set()

    # Running per-account budget: seed from what is already posted today, then
    # also charge each already-approved+due item so auto-approve tops up TO the
    # cap, not beyond it (approved-but-not-yet-posted still consumes a slot).
    budget: dict[str, int] = dict(posted_today)
    for iid, s in statuses.items():
        if s == "approved" and iid in items_by_id:
            it = items_by_id[iid]
            if account is not None and it.get("account") != account:
                continue
            if _is_due(it.get("scheduled_at"), now):
                acct = it.get("account", "")
                budget[acct] = budget.get(acct, 0) + 1

    # Deterministic consideration order: priority, then schedule, then id.
    candidates = [
        items_by_id[iid] for iid, s in statuses.items()
        if s == "queued" and iid in items_by_id and iid not in held
        and (account is None or items_by_id[iid].get("account") == account)
    ]
    candidates.sort(key=lambda i: (i.get("priority", 5), i.get("scheduled_at", ""), i.get("id", "")))

    approved: list[str] = []
    for it in candidates:
        iid = it["id"]
        acct = it.get("account", "")
        text = it.get("text", "") or ""
        link = it.get("link")
        links_allowed = _links_allowed_for(pub_cfg, acct)

        problems = validate_postable(text, link, links_allowed)
        if problems:
            log.info("auto-approve SKIP %s (%s): fails validation %s", iid, acct, problems)
            continue
        if not _channel_id_for(pub_cfg, acct):
            log.info("auto-approve SKIP %s (%s): no channel id configured", iid, acct)
            continue
        if budget.get(acct, 0) >= cap:
            log.info("auto-approve SKIP %s (%s): account at daily cap (%d/day)", iid, acct, cap)
            continue

        if live:
            if not outbox.transition(iid, "approved", actor="publisher-autoapprove",
                                     root=root, note="auto-approved (all gates passed)"):
                log.warning("auto-approve %s: transition failed — leaving queued", iid)
                continue
            log.info("auto-approve APPROVED %s (%s)", iid, acct)
        else:
            log.info("WOULD AUTO-APPROVE %s (%s) chars=%d", iid, acct, len(text))
        budget[acct] = budget.get(acct, 0) + 1
        approved.append(iid)

    return approved


def _is_due(scheduled_at: str | None, now: datetime) -> bool:
    """True if the item is due to post now.

    "immediate" (or empty/missing) is always due. Otherwise parse the ISO
    timestamp and compare; an unparseable value is treated as NOT due (fail
    closed — never post something on a schedule we cannot read).
    """
    s = (scheduled_at or "").strip()
    if not s or s == "immediate":
        return True
    try:
        iso = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt <= now
    except (ValueError, TypeError):
        log.warning("unparseable scheduled_at %r — treating as NOT due", scheduled_at)
        return False


def _make_publisher(backend: str, *, token: str, cfg: dict):
    """Instantiate the configured backend publisher. Returns None if unsupported."""
    from engine.marketing.social_publisher import BufferPublisher  # noqa: PLC0415
    if backend == "buffer":
        return BufferPublisher(token=token)
    log.error("unsupported publish backend %r", backend)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Marketing live social publisher (D02 W1 — dark by default)"
    )
    parser.add_argument("--live", action="store_true",
                        help="Actually post (requires MARKETING_PUBLISH_ENABLED=1 too). "
                             "Without this flag the runner is a dry-run.")
    parser.add_argument("--auto-approve", action="store_true",
                        help="Auto-advance queued→approved for items that pass ALL gates "
                             "(validate_postable clean, under the daily cap, channel id set) "
                             "before selecting approved items. OFF by default; also enabled by "
                             "config publish.auto_approve. In DRY-RUN this only REPORTS what it "
                             "would approve — it never mutates the ledger.")
    parser.add_argument("--account", default=None,
                        help="Only process this account id (default: all accounts)")
    parser.add_argument("--list-channels", action="store_true",
                        help="Print the backend's connected channels and exit "
                             "(for channel-id discovery; needs BUFFER_TOKEN)")
    parser.add_argument("--root", default=None,
                        help="Repo root directory (default: derived from script location)")
    parser.add_argument("--now", default=None,
                        help="Override 'now' as ISO8601 (testing/determinism)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    _ensure_importable()
    root = _data_root(args.root)
    cfg = _load_marketing_cfg(root)
    pub_cfg = _publish_cfg(cfg)
    backend = str(pub_cfg.get("backend") or "buffer").strip()
    token = os.environ.get("BUFFER_TOKEN", "").strip()

    now = _parse_now(args.now)

    # ── --list-channels convenience path (gated on a token) ─────────────────
    if args.list_channels:
        return _run_list_channels(backend, token=token, cfg=cfg)

    from engine.marketing import outbox as _outbox  # noqa: PLC0415
    try:
        from engine.marketing.sentinel import publish_enabled as _publish_enabled  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        def _publish_enabled() -> bool:  # conservative: switch off
            return False

    from engine.marketing.social_publisher import validate_postable  # noqa: PLC0415

    kill_on = _publish_enabled()
    live = bool(args.live) and kill_on
    cap = _outbox.effective_cap(cfg)

    state = _outbox.fold_state(root)
    items_by_id = state["items"]
    statuses = state["status"]

    # ── Startup safety: report items stuck in `posting`, NEVER repost them ───
    stuck_posting = [
        i for i, s in statuses.items()
        if s == "posting" and i in items_by_id
        and (args.account is None or items_by_id[i].get("account") == args.account)
    ]
    for iid in stuck_posting:
        log.warning(
            "item %s is stuck in 'posting' (in-flight from a prior run) — "
            "reporting, NOT reposting (no-double-post)", iid)

    # ── Per-account cap accounting: count items already posted TODAY ─────────
    today = now.strftime("%Y-%m-%d")
    posted_today: dict[str, int] = {}
    for iid, s in statuses.items():
        if s == "posted" and iid in items_by_id:
            it = items_by_id[iid]
            if it.get("as_of") == today:
                acct = it.get("account", "")
                posted_today[acct] = posted_today.get(acct, 0) + 1

    # ── OPTIONAL auto-approve: queued → approved for items that pass ALL gates ─
    # Gated OFF by default; enabled by publish.auto_approve OR --auto-approve.
    # This is the operator's path to full automation — leave it off during the
    # aged-account warm-up. In DRY-RUN it only REPORTS what it would approve and
    # NEVER mutates the ledger (the transitions happen only when `live`).
    auto_approve_on = bool(args.auto_approve) or _auto_approve_cfg(pub_cfg)
    auto_approved: list[str] = []
    if auto_approve_on:
        auto_approved = _auto_approve_pass(
            _outbox, state, pub_cfg, cap=cap, now=now, live=live,
            account=args.account, posted_today=posted_today,
            validate_postable=validate_postable, root=root,
        )
        if live and auto_approved:
            # Re-fold so the candidate set below sees the freshly-approved items.
            state = _outbox.fold_state(root)
            items_by_id = state["items"]
            statuses = state["status"]

    # ── Candidate set: APPROVED + DUE (+ optional account filter) ────────────
    approved_due: list[dict] = []
    for iid, s in statuses.items():
        if s != "approved" or iid not in items_by_id:
            continue
        it = items_by_id[iid]
        if args.account is not None and it.get("account") != args.account:
            continue
        if not _is_due(it.get("scheduled_at"), now):
            continue
        approved_due.append(it)
    # Deterministic order: priority, then schedule, then id.
    approved_due.sort(key=lambda i: (i.get("priority", 5), i.get("scheduled_at", ""), i.get("id", "")))

    mode = "LIVE" if live else "DRY-RUN"
    log.info(
        "%s | backend=%s cap=%d/day kill_switch=%s --live=%s auto_approve=%s | "
        "approved+due=%d stuck_posting=%d auto_approved=%d",
        mode, backend, cap, "ON" if kill_on else "off", bool(args.live),
        "on" if auto_approve_on else "off",
        len(approved_due), len(stuck_posting), len(auto_approved),
    )
    if bool(args.live) and not kill_on:
        log.warning("--live passed but MARKETING_PUBLISH_ENABLED is not set — "
                    "refusing to post; running as DRY-RUN")

    # ── Lazily build the publisher only when we actually post ────────────────
    publisher = None
    if live:
        publisher = _make_publisher(backend, token=token, cfg=cfg)
        if publisher is None:
            log.error("no usable backend — aborting live run")
            return 2
        if not token:
            log.error("BUFFER_TOKEN empty — refusing live run")
            return 2

    posted = failed = quarantined = skipped_cap = skipped_channel = would_post = 0
    tape_quarantined = tape_skipped = 0

    # ── Live tape gate context: load once per run (fail-soft) ────────────────
    # The plan was written off yesterday's EOD; the tape has been open for
    # hours by the AM/PM/EOD slots. Every item re-verifies against the freshest
    # repo-local quotes before it may post (engine/marketing/live_verify.py).
    try:
        from engine.marketing import live_verify as _live_verify  # noqa: PLC0415
        _tape = _live_verify.load_live_quotes(root)
        _earn_set = _live_verify.load_earnings_guard_set(root, now=now)
        log.info("live tape gate: %d quotes (%s), %d tickers on earnings guard",
                 len(_tape.get("quotes") or {}), _tape.get("source"), len(_earn_set))
    except Exception as _lv_exc:  # noqa: BLE001
        log.warning("live tape gate unavailable (%s) — signals will be held", _lv_exc)
        _live_verify = None  # type: ignore[assignment]
        _tape = {"quotes": {}, "asof": None, "source": "none"}
        _earn_set = frozenset()

    for it in approved_due:
        iid = it["id"]
        account = it.get("account", "")
        text = it.get("text", "") or ""
        links_allowed = _links_allowed_for(pub_cfg, account)
        # Items carry no separate link field today; the link (if any) is inline
        # in the post text. Pass link=None so validate_postable checks the body
        # length and the account's link policy is still available for the future.
        link = it.get("link")

        # -- validate → quarantine on failure --------------------------------
        problems = validate_postable(text, link, links_allowed)
        if problems:
            reason = "unpostable: " + ", ".join(problems)
            log.warning("item %s (%s) failed validation: %s", iid, account, problems)
            if live:
                _outbox.transition(iid, "quarantined", actor="publisher", root=root, note=reason)
            quarantined += 1
            continue

        # -- live tape gate: never post yesterday's read against today's tape --
        if _live_verify is not None:
            verdict = _live_verify.verify_item(
                it, live=_tape, earnings=_earn_set, now=now, cfg=cfg)
        else:
            # Gate module broken: hold signals (fail closed), pass the rest.
            verdict = ({"action": "skip", "reasons": ["live gate unavailable"]}
                       if it.get("kind") == "signal"
                       else {"action": "post", "reasons": []})
        if verdict["action"] == "quarantine":
            reason = "tape gate: " + "; ".join(verdict["reasons"])
            log.warning("item %s (%s) QUARANTINED by tape gate: %s", iid, account, reason)
            if live:
                _outbox.transition(iid, "quarantined", actor="publisher", root=root, note=reason)
            tape_quarantined += 1
            continue
        if verdict["action"] == "skip":
            log.info("item %s (%s) held by tape gate: %s", iid, account,
                     "; ".join(verdict["reasons"]))
            tape_skipped += 1
            continue

        # -- per-account daily cap -------------------------------------------
        if posted_today.get(account, 0) >= cap:
            log.info("item %s (%s) skipped — account at daily cap (%d/day)",
                     iid, account, cap)
            skipped_cap += 1
            continue

        # -- channel id must exist -------------------------------------------
        channel_id = _channel_id_for(pub_cfg, account)
        if not channel_id:
            log.warning("item %s (%s) has no configured channel id in "
                        "publish.channels.%s — cannot post", iid, account, account)
            skipped_channel += 1
            continue

        media_paths = [m.get("path") for m in (it.get("media") or []) if m.get("path")]

        # -- DRY-RUN: print, never touch the network or the ledger -----------
        if not live:
            log.info(
                "WOULD POST | account=%s channel=%s chars=%d media=%d sched=%s\n    %s",
                account, channel_id, len(text), len(media_paths),
                it.get("scheduled_at"), text.replace("\n", " ")[:200],
            )
            would_post += 1
            continue

        # -- LIVE: approved → posting BEFORE the network call ----------------
        if not _outbox.transition(iid, "posting", actor="publisher", root=root,
                                  note="in-flight (pre-publish)"):
            log.error("item %s: could not mark posting — skipping (not posting)", iid)
            continue

        receipt = publisher.publish(
            text=text,
            channel_id=channel_id,
            media_paths=media_paths or None,
            link=link,
            scheduled_at=(None if _is_immediate(it.get("scheduled_at")) else it.get("scheduled_at")),
            now=now,
        )

        if receipt.ok:
            _outbox.transition(
                iid, "posted", actor="publisher", root=root,
                note="published",
                receipt={
                    "backend": receipt.backend,
                    "external_id": receipt.external_id,
                    "external_url": receipt.external_url,
                    "at": receipt.at,
                },
            )
            posted_today[account] = posted_today.get(account, 0) + 1
            posted += 1
            log.info("item %s POSTED via %s id=%s", iid, receipt.backend, receipt.external_id)
        else:
            _outbox.transition(iid, "failed", actor="publisher", root=root,
                               note=receipt.error or "publish failed",
                               receipt={"backend": receipt.backend, "error": receipt.error,
                                        "at": receipt.at})
            failed += 1
            log.warning("item %s FAILED: %s", iid, receipt.error)

    # ── Summary + activity row ──────────────────────────────────────────────
    log.info(
        "%s complete | posted=%d failed=%d quarantined=%d would_post=%d "
        "tape_quarantined=%d tape_skipped=%d "
        "skipped_cap=%d skipped_no_channel=%d stuck_posting=%d auto_approved=%d",
        mode, posted, failed, quarantined, would_post,
        tape_quarantined, tape_skipped,
        skipped_cap, skipped_channel, len(stuck_posting), len(auto_approved),
    )
    try:
        _outbox._append_activity(root, {
            "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lane": "publisher_live" if live else "publisher_dry_run",
            "backend": backend,
            "cap": cap,
            "posted": posted,
            "failed": failed,
            "quarantined": quarantined,
            "would_post": would_post,
            "tape_quarantined": tape_quarantined,
            "tape_skipped": tape_skipped,
            "skipped_cap": skipped_cap,
            "skipped_no_channel": skipped_channel,
            "stuck_posting": len(stuck_posting),
            "auto_approved": len(auto_approved),
            "account": args.account or "all",
        })
    except Exception:  # noqa: BLE001
        pass

    return 0


def _parse_now(now_arg: str | None) -> datetime:
    if not now_arg:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(now_arg.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        log.warning("bad --now %r — using current time", now_arg)
        return datetime.now(timezone.utc)


def _is_immediate(scheduled_at: str | None) -> bool:
    s = (scheduled_at or "").strip()
    return not s or s == "immediate"


def dry_run_report(root=None, *, account: str | None = None,
                   now: datetime | None = None) -> dict:
    """Compute the DRY-RUN "would post" report as structured data — no side effects.

    This is the in-process entrypoint the admin "Run dry-run" button calls. It
    reuses the exact selection logic main() runs in dry-run, but returns a dict
    instead of logging and NEVER touches the network OR the ledger (no
    transition(), no _append_activity()). Fail-soft: any error becomes
    {"ok": False, "error": ...}.

    Returns {ok, mode:"dry_run", backend, cap, kill_switch, account,
             counts:{approved_due, would_post, quarantine, skipped_cap,
                     skipped_no_channel, stuck_posting, would_auto_approve},
             would_post:[{id,account,channel,chars,media,scheduled_at,preview}],
             quarantine:[{id,account,reasons}],
             would_auto_approve:[{id,account,chars}],
             stuck_posting:[ids], auto_approve:bool}.
    """
    try:
        _ensure_importable()
        r = _data_root(root)
        cfg = _load_marketing_cfg(r)
        pub_cfg = _publish_cfg(cfg)
        backend = str(pub_cfg.get("backend") or "buffer").strip()
        now = now or datetime.now(timezone.utc)

        from engine.marketing import outbox as _outbox  # noqa: PLC0415
        from engine.marketing.social_publisher import validate_postable  # noqa: PLC0415
        try:
            from engine.marketing.sentinel import publish_enabled as _pe  # noqa: PLC0415
            kill_on = _pe()
        except Exception:  # noqa: BLE001
            kill_on = False

        cap = _outbox.effective_cap(cfg)
        state = _outbox.fold_state(r)
        items_by_id = state["items"]
        statuses = state["status"]

        def _acct_ok(it: dict) -> bool:
            return account is None or it.get("account") == account

        stuck = [i for i, s in statuses.items()
                 if s == "posting" and i in items_by_id and _acct_ok(items_by_id[i])]

        today = now.strftime("%Y-%m-%d")
        posted_today: dict[str, int] = {}
        for iid, s in statuses.items():
            if s == "posted" and iid in items_by_id and items_by_id[iid].get("as_of") == today:
                acct = items_by_id[iid].get("account", "")
                posted_today[acct] = posted_today.get(acct, 0) + 1

        # Auto-approve preview (always dry here → never mutates).
        auto_on = _auto_approve_cfg(pub_cfg)
        would_auto: list[dict] = []
        if auto_on:
            ids = _auto_approve_pass(
                _outbox, state, pub_cfg, cap=cap, now=now, live=False,
                account=account, posted_today=posted_today,
                validate_postable=validate_postable, root=r,
            )
            for iid in ids:
                it = items_by_id.get(iid, {})
                would_auto.append({"id": iid, "account": it.get("account", ""),
                                   "chars": len(it.get("text", "") or "")})

        # APPROVED + DUE candidates, classified as main() would in dry-run.
        approved_due = sorted(
            (items_by_id[iid] for iid, s in statuses.items()
             if s == "approved" and iid in items_by_id and _acct_ok(items_by_id[iid])
             and _is_due(items_by_id[iid].get("scheduled_at"), now)),
            key=lambda i: (i.get("priority", 5), i.get("scheduled_at", ""), i.get("id", "")),
        )

        would_post: list[dict] = []
        quarantine: list[dict] = []
        skipped_cap = skipped_channel = 0
        budget = dict(posted_today)
        for it in approved_due:
            iid = it["id"]
            acct = it.get("account", "")
            text = it.get("text", "") or ""
            link = it.get("link")
            problems = validate_postable(text, link, _links_allowed_for(pub_cfg, acct))
            if problems:
                quarantine.append({"id": iid, "account": acct, "reasons": problems})
                continue
            if budget.get(acct, 0) >= cap:
                skipped_cap += 1
                continue
            channel_id = _channel_id_for(pub_cfg, acct)
            if not channel_id:
                skipped_channel += 1
                continue
            media = [m.get("path") for m in (it.get("media") or []) if m.get("path")]
            would_post.append({
                "id": iid, "account": acct, "channel": channel_id,
                "chars": len(text), "media": len(media),
                "scheduled_at": it.get("scheduled_at"),
                "preview": text.replace("\n", " ")[:200],
            })
            budget[acct] = budget.get(acct, 0) + 1

        return {
            "ok": True,
            "mode": "dry_run",
            "backend": backend,
            "cap": cap,
            "kill_switch": bool(kill_on),
            "account": account or "all",
            "auto_approve": bool(auto_on),
            "counts": {
                "approved_due": len(approved_due),
                "would_post": len(would_post),
                "quarantine": len(quarantine),
                "skipped_cap": skipped_cap,
                "skipped_no_channel": skipped_channel,
                "stuck_posting": len(stuck),
                "would_auto_approve": len(would_auto),
            },
            "would_post": would_post,
            "quarantine": quarantine,
            "would_auto_approve": would_auto,
            "stuck_posting": stuck,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("dry_run_report failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _run_list_channels(backend: str, *, token: str, cfg: dict) -> int:
    """--list-channels path: gated on a token; prints {id, service, name}."""
    if not token:
        log.error("--list-channels needs BUFFER_TOKEN in the environment "
                  "(none set) — nothing to query")
        return 2
    publisher = _make_publisher(backend, token=token, cfg=cfg)
    if publisher is None:
        return 2
    channels = publisher.list_channels()
    if not channels:
        log.info("no channels returned (empty token scope, or a query error — "
                 "see warnings above)")
        return 0
    print(f"Connected {backend} channels:")
    for ch in channels:
        print(f"  {ch.get('service',''):<12} {ch.get('id',''):<28} {ch.get('name','')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
