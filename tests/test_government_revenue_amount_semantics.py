"""Government Revenue dollar figures of different CLASSES never become one number.

The lobe's central financial-honesty rule was written twice as prose —

    "obligation, outlay, ceiling, bookings, backlog, funded backlog, and GAAP revenue
     are never conflated"        (GOVERNMENT_REVENUE_FORESIGHT_ACCOUNT_HANDOFF.md)
    "funded obligations are never conflated with ceilings, appropriations,
     announcements, or GAAP revenue"  (GOVERNMENT_REVENUE_FORESIGHT_MASTERPLAN_FOR_FABLE.md)

— and enforced by nothing.  ``grep -rl 'obligat.*ceiling' tests/`` returned no match, so
the rule was a claim.  This suite is what makes it a rule.

Four dangerous mixes, each pinned below by a case that the guard MUST see:

  1. award-cumulative + transaction-delta   an award's deltas sum to its own cumulative,
                                            so the pair double-counts
  2. obligation + ceiling                   money COMMITTED added to money merely
                                            AUTHORISED reports capacity as activity
  3. obligation + outlay                    the committed dollar counted again when paid
  4. any of the above rendered into ONE figure with its class label left behind

Every assertion here is paired with the shape it would miss: the taxonomy's coverage is
asserted against a DERIVED set (so a new number column cannot join a ledger unclassified),
the payload rule is asserted non-vacuous (a rule that matches nothing reads green forever),
and the guard's precision is pinned as hard as its recall — an inventory list, a per-column
coercion loop, a rail VALIDATION, and two figures rendered side by side must all stay
silent, because a guard that cries wolf is switched off and then the rule is prose again.

Run: python -m pytest tests/test_government_revenue_amount_semantics.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.government_revenue import amount_semantics as sem  # noqa: E402
from scripts import check_government_revenue_amount_semantics as guard  # noqa: E402

PY = "engine/government_revenue/_case.py"
JS = "templates/government-revenue-_case.js"


def _rules(findings) -> set[str]:
    return {finding.rule for finding in findings}


# --------------------------------------------------------------- the four mixes


def test_mix1_award_cumulative_plus_transaction_delta_is_caught():
    """Summing an award's running total with one action's increment double-counts."""
    findings = guard.scan_python(PY, 'total = row["total_obligated"] + row["federal_action_obligation"]\n')
    assert _rules(findings) == {"mixed_class_sum"}
    assert "counts the same dollars twice" in findings[0].detail
    assert "award_cumulative" in findings[0].detail and "transaction_delta" in findings[0].detail


def test_mix1_is_caught_through_locals_not_only_string_literals():
    """The real arithmetic in this lobe runs on locals, not on inline column keys."""
    source = (
        'cumulative = pd.to_numeric(frame.get("total_obligated"), errors="coerce")\n'
        'delta = pd.to_numeric(actions.get("federal_action_obligation"), errors="coerce")\n'
        'exposure = cumulative + delta\n'
    )
    findings = guard.scan_python(PY, source)
    assert _rules(findings) == {"mixed_class_sum"}


def test_mix2_obligation_plus_ceiling_is_caught():
    """A ceiling may never be spent; adding it to an obligation reports capacity as activity."""
    findings = guard.scan_python(PY, 'exposure = sum([row["total_obligated"], row["potential_award_amount"]])\n')
    assert _rules(findings) == {"mixed_class_sum"}
    assert "AUTHORISED" in findings[0].detail


def test_mix2_is_caught_in_a_fallback_ladder():
    """The quietest form: an obligation on most rows, a CEILING where only the last rung survives."""
    source = (
        'for col in ("total_obligated", "award_amount", "current_award_amount"):\n'
        '    if col in frame.columns:\n'
        '        weights = frame[col]\n'
        '        break\n'
    )
    findings = guard.scan_python(PY, source)
    assert _rules(findings) == {"mixed_class_fallback"}
    assert "ceiling" in findings[0].detail


def test_mix2_is_caught_in_a_get_default_chain():
    """``row.get("a", row.get("b"))`` is a two-rung ladder wearing different syntax."""
    findings = guard.scan_python(PY, 'v = row.get("total_obligated", row.get("potential_award_amount"))\n')
    assert _rules(findings) == {"mixed_class_default"}
    assert "AUTHORISED" in findings[0].detail


def test_mix3_obligation_plus_outlay_is_caught():
    """An outlay is cash paid against an obligation — the pair counts one dollar twice."""
    findings = guard.scan_python(PY, 'spend = row["total_obligation"] + row["total_outlay"]\n')
    assert _rules(findings) == {"mixed_class_sum"}
    assert "outlay" in findings[0].detail


def test_mix4_figure_published_without_its_class_label_is_caught():
    """A published amount fact must carry the class, not only the number."""
    findings = guard.scan_python(PY, 'fact = {"id": "total_obligated", "value": v, "currency": "USD"}\n')
    assert _rules(findings) == {"unlabelled_figure"}
    assert "no class label travelling with it" in findings[0].detail


def test_mix4_label_from_the_wrong_class_is_caught():
    """A label that travels but describes a different measurement is worse than none."""
    source = 'fact = {"id": "potential_award_amount", "value": v, "currency": "USD", "semantic": "obligated"}\n'
    findings = guard.scan_python(PY, source)
    assert _rules(findings) == {"unlabelled_figure"}
    assert "is ceiling but is labelled" in findings[0].detail


def test_mix4_is_caught_in_a_built_payload_not_only_in_source():
    """Static rules read literals; a payload is where the figure crosses the publish boundary."""
    payload = {"amounts": [{"id": "total_obligated", "value": 1.0, "currency": "USD"}]}
    findings = guard.scan_payload("payload.json", payload)
    assert _rules(findings) == {"unlabelled_figure"}
    labelled = {"amounts": [{
        "id": "total_obligated", "value": 1.0, "currency": "USD",
        "semantic": "obligated", "label_code": "reported_obligations",
    }]}
    assert guard.scan_payload("payload.json", labelled) == []


def test_mix4_reaches_the_rendered_surface_too():
    """One displayed figure built from two classes is the same defect one layer out."""
    findings = guard.scan_surface(JS, "html+=money(a.total_obligated+a.potential_award_amount);")
    assert _rules(findings) == {"unlabelled_figure"}


def test_template_fallback_ladder_across_classes_is_caught():
    findings = guard.scan_surface(JS, "var v=money(label(a,['total_obligated','current_award_amount'],null));")
    assert "mixed_class_fallback" in _rules(findings)


# ----------------------------------------------------- precision (the other half)


@pytest.mark.parametrize(
    "why, source",
    [
        (
            "ceiling MINUS obligation is the lobe's published headroom, not a total",
            'headroom = row["potential_award_amount"] - row["total_obligated"]\n',
        ),
        (
            "obligation MINUS outlay is the unliquidated balance",
            'unliquidated = row["total_obligation"] - row["total_outlay"]\n',
        ),
        (
            "a same-class ladder is a legitimate alias fallback",
            'v = _first_number(row, ("total_obligated", "award_amount"))\n',
        ),
        (
            "an inventory of amount columns is carried separately, never totalled",
            'SNAPSHOT_STATE_FIELDS = ("total_obligation", "current_award_amount", "potential_award_amount")\n',
        ),
        (
            "a per-column coercion loop visits every member and selects nothing",
            'for col in ("total_obligated", "current_award_amount"):\n    frame[col] = coerce(frame[col])\n',
        ),
        (
            "validating that two rails carry the RIGHT fields keeps the classes apart",
            'if a.get("field") != "total_obligation" or b.get("field") != "federal_action_obligation":\n'
            '    raise ValueError("wrong rails")\n',
        ),
        (
            "a nullability idiom on a projected dict totals nothing",
            'compact = _present_fields(event, ("total_obligated", "current_award_amount")) or None\n',
        ),
    ],
)
def test_legitimate_shapes_are_not_findings(why, source):
    assert guard.scan_python(PY, source) == [], why


def test_two_figures_side_by_side_are_the_honest_presentation():
    """The dossier's Obligated / Current value / Potential ceiling row is correct design."""
    surface = (
        "html+='<b>'+money(a.total_obligated)+'</b>'"
        "+'<b>'+money(a.current_award_amount)+'</b>'"
        "+'<b>'+money(a.potential_award_amount)+'</b>';"
    )
    assert guard.scan_surface(JS, surface) == []


