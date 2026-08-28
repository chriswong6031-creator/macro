"""China institutional-visit tape (P1, China Alpha Intelligence) — DERIVED, keyless.

Rights basis: research/china_alpha_intelligence/RIGHTS_REGISTRY.md §1/§10 (PR
#6046). The CNInfo 投资者关系活动记录表 / 调研-class filing metadata plane is
rights-clear TODAY under the house public-regulatory-disclosure classification
(docs/QUAL_DATA_COMPLIANCE.md §1.4) — persistence, derived-use, and product
display of "a visit-category filing exists, for company X, on date Y" are all
settled. The blocker was extraction, not rights: collectors/china_filings.py's
CATEGORY_PRIORITY had no visit-record keyword bucket. This collector does NOT
re-scrape CNInfo — that would create a second ingester of the same endpoint,
forbidden by the commission. It DERIVES the visit tape from china_filings'
own store (data/china_filings/filings.parquet), filtering to
category == "institutional_visit" (added alongside this file).

Metadata-first, two-stage ingestion (masterplan §10): this collector emits the
EVENT row (who/when/company/type/published_at) as stage 1. Visitor-list body
hydration (parsing the PDF attachment to learn WHO visited) is explicitly a
LATER stage — RUL-4 (never fetch PDF bodies) is unchanged by this PR — so
every row's visitor fields are typed "not_yet_available" today, never guessed.

Store: data/china_visits/visits.parquet, append-only, dedup keep-FIRST on the
natural key `announcement_id` (china_filings already dedups the same key, so
this store simply narrows to one category — no new identity question).  Every
row carries BOTH `source_published_at` (china_filings' publish_ts — the
genuine PIT known_at, per RIGHTS-0's disclosure-timing finding) and
`system_recorded_at` (when THIS collector derived the row).

Coverage-start law (dispatch-header backfill ruling): P1 accrues FORWARD-ONLY
from first production light. `data/china_visits/coverage.json` is stamped
ONCE, on this collector's first-ever successful run, and never rewritten —
every later "first visit" read is `first_seen_since_coverage_start`, never a
real-world "first ever" claim (no historical backfill exists or is planned).

Failure isolation (asia-close is C0 market-critical — Sol precision ruling
2026-08-19): refresh() never raises past its own try/except. Every distinct
failure mode (china_filings store missing = not-yet-started; unreadable =
source failure) degrades to a typed, PERSISTED health record
(data/china_visits/health.json) that engine/china_intel_hub.py's dossier
block reads before it will ever assert "measured_no_event" for a name — a run
whose source read failed must never present a quiet tape as a clean null.

Same-cycle ordering (P1-R1, Sol product ruling 2026-08-20): scripts/collect.py
now runs this adapter in the SAME cninfo host-group thread as china_filings,
immediately after it (registry order china_filings -> china_visits ->
china_irm), so a single collect invocation's china_filings refresh is
consumed by this plane in the SAME cycle instead of the prior night's. The
contract is carried by a process-local flag, collectors.china_filings.
LAST_RUN_OUTCOME: refresh() reads it (lazily, to avoid an import cycle) right
after the existing store-missing/unreadable checks. None means china_filings
did not run in THIS process (the `--only china_visits` proof/debug path) and
this plane derives over whatever store is already committed to disk — legal,
unchanged behavior. A present outcome that is not ok means today's CNInfo
refresh degraded (partially or wholly): derivation and write_visits() still
run exactly as before — positive rows (real filings) are NEVER discarded on
account of a degraded refresh — but the run is typed "upstream_degraded"
instead of "ok", coverage_start is not stamped, and last_success_utc is not
advanced, because a degraded run proves nothing about absence.

P1-R2 announcement-id integrity (2026-08-22, DSC:CHINA-VISITS-UNTYPED-
ANNOUNCEMENT-ID-DROP): the bare comprehension that used to build candidate
rows dropped any row with a falsy announcementId silently — no typed
exclusion, no counter, no health note, while n_candidates kept counting the
pre-filter list. account_candidates() now performs that split explicitly and
typed, using the SAME key_anomaly() predicate china_filings.py's own write
path uses (imported from there, never re-derived here, so the two boundaries
can never silently diverge); refresh() then MECHANICALLY VERIFIES
`represented + typed_exclusions == eligible` before trusting the derivation,
and the collectors.china_filings import block that supplies the predicate is
now FAIL-CLOSED (an import failure degrades to source_failure instead of
deriving blind). Any run with typed exclusions is typed "upstream_degraded"
— reusing the existing health state rather than inventing a fifth, per
_HEALTH_STATES' comment below — and both causes (a degraded same-run
china_filings refresh, and this plane's own typed exclusions) are composed
into ONE record's detail when both fire.

P1-R3 durable scoped key-exclusion recovery (2026-08-22, Sol commission —
SUPERSEDES P1-R2's exclusion-health semantics only; everything else in P1-R2
is retained, see the frozen spec's §2). P1-R2 gave typed key exclusions the
wrong temporal semantics and produced two defects: D1 LATCH (one pre-
existing unkeyed row made `typed_exclusions >= 1` on EVERY later run
forever, latching the WHOLE plane to "upstream_degraded" — or, if it landed
before the first success, `coverage_start` never stamped and the plane never
started at all) and D2 AGING FORGETFULNESS (a newly malformed row is only
visible via the process-local `LAST_RUN_OUTCOME.key_integrity` in the SAME
run; once it ages out of china_filings' 3-day re-pull window the exclusion
vanishes and the affected company renders a FALSE clean measured_no_event).

The repair: a malformed source key now mints a durable, COMPANY-SCOPED
coverage exception in a new store (`data/china_visits/coverage_exceptions.
parquet`) instead of freezing the whole plane. Exceptions are versioned-
fingerprinted (`observation_fingerprint()`, §4 of the frozen spec —
EXCLUDES announcementId, `_collected_at`, `sec_name`, `kind`) so repeated
re-pulls of the SAME malformed observation reaffirm ONE row
(`upsert_exceptions()`) rather than minting N, and are deterministically
RESOLVED (never fuzzy-matched) once a later well-keyed filing shares the
same fingerprint (`reconcile_exceptions()`) — reconciliation is skipped
entirely when there are zero open exceptions (the cost guard; the render
budget is law). Typed key exclusions are therefore NO LONGER a GLOBAL cause
of `upstream_degraded` (§9 below supersedes the P1-R2 comment on
_HEALTH_STATES): a globally-clean run MAY now advance `last_success_utc` and
MAY stamp `coverage_start` even while a company-scoped exception stays open
— the negative authority is refused PER COMPANY by
engine/china_intel_hub.py's `_visit_block()` (state `not_yet_available`
instead of a false `measured_no_event`), never by freezing the plane. The
CANONICAL-IDENTITY FIREWALL (`is_observation_fingerprint()`) keeps a
fingerprint from EVER becoming `announcement_id`, a DataOS/GMI alias, or a
scoring input — enforced in `write_visits()`, which REFUSES the whole
append if any row's announcement_id is a fingerprint.

P1-R3A crash consistency at the source boundary (2026-08-22, Sol review of
PR #6242 — the COMPLETION of the same durability contract, not a new one).
P1-R3 made the exception durable, but only AFTER china_filings had already
committed a filtered canonical store that omitted the observation: the sole
bridge between the two was the PROCESS-LOCAL
`china_filings.LAST_KEY_INTEGRITY["excluded_rows"]` handoff, harvested later
by refresh(). A hard kill in that window — and the asia lane runs under one
— lost the observation from EVERY durable store at once: excluded from
filings.parquet by design, never written to coverage_exceptions.parquet, and
aged out of china_filings' 3-day re-pull within days. That is D2 again, one
layer down.

The frozen ordering invariant is now

    durable coverage exception  ->  canonical filtered filing-store commit

and never the reverse. `persist_boundary_exceptions()` below is the single
entry point china_filings calls BEFORE its commit (the fingerprint/upsert
law stays owned HERE and is reused, never duplicated there); if it cannot
make the observation durable, china_filings REFUSES to commit and leaves
filings.parquet byte-identical. There is still exactly ONE ledger, no retry
database and no transaction framework. refresh() therefore no longer
harvests `excluded_rows` at all — the boundary already did — and skips any
`visits_candidate` observation whose fingerprint the boundary made durable
in the same invocation, so one source occurrence yields one observation,
never two. A refused fence is a GLOBAL `upstream_degraded` cause: a run
whose canonical write never committed derived from a stale tape and may not
assert a measured absence over it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger("china_visits")

GROUP = "china_visits"
_CATEGORY = "institutional_visit"

# ------------------------------------------------------------------ identity --

# Manager-complex ontology (DRAFT, frozen only at the K2 estate wave —
# research/alpha_intelligence/censuses/B0/B0_MANAGER_COMPLEX_DRAFT.md, pin
# 3d12412e561e). B0's draft enumerates US 13F manager complexes only; no
# China visiting-institution name has been written into a deterministic
# house mapping yet, so this table starts EMPTY. Every row still stores the
# ontology_version stamp alongside the raw actor string (masterplan §5) so a
# later K2 freeze can re-map every historical row without rewriting history.
ONTOLOGY_VERSION = "B0_DRAFT_pin-3d12412e561e"

# Exact-match only (masterplan §5 exact-identity law: vendor/free-text names
# are aliases, not authority — never fuzzy-guess). Seed this ONLY from a
# written, deterministic house mapping; never invent one here.
_KNOWN_ACTORS: dict[str, str] = {}


def resolve_actor(raw_name: str) -> tuple[str, str]:
    """Map a raw visiting-institution name string to (class, ontology_version).

    Exact-match against `_KNOWN_ACTORS`; anything absent (including '') is
    typed "unresolved", never a fuzzy guess. Pure function, no I/O — safe to
    call once body-hydration (a later stage) starts producing raw visitor
    names. `ONTOLOGY_VERSION` is stamped on every call's result so a name
    that later gets a deterministic mapping can be re-resolved without
    losing the version the ORIGINAL resolution ran under.
    """
    name = (raw_name or "").strip()
    if not name:
        return "unresolved", ONTOLOGY_VERSION
    cls = _KNOWN_ACTORS.get(name)
    return (cls, ONTOLOGY_VERSION) if cls else ("unresolved", ONTOLOGY_VERSION)


# Plain-word filing-TYPE label for display only — never used to route, score,
# or rank. Priority mirrors CATEGORY_PRIORITY's institutional_visit keyword
# family (collectors/china_filings.py) so the two never drift: most specific
# first, falling back to a generic label for a title that matched the bucket
# only via the broad 调研 keyword (e.g. 机构调研情况登记表).
_VISIT_KIND_LABELS: tuple[tuple[str, tuple[str, str]], ...] = (
    ("业绩说明会", ("earnings briefing", "业绩说明会")),
    ("分析师会议", ("analyst meeting", "分析师会议")),
    ("特定对象调研", ("site visit", "特定对象调研")),
    ("投资者关系活动记录表", ("IR activity record", "投资者关系活动记录表")),
)
_VISIT_KIND_DEFAULT = ("investor visit", "机构调研")


def visit_kind_label(title: str) -> tuple[str, str]:
    """(en, zh) plain-word filing-type label for display. Pure, descriptive
    only. Falls back to a generic label for a still-genuine institutional_visit
    filing whose title matched only the broad 调研 keyword."""
    title = title or ""
    for kw, label in _VISIT_KIND_LABELS:
        if kw in title:
            return label
    return _VISIT_KIND_DEFAULT


# ------------------------------------------------------------------ store --

_VISIT_COLUMNS = (
    "announcement_id",     # natural key — shared with china_filings.announcementId
    "sec_code",
    "sec_name",
    "org_id",
    "exchange",
    "title",
    "source_published_at",  # china_filings.publish_ts — the genuine PIT known_at
    "system_recorded_at",   # ISO UTC — when THIS collector derived the row
    "visitor_raw",           # 'not_yet_available' until body hydration (later stage)
    "visitor_class",         # resolve_actor() class, or 'not_yet_available'
    "ontology_version",
    "adjunct_url",           # relative path — carried, NEVER fetched (RUL-4)
)


def _dir() -> Path:
    p = config.data_dir() / GROUP
    p.mkdir(parents=True, exist_ok=True)
    return p


def _visits_path() -> Path:
    return _dir() / "visits.parquet"


def _coverage_path() -> Path:
    return _dir() / "coverage.json"


def _health_path() -> Path:
    return _dir() / "health.json"


def _atomic_write(df: pd.DataFrame, path: Path) -> None:
    """Write ``df`` via a tmp sibling + os.replace — never a truncated store
    (china_irm precedent: the asia lane runs under a hard job kill)."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001 — never leave a half-written sibling behind
        tmp.unlink(missing_ok=True)
        raise


