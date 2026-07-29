"""scripts/marketing_recall.py — pull back posts that are booked but not yet sent.

THE HOLE THIS CLOSES.
`publish.max_forward_book_min` (#3913, 2026-07-28) let one publish sweep book
several posts ahead as Buffer `customScheduled` sends, up to an hour out. That
decoupled throughput from the cron grid, which was the point — but it also
quietly broke the operator kill switch. `MARKETING_PUBLISH_ENABLED=0` stops the
runner from creating NEW posts; it has no reach at all into posts already handed
to Buffer, which fire on Buffer's schedule regardless.

It bit the same day it shipped. A sweep at 16:25:46Z booked five posts for
16:31 / 16:41 / 16:56 / 17:12 / 17:27Z. The operator found quality defects and
disarmed the publisher at 16:26:47Z — ONE MINUTE later — and it changed nothing.
All five were already in Buffer's queue; three of them were posts already
identified as defective; the only recall available was the operator deleting
them by hand in the Buffer UI. This runner is the missing half of that switch.

WHAT "RECALLABLE" MEANS — the safety core, and the only part worth arguing about.
An item is a candidate if and only if ALL of:
  1. its folded outbox status is `posted`;
  2. its `posted` ledger row carries a receipt with a non-empty `external_id`
     (the Buffer post id — without it there is nothing to cancel); and
  3. the wall-clock it was BOOKED for (receipt `booked_at`, falling back to the
     receipt/row `at`) is STRICTLY IN THE FUTURE relative to `now`.
Rule 3 is what keeps an already-sent post out of reach. An unparseable or
missing send time is NOT a candidate either — fail closed; we never delete
something whose send time we cannot read. And the item only leaves `posted` on a
CONFIRMED backend delete (DeleteResult.ok): a delete that errors, times out, or
comes back ambiguous leaves the item exactly where it was, reported as failed.

Together those give the two guarantees the outbox depends on:
  * a genuinely-sent post is never resurrected — it stays `posted` forever, so
    posted_today_by_account keeps counting it and no cap is silently refilled;
  * a recalled post can never re-send — `recalled` is TERMINAL in
    outbox.TRANSITIONS, with no edge back to approved or queued.

WHY THIS IS NOT GATED ON THE KILL SWITCH.
scripts/marketing_publisher.py self-downgrades to dry-run unless
MARKETING_PUBLISH_ENABLED is on. This runner deliberately does NOT. Recall is a
STOP action, not a send action, and the moment an operator most needs it is the
moment they have just switched the publisher off. Gating recall on the arm
variable would make it inoperable in precisely the situation it exists for. The
safety here comes from `--live` (dry-run is the default) plus the candidate
rules above — never from the arm state.

Usage:
    # dry-run (default): print exactly what WOULD be recalled, ZERO network calls
    python -m scripts.marketing_recall --recall-pending
    python -m scripts.marketing_recall --ids out-abc123,out-def456
    python -m scripts.marketing_recall --as-of 2026-07-28 --account flagship

    # LIVE recall — one action, everything booked-but-unsent:
    BUFFER_TOKEN=... python -m scripts.marketing_recall --recall-pending --live

Exit codes: 0 = nothing to do, or every attempted recall succeeded.
            1 = at least one delete FAILED — posts the operator asked to stop are
                still scheduled to go out. That is an incident, so it is red.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

log = logging.getLogger("marketing_recall")

_PUBLICATIONS_REL = Path("data/marketing/publications.jsonl")


# ─────────────────────────────────────────────────────────────────────────────
# Bootstrapping helpers (mirror scripts/marketing_publisher.py)
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


def _parse_now(now_arg: str | None) -> datetime:
    if not now_arg:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(now_arg.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        log.warning("bad --now %r — using current time", now_arg)
        return datetime.now(timezone.utc)


def _parse_iso(ts: object) -> datetime | None:
    """Parse an iso8601-ish timestamp to an aware UTC datetime, or None.

    None on ANYTHING unreadable — the caller treats that as "not recallable",
    so a lenient parse here would be a safety hole, not a convenience.
    """
    if not ts:
        return None
    s = str(ts).strip()
    if not s:
        return None
    for candidate in (s, s.replace("Z", "+00:00")):
        try:
            dt = datetime.fromisoformat(candidate)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _make_publisher(backend: str, *, token: str, cfg: dict):
    """Instantiate the configured backend publisher. Returns None if unsupported.

    Defined HERE rather than imported from scripts.marketing_publisher so tests
    monkeypatch this module's own seam (and so a recall never drags the
    publisher's post-time gates into its import closure).
    """
    from engine.marketing.social_publisher import BufferPublisher  # noqa: PLC0415
    if backend == "buffer":
        return BufferPublisher(token=token)
    log.error("unsupported publish backend %r", backend)
    return None


def _append_publication(root: Path | str | None, row: dict) -> None:
    """Append a publication receipt row. Fail-soft — a bookkeeping write must
    never turn a successful recall into a crash."""
    from engine.marketing.ledgers import append_jsonl  # noqa: PLC0415
    try:
        append_jsonl(Path(_data_root(root)) / _PUBLICATIONS_REL, row)
    except Exception as exc:  # noqa: BLE001
        log.warning("recall: publications.jsonl append failed for %s: %s",
                    row.get("asset_id", "?"), exc)


# ─────────────────────────────────────────────────────────────────────────────
# Candidate selection — the safety core
# ─────────────────────────────────────────────────────────────────────────────

#: Why an item that looked recallable is not. Surfaced verbatim in the summary
#: so an operator can tell "already went out" from "we never stored the id".
SKIP_NOT_POSTED = "not_posted"
SKIP_NO_RECEIPT = "no_buffer_post_id"
SKIP_UNREADABLE_SEND_TIME = "unreadable_send_time"
SKIP_ALREADY_SENT = "already_sent"
SKIP_UNKNOWN_ID = "unknown_item_id"


def _receipt_of(last_row: dict) -> dict:
    """The receipt dict off an item's last applied ledger row ({} if absent)."""
    rec = (last_row or {}).get("receipt")
    return rec if isinstance(rec, dict) else {}


