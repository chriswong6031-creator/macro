"""Thesis condition monitor (F11 packet B-F11-1).

Pure projection over the EXISTING tripwire latch machine
(engine/falsifier_tripwires.py) -- no new analysis lifecycle, no scoring, no send.

Provenance of the two committed files this module reads (round-3 review MINOR-2:
the prior docstring wrongly claimed BOTH files are render-produced -- measured
against the actual code, only one is):
  - data/cycle_ontology/falsifiers.json is AUTHORED input -- "the compiled DSL
    registry" itself (engine/falsifier_tripwires.py:5). It is NOT produced by
    this repo's render lane; it is read by it.
  - data/cycle_ontology/tripwire_state.json IS produced by the render lane: it
    is the persisted latch state written by
    `falsifier_tripwires.evaluate_and_persist()`, called from
    `.github/workflows/render.yml:946` -> `scripts/build_cycle.py:311-321`.
This module joins both to active Supabase Thesis Objects BY SUBJECT, and enqueues one
public.alert_outbox row per not-yet-notified FIRED window. Delivery belongs to F08
(scripts/drain_alert_outbox.py). Notification latency is <= one nightly cycle after the
render that latched the fire. human_research_only: informational; no trading authority,
no sizing, no position advice.

Schema note (verified against the actual reviewed migration, `gh pr diff 502 -R
mastermindx-market-intelligence/mastermind-terminal -- supabase`, 2026-09-06): the
merged/reviewed schema defines exactly two tables, `public.theses` (the head/subscription
row -- an active thesis IS the user's standing "watch") and `public.thesis_versions`
(the immutable revision ledger, `transition`/`previous_version`, no `amended_from`
field). There is no separate `thesis_conditions` table anywhere in that migration or in
mastermind-terminal's merged `supabase/migrations/` (`gh api .../contents/supabase/migrations`
lists only 0001-0010; a code search for `thesis_conditions` in that repo returns zero
hits). A subscription's "condition version" IS `theses.current_version` /
`thesis_versions.version` -- there is no second, more-granular version to key off. This
module therefore keys `fire_event_id` off the tripwire's own identity ONLY
(META-CEO RULING B-F11-1 round-3 blocker 3) -- `thesis_version`/`current_version` is
carried on the payload for DISPLAY only and is never hashed. If a later migration adds
a genuine `thesis_conditions` table this module must be revisited; until then treating
one as existing would be inventing schema, not implementing spec.

condition_plain vs engine_window_plain (META-CEO RULING B-F11-1 round-3 blocker 1):
condition_plain is the USER's OWN falsifier text(s), read verbatim from
`thesis_versions.content.falsifiers` -- never the engine's tripwire `claim`. The
engine's own claim about the cycle is carried SEPARATELY as `engine_window_plain`
(Tier-2 detail only; may contain stats/abbreviations the glance-tier text may not).
Presenting the engine's claim as though it were the user's own condition puts words
in the user's mouth and was BLOCKER 1 of the round-2 review.

alert_outbox row shape (META-CEO RULING M1): the enqueued row's columns match
`public.alert_outbox` byte-for-byte per terminal PR #513's migration
`supabase/migrations/0013_alert_runs_outbox.sql` (id, user_id, alert_id,
fire_event_id, channel, status, payload, attempts, last_error, deliver_after,
delivered_at, created_at -- this module supplies user_id/alert_id/fire_event_id/
channel/status/payload/attempts and leaves the rest to column defaults). `alert_id`
is typed `uuid` in that migration and there is no real per-position Alerts-table row
backing a thesis-condition fire, so the conceptual synthetic identity
"thesis:<thesis_id>" (one alert_id per thesis, stable across every fire it produces)
is rendered through `uuid5` rather than stored as the literal string, which the
`uuid` column would reject -- see `synthetic_alert_id()`.

Glance-tier subject display (META-CEO RULING M3, round-3 review BLOCKER 1): the
committed falsifiers.json corpus carries no human `label` field on any entry
today. Title-casing the raw internal cycle slug (e.g. 'spx' -> 'Spx', 'pgms' ->
'Pgms', 'em-equities' -> 'Em Equities') is NOT a genuine plain-language label --
it is still the internal slug/abbreviation, merely reformatted, and is exactly
the class of untranslated engine jargon the plain-language law bans from the
glance tier. `_glance_subject()` therefore uses a window's `label` field only
when the corpus actually supplies one; a TICKER symbol (a real, universally-
shown market identifier) is always safe and is used directly; a CYCLE-scope
window with no `label` falls back to a fully-translated generic sentence that
never names the cycle at all, in both EN and ZH.

Disclosure (META-CEO RULING M1): terminal's alerts_engine.py guards its own
per-position fires with a "guarded one-shot disarm" PATCH against the fired alert
row (Freeze `research/MARKET_ONTOLOGY_F08_ARCHITECTURE_FREEZE_2026-09-05.md:60`).
That mechanism does NOT apply here. This module's fires are re-derived from the
committed tripwire latch state on every nightly run, and the ONLY dedup guard is
(a) the deterministic `fire_event_id`, (b) a pre-insert SELECT against
`alert_outbox` for ids already present, and (c) `alert_outbox`'s own unique index
on `fire_event_id` as the backstop enforcement point. There is no local disarm
state and none is added here (F11's `do_not_redo` forbids a second local
canonical-fact/idempotency store). Consequently, IF an operator or a future
migration ever purges/archives old `alert_outbox` rows, a tripwire whose latch
is still FIRED could be re-notified on the next run that no longer finds its old
row -- this is an F08-owned retention-policy question, not something this module
can close from its own owned files, and is deliberately disclosed here rather
than silently assumed away.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
import urllib.error
import uuid as _uuid_mod
from dataclasses import dataclass, field
from datetime import datetime, timezone
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

# Words banned from every GLANCE-TIER user-facing string this module emits (house
# law, CLAUDE.md ruling #3821): falsifier/refutation language is never front-facing.
# Tier-2 fields (engine_window_plain*) are explicit raw-detail passthrough and are
# NOT subject to this ban -- see the module docstring.
_BANNED_TERMS = ("falsif", "refut", "证伪")

# A fixed, arbitrary namespace UUID for synthesizing alert_outbox.alert_id values
# (uuid5) from the conceptual "thesis:<thesis_id>" identity documented above. Never
# change this constant -- doing so would re-mint every thesis's synthetic alert_id.
_ALERT_ID_NAMESPACE = _uuid_mod.UUID("6f1e6cf4-6e9b-5f2a-9d0a-6d0f6a5b6c00")

# A ZH sentence must never leave the user-authored parts of a message untranslated
# without saying so (META-CEO RULING MINOR-2: "fallback to EN with a 'translation
# pending' marker rather than a ZH subject with an EN body"). The user's own
# falsifier text has no ZH counterpart in the thesis schema, so any ZH sentence
# that quotes it verbatim carries this marker.
TRANSLATION_PENDING_ZH_MARKER = "（翻译待补）"


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
    stale_n: int = 0
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
    planned_n: int = 0
    # A window that fired BEFORE the thesis existed is pre-existing history,
    # not a new transition (_not_stale), and is suppressed from enqueue --
    # but a run that suppressed N such windows must not be byte-identical in
    # its log line to a run that saw nothing at all (round-3 review MINOR-1:
    # MonitorPlan.stale_n was computed then silently discarded).
    stale_n: int = 0


# ---------------------------------------------------------------------------
# Pure functions -- no IO
# ---------------------------------------------------------------------------

def subject_key(subject_ref: dict) -> tuple[str, str] | None:
    """Resolve a thesis subject_ref to a ('ticker'|'cycle', normalized) tuple.

    kind/owner vocabulary verified against the reviewed migration's
    `theses_set_subject_ref` guard: kind in ('issuer','theme'); owner in
    ('data_os.security_master','terminal.analysis_symbol','macro.theme_registry');
    owner='macro.theme_registry' <=> kind='theme'; the other two owners <=> kind='issuer'.
    """
    if not isinstance(subject_ref, dict):
        return None
    kind = subject_ref.get("kind")
    owner = subject_ref.get("owner")
    key = subject_ref.get("key")
    if kind == "issuer" and owner in ("data_os.security_master", "terminal.analysis_symbol"):
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


def load_tripwire_view() -> tuple[list[dict], dict, str | None]:
    """Read the committed falsifiers + latch state. NEVER recomputes them.

    Returns (entries, state, error_class). error_class is None for the normal
    "file absent" state (nothing has rendered yet -- a legitimate READ_OK_ZERO,
    not an error) and is a typed string when a file EXISTS but cannot be parsed
    -- an unknown latch state must never render identically to an empty one.
    """
    root = config.ROOT
    f_path = root / ft._FALSIFIERS_JSON
    s_path = root / ft._STATE_JSON
    entries: list[dict] = []
    state: dict = {}
    if f_path.exists():
        try:
            data = json.loads(f_path.read_text())
            entries = data if isinstance(data, list) else data.get("falsifiers", [])
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return [], {}, "corrupt_falsifiers_json"
    if s_path.exists():
        try:
            state = json.loads(s_path.read_text())
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return [], {}, "corrupt_tripwire_state_json"
    return entries, state, None


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
                "claim_zh": e.get("claim_zh", ""),
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


def _not_stale(window: dict, thesis_created_at: str | None) -> bool:
    """A window fired before the thesis existed is not a transition 'since the
    last run' for that subscription -- it is pre-existing history. Enabling this
    monitor for the first time must not backfire every historically latched
    window at every currently-active thesis. Comparison is lexical ISO-8601,
    which sorts correctly for both date-only and full-timestamp strings. When
    the thesis has no recorded creation time (should not happen for a real row
    selected with `created_at` in the query, but defensive for callers that
    omit it) the window is not filtered -- an unknown recency is disclosed via
    the existing no_coverage/duplicate accounting, never silently dropped.
    """
    if not thesis_created_at:
        return True
    fired_on = window.get("fired_on") or ""
    return fired_on >= thesis_created_at[:10]


def fire_event_id(
    *,
    thesis_id: str,
    tripwire_id: str,
    tripwire_version: int,
    fired_on: str,
    thesis_version: int | None = None,
) -> str:
    """Deterministic id for one (thesis, tripwire-transition) fire.

    META-CEO RULING (B-F11-1 round-3 blocker 3): `thesis_version` is DISPLAY
    ONLY and is accepted here purely so callers can log/carry it alongside the
    id -- it is NEVER part of the digest. A thesis amendment (which bumps
    `current_version`) must not mint a new id for an already-notified
    (tripwire_id, tripwire_version, fired_on) transition, or a sticky/already-
    FIRED window would re-notify on every edit to the thesis.
    """
    parts = "|".join([thesis_id, tripwire_id, str(tripwire_version), fired_on])
    digest = hashlib.sha256(parts.encode("utf-8")).hexdigest()[:32]
    return f"thesis:{digest}"


def synthetic_alert_id(thesis_id: str) -> str:
    """Deterministic per-thesis synthetic `alert_outbox.alert_id` (uuid5 of the
    conceptual "thesis:<thesis_id>" identity -- META-CEO RULING M1). Stable
    across every fire produced for the same thesis; NOT a foreign key into any
    real Alerts-table row (none exists for a thesis-condition fire)."""
    return str(_uuid_mod.uuid5(_ALERT_ID_NAMESPACE, f"thesis:{thesis_id}"))


def user_condition_text(falsifiers: Any) -> str:
    """The user's OWN condition text(s), byte-verbatim from
    `thesis_versions.content.falsifiers` -- no rstrip/lstrip/normalization of
    any kind (META-CEO RULING MINOR-1). Multiple falsifiers are joined with
    '; ' BETWEEN the verbatim strings; a single falsifier is returned exactly
    as authored, with no separator applied. Never derived from the engine's
    tripwire `claim` -- see `engine_window_plain` and the module docstring."""
    if not falsifiers:
        return ""
    if isinstance(falsifiers, str):
        falsifiers = [falsifiers]
    return "; ".join(str(f) for f in falsifiers if f)


def _glance_subject(window: dict, subject: tuple[str, str]) -> str | None:
    """The safe glance-tier subject label, or None when no safe label exists.

    META-CEO RULING M3 else-branch (round-3 review BLOCKER 1): a humanized/
    title-cased form of the raw internal cycle slug ('long_bonds' ->
    'Long Bonds') is STILL the internal slug -- it is not a genuine plain-
    language label just because the underscores were swapped for spaces and
    the words capitalized. The real committed corpus carries no `label` field
    today, so every cycle-scope window falls through to None (caller uses the
    generic fallback sentence). A TICKER symbol is a real, universally-shown
    market identifier (not an internal abbreviation) and is always safe to
    use directly. A future corpus `label` field wins over both when present.
    """
    label = window.get("label")
    if label:
        return str(label).strip()
    kind, norm = subject
    if kind == "ticker":
        return norm
    return None


def _close_sentence(text: str) -> str:
    """Append a terminal period only when `text` doesn't already end with one
    (round-3 review MINOR-4): the user's byte-verbatim condition text may
    already end in '.'/'!'/'?', and blindly appending another produced a
    double period ('...decisively..') in the composed glance sentence. This
    never mutates the stored `condition_plain` field itself -- only the
    derived summary sentence's closing punctuation."""
    if text and text[-1] in ".!?":
        return text
    return f"{text}."


