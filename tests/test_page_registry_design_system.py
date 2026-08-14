"""Contracts for the `design_system` field and the closed archetype vocabulary.

Both were added by DS-PR-1.  `design_system` is a GOVERNANCE claim — "this region
of this template is design-system compliant" — so its shape law is fail-closed:
an unknown key, a wrong type or an unparseable date is an error, never a silent
coercion.  A claim that gets quietly repaired is a claim nobody can audit.

Units run on ``blank_row`` fixtures, never on a sister repo, git, gh or the
network; the committed-artifact half asserts the invariants the shipped registry
must keep.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
import yaml

from scripts import build_product_page_registry as reg

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "data" / "product_experience" / "page_registry.json"
OVERRIDES = REPO_ROOT / "config" / "product_experience" / "page_registry_overrides.yml"


def _row() -> list[dict]:
    return [reg.blank_row("macro:alpha", "macro", "/alpha.html")]


def _apply(value) -> tuple[list[dict], list[str]]:
    rows = _row()
    errors = reg.apply_overrides(rows, {"macro:alpha": {"design_system": value}},
                                 source_name="test.yml")
    return rows, errors


# ---------------------------------------------------------------------------
# blank default
# ---------------------------------------------------------------------------

def test_blank_row_carries_the_honest_design_system_default():
    row = reg.blank_row("macro:alpha", "macro", "/alpha.html")
    assert row["design_system"] == {"compliant": False}


def test_design_system_is_an_ordered_registry_field():
    assert "design_system" in reg.FIELD_ORDER
    assert "design_system" in reg.OVERRIDABLE


def test_blank_default_passes_its_own_shape_law():
    row = reg.blank_row("macro:alpha", "macro", "/alpha.html")
    assert reg._design_system_problems(row["design_system"], "x") == []


# ---------------------------------------------------------------------------
# round trip
# ---------------------------------------------------------------------------

def test_design_system_override_round_trips():
    claim = {
        "compliant": True,
        "governed_regions": [
            {"template": "templates/dashboard.html.j2", "region": "body.page-macro"}],
        "exempt": {"reason": "legacy inline styles", "expires": "2026-12-31"},
        "migrated_pr": 5501,
        "evidence": ["mockups/design_system/specimen.html"],
    }
    rows, errors = _apply(claim)
    assert errors == []
    assert rows[0]["design_system"] == claim


def test_a_row_survives_a_json_round_trip():
    """The field must be JSON-serialisable — a date object here would raise."""
    rows, errors = _apply({"compliant": False,
                           "exempt": {"reason": "r", "expires": "2026-01-01"}})
    assert errors == []
    assert json.loads(json.dumps(rows[0]))["design_system"] == rows[0]["design_system"]


# ---------------------------------------------------------------------------
# shape law — every malformed form hard-errors AND is not written
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad,needle", [
    ("not-a-mapping", "must be a mapping"),
    (["compliant"], "must be a mapping"),
    ({}, "missing required key 'compliant'"),
    ({"governed_regions": []}, "missing required key 'compliant'"),
    ({"compliant": "yes"}, "compliant must be a bool"),
    ({"compliant": 1}, "compliant must be a bool"),
    ({"compliant": False, "unexpected": 1}, "unknown key(s) ['unexpected']"),
    ({"compliant": False, "governed_regions": {}}, "governed_regions must be a list"),
    ({"compliant": False, "governed_regions": ["t"]}, "must be a mapping"),
    ({"compliant": False, "governed_regions": [{"template": "t"}]},
     "must have exactly the keys"),
    ({"compliant": False,
      "governed_regions": [{"template": "t", "region": "r", "extra": 1}]},
     "must have exactly the keys"),
    ({"compliant": False, "governed_regions": [{"template": "t", "region": ""}]},
     "must be a non-empty string"),
    ({"compliant": False, "governed_regions": [{"template": 1, "region": "r"}]},
     "must be a non-empty string"),
    ({"compliant": False, "exempt": []}, "exempt must be a mapping"),
    ({"compliant": False, "exempt": {"reason": "r"}}, "must have exactly the keys"),
    ({"compliant": False, "exempt": {"reason": "", "expires": "2026-01-01"}},
     "reason must be a non-empty string"),
    ({"compliant": False, "exempt": {"reason": "r", "expires": "01-01-2026"}},
     "must be a YYYY-MM-DD date"),
    ({"compliant": False, "exempt": {"reason": "r", "expires": "2026-13-45"}},
     "must be a YYYY-MM-DD date"),
    ({"compliant": False, "exempt": {"reason": "r", "expires": dt.date(2026, 1, 1)}},
     "must be a QUOTED"),
])
def test_a_malformed_design_system_is_a_hard_error(bad, needle):
    rows, errors = _apply(bad)
    assert errors, f"{bad!r} was accepted"
    assert any(needle in e for e in errors), errors
    # fail closed: the malformed claim never reaches the row
    assert rows[0]["design_system"] == {"compliant": False}


def test_an_unparseable_expiry_cannot_be_an_exemption_that_never_expires():
    """2026-13-45 matches the digit shape but is not a day on any calendar."""
    assert reg._is_calendar_date("2026-12-31")
    assert not reg._is_calendar_date("2026-13-45")
    assert not reg._is_calendar_date("2026-02-30")
    assert not reg._is_calendar_date("2026-1-1")


# --- migrated_pr (design-migration factory §0 gate 8) -----------------------

def test_migrated_pr_is_accepted_as_an_int():
    rows, errors = _apply({"compliant": True, "migrated_pr": 5501})
    assert errors == []
    assert rows[0]["design_system"]["migrated_pr"] == 5501


@pytest.mark.parametrize("bad", ["5501", 5501.0, None, [5501]])
def test_migrated_pr_is_rejected_when_it_is_not_an_int(bad):
    rows, errors = _apply({"compliant": True, "migrated_pr": bad})
    assert any("migrated_pr must be an int" in e for e in errors), errors
    assert rows[0]["design_system"] == {"compliant": False}


def test_migrated_pr_rejects_a_bool_because_bools_are_ints_in_python():
    """`migrated_pr: true` is a mistake, not PR number 1."""
    _, errors = _apply({"compliant": True, "migrated_pr": True})
    assert any("got bool" in e for e in errors), errors


def test_migrated_pr_must_be_positive():
    _, errors = _apply({"compliant": True, "migrated_pr": 0})
    assert any("positive PR" in e for e in errors), errors


# --- evidence (migration artifact, distinct from row source_evidence) -------

def test_evidence_is_accepted_as_a_string():
    rows, errors = _apply({"compliant": True, "evidence": "mockups/x/matrix.md"})
    assert errors == []
    assert rows[0]["design_system"]["evidence"] == "mockups/x/matrix.md"


def test_evidence_is_accepted_as_a_list():
    rows, errors = _apply({"compliant": True, "evidence": ["a.md", "b.md"]})
    assert errors == []
    assert rows[0]["design_system"]["evidence"] == ["a.md", "b.md"]


@pytest.mark.parametrize("bad,needle", [
    (7, "must be a string or a list of strings"),
    ({"path": "a.md"}, "must be a string or a list of strings"),
    ("", "must be a non-empty string"),
    (["a.md", ""], "[1] must be a non-empty string"),
    (["a.md", 3], "[1] must be a non-empty string"),
])
def test_a_malformed_evidence_claim_is_a_hard_error(bad, needle):
    _, errors = _apply({"compliant": True, "evidence": bad})
    assert any(needle in e for e in errors), errors


def test_design_system_evidence_does_not_leak_into_row_source_evidence():
    """Two different receipts: the migration's matrix vs what the census derived."""
    rows, errors = _apply({"compliant": True, "evidence": ["mockups/x/matrix.md"]})
    assert errors == []
    assert "mockups/x/matrix.md" not in rows[0]["source_evidence"]


