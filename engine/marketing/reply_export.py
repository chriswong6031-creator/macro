"""engine.marketing.reply_export — the M1 desktop handoff (XG-W4).

The contract between the brain (this repo) and the hands (the operator's
desktop session). The split is deliberate and load-bearing: **Buffer cannot
reply** (``social_publisher._CREATE_POST_MUTATION`` has no reply target), so
every reply necessarily leaves the sanctioned posting rail. Rather than smuggle
a sender into the repo, the queue ends at a directory and a human-supervised
session picks it up.

That boundary is what makes a future official-API write lane a drop-in: nothing
upstream of this module knows how a reply is delivered, and the item schema
already carries both ``local_path`` and ``public_url`` for media.

Directory contract (host state, never the repo checkout):

    ~/.mastermind/reply_desk/
      queue/     <id>.json    exported APPROVED items, ready to send
      claims/    <id>.json    a session's lease; claim BEFORE navigating
      receipts/  <id>.json    screenshot + URL proof that a reply went out

**Mode dial.** M0 exports NOTHING — the queue fills, the critics run, the
operator reviews, and not one byte reaches the desktop lane. M1 exports items an
operator APPROVED in the admin UI, and only those. M2/M3 are config-gated OFF
upstream in ``reply_queue.resolve_mode`` (XG-W6's per-account health monitor and
network tripwire are a hard precondition, because a failure must be able to halt
one account without halting seven).

**Per-account halt (XG-W6).** ``health_monitor.is_halted`` is consulted per
account here and in ``claim_for_desktop``, ahead of the mode and cap gates. A
halted desk exports nothing and can claim nothing while every other desk runs
untouched — this is the reply half of the "halt one without halting seven"
guarantee; ``scripts/marketing_publisher.py`` is the post half. The registry is
read ONCE per sweep and the table is threaded through, so a per-item gate never
re-reads it per item.

Credentials never appear here. They live only in the browser profiles; nothing
in this repo reads them (see ``docs/reply_desk_runbook.md``).

Public API:
    queue_dir/claims_dir/receipts_dir(root=None) -> Path
    export_approved(*, cfg, root=None, now=None) -> dict
    ingest_receipts(*, cfg, root=None, now=None) -> dict
    sweep(*, cfg, root=None, now=None) -> dict
    exported_ids(root=None) -> set[str]
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.marketing import reply_queue as _rq

log = logging.getLogger(__name__)

#: Only these fields cross the boundary. The desktop session needs what to post,
#: where, and by when — not our scoring internals. Keeping the export narrow
#: means a leaked queue file leaks no strategy and no credentials.
_EXPORT_FIELDS: tuple[str, ...] = (
    "id", "as_of", "account", "target_url", "target_status_id", "thread_key",
    "parent_author", "parent_excerpt", "draft", "chart", "tier", "mode",
    "not_before", "expires_at",
)


def queue_dir(root: Path | str | None = None) -> Path:
    return _rq.state_dir(root) / "queue"


def claims_dir(root: Path | str | None = None) -> Path:
    return _rq.state_dir(root) / "claims"


def receipts_dir(root: Path | str | None = None) -> Path:
    return _rq.state_dir(root) / "receipts"


def exported_ids(root: Path | str | None = None) -> set[str]:
    d = queue_dir(root)
    if not d.exists():
        return set()
    return {p.stem for p in d.glob("*.json")}


def _write_json(path: Path, payload: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_export: cannot write %s: %s", path, exc)
        return False


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_export: cannot read %s: %s", path, exc)
        return None


#: A mirror may only exist for an item that is still headed for a send. Anything
#: else on disk is a live instruction to post something we have already killed.
_MIRRORED_STATUSES: frozenset[str] = frozenset({"approved", "claimed"})


def pending_receipt_ids(root: Path | str | None = None) -> set[str]:
    """Item ids with an unconsumed receipt waiting to be ingested."""
    d = receipts_dir(root)
    if not d.exists():
        return set()
    return {p.stem for p in d.glob("*.json")}


def sweep_mirrors(root: Path | str | None = None, *, _state: dict | None = None) -> list[str]:
    """Delete queue mirrors AND stale claims whose item is no longer live.

    Expiry, rejection, and a released lease all have to reach the DESKTOP LANE,
    not just the ledger. A mirror left behind after its item expired is an
    instruction to post a stale reply, and the runbook's "check expires_at" step
    is a human, not a gate. Returns the ids whose mirrors were removed.

    ``claims/`` is swept on the same rule: it is a published contract directory,
    and a lease file that outlives its lease is exactly the divergence the
    directory was wired up to avoid.
    """
    state = _state if _state is not None else _rq.fold_state(root)
    removed: list[str] = []

    d = queue_dir(root)
    if d.exists():
        for path in sorted(d.glob("*.json")):
            if state["status"].get(path.stem) in _MIRRORED_STATUSES:
                continue
            try:
                path.unlink()
                removed.append(path.stem)
            except OSError as exc:
                log.warning("reply_export: cannot clear stale mirror %s: %s", path, exc)

    c = claims_dir(root)
    if c.exists():
        for path in sorted(c.glob("*.json")):
            # A claim file is only meaningful while the item is actually claimed.
            if state["status"].get(path.stem) == "claimed":
                continue
            try:
                path.unlink()
            except OSError as exc:
                log.warning("reply_export: cannot clear stale claim %s: %s", path, exc)

    return removed


def export_approved(
    *,
    cfg: dict | None,
    root: Path | str | None = None,
    repo_root: Path | str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Mirror APPROVED items into the desktop lane's queue directory.

    Four gates, in this order:

    0. **The per-account halt (XG-W6).** A halted desk exports nothing. Checked
       FIRST because it outranks the dial: an account the tripwire silenced must
       not ship even items an operator approved before the trip, and the other
       six desks must be entirely unaffected.
    1. **Expiry runs next, always.** A draft whose window closed must never
       reach the desktop session: by the time a human reads it the reply is
       late, and a late reply under a cold thread is the automation tell we are
       trying not to leave.
    2. **Stale mirrors are swept.** A kill that never reaches the handoff
       directory is not a kill.
    3. **The daily cap binds HERE.** Enforcing it only when a receipt comes back
       would gate bookkeeping, not sending: the reply is already public by then.
       Headroom counts sends already made today PLUS mirrors still in flight, so
       a queue of ten approved items against a cap of one exports one.

    ``root`` is the reply desk's HOST state dir; ``repo_root`` is the checkout
    the halt registry is read from. They are different directories.

    Returns {exported, count, skipped_mode, skipped_cap, skipped_halt,
             halted_accounts, skipped_expired, expired_ids, swept_mirrors,
             modes, headroom}.
    """
    from engine.marketing import health_monitor as _health  # noqa: PLC0415

    ts = now or datetime.now(timezone.utc)
    expired = _rq.expire_due(now=ts, root=root)

    state = _rq.fold_state(root)
    swept = sweep_mirrors(root, _state=state)
    already = exported_ids(root)
    # ONE registry read for the whole sweep — a per-item read would re-parse the
    # file once per approved draft.
    halts = _health.load_halts(repo_root)

    exported: list[str] = []
    skipped_mode: list[str] = []
    skipped_cap: list[str] = []
    skipped_halt: list[str] = []
    modes: dict[str, str] = {}
    headroom: dict[str, int] = {}
    caps_seen: dict[str, int] = {}

    # Deterministic order: best score first, so a capped account exports its
    # strongest opportunities rather than whichever item hashed first.
    candidates = sorted(
        (iid for iid, st in state["status"].items() if st == "approved"),
        key=lambda i: (-float(state["items"][i].get("score") or 0.0), i),
    )

    for iid in candidates:
        item = state["items"][iid]
        account = str(item.get("account") or "")

        # HALT GATE — outranks the dial and the cap. Per account, by
        # construction: there is no code path here that can stop a second desk.
        if _health.is_halted(account, halts=halts):
            skipped_halt.append(iid)
            continue

        if account not in modes:
            modes[account] = _rq.resolve_mode(cfg, account)
        mode = modes[account]
        # M0 is draft-only. This is the single line that keeps the launch state
        # honest: everything upstream runs, nothing leaves.
        if mode == "M0":
            skipped_mode.append(iid)
            continue

        if account not in headroom:
            # Reuse the fold already computed above — may_send would otherwise
            # re-read and re-fold the whole ledger once per account.
            gate = _rq.may_send(account, cfg=cfg, root=root, now=ts, _state=state)
            in_flight = sum(
                1 for other in already
                if str((state["items"].get(other) or {}).get("account") or "") == account
            )
            caps_seen[account] = int(gate["cap"])
            headroom[account] = max(0, int(gate["cap"]) - int(gate["sent"]) - in_flight)

        if iid in already:
            continue
        if headroom[account] <= 0:
            skipped_cap.append(iid)
            continue

        payload = {k: item.get(k) for k in _EXPORT_FIELDS}
        payload["exported_at"] = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        if _write_json(queue_dir(root) / f"{iid}.json", payload):
            exported.append(iid)
            headroom[account] -= 1

    if skipped_halt:
        halted_here = sorted({
            str((state["items"].get(i) or {}).get("account") or "") for i in skipped_halt
        })
        print(
            f"::warning title=reply-export-halted::{len(skipped_halt)} approved repl"
            f"{'ies' if len(skipped_halt) != 1 else 'y'} held back — account(s) "
            f"{halted_here} are HALTED (health monitor / network tripwire). Every "
            "other desk exported normally. Clear the halt in the admin health panel.",
            flush=True,
        )

    if skipped_cap:
        # Report the caps that BOUND, not the post-loop headroom (which is 0 for
        # every account by construction and tells the operator nothing).
        bound = {a: caps_seen[a] for a in sorted({
            str((state["items"].get(i) or {}).get("account") or "") for i in skipped_cap
        }) if a in caps_seen}
        print(
            f"::warning title=reply-cap-export::{len(skipped_cap)} approved repl"
            f"{'ies' if len(skipped_cap) != 1 else 'y'} held back at the daily cap "
            f"(caps {bound}) — raise the dial or let them expire",
            flush=True,
        )

    return {
        "exported": exported,
        "count": len(exported),
        "skipped_mode": skipped_mode,
        "skipped_cap": skipped_cap,
        "skipped_halt": skipped_halt,
        "halted_accounts": sorted(halts),
        "skipped_expired": len(expired),
        "expired_ids": expired,
        "swept_mirrors": swept,
        "modes": modes,
        "headroom": headroom,
    }


