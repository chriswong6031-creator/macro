"""The `avoid` verdict must not claim a downtrend the timeframe table refutes.

`avoid` is reached from long_sign<0 AND short_sign<0. Both can go negative with zero
timeframes reading down: long_sign folds in the polarity-corrected driver/trend leans
plus the cycle penalties, and short_sign is overridden outright by a bearish ladder
state. Oil hit exactly that on 2026-07-24 — D/3D/ME up, W/2W flat, no timeframe down —
and the page still printed "Downtrend confirmed across timeframes" directly above a
table showing the opposite.

The directional call is NOT under test here (short/mid/long signs are untouched, so the
conviction score is unchanged). What is under test is that the stated BASIS matches the
displayed evidence.
"""
from __future__ import annotations

import pandas as pd
import pytest

from engine import commodity_mtf as cm


def _verdict(per_tf: dict, long_sign: int, short_sign: int, monkeypatch) -> dict:
    """Drive confluence_verdict to a chosen (long_sign, short_sign) with a chosen
    per-timeframe read, without needing a synthetic price series that happens to
    produce them."""
    signs = {"D": 0, "3D": 0, "W": 0, "2W": 0, "ME": 0}
    signs.update({k: {"up": 1, "down": -1, "flat": 0}[v] for k, v in per_tf.items()})
    monkeypatch.setattr(cm, "_tf_sign", lambda tf: signs.get((tf or {}).get("_name"), 0))

    a = {
        "mtf": {k: {"_name": k} for k in signs},
        # regime drives long_score; ladder state drives short_sign
        "ladder": {"regime": "bear" if long_sign < 0 else "bull",
                   "state": "DECLINE" if short_sign < 0 else "FRESH BUY"},
        "cycle": {},
    }
    return cm.confluence_verdict(a, "oil", None, None)


def test_avoid_copy_not_used_when_no_timeframe_is_down(monkeypatch):
    """The oil 2026-07-24 shape: nothing down, yet the governor is bearish."""
    v = _verdict({"D": "up", "3D": "up", "W": "flat", "2W": "flat", "ME": "up"},
                 long_sign=-1, short_sign=-1, monkeypatch=monkeypatch)

    assert v["long_sign"] < 0 and v["short_sign"] < 0, "precondition: still the avoid bucket"
    assert not any(x == "down" for x in v["per_tf"].values())

    for field in ("headline", "sub"):
        assert "across timeframes" not in v[field].lower(), (
            f"{field} claims a downtrend across timeframes while none is down: {v[field]!r}")
    assert "各周期确认下行" not in v["headline_zh"]
    # the call itself is unchanged — only the stated basis
    assert v["grade"] == "DON'T CHASE"


def test_avoid_copy_still_used_when_timeframes_really_are_down(monkeypatch):
    """The honest case must keep its original, stronger wording."""
    v = _verdict({"D": "down", "3D": "down", "W": "down", "2W": "down", "ME": "down"},
                 long_sign=-1, short_sign=-1, monkeypatch=monkeypatch)
    assert v["headline"] == "Downtrend confirmed across timeframes"
    assert v["grade"] == "AVOID"


@pytest.mark.parametrize("grade", ["AVOID", "DON'T CHASE"])
def test_every_grade_has_a_bilingual_plain_word_mapping(grade):
    """A grade with no entry in _mtf_grade_plain falls through to the raw English slug
    in BOTH languages — an untranslated string in the Chinese view."""
    from scripts.build_commodities import _mtf_grade_plain
    en, zh = _mtf_grade_plain(grade)
    assert en != grade and zh != grade, f"{grade} has no plain-word mapping"
    assert not any("A" <= ch <= "Z" for ch in zh), f"{grade} zh is untranslated: {zh}"


def test_bilingual_fields_present_on_the_new_branch(monkeypatch):
    v = _verdict({"D": "up", "3D": "up", "W": "flat", "2W": "flat", "ME": "up"},
                 long_sign=-1, short_sign=-1, monkeypatch=monkeypatch)
    for f in ("headline", "headline_zh", "sub", "sub_zh", "grade", "grade_zh"):
        assert v.get(f), f"missing {f}"
    assert v["grade_zh"] == "勿追高"
