"""tests/test_regen_hk_g1_fixture.py — scripts/regen_hk_g1_fixture.py.

The generator exists so a yahoo dividend adjustment (which rewrites a ticker's
whole price history and hard-fails ``TestG1FixtureIsNotStale``) has a remedy that
is a re-pin WITH a receipt rather than a hand-edit.  Two properties make it safe
to run, and both are guarded here:

  * on an UNCHANGED panel it is a byte-level no-op — running it never churns the
    fixture, so it can be run to ask a question, not only to answer one.  An
    append-only panel advance (new panel sha, identical frozen payload) is the
    same no-op, which is why the sha is stamped on real writes only;
  * on drift it classifies before it writes.  A constant-ratio rewrite prints an
    ADJUSTMENT-SIGNATURE receipt and re-pins; a NON-constant rewrite, calendar
    surgery, a ticker-set change, or verdict/meta movement on a ticker whose
    closes did not move is REFUSED with the file untouched.

A THIRD property was added 2026-08-05 and has its own section below: the window
each ticker is re-cut to is that ticker's OWN committed first date, never a flat
``tail(N)`` from one era-wide count.  The generator shipped cutting the flat tail,
which is correct only while every window in the era happens to be the same length.
The 2026-07-31 freeze is 3B-phase-aligned and holds THREE lengths (342/341/340)
behind a single ``_tail_sessions: 340`` stamp, so a flat re-pin re-phased 123 of
its 157 tickers, silently moved every ``resample("3B")`` bucket label the frozen
verdicts' markers sit on, and collapsed the HK vetoed lane from 33 measured names
(max move 24.3%) to 5 (max 4.7%) — top-first, so the surviving maximum described
nothing.  ``TestTheWindowIsPerTickerNotACount`` pins the fix and, deliberately,
also pins that its own bed can still expose the defect.

Everything runs against SYNTHETIC panels built once per session — no repo data, no
subprocesses.  There are two beds: the flat-window one (three tickers, one shared
start, ``_tail_sessions: 90``) that the original suite was written against, and a
3B-phase-aligned one whose tickers start on three different sessions so their
windows come out 90/92/91 — the real fixture's shape in miniature.  Each test
copies its bed into its own tmp dir, so a test that writes cannot leak into the
next one.  "Untouched" is asserted on bytes AND ``st_mtime_ns``: a rewrite with
identical content is still a write, and this suite must be able to tell them apart.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")
pytest.importorskip("pyarrow")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import regen_hk_g1_fixture as regen        # noqa: E402
from scripts.regen_hk_g1_fixture import main            # noqa: E402


AS_OF = "2026-07-31"
TAIL = 90
TICKERS = ("0001.HK", "0002.HK", "0003.HK")
SESSIONS = 300

# The 3B bed.  Each ticker's column starts one business day later than the last,
# so the walk-back to a phase boundary lands a different distance for each and the
# three windows come out 90 / 92 / 91 — heterogeneous by construction, which is
# the property a flat tail cannot reproduce.
TICKERS_3B = ("0011.HK", "0012.HK", "0013.HK")
LEAD_NANS = (0, 1, 2)
MIN_SESSIONS_3B = 90
PHASE_MOD = 3
ANCHOR_3B = {"rule": "3b_phase_aligned", "min_sessions": MIN_SESSIONS_3B,
             "phase_mod": PHASE_MOD}


def _phase(series: "pd.Series", start: str) -> int:
    """Business days from the column's first session to ``start``, mod PHASE_MOD.

    Zero is the invariant: ``signal_quality.signal_frame`` anchors its ``3B`` bins
    on the series' first index, so a window that does not start on a bin boundary
    of its own full column re-labels every bucket the frozen markers name.
    """
    return int(np.busday_count(str(series.index[0].date()), start)) % PHASE_MOD


def _panel_frame() -> "pd.DataFrame":
    """Deterministic, strictly positive closes — no randomness, no NaN."""
    index = pd.bdate_range(end=AS_OF, periods=SESSIONS)
    data = {
        ticker: [10.0 + 0.01 * i + 0.05 * (i % 7) + k
                 for i in range(SESSIONS)]
        for k, ticker in enumerate(TICKERS)
    }
    return pd.DataFrame(data, index=index, dtype="float64")


@pytest.fixture(scope="session")
def template(tmp_path_factory):
    """One built-once panel + bootstrapped fixture; every test copies it.

    The bootstrap is itself the documented first-run flow: against a seed fixture
    with empty sections every ticker is an ADDITION, which is a structural refusal,
    so minting the payload the first time takes ``--force``.
    """
    root = tmp_path_factory.mktemp("regen_g1_template")
    panel_path = root / "closes_deep.parquet"
    _panel_frame().to_parquet(panel_path)

    fixture_path = root / "hk_board_2026_07_31.json"
    fixture_path.write_text(json.dumps({
        "_note": "seed",
        "_source": str(panel_path),
        "_source_sha256_16": "0" * 16,
        "_as_of": AS_OF,
        "_tail_sessions": TAIL,
        "verdicts": {},
        "meta": {},
        "closes": {},
    }))

    assert main(["--fixture", str(fixture_path), "--panel", str(panel_path),
                 "--force"]) == 0
    return {"panel": panel_path, "fixture": fixture_path}


class _Bed:
    """One test's private panel + fixture pair."""

    def __init__(self, panel: Path, fixture: Path):
        self.panel = panel
        self.fixture = fixture

    def run(self, *flags: str) -> int:
        return main(["--fixture", str(self.fixture), "--panel", str(self.panel),
                     *flags])

    def state(self) -> tuple[bytes, int]:
        return self.fixture.read_bytes(), self.fixture.stat().st_mtime_ns

    def payload(self) -> dict:
        return json.loads(self.fixture.read_text())

    def frame(self) -> "pd.DataFrame":
        return pd.read_parquet(self.panel)

    def rewrite(self, frame: "pd.DataFrame") -> None:
        frame.to_parquet(self.panel)

    def restore_clean_panel(self) -> None:
        _panel_frame().to_parquet(self.panel)


