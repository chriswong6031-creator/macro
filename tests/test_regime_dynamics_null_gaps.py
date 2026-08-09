"""Regime-dynamics trajectory math must survive null-holed timeline series.

2026-08-08: a collection gap committed nulls into site regime_timeline.json and
`_regime_dynamics` raised `TypeError: NoneType - float` at the window endpoint,
redding every consumer of the vector build (test_factor_exposure,
test_spvector_page) fleet-wide. The contract in its own docstring is
"Empty (null) when we have no history — honest, not guessed": nulls compact to
clean pairs, and the 30-reading coverage floor counts CLEAN pairs.

An INTERIOR hole and a null TIP are different failures and get different answers:

  - interior hole -> compact it away. Dropping unpaired days only widens the
    calendar span of the ~1-month window, so one missing print must not blank a
    whole market.
  - null TIP -> disclose null. There is no current reading, so there is no
    current direction. Compaction ALONE would anchor `pairs[-1]` on the last
    clean day, which for HK (whose `i` has been null since 2026-07-28) publishes
    an 11-day-stale endpoint AS today's direction with nothing on the card saying
    so — the same lie as coercing the gap to 0.0, which renders a confident
    rdir="stable".

Registered in the `unrun-vector-baskets` legacy job alongside test_spvector_page,
which is the job the original crash reddened; before that it ran nowhere.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import build_vector  # noqa: E402

EMPTY = {"rdir": None, "rphase": None, "rtoward_en": None,
         "rtoward_zh": None, "rflip": None}


def _write_timeline(tmp_path, g, i, trans=None):
    (tmp_path / "regime_timeline.json").write_text(
        json.dumps({"g": g, "i": i, "trans": trans or []}), encoding="utf-8")


def test_interior_nulls_compact_away_and_still_read(tmp_path, monkeypatch):
    """Nulls mid-window compact away; a live TIP still produces a real verdict.

    The tip is deliberately non-null here so this isolates compaction. (It used to
    end on nulls, which now short-circuits on the tip rule — the test would have
    passed for the wrong reason, proving nothing about interior holes.)
    """
    monkeypatch.setattr(build_vector.config, "site_dir", lambda: tmp_path)
    g = [0.5] * 40 + [None, 0.6, 0.7]
    i = [0.2] * 40 + [0.1, None, 0.2]
    _write_timeline(tmp_path, g, i, ["STABLE"])
    out = build_vector._regime_dynamics("US", {"quad": "Q1"})
    assert out["rdir"] in ("improving", "stable", "deteriorating")
    assert out["rphase"] is not None


def test_null_tip_discloses_instead_of_publishing_a_stale_endpoint(tmp_path, monkeypatch):
    """A missing CURRENT reading reads as unknown — not as the last clean day.

    This is the HK case. Both wrong answers are ruled out: coercing the gap to 0.0
    (a confident "stable" invented from nothing), and silently anchoring on the last
    paired day (a stale endpoint published as today). Compaction alone returns
    "improving" for both series below, so this is what separates the two designs.
    """
    monkeypatch.setattr(build_vector.config, "site_dir", lambda: tmp_path)
    rising = [round(0.02 * k, 3) for k in range(45)]

    # inflation tip missing (HK's actual shape: `i` null, `g` still printing)
    _write_timeline(tmp_path, rising, [0.2] * 42 + [None] * 3, ["STABLE"])
    assert build_vector._regime_dynamics("US", {"quad": "Q1"}) == EMPTY

    # growth tip missing
    _write_timeline(tmp_path, rising[:42] + [None] * 3, [0.2] * 45, ["STABLE"])
    assert build_vector._regime_dynamics("US", {"quad": "Q1"}) == EMPTY


def test_nulls_below_the_coverage_floor_return_empty(tmp_path, monkeypatch):
    """25 clean pairs is under the floor even when the raw series is long.

    Tip is live so this isolates the FLOOR rather than re-testing the tip rule.
    """
    monkeypatch.setattr(build_vector.config, "site_dir", lambda: tmp_path)
    g = [None] * 33 + [0.5] * 25
    i = [None] * 33 + [0.2] * 25
    assert len(g) == 58 and g[-1] is not None and i[-1] is not None
    _write_timeline(tmp_path, g, i)
    out = build_vector._regime_dynamics("US", {"quad": "Q1"})
    assert out == EMPTY


def test_all_null_series_return_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(build_vector.config, "site_dir", lambda: tmp_path)
    _write_timeline(tmp_path, [None] * 60, [None] * 60)
    out = build_vector._regime_dynamics("US", {"quad": "Q2"})
    assert out["rdir"] is None
