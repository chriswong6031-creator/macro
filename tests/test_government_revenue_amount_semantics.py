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


# ------------------------------------- the two shapes that already fooled this guard
#
# Both were found by injecting a real conflation into the real ``metrics.py`` and watching
# the gate print "OK — no figure mixes amount classes".  A rule fixed once is a rule that
# rots, so each is pinned here AS THE MUTATION: the anchor is asserted present in the
# shipped source (so the test cannot go vacuous when the source moves), the unmutated
# source is asserted clean at that site (so the finding is attributable to the mutation and
# not to background noise), and the mutated source must produce a mixed_class_sum naming
# the two classes.

METRICS = "engine/government_revenue/metrics.py"


def _metrics_source() -> str:
    return (ROOT / METRICS).read_text(encoding="utf-8")


def _mutate(source: str, old: str, new: str) -> str:
    """Replace an anchor that MUST exist exactly once, else the test is vacuous."""
    assert source.count(old) == 1, (
        f"{METRICS}: mutation anchor is not present exactly once — this test can no "
        f"longer prove anything.  Anchor:\n{old}"
    )
    return source.replace(old, new)


def test_mutation_backlog_headroom_addition_is_seen_through_the_defensive_rebind():
    """_backlog's ``current - obligated`` flipped to ``+`` must go RED.

    This is the mix the guard exists to refuse — a CEILING added to an OBLIGATION — and
    for the whole of PR #4950's first round it scanned clean, because ``_backlog`` writes
    every amount local with the lobe's defensive rebind::

        obligated = pd.to_numeric(active.get("total_obligated"), errors="coerce")
        if obligated is None:
            obligated = pd.Series(float("nan"), index=active.index)

    and the tracker popped the local's class on the class-neutral second assignment.  The
    function was therefore invisible to the matcher in its entirety.
    """
    source = _metrics_source()
    assert guard.scan_python(METRICS, source) == [], "shipped metrics.py is not clean"
    mutated = _mutate(
        source,
        "float((current[current_mask] - obligated[current_mask]).clip(lower=0).sum())",
        "float((current[current_mask] + obligated[current_mask]).clip(lower=0).sum())",
    )
    findings = guard.scan_python(METRICS, mutated)
    assert _rules(findings) == {"mixed_class_sum"}, [str(f) for f in findings]
    detail = " ".join(f.detail for f in findings)
    assert "ceiling" in detail and "award_cumulative" in detail, detail


def test_mutation_concentration_total_plus_outlays_is_seen_through_the_loop_variable():
    """_concentration's published total plus an outlay total must go RED.

    ``weights`` is bound from ``frame[col]`` where ``col`` is the LOOP VARIABLE of
    ``for col in _CONCENTRATION_WEIGHT_FIELDS``, so it carried no class, and the ``+`` rule
    needs both operands classed.  An obligation-weighted total added to an outlay total —
    published under the key ``covered_obligations``, in the very function whose ceiling
    rung this PR removed — therefore scanned clean.
    """
    source = _metrics_source()
    assert guard.scan_python(METRICS, source) == [], "shipped metrics.py is not clean"
    mutated = _mutate(
        source,
        "    total = float(weights.sum())\n",
        '    total = float(weights.sum()) + '
        'float(pd.to_numeric(frame["total_outlays"], errors="coerce").sum())\n',
    )
    findings = guard.scan_python(METRICS, mutated)
    assert _rules(findings) == {"mixed_class_sum"}, [str(f) for f in findings]
    detail = " ".join(f.detail for f in findings)
    assert "outlay" in detail and "award_cumulative" in detail, detail


def test_the_defensive_rebind_idiom_is_still_in_metrics_where_it_blinded_the_guard():
    """Proof the mutation tests above exercise the idiom, not a hypothetical.

    If the lobe ever stops writing the rebind, the two tests above would still pass while
    silently no longer testing the thing they name.
    """
    source = _metrics_source()
    assert source.count('obligated = pd.Series(float("nan"), index=active.index)') == 1
    assert "for col in _CONCENTRATION_WEIGHT_FIELDS:" in source


