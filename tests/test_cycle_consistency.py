"""Cross-page cycle-consistency gate tests (W3.6 / R3-M3).

Covers:
1. The checker PASSES on the current committed build (no same-tape mismatch, no
   undeclared cross-tape difference).
2. The checker's `check()` FAILS on a synthetic same-tape mismatch (two pages
   rendering the same tape with different pos_v2 / phase_v2) — proving the gate bites.
3. An UNDECLARED cross-tape difference (same ticker, one reading missing its basis)
   is caught.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _REPO)

from scripts import check_cycle_consistency as ccc  # noqa: E402

_SITE = os.path.join(_REPO, "site")


def _have_build() -> bool:
    return os.path.exists(os.path.join(_SITE, "countrycyclesdata", "country_cycles.json"))


@pytest.mark.skipif(not _have_build(), reason="no built site/ present")
def test_checker_passes_on_current_build():
    """On the current build, every same-tape group agrees and every cross-tape
    difference is declared (the W3.6 acceptance)."""
    same_tape_violations, cross_tape_declared, same_tape_ok = ccc.check(_SITE)
    undeclared = [c for c in cross_tape_declared if c[3]]
    assert not same_tape_violations, (
        "same-tape consistency violations on the current build: "
        + "; ".join(f"{k}" for k, *_ in same_tape_violations)
    )
    assert not undeclared, (
        "undeclared cross-tape differences: " + "; ".join(c[0] for c in undeclared)
    )
    # sanity: the checker actually compared something (the markets↔country EWx ties).
    assert same_tape_ok, "checker found no same-tape groups to compare — extraction is broken"


def test_checker_catches_synthetic_same_tape_mismatch(monkeypatch):
    """Two pages rendering the SAME tape (EWX/price) with different pos_v2 + phase_v2
    must trip the same-tape violation path."""
    fake = [
        ccc.Reading("country_cycles", "EWX", "EWX", "price", 30.0, "Trough"),
        ccc.Reading("markets", "ewx", "EWX", "price", 88.0, "Peak"),  # frozen/stale — a real bug
    ]
    monkeypatch.setattr(ccc, "_collect", lambda site_dir: fake)
    same_tape_violations, cross_tape_declared, same_tape_ok = ccc.check("ignored")
    assert same_tape_violations, "synthetic same-tape mismatch was NOT caught"
    (key, group, spread, phases) = same_tape_violations[0]
    assert key == ("EWX", "price")
    assert spread > ccc.POS_TOL
    assert phases == {"Trough", "Peak"}
    # main() must exit non-zero on it
    monkeypatch.setattr(ccc, "_collect", lambda site_dir: fake)
    assert ccc.main(["ignored"]) == 1


def test_checker_catches_undeclared_cross_tape(monkeypatch):
    """Same ticker on two bases where ONE reading has no basis label = undeclared drift."""
    fake = [
        ccc.Reading("cycle", "gold", "GC=F", "futures_cont", 45.0, "Downturn"),
        ccc.Reading("country_cycles", "GLD", "GC=F", "", 70.0, "Peak"),  # basis MISSING
    ]
    monkeypatch.setattr(ccc, "_collect", lambda site_dir: fake)
    assert ccc.main(["ignored"]) == 1


def test_synthetic_pass_case(monkeypatch):
    """A fully-consistent synthetic set (agreeing same-tape + declared cross-tape) passes."""
    fake = [
        ccc.Reading("country_cycles", "EWU", "EWU", "price", 92.9, "Downturn"),
        ccc.Reading("markets", "uk", "EWU", "price", 92.9, "Downturn"),      # agrees
        ccc.Reading("cycle", "em", "EEM", "etf_tr", 80.0, "Peak"),           # declared basis
        ccc.Reading("country_cycles", "EEM", "EEM", "price", 60.0, "Expansion"),  # declared basis
    ]
    monkeypatch.setattr(ccc, "_collect", lambda site_dir: fake)
    assert ccc.main(["ignored"]) == 0
