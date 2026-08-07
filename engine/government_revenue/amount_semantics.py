"""The ONE declaration of what every Government Revenue dollar figure MEANS.

WHY THIS FILE EXISTS.  The lobe's central financial-honesty rule was written in two
places as prose and enforced by nothing:

    research/GOVERNMENT_REVENUE_FORESIGHT_ACCOUNT_HANDOFF.md
        "obligation, outlay, ceiling, bookings, backlog, funded backlog, and GAAP
         revenue are never conflated"
    research/GOVERNMENT_REVENUE_FORESIGHT_MASTERPLAN_FOR_FABLE.md
        "funded obligations are never conflated with ceilings, appropriations,
         announcements, or GAAP revenue"

Neither sentence was reachable by a test: ``grep -rl 'obligat.*ceiling' tests/``
returned nothing.  A rule we claim but do not enforce is a claim, not a rule.  The
incumbent publishes the same caution in its own public documentation; the difference
between their caution and ours has to be that ours can go red.

THE FOUR CLASSES, AND WHY EACH PAIR IS NOT ADDABLE.

  award_cumulative   A running total carried ON the award record
                     (``total_obligation`` / ``total_obligated``).
  transaction_delta  ONE action's increment (``federal_action_obligation``).
                     Summing the deltas of an award REPRODUCES its cumulative, so
                     adding a delta to a cumulative DOUBLE-COUNTS the same dollars.
  ceiling            An authorised maximum that may never be spent
                     (``current_award_amount`` funded ceiling,
                     ``potential_award_amount`` including options).  Not money moved
                     — money PERMITTED.  Adding it to an obligation states that
                     authorised capacity has been committed, which is the exact
                     press-release-versus-funded-work confusion the lobe exists to
                     refuse.
  outlay             Cash actually disbursed (``total_outlay`` / ``total_outlays``).
                     It LAGS obligation, so obligation + outlay counts the committed
                     dollar once when it is committed and again when it is paid.

None of the four IS bookings, backlog, funded backlog, or GAAP revenue — but do not read
that as "the lobe has no backlog figure".  It has several, and they are built from these
very columns: ``metrics._backlog()`` publishes ``funded_backlog`` / ``total_backlog`` and
their preferred names ``funded_capacity_observed`` / ``potential_capacity_observed`` as
``ceiling - obligation`` residuals over the bounded USAspending award-detail sample, and
``metrics.py`` publishes ``ttm_obligations``, ``covered_obligations`` and
``funded_capacity_company_exposure_sum`` from the same source.  Each of those is a
DIFFERENCE or a within-class total, never a cross-class sum, which is why this module
declares subtraction legal and addition not; none of them is a fifth class, so none is
declared here.  What genuinely lives outside the federal source is COMPANY-reported
bookings, company-reported backlog and GAAP revenue — the numbers an issuer prints — and
this module classifies none of those, which is exactly why a federal residual must never
be published under their names.

COVERAGE IS DERIVED, NOT HAND-LISTED.  The defect class this lobe keeps hitting is
"a column joined a canonical list and something downstream never followed" — the
comment above ``collectors.usaspending_awards.NUMERIC_LEDGER_COLUMNS`` records the
last time it bit.  So the set of fields that MUST carry a class is derived from the
collector's own canonical number-column declarations
(``NUMERIC_LEDGER_COLUMNS`` + ``AWARD_EVENT_NUMBER_COLUMNS``) rather than copied
here.  ``unclassified_canonical_fields()`` is that derivation's residue and is
asserted empty by ``tests/test_government_revenue_amount_semantics.py``: a new
number column cannot join a ledger without a declared class.  The reverse residue,
``alias_fields()``, is every classified name the collector does NOT declare — the
UI/legacy aliases — so the alias list is auditable by subtraction instead of trust.

AUTHORITY.  Display/context tier.  Nothing here ranks, sizes, gates, escalates, or
originates a signal; it only refuses to add two numbers that do not mean the same
thing, and hands a figure the plain words that say which one it is.
"""
from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "AmountClass",
    "AmountClassConflict",
    "AMOUNT_CLASSES",
    "AMOUNT_SEMANTIC_CLASSES",
    "CLASS_LABELS",
    "CLASS_MEANINGS",
    "alias_fields",
    "amount_fact",
    "assert_combinable",
    "assert_figure_labeled",
    "canonical_numeric_fields",
    "checked_fallback",
    "checked_sum",
    "classify",
    "classify_semantic",
    "classes_of",
    "conflict_reason",
    "unclassified_canonical_fields",
]


