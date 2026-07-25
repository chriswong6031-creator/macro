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
  * per-account daily cap  outbox.effective_cap(cfg), counted ledger-based via
                           outbox.posted_today_by_account (folded status
                           posted/posting whose last transition landed today —
                           nightly items post the day AFTER their as_of)
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
import hashlib
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
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


_PUBLICATIONS_REL = Path("data/marketing/publications.jsonl")


def _publication_row(it: dict, text: str, receipt, *, published_at: str) -> dict:
    """A PublicationReceipt-shaped row (contracts/marketing_publication_receipt.v1)
    for one live X post — the Channels page reads publications.jsonl, and until now
    posted receipts landed ONLY in the outbox status ledger, so that page stayed dead.

    Required schema fields (publication_id, asset_id, channel, account, published_at,
    campaign_id) are always populated; the rest carry honest live-post defaults.
    """
    iid = str(it.get("id", ""))
    external_id = getattr(receipt, "external_id", None)
    external_url = getattr(receipt, "external_url", None)
    return {
        "publication_id": f"pub-{iid}" if iid else f"pub-{external_id or 'unknown'}",
        "asset_id": iid,
        "channel": "x",
        "account": it.get("account", ""),
        "remote_id": external_id,
        "published_at": published_at,
        "effective_copy_hash": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "policy_version": str(it.get("policy_version") or "v1"),
        "audience": "public",
        "destination": "x_timeline",
        # Items don't carry a campaign_id today; fall back to provenance so the
        # required field is never empty. A later PR threads real campaign ids.
        "campaign_id": str(it.get("campaign_id") or it.get("provenance") or "publisher_live"),
        "experiment_cell": it.get("experiment_cell"),
        "correction_state": "clean",
        "takedown_method": "unpublish_via_adapter",
        "mode": "live",
        "external_url": external_url,
    }


def _append_publication(root: Path | str | None, row: dict) -> None:
    """Append a publication receipt to publications.jsonl. Fail-soft — a ledger
    write must never turn a successful post into a crash."""
    from engine.marketing.ledgers import append_jsonl  # noqa: PLC0415
    try:
        append_jsonl(Path(_data_root(root)) / _PUBLICATIONS_REL, row)
    except Exception as exc:  # noqa: BLE001
        log.warning("publisher: publications.jsonl append failed for %s: %s",
                    row.get("asset_id", "?"), exc)


def _links_allowed_for(pub_cfg: dict, account: str) -> bool:
    v = (pub_cfg.get("links_allowed") or {}).get(account, False)
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes"}


def _media_enabled_cfg(pub_cfg: dict) -> bool:
    """publish.media_enabled — the top-level chart-image attach gate (default OFF)."""
    v = pub_cfg.get("media_enabled", False)
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes"}


def _media_paths_for(it: dict, pub_cfg: dict) -> list[str]:
    """Public media URLs to attach to a post (PNG on X; Buffer needs a hosted URL).

    Prefers the chart's public https media_url (stamped at plan-build time when
    publish.media_enabled AND R2 creds existed). The local .svg/.png `path` is a
    repo file Buffer cannot fetch — _build_assets() skips non-http paths anyway —
    so we never pass it. Returns [] (text-only) when the gate is off or no post
    carries a public URL: the graceful, always-correct fallback.
    """
    if not _media_enabled_cfg(pub_cfg):
        return []
    urls: list[str] = []
    for m in it.get("media") or []:
        if not isinstance(m, dict):
            continue
        u = str(m.get("media_url") or "").strip()
        if u.lower().startswith(("http://", "https://")):
            urls.append(u)
    return urls


def _auto_approve_cfg(pub_cfg: dict) -> bool:
    """publish.auto_approve, parsed strictly (a quoted "false" must not enable)."""
    v = pub_cfg.get("auto_approve", False)
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes"}


