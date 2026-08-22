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
"""
from __future__ import annotations

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


def write_visits(rows: list[dict]) -> int:
    """Append rows, dedup keep-FIRST on announcement_id. Returns net-new count.

    Never raises. An existing-but-unreadable store ABORTS the append (0
    returned, file left untouched for manual recovery) rather than being
    silently replaced by tonight's derived rows.
    """
    if not rows:
        return 0
    try:
        existing = _read_store_strict()
        if existing is None:
            log.error("china_visits: ABORTING the visits.parquet append — the accrued "
                      "store is unreadable and is left untouched for manual recovery")
            return 0
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
        return 0


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


# ------------------------------------------------------------------ health --

# The house ten-state taxonomy (masterplan §9.3). Only a subset is
# PRODUCIBLE by this collector today (the rest are dossier/read-time states
# computed in engine/china_intel_hub.py, or reserved for a later stage):
#   ok               — last run read the filings store and derived cleanly.
#   no_coverage      — no successful run has EVER completed (coverage_start unset).
#   source_failure   — the filings store exists but could not be read
#                       (corrupt / schema drift) — LOUD, never silently a quiet tape.
#   upstream_degraded — (P1-R1) producible when the SAME-RUN china_filings
#                       refresh failed entirely or lost an exchange
#                       (collectors.china_filings.LAST_RUN_OUTCOME.ok is
#                       False). Derived rows (positive evidence) are still
#                       kept — a degraded refresh never discards a real
#                       filing — but the run advances no absence evidence
#                       (last_success_utc stays frozen, coverage_start is not
#                       stamped) and the dossier must never read
#                       measured_no_event from it. (P1-R2) ALSO producible
#                       when this run's own account_candidates() typed-
#                       excludes >=1 candidate on a malformed announcementId
#                       — reused rather than a new fifth state, because
#                       engine/china_intel_hub.py's _visit_block() diverts a
#                       no-rows name away from measured_no_event on the
#                       LITERAL status string "upstream_degraded" only; a new
#                       state would fall through that check and render as a
#                       clean measured absence — the exact silent conversion
#                       this repair exists to prevent. When both causes fire
#                       in the same run, one record's detail names BOTH.
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

    refresh() uses `represented + typed_exclusions == eligible` as its
    mechanical accounting identity — this function is what makes that
    identity meaningful rather than tautological.
    """
    rows: list[dict] = []
    exclusions_by_type: dict[str, int] = {}
    excluded_identities: list[str] = []
    for f in candidates:
        anomaly = key_anomaly(f.get("announcementId"))
        if anomaly is None:
            rows.append(_derive_row(f, system_recorded_at))
        else:
            exclusions_by_type[anomaly] = exclusions_by_type.get(anomaly, 0) + 1
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

        n_new = write_visits(accounting["rows"])
        candidates_n = len(candidates)
        accounting_receipt = {
            "eligible": accounting["eligible"],
            "represented_downstream": accounting["represented"],
            "typed_exclusions": accounting["typed_exclusions"],
            "exclusions_by_type": accounting["exclusions_by_type"],
        }

        # Cause composition (P1-R2 §C.6): a same-run china_filings refresh
        # that was itself degraded, and this run's own typed exclusions, are
        # TWO DISTINCT causes of "this run proves no absence" — when both
        # fire, the single upstream_degraded record must name both, never
        # let one cause's sentence stand in for the other.
        causes: list[str] = []
        if same_run_outcome is not None and not same_run_outcome.get("ok"):
            errors = same_run_outcome.get("errors") or []
            causes.append(
                "derived over a DEGRADED same-run china_filings refresh "
                f"({'; '.join(errors)})"
            )
        if accounting["typed_exclusions"]:
            causes.append(
                f"{accounting['typed_exclusions']} candidate row(s) this run "
                f"excluded on malformed announcementId ({accounting['exclusions_by_type']})"
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
