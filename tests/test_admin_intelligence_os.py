"""tests/test_admin_intelligence_os.py — the Intelligence OS admin surface.

FIXTURE ROOTS ONLY, same law as the T4 suite this joins: nothing here reads the live
``config/synapse.yml`` or asserts anything about the live estate's health. The registry
took 69 commits in a trailing fortnight and "an artifact is stale tonight" is operational
data, not a PR defect — either would turn this lane into a nightly alarm about work the
operator has not done yet.

THE LOAD-BEARING TEST IS :func:`test_reflectivity_a_new_engine_appears_with_no_code_edit`.
The panel is only worth having if the estate is its source: an engine added to the
registry must show up with no edit here, and one removed must disappear. A page that has
to be taught about each engine is a second registry wearing a dashboard's clothes, and it
goes wrong exactly when it matters — quietly, at the moment the estate changes.
"""
from __future__ import annotations

import ast
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from admin import intelligence_os as IOS  # noqa: E402

# Wall-clock relative: panel() uses datetime.now(), so a frozen 2026-08-14
# asof ages out of the 24h SLA the next calendar day and this suite becomes a
# nightly alarm. Keep FRESH 6h behind now, matching the T4 suite contract.
FRESH = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime(
    "%Y-%m-%dT%H:%M:%S+00:00"
)


# ---------------------------------------------------------------------------
# Fixture builders — adapted from tests/test_output_health.py
# ---------------------------------------------------------------------------

def artifact(
    path: str,
    *,
    producer: str,
    owner: str,
    consumers: tuple[str, ...] = (),
    asof_field: str | None = "asof",
    sla: int | None = 24,
    storage: str = "git",
    fmt: str = "json",
    **extra: object,
) -> dict:
    entry: dict = {
        "path": path,
        "format": fmt,
        "producer": producer,
        "owner_program": owner,
        "cadence": "daily-engine",
        "storage": storage,
        "asof_field": asof_field,
        "freshness_sla_hours": sla,
        "schema": "none",
        "tier": "display",
        "horizon_role": "context",
        "weights": "none",
        "consumers": list(consumers),
    }
    entry.update(extra)
    return entry