class AmountClass(str, Enum):
    """What a Government Revenue dollar figure is a measurement OF."""

    AWARD_CUMULATIVE = "award_cumulative"
    TRANSACTION_DELTA = "transaction_delta"
    CEILING = "ceiling"
    OUTLAY = "outlay"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class AmountClassConflict(ValueError):
    """Raised when figures of different semantic classes would become one number."""


# THE TAXONOMY.  One dict, every classified amount field name in the lobe.  A name
# that is not here carries no class and is therefore never combined BY THIS MODULE
# with one that does — silence is not permission, it is "unknown", and the static
# guard reports an unknown name beside a classified one rather than guessing.
AMOUNT_CLASSES: Mapping[str, AmountClass] = MappingProxyType({
    # --- award-cumulative: a running total on the award record -----------------
    "total_obligation": AmountClass.AWARD_CUMULATIVE,   # forward event ledger
    "total_obligated": AmountClass.AWARD_CUMULATIVE,    # legacy award/snapshot ledgers
    # USAspending's ``spending_by_award`` search column "Award Amount".  It is the
    # award's obligated total, which is why metrics.py reads it as a fallback for
    # ``total_obligated`` — recorded here so that fallback is checkable rather than
    # merely conventional.
    "award_amount": AmountClass.AWARD_CUMULATIVE,
    # --- transaction-delta: one action's increment -----------------------------
    "federal_action_obligation": AmountClass.TRANSACTION_DELTA,
    # UI alias used by the queue/inspector fallbacks in
    # templates/government_revenue.html.j2 and government-revenue-dossiers.js.
    "obligation_delta": AmountClass.TRANSACTION_DELTA,
    # --- ceiling: authorised maximum, not money moved --------------------------
    "current_award_amount": AmountClass.CEILING,        # funded/exercised ceiling
    "potential_award_amount": AmountClass.CEILING,      # ceiling including options
    # --- outlay: cash actually disbursed ---------------------------------------
    "total_outlay": AmountClass.OUTLAY,                 # forward event ledger
    "total_outlays": AmountClass.OUTLAY,                # legacy award/snapshot ledgers
})

# Plain-word stance for each class, EN + ZH.  DESIGN_DOCTRINE glance tier: a figure
# shows a person a plain word, never ``potential_award_amount``.  The ZH side reads
# as Chinese finance copy, not as translated English.
CLASS_LABELS: Mapping[AmountClass, tuple[str, str]] = MappingProxyType({
    AmountClass.AWARD_CUMULATIVE: ("Obligated to date", "累计已承诺义务"),
    AmountClass.TRANSACTION_DELTA: ("Obligation change", "义务额变化"),
    AmountClass.CEILING: ("Authorised ceiling", "授权上限"),
    AmountClass.OUTLAY: ("Cash disbursed", "已支付现金"),
})

# One sentence a reader can act on: what the number is, and what it is NOT.
CLASS_MEANINGS: Mapping[AmountClass, tuple[str, str]] = MappingProxyType({
    AmountClass.AWARD_CUMULATIVE: (
        "Total committed on this award so far. Not cash paid, and not a company's reported revenue.",
        "该授标迄今累计承诺的金额。并非已支付现金，也不是公司报告收入。",
    ),
    AmountClass.TRANSACTION_DELTA: (
        "How much one recorded action added or removed. Adding it to a running total counts the same dollars twice.",
        "单笔已记录行动增加或减少的金额。将其与累计金额相加会重复计算同一笔钱。",
    ),
    AmountClass.CEILING: (
        "The most this award is allowed to reach. It may never be funded, so it is capacity, not spending.",
        "该授标允许达到的上限。可能永远不会拨款，因此是余量而非支出。",
    ),
    AmountClass.OUTLAY: (
        "Cash the government has actually paid out. It lags what has been committed.",
        "政府实际支付的现金。滞后于已承诺的金额。",
    ),
})

