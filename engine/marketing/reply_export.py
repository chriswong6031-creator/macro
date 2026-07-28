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


def export_approved(
    *,
    cfg: dict | None,
    root: Path | str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Mirror APPROVED items into the desktop lane's queue directory.

    Expiry runs FIRST, always. A draft whose window closed must never reach the
    desktop session: by the time a human reads it the reply is late, and a late
    reply under a cold thread is the automation tell we are trying not to leave.

    Returns {exported, skipped_mode, skipped_expired, expired_ids, modes}.
    """
    ts = now or datetime.now(timezone.utc)
    expired = _rq.expire_due(now=ts, root=root)

    state = _rq.fold_state(root)
    already = exported_ids(root)
    exported: list[str] = []
    skipped_mode: list[str] = []
    modes: dict[str, str] = {}

    for iid, item in state["items"].items():
        if state["status"].get(iid) != "approved":
            continue
        account = str(item.get("account") or "")
        mode = modes.get(account)
        if mode is None:
            mode = _rq.resolve_mode(cfg, account)
            modes[account] = mode
        # M0 is draft-only. This is the single line that keeps the launch state
        # honest: everything upstream runs, nothing leaves.
        if mode == "M0":
            skipped_mode.append(iid)
            continue
        if iid in already:
            continue
        payload = {k: item.get(k) for k in _EXPORT_FIELDS}
        payload["exported_at"] = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        if _write_json(queue_dir(root) / f"{iid}.json", payload):
            exported.append(iid)

    return {
        "exported": exported,
        "count": len(exported),
        "skipped_mode": skipped_mode,
        "skipped_expired": len(expired),
        "expired_ids": expired,
        "modes": modes,
    }


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
        receipt = {
            "url": payload.get("url"),
            "screenshot": payload.get("screenshot"),
            "holder": payload.get("holder"),
            "reported_at": payload.get("sent_at") or ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        result = _rq.mark_sent(iid, receipt=receipt, actor=str(payload.get("holder") or "desktop"),
                               root=root, cfg=cfg, now=ts)
        if result.get("ok"):
            recorded.append(iid)
            try:
                path.rename(path.with_suffix(".done"))
            except Exception as exc:  # noqa: BLE001
                log.warning("reply_export: cannot retire receipt %s: %s", path, exc)
            # The item has left; its queue mirror is stale.
            qpath = queue_dir(root) / f"{iid}.json"
            if qpath.exists():
                try:
                    qpath.unlink()
                except Exception as exc:  # noqa: BLE001
                    log.warning("reply_export: cannot clear queue mirror %s: %s", qpath, exc)
        else:
            refused.append({"id": iid, "reason": result.get("reason")})
            if result.get("reason") == "reply_cap_daily":
                print(
                    f"::warning title=reply-cap-daily::receipt for {iid} refused: account "
                    f"hit its daily reply cap ({result.get('sent')}/{result.get('cap')})",
                    flush=True,
                )

    return {"recorded": recorded, "refused": refused, "count": len(recorded)}


def sweep(
    *,
    cfg: dict | None,
    root: Path | str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """One full desk tick: reclaim, expire, export, ingest.

    Ordering matters. Leases are released before expiry so an item whose session
    died still gets a fair expiry check; expiry runs before export so nothing
    stale leaves; receipts are ingested last so a send recorded this tick counts
    against the cap the next one reads.
    """
    ts = now or datetime.now(timezone.utc)
    released = _rq.release_expired_claims(now=ts, root=root)
    result = export_approved(cfg=cfg, root=root, now=ts)
    ingested = ingest_receipts(cfg=cfg, root=root, now=ts)
    return {
        "released_claims": released,
        "export": result,
        "ingest": ingested,
        "at": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


__all__ = [
    "queue_dir", "claims_dir", "receipts_dir", "exported_ids",
    "export_approved", "ingest_receipts", "sweep",
]