# ---------------------------------- the re-binding rule, pinned in BOTH directions


def test_a_class_neutral_rebind_preserves_the_class():
    """The guard-clause placeholder is the ABSENCE of the quantity, not a new one."""
    source = (
        'obligated = pd.to_numeric(active.get("total_obligated"), errors="coerce")\n'
        "if obligated is None:\n"
        '    obligated = pd.Series(float("nan"), index=active.index)\n'
        'ceiling = row["potential_award_amount"]\n'
        "exposure = obligated + ceiling\n"
    )
    findings = guard.scan_python(PY, source)
    assert _rules(findings) == {"mixed_class_sum"}, [str(f) for f in findings]


@pytest.mark.parametrize(
    "placeholder",
    [
        'pd.Series(float("nan"), index=active.index)',
        "0.0",
        "None",
        "pd.DataFrame()",
        "frame.iloc[0:0]",
    ],
)
def test_every_placeholder_shape_preserves_the_class(placeholder):
    source = (
        'obligated = pd.to_numeric(active.get("total_obligated"), errors="coerce")\n'
        f"obligated = {placeholder}\n"
        'total = obligated + row["total_outlay"]\n'
    )
    assert _rules(guard.scan_python(PY, source)) == {"mixed_class_sum"}


def test_a_rebind_to_a_DIFFERENT_class_still_overwrites():
    """Preserving is only for silence.  Real counter-evidence keeps Python's last-wins.

    Here the second bind genuinely re-measures the local as a ceiling, so adding it to
    another ceiling is a same-class sum and must NOT be reported.  Were the rule "union
    the classes" instead of "silence does not clobber", this would be a false positive.
    """
    source = (
        'x = row["total_obligated"]\n'
        'x = row["current_award_amount"]\n'
        'total = x + row["potential_award_amount"]\n'
    )
    assert guard.scan_python(PY, source) == []


def test_a_rebind_to_a_different_class_is_caught_against_its_NEW_class():
    source = (
        'x = row["current_award_amount"]\n'
        'x = row["total_obligated"]\n'
        'total = x + row["potential_award_amount"]\n'
    )
    assert _rules(guard.scan_python(PY, source)) == {"mixed_class_sum"}


def test_a_first_bind_that_carries_no_class_stays_unclassed():
    """Preservation resurrects nothing: a name that never had a class does not gain one."""
    source = 'x = compute()\ntotal = x + row["total_obligated"]\n'
    assert guard.scan_python(PY, source) == []


def test_a_right_hand_side_that_itself_spans_classes_leaves_the_name_unclassed():
    """An ambiguous value carries no single class; the mix is reported where it happens."""
    source = (
        'mask = row["total_obligated"] + row["current_award_amount"]\n'
        'total = mask + row["total_outlay"]\n'
    )
    findings = guard.scan_python(PY, source)
    assert len(findings) == 1 and findings[0].line == 1, [str(f) for f in findings]


# ------------------------------- the loop-variable rule, pinned in BOTH directions


def test_a_loop_variable_over_a_single_class_ladder_carries_that_class():
    source = (
        'WEIGHTS = ("total_obligated", "award_amount")\n'
        "for col in WEIGHTS:\n"
        "    if col in frame.columns:\n"
        "        weights = pd.to_numeric(frame[col])\n"
        "        break\n"
        'total = float(weights.sum()) + float(frame["total_outlays"].sum())\n'
    )
    assert _rules(guard.scan_python(PY, source)) == {"mixed_class_sum"}


def test_a_loop_variable_over_a_MIXED_ladder_carries_no_class():
    """The loop is already a mixed_class_fallback; guessing one of its two classes would
    attribute an invented measurement to everything the variable touches."""
    source = (
        'LADDER = ("total_obligated", "current_award_amount")\n'
        "for col in LADDER:\n"
        "    if col in frame.columns:\n"
        "        weights = frame[col]\n"
        "        break\n"
        'total = float(weights.sum()) + float(frame["total_outlays"].sum())\n'
    )
    findings = guard.scan_python(PY, source)
    assert _rules(findings) == {"mixed_class_fallback"}, [str(f) for f in findings]


