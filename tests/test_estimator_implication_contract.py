"""Contract + behavior tests for engine/estimator_implication.py (packet B-A-F10-4)."""
from __future__ import annotations

import copy
import importlib
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

import engine.estimator_implication as eimp
from engine.estimator_implication import (
    AUTHORITY_KEYS,
    ES_FAMILY,
    FORBIDDEN_KEYS,
    REPO_ROOT,
    SC_MODULE_PATH,
    ImplicationContractError,
    build_estimator_implications,
    compose_event_study_implication,
    compose_synthetic_control_implication,
    compute_payload_id,
    load_contract,
    sha256_file,
    validate_payload,
)
from engine.seasonality.event_study import UnregisteredSearchFamily


class _StubLedger:
    """A duck-typed ledger. Empty by default (refusal test); pass ``registered``
    to make it register specific families (positive-path test)."""

    def __init__(self, registered=()):
        self._registered = set(registered)

    def families(self):
        return list(self._registered)

    def effective_n(self, family):
        return 32 if family in self._registered else 0


def test_contract_file_is_a_valid_draft_2020_12_schema():
    Draft202012Validator.check_schema(load_contract())


def test_synthetic_control_payload_validates_against_the_contract():
    payload = compose_synthetic_control_implication()
    validate_payload(payload)


def test_provenance_names_the_producing_module_and_its_live_digest():
    payload = compose_synthetic_control_implication()
    assert payload["provenance"]["producing_module"] == "engine/synthetic_control.py"
    live_digest = sha256_file(REPO_ROOT / SC_MODULE_PATH)
    assert payload["provenance"]["producing_module_sha256"] == live_digest


@pytest.mark.parametrize("forbidden_key", sorted(FORBIDDEN_KEYS))
def test_contract_rejects_promotion_fields(forbidden_key):
    payload = compose_synthetic_control_implication()
    payload = copy.deepcopy(payload)
    payload[forbidden_key] = 1
    with pytest.raises((ImplicationContractError, ValidationError)):
        validate_payload(payload)


def test_contract_rejects_nested_promotion_field():
    payload = copy.deepcopy(compose_synthetic_control_implication())
    payload["point_estimate"]["rank"] = 1
    with pytest.raises(ValidationError):
        validate_payload(payload)


def test_unregistered_event_study_family_is_refused():
    with pytest.raises(UnregisteredSearchFamily):
        compose_event_study_implication(ledger=_StubLedger())


def test_registered_family_block_is_required_and_cannot_be_null():
    base = compose_synthetic_control_implication()

    missing = copy.deepcopy(base)
    del missing["registered_family"]
    with pytest.raises(ValidationError):
        validate_payload(missing)

    unregistered = copy.deepcopy(base)
    unregistered["registered_family"]["registered"] = False
    with pytest.raises(ValidationError):
        validate_payload(unregistered)


def test_null_values_carry_a_plain_word_null_reason_in_both_languages():
    # The SC payload's honest_n is fully populated (see
    # test_synthetic_control_honest_n_is_populated_from_the_artifact below); the
    # event-study positive path is where a real null (its t-statistic) shows up,
    # so that is what exercises the plain-word bilingual null_reasons contract.
    stub = _StubLedger(registered=[ES_FAMILY])
    payload = compose_event_study_implication(ledger=stub)
    assert payload["uncertainty"][0]["value"] is None
    assert payload["null_reasons"], "expected at least one null_reasons entry"
    for nr in payload["null_reasons"]:
        assert nr["reason"]["en"].strip()
        assert nr["reason"]["zh"].strip()
        assert nr["detail"]["en"].strip()
        assert nr["detail"]["zh"].strip()


def test_synthetic_control_honest_n_is_populated_from_the_artifact():
    # sample_n is the fitted event-window observation count (n_fitted=303).
    # episode_n is the monthly-cluster count backing the reported CLUSTERED
    # t-stat (arm["n_months"]=52 in the pinned artifact) — the honest
    # episode-level denominator for a clustered standard error, never the raw
    # event count (n_events=361), which would overstate the clustering's
    # effective precision. Neither field is left null under an untrue reason.
    payload = compose_synthetic_control_implication()
    assert payload["honest_n"]["sample_n"] == 303
    assert payload["honest_n"]["episode_n"] == 52
    assert "monthly cluster" in payload["honest_n"]["basis"]["en"]
    assert payload["honest_n"]["basis"]["zh"].strip()


