"""engine.marketing.attribution — Funnel W1b scaffold (docket D07) — UTM attribution join.

Signups arrive as an exported JSON/JSONL file (production: a Supabase export read by the
nightly — never live access from this module).  Joins signup records × posted items on
``utm_content == post_id``, appends to the attribution ledger.

Privacy law: first-touch UTM only; ledger stores an opaque ``user_ref`` (sha256 prefix of
the provider user id), plan tier and timestamps — never email/name/phone/IP.

Nightly is the sole advancer of forward ledgers; this module only appends when invoked by
the nightly lane (wiring lands in W1b proper).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

LEDGER_SCHEMA = "marketing.attribution/v1"
LEDGER_SCHEMA_VERSION = 1
DEFAULT_LEDGER_PATH = Path("data") / "marketing" / "attribution_ledger.jsonl"

_PII_KEYS: frozenset[str] = frozenset({
    "email", "e_mail", "name", "full_name", "first_name", "last_name",
    "phone", "ip", "ip_address", "address", "user_agent",
})

_UTM_KEYS: tuple[str, ...] = (
    "utm_source", "utm_medium", "utm_campaign", "utm_content",
)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def user_ref(raw_id: Any) -> str:
    """Return an opaque, deterministic 18-char reference for *raw_id*.

    Format: ``"u_" + sha256(str(raw_id))[:16]``.  PII never stored.
    """
    digest = hashlib.sha256(str(raw_id).encode("utf-8")).hexdigest()
    return "u_" + digest[:16]


def parse_utm(signup: dict[str, Any]) -> dict[str, str | None]:
    """Extract first-touch UTM fields from a signup record.

    Accepts fields flat on the record (``signup["utm_content"]``) **or** nested
    under ``signup["utm"]``.  Flat wins on conflict — first-touch is what the
    capture stored first.  Values are coerced to str and stripped; empty string
    becomes ``None``.
    """
    nested: dict[str, Any] = signup.get("utm") or {}
    result: dict[str, str | None] = {}
    for key in _UTM_KEYS:
        # Flat takes precedence
        if key in signup:
            raw = signup[key]
        else:
            raw = nested.get(key)
        if raw is None:
            result[key] = None
        else:
            val = str(raw).strip()
            result[key] = val if val else None
    return result


def strip_pii(record: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *record* with every top-level key in ``_PII_KEYS`` removed.

    Key comparison is case-insensitive.  This is a shallow, defense-in-depth
    sweep — nested PII (e.g. ``record["profile"]["email"]``) survives it.  The
    real privacy guarantee is the explicit field allowlist in
    :func:`join_attribution`: only whitelisted fields ever reach the ledger.
    """
    lower_pii = {k.lower() for k in _PII_KEYS}
    return {k: v for k, v in record.items() if k.lower() not in lower_pii}


def load_signups(path: Path | str) -> list[dict[str, Any]]:
    """Load signup records from *path* (``.json`` or ``.jsonl``).

    Every record is passed through :func:`strip_pii`.  Records missing both
    ``id`` and ``user_id`` are silently dropped.  Blank lines in JSONL files
    are skipped.  Raises :exc:`FileNotFoundError` naturally if the file is
    absent — caller decides.
    """
    p = Path(path)
    suffix = p.suffix.lower()

    raw_records: list[dict[str, Any]] = []
    if suffix == ".json":
        text = p.read_text(encoding="utf-8")
        raw_records = json.loads(text)
    else:
        # .jsonl and anything else: one object per non-blank line
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            raw_records.append(json.loads(line))

    cleaned: list[dict[str, Any]] = []
    for rec in raw_records:
        if not isinstance(rec, dict):
            continue
        # Drop records with neither id nor user_id
        if rec.get("id") is None and rec.get("user_id") is None:
            continue
        cleaned.append(strip_pii(rec))
    return cleaned


def posts_index(plan_or_items: Any) -> dict[str, dict[str, Any]]:
    """Build ``{post_id: {"account": ..., "kind": ...}}`` from a content plan or item list.

    Accepts either:

    - A content-plan dict: walks ``plan["accounts"][*]["queue"]``; kind comes from
      the item ``"type"`` field.
    - A plain list of item dicts (the future D02 outbox seam): each has
      ``"id"``/``"account"`` and ``"type"`` or ``"kind"``.

    Items without an ``id`` are skipped.
    """
    index: dict[str, dict[str, Any]] = {}

    if isinstance(plan_or_items, dict):
        # Content-plan shape
        for account_entry in plan_or_items.get("accounts", []):
            account_id = account_entry.get("id") or account_entry.get("account")
            for item in account_entry.get("queue", []):
                post_id = item.get("id")
                if not post_id:
                    continue
                kind = item.get("type") or item.get("kind")
                # account on queue item wins; fall back to parent account id
                acct = item.get("account") or account_id
                index[str(post_id)] = {"account": acct, "kind": kind}
    elif isinstance(plan_or_items, list):
        # Plain outbox-style list
        for item in plan_or_items:
            if not isinstance(item, dict):
                continue
            post_id = item.get("id")
            if not post_id:
                continue
            kind = item.get("type") or item.get("kind")
            acct = item.get("account")
            index[str(post_id)] = {"account": acct, "kind": kind}

    return index