def test_a_loop_over_an_unknowable_domain_binds_nothing():
    """``for col in frame.columns`` is unread, and this guard does not guess."""
    source = (
        "for col in frame.columns:\n"
        "    weights = frame[col]\n"
        'total = float(weights.sum()) + float(frame["total_outlays"].sum())\n'
    )
    assert guard.scan_python(PY, source) == []


# ---------------------------------- the scoping rule, pinned in BOTH directions
#
# THE RULE: a name proved inside a function does not carry its class out of that
# function.  An inner scope may READ an enclosing binding; it may only WRITE into its
# own, unless it declares ``global``/``nonlocal``.
#
# Before scoping, ``_name_class`` was ONE FLAT DICT for the whole module, and the
# never-clobber-on-class-neutral-rebind rule above made that permanent.  Measured on the
# real metrics.py: ``_backlog``'s ``current_total``/``funded_total`` floats stayed classed
# for ~1,000 further lines, so an expression injected into ``_catalysts`` — a different
# function, where neither name exists — was REPORTED as a ceiling added to a transaction
# delta.  Every test below is paired with its non-vacuity proof: the same shape placed
# where the names really live must still go RED, or "silent" would mean "the tracker died"
# rather than "the tracker learned where the name lives".


_CATALYSTS_SITE = '    agency = metrics.get("agency_concentration") or {}\n'
_BACKLOG_SITE = "    funding_pct = 100.0 * funded_total / current_total if current_total > 0 else None\n"
_MODIFICATION_SITE = "    denom = float(trailing[trailing > 0].sum())\n"


def _inject(source: str, anchor: str, statement: str) -> str:
    """Insert ``statement`` immediately BEFORE an anchor that must exist exactly once."""
    return _mutate(source, anchor, f"{statement}{anchor}")


@pytest.mark.parametrize("leaked", ["current_total", "funded_total"])
def test_a_backlog_local_is_not_still_classed_a_thousand_lines_later(leaked):
    """``float(current_total) + float(denom)`` inside ``_catalysts`` is NOT a finding.

    Both measured false positives, pinned at the real site the reviewer measured them at.
    ``current_total`` and ``funded_total`` are ``_backlog``'s guard floats; ``denom`` is
    ``_modification_metrics``' denominator.  None of the three is a name of ``_catalysts``,
    so the expression names nothing and mixes nothing — the guard was inventing a
    ceiling-plus-delta out of two locals it could not see.
    """
    source = _metrics_source()
    assert guard.scan_python(METRICS, source) == [], "shipped metrics.py is not clean"
    injected = _inject(source, _CATALYSTS_SITE, f"    _leak = float({leaked}) + float(denom)\n")
    findings = guard.scan_python(METRICS, injected)
    assert findings == [], [str(f) for f in findings]


def test_those_backlog_locals_are_still_tracked_where_they_actually_live():
    """Non-vacuity for the two tests above: silence must be SCOPE, not a dead tracker.

    ``current_total`` is a ceiling total and ``funded_total`` an obligation total, both
    proved inside ``_backlog``.  Added to each other IN ``_backlog`` they are exactly the
    mix this file refuses, so this must go red — otherwise the negative tests above would
    keep passing after a change that simply stopped tracking either name.
    """
    source = _metrics_source()
    injected = _inject(
        _metrics_source(), _BACKLOG_SITE, "    _probe = float(current_total) + float(funded_total)\n"
    )
    findings = guard.scan_python(METRICS, injected)
    assert _rules(findings) == {"mixed_class_sum"}, [str(f) for f in findings]
    detail = " ".join(f.detail for f in findings)
    assert "ceiling" in detail and "award_cumulative" in detail, detail
    assert guard.scan_python(METRICS, source) == []