# Published ``semantic`` / ``label_code`` strings that a user-facing amount fact may
# carry (contracts/government_revenue/government_procurement_event.v2.schema.json
# ``amountFact.semantic``, and the ``values`` block of
# contracts/government_revenue/government_revenue_dossiers.v1.schema.json).  The
# contract types these as free strings, so without this map an amount fact can be
# published with a label from a different class and nothing notices.
AMOUNT_SEMANTIC_CLASSES: Mapping[str, AmountClass] = MappingProxyType({
    "obligated": AmountClass.AWARD_CUMULATIVE,
    "reported_obligations": AmountClass.AWARD_CUMULATIVE,
    "total_obligated": AmountClass.AWARD_CUMULATIVE,
    "action_obligation": AmountClass.TRANSACTION_DELTA,
    "federal_action_obligation": AmountClass.TRANSACTION_DELTA,
    "current_award_value": AmountClass.CEILING,
    "potential_award_value": AmountClass.CEILING,
    "ceiling": AmountClass.CEILING,
    "current_award_amount": AmountClass.CEILING,
    "potential_award_amount": AmountClass.CEILING,
    "outlay": AmountClass.OUTLAY,
    "total_outlays": AmountClass.OUTLAY,
    "total_outlay": AmountClass.OUTLAY,
})


def canonical_numeric_fields() -> frozenset[str]:
    """Number columns the award collector itself declares, across all five ledgers.

    Imported lazily and NEVER defaulted: a missing collector must raise here rather
    than return an empty set, because an empty set would make
    ``unclassified_canonical_fields()`` vacuously clean — the failure mode where a
    coverage guard reads green precisely when it can no longer see anything.
    """
    from collectors import usaspending_awards

    return frozenset(usaspending_awards.NUMERIC_LEDGER_COLUMNS) | frozenset(
        usaspending_awards.AWARD_EVENT_NUMBER_COLUMNS
    )


def unclassified_canonical_fields() -> frozenset[str]:
    """Collector-declared number columns with NO semantic class. Must stay empty."""
    return canonical_numeric_fields() - frozenset(AMOUNT_CLASSES)


def alias_fields() -> frozenset[str]:
    """Classified names the collector does not declare — the UI/legacy aliases."""
    return frozenset(AMOUNT_CLASSES) - canonical_numeric_fields()


def classify(field: Any) -> AmountClass | None:
    """The declared class of an amount field name, or None when it carries none."""
    if not isinstance(field, str):
        return None
    return AMOUNT_CLASSES.get(field.strip())


def classify_semantic(semantic: Any) -> AmountClass | None:
    """The declared class of a published ``semantic`` / ``label_code`` string."""
    if not isinstance(semantic, str):
        return None
    return AMOUNT_SEMANTIC_CLASSES.get(semantic.strip())


def classes_of(fields: Iterable[Any]) -> frozenset[AmountClass]:
    """Every declared class present in ``fields``. Unknown names contribute nothing."""
    return frozenset(c for c in (classify(f) for f in fields) if c is not None)


def conflict_reason(fields: Iterable[Any]) -> str | None:
    """Plain-English reason these fields may not become one figure, or None."""
    named = [f for f in fields if isinstance(f, str)]
    present = sorted(
        {(classify(f).value, f) for f in named if classify(f) is not None}
    )
    classes = {value for value, _ in present}
    if len(classes) < 2:
        return None
    by_class: dict[str, list[str]] = {}
    for value, field in present:
        by_class.setdefault(value, []).append(field)
    shape = "; ".join(
        f"{value} ({', '.join(sorted(names))})" for value, names in sorted(by_class.items())
    )
    if {"award_cumulative", "transaction_delta"} <= classes:
        why = (
            "an award's transaction deltas sum to its own cumulative total, so combining "
            "the two counts the same dollars twice"
        )
    elif "ceiling" in classes and ({"award_cumulative", "transaction_delta"} & classes):
        why = (
            "a ceiling is money AUTHORISED and may never be spent; an obligation is money "
            "COMMITTED — combining them reports capacity as activity"
        )
    elif "outlay" in classes and ({"award_cumulative", "transaction_delta"} & classes):
        why = (
            "an outlay is cash already disbursed against an obligation, so combining them "
            "counts the committed dollar again when it is paid"
        )
    elif {"ceiling", "outlay"} <= classes:
        why = (
            "a ceiling is money authorised and an outlay is cash already paid; they are "
            "two different points of the same award's life, not two quantities to total"
        )
    else:  # pragma: no cover - defensive; every pair of the four is enumerated above
        why = "these are measurements of different things"
    return f"mixes {shape} — {why}"


def assert_combinable(fields: Iterable[Any], *, context: str) -> AmountClass | None:
    """Return the single class shared by ``fields``; raise when they disagree.

    ``context`` names the figure being built so the failure reads as a sentence
    about the product, not about a tuple.
    """
    reason = conflict_reason(fields)
    if reason is not None:
        raise AmountClassConflict(f"{context}: {reason}")
    present = classes_of(fields)
    return next(iter(present)) if present else None


