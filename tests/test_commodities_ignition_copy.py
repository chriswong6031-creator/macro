"""W-C(3)/(4) — commodities page ignition + dual-read copy (display tier).

Precious metals ignited after ~3 weeks of basing while commodities.html printed
"Momentum down" on gold/silver and a bare "Cycle low" on silver.  The data was
fresh; the copy was the defect.  These tests pin the two view-model repairs:

  W-C(3) the momentum cell discloses a split read — hysteresis momentum bear
         while the slow trend is up and the 20-day thrust vote is positive —
         WITHOUT changing momentum_state itself;
  W-C(4) Trough + a confirmed base reads as a state ("At cycle low — basing"),
         not as the bare warning-shaped "Cycle low".

Every string under test is display tier: nothing here feeds a score or a rank.

Run: python -m pytest tests/test_commodities_ignition_copy.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_commodities import (  # noqa: E402
    _DUAL_READ_CHIP,
    _IGNITING_CHIP,
    _dual_read,
    _plain_cycle,
    _plain_cycle_state,
    _roc20,
)


# --------------------------------------------------------------------------- #
# W-C(3) — the dual-read flag fires on the full conjunction and nothing less
# --------------------------------------------------------------------------- #
def test_dual_read_fires_on_the_full_conjunction() -> None:
    assert _dual_read("bear", "up", 0.007) is True


@pytest.mark.parametrize("mom,trend,roc,why", [
    ("bull",    "up",   0.007, "momentum not bear"),
    ("neutral", "up",   0.007, "momentum not bear"),
    ("bear",    "down", 0.007, "trend not up"),
    ("bear",    "flat", 0.007, "trend not up"),
    ("bear",    "up",  -0.007, "roc20 vote negative"),
    ("bear",    "up",   0.0,   "roc20 vote flat, not positive"),
    ("bear",    "up",   None,  "roc20 unavailable"),
    (None,      "up",   0.007, "momentum missing"),
    ("bear",    None,   0.007, "trend missing"),
])
def test_dual_read_requires_every_leg(mom, trend, roc, why) -> None:
    """Drop exactly one leg at a time — the chip must go dark each time."""
    assert _dual_read(mom, trend, roc) is False, f"chip survived: {why}"


def test_dual_read_returns_a_plain_bool() -> None:
    """JSON-safe: the template renders this straight into the view model."""
    assert type(_dual_read("bear", "up", 0.01)) is bool


# --------------------------------------------------------------------------- #
# W-C(3) — the roc20 helper mirrors the engine's roc20 vote
# --------------------------------------------------------------------------- #
def test_roc20_matches_a_20_session_rate_of_change() -> None:
    close = pd.Series([100.0] * 21 + [110.0])
    # last bar vs 20 sessions back (both inside the flat run except the last)
    assert _roc20(close) == pytest.approx(0.10)


def test_roc20_none_when_history_too_short() -> None:
    assert _roc20(pd.Series([100.0] * 20)) is None


def test_roc20_ignores_gaps() -> None:
    """dropna first — a NaN tail must not blank the vote."""
    close = pd.Series([100.0] * 21 + [110.0, float("nan")])
    assert _roc20(close) == pytest.approx(0.10)


# --------------------------------------------------------------------------- #
# W-C(4) — Trough + basing is a state, not a warning
# --------------------------------------------------------------------------- #
def test_trough_with_basing_reads_as_a_state() -> None:
    en, zh = _plain_cycle_state("Trough", basing=True)
    assert en == "At cycle low — basing"
    assert zh == "处于周期底部——筑底中"


def test_trough_without_basing_keeps_the_bare_label() -> None:
    """No confirmed base under it -> the copy must NOT claim one."""
    assert _plain_cycle_state("Trough", basing=False) == _plain_cycle("Trough")


@pytest.mark.parametrize("phase", ["Recovery", "Expansion", "Peak", "Downturn"])
def test_basing_does_not_rewrite_any_other_phase(phase: str) -> None:
    """The Trough copy is Trough-only — basing elsewhere changes nothing."""
    assert _plain_cycle_state(phase, basing=True) == _plain_cycle(phase)


def test_missing_phase_still_degrades_to_the_null_dash() -> None:
    assert _plain_cycle_state(None, basing=True) == ("—", "—")


# --------------------------------------------------------------------------- #
# Bilingual + vocabulary law
# --------------------------------------------------------------------------- #
def test_every_new_string_ships_both_languages() -> None:
    for en, zh in (_DUAL_READ_CHIP, _IGNITING_CHIP,
                   _plain_cycle_state("Trough", basing=True)):
        assert en and zh, "both languages required"
        assert en != zh, "zh must not be the EN string"
        assert not any("一" <= ch <= "鿿" for ch in en), \
            f"EN string carries Han characters: {en!r}"
        assert any("一" <= ch <= "鿿" for ch in zh), \
            f"zh string carries no Han characters: {zh!r}"


def test_ignition_chip_carries_no_buy_words() -> None:
    """Watch tier: `armed_recent` is an early, unconfirmed read.

    The chip may describe the STATE; it may never issue an instruction.
    """
    en_l = _IGNITING_CHIP[0].lower()
    for word in ("buy", "long", "enter", "entry", "add", "accumulate", "target"):
        assert word not in en_l, f"buy word in ignition chip: {word}"
    for word in ("买入", "做多", "建仓", "加仓", "入场"):
        assert word not in _IGNITING_CHIP[1], f"buy word in zh ignition chip: {word}"


def test_new_copy_uses_no_falsifier_vocabulary() -> None:
    """Falsifier/refutation language is never front-facing (operator, #3821)."""
    banned_en = ("falsif", "refut", "invalidat", "disprov", "thesis broken")
    banned_zh = ("证伪", "证否", "推翻")
    for en, zh in (_DUAL_READ_CHIP, _IGNITING_CHIP,
                   _plain_cycle_state("Trough", basing=True)):
        for w in banned_en:
            assert w not in en.lower(), f"falsifier vocabulary in {en!r}: {w}"
        for w in banned_zh:
            assert w not in zh, f"falsifier vocabulary in {zh!r}: {w}"