def test_the_modification_denominator_is_still_tracked_where_it_actually_lives():
    """Non-vacuity for ``denom``, the other half of both false positives."""
    injected = _inject(
        _metrics_source(),
        _MODIFICATION_SITE,
        '    _probe = float(trailing.sum()) + float(pd.to_numeric(frame["total_outlays"]).sum())\n',
    )
    findings = guard.scan_python(METRICS, injected)
    assert _rules(findings) == {"mixed_class_sum"}, [str(f) for f in findings]
    detail = " ".join(f.detail for f in findings)
    assert "outlay" in detail and "transaction_delta" in detail, detail


@pytest.mark.parametrize(
    "leaked",
    ["current_total", "funded_total", "obligated", "current", "potential", "denom", "weights", "shares"],
)
def test_no_function_local_survives_into_module_scope(leaked):
    """The leak itself, asserted structurally rather than only through its symptoms.

    Each of these is a local of exactly one function in metrics.py.  If any is visible at
    module scope after the whole file is traversed, every later function in the file has
    inherited it and the two false positives above are back.
    """
    import ast

    tree = ast.parse(_metrics_source())
    scanner = guard._PythonScanner(METRICS, guard._first_wins_readers(tree))
    scanner.visit(tree)
    assert len(scanner._scopes) == 1, "the scope stack did not unwind"
    assert scanner._scopes[0].classes.get(leaked) is None


def _functions_holding_amount_state(rel: str, source: str) -> dict[str, list[str]]:
    """Functions whose OWN locals the scanner proved a class for, by scanning the source.

    The scanner discards a scope when it pops, so the census re-implements the pop and
    reads the scope on the way out.  Nothing about the rule is re-stated here — it is the
    real ``_PythonScanner`` doing the real traversal.
    """
    import ast

    class _Census(guard._PythonScanner):
        def __init__(self, path, readers):
            super().__init__(path, readers)
            self.owners: dict[str, list[str]] = {}
            self._stack: list[str] = []

        def _scoped(self, kind, node):
            self._scopes.append(guard._Scope(kind))
            try:
                self.generic_visit(node)
                classed = sorted(n for n, c in self._scopes[-1].classes.items() if c is not None)
                if classed and kind == "function" and self._stack:
                    self.owners.setdefault(self._stack[-1], []).extend(classed)
            finally:
                self._scopes.pop()

        def _enter(self, node):
            self._stack.append(node.name)
            try:
                self._scoped("function", node)
            finally:
                self._stack.pop()

        def visit_FunctionDef(self, node):
            self._enter(node)

        def visit_AsyncFunctionDef(self, node):
            self._enter(node)

    tree = ast.parse(source)
    census = _Census(rel, guard._first_wins_readers(tree))
    census.visit(tree)
    return census.owners


def test_the_scoping_rule_bites_in_three_modules_not_one():
    """Where per-function amount state actually lives, measured rather than remembered.

    A build report for the scoping round counted FOUR functions in ``metrics.py`` and ONE
    in ``award_events.py`` and stopped there.  ``workspace._recompete_workspace_event``
    proves a class for ``obligated`` and ``ratio`` as well, so the rule bites in SIX
    functions across THREE modules — which is the difference between "scoping matters in
    one file" and "scoping matters wherever this lobe does arithmetic".

    Asserted as a floor, not an equality: the census may GROW when the lobe grows an
    amount local, and pinning the exact set would turn every such edit into a red.  What
    it may not do is shrink to nothing — a scoping rule with no per-function state left to
    scope would leave every test in this section passing while testing nothing.
    """
    measured: dict[str, dict[str, list[str]]] = {}
    for module in (
        "engine/government_revenue/metrics.py",
        "engine/government_revenue/award_events.py",
        "engine/government_revenue/workspace.py",
    ):
        source = (ROOT / module).read_text(encoding="utf-8")
        measured[module] = _functions_holding_amount_state(module, source)

    for module, function in (
        ("engine/government_revenue/metrics.py", "_backlog"),
        ("engine/government_revenue/metrics.py", "_catalysts"),
        ("engine/government_revenue/metrics.py", "_concentration"),
        ("engine/government_revenue/metrics.py", "_modification_metrics"),
        ("engine/government_revenue/award_events.py", "_action_classification"),
        ("engine/government_revenue/workspace.py", "_recompete_workspace_event"),
    ):
        assert function in measured[module], (
            f"{module}:{function} no longer holds per-function amount state — the scoping "
            f"tests above may now be vacuous.  Measured: "
            f"{ {m: sorted(f) for m, f in measured.items()} }"
        )
    assert {"obligated", "ratio"} <= set(
        measured["engine/government_revenue/workspace.py"]["_recompete_workspace_event"]
    )