def test_an_assigned_key_inventory_in_a_template_is_not_a_ladder():
    surface = "var RECOMPETE_KEYS = ['total_obligated','current_award_amount','potential_award_amount'];"
    assert guard.scan_surface(JS, surface) == []


def test_unparseable_python_fails_closed():
    """A subject the guard cannot read must read as a finding, never as clean."""
    findings = guard.scan_python(PY, "def broken(:\n")
    assert _rules(findings) == {"unparseable"}


# --------------------------------------------------------------- the taxonomy


def test_every_collector_declared_number_column_has_a_class():
    """A number column cannot join a canonical ledger list without a semantic class.

    The subject set is DERIVED from the collector's own declarations, so this fails the
    day a new amount column lands unclassified — the defect shape this lobe keeps hitting
    ("a column joined a canonical list and something downstream never followed").
    """
    assert sem.unclassified_canonical_fields() == frozenset()


def test_the_derived_subject_set_is_not_empty():
    """A coverage guard whose subject set collapses to nothing reads green forever."""
    canonical = sem.canonical_numeric_fields()
    assert len(canonical) >= 5
    assert {"total_obligated", "federal_action_obligation", "total_obligation"} <= canonical


def test_alias_fields_are_exactly_the_names_the_collector_does_not_declare():
    """The alias list is auditable by subtraction rather than by trust."""
    assert sem.alias_fields() == frozenset({"award_amount", "obligation_delta"})
    assert sem.alias_fields() & sem.canonical_numeric_fields() == frozenset()