def load_visits() -> pd.DataFrame:
    """Existing visits.parquet reindexed to the canonical schema, or an empty
    frame with that schema when absent. A present-but-unreadable store also
    reads empty HERE (a reader must not crash) — write_visits() checks
    readability separately and ABORTS rather than silently replacing it."""
    path = _visits_path()
    if not path.exists():
        return pd.DataFrame(columns=list(_VISIT_COLUMNS))
    try:
        return pd.read_parquet(path).reindex(columns=list(_VISIT_COLUMNS))
    except Exception as e:  # noqa: BLE001
        log.warning("china_visits: could not read existing visits.parquet: %s", e)
        return pd.DataFrame(columns=list(_VISIT_COLUMNS))


def _read_store_strict() -> pd.DataFrame | None:
    """Like load_visits() but returns None (not empty) on an unreadable-but-
    present store, so write_visits() can ABORT instead of overwriting it."""
    path = _visits_path()
    if not path.exists():
        return pd.DataFrame(columns=list(_VISIT_COLUMNS))
    try:
        return pd.read_parquet(path).reindex(columns=list(_VISIT_COLUMNS))
    except Exception as e:  # noqa: BLE001
        log.error("china_visits: visits.parquet is present but UNREADABLE (%s)", e)
        return None


def read_visits_strict() -> pd.DataFrame | None:
    """Public alias of _read_store_strict() (frozen spec correction,
    2026-08-22): engine/china_intel_hub.py's _load_visits_context() must be
    able to distinguish an absent visits.parquet (empty frame — normal,
    unchanged) from a PRESENT-BUT-UNREADABLE one (None) — load_visits()
    deliberately swallows a read error and always answers empty, which
    would otherwise make a corrupt tape indistinguishable from a genuinely
    empty one and render as a clean measured_no_event for every A-share
    name. load_visits() itself is UNCHANGED (other callers depend on its
    forgiving contract) — this is a second, strict entry point."""
    return _read_store_strict()


def write_visits(rows: list[dict]) -> int:
    """Append rows, dedup keep-FIRST on announcement_id.

    Returns:
      >= 0  — the append was ATTEMPTED and completed (net-new count; 0 means
              "nothing to do" — empty input, or every row was already a
              known duplicate).
      -1    — REFUSED. The append did NOT happen and the store was left
              UNTOUCHED, for one of three reasons: the accrued store is
              present-but-unreadable (ABORT, manual recovery required), the
              P1-R3 canonical-identity firewall fired (a row's
              announcement_id was an observation_fingerprint), or an
              unexpected exception hit the write itself. -1 is a DISTINCT
              signal from 0 on purpose (correction, 2026-08-22): before this
              fix, all three refusal paths ALSO returned 0, indistinguishable
              from "0 net-new, wrote fine" — refresh() then fell straight
              through to `_write_health("ok", ..., success=True)` and
              ADVANCED absence authority over a store it had just refused to
              write. A guard whose firing is invisible to the health
              instrument is only half a guard. Callers (refresh()) MUST
              branch on `< 0` to add a GLOBAL upstream_degraded cause and
              must never let -1 leak into a user-facing "N net-new" count.

    Never raises.

    P1-R3 CANONICAL-IDENTITY FIREWALL (frozen spec §4): an
    `observation_fingerprint()` value must NEVER become `announcement_id` —
    not a canonical filing/event identity, not a DataOS/GMI alias, never
    consumed by scoring/ranking/Prophet. This is enforced HERE, not only in
    tests: the WHOLE append is refused (store left byte-identical) the
    instant ANY row's announcement_id is a fingerprint. Real CNInfo ids are
    numeric strings, so this can never fire in normal operation — it exists
    purely as a mutation-tested guard rail.
    """
    if not rows:
        return 0
    try:
        for r in rows:
            if is_observation_fingerprint(r.get("announcement_id")):
                log.error(
                    "china_visits: REFUSING write_visits — row announcement_id %r is an "
                    "observation_fingerprint value, which must NEVER become a canonical "
                    "filing/event identity; the whole append is refused and the store is "
                    "left untouched",
                    r.get("announcement_id"),
                )
                # Bare print, NOT log.* — see collectors/china_filings.py's
                # write_filings() for why (tests/test_gh_annotation_line_start.py).
                print(
                    "::error title=china-visits-fingerprint-identity-breach::"
                    "write_visits refused the whole append — a row's announcement_id is "
                    "an observation_fingerprint value, which must never become a "
                    "canonical filing/event identity",
                    flush=True,
                )
                return -1
        existing = _read_store_strict()
        if existing is None:
            log.error("china_visits: ABORTING the visits.parquet append — the accrued "
                      "store is unreadable and is left untouched for manual recovery")
            return -1
        new_df = pd.DataFrame(rows).reindex(columns=list(_VISIT_COLUMNS))
        if existing.empty:
            merged = new_df.drop_duplicates(subset=["announcement_id"], keep="first")
            net_new = len(merged)
        else:
            pre = existing["announcement_id"].nunique()
            merged = pd.concat([existing, new_df], ignore_index=True)
            merged = merged.drop_duplicates(subset=["announcement_id"], keep="first")
            net_new = merged["announcement_id"].nunique() - pre
        merged = merged.sort_values(
            ["source_published_at", "announcement_id"], na_position="last"
        ).reset_index(drop=True)
        _atomic_write(merged, _visits_path())
        return int(net_new)
    except Exception as e:  # noqa: BLE001
        log.error("china_visits.write_visits failed: %s", e)
        return -1