def test_an_inner_scope_reads_an_enclosing_binding():
    """Scoping narrows WRITES, not reads — a closure really does see the outer name."""
    source = (
        'LADDER = ("total_obligated", "award_amount")\n'
        "def outer():\n"
        "    obligated = _first_number(row, LADDER)\n"
        "    def inner():\n"
        '        return obligated + row["potential_award_amount"]\n'
        "    return inner\n"
    )
    assert _rules(guard.scan_python(PY, source)) == {"mixed_class_sum"}


def test_an_inner_scope_does_not_write_into_an_enclosing_one():
    source = (
        "def proves_it():\n"
        '    obligated = row["total_obligated"]\n'
        "def elsewhere():\n"
        '    return obligated + row["potential_award_amount"]\n'
    )
    assert guard.scan_python(PY, source) == []


def test_a_local_shadows_an_enclosing_binding_of_the_same_name():
    """A name a function assigns is that function's own; it must not inherit outward."""
    source = (
        'obligated = row["total_obligated"]\n'
        "def f():\n"
        "    obligated = compute()\n"
        '    return obligated + row["potential_award_amount"]\n'
    )
    assert guard.scan_python(PY, source) == []


def test_global_and_nonlocal_write_outward_as_python_does():
    """``metrics.py`` really uses ``nonlocal`` (the recipient-graph loader), so the
    declaration cannot be treated as a no-op."""
    with_global = (
        "def f():\n"
        "    global obligated\n"
        '    obligated = row["total_obligated"]\n'
        "def g():\n"
        '    return obligated + row["potential_award_amount"]\n'
    )
    assert _rules(guard.scan_python(PY, with_global)) == {"mixed_class_sum"}
    with_nonlocal = (
        "def outer():\n"
        "    obligated = None\n"
        "    def inner():\n"
        "        nonlocal obligated\n"
        '        obligated = row["total_obligated"]\n'
        "    inner()\n"
        '    return obligated + row["potential_award_amount"]\n'
    )
    assert _rules(guard.scan_python(PY, with_nonlocal)) == {"mixed_class_sum"}


def test_a_comprehension_does_not_write_into_the_scope_around_it():
    source = (
        "def f():\n"
        '    rows = [obligated for obligated in frame["total_obligated"]]\n'
        '    return obligated + row["potential_award_amount"]\n'
    )
    assert guard.scan_python(PY, source) == []


# ------------------------------ the value-position rule, pinned in BOTH directions
#
# THE RULE: a class describes what a figure is a measurement OF, so it is read only from
# the parts of an expression that can BE the value — never from a part that merely decides
# which value is taken, and never past a call whose result is a different KIND of thing.
#
# Measured on the real award_events.py, the tracker had classed ``event_type``, ``verb``,
# ``kind`` and ``amount_type`` — STRING LABELS, every one — as ``transaction_delta``,
# because it read the TEST of the conditional that chose between two words.  ``len(...)``
# was the other vector: the reviewer's ``len(value_items) + len(changes)`` was reported as
# a ceiling added to a delta, and two counts are dimensionless.
#
# What this rule deliberately does NOT do is refuse provenance through an opaque helper
# call (``changes = _changed_fields(prior, current, ...)``).  The result KIND of a call
# this guard has never heard of is unknown, and the module's law is that an unknown is not
# reclassified — refusing there would also refuse
# ``pd.to_numeric(active.get("total_obligated"), errors="coerce")``, the binding both
# mutation tests above rest on.