def _auto_approve_kinds_cfg(pub_cfg: dict) -> frozenset[str]:
    """publish.auto_approve_kinds → the set of kinds that may auto-approve even
    while publish.require_approval is true, but ONLY for publish-time-lane items
    (provenance publisher_live_movers — enforced in _auto_approve_pass).

    Parsed STRICTLY: each entry must be a lowercase string that is a member of
    outbox.KINDS; junk (non-strings, unknown kinds) is ignored with a warning so
    a typo can never silently widen the auto-approve surface. Absent/empty → the
    empty set (no scoped exception; fully manual).
    """
    raw = pub_cfg.get("auto_approve_kinds")
    if not raw or not isinstance(raw, (list, tuple)):
        return frozenset()
    try:
        from engine.marketing.outbox import KINDS  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        KINDS = frozenset()  # type: ignore[assignment]
    out: set[str] = set()
    for v in raw:
        if not isinstance(v, str):
            log.warning("publish.auto_approve_kinds: ignoring non-string entry %r", v)
            continue
        k = v.strip().lower()
        if KINDS and k not in KINDS:
            log.warning("publish.auto_approve_kinds: ignoring unknown kind %r", v)
            continue
        out.add(k)
    return frozenset(out)


def _at_cap(count: int, cap: int) -> bool:
    """True when ``count`` has reached a REAL per-account daily cap. A negative
    cap is the UNLIMITED sentinel (config ``max_posts_per_account_per_day: -1``,
    surfaced by ``outbox.effective_cap`` as ``-1``): it means NO limit, so this
    is always False. Every daily-cap gate routes through here so the -1 trap
    (``0 >= -1`` → skip everything) can never re-appear at one site and not
    another — the cap is a FUNCTIONAL gate on posting, not just a display value.
    """
    return cap >= 0 and count >= cap


def _floor_minutes_cfg(pub_cfg: dict) -> int:
    """publish.min_minutes_between_any_posts — the GLOBAL post-time anti-spam
    floor: no two posts go out within N minutes of each other, across ALL
    accounts (distinct from the sentinel's per-account *plan-time* cadence
    min_minutes_between_posts). 0 / absent / non-positive / unparseable → 0 =
    disabled (fully backward-compatible)."""
    raw = pub_cfg.get("min_minutes_between_any_posts", 0)
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return 0
    return v if v > 0 else 0


def _last_global_post_at(root) -> "datetime | None":
    """The most recent 'posted' transition time across ALL accounts (the floor is
    account-agnostic), or None if nothing has ever posted. Seeds the floor across
    cron runs. Fail-soft: malformed rows / timestamps are skipped, never raises."""
    from engine.marketing.outbox import read_ledger  # noqa: PLC0415
    latest: "datetime | None" = None
    for row in read_ledger(root):
        if row.get("to") != "posted":
            continue
        raw = str(row.get("at") or "").strip()
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if latest is None or dt > latest:
            latest = dt
    return latest


def _within_floor(last_post_at: "datetime | None", now: datetime, floor_min: int) -> bool:
    """True when posting *now* would violate the global min-spacing floor — the
    last post was less than floor_min minutes ago. No prior post or a non-positive
    floor → never blocks. Callers advance ``last_post_at`` in memory after each
    post so a single run emits at most one item per window."""
    if last_post_at is None or floor_min <= 0:
        return False
    return (now - last_post_at) < timedelta(minutes=floor_min)


def _select_approved_due(state: dict, statuses: dict, items_by_id: dict,
                         account: str | None, now: datetime) -> list[dict]:
    """The APPROVED + DUE candidate set (+ optional account filter), sorted the
    canonical way: priority, then schedule, then id. Refactored out of main() so
    it can run twice (once to feed generate_slot_items a preliminary list, once
    after the auto-approve pass) without duplicating the selection logic.
    """
    out: list[dict] = []
    for iid, s in statuses.items():
        if s != "approved" or iid not in items_by_id:
            continue
        it = items_by_id[iid]
        if account is not None and it.get("account") != account:
            continue
        if not _is_due(it.get("scheduled_at"), now):
            continue
        out.append(it)
    out.sort(key=lambda i: (i.get("priority", 5), i.get("scheduled_at", ""), i.get("id", "")))
    return out