# ------------------------------------------------------------------ coverage --

def read_coverage_start() -> str | None:
    """The plane's persisted coverage_start date (ISO), or None if the plane
    has never completed a successful run."""
    path = _coverage_path()
    if not path.exists():
        return None
    try:
        doc = json.loads(path.read_text())
        return doc.get("coverage_start")
    except Exception as e:  # noqa: BLE001
        log.warning("china_visits: coverage.json unreadable (%s)", e)
        return None


def _stamp_coverage_start_once(today_iso: str) -> None:
    """Write coverage.json's coverage_start ONCE — never overwritten once set.

    This is the forward-only law made durable: the plane's history begins at
    OUR first successful observation, not the phenomenon's, and every later
    novelty read must be able to trust this stamp did not silently move.
    """
    if read_coverage_start() is not None:
        return
    try:
        _coverage_path().write_text(
            json.dumps({"coverage_start": today_iso}, indent=1)
        )
    except Exception as e:  # noqa: BLE001 — a sidecar write must never sink the night
        log.error("china_visits: could not stamp coverage_start: %s", e)


# ------------------------------------------------------------------ coverage exceptions (P1-R3) --
#
# Durable, company-scoped memory for "we observed source evidence relevant to
# this company but could not canonically admit it" — the repair for D1
# (permanent global blackout latch) and D2 (aging forgetfulness) described in
# the frozen spec's §0. Path: data/china_visits/coverage_exceptions.parquet.
# Resolved rows are KEPT FOREVER (never rewrite a historical exclusion away);
# only status=="open" rows suppress authority.

_EXCEPTION_COLUMNS = (
    "observation_fingerprint",   # dedup key, "obsfp1:<64 hex>"
    "fingerprint_version",       # "obsfp1"
    "sec_code",                  # "" when unresolvable -> UNSCOPED exception
    "sec_name",                  # display/proof only, NOT fingerprinted (mutable)
    "org_id",
    "exchange",
    "title",
    "source_published_at",       # the excluded observation's publish_ts
    "announcement_type_raw",
    "adjunct_url",
    "adjunct_type",
    "category",
    "key_anomaly",                # which typed anomaly excluded it
    "origin",                     # "filings_boundary" | "visits_candidate"
    "first_seen_utc",             # NEVER rewritten after first insert
    "last_seen_utc",              # reaffirmed on every re-observation
    "observed_count",             # int, incremented on every re-observation
    "status",                     # "open" | "resolved"
    "resolved_announcement_id",   # "" while open
    "resolved_utc",               # "" while open
)

# Fingerprint law (versioned, frozen spec §4). EXCLUDED from the fingerprint
# BY LAW: announcementId (the whole point of this store), _collected_at
# (collection-time noise), sec_name (mutable — an ST/rename would break dedup
# across a rename), kind (derived, not source). `_FINGERPRINT_FIELDS` and
# `_FINGERPRINT_VERSION` are the FROZEN RECOVERY TUPLE — changing either
# requires bumping the version string; a bumped version simply stops
# matching old rows (a visible non-match), never a silent re-key.
_FINGERPRINT_VERSION = "obsfp1"
_FINGERPRINT_FIELDS = ("exchange", "sec_code", "org_id", "title",
                        "publish_ts", "announcement_type_raw",
                        "adjunct_url", "adjunct_type", "category")


def _fp_norm(v) -> str:
    """Per-field fingerprint normalizer (frozen spec §4). "" for None or any
    NaN-like scalar (guarded pd.isna, same TypeError/ValueError shield as
    china_filings.key_anomaly()); else str(v).strip(); "" on a raising
    __str__. Pure, NEVER raises."""
    try:
        if v is None:
            return ""
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass  # non-scalar (list/array/...) input — never NaN-like
    try:
        return str(v).strip()
    except Exception:  # noqa: BLE001 — an un-stringable value normalizes to ""
        return ""


def observation_fingerprint(row: dict) -> str:
    """Versioned fingerprint of a source observation (frozen spec §4). PURE,
    NEVER raises. Joins the frozen field tuple's normalized values with the
    unit separator ("\\x1f", cannot occur in CNInfo text) and hashes.
    announcementId is deliberately NOT one of the joined fields — that is the
    whole point (a malformed/absent key must not prevent dedup of the
    UNDERLYING observation across repeated re-pulls).

    The except branch below is believed UNREACHABLE — _fp_norm() itself
    never raises for any input — but it is deliberately NOT a shared
    sentinel: `f"{_FINGERPRINT_VERSION}:" + "0" * 64` would let two
    DIFFERENT unfingerprintable observations collide onto the same
    fingerprint, and upsert_exceptions() would then silently merge them
    into ONE ledger row — exactly the drop_duplicates collapse this whole
    program exists to prevent, just moved one level up. So the fallback
    digest is derived from the row's own (best-effort) repr instead, which
    keeps two distinct failures from ever merging, and the failure is
    logged LOUDLY rather than swallowed.
    """
    try:
        parts = [_fp_norm(row.get(f)) for f in _FINGERPRINT_FIELDS]
        joined = "\x1f".join(parts)
        digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
        return f"{_FINGERPRINT_VERSION}:{digest}"
    except Exception as e:  # noqa: BLE001 — PURE, must NEVER raise
        log.error(
            "china_visits: observation_fingerprint() hit its believed-unreachable "
            "except branch for row=%r (%s) — falling back to a row-distinguishing "
            "digest so two distinct failures can never silently collide",
            row, e,
        )
        try:
            fallback_src = repr(sorted(row.items(), key=lambda kv: str(kv[0])))
        except Exception:  # noqa: BLE001 — even repr() must not escalate this
            fallback_src = repr(id(row))
        digest = hashlib.sha256(fallback_src.encode("utf-8", "replace")).hexdigest()
        return f"{_FINGERPRINT_VERSION}:{digest}"


def is_observation_fingerprint(value) -> bool:
    """True for any str starting with "obsfp" (frozen spec §4's CANONICAL-
    IDENTITY FIREWALL predicate). Real CNInfo announcementId values are
    numeric strings, so this can never true-positive in normal operation —
    it exists purely to KILL a mutation that lets a fingerprint leak into
    `announcement_id`/write_visits(). Never raises."""
    try:
        return isinstance(value, str) and value.startswith("obsfp")
    except Exception:  # noqa: BLE001
        return False


# A pre-this-fix `x or ""` idiom could have written one of these LITERAL
# strings into an already-persisted sec_code (NaN is truthy in Python, so
# `str(float('nan') or "").strip()` yields the 3-char string 'nan', not "").
# is_unscoped_sec_code() below is defense-in-depth against exactly that: a
# hand-written test row, or a historical ledger row written before
# _exception_fields() was fixed to normalize with _fp_norm() throughout.
_NAN_LITERAL_SEC_CODE_STRINGS = frozenset({"nan", "nat", "none", "<na>"})


def is_unscoped_sec_code(value) -> bool:
    """True when a ledger sec_code value carries no usable company
    identifier — i.e. the exception is UNSCOPED (frozen spec §12 hostile
    item 4: "a malformed visit with no usable company identifier -> global
    negative authority blocked"). Blank after _fp_norm() (covers None,
    every NaN-like scalar, and an un-stringable value), OR one of the
    literal NaN-derived strings a naive `x or ""` idiom could have produced.
    Never raises. Shared by refresh()'s own open_scoped/open_unscoped
    accounting and engine/china_intel_hub.py's _load_visits_context() so the
    two can never silently diverge on what counts as scoped."""
    norm = _fp_norm(value)
    return norm == "" or norm.lower() in _NAN_LITERAL_SEC_CODE_STRINGS


def _exceptions_path() -> Path:
    return _dir() / "coverage_exceptions.parquet"


