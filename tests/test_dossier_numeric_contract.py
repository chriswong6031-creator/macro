"""Mutation-grade coverage of lib.numeric.finite — the single dossier numeric
normalization contract.

69 of 2066 generated site/stocks/*.html pages rendered the literal "$nanM" /
"$nan" to the public because two formatters in scripts/build_ticker_pages.py
treated a float NaN as a present value (NaN is truthy in Python). finite()
is the fix: missingness is decided by math.isfinite(), never by truthiness,
and zero is always a present value. Every input class in the contract is
asserted individually here.
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.numeric import finite  # noqa: E402


# ---------------------------------------------------------------------------
# None-producing inputs
# ---------------------------------------------------------------------------

def test_none_input_is_none():
    assert finite(None) is None


def test_python_float_nan_is_none():
    assert finite(float("nan")) is None


def test_numpy_nan_is_none():
    np = pytest.importorskip("numpy")
    assert finite(np.nan) is None


def test_numpy_float64_nan_is_none():
    np = pytest.importorskip("numpy")
    assert finite(np.float64("nan")) is None


def test_pandas_na_is_none():
    pd = pytest.importorskip("pandas")
    assert finite(pd.NA) is None


def test_pandas_nat_is_none():
    pd = pytest.importorskip("pandas")
    assert finite(pd.NaT) is None


def test_positive_infinity_is_none():
    assert finite(float("inf")) is None


def test_negative_infinity_is_none():
    assert finite(float("-inf")) is None


def test_numpy_positive_infinity_is_none():
    np = pytest.importorskip("numpy")
    assert finite(np.inf) is None


def test_numpy_negative_infinity_is_none():
    np = pytest.importorskip("numpy")
    assert finite(-np.inf) is None


def test_empty_string_is_none():
    assert finite("") is None


def test_whitespace_only_string_is_none():
    assert finite("   ") is None
    assert finite("\t\n") is None


def test_non_numeric_string_is_none():
    assert finite("abc") is None


def test_non_coercible_type_is_none():
    assert finite([1, 2, 3]) is None
    assert finite({"x": 1}) is None
    assert finite(object()) is None


def test_decimal_nan_is_none():
    assert finite(Decimal("NaN")) is None


def test_bool_is_none():
    """bool is explicitly excluded from the numeric contract (see module
    docstring): a flag column leaking into a numeric column is far more
    likely than a deliberate 0/1 encoding, so both True and False are
    treated as non-numeric rather than silently laundered into a figure."""
    assert finite(True) is None
    assert finite(False) is None


# ---------------------------------------------------------------------------
# Float-producing inputs
# ---------------------------------------------------------------------------

def test_valid_int():
    assert finite(42) == 42.0
    assert finite(-7) == -7.0


def test_valid_float():
    assert finite(3.14) == 3.14
    assert finite(-2.5) == -2.5


def test_zero_is_present_not_missing():
    """The load-bearing case: zero is a real, present value and must never
    be conflated with missing."""
    assert finite(0) == 0.0
    assert finite(0.0) == 0.0
    assert finite(-0.0) == 0.0
    assert finite("0") == 0.0


def test_numeric_strings():
    assert finite("1234.5") == 1234.5
    assert finite(" 12 ") == 12.0
    assert finite("-3") == -3.0
    assert finite("0.0") == 0.0


def test_numpy_numeric_scalars():
    np = pytest.importorskip("numpy")
    assert finite(np.float64(3.5)) == 3.5
    assert finite(np.int64(7)) == 7.0
    assert finite(np.float32(1.5)) == pytest.approx(1.5)


def test_decimal_valid_value():
    assert finite(Decimal("4.5")) == 4.5
    assert finite(Decimal("0")) == 0.0
    assert finite(Decimal("-10.25")) == -10.25


# ---------------------------------------------------------------------------
# Module import discipline
# ---------------------------------------------------------------------------

def test_module_importable_without_pandas(monkeypatch):
    """lib.numeric must stay importable (and functional) with pandas absent."""
    import builtins
    import importlib

    real_import = builtins.__import__

    def _blocked(name, *args, **kwargs):
        if name == "pandas" or name.startswith("pandas."):
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked)
    import lib.numeric as numeric_mod

    importlib.reload(numeric_mod)
    try:
        assert numeric_mod.pd is None
        assert numeric_mod.finite(None) is None
        assert numeric_mod.finite(3) == 3.0
        assert numeric_mod.finite(float("nan")) is None
        assert numeric_mod.finite("5.5") == 5.5
    finally:
        importlib.reload(numeric_mod)  # restore the real pandas-backed module