def test_episode_n_never_exceeds_sample_n_for_any_emitted_payload():
    # Regression (round-4 review, MAJOR): honest_n.episode_n must never
    # exceed honest_n.sample_n -- a fabricated denominator would overstate
    # the honest episode-level precision. Exercised against every payload the
    # composer can actually emit today (the default envelope) AND against the
    # event-study's hypothetical positive-compose path (a test-registered
    # ledger), since that path is not reachable through the default envelope
    # while the real ledger leaves the family unregistered.
    envelope = build_estimator_implications()
    for payload in envelope["payloads"]:
        sample_n = payload["honest_n"]["sample_n"]
        episode_n = payload["honest_n"]["episode_n"]
        assert episode_n is None or (sample_n is not None and episode_n <= sample_n), (
            f"{payload['estimator_id']}: episode_n={episode_n} exceeds "
            f"sample_n={sample_n}"
        )

    stub = _StubLedger(registered=[ES_FAMILY])
    es_payload = compose_event_study_implication(ledger=stub)
    sample_n = es_payload["honest_n"]["sample_n"]
    episode_n = es_payload["honest_n"]["episode_n"]
    assert episode_n is None or (sample_n is not None and episode_n <= sample_n)


def test_event_study_episode_n_is_null_never_fabricated_from_roster_add_events():
    # Regression (round-4 review, MAJOR): episode_n used to be the raw
    # roster_add_events count (466 in the pinned artifact), which exceeds
    # sample_n (the h=20 curve's 276 supporting observations, from
    # event_curve_announce["20"]) -- a fabricated, oversized denominator. The
    # artifact records how many roster-add events reach h=20 in aggregate
    # (276) but not WHICH distinct episodes those are, so episode_n must be
    # null with a plain, EN/ZH-paired reason naming both real counts -- never
    # a substitute (n_months is reserved for the OTHER (synthetic-control)
    # artifact's monthly-cluster t-stat denominator).
    stub = _StubLedger(registered=[ES_FAMILY])
    payload = compose_event_study_implication(ledger=stub)
    validate_payload(payload)

    assert payload["honest_n"]["sample_n"] == 276
    assert payload["honest_n"]["episode_n"] is None

    entry = next(nr for nr in payload["null_reasons"] if nr["code"] == "honest_n.episode_n")
    assert "466" in entry["detail"]["en"] and "276" in entry["detail"]["en"]
    assert "roster_add_events" not in entry["detail"]["en"],         "no raw Python/JSON identifier in a user-facing string"
    assert entry["reason"]["en"].strip() and entry["reason"]["zh"].strip()
    assert entry["detail"]["zh"].strip() and entry["detail"]["zh"] != entry["detail"]["en"]
    # Same facts as the EN detail: both real counts appear in the ZH text too
    # (parity), not merely a non-empty placeholder translation.
    assert "466" in entry["detail"]["zh"] and "276" in entry["detail"]["zh"]

    assert "roster_add_events" not in payload["honest_n"]["basis"]["en"]
    assert "roster_add_events" not in payload["honest_n"]["basis"]["zh"]


def test_unregistered_family_refusal_detail_has_en_zh_clause_parity():
    # Regression (round-4 review, MINOR-1): the refusal that actually fires
    # against the real pinned artifact today (unregistered_search_family) had
    # an EN detail with two clauses (never registered; so the multiple-testing
    # budget spent is unrecorded) but a ZH detail carrying only the first
    # clause -- same facts must appear in both languages, not a shortened
    # translation.
    envelope = build_estimator_implications()
    refusal = next(r for r in envelope["refusals"]
                   if r["refusal_code"] == "unregistered_search_family")
    detail = refusal["detail"]
    assert "trial ledger" in detail["en"] and "试验账本" in detail["zh"]
    assert "multiple-testing" in detail["en"]
    # The ZH clause naming the multiple-testing-budget consequence, not just
    # the registration fact.
    assert "多重检验" in detail["zh"],         "zh detail dropped the multiple-testing-budget clause the en detail carries"