def load_coverage_exceptions() -> pd.DataFrame:
    """Existing coverage_exceptions.parquet reindexed to the canonical
    schema, or an empty frame with that schema when absent. A present-but-
    unreadable store also reads empty HERE (a reader must not crash) —
    read_coverage_exceptions_strict() checks readability separately."""
    path = _exceptions_path()
    if not path.exists():
        return pd.DataFrame(columns=list(_EXCEPTION_COLUMNS))
    try:
        return pd.read_parquet(path).reindex(columns=list(_EXCEPTION_COLUMNS))
    except Exception as e:  # noqa: BLE001
        log.warning("china_visits: could not read existing coverage_exceptions.parquet: %s", e)
        return pd.DataFrame(columns=list(_EXCEPTION_COLUMNS))


def read_coverage_exceptions_strict() -> pd.DataFrame | None:
    """Like load_coverage_exceptions() but returns None (not empty) for a
    present-but-UNREADABLE ledger, so refresh() can fail closed (frozen spec
    §8): ABORT the ledger write, still write visits.parquet (positive
    evidence is real), and block measured_no_event for EVERY name via the
    hub's exceptions_readable flag — never silently replace a corrupt ledger
    with a fresh, empty-looking one."""
    path = _exceptions_path()
    if not path.exists():
        return pd.DataFrame(columns=list(_EXCEPTION_COLUMNS))
    try:
        return pd.read_parquet(path).reindex(columns=list(_EXCEPTION_COLUMNS))
    except Exception as e:  # noqa: BLE001
        log.error("china_visits: coverage_exceptions.parquet is present but UNREADABLE (%s)", e)
        return None


def _is_p1_relevant_exclusion(row: dict) -> bool:
    """P1-relevance filter (frozen spec §5, commission scope law: "a
    malformed row outside institutional_visit must not globally poison
    P1"). True iff category=='institutional_visit', OR the title is
    blank/absent (category is then UNKNOWABLE, not merely "other" — we
    cannot rule out it was a visit filing, so fail CLOSED and still harvest
    it). Everything else is china_filings' own instrument only and never
    touches P1. Never raises — an unexpected shape fails closed (True),
    the safer default for a filter guarding against silently dropping a
    potentially-relevant observation."""
    try:
        if (row.get("category") or "") == _CATEGORY:
            return True
        title = row.get("title")
        if title is None:
            return True
        try:
            if pd.isna(title):
                return True
        except (TypeError, ValueError):
            pass
        if isinstance(title, str) and title.strip() == "":
            return True
        return False
    except Exception:  # noqa: BLE001 — fail CLOSED (treat as relevant)
        return True


def _exception_fields(row: dict, origin: str, key_anomaly_fn) -> dict:
    """Pure mapping from a raw china_filings-shaped row dict (a malformed-key
    observation) to the ledger fields upsert_exceptions() needs to mint or
    reaffirm a row. Deliberately does NOT touch first_seen_utc/last_seen_utc/
    observed_count/status/resolved_* — those are upsert_exceptions()'s job
    alone, so a row that is REAFFIRMED never has its dedup-managed fields
    stomped by a fresh harvest.

    Every string field is normalized with _fp_norm(), NOT the `x or ""`
    idiom. `x or ""` does NOT handle a NaN-like value — NaN is TRUTHY in
    Python, so `str(float('nan') or "").strip()` yields the literal 3-char
    string 'nan' (and `pd.NA or ""` raises TypeError outright). A NaN/NaT
    `sec_code` is exactly "a malformed visit with no usable company
    identifier" (frozen spec §12 hostile item 4) — the origin=
    "visits_candidate" harvest path builds its rows from a `.reindex(
    columns=...)`'d frame, which materializes any MISSING column as
    all-NaN float64, and malformed-key rows are precisely the anomalous
    ones most likely to carry nulls. `x or ""` would silently convert "we
    don't know who this affects" into the truthy literal string 'nan' —
    the SAME class of lie this whole program exists to close, just one
    field over. _fp_norm() already handles None, every NaN-like scalar
    (guarded pd.isna, TypeError/ValueError-shielded), a non-scalar, and a
    raising __str__ — reuse it here rather than re-deriving a second,
    weaker normalizer.
    """
    return {
        "observation_fingerprint": observation_fingerprint(row),
        "fingerprint_version": _FINGERPRINT_VERSION,
        "sec_code": _fp_norm(row.get("sec_code")),
        "sec_name": _fp_norm(row.get("sec_name")),
        "org_id": _fp_norm(row.get("org_id")),
        "exchange": _fp_norm(row.get("exchange")),
        "title": _fp_norm(row.get("title")),
        "source_published_at": _fp_norm(row.get("publish_ts")),
        "announcement_type_raw": _fp_norm(row.get("announcement_type_raw")),
        "adjunct_url": _fp_norm(row.get("adjunct_url")),
        "adjunct_type": _fp_norm(row.get("adjunct_type")),
        "category": _fp_norm(row.get("category")),
        "key_anomaly": _fp_norm(key_anomaly_fn(row.get("announcementId"))),
        "origin": origin,
    }


def upsert_exceptions(
    existing_df: "pd.DataFrame | None", new_observations: list[dict], now_utc: str,
) -> tuple[pd.DataFrame, int, int]:
    """PURE (no I/O). Keyed on observation_fingerprint (frozen spec §7 —
    requirement 6: repeated re-pulls of the same malformed observation must
    produce ONE durable exception, never N rows):
      - fingerprint already present -> last_seen_utc updated, observed_count
        incremented. first_seen_utc, status, resolved_* are NOT touched — a
        re-observation of an already-RESOLVED fingerprint reaffirms
        last_seen/count but does NOT reopen it.
      - new fingerprint -> inserted with first_seen_utc=last_seen_utc=now,
        observed_count=1, status="open", resolved_*="".

    Processes `new_observations` in order against a running index, so two
    observations sharing a fingerprint WITHIN one batch correctly count as
    one insert + one reaffirm — never two separate inserts.

    Returns (df, n_new, n_reaffirmed).
    """
    base = existing_df if existing_df is not None else pd.DataFrame(columns=list(_EXCEPTION_COLUMNS))
    records: list[dict] = base.reindex(columns=list(_EXCEPTION_COLUMNS)).to_dict("records")
    index_by_fp: dict[str, int] = {
        r.get("observation_fingerprint"): i for i, r in enumerate(records)
    }
    n_new = 0
    n_reaffirmed = 0
    for obs in new_observations:
        fp = obs.get("observation_fingerprint")
        if not fp:
            continue  # observation_fingerprint() never returns falsy in practice
        if fp in index_by_fp:
            idx = index_by_fp[fp]
            records[idx]["last_seen_utc"] = now_utc
            try:
                prior = int(records[idx].get("observed_count") or 0)
            except (TypeError, ValueError):
                prior = 0
            records[idx]["observed_count"] = prior + 1
            n_reaffirmed += 1
        else:
            rec = {
                "observation_fingerprint": fp,
                "fingerprint_version": obs.get("fingerprint_version", _FINGERPRINT_VERSION),
                "sec_code": obs.get("sec_code", ""),
                "sec_name": obs.get("sec_name", ""),
                "org_id": obs.get("org_id", ""),
                "exchange": obs.get("exchange", ""),
                "title": obs.get("title", ""),
                "source_published_at": obs.get("source_published_at", ""),
                "announcement_type_raw": obs.get("announcement_type_raw", ""),
                "adjunct_url": obs.get("adjunct_url", ""),
                "adjunct_type": obs.get("adjunct_type", ""),
                "category": obs.get("category", ""),
                "key_anomaly": obs.get("key_anomaly", ""),
                "origin": obs.get("origin", ""),
                "first_seen_utc": now_utc,
                "last_seen_utc": now_utc,
                "observed_count": 1,
                "status": "open",
                "resolved_announcement_id": "",
                "resolved_utc": "",
            }
            records.append(rec)
            index_by_fp[fp] = len(records) - 1
            n_new += 1
    if records:
        result = pd.DataFrame(records).reindex(columns=list(_EXCEPTION_COLUMNS))
    else:
        result = pd.DataFrame(columns=list(_EXCEPTION_COLUMNS))
    return result, n_new, n_reaffirmed


