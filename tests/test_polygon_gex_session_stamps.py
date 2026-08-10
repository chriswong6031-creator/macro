"""polygon_gex stamps the SESSION, not the UTC run date — the 2026-08-06 repair.

THE DEFECT.  ``scripts/build_polygon_gex.accrue`` stamped
``datetime.now(timezone.utc).date()``.  A nightly run landing at 01:24 UTC carries the
PREVIOUS ET session's closing chain, so the entire store sat one session forward of the
market it measures — measured against the independent Cboe-derived sibling
``data/index_gex_history/SPY.parquet``, only 3 of 42 polygon rows matched their own
stamped session while 30 matched the PREVIOUS one.

THE SECOND DEFECT, CAUSED BY THE FIRST.  The write-side ``is_session`` gate then refused
every Saturday/Sunday-UTC run — which is a FRIDAY-EVENING or weekend ET accrual.  Session
2026-07-31 was permanently lost that way: runs fired on both 08-01 and 08-02 and both
were refused *before* ``client.snapshot()``, and polygon open interest is point-in-time
and cannot be backfilled.  07-31 was the first Friday after the gate landed; every later
Friday would have followed.

THE FIX.  ``_resolve_session`` maps an accrual INSTANT through
``nyse_calendar.expected_last_session`` (16:00 ET close + settle buffer) and takes a bare
``date`` at face value as an EXPLICIT session.  A first-writer-wins guard then keeps the
Friday-evening snapshot from being overwritten by Saturday's, Sunday's and Monday's
pre-open re-runs, which all resolve to the same session.

Run: .venv/bin/python -m pytest tests/test_polygon_gex_session_stamps.py -q
"""
from __future__ import annotations

import glob
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.build_polygon_gex as bpg  # noqa: E402
import scripts.complete_polygon_gex_session_stamps as comp  # noqa: E402
import scripts.migrate_polygon_gex_session_stamps as mig  # noqa: E402
import scripts.quarantine_polygon_gex_20260807_preopen as preopen_repair  # noqa: E402
from lib import config, nyse_calendar  # noqa: E402

#: The chains files the two rulings kept: #4807's adjudication of the 42 run-date files
#: that existed when its manifest was frozen, plus PINNED_COMPLETION's re-adjudication of
#: the one that arrived ~4h after (2026-08-07 -> session 2026-08-06).
_ADJUDICATED_KEEPS = sorted(
    [session for session, _cls, disp in mig.PINNED_ADJUDICATION.values()
     if disp == mig.KEEP]
    + [session for session, _cls, disp in comp.PINNED_COMPLETION.values()
       if disp == mig.KEEP])

#: Where the adjudicated window closes. Through this date the store must be EXACTLY the
#: ruled-on survivors; past it the nightly writer adds sessions of its own and the store
#: is expected to grow. Pinning the tail instead of the window is what made these
#: assertions red main the night chains/2026-08-07.parquet landed.
_WINDOW_END = _ADJUDICATED_KEEPS[-1]


# ═══════════════ 1. _resolve_session — instant vs explicit session ══════════════

class TestResolveSession:
    def test_a_bare_date_is_an_explicit_session(self):
        """The --date CLI path and the tests name a session; it is taken at face value."""
        assert bpg._resolve_session(date(2026, 7, 30)) == date(2026, 7, 30)

    def test_an_evening_instant_resolves_to_that_days_session(self):
        # 2026-07-30 18:24 ET (Thursday), i.e. 2026-07-31 01:24 UTC — the real shape of a
        # nightly run. It holds 07-30's close and must be filed under 07-30.
        got = bpg._resolve_session(datetime(2026, 7, 31, 1, 24, tzinfo=timezone.utc))
        assert got == date(2026, 7, 30)

    def test_a_pre_open_instant_resolves_BACK_to_the_prior_session(self):
        """02:24 ET Wednesday carries TUESDAY's close.

        This is the case that rules out ``nyse_calendar.session_date()``, the house
        default for artifact stamps: it calls the whole ET calendar day "the session" so
        the intraday fastpath can stamp the session in progress, and would return
        Wednesday here. Measured on the real store: the file stamped 2026-07-08 (committed
        07-08 06:24Z) carries SPY spot 747.71, exactly the yahoo close of 07-07.
        """
        instant = datetime(2026, 7, 8, 6, 24, tzinfo=timezone.utc)   # 02:24 ET Wed
        assert bpg._resolve_session(instant) == date(2026, 7, 7)
        assert nyse_calendar.session_date(instant) == date(2026, 7, 8)   # the wrong answer

    def test_datetime_is_checked_before_date(self):
        """``datetime`` subclasses ``date``; the wrong isinstance order silently takes
        every accrual instant as an explicit session — i.e. reinstates the defect."""
        instant = datetime(2026, 8, 1, 1, 24, tzinfo=timezone.utc)
        assert bpg._resolve_session(instant) != instant.date()

    def test_none_means_now(self):
        assert bpg._resolve_session(None) == nyse_calendar.expected_last_session()

    def test_a_naive_datetime_is_read_as_utc(self):
        assert (bpg._resolve_session(datetime(2026, 7, 31, 1, 24))
                == bpg._resolve_session(datetime(2026, 7, 31, 1, 24, tzinfo=timezone.utc)))