# --- archetype has ONE home ------------------------------------------------

def test_archetype_inside_design_system_is_rejected_with_a_teaching_message():
    _, errors = _apply({"compliant": True, "archetype": "editorial"})
    assert errors
    message = " ".join(errors)
    assert "archetype is a top-level registry field" in message
    assert "not inside design_system" in message


def test_archetype_inside_design_system_is_not_reported_as_a_generic_unknown_key():
    errors = reg._design_system_problems({"compliant": True, "archetype": "editorial"},
                                         "x")
    assert not any("unknown key(s) ['archetype']" in e for e in errors), errors


# ---------------------------------------------------------------------------
# archetype vocabulary
# ---------------------------------------------------------------------------

def test_the_archetype_vocabulary_is_the_ten_ids_plus_unclassified():
    assert set(reg.ARCHETYPES) == {
        "command_center", "discovery_board", "instrument_analyzer",
        "regime_dashboard", "intelligence_desk", "editorial", "monitor",
        "marketing", "utility", "chart_workspace", "unclassified"}


@pytest.mark.parametrize("archetype", [
    "ranked_decision_board", "marketing_landing", "pricing", "dashboard", "", None])
def test_an_archetype_outside_the_vocabulary_is_a_hard_error(archetype):
    rows = _row()
    errors = reg.apply_overrides(rows, {"macro:alpha": {"archetype": archetype}},
                                 source_name="test.yml")
    assert errors, f"{archetype!r} was accepted"
    assert "is not one of" in errors[0]
    assert rows[0]["archetype"] == "unclassified"


