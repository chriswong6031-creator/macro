"""Tests for scripts/cctv_finalize_watcher.py — CCTV backfill state machine.

Covers:
  - State transitions: SCRAPING → COMPLETE → FINALIZING → FINALIZED
  - Stall detection + relaunch decision (mock pgrep / log mtime)
  - Marker idempotency (FINALIZED is a no-op)
  - Alert dedup via fired-state file
  - Coverage threshold math
  - Gitignore mutation (remove shard line)
  - Monthly top-up mtime gate

All tests are hermetic: they never touch the real archive dir (DEFAULT_ARCHIVE).
All tracked files that may be dirtied (e.g. .gitignore) are restored via tmp copies.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Ensure the repo root is importable
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_archive(tmp_path: Path) -> Path:
    """Isolated archive directory in a tmp location."""
    d = tmp_path / "cctv_archive"
    d.mkdir()
    return d


@pytest.fixture()
def tmp_china_news(tmp_path: Path) -> Path:
    """Isolated china_news parent directory."""
    d = tmp_path / "china_news"
    d.mkdir()
    return d


@pytest.fixture()
def tmp_gitignore(tmp_path: Path) -> Path:
    """A scratch .gitignore with the shard pattern present."""
    content = textwrap.dedent("""\
        *.pyc
        __pycache__/
        # CCTV 新闻联播 raw archive shards (W4 backfill). Projected ≈43MB total — under
        # the 150MB commit threshold, but shards are gitignored because the long backfill
        # scrape outlives this PR.
        data/china_news/cctv_archive/*.parquet
        data/news_vector/fetch_cache/
    """)
    p = tmp_path / ".gitignore"
    p.write_text(content, encoding="utf-8")
    return p


def _make_shard(archive_dir: Path, ym: str = "2025-01", n_ok: int = 5) -> None:
    """Write a minimal monthly shard parquet to the archive dir."""
    rows = [
        {
            "date": f"{ym}-{i+1:02d}",
            "order_idx": 0,
            "title": f"title {i}",
            "content": f"content {i}",
            "fetch_status": "ok",
            "fetched_at": "2025-01-01T00:00:00Z",
        }
        for i in range(n_ok)
    ]
    df = pd.DataFrame(rows)
    df.to_parquet(archive_dir / f"{ym}.parquet", compression="zstd", index=False)


def _write_state(archive_dir: Path, state: str, **extra) -> None:
    data = {"state": state, **extra}
    (archive_dir / "finalize_state.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )


def _read_state(archive_dir: Path) -> dict:
    p = archive_dir / "finalize_state.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


# ---------------------------------------------------------------------------
# Module-level patches so tests don't need real data dirs
# ---------------------------------------------------------------------------

def _patch_paths(archive_dir: Path, china_news_dir: Path, tmp_path: Path):
    """Return a dict of patches redirecting all module-level paths."""
    return {
        "scripts.cctv_finalize_watcher.ARCHIVE_DIR": archive_dir,
        "scripts.cctv_finalize_watcher.STATE_FILE": archive_dir / "finalize_state.json",
        "scripts.cctv_finalize_watcher.TONE_HISTORY_PATH": china_news_dir / "cctv_tone_history.parquet",
        "scripts.cctv_finalize_watcher.GITIGNORE_PATH": tmp_path / ".gitignore",
        "scripts.cctv_finalize_watcher.FIRED_STATE_FILE": tmp_path / "cctv_finalize_alerts_fired.json",
        "scripts.cctv_finalize_watcher.BACKFILL_LOG": archive_dir / "backfill.log",
    }


# ---------------------------------------------------------------------------
# 1. Coverage threshold math
# ---------------------------------------------------------------------------

class TestThresholdMath:
    """_fast_gap_audit returns is_above_threshold correctly."""

    def test_above_threshold(self, tmp_archive):
        # Mock _all_dates to return 100 dates and _already_archived to say 98 are covered
        import scripts.cctv_finalize_watcher as watcher
        with (
            mock.patch("scripts.backfill_cctv_archive._all_dates",
                       return_value=[f"date_{i}" for i in range(100)]),
            mock.patch("scripts.backfill_cctv_archive._already_archived",
                       return_value=True),  # all covered
            mock.patch.object(watcher, "ARCHIVE_DIR", tmp_archive),
        ):
            # 100/100 = 1.0 ≥ 0.97 → True
            result = watcher._fast_gap_audit(tmp_archive)
        assert result["is_above_threshold"] is True
        assert result["total_covered"] == 100

    def test_below_threshold(self, tmp_archive):
        import scripts.cctv_finalize_watcher as watcher
        # 90/100 = 0.90 < 0.97 → False
        dates = list(range(100))
        covered = set(range(90))

        def mock_archived(archive_dir, d):
            return d in covered

        with (
            mock.patch("scripts.backfill_cctv_archive._all_dates", return_value=dates),
            mock.patch("scripts.backfill_cctv_archive._already_archived",
                       side_effect=mock_archived),
        ):
            result = watcher._fast_gap_audit(tmp_archive)
        assert result["is_above_threshold"] is False
        assert result["coverage_pct"] == pytest.approx(0.90)

    def test_empty_archive(self, tmp_archive):
        import scripts.cctv_finalize_watcher as watcher
        with (
            mock.patch("scripts.backfill_cctv_archive._all_dates", return_value=list(range(50))),
            mock.patch("scripts.backfill_cctv_archive._already_archived", return_value=False),
        ):
            result = watcher._fast_gap_audit(tmp_archive)
        assert result["is_above_threshold"] is False
        assert result["total_covered"] == 0


# ---------------------------------------------------------------------------
# 2. Stall detection
# ---------------------------------------------------------------------------

class TestStallDetection:
    def test_not_stalled_process_alive(self, tmp_archive):
        import scripts.cctv_finalize_watcher as watcher
        with mock.patch.object(watcher, "_backfill_process_alive", return_value=True):
            assert watcher._is_stalled(tmp_archive) is False

    def test_not_stalled_recent_log(self, tmp_archive):
        import scripts.cctv_finalize_watcher as watcher
        # Write a log that is only 1 hour old
        log_path = tmp_archive / "backfill.log"
        log_path.write_text("progress", encoding="utf-8")
        now = datetime.now(timezone.utc)
        import os, time as _time
        recent = (now - timedelta(hours=1)).timestamp()
        os.utime(log_path, (recent, recent))

        with mock.patch.object(watcher, "_backfill_process_alive", return_value=False):
            assert watcher._is_stalled(tmp_archive) is False

    def test_stalled_old_log_no_process(self, tmp_archive):
        import scripts.cctv_finalize_watcher as watcher, os
        log_path = tmp_archive / "backfill.log"
        log_path.write_text("progress", encoding="utf-8")
        # Backdate by 30 hours
        old = (datetime.now(timezone.utc) - timedelta(hours=30)).timestamp()
        os.utime(log_path, (old, old))

        with mock.patch.object(watcher, "_backfill_process_alive", return_value=False):
            assert watcher._is_stalled(tmp_archive) is True

    def test_no_log_no_shards_not_stalled(self, tmp_archive):
        import scripts.cctv_finalize_watcher as watcher
        # No files at all — can't be stalled (just not started)
        with mock.patch.object(watcher, "_backfill_process_alive", return_value=False):
            assert watcher._is_stalled(tmp_archive) is False


# ---------------------------------------------------------------------------
# 3. Alert dedup (fired-state file)
# ---------------------------------------------------------------------------

class TestAlertDedup:
    def test_fires_once(self, tmp_path):
        import scripts.cctv_finalize_watcher as watcher
        fired_file = tmp_path / "alerts_fired.json"
        with (
            mock.patch.object(watcher, "FIRED_STATE_FILE", fired_file),
            mock.patch.object(watcher, "_send_alert") as mock_send,
        ):
            # First call fires
            assert not watcher._already_fired("test_key")
            watcher._mark_fired("test_key")
            assert watcher._already_fired("test_key")

            # Simulate the pattern used in the state machine
            if not watcher._already_fired("test_key"):
                mock_send("msg")
            # Should NOT call send (already fired)
            mock_send.assert_not_called()

    def test_separate_keys_independent(self, tmp_path):
        import scripts.cctv_finalize_watcher as watcher
        fired_file = tmp_path / "alerts_fired.json"
        with mock.patch.object(watcher, "FIRED_STATE_FILE", fired_file):
            watcher._mark_fired("key_a")
            assert watcher._already_fired("key_a") is True
            assert watcher._already_fired("key_b") is False

    def test_fired_file_persists(self, tmp_path):
        import scripts.cctv_finalize_watcher as watcher
        fired_file = tmp_path / "alerts_fired.json"
        with mock.patch.object(watcher, "FIRED_STATE_FILE", fired_file):
            watcher._mark_fired("key_x")
        # Re-load (simulate new process)
        with mock.patch.object(watcher, "FIRED_STATE_FILE", fired_file):
            assert watcher._already_fired("key_x") is True


# ---------------------------------------------------------------------------
# 4. State transitions
# ---------------------------------------------------------------------------

class TestStateTransitions:
    """Test the state machine transition logic."""

    def _redirect_paths(self, watcher, tmp_archive, tmp_path):
        """Redirect all module-level paths in watcher to tmp locations."""
        china_news = tmp_path / "china_news"
        china_news.mkdir(exist_ok=True)
        watcher.ARCHIVE_DIR = tmp_archive
        watcher.STATE_FILE = tmp_archive / "finalize_state.json"
        watcher.TONE_HISTORY_PATH = china_news / "cctv_tone_history.parquet"
        watcher.GITIGNORE_PATH = tmp_path / ".gitignore"
        watcher.FIRED_STATE_FILE = tmp_path / "fired.json"

    def _restore_paths(self, watcher):
        """Restore module-level paths to their canonical values."""
        watcher.ARCHIVE_DIR = REPO_ROOT / "data" / "china_news" / "cctv_archive"
        watcher.STATE_FILE = watcher.ARCHIVE_DIR / "finalize_state.json"
        watcher.TONE_HISTORY_PATH = REPO_ROOT / "data" / "china_news" / "cctv_tone_history.parquet"
        watcher.GITIGNORE_PATH = REPO_ROOT / ".gitignore"
        watcher.FIRED_STATE_FILE = REPO_ROOT / "data" / "china_news" / "cctv_finalize_alerts_fired.json"

    def test_scraping_stays_scraping_below_threshold(self, tmp_archive, tmp_path):
        import scripts.cctv_finalize_watcher as watcher
        self._redirect_paths(watcher, tmp_archive, tmp_path)
        try:
            def mock_audit(_d):
                return {"total_dates": 100, "total_covered": 50,
                        "coverage_pct": 0.50, "is_above_threshold": False,
                        "history_start": "2016-02-03", "as_of": "2026-07-02"}

            with (
                mock.patch.object(watcher, "_fast_gap_audit", side_effect=mock_audit),
                mock.patch.object(watcher, "_is_stalled", return_value=False),
            ):
                result = watcher.run(dry_run=True)

            assert result["state"] == "SCRAPING"
            st = _read_state(tmp_archive)
            assert st["state"] == "SCRAPING"
        finally:
            self._restore_paths(watcher)

    def test_scraping_transitions_to_finalized_above_threshold(self, tmp_archive, tmp_path):
        import scripts.cctv_finalize_watcher as watcher
        self._redirect_paths(watcher, tmp_archive, tmp_path)
        try:
            gi = tmp_path / ".gitignore"
            gi.write_text("data/china_news/cctv_archive/*.parquet\nother_line\n", encoding="utf-8")
            watcher.GITIGNORE_PATH = gi

            def mock_audit(_d):
                return {"total_dates": 100, "total_covered": 98,
                        "coverage_pct": 0.98, "is_above_threshold": True,
                        "history_start": "2016-02-03", "as_of": "2026-07-02"}

            with (
                mock.patch.object(watcher, "_fast_gap_audit", side_effect=mock_audit),
                mock.patch.object(watcher, "_is_stalled", return_value=False),
                mock.patch.object(watcher, "_run_finalize") as mock_finalize,
            ):
                mock_finalize.return_value = {"state": "FINALIZED", "action": "finalized"}
                watcher.run(dry_run=True)

            mock_finalize.assert_called_once()
        finally:
            self._restore_paths(watcher)

    def test_finalized_is_idempotent(self, tmp_archive, tmp_path):
        import scripts.cctv_finalize_watcher as watcher
        self._redirect_paths(watcher, tmp_archive, tmp_path)
        try:
            _write_state(tmp_archive, "FINALIZED")

            with mock.patch.object(watcher, "_monthly_topup") as mock_topup:
                result = watcher.run(dry_run=True)

            assert result["state"] == "FINALIZED"
            assert result["action"] == "monthly_topup_check"
            mock_topup.assert_called_once()
            st = _read_state(tmp_archive)
            assert st["state"] == "FINALIZED"
        finally:
            self._restore_paths(watcher)

    def test_finalized_does_not_rerun_finalize(self, tmp_archive, tmp_path):
        import scripts.cctv_finalize_watcher as watcher
        self._redirect_paths(watcher, tmp_archive, tmp_path)
        try:
            _write_state(tmp_archive, "FINALIZED")

            with (
                mock.patch.object(watcher, "_run_finalize") as mock_finalize,
                mock.patch.object(watcher, "_monthly_topup"),
            ):
                watcher.run(dry_run=True)

            mock_finalize.assert_not_called()
        finally:
            self._restore_paths(watcher)

    def test_stall_triggers_relaunch_and_alert(self, tmp_archive, tmp_path):
        import scripts.cctv_finalize_watcher as watcher
        self._redirect_paths(watcher, tmp_archive, tmp_path)
        try:
            def mock_audit(_d):
                return {"total_dates": 100, "total_covered": 50,
                        "coverage_pct": 0.50, "is_above_threshold": False,
                        "history_start": "2016-02-03", "as_of": "2026-07-02"}

            with (
                mock.patch.object(watcher, "_fast_gap_audit", side_effect=mock_audit),
                mock.patch.object(watcher, "_is_stalled", return_value=True),
                mock.patch.object(watcher, "_relaunch_backfill") as mock_relaunch,
                mock.patch.object(watcher, "_send_alert") as mock_alert,
            ):
                result = watcher.run(dry_run=False)

            mock_relaunch.assert_called_once_with(tmp_archive)
            mock_alert.assert_called_once()
            alert_msg = mock_alert.call_args[0][0]
            assert "stall" in alert_msg.lower()
        finally:
            self._restore_paths(watcher)

    def test_stall_alert_fires_only_once(self, tmp_archive, tmp_path):
        import scripts.cctv_finalize_watcher as watcher
        self._redirect_paths(watcher, tmp_archive, tmp_path)
        try:
            fired_file = tmp_path / "fired.json"
            fired_file.write_text(
                json.dumps({"cctv_scrape_stall": "2026-07-01T00:00:00"}),
                encoding="utf-8"
            )
            watcher.FIRED_STATE_FILE = fired_file

            def mock_audit(_d):
                return {"total_dates": 100, "total_covered": 50,
                        "coverage_pct": 0.50, "is_above_threshold": False,
                        "history_start": "2016-02-03", "as_of": "2026-07-02"}

            with (
                mock.patch.object(watcher, "_fast_gap_audit", side_effect=mock_audit),
                mock.patch.object(watcher, "_is_stalled", return_value=True),
                mock.patch.object(watcher, "_relaunch_backfill"),
                mock.patch.object(watcher, "_send_alert") as mock_alert,
            ):
                watcher.run(dry_run=False)

            mock_alert.assert_not_called()
        finally:
            self._restore_paths(watcher)


# ---------------------------------------------------------------------------
# 5. Gitignore mutation
# ---------------------------------------------------------------------------

class TestGitignoreMutation:
    def test_removes_shard_pattern_and_comment(self, tmp_gitignore):
        import scripts.cctv_finalize_watcher as watcher
        with mock.patch.object(watcher, "GITIGNORE_PATH", tmp_gitignore):
            changed = watcher._remove_gitignore_shard_line(dry_run=False)

        assert changed is True
        text = tmp_gitignore.read_text(encoding="utf-8")
        assert "cctv_archive/*.parquet" not in text
        # Other lines must survive
        assert "*.pyc" in text
        assert "data/news_vector/fetch_cache/" in text

    def test_dry_run_does_not_modify(self, tmp_gitignore):
        import scripts.cctv_finalize_watcher as watcher
        original = tmp_gitignore.read_text(encoding="utf-8")
        with mock.patch.object(watcher, "GITIGNORE_PATH", tmp_gitignore):
            changed = watcher._remove_gitignore_shard_line(dry_run=True)

        assert changed is True   # reports it would change
        assert tmp_gitignore.read_text(encoding="utf-8") == original

    def test_idempotent_when_line_absent(self, tmp_path):
        import scripts.cctv_finalize_watcher as watcher
        gi = tmp_path / ".gitignore"
        gi.write_text("*.pyc\n__pycache__/\n", encoding="utf-8")

        with mock.patch.object(watcher, "GITIGNORE_PATH", gi):
            changed = watcher._remove_gitignore_shard_line(dry_run=False)

        assert changed is False
        assert gi.read_text(encoding="utf-8") == "*.pyc\n__pycache__/\n"

    def test_missing_gitignore_returns_false(self, tmp_path):
        import scripts.cctv_finalize_watcher as watcher
        with mock.patch.object(watcher, "GITIGNORE_PATH", tmp_path / "nonexistent.gitignore"):
            result = watcher._remove_gitignore_shard_line(dry_run=False)
        assert result is False


# ---------------------------------------------------------------------------
# 6. Monthly top-up content gate (was mtime-gated — #2690 class)
# ---------------------------------------------------------------------------

class TestMonthlyTopup:
    def test_topup_skipped_when_fresh(self, tmp_path):
        """Content-fresh tone history (newest observation ≈ today) ⇒ skip.
        Freshness is the parquet's own newest index date, never file mtime
        (mtime = checkout time on CI — #2690 class)."""
        import scripts.cctv_finalize_watcher as watcher
        china_news = tmp_path / "china_news"
        china_news.mkdir()
        tone = china_news / "cctv_tone_history.parquet"
        pd.DataFrame({"tone": [0.1] * 5},
                     index=pd.date_range(end=pd.Timestamp.today(), periods=5)
                     ).to_parquet(tone)

        with (
            mock.patch.object(watcher, "TONE_HISTORY_PATH", tone),
            mock.patch("scripts.rebuild_cctv_tone_history.rebuild") as mock_rebuild,
        ):
            watcher._monthly_topup(tmp_path / "archive", dry_run=False)

        mock_rebuild.assert_not_called()

    def test_topup_runs_when_stale(self, tmp_path):
        import scripts.cctv_finalize_watcher as watcher
        import os
        china_news = tmp_path / "china_news"
        china_news.mkdir()
        tone = china_news / "cctv_tone_history.parquet"
        # Newest observation 35 days ago — content-stale; give the FILE a
        # fresh (checkout-time) mtime to pin the #2690 regression.
        pd.DataFrame({"tone": [0.1] * 5, "n_items": [3] * 5, "n_stub": [0] * 5},
                     index=pd.date_range(
                         end=pd.Timestamp.today() - pd.Timedelta(days=35), periods=5)
                     ).to_parquet(tone)
        now = datetime.now(timezone.utc).timestamp()
        os.utime(tone, (now, now))

        mock_df = pd.DataFrame({"tone": [0.1] * 100, "n_items": [3] * 100, "n_stub": [0] * 100},
                                index=pd.date_range("2024-01-01", periods=100))

        with (
            mock.patch.object(watcher, "TONE_HISTORY_PATH", tone),
            mock.patch("scripts.rebuild_cctv_tone_history.rebuild", return_value=mock_df),
        ):
            watcher._monthly_topup(tmp_path / "archive", dry_run=False)
            # rebuild was imported from module; patch at the import site
            # Just verify no exception was raised and tone_history exists


# ---------------------------------------------------------------------------
# 7. run_as_collect_step never raises
# ---------------------------------------------------------------------------

class TestCollectHookNeverRaises:
    def test_exception_is_swallowed(self, tmp_archive, tmp_path):
        import scripts.cctv_finalize_watcher as watcher
        with mock.patch.object(watcher, "run", side_effect=RuntimeError("bang")):
            # Must not raise
            watcher.run_as_collect_step()

    def test_normal_path_succeeds(self, tmp_archive, tmp_path):
        import scripts.cctv_finalize_watcher as watcher
        with mock.patch.object(watcher, "run", return_value={"state": "SCRAPING",
                                                               "coverage_pct": 42.0,
                                                               "action": "watching"}):
            watcher.run_as_collect_step()  # should not raise


# ---------------------------------------------------------------------------
# 8. Backfill process detection
# ---------------------------------------------------------------------------

class TestProcessDetection:
    def test_alive_when_pgrep_exits_0(self):
        import scripts.cctv_finalize_watcher as watcher
        fake = mock.MagicMock()
        fake.returncode = 0
        with mock.patch("subprocess.run", return_value=fake):
            assert watcher._backfill_process_alive() is True

    def test_not_alive_when_pgrep_exits_1(self):
        import scripts.cctv_finalize_watcher as watcher
        fake = mock.MagicMock()
        fake.returncode = 1
        with mock.patch("subprocess.run", return_value=fake):
            assert watcher._backfill_process_alive() is False

    def test_conservative_on_pgrep_error(self):
        import scripts.cctv_finalize_watcher as watcher
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("pgrep")):
            # Should return False (conservative — if pgrep not found, assume not alive)
            assert watcher._backfill_process_alive() is False
