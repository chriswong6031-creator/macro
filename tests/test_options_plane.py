"""options_structure — the dealer-positioning block of the Neural Web market plane.

Program of record: charting-app docs/MARKET_STRUCTURE_CORE_MASTERPLAN_2026-08-01.md §6.

Run: .venv/bin/python -m pytest tests/test_options_plane.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.options_plane import (  # noqa: E402
    NEAR_FLIP_PCT,
    ROOTS,
    options_structure_block,
)


def _payload(**over):
    """A plausible options_hub.gex/v1 payload."""
    base = {
        "schema": "options_hub.gex/v1",
        "asof": "2026-07-30",
        "root": "SPX",
        "spot_ref": 7437.63,
        "net_gex_bn": 1.41,
        "gamma_flip": 7481.82,
        "by_strike": [
            {"strike": 7300.0, "gamma_net": -40.0, "gamma_call": 10.0, "gamma_put": -50.0},
            {"strike": 7500.0, "gamma_net": 60.0, "gamma_call": 70.0, "gamma_put": -10.0},
        ],
        "by_expiry": [
            {"exp": "2026-08-01", "gamma_net": 100.0},
            {"exp": "2026-08-15", "gamma_net": 400.0},
        ],
        "history": [
            {"date": "2026-07-28", "net_gex_bn": 1.0},
            {"date": "2026-07-29", "net_gex_bn": 1.2},
            {"date": "2026-07-30", "net_gex_bn": 1.41},
        ],
    }
    base.update(over)
    return base


def _reader(files: dict[str, dict]):
    """Stand-in for the plane builder's own JSON reader, keyed by file stem."""
    def read(path: Path):
        return files.get(Path(path).stem)
    return read


REPO = Path("/nonexistent")


# ── Regime ────────────────────────────────────────────────────────────────────

def test_regime_reads_the_sign_of_net_gamma_not_the_side_of_the_flip():
    """A book can be SHORT gamma above its flip — put-heavy index books do it routinely.

    Deriving the regime from which side of the flip spot sits would report that as
    long_gamma, confidently and backwards.
    """
    gaps: list[str] = []
    b = options_structure_block(
        REPO, gaps,
        _reader({"SPX": _payload(net_gex_bn=-3.0, spot_ref=100.0, gamma_flip=90.0)}),
    )
    assert b["dist_to_flip_pct"] == pytest.approx(10.0)   # spot ABOVE the flip
    assert b["index_regime"] == "short_gamma"             # but the book is short


def test_near_the_flip_the_regime_declines_to_pick_a_side():
    gaps: list[str] = []
    b = options_structure_block(
        REPO, gaps,
        _reader({"SPX": _payload(spot_ref=100.0, gamma_flip=100.5)}),
    )
    assert abs(b["dist_to_flip_pct"]) < NEAR_FLIP_PCT
    assert b["index_regime"] == "near_flip"


def test_regime_is_none_rather_than_guessed_without_a_headline():
    gaps: list[str] = []
    b = options_structure_block(REPO, gaps, _reader({"SPX": _payload(net_gex_bn=None)}))
    # No usable root at all -> the honest empty block, with a gap.
    assert b["index_regime"] is None
    assert any("options_structure" in g for g in gaps)


# ── Regime-dynamics law: the label never ships bare ───────────────────────────

def test_trend_measures_the_magnitude_of_the_position_not_its_signed_value():
    """−2bn → −6bn is a STRENGTHENING short-gamma regime, not a weakening one.

    Comparing raw signed values would call it "weakening" because the number fell —
    exactly backwards, and entirely plausible-looking on a chip.
    """
    gaps: list[str] = []
    b = options_structure_block(
        REPO, gaps,
        # spot moved well clear of the flip so this test isolates the TREND — the
        # default fixture sits 0.59% away, which is correctly reported as near_flip.
        _reader({"SPX": _payload(
            net_gex_bn=-6.0,
            spot_ref=7000.0,
            gamma_flip=7400.0,
            history=[
                {"date": "2026-07-28", "net_gex_bn": -1.0},
                {"date": "2026-07-29", "net_gex_bn": -2.0},
                {"date": "2026-07-30", "net_gex_bn": -6.0},
            ],
        )}),
    )
    assert b["index_regime"] == "short_gamma"
    assert b["regime_trend"] == "strengthening"
    assert b["regime_velocity_1d"] == pytest.approx(-4.0)


