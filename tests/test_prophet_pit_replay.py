"""Tests for scripts/prophet_pit_replay.py — the general point-in-time Prophet session
replay harness (research/PROPHET_PIT_REPLAY_HARNESS_V1.md).

Fast, no network, no real board builds: synthetic frames and tmp git fixtures only.
Covers the primitives the build commission's TESTS section names:
  * truncate/overlay/fence on synthetic frames
  * vintage resolution: --first-parent monotonicity + slot boundary
  * disclosed-gap guard refusal (fixture copy of the real gap shape)
  * registry validation: cn/hk/ca/intl refuse naming unresolved fields; unknown
    market string rejected by argparse
  * collision cutoff boundary
  * receipt idempotence refusal

The real-repo `--resolve-only` integration checks (US 2026-08-14 resolves; CN
2026-08-17 refuses naming unresolved fields; US 2026-08-04 refuses citing the
disclosed gap) are exercised directly by the build commission's EVIDENCE commands,
not duplicated here as slow subprocess tests.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import scripts.prophet_pit_replay as ppr  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _frame(dates: list[str], closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"close": closes, "high": closes, "low": closes,
                         "volume": [1_000] * len(closes)},
                        index=pd.to_datetime(dates))


_GIT_ENV = {
    "GIT_AUTHOR_NAME": "pit-replay-test", "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "pit-replay-test", "GIT_COMMITTER_EMAIL": "test@example.com",
}


def _git(repo: Path, *args: str, env: dict | None = None) -> str:
    merged_env = dict(os.environ)
    merged_env.update(_GIT_ENV)
    if env:
        merged_env.update(env)
    result = subprocess.run(["git", *args], cwd=repo, check=True,
                            capture_output=True, env=merged_env)
    return result.stdout.decode("utf-8").strip()


def _init_repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    return repo


def _commit(repo: Path, message: str, *, date_iso: str) -> str:
    _git(repo, "commit", "--allow-empty", "-m", message,
        env={"GIT_AUTHOR_DATE": date_iso, "GIT_COMMITTER_DATE": date_iso})
    return _git(repo, "rev-parse", "HEAD")


def _set_origin_main(repo: Path, ref: str = "main") -> None:
    _git(repo, "update-ref", "refs/remotes/origin/main", ref)


# ---------------------------------------------------------------------------
# R1 — truncate / overlay / fence primitives
# ---------------------------------------------------------------------------

class TestTruncateFrame:
    def test_drops_every_bar_after_the_ceiling(self):
        frame = _frame(["2026-08-10", "2026-08-11", "2026-08-12"], [10.0, 11.0, 99.0])
        kept = ppr.truncate_frame(frame, "2026-08-11")
        assert list(kept.index.strftime("%Y-%m-%d")) == ["2026-08-10", "2026-08-11"]
        assert kept["close"].max() == 11.0

    def test_keeps_a_bar_exactly_on_the_ceiling(self):
        frame = _frame(["2026-08-10", "2026-08-11"], [10.0, 11.0])
        assert len(ppr.truncate_frame(frame, "2026-08-11")) == 2

    def test_date_in_a_column_frame_is_truncated_correctly(self):
        """A RangeIndex frame with dates in a column (prophet_bridge's shape) must
        resolve via the column, never be misread as epoch-nanosecond dates."""
        frame = pd.DataFrame({
            "date": ["2026-08-10", "2026-08-11", "2026-08-12"],
            "close": [10.0, 11.0, 99.0],
        })
        kept = ppr.truncate_frame(frame, "2026-08-11")
        assert kept["close"].max() == 11.0

    def test_a_rangeindex_frame_with_no_date_column_is_returned_untouched(self):
        """The refusal-to-misread-1970 case: no date column, no parseable index."""
        frame = pd.DataFrame({"close": [10.0, 11.0, 99.0]})
        out = ppr.truncate_frame(frame, "2026-08-11")
        assert len(out) == 3  # untouched, not silently emptied or corrupted

    def test_tz_aware_index_is_handled(self):
        frame = _frame(["2026-08-10", "2026-08-11", "2026-08-12"], [10.0, 11.0, 99.0])
        frame.index = frame.index.tz_localize("UTC")
        kept = ppr.truncate_frame(frame, "2026-08-11")
        assert list(kept.index.strftime("%Y-%m-%d")) == ["2026-08-10", "2026-08-11"]

    def test_none_passes_through(self):
        assert ppr.truncate_frame(None, "2026-08-11") is None


class TestOverlaySessions:
    def test_appends_only_the_missing_tail(self):
        vintage = _frame(["2026-08-07", "2026-08-10"], [10.0, 10.5])
        live = _frame(["2026-08-07", "2026-08-10", "2026-08-11", "2026-08-12"],
                      [10.0, 10.5, 11.0, 110.0])
        merged, provenance = ppr.overlay_sessions(vintage, live, "2026-08-11")
        assert provenance["added"] == ["2026-08-11"]
        assert list(merged.index.strftime("%Y-%m-%d")) == [
            "2026-08-07", "2026-08-10", "2026-08-11"]
        assert 110.0 not in set(merged["close"])

    def test_keeps_vintage_bytes_for_restated_history(self):
        vintage = _frame(["2026-08-10"], [10.5])
        live = _frame(["2026-08-10", "2026-08-11"], [10.9, 11.0])
        merged, _ = ppr.overlay_sessions(vintage, live, "2026-08-11")
        assert merged.loc[pd.Timestamp("2026-08-10"), "close"] == 10.5
        assert merged.loc[pd.Timestamp("2026-08-11"), "close"] == 11.0

    def test_column_alignment_to_the_vintage_frame(self):
        vintage = pd.DataFrame({"close": [10.5]}, index=pd.to_datetime(["2026-08-10"]))
        live = pd.DataFrame({"close": [10.9, 11.0], "extra_col": [1, 2]},
                            index=pd.to_datetime(["2026-08-10", "2026-08-11"]))
        merged, provenance = ppr.overlay_sessions(vintage, live, "2026-08-11")
        assert list(merged.columns) == ["close"]  # extra_col dropped, not widened
        assert provenance["dropped_columns"] == ["extra_col"]

    def test_wholesale_substitution_branch_when_no_vintage_history(self):
        live = _frame(["2026-08-10", "2026-08-11", "2026-08-12"], [10.0, 11.0, 99.0])
        merged, provenance = ppr.overlay_sessions(None, live, "2026-08-11")
        assert provenance["substituted"] is True
        assert list(merged.index.strftime("%Y-%m-%d")) == ["2026-08-10", "2026-08-11"]

    def test_empty_vintage_frame_also_takes_the_substitution_branch(self):
        vintage = _frame([], [])
        live = _frame(["2026-08-10", "2026-08-11"], [10.0, 11.0])
        merged, provenance = ppr.overlay_sessions(vintage, live, "2026-08-11")
        assert provenance["substituted"] is True
        assert len(merged) == 2

    def test_no_live_source_keeps_vintage_only(self):
        vintage = _frame(["2026-08-10"], [10.5])
        merged, provenance = ppr.overlay_sessions(vintage, None, "2026-08-11")
        assert provenance["added_sessions"] == 0
        assert len(merged) == 1


class TestNeedsWrite:
    def test_added_sessions_forces_a_write(self):
        assert ppr._needs_write(object(), object(), {"added_sessions": 1}) is True

    def test_absent_on_disk_forces_a_write(self):
        assert ppr._needs_write(object(), None, {"added_sessions": 0}) is True

    def test_truncation_without_append_still_needs_a_write(self):
        """The Russell-panel case: nothing appended, but the on-disk frame extends
        past the pass ceiling and must be rewritten shorter."""
        on_disk = _frame(["2026-08-10", "2026-08-11"], [10.0, 11.0])
        live = _frame(["2026-08-10", "2026-08-11"], [10.0, 11.0])
        merged, provenance = ppr.overlay_sessions(on_disk, live, "2026-08-10")
        assert provenance["added_sessions"] == 0
        assert len(merged) == 1
        assert ppr._needs_write(merged, on_disk, provenance) is True

    def test_unchanged_frame_does_not_need_a_write(self):
        frame = _frame(["2026-08-10", "2026-08-11"], [10.0, 11.0])
        provenance = {"added_sessions": 0}
        assert ppr._needs_write(frame, frame, provenance) is False


_SURFACE = ppr.PriceSurface(
    ticker_stores=(("data/stocks", "*.parquet"),),
    wide_panels=("data/breadth/_closes_cache.parquet",),
)


class TestFenceNoBarAfter:
    def test_fires_on_a_planted_bar(self, tmp_path):
        store = tmp_path / "data" / "stocks"
        store.mkdir(parents=True)
        _frame(["2026-08-11", "2026-08-12"], [11.0, 12.0]).to_parquet(store / "AAA.parquet")
        with pytest.raises(ppr.PitReplayRefused, match="carry bars AFTER"):
            ppr.fence_no_bar_after(tmp_path, "2026-08-11", _SURFACE)

    def test_passes_a_clean_tree_and_reports_what_it_scanned(self, tmp_path):
        store = tmp_path / "data" / "stocks"
        store.mkdir(parents=True)
        _frame(["2026-08-10", "2026-08-11"], [10.0, 11.0]).to_parquet(store / "AAA.parquet")
        report = ppr.fence_no_bar_after(tmp_path, "2026-08-11", _SURFACE)
        assert report["violations"] == 0
        assert report["files_scanned"] == 1
        assert report["max_date_found"] == "2026-08-11"

    def test_is_not_vacuous_when_nothing_is_there(self, tmp_path):
        assert ppr.fence_no_bar_after(tmp_path, "2026-08-11", _SURFACE)["files_scanned"] == 0

    def test_ahead_of_pass_is_reported_not_refused(self, tmp_path):
        """F5: exercised via the PRIMITIVE directly (a genuinely different callable
        contract than prepare_reconstruction_tree's — see
        TestPrepareReconstructionTreePassThrough below for the PRODUCTION call path,
        which is what actually caught the 'pass_through wired shut' bug: every real
        caller used to pass pass_through==ceiling, so this primitive-level test alone
        could not have caught it)."""
        store = tmp_path / "data" / "stocks"
        store.mkdir(parents=True)
        _frame(["2026-08-10", "2026-08-11"], [1.0, 1.1]).to_parquet(store / "EURUSD_X.parquet")
        report = ppr.fence_no_bar_after(tmp_path, "2026-08-11", _SURFACE, pass_through="2026-08-10")
        assert report["violations"] == 0
        assert report["ahead_of_pass_count"] == 1
        assert report["ahead_of_pass"][0]["max_date"] == "2026-08-11"

    def test_unscannable_file_is_named_not_silently_clean(self, tmp_path):
        store = tmp_path / "data" / "stocks"
        store.mkdir(parents=True)
        # An index that is neither datetime nor a recognisable date column.
        pd.DataFrame({"close": [1.0, 2.0]}).to_parquet(store / "WEIRD.parquet")
        report = ppr.fence_no_bar_after(tmp_path, "2026-08-11", _SURFACE)
        assert report["unscannable_count"] == 1
        assert "data/stocks/WEIRD.parquet" in report["unscannable"]


class TestPrepareReconstructionTreePassThrough:
    """F5 SHIP-BLOCKER fix, tested via the PRODUCTION call path: before this fix,
    ``prepare_reconstruction_tree`` called ``fence_no_bar_after(vintage, through,
    surface, pass_through=through)`` — hard ceiling == soft ceiling on every real
    caller, wiring the ``ahead_of_pass`` distinction shut. A control pass
    (``through=control_through``, an EARLIER date than the true reconstruction
    session) would misreport the vintage's own legitimate round-the-clock bars
    between ``control_through`` and ``session`` as VIOLATIONS instead of the softer
    ``ahead_of_pass``. ``session_ceiling`` (always the harness's own ``session``, on
    BOTH passes) is now the fence's hard ceiling; ``through`` (this pass's own
    ceiling) is the soft ``pass_through``."""

    def test_control_pass_reports_ahead_of_pass_not_a_violation(self, tmp_path):
        repo = _init_repo(tmp_path, "repo")
        vintage_sha = _commit(repo, "seed", date_iso="2026-08-14T00:00:00+00:00")
        store = tmp_path / "vintage" / "data" / "stocks"
        store.mkdir(parents=True)
        # A round-the-clock instrument bar dated AFTER the control pass's own
        # ceiling (2026-08-10) but still within (i.e. AT) the true reconstruction
        # session (2026-08-11) — legitimate vintage-native content, not lookahead.
        _frame(["2026-08-10", "2026-08-11"], [1.0, 1.1]).to_parquet(store / "EURUSD_X.parquet")

        manifest = ppr.prepare_reconstruction_tree(
            tmp_path / "vintage", repo, through="2026-08-10", live_ref="main",
            vintage_commit=vintage_sha, surface=_SURFACE, session_ceiling="2026-08-11",
        )
        assert manifest["fence"]["violations"] == 0, (
            "a vintage-native bar within the TRUE session must not refuse the "
            "control pass"
        )
        assert manifest["fence"]["ahead_of_pass_count"] == 1
        assert manifest["fence"]["ahead_of_pass"][0]["max_date"] == "2026-08-11"

    def test_a_bar_past_the_true_session_still_refuses(self, tmp_path):
        repo = _init_repo(tmp_path, "repo")
        vintage_sha = _commit(repo, "seed", date_iso="2026-08-14T00:00:00+00:00")
        store = tmp_path / "vintage" / "data" / "stocks"
        store.mkdir(parents=True)
        # This bar is past the TRUE reconstruction session (2026-08-11), not merely
        # past the control pass's own ceiling — a genuine lookahead violation on
        # BOTH the control pass (checked here) and the replay pass.
        _frame(["2026-08-10", "2026-08-12"], [1.0, 1.2]).to_parquet(store / "EURUSD_X.parquet")

        with pytest.raises(ppr.PitReplayRefused, match="carry bars AFTER"):
            ppr.prepare_reconstruction_tree(
                tmp_path / "vintage", repo, through="2026-08-10", live_ref="main",
                vintage_commit=vintage_sha, surface=_SURFACE, session_ceiling="2026-08-11",
            )

    def test_replay_pass_hard_and_soft_ceiling_are_equal_so_behavior_is_unchanged(
        self, tmp_path
    ):
        """On the replay pass through==session, so session_ceiling defaults to
        through when the caller omits it (or is passed explicitly equal) — the
        control-pass-only relaxation must not loosen anything here."""
        repo = _init_repo(tmp_path, "repo")
        vintage_sha = _commit(repo, "seed", date_iso="2026-08-14T00:00:00+00:00")
        store = tmp_path / "vintage" / "data" / "stocks"
        store.mkdir(parents=True)
        _frame(["2026-08-10", "2026-08-12"], [1.0, 1.2]).to_parquet(store / "AAA.parquet")

        with pytest.raises(ppr.PitReplayRefused, match="carry bars AFTER"):
            ppr.prepare_reconstruction_tree(
                tmp_path / "vintage", repo, through="2026-08-11", live_ref="main",
                vintage_commit=vintage_sha, surface=_SURFACE, session_ceiling="2026-08-11",
            )


# ---------------------------------------------------------------------------
# R4 — vintage resolution
# ---------------------------------------------------------------------------

class TestValidateSession:
    """2026-08-18 orchestrator amendment (GAP 4 in the original build's return): a
    malformed --session must refuse cleanly via PitReplayRefused, never surface a raw
    ValueError/TypeError from deep inside _us_bake_slot or a git command."""

    @pytest.mark.parametrize("bad", [
        "not-a-date", "2026/08/14", "26-08-14", "2026-8-14", "",
        "2026-08-14T00:00:00", "20260814",
    ])
    def test_wrong_shape_refuses_cleanly(self, bad):
        with pytest.raises(ppr.PitReplayRefused, match="not YYYY-MM-DD"):
            ppr.validate_session(bad)

    @pytest.mark.parametrize("bad", ["2026-13-01", "2026-02-30", "2026-00-14", "2026-08-32"])
    def test_out_of_range_calendar_date_refuses_cleanly(self, bad):
        with pytest.raises(ppr.PitReplayRefused, match="not a valid calendar date"):
            ppr.validate_session(bad)

    def test_well_formed_session_passes_through_unchanged(self):
        assert ppr.validate_session("2026-08-14") == "2026-08-14"

    def test_resolve_vintage_refuses_a_malformed_session_cleanly(self, tmp_path):
        """resolve_vintage() validates at the source too (defense in depth) — a
        malformed session must never reach date.fromisoformat inside _us_bake_slot as
        a raw, uncaught exception."""
        repo = _init_repo(tmp_path)
        _commit(repo, "init", date_iso="2026-08-14T10:00:00+00:00")
        _set_origin_main(repo)
        with pytest.raises(ppr.PitReplayRefused, match="not a valid calendar date"):
            ppr.resolve_vintage(repo, ppr.MARKETS["us"], "2026-13-40")

    def test_cli_resolve_only_refuses_a_malformed_session_cleanly(self):
        """End-to-end: the CLI must print a clean ::error and exit nonzero, never a
        Python traceback, for a malformed --session."""
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.prophet_pit_replay",
             "--market", "us", "--session", "2026-13-40", "--resolve-only"],
            cwd=_REPO, capture_output=True, text=True,
        )
        assert proc.returncode == 2
        assert "::error title=prophet-pit-replay-refused::" in proc.stdout
        assert "Traceback" not in proc.stderr


class TestResolveVintage:
    def test_first_parent_is_load_bearing(self, tmp_path):
        """A merge lands AFTER the slot but carries an interior commit timestamped
        BEFORE it. The resolver must pick the pre-slot MAINLINE commit, not the
        interior branch commit that only became reachable from main after the merge —
        proving --first-parent is doing real work, not decoration."""
        repo = _init_repo(tmp_path)
        a = _commit(repo, "A", date_iso="2026-08-14T10:00:00+00:00")
        _git(repo, "checkout", "-q", "-b", "feature")
        b = _commit(repo, "B interior", date_iso="2026-08-14T20:00:00+00:00")
        _git(repo, "checkout", "-q", "main")
        _git(repo, "merge", "--no-ff", "feature", "-m", "merge",
            env={"GIT_AUTHOR_DATE": "2026-08-15T00:00:00+00:00",
                "GIT_COMMITTER_DATE": "2026-08-15T00:00:00+00:00"})
        _set_origin_main(repo)

        result = ppr.resolve_vintage(repo, ppr.MARKETS["us"], "2026-08-14")
        assert result["sha"] == a, (
            "expected the pre-slot mainline commit A, not the interior branch commit"
        )
        assert result["sha"] != b

        # Negative control: WITHOUT --first-parent, the naive rev-list picks the wrong
        # (interior) commit — proving the bug this discipline exists to prevent is
        # real, not hypothetical.
        naive = _git(repo, "rev-list", "-1", "--before=2026-08-14T22:30:00Z", "origin/main")
        assert naive == b

    def test_slot_boundary_is_inclusive(self, tmp_path):
        repo = _init_repo(tmp_path)
        c = _commit(repo, "C at slot", date_iso="2026-08-14T22:30:00+00:00")
        _set_origin_main(repo)
        result = ppr.resolve_vintage(repo, ppr.MARKETS["us"], "2026-08-14")
        assert result["sha"] == c
        assert result["slot_utc"] == "2026-08-14T22:30:00Z"

    def test_a_commit_one_second_after_the_slot_is_excluded(self, tmp_path):
        repo = _init_repo(tmp_path)
        _commit(repo, "D after slot", date_iso="2026-08-14T22:30:01+00:00")
        _set_origin_main(repo)
        with pytest.raises(ppr.PitReplayRefused, match="no origin/main commit found"):
            ppr.resolve_vintage(repo, ppr.MARKETS["us"], "2026-08-14")

    def test_bake_slot_override_is_honoured(self, tmp_path):
        repo = _init_repo(tmp_path)
        e = _commit(repo, "E", date_iso="2026-08-14T05:00:00+00:00")
        _set_origin_main(repo)
        result = ppr.resolve_vintage(repo, ppr.MARKETS["us"], "2026-08-14",
                                     bake_slot_override="2026-08-14T06:00:00Z")
        assert result["sha"] == e
        assert result["slot_utc"] == "2026-08-14T06:00:00Z"

    def test_us_bake_slot_is_1830_eastern_in_august(self):
        slot = ppr._us_bake_slot("2026-08-14")
        assert slot.strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-08-14T22:30:00Z"

    def test_us_bake_slot_is_1830_eastern_in_january_est(self):
        """F5: the reviewer noted the EST (winter, UTC-5) bake-slot pin was
        uncovered — every prior test exercised August (EDT, UTC-4) only. 18:30 EST
        is 23:30Z, one hour later than the EDT case above."""
        slot = ppr._us_bake_slot("2026-01-15")
        assert slot.strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-01-15T23:30:00Z"


class TestAssertAncestorOfMain:
    def test_a_commit_not_on_main_is_refused(self, tmp_path):
        repo = _init_repo(tmp_path)
        _commit(repo, "A", date_iso="2026-08-14T10:00:00+00:00")
        _git(repo, "checkout", "-q", "-b", "side")
        side = _commit(repo, "side-only", date_iso="2026-08-14T11:00:00+00:00")
        _git(repo, "checkout", "-q", "main")
        _set_origin_main(repo)
        with pytest.raises(ppr.PitReplayRefused, match="NOT an ancestor"):
            ppr.assert_ancestor_of_main(repo, side, label="test")

    def test_an_ancestor_of_main_passes(self, tmp_path):
        repo = _init_repo(tmp_path)
        a = _commit(repo, "A", date_iso="2026-08-14T10:00:00+00:00")
        _set_origin_main(repo)
        assert ppr.assert_ancestor_of_main(repo, a, label="test") == "ancestor_of_origin_main"


# ---------------------------------------------------------------------------
# disclosed-gap guard
# ---------------------------------------------------------------------------

_GAP_FIXTURE = {
    "schema_version": "1.0.0",
    "gaps": [
        {
            "id": "us-board-frozen-alpha-2026-08",
            "market": "US",
            "window": {"from": "2026-08-01", "to": "2026-08-06"},
            "missing_trading_days": ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"],
            "gradeable": False,
            "backfillable": False,
            "headline": "The board published every day but ranked on factors frozen at 2026-07-31.",
        }
    ],
}


class TestDisclosedGapGuard:
    def test_a_session_inside_the_window_refuses_citing_the_gap_id(self, tmp_path):
        gaps_path = tmp_path / "data" / "us_board_ledger" / "disclosed_gaps.json"
        gaps_path.parent.mkdir(parents=True)
        gaps_path.write_text(json.dumps(_GAP_FIXTURE), encoding="utf-8")
        entry = {"gaps_file": "data/us_board_ledger/disclosed_gaps.json"}
        with pytest.raises(ppr.PitReplayRefused, match="us-board-frozen-alpha-2026-08"):
            ppr.check_disclosed_gaps(tmp_path, entry, "2026-08-04")

    def test_a_session_via_missing_trading_days_also_refuses(self, tmp_path):
        gaps_path = tmp_path / "data" / "us_board_ledger" / "disclosed_gaps.json"
        gaps_path.parent.mkdir(parents=True)
        doc = json.loads(json.dumps(_GAP_FIXTURE))
        doc["gaps"][0]["window"] = {"from": "", "to": ""}
        gaps_path.write_text(json.dumps(doc), encoding="utf-8")
        entry = {"gaps_file": "data/us_board_ledger/disclosed_gaps.json"}
        with pytest.raises(ppr.PitReplayRefused, match="us-board-frozen-alpha-2026-08"):
            ppr.check_disclosed_gaps(tmp_path, entry, "2026-08-05")

    def test_a_session_outside_the_window_passes(self, tmp_path):
        gaps_path = tmp_path / "data" / "us_board_ledger" / "disclosed_gaps.json"
        gaps_path.parent.mkdir(parents=True)
        gaps_path.write_text(json.dumps(_GAP_FIXTURE), encoding="utf-8")
        entry = {"gaps_file": "data/us_board_ledger/disclosed_gaps.json"}
        ppr.check_disclosed_gaps(tmp_path, entry, "2026-08-14")  # must not raise

    def test_a_backfillable_gap_does_not_refuse(self, tmp_path):
        gaps_path = tmp_path / "data" / "us_board_ledger" / "disclosed_gaps.json"
        gaps_path.parent.mkdir(parents=True)
        doc = json.loads(json.dumps(_GAP_FIXTURE))
        doc["gaps"][0]["backfillable"] = True
        gaps_path.write_text(json.dumps(doc), encoding="utf-8")
        entry = {"gaps_file": "data/us_board_ledger/disclosed_gaps.json"}
        ppr.check_disclosed_gaps(tmp_path, entry, "2026-08-04")  # must not raise

    def test_absent_gaps_file_is_not_an_error(self, tmp_path):
        entry = {"gaps_file": "data/us_board_ledger/disclosed_gaps.json"}
        ppr.check_disclosed_gaps(tmp_path, entry, "2026-08-04")  # must not raise

    def test_market_with_no_gaps_file_declared_always_passes(self, tmp_path):
        ppr.check_disclosed_gaps(tmp_path, {}, "2026-08-04")  # must not raise

    def test_against_the_real_repo_us_2026_08_04_refuses(self):
        """Sanity check against the ACTUAL committed disclosed_gaps.json, not just the
        fixture copy — confirms the fixture above still matches production shape."""
        entry = ppr.MARKETS["us"]
        with pytest.raises(ppr.PitReplayRefused, match="us-board-frozen-alpha-2026-08"):
            ppr.check_disclosed_gaps(_REPO, entry, "2026-08-04")

    def test_against_the_real_repo_us_2026_08_14_passes(self):
        entry = ppr.MARKETS["us"]
        ppr.check_disclosed_gaps(_REPO, entry, "2026-08-14")  # must not raise


# ---------------------------------------------------------------------------
# registry validation
# ---------------------------------------------------------------------------

class TestRegistry:
    # cn/hk RESOLVED (research/PROPHET_PIT_REPLAY_HARNESS_V1.md §1 completion,
    # tests/test_pit_replay_absorb_asia.py::TestRegistryResolution covers their
    # resolved shape) — only ca/intl remain DECLARED-UNRESOLVED. Adjusted per the
    # build commission's explicit carve-out; no other expectation in this file
    # changed.
    @pytest.mark.parametrize("market", ["ca", "intl"])
    def test_unresolved_markets_refuse_naming_missing_fields(self, market):
        with pytest.raises(ppr.PitReplayRefused, match="DECLARED-UNRESOLVED") as exc_info:
            ppr.get_market_entry(market)
        message = str(exc_info.value)
        for field_name in ppr.MARKETS[market]["unresolved"]:
            assert field_name in message

    def test_us_is_fully_resolved(self):
        entry = ppr.get_market_entry("us")
        assert "unresolved" not in entry
        assert entry["board_relpath"] == "site/factordata/us_standouts.json"
        assert isinstance(entry["price_surface"], ppr.PriceSurface)

    def test_unknown_market_string_is_rejected_by_argparse(self):
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.prophet_pit_replay",
             "--market", "not-a-market", "--session", "2026-08-14", "--resolve-only"],
            cwd=_REPO, capture_output=True, text=True,
        )
        assert proc.returncode != 0
        assert "invalid choice" in proc.stderr

    def test_all_registry_markets_are_argparse_choices(self):
        assert set(ppr.MARKETS.keys()) == {"us", "cn", "hk", "ca", "intl"}


# ---------------------------------------------------------------------------
# US collision cutoff boundary
# ---------------------------------------------------------------------------

class TestCollisionCutoff:
    def test_cutoff_is_session_plus_one_day(self):
        assert ppr.collision_cutoff("2026-08-14") == "2026-08-15"

    def test_a_plan_recorded_exactly_on_the_cutoff_wins(self):
        plans = {"AAA-BULL-20260810": {"asset": "AAA", "direction": "BULL",
                                       "recorded_at": "2026-08-15"}}
        by_key = ppr.live_plans_since(plans, ppr.collision_cutoff("2026-08-14"))
        assert "AAA-BULL" in by_key

    def test_a_plan_recorded_the_day_before_the_cutoff_does_not_win(self):
        plans = {"AAA-BULL-20260810": {"asset": "AAA", "direction": "BULL",
                                       "recorded_at": "2026-08-14"}}
        by_key = ppr.live_plans_since(plans, ppr.collision_cutoff("2026-08-14"))
        assert "AAA-BULL" not in by_key

    def test_keyed_on_ticker_and_direction_not_ticker_alone(self):
        plans = {
            "AAA-BEAR-20260810": {"asset": "AAA", "direction": "BEAR",
                                  "recorded_at": "2026-08-15"},
        }
        by_key = ppr.live_plans_since(plans, ppr.collision_cutoff("2026-08-14"))
        assert "AAA-BULL" not in by_key
        assert "AAA-BEAR" in by_key

    def test_a_prior_pit_replay_plan_is_treated_as_live_once_merged(self):
        """The DEC mandates unmarked rows, so unlike the ancestors this harness does
        NOT special-case its own earlier output by an origination_mode field — a plan
        this harness minted on an earlier run is, once merged, indistinguishable from
        a live plan and correctly wins a collision like any other."""
        plans = {"AAA-BULL-20260810": {"asset": "AAA", "direction": "BULL",
                                       "recorded_at": "2026-08-15"}}
        by_key = ppr.live_plans_since(plans, ppr.collision_cutoff("2026-08-14"))
        assert "AAA-BULL" in by_key


# ---------------------------------------------------------------------------
# receipt idempotence
# ---------------------------------------------------------------------------

class TestReceiptIdempotence:
    def test_no_existing_receipt_passes(self, tmp_path):
        repo = _init_repo(tmp_path)
        _commit(repo, "init", date_iso="2026-08-01T00:00:00+00:00")
        _set_origin_main(repo)
        ppr.check_receipt_idempotence(repo, "us", "2026-08-14")  # must not raise

    def test_a_receipt_in_the_working_tree_refuses(self, tmp_path):
        repo = _init_repo(tmp_path)
        _commit(repo, "init", date_iso="2026-08-01T00:00:00+00:00")
        _set_origin_main(repo)
        receipts = repo / "data" / "pit_replay"
        receipts.mkdir(parents=True)
        (receipts / "us-2026-08-14-deadbeef.json").write_text("{}", encoding="utf-8")
        with pytest.raises(ppr.PitReplayRefused, match="already exists in the working tree"):
            ppr.check_receipt_idempotence(repo, "us", "2026-08-14")

    def test_a_receipt_committed_on_origin_main_refuses(self, tmp_path):
        repo = _init_repo(tmp_path)
        _commit(repo, "init", date_iso="2026-08-01T00:00:00+00:00")
        receipts = repo / "data" / "pit_replay"
        receipts.mkdir(parents=True)
        (receipts / "us-2026-08-14-deadbeef.json").write_text("{}", encoding="utf-8")
        _git(repo, "add", "data/pit_replay/us-2026-08-14-deadbeef.json")
        _commit(repo, "add receipt", date_iso="2026-08-15T00:00:00+00:00")
        _set_origin_main(repo)
        # Remove the working-tree copy so only the COMMITTED history carries it —
        # proves the check reads history, not merely the working tree.
        (receipts / "us-2026-08-14-deadbeef.json").unlink()
        with pytest.raises(ppr.PitReplayRefused, match="already exists on origin/main"):
            ppr.check_receipt_idempotence(repo, "us", "2026-08-14")

    def test_a_receipt_for_a_different_session_does_not_collide(self, tmp_path):
        repo = _init_repo(tmp_path)
        _commit(repo, "init", date_iso="2026-08-01T00:00:00+00:00")
        _set_origin_main(repo)
        receipts = repo / "data" / "pit_replay"
        receipts.mkdir(parents=True)
        (receipts / "us-2026-08-15-deadbeef.json").write_text("{}", encoding="utf-8")
        ppr.check_receipt_idempotence(repo, "us", "2026-08-14")  # must not raise

    def test_a_receipt_for_a_different_market_does_not_collide(self, tmp_path):
        repo = _init_repo(tmp_path)
        _commit(repo, "init", date_iso="2026-08-01T00:00:00+00:00")
        _set_origin_main(repo)
        receipts = repo / "data" / "pit_replay"
        receipts.mkdir(parents=True)
        (receipts / "cn-2026-08-14-deadbeef.json").write_text("{}", encoding="utf-8")
        ppr.check_receipt_idempotence(repo, "us", "2026-08-14")  # must not raise


# ---------------------------------------------------------------------------
# receipt shape satisfies the real chronology auditor (directive 10)
# ---------------------------------------------------------------------------

class TestOriginationReceiptSatisfiesTheRealAuditor:
    """SHAPE IS LOAD-BEARING (see scripts/audit_prophet_plan_chronology.py's
    _validate_receipt_shape): a receipt that merely looks like the nightly's would
    take every plan created in that commit out of audit with it. Pinned here exactly
    as the 08-11 ancestor pins it for its own receipt shape."""

    def _receipt(self) -> dict:
        board = {
            "as_of": "2026-08-14", "rank_by": "us_prophet_v2", "gate_go": True,
            "staleness": {"price_through": "2026-08-14", "basis": "panel_majority",
                          "delayed": False, "unknown": False},
            "buy": [{"ticker": "AAA", "price": 10.0}],
        }
        plan = {"schema": "prophet.trade_plan/v1", "id": "AAA-BULL-20260810",
               "asset": "AAA", "direction": "BULL", "formation_date": "2026-08-10",
               "recorded_at": "2026-08-14"}
        return ppr._build_origination_receipt(
            receipt_id="replay-2026-08-14-deadbeefdeadbeef", board=board,
            board_blob=json.dumps(board).encode("utf-8"), baseline_sha="a" * 40,
            minted=[plan], intake={"admitted": 1}, executed_at="2026-08-15T00:00:00+00:00",
            market="us", session="2026-08-14", vintage_sha="b" * 40,
            overlay={"live_price_source_commit": "c" * 40, "fence": {"violations": 0},
                    "files": {}},
            alpha={"as_of": "2026-08-14"}, fidelity={"measured": True},
            executing_commit="d" * 40,
        )

    def test_no_origination_mode_or_disclosure_field_anywhere(self):
        """The DEC mandates unmarked rows — the harness's own provenance lives ONLY
        under the non-schema 'pit_replay' key, never mixed into the schema fields an
        auditor or a live consumer reads."""
        receipt = self._receipt()
        assert "origination_mode" not in receipt
        assert "origination_mode" not in json.dumps(receipt["originations"])

    def test_the_real_auditor_accepts_the_receipt(self):
        from scripts.audit_prophet_plan_chronology import _validate_receipt_shape

        source, by_id = _validate_receipt_shape(
            self._receipt(),
            receipt_path=(f"{ppr.RECEIPTS_RELDIR}/"
                         "replay-2026-08-14-deadbeefdeadbeef.json"))
        assert source["price_through"] == "2026-08-14"
        assert "AAA-BULL-20260810" in by_id

    def test_the_receipt_carries_its_price_basis_explicitly(self):
        receipt = self._receipt()
        assert receipt["source"]["price_through"] == "2026-08-14"
        assert receipt["source"]["source_asof"] == receipt["source"]["price_through"]

    def test_the_receipt_says_it_is_a_backfill_lane_run(self):
        receipt = self._receipt()
        assert receipt["run"]["is_backfill"] is True
        assert receipt["run"]["actor"].endswith("prophet_pit_replay.py")


# ---------------------------------------------------------------------------
# reconciliation / partition helpers (pure, no I/O)
# ---------------------------------------------------------------------------

class TestReconciliation:
    def test_identities_hold_on_a_balanced_funnel(self):
        counts = {"admitted": 5, "duplicate_id_blocked": 1, "reorigination_blocked_rows": 1,
                 "eligible_after_skips": 3, "reorigination_blocked": 0, "minted": 2,
                 "collided": 1, "chronology_refused": 0, "still_refused": 0}
        rec = ppr.check_reconciliation(counts)
        assert rec["admission_identity"]["holds"] is True
        assert rec["disposition_identity"]["holds"] is True

    def test_identity_break_is_reported_not_hidden(self):
        counts = {"admitted": 5, "duplicate_id_blocked": 0, "reorigination_blocked_rows": 0,
                 "eligible_after_skips": 3}  # deliberately short of 5
        rec = ppr.check_reconciliation(counts)
        assert rec["admission_identity"]["holds"] is False


class TestPartitionChronology:
    def test_splits_chronology_from_other_refusals(self):
        refusals = [
            {"ticker": "AAA", "reason": "engine_refusal:clock_provenance"},
            {"ticker": "BBB", "reason": "engine_refusal:panel_mixed_vintage"},
        ]
        chrono, other = ppr.partition_chronology(refusals)
        assert [r["ticker"] for r in chrono] == ["AAA"]
        assert [r["ticker"] for r in other] == ["BBB"]


class TestAlreadyPublishedIds:
    def test_enumerated_names_when_counts_reconcile(self):
        ids, note = ppr.already_published_ids(
            {"on_main": ["AAA-BULL-20260810"], "intra_board": []}, expected=1)
        assert ids == ["AAA-BULL-20260810"]
        assert "already published" in note

    def test_withholds_names_on_a_count_mismatch(self):
        ids, note = ppr.already_published_ids(
            {"on_main": ["AAA-BULL-20260810"], "intra_board": []}, expected=5)
        assert ids == []
        assert "not enumerated" in note


# ---------------------------------------------------------------------------
# session_valid — wired into the shared early path (2026-08-18 amendment)
# ---------------------------------------------------------------------------

class TestSessionValidGuard:
    """check_session_valid() calls the registry entry's own session_valid(session)
    hook — previously registered on every market entry but never CALLED anywhere in
    the shared flow, so a non-trading-day --session used to sail through the gap
    guard and vintage resolution and only fail LATE, after a full board build,
    inside the reconstructed board's own stamp check."""

    def test_a_weekend_session_refuses_for_us(self):
        # 2026-08-16 is a Sunday.
        with pytest.raises(ppr.PitReplayRefused,
                           match=r"2026-08-16 is not a US trading session \(NYSE calendar\)"):
            ppr.check_session_valid(ppr.MARKETS["us"], "2026-08-16", "us")

    @pytest.mark.parametrize("market", ["cn", "hk"])
    def test_a_weekend_session_refuses_for_cn_and_hk(self, market):
        entry = ppr.get_market_entry(market)  # raises if still DECLARED-UNRESOLVED
        with pytest.raises(ppr.PitReplayRefused, match=r"2026-08-16 is not a"):
            ppr.check_session_valid(entry, "2026-08-16", market)

    def test_a_real_trading_session_passes_for_us(self):
        ppr.check_session_valid(ppr.MARKETS["us"], "2026-08-14", "us")  # must not raise

    @pytest.mark.parametrize("market,session", [("cn", "2026-08-17"), ("hk", "2026-08-17")])
    def test_a_real_trading_session_passes_for_cn_and_hk(self, market, session):
        entry = ppr.get_market_entry(market)
        ppr.check_session_valid(entry, session, market)  # must not raise

    def test_an_entry_with_no_session_valid_hook_is_not_gated(self):
        """A registry entry that legitimately carries no session_valid hook is a
        registry-completeness question for get_market_entry, not this function's —
        it must pass through rather than raise (there is nothing to call)."""
        ppr.check_session_valid({}, "2026-08-16", "us")  # must not raise

    def test_resolve_only_prints_the_session_valid_line(self, tmp_path, capsys):
        repo = _init_repo(tmp_path)
        _commit(repo, "init", date_iso="2026-08-14T10:00:00+00:00")
        _set_origin_main(repo)
        rc = ppr._cmd_resolve_only(repo, "us", "2026-08-14", None)
        out = capsys.readouterr().out
        assert rc == 0
        assert "session-valid: OK" in out

    def test_resolve_only_refuses_a_weekend_session_naming_the_calendar(self, tmp_path, capsys):
        repo = _init_repo(tmp_path)
        _commit(repo, "init", date_iso="2026-08-14T10:00:00+00:00")
        _set_origin_main(repo)
        rc = ppr._cmd_resolve_only(repo, "us", "2026-08-16", None)
        out = capsys.readouterr().out
        assert rc == 2
        assert "is not a US trading session (NYSE calendar)" in out
        assert "session-valid: OK" not in out  # never printed on a refusal

    def test_the_check_runs_before_vintage_resolution(self, tmp_path, capsys):
        """A weekend session must refuse citing the calendar WITHOUT ever needing to
        resolve a vintage commit — the whole point of moving the check early. Proven
        against a directory that is not a git repository at all: if resolve_vintage
        ran first (or ran at all), it would fail with a git-command error instead of
        the session-valid message; check_session_valid must win the race."""
        not_a_repo = tmp_path / "not_a_repo"
        not_a_repo.mkdir()
        rc = ppr._cmd_resolve_only(not_a_repo, "us", "2026-08-16", None)
        out = capsys.readouterr().out
        assert rc == 2
        assert "is not a US trading session (NYSE calendar)" in out
        assert "git" not in out.lower()  # no git-command error leaked through


# ---------------------------------------------------------------------------
# --work-dir is user-supplied and must never be assumed to exist
# ---------------------------------------------------------------------------

class TestWorkDirAutoCreated:
    """A nonexistent --work-dir used to crash with an uncaught FileNotFoundError
    (build_alpha's runner.write_text() into a directory nothing had created yet).
    build_alpha and build_board now mkdir(parents=True, exist_ok=True) defensively,
    and main() creates --work-dir once up front."""

    def test_build_alpha_does_not_crash_on_a_nonexistent_work_dir(self, tmp_path):
        vintage = tmp_path / "not_a_real_vintage"
        vintage.mkdir()
        work = tmp_path / "work" / "nested" / "does_not_exist_yet"
        assert not work.exists()
        # The fake vintage tree has no lib/scripts modules, so the runner subprocess
        # itself fails — but it must fail as a CLEAN PitReplayRefused, never a raw
        # FileNotFoundError from write_text() into a missing directory.
        with pytest.raises(ppr.PitReplayRefused):
            ppr.build_alpha(vintage, through="2026-08-14", work=work)
        assert work.exists(), "the mkdir must happen even though the build itself fails"

    def test_build_board_does_not_crash_on_a_nonexistent_work_dir(self, tmp_path):
        vintage = tmp_path / "not_a_real_vintage"
        vintage.mkdir()
        work = tmp_path / "work2" / "nested" / "does_not_exist_yet"
        assert not work.exists()
        with pytest.raises(ppr.PitReplayRefused, match="board builder exited"):
            ppr.build_board(
                vintage, through="2026-08-14", work=work,
                build_cmd=(sys.executable, "-c", "import sys; sys.exit(1)"),
                board_relpath="site/factordata/us_standouts.json",
            )
        assert work.exists()

    def test_build_alpha_reuses_an_existing_work_dir_without_error(self, tmp_path):
        """mkdir(exist_ok=True) must not raise on a work dir that already exists —
        the ordinary case, now that main() also creates it up front."""
        vintage = tmp_path / "not_a_real_vintage"
        vintage.mkdir()
        work = tmp_path / "already_here"
        work.mkdir()
        with pytest.raises(ppr.PitReplayRefused):
            ppr.build_alpha(vintage, through="2026-08-14", work=work)  # must not raise OSError


class TestBuildBoardCacheCoherence:
    """Coordinator amendment (found by a warm-cache dry-run re-run): a build_board
    CACHE HIT must leave the vintage tree's own board_relpath bytes equal to the
    cached board. Before this fix, a cache hit returned the cached ``work/`` path
    without ever writing back to the tree — but ``reset_builder_state`` (called
    earlier in the SAME pass) had already restored the tree's board to the
    vintage's own committed (stale) bytes, so an in-process reader of the tree's
    OWN board path (``capture_us_snapshot_row``'s ``snapshot_today()``, which reads
    ``BOARD_PATH`` off the vintage tree rather than off the returned path) could
    read the wrong as_of and refuse — exactly the failure a warm-cache re-run of
    the same session hit. A real (non-cached) build does not have this problem: its
    very last step reads the board FROM the tree (``out.write_bytes(board_path.
    read_bytes())``), so the tree is already correct by construction; the cache-hit
    branch needed the mirror-image write."""

    def test_cache_hit_writes_the_cached_board_back_to_the_vintage_tree(self, tmp_path):
        vintage = tmp_path / "vintage"
        (vintage / "site" / "factordata").mkdir(parents=True)
        stale_board = json.dumps({"as_of": "2026-08-13", "rank_by": "stale"})
        (vintage / "site" / "factordata" / "us_standouts.json").write_text(stale_board)

        work = tmp_path / "work"
        work.mkdir()
        cached_board = json.dumps({"as_of": "2026-08-14", "rank_by": "fresh"})
        fingerprint = "deadbeef"
        (work / f"board_2026-08-14_{fingerprint}.json").write_text(cached_board)

        out = ppr.build_board(
            vintage, through="2026-08-14", work=work,
            # A cache hit must short-circuit BEFORE this subprocess ever runs — a
            # command that always fails is the proof it was never invoked.
            build_cmd=(sys.executable, "-c", "import sys; sys.exit(1)"),
            board_relpath="site/factordata/us_standouts.json",
            fingerprint=fingerprint,
        )
        assert out.read_text() == cached_board
        tree_board = (vintage / "site" / "factordata" / "us_standouts.json").read_text()
        assert tree_board == cached_board, (
            "a cache hit must leave the tree's own board path equal to the cached "
            f"board, not the stale pre-reset bytes — got {tree_board!r}"
        )

    def test_cache_hit_creates_the_board_relpath_parent_if_missing(self, tmp_path):
        """The vintage tree may not even have the board's parent directory yet
        (a throwaway worktree that never ran a real build before this cache hit) —
        the write-back must mkdir(parents=True), not crash."""
        vintage = tmp_path / "vintage"
        vintage.mkdir()
        work = tmp_path / "work"
        work.mkdir()
        cached_board = json.dumps({"as_of": "2026-08-14", "rank_by": "fresh"})
        fingerprint = "cafef00d"
        (work / f"board_2026-08-14_{fingerprint}.json").write_text(cached_board)

        ppr.build_board(
            vintage, through="2026-08-14", work=work,
            build_cmd=(sys.executable, "-c", "import sys; sys.exit(1)"),
            board_relpath="site/factordata/us_standouts.json",
            fingerprint=fingerprint,
        )
        assert (vintage / "site" / "factordata" / "us_standouts.json").read_text() \
            == cached_board


# ---------------------------------------------------------------------------
# F1 SHIP-BLOCKER — --verify-collisions must reach the collision logic even when
# the run's OWN harness receipt already exists (the exact shape --execute leaves
# behind, immediately before the documented "run it before merge" invocation).
# ---------------------------------------------------------------------------

class TestVerifyCollisionsAheadOfIdempotence:
    def test_execute_shaped_fixture_reaches_collision_logic_not_idempotence_refusal(
        self, tmp_path
    ):
        repo = _init_repo(tmp_path)
        _commit(repo, "init", date_iso="2026-08-01T00:00:00+00:00")
        _set_origin_main(repo)
        _git(repo, "remote", "add", "origin", str(repo))

        session = "2026-08-14"
        plan_id = "AAA-BULL-20260810"

        # execute-shaped: the harness's OWN receipt already sits in data/pit_replay/
        # — before the F1 fix this alone made check_receipt_idempotence refuse
        # BEFORE --verify-collisions ever reached the collision logic.
        pit_dir = repo / "data" / "pit_replay"
        pit_dir.mkdir(parents=True)
        (pit_dir / f"us-{session}-deadbeef.json").write_text("{}", encoding="utf-8")

        # the origination receipt --verify-collisions reads to learn the minted ids
        receipts_dir = repo / ppr.RECEIPTS_RELDIR
        receipts_dir.mkdir(parents=True)
        (receipts_dir / f"replay-{session}-deadbeef.json").write_text(
            json.dumps({"originated_plan_ids": [plan_id]}), encoding="utf-8")

        # the minted plan file --verify-collisions reads for its ticker+direction
        plans_dir = repo / ppr.PLANS_RELDIR
        plans_dir.mkdir(parents=True)
        (plans_dir / f"{plan_id}.json").write_text(
            json.dumps({"id": plan_id, "asset": "AAA", "direction": "BULL"}),
            encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, "-m", "scripts.prophet_pit_replay",
             "--market", "us", "--session", session, "--verify-collisions",
             "--repo", str(repo)],
            cwd=_REPO, capture_output=True, text=True,
        )
        assert "already exists in the working tree" not in proc.stdout, (
            "idempotence must not gate --verify-collisions — got:\n" + proc.stdout
            + proc.stderr
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "no new collisions" in proc.stdout


# ---------------------------------------------------------------------------
# F2a/F12 — every vintage subprocess's environment
# ---------------------------------------------------------------------------

class TestVintageEnv:
    def test_dead_proxy_keys_present(self):
        env = ppr._vintage_env({})
        assert env["HTTP_PROXY"] == "http://127.0.0.1:9"
        assert env["HTTPS_PROXY"] == "http://127.0.0.1:9"
        assert env["ALL_PROXY"] == "http://127.0.0.1:9"
        assert env["NO_PROXY"] == ""
        assert env["no_proxy"] == ""

    def test_registry_env_pins_still_applied_on_top(self):
        env = ppr._vintage_env({"TZ": "UTC", "RENDER_NO_DRIP": "1"})
        assert env["TZ"] == "UTC"
        assert env["RENDER_NO_DRIP"] == "1"

    def test_stripped_keys_absent_even_when_inherited(self, monkeypatch):
        monkeypatch.setenv("PYTHONPATH", "/should/not/leak/into/the/vintage/tree")
        monkeypatch.setenv("PYTHONSTARTUP", "/should/not/leak/either")
        env = ppr._vintage_env({})
        assert "PYTHONPATH" not in env
        assert "PYTHONSTARTUP" not in env

    def test_applied_env_pins_matches_what_vintage_env_layers_on(self):
        """The receipt (F3) and the real subprocess environment must never drift —
        both are built from the SAME applied_env_pins() call."""
        pins = ppr.applied_env_pins({"TZ": "UTC", "RENDER_NO_DRIP": "1"})
        env = ppr._vintage_env({"TZ": "UTC", "RENDER_NO_DRIP": "1"})
        for key, value in pins.items():
            assert env[key] == value


# ---------------------------------------------------------------------------
# F2b — pinned CN store directories must be byte-identical to the vintage commit
# after every board build
# ---------------------------------------------------------------------------

class TestPinnedStoresAssertion:
    def _vintage_repo(self, tmp_path) -> Path:
        repo = _init_repo(tmp_path, "vintage")
        (repo / "data" / "china_st").mkdir(parents=True)
        (repo / "data" / "china_st" / "st_snapshot.parquet").write_bytes(b"vintage-bytes")
        _git(repo, "add", "data/china_st/st_snapshot.parquet")
        _commit(repo, "seed", date_iso="2026-08-14T00:00:00+00:00")
        return repo

    def test_clean_tree_passes(self, tmp_path):
        vintage = self._vintage_repo(tmp_path)
        pinned = {"dirs": ["data/china_st"], "exempt_files": []}
        result = ppr.assert_pinned_stores_unchanged(
            vintage, pinned_stores=pinned, pass_label="control")
        assert result == [{"dir": "data/china_st", "pass": "control",
                          "clean": True, "changed": []}]

    def test_no_pinned_dirs_is_a_noop(self, tmp_path):
        vintage = self._vintage_repo(tmp_path)
        assert ppr.assert_pinned_stores_unchanged(
            vintage, pinned_stores={}, pass_label="control") == []

    def test_a_modified_pinned_file_refuses(self, tmp_path):
        vintage = self._vintage_repo(tmp_path)
        (vintage / "data" / "china_st" / "st_snapshot.parquet").write_bytes(
            b"LIVE-FETCHED-BYTES")
        pinned = {"dirs": ["data/china_st"], "exempt_files": []}
        with pytest.raises(ppr.PitReplayRefused, match="pinned CN store 'data/china_st' "
                           "was MODIFIED"):
            ppr.assert_pinned_stores_unchanged(
                vintage, pinned_stores=pinned, pass_label="control")

    def test_a_new_untracked_file_in_a_pinned_dir_also_refuses(self, tmp_path):
        """A collector's live fetch that writes a BRAND NEW file (never previously
        tracked) must be caught too — not just a modification of an existing one."""
        vintage = self._vintage_repo(tmp_path)
        (vintage / "data" / "china_st" / "goodwill.parquet").write_bytes(b"new file")
        pinned = {"dirs": ["data/china_st"], "exempt_files": []}
        with pytest.raises(ppr.PitReplayRefused):
            ppr.assert_pinned_stores_unchanged(
                vintage, pinned_stores=pinned, pass_label="replay")

    def test_an_exempt_file_does_not_refuse(self, tmp_path):
        vintage = self._vintage_repo(tmp_path)
        (vintage / "data" / "china_st" / "status.json").write_bytes(b"stamp")
        pinned = {"dirs": ["data/china_st"], "exempt_files": ["data/china_st/status.json"]}
        result = ppr.assert_pinned_stores_unchanged(
            vintage, pinned_stores=pinned, pass_label="control")
        assert result[0]["clean"] is True

    def test_registry_pinned_stores_for_cn_names_all_13_collector_dirs(self):
        """Sanity pin: the registry's own CN entry must actually declare the 13
        collector directories the build commission's F2 census enumerated."""
        dirs = set(ppr.MARKETS["cn"]["pinned_stores"]["dirs"])
        assert dirs == {
            "data/china_analyst", "data/china_earnings", "data/china_margin_detail",
            "data/china_valuation", "data/china_comment", "data/china_lhb",
            "data/china_block_trades", "data/china_zt_pool", "data/china_buyback",
            "data/china_pledge", "data/china_unlocks", "data/china_preannounce",
            "data/china_st",
        }

    def test_us_and_hk_pinned_stores_are_empty(self):
        assert ppr.MARKETS["us"]["pinned_stores"]["dirs"] == []
        assert ppr.MARKETS["hk"]["pinned_stores"]["dirs"] == []


# ---------------------------------------------------------------------------
# F3 — the harness receipt carries every masterplan §0.9 field this build adds
# ---------------------------------------------------------------------------

class TestBuildHarnessReceiptFields:
    @staticmethod
    def _vintage_info() -> dict:
        return {"slot_utc": "2026-08-14T22:30:00Z", "sha": "a" * 40,
               "committed_utc": "2026-08-14T22:00:00+00:00",
               "ancestry": "ancestor_of_origin_main"}

    @staticmethod
    def _result() -> dict:
        return {
            "overlay": {
                "live_price_source_commit": "b" * 40,
                "totals": {"written": 1, "sessions_added": 1, "unchanged": 0},
                "files": {"data/stocks/AAA.parquet": {"added_sessions": 1}},
                "skipped_identical": {"data/stocks": 5},
                "fence": {"violations": 0},
            },
            "control_through": "2026-08-13",
            "fidelity": {"measured": True, "jaccard": 1.0},
            "board_identity": {"as_of": "2026-08-14"},
            "counts": {}, "reconciliation": {}, "clock": None,
            "snapshot_capture": None, "ledger_capture": None,
            "pinned_stores_check": [{"dir": "data/china_st", "pass": "control",
                                    "clean": True, "changed": []}],
            "aux_panel_source": "/some/aux/checkout",
        }

    @pytest.mark.parametrize("market", ["us", "cn"])
    def test_receipt_carries_every_f3_field(self, market):
        entry = ppr.MARKETS[market]
        result = self._result()
        receipt = ppr.build_harness_receipt(
            market=market, session="2026-08-14", entry=entry,
            vintage_info=self._vintage_info(), result=result,
            executed_at="2026-08-15T00:00:00+00:00", executing_commit="c" * 40,
            dry_run=False,
        )
        for field in ("overlay_files", "skipped_identical", "aux_panel_source",
                     "env_pins", "residual_network", "pinned_stores"):
            assert field in receipt, f"{field!r} missing for market={market}"
        assert receipt["env_pins"]["HTTP_PROXY"] == "http://127.0.0.1:9"
        assert receipt["env_pins"] == ppr.applied_env_pins(entry.get("env_pins"))
        assert receipt["pinned_stores"]["registry"] == entry.get("pinned_stores")
        assert receipt["pinned_stores"]["checks"] == result["pinned_stores_check"]
        assert receipt["overlay_files"] == result["overlay"]["files"]
        assert receipt["skipped_identical"] == result["overlay"]["skipped_identical"]
        assert receipt["aux_panel_source"] == "/some/aux/checkout"
        assert receipt["residual_network"] == (entry.get("residual_network") or [])

    def test_missing_optional_result_fields_degrade_to_empty_not_a_crash(self):
        """A US-shaped result that never populated pinned_stores_check/aux_panel_source
        (US carries no pinned stores) must still produce a valid receipt."""
        entry = ppr.MARKETS["us"]
        result = self._result()
        result.pop("pinned_stores_check")
        result.pop("aux_panel_source")
        receipt = ppr.build_harness_receipt(
            market="us", session="2026-08-14", entry=entry,
            vintage_info=self._vintage_info(), result=result,
            executed_at="2026-08-15T00:00:00+00:00", executing_commit="c" * 40,
            dry_run=True,
        )
        assert receipt["pinned_stores"]["checks"] == []
        assert receipt["aux_panel_source"] is None


# ---------------------------------------------------------------------------
# F4 — substituted wide panels report substituted_columns + a constituents diff
# ---------------------------------------------------------------------------

class TestOverlaySessionsSubstitutedColumns:
    def test_wholesale_substitution_reports_column_count(self):
        live = _frame(["2026-08-10", "2026-08-11"], [10.0, 11.0])
        merged, provenance = ppr.overlay_sessions(None, live, "2026-08-11")
        assert provenance["substituted"] is True
        assert provenance["substituted_columns"] == len(live.columns)


class TestConstituentsDiff:
    def test_added_and_removed_named_against_the_vintage_commit(self, tmp_path):
        repo = _init_repo(tmp_path)
        constituents = pd.DataFrame(
            {"name": ["Alpha Co"], "sector": ["Tech"]},
            index=pd.Index(["AAA"], name="symbol"))
        cdir = repo / "data" / "china_breadth"
        cdir.mkdir(parents=True)
        constituents.to_parquet(cdir / "constituents.parquet")
        _git(repo, "add", "data/china_breadth/constituents.parquet")
        vintage_sha = _commit(repo, "seed", date_iso="2026-08-14T00:00:00+00:00")

        diff = ppr._constituents_diff(
            repo, vintage_sha, "data/china_breadth/constituents.parquet",
            ["AAA", "BBB"])
        assert diff["available"] is True
        assert diff["added"] == ["BBB"]
        assert diff["removed"] == []
        assert diff["added_count"] == 1
        assert diff["removed_count"] == 0

    def test_absent_constituents_file_reports_unavailable(self, tmp_path):
        repo = _init_repo(tmp_path)
        vintage_sha = _commit(repo, "seed", date_iso="2026-08-14T00:00:00+00:00")
        diff = ppr._constituents_diff(
            repo, vintage_sha, "data/china_breadth/constituents.parquet", ["AAA"])
        assert diff["available"] is False


class TestPrepareReconstructionTreeConstituentsDiff:
    def test_substituted_wide_panel_reports_constituents_diff(self, tmp_path):
        repo = _init_repo(tmp_path, "repo")
        cdir = repo / "data" / "china_breadth"
        cdir.mkdir(parents=True)
        pd.DataFrame(
            {"name": ["Alpha"], "sector": ["Tech"]},
            index=pd.Index(["AAA"], name="symbol"),
        ).to_parquet(cdir / "constituents.parquet")
        panel = pd.DataFrame(
            {"AAA": [1.0, 1.1], "BBB": [2.0, 2.1]},
            index=pd.to_datetime(["2026-08-10", "2026-08-11"]),
        )
        panel.to_parquet(cdir / "_closes_cache.parquet")
        _git(repo, "add", "data/china_breadth/constituents.parquet",
            "data/china_breadth/_closes_cache.parquet")
        live_sha = _commit(repo, "seed", date_iso="2026-08-14T00:00:00+00:00")

        surface = ppr.PriceSurface(
            wide_panels=("data/china_breadth/_closes_cache.parquet",),
            constituents_index={
                "data/china_breadth/_closes_cache.parquet":
                    "data/china_breadth/constituents.parquet",
            },
        )
        vintage_dir = tmp_path / "vintage"
        vintage_dir.mkdir()
        manifest = ppr.prepare_reconstruction_tree(
            vintage_dir, repo, through="2026-08-11", live_ref="main",
            vintage_commit=live_sha, surface=surface, session_ceiling="2026-08-11",
        )
        prov = manifest["files"]["data/china_breadth/_closes_cache.parquet"]
        assert prov["substituted"] is True
        diff = prov["constituents_diff"]
        assert diff["available"] is True
        assert diff["added"] == ["BBB"]
        assert diff["removed"] == []


# ---------------------------------------------------------------------------
# F6 — a sparse worktree must refuse --execute (before any board build starts)
# and must not affect a dry run
# ---------------------------------------------------------------------------

class TestSparseExecuteGuard:
    def test_sparse_execute_refuses_naming_the_remedy(self, tmp_path, monkeypatch, capsys):
        repo = _init_repo(tmp_path)
        _commit(repo, "init", date_iso="2026-08-14T10:00:00+00:00")
        _set_origin_main(repo)

        import scripts.worktree_sparse as ws
        monkeypatch.setattr(ws, "missing_dirs", lambda root=None: ["data", "site"])

        rc = ppr.main(["--market", "us", "--session", "2026-08-14", "--execute",
                       "--repo", str(repo)])
        assert rc == 2
        out = capsys.readouterr().out
        assert "sparse worktree" in out
        assert "python3 scripts/worktree_sparse.py full" in out

    def test_sparse_dry_run_is_unaffected_by_the_execute_gate(
        self, tmp_path, monkeypatch, capsys
    ):
        repo = _init_repo(tmp_path)
        _commit(repo, "init", date_iso="2026-08-14T10:00:00+00:00")
        _set_origin_main(repo)

        import scripts.worktree_sparse as ws
        monkeypatch.setattr(ws, "missing_dirs", lambda root=None: ["data", "site"])

        rc = ppr.main(["--market", "us", "--session", "2026-08-14",
                       "--repo", str(repo), "--work-dir", str(tmp_path / "work")])
        out = capsys.readouterr().out
        assert "sparse worktree" not in out, (
            "the F6 execute-only sparse gate must not fire on a dry run:\n" + out
        )
        # Fails for an unrelated reason (this tiny fixture repo has no real board
        # content) — out of scope here; only the ABSENCE of the sparse message matters.
        assert rc != 0


class TestReceiptIdempotenceSparseAware:
    def test_working_tree_half_is_skipped_when_data_is_sparse_omitted(
        self, tmp_path, monkeypatch
    ):
        repo = _init_repo(tmp_path)
        _commit(repo, "init", date_iso="2026-08-01T00:00:00+00:00")
        _set_origin_main(repo)
        receipts = repo / "data" / "pit_replay"
        receipts.mkdir(parents=True)
        (receipts / "us-2026-08-14-deadbeef.json").write_text("{}", encoding="utf-8")

        import scripts.worktree_sparse as ws
        monkeypatch.setattr(ws, "missing_dirs", lambda root=None: ["data"])
        ppr.check_receipt_idempotence(repo, "us", "2026-08-14")  # must not raise

    def test_working_tree_half_still_fires_when_not_sparse(self, tmp_path, monkeypatch):
        repo = _init_repo(tmp_path)
        _commit(repo, "init", date_iso="2026-08-01T00:00:00+00:00")
        _set_origin_main(repo)
        receipts = repo / "data" / "pit_replay"
        receipts.mkdir(parents=True)
        (receipts / "us-2026-08-14-deadbeef.json").write_text("{}", encoding="utf-8")

        import scripts.worktree_sparse as ws
        monkeypatch.setattr(ws, "missing_dirs", lambda root=None: [])
        with pytest.raises(ppr.PitReplayRefused, match="already exists in the working tree"):
            ppr.check_receipt_idempotence(repo, "us", "2026-08-14")


# ---------------------------------------------------------------------------
# F11 — the execute log must not open with the false "nothing was written" claim
# ---------------------------------------------------------------------------

class TestPrintDryRunExecuteGating:
    @staticmethod
    def _result() -> dict:
        return {
            "market": "us", "session": "2026-08-14", "vintage_sha": "a" * 40,
            "control_through": "2026-08-13",
            "fidelity": {"measured": False, "reason": "n/a"},
            "board_identity": {"as_of": "2026-08-14", "rank_by": "x", "buy_rows": 0,
                              "sha256": "b" * 64},
            "counts": {}, "reconciliation": {}, "minted": [], "snapshot_capture": None,
        }

    def test_execute_mode_does_not_print_the_dry_run_banner(self, capsys):
        ppr._print_dry_run(self._result(), execute=True)
        out = capsys.readouterr().out
        assert "DRY RUN" not in out
        assert "EXECUTE" in out

    def test_dry_run_mode_still_prints_the_dry_run_banner(self, capsys):
        ppr._print_dry_run(self._result(), execute=False)
        out = capsys.readouterr().out
        assert "DRY RUN" in out