@pytest.fixture
def bed(template, tmp_path):
    """A private copy of the bootstrapped pair — a test that writes cannot leak."""
    panel = tmp_path / "closes_deep.parquet"
    fixture = tmp_path / "hk_board_2026_07_31.json"
    shutil.copy2(template["panel"], panel)
    shutil.copy2(template["fixture"], fixture)
    return _Bed(panel=panel, fixture=fixture)


def _phase_aligned_frame() -> "pd.DataFrame":
    """Three columns with three different FIRST sessions — hence three windows.

    The leading NaNs are the whole point: ``dropna()`` gives each ticker its own
    column start, the phase walk-back therefore travels 0 / 2 / 1 sessions, and the
    frozen windows come out 90 / 92 / 91.  A bed where every column starts on the
    same session cannot tell a phase-aligned cut from a flat one.
    """
    index = pd.bdate_range(end=AS_OF, periods=SESSIONS)
    data = {}
    for k, (ticker, lead) in enumerate(zip(TICKERS_3B, LEAD_NANS)):
        values = [10.0 + 0.01 * i + 0.05 * (i % 7) + k for i in range(SESSIONS)]
        for i in range(lead):
            values[i] = float("nan")
        data[ticker] = values
    return pd.DataFrame(data, index=index, dtype="float64")


@pytest.fixture(scope="session")
def template_3b(tmp_path_factory):
    """A bootstrapped fixture stamped ``_tail_anchor``, not ``_tail_sessions``."""
    root = tmp_path_factory.mktemp("regen_g1_template_3b")
    panel_path = root / "closes_deep.parquet"
    _phase_aligned_frame().to_parquet(panel_path)

    fixture_path = root / "hk_board_2026_07_31.json"
    fixture_path.write_text(json.dumps({
        "_note": "seed",
        "_source": str(panel_path),
        "_source_sha256_16": "0" * 16,
        "_as_of": AS_OF,
        "_tail_anchor": dict(ANCHOR_3B),
        "verdicts": {},
        "meta": {},
        "closes": {},
    }))

    assert main(["--fixture", str(fixture_path), "--panel", str(panel_path),
                 "--force"]) == 0
    return {"panel": panel_path, "fixture": fixture_path}


