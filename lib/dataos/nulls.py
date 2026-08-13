"""Null / zero / unknown — a closed vocabulary of ABSENCE (Data OS §D6).

WHY THIS FILE EXISTS.  Measured surface today: **635 ``fillna(0)`` sites across 266
files, and 1,426 ``get(...) or 0`` coercions.**  Each one of those turns "we do not
know" into "we know it is zero", and the two are opposite claims.  A zeroed flow is
not a neutral flow; a zeroed spread is not a tight spread; a zeroed weight silently
drops a member from a basket average without changing the denominator.  Nothing goes
red, and the number that reaches the page is confidently wrong.

THE LAWS (§D6):

* ``NaN`` means "unknown, reason unrecorded" and is legal ONLY where the contract
  permits it (``NullPolicy.nan_permitted``).
* **``0`` may never be written to mean absence.**  Contracts declare
  ``zero_is_meaningful`` per column; a validator flags the coercion where it is false.
* Every deliberate absence carries one of the nine :class:`MissingReason` values as a
  status sidecar — never conflated with the value column.

The reasons are a CLOSED set on purpose.  An open-ended free-text reason is how a
null becomes unqueryable, and the point of the vocabulary is that a consumer can act
differently on ``NOT_YET_AVAILABLE`` (wait) than on ``POST_DELISTING`` (stop asking)
than on ``VENDOR_FAILED`` (retry and alarm) — which is impossible when all three
arrive as the same ``NaN``.

STDLIB ONLY.
"""
from __future__ import annotations

import math
import numbers
from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "MissingReason",
    "NullPolicy",
    "validate_value",
]


class MissingReason(Enum):
    """Why a value is absent — the closed vocabulary of §D6."""

    OK = "OK"                              # present and meaningful; not missing at all
    NOT_YET_AVAILABLE = "NOT_YET_AVAILABLE"  # exists upstream later; the release has not landed
    NOT_APPLICABLE = "NOT_APPLICABLE"      # the field cannot apply to this entity (no dividend on an index)
    NO_COVERAGE = "NO_COVERAGE"            # we do not carry this entity/field at all
    VENDOR_FAILED = "VENDOR_FAILED"        # we asked and the source did not answer
    SUPPRESSED_LICENSE = "SUPPRESSED_LICENSE"  # we have it and may not serve it
    HALTED = "HALTED"                      # no print exists because trading was halted
    PRE_INCEPTION = "PRE_INCEPTION"        # before the security/series existed
    POST_DELISTING = "POST_DELISTING"      # after the security stopped existing


@dataclass(frozen=True, slots=True)
class NullPolicy:
    """What a single column is allowed to say when it has nothing to say.

    ``zero_is_meaningful``
        ``True`` only when a stored ``0`` is a real observation (a net flow that
        genuinely netted to zero, a count of zero events).  ``False`` — the default —
        makes a stored ``0`` a masked absence and therefore a violation, which is the
        635-site ``fillna(0)`` defect made mechanical.
    ``allowed_reasons``
        The subset of :class:`MissingReason` this column may legitimately carry.
        Declaring it narrowly is what turns an unexpected reason into a finding
        instead of a shrug: a price column that starts emitting ``SUPPRESSED_LICENSE``
        is a licensing incident, not a data gap.
    ``nan_permitted``
        Whether "unknown, reason unrecorded" is tolerable here at all.
    """

    zero_is_meaningful: bool = False
    allowed_reasons: frozenset[MissingReason] = field(default_factory=frozenset)
    nan_permitted: bool = False

    def permits(self, reason: MissingReason) -> bool:
        """``OK`` is always permitted — it is the absence of a missing-reason."""
        return reason is MissingReason.OK or reason in self.allowed_reasons


def _is_number(value: object) -> bool:
    """A NUMBER for the purposes of §D6 — the ABC, not the two builtin classes.

    WHY ``numbers.Number`` AND NOT ``(int, float)``.  The narrow form was blind to
    exactly the types the stores this library describes hand back: ``decimal.Decimal``
    from a money-shaped column, and the ``numpy`` scalars a parquet-backed frame
    yields through ``iterrows()`` / ``itertuples()`` — ``numpy.int64`` and
    ``numpy.int32`` are neither ``int`` nor ``float`` subclasses, so a validator
    walking a frame that way read every masked ``fillna(0)`` on an integer column as
    lawful and reported a clean run.  ``numbers.Number`` covers all of them without
    importing numpy, which the stdlib-only import contract forbids.

    ``bool`` is excluded here rather than at each call site: ``False == 0`` is True in
    Python and means nothing about absence — a boolean column's ``False`` is an
    observation.
    """
    return isinstance(value, numbers.Number) and not isinstance(value, bool)


def _is_nan(value: object) -> bool:
    """"Unknown, reason unrecorded" for any numeric type, not just ``float``.

    ``Decimal('NaN')`` is the same unknown as ``float('nan')``; keying this on
    ``isinstance(value, float)`` let a money-shaped column's NaN through as a lawful
    VALUE.  Anything that cannot be asked (``complex``, an exotic ``Number`` with no
    float conversion) is simply not a NaN.
    """
    if not _is_number(value):
        return False
    try:
        return math.isnan(value)   # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return False


def _is_zero(value: object) -> bool:
    """Numeric equality with zero, never truthiness.

    ``Decimal('0.00')``, ``Decimal('0E-8')`` and ``numpy.int64(0)`` all compare equal
    to ``0`` while being different objects with different reprs; a ``not value`` test
    would additionally swallow empty containers and empty strings, which are not
    masked zeros and are not this validator's business.
    """
    try:
        return bool(value == 0)
    except Exception:      # noqa: BLE001 — an exotic __eq__ is "not a zero", never a crash
        return False


def validate_value(value: object, policy: NullPolicy) -> MissingReason | None:
    """The missing-reason *value* is unlawfully standing in for, or ``None`` if lawful.

    ``None`` means "this value is fine under this policy".  Anything else is a
    violation, named by the reason the stored value is masquerading as:

    * ``value`` is a :class:`MissingReason` — a status sidecar.  ``OK`` and any
      declared reason pass; an UNDECLARED reason is returned as the violation.
    * ``value`` is ``None`` or ``NaN`` — an absence with no reason recorded.  Lawful
      only when ``nan_permitted``; otherwise returned as ``NO_COVERAGE``.
    * ``value`` is ``0`` on a column where ``zero_is_meaningful`` is ``False`` — the
      §D6 headline violation, likewise returned as ``NO_COVERAGE``.

    WHY ``NO_COVERAGE`` FOR AN UNRECORDED ABSENCE.  An absence whose reason was never
    written down is indistinguishable from having no coverage at all — the reader
    cannot tell "we never had it" from "the vendor failed tonight".  Returning the
    weakest, most pessimistic reading is the fail-closed choice: it never claims more
    knowledge than the record contains.  A caller that needs the two apart must fix
    the PRODUCER to record a reason; that is the whole intent of the sidecar.
    """
    if isinstance(value, MissingReason):
        return None if policy.permits(value) else value
    if value is None or _is_nan(value):
        return None if policy.nan_permitted else MissingReason.NO_COVERAGE
    if isinstance(value, bool):
        return None      # a bool is not a masked zero, whatever int() says about it
    if _is_number(value) and _is_zero(value) and not policy.zero_is_meaningful:
        return MissingReason.NO_COVERAGE
    return None
