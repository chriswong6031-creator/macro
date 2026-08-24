"""engine/cycle_pattern/imce_prospective.py — IMCE A5B registered prospective forward capture.

Append-only, decision-time observation ledger for the registered
``rf.cycle_pattern.imce_phase_v0`` / ``imce_sync_v0`` trial families
(registered_contract_hash ``05b43f9119fd1fd357d3994bd652abbc3cdff3d8``, A4
registration, PR #6244). After activation, a qualifying DHI/PHM/KBH/TOL
earnings event produces ONE immutable decision-time packet capturing:

  * ``M_t`` — the ``order_softness`` mechanism-local state, constructed
    EXACTLY per ``research/imce/IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md``
    (sign-only per-issuer lookup table §2, >=2-contributor pooling floor §3.1,
    4/4->cohort / 2-3->named_subset / <2->NOT_RECONSTRUCTABLE label rule —
    this arithmetic is UNCHANGED by the red-team fixes below; only per-issuer
    CONTRIBUTOR ELIGIBILITY gates upstream of it gained two new checks).
  * ``R_t`` — a PIT-safe price-technical leg (MACD histogram classic
    12/26/9 over the biweekly close series), frozen at the event's own
    decision cutoff, never at nightly build time.
  * ``C_t`` — rights-safe owner-source macro context (Treasury CMT under
    GO_LIMITED; PMMS/FRED/ALFRED/NAR are held/excluded, never persisted).

THIS DATASET IS NOT CANONICAL EVENT/DOCUMENT/ACCOUNTING TRUTH. It is the
registered experiment's own DERIVED evidence store — a bounded, dataset-local
ledger, not a new generic forward-log or trial-ledger primitive. It contains
ZERO outcome fields (no forward return, drawdown, Brier, hit-rate, or
p-value of any kind) — this module can only ever compute decision-time
state, never a graded result. Authority is context_only everywhere; nothing
here ranks, sizes, gates, or feeds Prophet/Radar/screener/recommendation.

Primitive-inspection verdict (re-derived, not merely restated, from reading
each module's own docstring/keying logic before writing this one):

  * ``engine/cycle_forward_log.py`` — keep-FIRST per ``(date, id)``. Wrong
    keying for a per-event, per-decision-cutoff observation ledger (a single
    calendar date can carry more than one issuer's decision cutoff, and this
    dataset's identity is event-keyed, not date-keyed) — NOT reused.
  * ``engine/trial_ledger.py`` — a multiple-testing REGISTRATION registry
    (dedup-by-config-hash trial count for the Deflated Sharpe gate), not an
    observation ledger of any kind — NOT reused.
  * ``engine/neuralweb/market_memory_forward_store.py`` — explicitly a
    "temp-only immutable ledger for SYNTHETIC Market Memory forward
    contracts" with "no default root, environment-variable lookup, command
    line, scheduler, service, API, or production call site" — excluded by
    its own docstring from any production use — NOT reused.

Row kinds (append-only JSONL, one JSON object per line, never rewritten):

  * ``activation``  — exactly one row; stamps ``activation_started_at`` the
    first time a production nightly run succeeds; idempotent (never
    re-stamped on a later run).
  * ``observation``  — at most ONE immutable decision-time packet per
    ``event_id``, EVER (red-team M4 fix — see append_observation). First
    observation wins; an exact-duplicate rerun (same event_id AND same
    decision_cutoff) is a no-op. A second attempt at the SAME event_id with
    a DIFFERENT decision_cutoff (e.g. an 8-K/A source correction) is
    REFUSED by append_observation — it must route through append_correction.
    A FIRST-EVER attempt whose triggering workspace is itself a correction
    (or an unrecognized lifecycle state, or a non-"8-K" SEC form) is also
    REFUSED, log-only, with NO row of any kind appended (A5C safety law —
    see ``SAFE_ORIGINAL_LIFECYCLE_STATES`` / ``is_safe_original_source_form``
    / ``append_observation``'s ``trigger_lifecycle_state`` and
    ``trigger_source_form`` parameters below).
  * ``correction``   — a linked supersession record referencing the
    superseded ``observation_id`` when a source correction (a new workspace
    revision for the same event) is observed. The original packet is NEVER
    rewritten.

Activation law (strict reading, frozen by the commissioning directive): no
source event whose ``source_available_at`` predates ``activation_started_at``
may enter the prospective cohort. This binds CONTRIBUTING issuer states too,
not only the triggering event — a pre-activation snapshot may never supply a
pooled-cohort contributor state; it is recorded as a typed absence
(``activation_law: "pre_activation_excluded"``) instead. Enforced at BOTH
layers: the builder script fences the trigger before it ever calls into this
module, AND (red-team M7 fix) ``append_observation`` itself refuses any
packet whose ``decision_cutoff`` predates the ledger's own activation row,
independent of caller discipline.

A5C safety law (Sol A5C review, 2026-08-23, item 1): "no correction to a
pre-activation event can ever enter the prospective cohort as a new
observation." Until canonical source-revision history exists, a first-ever
write for an ``event_id`` whose triggering workspace is a CORRECTION (or
carries an unrecognized/future lifecycle state, or a non-"8-K" SEC form —
see ``SAFE_ORIGINAL_LIFECYCLE_STATES`` / ``is_safe_original_source_form``
below) is REFUSED rather than minted: activation may exist and other
candidates proceed normally, but this one event_id gets no observation row
until a genuinely safe-original revision (or the future manifest/history-
chain eligibility path) is seen. The refusal is log-only (a bare
``::warning`` line reporting what was SEEN, never a guessed diagnosis) — it
never writes a row of any kind, never stamps/unstamps activation, and is
naturally idempotent (nothing was written, so nothing needs to be undone).
Two independent signals are checked (Opus red-team BLOCKER-1 hardening,
2026-08-23): lifecycle.state alone only fires when a PRIOR published
workspace exists to compare against — closed for OUR OWN sha-tracked
corrections by making the "corrected" state STICKY across an unchanged-
source republish (engine/company_intelligence/event_workspace_build.py's
``prior_lifecycle_state`` parameter), but a replacement 8-K/A whose
original was never published at all still presents as a first-ever
"complete" state either way; the SEC's own issuer_release source-row
``form`` closes part of that residual gap for free (an "8-K/A" is visible
from the FIRST observed revision, prior workspace or not). The remaining
gap (a NON-amendment replacement 8-K whose original was never published)
is a NAMED residual, closed only by the future manifest/history chain. See
``append_observation``'s ``trigger_lifecycle_state``/``trigger_source_form``
parameters for the enforcement itself.

Two additional per-issuer contributor-eligibility gates (red-team M5/MIN9,
layered UPSTREAM of the verbatim §2/§3.1 math, which is otherwise untouched):

  * Calendar-quarter pooling-key alignment — a contributor snapshot is
    eligible only if its own fiscal-quarter-end maps, under the FROZEN
    majority-month pooling key (``research/imce/
    IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md`` §4b, "Pooling key (NEW) =
    calendar quarter by majority-month" — verified zero-collision across all
    six roster issuers), to the SAME (calendar_year, calendar_quarter) as the
    triggering event. A misaligned (stale) snapshot is
    ``activation_law: "stale_snapshot_outside_aligned_quarter"``.
  * Denominator-convention conformance — the captured
    ``fact_cancellation_rate_denominator`` text is checked against the
    construction doc's §1 frozen per-issuer canonical denominator keywords;
    a mismatch is ``activation_law: "denominator_convention_mismatch"``.

Reconstruction/production mode (red-team M7 fix, hardened): every write
function takes both ``reconstruction`` and ``production`` flags.
``reconstruction=True`` writes an explicit non-default path and can NEVER
touch the production path. ``reconstruction=False`` (the default) additionally
REQUIRES ``production=True`` or the write is refused outright — a bare,
flagless call can never mutate the production ledger even by accident; the
nightly builder is the only caller that passes ``production=True``, gated by
its own ``--production`` CLI flag.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Identity / schema constants
# ---------------------------------------------------------------------------

SCHEMA = "imce.prospective_observation.v1"
REGISTERED_CONTRACT_HASH = "05b43f9119fd1fd357d3994bd652abbc3cdff3d8"
CONSTRUCTION_DOC = "research/imce/IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md"
POOLING_KEY_DOC = "research/imce/IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md"

#: Prospective nominal pooled roster — the PROSPECTIVE arm retains the genuine
#: four-issuer cohort basis (construction doc §1a/§3.1); LEN is excluded
#: (no cancellation denominator, ever) and NVR is held out as its own
#: stratum, never pooled (contract §2 NVR bullet, AG13) — unchanged by A5B.
ROSTER: tuple[str, ...] = ("DHI", "PHM", "KBH", "TOL")

ROW_KIND_ACTIVATION = "activation"
ROW_KIND_OBSERVATION = "observation"
ROW_KIND_CORRECTION = "correction"
ROW_KINDS = frozenset({ROW_KIND_ACTIVATION, ROW_KIND_OBSERVATION, ROW_KIND_CORRECTION})

# ---------------------------------------------------------------------------
# A5C safety law (Sol A5C review, 2026-08-23, item 1) — fail-closed
# correction detection pending canonical source-revision history.
#
# "Until canonical source-revision history is available, A5B must fail
# closed rather than mint an observation from a corrected workspace when no
# prior observation exists. Activation may exist; unsafe observation
# creation may not." — Sol, A5C item 1.
#
# The published ``event_workspace.v1`` carries only a SINGLE current
# ``lifecycle.state`` (engine/company_intelligence/event_workspace.py
# ``_lifecycle_payload`` -> ``CompanyEvent.state``) — there is no
# revision-number or amends-generation field in the current contract. The
# only production writer of that field, ``build_event_workspace``
# (engine/company_intelligence/event_workspace_build.py:169-196), walks
# started -> complete, and ADDITIONALLY -> corrected only when
# ``prior_source_sha256`` differs from the newly bound exhibit hash.
# "complete" is therefore the ONLY published state this repo's real builder
# ever emits WITHOUT having applied a "corrected" transition.
#
# Every other value is treated as unsafe, INCLUDING states this module has
# never seen a production writer emit: engine/company_intelligence/events.py
# ``_TRANSITIONS`` lets "corrected" advance to "derived_ready" / "superseded"
# / itself, so a state reached further down that graph cannot be trusted as
# "never corrected" merely because its CURRENT state string is no longer
# literally "corrected" — the machine carries no revision counter to prove
# it. Fail-closed: only a state explicitly enumerated below is safe-original;
# "corrected" and any unknown/future state are unsafe.
SAFE_ORIGINAL_LIFECYCLE_STATES: frozenset[str] = frozenset({"complete"})


def is_safe_original_lifecycle_state(state: object) -> bool:
    """True only for a lifecycle state KNOWN to be reachable without ever
    having passed through a "corrected" transition (see
    ``SAFE_ORIGINAL_LIFECYCLE_STATES`` above). ``None``, ``"corrected"``, and
    any unrecognized/future state string all return False — fail-closed by
    construction, never by an exception a caller could forget to catch."""
    return isinstance(state, str) and state in SAFE_ORIGINAL_LIFECYCLE_STATES


#: A5C BLOCKER-1 (1c) — the lifecycle-state signal alone is a NECESSARY but
#: not (until the manifest/history chain lands) SUFFICIENT safety signal:
#: the state signal is now durable within our OWN sha-comparison lineage
#: (build_event_workspace's sticky-corrected fix, engine/company_intelligence/
#: event_workspace_build.py) PROVIDED the prior-workspace READ ITSELF
#: succeeds (see refresh_event_workspaces.PriorWorkspaceFetchFailed — a
#: separate NEW-1 fix), but it only fires when a PRIOR published workspace
#: exists to compare against at all. A second, independent signal closes
#: part of that gap for free: the SEC's own form on the bound filing
#: (issuer_release source row "form") is "8-K/A" the moment EDGAR itself
#: marks a filing as an amendment — true even on the FIRST-ever observed
#: revision of an event, with no prior workspace to compare against.
#: Requiring form == "8-K" EXACTLY (not merely "not 8-K/A") is deliberately
#: the stricter reading: a missing/blank/unrecognized form is unsafe too.
#:
#: HONEST PRODUCER CLAIM (NEW-2 fix, Opus red-team round 2, 2026-08-23): an
#: earlier version of this comment claimed a missing/blank form
#: "self-heals within one 3h publish cycle once populated" — false as
#: written, because FIVE separate `or "8-K"` sites upstream of this gate
#: (engine/earnings_release/binding.py, event_workspace_build.py,
#: refresh_event_workspaces.py x3) manufactured the literal string "8-K"
#: from ANY absence, so a genuinely missing form could never actually
#: reach this function in the first place — the "self-healing" case was
#: unreachable, not handled. Fixed: the PUBLISHED issuer_release source row
#: now carries the RAW EDGAR-supplied form (event_workspace_build.py),
#: decoupled from bind_release_document's own internal "8-K" default (that
#: internal default is left alone — it exists for document-identity/
#: is_amendment purposes this function never reads). On the REAL nightly
#: path, a missing form is STILL expected unreachable: discovery
#: (refresh_event_workspaces._select_newest_results_rows) pre-filters every
#: candidate to {"8-K", "8-K/A"} before a filing is ever acquired. This
#: function's None/missing-form handling is therefore genuinely
#: reachable CODE, but consumer-side DEFENSE-IN-DEPTH in practice — not a
#: transient state the nightly path is expected to pass through.
def is_safe_original_source_form(form: object) -> bool:
    """True only when the bound filing's own SEC-assigned form is EXACTLY
    "8-K" (never "8-K/A", never missing/blank/unrecognized) — fail-closed,
    mirroring ``is_safe_original_lifecycle_state`` above. See the module
    comment above for the honest producer-defaulting claim (NEW-2 fix)."""
    return form == "8-K"


AUTHORITY = "context_only"
PROPHET_FLAGS = {
    "may_rank": False,
    "may_size": False,
    "may_gate": False,
    "prophet_authority": False,
}

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PRODUCTION_PATH = _REPO_ROOT / "data" / "cycle_pattern" / "imce_prospective_observation_v1.jsonl"

# Keys stripped from the HASHED body only (red-team M6) — wall-clock
# stamps (c_t leg observation_timestamp, r_t leg read-time vintage) must
# never make observation_id nondeterministic. The keys stay in the STORED
# packet; only compute_observation_id()'s input is stripped.
_HASH_STRIP_KEYS: frozenset[str] = frozenset({"observation_timestamp", "vintage"})

# ---------------------------------------------------------------------------
# M_t — the six frozen source facts (construction doc §1/§1b)
# ---------------------------------------------------------------------------

FACT_IDS: tuple[str, ...] = (
    "fact_net_orders_current",
    "fact_net_orders_prior_year",
    "fact_cancellation_rate_current",
    "fact_cancellation_rate_prior_year",
    "fact_cancellation_rate_denominator",
)
TOL_SENSITIVITY_FACT_ID = "fact_cancellation_rate_beginning_backlog_sensitivity"
#: IMCE A5C item 7 (TOL backlog-sensitivity prior-year extraction, PR #6307,
#: 2026-08-23): the source plane (engine/company_intelligence/issuer_profiles.py
#: _tol_extract_release_facts) NOW emits this fact_id from the exhibit's own
#: two-cell beginning-quarter-backlog row (current + prior-year), MIN8's
#: self-healing having landed — this was a REAL fact lookup even before that
#: PR (never a placeholder), so no code changed here when extraction caught
#: up; the lookup below simply started resolving instead of typed-absenting.
TOL_SENSITIVITY_PRIOR_YEAR_FACT_ID = "fact_cancellation_rate_beginning_backlog_sensitivity_prior_year"

# Sign-only per-issuer lookup table (construction doc §2) — VERBATIM,
# red-team-verified constant-exact; DO NOT MODIFY. Any combination not
# present here (either sign missing) resolves to NOT_RECONSTRUCTABLE in
# order_softness_state() below — never fitted, never a magnitude threshold.
_ORDER_SOFTNESS_TABLE: dict[tuple[str, str], str] = {
    ("+", "-"): "TIGHTENING", ("+", "0"): "TIGHTENING",
    ("-", "+"): "SOFTENING", ("-", "0"): "SOFTENING",
    ("+", "+"): "MIXED", ("-", "-"): "MIXED",
    ("0", "+"): "MIXED", ("0", "-"): "MIXED", ("0", "0"): "MIXED",
}

# Construction doc §1 frozen per-issuer canonical cancellation-rate
# denominator convention — keyword substrings expected (case-insensitive) in
# the captured fact_cancellation_rate_denominator VALUE text (MIN9
# conformance guard; never feeds the sign table itself).
_DENOMINATOR_CONFORMANCE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "DHI": ("gross orders",),
    "PHM": ("gross new orders", "gross orders"),
    "KBH": ("gross orders",),
    "TOL": ("signed contracts",),
}

# ---------------------------------------------------------------------------
# Outcome-field blacklist (frozen spec item 9, hardened per red-team B2) —
# no schema, present or future, may carry a KEY whose normalized form
# CONTAINS any of these stems anywhere (substring match on a
# separator-stripped, lowercased key — catches forward_return_63d,
# fwd_ret_21d, brier_score_90d, hit_rate_pct, p_value_two_sided, sharpe_1y,
# forwardReturn, outcome, etc., not just an exact-match token).
# ---------------------------------------------------------------------------

FORBIDDEN_OUTCOME_TOKENS: frozenset[str] = frozenset({
    "forward_return", "fwd_return", "fwd_ret", "return_fwd", "excess_return", "realized_return",
    "drawdown", "max_drawdown", "mdd", "maxdd",
    "brier", "brier_score",
    "hit_rate", "hitrate", "win_rate", "winrate",
    "p_value", "pvalue", "p_val",
    "sharpe", "sharpe_ratio", "information_ratio", "alpha",
    "outcome",
    "return",  # N1/N2 residual: catches a bare "return_63d"-shaped key too;
               # the frozen-schema WHITELIST test below is the real backstop
               # for anything this stem (or any other) still misses.
})


def _normalize_key(key: str) -> str:
    """Lowercase, separator-stripped stem form for blacklist matching —
    'forward_return_63d' and 'forwardReturn' both normalize to a form that
    contains 'forwardreturn'."""
    return "".join(ch for ch in str(key).lower() if ch.isalnum())


_FORBIDDEN_STEMS: frozenset[str] = frozenset(_normalize_key(t) for t in FORBIDDEN_OUTCOME_TOKENS)


class ProspectiveLedgerError(RuntimeError):
    """A write violated the reconstruction/production path law, the
    production-flag law, the activation law, the event-identity law, or the
    outcome-field blacklist."""


def _now_iso(now: datetime | None = None) -> str:
    dt = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value: object) -> datetime:
    """Public: parse an ISO-8601 timestamp (any offset, 'Z' or otherwise)
    into a UTC-aware datetime."""
    text = str(value or "").strip()
    if not text:
        raise ProspectiveLedgerError(f"not a timestamp: {value!r}")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Outcome-field blacklist enforcement
# ---------------------------------------------------------------------------

def _walk_forbidden(obj: Any, path: str = "$") -> str | None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if _normalize_key(k) and any(stem in _normalize_key(k) for stem in _FORBIDDEN_STEMS):
                return f"{path}.{k}"
            hit = _walk_forbidden(v, f"{path}.{k}")
            if hit:
                return hit
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            hit = _walk_forbidden(item, f"{path}[{i}]")
            if hit:
                return hit
    return None


def assert_no_outcome_fields(packet: dict) -> None:
    """Raise ProspectiveLedgerError if any forbidden outcome stem appears
    anywhere in *packet* (recursively, normalized key-name match)."""
    hit = _walk_forbidden(packet)
    if hit:
        raise ProspectiveLedgerError(
            f"forbidden outcome field present in packet at {hit} — IMCE A5B "
            f"computes decision-time state only, never a graded outcome"
        )


# ---------------------------------------------------------------------------
# Path law + production-flag law (red-team M7 hardening)
# ---------------------------------------------------------------------------

def _validate_write_path(path: Path, *, reconstruction: bool) -> Path:
    resolved = Path(path).resolve()
    prod = PRODUCTION_PATH.resolve()
    if reconstruction:
        if resolved == prod:
            raise ProspectiveLedgerError(
                "reconstruction mode may never write the production prospective "
                f"ledger path ({PRODUCTION_PATH}); pass an explicit temp path"
            )
    else:
        if resolved != prod:
            raise ProspectiveLedgerError(
                "a production (non-reconstruction) write must target the "
                f"production path ({PRODUCTION_PATH}); pass reconstruction=True "
                "with an explicit temp path for a test/reconstruction write"
            )
    return resolved


def _require_production_flag(production: bool) -> None:
    if not production:
        raise ProspectiveLedgerError(
            "a production (non-reconstruction) write requires production=True — a "
            "bare/flagless call refuses to touch the production ledger; the nightly "
            "builder passes production=True explicitly via its --production CLI flag"
        )


def _append_line(row: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def load_rows(path: Path | None = None) -> list[dict]:
    """Return every row (all kinds) from the ledger, in file order.

    Returns [] if the file does not exist yet (first-publish, not a failure).
    """
    p = Path(path) if path is not None else PRODUCTION_PATH
    if not p.exists():
        return []
    rows: list[dict] = []
    with p.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                log.warning("imce_prospective_observation_v1.jsonl line %d parse error: %s", lineno, exc)
    return rows


def activation_row(path: Path | None = None) -> dict | None:
    for row in load_rows(path):
        if row.get("row_kind") == ROW_KIND_ACTIVATION:
            return row
    return None


def _observation_rows(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r.get("row_kind") == ROW_KIND_OBSERVATION]


def find_observation(event_id: str, decision_cutoff: str, path: Path | None = None) -> dict | None:
    """The observation with this EXACT (event_id, decision_cutoff) key."""
    for row in _observation_rows(load_rows(path)):
        if row.get("trigger", {}).get("event_id") == event_id and row.get("trigger", {}).get("decision_cutoff") == decision_cutoff:
            return row
    return None


def find_observation_by_event_id(event_id: str, path: Path | None = None) -> dict | None:
    """ANY observation for *event_id*, regardless of decision_cutoff
    (red-team M4 fix): an event_id may carry at most one observation, ever —
    a later workspace revision for the same event_id (whether the source
    document sha256 changed via re-extraction, or an 8-K/A minted a new
    acceptance datetime and therefore a new decision_cutoff) is a
    CORRECTION, never a second observation."""
    for row in _observation_rows(load_rows(path)):
        if row.get("trigger", {}).get("event_id") == event_id:
            return row
    return None


def find_observation_by_id(observation_id: str, path: Path | None = None) -> dict | None:
    for row in _observation_rows(load_rows(path)):
        if row.get("observation_id") == observation_id:
            return row
    return None


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------

def ensure_activation(
    *, path: Path | None = None, reconstruction: bool = False, production: bool = False,
    now: datetime | None = None,
) -> dict:
    """Idempotent: returns the existing activation row unchanged if one
    already exists (NEVER re-stamped); otherwise appends and returns a new
    one stamped with *now* (default: current UTC time).

    A non-reconstruction call additionally requires production=True (M7)."""
    target = _validate_write_path(Path(path) if path is not None else PRODUCTION_PATH, reconstruction=reconstruction)
    if not reconstruction:
        _require_production_flag(production)
    existing = activation_row(target)
    if existing is not None:
        return existing
    ts = _now_iso(now)
    row = {
        "schema": SCHEMA,
        "row_kind": ROW_KIND_ACTIVATION,
        "activation_started_at": ts,
        "registered_contract_hash": REGISTERED_CONTRACT_HASH,
        "roster": list(ROSTER),
        "created_at": ts,
    }
    _append_line(row, target)
    return row


# ---------------------------------------------------------------------------
# Observation identity (content-address, LOCAL to this dataset)
# ---------------------------------------------------------------------------

def _strip_keys_recursive(obj: Any, keys: frozenset[str]) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_keys_recursive(v, keys) for k, v in obj.items() if k not in keys}
    if isinstance(obj, list):
        return [_strip_keys_recursive(v, keys) for v in obj]
    return obj


def compute_observation_id(packet: dict, *, prefix: str = "obs") -> str:
    """Content-address over the packet's DECISION-TIME content only.

    Excludes bookkeeping keys (observation_id/created_at/row_kind/schema)
    AND (red-team M6) every ``observation_timestamp`` field anywhere in the
    body — a wall-clock stamp sitting inside c_t legs must never make two
    otherwise-identical builds mint different ids.
    """
    body = {k: v for k, v in packet.items() if k not in ("observation_id", "created_at", "row_kind", "schema")}
    body = _strip_keys_recursive(body, _HASH_STRIP_KEYS)
    canon = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = sha256(canon.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:32]}"


def append_observation(
    packet: dict, *, path: Path | None = None, reconstruction: bool = False, production: bool = False,
    trigger_lifecycle_state: str | None = None, trigger_source_form: str | None = None,
) -> tuple[dict | None, bool]:
    """Append one observation packet.

    Identity law (red-team M4): at most ONE observation per event_id, ever.
      * SAME (event_id, decision_cutoff) as an existing row -> exact-duplicate
        no-op, returns the existing row, appended=False.
      * SAME event_id, DIFFERENT decision_cutoff -> REFUSED. Route this
        through append_correction() instead — never call append_observation
        a second time for an event_id that already has one.

    Activation law (red-team M7): if this ledger already carries an
    activation row, a packet whose decision_cutoff predates
    activation_started_at is refused, independent of any upstream fencing
    the caller may or may not have done.

    A5C safety law (Sol A5C review, 2026-08-23, item 1; hardened by the
    Opus red-team BLOCKER-1 fix on the same day): *trigger_lifecycle_state*
    and *trigger_source_form* are the triggering event_workspace's OWN
    ``lifecycle.state`` string and issuer_release source row ``form`` string
    at the time of this call — the caller (the nightly builder) must read
    both straight off the workspace and pass them through; this function
    never infers either from the packet, which does not (and must not)
    carry them as stored keys. When this call is about to mint a genuinely
    FIRST observation for event_id (no exact-duplicate, no existing
    observation of any kind — see ``existing_any`` below) AND EITHER signal
    is unsafe (``is_safe_original_lifecycle_state`` is False, OR
    ``is_safe_original_source_form`` is False), the write is REFUSED: no row
    of any kind is appended, no exception is raised, activation is left
    untouched, and the caller's per-candidate loop is expected to continue
    with the next one. Two independent signals are required because
    lifecycle.state alone is a NECESSARY but not (until the manifest/history
    chain lands) SUFFICIENT signal: it only fires when a prior published
    workspace exists to compare against, while the SEC's own form is
    "8-K/A" from the very first observed revision of an amended event, prior
    workspace or not. The refusal is log-only — a bare ``::warning`` line
    reporting what was SEEN (never a guessed diagnosis), and never a logger
    call (this repo's "GitHub annotations must start the line" law) — and
    returns ``(None, False)``, distinguishable from an exact-duplicate no-op
    (which always returns the existing row, never ``None``, alongside
    ``appended=False``). A corrected revision for an event_id that ALREADY
    has a prior observation is UNAFFECTED by this law — it still routes
    through the existing_any branch below into ``append_correction()``,
    exactly as before. KNOWN RESIDUAL GAP (named, not closed here): a
    replacement/amended 8-K whose ORIGINAL was never published at all still
    presents as a first-ever "complete"/"8-K" revision to both signals —
    closing that requires the manifest/history chain, a separate future PR.

    A non-reconstruction call additionally requires production=True (M7).
    """
    target = _validate_write_path(Path(path) if path is not None else PRODUCTION_PATH, reconstruction=reconstruction)
    if not reconstruction:
        _require_production_flag(production)
    assert_no_outcome_fields(packet)
    trigger = packet.get("trigger") or {}
    event_id = trigger.get("event_id")
    decision_cutoff = trigger.get("decision_cutoff")
    if not event_id or not decision_cutoff:
        raise ProspectiveLedgerError("packet.trigger.event_id and .decision_cutoff are required")

    activation = activation_row(target)
    if activation is not None and parse_iso(decision_cutoff) < parse_iso(activation["activation_started_at"]):
        raise ProspectiveLedgerError(
            f"activation law: decision_cutoff {decision_cutoff} predates this ledger's "
            f"activation_started_at {activation['activation_started_at']!r} — refusing to write"
        )

    exact_dup = find_observation(event_id, decision_cutoff, target)
    if exact_dup is not None:
        # Red-team N3: an EXACT (event_id, decision_cutoff) match that also
        # carries materially different derived content is NOT a safe no-op
        # — a genuinely identical rebuild should never differ, so silently
        # returning the stale row would hide either a bug or a race. Raise
        # instead of asymmetrically trusting the key over the content.
        if packet_materially_differs(exact_dup, packet, trigger.get("ticker")):
            raise ProspectiveLedgerError(
                f"an observation already exists for event_id={event_id!r} "
                f"decision_cutoff={decision_cutoff!r} "
                f"(observation_id={exact_dup.get('observation_id')!r}) whose derived "
                f"state MATERIALLY DIFFERS from the packet just built — refusing a "
                f"silent no-op over content that disagrees; this should never happen "
                f"for a genuinely identical rebuild (N3 fix)"
            )
        return exact_dup, False

    existing_any = find_observation_by_event_id(event_id, target)
    if existing_any is not None:
        raise ProspectiveLedgerError(
            f"event_id {event_id!r} already has an observation "
            f"(observation_id={existing_any.get('observation_id')!r}, "
            f"decision_cutoff={existing_any.get('trigger', {}).get('decision_cutoff')!r}) — "
            f"a second append_observation() call for the same event_id is refused; "
            f"route this through append_correction() (M4 fix)"
        )

    safe_state = is_safe_original_lifecycle_state(trigger_lifecycle_state)
    safe_form = is_safe_original_source_form(trigger_source_form)
    if not (safe_state and safe_form):
        # A5C safety law (Sol, 2026-08-23, item 1) + BLOCKER-1 hardening
        # (Opus red-team, same day): this would be the FIRST observation
        # ever recorded for event_id, and at least one of the two safety
        # signals says unsafe — with no prior observation to anchor against
        # and no source-revision history chain yet, we cannot know whether
        # the ORIGINAL revision predated activation. Fail closed: log and
        # refuse, never guess. The message reports what was SEEN (both
        # signals, verbatim via !r), never an asserted diagnosis — MAJOR-2
        # fix: a missing/unknown state or form must not be narrated as "a
        # correction" when it might instead be a missing field or a novel
        # state this module has never seen. Bare print, line-start
        # "::warning" — never log.*, which prefixes the line and makes
        # GitHub silently drop it (repo law); flush=True is load-bearing
        # because stdout is block-buffered when piped in CI.
        print(
            "::warning title=imce-prospective-unsafe-correction::"
            f"{event_id} unsafe trigger for first observation — "
            f"lifecycle_state={trigger_lifecycle_state!r} (safe={safe_state}) "
            f"source_form={trigger_source_form!r} (safe={safe_form}); "
            "fail-closed pending source-revision history",
            flush=True,
        )
        return None, False

    row = dict(packet)
    row["schema"] = SCHEMA
    row["row_kind"] = ROW_KIND_OBSERVATION
    row["registered_contract_hash"] = REGISTERED_CONTRACT_HASH
    row.setdefault("authority", AUTHORITY)
    row.setdefault("prophet_flags", dict(PROPHET_FLAGS))
    row.setdefault("created_at", _now_iso())
    row["observation_id"] = compute_observation_id(row)
    _append_line(row, target)
    return row, True


def append_correction(
    *,
    superseded_observation_id: str,
    corrected_packet: dict,
    reason: str,
    path: Path | None = None,
    reconstruction: bool = False,
    production: bool = False,
) -> dict:
    """Append a correction row linked to *superseded_observation_id*.

    The original observation row is NEVER rewritten — this only appends a
    new, separately-identified row. Raises if the superseded id is not a
    known observation in this ledger, or if the corrected packet carries a
    forbidden outcome field. A non-reconstruction call additionally requires
    production=True (M7).
    """
    target = _validate_write_path(Path(path) if path is not None else PRODUCTION_PATH, reconstruction=reconstruction)
    if not reconstruction:
        _require_production_flag(production)
    assert_no_outcome_fields(corrected_packet)
    if find_observation_by_id(superseded_observation_id, target) is None:
        raise ProspectiveLedgerError(
            f"correction references unknown observation_id {superseded_observation_id!r} "
            f"in {target}"
        )
    row = dict(corrected_packet)
    row["schema"] = SCHEMA
    row["row_kind"] = ROW_KIND_CORRECTION
    row["registered_contract_hash"] = REGISTERED_CONTRACT_HASH
    row["supersedes_observation_id"] = superseded_observation_id
    row["correction_reason"] = str(reason or "").strip()
    row.setdefault("authority", AUTHORITY)
    row.setdefault("prophet_flags", dict(PROPHET_FLAGS))
    row.setdefault("created_at", _now_iso())
    row["observation_id"] = compute_observation_id(row)
    _append_line(row, target)
    return row


def packet_materially_differs(original_observation: dict, new_packet: dict, trigger_ticker: str) -> bool:
    """Red-team M4: the correction-worthiness test.

    Material difference = the event_workspace generation_id changed AND the
    derived six-fact / per-issuer state for *trigger_ticker* differs from
    what the original observation recorded. A generation bump with no
    derived-state change (a cosmetic republish) is NOT material — no
    correction noise. Comparing only the trigger ticker's own per-issuer
    block (not the whole pooled read) isolates what actually changed at the
    source, independent of any OTHER issuer's snapshot drifting between the
    two builds.
    """
    old_gen = (original_observation.get("trigger") or {}).get("event_workspace_generation_id")
    new_gen = (new_packet.get("trigger") or {}).get("event_workspace_generation_id")
    if old_gen == new_gen:
        return False
    old_issuer = ((original_observation.get("m_t") or {}).get("per_issuer") or {}).get(trigger_ticker) or {}
    new_issuer = ((new_packet.get("m_t") or {}).get("per_issuer") or {}).get(trigger_ticker) or {}
    old_cmp = {k: old_issuer.get(k) for k in ("facts", "d_orders", "d_cancel", "order_softness")}
    new_cmp = {k: new_issuer.get(k) for k in ("facts", "d_orders", "d_cancel", "order_softness")}
    return old_cmp != new_cmp


# ---------------------------------------------------------------------------
# M_t — per-issuer state + pooling (construction doc §2/§3.1 sign table,
# floor, tie, and label rules are VERBATIM below — red-team constant-exact
# verified; do not modify order_softness_state/_ORDER_SOFTNESS_TABLE/
# pool_cohort_state's arithmetic. The two new gates below (calendar-quarter
# pooling-key alignment, denominator-convention conformance) sit strictly
# UPSTREAM: they decide contributor ELIGIBILITY before the verbatim math
# ever runs, exactly like the pre-existing activation-law gate.)
# ---------------------------------------------------------------------------

def _fact_by_id(workspace: dict, fact_id: str) -> dict | None:
    for f in workspace.get("facts") or []:
        if isinstance(f, dict) and f.get("fact_id") == fact_id:
            return f
    return None


def _fact_value(fact: dict | None) -> tuple[Any, str | None]:
    """(value, absence_reason). absence_reason is None iff a value is present."""
    if fact is None:
        return None, "fact_absent_from_workspace"
    if fact.get("typed_absence"):
        absence = fact["typed_absence"]
        reason = absence.get("reason") if isinstance(absence, dict) else "typed_absence"
        return None, str(reason or "typed_absence")
    return fact.get("value"), None


def yoy_sign(current: object, prior: object) -> str | None:
    """Sign of (current - prior): '+' / '-' / '0', or None if either input
    is missing/non-numeric. Never a magnitude threshold — sign only."""
    if current is None or prior is None:
        return None
    try:
        delta = float(current) - float(prior)
    except (TypeError, ValueError):
        return None
    if delta > 0:
        return "+"
    if delta < 0:
        return "-"
    return "0"


def order_softness_state(d_orders: str | None, d_cancel: str | None) -> str:
    """Construction doc §2 lookup table, verbatim. NOT_RECONSTRUCTABLE
    whenever either sign is missing. UNCHANGED by the red-team fixes."""
    if d_orders is None or d_cancel is None:
        return "NOT_RECONSTRUCTABLE"
    return _ORDER_SOFTNESS_TABLE.get((d_orders, d_cancel), "NOT_RECONSTRUCTABLE")


def calendar_quarter_key(calendar_end: object) -> tuple[int, int] | None:
    """(calendar_year, calendar_quarter 1-4) via the FROZEN majority-month
    pooling key (POOLING_KEY_DOC §4b, "Pooling key (NEW) = calendar quarter
    by majority-month"): the fiscal quarter ENDING on *calendar_end* is
    assigned to whichever calendar quarter contains >=2 of its 3 constituent
    months. This is a GENERIC, mechanical reproduction of that frozen,
    verified-zero-collision rule — not a new one: applying it to any fixed
    fiscal-year-end offset reproduces the doc's own per-issuer table exactly
    (e.g. TOL's fiscal Q1, ending Jan 31, assigns to CQ4 of the PRIOR
    calendar year — Nov+Dec are 2 of the 3 constituent months — matching the
    doc's printed TOL row precisely).

    Returns None if calendar_end is unavailable/unparseable — pooling
    alignment can never be assumed, only computed.
    """
    if not calendar_end:
        return None
    try:
        d = calendar_end if hasattr(calendar_end, "year") else datetime.fromisoformat(str(calendar_end)).date()
    except (TypeError, ValueError):
        return None
    idx = d.year * 12 + (d.month - 1)
    buckets: dict[tuple[int, int], int] = {}
    for offset in (0, 1, 2):
        m_year, m_month0 = divmod(idx - offset, 12)
        cq = m_month0 // 3 + 1
        key = (m_year, cq)
        buckets[key] = buckets.get(key, 0) + 1
    return max(buckets.items(), key=lambda kv: kv[1])[0]


def _denominator_conforms(ticker: str, denom_value: object) -> bool | None:
    """MIN9 conformance guard against the construction doc §1 frozen
    per-issuer canonical denominator keywords. None = no keyword set for
    this ticker or nothing to check (never a hard exclusion by itself —
    only an explicit False excludes)."""
    keywords = _DENOMINATOR_CONFORMANCE_KEYWORDS.get(ticker.upper())
    if keywords is None:
        return None
    text = str(denom_value or "").strip().lower()
    if not text:
        return None
    return any(kw in text for kw in keywords)


def _tol_sensitivity(workspace: dict, *, d_orders: str | None, primary_state: str) -> dict:
    """Construction doc §1b mandatory diagnostic. Both the current- and
    prior-year values are REAL fact lookups — this function never changed;
    only the source plane's own extraction caught up (IMCE A5C item 7, PR
    #6307, 2026-08-23: engine/company_intelligence/issuer_profiles.py
    _tol_extract_release_facts now emits TOL_SENSITIVITY_PRIOR_YEAR_FACT_ID
    from the exhibit's own two-cell beginning-quarter-backlog row). A
    workspace whose exhibit lacks that row (an ambiguous/absent cell shape)
    still resolves the prior-year lookup to a typed absence
    (fact_absent_from_workspace) and the sensitivity state stays honestly
    NOT_RECONSTRUCTABLE for that event — this is a per-event data
    completeness outcome, not a placeholder."""
    current_fact = _fact_by_id(workspace, TOL_SENSITIVITY_FACT_ID)
    current_value, current_absence = _fact_value(current_fact)
    basis = current_fact.get("basis") if isinstance(current_fact, dict) else None

    prior_fact = _fact_by_id(workspace, TOL_SENSITIVITY_PRIOR_YEAR_FACT_ID)
    prior_value, prior_absence = _fact_value(prior_fact)

    d_cancel_sensitivity = yoy_sign(current_value, prior_value)
    sensitivity_state = order_softness_state(d_orders, d_cancel_sensitivity)
    agreement = None
    if sensitivity_state != "NOT_RECONSTRUCTABLE" and primary_state != "NOT_RECONSTRUCTABLE":
        agreement = sensitivity_state == primary_state
    return {
        "fact_id": TOL_SENSITIVITY_FACT_ID,
        "prior_year_fact_id": TOL_SENSITIVITY_PRIOR_YEAR_FACT_ID,
        "current_value": current_value,
        "current_absence_reason": current_absence,
        "basis": basis,
        "prior_year_value": prior_value,
        "prior_year_absence_reason": prior_absence,
        "d_cancel_sensitivity": d_cancel_sensitivity,
        "order_softness_sensitivity_basis": sensitivity_state,
        "agreement_with_primary_basis": agreement,
    }


def per_issuer_state(
    ticker: str,
    workspace: dict | None,
    *,
    activation_started_at: str,
    as_of_cutoff: str,
    trigger_pooling_key: tuple[int, int] | None,
) -> dict:
    """Pure. *workspace* is the most recent published event_workspace for
    *ticker* known at/before *as_of_cutoff* (or None if no such snapshot
    exists at all). Enforces, in order: the activation law, the
    PIT-knowability bound, calendar-quarter pooling-key alignment against
    *trigger_pooling_key* (red-team M5), and denominator-convention
    conformance (red-team MIN9) — all upstream of the verbatim §2 sign
    table, which never changes.
    """
    base = {"ticker": ticker, "facts": {}, "d_orders": None, "d_cancel": None,
            "order_softness": "NOT_RECONSTRUCTABLE", "as_of_event_id": None,
            "as_of_decision_cutoff": None, "pooling_key": None,
            "denominator_conforms": None}

    if workspace is None:
        return {**base, "contributor_eligible": False, "activation_law": "no_snapshot_available"}

    src_avail = (workspace.get("lifecycle") or {}).get("source_available_at")
    event_id = workspace.get("event_id")
    if not src_avail:
        return {**base, "contributor_eligible": False, "activation_law": "no_source_available_at",
                "as_of_event_id": event_id}

    src_dt = parse_iso(src_avail)
    if src_dt < parse_iso(activation_started_at):
        return {**base, "contributor_eligible": False, "activation_law": "pre_activation_excluded",
                "as_of_event_id": event_id, "as_of_decision_cutoff": src_avail}
    if src_dt > parse_iso(as_of_cutoff):
        return {**base, "contributor_eligible": False, "activation_law": "future_relative_to_trigger_excluded",
                "as_of_event_id": event_id, "as_of_decision_cutoff": src_avail}

    calendar_end = (workspace.get("fiscal_period") or {}).get("calendar_end")
    own_pooling_key = calendar_quarter_key(calendar_end)
    if own_pooling_key is None or trigger_pooling_key is None or own_pooling_key != trigger_pooling_key:
        return {**base, "contributor_eligible": False, "activation_law": "stale_snapshot_outside_aligned_quarter",
                "as_of_event_id": event_id, "as_of_decision_cutoff": src_avail,
                "pooling_key": own_pooling_key}

    facts_out: dict[str, dict] = {}
    for fid in FACT_IDS:
        value, absence_reason = _fact_value(_fact_by_id(workspace, fid))
        facts_out[fid] = {"value": value, "absence_reason": absence_reason}

    denom_conforms = _denominator_conforms(ticker, facts_out["fact_cancellation_rate_denominator"]["value"])
    if denom_conforms is False:
        return {**base, "contributor_eligible": False, "activation_law": "denominator_convention_mismatch",
                "as_of_event_id": event_id, "as_of_decision_cutoff": src_avail,
                "pooling_key": own_pooling_key, "facts": facts_out, "denominator_conforms": False}

    d_orders = yoy_sign(
        facts_out["fact_net_orders_current"]["value"],
        facts_out["fact_net_orders_prior_year"]["value"],
    )
    d_cancel = yoy_sign(
        facts_out["fact_cancellation_rate_current"]["value"],
        facts_out["fact_cancellation_rate_prior_year"]["value"],
    )
    state = order_softness_state(d_orders, d_cancel)

    result = {
        "ticker": ticker,
        "contributor_eligible": True,
        "activation_law": "post_activation",
        "as_of_event_id": event_id,
        "as_of_decision_cutoff": src_avail,
        "pooling_key": own_pooling_key,
        "denominator_conforms": denom_conforms,
        "facts": facts_out,
        "d_orders": d_orders,
        "d_cancel": d_cancel,
        "order_softness": state,
    }
    if ticker.upper() == "TOL":
        result["sensitivity"] = _tol_sensitivity(workspace, d_orders=d_orders, primary_state=state)
    return result


def pool_cohort_state(per_issuer: dict[str, dict]) -> dict:
    """Construction doc §3.1, VERBATIM — red-team constant-exact verified,
    UNCHANGED: >=2-contributor floor, modal state with any tie (two-way or
    three-way) typed MIXED, label by contributor count (4/4 cohort, 2-3
    named_subset + exact names, <2 NOT_RECONSTRUCTABLE)."""
    contributing = {
        t: v["order_softness"] for t, v in per_issuer.items()
        if v.get("order_softness") != "NOT_RECONSTRUCTABLE"
    }
    n = len(contributing)
    if n < 2:
        return {
            "label": "NOT_RECONSTRUCTABLE", "pooled_state": "NOT_RECONSTRUCTABLE",
            "named_subset_basis": None, "contributors": sorted(contributing), "n_contributors": n,
        }
    counts = Counter(contributing.values())
    top = max(counts.values())
    modal = sorted(s for s, c in counts.items() if c == top)
    pooled_state = "MIXED" if len(modal) > 1 else modal[0]
    label = "cohort" if n == len(ROSTER) else "named_subset"
    return {
        "label": label,
        "pooled_state": pooled_state,
        "named_subset_basis": sorted(contributing) if label == "named_subset" else None,
        "contributors": sorted(contributing),
        "n_contributors": n,
    }


# ---------------------------------------------------------------------------
# R_t — PIT-safe price-technical leg (frozen spec item 7)
# ---------------------------------------------------------------------------

#: House price-plane precedence (engine/stock_identity/plane.py §1). NO
#: fallback across planes: a symbol not on its assigned plane is a typed
#: absence, never a second store lookup.
PRICE_CONSTRUCTION_VERSION = "imce_prospective.r_t.macd_hist_12_26_9.biweekly_epoch2000.v1"


def _bar_admissible(bar_date, decision_cutoff: datetime) -> bool:
    """A daily bar (or a biweekly PERIOD-END date, red-team B1) is fully
    knowable once its own trading session has CLOSED — reuses the house
    DST-aware session-close computation (engine.session_digest.
    session_window_et); never a hand-rolled UTC offset constant."""
    from engine.session_digest import session_window_et  # local import: keeps this module's import graph flat

    d = bar_date.date() if hasattr(bar_date, "date") else bar_date
    try:
        _, close_et = session_window_et(d)
    except Exception:  # noqa: BLE001 — an unparseable/non-session date is simply inadmissible
        return False
    return close_et.astimezone(timezone.utc) <= decision_cutoff


def price_leg_for_ticker(
    ticker: str, decision_cutoff: datetime, *, repo_root: Path | None = None, now: datetime | None = None,
) -> dict:
    """One R_t leg: PIT-bounded MACD-histogram sign on the biweekly close
    series, or a typed absence. NO fallback across price stores — the
    ticker's single house-canonical plane (or none) is the only read.

    Red-team B1 fix: admissibility is enforced at BOTH the daily-bar level
    AND the resulting biweekly PERIOD-END level — a Wed cutoff must not
    admit a biweekly bar whose period-end Friday has not itself closed yet
    (that partial-week pair's value is provisional and its date is future
    relative to the cutoff).

    Red-team item (i): adjustment_basis is stated honestly — the plane
    applies its own back-adjustment convention at READ TIME, so a value is
    NOT guaranteed stable across re-reads if a corporate action posts
    retroactively into this window; sign stability holds only absent such
    an event. ``vintage`` records the read-time timestamp (read-time-latest,
    never a per-bar revision vintage the plane does not itself carry).
    """
    import pandas as pd

    from engine.htf_durability import _biweekly_close
    from engine.stock_identity.plane import PLANE_DIRS, primary_planes
    from engine.technicals import macd_hist

    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    leg: dict[str, Any] = {
        "ticker": ticker, "price_plane_id": None, "adjustment_basis": None, "vintage": _now_iso(now),
        "last_admissible_bar": None, "last_biweekly_period_end": None,
        "construction_version": PRICE_CONSTRUCTION_VERSION,
        "sign": None, "macd_hist_value": None, "typed_absence": None,
    }

    planes = primary_planes(root)
    plane_id = planes.get(ticker.upper())
    if plane_id is None:
        leg["typed_absence"] = {
            "reason": "no_price_plane_holds_ticker",
            "detail": f"{ticker} is not present on any house price plane ({', '.join(PLANE_DIRS)})",
        }
        return leg

    leg["price_plane_id"] = plane_id
    leg["adjustment_basis"] = (
        f"plane {plane_id!r} (engine/stock_identity/plane.py §1 precedence) applies its own "
        "back-adjustment convention (splits/dividends) AT READ TIME — the value above is not "
        "guaranteed stable across re-reads of this window if a corporate action posts "
        "retroactively; sign stability of this leg holds only absent such an adjustment event "
        "and is not otherwise independently verified. 'vintage' is the read-time timestamp "
        "(read-time-latest), not a per-bar revision vintage the plane does not itself carry."
    )

    path = root / PLANE_DIRS[plane_id] / f"{ticker.upper()}.parquet"
    if not path.exists():
        leg["typed_absence"] = {"reason": "plane_file_missing", "detail": str(path)}
        return leg

    try:
        df = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        leg["typed_absence"] = {"reason": "plane_file_unreadable", "detail": str(exc)}
        return leg

    if "close" not in df.columns or df.empty:
        leg["typed_absence"] = {"reason": "plane_file_no_close_column_or_empty", "detail": str(path)}
        return leg

    cutoff = decision_cutoff if decision_cutoff.tzinfo else decision_cutoff.replace(tzinfo=timezone.utc)
    admissible_mask = [_bar_admissible(ts, cutoff) for ts in df.index]
    if not any(admissible_mask):
        leg["typed_absence"] = {
            "reason": "no_admissible_bar_before_cutoff",
            "detail": f"earliest bar {df.index.min()} postdates decision_cutoff {decision_cutoff.isoformat()}",
        }
        return leg

    bounded_close = df.loc[admissible_mask, "close"].astype(float)
    leg["last_admissible_bar"] = str(bounded_close.index.max())

    biweekly_full = _biweekly_close(bounded_close)
    # B1 FIX: _biweekly_close pairs WEEKLY bars into a 2W period regardless
    # of whether the FINAL weekly bar's own week has fully elapsed — a
    # truncated daily series ending mid-week still produces a resample bin
    # labelled by that week's (future) Friday, built from a partial week.
    # Only period-ends whose own session has itself closed by cutoff may
    # participate; this can only ever drop TRAILING bar(s), never disturb
    # history (every earlier week in a truncated-but-continuous daily series
    # is, by construction, already fully populated).
    biweekly_mask = [_bar_admissible(ts, cutoff) for ts in biweekly_full.index]
    biweekly = biweekly_full[biweekly_mask]
    if biweekly.empty:
        leg["typed_absence"] = {
            "reason": "no_completed_biweekly_period_before_cutoff",
            "detail": (
                f"{len(bounded_close)} admissible daily bars produced "
                f"{len(biweekly_full)} biweekly bin(s), none of whose period-end "
                f"had itself closed by cutoff {decision_cutoff.isoformat()}"
            ),
        }
        return leg
    leg["last_biweekly_period_end"] = str(biweekly.index.max())

    hist = macd_hist(biweekly).dropna()
    if hist.empty:
        leg["typed_absence"] = {
            "reason": "insufficient_biweekly_history_for_macd",
            "detail": f"{len(bounded_close)} admissible daily bars produced {len(biweekly)} admissible biweekly bars",
        }
        return leg

    last_val = float(hist.iloc[-1])
    leg["macd_hist_value"] = last_val
    leg["sign"] = "+" if last_val > 0 else ("-" if last_val < 0 else "0")
    return leg


# ---------------------------------------------------------------------------
# C_t — rights-safe owner-source macro context (frozen spec item 8)
# ---------------------------------------------------------------------------

def _context_leg_shape(
    *, source: str, value: object, typed_absence: dict | None, pit_class: str | None,
    source_timestamp: str | None, obs_ts: str, context_only: bool = True, **extra: Any,
) -> dict:
    """MIN10: every C_t leg carries the SAME full shape (not just treasury_cmt)."""
    leg = {
        "source": source, "value": value, "typed_absence": typed_absence, "pit_class": pit_class,
        "source_timestamp": source_timestamp, "observation_timestamp": obs_ts, "context_only": context_only,
    }
    leg.update(extra)
    return leg


def context_legs(*, now: datetime | None = None) -> dict:
    """Every leg records source/value-or-typed-absence/pit_class/timestamps
    (MIN10: pmms/fred_alfred/nar_series now carry the same full shape as
    treasury_cmt). No FRED/ALFRED (not even a fetch). No NAR series. PMMS is
    HELD — never persisted. Treasury CMT is persistable under GO_LIMITED but
    this wave ships no in-repo first-party Treasury Daily Par Yield Curve
    fetcher/store — captured as an honest typed absence, never an invented
    value. Every captured field the registered contract does not name as a
    model feature is context_only — capture never grants statistical use."""
    obs_ts = _now_iso(now)
    return {
        "treasury_cmt": _context_leg_shape(
            source="US Treasury Daily Treasury Par Yield Curve",
            value=None,
            typed_absence={
                "reason": "no_in_repo_first_party_fetcher_or_store",
                "detail": (
                    "GO_LIMITED authorizes persistence of Treasury-published Daily "
                    "Treasury Par Yield Curve values with first-party provenance, "
                    "retrieval timestamp, and methodology reference, but no such "
                    "fetcher/store exists in this repo yet — building one is new "
                    "collector infrastructure outside this wave's scope; captured "
                    "honestly as absent rather than invented"
                ),
            },
            pit_class=None, source_timestamp=None, obs_ts=obs_ts,
            rights_disposition="GO_LIMITED",
        ),
        "pmms": _context_leg_shape(
            source="Freddie Mac Primary Mortgage Market Survey",
            value=None,
            typed_absence={"reason": "held", "detail": "pit_pure_archive_but_redistribution_commercial_exploitation_terms_ambiguous"},
            pit_class=None, source_timestamp=None, obs_ts=obs_ts,
            persisted=False, status="held",
        ),
        "fred_alfred": _context_leg_shape(
            source="FRED/ALFRED", value=None,
            typed_absence={"reason": "excluded_categorically", "detail": "not even a fetch is performed"},
            pit_class=None, source_timestamp=None, obs_ts=obs_ts,
            fetched=False, status="excluded_categorically",
        ),
        "nar_series": _context_leg_shape(
            source="National Association of Realtors (existing_home_sales, housing_affordability_index)",
            value=None,
            typed_absence={"reason": "may_not_be_stored", "detail": "NAR terms bar storage in a retrieval system, not merely redistribution"},
            pit_class=None, source_timestamp=None, obs_ts=obs_ts,
            may_be_stored=False,
        ),
    }


# ---------------------------------------------------------------------------
# Packet assembly
# ---------------------------------------------------------------------------

def build_observation_packet(
    *,
    trigger_ticker: str,
    trigger_workspace: dict,
    issuer_workspaces: dict[str, dict | None],
    activation_started_at: str,
    now: datetime | None = None,
) -> dict:
    """Assemble one full decision-time observation packet.

    *issuer_workspaces* maps EVERY roster ticker (including the trigger) to
    the most recent published event_workspace known at/before the trigger's
    own decision cutoff (or None if no snapshot is available for that
    issuer yet) — the caller (the nightly builder) owns candidate discovery
    and PIT-bounded selection; this function is pure given that mapping.
    """
    lifecycle = trigger_workspace.get("lifecycle") or {}
    decision_cutoff = lifecycle.get("source_available_at")
    if not decision_cutoff:
        raise ProspectiveLedgerError("trigger_workspace.lifecycle.source_available_at is required")

    trigger_calendar_end = (trigger_workspace.get("fiscal_period") or {}).get("calendar_end")
    trigger_pooling_key = calendar_quarter_key(trigger_calendar_end)
    if trigger_pooling_key is None:
        raise ProspectiveLedgerError(
            "trigger_workspace.fiscal_period.calendar_end is required to compute the "
            "calendar-quarter pooling key (red-team M5) — cannot pool without it"
        )

    issuer = trigger_workspace.get("issuer") or {}
    listings = issuer.get("listings") or []
    primary_listing = next((l for l in listings if l.get("is_primary")), (listings[0] if listings else {}))

    sources = trigger_workspace.get("sources") or []
    release_source = next((s for s in sources if s.get("kind") == "issuer_release"), {})
    filing_key = release_source.get("filing_key") or {}

    per_issuer: dict[str, dict] = {}
    for ticker in ROSTER:
        ws = issuer_workspaces.get(ticker)
        per_issuer[ticker] = per_issuer_state(
            ticker, ws, activation_started_at=activation_started_at, as_of_cutoff=decision_cutoff,
            trigger_pooling_key=trigger_pooling_key,
        )

    m_t = {
        "construction_doc": CONSTRUCTION_DOC,
        "pooling_key_doc": POOLING_KEY_DOC,
        "trigger_pooling_key": list(trigger_pooling_key),
        "roster": list(ROSTER),
        "per_issuer": per_issuer,
        **pool_cohort_state(per_issuer),
    }

    r_t = {
        "construction_version": PRICE_CONSTRUCTION_VERSION,
        "legs": {
            ticker: price_leg_for_ticker(ticker, parse_iso(decision_cutoff), now=now)
            for ticker in ROSTER
        },
    }

    packet = {
        "trigger": {
            "ticker": trigger_ticker,
            "company_id": issuer.get("company_id"),
            "security_id": primary_listing.get("security_id"),
            "event_id": trigger_workspace.get("event_id"),
            "fiscal_period": trigger_workspace.get("fiscal_period"),
            "event_workspace_generation_id": trigger_workspace.get("generation_id"),
            "source_document_sha256": release_source.get("source_sha256"),
            "source_accession": filing_key.get("accession"),
            "decision_cutoff": decision_cutoff,
        },
        "activation_started_at": activation_started_at,
        "m_t": m_t,
        "r_t": r_t,
        "c_t": context_legs(now=now),
        "authority": AUTHORITY,
        "prophet_flags": dict(PROPHET_FLAGS),
    }
    return packet