@pytest.fixture
def bed3b(template_3b, tmp_path):
    panel = tmp_path / "closes_deep.parquet"
    fixture = tmp_path / "hk_board_2026_07_31.json"
    shutil.copy2(template_3b["panel"], panel)
    shutil.copy2(template_3b["fixture"], fixture)
    return _Bed(panel=panel, fixture=fixture)


# --------------------------------------------------------------------------- #
# 1. the no-op contract
# --------------------------------------------------------------------------- #
def test_bootstrap_then_byte_idempotent(bed, capsys):
    """Re-running on an unchanged panel writes NOTHING — not even identical bytes."""
    before_bytes, before_mtime = bed.state()
    assert bed.run() == 0
    out = capsys.readouterr().out
    after_bytes, after_mtime = bed.state()

    assert "NO-OP" in out
    assert after_bytes == before_bytes
    assert after_mtime == before_mtime, "an identical rewrite is still a write"

    # the bootstrap really did mint the payload it is now idempotent on
    payload = json.loads(before_bytes)
    assert list(payload["verdicts"]) == list(TICKERS)
    assert list(payload["meta"]) == list(TICKERS)
    assert list(payload["closes"]) == list(TICKERS)
    assert len(payload["closes"]["0001.HK"]["dates"]) == TAIL
    assert payload["_note"] == regen.NOTE
    assert payload["_source_sha256_16"] != "0" * 16


def test_append_only_advance_is_noop(bed, capsys):
    """Sessions appended AFTER the as-of move the panel sha and nothing else."""
    before_bytes, before_mtime = bed.state()
    frame = bed.frame()
    extra = pd.DataFrame(
        {ticker: [float(frame[ticker].iloc[-1]) + 0.1,
                  float(frame[ticker].iloc[-1]) + 0.2] for ticker in TICKERS},
        index=pd.to_datetime(["2026-08-03", "2026-08-04"]))
    bed.rewrite(pd.concat([frame, extra]))

    assert bed.run() == 0
    out = capsys.readouterr().out
    after_bytes, after_mtime = bed.state()

    assert "NO-OP" in out
    assert after_bytes == before_bytes
    assert after_mtime == before_mtime
    assert json.loads(after_bytes)["_source_sha256_16"] == \
        json.loads(before_bytes)["_source_sha256_16"], \
        "the sha is provenance for the last real freeze, not a panel mtime"


# --------------------------------------------------------------------------- #
# 2. adjustment drift — re-pin WITH a receipt
# --------------------------------------------------------------------------- #
def _adjust(bed, ratio: float = 0.987, before_last: int = 50) -> None:
    """Rescale every session strictly older than ``before_last``-from-the-end.

    Mirrors a dividend adjustment's shape: one constant ratio applied to a
    contiguous historical block, leaving the recent sessions alone.
    """
    frame = bed.frame()
    cut = len(frame) - before_last
    frame.iloc[:cut] = frame.iloc[:cut] * ratio
    bed.rewrite(frame)


def test_constant_ratio_adjustment_repins_with_receipt(bed, capsys):
    before = bed.payload()
    _adjust(bed)

    assert bed.run() == 0
    out = capsys.readouterr().out
    after = bed.payload()

    assert "ADJUSTMENT-SIGNATURE" in out
    assert "dates_equal=True" in out
    assert "0.987" in out, "the receipt must carry the measured ratio"
    for ticker in TICKERS:
        assert f"ADJUSTMENT-SIGNATURE {ticker}" in out
    assert "REFUSE" not in out

    assert after["closes"] != before["closes"], "the re-pin must land"
    assert after["closes"]["0001.HK"]["dates"] == before["closes"]["0001.HK"]["dates"]
    assert after["_source_sha256_16"] != before["_source_sha256_16"]

    # ~40 of the 90 stored sessions moved: the block boundary sits inside the tail
    moved = sum(1 for old, new in zip(before["closes"]["0001.HK"]["closes"],
                                      after["closes"]["0001.HK"]["closes"])
                if old != new)
    assert 30 <= moved <= 50, moved