def test_event_study_limitations_text_has_no_raw_identifiers_or_exception_names():
    # Regression (round-4 review, MINOR-2): the limitations text used to name
    # raw internal identifiers (family_id, engine.trial_ledger) and a Python
    # exception class name (UnregisteredSearchFamily) verbatim inside a
    # user-facing string with no separate `detail` field to relegate them
    # into. Plain words only, in both languages.
    stub = _StubLedger(registered=[ES_FAMILY])
    payload = compose_event_study_implication(ledger=stub)
    banned = ("family_id", "engine.trial_ledger", "UnregisteredSearchFamily",
              "FileNotFoundError", "ImplicationContractError", "Traceback")
    for lim in payload["limitations"]:
        for text in (lim["en"], lim["zh"]):
            for token in banned:
                assert token not in text, f"{token!r} leaked into limitations text: {text!r}"
        assert lim["zh"].strip() and lim["zh"] != lim["en"]


def test_diagnostics_zh_detail_is_a_genuine_translation_not_a_pointer():
    payload = compose_synthetic_control_implication()
    for d in payload["diagnostics"]:
        zh = d["detail"]["zh"]
        assert zh != "见 gate_eval.reasons", "zh detail must not be a raw pointer"
        assert len(zh) > 10
        assert zh != d["detail"]["en"]


def test_registered_event_study_family_composes_a_valid_payload():
    stub = _StubLedger(registered=[ES_FAMILY])
    payload = compose_event_study_implication(ledger=stub)
    validate_payload(payload)
    assert payload["estimator_id"] == "engine.seasonality.event_study"
    assert payload["registered_family"]["family_id"] == ES_FAMILY
    assert payload["registered_family"]["registered"] is True
    assert payload["selection"]["selection_id"]
    assert payload["uncertainty"] and "value" in payload["uncertainty"][0]
    assert payload["provenance"]["producing_module"] == "engine/seasonality/event_study.py"


def test_payload_id_is_deterministic_and_content_bound():
    payload = compose_synthetic_control_implication()
    recomputed = compute_payload_id(
        composer_version=payload["composer_version"],
        estimator_id=payload["estimator_id"],
        result_artifact_path=payload["provenance"]["result_artifact_path"],
        result_artifact_sha256=payload["provenance"]["result_artifact_sha256"],
        selection_id=payload["selection"]["selection_id"],
        family_id=payload["registered_family"]["family_id"],
        producing_module_sha256=payload["provenance"]["producing_module_sha256"],
    )
    assert recomputed == payload["payload_id"]

    mutated = compute_payload_id(
        composer_version=payload["composer_version"],
        estimator_id=payload["estimator_id"],
        result_artifact_path=payload["provenance"]["result_artifact_path"],
        result_artifact_sha256=payload["provenance"]["result_artifact_sha256"],
        selection_id="a-different-selection",
        family_id=payload["registered_family"]["family_id"],
        producing_module_sha256=payload["provenance"]["producing_module_sha256"],
    )
    assert mutated != payload["payload_id"]


def test_payload_id_is_bound_to_the_producing_module_digest():
    # Regression: compute_payload_id used to omit producing_module_sha256, so
    # editing engine/synthetic_control.py changed provenance while payload_id
    # stayed identical — the "content-bound digest" claim held only for the
    # artifact, never the producing module. Simulating a module edit (a
    # different sha256, holding every other field fixed) must change the id.
    payload = compose_synthetic_control_implication()
    same_module = compute_payload_id(
        composer_version=payload["composer_version"],
        estimator_id=payload["estimator_id"],
        result_artifact_path=payload["provenance"]["result_artifact_path"],
        result_artifact_sha256=payload["provenance"]["result_artifact_sha256"],
        selection_id=payload["selection"]["selection_id"],
        family_id=payload["registered_family"]["family_id"],
        producing_module_sha256=payload["provenance"]["producing_module_sha256"],
    )
    assert same_module == payload["payload_id"]

    edited_module = compute_payload_id(
        composer_version=payload["composer_version"],
        estimator_id=payload["estimator_id"],
        result_artifact_path=payload["provenance"]["result_artifact_path"],
        result_artifact_sha256=payload["provenance"]["result_artifact_sha256"],
        selection_id=payload["selection"]["selection_id"],
        family_id=payload["registered_family"]["family_id"],
        producing_module_sha256="0" * 64,
    )
    assert edited_module != payload["payload_id"]


def test_authority_block_is_exactly_five_literal_false_keys():
    payload = copy.deepcopy(compose_synthetic_control_implication())
    validate_payload(payload)  # sanity: base payload passes

    extra = copy.deepcopy(payload)
    extra["authority"]["extra_authority"] = False
    with pytest.raises(ValidationError):
        validate_payload(extra)

    flipped = copy.deepcopy(payload)
    flipped["authority"]["trading_authority"] = True
    with pytest.raises(ValidationError):
        validate_payload(flipped)

    assert set(AUTHORITY_KEYS) == {
        "forecast_authority", "ranking_authority", "gating_authority",
        "sizing_authority", "trading_authority",
    }