def _write_root(tmp_path: Path, artifacts: dict, overlay: dict | None = None) -> Path:
    """A checkout-shaped fixture: config/, the producer modules, the artifacts themselves.

    Deliberately NOT a git repo. Every artifact is materialized on disk, so the presence
    ladder answers from the worktree and the git half is never consulted — which keeps
    this suite off subprocess spawn entirely (the live estate walk costs minutes).
    """
    root = tmp_path / "estate"
    (root / "config").mkdir(parents=True, exist_ok=True)
    doc = {
        "meta": {
            "schema_version": 1,
            "description": "fixture",
            "tier_vocabulary": {},
            "article2_surfaces": [],
        },
        "artifacts": artifacts,
    }
    (root / "config" / "synapse.yml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    (root / "config" / "intelligence_registry_overlay.yml").write_text(
        yaml.safe_dump(overlay or {"engines": {}}), encoding="utf-8"
    )
    for entry in artifacts.values():
        producer = root / str(entry["producer"])
        producer.parent.mkdir(parents=True, exist_ok=True)
        producer.write_text("", encoding="utf-8")
        target = root / str(entry["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"asof": FRESH}), encoding="utf-8")
    return root


def one_engine(tmp_path: Path, **kw) -> Path:
    return _write_root(
        tmp_path,
        {"a": artifact("data/a.json", producer="engine/a.py", owner="prog-one")},
        **kw,
    )


@pytest.fixture(autouse=True)
def _clean_cache():
    """Every test starts cold. The panel cache is module-level and keyed on mtimes, and
    two tmp_path roots minted in the same nanosecond would otherwise share an entry."""
    IOS._CACHE.clear()
    yield
    IOS._CACHE.clear()


def _tree(root: Path) -> dict[str, tuple[int, int]]:
    """path -> (size, mtime_ns) for every file under *root*."""
    return {
        p.relative_to(root).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# ---------------------------------------------------------------------------
# The reflectivity gate
# ---------------------------------------------------------------------------

def test_reflectivity_a_new_engine_appears_with_no_code_edit(tmp_path):
    """Add an engine to the registry -> it is on the page. Remove it -> it is gone.

    BOTH directions, because only one of them is the failure mode people notice. A page
    that never learns about a new engine looks empty and gets investigated; a page that
    keeps rendering a DELETED one looks healthy and does not.
    """
    root = _write_root(
        tmp_path,
        {"a": artifact("data/a.json", producer="engine/a.py", owner="prog-one")},
    )
    before = IOS.panel(root=root)
    assert before["ok"] is True
    ids_before = {r["engine_id"] for r in before["engines"]}
    assert ids_before == {"engine/a.py::prog-one"}
    assert before["census"]["engines"] == 1
    assert before["census"]["artifacts"] == 1

    # --- the estate grows, the module does not ---------------------------
    root = _write_root(
        tmp_path,
        {
            "a": artifact("data/a.json", producer="engine/a.py", owner="prog-one"),
            "z": artifact("data/z.json", producer="engine/z.py", owner="prog-two"),
        },
    )
    after = IOS.panel(root=root, force=True)
    ids_after = {r["engine_id"] for r in after["engines"]}
    assert ids_after == {"engine/a.py::prog-one", "engine/z.py::prog-two"}
    assert after["census"]["engines"] == 2
    assert after["census"]["artifacts"] == 2
    grown = next(r for r in after["engines"] if r["engine_id"] == "engine/z.py::prog-two")
    assert grown["owner_program"] == "prog-two"
    assert grown["producer"] == "engine/z.py"
    assert grown["n_artifacts"] == 1

    # --- and it shrinks again --------------------------------------------
    root = _write_root(
        tmp_path,
        {"a": artifact("data/a.json", producer="engine/a.py", owner="prog-one")},
    )
    shrunk = IOS.panel(root=root, force=True)
    assert {r["engine_id"] for r in shrunk["engines"]} == {"engine/a.py::prog-one"}
    assert shrunk["census"]["engines"] == 1


def test_output_class_is_null_for_an_uncurated_engine(tmp_path):
    """No adjudication in the overlay -> ``None``, never a guess.

    The panel joins T1's overlay and nothing else. Inferring a class from tier, authority
    or the producer's name would turn a census row into an authority claim, which is the
    one thing this surface is not allowed to mint.
    """
    root = one_engine(tmp_path)
    panel = IOS.panel(root=root)
    row = panel["engines"][0]
    assert row["output_class"] is None
    assert panel["census"]["by_output_class"] == {"null": 1}

    detail = IOS.engine_detail("engine/a.py::prog-one", root=root)
    assert detail["ok"] is True
    assert detail["engine"]["output_class"] is None
    assert detail["outputs"][0]["output_class"] is None


def test_a_curated_output_class_is_passed_through_verbatim(tmp_path):
    """The other half of the null test: when the overlay HAS adjudicated a class, the
    panel must show that class and its rationale — otherwise "always None" would pass the
    test above while the join was simply broken."""
    root = _write_root(
        tmp_path,
        {"a": artifact("data/a.json", producer="engine/a.py", owner="prog-one")},
        overlay={
            "engines": {
                "engine/a.py::prog-one": {
                    "output_class": {
                        "value": "state_estimate",
                        "rationale": "fixture adjudication",
                    }
                }
            }
        },
    )
    panel = IOS.panel(root=root)
    assert panel["engines"][0]["output_class"] == "state_estimate"
    detail = IOS.engine_detail("engine/a.py::prog-one", root=root)
    assert detail["engine"]["output_class"] == "state_estimate"
    assert "fixture adjudication" in (detail["engine"]["output_class_rationale"] or "")


# ---------------------------------------------------------------------------
# A1 evidence disposition — pure, deterministic, and owner-bounded
# ---------------------------------------------------------------------------

def evidence_cell(**overrides: object) -> dict:
    """A complete T1-shaped cell for the A1 pure-derivation tests."""
    cell: dict = {
        "engine_id": "engine/a.py::prog-one",
        "producer": "engine/a.py",
        "owner_program": "prog-one",
        "output_class": "predictive",
        "output_class_reason": "curated: fixture",
        "authority": "engine_input",
        "ledger": "data/a/theses.jsonl",
        "ledger_evidence": {
            "rule": 3,
            "desk": None,
            "shape": "store",
            "corpus_checked": False,
            "corpus_rows": None,
        },
        "graded_by_design": "yes",
        "graded_by_design_evidence": "strong",
        "graded_by_design_source": "derived: fixture owner ledger",
        "declared_horizon": {
            "horizon_role": ["context"],
            "horizon_role_homogeneous": True,
            "horizon_d": [21],
        },
        "validation_state": "phase0",
        "validation_state_evidence": {
            "bound_species": [],
            "reason": "no_species_bound",
        },
        "evidence_ref": ["fixture.prereg"],
    }
    cell.update(overrides)
    return cell


def healthy_output(**overrides: object) -> dict:
    output: dict = {
        "artifact_id": "a",
        "state": "healthy",
        "assessment_status": "complete",
        "reason_codes": [],
    }
    output.update(overrides)
    return output


def qledger_provider(**row_overrides: object) -> dict:
    row: dict = {
        "n_dates": 7,
        "needed": 25,
        "ready": False,
        "approaching": False,
        "projected_ready_date": "2026-09-30",
        "reason": "7 independent dates; evidence still accruing",
        "clock_basis": "explicit_unit_v1:trading_days:US",
        "clock_migration": False,
        "clock_prior_n_dates": {},
        "evidence_basis": "benchmark",
        "control_coverage": None,
        "n_cohort_dates": None,
        "n_controlled_dates": None,
        "cohort_rowless": {},
        "control_clock_start": None,
        "unclassified": False,
    }
    row.update(row_overrides)
    return {
        "kind": "qledger",
        "binding": "direct:qledger:fixture",
        "family": "fixture",
        "read_status": "ok",
        "clock_start": {
            "claim_family": "fixture",
            "first_prospective_registration_utc": "2026-08-20T01:02:03+00:00",
            "declared_horizon_d": 21,
            "horizon_unit": "trading_days",
            "git_sha": "abc123",
        },
        "readiness": {"21": row},
    }


def test_ceo_view_keeps_an_empty_validated_band_visible():
    """Removing empty bands would turn zero validated engines into an invisible omission."""
    view = IOS.build_ceo_view(
        [
            {"engine_id": "engine/z.py::p", "evidence_status": "Accruing"},
            {"engine_id": "engine/a.py::p", "evidence_status": "Accruing"},
        ]
    )

    assert [band["evidence_status"] for band in view] == [
        "Validated",
        "Accruing",
        "Ungraded by design",
        "Degraded",
        "Disproven",
    ]
    assert view[0] == {
        "evidence_status": "Validated",
        "n_engines": 0,
        "engine_ids": [],
    }
    assert view[1]["engine_ids"] == ["engine/a.py::p", "engine/z.py::p"]


def test_null_output_class_stays_null_and_cannot_be_validated():
    """A validated lifecycle may not fill an unknown metric contract with a guessed class."""
    cell = evidence_cell(output_class=None, validation_state="validated")
    result = IOS.derive_evidence_status(cell, [healthy_output()])

    assert cell["output_class"] is None
    assert result["evidence_status"] == "Accruing"
    assert "output_class_null" in result["evidence_reason_codes"]


def test_t1_null_output_class_cannot_be_backfilled_from_a_t4_record():
    """Even contradictory downstream bytes cannot overwrite T1's explicit null contract."""
    cell = evidence_cell(output_class=None, validation_state="validated")
    output = healthy_output(
        engine_id=cell["engine_id"], output_class="predictive", authority="engine_input"
    )

    rows = IOS._engine_rows(
        {"outputs": [output]}, {"engines": [cell], "excluded": []}, {}
    )

    assert rows[0]["output_class"] is None
    assert rows[0]["evidence_status"] == "Accruing"
    assert "output_class_null" in rows[0]["evidence_reason_codes"]


def test_panel_and_detail_keep_a_canonical_t1_cell_with_no_t4_outputs(
    monkeypatch, tmp_path
):
    """Every canonical T1 cell gets a disposition, including an explicit no-output failure."""
    cell = evidence_cell()
    view = {"outputs": [], "summary": {}, "generated": {}}
    registry = {"engines": [cell], "excluded": []}
    monkeypatch.setattr(
        IOS,
        "_derive",
        lambda root, force: (view, registry, {}, 0.0, "miss"),
    )

    panel = IOS.panel(root=tmp_path)
    assert panel["census"]["canonical_engines"] == 1
    assert panel["engines"][0]["engine_id"] == cell["engine_id"]
    assert panel["engines"][0]["evidence_status"] == "Degraded"
    assert "health_no_outputs" in panel["engines"][0]["evidence_reason_codes"]
    assert sum(band["n_engines"] for band in panel["ceo_view"]) == 1

    detail = IOS.engine_detail(cell["engine_id"], root=tmp_path)
    assert detail["ok"] is True
    assert detail["engine"]["evidence_status"] == "Degraded"
    assert detail["outputs"] == []


def test_mixed_explicit_bases_refuse_a_validated_disposition():
    """Two incompatible explicit clocks must not pool into one apparently mature verdict."""
    provider = qledger_provider(
        n_dates=0,
        ready=False,
        clock_basis=None,
        clock_prior_n_dates={
            "explicit_unit_v1:calendar_days:US": 11,
            "explicit_unit_v1:trading_days:US": 14,
        },
        by_clock_basis={
            "explicit_unit_v1:calendar_days:US": {"n_dates": 11, "ready": False},
            "explicit_unit_v1:trading_days:US": {"n_dates": 14, "ready": False},
        },
        reason="two explicit clock bases; refusing to pool",
    )
    result = IOS.derive_evidence_status(
        evidence_cell(validation_state="validated"),
        [healthy_output()],
        provider,
    )

    assert result["evidence_status"] == "Accruing"
    assert "mixed_clock_basis_refused" in result["evidence_reason_codes"]
    assert result["evidence_basis"]["pooling_refused"] is True
    assert sorted(result["evidence_basis"]["available_clock_bases"]) == [
        "explicit_unit_v1:calendar_days:US",
        "explicit_unit_v1:trading_days:US",
    ]


def test_immature_qledger_record_is_accruing_with_its_ruler_and_honest_n():
    """Seven independent dates are not silently rounded up to the 25-date owner floor."""
    result = IOS.derive_evidence_status(
        evidence_cell(),
        [healthy_output()],
        qledger_provider(),
    )

    assert result["evidence_status"] == "Accruing"
    assert "insufficient_maturity" in result["evidence_reason_codes"]
    assert result["evidence_ruler"]["qledger_clock"] == {
        "horizon_d": 21,
        "horizon_unit": "trading_days",
        "clock_market": "US",
    }
    assert result["evidence_maturity"]["rungs"]["21"] == {
        "n_dates": 7,
        "needed": 25,
        "ready": False,
        "approaching": False,
        "projected_ready_date": "2026-09-30",
    }


def test_degraded_health_overrides_an_otherwise_validated_engine():
    """A lifecycle receipt must not paint over an output the current observer cannot trust."""
    result = IOS.derive_evidence_status(
        evidence_cell(validation_state="validated"),
        [healthy_output(state="degraded", assessment_status="partial")],
    )

    assert result["evidence_status"] == "Degraded"
    assert "health_degraded" in result["evidence_reason_codes"]


def test_blind_output_is_degraded_but_remains_distinct_from_a_health_verdict():
    """Could-not-look is reduced trust, not an invented unavailable or stale verdict."""
    result = IOS.derive_evidence_status(
        evidence_cell(validation_state="validated"),
        [healthy_output(state=None, assessment_status="could_not_look")],
    )

    assert result["evidence_status"] == "Degraded"
    assert "health_blind" in result["evidence_reason_codes"]
    assert "health_unavailable" not in result["evidence_reason_codes"]


def test_ungraded_by_design_requires_t1_semantic_evidence():
    """Missing data must not be mislabeled as an intentional descriptive contract."""
    semantic = IOS.derive_evidence_status(
        evidence_cell(
            output_class=None,
            graded_by_design="no — descriptive",
            graded_by_design_evidence="none",
            graded_by_design_source="derived: every artifact is infrastructure",
        ),
        [healthy_output()],
    )
    unsupported = IOS.derive_evidence_status(
        evidence_cell(
            output_class="descriptive",
            graded_by_design="no — not yet",
            graded_by_design_evidence="none",
            graded_by_design_source="derived: no ledger",
        ),
        [healthy_output()],
    )

    assert semantic["evidence_status"] == "Ungraded by design"
    assert "t1_semantic_ungraded" in semantic["evidence_reason_codes"]
    assert unsupported["evidence_status"] == "Accruing"
    assert "t1_semantic_ungraded" not in unsupported["evidence_reason_codes"]


def test_terminal_owner_state_is_disproven_and_keeps_its_evidence():
    """A1 displays the owner's terminal decision; it does not recreate or soften it."""
    result = IOS.derive_evidence_status(
        evidence_cell(
            validation_state="falsified",
            validation_state_evidence={
                "bound_species": [
                    {"species_id": "S-DEAD", "validation_status": "falsified"}
                ],
                "reason": "single_species",
            },
        ),
        [healthy_output(state="degraded", assessment_status="partial")],
    )

    assert result["evidence_status"] == "Disproven"
    assert "owner_terminal_falsified" in result["evidence_reason_codes"]
    assert "species:S-DEAD" in result["evidence_refs"]


def test_validated_requires_the_existing_owner_lifecycle_not_qledger_readiness():
    """Qledger readiness is measurement evidence and cannot mint validation authority."""
    ready_provider = qledger_provider(n_dates=30, needed=25, ready=True)
    still_phase0 = IOS.derive_evidence_status(
        evidence_cell(validation_state="phase0"), [healthy_output()], ready_provider
    )
    owner_validated = IOS.derive_evidence_status(
        evidence_cell(validation_state="validated", output_class="ranking"),
        [healthy_output()],
    )

    assert still_phase0["evidence_status"] == "Accruing"
    assert owner_validated["evidence_status"] == "Validated"
    assert "owner_validated" in owner_validated["evidence_reason_codes"]
    assert "evidence_score" not in owner_validated


@pytest.mark.parametrize(
    ("cell", "adapter_families", "expected"),
    [
        (
            evidence_cell(
                ledger="qledger:whitehouse",
                ledger_evidence={"desk": "whitehouse", "rule": 2},
            ),
            ("stock_desk", "thematic_desk", "demand_chain"),
            "whitehouse",
        ),
        (
            evidence_cell(ledger="data/stock_desk/theses.jsonl"),
            ("stock_desk", "thematic_desk", "demand_chain"),
            "stock_desk",
        ),
        (
            evidence_cell(ledger="data/not_stock_desk/theses.jsonl"),
            ("stock_desk", "thematic_desk", "demand_chain"),
            None,
        ),
    ],
)
def test_qledger_family_binding_is_exact_and_derived(cell, adapter_families, expected):
    """A1 may join canonical owner names exactly; fuzzy producer/name routing is illegal."""
    assert IOS.qledger_family_for_cell(cell, adapter_families) == expected


def test_panel_and_detail_expose_one_status_and_all_five_ceo_bands(tmp_path):
    """Dropping the pure result at the API seam would leave A1 built but invisible."""
    root = one_engine(tmp_path)

    panel = IOS.panel(root=root)
    assert panel["census"]["by_evidence_status"] == {"Accruing": 1}
    assert [band["evidence_status"] for band in panel["ceo_view"]] == list(
        IOS.EVIDENCE_STATUS_ORDER
    )
    assert panel["ceo_view"][0]["n_engines"] == 0
    row = panel["engines"][0]
    assert row["output_class"] is None
    assert row["evidence_status"] == "Accruing"
    assert "output_class_null" in row["evidence_reason_codes"]

    detail = IOS.engine_detail("engine/a.py::prog-one", root=root)
    assert detail["engine"]["evidence_status"] == "Accruing"
    assert detail["engine"]["evidence_provider"]["kind"] == "t1_owner_native"
    assert detail["engine"]["declared_horizon"]["horizon_role"] == ["context"]
    assert detail["engine"]["validation_state"] is None
    assert detail["engine"]["validation_state_evidence"] == {
        "bound_species": None,
        "reason": "species_store_absent",
    }


def test_panel_orders_by_evidence_band_then_engine_id(tmp_path):
    """The CEO view orders status strength, never class or headline performance."""
    root = _write_root(
        tmp_path,
        {
            "z": artifact("data/z.json", producer="engine/z.py", owner="prog-z"),
            "a": artifact(
                "data/a.json",
                producer="engine/a.py",
                owner="prog-a",
                tier="infrastructure",
            ),
        },
    )
    rows = IOS.panel(root=root)["engines"]

    assert [(row["evidence_status"], row["engine_id"]) for row in rows] == [
        ("Accruing", "engine/z.py::prog-z"),
        ("Ungraded by design", "engine/a.py::prog-a"),
    ]


def qledger_adapter_root(tmp_path: Path, *, with_store: bool = True) -> Path:
    root = _write_root(
        tmp_path,
        {
            "stock-ledger": artifact(
                "data/stock_desk/theses.jsonl",
                producer="engine/stock_desk.py",
                owner="qualitative-intelligence",
                tier="shadow",
                fmt="jsonl",
            )
        },
        overlay={
            "engines": {
                "engine/stock_desk.py::qualitative-intelligence": {
                    "output_class": {
                        "value": "predictive",
                        "rationale": "forward stock calls in the fixture",
                    }
                }
            }
        },
    )
    if with_store:
        qdir = root / "data" / "qledger"
        qdir.mkdir(parents=True, exist_ok=True)
        (qdir / "claims.jsonl").write_text("", encoding="utf-8")
        (qdir / "grades.jsonl").write_text("", encoding="utf-8")
    return root


def test_incomplete_e1_adapter_evidence_is_accruing_not_absent(tmp_path):
    """An empty-but-readable stock desk clock is the commissioned incomplete E1 case."""
    root = qledger_adapter_root(tmp_path)
    before = _tree(root)

    panel = IOS.panel(root=root)
    row = panel["engines"][0]
    assert row["evidence_status"] == "Accruing"
    assert row["evidence_provider"] == {
        "kind": "qledger",
        "binding": "adapter:stock_desk",
        "family": "stock_desk",
        "read_status": "ok",
    }
    assert "evidence_clock_not_started" in row["evidence_reason_codes"]
    assert row["evidence_maturity"]["rungs"]["63"]["n_dates"] == 0

    detail = IOS.engine_detail(
        "engine/stock_desk.py::qualitative-intelligence", root=root
    )
    assert detail["engine"]["evidence_provider"]["family"] == "stock_desk"
    assert detail["engine"]["evidence_ruler"]["qledger_clock"] is None
    assert _tree(root) == before


def test_a_bound_but_unreadable_qledger_store_degrades_instead_of_faking_empty(tmp_path):
    """Missing owner bytes are could-not-look, not a zero-row accruing receipt."""
    root = qledger_adapter_root(tmp_path, with_store=False)
    row = IOS.panel(root=root)["engines"][0]

    assert row["evidence_status"] == "Degraded"
    assert row["evidence_provider"]["read_status"] == "could_not_look"
    assert "evidence_provider_unreadable" in row["evidence_reason_codes"]


def test_malformed_qledger_claims_degrade_instead_of_faking_an_empty_store(tmp_path):
    """A compatibility reader skipping corrupt JSONL must not become zero evidence."""
    root = qledger_adapter_root(tmp_path)
    (root / "data" / "qledger" / "claims.jsonl").write_text(
        "{not-json}\n", encoding="utf-8"
    )

    row = IOS.panel(root=root)["engines"][0]

    assert row["evidence_status"] == "Degraded"
    assert row["evidence_provider"]["read_status"] == "partial"
    assert "unparseable" in row["evidence_provider"]["error"]
    assert "evidence_provider_unreadable" in row["evidence_reason_codes"]


@pytest.mark.parametrize("store_name", ["claims.jsonl", "grades.jsonl"])
def test_semantically_invalid_qledger_rows_degrade_even_when_json_parses(
    tmp_path, store_name
):
    """Owner readers accepting ``{}`` must not turn corruption into Accruing."""
    root = qledger_adapter_root(tmp_path)
    (root / "data" / "qledger" / store_name).write_text("{}\n", encoding="utf-8")

    row = IOS.panel(root=root)["engines"][0]

    assert row["evidence_status"] == "Degraded"
    assert row["evidence_provider"]["read_status"] == "partial"
    assert "semantically invalid" in row["evidence_provider"]["error"]
    assert "evidence_provider_unreadable" in row["evidence_reason_codes"]


@pytest.mark.parametrize("store_name", ["claims.jsonl", "grades.jsonl"])
def test_invalid_utf8_qledger_store_is_provider_blindness_not_page_failure(
    tmp_path, store_name
):
    """Undecodable owner bytes degrade bound evidence while preserving the census."""
    root = qledger_adapter_root(tmp_path)
    (root / "data" / "qledger" / store_name).write_bytes(b"\xff\xfe\x00")

    result = IOS.panel(root=root)

    assert result["ok"] is True
    row = result["engines"][0]
    assert row["evidence_status"] == "Degraded"
    assert row["evidence_provider"]["read_status"] == "unreadable"
    assert "unreadable" in row["evidence_provider"]["error"]
    assert "evidence_provider_unreadable" in row["evidence_reason_codes"]


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("direction", True),
        ("scope", {"type": [], "key": "AAPL"}),
    ],
)
def test_claim_semantic_validation_is_type_total(tmp_path, field, bad_value):
    """Every JSON type becomes a provider verdict, never a page-level exception."""
    root = qledger_adapter_root(tmp_path)
    claim = {
        "claim_id": "c1",
        "desk": "stock_desk",
        "claim_family": "stock_desk",
        "asof": "2026-08-29",
        "scope": {"type": "entity", "key": "AAPL"},
        "direction": 1,
        "horizon_d": 20,
        "timestamp_quality": "CRAWL_BOUNDED",
    }
    claim[field] = bad_value
    (root / "data" / "qledger" / "claims.jsonl").write_text(
        json.dumps(claim) + "\n", encoding="utf-8"
    )

    result = IOS.panel(root=root)
    assert result["ok"] is True
    row = result["engines"][0]
    assert row["evidence_status"] == "Degraded"
    assert row["evidence_provider"]["read_status"] == "partial"
    assert "semantically invalid" in row["evidence_provider"]["error"]


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("subject_ret", "0.1"),
        ("excess", {"value": 0.1}),
    ],
)
def test_grade_semantic_validation_rejects_nonnumeric_metrics(
    tmp_path, field, bad_value
):
    """Parseable prose/objects are not numeric owner evidence."""
    root = qledger_adapter_root(tmp_path)
    grade = {
        "claim_id": "c1",
        "horizon_d": 20,
        "graded_at": "2026-08-29T01:02:03+00:00",
        "subject_ret": 0.1,
        "bench_ret": 0.0,
        "control_ret": None,
        "excess": 0.1,
        "hit": True,
    }
    grade[field] = bad_value
    (root / "data" / "qledger" / "grades.jsonl").write_text(
        json.dumps(grade) + "\n", encoding="utf-8"
    )

    row = IOS.panel(root=root)["engines"][0]
    assert row["evidence_status"] == "Degraded"
    assert row["evidence_provider"]["read_status"] == "partial"
    assert "semantically invalid" in row["evidence_provider"]["error"]


