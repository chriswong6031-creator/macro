"""Mastermind AI response log — the shared write contract for every user-facing
answer produced by the Mastermind assistant, across BOTH surfaces:

    * "macro"    — the Macro Dashboard brain chat (engine/neuralweb/brain_gateway.py,
                   served by macro-api / app/main.py's POST /api/brain/stream).
    * "terminal" — the charting-app Terminal copilot, which reaches the SAME gateway
                   (mm_brain.js → /api/brain/stream, context.page == "terminal"), so
                   ONE instrumentation point covers both. (The old Node-side writer in
                   terminal/app/api/copilot/route.ts is DEPRECATED and unused; both
                   surfaces now flow through the gateway.)

Why a shared bus and not a DB: the two AIs run on two separate remote deployments,
while the operator's admin panel reads local files on the Mac. Cloudflare R2 is the
transport every other artifact in this repo already rides (scripts/publish_r2 /
fetch_r2). Each response is written as ONE immutable object:

    mastermind_response_logs/<surface>/<YYYY-MM-DD>/<id>.json

Object-per-response (not an append-only shard) sidesteps R2's lack of append and
lets two hosts write concurrently with zero coordination. The admin ingests the
prefix incrementally (admin/mastermind_logs.py) into data/mastermind/response_log.jsonl
and overlays a local, mutable eval sidecar for batch grading/training curation.

CONTRACT (schema "mastermind.response_log.v1"):
    id            stable unique row id (uuid hex)
    schema        "mastermind.response_log.v1"
    ts            ISO-8601 UTC (…+00:00)
    surface       "macro" | "terminal"
    lane          "fast" | "pro" | null      (macro lanes; terminal → "fast")
    mode          "chat" | "research" | null
    model         provider model id that served the turn
    provider      "claude_api" | "deepseek" | ...
    thread_id     conversation id if any (null for stateless/guest)
    user_ref      HASHED user id, or "guest" — raw ids/emails are NEVER stored
    question      the user's message (text only; image markers stripped upstream)
    answer        the full assistant answer text
    input_tokens  int
    output_tokens int
    latency_ms    int | null
    context       {"page": ..., "symbol": ...} (small dict; scalars only)
    citations     list (macro only; [] otherwise)
    tools         list of tool names invoked ([] when unknown)
    lang          "en" | "zh" | null
    flags         {"filtered": bool, "degraded": bool, "error": bool, "screened": bool}
    thinking      OPTIONAL list of reasoning segments (added 2026-07-26, no version
                  bump — readers tolerate extra keys and older rows simply lack it):
                  [{"round": int, "phase": "tool"|"synthesis", "model": str,
                    "text": str}]; a Claude redacted_thinking block becomes the same
                  shape with "text": "" and "redacted": true.
                  WHY: the model's own reasoning is the eval corpus for CONTRADICTION
                  ASSESSMENT — whether it wrestled genuinely conflicting site signals,
                  and whether the conflict was our data being wrong (system error) or
                  the market being honestly split. The answer text alone hides that.

FAIL-SOFT: every public function is best-effort and must NEVER raise into the
request path. A missing R2 credential is a graceful no-op (returns False), exactly
like scripts/publish_r2. Logging is OFF only when explicitly disabled or when no
sink (R2 creds or a local dir) is configured.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "mastermind.response_log.v1"
R2_PREFIX = "mastermind_response_logs"

_VALID_SURFACES = ("macro", "terminal")

# Reasoning-trace bounds. A single Opus round can think for pages; the log is an eval
# corpus, not an archive, so each segment is clipped and the trace itself is capped.
# When the cap bites, the kept window is FIRST (N-1) + LAST: a chain of thought frames
# the conflict up front, but the SYNTHESIS segment — the decision this corpus exists to
# show — always rides last. Dropping it to keep an extra middle tool round would throw
# away the one segment the contradiction audit most needs.
_THINKING_TEXT_CAP = 6000
_THINKING_MAX_SEGMENTS = 24


# ---------------------------------------------------------------------------
# Config / gating
# ---------------------------------------------------------------------------

def _truthy(v: str | None) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def _local_dir() -> Path | None:
    """Optional local mirror dir. When set, rows are also written as
    <dir>/<surface>/<YYYY-MM-DD>/<id>.json — used by tests and as a VPS-side
    durability fallback when R2 is briefly unreachable."""
    d = os.environ.get("MASTERMIND_RESPONSE_LOG_LOCAL_DIR", "").strip()
    return Path(d) if d else None


def _r2_creds() -> bool:
    return bool(
        os.environ.get("R2_ENDPOINT")
        and os.environ.get("R2_ACCESS_KEY_ID")
        and os.environ.get("R2_SECRET_ACCESS_KEY")
        and os.environ.get("R2_BUCKET")
    )


def enabled() -> bool:
    """True when logging should run: not explicitly disabled AND a sink exists
    (R2 creds or a local mirror dir)."""
    if _truthy(os.environ.get("MASTERMIND_RESPONSE_LOG_DISABLED")):
        return False
    return _r2_creds() or _local_dir() is not None


# ---------------------------------------------------------------------------
# Privacy helpers
# ---------------------------------------------------------------------------

def hash_user_ref(user_id: str = "", user_email: str = "", is_guest: bool = False) -> str:
    """Stable, non-reversible reference for a user. Guests collapse to "guest".
    Never emits a raw id or email — only sha256[:16] over the id (falling back to
    the email) so the operator can group a user's turns without storing PII."""
    if is_guest:
        return "guest"
    seed = (str(user_id or "").strip() or str(user_email or "").strip())
    if not seed:
        return "anon"
    return "u_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _clip(s: Any, n: int) -> str:
    """Coerce to str and bound length — answers/questions can be long; the log is
    for eval, not archival, so a generous but finite cap keeps objects small."""
    t = "" if s is None else str(s)
    return t if len(t) <= n else t[:n] + " …[truncated]"