def test_null_reasons_must_be_named_by_the_exact_null_site_code():
    # Regression: validate_payload used to accept ANY non-empty null_reasons
    # array once at least one null existed anywhere, so a payload with four
    # nulls and one unrelated reason validated. Each null site now needs its
    # OWN entry named by its own code.
    stub = _StubLedger(registered=[ES_FAMILY])
    payload = compose_event_study_implication(ledger=stub)
    validate_payload(payload)  # sanity: the real payload's codes already match

    mismatched = copy.deepcopy(payload)
    mismatched["null_reasons"][0]["code"] = "a_completely_unrelated_code"
    with pytest.raises(ImplicationContractError, match="null_reasons entry"):
        validate_payload(mismatched)


def test_missing_gate_reason_gets_an_explicit_note_not_another_gates_prose():
    # Regression m4: a missing PC1/PC3/F1 reason in gate_eval.reasons used to
    # silently fall back to PC2's English prose while the ZH detail stayed
    # correct — a wrong caption plus an EN/ZH parity break. It must now be an
    # explicit "no reason recorded" note naming the actual missing gate.
    import json as _json

    root = REPO_ROOT
    data = _json.loads((root / eimp.SC_RESULT_PATH).read_text(encoding="utf-8"))
    del data["gate_eval"]["reasons"]["PC3"]

    orig_load_json = eimp._load_json

    def _patched(load_root, rel_path):
        if rel_path == eimp.SC_RESULT_PATH:
            return data
        return orig_load_json(load_root, rel_path)

    import unittest.mock as mock
    with mock.patch.object(eimp, "_load_json", side_effect=_patched):
        payload = compose_synthetic_control_implication()

    pc3 = next(d for d in payload["diagnostics"] if d["code"] == "PC3_sc_not_noisier")
    assert pc3["detail"]["en"] == "no PC3 reason recorded in gate_eval for this artifact"
    assert pc3["detail"]["zh"] != pc3["detail"]["en"]
    assert pc3["detail"]["zh"].strip()


def test_es_artifact_digest_mismatch_degrades_to_a_typed_refusal_not_a_crash(monkeypatch):
    # Regression m6: an ImplicationContractError (digest mismatch) or a
    # missing ES artifact used to propagate out of build_estimator_implications
    # and destroy the whole envelope, including the already-healthy SC
    # payload. It must instead degrade to a typed refusal for the event-study
    # estimator only.
    # _verify_digest for the ES artifact runs BEFORE the family-registration
    # check (see compose_event_study_implication), so the real default ledger
    # (which registers SC's own family but not ES's) is enough here — the
    # digest mismatch must fire first regardless of ES family registration.
    monkeypatch.setattr(eimp, "ES_RESULT_SHA256", "0" * 64)
    envelope = build_estimator_implications()

    sc_payloads = [p for p in envelope["payloads"] if p["estimator_id"] == "engine.synthetic_control"]
    assert len(sc_payloads) == 1, "a healthy SC payload must survive an ES artifact failure"

    es_refusals = [r for r in envelope["refusals"] if r["estimator_id"] == "engine.seasonality.event_study"]
    assert len(es_refusals) == 1
    assert es_refusals[0]["refusal_code"] == "artifact_unavailable"
    assert es_refusals[0]["detail"]["en"].strip()
    assert es_refusals[0]["detail"]["zh"].strip()


def test_es_contract_validation_failure_is_not_swallowed_as_artifact_unavailable(monkeypatch):
    # Regression (round-2 review, MAJOR): the earlier m6 fix widened the try
    # in build_estimator_implications to enclose BOTH
    # compose_event_study_implication AND validate_payload(es_payload),
    # catching (ImplicationContractError, FileNotFoundError) around both.
    # validate_payload raises ImplicationContractError for every genuine
    # contract violation it owns (forbidden promotion field, payload_id
    # mismatch, missing null-reason pairing, non-false authority block) --
    # so a composer bug that produced a payload carrying a forbidden
    # promotion field no longer raised: it degraded to a typed
    # "artifact_unavailable" refusal and the caller saw a successful build,
    # defeating the promotion firewall at this module's only public entry
    # point. validate_payload must sit OUTSIDE the try, so its raise
    # propagates exactly like the SC payload's validate_payload already does.
    stub = _StubLedger(registered=[eimp.SC_FAMILY, ES_FAMILY])

    def _bad_compose(root=REPO_ROOT, *, ledger=None, family_id=ES_FAMILY):
        payload = copy.deepcopy(
            compose_event_study_implication(root, ledger=ledger, family_id=family_id)
        )
        payload["rank"] = 1  # forbidden promotion field injected by a hypothetical bug
        return payload

    monkeypatch.setattr(eimp, "compose_event_study_implication", _bad_compose)
    with pytest.raises((ImplicationContractError, ValidationError)):
        build_estimator_implications(ledger=stub)