@pytest.mark.parametrize(
    "field, expected",
    [
        ("total_obligation", sem.AmountClass.AWARD_CUMULATIVE),
        ("total_obligated", sem.AmountClass.AWARD_CUMULATIVE),
        ("award_amount", sem.AmountClass.AWARD_CUMULATIVE),
        ("federal_action_obligation", sem.AmountClass.TRANSACTION_DELTA),
        ("obligation_delta", sem.AmountClass.TRANSACTION_DELTA),
        ("current_award_amount", sem.AmountClass.CEILING),
        ("potential_award_amount", sem.AmountClass.CEILING),
        ("total_outlay", sem.AmountClass.OUTLAY),
        ("total_outlays", sem.AmountClass.OUTLAY),
    ],
)
def test_declared_classes(field, expected):
    assert sem.classify(field) is expected


def test_unknown_names_carry_no_class_and_never_imply_compatibility():
    assert sem.classify("opportunity_value") is None
    assert sem.classify(None) is None
    # Silence is "unknown", not "combinable": an unknown name beside a classified one
    # must not manufacture a conflict either.
    assert sem.conflict_reason(["total_obligated", "opportunity_value"]) is None


def test_every_published_semantic_label_maps_to_a_real_class():
    assert all(isinstance(cls, sem.AmountClass) for cls in sem.AMOUNT_SEMANTIC_CLASSES.values())


def test_every_class_has_bilingual_plain_words():
    """Glance tier: a reader sees plain words, never ``potential_award_amount``."""
    for cls in sem.AmountClass:
        label_en, label_zh = sem.CLASS_LABELS[cls]
        meaning_en, meaning_zh = sem.CLASS_MEANINGS[cls]
        assert label_en and label_zh and meaning_en and meaning_zh
        assert "_" not in label_en and "_" not in label_zh
        assert any("一" <= ch <= "鿿" for ch in label_zh)
        assert any("一" <= ch <= "鿿" for ch in meaning_zh)


# ------------------------------------------------------------ the runtime API


@pytest.mark.parametrize(
    "fields, needle",
    [
        (("total_obligated", "federal_action_obligation"), "twice"),
        (("total_obligated", "potential_award_amount"), "AUTHORISED"),
        (("total_obligation", "total_outlay"), "again when it is paid"),
        (("current_award_amount", "total_outlays"), "two different points"),
    ],
)
def test_assert_combinable_refuses_each_dangerous_pair(fields, needle):
    with pytest.raises(sem.AmountClassConflict) as excinfo:
        sem.assert_combinable(fields, context="test figure")
    assert needle in str(excinfo.value)
    assert "test figure" in str(excinfo.value)


def test_assert_combinable_returns_the_shared_class():
    assert sem.assert_combinable(("total_obligated", "award_amount"), context="x") is sem.AmountClass.AWARD_CUMULATIVE
    assert sem.assert_combinable((), context="x") is None