def _clean_context(context: Any) -> dict:
    """Keep only small scalar fields from the page context (page, symbol, …)."""
    out: dict[str, Any] = {}
    if isinstance(context, dict):
        for k in ("page", "symbol", "timeframe", "ticker", "route"):
            v = context.get(k)
            if isinstance(v, (str, int, float, bool)) and str(v):
                out[k] = v
    return out


def _clean_segment(seg: Any) -> dict | None:
    """Sanitize ONE reasoning segment, or None if it carries nothing worth keeping.

    Clips text to _THINKING_TEXT_CAP; coerces round→int and phase/model→str; drops an
    empty-text segment UNLESS it is redacted (a redacted_thinking block is evidence the
    model reasoned even though the text is unavailable)."""
    if not isinstance(seg, dict):
        return None
    redacted = bool(seg.get("redacted"))
    text = _clip(seg.get("text") or "", _THINKING_TEXT_CAP)
    if not text and not redacted:
        return None
    try:
        rnd = int(seg.get("round") or 0)
    except (TypeError, ValueError):
        rnd = 0
    item: dict[str, Any] = {
        "round": rnd,
        "phase": str(seg.get("phase") or ""),
        "model": str(seg.get("model") or ""),
        "text": text,
    }
    if redacted:
        item["redacted"] = True
    return item


def _clean_thinking(thinking: Any) -> list[dict]:
    """Sanitize a captured reasoning trace into the schema's `thinking` list.

    Keeps dict segments only (see _clean_segment) and caps the trace at
    _THINKING_MAX_SEGMENTS. When the cap bites the kept window is the FIRST
    (_THINKING_MAX_SEGMENTS - 1) segments PLUS the LAST surviving segment: the synthesis
    phase rides last and IS the decision the contradiction corpus exists to show, so a
    plain head-truncation would drop the most valuable segment of a long trace. Middle
    tool rounds are what gets dropped. Pure — never raises."""
    out: list[dict] = []
    if not isinstance(thinking, list):
        return out
    tail: dict | None = None   # newest keepable segment beyond the head window
    for seg in thinking:
        item = _clean_segment(seg)
        if item is None:
            continue
        if len(out) < _THINKING_MAX_SEGMENTS - 1:
            out.append(item)
        else:
            # Only the newest is held, so a 10k-segment trace never materialises 10k
            # clipped copies — one rolling slot, not a buffer.
            tail = item
    if tail is not None:
        out.append(tail)
    return out


