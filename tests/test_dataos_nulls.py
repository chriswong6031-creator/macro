"""Null / zero / unknown contracts (Data OS §D6) — ``lib/dataos/nulls.py``.

THE INCIDENT THIS SUITE EXISTS FOR is the one the module's own docstring measures:
**635 ``fillna(0)`` sites across 266 files and 1,426 ``get(...) or 0`` coercions.**
Every one of them turns "we do not know" into "we know it is zero", which is the
opposite claim, and nothing goes red.

THE SECOND INCIDENT IS THIS FILE'S ABSENCE.  ``lib/dataos/nulls.py`` shipped in the
first Data OS foundation pass with NO test file at all, and no ``run:`` step naming
it — there is no broad ``pytest tests/`` anywhere in CI, so an unnamed suite never
runs.  An adversarial mutation replaced the zero-masking law
(``value == 0 and not policy.zero_is_meaningful``) with ``if False:``, deleting §D6's
headline law outright, and all 279 tests still passed.  A law nothing can see die is
not a law.  ``test_a_masked_zero_is_the_headline_d6_violation`` is that mutation,
pinned.

THE THIRD IS THE TYPE SURFACE.  The guard was keyed on ``isinstance(value, (int,
float))``, which is blind to exactly the numeric types the stores this library
describes actually yield: ``decimal.Decimal`` from a money-shaped column, and the
``numpy`` scalars a parquet-backed frame hands back through ``iterrows()`` /
``itertuples()`` (unlike ``to_dict('records')``, which unboxes to builtins).  A
Wave-1 validator walking a frame that way saw every masked ``fillna(0)`` on an
integer column as lawful and reported a clean run.  The ``Decimal`` / ``Fraction`` /
registered-``numbers.Number`` cases below pin the broadened guard in a lane that has
only pytest, and the ``numpy`` case pins it wherever numpy is installed.

Pure unit tests: no ``data/`` read anywhere, so the suite is identical on a full
checkout and in a thin CI lane.

Run: .venv/bin/python -m pytest tests/test_dataos_nulls.py -q
"""

from __future__ import annotations

import numbers
from decimal import Decimal
from fractions import Fraction

import pytest

from lib.dataos.nulls import MissingReason, NullPolicy, validate_value


# A stdlib stand-in for a numpy scalar: a number that is NOT an ``int``/``float``
# subclass but IS a ``numbers.Number``, which is precisely the shape ``np.int64``
# presents.  Pinning the behaviour on this keeps the law under test in the thin CI
# lane, where numpy is not installed and never will be (the Data OS library is
# stdlib-only at import time by contract).
class _NumpyLikeScalar(numbers.Number):
    __slots__ = ("_v",)

    def __init__(self, v: float) -> None:
        self._v = v

    def __eq__(self, other: object) -> bool:
        return self._v == other

    def __hash__(self) -> int:  # pragma: no cover - identity only, never keyed on
        return hash(self._v)

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"_NumpyLikeScalar({self._v!r})"


STRICT = NullPolicy()   # the defaults ARE the law: no zeros, no bare NaN, no reasons


# ── the closed vocabulary (§D6) ──────────────────────────────────────────────
def test_the_nine_missing_reasons_are_exactly_the_d6_vocabulary() -> None:
    """CLOSED on purpose.  An open-ended free-text reason is how a null becomes
    unqueryable, and the point is that a consumer acts differently on
    ``NOT_YET_AVAILABLE`` (wait) than on ``POST_DELISTING`` (stop asking) than on
    ``VENDOR_FAILED`` (retry and alarm)."""
    assert {r.name for r in MissingReason} == {
        "OK",
        "NOT_YET_AVAILABLE",
        "NOT_APPLICABLE",
        "NO_COVERAGE",
        "VENDOR_FAILED",
        "SUPPRESSED_LICENSE",
        "HALTED",
        "PRE_INCEPTION",
        "POST_DELISTING",
    }