def reconcile_exceptions(
    exceptions_df: pd.DataFrame, well_keyed_candidates: list[dict], now_utc: str,
) -> tuple[pd.DataFrame, int]:
    """Deterministic reconciliation (frozen spec §6). PURE, zero network.

    `well_keyed_candidates` must already be filtered to WELL-KEYED
    institutional_visit candidate rows (this function does not re-check
    key_anomaly — callers own that filter so this stays a pure function
    over exactly the fp->id map the spec describes).

    For each OPEN exception with fingerprint F, over the DISTINCT
    announcementIds among well-keyed candidates sharing F:
      - exactly ONE distinct id -> RESOLVE: status="resolved",
        resolved_announcement_id=<that real id>, resolved_utc=now. The SAME
        real announcement appearing twice among `well_keyed_candidates` (a
        duplicate row in the accrued store, a pre-dedup historical row, an
        unfiltered caller) is ONE canonical match, not two plausible ones —
        counting ROWS instead of distinct ids here would let a harmless
        duplicate classify a genuinely unambiguous match as "ambiguous" and
        leave it open FOREVER (no later event can ever remove the
        duplicate) — precisely the D1 "latch with no in-code exit" failure
        mode this whole wave exists to remove, reintroduced one layer down.
      - ZERO matches -> remains open.
      - TWO OR MORE distinct ids -> remains open (genuinely ambiguous).
        Never pick one.
      - NEVER fuzzy-match. Exact fingerprint equality only.

    Callers apply the COST GUARD (skip calling this when there are zero open
    exceptions) — this function still behaves correctly if called with none,
    it is just wasted work the render-budget-law common path should avoid.
    """
    if exceptions_df is None or exceptions_df.empty:
        empty = exceptions_df if exceptions_df is not None else pd.DataFrame(columns=list(_EXCEPTION_COLUMNS))
        return empty, 0

    fp_to_ids: dict[str, list[str]] = {}
    for row in well_keyed_candidates:
        # Defensive despite the "well-keyed only" contract above (this
        # function is public and pure): an id that normalizes to empty via
        # _fp_norm() (None/NaN-like/un-stringable) is SKIPPED rather than
        # coerced with str(...), which would mint the literal string 'None'
        # or 'nan' and risk it later being written into
        # resolved_announcement_id as a SYNTHETIC canonical identity — the
        # commission forbids that outright, no matter how it is spelled.
        raw_id = row.get("announcementId")
        norm_id = _fp_norm(raw_id)
        if not norm_id:
            continue
        fp = observation_fingerprint(row)
        fp_to_ids.setdefault(fp, []).append(norm_id)

    records = exceptions_df.reindex(columns=list(_EXCEPTION_COLUMNS)).to_dict("records")
    n_resolved = 0
    for rec in records:
        if rec.get("status") != "open":
            continue
        ids = fp_to_ids.get(rec.get("observation_fingerprint"), [])
        unique_ids = sorted(set(ids))
        if len(unique_ids) == 1:
            rec["status"] = "resolved"
            rec["resolved_announcement_id"] = unique_ids[0]
            rec["resolved_utc"] = now_utc
            n_resolved += 1
        # 0 or >=2 DISTINCT ids: remain open — never fuzzy-match, never pick one.
    result = pd.DataFrame(records).reindex(columns=list(_EXCEPTION_COLUMNS))
    return result, n_resolved


def persist_boundary_exceptions(
    malformed_rows: "list[dict] | None", key_anomaly_fn, now_utc: str | None = None,
) -> dict:
    """P1-R3A CRASH-CONSISTENCY FENCE. Durably upsert/reaffirm the P1-relevant
    malformed observations of ONE collectors.china_filings.write_filings()
    call, BEFORE that call commits its filtered canonical bytes.

    THE INVARIANT THIS EXISTS FOR:

        durable coverage exception  ->  canonical filtered filing-store commit

    and NEVER the reverse. Before P1-R3A the only bridge from the
    china_filings write boundary to this plane was the PROCESS-LOCAL
    china_filings.LAST_KEY_INTEGRITY["excluded_rows"] handoff, harvested
    later by refresh(). A hard kill between the filtered filings.parquet
    write and refresh()'s ledger write therefore lost the observation from
    EVERY durable store at once: it was already absent from filings.parquet
    (excluded by key integrity, by design), it had never reached
    coverage_exceptions.parquet, and china_filings' 3-day re-pull window
    (_NIGHTLY_LOOKBACK_DAYS) ages the source row out within days. The asia
    lane runs under a hard job kill, so that window is real, not theoretical.

    This function is the ONLY thing china_filings needs to call to satisfy
    that invariant. It deliberately does NOT duplicate the fingerprint /
    upsert law in china_filings (commission: "Factor/reuse the existing
    fingerprint/upsert law. Do not duplicate it in china_filings"): the
    ledger, its schema, its fingerprint version, its P1-relevance filter and
    its dedup semantics all stay owned HERE, in the plane the ledger belongs
    to. There is exactly ONE ledger — data/china_visits/coverage_exceptions
    .parquet — and no retry database, no journal, no second quarantine store.

    INERT ON THE COMMON PATH. `malformed_rows` is empty on every normal night
    (measured 2026-08-22: 0 of 54,078 accrued keys are malformed), and this
    returns immediately on that input WITHOUT reading or writing anything —
    so a zero-exception night never creates the ledger file, and "ledger
    absent" keeps meaning "normal empty state". The fence only becomes
    load-bearing on the rare night it was built for.

    FAILS CLOSED, AND THE CALLER MUST REFUSE ITS COMMIT WHEN IT DOES.
    `ok=False` means this function could NOT make the observation durable —
    an unreadable ledger, a failed write, or any unexpected exception. The
    caller must then leave the canonical store byte-identical: committing a
    filtered store that omits an observation we could not remember is
    exactly the silent forgetting this whole wave exists to close. The
    blast radius of that refusal is bounded by the inertness above: it can
    only ever fire on a night that already contains a malformed row.

    Returns a receipt, and NEVER raises (a raise here would sink the C0
    asia-close lane through china_filings):
      {"ok": bool,              — was every relevant observation made durable
       "n_relevant": int,       — P1-relevant malformed rows seen
       "n_new": int,            — newly inserted ledger rows
       "n_reaffirmed": int,     — existing fingerprints reaffirmed
       "fingerprints": [str],   — DURABLY handled this call (empty unless ok)
       "detail": str}           — human/log reason, "" when nothing happened

    `fingerprints` is the same-invocation double-count guard: refresh() skips
    any observation whose fingerprint this call already made durable, so one
    source occurrence produces ONE observation/reaffirmation per invocation,
    never two (commission discriminating test 4).
    """
    receipt = {"ok": True, "n_relevant": 0, "n_new": 0, "n_reaffirmed": 0,
               "fingerprints": [], "detail": ""}
    if not malformed_rows:
        return receipt
    try:
        relevant = [row for row in malformed_rows if _is_p1_relevant_exclusion(row)]
        receipt["n_relevant"] = len(relevant)
        if not relevant:
            # A malformed row outside institutional_visit (with a real title)
            # is china_filings' own instrument only and must never touch P1 —
            # scope law, commission discriminating test 6. No read, no write,
            # no ledger file created.
            receipt["detail"] = "no P1-relevant malformed rows this call"
            return receipt

        stamp = now_utc or datetime.now(timezone.utc).isoformat()
        existing = read_coverage_exceptions_strict()
        if existing is None:
            receipt["ok"] = False
            receipt["detail"] = (
                "coverage_exceptions.parquet is present but UNREADABLE — refusing to "
                "overwrite it, and the caller must refuse its canonical commit"
            )
            log.error("china_visits: boundary fence — %s", receipt["detail"])
            return receipt

        observations = [
            _exception_fields(row, "filings_boundary", key_anomaly_fn)
            for row in relevant
        ]
        updated, n_new, n_reaffirmed = upsert_exceptions(existing, observations, stamp)
        _atomic_write(updated, _exceptions_path())

        # Only AFTER the durable write succeeds are these fingerprints
        # reported as handled — an unwritten exception must never suppress
        # refresh()'s own harvest of the same observation.
        receipt["n_new"] = n_new
        receipt["n_reaffirmed"] = n_reaffirmed
        receipt["fingerprints"] = sorted(
            {obs["observation_fingerprint"] for obs in observations}
        )
        receipt["detail"] = (
            f"{len(relevant)} P1-relevant malformed observation(s) made durable "
            f"before the canonical commit ({n_new} new, {n_reaffirmed} reaffirmed)"
        )
        log.error("china_visits: boundary fence — %s", receipt["detail"])
        # Bare print, NOT log.* — this repo's loggers prefix the line, which
        # makes GitHub silently drop the annotation (it only parses "::" at
        # column 0). See tests/test_gh_annotation_line_start.py.
        print(
            f"::warning title=china-visits-coverage-exception-fence::"
            f"{len(relevant)} P1-relevant malformed observation(s) persisted to the "
            f"coverage-exception ledger before the canonical filings commit "
            f"({n_new} new, {n_reaffirmed} reaffirmed)",
            flush=True,
        )
        return receipt
    except Exception as e:  # noqa: BLE001 — NEVER raise into the C0 asia lane
        receipt["ok"] = False
        receipt["fingerprints"] = []
        receipt["detail"] = f"coverage-exception persistence failed unexpectedly: {e}"
        log.error("china_visits: boundary fence — %s", receipt["detail"])
        return receipt


# ------------------------------------------------------------------ health --