# ═══════════════ 2. the Friday that used to be refused ══════════════════════════

class _FakeClient:
    """Minimal stand-in: records the asof it was asked for, returns a one-name chain."""

    def __init__(self):
        self.calls: list[date] = []

    def enabled(self):
        return True

    def snapshot(self, symbols, asof):
        self.calls.append(asof)
        exp = pd.Timestamp("2026-09-18")
        rows = [{"underlying": "SPY", "strike_ticker": f"O:SPY260918C{k:08d}",
                 "expiry": exp, "K": float(k), "T": 0.13, "is_call": True,
                 "oi": 1000.0, "iv": 0.20, "gamma": 0.01, "delta": 0.5,
                 "volume": 10.0, "spot": 700.0, "asof": pd.Timestamp(asof)}
                for k in (690, 700, 710)]
        return pd.DataFrame(rows)


@pytest.fixture()
def fake_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    client = _FakeClient()
    monkeypatch.setattr(bpg, "PolygonOptions", lambda: client)
    return tmp_path, client


class TestFridayEveningAccrual:
    """THE REGRESSION TEST FOR THE LOST FRIDAY. Fails on the pre-2026-08-06 code.

    2026-08-01 01:24 UTC is Friday 2026-07-31 21:24 ET — the evening run that holds
    Friday's closing chain. The old ``_as_date`` stamped the UTC date (Saturday 08-01),
    the gate saw a non-session and returned ``non_session`` before the fetch, and Friday
    was never stored at all.
    """

    FRIDAY_EVENING_UTC = datetime(2026, 8, 1, 1, 24, tzinfo=timezone.utc)

    def test_a_utc_saturday_instant_writes_fridays_session(self, fake_store):
        tmp_path, client = fake_store
        res = bpg.accrue(self.FRIDAY_EVENING_UTC)

        assert res["status"] == "ok", (
            f"the Friday-evening accrual was refused ({res}); this is the exact shape "
            "that permanently lost session 2026-07-31")
        assert res["session"] == "2026-07-31"
        assert res["date"] == "2026-07-31", "the `date` key must be the SESSION"
        assert client.calls == [date(2026, 7, 31)], (
            "the fetch must be asked for the session, not the UTC run date")

        written = sorted(p.name for p in
                         (tmp_path / "polygon_gex" / "chains").glob("*.parquet"))
        assert written == ["2026-07-31.parquet"], written
        assert "2026-08-01.parquet" not in written

    def test_the_stored_asof_column_is_the_session_too(self, fake_store):
        tmp_path, _ = fake_store
        bpg.accrue(self.FRIDAY_EVENING_UTC)
        chain = pd.read_parquet(tmp_path / "polygon_gex" / "chains" / "2026-07-31.parquet")
        assert set(pd.unique(chain["asof"])) == {pd.Timestamp("2026-07-31")}
        summ = pd.read_parquet(tmp_path / "polygon_gex" / "summary_SPY.parquet")
        assert [t.date() for t in summ.index] == [date(2026, 7, 31)]

    def test_a_sunday_instant_also_lands_on_friday(self, fake_store):
        """The weekend runs describe Friday too — they must not invent a Saturday row."""
        tmp_path, _ = fake_store
        res = bpg.accrue(datetime(2026, 8, 2, 15, 0, tzinfo=timezone.utc))  # Sun 11:00 ET
        assert res["session"] == "2026-07-31"

    def test_an_explicit_non_session_date_is_still_refused(self, fake_store, capsys):
        """The gate keeps its job on the --date path: a caller naming a closed day is a
        caller error, and the store must stay unadvanced."""
        tmp_path, client = fake_store
        res = bpg.accrue(date(2026, 8, 1))            # a Saturday, named explicitly
        assert res["status"] == "non_session"
        assert not client.calls, "a refused run must not spend API quota"
        assert not (tmp_path / "polygon_gex" / "chains").exists()
        ann = [l for l in capsys.readouterr().out.splitlines() if "::" in l]
        assert ann and all(l.startswith("::") for l in ann), ann
        assert any("polygon-session-gate" in l for l in ann)