def checked_sum(
    contributions: Mapping[str, Any] | Iterable[tuple[str, Any]],
    *,
    context: str,
) -> float:
    """Add field-labelled amounts, refusing a sum that spans semantic classes."""
    items = list(contributions.items()) if isinstance(contributions, Mapping) else list(contributions)
    assert_combinable([field for field, _ in items], context=context)
    total = 0.0
    for _, value in items:
        if value is None:
            continue
        total += float(value)
    return total


def checked_fallback(
    row: Mapping[str, Any],
    fields: Sequence[str],
    *,
    context: str,
) -> Any:
    """First present value across a fallback ladder, refusing a mixed-class ladder.

    A ladder is a silent conflation vector: ``("total_obligated", "award_amount",
    "current_award_amount")`` reads as an obligation on most rows and as a CEILING on
    the rows where only the third column survives, under one output name, with no
    trace of which happened.
    """
    assert_combinable(fields, context=context)
    for field in fields:
        try:
            value = row[field]
        except (KeyError, IndexError, TypeError):
            continue
        if value is not None and value == value:  # NaN-safe presence test
            return value
    return None


def amount_fact(
    field: str,
    value: Any,
    *,
    source_ref: str | None = None,
    as_of: str | None = None,
    is_lower_bound: bool = False,
    semantic: str | None = None,
) -> dict[str, Any]:
    """Build one user-facing amount fact whose class travels WITH the number.

    Shaped for ``government_procurement_event.v2#/$defs/amountFact`` and extended
    with ``amount_class`` plus the plain EN/ZH words a reader actually sees, so a
    figure can never reach a surface as a bare dollar amount.
    """
    cls = classify(field)
    if cls is None:
        raise AmountClassConflict(
            f"amount_fact({field!r}): no declared semantic class — a figure may not be "
            f"published without one (declare it in engine/government_revenue/amount_semantics.py)"
        )
    label_en, label_zh = CLASS_LABELS[cls]
    meaning_en, meaning_zh = CLASS_MEANINGS[cls]
    resolved_semantic = semantic or field
    semantic_class = classify_semantic(resolved_semantic)
    if semantic_class is not None and semantic_class is not cls:
        raise AmountClassConflict(
            f"amount_fact({field!r}): published semantic {resolved_semantic!r} is "
            f"{semantic_class.value} but the field is {cls.value}"
        )
    return {
        "id": field,
        "label_code": resolved_semantic,
        "value": value,
        "currency": "USD",
        "semantic": resolved_semantic,
        "amount_class": cls.value,
        "class_label_en": label_en,
        "class_label_zh": label_zh,
        "class_meaning_en": meaning_en,
        "class_meaning_zh": meaning_zh,
        "as_of": as_of,
        "is_lower_bound": bool(is_lower_bound),
        "source_ref": source_ref,
    }


def assert_figure_labeled(fact: Mapping[str, Any], *, context: str) -> AmountClass:
    """A published amount fact must carry a class label that MATCHES its field.

    The fourth dangerous mix is the quiet one: any of the first three rendered into a
    single figure with the class label left behind.  The v2 contract types
    ``semantic`` as a free string, so this is the only place the label can be held to
    the field it describes.
    """
    if not isinstance(fact, Mapping):
        raise AmountClassConflict(f"{context}: amount fact is not a mapping")
    field = fact.get("id")
    field_class = classify(field)
    if field_class is None:
        raise AmountClassConflict(
            f"{context}: amount fact id={field!r} has no declared semantic class"
        )
    labels = [fact.get("semantic"), fact.get("label_code")]
    declared = fact.get("amount_class")
    if declared is not None and declared != field_class.value:
        raise AmountClassConflict(
            f"{context}: amount fact id={field!r} is {field_class.value} but declares "
            f"amount_class={declared!r}"
        )
    resolved = [classify_semantic(label) for label in labels if isinstance(label, str)]
    if not any(cls is not None for cls in resolved) and declared is None:
        raise AmountClassConflict(
            f"{context}: amount fact id={field!r} publishes a {field_class.value} figure "
            f"with no class label travelling with it (semantic={labels[0]!r}, "
            f"label_code={labels[1]!r})"
        )
    for label, cls in zip([label for label in labels if isinstance(label, str)], resolved):
        if cls is not None and cls is not field_class:
            raise AmountClassConflict(
                f"{context}: amount fact id={field!r} is {field_class.value} but is "
                f"labelled {label!r} ({cls.value})"
            )
    return field_class