def test_checked_sum_adds_within_a_class_and_refuses_across_one():
    assert sem.checked_sum({"total_obligated": 10.0, "award_amount": 5.0}, context="x") == 15.0
    with pytest.raises(sem.AmountClassConflict):
        sem.checked_sum({"total_obligated": 10.0, "total_outlay": 5.0}, context="x")


def test_checked_fallback_refuses_a_mixed_class_ladder_before_it_reads_a_row():
    row = {"current_award_amount": 7.0}
    assert sem.checked_fallback(row, ("total_obligated", "award_amount"), context="x") is None
    with pytest.raises(sem.AmountClassConflict):
        sem.checked_fallback(row, ("total_obligated", "current_award_amount"), context="x")


def test_amount_fact_carries_the_class_with_the_number():
    fact = sem.amount_fact("potential_award_amount", 12.0, source_ref="https://example.gov/a")
    assert fact["amount_class"] == "ceiling"
    assert fact["class_label_en"] == "Authorised ceiling"
    assert "never be funded" in fact["class_meaning_zh"] or fact["class_meaning_zh"]
    assert fact["currency"] == "USD"
    assert sem.assert_figure_labeled(fact, context="x") is sem.AmountClass.CEILING


def test_amount_fact_refuses_an_undeclared_field_and_a_cross_class_label():
    with pytest.raises(sem.AmountClassConflict):
        sem.amount_fact("opportunity_value", 1.0)
    with pytest.raises(sem.AmountClassConflict):
        sem.amount_fact("potential_award_amount", 1.0, semantic="obligated")


def test_assert_figure_labeled_refuses_a_bare_number():
    with pytest.raises(sem.AmountClassConflict) as excinfo:
        sem.assert_figure_labeled({"id": "total_obligated", "value": 1.0, "currency": "USD"}, context="award card")
    assert "no class label travelling with it" in str(excinfo.value)


# ------------------------------------------------------- the tree, as it stands


def test_the_shipped_lobe_mixes_no_amount_classes():
    """The gate itself. Government Revenue source + rendered surfaces, as committed."""
    findings = guard.scan_tree()
    assert findings == [], "\n".join(str(f) for f in findings)


def test_the_gate_scans_the_surfaces_it_claims_to():
    """A gate pointed at nothing passes forever; pin the subjects by name."""
    subjects = {path.relative_to(guard.ROOT).as_posix() for path in guard.subject_paths()}
    assert "engine/government_revenue/metrics.py" in subjects
    assert "engine/government_revenue/workspace.py" in subjects
    assert "engine/government_revenue/dossiers.py" in subjects
    assert "scripts/build_government_revenue.py" in subjects
    assert "templates/government_revenue.html.j2" in subjects
    assert "templates/government-revenue-dossiers.js" in subjects
    assert len(subjects) >= 20


def test_the_concentration_weight_ladder_stays_single_class():
    """Regression: the third rung was ``current_award_amount``.

    ``_concentration`` publishes ``covered_obligations`` and feeds the user-facing
    customer-concentration read, so a CEILING rung meant that a frame arriving without an
    obligated column produced shares, an HHI, and a total computed from money merely
    authorised — under the word "obligations".
    """
    from engine.government_revenue import metrics

    assert metrics._CONCENTRATION_WEIGHT_FIELDS == ("total_obligated", "award_amount")
    assert sem.assert_combinable(
        metrics._CONCENTRATION_WEIGHT_FIELDS, context="concentration weights"
    ) is sem.AmountClass.AWARD_CUMULATIVE


@pytest.mark.parametrize(
    "artifact",
    ["data/government_revenue/latest.json", "data/government_revenue/workspace.json"],
)
def test_published_amount_facts_carry_their_class(artifact):
    """The rule applied to the artifact, and proof the rule can SEE something there."""
    path = ROOT / artifact
    if not path.exists():  # pragma: no cover - artifact is committed on main
        pytest.skip(f"{artifact} not present in this checkout")
    payload = json.loads(path.read_text(encoding="utf-8"))
    seen = 0

    def walk(node):
        nonlocal seen
        if isinstance(node, dict):
            if {"value", "currency"} <= set(node) and sem.classify(node.get("id")) is not None:
                seen += 1
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    assert seen > 0, f"{artifact}: the payload rule matched no amount fact — vacuously clean"
    assert guard.scan_payload(artifact, payload) == []


def test_guard_selftest_passes():
    assert guard.selftest() == 0