# ═══════════════ 3. first writer wins ═══════════════════════════════════════════

class TestFirstWriterWins:
    """Session stamping makes Friday evening, Saturday, Sunday and Monday pre-open all
    resolve to Friday. Without this guard each later run would overwrite Friday's file
    with a staler and eventually PRE-MARKET snapshot — manufacturing exactly the
    mixed-tape rows the 2026-08-06 migration had to quarantine."""

    EVENING = datetime(2026, 8, 1, 1, 24, tzinfo=timezone.utc)     # Fri 21:24 ET
    SUNDAY = datetime(2026, 8, 2, 15, 0, tzinfo=timezone.utc)      # Sun 11:00 ET

    def test_a_second_run_for_the_same_session_is_a_noop(self, fake_store, capsys):
        tmp_path, client = fake_store
        assert bpg.accrue(self.EVENING)["status"] == "ok"
        path = tmp_path / "polygon_gex" / "chains" / "2026-07-31.parquet"
        stamp_before = path.stat().st_mtime_ns

        capsys.readouterr()
        res = bpg.accrue(self.SUNDAY)
        assert res["status"] == "already_present"
        assert res["session"] == "2026-07-31"
        assert path.stat().st_mtime_ns == stamp_before, "the stored file was rewritten"
        assert client.calls == [date(2026, 7, 31)], (
            "the no-op must precede the fetch — a repeat run spends no API quota")

    def test_the_noop_annotates_at_line_start(self, fake_store, capsys):
        bpg.accrue(self.EVENING)
        capsys.readouterr()
        bpg.accrue(self.SUNDAY)
        ann = [l for l in capsys.readouterr().out.splitlines() if "::" in l]
        assert ann and all(l.startswith("::") for l in ann), ann
        assert any("polygon-session-present" in l for l in ann)

    def test_force_overrides(self, fake_store):
        tmp_path, client = fake_store
        bpg.accrue(self.EVENING)
        res = bpg.accrue(self.SUNDAY, force=True)
        assert res["status"] == "ok"
        assert len(client.calls) == 2


# ═══════════════ 4. the migrated store — standing invariants ════════════════════

def _chain_files() -> list[Path]:
    return sorted((config.data_dir() / "polygon_gex" / "chains").glob("*.parquet"))


def _summary_files() -> list[Path]:
    return sorted((config.data_dir() / "polygon_gex").glob("summary_*.parquet"))


