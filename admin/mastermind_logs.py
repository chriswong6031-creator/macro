"""admin/mastermind_logs.py — operator view over the Mastermind AI response log.

Every user-facing answer from BOTH surfaces (Macro Dashboard brain chat + the
charting-app Terminal copilot) is written as one immutable object to Cloudflare
R2 under `mastermind_response_logs/<surface>/<date>/<id>.json`
(schema `mastermind.response_log.v1`, see lib/mastermind_response_log.py).

This module is the READ + EVAL half, running inside the admin panel on the Mac:

  * refresh(root)  — pull new R2 objects into data/mastermind/response_log.jsonl
                     (dedup by id). Graceful no-op when R2 creds are absent.
  * logs(...)      — read the local ledger, overlay the eval sidecar, filter,
                     and return newest-first rows + summary stats.
  * rate(...)      — append an eval verdict (grade / thumb / star / tags / note)
                     to the local, mutable sidecar data/mastermind/response_eval.jsonl.
  * export(...)    — the filtered set as a JSONL or CSV string for batch eval /
                     training-set curation outside the panel.

The log ledger is APPEND-ONLY and immutable (it mirrors R2). Evaluation is a
SEPARATE local sidecar overlaid at read time by id — so grading never mutates
the corpus, and a re-ingest can never clobber an operator's verdicts.

FAIL-SOFT: readers never raise; a missing dir/file/creds yields an empty-but-valid
response. Writers (refresh/rate) create the dir on demand.
"""
from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import ROOT

_LOG_NAME = "response_log.jsonl"
_EVAL_NAME = "response_eval.jsonl"
_SUBDIR = ("data", "mastermind")

# Bound the request path: read at most this many trailing ledger lines per call.
_READ_CAP = 20000
# Bound one R2 refresh: never GET more than this many new objects in a pass.
_REFRESH_CAP = 5000
# Export bound.
_EXPORT_CAP = 50000

_ALLOWED_TAGS_MAX = 12
# Ingest-health: warn when the newest ledger row is at least this many days old.
_DARK_AFTER_DAYS = 2
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Paths + primitives
# ---------------------------------------------------------------------------

def _base(root: Path | None) -> Path:
    return Path(root) if root is not None else ROOT


def _log_path(root: Path | None) -> Path:
    return _base(root).joinpath(*_SUBDIR, _LOG_NAME)


def _eval_path(root: Path | None) -> Path:
    return _base(root).joinpath(*_SUBDIR, _EVAL_NAME)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_ts(ts: Any) -> datetime:
    try:
        s = str(ts or "").strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return _EPOCH


def _tail_lines(p: Path, n: int) -> list[str]:
    """Last n lines of a file — bounds the request path as the ledger accrues."""
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:  # noqa: BLE001
        return []
    return lines[-n:] if len(lines) > n else lines