def _auto_approve_pass(
    outbox, state: dict, pub_cfg: dict, *, cap: int, now: datetime, live: bool,
    account: str | None, posted_today: dict, validate_postable, root,
    allowed_kinds: "frozenset[str] | None" = None,
) -> list[str]:
    """Auto-advance queued → approved for items passing ALL publish gates.

    Gates (an item must clear every one to be auto-approved):
      * NOT held (a queued item whose latest operator decision is 'hold' stays put)
      * kind scope: when ``allowed_kinds`` is not None (global publish.auto_approve
        is OFF but publish.auto_approve_kinds is set), an item is a candidate ONLY
        if its kind is in allowed_kinds AND it was generated by the publish-time
        lane (provenance publisher_live_movers). When allowed_kinds is None
        (global auto_approve ON), the scope is unrestricted — every kind, exactly
        as before.
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

    # Kind-scope predicate. allowed_kinds None → unrestricted (global auto_approve
    # ON, legacy behavior). allowed_kinds set → ONLY publish-time-lane items of a
    # listed kind may auto-approve (the scoped exception to require_approval).
    _scoped = allowed_kinds is not None
    _AUTO_LANE = "publisher_live_movers"

    def _kind_ok(it: dict) -> bool:
        if not _scoped:
            return True
        return (it.get("kind") in allowed_kinds
                and it.get("provenance") == _AUTO_LANE)

    # Deterministic consideration order: priority, then schedule, then id.
    candidates = [
        items_by_id[iid] for iid, s in statuses.items()
        if s == "queued" and iid in items_by_id and iid not in held
        and (account is None or items_by_id[iid].get("account") == account)
        and _kind_ok(items_by_id[iid])
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
        if _at_cap(budget.get(acct, 0), cap):
            log.info("auto-approve SKIP %s (%s): account at daily cap (%d/day)", iid, acct, cap)
            continue

        if live:
            _note = ("auto-approved (kind-scoped publish-time lane)" if _scoped
                     else "auto-approved (all gates passed)")
            if not outbox.transition(iid, "approved", actor="publisher-autoapprove",
                                     root=root, note=_note):
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

    # ── Per-account cap accounting: ledger-based posts-today ─────────────────
    # NOT as_of-based: nightly items post the day AFTER their as_of, so as_of
    # counting misses them — see outbox.posted_today_by_account.
    today = now.strftime("%Y-%m-%d")
    posted_today: dict[str, int] = _outbox.posted_today_by_account(state, today)

    # ── Publish-time mover/theme generation (honest live tape posts) ─────────
    # mover/theme_list posts are generated NIGHTLY but never emitted (a "+7%
    # today" claim is stale next morning). Generate them HERE from the freshest
    # tape in this checkout, enqueue via outbox, and let the tape gate re-verify
    # them below. Runs BEFORE the auto-approve pass so the scoped lane can pick
    # them up this same run. Fully fail-soft: any error leaves the legacy flow
    # untouched. The preliminary approved_due list feeds the module's per-account
    # spacing law (one post per account per slot run).
    pt_generated = pt_dropped = 0
    try:
        from engine.marketing import publish_time_content as _pt  # noqa: PLC0415
        _prelim_due = _select_approved_due(state, statuses, items_by_id,
                                           args.account, now)
        _pt_report = _pt.generate_slot_items(
            root, cfg=cfg, now=now, state=state, approved_due=_prelim_due,
            posted_counts=posted_today, cap=cap, live=live,
            account_filter=args.account,
        )
        pt_generated = len(_pt_report.get("generated") or [])
        pt_dropped = len(_pt_report.get("dropped") or [])
        log.info(
            "publish-time generation | enabled=%s slot=%s quotes=%s "
            "generated=%d would_generate=%d dropped=%d",
            _pt_report.get("enabled"), _pt_report.get("slot") or "-",
            _pt_report.get("quote_source"), pt_generated,
            len(_pt_report.get("would_generate") or []), pt_dropped,
        )
        for _d in (_pt_report.get("dropped") or []):
            log.info("  pt drop: %s — %s", _d.get("reason"), _d.get("detail"))
        for _w in (_pt_report.get("would_generate") or []):
            log.info("  WOULD GENERATE | account=%s kind=%s %s | %s",
                     _w.get("account"), _w.get("kind"), _w.get("ticker") or "",
                     _w.get("text", ""))
        if live and pt_generated:
            # Re-fold so the auto-approve pass + candidate set see the new items.
            state = _outbox.fold_state(root)
            items_by_id = state["items"]
            statuses = state["status"]
    except Exception as _pt_exc:  # noqa: BLE001
        log.warning("publish-time generation unavailable (%s) — legacy flow unaffected",
                    _pt_exc)

    # ── OPTIONAL auto-approve: queued → approved for items that pass ALL gates ─
    # Gated OFF by default; enabled by publish.auto_approve OR --auto-approve.
    # This is the operator's path to full automation — leave it off during the
    # aged-account warm-up. In DRY-RUN it only REPORTS what it would approve and
    # NEVER mutates the ledger (the transitions happen only when `live`).
    #
    # SCOPED exception (publish.auto_approve_kinds): when the global flag is OFF
    # but a kind list is configured, the pass still runs — restricted to
    # publish-time-lane items of those kinds (the descriptive tape posts above).
    # Operator-authored / nightly items of any kind still require approval.
    auto_approve_on = bool(args.auto_approve) or _auto_approve_cfg(pub_cfg)
    allowed_kinds = _auto_approve_kinds_cfg(pub_cfg)
    scoped_on = (not auto_approve_on) and bool(allowed_kinds)
    auto_approved: list[str] = []
    if auto_approve_on or scoped_on:
        # allowed_kinds param: None when the global flag is ON (unrestricted,
        # legacy), the configured set when only the scoped exception is active.
        _kinds_param = None if auto_approve_on else allowed_kinds
        auto_approved = _auto_approve_pass(
            _outbox, state, pub_cfg, cap=cap, now=now, live=live,
            account=args.account, posted_today=posted_today,
            validate_postable=validate_postable, root=root,
            allowed_kinds=_kinds_param,
        )
        if live and auto_approved:
            # Re-fold so the candidate set below sees the freshly-approved items.
            state = _outbox.fold_state(root)
            items_by_id = state["items"]
            statuses = state["status"]

    # ── Candidate set: APPROVED + DUE (+ optional account filter) ────────────
    approved_due = _select_approved_due(state, statuses, items_by_id,
                                        args.account, now)

    mode = "LIVE" if live else "DRY-RUN"
    log.info(
        "%s | backend=%s cap=%d/day kill_switch=%s --live=%s auto_approve=%s | "
        "approved+due=%d stuck_posting=%d auto_approved=%d "
        "pt_generated=%d pt_dropped=%d",
        mode, backend, cap, "ON" if kill_on else "off", bool(args.live),
        ("on" if auto_approve_on else ("scoped" if scoped_on else "off")),
        len(approved_due), len(stuck_posting), len(auto_approved),
        pt_generated, pt_dropped,
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
    tape_quarantined = tape_skipped = skipped_floor = 0

    # ── Global min-spacing floor (publish.min_minutes_between_any_posts) ──────
    # Post-time anti-spam guard: at most one post per floor-minute window across
    # ALL accounts, so an accumulated backlog (or a breaking item) can never
    # burst out at once. Seeded from the last posted row in the ledger so it
    # holds across cron runs, then advanced in-memory after each post so ONE run
    # emits at most one item per window (the rest defer to the next slot). 0 =
    # disabled. This is the Phase-2 floor from the cadence masterplan.
    floor_min = _floor_minutes_cfg(pub_cfg)
    last_post_at = _last_global_post_at(root) if floor_min else None

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
        if _at_cap(posted_today.get(account, 0), cap):
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
            # Approved items on a channel-less account otherwise rot 'approved'
            # forever (re-skipped every run, never expiring). After 3 days,
            # quarantine so the queue drains honestly. Only in --live (dry-run
            # never mutates the ledger).
            if live:
                _stamp = str(it.get("as_of") or it.get("created_at") or "")[:10]
                try:
                    _age_days = (now.date() - date.fromisoformat(_stamp)).days
                except (ValueError, TypeError):
                    _age_days = 0  # unparseable stamp → don't expire (fail-soft)
                if _age_days > 3:
                    _outbox.transition(iid, "quarantined", actor="publisher",
                                       root=root, note="expired_no_channel")
            continue

        # -- global min-spacing floor: at most one post per window (any acct) --
        # Checked AFTER the tape/cap/channel gates so a held item never consumes
        # the window. A blocked item stays approved and retries the next slot.
        if _within_floor(last_post_at, now, floor_min):
            _ago = int((now - last_post_at).total_seconds() // 60)
            log.info("item %s (%s) deferred — a post went out %dm ago (< %dm "
                     "global floor); retries next slot", iid, account, _ago, floor_min)
            skipped_floor += 1
            continue

        # Public chart-image URLs (PNG on X) when publish.media_enabled + a plan-
        # build-time R2 upload produced one; else [] → text-only (graceful).
        media_paths = _media_paths_for(it, pub_cfg)

        # -- DRY-RUN: print, never touch the network or the ledger -----------
        if not live:
            log.info(
                "WOULD POST | account=%s channel=%s chars=%d media=%d sched=%s\n    %s",
                account, channel_id, len(text), len(media_paths),
                it.get("scheduled_at"), text.replace("\n", " ")[:200],
            )
            would_post += 1
            last_post_at = now   # advance the floor so a dry-run mirrors live pacing
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
            # ALSO record a publication receipt so the Channels page (reads
            # publications.jsonl via engine.marketing.state) surfaces the post —
            # the outbox status ledger alone never reached that reader.
            _append_publication(
                root,
                _publication_row(
                    it, text, receipt,
                    published_at=(receipt.at or now.strftime("%Y-%m-%dT%H:%M:%SZ")),
                ),
            )
            posted_today[account] = posted_today.get(account, 0) + 1
            posted += 1
            last_post_at = now   # advance the global floor: next item this run defers
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
        "tape_quarantined=%d tape_skipped=%d skipped_floor=%d "
        "skipped_cap=%d skipped_no_channel=%d stuck_posting=%d auto_approved=%d",
        mode, posted, failed, quarantined, would_post,
        tape_quarantined, tape_skipped, skipped_floor,
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
            "skipped_floor": skipped_floor,
            "skipped_cap": skipped_cap,
            "skipped_no_channel": skipped_channel,
            "stuck_posting": len(stuck_posting),
            "auto_approved": len(auto_approved),
            "pt_generated": pt_generated,
            "pt_dropped": pt_dropped,
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
        posted_today: dict[str, int] = _outbox.posted_today_by_account(state, today)

        # Auto-approve preview (always dry here → never mutates). Honors both the
        # global flag AND the scoped publish.auto_approve_kinds exception, so the
        # admin dry-run mirrors what a live run would auto-approve.
        auto_on = _auto_approve_cfg(pub_cfg)
        allowed_kinds = _auto_approve_kinds_cfg(pub_cfg)
        scoped_on = (not auto_on) and bool(allowed_kinds)
        would_auto: list[dict] = []
        if auto_on or scoped_on:
            ids = _auto_approve_pass(
                _outbox, state, pub_cfg, cap=cap, now=now, live=False,
                account=account, posted_today=posted_today,
                validate_postable=validate_postable, root=r,
                allowed_kinds=(None if auto_on else allowed_kinds),
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
        skipped_cap = skipped_channel = skipped_floor = 0
        budget = dict(posted_today)
        floor_min = _floor_minutes_cfg(pub_cfg)
        last_post_at = _last_global_post_at(r) if floor_min else None
        for it in approved_due:
            iid = it["id"]
            acct = it.get("account", "")
            text = it.get("text", "") or ""
            link = it.get("link")
            problems = validate_postable(text, link, _links_allowed_for(pub_cfg, acct))
            if problems:
                quarantine.append({"id": iid, "account": acct, "reasons": problems})
                continue
            if _at_cap(budget.get(acct, 0), cap):
                skipped_cap += 1
                continue
            channel_id = _channel_id_for(pub_cfg, acct)
            if not channel_id:
                skipped_channel += 1
                continue
            if _within_floor(last_post_at, now, floor_min):
                skipped_floor += 1
                continue
            media = [m.get("path") for m in (it.get("media") or []) if m.get("path")]
            would_post.append({
                "id": iid, "account": acct, "channel": channel_id,
                "chars": len(text), "media": len(media),
                "scheduled_at": it.get("scheduled_at"),
                "preview": text.replace("\n", " ")[:200],
            })
            budget[acct] = budget.get(acct, 0) + 1
            last_post_at = now   # advance the floor so the preview mirrors live pacing

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
                "skipped_floor": skipped_floor,
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