class TestTheMigratedStore:
    def test_every_chains_stamp_is_an_nyse_session(self):
        files = _chain_files()
        if not files:
            pytest.skip("polygon_gex chains absent on this runner")
        bad = [p.name for p in files
               if not nyse_calendar.is_session(date.fromisoformat(p.stem))]
        assert not bad, f"non-session chain files: {bad}"

    def test_every_summary_row_is_an_nyse_session(self):
        files = _summary_files()
        if not files:
            pytest.skip("polygon_gex summaries absent on this runner")
        bad, n_rows = [], 0
        for p in files:
            idx = pd.read_parquet(p).index
            n_rows += len(idx)
            bad += [(p.name, str(pd.Timestamp(t).date())) for t in idx
                    if not nyse_calendar.is_session(pd.Timestamp(t).date())]
        assert not bad, f"non-session summary rows ({len(bad)} of {n_rows}): {bad[:10]}"
        assert n_rows, "no summary rows were checked"

    def test_each_chains_asof_column_matches_its_filename(self):
        """The stamp lives in two places; a migration that moved only the filename would
        leave every reader of the `asof` column on the old date."""
        files = _chain_files()
        if not files:
            pytest.skip("polygon_gex chains absent on this runner")
        bad = []
        for p in files:
            vals = pd.unique(pd.read_parquet(p, columns=["asof"])["asof"])
            if len(vals) != 1 or pd.Timestamp(vals[0]).strftime("%Y-%m-%d") != p.stem:
                bad.append((p.name, [str(v) for v in vals[:3]]))
        assert not bad, f"asof column disagrees with the filename: {bad}"

    def test_the_store_spans_the_adjudicated_window(self):
        """24 CLEAN survivors 2026-06-15..2026-07-30, plus the one session re-adjudicated
        afterwards by ``complete_polygon_gex_session_stamps`` (2026-08-06).

        Session 2026-08-05 is deliberately ABSENT: its only coverage was the 08-06 file,
        accrued 09:57Z = 05:57 ET pre-open during the emergency morning run, whose spot
        column is a live pre-market tape (median error 0.14%, 59% of names disagreeing
        with 08-05's closes). Quarantined — an honest gap beats a fabricated row.

        Session 2026-08-06 IS present, and the distinction matters: the run-date STAMP
        "2026-08-06" is gone (that was the quarantined pre-market file), while the SESSION
        08-06 is carried by the 08-07-stamped accrual, which landed 2026-08-07T04:06:20Z =
        00:06 ET — after the 08-06 close — and matches that close exactly to the cent for
        every one of its 283 checkable underlyings. The #4807 manifest was frozen ~4h
        before that file existed, so it is a completion of the adjudication under its own
        CLEAN rule, not an exception to it.
        """
        files = _chain_files()
        if not files:
            pytest.skip("polygon_gex chains absent on this runner")
        stems = [p.stem for p in files]
        assert stems[0] == "2026-06-15", stems[:3]
        assert "2026-08-05" not in stems, (
            "session 08-05 is quarantined — its only snapshot was a pre-market tape")
        # Every stamp in the store is a SESSION. This is the invariant both migrations
        # exist to hold; a weekend or holiday stem means run-date stamping is back.
        assert not [s for s in stems
                    if not nyse_calendar.is_session(date.fromisoformat(s))], stems
        # Inside the adjudicated window the store is EXACTLY what was ruled on — no
        # dropped or quarantined run-date stamp may come back. Past it the nightly is
        # free to add sessions, so the window is bounded rather than the store frozen.
        # (`assert stems[-1] == ...` used to pin the tail; the nightly commits a chains
        # file most evenings, so that form red-ed main the night 2026-08-07 landed.)
        assert stems[-1] >= _WINDOW_END, (
            f"the store ends at {stems[-1]}, before the adjudicated window closes at "
            f"{_WINDOW_END} — sessions have gone missing")
        inside = [s for s in stems if s <= _WINDOW_END]
        assert inside == _ADJUDICATED_KEEPS, (
            f"inside the adjudicated window the store must be exactly the ruled-on "
            f"survivors; {sorted(set(inside) ^ set(_ADJUDICATED_KEEPS))} is not")


