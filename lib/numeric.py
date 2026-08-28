"""Single canonical numeric-normalization contract for the stock dossier estate.

``finite(value) -> float | None`` is the ONE place in this codebase that
decides whether a numeric value is "present" or "missing". Missingness MUST be
decided by ``math.isfinite`` (or an equivalent explicit check) — NEVER by
truthiness. ``if value:`` treats a float NaN as present, because NaN is
truthy in Python. That exact bug shipped 69 public ticker dossier pages under
site/stocks/ rendering the literal strings ``$nan`` / ``$nanM`` to real users
(two independent code paths in scripts/build_ticker_pages.py: `_humanize_number`
and `_build_peers`), because a NaN market cap or NaN financial figure sailed
through an `if x:` / `if not x:` gate as though it were a real number.

Zero is a valid, present value and must never be conflated with missing.

Contract:
  * Returns ``None`` for: ``None``, float ``nan``, numpy ``nan``,
    ``pandas.NA`` / ``pandas.NaT``, ``+inf``, ``-inf``, the empty string,
    a whitespace-only string, and anything that cannot be coerced to
    ``float`` (e.g. a list, a non-numeric string).
  * Returns a ``float`` for: valid ints, valid floats (including ``0.0``),
    numeric strings such as ``"1234.5"`` / ``" 12 "`` / ``"-3"``, numpy
    numeric scalars, and ``decimal.Decimal``.
  * ``bool`` is explicitly NOT treated as a valid number and returns
    ``None`` — even though ``bool`` is a ``float``-coercible subclass of
    ``int`` in Python. No caller in this codebase relies on
    ``finite(True) == 1.0``; passing a boolean into a numeric-formatting
    path is far more likely to be a data-shape bug (e.g. a flag column
    leaking into a numeric column) than a deliberate 0/1 encoding, so this
    module refuses to silently launder it into a dossier figure.
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Any

try:  # pandas is optional — this module must stay importable without it.
    import pandas as pd
except ImportError:  # pragma: no cover - exercised only in pandas-less envs
    pd = None  # type: ignore[assignment]


def finite(value: Any) -> float | None:
    """Normalize `value` to a finite float, or None if it is missing/non-finite.

    Never uses truthiness to infer missingness. See module docstring for the
    full contract and the incident (`$nanM` leaking to 69 public pages) that
    made this the required entry point for every dossier numeric formatter.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if pd is not None:
        try:
            if value is pd.NA or value is pd.NaT:
                return None
        except (TypeError, ValueError):
            pass
        try:
            if pd.isna(value) is True:
                return None
        except (TypeError, ValueError):
            # pd.isna raises/returns an array for non-scalar input; a value
            # that reaches here is not one of the scalar NA sentinels we
            # care about, so fall through to the normal coercion attempt.
            pass
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    if isinstance(value, Decimal):
        try:
            f = float(value)
        except (InvalidOperation, ValueError, OverflowError):
            return None
        return f if math.isfinite(f) else None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f