# The house ten-state taxonomy (masterplan §9.3). Only a subset is
# PRODUCIBLE by this collector today (the rest are dossier/read-time states
# computed in engine/china_intel_hub.py, or reserved for a later stage):
#   ok               — last run read the filings store and derived cleanly.
#   no_coverage      — no successful run has EVER completed (coverage_start unset).
#   source_failure   — the filings store exists but could not be read
#                       (corrupt / schema drift) — LOUD, never silently a quiet tape.
#   upstream_degraded — (P1-R1) producible when the SAME-RUN china_filings
#                       refresh's TRANSPORT degraded — an exchange raised
#                       (collectors.china_filings.LAST_RUN_OUTCOME.
#                       transport_ok is False) — or its key-integrity
#                       partition never completed (key_integrity_known is
#                       False), or (P1-R3) the coverage-exception ledger is
#                       present but unreadable. Derived rows (positive
#                       evidence) are still kept — a degraded refresh never
#                       discards a real filing — but the run advances no
#                       absence evidence (last_success_utc stays frozen,
#                       coverage_start is not stamped) and the dossier must
#                       never read measured_no_event from it. (P1-R2 —
#                       SUPERSEDED by P1-R3, frozen spec §9) used to ALSO be
#                       producible purely from this run's own typed key
#                       exclusions; that caused D1 (one pre-existing unkeyed
#                       row latched the WHOLE plane to upstream_degraded
#                       forever) and D2 (a fresh exclusion was only visible
#                       for the one run that saw it, then vanished once it
#                       aged out of the 3-day re-pull window — a false clean
#                       measured_no_event). P1-R3 instead mints a durable,
#                       COMPANY-SCOPED coverage exception (data/china_visits/
#                       coverage_exceptions.parquet) and suppresses
#                       measured_no_event PER COMPANY at dossier read time
#                       (engine/china_intel_hub.py's _visit_block(), state
#                       "not_yet_available") — a run with open exceptions but
#                       no OTHER cause above is now "ok" and DOES advance
#                       last_success_utc / stamp coverage_start. When
#                       multiple of the causes above fire in the same run,
#                       one record's detail names ALL of them.
# Reserved, not producible by this collector build: rights_suppressed (rights
# are settled — RIGHTS-0), low_extraction_confidence and contradicted (no LLM
# extraction in this PR). not_yet_available / identity_unresolved /
# not_applicable / stale / measured_no_event are computed at DOSSIER read
# time (engine/china_intel_hub.py), not stored here.
_HEALTH_STATES = ("ok", "no_coverage", "source_failure", "upstream_degraded")


def read_health() -> dict:
    """The plane's persisted health record, or a no_coverage default."""
    path = _health_path()
    if not path.exists():
        return {"status": "no_coverage", "detail": "china_visits has never run"}
    try:
        return json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("china_visits: health.json unreadable (%s)", e)
        return {"status": "no_coverage", "detail": f"health.json unreadable: {e}"}


def _write_health(
    status: str, detail: str, *, success: bool, accounting: dict | None = None,
) -> None:
    """Persist the health record. `success` advances last_success_utc; a
    failed run keeps the PRIOR last_success_utc (health.status alone tells
    the dossier the tape may currently be behind).

    `accounting` (P1-R2, optional, keyword-only): when present it is
    persisted as an ADDITIVE `candidate_accounting` field —
    `{"eligible": N, "represented_downstream": R, "typed_exclusions": X,
    "exclusions_by_type": {...}}` — so a clean run's own receipt also
    carries the arithmetic that used to be recoverable only by cross-
    referencing the filings and visits stores directly (the `so_what` in
    DSC:CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP). Existing fields and
    their semantics are unchanged; omitting `accounting` (the default)
    reproduces the pre-P1-R2 health.json shape exactly.
    """
    assert status in _HEALTH_STATES, f"unknown health status {status!r}"
    now = datetime.now(timezone.utc).isoformat()
    prior = read_health()
    doc = {
        "status": status,
        "detail": detail,
        "last_attempt_utc": now,
        "last_success_utc": now if success else prior.get("last_success_utc"),
    }
    if accounting is not None:
        doc["candidate_accounting"] = accounting
    try:
        _health_path().write_text(json.dumps(doc, indent=1))
    except Exception as e:  # noqa: BLE001
        log.error("china_visits: could not write health.json: %s", e)


# ------------------------------------------------------------------ derivation --

def _derive_row(filing: dict, system_recorded_at: str) -> dict:
    """One china_filings row (already category=='institutional_visit') → one
    canonical china_visits row. Pure (no I/O). Visitor fields are typed
    'not_yet_available': the metadata plane never fetches the PDF body
    (RUL-4), so a visitor LIST is genuinely not extractable at this stage —
    never guessed from the title.
    """
    return {
        "announcement_id": filing.get("announcementId", ""),
        "sec_code": filing.get("sec_code", ""),
        "sec_name": filing.get("sec_name", ""),
        "org_id": filing.get("org_id", ""),
        "exchange": filing.get("exchange", ""),
        "title": filing.get("title", ""),
        "source_published_at": filing.get("publish_ts", ""),
        "system_recorded_at": system_recorded_at,
        "visitor_raw": "not_yet_available",
        "visitor_class": "not_yet_available",
        "ontology_version": ONTOLOGY_VERSION,
        "adjunct_url": filing.get("adjunct_url", ""),
    }


def account_candidates(candidates: list[dict], system_recorded_at: str, key_anomaly) -> dict:
    """Explicit, PURE accounting over eligible candidate filing rows (P1-R2).

    Replaces the bare comprehension `[_derive_row(f, ts) for f in candidates
    if f.get("announcementId")]` — untyped, uncounted, silent (DSC:
    CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP) — with a typed split on the
    SAME predicate china_filings.py's own write path uses (`key_anomaly`,
    passed in rather than imported, so this stays a pure function callers can
    stub for the mutation test in tests/test_china_visits_collector.py).

    Returns:
      eligible            — len(candidates), the pre-filter count.
      rows                — derived china_visits rows for well-keyed candidates.
      represented         — len(rows).
      typed_exclusions    — count of malformed candidates excluded.
      exclusions_by_type  — {anomaly: count} for the anomalies that fired.
      excluded_identities — up to 5 human-recoverable identity strings for
                             excluded rows, formatted "sec_code|publish_ts|
                             title[:60]" because there is no announcementId
                             to name them by. LOG / GitHub-annotation use
                             ONLY — never a user-facing surface.
      excluded_rows        — (P1-R3) the excluded candidate row dicts
                             THEMSELVES, verbatim, uncapped (unlike
                             excluded_identities' 5-item cap). This is the
                             origin="visits_candidate" harvest source for
                             the durable coverage-exception ledger — every
                             candidate here already carries category==
                             "institutional_visit" (candidates is pre-
                             filtered to that category by refresh()), so no
                             further P1-relevance filtering is needed on
                             this list.

    refresh() uses `represented + typed_exclusions == eligible` as its
    mechanical accounting identity — this function is what makes that
    identity meaningful rather than tautological.
    """
    rows: list[dict] = []
    exclusions_by_type: dict[str, int] = {}
    excluded_identities: list[str] = []
    excluded_rows: list[dict] = []
    for f in candidates:
        anomaly = key_anomaly(f.get("announcementId"))
        if anomaly is None:
            rows.append(_derive_row(f, system_recorded_at))
        else:
            exclusions_by_type[anomaly] = exclusions_by_type.get(anomaly, 0) + 1
            excluded_rows.append(f)
            if len(excluded_identities) < 5:
                sec_code = f.get("sec_code", "")
                publish_ts = f.get("publish_ts", "")
                title = (f.get("title") or "")[:60]
                excluded_identities.append(f"{sec_code}|{publish_ts}|{title}")
    return {
        "eligible": len(candidates),
        "rows": rows,
        "represented": len(rows),
        "typed_exclusions": sum(exclusions_by_type.values()),
        "exclusions_by_type": exclusions_by_type,
        "excluded_identities": excluded_identities,
        "excluded_rows": excluded_rows,
    }


def _zero_progress(status: str) -> dict:
    """Canonical zero-progress sentinel shape (P1-R2 adds n_represented/
    n_excluded/exclusions alongside the pre-existing status/n_candidates/
    n_new fields — every refresh() return path now carries all six)."""
    return {"status": status, "n_candidates": 0, "n_new": 0,
            "n_represented": 0, "n_excluded": 0, "exclusions": {}}


