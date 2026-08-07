"""Contract guard for the Company Intelligence golden corpus (R0-D).

The corpus exists to grade Wave 1.  A benchmark that CLAIMS coverage it does not
have is worse than no benchmark at all, so every number the manifest advertises is
recomputed here from the case index itself — never read back from a declared count
and never hardcoded in this file.

Companion suite: ``tests/test_company_intelligence_golden_corpus_replay.py`` byte-
replays the receipts and round-trips the v1 payloads through the real validators.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from engine.company_intelligence.contracts import event_key as cie_event_key
from engine.company_intelligence.contracts import stable_event_id
from engine.earnings_narrative.contracts import event_key as narrative_event_key

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "research/company_intelligence/GOLDEN_CORPUS_MANIFEST.json"
BUILDER_PATH = ROOT / "scripts/research/build_company_intelligence_golden_corpus.py"
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "company_intelligence"

REQUIRED_ISSUERS = 100
REQUIRED_DIFFICULT_EVENTS = 200

# The classes the R0-D ticket names, verbatim in intent.  ``edgar_identity_join`` is
# the estate finding the ticket asks the corpus to carry as a first-class class.
TICKETED_CLASSES = frozenset({
    "fiscal_year_ambiguity", "amendment", "duplicate_release", "share_class",
    "dual_listing", "gaap_vs_non_gaap", "units_currency", "bank_basis",
    "insurer_basis", "reit_basis", "missing_transcript", "missing_release",
    "pdf_table", "changed_slide_family", "speaker_role_error",
    "future_dated_quarantine", "edgar_identity_join",
})

EXPECTED_OUTCOMES = frozenset({"exact_receipt", "typed_absence", "quarantined", "duplicate_collapsed"})


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cases(manifest: dict) -> list[dict]:
    return manifest["cases"]


# ─────────────────────────────────────────────────────────────────────────────
# Authority.  Benchmark material ranks nothing, sizes nothing, gates nothing.
# ─────────────────────────────────────────────────────────────────────────────

def test_manifest_declares_benchmark_authority(manifest: dict) -> None:
    assert manifest["schema"] == "company_intelligence.golden_corpus/v1"
    assert manifest["authority"] == "context_only"
    assert manifest["research_only"] is True
    for flag in ("may_rank", "may_size", "may_gate", "may_alert"):
        assert manifest[flag] is False, f"{flag} must be false on benchmark material"
    assert manifest["generated_utc"].endswith("+00:00")


def test_manifest_states_provenance_and_limitations(manifest: dict) -> None:
    note = manifest["note"]
    assert "SYNTHETIC" in note and "no " in note.lower()
    # The rights constraint is not decoration: it is why the corpus stores hashes.
    assert "third-party" in note
    assert len(manifest["limitations"]) >= 4
    assert manifest["wave1_open_questions"]


# ─────────────────────────────────────────────────────────────────────────────
# Size.  Recomputed from the case index, never trusted from a declared count.
# ─────────────────────────────────────────────────────────────────────────────

def test_corpus_meets_its_own_stated_size(manifest: dict, cases: list[dict]) -> None:
    issuers = {case["issuer_id"] for case in cases}
    difficult = [case for case in cases if case["difficult"] is True]

    assert len(issuers) >= REQUIRED_ISSUERS, (
        f"corpus covers {len(issuers)} issuers, R0-D requires >= {REQUIRED_ISSUERS}"
    )
    assert len(difficult) >= REQUIRED_DIFFICULT_EVENTS, (
        f"corpus carries {len(difficult)} difficult events, R0-D requires >= {REQUIRED_DIFFICULT_EVENTS}"
    )
    assert manifest["required_minimums"] == {
        "issuers": REQUIRED_ISSUERS, "difficult_events": REQUIRED_DIFFICULT_EVENTS,
    }


def test_declared_counts_match_the_case_index(manifest: dict, cases: list[dict]) -> None:
    """A manifest that advertises coverage it does not have is the failure this lane prevents."""
    counts = manifest["counts"]
    assert counts["cases"] == len(cases)
    assert counts["issuers_with_cases"] == len({case["issuer_id"] for case in cases})
    assert counts["difficult_events"] == sum(1 for case in cases if case["difficult"])
    assert counts["distinct_event_ids"] == len({case["event_id_company_intelligence"] for case in cases})
    assert counts["cases_with_exact_span_receipt"] == sum(1 for case in cases if case["receipt"] is not None)
    assert counts["by_difficulty_class"] == dict(Counter(case["difficulty_class"] for case in cases))
    observed_outcomes = Counter(case["expected_v2_outcome"] for case in cases)
    assert counts["by_expected_v2_outcome"] == {
        outcome: observed_outcomes.get(outcome, 0) for outcome in sorted(EXPECTED_OUTCOMES)
    }


def test_every_ticketed_difficulty_class_has_at_least_one_case(manifest: dict, cases: list[dict]) -> None:
    observed = Counter(case["difficulty_class"] for case in cases)
    missing = sorted(TICKETED_CLASSES - set(observed))
    assert not missing, f"difficulty classes with zero cases: {missing}"
    undeclared = sorted(set(observed) - set(manifest["difficulty_classes"]))
    assert not undeclared, f"cases use classes the manifest never declares: {undeclared}"
    for name, block in manifest["difficulty_classes"].items():
        assert block["case_count"] == observed[name], f"{name} case_count is stale"
        assert block["definition"].strip()
        assert block["default_expected_v2_outcome"] in EXPECTED_OUTCOMES


# ─────────────────────────────────────────────────────────────────────────────
# Integrity.  A stale hash must go red.
# ─────────────────────────────────────────────────────────────────────────────

def test_every_fixture_hash_matches_the_file_on_disk(manifest: dict) -> None:
    assert manifest["fixtures"], "manifest lists no fixtures"
    for relative, block in manifest["fixtures"].items():
        path = ROOT / relative
        assert path.is_file(), f"manifest names a missing fixture: {relative}"
        blob = path.read_bytes()
        assert sha256(blob).hexdigest() == block["sha256"], f"stale sha256 for {relative}"
        assert len(blob) == block["bytes"], f"stale byte count for {relative}"
        # Prove the comparison is byte-sensitive rather than vacuously true.
        assert sha256(blob + b"\x00").hexdigest() != block["sha256"]


def test_manifest_records_the_builder_that_produced_it(manifest: dict) -> None:
    builder = manifest["builder"]
    assert builder["path"] == "scripts/research/build_company_intelligence_golden_corpus.py"
    assert builder["deterministic"] is True
    assert sha256(BUILDER_PATH.read_bytes()).hexdigest() == builder["sha256"], (
        "the builder changed without the corpus being rebuilt — run "
        "`python3 scripts/research/build_company_intelligence_golden_corpus.py`"
    )


def test_committed_corpus_is_exactly_what_the_builder_produces() -> None:
    """Reproducibility is the whole claim of a frozen benchmark."""
    proc = subprocess.run(
        [sys.executable, str(BUILDER_PATH), "--check"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=300,
    )
    assert proc.returncode == 0, f"corpus is stale:\n{proc.stdout}\n{proc.stderr}"


# ─────────────────────────────────────────────────────────────────────────────
# The two id schemes, reconciled.  A change to either minting function goes red here.
# ─────────────────────────────────────────────────────────────────────────────

def test_both_event_id_schemes_are_recomputed_from_the_same_triple(cases: list[dict]) -> None:
    for case in cases:
        ticker, year, quarter = case["ticker"], case["fiscal_year"], case["fiscal_quarter"]

        assert case["event_key_company_intelligence"] == cie_event_key(ticker, year, quarter), case["case_id"]
        assert case["event_id_company_intelligence"] == stable_event_id(
            ticker, year, quarter, case["call_date"]
        ), case["case_id"]

        assert case["transcript_id"] == f"{year}Q{quarter}"
        assert case["event_key_earnings_narrative"] == narrative_event_key(
            {"ticker": ticker, "transcript_id": case["transcript_id"]}
        ), case["case_id"]

        # The reconciliation itself: both keys are projections of one triple.
        assert case["event_key_company_intelligence"] == f"{ticker}|{year}|Q{quarter}"
        assert case["event_key_earnings_narrative"] == f"{ticker}/{year}Q{quarter}"


def test_event_ids_stay_stable_when_a_provider_re_dates_the_call(cases: list[dict]) -> None:
    """``call_date`` is accepted but deliberately unhashed — the correction-stability property."""
    for case in cases:
        redated = stable_event_id(
            case["ticker"], case["fiscal_year"], case["fiscal_quarter"], "1999-01-01"
        )
        assert redated == case["event_id_company_intelligence"], case["case_id"]
        assert case["expected_event_identity"] == "preserved"


def test_every_case_is_a_distinct_event(cases: list[dict]) -> None:
    ids = [case["event_id_company_intelligence"] for case in cases]
    assert len(set(ids)) == len(ids), "two cases collide on one event id"
    triples = [(c["ticker"], c["fiscal_year"], c["fiscal_quarter"]) for c in cases]
    assert len(set(triples)) == len(triples)
    for case in cases:
        assert case["event_id_company_intelligence"].startswith("cie_")
        assert len(case["event_id_company_intelligence"]) == len("cie_") + 24


# ─────────────────────────────────────────────────────────────────────────────
# What Wave 1 is graded on
# ─────────────────────────────────────────────────────────────────────────────

def test_every_case_names_the_outcome_that_replaces_the_v1_invariant(cases: list[dict]) -> None:
    for case in cases:
        # v1 hard-codes this to True for every event (contracts.py:501-502).
        assert case["v1_claim_citations_pending"] is True, case["case_id"]
        assert case["expected_v2_outcome"] in EXPECTED_OUTCOMES, case["case_id"]
    observed = {case["expected_v2_outcome"] for case in cases}
    assert observed == EXPECTED_OUTCOMES, f"outcome vocabulary is not exercised: {sorted(EXPECTED_OUTCOMES - observed)}"


def test_absent_sources_never_promise_an_exact_receipt(cases: list[dict]) -> None:
    for case in cases:
        if not case["transcript_present"]:
            assert case["receipt"] is None, case["case_id"]
            assert case["expected_v2_outcome"] in {"typed_absence", "quarantined"}, case["case_id"]
        if case["expected_v2_outcome"] != "exact_receipt":
            assert case["receipt"] is None, (
                f"{case['case_id']} expects {case['expected_v2_outcome']} but ships a receipt"
            )


def test_a_receipt_is_only_committed_where_its_locator_kind_exists_in_code(manifest: dict, cases: list[dict]) -> None:
    """A text-span receipt on a PDF-table case would assert the number lives in prose."""
    declared = set(manifest["expected_receipt_locator_kinds"])
    assert declared == {"text_span", "table_cell", "slide_region"}
    observed: Counter[str] = Counter()
    for case in cases:
        kind = case["expected_receipt_locator_kind"]
        if case["expected_v2_outcome"] == "exact_receipt":
            assert kind in declared, case["case_id"]
            observed[kind] += 1
        else:
            assert kind is None, case["case_id"]
        # Only text_span is expressible with the receipt shape that exists today.
        assert (case["receipt"] is not None) == (kind == "text_span" and case["transcript_present"]), case["case_id"]
    assert observed["table_cell"] and observed["slide_region"], (
        "the corpus must declare receipt shapes Wave 1 has to build, not only the one that exists"
    )
    assert manifest["counts"]["by_expected_receipt_locator_kind"] == {
        kind: observed.get(kind, 0) for kind in ("text_span", "table_cell", "slide_region")
    }


def test_every_quarantined_case_proves_its_own_violation(manifest: dict, cases: list[dict]) -> None:
    """A class that is only a label cannot grade the behaviour it exists to grade."""
    observed_at = datetime.fromisoformat(manifest["observation_time"]["observed_at"])
    quarantined = 0
    for case in cases:
        block = case["quarantine"]
        if case["expected_v2_outcome"] != "quarantined":
            assert block is None, case["case_id"]
            continue
        assert block is not None, f"{case['case_id']} is quarantined with no evidence"
        assert block["observed_at"] == manifest["observation_time"]["observed_at"]
        stamped = datetime.fromisoformat(block["record_timestamp"])
        assert stamped > observed_at, (
            f"{case['case_id']} claims quarantine but its record is not future-dated"
        )
        assert block["offending_field"] and block["reason"]
        quarantined += 1
    assert quarantined == manifest["counts"]["by_expected_v2_outcome"]["quarantined"]
    assert quarantined > 0


def test_future_dated_cases_are_dated_after_the_observation_time(manifest: dict, cases: list[dict]) -> None:
    observed_date = manifest["observation_time"]["observed_at"][:10]
    future = [case for case in cases if case["difficulty_class"] == "future_dated_quarantine"]
    assert future
    for case in future:
        assert case["call_date"] > observed_date, case["case_id"]
        assert case["quarantine"]["offending_field"] == "event.call_date"
    # The inverse must hold too, or the class is not isolating anything.
    for case in cases:
        if case["difficulty_class"] != "future_dated_quarantine":
            assert case["call_date"] <= observed_date, case["case_id"]


def test_duplicate_and_amendment_cases_carry_a_second_revision(cases: list[dict]) -> None:
    for case in cases:
        revisions = case["document_revisions"]
        assert revisions and revisions[0]["supersedes_source_sha256"] is None
        if case["difficulty_class"] in {"amendment", "duplicate_release"}:
            assert len(revisions) == 2, case["case_id"]
            # Story-level correction lineage requires a CHANGED body hash (story.py:506-522).
            assert revisions[1]["source_sha256"] != revisions[0]["source_sha256"]
            assert revisions[1]["supersedes_source_sha256"] == revisions[0]["source_sha256"]


def test_every_duplicate_collapsed_case_proves_its_own_duplicate(
    manifest: dict, cases: list[dict]
) -> None:
    """An outcome assigned by POSITION rather than by evidence cannot be graded.

    The defect this pins: the builder once labelled two ``edgar_identity_join``
    cases (CIE-GC-0227, CIE-GC-0234) ``duplicate_collapsed`` off an
    ``index % 7 == 6`` rule, while their rows carried ONE ``release`` revision and
    no observable duplication at all — structurally identical to the twelve
    siblings expecting ``typed_absence``.  Only the answer key could separate them.
    This assertion is keyed on the OUTCOME rather than the difficulty class, which
    is precisely why ``test_duplicate_and_amendment_cases_carry_a_second_revision``
    (class-keyed, and still the right test for what it covers) could not see it.
    """
    collapsed = 0
    for case in cases:
        if case["expected_v2_outcome"] != "duplicate_collapsed":
            continue
        revisions = case["document_revisions"]
        assert len(revisions) >= 2, (
            f"{case['case_id']} expects duplicate_collapsed carrying {len(revisions)} "
            "revision(s) — with no second document there is no duplicate to collapse"
        )
        assert revisions[1]["document_kind"] == "release_duplicate", case["case_id"]
        assert revisions[1]["source_sha256"] != revisions[0]["source_sha256"], case["case_id"]
        assert revisions[1]["supersedes_source_sha256"] == revisions[0]["source_sha256"], case["case_id"]
        collapsed += 1
    assert collapsed == manifest["counts"]["by_expected_v2_outcome"]["duplicate_collapsed"]
    assert collapsed > 0


def test_share_class_and_dual_listing_cases_actually_span_sibling_symbols(cases: list[dict]) -> None:
    """The id-inflation finding must be EXERCISED, not merely asserted in prose."""
    for difficulty in ("share_class", "dual_listing"):
        by_issuer: dict[str, set[str]] = {}
        for case in cases:
            if case["difficulty_class"] == difficulty:
                by_issuer.setdefault(case["issuer_id"], set()).add(case["ticker"])
        spanning = [issuer for issuer, tickers in by_issuer.items() if len(tickers) > 1]
        assert spanning, f"no {difficulty} issuer carries more than one symbol"
        for issuer in spanning:
            ids = {
                case["event_id_company_intelligence"] for case in cases
                if case["issuer_id"] == issuer and case["difficulty_class"] == difficulty
            }
            # One issuer, several listings, several event ids: the reason Wave 1 must
            # key the canonical event on the ISSUER.
            assert len(ids) > 1


# ─────────────────────────────────────────────────────────────────────────────
# Estate findings recorded as machine-readable known limits
# ─────────────────────────────────────────────────────────────────────────────

def test_known_limits_record_the_estate_findings(manifest: dict) -> None:
    keys = {row["key"] for row in manifest["known_limits"]}
    for required in (
        "status-vocabularies-are-inline-set-literals",
        "blocked-rights-does-not-exist-in-code",
        "claim-citations-pending-is-a-hard-v1-invariant",
        "edgar-readers-capture-disjoint-keys",
        "both-id-schemes-are-ticker-keyed",
    ):
        assert required in keys, f"known_limits is missing {required}"
    for row in manifest["known_limits"]:
        assert row["finding"].strip() and row["wave1_implication"].strip()


def test_blocked_rights_is_never_used_as_if_it_existed(manifest: dict) -> None:
    """It is a planned Wave-7 value with no vocabulary in code today."""
    for case in manifest["cases"]:
        assert case["expected_v2_outcome"] != "blocked_rights"
    assert "blocked_rights" not in set(manifest["expected_v2_outcome_vocabulary"])


def test_issuer_registry_covers_every_case(cases: list[dict]) -> None:
    registry = json.loads((FIXTURE_ROOT / "golden_corpus_issuers.v1.json").read_text(encoding="utf-8"))
    by_id = {row["issuer_id"]: row for row in registry["issuers"]}
    assert registry["issuer_count"] == len(by_id)
    assert len(by_id) >= REQUIRED_ISSUERS
    for case in cases:
        issuer = by_id.get(case["issuer_id"])
        assert issuer is not None, f"{case['case_id']} names an unregistered issuer"
        assert case["ticker"] in {row["ticker"] for row in issuer["listings"]}, case["case_id"]
        assert case["fiscal_year_end_month"] == issuer["fiscal_year_end_month"]
