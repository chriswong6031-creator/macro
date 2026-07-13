"""engine.neuralweb.mastermind_feedback — Mastermind → Neural Web reverse bridge reader.

PURPOSE
-------
Reads the counts-only feedback artifact Mastermind pushes into this repo
(site/mastermind/nw_feedback.json) and produces a governed, staleness-gated,
counts-only summary the Neural Web can rely on.

AUTHORITY CONTRACT (FB-R7/R8/R10, binding)
-------------------------------------------
This module is READ-ONLY with respect to site/mastermind/. It never writes
under that directory. The output is counts-only: no tickers, no position IDs,
no fill IDs, no notional, no host paths. All five authority booleans are FALSE.

STALENESS CONTRACT (FB-R14)
----------------------------
generated_at older than SOURCE_STALENESS_DAYS (4 calendar days) → state: "stale".
File missing, unparseable JSON, or unparseable generated_at → state: "absent".
Neither state may produce fabricated zero counts; totals are omitted or null
with gap_notes explaining the degraded state.

SCHEMA TOLERANCE
----------------
Accepts mastermind_nw_feedback.v1, .v2 (additive: decision_flow, outcome_mix,
context_audit, metric_families blocks) and .v3 (W-AI dialogue: reflection,
nudges, operator_directives — the Mastermind AI reflection lobe's coded asks
plus operator-authored, bot-side-scrubbed directives, re-scrubbed here).
Unknown schema string → treat as absent with a gap note naming the schema seen.

LEAK-PROOF BY CONSTRUCTION (FB-R8, test-enforced)
---------------------------------------------------
All output is built by WHITELIST copy of known count keys only. This module
never deep-copies unknown keys or sub-objects from the source. A poisoned
source carrying ticker/fill_id/dollar strings will not reach the output.

METRIC FAMILIES (§3 frozen)
----------------------------
See _METRIC_FAMILIES_STATUS for the preregistered families and their
live/blocked/registered status. Blocked families are printed with reasons,
never faked. The metric_families block in the output is the hardcoded registry
below — it is NOT a passthrough of any metric_families key in the source.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema identity
# ---------------------------------------------------------------------------

SCHEMA = "neuralweb.mastermind_feedback_summary.v1"
ARTIFACT_ID = "mastermind-feedback-summary"

# Accepted source schemas
_ACCEPTED_SOURCE_SCHEMAS = frozenset({
    "mastermind_nw_feedback.v1",
    "mastermind_nw_feedback.v2",
    "mastermind_nw_feedback.v3",
})

# Schemas that carry the v2 additive blocks (v3 is a superset of v2)
_V2_PLUS_SCHEMAS = frozenset({
    "mastermind_nw_feedback.v2",
    "mastermind_nw_feedback.v3",
})

# Staleness threshold: generated_at older than this many calendar days → stale
SOURCE_STALENESS_DAYS = 4

# Source artifact path relative to repo root
_SOURCE_PATH = Path("site") / "mastermind" / "nw_feedback.json"

# Output path relative to repo root
_OUTPUT_PATH = Path("data") / "governance" / "mastermind_feedback_summary.json"

# Label sanitization: keys must match this pattern (lowercase enforced first)
_LABEL_RE = re.compile(r'^[a-z0-9_]{1,40}$')

# Maximum label-dict entries to copy (drop extras by descending count then lexicographic)
_MAX_LABEL_ENTRIES = 12

# Preregistered metric families (FB-R9, §3)
_METRIC_FAMILIES_STATUS: list[dict] = [
    {
        "family": "context_engagement",
        "status": "live",
        "definition": (
            "Per window: n_runs with nw_context present / stale / absent "
            "(from nw_context_audit.jsonl); context_seen_rate = present / total"
        ),
        "notes": "Live in W-M (Mastermind-side substrate built).",
    },
    {
        "family": "decision_flow",
        "status": "live",
        "definition": (
            "Per book, per window: packet_accepted, packet_rejected counts "
            "(from run_events); rejection error class counts (sanitized labels only)"
        ),
        "notes": "Live in W-M.",
    },
    {
        "family": "outcome_mix",
        "status": "live",
        "definition": (
            "Per window: resolved-outcome counts by outcome label from outcome_ledger.jsonl "
            "(outcome field), n_resolved"
        ),
        "notes": "Live in W-M.",
    },
    {
        "family": "nw_reflection",
        "status": "live",
        "definition": (
            "Mastermind AI reflection over the context bridge: contract-drift codes, "
            "coverage counts, context-quality counts, attribution state (v3 source block)"
        ),
        "notes": "Live in W-AI (bot-side brain/nw_reflection.py).",
    },
    {
        "family": "orchestrator_dialogue",
        "status": "live",
        "definition": (
            "Coded nudges + operator directives from the bot, acknowledged per build "
            "via the ack block → lobes.mastermind_ai in mastermind_context (v3 source blocks)"
        ),
        "notes": "Live in W-AI. Acknowledgement ≠ action; actions are operator/cortex items.",
    },
    {
        "family": "warning_interaction",
        "status": "registered",
        "definition": (
            "Warning-present × operator/brain action cross-counts; requires a frozen "
            "warning taxonomy (contradictions / risk flags in the forward context)"
        ),
        "notes": "REGISTERED — needs taxonomy ruling before compute.",
        "blocked_reason": "Requires frozen warning taxonomy ruling.",
    },
    {
        "family": "warning_outcome_delta",
        "status": "blocked",
        "definition": "Outcome mix conditioned on warning-followed vs warning-ignored",
        "notes": "BLOCKED until ≥60 context-audit sessions (FB-R10).",
        "blocked_reason": (
            "Requires ≥60 context-audit sessions and preregistered warning_outcome_delta "
            "with sign stability across two non-overlapping eras, plus Fable-tier ruling."
        ),
    },
    {
        "family": "fill_slippage_by_context",
        "status": "blocked",
        "definition": (
            "fill_slippage_by_context, arrival_mid_slippage_bps, spread_paid_bps, "
            "participation_band"
        ),
        "notes": "BLOCKED — no execution model exists (paper fills at close/open). Do not fake.",
        "blocked_reason": (
            "No execution model exists. Paper fills execute at last close / next open. "
            "No spread, no participation, no venue. Metrics are unmeasurable."
        ),
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root)
    # engine/neuralweb/mastermind_feedback.py → up 3 → repo root
    return Path(__file__).resolve().parent.parent.parent


def _parse_date(ts: str) -> datetime | None:
    """Parse ISO-8601 datetime string, returning None on failure.

    Handles both "2026-07-06T22:25:00Z" and "2026-07-06T22:25:00+00:00" forms.
    Naive datetimes are attached to UTC; aware datetimes are converted to UTC.
    Does NOT truncate the fractional-seconds or sub-second portion.
    """
    if not isinstance(ts, str) or not ts:
        return None
    try:
        # Replace trailing Z with +00:00 for fromisoformat compatibility
        s = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        # Convert aware datetime to UTC
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _is_stale(generated_at: str) -> bool:
    """Return True if generated_at is older than SOURCE_STALENESS_DAYS calendar days.

    Staleness is measured in wall-clock seconds elapsed since generated_at.
    Returns True (treat as absent) if the timestamp cannot be parsed.
    """
    dt = _parse_date(generated_at)
    if dt is None:
        return True
    now = datetime.now(timezone.utc)
    age_days = (now - dt).total_seconds() / 86400
    return age_days > SOURCE_STALENESS_DAYS


def _int_or_none(v: object) -> int | None:
    """Safely coerce to int; return None if not a valid integer."""
    if isinstance(v, int) and not isinstance(v, bool):
        return v
    if isinstance(v, float) and v == int(v):
        return int(v)
    return None


def _sanitize_label_dict(
    raw: dict,
    block_name: str,
    gap_notes: list[str],
) -> dict:
    """Sanitize a label→count dict with strict rules.

    Rules:
    - Key is lowercased; must then match ^[a-z0-9_]{1,40}$; otherwise dropped.
    - Value must pass _int_or_none; otherwise dropped.
    - At most _MAX_LABEL_ENTRIES entries kept: sort by descending count, then
      lexicographic key, truncate.
    - A single gap note is emitted (once) if any entry is dropped.

    Returns a cleaned dict (may be empty).
    """
    cleaned: dict[str, int] = {}
    dropped = 0
    for raw_key, raw_val in raw.items():
        key = raw_key.lower() if isinstance(raw_key, str) else ""
        if not _LABEL_RE.match(key):
            dropped += 1
            continue
        v = _int_or_none(raw_val)
        if v is None:
            dropped += 1
            continue
        cleaned[key] = v

    if dropped:
        gap_notes.append(
            f"{block_name}: dropped {dropped} label(s) that failed strict sanitization "
            f"(key must match ^[a-z0-9_]{{1,40}}$; value must be an integer)"
        )

    if len(cleaned) > _MAX_LABEL_ENTRIES:
        # Sort by descending count, then lexicographic key, keep top _MAX_LABEL_ENTRIES
        sorted_items = sorted(cleaned.items(), key=lambda kv: (-kv[1], kv[0]))
        gap_notes.append(
            f"{block_name}: capped at {_MAX_LABEL_ENTRIES} entries "
            f"(dropped {len(cleaned) - _MAX_LABEL_ENTRIES} by ascending count)"
        )
        cleaned = dict(sorted_items[:_MAX_LABEL_ENTRIES])

    return cleaned


def _sanitize_book_id(raw_id: object) -> str:
    """Sanitize a book_id value.

    Must match ^[a-z0-9_]{1,40}$ after lowercasing; falls back to 'unknown'.
    """
    if not isinstance(raw_id, str) or not raw_id:
        return "unknown"
    key = raw_id.lower()
    if _LABEL_RE.match(key):
        return key
    return "unknown"


# ---------------------------------------------------------------------------
# Per-book whitelist extractor
# ---------------------------------------------------------------------------

# The only count keys we copy from each book entry in the source.
_BOOK_COUNT_KEYS = frozenset({
    "gate_failures_total",
    "rejected_decision_count",
    "lock_conflict_count",
    "stale_freeze_count",
})

# Map source key names → output key names for per-book counts
_BOOK_KEY_MAP: dict[str, str] = {
    "gate_failures_total": "gate_failures_total",
    "rejected_decision_count": "rejected_decision_count",
    "lock_conflict_count": "lock_conflict_count",
    "stale_freeze_count": "stale_freeze_count",
}


def _extract_book(raw_book: dict) -> dict:
    """Whitelist-extract count fields from a raw book entry.

    Only copies known count keys. book_id is taken from the source but
    validated to match ^[a-z0-9_]{1,40}$ after lowercasing.
    Falls back to 'unknown' if book_id is not a valid string.
    """
    book_id = _sanitize_book_id(raw_book.get("book_id", ""))
    out: dict = {"book_id": book_id}

    # gate_failures: in v1 it's a nested object; we whitelist only .total
    raw_gate = raw_book.get("gate_failures")
    if isinstance(raw_gate, dict):
        total_v = raw_gate.get("total")
        out["gate_failures_total"] = _int_or_none(total_v)
    elif isinstance(raw_gate, (int, float)):
        out["gate_failures_total"] = _int_or_none(raw_gate)
    else:
        out["gate_failures_total"] = None

    # Remaining count keys — direct whitelist copy
    for src_key, out_key in (
        ("rejected_decision_count", "rejected_decision_count"),
        ("lock_conflict_count", "lock_conflict_count"),
        ("stale_freeze_count", "stale_freeze_count"),
    ):
        out[out_key] = _int_or_none(raw_book.get(src_key))

    return out


# ---------------------------------------------------------------------------
# v2 passthrough blocks (counts-only whitelist extraction)
# ---------------------------------------------------------------------------

def _extract_decision_flow(raw: dict, gap_notes: list[str]) -> dict | None:
    """Whitelist-extract decision_flow counts from v2 source block.

    Canonical v2 shape:
        {
          "by_book": [{"book_id": "flagship", "packet_accepted": 1, "packet_rejected": 1}],
          "rejection_error_classes": {"falsifiers": 1, "expected_failure_mode": 1}
        }

    book_id values are sanitized via _sanitize_book_id.
    rejection_error_classes keys are sanitized via _sanitize_label_dict
    (^[a-z0-9_]{1,40}$, cap 12, drop+note on failure).
    """
    df = raw.get("decision_flow")
    if not isinstance(df, dict):
        return None
    out: dict = {}

    # by_book list (v2 canonical — per-book packet accepted/rejected)
    by_book_raw = df.get("by_book")
    if isinstance(by_book_raw, list):
        by_book_out = []
        for entry in by_book_raw:
            if not isinstance(entry, dict):
                continue
            book_id = _sanitize_book_id(entry.get("book_id", ""))
            book_entry: dict = {"book_id": book_id}
            for key in ("packet_accepted", "packet_rejected"):
                v = _int_or_none(entry.get(key))
                if v is not None:
                    book_entry[key] = v
            by_book_out.append(book_entry)
        if by_book_out:
            out["by_book"] = by_book_out

    # rejection_error_classes (v2 canonical — replaces old top_error_classes)
    error_classes_raw = df.get("rejection_error_classes")
    if isinstance(error_classes_raw, dict):
        cleaned = _sanitize_label_dict(
            error_classes_raw,
            "decision_flow.rejection_error_classes",
            gap_notes,
        )
        if cleaned:
            out["rejection_error_classes"] = cleaned

    return out if out else None


def _extract_outcome_mix(raw: dict, gap_notes: list[str]) -> dict | None:
    """Whitelist-extract outcome_mix counts from v2 source block.

    Canonical v2 shape:
        {"n_resolved": 3, "by_outcome": {"1": 2, "0": 1}}

    by_outcome keys are sanitized via _sanitize_label_dict
    (^[a-z0-9_]{1,40}$, cap 12). Note: digit-only keys ("1", "0") are
    valid under this charset and pass through.
    """
    om = raw.get("outcome_mix")
    if not isinstance(om, dict):
        return None
    out: dict = {}
    n_resolved = _int_or_none(om.get("n_resolved"))
    if n_resolved is not None:
        out["n_resolved"] = n_resolved

    # by_outcome (v2 canonical — replaces old by_band)
    by_outcome_raw = om.get("by_outcome")
    if isinstance(by_outcome_raw, dict):
        cleaned = _sanitize_label_dict(
            by_outcome_raw,
            "outcome_mix.by_outcome",
            gap_notes,
        )
        if cleaned:
            out["by_outcome"] = cleaned

    return out if out else None


def _extract_context_audit(raw: dict, gap_notes: list[str]) -> dict | None:
    """Whitelist-extract context_audit counts from v2 source block.

    Canonical v2 shape (normal):
        {"n_present": 1, "n_stale": 1, "n_absent": 1, "n_runs_total": 3,
         "context_seen_rate": 0.333}

    Accruing variant — when the source sidecar has not yet accrued, the
    exporter emits {"state": "accruing", "n_runs_total": 0}. This is
    passed through intact (state string whitelisted to exactly "accruing").

    context_seen_rate is clamped to [0, 1]; out-of-range → field dropped
    with a gap note.
    """
    ca = raw.get("context_audit")
    if not isinstance(ca, dict):
        return None

    # Accruing variant
    if ca.get("state") == "accruing":
        accruing_out: dict = {"state": "accruing"}
        n_runs = _int_or_none(ca.get("n_runs_total"))
        if n_runs is not None:
            accruing_out["n_runs_total"] = n_runs
        return accruing_out

    out: dict = {}
    for key in ("n_present", "n_stale", "n_absent", "n_runs_total"):
        v = _int_or_none(ca.get(key))
        if v is not None:
            out[key] = v

    # context_seen_rate: float [0,1]; clamp out-of-range → drop + gap note
    rate_raw = ca.get("context_seen_rate")
    if rate_raw is not None:
        if isinstance(rate_raw, (int, float)) and not isinstance(rate_raw, bool):
            rate = float(rate_raw)
            if 0.0 <= rate <= 1.0:
                out["context_seen_rate"] = rate
            else:
                gap_notes.append(
                    f"context_audit.context_seen_rate={rate!r} out of [0,1] range; "
                    "field dropped"
                )

    return out if out else None


# ---------------------------------------------------------------------------
# v3 blocks (W-AI dialogue) — whitelist extraction + directive text re-scrub
# ---------------------------------------------------------------------------

_MAX_NUDGES = 10
_MAX_DIRECTIVES = 10
_NUDGE_DETAIL_MAX = 160
_DIRECTIVE_TEXT_MAX = 280
_DIRECTIVE_ID_RE = re.compile(r'^[0-9a-f]{6,16}$')
_SEVERITY_ALLOWED = frozenset({"high", "medium", "low"})
_NUDGE_KIND_ALLOWED = frozenset({"contract_drift", "coverage_gap", "staleness",
                                 "lobe_request", "other"})
_DRIFT_STATUS_ALLOWED = frozenset({"dead", "partial", "ok", "unknown"})
# Directive text re-scrub (defence-in-depth — the bot refuses these at intake too).
# Any match → the directive is DROPPED with a gap note, never partially copied.
_DIRECTIVE_DENY = [
    re.compile(r'MASTERMIND_[A-Z_]+'),
    re.compile(r'\$[\d,]+'),
    re.compile(r'(?i)\b[A-Za-z0-9+/]{40,}\b'),
    re.compile(r'(?i)(api[_-]?key|token|secret|password)\s*[:=]'),
]


def _clean_date_str(v: object) -> str | None:
    if isinstance(v, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', v[:10]):
        return v[:10]
    return None


def _extract_reflection(raw: dict, gap_notes: list[str]) -> dict | None:
    """Whitelist-extract the v3 reflection block (codes + counts only)."""
    rf = raw.get("reflection")
    if not isinstance(rf, dict):
        return None
    out: dict = {}
    state = rf.get("state")
    out["state"] = state if state in ("ok", "absent") else "absent"
    if out["state"] != "ok":
        return out
    asof = _clean_date_str(rf.get("asof"))
    if asof:
        out["asof"] = asof
    drift_out: list[dict] = []
    for d in (rf.get("contract_drift") or [])[:_MAX_NUDGES] if isinstance(rf.get("contract_drift"), list) else []:
        if not isinstance(d, dict):
            continue
        code = str(d.get("code", "")).lower()
        if not _LABEL_RE.match(code[:40]):
            continue
        status = d.get("status") if d.get("status") in _DRIFT_STATUS_ALLOWED else "unknown"
        sev = d.get("severity") if d.get("severity") in _SEVERITY_ALLOWED else "low"
        drift_out.append({"code": code[:40], "status": status, "severity": sev})
    if drift_out:
        out["contract_drift"] = drift_out
    for block_name, keys in (
        ("coverage", ("open_theses_n", "resolved_recent_n", "with_context_row_n")),
        ("context_quality", ("window_runs", "n_present", "n_stale", "n_absent")),
        ("attribution", ("n_resolved", "joinable_n")),
    ):
        src = rf.get(block_name)
        if not isinstance(src, dict):
            continue
        blk: dict = {}
        for k in keys:
            v = _int_or_none(src.get(k))
            if v is not None:
                blk[k] = v
        for rate_key in ("coverage_rate", "seen_rate"):
            rv = src.get(rate_key)
            if isinstance(rv, (int, float)) and not isinstance(rv, bool) and 0.0 <= float(rv) <= 1.0:
                blk[rate_key] = float(rv)
        if block_name == "attribution":
            st = src.get("state")
            if isinstance(st, str) and _LABEL_RE.match(st.lower()[:40]):
                blk["state"] = st.lower()[:40]
        if blk:
            out[block_name] = blk
    return out


def _extract_nudges(raw: dict, gap_notes: list[str]) -> list[dict]:
    """Whitelist-extract the v3 nudges list (≤10 coded rows; detail length-capped and
    deny-scrubbed — a nudge whose detail matches a deny pattern is dropped whole)."""
    src = raw.get("nudges")
    if not isinstance(src, list):
        return []
    out: list[dict] = []
    dropped = 0
    for n in src:
        if not isinstance(n, dict):
            dropped += 1
            continue
        code = str(n.get("code", "")).lower()
        if not _LABEL_RE.match(code[:40]):
            dropped += 1
            continue
        detail = str(n.get("detail", ""))[:_NUDGE_DETAIL_MAX]
        if any(p.search(detail) for p in _DIRECTIVE_DENY):
            dropped += 1
            continue
        out.append({
            "code": code[:40],
            "kind": (n.get("kind") if n.get("kind") in _NUDGE_KIND_ALLOWED else "other"),
            "severity": (n.get("severity") if n.get("severity") in _SEVERITY_ALLOWED else "low"),
            "detail": detail,
            "first_seen": _clean_date_str(n.get("first_seen")),
            "builds_seen": _int_or_none(n.get("builds_seen")),
        })
        if len(out) >= _MAX_NUDGES:
            break
    if dropped:
        gap_notes.append(f"nudges: dropped {dropped} row(s) failing whitelist/scrub")
    return out


def _extract_operator_directives(raw: dict, gap_notes: list[str]) -> list[dict]:
    """Whitelist-extract v3 operator directives (≤10). The text is operator-authored and
    bot-side scrubbed; re-scrubbed here (deny patterns → drop whole row + gap note)."""
    src = raw.get("operator_directives")
    if not isinstance(src, list):
        return []
    out: list[dict] = []
    dropped = 0
    for d in src:
        if not isinstance(d, dict):
            dropped += 1
            continue
        rid = str(d.get("id", "")).lower()
        text = str(d.get("text", "")).strip()[:_DIRECTIVE_TEXT_MAX]
        if not _DIRECTIVE_ID_RE.match(rid) or not text:
            dropped += 1
            continue
        if any(p.search(text) for p in _DIRECTIVE_DENY):
            dropped += 1
            continue
        out.append({"id": rid, "created": _clean_date_str(d.get("created")), "text": text})
        if len(out) >= _MAX_DIRECTIVES:
            break
    if dropped:
        gap_notes.append(f"operator_directives: dropped {dropped} row(s) failing whitelist/scrub")
    return out


# ---------------------------------------------------------------------------
# Main read + build functions
# ---------------------------------------------------------------------------

def _ingest_enabled(repo: Path) -> bool:
    """config.yml orchestrator.ingest_bot_feedback — the operator's ingestion switch (W-AI).

    Default True; any read failure degrades to enabled (the switch must fail open, never
    silently disable the contract)."""
    try:
        import yaml  # noqa: PLC0415
        cfg = yaml.safe_load((repo / "config.yml").read_text(encoding="utf-8")) or {}
        v = (cfg.get("orchestrator") or {}).get("ingest_bot_feedback")
        return v if isinstance(v, bool) else True
    except Exception:  # noqa: BLE001
        return True


def read_feedback(root: Path | str | None = None) -> dict:
    """Read and parse site/mastermind/nw_feedback.json.

    Returns a dict with:
        state: "present" | "stale" | "absent" | "disabled"
        raw:   the parsed source dict (only when state == "present")
        gap_notes: list of str
        source_schema: str or None
    """
    repo = _repo_root(root)
    source_path = repo / _SOURCE_PATH
    gap_notes: list[str] = []

    # Operator switch (W-AI): config.yml orchestrator.ingest_bot_feedback=false → the build
    # ignores the bot artifact entirely (state 'disabled', never fabricated counts).
    if not _ingest_enabled(repo):
        gap_notes.append(
            "ingestion disabled by operator (config.yml orchestrator.ingest_bot_feedback=false)"
        )
        return {"state": "disabled", "raw": None, "gap_notes": gap_notes, "source_schema": None}

    if not source_path.exists():
        gap_notes.append(
            f"site/mastermind/nw_feedback.json absent — source path {_SOURCE_PATH} not found"
        )
        return {"state": "absent", "raw": None, "gap_notes": gap_notes, "source_schema": None}

    try:
        raw = json.loads(source_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        gap_notes.append(f"site/mastermind/nw_feedback.json unparseable — {exc}")
        return {"state": "absent", "raw": None, "gap_notes": gap_notes, "source_schema": None}

    if not isinstance(raw, dict):
        gap_notes.append("site/mastermind/nw_feedback.json is not a JSON object")
        return {"state": "absent", "raw": None, "gap_notes": gap_notes, "source_schema": None}

    # Schema check
    source_schema = raw.get("schema")
    if source_schema not in _ACCEPTED_SOURCE_SCHEMAS:
        gap_notes.append(
            f"site/mastermind/nw_feedback.json has unknown schema {source_schema!r} "
            f"(accepted: {sorted(_ACCEPTED_SOURCE_SCHEMAS)}); treating as absent"
        )
        return {
            "state": "absent",
            "raw": None,
            "gap_notes": gap_notes,
            "source_schema": source_schema,
        }

    # Staleness check
    generated_at = raw.get("generated_at", "")
    if not isinstance(generated_at, str) or not generated_at:
        gap_notes.append(
            "site/mastermind/nw_feedback.json has absent or non-string generated_at; "
            "treating as absent"
        )
        return {
            "state": "absent",
            "raw": None,
            "gap_notes": gap_notes,
            "source_schema": source_schema,
        }

    # Try to parse generated_at; unparseable → absent (distinct gap note from stale)
    dt = _parse_date(generated_at)
    if dt is None:
        gap_notes.append(
            f"site/mastermind/nw_feedback.json has unparseable generated_at={generated_at!r}; "
            "treating as absent (cannot verify freshness)"
        )
        return {
            "state": "absent",
            "raw": None,
            "gap_notes": gap_notes,
            "source_schema": source_schema,
        }

    now = datetime.now(timezone.utc)
    age_days = (now - dt).total_seconds() / 86400
    if age_days > SOURCE_STALENESS_DAYS:
        gap_notes.append(
            f"site/mastermind/nw_feedback.json is stale — generated_at={generated_at!r} "
            f"is older than {SOURCE_STALENESS_DAYS} calendar days"
        )
        return {
            "state": "stale",
            "raw": None,
            "gap_notes": gap_notes,
            "source_schema": source_schema,
        }

    return {
        "state": "present",
        "raw": raw,
        "gap_notes": gap_notes,
        "source_schema": source_schema,
    }


def build_summary(root: Path | str | None = None) -> dict:
    """Build the mastermind_feedback_summary artifact.

    Returns a dict conforming to neuralweb.mastermind_feedback_summary.v1.
    All counts are from the source whitelist only. When state is absent or
    stale, totals are omitted/null — never fabricated zeros.

    The dict always contains:
        schema, generated_utc, state, source_schema, gap_notes,
        is_context_only, authority, metric_families

    When state == "present" it also contains:
        asof, window_days, totals, per_book
        (and optionally: decision_flow, outcome_mix, context_audit if v2 blocks present)

    metric_families is the hardcoded registry (_METRIC_FAMILIES_STATUS) — it is
    NOT a passthrough of any metric_families key found in the source artifact.
    """
    repo = _repo_root(root)
    now = datetime.now(timezone.utc)

    result = read_feedback(repo)
    state: str = result["state"]
    raw: dict | None = result["raw"]
    gap_notes: list[str] = list(result["gap_notes"])
    source_schema: str | None = result["source_schema"]

    # Authority block — all five booleans false (FB-R10, mirrors mastermind_context.py)
    authority: dict = {
        "can_add_candidates": False,
        "can_raise_size": False,
        "can_lower_size": False,
        "can_block_entry": False,
        "can_force_exit": False,
        "notes": (
            "context_only at birth; all authority booleans false. "
            "Promotions require ≥60 context-audit sessions, preregistered "
            "warning_outcome_delta with sign stability, Fable-tier ruling, "
            "and a governance-ledger event on the Mastermind side (FB-R10)."
        ),
    }

    payload: dict = {
        "schema": SCHEMA,
        "generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "state": state,
        "source_schema": source_schema,
        "is_context_only": True,
        "authority": authority,
        "metric_families": _METRIC_FAMILIES_STATUS,
        "gap_notes": gap_notes,
    }

    if state != "present" or raw is None:
        # Absent or stale: do NOT fabricate totals (FB-R14)
        payload["totals"] = None
        payload["per_book"] = None
        return payload

    # ── Extract allowed fields from source (whitelist only) ───────────────────

    # asof: use generated_at[:10] as date string
    generated_at = raw.get("generated_at", "")
    asof = generated_at[:10] if isinstance(generated_at, str) and generated_at else None
    payload["asof"] = asof

    # window_days
    window_days = _int_or_none(raw.get("window_days"))
    payload["window_days"] = window_days

    # ── Totals (whitelist aggregation across books) ────────────────────────────
    books_raw = raw.get("books")
    if not isinstance(books_raw, list):
        books_raw = []

    n_books = 0
    gate_failures_total = 0
    rejected_decisions_total = 0
    lock_conflicts_total = 0
    stale_freezes_total = 0
    per_book_out: list[dict] = []

    for book_raw in books_raw:
        if not isinstance(book_raw, dict):
            continue
        book_out = _extract_book(book_raw)
        per_book_out.append(book_out)
        n_books += 1
        # Accumulate totals (treat None as 0 for aggregation)
        gate_failures_total += book_out.get("gate_failures_total") or 0
        rejected_decisions_total += book_out.get("rejected_decision_count") or 0
        lock_conflicts_total += book_out.get("lock_conflict_count") or 0
        stale_freezes_total += book_out.get("stale_freeze_count") or 0

    # Thesis counts (whitelist only)
    thesis_counts_raw = raw.get("thesis_counts")
    theses_open: int | None = None
    theses_total: int | None = None
    if isinstance(thesis_counts_raw, dict):
        theses_open = _int_or_none(thesis_counts_raw.get("open"))
        theses_total = _int_or_none(thesis_counts_raw.get("total"))

    # Run counts (whitelist: ok + error totals only — no per-job names)
    run_counts_raw = raw.get("run_counts")
    runs_ok_total: int | None = None
    runs_error_total: int | None = None
    if isinstance(run_counts_raw, dict):
        ok_sum = 0
        err_sum = 0
        for job_counts in run_counts_raw.values():
            if isinstance(job_counts, dict):
                ok_sum += _int_or_none(job_counts.get("ok")) or 0
                err_sum += _int_or_none(job_counts.get("error")) or 0
        runs_ok_total = ok_sum
        runs_error_total = err_sum

    payload["totals"] = {
        "n_books": n_books,
        "gate_failures_total": gate_failures_total,
        "rejected_decisions_total": rejected_decisions_total,
        "lock_conflicts_total": lock_conflicts_total,
        "stale_freezes_total": stale_freezes_total,
        "theses_open": theses_open,
        "theses_total": theses_total,
        "runs_ok_total": runs_ok_total,
        "runs_error_total": runs_error_total,
    }
    payload["per_book"] = per_book_out

    # ── v2 passthrough blocks (counts-only; v3 is a superset of v2) ────────────
    if source_schema in _V2_PLUS_SCHEMAS:
        df = _extract_decision_flow(raw, gap_notes)
        if df is not None:
            payload["decision_flow"] = df

        om = _extract_outcome_mix(raw, gap_notes)
        if om is not None:
            payload["outcome_mix"] = om

        ca = _extract_context_audit(raw, gap_notes)
        if ca is not None:
            payload["context_audit"] = ca

    # ── v3 dialogue blocks (W-AI: reflection / nudges / operator directives) ──
    if source_schema == "mastermind_nw_feedback.v3":
        rf = _extract_reflection(raw, gap_notes)
        if rf is not None:
            payload["reflection"] = rf
        nudges = _extract_nudges(raw, gap_notes)
        if nudges:
            payload["nudges"] = nudges
        directives = _extract_operator_directives(raw, gap_notes)
        if directives:
            payload["operator_directives"] = directives
        # The ACK the bot reads back through the context bridge (lobes.mastermind_ai):
        # every ingested code/id is acknowledged — action status is the operator's/cortex's.
        payload["ack"] = {
            "nudge_codes_seen": [n["code"] for n in nudges],
            "directive_ids_seen": [d["id"] for d in directives],
        }

    return payload


def build_and_write(root: Path | str | None = None) -> dict:
    """Build summary and write to data/governance/mastermind_feedback_summary.json.

    Raises
    ------
    OSError
        Only if writing the artifact itself fails.
    """
    repo = _repo_root(root)
    payload = build_summary(root=repo)

    out_path = repo / _OUTPUT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)

    raw_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=str)
    out_path.write_text(raw_json, encoding="utf-8")
    log.info("mastermind_feedback: written → %s", out_path)

    return payload