def _read_jsonl(p: Path, cap: int) -> list[dict]:
    out: list[dict] = []
    for line in _tail_lines(p, cap):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _append_jsonl(p: Path, row: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Eval overlay
# ---------------------------------------------------------------------------

def _eval_overlay(root: Path | None) -> dict[str, dict]:
    """Collapse the eval sidecar to latest-wins by id → the current verdict."""
    latest: dict[str, dict] = {}
    for row in _read_jsonl(_eval_path(root), _READ_CAP):
        rid = row.get("id")
        if isinstance(rid, str) and rid:
            latest[rid] = row  # append-only file → last write wins naturally
    return latest


def _public_eval(ev: dict | None) -> dict:
    """Shape an eval sidecar row for the UI (drop internal-only churn)."""
    if not isinstance(ev, dict):
        return {}
    tags = ev.get("tags")
    return {
        "grade": ev.get("grade"),
        "thumb": ev.get("thumb"),
        "star": bool(ev.get("star")),
        "tags": [str(t) for t in tags][:_ALLOWED_TAGS_MAX] if isinstance(tags, list) else [],
        "note": str(ev.get("note") or ""),
        "evaluator": ev.get("evaluator") or "",
        "updated_ts": ev.get("updated_ts") or "",
    }


# ---------------------------------------------------------------------------
# Ingest health
# ---------------------------------------------------------------------------

def ingest_health(rows: list[dict]) -> dict:
    """How stale is the ledger, overall and per surface — is the ingest dark?

    WHY: through July 2026 macro-api ran without plain R2_* creds, so the writer's
    `enabled()` was False, zero objects were ever written, and the panel showed an
    empty corpus with nothing saying anything was wrong. An empty or aging ledger
    is now loud. Fail-soft: any error reports healthy, never a false alarm."""
    try:
        newest: datetime | None = None
        newest_by_surface: dict[str, datetime] = {}
        last_by_surface: dict[str, str] = {}
        for r in rows:
            ts = r.get("ts")
            dt = _parse_ts(ts)
            if dt == _EPOCH:  # unparseable/missing — not evidence of a live ingest
                continue
            if newest is None or dt > newest:
                newest = dt
            surface = str(r.get("surface") or "?")
            prev = newest_by_surface.get(surface)
            if prev is None or dt > prev:
                newest_by_surface[surface] = dt
                last_by_surface[surface] = str(ts)

        if newest is None:
            # No parseable row at all — an empty ledger IS dark (the July-2026 state).
            return {"dark": True, "dark_days": None, "last_ts": None,
                    "last_by_surface": {}, "threshold_days": _DARK_AFTER_DAYS}

        age_days = (datetime.now(timezone.utc) - newest).total_seconds() / 86400.0
        return {
            "dark": age_days >= _DARK_AFTER_DAYS,
            "dark_days": int(age_days),
            "last_ts": newest.isoformat(timespec="seconds"),
            "last_by_surface": last_by_surface,
            "threshold_days": _DARK_AFTER_DAYS,
        }
    except Exception:  # noqa: BLE001
        return {"dark": False, "dark_days": None, "last_ts": None,
                "last_by_surface": {}, "threshold_days": _DARK_AFTER_DAYS}


# ---------------------------------------------------------------------------
# R2 refresh (ingest)
# ---------------------------------------------------------------------------

def refresh(root: Path | None = None) -> dict:
    """Pull new response-log objects from R2 into the local ledger. Dedup by id.
    Graceful no-op (ok=False, note) when R2 creds/boto3 are absent. Never raises."""
    try:
        from lib import mastermind_response_log as _mm  # noqa: PLC0415
        s3 = _mm._client()
        if s3 is None:
            return {"ok": False, "ingested": 0, "note": "no R2 creds — ledger unchanged",
                    "generated_at": _now_iso()}
        bucket = os.environ.get("R2_BUCKET")
        if not bucket:
            return {"ok": False, "ingested": 0, "note": "R2_BUCKET unset",
                    "generated_at": _now_iso()}

        # Ids already in the local ledger (dedup key).
        ledger_rows = _read_jsonl(_log_path(root), _READ_CAP)
        seen: set[str] = set()
        for r in ledger_rows:
            rid = r.get("id")
            if isinstance(rid, str):
                seen.add(rid)

        prefix = _mm.R2_PREFIX + "/"
        new_rows: list[dict] = []
        token = None
        listed = 0
        while len(new_rows) < _REFRESH_CAP:
            kw = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
            if token:
                kw["ContinuationToken"] = token
            resp = s3.list_objects_v2(**kw)
            for obj in resp.get("Contents") or []:
                key = obj.get("Key") or ""
                if not key.endswith(".json"):
                    continue
                listed += 1
                rid = Path(key).stem
                if rid in seen:
                    continue
                try:
                    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
                    parsed = json.loads(body.decode("utf-8"))
                except Exception:  # noqa: BLE001
                    continue
                if not isinstance(parsed, dict) or parsed.get("schema") != _mm.SCHEMA:
                    continue
                parsed.setdefault("id", rid)
                new_rows.append(parsed)
                seen.add(parsed["id"])
                if len(new_rows) >= _REFRESH_CAP:
                    break
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")

        # Append newest-first-by-ts so the local ledger stays roughly time-ordered.
        new_rows.sort(key=lambda r: _parse_ts(r.get("ts")))
        p = _log_path(root)
        for r in new_rows:
            _append_jsonl(p, r)

        return {"ok": True, "ingested": len(new_rows), "listed": listed,
                "capped": len(new_rows) >= _REFRESH_CAP,
                "ingest": ingest_health(ledger_rows + new_rows),
                "generated_at": _now_iso()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "ingested": 0, "note": f"refresh error: {exc}",
                "generated_at": _now_iso()}


# ---------------------------------------------------------------------------
# Read + filter
# ---------------------------------------------------------------------------

def _matches(row: dict, ev: dict, f: dict) -> bool:
    surface = f.get("surface")
    if surface and surface != "all" and row.get("surface") != surface:
        return False
    lane = f.get("lane")
    if lane and lane != "all" and (row.get("lane") or "") != lane:
        return False
    model = (f.get("model") or "").strip().lower()
    if model and model not in str(row.get("model") or "").lower():
        return False
    graded = f.get("graded")
    if graded == "yes" and ev.get("grade") is None and not ev.get("thumb"):
        return False
    if graded == "no" and (ev.get("grade") is not None or ev.get("thumb")):
        return False
    thumb = f.get("thumb")
    if thumb and thumb != "all" and ev.get("thumb") != thumb:
        return False
    if f.get("starred") and not ev.get("star"):
        return False
    if f.get("error") and not (row.get("flags") or {}).get("error"):
        return False
    since = f.get("since")
    if since:
        if _parse_ts(row.get("ts")) < _parse_ts(since):
            return False
    q = (f.get("q") or "").strip().lower()
    if q:
        hay = (str(row.get("question") or "") + " " + str(row.get("answer") or "")).lower()
        if q not in hay:
            return False
    return True


def logs(limit: int = 100, filters: dict | None = None, root: Path | None = None) -> dict:
    """Return newest-first response rows (with eval overlay) + summary stats.

    `limit` clamped to [1, 500]. Filtering runs over the trailing _READ_CAP rows.
    Never raises — a missing ledger yields an empty, valid response."""
    try:
        limit = max(1, min(500, int(limit)))
        f = filters or {}
        rows = _read_jsonl(_log_path(root), _READ_CAP)
        overlay = _eval_overlay(root)

        # Whole-window stats (before the display cap) so the header counts are honest.
        stats = {
            "total": len(rows),
            "by_surface": {}, "by_provider": {},
            "graded": 0, "starred": 0, "thumbs_up": 0, "thumbs_down": 0,
            "errors": 0,
        }
        matched: list[dict] = []
        for r in rows:
            rid = r.get("id") or ""
            ev = _public_eval(overlay.get(rid))
            stats["by_surface"][r.get("surface") or "?"] = stats["by_surface"].get(r.get("surface") or "?", 0) + 1
            prov = r.get("provider") or "?"
            stats["by_provider"][prov] = stats["by_provider"].get(prov, 0) + 1
            if ev.get("grade") is not None or ev.get("thumb"):
                stats["graded"] += 1
            if ev.get("star"):
                stats["starred"] += 1
            if ev.get("thumb") == "up":
                stats["thumbs_up"] += 1
            elif ev.get("thumb") == "down":
                stats["thumbs_down"] += 1
            if (r.get("flags") or {}).get("error"):
                stats["errors"] += 1
            if _matches(r, ev, f):
                out = dict(r)
                out["eval"] = ev
                matched.append(out)

        matched.sort(key=lambda r: _parse_ts(r.get("ts")), reverse=True)
        return {
            "rows": matched[:limit],
            "matched": len(matched),
            "stats": stats,
            "ingest": ingest_health(rows),
            "read_capped": len(rows) >= _READ_CAP,
            "generated_at": _now_iso(),
        }
    except Exception as exc:  # noqa: BLE001
        return {"rows": [], "matched": 0, "stats": {"total": 0}, "error": str(exc),
                "generated_at": _now_iso()}


# ---------------------------------------------------------------------------
# Rate (eval writeback)
# ---------------------------------------------------------------------------

def validate_rate_body(body: dict) -> tuple[bool, str | None, dict | None]:
    """Server-side validation for a rating POST. Returns (ok, error, cleaned)."""
    if not isinstance(body, dict):
        return False, "body must be an object", None
    rid = body.get("id")
    if not isinstance(rid, str) or not rid.strip():
        return False, "id required", None

    cleaned: dict[str, Any] = {"id": rid.strip()}

    if "grade" in body and body.get("grade") is not None:
        try:
            g = int(body["grade"])
        except (TypeError, ValueError):
            return False, "grade must be an integer 1–5 or null", None
        if not (1 <= g <= 5):
            return False, "grade out of range (1–5)", None
        cleaned["grade"] = g
    else:
        cleaned["grade"] = None

    thumb = body.get("thumb")
    if thumb not in (None, "", "up", "down"):
        return False, "thumb must be 'up', 'down', or null", None
    cleaned["thumb"] = thumb or None

    cleaned["star"] = bool(body.get("star"))

    tags = body.get("tags")
    if tags is None:
        cleaned["tags"] = []
    elif isinstance(tags, list):
        norm = [str(t).strip()[:32] for t in tags if str(t).strip()]
        cleaned["tags"] = norm[:_ALLOWED_TAGS_MAX]
    else:
        return False, "tags must be a list", None

    note = body.get("note")
    if note is not None and not isinstance(note, str):
        return False, "note must be a string", None
    cleaned["note"] = (note or "")[:2000]

    return True, None, cleaned


def rate(cleaned: dict, evaluator: str = "", root: Path | None = None) -> dict:
    """Append one eval verdict for a response id. Returns the current overlay
    for that id. `cleaned` MUST come from validate_rate_body. Never raises."""
    try:
        row = dict(cleaned)
        row["schema"] = "mastermind.response_eval.v1"
        row["evaluator"] = evaluator or "operator"
        row["updated_ts"] = _now_iso()
        _append_jsonl(_eval_path(root), row)
        return {"ok": True, "id": row["id"], "eval": _public_eval(row),
                "generated_at": _now_iso()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

_EXPORT_FIELDS = (
    "id", "ts", "surface", "lane", "mode", "model", "provider", "thread_id",
    "user_ref", "question", "answer", "input_tokens", "output_tokens",
    "latency_ms", "lang",
)


def export(filters: dict | None = None, fmt: str = "jsonl", root: Path | None = None) -> dict:
    """Return the filtered corpus as a downloadable string.

    fmt='jsonl' → one full row (with eval) per line.
    fmt='csv'   → flattened core fields + eval grade/thumb/star/tags/note.
    Returns {ok, filename, mime, content, count}. Never raises."""
    try:
        fmt = "csv" if str(fmt).lower() == "csv" else "jsonl"
        f = filters or {}
        rows = _read_jsonl(_log_path(root), _READ_CAP)
        overlay = _eval_overlay(root)
        sel: list[dict] = []
        for r in rows:
            ev = _public_eval(overlay.get(r.get("id") or ""))
            if _matches(r, ev, f):
                out = dict(r)
                out["eval"] = ev
                sel.append(out)
        sel.sort(key=lambda r: _parse_ts(r.get("ts")), reverse=True)
        sel = sel[:_EXPORT_CAP]

        stamp = _now_iso()[:10]
        if fmt == "jsonl":
            content = "\n".join(json.dumps(r, ensure_ascii=False) for r in sel)
            return {"ok": True, "filename": f"mastermind_responses_{stamp}.jsonl",
                    "mime": "application/x-ndjson", "content": content, "count": len(sel)}
        # CSV
        buf = io.StringIO()
        cols = list(_EXPORT_FIELDS) + ["grade", "thumb", "star", "tags", "note"]
        w = csv.writer(buf)
        w.writerow(cols)
        for r in sel:
            ev = r.get("eval") or {}
            w.writerow(
                [r.get(k, "") for k in _EXPORT_FIELDS]
                + [ev.get("grade", ""), ev.get("thumb", ""), ev.get("star", ""),
                   " ".join(ev.get("tags") or []), (ev.get("note") or "").replace("\n", " ")]
            )
        return {"ok": True, "filename": f"mastermind_responses_{stamp}.csv",
                "mime": "text/csv", "content": buf.getvalue(), "count": len(sel)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