def refresh() -> dict:
    """Derive tonight's visit-tape delta from china_filings' own store.

    Never raises: every failure mode degrades to a typed health record and a
    zero-progress sentinel, isolated to THIS plane only — asia-close's
    market-critical collectors must never see this module's exceptions. The
    outer try/except is belt-and-suspenders: every ANTICIPATED failure mode
    already returns early with its own typed health write below, so this
    only fires for a genuinely unexpected bug — and even then must still
    degrade instead of raising.

    Reads china_filings' parquet DIRECTLY (pd.read_parquet), not through
    china_filings.load_filings() — that helper swallows its own read
    exceptions and returns an empty frame either way (collectors/china_filings.py
    load_filings()), which would make a CORRUPT upstream store indistinguishable
    from a genuinely empty one. This plane needs that distinction: only the
    latter is safe to treat as "0 candidates, healthy run" — the former must
    surface as source_failure so the dossier never renders it as a quiet tape.

    P1-R2 (2026-08-22, DSC:CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP): the
    bare comprehension that used to build `rows` from `candidates` dropped
    any candidate with a falsy announcementId with no typed exclusion, no
    counter, no health note — while n_candidates kept counting the
    PRE-filter list, so a run that silently dropped k candidates printed the
    exact same "N candidate row(s) this run, ok" shape as a run that dropped
    none. account_candidates() below replaces the comprehension with an
    explicit, typed split, and the `represented + typed_exclusions ==
    eligible` check just after it is this plane's own mechanical proof that
    its accounting has not silently diverged from what it derived — an
    assert would be stripped under `python -O` and swallowed by the outer
    except, so it is an explicit branch instead (the branch the mutation
    test in tests/test_china_visits_collector.py kills).

    P1-R3 (2026-08-22, durable scoped key-exclusion recovery — SUPERSEDES
    P1-R2's exclusion-health semantics only, see the module docstring):
    typed key exclusions are harvested into the durable, company-scoped
    coverage_exceptions.parquet ledger (upsert_exceptions() +, when there is
    at least one open exception, reconcile_exceptions() — the COST GUARD:
    reconciliation is SKIPPED entirely on the overwhelming common case of
    zero open exceptions, never fingerprinting the candidate tape
    unconditionally) instead of freezing the WHOLE plane. GLOBAL causes of
    "upstream_degraded" are now only: a same-run china_filings TRANSPORT
    degradation, an UNKNOWN same-run key-integrity partition, or an
    unreadable coverage-exception ledger (the mechanical-accounting-mismatch
    cause above stays its own source_failure branch, unchanged). A clean run
    with an open company-scoped exception now advances last_success_utc and
    stamps coverage_start — the negative authority is refused PER COMPANY by
    engine/china_intel_hub.py's _visit_block(), never by freezing the plane.
    """
    system_recorded_at = datetime.now(timezone.utc).isoformat()
    today_iso = system_recorded_at[:10]
    try:
        filings_path = config.data_dir() / "china_filings" / "filings.parquet"
        if not filings_path.exists():
            # china_filings has never produced a store yet — not a failure of
            # THIS plane, just nothing to derive from yet. Coverage does not start.
            log.info("china_visits: china_filings store not present yet — 0-row night")
            _write_health("no_coverage", "china_filings store not present yet", success=False)
            return _zero_progress("no_coverage")

        try:
            filings = pd.read_parquet(filings_path)
        except Exception as e:  # noqa: BLE001
            log.error("china_visits: china_filings store unreadable: %s", e)
            _write_health("source_failure", f"filings store unreadable: {e}", success=False)
            return _zero_progress("source_failure")

        # P1-R1 same-cycle derivation contract: when china_filings ran earlier
        # in THIS process (same cninfo host-group thread, china_filings then
        # china_visits — see scripts/collect.py _CONCURRENT_HOSTS), its
        # outcome names whether the store just read above is a clean
        # same-run refresh or a degraded one. Lazy import to avoid an import
        # cycle.
        #
        # P1-R2: this import is now ALSO the source of the key-integrity
        # predicate (key_anomaly) this plane depends on to compute its own
        # accounting identity below — so an import FAILURE here is no longer
        # equivalent to "china_filings did not run in this process". It used
        # to degrade to same_run_outcome=None and proceed (deriving blind);
        # now it fails CLOSED: without the predicate this plane cannot
        # verify its own accounting, so it must not derive at all. A
        # SUCCESSFUL import with LAST_RUN_OUTCOME is None is UNCHANGED and
        # still the legitimate `--only china_visits` committed-store
        # proof/debug path.
        try:
            from collectors import china_filings as _cf  # noqa: PLC0415
        except Exception as e:  # noqa: BLE001 — must never sink this plane
            log.error("china_visits: collectors.china_filings import failed: %s", e)
            _write_health("source_failure", f"china_filings import failed: {e}", success=False)
            return _zero_progress("source_failure")
        same_run_outcome = _cf.LAST_RUN_OUTCOME

        # P1-R3A: what the china_filings write boundary ALREADY made durable
        # in this same invocation. `boundary_fingerprints` is the double-count
        # guard (one observation/reaffirmation per source occurrence, never
        # two); `boundary_persist_ok` is False only when the fence REFUSED —
        # in which case china_filings left its canonical store byte-identical
        # and the tape this plane just read is STALE, a GLOBAL cause below.
        # Both default to the permissive reading when the keys are absent
        # (a `--only china_visits` run, or a china_filings from before
        # P1-R3A), because their absence means the fence never spoke, not
        # that it failed.
        boundary_fingerprints: set[str] = set()
        boundary_persist_ok = True
        if same_run_outcome is not None:
            _ki = same_run_outcome.get("key_integrity") or {}
            boundary_persist_ok = bool(_ki.get("boundary_persist_ok", True))
            try:
                boundary_fingerprints = {
                    str(fp) for fp in (_ki.get("boundary_fingerprints") or [])
                }
            except (TypeError, ValueError):  # non-iterable / unhashable shape
                boundary_fingerprints = set()

        if filings is None or filings.empty or "category" not in filings.columns:
            candidates: list[dict] = []
        else:
            candidates = filings[filings["category"] == _CATEGORY].to_dict("records")

        accounting = account_candidates(candidates, system_recorded_at, _cf.key_anomaly)

        # Mechanical identity check — the branch the mutation test kills.
        if accounting["represented"] + accounting["typed_exclusions"] != accounting["eligible"]:
            detail = (
                "candidate accounting mismatch: represented="
                f"{accounting['represented']} + typed_exclusions="
                f"{accounting['typed_exclusions']} != eligible={accounting['eligible']} "
                "— refusing to trust this run's derivation"
            )
            log.error("china_visits: %s", detail)
            _write_health("source_failure", detail, success=False)
            return _zero_progress("source_failure")

        if accounting["typed_exclusions"]:
            log.error(
                "china_visits: %d candidate row(s) excluded on malformed "
                "announcementId (%s); identities: %s",
                accounting["typed_exclusions"], accounting["exclusions_by_type"],
                accounting["excluded_identities"],
            )
            # Bare print, NOT log.* — see collectors/china_filings.py's
            # write_filings() for why (tests/test_gh_annotation_line_start.py).
            print(
                f"::warning title=china-visits-malformed-announcement-id::"
                f"{accounting['typed_exclusions']} candidate row(s) excluded "
                f"on malformed announcementId ({accounting['exclusions_by_type']})",
                flush=True,
            )

        n_new_raw = write_visits(accounting["rows"])
        # write_visits() returns -1 for a REFUSED append (unreadable store
        # ABORT, or the P1-R3 canonical-identity firewall), distinct from a
        # genuine "0 net-new, wrote fine". A refusal must become a named
        # GLOBAL cause below (never silently fall through to "ok") and must
        # never leak into the returned/receipted "N net-new" count.
        write_visits_refused = n_new_raw < 0
        n_new = 0 if write_visits_refused else n_new_raw
        candidates_n = len(candidates)

        # ------------------------------------------------------------ #
        # P1-R3 durable coverage-exception ledger (frozen spec §3-§9).
        # Zero network. Read is fail-closed (§8): an unreadable ledger
        # ABORTS the ledger write entirely (never overwritten) and becomes
        # a GLOBAL upstream_degraded cause below — everything else here
        # (harvest/upsert/reconcile/write) is skipped on that path.
        # ------------------------------------------------------------ #
        exceptions_readable = True
        try:
            exceptions_before = read_coverage_exceptions_strict()
        except Exception as e:  # noqa: BLE001 — must never sink this plane
            log.error("china_visits: coverage_exceptions read raised unexpectedly: %s", e)
            exceptions_before = None
        if exceptions_before is None:
            exceptions_readable = False

        n_new_exc = n_reaffirmed_exc = n_resolved_exc = 0
        open_total = open_scoped = open_unscoped = 0

        if exceptions_readable:
            # Harvest (§5): origin="filings_boundary" from THIS run's
            # china_filings write. P1-R3A MOVED that harvest to the source
            # boundary itself — persist_boundary_exceptions() above, called
            # by china_filings.write_filings() BEFORE it commits — so this
            # step no longer reads LAST_KEY_INTEGRITY["excluded_rows"] at
            # all. Re-adding that loop here would double-count every
            # boundary observation (the fence already made it durable AND
            # reported its fingerprint), which is what
            # TestP1R3ACrashConsistencyFence::
            # test_item4_full_invocation_counts_one_observation_per_occurrence
            # kills.
            #
            # What REMAINS this plane's own job is the historical scan:
            # origin="visits_candidate" from THIS run's account_candidates()
            # over the ACCRUED store (pre-existing unkeyed rows that were
            # written before the typed-exclusion boundary existed, and which
            # no future china_filings write will ever re-present). Already
            # scoped to category=="institutional_visit" by `candidates`
            # itself, so no further P1-relevance filtering is needed.
            visits_candidate_rows = accounting.get("excluded_rows") or []

            new_observations: list[dict] = []
            for row in visits_candidate_rows:
                fields = _exception_fields(row, "visits_candidate", _cf.key_anomaly)
                if fields["observation_fingerprint"] in boundary_fingerprints:
                    # Same source occurrence, already made durable by the
                    # fence in THIS invocation — reaffirming it here would
                    # inflate observed_count to 2 for one occurrence.
                    continue
                new_observations.append(fields)

            exceptions_df, n_new_exc, n_reaffirmed_exc = upsert_exceptions(
                exceptions_before, new_observations, system_recorded_at
            )

            # COST GUARD (§6): only fingerprint the well-keyed candidate
            # tape when there is at least one OPEN exception to try to
            # resolve — the normal case, forever, is zero.
            if not exceptions_df.empty and (exceptions_df["status"] == "open").any():
                well_keyed = [
                    row for row in candidates
                    if _cf.key_anomaly(row.get("announcementId")) is None
                ]
                exceptions_df, n_resolved_exc = reconcile_exceptions(
                    exceptions_df, well_keyed, system_recorded_at
                )

            if n_new_exc or n_reaffirmed_exc or n_resolved_exc:
                try:
                    _atomic_write(exceptions_df, _exceptions_path())
                except Exception as e:  # noqa: BLE001 — must never sink this plane
                    log.error(
                        "china_visits: could not write coverage_exceptions.parquet: %s", e
                    )
                    exceptions_readable = False  # treat a failed write like unreadable

            if exceptions_readable and not exceptions_df.empty:
                open_mask = exceptions_df["status"] == "open"
                open_total = int(open_mask.sum())
                if open_total:
                    # Per-value is_unscoped_sec_code(), NOT
                    # .astype(str).str.strip() == "" — the latter turns a
                    # genuine NaN into the TRUTHY literal string 'nan',
                    # which would never equal "" and so misclassify an
                    # unscoped exception as scoped to company "nan".
                    codes = exceptions_df.loc[open_mask, "sec_code"]
                    open_unscoped = int(codes.map(is_unscoped_sec_code).sum())
                    open_scoped = open_total - open_unscoped

        accounting_receipt = {
            "eligible": accounting["eligible"],
            "represented_downstream": accounting["represented"],
            "typed_exclusions": accounting["typed_exclusions"],
            "exclusions_by_type": accounting["exclusions_by_type"],
            "coverage_exceptions": {
                "open": open_total, "open_scoped": open_scoped,
                "open_unscoped": open_unscoped, "new_this_run": n_new_exc,
                "reaffirmed_this_run": n_reaffirmed_exc,
                "resolved_this_run": n_resolved_exc, "readable": exceptions_readable,
                # P1-R3A: did the china_filings write boundary manage to make
                # its own malformed observations durable before committing?
                "boundary_persist_ok": boundary_persist_ok,
            },
        }

        # Cause composition (P1-R3 §9 — SUPERSEDES the P1-R2 comment on
        # _HEALTH_STATES above): typed key exclusions are NO LONGER a
        # GLOBAL cause of "upstream_degraded" — they became durable,
        # company-scoped ledger rows instead, suppressed PER COMPANY by
        # engine/china_intel_hub.py's _visit_block(). GLOBAL causes are now
        # ONLY: a same-run china_filings TRANSPORT degradation, an UNKNOWN
        # same-run key-integrity partition, an unreadable ledger, or (FIX,
        # correction 2026-08-22) write_visits() itself REFUSING the append.
        # china_visits reads the typed booleans china_filings now carries
        # instead of string-sniffing errors[].
        causes: list[str] = []
        if write_visits_refused:
            # The single most severe guard in this design (the unreadable-
            # store ABORT, or the P1-R3 canonical-identity firewall) fired
            # and protected the store exactly as intended — that must not be
            # invisible to the health instrument. Without this cause, a
            # refusal fell straight through to `_write_health("ok", ...,
            # success=True)` and ADVANCED absence authority over a store
            # this run knowingly refused to write.
            causes.append(
                "write_visits() REFUSED the append (unreadable accrued store, or the "
                "canonical-identity firewall) — the store was left untouched"
            )
        if same_run_outcome is not None and not same_run_outcome.get("transport_ok", True):
            errors = same_run_outcome.get("errors") or []
            causes.append(
                "derived over a same-run china_filings TRANSPORT degradation "
                f"({'; '.join(errors)})"
            )
        if same_run_outcome is not None and not same_run_outcome.get("key_integrity_known", True):
            causes.append(
                "same-run china_filings key-integrity partition is UNKNOWN this run"
            )
        if not exceptions_readable:
            causes.append(
                "the coverage-exception ledger is present but unreadable — the ledger "
                "write was ABORTED and the accrued ledger left untouched for manual recovery"
            )
        if not boundary_persist_ok:
            # P1-R3A: the fence refused, so china_filings left filings.parquet
            # byte-identical and this run derived from a STALE tape. Loud and
            # globally degraded for absence authority — the plane cannot claim
            # a measured absence over a store that never took tonight's rows.
            causes.append(
                "the china_filings coverage-exception fence REFUSED this run — the "
                "filtered canonical filings write was NOT committed, so the tape this "
                "plane derived from is STALE"
            )

        if causes:
            detail = "; ".join(causes) + " — this run contributes no absence evidence"
            log.warning("china_visits: %s", detail)
            _write_health("upstream_degraded", detail, success=False,
                          accounting=accounting_receipt)
            log.info("china_visits: %d candidate rows, %d net-new stored (upstream degraded)",
                      candidates_n, n_new)
            return {"status": "upstream_degraded", "n_candidates": candidates_n, "n_new": n_new,
                    "n_represented": accounting["represented"],
                    "n_excluded": accounting["typed_exclusions"],
                    "exclusions": accounting["exclusions_by_type"]}

        _stamp_coverage_start_once(today_iso)
        _write_health("ok", f"{candidates_n} candidate row(s) this run", success=True,
                      accounting=accounting_receipt)
        log.info("china_visits: %d candidate rows, %d net-new stored",
                 candidates_n, n_new)
        return {"status": "ok", "n_candidates": candidates_n, "n_new": n_new,
                "n_represented": accounting["represented"],
                "n_excluded": accounting["typed_exclusions"],
                "exclusions": accounting["exclusions_by_type"]}
    except Exception as e:  # noqa: BLE001 — must NEVER raise into the lane runner
        log.error("china_visits: refresh() failed unexpectedly: %s", e)
        try:
            _write_health("source_failure", f"unexpected refresh failure: {e}", success=False)
        except Exception:  # noqa: BLE001 — even the health write must not escalate this
            pass
        return _zero_progress("source_failure")