def test_grade_semantic_validation_contains_unrepresentable_numeric_metrics(tmp_path):
    """An enormous JSON integer degrades its provider; it never sinks the panel."""
    root = qledger_adapter_root(tmp_path)
    grade = {
        "claim_id": "c1",
        "horizon_d": 20,
        "graded_at": "2026-08-29T01:02:03+00:00",
        "subject_ret": 10**1000,
        "bench_ret": 0.0,
        "control_ret": None,
        "excess": 0.1,
        "hit": True,
    }
    (root / "data" / "qledger" / "grades.jsonl").write_text(
        json.dumps(grade) + "\n", encoding="utf-8"
    )

    result = IOS.panel(root=root)
    assert result["ok"] is True
    row = result["engines"][0]
    assert row["evidence_status"] == "Degraded"
    assert row["evidence_provider"]["read_status"] == "partial"
    assert "semantically invalid" in row["evidence_provider"]["error"]


@pytest.mark.parametrize(
    "basis_patch",
    [
        {"clock_version": "explicit_unit_v1"},
        {"horizon_unit": "trading_days"},
        {"clock_market": "US"},
    ],
)
def test_grade_semantic_validation_rejects_partial_clock_basis(
    tmp_path, basis_patch
):
    """Partial explicit stamps cannot be silently reclassified as legacy evidence."""
    root = qledger_adapter_root(tmp_path)
    grade = {
        "claim_id": "c1",
        "horizon_d": 20,
        "graded_at": "2026-08-29T01:02:03+00:00",
        "subject_ret": 0.1,
        "bench_ret": 0.0,
        "control_ret": None,
        "excess": 0.1,
        "hit": True,
        **basis_patch,
    }
    (root / "data" / "qledger" / "grades.jsonl").write_text(
        json.dumps(grade) + "\n", encoding="utf-8"
    )

    row = IOS.panel(root=root)["engines"][0]
    assert row["evidence_status"] == "Degraded"
    assert row["evidence_provider"]["read_status"] == "partial"
    assert "semantically invalid" in row["evidence_provider"]["error"]