class TestTheAdjudicationOutcomes:
    """The 2026-08-06 collision ruling, pinned. These are the ADJUDICATION, not an
    implementation detail: 42 run-date files collapsed onto 29 sessions, and each
    collision was resolved by preferring CLEAN, then lowest median error against that
    session's closes, then the widest underlying count, then the earliest stamp."""

    # session -> (stamps that resolved to it, the winning stamp)
    COLLISIONS = {
        "2026-06-15": (["2026-06-15", "2026-06-16"], "2026-06-15"),
        "2026-06-17": (["2026-06-17", "2026-06-18"], "2026-06-17"),
        # 2026-06-19 is Juneteenth, so 06-19/06-20/06-21 all carry 06-18's close;
        # 06-21 wins on breadth (345 underlyings vs 10).
        "2026-06-18": (["2026-06-19", "2026-06-20", "2026-06-21", "2026-06-22"],
                       "2026-06-21"),
        "2026-06-24": (["2026-06-24", "2026-06-25"], "2026-06-24"),
        "2026-06-26": (["2026-06-27", "2026-06-28", "2026-06-29"], "2026-06-27"),
        "2026-07-10": (["2026-07-12", "2026-07-13"], "2026-07-12"),
        "2026-07-17": (["2026-07-18", "2026-07-19", "2026-07-20"], "2026-07-18"),
        "2026-07-24": (["2026-07-25", "2026-07-26", "2026-07-27"], "2026-07-25"),
    }
    QUARANTINED = {"2026-06-23": "2026-06-22", "2026-06-26": "2026-06-25",
                   "2026-06-30": "2026-06-29", "2026-07-07": "2026-07-06",
                   "2026-08-06": "2026-08-05"}

    def test_the_pinned_table_totals(self):
        pin = mig.PINNED_ADJUDICATION
        assert len(pin) == 42
        assert len({s for s, _c, _d in pin.values()}) == 29
        assert sum(1 for _s, c, _d in pin.values() if c == "CLEAN") == 33
        assert sum(1 for _s, c, _d in pin.values() if c == "MIXED") == 9
        assert sum(1 for _s, _c, d in pin.values() if d == mig.KEEP) == 24
        assert sum(1 for _s, _c, d in pin.values() if d == mig.DROP) == 13
        assert sum(1 for _s, _c, d in pin.values() if d == mig.QUARANTINE) == 5

    @pytest.mark.parametrize("session", sorted(COLLISIONS))
    def test_each_collision_resolved_to_the_named_winner(self, session):
        stamps, winner = self.COLLISIONS[session]
        pin = mig.PINNED_ADJUDICATION
        got = sorted(s for s, (sess, _c, _d) in pin.items() if sess == session)
        assert got == sorted(stamps), f"session {session} collision group moved"
        assert pin[winner][2] == mig.KEEP, f"{winner} must be the kept file"
        for loser in set(stamps) - {winner}:
            assert pin[loser][2] == mig.DROP, f"{loser} must be dropped"

    @pytest.mark.parametrize("stamp,session", sorted(QUARANTINED.items()))
    def test_the_mixed_survivors_are_quarantined(self, stamp, session):
        """A MIXED survivor's spot column is a live intraday/pre-market tape, so every
        spot-derived GEX field was computed off a price that is not the session's close.
        The session becomes an honest gap rather than a fabricated row."""
        sess, cls, disp = mig.PINNED_ADJUDICATION[stamp]
        assert (sess, cls, disp) == (session, "MIXED", mig.QUARANTINE)
        assert not (config.data_dir() / "polygon_gex"
                    / "chains" / f"{session}.parquet").exists()

    def test_the_classification_thresholds_are_the_adjudicated_ones(self):
        assert mig.MEDIAN_ERR_PCT_MAX == 0.05
        assert mig.WITHIN_RATE_MIN_PCT == 90.0
        assert mig.WITHIN_TOL_PCT == 0.5


# ═══════════════ 5. the migration script itself ═════════════════════════════════

class TestTheMigrationIsIdempotent:
    def test_a_migrated_store_is_detected_as_already_done(self):
        if not _chain_files():
            pytest.skip("polygon_gex chains absent on this runner")
        assert mig.already_migrated(), (
            "the migrated store must be recognised as done, or a re-run would try to "
            "re-derive accrual instants from a history this migration already rewrote")

    def test_a_second_apply_writes_nothing(self, monkeypatch, capsys):
        """Re-runnable by contract: --apply on a migrated store is a clean no-op.

        Driven through ``main()`` IN-PROCESS rather than by shelling out. A subprocess
        would exercise the same code path but deadlocks intermittently on macOS in
        pyarrow's atexit ``ThreadPool::Shutdown`` — the script finishes its work and then
        hangs at interpreter teardown, which in CI is an unkillable job rather than a
        failure. Observed here at ~10 minutes on an otherwise 1-second run.
        """
        if not _chain_files():
            pytest.skip("polygon_gex chains absent on this runner")
        before = {p: p.stat().st_mtime_ns for p in _chain_files() + _summary_files()}
        monkeypatch.setattr(
            sys, "argv", ["migrate_polygon_gex_session_stamps", "--apply"])
        assert mig.main() == 0
        assert "already session-stamped" in capsys.readouterr().out
        after = {p: p.stat().st_mtime_ns for p in _chain_files() + _summary_files()}
        assert after == before, "a re-run touched files"

    def test_a_non_session_stamp_makes_it_run_again(self, tmp_path, monkeypatch):
        """The idempotence check must key on the DATA, never on a marker file — a marker
        would let a regressed writer's run-date file sit unnoticed."""
        chains = tmp_path / "polygon_gex" / "chains"
        chains.mkdir(parents=True)
        pd.DataFrame({"x": [1]}).to_parquet(chains / "2026-08-01.parquet")  # a Saturday
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        assert not mig.already_migrated()