# --------------------------------------------------------------------------- #
# 3. refusals — the file is not touched
# --------------------------------------------------------------------------- #
def _corrupt_one_session(bed) -> None:
    """One session ×1.5 — a re-printed close, not a rescaled history.

    Exactly one stored session moves, which is the shape the constant-ratio test is
    arithmetically incapable of failing on its own (median of one ratio, residual
    zero).  The generator refuses it on that ground, so this is also the guard on
    the guard: a signature that could not fail would let this through.
    """
    frame = bed.frame()
    frame.iloc[-10, 0] = float(frame.iloc[-10, 0]) * 1.5
    bed.rewrite(frame)


def test_non_constant_drift_refuses_untouched(bed, capsys):
    before_bytes, before_mtime = bed.state()
    _corrupt_one_session(bed)

    assert bed.run() == 2
    out = capsys.readouterr().out
    after_bytes, after_mtime = bed.state()

    assert after_bytes == before_bytes
    assert after_mtime == before_mtime
    assert "REFUSE 0001.HK" in out
    assert "human eyes" in out
    assert "--force" in out
    assert "Nothing was written." in out


def test_force_writes_through_refusal(bed, capsys):
    before_bytes, _ = bed.state()
    _corrupt_one_session(bed)

    assert bed.run("--force") == 0
    out = capsys.readouterr().out

    assert "FORCED past" in out
    assert bed.fixture.read_bytes() != before_bytes
    assert bed.payload()["closes"]["0001.HK"]["closes"] != \
        json.loads(before_bytes)["closes"]["0001.HK"]["closes"]


def test_check_never_writes(bed, capsys):
    # a) refusal state — --check reports it and still writes nothing
    _corrupt_one_session(bed)
    before_bytes, before_mtime = bed.state()
    assert bed.run("--check") == 2
    out = capsys.readouterr().out
    assert bed.state() == (before_bytes, before_mtime)
    assert "REFUSE 0001.HK" in out

    # b) clean state — --check on a byte-idempotent pair is a plain no-op
    bed.restore_clean_panel()
    before_bytes, before_mtime = bed.state()
    assert bed.run("--check") == 0
    out = capsys.readouterr().out
    assert bed.state() == (before_bytes, before_mtime)
    assert "NO-OP" in out


def test_derived_only_drift_refuses(bed, capsys, monkeypatch):
    """A verdict that moves while its stored closes do not is never written blind.

    That shape is either a panel rewrite DEEPER than the 90-session tail can see or
    an engine-era change — both need a human, so an engine-change PR re-pins with
    ``--force`` and a data surprise stops here.  Patched at the seam the script
    itself calls, so the refusal is exercised through the real code path.
    """
    real_compact = regen.signal_gate.compact

    def shifted(verdict):
        out = dict(real_compact(verdict))
        if out.get("ticks") is not None:
            out["ticks"] = int(out["ticks"]) + 7
        else:
            out["ticks"] = 7
        return out

    before_bytes, before_mtime = bed.state()
    monkeypatch.setattr(regen.signal_gate, "compact", shifted)

    assert bed.run() == 2
    out = capsys.readouterr().out

    assert bed.state() == (before_bytes, before_mtime)
    assert "REFUSE 0001.HK" in out
    assert "verdict.ticks" in out
    assert "closes did NOT" in out
    assert "human eyes" in out