def test_market_unstamped_explicit_basis_remains_lawful(tmp_path):
    """The owner contract permits version+unit without a market during migration."""
    root = qledger_adapter_root(tmp_path)
    grade = {
        "claim_id": "c1",
        "horizon_d": 20,
        "graded_at": "2026-08-29T01:02:03+00:00",
        "subject_ret": 0.1,
        "bench_ret": 0.0,
        "control_ret": None,
        "excess": 0.1,
        "hit": True,
        "clock_version": "explicit_unit_v1",
        "horizon_unit": "trading_days",
    }
    (root / "data" / "qledger" / "grades.jsonl").write_text(
        json.dumps(grade) + "\n", encoding="utf-8"
    )

    row = IOS.panel(root=root)["engines"][0]
    assert row["evidence_provider"]["read_status"] == "ok"
    assert "evidence_provider_unreadable" not in row["evidence_reason_codes"]


def test_qledger_semantic_validators_are_total_over_json_types():
    """Adversarial JSON values always yield a boolean, never an exception."""
    from engine import qledger

    values = [None, False, True, 0, 1, 1.5, "", "value", [], {}]
    claim = {
        "claim_id": "c1",
        "desk": "stock_desk",
        "claim_family": "stock_desk",
        "asof": "2026-08-29",
        "scope": {"type": "entity", "key": "AAPL"},
        "direction": 1,
        "horizon_d": 20,
        "timestamp_quality": "CRAWL_BOUNDED",
    }
    for field in claim:
        for value in values:
            assert isinstance(
                IOS._valid_claim_row({**claim, field: value}, qledger), bool
            )
    for nested in ("type", "key"):
        for value in values:
            assert isinstance(
                IOS._valid_claim_row(
                    {**claim, "scope": {**claim["scope"], nested: value}}, qledger
                ),
                bool,
            )

    grade = {
        "claim_id": "c1",
        "horizon_d": 20,
        "graded_at": "2026-08-29T01:02:03+00:00",
        "subject_ret": 0.1,
        "bench_ret": 0.0,
        "control_ret": None,
        "excess": 0.1,
        "hit": True,
        "clock_version": "explicit_unit_v1",
        "horizon_unit": "trading_days",
        "clock_market": "US",
    }
    for field in grade:
        for value in [*values, float("nan"), float("inf"), float("-inf"), 10**1000]:
            assert isinstance(
                IOS._valid_grade_row({**grade, field: value}, qledger), bool
            )