class TestTheMigrationVerifiesBeforeItWrites:
    def _record(self, **kw):
        base = dict(original_stamp="2026-07-31", original_path="x.parquet",
                    accrual_instant_utc="2026-07-31T01:24:00+00:00",
                    accrual_instant_et="2026-07-30T21:24:00-04:00",
                    resolved_session="2026-07-30", classification="CLEAN",
                    metrics={"underlyings": 370, "checkable": 286,
                             "unverifiable": 84, "median_abs_err_pct": 0.0,
                             "within_0_5pct_rate": 99.0,
                             "exact_to_the_cent_rate": 97.2,
                             "worst_abs_err_pct": 1.0},
                    disposition=mig.KEEP, new_path="y.parquet")
        base.update(kw)
        return mig.Record(**base)

    def test_a_kept_file_that_fails_the_cross_section_blocks_the_write(self):
        bad = self._record(metrics={**self._record().metrics,
                                    "median_abs_err_pct": 1.5,
                                    "within_0_5pct_rate": 20.0})
        problems = mig.verify_plan([bad])
        assert any("median error" in p for p in problems), problems
        assert any("within-0.5% rate" in p for p in problems), problems

    def test_a_kept_file_with_nothing_verifiable_blocks_the_write(self):
        m = {**self._record().metrics, "checkable": 0, "median_abs_err_pct": None,
             "within_0_5pct_rate": None}
        assert any("zero verifiable underlyings" in p
                   for p in mig.verify_plan([self._record(metrics=m)]))

    def test_a_plan_that_disagrees_with_the_adjudication_blocks_the_write(self):
        drifted = self._record(resolved_session="2026-07-29")
        problems = mig.verify_plan([drifted])
        assert any("!= pinned" in p for p in problems), problems

    def test_an_unruled_chains_file_blocks_the_write(self):
        problems = mig.verify_plan([self._record(original_stamp="2026-09-09")])
        assert any("never ruled on" in p for p in problems), problems

    def test_a_forward_resolving_file_blocks_the_write(self):
        """The rename pass is only collision-free while every session <= its stamp."""
        fwd = self._record(original_stamp="2026-06-15", resolved_session="2026-06-24")
        assert any("resolves FORWARD" in p for p in mig.verify_plan([fwd]))


class TestTheManifestIsCommittedProvenance:
    """The git-derived accrual instants are UNRECOVERABLE once the migration commit
    rewrites the history of those paths, so the manifest is load-bearing, not decorative.
    It is also the only pointer back to the 18 removed blobs."""

    @pytest.fixture(scope="class")
    def manifest(self):
        if not mig.MANIFEST_PATH.exists():
            pytest.skip("manifest absent on this runner")
        import json
        return json.loads(mig.MANIFEST_PATH.read_text())

    def test_it_records_every_one_of_the_42_files(self, manifest):
        assert len(manifest["files"]) == 42
        assert {f["original_stamp"] for f in manifest["files"]} == set(
            mig.PINNED_ADJUDICATION)

    @pytest.mark.parametrize("field", [
        "original_stamp", "original_path", "accrual_instant_utc", "resolved_session",
        "classification", "metrics", "disposition", "reason", "recovery_sha"])
    def test_every_row_carries_the_required_field(self, manifest, field):
        missing = [f["original_stamp"] for f in manifest["files"] if not f.get(field)]
        assert not missing, f"{field} missing for {missing}"

    def test_the_accrual_instants_are_real_utc_timestamps(self, manifest):
        for f in manifest["files"]:
            got = datetime.fromisoformat(f["accrual_instant_utc"])
            assert got.tzinfo is not None
            # the instant must resolve to the session the file was filed under
            assert nyse_calendar.expected_last_session(got) == date.fromisoformat(
                f["resolved_session"]), f["original_stamp"]

    def test_the_removed_blobs_are_still_reachable_in_git(self, manifest):
        """Nothing was destroyed. Every removed file resolves at its recovery SHA.

        ``rev-parse`` resolves the path through the commit's TREE to a blob OID; it never
        needs the blob's CONTENT, so this stays a local, instant check under CI's
        ``filter: blob:none`` partial clone (``cat-file -e`` would trigger a lazy fetch of
        a ~4 MB blob per file).
        """
        if subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip() == "true":
            pytest.skip("shallow clone — history is not present to check against")
        removed = [f for f in manifest["files"]
                   if f["disposition"] in (mig.DROP, mig.QUARANTINE)]
        assert len(removed) == 18, len(removed)
        broken = []
        for row in removed:
            out = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet",
                 f"{row['recovery_sha']}:{row['original_path']}"],
                cwd=ROOT, capture_output=True, text=True, check=False)
            if out.returncode != 0:
                broken.append((row["original_stamp"], row["recovery_sha"]))
        assert not broken, (
            f"the manifest's recovery pointers are broken for {broken} — the removed "
            "blobs are the ONLY copy of those snapshots")

    def test_the_08_06_ruling_is_recorded_in_words(self, manifest):
        row = next(f for f in manifest["files"] if f["original_stamp"] == "2026-08-06")
        assert row["resolved_session"] == "2026-08-05"
        assert row["classification"] == "MIXED"
        assert row["disposition"] == mig.QUARANTINE
        assert row["accrual_instant_utc"].startswith("2026-08-06T09:57")
        assert "pre-market" in row["reason"]
        assert row["metrics"]["within_0_5pct_rate"] < 70.0