def test_es_digest_mismatch_refusal_detail_has_no_raw_exception_text_and_real_zh(monkeypatch):
    # Regression (round-2 review, minor): the refusal's detail.en used to
    # interpolate the caught Python exception verbatim (f"({exc})"), leaking
    # internal field names/paths into a user-facing string, while detail.zh
    # was a fixed generic sentence with no corresponding content -- breaking
    # EN/ZH parity. Both languages must now be genuine, content-matched
    # translations with no raw exception text.
    monkeypatch.setattr(eimp, "ES_RESULT_SHA256", "0" * 64)
    envelope = build_estimator_implications()
    es_refusals = [r for r in envelope["refusals"] if r["estimator_id"] == "engine.seasonality.event_study"]
    assert len(es_refusals) == 1
    detail = es_refusals[0]["detail"]
    assert "expected" not in detail["en"] and "observed" not in detail["en"], \
        "detail.en must not leak the raw digest-mismatch exception text"
    assert eimp.ES_RESULT_SHA256 not in detail["en"]
    assert detail["zh"].strip() and detail["zh"] != detail["en"]


def test_diagnostic_null_passed_requires_its_own_null_reasons_entry():
    # Regression (round-2 review, minor): diagnostics[].passed is a nullable
    # spot in the schema (["boolean", "null"]) but validate_payload's
    # nullable_spots list never covered it, so a diagnostic with passed=None
    # validated with no null_reasons disclosure at all.
    payload = copy.deepcopy(compose_synthetic_control_implication())
    payload["diagnostics"][0]["passed"] = None
    # A null diagnostics[].passed with an empty null_reasons array is now
    # rejected at the SCHEMA level too (minor #2's null-pairing floor), so
    # this can raise either there or in validate_payload's own by-code check
    # -- both are the fix, whichever fires first.
    with pytest.raises((ImplicationContractError, ValidationError)):
        validate_payload(payload)

    # Adding the matching entry (named by that diagnostic's own code) fixes it.
    fixed = copy.deepcopy(payload)
    fixed["null_reasons"].append({
        "code": fixed["diagnostics"][0]["code"],
        "reason": {"en": "test reason", "zh": "测试原因"},
        "detail": {"en": "test detail", "zh": "测试详情"},
    })
    validate_payload(fixed)


def test_schema_itself_rejects_a_null_with_empty_null_reasons():
    # Regression (round-2 review, minor): the shipped schema did not itself
    # carry the null-pairing rule -- enforcement lived only in Python, so a
    # consumer validating against the schema alone (never calling
    # validate_payload) accepted a payload with a null and an empty
    # null_reasons array. This exercises the schema DIRECTLY via
    # Draft202012Validator, bypassing validate_payload's Python checks.
    stub = _StubLedger(registered=[ES_FAMILY])
    payload = copy.deepcopy(compose_event_study_implication(ledger=stub))
    assert payload["uncertainty"][0]["value"] is None
    payload["null_reasons"] = []
    with pytest.raises(ValidationError):
        Draft202012Validator(load_contract()).validate(payload)


def test_composer_performs_no_writes_and_no_network():
    source = (REPO_ROOT / "engine" / "estimator_implication.py").read_text(encoding="utf-8")
    assert not re.search(r'open\([^)]*["\']w', source)
    assert not re.search(r'open\([^)]*["\']a', source)
    assert ".write_text(" not in source
    assert ".write_bytes(" not in source
    assert "os.write(" not in source
    for banned_import in (
        "import requests", "import urllib", "import httpx", "import socket",
        "import http.client", "from http import client",
        "from urllib.request import", "from urllib import request",
    ):
        assert banned_import not in source
    # Every bare ``.open(...)`` call must carry an explicit read-only mode
    # ("rb"), an explicit text encoding (the stdlib default is "r"), or no
    # arguments at all — never a bare variable that could carry a
    # caller-supplied write mode, which the two checks above would miss.
    for call_args in re.findall(r"\.open\(([^)]*)\)", source):
        assert call_args == "" or '"rb"' in call_args or "'rb'" in call_args \
            or "encoding=" in call_args, f"ambiguous .open() mode: {call_args!r}"