def claim_for_desktop(
    item_id: str,
    *,
    holder: str,
    lease_s: int | None = None,
    cfg: dict | None = None,
    root: Path | str | None = None,
    repo_root: Path | str | None = None,
    now: datetime | None = None,
) -> dict | None:
    """Take a lease AND write the claim file the handoff contract publishes.

    The desktop session claims before navigating. Writing the claim to
    ``claims/`` keeps the published directory contract honest — a directory in a
    contract that no code ever touches grows divergent implementations on the
    other side of the boundary.
    """
    if lease_s is None:
        # Via the fail-soft helper: a typo'd lease_s must not take down the
        # desktop claim path, which is step 3 of the runbook.
        lease_s = _rq.lease_s_for(cfg)

    from engine.marketing import health_monitor as _health  # noqa: PLC0415

    # The dial gates EVERY host-dir write, not just the export. This was the one
    # path that wrote into ~/.mastermind while an account sat at M0, which made
    # "M0 exports NOTHING" false by a file. The halt gate rides the same path
    # for the same reason: an export-only halt would still let a session claim
    # (and therefore send) an item mirrored before the trip.
    state = _rq.fold_state(root)
    account = str((state["items"].get(item_id) or {}).get("account") or "")
    if account and _health.is_halted(account, root=repo_root):
        print(
            f"::warning title=reply-claim-halted::{account!r} is HALTED — refusing "
            f"the claim on {item_id}; other desks are unaffected",
            flush=True,
        )
        return None
    if account and _rq.resolve_mode(cfg, account) == "M0":
        log.warning("reply_export.claim_for_desktop: %r is at M0 — nothing may be claimed",
                    account)
        return None

    claim = _rq.claim(item_id, holder=holder, lease_s=lease_s, root=root, now=now)
    if claim is None:
        return None
    _write_json(claims_dir(root) / f"{item_id}.json", claim)
    return claim