def test_a_shrinking_position_reads_as_weakening():
    gaps: list[str] = []
    b = options_structure_block(
        REPO, gaps,
        _reader({"SPX": _payload(
            net_gex_bn=-1.0,
            history=[
                {"date": "2026-07-28", "net_gex_bn": -5.0},
                {"date": "2026-07-29", "net_gex_bn": -4.0},
                {"date": "2026-07-30", "net_gex_bn": -1.0},
            ],
        )}),
    )
    assert b["regime_trend"] == "weakening"


def test_a_small_change_reads_as_stable_rather_than_a_trend():
    gaps: list[str] = []
    b = options_structure_block(
        REPO, gaps,
        _reader({"SPX": _payload(
            net_gex_bn=4.02,
            history=[
                {"date": "2026-07-28", "net_gex_bn": 4.0},
                {"date": "2026-07-29", "net_gex_bn": 4.01},
                {"date": "2026-07-30", "net_gex_bn": 4.02},
            ],
        )}),
    )
    assert b["regime_trend"] == "stable"


def test_thin_history_says_unknown_never_stable():
    """A default that looks like a measurement is worse than an absence.

    "stable" on two sessions of history is a claim the data cannot support, and it is
    indistinguishable on screen from a measured stable regime.
    """
    for hist in (None, [], [{"date": "2026-07-30", "net_gex_bn": 1.0}]):
        gaps: list[str] = []
        b = options_structure_block(REPO, gaps, _reader({"SPX": _payload(history=hist)}))
        assert b["regime_trend"] == "unknown"
        assert b["regime_velocity_1d"] is None


# ── Sign confidence ───────────────────────────────────────────────────────────

def test_sign_confidence_matches_the_terminals_tilt_definition():
    """One definition, two surfaces. |callAbs − putAbs| / (callAbs + putAbs)."""
    gaps: list[str] = []
    b = options_structure_block(REPO, gaps, _reader({"SPX": _payload()}))
    # calls 10+70 = 80, puts 50+10 = 60 -> |80-60| / 140
    assert b["sign_confidence"] == pytest.approx(20 / 140, abs=1e-4)


def test_a_balanced_book_reports_low_confidence():
    gaps: list[str] = []
    b = options_structure_block(
        REPO, gaps,
        _reader({"SPX": _payload(by_strike=[
            {"strike": 100.0, "gamma_net": 0.0, "gamma_call": 50.0, "gamma_put": -50.0},
        ])}),
    )
    assert b["sign_confidence"] == pytest.approx(0.0)


def test_sign_confidence_is_none_without_a_ladder():
    gaps: list[str] = []
    b = options_structure_block(REPO, gaps, _reader({"SPX": _payload(by_strike=[])}))
    assert b["sign_confidence"] is None


# ── OPEX concentration ────────────────────────────────────────────────────────

def test_expiring_share_is_the_front_expiry_by_date_not_by_size():
    gaps: list[str] = []
    b = options_structure_block(
        REPO, gaps,
        _reader({"SPX": _payload(by_expiry=[
            {"exp": "2026-09-18", "gamma_net": 900.0},   # biggest, but NOT the front
            {"exp": "2026-08-01", "gamma_net": 100.0},
        ])}),
    )
    assert b["expiring_gamma_share_pct"] == pytest.approx(10.0)
    assert b["opex_window"] is False


def test_opex_window_flags_a_concentrated_front_expiry():
    gaps: list[str] = []
    b = options_structure_block(
        REPO, gaps,
        _reader({"SPX": _payload(by_expiry=[
            {"exp": "2026-08-01", "gamma_net": 800.0},
            {"exp": "2026-09-18", "gamma_net": 200.0},
        ])}),
    )
    assert b["expiring_gamma_share_pct"] == pytest.approx(80.0)
    assert b["opex_window"] is True


def test_opex_flag_is_none_not_false_when_unknown():
    """False would assert "not an OPEX window", which is a different claim from silence."""
    gaps: list[str] = []
    b = options_structure_block(REPO, gaps, _reader({"SPX": _payload(by_expiry=None)}))
    assert b["expiring_gamma_share_pct"] is None
    assert b["opex_window"] is None


