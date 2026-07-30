"""Is `engine.quad.shock_override_z` actually REACHABLE on each axis's weight lattice?

Axis components score −1/0/+1 and the axis score is a weighted mean over the AVAILABLE
components (`engine/axes.score_axis`), so the set of attainable |score| values is a
finite lattice determined entirely by the configured weights. A threshold placed in a
gap in that lattice is not a tuning choice — it silently becomes a stricter rule than it
reads as.

Found by adversarial audit 2026-07-29: with `shock_override_z = 0.85` and the inflation
axis's weights (sum 6.25), ANY single dissenting leg caps the axis at 0.84 — even the
smallest, sticky-CPI at weight 0.5. So the inflation shock override is in effect a
UNANIMITY rule (attainable only at 0.88 / 0.92 / 1.00, i.e. with neutral-or-unanimous
legs), while the growth axis (sum 7.5) reaches 0.867 through a single 0.5-weight dissent
and so CAN shock with dissent. Two axes, one parameter, two effective rules.

The lattice is enumerated FROM `config.yml` — never a hardcoded list — so a weight change
re-derives it and this test keeps telling the truth.

The dissent assertion for the inflation axis is a KNOWN, EXPECTED failure and is marked
xfail(strict=True): it will FAIL LOUDLY if the config is ever changed such that the
override becomes dissent-reachable, which is the notification we want. The proposed
resolution and its pre-registered gate live in
research/REGIME_DISLOCATION_RECAL_PROPOSAL.md §2. Nothing here changes a gate value.

Run as a plain script:  python tests/test_shock_override_attainable.py
"""
from __future__ import annotations

import sys
from itertools import product
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

AXES = ("growth", "inflation")


def _weights(axis: str) -> dict[str, float]:
    comps = config.load()["engine"][f"{axis}_axis"]["components"]
    return {k: float(v["weight"]) for k, v in comps.items()}


def _lattice(axis: str, all_available: bool = True):
    """Every attainable (|score|, n_dissenting) pair with all legs available.

    score = sum(w_i * s_i) / sum(w_i over available), s_i in {-1, 0, +1}. Only the
    all-available case is enumerated: a missing leg shrinks the denominator too, which
    ADDS attainable values, so all-available is the conservative (smallest) lattice —
    exactly the one a threshold has to live inside on a healthy data day.
    """
    w = _weights(axis)
    names = sorted(w)
    denom = sum(w.values())
    out = []
    for signs in product((-1, 0, 1), repeat=len(names)):
        num = sum(w[n] * s for n, s in zip(names, signs))
        if num <= 0:                       # by symmetry only the positive side matters
            continue
        n_dissent = sum(1 for s in signs if s < 0)
        out.append((num / denom, n_dissent))
    return out


def test_lattice_is_derived_from_config_not_hardcoded():
    """Guard the guard: if the weights move, the lattice must move with them."""
    for axis in AXES:
        w = _weights(axis)
        assert w, f"{axis}_axis has no configured components"
        assert all(v > 0 for v in w.values())
        lat = _lattice(axis)
        assert lat, "lattice enumeration produced nothing"
        assert max(s for s, _ in lat) == pytest.approx(1.0), (
            "a unanimous axis must score exactly 1.0")


@pytest.mark.parametrize("axis", AXES)
def test_shock_override_threshold_is_attainable_at_all(axis):
    """The threshold must be reachable by SOME configured state, or the override is
    dead code on that axis."""
    thr = float(config.load()["engine"]["quad"]["shock_override_z"])
    reachable = [s for s, _ in _lattice(axis) if s >= thr]
    assert reachable, (
        f"{axis} axis can never reach shock_override_z={thr} — the override is "
        f"unreachable. Max attainable |score| is {max(s for s, _ in _lattice(axis)):.4f}. "
        f"See research/REGIME_DISLOCATION_RECAL_PROPOSAL.md §2.")


def test_growth_axis_shock_is_reachable_with_dissent():
    """Control for the xfail below: growth CAN shock while a leg disagrees, which is
    what makes the inflation axis's behaviour an asymmetry rather than a house rule."""
    thr = float(config.load()["engine"]["quad"]["shock_override_z"])
    with_dissent = [s for s, d in _lattice("growth") if d >= 1 and s >= thr]
    assert with_dissent, "growth axis lost its dissent-reachable shock override"


@pytest.mark.xfail(strict=True, reason=(
    "KNOWN DEFECT, pinned deliberately: shock_override_z=0.85 sits in a gap in the "
    "inflation weight lattice. With any dissenting leg the max attainable |score| is "
    "0.84 (5.25/6.25), so the inflation shock override is effectively a unanimity rule "
    "(reachable only at 0.88/0.92/1.00). Proposed resolution + pre-registered gate: "
    "research/REGIME_DISLOCATION_RECAL_PROPOSAL.md §2. This xfail is strict, so it "
    "turns RED if the config ever makes the override dissent-reachable — that is the "
    "notification, not a failure."))
def test_inflation_axis_shock_is_reachable_with_dissent():
    thr = float(config.load()["engine"]["quad"]["shock_override_z"])
    with_dissent = [s for s, d in _lattice("inflation") if d >= 1 and s >= thr]
    assert with_dissent, (
        "inflation shock override is unreachable with any dissenting leg; max with "
        f"dissent = {max((s for s, d in _lattice('inflation') if d >= 1), default=0):.4f}")


def test_documented_inflation_lattice_values_still_hold():
    """Pins the exact numbers cited in the proposal doc, so the doc cannot silently
    go stale against the config."""
    w = _weights("inflation")
    assert sum(w.values()) == pytest.approx(6.25)
    lat = _lattice("inflation")
    max_with_dissent = max(s for s, d in lat if d >= 1)
    assert max_with_dissent == pytest.approx(5.25 / 6.25)      # 0.84
    assert max_with_dissent == pytest.approx(0.84)
    no_dissent = sorted({round(s, 4) for s, d in lat if d == 0}, reverse=True)[:3]
    assert no_dissent == [pytest.approx(1.0), pytest.approx(0.92), pytest.approx(0.88)]


def test_documented_growth_lattice_value_still_holds():
    w = _weights("growth")
    assert sum(w.values()) == pytest.approx(7.5)
    max_with_dissent = max(s for s, d in _lattice("growth") if d >= 1)
    assert max_with_dissent == pytest.approx(6.5 / 7.5)        # 0.8667
    assert max_with_dissent >= float(config.load()["engine"]["quad"]["shock_override_z"])


if __name__ == "__main__":
    # xfail is a pytest concept; in script mode report the known defect as a note.
    thr = float(config.load()["engine"]["quad"]["shock_override_z"])
    for axis in AXES:
        lat = _lattice(axis)
        best = max(s for s, _ in lat)
        best_d = max((s for s, d in lat if d >= 1), default=0.0)
        print(f"{axis:10s} sum(w)={sum(_weights(axis).values()):.2f}  "
              f"max|score|={best:.4f}  max with >=1 dissent={best_d:.4f}  "
              f"thr={thr}  dissent-reachable={'YES' if best_d >= thr else 'NO (known defect)'}")
    for fn in (test_lattice_is_derived_from_config_not_hardcoded,
               test_growth_axis_shock_is_reachable_with_dissent,
               test_documented_inflation_lattice_values_still_hold,
               test_documented_growth_lattice_value_still_holds):
        fn()
        print(f"ok  {fn.__name__}")
    for axis in AXES:
        test_shock_override_threshold_is_attainable_at_all(axis)
    print("ok  test_shock_override_threshold_is_attainable_at_all (both axes)")