# --------------------------------------------------------------------------- #
# 4. the window is PER-TICKER, and it is not a count
# --------------------------------------------------------------------------- #
class TestTheWindowIsPerTickerNotACount:
    """Each ticker is re-cut from its OWN committed first date.

    The generator shipped cutting ``series.tail(_tail_sessions)`` — one count for
    every ticker.  That is right only while the era's windows all happen to be the
    same length, and the 2026-07-31 freeze's are not: it is 3B-phase-aligned, so it
    carries 342/341/340-session windows behind a single ``_tail_sessions: 340``
    stamp.  Re-pinning it flat re-phased 123 of 157 tickers and deleted the top 11
    of 33 rows from the HK vetoed lane.

    Every assertion below is paired with the reason it can fail, because the defect
    it guards was invisible for exactly one reason: the invariant was prose.
    """

    def test_the_three_windows_have_three_different_lengths(self, bed3b):
        """The bed's premise. Without it every test in this class is decoration."""
        closes = bed3b.payload()["closes"]
        lengths = {t: len(closes[t]["dates"]) for t in TICKERS_3B}
        assert sorted(lengths.values()) == [90, 91, 92], lengths
        assert len(set(lengths.values())) == 3, (
            "a bed whose windows are all the same length cannot tell a per-ticker "
            f"cut from a flat one: {lengths}")

    def test_every_frozen_window_starts_on_a_3b_bucket_boundary(self, bed3b):
        """THE INVARIANT, checked AFTER a re-pin — not only on the bootstrap.

        Checking it on the freshly bootstrapped file would be near-vacuous: the
        bootstrap has no committed window to preserve, so it cuts by the era rule
        and is phase-aligned no matter how the RE-PIN path slices.  The defect lives
        in the re-pin.  So this drives a real write first (a constant-ratio
        adjustment, the flow the script exists for) and measures the windows the
        re-pin left behind.
        """
        panel = pd.read_parquet(bed3b.panel).loc[:AS_OF]
        before = {t: _phase(panel[t].dropna(), v["dates"][0])
                  for t, v in bed3b.payload()["closes"].items()}
        assert set(before.values()) == {0}, before

        frame = bed3b.frame()
        frame.iloc[:-50] = frame.iloc[:-50] * 0.987
        bed3b.rewrite(frame)
        assert bed3b.run() == 0, "the adjustment must actually re-pin"

        closes = bed3b.payload()["closes"]
        after = {t: _phase(panel[t].dropna(), closes[t]["dates"][0])
                 for t in TICKERS_3B}
        assert set(after.values()) == {0}, (
            f"off-grid after the re-pin {({t: p for t, p in after.items() if p})} — "
            f"every frozen verdict's marker date stops being a 3B bucket label, and "
            f"the move-anchored lanes silently lose the rows they cannot anchor")

    def test_a_flat_tail_would_take_two_of_the_three_off_grid(self, bed3b):
        """THE GUARD ON THE GUARD: the bed can still expose the defect it pins.

        A test that a phase-aligned cut is phase-aligned proves nothing unless the
        obvious wrong answer is measurably wrong on the same data.  Here the flat
        ``tail(90)`` puts all three windows on one start, which is off-grid for two
        of them — the miniature of 123-of-157.
        """
        closes = bed3b.payload()["closes"]
        panel = pd.read_parquet(bed3b.panel).loc[:AS_OF]

        flat_starts, off_grid, moved = {}, [], []
        for ticker in TICKERS_3B:
            column = panel[ticker].dropna()
            start = str(column.tail(MIN_SESSIONS_3B).index[0].date())
            flat_starts[ticker] = start
            if _phase(column, start):
                off_grid.append(ticker)
            if start != closes[ticker]["dates"][0]:
                moved.append(ticker)

        assert len(set(flat_starts.values())) == 1, (
            "a flat tail collapses every window onto one start — that IS the defect")
        assert len(moved) == 2, moved
        assert len(off_grid) == 2, (
            f"the flat cut must be demonstrably off-grid, else the invariant test "
            f"above cannot fail: {off_grid}")

    def test_an_unchanged_panel_is_still_a_byte_level_no_op(self, bed3b, capsys):
        """Heterogeneous windows must not churn the file on a re-run."""
        before_bytes, before_mtime = bed3b.state()
        assert bed3b.run() == 0
        out = capsys.readouterr().out
        assert "NO-OP" in out
        assert bed3b.state() == (before_bytes, before_mtime)

    def test_an_adjustment_re_pins_without_touching_one_date(self, bed3b, capsys):
        """The remedy still works on a per-ticker era: prices move, calendars do not."""
        before = bed3b.payload()
        frame = bed3b.frame()
        cut = len(frame) - 50
        frame.iloc[:cut] = frame.iloc[:cut] * 0.987
        bed3b.rewrite(frame)

        assert bed3b.run() == 0
        out = capsys.readouterr().out
        after = bed3b.payload()

        assert "REFUSE" not in out
        for ticker in TICKERS_3B:
            assert f"ADJUSTMENT-SIGNATURE {ticker}" in out
            assert after["closes"][ticker]["dates"] == before["closes"][ticker]["dates"]
            assert after["closes"][ticker]["closes"] != before["closes"][ticker]["closes"]
        assert "dates_equal=True" in out
        # the lengths that a flat re-pin would have flattened to one number
        assert sorted(len(v["dates"]) for v in after["closes"].values()) == [90, 91, 92]

    def test_the_era_stamp_survives_a_re_pin(self, bed3b):
        """``assemble`` copies era keys by iteration, so a new stamp is not dropped.

        The version this replaced listed ``_tail_sessions`` by name, so a fixture
        stamped ``_tail_anchor`` would have lost it (and raised on the missing key).
        A re-pin that silently drops the field describing how to cut the file is how
        the next regenerator gets it wrong.
        """
        before = bed3b.payload()
        frame = bed3b.frame()
        frame.iloc[:-50] = frame.iloc[:-50] * 0.987
        bed3b.rewrite(frame)
        assert bed3b.run() == 0

        after = bed3b.payload()
        assert after["_tail_anchor"] == ANCHOR_3B
        assert "_tail_sessions" not in after, "the count was never true; do not mint it"
        assert list(after) == list(before), "top-level key order is part of the contract"

    def test_a_stamp_that_stops_describing_its_file_refuses(self, bed3b, capsys):
        """`_tail_sessions: N` over phase-aligned windows is a FALSE stamp.

        This is #4473's fixture exactly: three window lengths behind one count.  The
        committed starts still win the cut, so nothing is corrupted — but the stamp
        is what cuts any NEWLY qualifying ticker, so a stamp this far from its own
        file must stop the run rather than mint a misaligned window later.
        """
        payload = bed3b.payload()
        swapped = {("_tail_sessions" if k == "_tail_anchor" else k):
                   (MIN_SESSIONS_3B if k == "_tail_anchor" else v)
                   for k, v in payload.items()}
        bed3b.fixture.write_bytes(regen.serialize(swapped))
        before_bytes, before_mtime = bed3b.state()

        assert bed3b.run() == 2
        out = capsys.readouterr().out

        assert bed3b.state() == (before_bytes, before_mtime)
        assert "era window rule no longer derives the frozen start" in out
        # exactly the two the flat count does not fit — not a blanket alarm
        assert out.count("era window rule no longer derives") == 2, out

    def test_a_newly_qualifying_ticker_is_cut_by_the_era_rule(self, bed3b, capsys):
        """An addition has no frozen start, so the RULE cuts it — phase-aligned.

        This is the reason the era rule is stored machine-readably at all.  A ticker
        the panel newly qualifies is still a ticker-set change and still refuses, but
        a ``--force`` through that refusal must not leave one off-grid window behind
        for every future re-pin to preserve faithfully.
        """
        frame = bed3b.frame()
        # four leading NaNs: a column start no existing ticker shares
        values = [12.0 + 0.02 * i + 0.03 * (i % 5) for i in range(SESSIONS)]
        for i in range(4):
            values[i] = float("nan")
        frame["0014.HK"] = values
        bed3b.rewrite(frame)

        assert bed3b.run() == 2
        out = capsys.readouterr().out
        assert "MINTED-WINDOW 1 ticker(s)" in out
        assert "0014.HK" in out
        assert "REFUSE ticker set changed" in out

        assert bed3b.run("--force") == 0
        closes = bed3b.payload()["closes"]
        panel = pd.read_parquet(bed3b.panel).loc[:AS_OF]
        assert _phase(panel["0014.HK"].dropna(), closes["0014.HK"]["dates"][0]) == 0, (
            "a minted window must obey the same law as the ones it joins")
        assert len(closes["0014.HK"]["dates"]) >= MIN_SESSIONS_3B

    def test_an_unknown_rule_is_fatal_not_a_silent_flat_fallback(self, bed3b, capsys):
        """A rule this script cannot cut must stop it, not degrade to ``tail(N)``."""
        payload = bed3b.payload()
        payload["_tail_anchor"] = {"rule": "moon_phase", "min_sessions": 90}
        bed3b.fixture.write_bytes(regen.serialize(payload))
        before_bytes, before_mtime = bed3b.state()

        assert bed3b.run() == 1
        out = capsys.readouterr().out
        assert bed3b.state() == (before_bytes, before_mtime)
        assert "cannot read the era window rule" in out
        assert "moon_phase" in out

    def test_the_legacy_flat_stamp_still_cuts_a_flat_era(self, bed, capsys):
        """Backward compatibility: ``_tail_sessions`` on a genuinely flat era is fine.

        The count is not banned — it is only false when the windows differ.  The
        original bed's three columns share a start, so ``tail(90)`` IS the law there
        and the same code path must leave it a byte-level no-op.
        """
        before_bytes, before_mtime = bed.state()
        assert bed.run() == 0
        assert "NO-OP" in capsys.readouterr().out
        assert bed.state() == (before_bytes, before_mtime)
        assert {len(v["dates"]) for v in bed.payload()["closes"].values()} == {TAIL}