def build_row(
    *,
    surface: str,
    question: str,
    answer: str,
    model: str = "",
    lane: str | None = None,
    mode: str | None = None,
    provider: str | None = None,
    thread_id: str | None = None,
    user_id: str = "",
    user_email: str = "",
    is_guest: bool = False,
    latency_ms: int | None = None,
    latency: dict | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    context: dict | None = None,
    citations: list | None = None,
    tools: list | None = None,
    lang: str | None = None,
    flags: dict | None = None,
    thinking: list | None = None,
    row_id: str | None = None,
) -> dict:
    """Build one `mastermind.response_log.v1` row. Pure — no I/O, never raises."""
    surf = surface if surface in _VALID_SURFACES else "macro"
    if not provider:
        provider = "claude_api" if str(model).startswith("claude") else (
            "deepseek" if "deepseek" in str(model).lower() else "")
    row: dict[str, Any] = {
        "id": row_id or uuid.uuid4().hex,
        "schema": SCHEMA,
        "ts": _now_iso(),
        "surface": surf,
        "lane": lane or None,
        "mode": mode or None,
        "model": str(model or "unknown"),
        "provider": provider or None,
        "thread_id": str(thread_id) if thread_id else None,
        "user_ref": hash_user_ref(user_id, user_email, is_guest),
        "question": _clip(question, 8000),
        "answer": _clip(answer, 24000),
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "latency_ms": int(latency_ms) if latency_ms is not None else None,
        # W5 Contract M: the breakdown behind latency_ms — {route, ttfv_ms, rounds[],
        # synthesis_ms, total_ms}. Additive: absent on every pre-W5 row, and a reader
        # that does not know the key is unaffected.
        "latency": dict(latency) if isinstance(latency, dict) else None,
        "context": _clean_context(context),
        "citations": list(citations) if isinstance(citations, list) else [],
        "tools": [str(t) for t in tools] if isinstance(tools, list) else [],
        "lang": lang or None,
        "flags": {
            "filtered": bool((flags or {}).get("filtered")),
            "degraded": bool((flags or {}).get("degraded")),
            "error": bool((flags or {}).get("error")),
            "screened": bool((flags or {}).get("screened")),
        },
        "thinking": _clean_thinking(thinking),
    }
    return row


# ---------------------------------------------------------------------------
# R2 sink
# ---------------------------------------------------------------------------

def _client():
    """Boto3 S3 client for R2, or None when creds/boto3 are absent. Mirrors
    scripts/publish_r2._client but kept self-contained so lib/ has no scripts dep."""
    ep = os.environ.get("R2_ENDPOINT")
    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (ep and ak and sk):
        return None
    try:
        import boto3  # noqa: PLC0415
        from botocore.config import Config  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — boto3 not installed → graceful no-op
        return None
    kw = dict(region_name="auto", signature_version="s3v4",
              retries={"max_attempts": 2, "mode": "standard"},
              connect_timeout=5, read_timeout=10)
    try:
        cfg = Config(**kw, request_checksum_calculation="when_required",
                     response_checksum_validation="when_required")
    except TypeError:
        cfg = Config(**kw)
    try:
        return boto3.client("s3", endpoint_url=ep, aws_access_key_id=ak,
                            aws_secret_access_key=sk, config=cfg)
    except Exception:  # noqa: BLE001
        return None


def object_key(row: dict) -> str:
    """R2 key for a row: mastermind_response_logs/<surface>/<date>/<id>.json.
    Date is taken from the row's ts so re-ingested rows land deterministically."""
    surf = row.get("surface") or "macro"
    ts = str(row.get("ts") or "")
    date = ts[:10] if len(ts) >= 10 and ts[4] == "-" else _today()
    rid = row.get("id") or uuid.uuid4().hex
    return f"{R2_PREFIX}/{surf}/{date}/{rid}.json"


def _write_local(row: dict, base: Path) -> None:
    key = object_key(row)
    p = base / Path(key).relative_to(R2_PREFIX)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _write_r2(row: dict) -> bool:
    s3 = _client()
    if s3 is None:
        return False
    try:
        s3.put_object(
            Bucket=os.environ["R2_BUCKET"],
            Key=object_key(row),
            Body=json.dumps(row, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        return True
    except Exception:  # noqa: BLE001 — network/creds problem → best-effort no-op
        return False


def write_row(row: dict) -> bool:
    """Persist one row to every configured sink (R2 + optional local mirror).
    Returns True if AT LEAST one sink accepted it. Never raises."""
    if not enabled():
        return False
    ok = False
    ld = _local_dir()
    if ld is not None:
        try:
            _write_local(row, ld)
            ok = True
        except Exception:  # noqa: BLE001
            pass
    try:
        if _write_r2(row):
            ok = True
    except Exception:  # noqa: BLE001
        pass
    return ok


def log_response(**kwargs: Any) -> bool:
    """Build + write in one call. Best-effort; never raises into the caller."""
    try:
        if not enabled():
            return False
        return write_row(build_row(**kwargs))
    except Exception:  # noqa: BLE001
        return False


def log_response_async(**kwargs: Any) -> None:
    """Fire-and-forget variant — offloads the R2 PUT to a daemon thread so a
    slow network call never delays the caller (the answer is already on the wire).
    Never raises."""
    if not enabled():
        return
    try:
        t = threading.Thread(target=log_response, kwargs=kwargs, daemon=True)
        t.start()
    except Exception:  # noqa: BLE001
        # Threading unavailable (extremely rare) — fall back to inline best-effort.
        log_response(**kwargs)