def ingest_receipts(
    *,
    cfg: dict | None,
    root: Path | str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read screenshot+URL receipts back and record real sends.

    A receipt is the ONLY evidence a reply went out. ``mark_sent`` re-checks the
    per-account daily cap here rather than trusting the export-time check: the
    desktop session runs on its own clock, and a cap enforced only upstream is a
    cap a slow queue walks straight through.

    Receipt files are consumed (renamed to ``.done``) so a re-run never
    double-counts a send against the cap.
    """
    ts = now or datetime.now(timezone.utc)
    d = receipts_dir(root)
    recorded: list[str] = []
    refused: list[dict] = []
    if not d.exists():
        return {"recorded": recorded, "refused": refused, "count": 0}

    for path in sorted(d.glob("*.json")):
        payload = _read_json(path)
        if not payload:
            continue
        iid = str(payload.get("id") or payload.get("item_id") or path.stem)

        # A receipt is the only evidence a reply went out, so an empty one is
        # not evidence. The URL is the machine-checkable half and is required;
        # a missing screenshot is announced but does not void the send, because
        # refusing it would leave a PUBLIC reply permanently uncounted.
        url = str(payload.get("url") or "").strip()
        if not url:
            refused.append({"id": iid, "reason": "receipt_missing_url"})
            _retire(path, ".invalid")
            print(
                f"::warning title=reply-receipt-invalid::receipt for {iid} has no URL "
                "— cannot record a send without proof of one",
                flush=True,
            )
            continue
        if not str(payload.get("screenshot") or "").strip():
            print(
                f"::warning title=reply-receipt-no-shot::receipt for {iid} carries a URL "
                "but no screenshot — recorded, but it cannot be audited by eye",
                flush=True,
            )

        receipt = {
            "url": url,
            "screenshot": payload.get("screenshot"),
            "holder": payload.get("holder"),
            "reported_at": payload.get("sent_at") or ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        result = _rq.mark_sent(iid, receipt=receipt, actor=str(payload.get("holder") or "desktop"),
                               root=root, cfg=cfg, now=ts)
        if result.get("ok"):
            recorded.append(iid)
            _retire(path, ".done")
            # The item has left; its queue mirror and claim are stale.
            for stale in (queue_dir(root) / f"{iid}.json", claims_dir(root) / f"{iid}.json"):
                if stale.exists():
                    try:
                        stale.unlink()
                    except OSError as exc:
                        log.warning("reply_export: cannot clear %s: %s", stale, exc)
        else:
            reason = result.get("reason")
            refused.append({"id": iid, "reason": reason})
            if reason == "reply_cap_daily":
                # Retryable and ONLY this one: a spent cap clears at midnight, so
                # the receipt is worth keeping. A silenced account (cap nulled,
                # desk disabled, M0) never clears on its own, so retaining its
                # receipt would warn on every sweep forever with nothing an
                # operator could do about it — those fall to the park branch.
                print(
                    f"::warning title=reply-cap-daily::receipt for {iid} refused: account "
                    f"hit its daily reply cap ({result.get('sent')}/{result.get('cap')})",
                    flush=True,
                )
            else:
                # Everything else is terminal for this receipt: retrying can
                # never succeed, and a receipt re-read and re-refused on every
                # sweep is a permanent warning nobody can clear. This branch is
                # deliberately a catch-all rather than a list of known reasons —
                # `mode_m0_draft_only` (the desk disabled after a send went out)
                # fell through an earlier list of two and looped forever in
                # silence, which is the worst version of this bug.
                _retire(path, ".unresolved")
                print(
                    f"::warning title=reply-receipt-orphan::receipt for {iid} refused "
                    f"({reason}) — the reply may be PUBLIC but unrecorded; parked as "
                    ".unresolved for review",
                    flush=True,
                )

    return {"recorded": recorded, "refused": refused, "count": len(recorded)}


def _retire(path: Path, suffix: str) -> None:
    """Rename a consumed receipt so a re-run never re-reads it.

    Never clobbers: two receipts retiring to the same suffix would otherwise
    silently overwrite, and a receipt is evidence about a public reply.
    """
    target = path.with_suffix(suffix)
    n = 1
    while target.exists():
        target = path.with_suffix(f"{suffix}.{n}")
        n += 1
    try:
        path.rename(target)
    except OSError as exc:
        log.warning("reply_export: cannot retire receipt %s: %s", path, exc)


def sweep(
    *,
    cfg: dict | None,
    root: Path | str | None = None,
    repo_root: Path | str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """One full desk tick: ingest, reclaim, expire, sweep, export.

    Ordering matters and this is the order:

    1. **Ingest receipts first.** A send that happened since the last tick must
       be on the books BEFORE the cap is computed, or the export step hands out
       headroom that is already spent.
    2. **Release expired leases**, so an item whose session died is reclaimable.
    3. **Expire, sweep, and export** (inside ``export_approved``), so nothing
       stale reaches the desktop lane and the cap binds before anything ships.

    An earlier version ran export first and ingest last, which meant every tick
    sized the cap against a stale send count.
    """
    ts = now or datetime.now(timezone.utc)
    ingested = ingest_receipts(cfg=cfg, root=root, now=ts)
    # A receipt that survived ingest (a cap deferral, say) still describes a
    # PUBLIC reply. Releasing its lease would move the item to `queued`, which
    # has no edge to `sent`, so the send could never be recorded afterwards —
    # and the cap is sized against that count, so the loss buys back a slot.
    released = _rq.release_expired_claims(now=ts, root=root,
                                          skip_ids=pending_receipt_ids(root))
    result = export_approved(cfg=cfg, root=root, repo_root=repo_root, now=ts)
    return {
        "ingest": ingested,
        "released_claims": released,
        "export": result,
        "at": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


__all__ = [
    "queue_dir", "claims_dir", "receipts_dir", "exported_ids",
    "export_approved", "ingest_receipts", "sweep", "sweep_mirrors",
    "claim_for_desktop", "pending_receipt_ids",
]