# --------------------------------------------------------------------------- #
# The marker prune's reviewed allowlist (2026-08-13)
# --------------------------------------------------------------------------- #
class TestTheMarkerPruneAllowlist:
    """The widening warning has to be able to stay QUIET, or it announces nothing.

    ``prune_verdict`` drops every marker key outside the era-stamped four and warns
    that it did.  By 2026-08-13 the upstream marker had widened three times — ``reasons``
    (#4583), ``signal_date`` (#5071) and ``confirmed_date`` (#5258) — so the warning
    fired on 157 of 157 markers, i.e. on every marker in the file.  A warning with no
    silent state cannot distinguish a FOURTH key from a Tuesday; it was off in the only
    sense that matters.

    The fix is a reviewed allowlist, and these tests exist to stop it from becoming a
    rubber stamp.  Two properties carry that weight: the allowlist is CLOSED against the
    published marker schema, so a key added upstream reds here instead of being
    swallowed; and the silence is caused BY the allowlist, proven by a seeded mutant that
    removes one entry and gets the warning back.  Without that second test, "no warning"
    would also pass if the warning were simply broken.
    """

    #: A live 2026-08 buy marker: the four stored keys plus every reviewed widening.
    WIDENED = {"date": "2026-07-06", "type": "buy", "quality": "block",
               "reason": "counter-trend, no 200-reclaim/hold",
               "reasons": ["counter-trend, no 200-reclaim/hold", "bearish divergence"],
               "signal_date": "2026-07-08", "confirmed_date": "2026-07-16"}

    def test_the_allowlist_and_the_stored_four_close_the_published_schema(self):
        """stored | allowlisted == every marker property the cross-repo contract declares.

        This is what keeps the allowlist honest: it can only ever be as wide as the
        schema it was reviewed against, and a NEW upstream key has nowhere to hide.
        """
        schema = json.loads(
            (regen.REPO_ROOT / "research" / "signal_engine" / "SCHEMA.json").read_text())
        marker = schema["$defs"]["marker"]
        assert marker.get("additionalProperties") is False, (
            "the closure below is only meaningful while the schema is closed")

        declared = set(marker["properties"])
        stored, allowed = set(regen.MARKER_KEYS), set(regen.MARKER_DROPPED_KEYS)
        assert not stored & allowed, "a key cannot be both stored and dropped"
        assert stored | allowed == declared, (
            f"marker schema drifted from the prune's review: "
            f"unreviewed={sorted(declared - stored - allowed)} "
            f"stale={sorted(stored | allowed - declared)} — adjudicate the key into "
            f"MARKER_DROPPED_KEYS (with its provenance) or widen MARKER_KEYS and re-pin")

    def test_every_allowlisted_key_names_where_it_came_from(self):
        """'Reviewed' means someone recorded the source, not that someone typed the key."""
        for key, note in regen.MARKER_DROPPED_KEYS.items():
            assert isinstance(note, str), key
            assert re.search(r"#\d{3,}|engine/[\w.]+|SCHEMA\.json", note), (
                f"{key}: allowlist entry names no PR or module — an unsourced entry is "
                f"an assertion, not a review")

    def test_a_reviewed_widening_drops_quietly_and_is_disclosed_to_the_caller(self, capsys):
        dropped: dict = {}
        out = regen.prune_verdict("0005.HK", {"last": dict(self.WIDENED)}, dropped)

        assert "WARNING" not in capsys.readouterr().out
        assert out["last"] == {"date": "2026-07-06", "type": "buy", "quality": "block",
                               "reason": "counter-trend, no 200-reclaim/hold"}
        assert dropped == {"confirmed_date": ["0005.HK"], "reasons": ["0005.HK"],
                           "signal_date": ["0005.HK"]}, (
            "a quiet drop must still be a DISCLOSED drop — silence is not the same "
            "as hiding it")

    def test_an_unreviewed_widening_still_warns_per_ticker(self, capsys):
        marker = dict(self.WIDENED, waiver_notch=0.2)
        regen.prune_verdict("0005.HK", {"last": marker}, {})

        printed = capsys.readouterr().out
        assert "WARNING 0005.HK" in printed
        assert "waiver_notch" in printed and "UNREVIEWED" in printed
        for reviewed in ("reasons", "signal_date", "confirmed_date"):
            assert reviewed not in printed, (
                f"{reviewed} is adjudicated and must not ride along in the warning — "
                f"the point is that the named key is the NEW one")

    def test_the_silence_is_caused_by_the_allowlist(self, capsys, monkeypatch):
        """Seeded mutant: pull one entry and its warning comes back.

        Without this, ``test_a_reviewed_widening_drops_quietly`` would pass just as
        happily against a warning that no longer fires at all.
        """
        monkeypatch.setattr(regen, "MARKER_DROPPED_KEYS",
                            {k: v for k, v in regen.MARKER_DROPPED_KEYS.items()
                             if k != "signal_date"})
        regen.prune_verdict("0005.HK", {"last": dict(self.WIDENED)}, {})

        printed = capsys.readouterr().out
        assert "WARNING 0005.HK" in printed and "signal_date" in printed

    def test_the_stored_shape_survives_any_widening(self):
        """Whatever arrives, the fixture stores the four — null-filled, in order."""
        for extra in ({}, {"signal_date": "2026-07-08"}, {"moon_phase": "waxing"}):
            out = regen.prune_verdict(
                "0001.HK", {"last": {"date": "2026-07-06", "type": "sell", **extra}}, {})
            assert list(out["last"]) == list(regen.MARKER_KEYS)
            assert out["last"]["quality"] is None and out["last"]["reason"] is None

    def test_a_missing_marker_is_still_a_null_not_a_dropped_key(self):
        assert regen.prune_verdict("0001.HK", {"last": None}, {})["last"] is None
        assert regen.prune_verdict("0001.HK", {}, {})["last"] is None

    def test_the_drops_are_disclosed_once_through_the_real_loop(self, bed, capsys,
                                                                monkeypatch):
        """End to end: ONE summary line, zero per-ticker warnings.

        The direct pin on the 157-line noise, and on the wiring behind it.  Patched at
        the seam the script itself calls, so the collector is exercised through the real
        ``build_payload`` loop — a regression that stopped THREADING it would leave this
        test silent where an isolated unit test on ``prune_verdict`` would still pass.

        The bed's own monotone panel fires no markers at all, so the marker is
        synthesised; that also moves the verdicts against unchanged closes, so the run
        REFUSES and writes nothing.  Deliberate: the drop must be disclosed even on a
        run whose outcome is a refusal, because that is exactly the run a human reads.
        """
        real_compact = regen.signal_gate.compact

        def widened(verdict):
            out = dict(real_compact(verdict))
            out["last"] = {"date": "2026-07-06", "type": "buy", "quality": "block",
                           "reason": "counter-trend, no 200-reclaim/hold",
                           "reasons": ["counter-trend, no 200-reclaim/hold", "bear div"],
                           "signal_date": "2026-07-08", "confirmed_date": "2026-07-16"}
            return out

        before = bed.state()
        monkeypatch.setattr(regen.signal_gate, "compact", widened)

        assert bed.run() == 2
        out = capsys.readouterr().out

        assert bed.state() == before, "a refusal writes nothing"
        assert "WARNING" not in out
        summary = [line for line in out.splitlines()
                   if line.startswith("marker keys dropped")]
        assert len(summary) == 1, "disclosed once per RUN, never once per ticker"
        for key in ("confirmed_date", "reasons", "signal_date"):
            assert f"{key} x{len(TICKERS)}" in summary[0], (
                f"{key} dropped on every ticker but not counted in the disclosure")