def join_attribution(
    signups: list[dict[str, Any]],
    index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Join *signups* against *index* and produce one ledger row per signup.

    Post-index truth wins for ``post_id``/``account``/``kind``.  The raw
    ``utm_medium``/``utm_campaign`` claims remain in their fields — honest,
    both printed.  Unmatched signups (no ``utm_content``, or unknown id) are
    **kept** with ``matched=False`` — nulls printed, not hidden.

    Ledger row schema::

        {
            "schema": LEDGER_SCHEMA,
            "schema_version": LEDGER_SCHEMA_VERSION,
            "user_ref": str,
            "signup_at": str | None,
            "plan": str | None,
            "trial_to_paid": bool | None,
            "utm_source": str | None,
            "utm_medium": str | None,
            "utm_campaign": str | None,
            "utm_content": str | None,
            "post_id": str | None,
            "account": str | None,
            "kind": str | None,
            "matched": bool,
        }
    """
    rows: list[dict[str, Any]] = []
    for rec in signups:
        raw_id = rec.get("id") or rec.get("user_id")
        utm = parse_utm(rec)
        utm_content = utm.get("utm_content")

        # Post-index lookup
        if utm_content and utm_content in index:
            idx_entry = index[utm_content]
            post_id: str | None = utm_content
            account: str | None = idx_entry.get("account")
            kind: str | None = idx_entry.get("kind")
            matched = True
        else:
            post_id = None
            account = None
            kind = None
            matched = False

        signup_at_raw = rec.get("signup_at")
        row: dict[str, Any] = {
            "schema": LEDGER_SCHEMA,
            "schema_version": LEDGER_SCHEMA_VERSION,
            "user_ref": user_ref(raw_id),
            "signup_at": str(signup_at_raw) if signup_at_raw is not None else None,
            "plan": rec.get("plan") or None,
            "trial_to_paid": rec.get("trial_to_paid"),
            "utm_source": utm["utm_source"],
            "utm_medium": utm["utm_medium"],
            "utm_campaign": utm["utm_campaign"],
            "utm_content": utm["utm_content"],
            "post_id": post_id,
            "account": account,
            "kind": kind,
            "matched": matched,
        }
        rows.append(row)
    return rows


def append_ledger(
    rows: list[dict[str, Any]],
    path: Path | str | None = None,
) -> dict[str, int]:
    """Append *rows* to the attribution ledger JSONL at *path*.

    Dedup key: ``(user_ref, utm_content, signup_at)``.  Reads existing keys
    first (tolerating blank/corrupt lines — counted as ``skipped_unparseable``),
    then opens the file in append mode.  Creates parent directories as needed.

    Returns::

        {
            "appended": int,
            "skipped_duplicates": int,
            "skipped_unparseable": int,
            "total_rows": int,
        }
    """
    p = Path(path) if path is not None else DEFAULT_LEDGER_PATH

    # ------------------------------------------------------------------
    # Read existing dedup keys
    # ------------------------------------------------------------------
    existing_keys: set[tuple[str | None, str | None, str | None]] = set()
    skipped_unparseable = 0
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                key = (
                    obj.get("user_ref"),
                    obj.get("utm_content"),
                    obj.get("signup_at"),
                )
                existing_keys.add(key)
            except (json.JSONDecodeError, AttributeError):
                skipped_unparseable += 1

    # ------------------------------------------------------------------
    # Append new rows
    # ------------------------------------------------------------------
    p.parent.mkdir(parents=True, exist_ok=True)
    appended = 0
    skipped_duplicates = 0

    with p.open("a", encoding="utf-8") as fh:
        for row in rows:
            key = (
                row.get("user_ref"),
                row.get("utm_content"),
                row.get("signup_at"),
            )
            if key in existing_keys:
                skipped_duplicates += 1
                continue
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            existing_keys.add(key)
            appended += 1

    total_rows = len(existing_keys)
    return {
        "appended": appended,
        "skipped_duplicates": skipped_duplicates,
        "skipped_unparseable": skipped_unparseable,
        "total_rows": total_rows,
    }


def build_attribution(
    signups_path: Path | str,
    plan_or_items: Any,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Orchestration seam for the future nightly wiring.

    Flow: :func:`load_signups` → :func:`posts_index` → :func:`join_attribution`
    → :func:`append_ledger`.

    Returns::

        {
            "signups": int,
            "matched": int,
            "unmatched": int,
            "appended": int,
            "skipped_duplicates": int,
            "skipped_unparseable": int,
            "total_rows": int,
        }

    .. warning::
        Do NOT call this from any builder or script in this wave.  Nightly
        wiring lands in W1b proper.
    """
    signups = load_signups(signups_path)
    index = posts_index(plan_or_items)
    rows = join_attribution(signups, index)
    append_result = append_ledger(rows, path=ledger_path)
    matched = sum(1 for r in rows if r["matched"])
    return {
        "signups": len(signups),
        "matched": matched,
        "unmatched": len(rows) - matched,
        **append_result,
    }