def test_a_conditions_class_does_not_become_the_chosen_values_class():
    """``verb`` is a WORD.  ``amount`` chooses between two words; it is not the word."""
    source = (
        'amount = row["federal_action_obligation"]\n'
        'verb = "deobligation" if amount < 0 else "positive contract action"\n'
        'label = verb + str(row["potential_award_amount"])\n'
    )
    assert guard.scan_python(PY, source) == []


def test_a_conditional_still_carries_the_class_of_the_VALUE_it_chooses():
    """Non-vacuity: only the TEST is pruned.  Both branches are still read."""
    source = (
        'amount = row["current_award_amount"] if flag else row["potential_award_amount"]\n'
        'total = amount + row["total_obligated"]\n'
    )
    assert _rules(guard.scan_python(PY, source)) == {"mixed_class_sum"}


def test_two_counts_are_not_two_amounts():
    """The reviewer's ``len(value_items) + len(changes)``, reduced to its shape.

    It fired on the guard as first committed.  A count of ceiling-valued facts plus a
    count of change records is a cardinality, and cardinality is the same 'thing' on both
    sides — nothing about it double-counts a dollar.
    """
    source = (
        'ceilings = row["current_award_amount"]\n'
        'deltas = row["federal_action_obligation"]\n'
        "n = len(ceilings) + len(deltas)\n"
    )
    assert guard.scan_python(PY, source) == []


def test_the_same_two_names_added_WITHOUT_len_still_go_red():
    """Non-vacuity for the test above: the prune is ``len``, not the two names."""
    source = (
        'ceilings = row["current_award_amount"]\n'
        'deltas = row["federal_action_obligation"]\n'
        "n = ceilings + deltas\n"
    )
    assert _rules(guard.scan_python(PY, source)) == {"mixed_class_sum"}


def test_a_container_is_not_one_figure():
    """``value_items = [...]`` is a LIST of facts; classing it says a list is a dollar."""
    source = (
        'value_items = [by_name[n] for n in ("current_award_amount", "potential_award_amount")]\n'
        'total = value_items + row["total_obligated"]\n'
    )
    assert guard.scan_python(PY, source) == []


def test_a_total_over_a_container_still_reads_inside_it():
    """Non-vacuity: refusing to class the CONTAINER never stops a rule that folds it."""
    source = 'exposure = sum([row["total_obligated"], row["potential_award_amount"]])\n'
    assert _rules(guard.scan_python(PY, source)) == {"mixed_class_sum"}


# --------------------------- the container-member rule, pinned in BOTH directions
#
# THE RULE: a name bound to a collection of amounts is not itself a figure, but it IS a
# collection of figures — so the members' classes are kept against the name and recovered
# wherever the collection is folded back into one number (a total, an element read).
#
# Before this, a container binding was classed ``frozenset()`` and only an ALL-STRING
# container was recoverable, so the members survived exactly as long as the collection was
# a LITERAL AT THE CALL SITE.  The differential below is one source shape written four
# ways: the version written inside ``sum()`` went red and the three where the same list
# was hoisted to a name — by hand, or by a comprehension, or read back by index — all
# scanned clean.  A blind spot a reader closes by hoisting one line is not a rule.
#
# The precision half is the round-2 lesson applied to containers: BUILDING a list of an
# obligation and a ceiling is legal (it is how the dossier renders them side by side), so
# nothing is reported at the binding; a container of non-amounts stays unclassed under the
# value-position rule; and an element read out of a MIXED container carries NO class,
# because which member an index picks is not knowable here — the same coin-flip refusal
# the loop-variable and reader-result rules make.