# ------------------------------------------------------------------ adapter --

class ChinaVisitsAdapter(Adapter):
    """China institutional-visit tape — derived from china_filings, keyless.

    Group ``china_visits`` starts with ``china`` so it is auto-assigned to
    the asia lane (scripts/collect.py group_members) and excluded from
    daily.yml's US-scope run.  refresh() does the real work directly (mirrors
    china_filings.py / china_irm.py); fetch() returns a small sentinel
    summary frame so the standard run_adapter circuit-breaker/staleness
    machinery has something to grade.
    """

    name = "china_visits"
    group = GROUP
    stale_after_days = 4   # mirrors china_filings' own cadence (it is the upstream)

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        s = refresh()
        idx = pd.Timestamp.now("UTC").normalize().tz_localize(None)
        summary = pd.DataFrame(
            {"n_candidates": [float(s["n_candidates"])],
             "n_new": [float(s["n_new"])]},
            index=[idx],
        )
        summary.index.name = "collected_at"
        return {"china_visits_summary": summary}


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    from collectors.base import run_adapter
    result = run_adapter(ChinaVisitsAdapter())
    print(f"status={result.status} rows={result.rows} last_date={result.last_date}")
    if result.error:
        print(f"error={result.error}", file=sys.stderr)
        sys.exit(1)