# ═══════════════ 6. the independent second verifier ═════════════════════════════

def test_the_migrated_spots_match_the_cboe_sibling_on_the_SAME_session():
    """``data/index_gex_history/SPY.parquet`` is the Cboe-derived GEX history — a fully
    independent pipeline that never had this defect (1 non-session stamp since 2016).

    Measured 2026-08-06 on the committed store: BEFORE the migration only 3 of 42 polygon
    rows matched their own stamped session's Cboe spot while 30 matched the PREVIOUS
    session — the off-by-one, seen without yahoo. After, every overlapping row matches on
    its own date.
    """
    poly = config.data_dir() / "polygon_gex" / "summary_SPY.parquet"
    cboe = config.data_dir() / "index_gex_history" / "SPY.parquet"
    if not (poly.exists() and cboe.exists()):
        pytest.skip("SPY GEX stores absent on this runner")
    p, c = pd.read_parquet(poly), pd.read_parquet(cboe)
    shared = [t for t in p.index if t in c.index]
    if len(shared) < 5:
        pytest.skip("too little overlap to be a meaningful check")
    mismatched = [(str(t.date()), round(float(p.loc[t, "spot"]), 2),
                   round(float(c.loc[t, "spot"]), 2)) for t in shared
                  if abs(float(p.loc[t, "spot"]) - float(c.loc[t, "spot"])) > 0.02]
    assert not mismatched, (
        f"{len(mismatched)} of {len(shared)} polygon rows disagree with the Cboe "
        f"sibling on their OWN session: {mismatched[:5]} — the store is shifted again")


def test_post_migration_spy_spots_match_the_committed_session_close():
    """Catch a bad session stamp on the same nightly it lands, without waiting for the
    weekly ``index_gex_history`` sibling to advance.

    The stale 2026-08-07 workflow row was only 0.38% away from SPY's eventual close, so
    a broad percentage tolerance would have hidden it.  Polygon's stock snapshot and the
    committed Yahoo daily bar both carry the official close to the cent after settlement;
    post-migration rows must therefore agree to the same two-cent float-storage tolerance
    used by the independent-sibling check above.
    """
    poly_path = config.data_dir() / "polygon_gex" / "summary_SPY.parquet"
    yahoo_path = config.data_dir() / "yahoo" / "SPY.parquet"
    if not (poly_path.exists() and yahoo_path.exists()):
        pytest.skip("SPY Polygon/Yahoo stores absent on this runner")
    poly, yahoo = pd.read_parquet(poly_path), pd.read_parquet(yahoo_path)
    close_col = "close" if "close" in yahoo.columns else "close_price"
    start = pd.Timestamp(_WINDOW_END)
    shared = [t for t in poly.index if t >= start and t in yahoo.index]
    assert shared, f"no SPY session-close row at/after the migration window {start.date()}"
    mismatched = [
        (str(t.date()), round(float(poly.loc[t, "spot"]), 3),
         round(float(yahoo.loc[t, close_col]), 3))
        for t in shared
        if abs(float(poly.loc[t, "spot"]) - float(yahoo.loc[t, close_col])) > 0.02
    ]
    assert not mismatched, (
        "post-migration Polygon SPY spots do not match their committed session close: "
        f"{mismatched}; this is the stale-runner/pre-open stamp shape")