@pytest.mark.parametrize("reason", list(MissingReason))
def test_every_reason_name_equals_its_wire_value(reason: MissingReason) -> None:
    """The enum is written to a status sidecar as a string; a name/value skew would
    make the stored column and the code disagree about the same reason."""
    assert reason.value == reason.name


# ── NullPolicy.permits ───────────────────────────────────────────────────────
def test_ok_is_permitted_even_when_nothing_is_declared() -> None:
    """``OK`` is the ABSENCE of a missing-reason, not one of them."""
    assert STRICT.permits(MissingReason.OK)


@pytest.mark.parametrize(
    "reason",
    [r for r in MissingReason if r is not MissingReason.OK],
)
def test_an_undeclared_reason_is_not_permitted(reason: MissingReason) -> None:
    assert not STRICT.permits(reason)


def test_a_declared_reason_is_permitted_and_its_siblings_are_not() -> None:
    """Declaring narrowly is what turns an unexpected reason into a FINDING: a price
    column that starts emitting ``SUPPRESSED_LICENSE`` is a licensing incident, not a
    data gap."""
    policy = NullPolicy(allowed_reasons=frozenset({MissingReason.NOT_YET_AVAILABLE}))
    assert policy.permits(MissingReason.NOT_YET_AVAILABLE)
    assert not policy.permits(MissingReason.SUPPRESSED_LICENSE)


def test_the_policy_defaults_are_the_strict_reading() -> None:
    """A column that declares nothing gets the fail-closed policy, not a lenient one."""
    assert STRICT.zero_is_meaningful is False
    assert STRICT.nan_permitted is False
    assert STRICT.allowed_reasons == frozenset()


# ── validate_value: status sidecars ──────────────────────────────────────────
def test_ok_as_a_sidecar_value_is_lawful() -> None:
    assert validate_value(MissingReason.OK, STRICT) is None


@pytest.mark.parametrize(
    "reason",
    [r for r in MissingReason if r is not MissingReason.OK],
)
def test_an_undeclared_sidecar_reason_is_returned_as_the_violation(
    reason: MissingReason,
) -> None:
    """The violation is named by the reason itself, so the caller can report WHICH
    unexpected state the column started emitting."""
    assert validate_value(reason, STRICT) is reason


@pytest.mark.parametrize(
    "reason",
    [r for r in MissingReason if r is not MissingReason.OK],
)
def test_a_declared_sidecar_reason_is_lawful(reason: MissingReason) -> None:
    policy = NullPolicy(allowed_reasons=frozenset({reason}))
    assert validate_value(reason, policy) is None


# ── validate_value: unrecorded absence ───────────────────────────────────────
@pytest.mark.parametrize("value", [None, float("nan")])
def test_an_absence_with_no_reason_recorded_reads_as_no_coverage(value: object) -> None:
    """WHY ``NO_COVERAGE``: an absence whose reason was never written down is
    indistinguishable from having no coverage at all — the reader cannot tell "we
    never had it" from "the vendor failed tonight".  The weakest reading is the
    fail-closed one; it never claims more knowledge than the record contains."""
    assert validate_value(value, STRICT) is MissingReason.NO_COVERAGE


@pytest.mark.parametrize("value", [None, float("nan")])
def test_nan_permitted_makes_an_unrecorded_absence_lawful(value: object) -> None:
    assert validate_value(value, NullPolicy(nan_permitted=True)) is None


def test_a_decimal_nan_is_an_unrecorded_absence_too() -> None:
    """A money-shaped column stores ``Decimal``, and ``Decimal('NaN')`` is the same
    unknown as ``float('nan')``.  Keying the NaN test on ``isinstance(value, float)``
    let it through as a lawful value — the same narrow-isinstance defect as the zero
    guard below, in the same function."""
    assert validate_value(Decimal("NaN"), STRICT) is MissingReason.NO_COVERAGE
    assert validate_value(Decimal("NaN"), NullPolicy(nan_permitted=True)) is None


