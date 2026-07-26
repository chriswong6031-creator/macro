"""engine.marketing.rejections — operator rejections as a feedback corpus.

WHY THIS EXISTS
Nothing judges post QUALITY. copywriter.validate_copy runs 20 rules and every
one of them is a pattern match — cashtag present, length, em dash, banned vocab,
emoji budget. It catches a banned WORD; it cannot see an awkward SENTENCE. It
also runs once, at generation, on LLM output only, so a post sitting in the
outbox is never re-examined by anything.

That left the operator as the only judge of style, with nowhere to put the
judgement. "Hold" keeps a post in the review rail (it is a reversible decision,
not a verdict), so a bad post could only be parked, never killed with a reason
attached, and the reason died in the operator's head.

This module is the missing half: a REJECT is terminal AND it records why, so a
run of rejections becomes a corpus you can export, annotate, and hand back to
whoever is tuning the writer.

LEDGER SHAPE (append-only, one JSON object per line, fold on read)
  {"row": "rejection", "id", "item_id", "account", "kind", "provenance",
   "as_of", "ticker", "text", "media", "reason", "rejected_at"}
  {"row": "export", "ids": [...], "at": "..."}

Export STAMPS rather than deletes. The operator's ask was "they get deleted and
don't show anymore, to prevent mixing solved rejections with new ones" — that is
a requirement about the VIEW, not about the data. Exported rows drop out of
pending() so the box only ever shows unreviewed rejections, and the corpus that
makes this whole loop worth having stays on disk.

Fail-soft throughout: a rejection that cannot be written must never block the
outbox transition that killed the post.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "marketing.rejection/v1"
_REL = Path("data") / "marketing" / "rejections.jsonl"

# Operator free text is unbounded by nature; cap it so one paste cannot balloon
# an append-only ledger.
_MAX_REASON = 2000


def ledger_path(root: Path | str | None = None) -> Path:
    return (Path(root) if root is not None else Path(".")) / _REL


def _read_rows(root: Path | str | None) -> list[dict[str, Any]]:
    """All ledger rows, oldest first. Unreadable/garbage lines are skipped."""
    p = ledger_path(root)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(row, dict):
                out.append(row)
    except Exception as exc:  # noqa: BLE001
        log.warning("rejections: unreadable ledger %s: %s", p, exc)
    return out


def _append(row: dict[str, Any], root: Path | str | None) -> bool:
    """Append one row atomically-ish. Returns False on any failure."""
    p = ledger_path(root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("rejections: append failed: %s", exc)
        return False


def record(item: dict, *, reason: str | None = None, actor: str = "admin",
           root: Path | str | None = None,
           now: datetime | None = None) -> dict | None:
    """Record one rejection for an outbox `item`. Returns the row, or None.

    Captures the post AS REJECTED — the text and media are copied in, not
    referenced, so the corpus survives the item being superseded or the outbox
    being pruned. That matters: the whole point is to review what went wrong
    long after the queue has moved on.
    """
    try:
        iid = str(item.get("id") or "").strip()
        if not iid:
            return None
        ts = (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
        src = item.get("source") or {}
        row = {
            "schema": SCHEMA,
            "row": "rejection",
            "id": f"rej-{iid}",
            "item_id": iid,
            "account": item.get("account") or "",
            "kind": item.get("kind") or "",
            "provenance": item.get("provenance") or "",
            "as_of": item.get("as_of") or "",
            "ticker": src.get("ticker") or "",
            "state": src.get("state") or "",
            "text": item.get("text") or "",
            "media": [
                {"path": m.get("path"), "media_url": m.get("media_url")}
                for m in (item.get("media") or []) if isinstance(m, dict)
            ],
            "reason": (str(reason or "").strip()[:_MAX_REASON]) or None,
            "actor": actor,
            "rejected_at": ts,
        }
        return row if _append(row, root) else None
    except Exception as exc:  # noqa: BLE001
        log.warning("rejections.record failed: %s", exc)
        return None


def pending(root: Path | str | None = None) -> list[dict[str, Any]]:
    """Rejections not yet carried out in an export, oldest first."""
    rows = _read_rows(root)
    exported: set[str] = set()
    for r in rows:
        if r.get("row") == "export":
            for i in (r.get("ids") or []):
                exported.add(str(i))
    out = [r for r in rows
           if r.get("row") == "rejection" and str(r.get("id")) not in exported]
    out.sort(key=lambda r: str(r.get("rejected_at") or ""))
    return out


def mark_exported(ids: list[str], *, root: Path | str | None = None,
                  now: datetime | None = None) -> bool:
    """Stamp `ids` as exported so they leave pending(). Append-only."""
    clean = [str(i) for i in (ids or []) if str(i).strip()]
    if not clean:
        return False
    ts = (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    return _append({"schema": SCHEMA, "row": "export", "ids": clean, "at": ts}, root)


def render_markdown(rows: list[dict[str, Any]], *,
                    generated_at: str | None = None) -> str:
    """Render rejections as an annotatable markdown review sheet.

    Every post gets an empty "What's wrong" field directly under it. The file is
    meant to be edited in place and handed back, so the prompt has to sit where
    the operator is already looking, not in a legend at the top.
    """
    n = len(rows)
    head = [
        "# Rejected posts — review sheet",
        "",
        f"{n} rejected post{'' if n == 1 else 's'}"
        + (f" · exported {generated_at}" if generated_at else ""),
        "",
        "Fill in **What's wrong** under each post. Anything you write there is the "
        "input for tuning the writer, so be specific: name the phrase, not just "
        "the feeling. Leave a post blank to skip it.",
        "",
        "---",
        "",
    ]
    if not rows:
        return "\n".join(head + ["_Nothing pending._", ""])

    body: list[str] = []
    for i, r in enumerate(rows, 1):
        ctx = " · ".join(x for x in [
            r.get("ticker") or "",
            r.get("provenance") or "",
            r.get("state") or "",
            r.get("as_of") or "",
        ] if x)
        body.append(f"## {i}. {r.get('ticker') or r.get('item_id')}")
        body.append("")
        if ctx:
            body.append(f"`{ctx}`")
            body.append("")
        text = str(r.get("text") or "")
        body.extend("> " + ln if ln else ">" for ln in text.splitlines())
        body.append("")
        media = [m for m in (r.get("media") or []) if m.get("media_url")]
        if media:
            body.append(f"Chart: {media[0]['media_url']}")
            body.append("")
        if r.get("reason"):
            body.append(f"Rejected because: {r['reason']}")
            body.append("")
        body.append("**What's wrong:**")
        body.append("")
        body.append("")
        body.append("---")
        body.append("")
    return "\n".join(head + body)