@pytest.mark.parametrize(
    "shape, source",
    [
        (
            "R1 a list literal hoisted out of the sum()",
            'vals = [row["total_obligated"], row["total_obligation"]]\n'
            'total = sum(vals) + row["total_outlays"]\n',
        ),
        (
            "R2 CONTROL — the same list written INSIDE the sum()",
            'total = sum([row["total_obligated"], row["total_obligation"]]) + row["total_outlays"]\n',
        ),
        (
            "R3 the same collection built by a comprehension",
            'vals = [r["total_obligated"] for r in rows]\n'
            'total = sum(vals) + rows[0]["total_outlays"]\n',
        ),
        (
            "R4 the collection read back by index instead of totalled",
            'pair = (row["total_obligated"], row["total_obligation"])\n'
            'total = pair[0] + row["total_outlays"]\n',
        ),
    ],
)
def test_obligations_plus_an_outlay_is_seen_however_the_collection_is_carried(shape, source):
    """One mix, four carriers.  All four must go red, or hoisting is a bypass."""
    findings = guard.scan_python(PY, source)
    assert _rules(findings) == {"mixed_class_sum"}, f"{shape}: {[str(f) for f in findings]}"
    assert "outlay" in findings[0].detail and "award_cumulative" in findings[0].detail


def test_building_a_container_of_two_classes_is_not_a_finding():
    """Obligated / Current value / Potential ceiling is the honest presentation.

    The report belongs where the collection becomes ONE number, not where it is built —
    otherwise the rule reads as "never put two classes in a list", which is not the claim
    and would fire on the dossier's own value row.
    """
    assert guard.scan_python(PY, 'both = [row["total_obligated"], row["potential_award_amount"]]\n') == []


def test_totalling_that_same_container_IS_the_finding():
    """Non-vacuity for the test above: silence at the binding is not a dead tracker."""
    source = (
        'both = [row["total_obligated"], row["potential_award_amount"]]\n'
        "exposure = sum(both)\n"
    )
    assert _rules(guard.scan_python(PY, source)) == {"mixed_class_sum"}


def test_an_element_of_a_MIXED_container_carries_no_class():
    """Which member an index picks is not knowable here; guessing invents a measurement."""
    source = (
        'both = [row["total_obligated"], row["potential_award_amount"]]\n'
        'total = both[0] + row["total_outlays"]\n'
    )
    assert guard.scan_python(PY, source) == []


@pytest.mark.parametrize(
    "why, source",
    [
        (
            "a container of string labels holds no dollar figure",
            'labels = ["deobligation", "positive contract action"]\n'
            'total = labels[0] + row["total_obligated"]\n',
        ),
        (
            "members are read from the ELEMENT, never from the iteration domain",
            'value_items = [by_name[n] for n in ("current_award_amount", "potential_award_amount")]\n'
            'total = sum(value_items) + row["total_obligated"]\n',
        ),
        (
            "a comprehension target shadows an enclosing name of the same word",
            'obligated = row["total_obligated"]\n'
            "vals = [obligated for obligated in raw]\n"
            'total = sum(vals) + row["total_outlays"]\n',
        ),
        (
            "a dict is a RECORD keyed by name, not a collection of like figures",
            'fact = {"id": "total_obligated", "value": v, "currency": "USD", "semantic": "obligated"}\n'
            'total = fact["currency"] + row["total_outlays"]\n',
        ),
        (
            "a container this file never saw bound carries nothing",
            'def f(vals):\n    return sum(vals) + row["total_outlays"]\n',
        ),
    ],
)
def test_a_container_of_non_amounts_stays_unclassed(why, source):
    assert guard.scan_python(PY, source) == [], why


def test_mutation_a_hoisted_container_total_is_seen_in_the_real_source():
    """The N1 shape written at a real site in the real ``metrics.py`` must go RED.

    The synthetic cases above prove the rule; this proves it survives contact with the
    file it exists to police — the same anchor the ``_concentration`` control uses, so a
    move breaks both loudly instead of leaving either vacuous.
    """
    source = _metrics_source()
    assert guard.scan_python(METRICS, source) == [], "shipped metrics.py is not clean"
    mutated = _mutate(
        source,
        "    total = float(weights.sum())\n",
        '    _hoisted = [frame["total_obligated"], frame["total_obligation"]]\n'
        "    total = float(sum(_hoisted)) + "
        'float(pd.to_numeric(frame["total_outlays"], errors="coerce").sum())\n',
    )
    findings = guard.scan_python(METRICS, mutated)
    assert _rules(findings) == {"mixed_class_sum"}, [str(f) for f in findings]
    detail = " ".join(f.detail for f in findings)
    assert "outlay" in detail and "award_cumulative" in detail, detail


