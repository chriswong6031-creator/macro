"""PSI W2.5 — the 1-day change (`tech.chg_1d` / index `c1`) across the five library bakes.

Charter: research/PORTFOLIO_SUPERINTELLIGENCE_MASTERPLAN_BY_FABLE.md §20 Amendment A3.4.

The five per-market builders (US / CN / HK / CA / INTL) all derive their `tech` block from
`engine.stock_technicals.snapshot()`, so the field is produced ONCE, from the same close
series that produced `tech.price` — it can never disagree with the price on the card. The
index mirror is a COPY of that published value via `stock_technicals.attach_chg_1d`, not a
re-derivation, so `c1 == tech.chg_1d` holds by construction rather than by convention.

What this file pins, per builder:
  * a full-history record carries `tech.chg_1d`, and it equals the percent move between the
    last two closes of the series that record was built from;
  * the index row the builder writes carries `c1` equal to that same value;
  * a record with no computable tech block (a sub-floor LIMITED name) carries the field in
    NEITHER place — omitted, never 0, never null;
  * the builder's index-emit site really calls the shared mirror with (idx, rec's tech) —
    asserted structurally over the module AST, so a silent removal or an arg swap fails here.

A literal "two-close fixture" cannot reach a builder's tech block at all: every one of them
gates on `min_days=300` and returns a LIMITED record below it. The two-close / one-close
boundary is therefore pinned at the producer in tests/test_stock_technicals.py, and pinned
here as "no tech block => no field in either artifact", which is what the builders can express.

Run: .venv/bin/python -m pytest tests/test_library_chg_1d.py -q
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import stock_technicals  # noqa: E402
from scripts import build_canada_library as bcal  # noqa: E402
from scripts import build_china_library as bcl  # noqa: E402
from scripts import build_hk_library as bhl  # noqa: E402
from scripts import build_intl_library as bil  # noqa: E402
from scripts import build_stock_library as bsl  # noqa: E402

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _series(n: int, seed: int = 11) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-02", periods=n)
    return pd.Series(30 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, n))), index=idx)


def _expected(c: pd.Series) -> float:
    """The 1-day move, computed straight from the fixture — independent of the helper."""
    return round((float(c.iloc[-1]) / float(c.iloc[-2]) - 1.0) * 100.0, 1)


# --- per-builder: full-history record carries the field, index mirrors it ----
#
# US is absent from this parameterisation on purpose: build_stock_library._one() seeds
# rec["tech"] with the THIN engine.technicals.snapshot and main() supersedes it with the rich
# read, so the field arrives at the enrich step, not at _one(). Covered separately below.
@pytest.mark.parametrize("builder, ticker, sector", [
    (bcl, "601939.SS", "Financial Services"),
    (bhl, "0700.HK", "Technology"),
    (bcal, "RY.TO", "Financial Services"),
])
def test_close_only_builder_emits_chg_1d_and_index_c1(builder, ticker, sector):
    c = _series(400)
    rec = builder._one(ticker, c, None, "Test Co", sector, allow_limited=True)
    assert rec is not None and not rec.get("limited")

    tech = rec["tech"]
    assert "chg_1d" in tech, f"{builder.__name__}: tech block lost chg_1d"
    assert tech["chg_1d"] == _expected(c)
    # the field must agree with the price published beside it, same bar
    assert tech["chg_1d"] == round((tech["price"] / float(c.iloc[-2]) - 1.0) * 100.0, 1)

    idx = {"t": ticker, "n": "Test Co", "s": sector, "st": rec["ladder"]["state"]}
    stock_technicals.attach_chg_1d(idx, rec.get("tech"))
    assert idx["c1"] == tech["chg_1d"]


def test_intl_builder_emits_chg_1d_and_index_c1():
    # intl's _one() takes flag/market instead of the high series
    c = _series(400)
    rec = bil._one("7203.T", c, "Toyota", "Consumer Cyclical", "\U0001F1EF\U0001F1F5", "Japan",
                   allow_limited=True)
    assert rec is not None and not rec.get("limited")
    assert rec["tech"]["chg_1d"] == _expected(c)

    idx = {"t": "7203.T", "n": rec["name"], "s": rec["sector"], "st": rec["ladder"]["state"],
           "fl": rec["flag"], "mk": rec["market"]}
    stock_technicals.attach_chg_1d(idx, rec.get("tech"))
    assert idx["c1"] == rec["tech"]["chg_1d"]


def test_us_builder_gets_chg_1d_from_the_rich_enrich():
    # _one() seeds the thin snapshot, which has no rich keys at all (bbwp, adx14, mom_12_1 …);
    # chg_1d is one of them, so the US field arrives with the enrich merge in main().
    c = _series(400)
    rec = bsl._one("AAPL", c, None, "Apple", "Technology", allow_limited=True)
    assert rec is not None and not rec.get("limited")
    assert "chg_1d" not in rec["tech"], "thin seed unexpectedly carries rich keys"

    # what main()'s enrich computes for a close-only name (build_stock_library L2977)
    rich = stock_technicals.snapshot(c, bench=None)
    assert rich["chg_1d"] == _expected(c)
    # …and the merge is rich-last, so the enriched value is what ships
    merged = {**rec["tech"], **rich}
    assert merged["chg_1d"] == _expected(c)

    idx = {"t": "AAPL", "n": "Apple", "s": "Technology", "st": rec["ladder"]["state"]}
    stock_technicals.attach_chg_1d(idx, merged)
    assert idx["c1"] == _expected(c)


def test_us_enrich_merge_is_rich_last():
    # the assertion above is only meaningful while the builder merges in this order
    src = (_SCRIPTS / "build_stock_library.py").read_text()
    assert 'rec["tech"] = {**(rec.get("tech") or {}), **rich}' in src, \
        "US tech enrich no longer merges the rich snapshot last — chg_1d may not ship"


# --- per-builder: no tech block => no field in EITHER artifact ---------------
@pytest.mark.parametrize("builder, ticker, sector", [
    (bcl, "301632.SZ", "Technology"),
    (bhl, "1024.HK", "Technology"),
    (bcal, "XYZ.TO", "Energy"),
    (bsl, "SPCX", "Technology"),
])
def test_sub_floor_record_omits_chg_1d_and_c1(builder, ticker, sector):
    rec = builder._one(ticker, _series(1), None, "Test Co", sector, allow_limited=True)
    assert rec is not None and rec["limited"] is True
    assert "tech" not in rec, "a LIMITED record must not publish a tech block"

    idx = {"t": ticker, "n": "Test Co", "s": sector, "st": "LIMITED"}
    stock_technicals.attach_chg_1d(idx, rec.get("tech"))
    assert "c1" not in idx, "c1 must be ABSENT (never 0, never null) with no tech block"


def test_intl_sub_floor_record_omits_chg_1d_and_c1():
    rec = bil._one("7203.T", _series(1), "Toyota", "Consumer Cyclical",
                   "\U0001F1EF\U0001F1F5", "Japan", allow_limited=True)
    assert rec is not None and rec["limited"] is True
    assert "tech" not in rec
    idx = {"t": "7203.T", "n": rec["name"], "s": rec["sector"], "st": "LIMITED",
           "fl": rec["flag"], "mk": rec["market"]}
    stock_technicals.attach_chg_1d(idx, rec.get("tech"))
    assert "c1" not in idx


# --- the five index-emit sites really call the shared mirror -----------------
_BUILDERS = ["build_stock_library", "build_china_library", "build_hk_library",
             "build_canada_library", "build_intl_library"]


def _attach_chg_1d_calls(module: str) -> list[ast.Call]:
    tree = ast.parse((_SCRIPTS / f"{module}.py").read_text())
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "attach_chg_1d"]


@pytest.mark.parametrize("module", _BUILDERS)
def test_builder_index_row_attaches_c1(module):
    calls = _attach_chg_1d_calls(module)
    assert calls, f"{module}: index rows no longer attach c1"
    unparsed = {ast.unparse(c) for c in calls}
    assert unparsed == {"stock_technicals.attach_chg_1d(idx, rec.get('tech'))"}, (
        f"{module}: c1 must be mirrored from the record's OWN tech block "
        f"(got {sorted(unparsed)})")


@pytest.mark.parametrize("module", _BUILDERS)
def test_builder_attaches_c1_beside_the_volume_field(module):
    # placement guard: the mirror belongs on the row the builder appends to `index`,
    # which is the row attach_latest_volume already enriches.
    lines = (_SCRIPTS / f"{module}.py").read_text().splitlines()
    vol = [i for i, ln in enumerate(lines) if "attach_latest_volume(idx, ticker" in ln]
    chg = [i for i, ln in enumerate(lines) if "attach_chg_1d(idx, rec.get(\"tech\"))" in ln]
    assert chg, f"{module}: no c1 attach found"
    for i in chg:
        assert any(0 < i - v <= 2 for v in vol), (
            f"{module}: c1 attach at line {i + 1} is not on the index row "
            "attach_latest_volume enriches")