# ── validate_value: THE §D6 HEADLINE — 0 may never mean absence ──────────────
@pytest.mark.parametrize("zero", [0, 0.0, -0.0])
def test_a_masked_zero_is_the_headline_d6_violation(zero: object) -> None:
    """``0`` may NEVER be written to mean absence.  This is the assertion the ``if
    False:`` mutation had to survive and could not: delete the law here and this
    test reds."""
    assert validate_value(zero, STRICT) is MissingReason.NO_COVERAGE


@pytest.mark.parametrize("zero", [0, 0.0, Decimal("0"), Fraction(0)])
def test_zero_is_meaningful_makes_a_real_zero_lawful(zero: object) -> None:
    """``True`` only where a stored ``0`` is a REAL observation — a net flow that
    genuinely netted to zero, a count of zero events."""
    assert validate_value(zero, NullPolicy(zero_is_meaningful=True)) is None


@pytest.mark.parametrize(
    "zero",
    [
        Decimal("0"),
        Decimal("0.00"),
        Decimal("-0"),
        Decimal("0E-8"),
        Fraction(0),
        Fraction(0, 5),
        _NumpyLikeScalar(0),
        _NumpyLikeScalar(0.0),
    ],
    ids=[
        "Decimal-0",
        "Decimal-0.00",
        "Decimal-neg0",
        "Decimal-0E-8",
        "Fraction-0",
        "Fraction-0-over-5",
        "numpy-like-int",
        "numpy-like-float",
    ],
)
def test_a_masked_zero_is_caught_on_non_builtin_numeric_types(zero: object) -> None:
    """The types the described stores ACTUALLY yield.  ``isinstance(value, (int,
    float))`` sees none of these, so a validator walking a parquet frame through
    ``iterrows()`` reported every masked ``fillna(0)`` on an integer column as OK."""
    assert validate_value(zero, STRICT) is MissingReason.NO_COVERAGE


# A `pytest.importorskip("numpy")` variant of the case above USED TO LIVE HERE and was
# removed rather than kept, because it could never run: `dataos-foundation` is a
# deliberately thin lane (pytest + pyyaml only) whose narrow dependency set is the
# CANARY for a pandas/numpy import creeping into lib/dataos — so numpy is absent there
# BY DESIGN and always will be. `scripts/check_skip_only_suites.py` is right to call a
# suite that skips in every job that names it dead: it reads as coverage and executes
# nowhere. Adding numpy to the lane to "fix" the skip would have silenced the guard by
# destroying the very property the lane exists to protect.
#
# Nothing is lost. `_NumpyLikeScalar` is a `numbers.Number` that is NOT an int/float
# subclass — precisely the shape of `np.int64`/`np.float64` for this code path, which
# branches on `isinstance(value, (int, float))` and nothing numpy-specific. It is
# exercised above, in the lane, on every run.


def test_a_bool_is_not_a_masked_zero_whatever_int_says_about_it() -> None:
    """``False == 0`` is True in Python and means nothing here: a boolean column's
    ``False`` is an OBSERVATION, and flagging it would make the guard unusable on
    every flag column in the repo."""
    assert validate_value(False, STRICT) is None
    assert validate_value(True, STRICT) is None


# ── validate_value: values that are simply fine ──────────────────────────────
@pytest.mark.parametrize(
    "value",
    [1, -1, 0.5, 114.80, Decimal("1150.00"), Fraction(1, 3), _NumpyLikeScalar(7)],
)
def test_a_present_non_zero_value_is_lawful_under_the_strictest_policy(
    value: object,
) -> None:
    assert validate_value(value, STRICT) is None


@pytest.mark.parametrize("value", ["0", "", "OK", b"\x00", [], {}])
def test_non_numeric_values_are_not_second_guessed(value: object) -> None:
    """The zero law is about a NUMBER standing in for absence.  The string ``"0"``
    is a string, and inventing a violation for it would put this validator in the
    business of guessing at dtypes it was never handed."""
    assert validate_value(value, STRICT) is None