def compose_payload(
    *, thesis: dict, window: dict, subject: tuple[str, str], evidence_base: str
) -> dict:
    """Compose the alert_outbox payload.

    condition_plain / condition_plain_zh are the USER's own falsifier text
    (verbatim, byte-for-byte). engine_window_plain / engine_window_plain_zh are
    the ENGINE's tripwire claim, carried as a SEPARATE Tier-2 detail field --
    never glued into the glance-tier summary/condition (META-CEO RULING
    B-F11-1 round-3 blocker 1).
    """
    title = (thesis.get("title") or "").strip() or "your thesis"
    condition = user_condition_text(thesis.get("falsifiers"))
    has_condition = bool(condition)
    display = _glance_subject(window, subject)
    kind, _norm = subject
    evidence_url = f"{evidence_base.rstrip('/')}/cycle.html"
    engine_window_plain = window.get("claim", "") or ""
    engine_window_plain_zh = window.get("claim_zh", "") or ""

    if display:
        subject_line = f"A window we watch for {display} has closed"
        subject_line_zh = f"你关注的“{display}”窗口已关闭"
        closed_prefix = f"A window we watch for {display} has closed."
        closed_prefix_zh = f"你关注的“{display}”窗口已关闭。"
    else:
        # META-CEO RULING M3 else-branch: no safe human label exists for this
        # window's subject (a cycle-scope window without a corpus `label`) --
        # fall back to a fully-translated generic sentence that never names
        # the raw/humanized internal slug, in either language.
        subject_line = "A market condition we watch for your thesis has changed"
        subject_line_zh = "你关注的一项市场条件已发生变化"
        closed_prefix = "A market condition we watch for your thesis has changed."
        closed_prefix_zh = "你关注的一项市场条件已发生变化。"

    if has_condition:
        summary_plain = (
            f'{closed_prefix} Your thesis "{title}" lists: {_close_sentence(condition)}'
        )
        summary_plain_zh = (
            f"{closed_prefix_zh}你的论点《{title}》列出的条件："
            f"{condition}{TRANSLATION_PENDING_ZH_MARKER}"
        )
        condition_plain_zh = f"{condition}{TRANSLATION_PENDING_ZH_MARKER}"
    else:
        summary_plain = f"{closed_prefix} Your thesis lists no conditions yet."
        summary_plain_zh = f"{closed_prefix_zh}你的论点尚未列出任何条件。"
        condition_plain_zh = ""

    return {
        "subject": subject_line,
        "subject_zh": subject_line_zh,
        "summary_plain": summary_plain,
        "summary_plain_zh": summary_plain_zh,
        # Only a ticker subject is a real ticker; a cycle subject's display
        # label is descriptive text, not a tradable symbol.
        "ticker": display if kind == "ticker" else None,
        "condition_plain": condition,
        "condition_plain_zh": condition_plain_zh,
        # Tier-2 detail only -- may contain the engine's own stats/abbreviations
        # (e.g. "SOX ~14,655"); never surfaced in the glance-tier fields above.
        "engine_window_plain": engine_window_plain,
        "engine_window_plain_zh": engine_window_plain_zh,
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
    stale_n = 0
    notes: list[str] = []

    for thesis in theses:
        evaluated_n += 1
        subject = subject_key(thesis.get("subject_ref") or {})
        if subject is None:
            unmappable_n += 1
            notes.append(f"unmappable subject_ref for thesis {thesis.get('id')}")
            continue
        all_matches = match_windows(subject, windows)
        created_at = thesis.get("created_at")
        matches = [w for w in all_matches if _not_stale(w, created_at)]
        if not all_matches:
            no_coverage_n += 1
            notes.append(f"no tripwire coverage for thesis {thesis.get('id')}")
            continue
        if not matches:
            stale_n += 1
            notes.append(
                f"tripwire fired before thesis {thesis.get('id')} was created — not a new transition"
            )
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
        falsifiers = content.get("falsifiers") or []
        for window in matches:
            matched_n += 1
            fid = fire_event_id(
                thesis_id=thesis_id,
                tripwire_id=window.get("id"),
                tripwire_version=window.get("version"),
                fired_on=window.get("fired_on"),
                thesis_version=current_version,
            )
            if fid in existing_fire_ids:
                duplicate_n += 1
                continue
            thesis_for_payload = {
                "id": thesis_id,
                "version": current_version,
                "title": title,
                "falsifiers": falsifiers,
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
                    "alert_id": synthetic_alert_id(thesis_id),
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
        stale_n=stale_n,
        notes=notes,
    )


def _classify_outcome(plan: MonitorPlan) -> tuple[str, str]:
    """(outcome, read_state) for a plan whose reads all succeeded. READ_NO_COVERAGE
    (META-CEO RULING MINOR-4) is used, not left dead, exactly when EVERY evaluated
    thesis had zero tripwire coverage at all -- a real, disclosed state distinct
    from a normal empty-but-covered run."""
    if plan.evaluated_n > 0 and plan.no_coverage_n == plan.evaluated_n:
        return "no_coverage", READ_NO_COVERAGE
    return "ok", READ_OK


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
        "theses?lifecycle_state=eq.active&select=id,user_id,current_version,subject_ref,created_at"
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


def _now_utc_iso() -> str:
    """Real wall-clock UTC timestamp. A thin, monkeypatchable seam so run_id can
    be tested deterministically without ever defaulting to a constant across
    nightly runs (META-CEO RULING MINOR-5)."""
    return datetime.now(timezone.utc).isoformat()


def run(
    *, now_utc=None, limit: int = 500, dry_run: bool = True, evidence_base: str = EVIDENCE_BASE
) -> MonitorResult:
    if now_utc is None:
        now_utc = _now_utc_iso()
    run_id = hashlib.sha256(f"{now_utc}|{limit}".encode("utf-8")).hexdigest()[:12]

    entries, latch_state, tripwire_error = load_tripwire_view()
    if tripwire_error is not None:
        return MonitorResult(
            outcome="unavailable",
            read_state=READ_UNAVAILABLE,
            error_class=tripwire_error,
            evaluated_n=0,
            matched_n=0,
            enqueued_n=0,
            duplicate_n=0,
            no_coverage_n=0,
            unmappable_n=0,
            run_id=run_id,
        )
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
            stale_n=plan.stale_n,
            run_id=run_id,
        )
    existing_ids = {r["fire_event_id"] for r in (existing_read.rows or [])}
    to_send = [r for r in plan.rows if r["fire_event_id"] not in existing_ids]
    duplicate_n = plan.duplicate_n + (len(plan.rows) - len(to_send))

    if dry_run:
        # Dormant/preview path: no write is attempted. enqueued_n reports what
        # ACTUALLY got written (always 0 here); planned_n reports what a live
        # run would attempt, so callers can log the two without conflating them.
        outcome, read_state = _classify_outcome(plan)
        return MonitorResult(
            outcome=outcome,
            read_state=read_state,
            error_class=None,
            evaluated_n=plan.evaluated_n,
            matched_n=plan.matched_n,
            enqueued_n=0,
            duplicate_n=duplicate_n,
            no_coverage_n=plan.no_coverage_n,
            unmappable_n=plan.unmappable_n,
            stale_n=plan.stale_n,
            run_id=run_id,
            planned_n=len(to_send),
        )

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
            stale_n=plan.stale_n,
            run_id=run_id,
        )

    outcome, read_state = _classify_outcome(plan)
    return MonitorResult(
        outcome=outcome,
        read_state=read_state,
        error_class=None,
        evaluated_n=plan.evaluated_n,
        matched_n=plan.matched_n,
        enqueued_n=enqueued_n,
        duplicate_n=duplicate_n,
        no_coverage_n=plan.no_coverage_n,
        unmappable_n=plan.unmappable_n,
        stale_n=plan.stale_n,
        run_id=run_id,
        planned_n=len(to_send),
    )