def test_the_2026_08_07_preopen_snapshot_is_quarantined_with_recovery_provenance():
    """The bad row is removed, not edited to agree with another provider.

    Run 31138544929 checked out the old UTC-date writer before #4807, slept in the
    queue, captured a pre-open 08-07 chain, then rebased its data commit onto fixed main.
    The raw bytes remain recoverable from that commit; the source store carries an honest
    gap rather than a fabricated close.
    """
    import json

    manifest_path = preopen_repair.MANIFEST
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["root_cause"]["workflow_run"] == 31138544929
    assert manifest["root_cause"]["checkout_head"] == preopen_repair.SOURCE_HEAD
    assert manifest["adjudication"]["classification_against_claimed_session"] == "MIXED"
    assert manifest["adjudication"]["metrics_against_claimed_session"][
        "median_abs_err_pct"] > 1.0
    assert manifest["adjudication"]["disposition"] == "quarantine"
    assert manifest["changes"]["summary_rows_removed"] == 372

    assert not (ROOT / preopen_repair.CHAIN_REL).exists()
    survivors = []
    for path in _summary_files():
        if pd.Timestamp(preopen_repair.TARGET) in pd.read_parquet(path).index:
            survivors.append(path.name)
    assert not survivors, f"pre-open {preopen_repair.TARGET} rows remain: {survivors[:10]}"

    if subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT,
                      capture_output=True, text=True).stdout.strip() != "true":
        blob = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet",
             f"{preopen_repair.RECOVERY_COMMIT}:{preopen_repair.CHAIN_REL}"],
            cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        assert blob == preopen_repair.CHAIN_GIT_BLOB

    assert preopen_repair.build_plan()["already_applied"] is True


def test_the_committed_chains_files_are_the_ones_the_adjudications_kept():
    """The store is exactly the union of the two pinned rulings — nothing absorbed silently.

    #4807 adjudicated the 42 run-date files that existed when its manifest was frozen and
    refuses to widen itself past them ("re-adjudicate before migrating — do NOT widen this
    script to absorb them"). ``complete_polygon_gex_session_stamps.PINNED_COMPLETION`` is
    that re-adjudication for the one file that arrived afterwards, measured under the same
    CLEAN rule. A chains file belonging to neither ruling is an un-adjudicated snapshot.
    """
    files = sorted(p.stem for p in _chain_files())
    if not files:
        pytest.skip("polygon_gex chains absent on this runner")
    inside = [s for s in files if s <= _WINDOW_END]
    assert inside == _ADJUDICATED_KEEPS, (
        f"inside the adjudicated window (through {_WINDOW_END}) the store holds "
        f"{len(inside)} chains files; the two rulings kept {len(_ADJUDICATED_KEEPS)} — "
        f"{sorted(set(inside) ^ set(_ADJUDICATED_KEEPS))} is ruled on by neither")
    # Anything past the window is the fixed writer's own output. It is not adjudicated,
    # but it still has to be a session — that is the property the migrations restored.
    after = [s for s in files if s > _WINDOW_END]
    assert not [s for s in after if not nyse_calendar.is_session(date.fromisoformat(s))], (
        f"post-window chains files that are not NYSE sessions: {after} — the writer "
        "regressed to UTC run-date stamping")


def test_no_stray_files_shadow_the_chains_glob():
    """Every reader globs ``chains/*.parquet``. A leftover staging directory or a stray
    file there would enter the store as a snapshot."""
    d = config.data_dir() / "polygon_gex" / "chains"
    if not d.exists():
        pytest.skip("polygon_gex chains absent on this runner")
    strays = [p.name for p in d.iterdir()
              if not (p.is_file() and p.suffix == ".parquet"
                      and mig._stamp_of(p) is not None)]
    assert not strays, f"unexpected entries under chains/: {strays}"
    root = config.data_dir() / "polygon_gex"
    strays = [p.name for p in root.iterdir()
              if not (p.name == "chains"
                      or (p.is_file() and p.name.startswith("summary_")
                          and p.suffix == ".parquet"))]
    assert not strays, f"unexpected entries under polygon_gex/: {strays}"


def test_the_migration_is_registered_in_ci():
    """A test file that no pack enumerates is dark. Fails if this file is ever dropped
    from ci.yml's pack lists."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "tests/test_polygon_gex_session_stamps.py" in ci, (
        "register this file in a ci.yml pack — an unenumerated suite never runs")
    assert glob.glob(str(ROOT / "scripts" / "migrate_polygon_gex_session_stamps.py"))
