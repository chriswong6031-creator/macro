"""Percent-vs-fraction contracts on the options ingestion seams — the ×100 class.

This defect class has landed twice.  Its signature: a store column changes scale (or a
new seam is written against the wrong assumption), the builder's ``× 100`` fires anyway,
and a surface prints a plausible-looking number that is 100× off.  Nothing asserted the
scale, so nothing went red.

The trap that let the earlier unit tests pass through it: the FIXTURE encoded the bug.
A test frame carrying ``iv30 = 28.5`` (percent-shaped) exercises a builder that
multiplies by 100 and "passes", because the fixture and the builder are wrong together.
So every seam here is exercised against BOTH shapes:

  * FIXTURE-SHAPED — hand-built tiny frames, both correct and flipped;
  * PROD-SHAPED    — the real stores, when present (skipped otherwise, never faked),
                     asserted against the magnitudes measured on 2026-07-29.

Measured contracts (real stores, 2026-07-29):
    FRACTION: options_skew.{atm_call_iv, otm_put_iv, skew}, options_ivspread.{ivspread,
              ivspread_rel}, polygon_gex.summary.iv30, polygon_gex.chains.iv
    PERCENT : polygon_gex.summary.dist_to_flip_pct, and every screener row field whose
              name ends in _pct / _pp (they are the post-×100 side of the seam)

Run: .venv/bin/python -m pytest tests/test_options_unit_seams.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import config, options_units  # noqa: E402

DATA = config.data_dir()
SKEW = DATA / "options_skew" / "snapshots.parquet"
IVSPREAD = DATA / "options_ivspread" / "snapshots.parquet"
GEX_DIR = DATA / "polygon_gex"
SCREENER_SRC = (ROOT / "scripts" / "build_options_screener.py").read_text()


# ───────────────────────────────────────────────── the checkers, fixture-shaped


class TestFractionChecker:
    def test_a_correct_fraction_series_is_silent(self):
        # 20%–90% vol, the ordinary range
        assert options_units.check_iv_fraction([0.20, 0.28, 0.47, 0.90], "iv") is None

    def test_a_percent_shaped_series_is_caught(self):
        """THE BUG: the same vols already multiplied by 100."""
        msg = options_units.check_iv_fraction([20.0, 28.0, 47.0, 90.0], "iv")
        assert msg and "PERCENT-scaled" in msg
        assert "FRACTION" in msg, "the message must name the expected contract"

    def test_a_genuine_high_iv_blowout_is_not_a_false_alarm(self):
        """chains.iv reaches 9.32 legitimately (932% near-expiry vol). The check keys on
        the MEDIAN, so a fat tail must not trip it."""
        vals = [0.3] * 50 + [9.32, 8.0, 7.5]
        assert options_units.check_iv_fraction(vals, "chains.iv") is None

    def test_all_percent_shaped_even_with_small_tail(self):
        vals = [45.0] * 50 + [0.3, 0.4]
        assert options_units.check_iv_fraction(vals, "iv") is not None

    @pytest.mark.parametrize("vals", [[], [None, None], [float("nan")], ["x", "y"]])
    def test_nothing_to_judge_is_silent_not_an_alarm(self, vals):
        assert options_units.check_iv_fraction(vals, "iv") is None

    def test_negative_values_are_judged_on_magnitude(self):
        """skew is signed (−1.01 … 1.44); the sign must not confuse the scale test."""
        assert options_units.check_iv_fraction([-0.9, 0.02, 1.4], "skew") is None
        assert options_units.check_iv_fraction([-90.0, 2.0, 140.0], "skew") is not None


class TestPercentChecker:
    def test_a_correct_percent_series_is_silent(self):
        assert options_units.check_percent_scale([3.74, 12.82, 23.75], "dist") is None

    def test_a_fraction_shaped_series_is_caught(self):
        """The reverse flip: someone divided by 100 twice, or dropped the multiply."""
        msg = options_units.check_percent_scale([0.0374, 0.1282, 0.2375], "dist")
        assert msg and "FRACTION-scaled" in msg
        assert "PERCENT" in msg

    def test_a_genuinely_tiny_percent_is_not_a_false_alarm(self):
        """A name sitting exactly on its flip legitimately reads ~0.02%; the MEDIAN
        decides, so one pinned name must not trip the check."""
        vals = [0.02, 0.01] + [8.0] * 20
        assert options_units.check_percent_scale(vals, "dist") is None


class TestAnnotationShape:
    def test_annotation_starts_the_line_with_flush(self, capsys):
        fired = options_units.annotate("iv: median |value| = 45, PERCENT-scaled")
        assert fired is True
        out = capsys.readouterr().out.splitlines()
        ann = [ln for ln in out if "::" in ln]
        assert ann, "annotate() must emit something"
        for ln in ann:
            assert ln.startswith("::"), (
                f"annotation not at line start: {ln!r} — a logger prefix makes GitHub "
                "drop the whole workflow command"
            )
        assert any(ln.startswith("::warning title=options-unit-seam::") for ln in ann)

    def test_no_message_emits_nothing(self, capsys):
        assert options_units.annotate(None) is False
        assert capsys.readouterr().out == ""

    def test_guards_never_raise_on_junk(self):
        for junk in (None, [], [object()], ["a"], [{}]):
            options_units.guard_iv_fraction(junk or [], "x")
            options_units.guard_percent_scale(junk or [], "x")


# ──────────────────────────────────────────────────────── prod-shaped: the stores


@pytest.mark.skipif(not SKEW.exists(), reason="options_skew store absent on this runner")
@pytest.mark.parametrize("col", ["atm_call_iv", "otm_put_iv", "skew"])
def test_prod_skew_columns_are_fraction_scaled(col):
    df = pd.read_parquet(SKEW)
    if col not in df.columns:
        pytest.skip(f"{col} absent")
    assert options_units.check_iv_fraction(df[col], f"options_skew.{col}") is None, (
        f"options_skew.{col} is no longer FRACTION-scaled — every downstream ×100 "
        "(skew_pp, the screener's skew column, the radar's rr proxy) is now 100× off"
    )


@pytest.mark.skipif(not IVSPREAD.exists(), reason="options_ivspread store absent")
@pytest.mark.parametrize("col", ["ivspread", "ivspread_rel"])
def test_prod_ivspread_columns_are_fraction_scaled(col):
    df = pd.read_parquet(IVSPREAD)
    if col not in df.columns:
        pytest.skip(f"{col} absent")
    assert options_units.check_iv_fraction(df[col], f"options_ivspread.{col}") is None


@pytest.mark.skipif(not GEX_DIR.exists(), reason="polygon_gex store absent")
def test_prod_gex_summary_mixes_the_two_scales_exactly_as_documented():
    """iv30 is a FRACTION, dist_to_flip_pct is already PERCENT. The one store carrying
    both scales is where the class bites — pin both directions together."""
    files = sorted(GEX_DIR.glob("summary_*.parquet"))[:40]
    if not files:
        pytest.skip("no summary parquets")
    iv30, dist = [], []
    for f in files:
        df = pd.read_parquet(f)
        if "iv30" in df.columns:
            iv30 += list(df["iv30"])
        if "dist_to_flip_pct" in df.columns:
            dist += list(df["dist_to_flip_pct"])
    assert options_units.check_iv_fraction(iv30, "summary.iv30") is None, (
        "summary.iv30 must stay FRACTION — the screener multiplies it by 100 for the "
        "iv30 column AND again inside implied_move_30d"
    )
    assert options_units.check_percent_scale(dist, "summary.dist_to_flip_pct") is None, (
        "summary.dist_to_flip_pct must stay PERCENT — the screener passes it through "
        "with no conversion"
    )


@pytest.mark.skipif(not (GEX_DIR / "chains").exists(), reason="chains absent")
def test_prod_chain_iv_is_fraction_scaled():
    files = sorted((GEX_DIR / "chains").glob("*.parquet"))
    if not files:
        pytest.skip("no chain snapshots")
    df = pd.read_parquet(files[-1], columns=["iv"])
    assert options_units.check_iv_fraction(df["iv"], "chains.iv") is None


# ─────────────────────────────────── the seam is wired, in BOTH directions


def test_the_screener_wires_both_guards():
    """A guard nobody calls is decoration. Pin the call sites in the builder."""
    assert 'options_units.guard_iv_fraction(df["skew"]' in SCREENER_SRC
    assert 'options_units.guard_iv_fraction(df["ivspread_rel"]' in SCREENER_SRC
    assert "guard_iv_fraction(\n" in SCREENER_SRC and "pre-×100" in SCREENER_SRC, \
        "the iv30 seam guard must be present"
    assert "guard_percent_scale(" in SCREENER_SRC and "pass-through" in SCREENER_SRC, \
        "the dist_to_flip_pct pass-through guard must be present"


def test_the_screener_still_converts_the_fraction_seams():
    """The conversions the guards protect must actually exist — a guard plus a missing
    ×100 is the same wrong number with a clean conscience."""
    assert "skew_pp = round(f * 100, 1)" in SCREENER_SRC
    assert "ivspread_pp = round(f * 100, 1)" in SCREENER_SRC
    assert 'round(iv30 * 100, 1) if iv30 is not None else None' in SCREENER_SRC
    assert "iv30 * math.sqrt(30 / 365) * 100" in SCREENER_SRC


def test_dist_to_flip_is_never_multiplied_in_the_screener():
    """The mirror assertion: the PERCENT field must NOT be converted."""
    body = SCREENER_SRC.split("dist_to_flip_pct", 1)[1][:4000]
    assert "dist_to_flip_pct * 100" not in body
    assert "dist_to_flip_pct\") * 100" not in body


@pytest.mark.skipif(not GEX_DIR.exists(), reason="polygon_gex store absent")
def test_screener_output_rows_land_on_the_percent_side():
    """End-to-end on the real store: the emitted rows must be percent-scaled, i.e. the
    seam actually fired.  A silent regression to fractions would make every IV read 0.3."""
    rows_json = ROOT / "site" / "screenerdata" / "rows.json"
    if not rows_json.exists():
        pytest.skip("rows.json not built on this runner")
    import json
    rows = json.loads(rows_json.read_text())["rows"]
    iv = [r["iv30"] for r in rows if r.get("iv30") is not None]
    if not iv:
        pytest.skip("no iv30 values")
    assert options_units.check_percent_scale(iv, "row.iv30") is None, (
        "emitted row iv30 is fraction-scaled — the ×100 seam did not fire"
    )
    dist = [r["dist_to_flip_pct"] for r in rows if r.get("dist_to_flip_pct") is not None]
    if dist:
        assert options_units.check_percent_scale(dist, "row.dist_to_flip_pct") is None