def test_corrupt_existing_evidence_clock_degrades_instead_of_looking_unstarted(tmp_path):
    """An existing unreadable write-once receipt is blindness, not an absent clock."""
    root = qledger_adapter_root(tmp_path)
    clock_dir = root / "data" / "qledger" / "evidence_clock_start"
    clock_dir.mkdir(parents=True)
    (clock_dir / "stock_desk.json").write_text("{not-json}", encoding="utf-8")

    row = IOS.panel(root=root)["engines"][0]

    assert row["evidence_status"] == "Degraded"
    assert row["evidence_provider"]["read_status"] == "unreadable"
    assert "evidence clock receipt" in row["evidence_provider"]["error"]
    assert "evidence_clock_not_started" not in row["evidence_reason_codes"]


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("first_prospective_registration_utc", "definitely-not-a-timestamp"),
        ("declared_horizon_d", True),
    ],
)
def test_semantically_invalid_evidence_clock_degrades(tmp_path, field, bad_value):
    """A parseable receipt still fails closed when its ruler fields are dishonest."""
    root = qledger_adapter_root(tmp_path)
    clock_dir = root / "data" / "qledger" / "evidence_clock_start"
    clock_dir.mkdir(parents=True)
    receipt = {
        "claim_family": "stock_desk",
        "first_prospective_registration_utc": "2026-08-29T01:02:03+00:00",
        "declared_horizon_d": 20,
        "horizon_unit": "trading_days",
        "git_sha": "abc123",
    }
    receipt[field] = bad_value
    (clock_dir / "stock_desk.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )

    row = IOS.panel(root=root)["engines"][0]

    assert row["evidence_status"] == "Degraded"
    assert row["evidence_provider"]["read_status"] == "unreadable"
    assert "evidence clock receipt" in row["evidence_provider"]["error"]
    assert "evidence_clock_not_started" not in row["evidence_reason_codes"]


def test_missing_grades_is_a_lawful_empty_accrual_not_provider_blindness(tmp_path):
    """Before the first grade, absence of the optional grade ledger is an honest zero."""
    root = qledger_adapter_root(tmp_path)
    (root / "data" / "qledger" / "grades.jsonl").unlink()

    row = IOS.panel(root=root)["engines"][0]

    assert row["evidence_status"] == "Accruing"
    assert row["evidence_provider"]["read_status"] == "ok"
    assert "evidence_provider_unreadable" not in row["evidence_reason_codes"]


def test_new_evidence_clock_invalidates_the_in_process_view(tmp_path):
    """The five-minute cache must not hide the first prospective clock receipt."""
    root = qledger_adapter_root(tmp_path)
    first = IOS.panel(root=root)
    assert first["generated"]["cache"] == "miss"
    assert IOS.panel(root=root)["generated"]["cache"] == "hit"

    clock_dir = root / "data" / "qledger" / "evidence_clock_start"
    clock_dir.mkdir(parents=True)
    (clock_dir / "stock_desk.json").write_text(
        json.dumps(
            {
                "claim_family": "stock_desk",
                "first_prospective_registration_utc": "2026-08-29T01:02:03+00:00",
                "declared_horizon_d": 20,
                "horizon_unit": "trading_days",
                "git_sha": "abc123",
            }
        ),
        encoding="utf-8",
    )

    fresh = IOS.panel(root=root)
    assert fresh["generated"]["cache"] == "miss"
    row = fresh["engines"][0]
    assert row["evidence_ruler"]["qledger_clock"]["horizon_d"] == 20
    assert "qledger-clock:stock_desk:2026-08-29T01:02:03+00:00" in row[
        "evidence_refs"
    ]


@pytest.mark.parametrize("changed_rel", ["data/species/registry.json", "engine/a.py"])
def test_t1_evidence_input_movement_invalidates_the_in_process_view(
    tmp_path, changed_rel
):
    """Owner lifecycle and producer semantics must not remain stale for the cache TTL."""
    root = one_engine(tmp_path)
    assert IOS.panel(root=root)["generated"]["cache"] == "miss"
    assert IOS.panel(root=root)["generated"]["cache"] == "hit"

    changed = root / changed_rel
    changed.parent.mkdir(parents=True, exist_ok=True)
    changed.write_text(
        '{"species": []}\n' if changed.suffix == ".json" else "# producer changed\n",
        encoding="utf-8",
    )

    assert IOS.panel(root=root)["generated"]["cache"] == "miss"


def test_new_repo_path_prereg_invalidates_the_in_process_view(tmp_path):
    """A newly materialized Synapse evidence pointer must not hide for the TTL."""
    prereg_rel = "research/new_prereg.md"
    root = _write_root(
        tmp_path,
        {
            "a": artifact(
                "data/a.json",
                producer="engine/a.py",
                owner="prog-one",
                tier="scored",
                qual_ladder_ref=prereg_rel,
            )
        },
    )
    (root / "config" / "qual_ladder.yml").write_text("{}\n", encoding="utf-8")
    first = IOS.panel(root=root)
    assert prereg_rel not in first["engines"][0]["evidence_refs"]
    assert IOS.panel(root=root)["generated"]["cache"] == "hit"

    prereg = root / prereg_rel
    prereg.parent.mkdir(parents=True)
    prereg.write_text("# prospective protocol\n", encoding="utf-8")

    fresh = IOS.panel(root=root)
    assert fresh["generated"]["cache"] == "miss"
    assert prereg_rel in fresh["engines"][0]["evidence_refs"]


def test_revised_existing_evidence_clock_invalidates_the_in_process_view(tmp_path):
    """Changing clock bytes in place must invalidate even when the directory does not."""
    root = qledger_adapter_root(tmp_path)
    clock_dir = root / "data" / "qledger" / "evidence_clock_start"
    clock_dir.mkdir(parents=True)
    clock = clock_dir / "stock_desk.json"
    receipt = {
        "claim_family": "stock_desk",
        "first_prospective_registration_utc": "2026-08-29T01:02:03+00:00",
        "declared_horizon_d": 20,
        "horizon_unit": "trading_days",
        "git_sha": "abc123",
    }
    clock.write_text(json.dumps(receipt), encoding="utf-8")
    first = IOS.panel(root=root)
    assert first["engines"][0]["evidence_ruler"]["qledger_clock"]["horizon_d"] == 20
    assert IOS.panel(root=root)["generated"]["cache"] == "hit"

    before = clock.stat().st_mtime_ns
    receipt["declared_horizon_d"] = 63
    receipt["git_sha"] = "def456"
    clock.write_text(json.dumps(receipt), encoding="utf-8")
    os.utime(clock, ns=(before + 1_000_000_000, before + 1_000_000_000))

    fresh = IOS.panel(root=root)
    assert fresh["generated"]["cache"] == "miss"
    assert fresh["engines"][0]["evidence_ruler"]["qledger_clock"]["horizon_d"] == 63
    assert "git:def456" in fresh["engines"][0]["evidence_refs"]


# ---------------------------------------------------------------------------
# No persisted state
# ---------------------------------------------------------------------------

def test_neither_entry_point_writes_anything_to_disk(tmp_path):
    """CEO law: this surface holds NO state. Not a cache file, not a snapshot.

    Compared by (size, mtime_ns) over every file, so a rewrite with identical bytes is
    caught as well as an addition or a deletion — 'the file did not change' has to mean
    nobody touched it, not that they put it back the way they found it.
    """
    root = one_engine(tmp_path)
    before = _tree(root)
    assert IOS.panel(root=root)["ok"] is True
    assert IOS.engine_detail("engine/a.py::prog-one", root=root)["ok"] is True
    assert IOS.panel(root=root, force=True)["ok"] is True
    assert _tree(root) == before

    # Nothing outside the fixture root either — the repo itself must be untouched.
    assert not list(tmp_path.glob("*.json"))
    assert not list(tmp_path.glob("*.cache"))


# ---------------------------------------------------------------------------
# engine_detail
# ---------------------------------------------------------------------------

def test_engine_detail_for_an_unknown_id_refuses_with_a_sample(tmp_path):
    root = one_engine(tmp_path)
    result = IOS.engine_detail("engine/nope.py::nowhere", root=root)
    assert result["ok"] is False
    assert "nope" in result["error"]
    # The sample is the affordance that turns a typo into a fix instead of a shrug.
    assert result["known_ids_sample"] == ["engine/a.py::prog-one"]


def test_engine_detail_returns_the_full_t4_record(tmp_path):
    """The drill-down renders the record verbatim, so the keys it draws must be present.

    Pinned by NAME: a resolver change that renamed one of these would otherwise show up
    as a silently blank row on the page rather than as a red test.
    """
    root = one_engine(tmp_path)
    detail = IOS.engine_detail("engine/a.py::prog-one", root=root)
    assert detail["ok"] is True
    record = detail["outputs"][0]
    for key in (
        "artifact_id", "path", "storage", "state", "assessment_status", "decided_by",
        "age_hours", "freshness_sla_hours", "dependency_bound", "reason_codes",
        "required_inputs", "optional_inputs", "reader_observation", "self_health",
        "source_asof", "display_confidence_state",
    ):
        assert key in record, f"the engine drill-down renders {key!r} and it is missing"


def test_artifacts_outside_every_engine_cell_are_surfaced_not_dropped(tmp_path):
    """A synapse artifact with a placeholder producer is in NO T1 engine cell. It still
    has to appear: an artifact nobody owns is precisely what an operator census exists to
    find, and dropping it would make the page's own artifact count a lie."""
    root = _write_root(
        tmp_path,
        {
            "a": artifact("data/a.json", producer="engine/a.py", owner="prog-one"),
            "orphan": artifact("data/orphan.json", producer="<MANUAL>", owner="prog-one"),
        },
    )
    panel = IOS.panel(root=root)
    assert panel["census"]["artifacts"] == 2
    ids = {r["engine_id"] for r in panel["engines"]}
    assert IOS.UNREGISTERED_ENGINE_ID in ids
    orphan = next(
        row for row in panel["engines"] if row["engine_id"] == IOS.UNREGISTERED_ENGINE_ID
    )
    assert orphan["canonical_t1"] is False
    assert orphan["evidence_status"] is None
    assert orphan["evidence_reason_codes"] == ["not_canonical_t1"]
    # The legacy table keeps the orphan visible, but the commissioned CEO ordering is
    # explicitly over canonical T1 cells. A registry gap is not a 2nd engine.
    assert panel["census"]["canonical_engines"] == 1
    assert panel["census"]["noncanonical_output_groups"] == 1
    assert sum(band["n_engines"] for band in panel["ceo_view"]) == 1
    assert IOS.UNREGISTERED_ENGINE_ID not in {
        engine_id
        for band in panel["ceo_view"]
        for engine_id in band["engine_ids"]
    }

    detail = IOS.engine_detail(IOS.UNREGISTERED_ENGINE_ID, root=root)
    assert detail["ok"] is True
    assert detail["engine"]["canonical_t1"] is False
    assert detail["engine"]["evidence_status"] is None
    assert detail["engine"]["evidence_reason_codes"] == ["not_canonical_t1"]
    assert [o["artifact_id"] for o in detail["outputs"]] == ["orphan"]


# ---------------------------------------------------------------------------
# worst_state ordering
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def blind_estate(tmp_path_factory):
    """A two-engine estate the roll-up cannot honestly summarize with a state alone.

    ``blind`` has ONE output and it is unreadable (a csv carries no readable watermark, so
    the freshness axis is blind). ``mixed`` has one readable-and-current output and one
    unreadable one — the shape that used to render a plain green row.

    Module-scoped because the panel is a real derivation and the assertions below hang off
    a parametrized test; deriving it once is the difference between a pin and a tax.
    """
    root = _write_root(
        tmp_path_factory.mktemp("blind"),
        {
            "b1": artifact("data/b1.csv", producer="engine/blind.py", owner="prog-blind",
                           fmt="csv"),
            "m1": artifact("data/m1.json", producer="engine/mixed.py", owner="prog-mixed"),
            "m2": artifact("data/m2.csv", producer="engine/mixed.py", owner="prog-mixed",
                           fmt="csv"),
        },
    )
    return IOS.panel(root=root, force=True)


@pytest.mark.parametrize(
    "states, expected",
    [
        (["healthy", "degraded"], "degraded"),
        (["healthy", "stale", "degraded"], "stale"),
        (["stale", "unavailable", "degraded"], "unavailable"),
        (["healthy", None], "healthy"),          # a null NEVER outranks a real verdict
        ([None, None], None),
        (["healthy", "healthy"], "healthy"),
        ([], None),
    ],
)
def test_worst_state_follows_the_t4_precedence_ladder(states, expected, blind_estate):
    assert IOS.worst_state(states) == expected

    # THE OTHER HALF OF THE SAME LADDER. `worst_state` folding only real verdicts is
    # correct — "could not determine" is not a health verdict and must never outrank one —
    # but it means the fold ALONE cannot describe an engine some of whose outputs were
    # unreadable. So every row carries the blind count, asserted on the payload (the DOM
    # is not the contract; the payload is).
    rows = {r["engine_id"]: r for r in blind_estate["engines"]}
    assert all("n_blind" in r for r in rows.values()), sorted(rows)

    all_blind = rows["engine/blind.py::prog-blind"]
    assert all_blind["worst_state"] is None
    assert all_blind["n_blind"] == all_blind["n_artifacts"] == 1

    mixed = rows["engine/mixed.py::prog-mixed"]
    assert mixed["worst_state"] == "healthy"          # the worst thing that could be SEEN
    assert (mixed["n_blind"], mixed["n_artifacts"]) == (1, 2)
    assert mixed["state_counts"]["null"] == 1         # and it agrees with its own tally


def test_worst_state_treats_an_unknown_word_as_the_worst_thing_it_has_seen():
    """A state this page has not learned must announce itself, not hide behind healthy.

    If the T4 vocabulary ever grows a fifth verdict, the roll-up surfacing it is a bug
    report; the roll-up quietly reporting `healthy` is an outage nobody sees.
    """
    assert IOS.worst_state(["healthy", "on_fire"]) == "on_fire"


def test_state_severity_matches_the_resolver_ladder():
    """The one hand-written list in the module, pinned against the contract it mirrors."""
    assert IOS.STATE_SEVERITY == ("unavailable", "stale", "degraded", "healthy", None)


def test_engine_worst_state_folds_its_own_outputs(tmp_path):
    """Fold direction, end to end: one stale output makes the whole engine row stale."""
    root = _write_root(
        tmp_path,
        {
            "fresh": artifact("data/fresh.json", producer="engine/a.py", owner="prog-one"),
            "old": artifact("data/old.json", producer="engine/a.py", owner="prog-one"),
        },
    )
    (root / "data" / "old.json").write_text(
        json.dumps({"asof": "2026-01-01T00:00:00+00:00"}), encoding="utf-8"
    )
    row = IOS.panel(root=root)["engines"][0]
    assert row["n_artifacts"] == 2
    assert row["worst_state"] == "stale"
    assert row["state_counts"]["stale"] == 1


# ---------------------------------------------------------------------------
# Cache protocol
# ---------------------------------------------------------------------------

def test_second_call_is_a_cache_hit_and_force_recomputes(tmp_path):
    root = one_engine(tmp_path)
    first = IOS.panel(root=root)
    assert first["generated"]["cache"] == "miss"

    second = IOS.panel(root=root)
    assert second["generated"]["cache"] == "hit"
    assert second["generated"]["compute_seconds"] == 0.0
    assert second["engines"] == first["engines"]

    forced = IOS.panel(root=root, force=True)
    assert forced["generated"]["cache"] == "miss"


def test_editing_the_registry_evicts_the_cache_without_force(tmp_path):
    """The TTL is a floor, not the invalidation rule. Keying on the two declared inputs'
    mtimes is what stops an operator editing synapse.yml and reading a five-minute-old
    census that still says the old thing."""
    root = one_engine(tmp_path)
    assert IOS.panel(root=root)["generated"]["cache"] == "miss"
    assert IOS.panel(root=root)["generated"]["cache"] == "hit"

    doc = yaml.safe_load((root / "config" / "synapse.yml").read_text())
    doc["artifacts"]["z"] = artifact("data/z.json", producer="engine/z.py", owner="prog-two")
    (root / "config" / "synapse.yml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    (root / "engine").mkdir(exist_ok=True)
    (root / "engine" / "z.py").write_text("", encoding="utf-8")
    (root / "data" / "z.json").write_text(json.dumps({"asof": FRESH}), encoding="utf-8")

    fresh = IOS.panel(root=root)
    assert fresh["generated"]["cache"] == "miss"
    assert fresh["census"]["engines"] == 2


def test_the_cache_does_not_grow_one_entry_per_registry_edit(tmp_path):
    """The key changes on every edit, and the process is long-lived. Without eviction the
    admin server would accumulate a full 642-record view per nightly commit."""
    root = one_engine(tmp_path)
    for i in range(3):
        doc = yaml.safe_load((root / "config" / "synapse.yml").read_text())
        doc["meta"]["description"] = f"fixture {i}"
        (root / "config" / "synapse.yml").write_text(yaml.safe_dump(doc), encoding="utf-8")
        assert IOS.panel(root=root)["ok"] is True
    assert len(IOS._CACHE) == 1


# ---------------------------------------------------------------------------
# Trust-mtime plane + fail-open
# ---------------------------------------------------------------------------

def test_write_time_evidence_is_refused_on_every_plane_including_the_deployed_one(
    monkeypatch,
):
    """A DEPLOYED file's mtime is a git-transport clock, not a write time.

    ``app/deploy/update.sh`` updates the VPS with ``git fetch && git reset --hard``, so
    every file git rewrites is stamped with the PULL time. The panel used to admit
    write-time evidence whenever ``ADMIN_DEPLOYED=1``, which means a deploy or a rollback
    would have restamped the tree and turned the 63 artifacts that declare an SLA but no
    watermark green — an entire class of frozen stores reading "fresh" because somebody
    deployed. The environment cannot turn it back on because the environment is no longer
    consulted: pinned structurally, since an env read is the thing being removed.
    """
    monkeypatch.setenv("ADMIN_DEPLOYED", "1")
    assert IOS._trust_mtime() is False
    monkeypatch.delenv("ADMIN_DEPLOYED", raising=False)
    assert IOS._trust_mtime() is False

    tree = ast.parse((REPO / "admin" / "intelligence_os.py").read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "os" not in imported
    assert not [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in ("environ", "getenv")
    ]
    assert "ADMIN_DEPLOYED" not in {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def test_a_no_watermark_artifact_stays_unassessed_rather_than_trusting_its_mtime(tmp_path):
    """The consequence of the rule above, made visible: an artifact that declares an SLA
    but no watermark field is NOT healthy and NOT stale — it is unassessed, and the record
    says which axis and why. That reason code is the standing argument for declaring a
    watermark; a silent green would have removed the argument."""
    root = _write_root(
        tmp_path,
        {
            "nowm": artifact("data/nowm.json", producer="engine/a.py", owner="prog-one",
                             asof_field=None, sla=24),
        },
    )
    detail = IOS.engine_detail("engine/a.py::prog-one", root=root)
    record = detail["outputs"][0]
    assert record["state"] is None
    assert record["assessment_status"] == "partial"
    assert "write_time_untrusted" in record["reason_codes"]
    assert IOS.panel(root=root)["generated"]["trust_mtime"] is False


def test_both_entry_points_fail_open_on_an_unreadable_root(tmp_path):
    """Every sibling admin panel degrades rather than 500s, and so does this one."""
    empty = tmp_path / "not-a-checkout"
    empty.mkdir()
    panel = IOS.panel(root=empty)
    assert panel["ok"] is False
    assert panel["error"]
    detail = IOS.engine_detail("anything", root=empty)
    assert detail["ok"] is False


def test_census_counts_agree_with_the_rows_they_summarize(tmp_path):
    """A census whose headline disagrees with its own table is worse than no census."""
    root = _write_root(
        tmp_path,
        {
            "a": artifact("data/a.json", producer="engine/a.py", owner="prog-one"),
            "b": artifact("data/b.json", producer="engine/b.py", owner="prog-two"),
            "c": artifact("data/c.json", producer="engine/b.py", owner="prog-two"),
        },
    )
    panel = IOS.panel(root=root)
    census, engines = panel["census"], panel["engines"]
    assert census["engines"] == len(engines)
    assert census["artifacts"] == sum(r["n_artifacts"] for r in engines)
    assert sum(census["by_state"].values()) == census["artifacts"]
    assert sum(census["by_authority"].values()) == census["artifacts"]
    assert sum(census["by_storage"].values()) == census["artifacts"]
    assert census["outputs_assessed"] <= census["artifacts"]
    assert census["by_assessment_status"].get("could_not_look", 0) == (
        census["artifacts"] - census["outputs_assessed"]
    )