def test_the_container_rule_reports_nothing_on_the_tree_as_it_stands():
    """Measured price of the rule: 0 of the tree's container bindings acquire a class.

    Injecting ``sum(<name>) + row["total_outlay"]`` and ``<name>[0] + row["total_outlay"]``
    after every one of the 450 container bindings in the 33 subjects reported ZERO sites —
    no member of any of them is a declared amount field, so the rule adds no
    false-positive surface here.  It is prospective, which is the point: the shape it
    refuses is one line of hoisting away, and until now that line was a bypass.

    Pinned as the gate itself rather than as a count, because a count of container
    bindings would fail on every unrelated edit to the lobe.
    """
    assert guard.scan_tree() == []


def test_provenance_still_travels_through_a_numeric_coercion():
    """The accepted residual, stated as a test: an unknown call keeps its provenance.

    This is the binding both mutation tests rest on, so a future narrowing that decided
    'a call result is unknown, therefore unclassed' would blind the guard again.
    """
    source = (
        'obligated = pd.to_numeric(active.get("total_obligated"), errors="coerce")\n'
        'total = obligated + row["current_award_amount"]\n'
    )
    assert _rules(guard.scan_python(PY, source)) == {"mixed_class_sum"}


# ------------------- the reader-result rule, the twin of the loop-variable rule
#
# A ladder handed to a first-present-wins reader RETURNS one of its rungs, so the reader's
# result carries the ladder's class on exactly the terms ``visit_For`` gives a loop
# variable.  Without this, hoisting a ladder to a constant would hide every downstream
# mix — a container's own NAME carries no class (a list is not a dollar figure), so the
# class has to be recovered from the ladder at the point the rung is taken.


def test_a_reader_over_a_single_class_ladder_yields_that_class():
    source = (
        'LADDER = ("total_obligated", "award_amount")\n'
        "v = _first_number(row, LADDER)\n"
        'total = v + row["total_outlay"]\n'
    )
    assert _rules(guard.scan_python(PY, source)) == {"mixed_class_sum"}


def test_a_reader_over_a_MIXED_ladder_yields_no_class():
    """The call is already a mixed_class_fallback; picking one rung's class would be a
    coin-flip attributed to everything the result touches."""
    source = (
        'LADDER = ("total_obligated", "current_award_amount")\n'
        "v = _first_number(row, LADDER)\n"
        'total = v + row["total_outlay"]\n'
    )
    findings = guard.scan_python(PY, source)
    assert _rules(findings) == {"mixed_class_fallback"}, [str(f) for f in findings]


def test_a_parameter_carries_no_class_the_known_limit_of_scoping():
    """The measured price of scoping, pinned so it stays a KNOWN limit.

    This file does no interprocedural analysis, so a function parameter's class is
    genuinely unknown.  Before scoping, ``_impact``'s ``amount`` parameter was classed —
    from a local of a DIFFERENT function that happened to share the name — and three
    numbers derived from it (``source_amount``, ``attributable_amount``, ``ratio``)
    inherited that guess.  Recovering them would mean restoring exactly the leak that
    reported ``float(current_total) + float(denom)`` a thousand lines from either name.

    Differential sweep over all 33 subjects, injecting ``<name> + row["total_outlay"]``
    after every assignment: 24 sites reported by both trackers, 0 by the scoped one alone,
    35 by the flat one alone — 32 of them names holding no dollar figure, 3 of them this.
    """
    source = (
        "def uses_a_parameter(amount):\n"
        '    return amount + row["total_outlay"]\n'
    )
    assert guard.scan_python(PY, source) == []
    # ... and the same function is seen the moment the class is proved INSIDE it.
    proved = (
        "def proves_it_locally(row):\n"
        '    amount = row["federal_action_obligation"]\n'
        '    return amount + row["total_outlay"]\n'
    )
    assert _rules(guard.scan_python(PY, proved)) == {"mixed_class_sum"}
