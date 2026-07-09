"""Tests for the HKEXnews company-catalyst filing bus.

Coverage:
  1. code_to_ticker normalisation (joint-announcement multi-code + numeric edge cases)
  2. _rows_to_frame: real HKEXnews servlet schema (DD/MM/YYYY HH:MM dates,
     double-escaped HTML, multi-stock codes)
  3. classify_row: per-category correctness
     - buyback MUST have buyback_flag=True and dilution_flag=False
     - dilutive mandate/placement MUST have dilution_flag=True and buyback_flag=False
     - HARD CONSTRAINT: both flags never simultaneously True (checked in engine)
  4. build_tape: combine filings+placements; apply window filter; dedup
  5. Fail-open: missing/stale stores return empty → banner rendered
  6. Ledger idempotency + CN_LANE gate
  7. git status clean: ALL writes go to tmp_path

The fixtures below mirror the REAL HKEXnews servlet schema (verified 2026-07-08).
Do NOT invent columns that the servlet does not return.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import date
from pathlib import Path

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fixture factory — mirrors real HKEXnews servlet row schema (verified 2026-07-08)
# Fields present in live rows: NEWS_ID, STOCK_CODE, STOCK_NAME, DATE_TIME,
# TITLE, SHORT_TEXT, FILE_TYPE, DOD_WEB_PATH, FILE_LINK (optional).
# ---------------------------------------------------------------------------

def _servlet_row(
    news_id: str = "10001",
    code: str = "00700",
    stock_name: str = "TENCENT",
    dt: str = "07/07/2026 18:30",
    title: str = "ANNOUNCEMENT OF ANNUAL RESULTS",
    short: str = "Announcements and Notices - [Final Results]",
) -> dict:
    return {
        "NEWS_ID": news_id, "STOCK_CODE": code, "STOCK_NAME": stock_name,
        "DATE_TIME": dt, "TITLE": title, "SHORT_TEXT": short,
        "FILE_TYPE": "PDF", "DOD_WEB_PATH": "/listedco/listconews/SEHK/2026/0707/0000.pdf",
    }


def _filing_df(rows: list[dict], category: str) -> pd.DataFrame:
    """Build a canonical event DataFrame from synthetic servlet rows."""
    from collectors.hk_hkexnews import _rows_to_frame
    return _rows_to_frame(rows, category)


# ---------------------------------------------------------------------------
# 1. code_to_ticker
# ---------------------------------------------------------------------------

class TestCodeToTicker:
    """code_to_ticker: servlet zero-padded codes → panel '.HK' keys."""

    def test_standard_zero_padded_5digit(self):
        from collectors.hk_hkexnews import code_to_ticker
        assert code_to_ticker("00700") == "0700.HK"

    def test_standard_4digit(self):
        from collectors.hk_hkexnews import code_to_ticker
        assert code_to_ticker("09988") == "9988.HK"

    def test_1digit_padded_to_4(self):
        from collectors.hk_hkexnews import code_to_ticker
        assert code_to_ticker("00388") == "0388.HK"

    def test_joint_announcement_multicode(self):
        """Joint announcement codes like '01024<br/>81024' → first numeric code."""
        from collectors.hk_hkexnews import code_to_ticker
        # The <br/> separator is the real servlet format
        result = code_to_ticker("01024<br/>81024")
        assert result == "1024.HK"

    def test_nonnumeric_returns_none(self):
        from collectors.hk_hkexnews import code_to_ticker
        assert code_to_ticker("ABC") is None

    def test_empty_returns_none(self):
        from collectors.hk_hkexnews import code_to_ticker
        assert code_to_ticker("") is None

    def test_none_returns_none(self):
        from collectors.hk_hkexnews import code_to_ticker
        assert code_to_ticker(None) is None

    def test_zero_out_of_range(self):
        from collectors.hk_hkexnews import code_to_ticker
        assert code_to_ticker("00000") is None


# ---------------------------------------------------------------------------
# 2. _rows_to_frame: real schema parsing
# ---------------------------------------------------------------------------

class TestRowsToFrame:
    """_rows_to_frame on real HKEXnews servlet row structure."""

    def test_parses_basic_row(self):
        from collectors.hk_hkexnews import _rows_to_frame, _EVENT_COLS
        rows = [_servlet_row()]
        df = _rows_to_frame(rows, "final_results")
        assert len(df) == 1
        for col in _EVENT_COLS:
            assert col in df.columns, f"Missing column: {col}"

    def test_datetime_parsed_correctly(self):
        from collectors.hk_hkexnews import _rows_to_frame
        rows = [_servlet_row(dt="08/07/2026 19:02")]
        df = _rows_to_frame(rows, "final_results")
        assert df.iloc[0]["announced_at"] == pd.Timestamp("2026-07-08 19:02")

    def test_double_escaped_html_unescape(self):
        """Double-escaped HTML entities (&#x2f; = /) are cleaned in the title."""
        from collectors.hk_hkexnews import _rows_to_frame
        row = _servlet_row(
            title="COMPLETION&#x20;OF&#x20;PLACING&#x20;OF&#x20;SHARES&#x20;&#x26;&#x20;UPDATE")
        df = _rows_to_frame([row], "general_mandate")
        assert "&#" not in df.iloc[0]["title"]

    def test_multi_stock_code_takes_first(self):
        """Joint announcements with 'CODE<br/>CODE2' use the first numeric code."""
        from collectors.hk_hkexnews import _rows_to_frame
        row = _servlet_row(code="01024<br/>81024")
        df = _rows_to_frame([row], "shareholder")
        assert df.iloc[0]["ticker"] == "1024.HK"

    def test_rows_missing_news_id_dropped(self):
        from collectors.hk_hkexnews import _rows_to_frame
        bad = _servlet_row()
        bad["NEWS_ID"] = ""
        df = _rows_to_frame([bad], "buyback")
        assert len(df) == 0

    def test_rows_missing_date_dropped(self):
        from collectors.hk_hkexnews import _rows_to_frame
        bad = _servlet_row(dt="not-a-date")
        df = _rows_to_frame([bad], "buyback")
        assert len(df) == 0

    def test_title_truncated_at_300(self):
        from collectors.hk_hkexnews import _rows_to_frame
        long_title = "X" * 500
        row = _servlet_row(title=long_title)
        df = _rows_to_frame([row], "buyback")
        assert len(df.iloc[0]["title"]) <= 300

    def test_category_assigned(self):
        from collectors.hk_hkexnews import _rows_to_frame
        df = _rows_to_frame([_servlet_row()], "interim_results")
        assert df.iloc[0]["category"] == "interim_results"


# ---------------------------------------------------------------------------
# 3. classify_row — deterministic category + flag assignment
# ---------------------------------------------------------------------------

class TestClassifyRow:
    """Deterministic classify_row correctness; hard constraint enforcement."""

    # BUYBACK tests
    @pytest.mark.parametrize("title", [
        "MONTHLY UPDATE IN RELATION TO PROPOSED PRE-CONDITIONAL SHARE BUY-BACK",
        "COMPLETION OF THE CASH OFFER TO BUY-BACK SHARES",
        "ANNOUNCEMENT REGARDING SHARE REPURCHASE PROGRAMME",
        "ON-MARKET SHARE BUY-BACK UPDATE",
    ])
    def test_buyback_titles_flag_buyback(self, title):
        from engine.hk_filing_bus import classify_row
        result = classify_row("buyback", title)
        assert result["buyback_flag"] is True, f"Expected buyback_flag=True for: {title!r}"
        assert result["dilution_flag"] is False, f"dilution_flag must be False: {title!r}"
        assert result["category"] == "buyback"

    # DILUTIVE mandate / placement tests
    @pytest.mark.parametrize("cat,title", [
        ("general_mandate", "COMPLETION OF PLACING OF NEW H SHARES UNDER GENERAL MANDATE"),
        ("general_mandate", "PLACING OF NEW SHARES UNDER GENERAL MANDATE"),
        ("placing",         "COMPLETION OF TOP-UP PLACING OF NEW SHARES"),
        ("placing",         "RIGHTS ISSUE OF NEW SHARES AT DISCOUNT"),
    ])
    def test_dilutive_mandate_flags_dilution(self, cat, title):
        from engine.hk_filing_bus import classify_row
        result = classify_row(cat, title)
        assert result["dilution_flag"] is True, f"Expected dilution_flag=True for {cat}/{title!r}"
        assert result["buyback_flag"] is False, f"buyback_flag must be False: {title!r}"

    # SHARE ISSUANCE token — the false-negative fixed by delegating to is_dilutive()
    @pytest.mark.parametrize("cat,title", [
        ("general_mandate", "SHARE ISSUANCE UNDER GENERAL MANDATE"),
        ("general_mandate", "GENERAL MANDATE FOR SHARE ISSUANCE"),
        ("placing",         "COMPLETION OF SHARE ISSUANCE UNDER GENERAL MANDATE"),
    ])
    def test_share_issuance_phrases_are_dilutive(self, cat, title):
        """'SHARE ISSUANCE' strong token must produce dilution_flag=True.

        Regression: the local _DILUTE_STRONG_RE omitted this token; delegating
        to collectors.hk_placements.is_dilutive() via _hk_placements_is_dilutive
        covers it correctly (hk_placements._STRONG_RE includes 'SHARE ISSUANCE').
        """
        from engine.hk_filing_bus import classify_row
        result = classify_row(cat, title)
        assert result["dilution_flag"] is True, \
            f"Expected dilution_flag=True for {cat}/{title!r}"
        assert result["buyback_flag"] is False, \
            f"buyback_flag must be False for {cat}/{title!r}"

    # NON-dilutive mandate (convertible bond — over-captured by category)
    @pytest.mark.parametrize("title", [
        "ADJUSTMENT TO CONVERSION PRICE OF HK$8,624,000,000 ZERO COUPON GUARANTEED CONVERTIBLE BONDS",
        "ISSUE OF US$2,000 MILLION ZERO COUPON CONVERTIBLE BONDS DUE 2033",
    ])
    def test_convertible_bond_not_dilutive(self, title):
        from engine.hk_filing_bus import classify_row
        result = classify_row("general_mandate", title)
        assert result["dilution_flag"] is False, \
            f"CB issuance should NOT be dilutive: {title!r}"
        # Demoted to 'other'
        assert result["category"] == "other", \
            f"CB rows should be demoted to 'other': {title!r}"

    # RESULTS category
    def test_results_no_flags(self):
        from engine.hk_filing_bus import classify_row
        for cat in ("final_results", "interim_results"):
            result = classify_row(cat, "ANNOUNCEMENT OF ANNUAL RESULTS")
            assert result["category"] == "results"
            assert result["dilution_flag"] is False
            assert result["buyback_flag"] is False

    # SHAREHOLDER category
    def test_shareholder_no_flags(self):
        from engine.hk_filing_bus import classify_row
        result = classify_row("shareholder",
                              "VOLUNTARY ANNOUNCEMENT - DISPOSAL OF SHARES BY A SHAREHOLDER")
        assert result["category"] == "shareholder"
        assert result["dilution_flag"] is False
        assert result["buyback_flag"] is False

    # HARD CONSTRAINT: a buyback must NEVER also be dilutive
    def test_buyback_never_dilutive(self):
        """Regression: the hard constraint that buyback_flag XOR dilution_flag."""
        from engine.hk_filing_bus import classify_row
        # Try every category with a buyback-sounding title
        for cat in ("buyback", "placing", "general_mandate", "final_results",
                    "interim_results", "shareholder"):
            result = classify_row(cat, "SHARE BUY-BACK ANNOUNCEMENT")
            both = result["buyback_flag"] and result["dilution_flag"]
            assert not both, \
                f"HARD CONSTRAINT VIOLATED: both flags True for category={cat}"

    # DILUTION never also flagged buyback
    def test_dilution_never_buyback(self):
        """Regression: a placing/mandate row can never also set buyback_flag."""
        from engine.hk_filing_bus import classify_row
        for cat in ("placing", "general_mandate"):
            result = classify_row(cat, "COMPLETION OF PLACING OF NEW SHARES UNDER GENERAL MANDATE")
            assert not (result["dilution_flag"] and result["buyback_flag"]), \
                f"HARD CONSTRAINT VIOLATED for category={cat}"


# ---------------------------------------------------------------------------
# 4. build_tape
# ---------------------------------------------------------------------------

class TestBuildTape:
    """build_tape: merge, classify, window filter, dedup."""

    def _make_filing_store(self) -> pd.DataFrame:
        """Synthetic hk_filings events DataFrame mirroring the real store schema."""
        today = pd.Timestamp.today().normalize()
        return pd.DataFrame([
            {
                "news_id": "F001", "stock_code": "00700", "ticker": "0700.HK",
                "category": "final_results", "announced_at": today - pd.Timedelta(days=5),
                "date": today - pd.Timedelta(days=5),
                "title": "ANNOUNCEMENT OF ANNUAL RESULTS FOR THE YEAR 2025",
                "subcats": "Announcements and Notices - [Final Results]",
            },
            {
                "news_id": "F002", "stock_code": "09988", "ticker": "9988.HK",
                "category": "buyback",
                "announced_at": today - pd.Timedelta(days=3),
                "date": today - pd.Timedelta(days=3),
                "title": "MONTHLY UPDATE ON SHARE BUY-BACK PROGRAMME",
                "subcats": "Announcements and Notices - [Announcement pursuant to Code on Share Buy-backs]",
            },
            {
                "news_id": "F003", "stock_code": "01810", "ticker": "1810.HK",
                "category": "general_mandate",
                "announced_at": today - pd.Timedelta(days=1),
                "date": today - pd.Timedelta(days=1),
                "title": "COMPLETION OF PLACING OF NEW SHARES UNDER GENERAL MANDATE",
                "subcats": "Announcements and Notices - [Issue of Shares under a General Mandate]",
            },
        ])

    def _make_placement_store(self) -> pd.DataFrame:
        """Synthetic hk_placements events DataFrame mirroring the real store schema."""
        today = pd.Timestamp.today().normalize()
        return pd.DataFrame([
            {
                "news_id": "P001", "stock_code": "03690", "ticker": "3690.HK",
                "category": "placing",
                "announced_at": today - pd.Timedelta(days=10),
                "date": today - pd.Timedelta(days=10),
                "title": "COMPLETION OF TOP-UP PLACING OF NEW SHARES",
                "subcats": "Announcements and Notices - [Placing]",
            },
        ])

    def test_tape_has_expected_categories(self):
        from engine.hk_filing_bus import build_tape
        tape = build_tape(self._make_filing_store(), self._make_placement_store())
        cats = set(tape["category"].tolist())
        # results: final_results → "results"
        assert "results" in cats
        # buyback
        assert "buyback" in cats

    def test_results_row_no_flags(self):
        from engine.hk_filing_bus import build_tape
        tape = build_tape(self._make_filing_store(), pd.DataFrame())
        results_rows = tape[tape["category"] == "results"]
        assert len(results_rows) > 0
        assert not results_rows["dilution_flag"].any()
        assert not results_rows["buyback_flag"].any()

    def test_buyback_row_flagged_correctly(self):
        from engine.hk_filing_bus import build_tape
        tape = build_tape(self._make_filing_store(), pd.DataFrame())
        buyback_rows = tape[tape["category"] == "buyback"]
        assert len(buyback_rows) > 0
        assert buyback_rows["buyback_flag"].all()
        assert not buyback_rows["dilution_flag"].any()

    def test_mandate_placement_dilution_flag(self):
        from engine.hk_filing_bus import build_tape
        tape = build_tape(self._make_filing_store(), self._make_placement_store())
        dilutive = tape[tape["dilution_flag"]]
        assert len(dilutive) > 0, "Expected dilutive rows from mandate/placement"
        assert not dilutive["buyback_flag"].any(), \
            "dilution_flag and buyback_flag must never both be True"

    def test_dedup_on_news_id_stock_code(self):
        from engine.hk_filing_bus import build_tape
        fdf = self._make_filing_store()
        # Add duplicate row (same news_id, stock_code)
        dup = fdf.iloc[[0]].copy()
        fdf_dup = pd.concat([fdf, dup], ignore_index=True)
        tape = build_tape(fdf_dup, pd.DataFrame())
        # After dedup, should have the same count as without duplicate
        tape_orig = build_tape(fdf, pd.DataFrame())
        assert len(tape) == len(tape_orig)

    def test_window_filter_excludes_old_events(self):
        from engine.hk_filing_bus import build_tape
        today = pd.Timestamp.today().normalize()
        old_fdf = pd.DataFrame([{
            "news_id": "OLD1", "stock_code": "00700", "ticker": "0700.HK",
            "category": "final_results",
            "announced_at": today - pd.Timedelta(days=200),
            "date": today - pd.Timedelta(days=200),
            "title": "VERY OLD RESULTS",
            "subcats": "",
        }])
        tape = build_tape(old_fdf, pd.DataFrame(), window_days=90)
        # Row from 200 days ago should be excluded
        assert len(tape) == 0, "Events older than window should be excluded"

    def test_empty_stores_return_empty_tape(self):
        from engine.hk_filing_bus import build_tape
        tape = build_tape(pd.DataFrame(), pd.DataFrame())
        assert tape.empty or len(tape) == 0

    def test_title_hash_present(self):
        from engine.hk_filing_bus import build_tape
        tape = build_tape(self._make_filing_store(), pd.DataFrame())
        assert "title_hash" in tape.columns
        assert tape["title_hash"].notna().all()


# ---------------------------------------------------------------------------
# 5. Fail-open: missing/stale stores
# ---------------------------------------------------------------------------

class TestFailOpen:
    """Engine degrades gracefully when stores are missing or stale."""

    def test_run_returns_dict_when_no_store(self, tmp_path):
        from engine.hk_filing_bus import run
        snap = run(data_root=tmp_path)
        assert isinstance(snap, dict)
        assert snap["display_only"] is True
        # Banner should be set when data is dead
        assert snap.get("freshness") in ("dead", "stale", "slow", "fresh")

    def test_run_tape_is_list(self, tmp_path):
        from engine.hk_filing_bus import run
        snap = run(data_root=tmp_path)
        assert isinstance(snap["tape"], list)

    def test_run_bellwethers_is_list(self, tmp_path):
        from engine.hk_filing_bus import run
        snap = run(data_root=tmp_path)
        assert isinstance(snap["bellwethers"], list)

    def test_store_status_missing_returns_unavailable(self, tmp_path):
        from collectors.hk_hkexnews import store_status
        st = store_status(data_root=tmp_path)
        assert st["available"] is False

    def test_load_store_missing_returns_empty(self, tmp_path):
        from collectors.hk_hkexnews import load_store
        df = load_store(data_root=tmp_path)
        assert df.empty

    def test_run_never_raises(self, tmp_path):
        """Engine must never raise; even with a corrupted coverage file."""
        from engine.hk_filing_bus import run
        cov_path = tmp_path / "hk_filings" / "coverage.json"
        cov_path.parent.mkdir(parents=True, exist_ok=True)
        cov_path.write_text("NOT VALID JSON {{{{")
        snap = run(data_root=tmp_path)  # must not raise
        assert isinstance(snap, dict)


# ---------------------------------------------------------------------------
# 6. Ledger idempotency + CN_LANE gate
# ---------------------------------------------------------------------------

class TestLedger:
    """Forward ledger: idempotent append; gated by CN_LANE=asia."""

    def _make_tape(self) -> pd.DataFrame:
        today = pd.Timestamp.today().normalize()
        from engine.hk_filing_bus import _title_hash
        return pd.DataFrame([{
            "ticker": "0700.HK", "date": today, "category": "results",
            "title_en": "RESULTS ANNOUNCEMENT", "official_flag": True,
            "dilution_flag": False, "buyback_flag": False,
            "title_hash": _title_hash("RESULTS ANNOUNCEMENT"),
        }])

    def test_stamp_skipped_when_cn_lane_not_set(self, tmp_path, monkeypatch):
        from engine.hk_filing_bus import stamp_ledger, load_ledger
        monkeypatch.delenv("CN_LANE", raising=False)
        tape = self._make_tape()
        n = stamp_ledger(tape, data_root=tmp_path)
        assert n == 0
        assert load_ledger(data_root=tmp_path) == []

    def test_stamp_appends_when_cn_lane_asia(self, tmp_path, monkeypatch):
        from engine.hk_filing_bus import stamp_ledger, load_ledger
        monkeypatch.setenv("CN_LANE", "asia")
        tape = self._make_tape()
        n = stamp_ledger(tape, data_root=tmp_path)
        assert n == 1
        rows = load_ledger(data_root=tmp_path)
        assert len(rows) == 1
        assert rows[0]["ticker"] == "0700.HK"
        assert rows[0]["category"] == "results"

    def test_stamp_idempotent(self, tmp_path, monkeypatch):
        from engine.hk_filing_bus import stamp_ledger, load_ledger
        monkeypatch.setenv("CN_LANE", "asia")
        tape = self._make_tape()
        n1 = stamp_ledger(tape, data_root=tmp_path)
        n2 = stamp_ledger(tape, data_root=tmp_path)   # same tape again
        assert n1 == 1
        assert n2 == 0, "Second stamp of same row should be idempotent (0 new rows)"
        rows = load_ledger(data_root=tmp_path)
        assert len(rows) == 1, "Ledger must not grow on duplicate stamp"

    def test_ledger_key_includes_title_hash(self, tmp_path, monkeypatch):
        """Two events on the same ticker/date/category but different title → two rows."""
        from engine.hk_filing_bus import stamp_ledger, load_ledger, _title_hash
        monkeypatch.setenv("CN_LANE", "asia")
        today = pd.Timestamp.today().normalize()
        tape = pd.DataFrame([
            {
                "ticker": "9988.HK", "date": today, "category": "buyback",
                "title_en": "FIRST BUYBACK UPDATE", "official_flag": True,
                "dilution_flag": False, "buyback_flag": True,
                "title_hash": _title_hash("FIRST BUYBACK UPDATE"),
            },
            {
                "ticker": "9988.HK", "date": today, "category": "buyback",
                "title_en": "SECOND BUYBACK ANNOUNCEMENT", "official_flag": True,
                "dilution_flag": False, "buyback_flag": True,
                "title_hash": _title_hash("SECOND BUYBACK ANNOUNCEMENT"),
            },
        ])
        n = stamp_ledger(tape, data_root=tmp_path)
        assert n == 2
        rows = load_ledger(data_root=tmp_path)
        assert len(rows) == 2

    def test_ledger_written_atomically(self, tmp_path, monkeypatch):
        """Atomic write: no .tmp files left after successful stamp."""
        from engine.hk_filing_bus import stamp_ledger
        monkeypatch.setenv("CN_LANE", "asia")
        stamp_ledger(self._make_tape(), data_root=tmp_path)
        ledger_dir = tmp_path / "hk_impulse"
        tmp_files = list(ledger_dir.glob(".filing_ledger_tmp_*"))
        assert len(tmp_files) == 0, f"Temp files left after stamp: {tmp_files}"


# ---------------------------------------------------------------------------
# 7. git status clean — all writes MUST go to tmp_path
# ---------------------------------------------------------------------------

class TestGitClean:
    """Verify that no tests write to the real data/ directory."""

    def test_no_real_data_writes(self, tmp_path, monkeypatch):
        """Run a full engine + stamp cycle; git status must remain clean."""
        import subprocess
        from engine.hk_filing_bus import run, stamp_ledger, build_tape

        # Run engine with tmp_path (no network; stores empty → fail-open)
        snap = run(data_root=tmp_path)
        assert isinstance(snap, dict)

        # Run stamp with CN_LANE=asia but tmp_path
        monkeypatch.setenv("CN_LANE", "asia")
        tape = build_tape(pd.DataFrame(), pd.DataFrame())
        stamp_ledger(tape, data_root=tmp_path)

        # Check git status in the worktree — must be clean
        repo_root = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_root), capture_output=True, text=True
        )
        dirty = [
            line for line in result.stdout.splitlines()
            if "hk_filings" in line or "hk_impulse/filing_ledger" in line
        ]
        assert not dirty, (
            f"git status shows unexpected dirty files after test:\n"
            + "\n".join(dirty)
        )