# ── Root selection + fail-open ────────────────────────────────────────────────

def test_first_usable_root_wins_and_the_rest_are_disclosed():
    gaps: list[str] = []
    b = options_structure_block(
        REPO, gaps,
        _reader({"SPY": _payload(root="SPY")}),   # SPX absent
    )
    assert b["root"] == "SPY"
    assert b["roots"] == list(ROOTS)
    assert gaps == []


def test_a_missing_plane_never_raises_and_always_leaves_a_gap():
    gaps: list[str] = []
    b = options_structure_block(REPO, gaps, _reader({}))
    assert b["root"] is None
    assert b["index_regime"] is None
    assert b["regime_trend"] == "unknown"
    assert len(gaps) == 1
    assert "options_structure" in gaps[0]


def test_a_malformed_payload_is_skipped_rather_than_half_read():
    gaps: list[str] = []
    reader = _reader({"SPX": {"not": "a gex payload"}, "SPY": _payload(root="SPY")})
    b = options_structure_block(REPO, gaps, reader)
    assert b["root"] == "SPY"


def test_the_block_is_json_serialisable():
    """It ships inside a ~2KB payload written to disk and served over HTTP."""
    gaps: list[str] = []
    b = options_structure_block(REPO, gaps, _reader({"SPX": _payload()}))
    assert json.loads(json.dumps(b)) == b


def test_the_block_stays_small():
    """market_plane is a header feed with a ~2KB budget across every block."""
    gaps: list[str] = []
    b = options_structure_block(REPO, gaps, _reader({"SPX": _payload()}))
    assert len(json.dumps(b, separators=(",", ":"))) < 400


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ── Audit regression: the history store can LAG the live asof ──────────────────
#
# `history` comes from data/polygon_gex/summary_{ROOT}.parquet, a separately-cadenced
# store whose loader documents that it "CAN lag behind the live asof by one or more
# sessions" — which is why the payload carries coverage.history_asof. _trend used to
# drop history[-1] unconditionally on the assumption it was today's row.
#
# Sampling 60 summary parquets on the live box found 5 stale at 2026-06-22 against 55
# at 2026-07-31, so the lag is real, not theoretical.

def test_a_lagging_history_is_not_treated_as_containing_today():
    """The tail row is dropped only when its date actually matches asof.

    Real SPY numbers: 07-29 -10.21, 07-30 -16.30, 07-31 -6.16. With asof=07-31 and a
    history that stops at 07-30, the correct previous reading is -16.30 (the book
    WEAKENED its short-gamma position). Dropping the tail unconditionally would compare
    against 07-29's -10.21 and report "strengthening" — both the sign of the velocity
    and the label inverted.
    """
    gaps: list[str] = []
    b = options_structure_block(
        REPO, gaps,
        _reader({"SPX": _payload(
            asof="2026-07-31",
            net_gex_bn=-6.16,
            spot_ref=7000.0, gamma_flip=7400.0,
            history=[
                {"date": "2026-07-28", "net_gex_bn": -4.0},
                {"date": "2026-07-29", "net_gex_bn": -10.21},
                {"date": "2026-07-30", "net_gex_bn": -16.30},   # history LAGS asof
            ],
        )}),
    )
    assert b["regime_velocity_1d"] == pytest.approx(-6.16 - (-16.30), abs=1e-6)
    assert b["regime_trend"] == "weakening"


def test_an_aligned_history_still_drops_the_duplicate_tail():
    """Unchanged behaviour when the store IS current — the common case."""
    gaps: list[str] = []
    b = options_structure_block(
        REPO, gaps,
        _reader({"SPX": _payload(
            asof="2026-07-31",
            net_gex_bn=-6.16,
            spot_ref=7000.0, gamma_flip=7400.0,
            history=[
                {"date": "2026-07-29", "net_gex_bn": -10.21},
                {"date": "2026-07-30", "net_gex_bn": -16.30},
                {"date": "2026-07-31", "net_gex_bn": -6.16},   # duplicate of the headline
            ],
        )}),
    )
    assert b["regime_velocity_1d"] == pytest.approx(-6.16 - (-16.30), abs=1e-6)
    assert b["regime_trend"] == "weakening"