@pytest.mark.parametrize("archetype", sorted(set(reg.ARCHETYPES)))
def test_every_vocabulary_member_is_settable(archetype):
    rows = _row()
    errors = reg.apply_overrides(rows, {"macro:alpha": {"archetype": archetype}},
                                 source_name="test.yml")
    assert errors == []
    assert rows[0]["archetype"] == archetype


def test_validate_rejects_a_derived_row_that_escaped_the_overlay():
    """--check reads a committed artifact a hand edit can reach without the overlay."""
    row = reg.blank_row("macro:alpha", "macro", "/alpha.html")
    row["archetype"] = "ranked_decision_board"
    row["source_evidence"] = ["scripts/x.py"]
    doc = {"schema": reg.SCHEMA, "generated_at": "2026-08-11T00:00:00Z",
           "sources": {"macro": {"available": True}}, "pages": [row]}
    assert any("is not one of" in p for p in reg.validate(doc))


def test_validate_rejects_a_malformed_design_system_in_a_committed_row():
    row = reg.blank_row("macro:alpha", "macro", "/alpha.html")
    row["design_system"] = {"compliant": True, "governed_regions": [{"template": "t"}]}
    row["source_evidence"] = ["scripts/x.py"]
    doc = {"schema": reg.SCHEMA, "generated_at": "2026-08-11T00:00:00Z",
           "sources": {"macro": {"available": True}}, "pages": [row]}
    assert any("must have exactly the keys" in p for p in reg.validate(doc))


# ---------------------------------------------------------------------------
# the committed artifact
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def committed() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_every_committed_row_carries_a_valid_design_system(committed):
    problems = []
    for row in committed["pages"]:
        problems.extend(reg._design_system_problems(row["design_system"],
                                                    row["page_id"]))
    assert problems == []


def test_no_committed_row_is_left_unclassified(committed):
    stragglers = [r["page_id"] for r in committed["pages"]
                  if r["archetype"] == "unclassified"]
    assert stragglers == []


def test_every_committed_archetype_is_in_the_vocabulary(committed):
    bad = sorted({r["archetype"] for r in committed["pages"]
                  if r["archetype"] not in reg.ARCHETYPES})
    assert bad == []


def test_nothing_claims_compliance_before_a_migration_pr_lands(committed):
    """R0 is report-only: a `compliant: true` row would arm enforcement early."""
    claimed = [r["page_id"] for r in committed["pages"]
               if r["design_system"].get("compliant")]
    assert claimed == []


def test_the_shared_dashboard_template_is_governed_per_render_not_per_file(committed):
    """templates/dashboard.html.j2 renders TWICE (build_site.py mode= macro|stocks).

    One whole-file claim would be two claims wearing one hat, so each row pins
    the body class that separates its render.
    """
    regions = {r["page_id"]: r["design_system"].get("governed_regions")
               for r in committed["pages"]
               if r["design_system"].get("governed_regions")}
    assert set(regions) == {"macro:macro", "macro:us_stocks"}
    assert regions["macro:macro"] == [
        {"template": "templates/dashboard.html.j2", "region": "body.page-macro"}]
    assert regions["macro:us_stocks"] == [
        {"template": "templates/dashboard.html.j2", "region": "body.page-stocks"}]


def test_the_overlay_assigns_an_archetype_to_every_committed_row(committed):
    overlay = yaml.safe_load(OVERRIDES.read_text(encoding="utf-8"))["pages"]
    missing = [r["page_id"] for r in committed["pages"]
               if not (overlay.get(r["page_id"]) or {}).get("archetype")]
    assert missing == []


def test_overlay_why_notes_stay_out_of_the_artifact(committed):
    """`why:` documents the overlay; only `note:` travels into the row."""
    overlay = yaml.safe_load(OVERRIDES.read_text(encoding="utf-8"))["pages"]
    whys = {pid: entry["why"] for pid, entry in overlay.items()
            if isinstance(entry, dict) and entry.get("why")}
    assert whys, "expected judgment calls to carry a why:"
    rows = {r["page_id"]: r for r in committed["pages"]}
    for pid, why in whys.items():
        assert why not in rows[pid]["notes"], pid