def test_build_returns_a_typed_refusal_not_a_fabricated_payload():
    envelope = build_estimator_implications()
    assert envelope["schema"] == "mastermind.estimator_implications/v1"
    assert len(envelope["refusals"]) == 1
    refusal = envelope["refusals"][0]
    assert refusal["estimator_id"] == "engine.seasonality.event_study"
    assert refusal["refusal_code"] == "unregistered_search_family"
    assert refusal["detail"]["en"].strip()
    assert refusal["detail"]["zh"].strip()
    event_study_payloads = [p for p in envelope["payloads"]
                             if p["estimator_id"] == "engine.seasonality.event_study"]
    assert event_study_payloads == []
    sc_payloads = [p for p in envelope["payloads"] if p["estimator_id"] == "engine.synthetic_control"]
    assert len(sc_payloads) == 1


# This is the drift alarm for the two-payload risk named in the frozen spec:
# it must genuinely READ #6830's engine/research_implication_card.py (never a
# same-file literal pinned by hand, which can drift silently and prove
# nothing — that was M1 of the 2026-09-06 review round). #6830 (macro PR
# #6830, branch claude/f10-x1-implication-cards-20260904) is not merged to
# main yet, so the module does not exist here today; this test SKIPS with a
# named reason until it lands, rather than fabricating a stand-in comparison.
# TODO(#6830): once engine/research_implication_card.py merges to main, this
# skip must stop firing — if it still skips after that merge, the import path
# or module name below has drifted and needs fixing, not silencing.
def test_payload_keys_are_a_profile_of_research_implication_card_v1():
    try:
        ric = importlib.import_module("engine.research_implication_card")
    except ImportError:
        pytest.skip("A card module not on main yet (#6830)")

    payload = compose_synthetic_control_implication()
    b_top_keys = set(payload.keys())

    # A's real top-level key set, read from the module itself (the same
    # frozenset _require_keys(card, ..., "card") enforces there) — never a
    # hand-copied literal.
    card_top_keys = set(ric._CARD_KEYS)
    card_authority_keys = set(ric.AUTHORITY_KEYS)

    # Keys that are genuinely spelled the same at TOP LEVEL in both A and B.
    # "authority"'s five sub-keys are asserted separately below, nested under
    # "authority" in both — never unioned into this flat set, which is
    # exactly the trick that let the old literal claim a flat placement A
    # never uses.
    shared_top_level_spelling_keys = frozenset({
        "quality", "null_reasons", "limitations", "diagnostics", "uncertainty",
    })
    for key in shared_top_level_spelling_keys:
        assert key in card_top_keys, f"{key!r} drifted out of A's card vocabulary"
        assert key in b_top_keys, f"{key!r} missing from B's payload"

    # The five authority keys are nested under "authority" in BOTH A and B —
    # assert the real nesting, not a flat union that would paper over a drift.
    assert "authority" in card_top_keys, '"authority" missing from A\'s card'
    assert "authority" in b_top_keys, '"authority" missing from B\'s payload'
    assert card_authority_keys == set(AUTHORITY_KEYS), \
        "A's AUTHORITY_KEYS drifted from B's"
    assert set(payload["authority"].keys()) == card_authority_keys

    # B's own id/version/point-estimate keys are deliberately renamed (see
    # module docstring); assert the rename against A's REAL spelling, never an
    # accidental collision. A uses "outputs" and never "point_estimate"; B
    # uses "point_estimate" and never "outputs".
    assert "payload_id" in b_top_keys and "card_id" not in b_top_keys
    assert "card_id" in card_top_keys
    assert "composer_version" in b_top_keys and "adapter_version" not in b_top_keys
    assert "adapter_version" in card_top_keys
    assert "point_estimate" in b_top_keys and "point_estimate" not in card_top_keys
    assert "outputs" in card_top_keys and "outputs" not in b_top_keys
    assert payload["schema"] != ric.CARD_SCHEMA
