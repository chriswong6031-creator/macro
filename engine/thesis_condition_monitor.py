"""Thesis condition monitor (F11 packet B-F11-1).

Pure projection over the EXISTING tripwire latch machine
(engine/falsifier_tripwires.py) -- no new analysis lifecycle, no scoring, no send.
Reads the committed data/cycle_ontology/{falsifiers,tripwire_state}.json produced by
the render lane (.github/workflows/render.yml:946 -> scripts/build_cycle.py:311-321),
joins them to active Supabase Thesis Objects BY SUBJECT, and enqueues one
public.alert_outbox row per not-yet-notified FIRED window. Delivery belongs to F08
(scripts/drain_alert_outbox.py). Notification latency is <= one nightly cycle after the
render that latched the fire. human_research_only: informational; no trading authority,
no sizing, no position advice.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any

from engine import falsifier_tripwires as ft
from lib import config

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://fsldfzlxyavsuwqbceod.supabase.co"
).rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
EVIDENCE_BASE = "https://www.mastermind-x.com"
SOURCE = "macro.thesis_condition_monitor"
CATEGORY = "thesis_window"
CHANNEL = "email"

READ_OK, READ_OK_ZERO, READ_NO_COVERAGE, READ_UNAVAILABLE = (
    "READ_OK",
    "READ_OK_ZERO",
    "READ_NO_COVERAGE",
    "READ_UNAVAILABLE",
)


@dataclass(frozen=True)
class TypedRead:
    state: str
    rows: list | None
    error_class: str | None = None


@dataclass(frozen=True)
class MonitorPlan:
    rows: list[dict]
    evaluated_n: int
    matched_n: int
    duplicate_n: int
    no_coverage_n: int
    unmappable_n: int
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MonitorResult:
    outcome: str
    read_state: str
    error_class: str | None
    evaluated_n: int
    matched_n: int
    enqueued_n: int
    duplicate_n: int
    no_coverage_n: int
    unmappable_n: int
    run_id: str


# ---------------------------------------------------------------------------
# Pure functions -- no IO
# ---------------------------------------------------------------------------

def subject_key(subject_ref: dict) -> tuple[str, str] | None:
    """Resolve a thesis subject_ref to a ('ticker'|'cycle', normalized) tuple."""
    if not isinstance(subject_ref, dict):
        return None
    kind = subject_ref.get("kind")
    owner = subject_ref.get("owner")
    key = subject_ref.get("key")
    if kind == "issuer":
        listing = subject_ref.get("listing") or {}
        symbol = listing.get("symbol") if isinstance(listing, dict) else None
        raw = symbol or key
        if not raw or not isinstance(raw, str):
            return None
        return ("ticker", raw.strip().upper())
    if kind == "theme" and owner == "macro.theme_registry":
        if not key or not isinstance(key, str):
            return None
        return ("cycle", key.strip().lower())
    return None


def load_tripwire_view() -> tuple[list[dict], dict]:
    """Read the committed falsifiers + latch state. NEVER recomputes them."""
    root = config.ROOT
    f_path = root / ft._FALSIFIERS_JSON
    s_path = root / ft._STATE_JSON
    entries: list[dict] = []
    state: dict = {}
    if f_path.exists():
        try:
            data = json.loads(f_path.read_text())
            entries = data if isinstance(data, list) else data.get("falsifiers", [])
        except (json.JSONDecodeError, OSError):
            entries = []
    if s_path.exists():
        try:
            state = json.loads(s_path.read_text())
        except (json.JSONDecodeError, OSError):
            state = {}
    return entries, state


def fired_windows(entries: list[dict], latch_state: dict) -> list[dict]:
    """Windows whose latch_state entry is a latched FIRED with a non-null fired_on."""
    out = []
    for e in entries:
        eid = e.get("id")
        st = latch_state.get(eid)
        if not isinstance(st, dict):
            continue
        if st.get("state") != "FIRED" or not st.get("latched"):
            continue
        fired_on = st.get("fired_on")
        if not fired_on:
            continue
        out.append(
            {
                "id": eid,
                "version": st.get("version", e.get("version")),
                "cycle": e.get("cycle"),
                "scope": e.get("scope", "cycle"),
                "tickers": e.get("tickers") or [],
                "claim": e.get("claim", ""),
                "direction": e.get("direction", "refutes"),
                "coverage": e.get("coverage", "full"),
                "fired_on": fired_on,
            }
        )
    return out


def match_windows(subject: tuple[str, str], windows: list[dict]) -> list[dict]:
    kind, norm = subject
    out = []
    for w in windows:
        scope = w.get("scope", "cycle")
        if kind == "ticker" and scope == "ticker":
            tickers = [t.upper() for t in (w.get("tickers") or [])]
            if norm in tickers:
                out.append(w)
        elif kind == "cycle" and scope != "ticker":
            if str(w.get("cycle", "")).lower() == norm:
                out.append(w)
    return out


def fire_event_id(
    *,
    thesis_id: str,
    thesis_version: int,
    tripwire_id: str,
    tripwire_version: int,
    fired_on: str,
) -> str:
    parts = "|".join(
        [thesis_id, str(thesis_version), tripwire_id, str(tripwire_version), fired_on]
    )
    digest = hashlib.sha256(parts.encode("utf-8")).hexdigest()[:32]
    return f"thesis:{digest}"


def plain_condition(window: dict) -> str:
    direction = window.get("direction", "refutes")
    register = (
        "this cuts against the read"
        if direction == "refutes"
        else "this supports the read"
    )
    claim = (window.get("claim") or "").rstrip(".")
    return f"{claim} — {register}"


def _display_for(window: dict, subject: tuple[str, str]) -> str:
    kind, norm = subject
    if kind == "ticker":
        return norm
    return window.get("cycle") or norm


def compose_payload(
    *, thesis: dict, window: dict, subject: tuple[str, str], evidence_base: str
) -> dict:
    title = (thesis.get("title") or "").strip() or "your thesis"
    condition = plain_condition(window)
    display = _display_for(window, subject)
    evidence_url = f"{evidence_base.rstrip('/')}/cycle.html"
    return {
        "subject": f"A window you were watching has closed — {display}",
        "summary_plain": (
            f"The window you were watching for “{title}” has closed: "
            f"{condition}. What to look at: {evidence_url}"
        ),
        "ticker": display,
        "condition_plain": condition,
        "evidence_url": evidence_url,
        "fired_at": window.get("fired_on"),
        "category": CATEGORY,
        "requires_tier": None,
        "source": SOURCE,
        "thesis_id": thesis.get("id"),
        "thesis_version": thesis.get("version"),
        "tripwire_id": window.get("id"),
        "tripwire_version": window.get("version"),
        "coverage": window.get("coverage", "full"),
    }


def plan_enqueue(
    *,
    theses: list[dict],
    versions: dict[str, dict],
    windows: list[dict],
    existing_fire_ids: set[str],
    evidence_base: str,
) -> MonitorPlan:
    rows: list[dict] = []
    evaluated_n = 0
    matched_n = 0
    duplicate_n = 0
    no_coverage_n = 0
    unmappable_n = 0
    notes: list[str] = []

    for thesis in theses:
        evaluated_n += 1
        subject = subject_key(thesis.get("subject_ref") or {})
        if subject is None:
            unmappable_n += 1
            notes.append(f"unmappable subject_ref for thesis {thesis.get('id')}")
            continue
        matches = match_windows(subject, windows)
        if not matches:
            no_coverage_n += 1
            notes.append(f"no tripwire coverage for thesis {thesis.get('id')}")
            continue
        thesis_id = thesis.get("id")
        current_version = thesis.get("current_version")
        version_row = versions.get(f"{thesis_id}:{current_version}")
        if version_row is None:
            unmappable_n += 1
            notes.append(f"no current version row for thesis {thesis_id}")
            continue
        content = version_row.get("content") or {}
        title = content.get("title", "")
        for window in matches:
            matched_n += 1
            fid = fire_event_id(
                thesis_id=thesis_id,
                thesis_version=current_version,
                tripwire_id=window.get("id"),
                tripwire_version=window.get("version"),
                fired_on=window.get("fired_on"),
            )
            if fid in existing_fire_ids:
                duplicate_n += 1
                continue
            thesis_for_payload = {
                "id": thesis_id,
                "version": current_version,
                "title": title,
            }
            payload = compose_payload(
                thesis=thesis_for_payload,
                window=window,
                subject=subject,
                evidence_base=evidence_base,
            )
            rows.append(
                {
                    "user_id": thesis.get("user_id"),
                    "fire_event_id": fid,
                    "channel": CHANNEL,
                    "status": "pending",
                    "attempts": 0,
                    "payload": payload,
                }
            )
            existing_fire_ids.add(fid)

    return MonitorPlan(
        rows=rows,
        evaluated_n=evaluated_n,
        matched_n=matched_n,
        duplicate_n=duplicate_n,
        no_coverage_n=no_coverage_n,
        unmappable_n=unmappable_n,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# IO functions -- isolated, monkeypatched in tests
# ---------------------------------------------------------------------------

def _pg(method: str, path: str, body: Any = None, prefer: str | None = None, timeout: int = 6):
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def typed_get(path: str) -> TypedRead:
    if not SUPABASE_SERVICE_ROLE_KEY:
        return TypedRead(READ_UNAVAILABLE, None, "no_credentials")
    try:
        rows = _pg("GET", path)
        rows = rows if rows is not None else []
        if not rows:
            return TypedRead(READ_OK_ZERO, [])
        return TypedRead(READ_OK, rows)
    except urllib.error.HTTPError as exc:
        code = getattr(exc, "code", None)
        body = ""
        try:
            body = exc.read().decode("utf-8", "ignore")
        except Exception:
            pass
        if code == 404 or "42P01" in body or "PGRST205" in body:
            return TypedRead(READ_UNAVAILABLE, None, "table_absent")
        return TypedRead(READ_UNAVAILABLE, None, f"http_{code}")
    except Exception:
        return TypedRead(READ_UNAVAILABLE, None, "unknown")


def read_active_theses(limit: int) -> TypedRead:
    path = (
        "theses?lifecycle_state=eq.active&select=id,user_id,current_version,subject_ref"
        f"&order=updated_at.desc&limit={limit}"
    )
    return typed_get(path)


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def read_current_versions(pairs: list[tuple[str, int]]) -> TypedRead:
    if not pairs:
        return TypedRead(READ_OK_ZERO, [])
    all_rows: list[dict] = []
    for chunk in _chunks(pairs, 50):
        ors = ",".join(f"and(thesis_id.eq.{tid},version.eq.{v})" for tid, v in chunk)
        path = f"thesis_versions?or=({ors})&select=thesis_id,user_id,version,content"
        result = typed_get(path)
        if result.state == READ_UNAVAILABLE:
            return result
        all_rows.extend(result.rows or [])
    return TypedRead(READ_OK if all_rows else READ_OK_ZERO, all_rows)


def read_existing_fire_ids(ids: list[str]) -> TypedRead:
    if not ids:
        return TypedRead(READ_OK_ZERO, [])
    all_rows: list[dict] = []
    for chunk in _chunks(ids, 100):
        in_list = ",".join(chunk)
        path = f"alert_outbox?fire_event_id=in.({in_list})&select=fire_event_id"
        result = typed_get(path)
        if result.state == READ_UNAVAILABLE:
            return result
        all_rows.extend(result.rows or [])
    return TypedRead(READ_OK if all_rows else READ_OK_ZERO, all_rows)


def enqueue(rows: list[dict], *, dry_run: bool) -> tuple[int, int, str | None]:
    enqueued = 0
    duplicates = 0
    if dry_run:
        return (0, 0, None)
    for row in rows:
        try:
            _pg("POST", "alert_outbox", body=row, prefer="return=minimal")
            enqueued += 1
        except urllib.error.HTTPError as exc:
            code = getattr(exc, "code", None)
            body = ""
            try:
                body = exc.read().decode("utf-8", "ignore")
            except Exception:
                pass
            if code == 409 or "23505" in body:
                duplicates += 1
                continue
            if code == 400 or "23502" in body:
                return (enqueued, duplicates, "schema_mismatch")
            return (enqueued, duplicates, f"http_{code}")
    return (enqueued, duplicates, None)


def run(
    *, now_utc=None, limit: int = 500, dry_run: bool = True, evidence_base: str = EVIDENCE_BASE
) -> MonitorResult:
    run_id = hashlib.sha256(f"{now_utc}|{limit}".encode("utf-8")).hexdigest()[:12]

    entries, latch_state = load_tripwire_view()
    windows = fired_windows(entries, latch_state)

    theses_read = read_active_theses(limit)
    if theses_read.state == READ_UNAVAILABLE:
        return MonitorResult(
            outcome="unavailable",
            read_state=theses_read.state,
            error_class=theses_read.error_class,
            evaluated_n=0,
            matched_n=0,
            enqueued_n=0,
            duplicate_n=0,
            no_coverage_n=0,
            unmappable_n=0,
            run_id=run_id,
        )
    theses = theses_read.rows or []

    pairs = [(t.get("id"), t.get("current_version")) for t in theses]
    versions_read = read_current_versions(pairs)
    if versions_read.state == READ_UNAVAILABLE:
        return MonitorResult(
            outcome="unavailable",
            read_state=versions_read.state,
            error_class=versions_read.error_class,
            evaluated_n=len(theses),
            matched_n=0,
            enqueued_n=0,
            duplicate_n=0,
            no_coverage_n=0,
            unmappable_n=0,
            run_id=run_id,
        )
    versions = {
        f"{v.get('thesis_id')}:{v.get('version')}": v for v in (versions_read.rows or [])
    }

    plan = plan_enqueue(
        theses=theses,
        versions=versions,
        windows=windows,
        existing_fire_ids=set(),
        evidence_base=evidence_base,
    )

    candidate_ids = [r["fire_event_id"] for r in plan.rows]
    existing_read = read_existing_fire_ids(candidate_ids)
    if existing_read.state == READ_UNAVAILABLE:
        return MonitorResult(
            outcome="unavailable",
            read_state=existing_read.state,
            error_class=existing_read.error_class,
            evaluated_n=plan.evaluated_n,
            matched_n=plan.matched_n,
            enqueued_n=0,
            duplicate_n=0,
            no_coverage_n=plan.no_coverage_n,
            unmappable_n=plan.unmappable_n,
            run_id=run_id,
        )
    existing_ids = {r["fire_event_id"] for r in (existing_read.rows or [])}
    to_send = [r for r in plan.rows if r["fire_event_id"] not in existing_ids]
    duplicate_n = plan.duplicate_n + (len(plan.rows) - len(to_send))

    enqueued_n, more_dupes, error_class = enqueue(to_send, dry_run=dry_run)
    duplicate_n += more_dupes

    if error_class is not None:
        return MonitorResult(
            outcome="unavailable",
            read_state=READ_UNAVAILABLE,
            error_class=error_class,
            evaluated_n=plan.evaluated_n,
            matched_n=plan.matched_n,
            enqueued_n=enqueued_n,
            duplicate_n=duplicate_n,
            no_coverage_n=plan.no_coverage_n,
            unmappable_n=plan.unmappable_n,
            run_id=run_id,
        )

    outcome = "ok" if (to_send or plan.rows) else ("no_coverage" if plan.no_coverage_n else "ok")
    return MonitorResult(
        outcome=outcome,
        read_state=READ_OK,
        error_class=None,
        evaluated_n=plan.evaluated_n,
        matched_n=plan.matched_n,
        enqueued_n=enqueued_n if not dry_run else len(to_send),
        duplicate_n=duplicate_n,
        no_coverage_n=plan.no_coverage_n,
        unmappable_n=plan.unmappable_n,
        run_id=run_id,
    )
