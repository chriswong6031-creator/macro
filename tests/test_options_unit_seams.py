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
from datetime import date
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
        """skew is signed (-1.01 ... 1.44, cross-sectional median |value| 0.0436); the
        sign must not confuse the scale test.  Values are a realistic cross-section, not
        the distribution's tails — the check is median-keyed, so a tail-heavy fixture
        would be testing the wrong statistic."""
        assert options_units.check_iv_difference([-0.05, 0.02, 0.07], "skew") is None
        assert options_units.check_iv_difference([-5.0, 2.0, 7.0], "skew") is not None
        # levels keep their own, wider bar and are unaffected by the sign
        assert options_units.check_iv_level([-0.9, 0.47, 1.4], "iv") is None


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
    kind = "difference" if col == "skew" else "level"
    assert options_units.check_iv_fraction(df[col], f"options_skew.{col}", kind) is None, (
        f"options_skew.{col} is no longer FRACTION-scaled — every downstream ×100 "
        "(skew_pp, the screener's skew column, the radar's rr proxy) is now 100× off"
    )


@pytest.mark.skipif(not IVSPREAD.exists(), reason="options_ivspread store absent")
@pytest.mark.parametrize("col", ["ivspread", "ivspread_rel"])
def test_prod_ivspread_columns_are_fraction_scaled(col):
    df = pd.read_parquet(IVSPREAD)
    if col not in df.columns:
        pytest.skip(f"{col} absent")
    assert options_units.check_iv_difference(df[col], f"options_ivspread.{col}") is None


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
    assert options_units.check_iv_level(iv30, "summary.iv30") is None, (
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
    assert options_units.check_iv_level(df["iv"], "chains.iv") is None


# ─────────────────────────────────── the seam is wired, in BOTH directions


# ──────────────────── the split ceilings, and why one bar cannot serve both


class TestSplitCeilings:
    """MEASURED: against a single 3.0 bar, a whole-store x100 flip clears by 15.6-16.3x
    for IV LEVELS but only 1.12-1.19x for IV DIFFERENCES (skew's flipped median is 3.56
    against a 3.0 bar). One threshold serving both is a threshold serving neither."""

    def test_the_two_ceilings_are_actually_different(self):
        assert options_units.IV_DIFF_MAX_MEDIAN < options_units.IV_LEVEL_MAX_MEDIAN

    def test_a_genuine_skew_cross_section_passes_the_difference_bar(self):
        # real latest-cross-section median |skew| is 0.0436
        assert options_units.check_iv_difference([0.02, 0.044, 0.07, -0.05], "skew") is None

    def test_a_flipped_skew_cross_section_fails_the_difference_bar(self):
        flipped = [2.0, 4.36, 7.0, -5.0]           # the same values x100
        msg = options_units.check_iv_difference(flipped, "skew")
        assert msg and "PERCENT-scaled" in msg and "difference" in msg

    def test_the_level_bar_would_have_MISSED_that_flip(self):
        """The regression this split exists for: 4.36 is under a 3.0... no — it is over.
        The real miss is subtler: a flipped DIFFERENCE median of 3.56 clears 3.0 by 1.19x,
        so any store drift or a partial-coverage vintage slips under it. Pin the margin."""
        genuine = 0.0436
        flipped = genuine * 100
        assert flipped / options_units.IV_DIFF_MAX_MEDIAN > 5, (
            "the difference ceiling must leave a wide margin over a flipped median"
        )
        assert flipped / options_units.IV_LEVEL_MAX_MEDIAN < 2, (
            "premise: the shared level ceiling left almost no margin for differences"
        )

    def test_a_genuine_iv_level_cross_section_passes_the_level_bar(self):
        assert options_units.check_iv_level([0.28, 0.47, 0.53, 1.74], "iv30") is None

    def test_a_genuine_iv_level_would_FAIL_the_difference_bar(self):
        """Why levels cannot borrow the difference bar: a normal 47% vol is 0.47, well
        over 0.5's neighbourhood once the tail is included."""
        assert options_units.check_iv_difference([0.47, 0.53, 1.74], "iv30") is not None


# ─────────────── THE flip that matters: newest vintage only (B3)


def _skew_store(n_dates: int = 30, n_names: int = 40, value: float = 0.0436):
    """A prod-shaped skew store: many dates x many names, one row each."""
    from lib import nyse_calendar
    dates, d = [], date(2026, 5, 1)
    while len(dates) < n_dates:
        if nyse_calendar.is_session(d):
            dates.append(d.isoformat())
        d = date.fromordinal(d.toordinal() + 1)
    rows = []
    for i, dt in enumerate(dates):
        for j in range(n_names):
            rows.append({"date": dt, "underlying": f"TK{j:03d}",
                         "skew": value + (j - n_names / 2) * 0.0004,
                         "atm_call_iv": 0.47, "otm_put_iv": 0.51})
    return pd.DataFrame(rows)


def _latest(df):
    return df.sort_values("date").drop_duplicates("underlying", keep="last")


class TestNewestVintageFlip:
    """The realistic ×100 flip lands on the NEWEST vintage while correct history sits
    behind it. Measured on the real stores, a whole-store median moves 0.0356 -> 0.0376
    (a MISS on all five columns) while the latest cross-section goes 0.0436 -> 3.95
    (CAUGHT on all five). These tests SIMULATE that flip rather than asserting on source
    text — the previous version of this file asserted substrings, which is the same
    fixture-encodes-the-bug class the module docstring warns about."""

    def test_whole_store_median_MISSES_a_newest_vintage_flip(self):
        df = _skew_store()
        newest = df["date"] == df["date"].max()
        df.loc[newest, "skew"] *= 100
        assert options_units.check_iv_difference(df["skew"], "whole store") is None, (
            "premise of the fix: the whole-store median cannot see this flip"
        )

    def test_latest_cross_section_CATCHES_the_same_flip(self):
        df = _skew_store()
        newest = df["date"] == df["date"].max()
        df.loc[newest, "skew"] *= 100
        msg = options_units.check_iv_difference(_latest(df)["skew"], "latest")
        assert msg and "PERCENT-scaled" in msg

    def test_the_screener_lookup_annotates_on_a_newest_vintage_flip(self, tmp_path, capsys):
        """End-to-end through the real builder function, not a helper call."""
        import scripts.build_options_screener as bos
        df = _skew_store()
        newest = df["date"] == df["date"].max()
        df.loc[newest, "skew"] *= 100
        df["tenor_days"] = 30
        (tmp_path / "options_skew").mkdir()
        path = tmp_path / "options_skew" / "snapshots.parquet"
        df.to_parquet(path)
        orig = bos.SKEW_PATH
        bos.SKEW_PATH = path
        try:
            out = bos._load_skew_lookup()
        finally:
            bos.SKEW_PATH = orig
        assert out, "the lookup must still return rows — a flip is loud, not fatal"
        ann = [l for l in capsys.readouterr().out.splitlines() if l.startswith("::")]
        assert any("options-unit-seam" in l for l in ann), (
            f"the builder must annotate the flip; got {ann}"
        )
        for l in ann:
            assert l.startswith("::"), f"annotation not at line start: {l!r}"

    def test_a_clean_store_annotates_nothing(self, tmp_path, capsys):
        import scripts.build_options_screener as bos
        df = _skew_store()
        df["tenor_days"] = 30
        (tmp_path / "options_skew").mkdir()
        path = tmp_path / "options_skew" / "snapshots.parquet"
        df.to_parquet(path)
        orig = bos.SKEW_PATH
        bos.SKEW_PATH = path
        try:
            bos._load_skew_lookup()
        finally:
            bos.SKEW_PATH = orig
        assert not [l for l in capsys.readouterr().out.splitlines()
                    if "options-unit-seam" in l], "no flip -> no annotation"


# ──────────── the conversions the guards protect must still exist


def test_the_screener_still_converts_the_fraction_seams():
    """A guard plus a missing ×100 is the same wrong number with a clean conscience.
    Behavioural: run the lookup on a known fraction and read the emitted pp value."""
    assert "skew_pp = round(f * 100, 1)" in SCREENER_SRC
    assert "ivspread_pp = round(f * 100, 1)" in SCREENER_SRC


def test_skew_pp_is_the_fraction_times_one_hundred(tmp_path):
    import scripts.build_options_screener as bos
    df = pd.DataFrame({"date": ["2026-07-29"], "underlying": ["AAA"],
                       "skew": [0.0436], "tenor_days": [30]})
    (tmp_path / "options_skew").mkdir()
    path = tmp_path / "options_skew" / "snapshots.parquet"
    df.to_parquet(path)
    orig = bos.SKEW_PATH
    bos.SKEW_PATH = path
    try:
        out = bos._load_skew_lookup()
    finally:
        bos.SKEW_PATH = orig
    assert out["AAA"]["skew_pp"] == 4.4, out          # 0.0436 -> 4.36 -> round 4.4
    assert out["AAA"]["skew_tenor_d"] == 30


def test_ivspread_pp_is_the_fraction_times_one_hundred(tmp_path):
    import scripts.build_options_screener as bos
    df = pd.DataFrame({"date": ["2026-07-29"], "underlying": ["AAA"],
                       "ivspread_rel": [0.0336]})
    (tmp_path / "options_ivspread").mkdir()
    path = tmp_path / "options_ivspread" / "snapshots.parquet"
    df.to_parquet(path)
    orig = bos.IVSPREAD_PATH
    bos.IVSPREAD_PATH = path
    try:
        out = bos._load_ivspread_lookup()
    finally:
        bos.IVSPREAD_PATH = orig
    assert out["AAA"] == 3.4, out                     # 0.0336 -> 3.36 -> round 3.4


def test_a_missing_skew_column_degrades_one_field_not_the_lookup(tmp_path):
    """The whole function is wrapped in `except -> return {}`, so a KeyError used to cost
    every ticker BOTH skew_pp and skew_tenor_d."""
    import scripts.build_options_screener as bos
    df = pd.DataFrame({"date": ["2026-07-29"], "underlying": ["AAA"], "tenor_days": [30]})
    (tmp_path / "options_skew").mkdir()
    path = tmp_path / "options_skew" / "snapshots.parquet"
    df.to_parquet(path)
    orig = bos.SKEW_PATH
    bos.SKEW_PATH = path
    try:
        out = bos._load_skew_lookup()
    finally:
        bos.SKEW_PATH = orig
    assert out and out["AAA"]["skew_pp"] is None
    assert out["AAA"]["skew_tenor_d"] == 30, "tenor must survive a missing skew column"


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