def _booked_send_time(receipt: dict, last_row: dict) -> datetime | None:
    """The wall-clock this post is scheduled to go out, or None if unreadable.

    Prefers the receipt's ``booked_at`` — the time the publisher actually booked
    the send for, which with forward-booking and send-time jitter is minutes to
    an hour AFTER the ledger row was written. Falls back to the receipt `at`,
    then the row `at`, both of which equal booked_at on any post written before
    forward-booking shipped.
    """
    return (_parse_iso(receipt.get("booked_at"))
            or _parse_iso(receipt.get("at"))
            or _parse_iso((last_row or {}).get("at")))


def select_candidates(
    state: dict,
    *,
    now: datetime,
    ids: "frozenset[str] | None" = None,
    account: str | None = None,
    as_of: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Split the outbox into (recallable, skipped).

    PURE — no I/O, no network, no clock read (``now`` is injected). `state` is an
    outbox.fold_state() dict.

    ``ids`` restricts to explicit item ids and, when given, makes every named id
    that is NOT recallable appear in `skipped` with a reason — an operator who
    names five ids deserves five answers, not silence about the two that already
    went out. Without ``ids`` the sweep is every posted item, narrowed by the
    optional ``account`` / ``as_of`` filters, and items filtered out that way are
    simply not mentioned.

    Each recallable entry: {id, account, external_id, booked_at, item}.
    Each skipped entry:    {id, account, reason, booked_at|None}.
    """
    items = state.get("items") or {}
    statuses = state.get("status") or {}
    last = state.get("last") or {}
    order = state.get("order") or list(items)

    recallable: list[dict] = []
    skipped: list[dict] = []
    seen_named: set[str] = set()

    for iid in order:
        it = items.get(iid)
        if not isinstance(it, dict):
            continue
        named = ids is not None and iid in ids
        if named:
            seen_named.add(iid)
        if ids is not None and not named:
            continue
        if not named:
            # Scope filters apply to the SWEEP only; an explicitly named id is
            # honoured whatever account or day it belongs to.
            if account is not None and it.get("account") != account:
                continue
            if as_of is not None and str(it.get("as_of") or "") != as_of:
                continue

        acct = str(it.get("account") or "")
        reason: str | None = None
        booked: datetime | None = None
        external_id = ""

        if statuses.get(iid) != "posted":
            reason = SKIP_NOT_POSTED
        else:
            last_row = last.get(iid) or {}
            receipt = _receipt_of(last_row)
            external_id = str(receipt.get("external_id") or "").strip()
            if not external_id:
                # Without the backend post id there is nothing to cancel. This
                # is the failure mode that would make recall structurally
                # impossible, so it is reported loudly, not skipped in silence.
                log.warning("item %s is posted but its receipt carries no external_id "
                            "— cannot recall (nothing to cancel)", iid)
                reason = SKIP_NO_RECEIPT
            else:
                booked = _booked_send_time(receipt, last_row)
                if booked is None:
                    log.warning("item %s has an unreadable booked send time — NOT "
                                "recalling (fail closed)", iid)
                    reason = SKIP_UNREADABLE_SEND_TIME
                elif booked <= now:
                    # ALREADY SENT (or sending this very second). Never touch it:
                    # the post is out in the world, the ledger must keep saying
                    # so, and a delete here would only remove Buffer's record of
                    # a live post.
                    reason = SKIP_ALREADY_SENT

        if reason is not None:
            # A NAMED id always gets an answer — five ids in, five answers out.
            # A SWEEP reports only posted items it could not recall (already
            # sent / no id / unreadable time), because those are the ones an
            # operator needs to see: "three of them already went out, you were
            # too late for those". It stays silent about items that were never
            # posted at all, which would just be the whole queue.
            if named or reason != SKIP_NOT_POSTED:
                skipped.append({
                    "id": iid, "account": acct, "reason": reason,
                    "booked_at": (booked.strftime(_TS_FMT)
                                  if booked is not None and reason == SKIP_ALREADY_SENT
                                  else None),
                })
            continue

        recallable.append({
            "id": iid,
            "account": acct,
            "external_id": external_id,
            "booked_at": booked.strftime(_TS_FMT),
            "item": it,
        })

    # An id the operator named that does not exist in the outbox at all. Almost
    # always a typo or a stale id from an older ledger — either way it must come
    # back as an answer, not vanish. Silence here reads as "handled".
    for missing in sorted((ids or frozenset()) - seen_named):
        log.warning("item %s is not in the outbox — nothing to recall", missing)
        skipped.append({"id": missing, "account": "", "reason": SKIP_UNKNOWN_ID,
                        "booked_at": None})

    return recallable, skipped


def _retraction_row(cand: dict, *, at: str) -> dict:
    """A publications.jsonl correction row for a recalled post.

    publications.jsonl is APPEND-ONLY (tests pin that), so the correction is a
    new row carrying the SAME publication_id as the original with
    correction_state "retracted" — the schema's existing vocabulary, no contract
    change. engine.marketing.state folds publications by publication_id
    last-row-wins, so this supersedes the "clean/live" row rather than
    double-counting it, and the Channels page stops claiming a post that never
    went out.
    """
    iid = str(cand.get("id") or "")
    it = cand.get("item") or {}
    return {
        "publication_id": f"pub-{iid}" if iid else f"pub-{cand.get('external_id')}",
        "asset_id": iid,
        "channel": "x",
        "account": it.get("account", ""),
        "remote_id": cand.get("external_id"),
        # The time it WOULD have gone out — kept so the row sorts where the
        # original did in any published_at ordering.
        "published_at": cand.get("booked_at") or at,
        "policy_version": str(it.get("policy_version") or "v1"),
        "audience": "public",
        "destination": "x_timeline",
        "campaign_id": str(it.get("campaign_id") or it.get("provenance") or "publisher_live"),
        "correction_state": "retracted",
        "takedown_method": "unpublish_via_adapter",
        "mode": "live",
        "recalled_at": at,
        "note": "cancelled at the backend before it sent (marketing_recall)",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Recall
# ─────────────────────────────────────────────────────────────────────────────

def recall_items(
    candidates: list[dict],
    *,
    publisher,
    root: Path,
    now: datetime,
    actor: str = "recall",
    note: str | None = None,
) -> dict:
    """Cancel each candidate at the backend and transition it out of `posted`.

    Returns {"recalled": [...], "failed": [{id, external_id, error}, ...]}.

    The order is deliberate and is the no-double-post discipline in miniature:
    DELETE FIRST, then move the ledger, and only on a confirmed delete. The
    publisher does the mirror image (ledger `posting` BEFORE the network call) —
    both choices make the ledger's error state the SAFE one. A crash between the
    delete and the transition leaves an item marked `posted` that is actually
    cancelled: it will not send, it is merely mis-labelled, and a re-run reports
    it. The reverse order would leave an item marked `recalled` that is still
    scheduled to fire, which is the failure this whole runner exists to prevent.
    """
    from engine.marketing import outbox as _outbox  # noqa: PLC0415

    out: dict = {"recalled": [], "failed": []}
    for cand in candidates:
        iid, external_id = cand["id"], cand["external_id"]
        result = publisher.delete_post(external_id, now=now)
        if not result.ok:
            log.error("item %s: backend refused to cancel post %s — %s "
                      "(LEAVING IT posted; it is still scheduled to send)",
                      iid, external_id, result.error)
            out["failed"].append({"id": iid, "external_id": external_id,
                                  "error": result.error})
            continue

        at = result.at or now.strftime(_TS_FMT)
        moved = _outbox.transition(
            iid, "recalled", actor=actor, root=root,
            note=note or "cancelled before send (kill-switch recall)",
            receipt={
                "backend": result.backend,
                "external_id": external_id,
                "at": at,
                # What the post WOULD have gone out at, preserved so the audit
                # trail shows how much warning the recall actually had.
                "booked_at": cand.get("booked_at"),
                "deleted": True,
            },
            now=now,
        )
        if not moved:
            # The delete DID succeed, so the post will not send — but the ledger
            # now disagrees with reality. Loud, not silent.
            log.error("item %s: post %s was cancelled at the backend but the "
                      "posted→recalled transition failed — the ledger still says "
                      "posted. The post will NOT send.", iid, external_id)
            out["failed"].append({"id": iid, "external_id": external_id,
                                  "error": "ledger_transition_failed_after_delete"})
            continue

        _append_publication(root, _retraction_row(cand, at=at))
        log.info("recalled %s (%s) — cancelled Buffer post %s booked for %s",
                 iid, cand.get("account"), external_id, cand.get("booked_at"))
        out["recalled"].append({"id": iid, "external_id": external_id,
                                "booked_at": cand.get("booked_at")})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Recall marketing posts booked at the backend but not yet sent "
                    "(dry-run by default)")
    parser.add_argument("--live", action="store_true",
                        help="Actually cancel at the backend and move the ledger. "
                             "Without this flag the runner is a dry-run and makes "
                             "ZERO network calls. Deliberately NOT gated on "
                             "MARKETING_PUBLISH_ENABLED — recall must work when the "
                             "publisher is disarmed, which is when it is needed.")
    parser.add_argument("--recall-pending", action="store_true",
                        help="Select EVERY booked-but-unsent post (optionally "
                             "narrowed by --account/--as-of). This is the one-action "
                             "companion to flipping the kill switch off.")
    parser.add_argument("--ids", default=None, metavar="ID[,ID…]",
                        help="Recall these specific outbox item ids. Each named id "
                             "that cannot be recalled is reported with a reason.")
    parser.add_argument("--account", default=None,
                        help="Only consider this account id (default: all)")
    parser.add_argument("--as-of", default=None, dest="as_of",
                        help="Only consider items with this as_of date (YYYY-MM-DD)")
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
    now = _parse_now(args.now)

    ids: "frozenset[str] | None" = None
    if args.ids:
        ids = frozenset(p.strip() for p in str(args.ids).split(",") if p.strip())
        if not ids:
            ids = None

    if ids is None and not args.recall_pending:
        # Refuse an unscoped recall. --account/--as-of narrow a sweep; they do
        # not authorise one. Recalling the whole queue is a big enough action to
        # deserve saying so out loud.
        log.error("nothing selected — pass --recall-pending to sweep every "
                  "booked-but-unsent post, or --ids to name specific items")
        return 2

    from engine.marketing import outbox as _outbox  # noqa: PLC0415

    state = _outbox.fold_state(root)
    recallable, skipped = select_candidates(
        state, now=now, ids=ids, account=args.account, as_of=args.as_of)

    for s in skipped:
        log.info("SKIP %s (%s) — %s%s", s["id"], s["account"], s["reason"],
                 f" (booked {s['booked_at']})" if s.get("booked_at") else "")

    if not recallable:
        log.info("nothing to recall — no booked-and-unsent post found "
                 "(%d posted item(s) examined and passed over)", len(skipped))
        return 0

    # ── DRY-RUN: print, never touch the network or the ledger ────────────────
    if not args.live:
        for c in recallable:
            log.info("WOULD RECALL | item=%s account=%s buffer_post=%s booked_at=%s\n    %s",
                     c["id"], c["account"], c["external_id"], c["booked_at"],
                     str((c["item"].get("text") or "")).replace("\n", " ")[:160])
        log.info("dry-run: %d post(s) WOULD be recalled, %d skipped. "
                 "Re-run with --live to actually cancel them.",
                 len(recallable), len(skipped))
        return 0

    # ── LIVE ─────────────────────────────────────────────────────────────────
    cfg = _load_marketing_cfg(root)
    pub_cfg = _publish_cfg(cfg)
    backend = str(pub_cfg.get("backend") or "buffer").strip()
    token = os.environ.get("BUFFER_TOKEN", "").strip()
    if not token:
        print("::error title=marketing-recall::BUFFER_TOKEN is unset — cannot cancel "
              f"{len(recallable)} booked post(s); they WILL send", flush=True)
        log.error("--live passed but BUFFER_TOKEN is empty — %d booked post(s) "
                  "cannot be cancelled and will send on schedule", len(recallable))
        return 1

    publisher = _make_publisher(backend, token=token, cfg=cfg)
    if publisher is None:
        print(f"::error title=marketing-recall::unsupported backend {backend!r} — "
              f"{len(recallable)} booked post(s) could not be cancelled", flush=True)
        return 1

    result = recall_items(recallable, publisher=publisher, root=root, now=now)
    n_ok, n_bad = len(result["recalled"]), len(result["failed"])

    log.info("recall complete | recalled=%d failed=%d skipped=%d", n_ok, n_bad, len(skipped))
    if n_ok:
        print(f"::notice title=marketing-recall::cancelled {n_ok} booked-but-unsent "
              "post(s) before they sent", flush=True)
    if n_bad:
        # These are still scheduled to go out. The operator has to know NOW, and
        # the job has to be red.
        print(f"::error title=marketing-recall::{n_bad} post(s) could NOT be "
              "cancelled and are still scheduled to send — delete them by hand in "
              "the Buffer queue", flush=True)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
