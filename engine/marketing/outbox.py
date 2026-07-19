"""engine.marketing.outbox — Posting-queue contract for the D02 desk network.

Contract:
  * Producers call enqueue() to append item records to items.jsonl.
  * Only the actuator (scripts/marketing_actuator.py or W1 publisher) may call
    transition() to advance statuses in status_ledger.jsonl.
  * Admin/operator decisions are recorded via record_decision(); the actuator
    then applies them as transitions.

Storage layout (all paths relative to repo root; written ONLY through this module):
  data/marketing/outbox/items.jsonl          — append-only item records
  data/marketing/outbox/status_ledger.jsonl  — append-only status transitions
  data/marketing/outbox/decisions.jsonl      — operator approve/hold decisions
  data/marketing/outbox/media/<as_of>/<chart_id>.svg  — chart snapshots

This is display-tier ops state — not a forward signal ledger.  Items describe
what the actuator should post; the ledger records what actually happened.  The
gauntlet does not apply here; nulls are the honest initial state.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.marketing.ledgers import append_jsonl, read_jsonl

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA_ID = "marketing.outbox/v1"

KINDS: frozenset[str] = frozenset({
    "signal", "chart", "education", "macro", "receipt",
    "watchlist", "event", "mover", "theme_list",
})

# Status machine — only these transitions are legal.
TRANSITIONS: dict[str, frozenset[str]] = {
    "queued":      frozenset({"approved", "quarantined"}),
    "approved":    frozenset({"posted", "failed", "quarantined"}),
    "failed":      frozenset({"approved", "quarantined"}),
    "posted":      frozenset(),   # terminal
    "quarantined": frozenset(),   # terminal
}

# Last-resort fallback ceiling only. D08 Sentinel owns the real cap
# (config/marketing.yml sentinel: max_posts_per_account_per_day) — see
# effective_cap(). Docket law: the actuator reads its caps from Sentinel
# config, never its own constants.
DEFAULT_MAX_POSTS_PER_ACCOUNT_PER_DAY: int = 8


# ─────────────────────────────────────────────────────────────────────────────
# Directory helpers
# ─────────────────────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    """Derive repo root the same way other marketing modules do."""
    return Path(__file__).resolve().parent.parent.parent


def outbox_dir(root: Path | str | None = None) -> Path:
    """Return the outbox directory: <root>/data/marketing/outbox."""
    r = Path(root) if root is not None else _repo_root()
    return r / "data" / "marketing" / "outbox"


# ─────────────────────────────────────────────────────────────────────────────
# Effective cap
# ─────────────────────────────────────────────────────────────────────────────

def effective_cap(cfg: dict) -> int:
    """Return the effective per-account-per-day cap.

    The authoritative cap is the D08 Sentinel one
    (sentinel.max_posts_per_account_per_day — ships at the weeks_1_2
    new-account tier). outbox.max_posts_per_account_per_day may LOWER it
    further, never raise it; DEFAULT_MAX_POSTS_PER_ACCOUNT_PER_DAY (8) is
    the last-resort ceiling when no config is present at all.
    """
    try:
        sentinel_cap = int((cfg.get("sentinel") or {}).get(
            "max_posts_per_account_per_day", DEFAULT_MAX_POSTS_PER_ACCOUNT_PER_DAY))
    except Exception:  # noqa: BLE001
        sentinel_cap = DEFAULT_MAX_POSTS_PER_ACCOUNT_PER_DAY
    try:
        outbox_cap = int((cfg.get("outbox") or {}).get(
            "max_posts_per_account_per_day", sentinel_cap))
    except Exception:  # noqa: BLE001
        outbox_cap = sentinel_cap
    return max(0, min(outbox_cap, sentinel_cap, DEFAULT_MAX_POSTS_PER_ACCOUNT_PER_DAY))


# ─────────────────────────────────────────────────────────────────────────────
# Item construction
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_text(text: str) -> str:
    """Collapse whitespace runs to single spaces, strip edges."""
    return re.sub(r"\s+", " ", text.strip())


def _item_id(account: str, kind: str, text: str, as_of: str) -> str:
    """Deterministic item id: sha1(account|kind|normalized_text|as_of)[:10]."""
    normalized = _normalize_text(text)
    raw = f"{account}|{kind}|{normalized}|{as_of}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"ob-{as_of}-{digest}"


def make_item(
    *,
    account: str,
    kind: str,
    text: str,
    as_of: str,
    media: list[dict] | None = None,
    scheduled_at: str = "immediate",
    slot: str | None = None,
    priority: int = 5,
    provenance: str,
    source: dict | None = None,
    now: datetime | None = None,
) -> dict:
    """Build and validate an outbox item dict.

    Raises ValueError on invalid inputs (bad kind, empty text, empty account,
    empty provenance).  All other public API functions are fail-soft.
    """
    if not account or not account.strip():
        raise ValueError("account must be a non-empty string")
    if kind not in KINDS:
        raise ValueError(f"kind {kind!r} not in KINDS; valid: {sorted(KINDS)}")
    if not text or not text.strip():
        raise ValueError("text must be a non-empty string")
    if not provenance or not provenance.strip():
        raise ValueError("provenance must be a non-empty string")
    if not isinstance(priority, int):
        raise ValueError("priority must be an int")

    ts_now = now if now is not None else datetime.now(timezone.utc)
    created_at = ts_now.strftime("%Y-%m-%dT%H:%M:%SZ")

    item: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "id": _item_id(account, kind, text, as_of),
        "as_of": as_of,
        "account": account,
        "kind": kind,
        "text": text,
        "media": media if media is not None else [],
        "scheduled_at": scheduled_at,
        "slot": slot,
        "priority": priority,
        "provenance": provenance,
        "source": source,
        "status": "queued",
        "created_at": created_at,
    }
    return item


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_item(item: dict) -> list[str]:
    """Return a list of validation error strings; [] means valid."""
    errors: list[str] = []

    if item.get("schema") != SCHEMA_ID:
        errors.append(f"schema must be {SCHEMA_ID!r}; got {item.get('schema')!r}")

    for field in ("id", "as_of", "account", "kind", "text", "provenance"):
        v = item.get(field)
        if not v or not str(v).strip():
            errors.append(f"field {field!r} must be non-empty")

    if item.get("kind") not in KINDS:
        errors.append(f"kind {item.get('kind')!r} not in KINDS")

    if item.get("status") != "queued":
        errors.append(f"status must be 'queued' at creation; got {item.get('status')!r}")

    if not isinstance(item.get("priority"), int):
        errors.append("priority must be an int")

    for i, m in enumerate(item.get("media") or []):
        if not isinstance(m, dict):
            errors.append(f"media[{i}] must be a dict")
            continue
        if m.get("kind") != "chart_svg":
            errors.append(f"media[{i}].kind must be 'chart_svg'")
        if not m.get("path"):
            errors.append(f"media[{i}].path must be non-empty")
        if not m.get("chart_id"):
            errors.append(f"media[{i}].chart_id must be non-empty")

    return errors


# ─────────────────────────────────────────────────────────────────────────────
# JSONL file paths
# ─────────────────────────────────────────────────────────────────────────────

def _items_path(root: Path | str | None) -> Path:
    return outbox_dir(root) / "items.jsonl"


def _ledger_path(root: Path | str | None) -> Path:
    return outbox_dir(root) / "status_ledger.jsonl"


def _decisions_path(root: Path | str | None) -> Path:
    return outbox_dir(root) / "decisions.jsonl"


# ─────────────────────────────────────────────────────────────────────────────
# Read helpers
# ─────────────────────────────────────────────────────────────────────────────

def read_items(root: Path | str | None = None) -> list[dict]:
    """Read all item records from items.jsonl.  Returns [] on any error."""
    return read_jsonl(_items_path(root))


def read_ledger(root: Path | str | None = None) -> list[dict]:
    """Read all status transition rows from status_ledger.jsonl."""
    return read_jsonl(_ledger_path(root))


def read_decisions(root: Path | str | None = None) -> list[dict]:
    """Read all operator decision rows from decisions.jsonl."""
    return read_jsonl(_decisions_path(root))


# ─────────────────────────────────────────────────────────────────────────────
# Status fold
# ─────────────────────────────────────────────────────────────────────────────

def current_statuses(root: Path | str | None = None) -> dict[str, str]:
    """Fold items' initial status + ledger rows to get the current status per id.

    Only legal transitions are applied; illegal or unknown rows are skipped
    with a log.warning (defensive — the ledger should never have illegal rows
    because transition() validates before appending).
    """
    statuses: dict[str, str] = {}

    # Seed from items (all start as "queued")
    for item in read_items(root):
        item_id = item.get("id")
        if item_id:
            statuses[item_id] = item.get("status", "queued")

    # Apply ledger rows in order
    for row in read_ledger(root):
        item_id = row.get("id")
        to_status = row.get("to")
        if not item_id or not to_status:
            log.warning("outbox.current_statuses: skipping row with missing id or to: %r", row)
            continue
        current = statuses.get(item_id)
        if current is None:
            log.warning("outbox.current_statuses: ledger row for unknown item %r; skipping", item_id)
            continue
        allowed = TRANSITIONS.get(current, frozenset())
        if to_status not in allowed:
            log.warning(
                "outbox.current_statuses: illegal transition %r→%r for item %r; skipping",
                current, to_status, item_id,
            )
            continue
        statuses[item_id] = to_status

    return statuses


# ─────────────────────────────────────────────────────────────────────────────
# Enqueue
# ─────────────────────────────────────────────────────────────────────────────

def enqueue(
    item: dict,
    root: Path | str | None = None,
    *,
    max_per_account_day: int | None = None,
) -> str:
    """Append an item to items.jsonl if valid and not duplicate/over-cap.

    Returns one of: "queued" | "duplicate" | "cap_exceeded" | "invalid:<msg>".
    Never raises.
    """
    try:
        # Validate
        errors = validate_item(item)
        if errors:
            return f"invalid:{errors[0]}"

        item_id = item["id"]
        account = item["account"]
        as_of = item["as_of"]

        # Read existing items to check dedupe and cap
        existing = read_items(root)
        existing_ids = {i["id"] for i in existing}

        # Dedupe
        if item_id in existing_ids:
            return "duplicate"

        # Cap enforcement: count all existing items for same (account, as_of)
        # regardless of status (including quarantined/failed — they consumed the slot)
        cap = max_per_account_day if max_per_account_day is not None else DEFAULT_MAX_POSTS_PER_ACCOUNT_PER_DAY
        same_day_count = sum(
            1 for i in existing
            if i.get("account") == account and i.get("as_of") == as_of
        )
        if same_day_count >= cap:
            return "cap_exceeded"

        # Append
        ok = append_jsonl(_items_path(root), item)
        if not ok:
            log.warning("outbox.enqueue: append_jsonl failed for item %r", item_id)
            return "invalid:append failed"

        return "queued"

    except Exception as exc:  # noqa: BLE001
        log.warning("outbox.enqueue: unexpected error: %s", exc)
        return f"invalid:{exc}"


# ─────────────────────────────────────────────────────────────────────────────
# Transitions
# ─────────────────────────────────────────────────────────────────────────────

def transition(
    item_id: str,
    to: str,
    *,
    actor: str,
    root: Path | str | None = None,
    note: str | None = None,
    receipt: str | None = None,
) -> bool:
    """Append a status transition row to status_ledger.jsonl.

    Returns False (with log.warning) if:
      - the item is unknown
      - the transition is illegal from the current folded status
    Returns True on success.  Never raises.
    """
    try:
        statuses = current_statuses(root)
        if item_id not in statuses:
            log.warning("outbox.transition: unknown item_id %r", item_id)
            return False

        current = statuses[item_id]
        allowed = TRANSITIONS.get(current, frozenset())
        if to not in allowed:
            log.warning(
                "outbox.transition: illegal transition %r→%r for %r (allowed: %s)",
                current, to, item_id, sorted(allowed),
            )
            return False

        row: dict[str, Any] = {
            "id": item_id,
            "from": current,
            "to": to,
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "actor": actor,
            "note": note,
            "receipt": receipt,
        }
        ok = append_jsonl(_ledger_path(root), row)
        if not ok:
            log.warning("outbox.transition: append_jsonl failed for %r→%r on %r", current, to, item_id)
            return False
        return True

    except Exception as exc:  # noqa: BLE001
        log.warning("outbox.transition: unexpected error: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Operator decisions
# ─────────────────────────────────────────────────────────────────────────────

_VALID_DECISIONS = frozenset({"approve", "hold"})


def record_decision(
    item_id: str,
    decision: str,
    *,
    actor: str,
    root: Path | str | None = None,
    note: str | None = None,
) -> bool:
    """Record an operator approve/hold decision to decisions.jsonl.

    Returns False (with log.warning) if:
      - item_id is unknown (not in items.jsonl)
      - decision is not in {"approve", "hold"}
    Never raises.
    """
    try:
        if decision not in _VALID_DECISIONS:
            log.warning("outbox.record_decision: invalid decision %r; must be approve|hold", decision)
            return False

        existing_ids = {i["id"] for i in read_items(root)}
        if item_id not in existing_ids:
            log.warning("outbox.record_decision: unknown item_id %r", item_id)
            return False

        row: dict[str, Any] = {
            "id": item_id,
            "decision": decision,
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "actor": actor,
            "note": note,
        }
        ok = append_jsonl(_decisions_path(root), row)
        if not ok:
            log.warning("outbox.record_decision: append_jsonl failed for %r on %r", decision, item_id)
            return False
        return True

    except Exception as exc:  # noqa: BLE001
        log.warning("outbox.record_decision: unexpected error: %s", exc)
        return False


def latest_decisions(root: Path | str | None = None) -> dict[str, dict]:
    """Return the last decision row per item_id."""
    result: dict[str, dict] = {}
    for row in read_decisions(root):
        item_id = row.get("id")
        if item_id:
            result[item_id] = row
    return result


# ─────────────────────────────────────────────────────────────────────────────
# emit_from_content_plan
# ─────────────────────────────────────────────────────────────────────────────

_SLOT_SUFFIX_TIMES = {
    "AM":  "T14:00:00Z",
    "PM":  "T17:30:00Z",
    "EOD": "T20:15:00Z",
}


def _scheduled_at_for_slot(slot: str, as_of: str) -> str:
    """Map slot suffix to an advisory scheduled_at time.

    Advisory times; W1 actuator applies jitter/spacing before actual posting.
    """
    suffix = slot.rsplit("-", 1)[-1] if "-" in slot else ""
    time_suffix = _SLOT_SUFFIX_TIMES.get(suffix)
    if time_suffix:
        return f"{as_of}{time_suffix}"
    return "immediate"


def emit_from_content_plan(
    plan: dict,
    root: Path | str | None = None,
    *,
    cfg: dict | None = None,
    day_prefix: str = "D1",
    now: datetime | None = None,
) -> dict:
    """Map a content_plan dict to outbox items and enqueue them.

    Only processes items whose slot startswith f"{day_prefix}-".
    Items with a truthy "_live_gate_fail" field are skipped (never queue stale
    or invalidated signals). Items the D08 Sentinel gate quarantined
    (status == "quarantined") or left unverified (sentinel_ok is False — the
    gate's crash path stamps this) are skipped too: quarantined items surface
    on the admin Sentinel/Outbox views with reasons, never as queueable posts.

    Returns a summary dict: {emitted, skipped_dupe, skipped_cap, skipped_gate,
    skipped_sentinel, skipped_invalid, media_written, by_account}.
    """
    ts_now = now if now is not None else datetime.now(timezone.utc)
    as_of: str = plan.get("as_of") or ts_now.strftime("%Y-%m-%d")

    # Build featured_charts lookup by id
    featured_charts: dict[str, dict] = {}
    for fc in plan.get("featured_charts") or []:
        fc_id = fc.get("id")
        if fc_id:
            featured_charts[fc_id] = fc

    counts = {
        "emitted": 0,
        "skipped_dupe": 0,
        "skipped_cap": 0,
        "skipped_gate": 0,
        "skipped_sentinel": 0,
        "skipped_invalid": 0,
        "media_written": 0,
        "by_account": {},
    }

    cap = effective_cap(cfg or {})

    for acct_block in plan.get("accounts") or []:
        account_id = acct_block.get("id") or acct_block.get("name") or ""
        for qi in acct_block.get("queue") or []:
            try:
                slot = qi.get("slot") or ""

                # Only today's day prefix
                if not slot.startswith(f"{day_prefix}-"):
                    continue

                # Skip items that failed the live gate
                if qi.get("_live_gate_fail"):
                    counts["skipped_gate"] += 1
                    continue

                # Skip items the D08 Sentinel gate quarantined or left
                # unverified (crash path stamps sentinel_ok=False). A missing
                # sentinel_ok field (pre-D08 plan) passes through.
                if qi.get("status") == "quarantined" or qi.get("sentinel_ok") is False:
                    counts["skipped_sentinel"] += 1
                    continue

                # Build text from headline + body
                parts = [
                    (qi.get("headline") or "").strip(),
                    (qi.get("body") or "").strip(),
                ]
                text = "\n\n".join(p for p in parts if p)
                if not text:
                    counts["skipped_invalid"] += 1
                    continue

                # Media: if chart_id is set and featured_charts has an entry
                media: list[dict] = []
                chart_id = qi.get("chart_id")
                if chart_id and chart_id in featured_charts:
                    fc = featured_charts[chart_id]
                    svg_str = fc.get("svg") or ""
                    if svg_str:
                        # Write svg to outbox media dir
                        media_dir = outbox_dir(root) / "media" / as_of
                        svg_rel_path = f"data/marketing/outbox/media/{as_of}/{chart_id}.svg"
                        try:
                            media_dir.mkdir(parents=True, exist_ok=True)
                            svg_path = media_dir / f"{chart_id}.svg"
                            if not svg_path.exists():
                                # Atomic write to avoid partial files
                                tmp_fd, tmp_p = tempfile.mkstemp(
                                    dir=media_dir, prefix=".tmp_", suffix=".svg"
                                )
                                try:
                                    with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                                        f.write(svg_str)
                                    os.replace(tmp_p, svg_path)
                                    counts["media_written"] += 1
                                except Exception:
                                    try:
                                        os.unlink(tmp_p)
                                    except Exception:  # noqa: BLE001
                                        pass
                                    raise
                        except Exception as exc:  # noqa: BLE001
                            log.warning("outbox.emit_from_content_plan: media write failed for %r: %s", chart_id, exc)

                        media.append({
                            "kind": "chart_svg",
                            "path": svg_rel_path,
                            "chart_id": chart_id,
                            "ticker": qi.get("ticker") or fc.get("ticker") or "",
                        })

                scheduled_at = _scheduled_at_for_slot(slot, as_of)

                source: dict[str, Any] = {
                    "plan_item_id": qi.get("id"),
                    "chart_id": chart_id,
                }
                plan_block = qi.get("_plan")
                if isinstance(plan_block, dict):
                    source["signal_id"] = plan_block.get("id")

                try:
                    item = make_item(
                        account=account_id,
                        kind=qi.get("type") or "signal",
                        text=text,
                        as_of=as_of,
                        media=media,
                        scheduled_at=scheduled_at,
                        slot=slot,
                        priority=5,
                        provenance="content_studio",
                        source=source,
                        now=ts_now,
                    )
                except ValueError as exc:
                    log.warning("outbox.emit_from_content_plan: make_item failed: %s", exc)
                    counts["skipped_invalid"] += 1
                    continue

                result_code = enqueue(item, root, max_per_account_day=cap)
                if result_code == "queued":
                    counts["emitted"] += 1
                    counts["by_account"][account_id] = counts["by_account"].get(account_id, 0) + 1
                elif result_code == "duplicate":
                    counts["skipped_dupe"] += 1
                elif result_code == "cap_exceeded":
                    counts["skipped_cap"] += 1
                elif result_code.startswith("invalid:"):
                    log.warning("outbox.emit_from_content_plan: invalid item: %s", result_code)
                    counts["skipped_invalid"] += 1

            except Exception as exc:  # noqa: BLE001
                log.warning("outbox.emit_from_content_plan: per-item error: %s", exc)
                counts["skipped_invalid"] += 1

    return counts
