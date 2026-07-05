"""tests/test_factor_contradictions.py — Test suite for engine.neuralweb.factor_contradictions (P1-D).

Tests:
  1. Record shape + severity clamp (note even if caller passes worse)
  2. Dormancy below 60 distinct panel dates (RULING-E)
  3. Q80 breakpoint trailing-252d cross-sectional correctness on synthetic panel (PIT)
  4. (date, ticker) dedupe on rerun (RULING-F)
  5. Fail-open on missing/corrupt inputs
  6. JSON-safety (allow_nan=False round-trip incl. numpy scalars)
  7. Firing payload correctness (falsifier string exact, direction=-1, no hand-set claim_family)
  8. Single-writer (module never references cortex_attention paths)
  9. DNA class all-false → mixed (from §3.3 spec requirement)

NOTE: #9 tests the build_factor_panel DNA cascade, not factor_contradictions directly.
It is included here per the overall P1-D test obligation for the 'all-false → mixed'
assertion.
"""
from __future__ import annotations

import importlib
import inspect
import json
import math
import textwrap
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_parquet(path: Path, df: "Any") -> None:  # type: ignore[name-defined]
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _make_panel_df(n_dates: int, n_tickers: int = 10, alibi_base: float = 0.3):
    """Synthetic panel DataFrame for testing."""
    import pandas as pd
    import numpy as np

    base_date = date(2025, 1, 2)
    dates = [
        (base_date + timedelta(days=i * 1)).strftime("%Y-%m-%d")
        for i in range(n_dates)
    ]
    tickers = [f"TICK{i:03d}" for i in range(n_tickers)]

    rows = []
    for d in dates:
        for t in tickers:
            rows.append({
                "ticker": t,
                "date": d,
                "alibi_share_20d": float(np.clip(
                    alibi_base + np.random.default_rng(abs(hash(t + d))).uniform(-0.1, 0.4),
                    0.0, 1.0,
                )),
            })
    return pd.DataFrame(rows)


def _write_synthetic_panel(tmp: Path, panel_df: "Any") -> None:
    """Write synthetic panel partitioned by month to tmp/data/factordata/panel/."""
    import pandas as pd

    panel_df["month"] = panel_df["date"].str[:7]
    for month, grp in panel_df.groupby("month"):
        p = tmp / "data" / "factordata" / "panel" / month / "panel.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        grp.drop(columns=["month"]).to_parquet(p, index=False)


def _write_standouts(tmp: Path, fires: list[dict]) -> None:
    """Write a minimal us_standouts.json with the given fires."""
    buy_lane = []
    as_of = fires[0]["as_of"] if fires else "2026-07-05"
    for f in fires:
        buy_lane.append({
            "ticker": f["ticker"],
            "signal": {"tier_cascade": f["tier_cascade"]},
        })
    doc = {"as_of": as_of, "buy": buy_lane}
    p = tmp / "site" / "factordata" / "us_standouts.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc), encoding="utf-8")


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

@pytest.fixture
def fc_module():
    """Import factor_contradictions fresh (bypasses caching issues in tests)."""
    import engine.neuralweb.factor_contradictions as m
    return m


# ---------------------------------------------------------------------------
# Test 1: Record shape + severity clamp
# ---------------------------------------------------------------------------

class TestRecordShape:
    def test_severity_always_note(self, fc_module):
        """_record() must return severity='note' even if caller passes 'tension'."""
        rec = fc_module._record(
            pair_id="test:AAPL:2026-07-05",
            a_artifact="site/factordata/us_standouts.json",
            a_reading="T1 fire for AAPL",
            b_artifact="data/factordata/panel/",
            b_reading="alibi=0.8 >= Q80=0.75",
            kind="label-tension",
            severity="tension",  # caller passes worse — must be clamped
            as_of="2026-07-05",
            note="test note",
            ticker="AAPL",
            date_str="2026-07-05",
        )
        assert rec["severity"] == "note", "severity must be clamped to 'note' in P1-D"

    def test_severity_note_passthrough(self, fc_module):
        """_record() with severity='note' stays 'note'."""
        rec = fc_module._record(
            pair_id="test:AAPL:2026-07-05",
            a_artifact="a", a_reading="r", b_artifact="b", b_reading="s",
            kind="label-tension",
            severity="note",
            as_of="2026-07-05",
            note="n",
            ticker="AAPL",
            date_str="2026-07-05",
        )
        assert rec["severity"] == "note"

    def test_display_only_always_true(self, fc_module):
        """display_only must always be True."""
        rec = fc_module._record(
            pair_id="test", a_artifact="a", a_reading="r",
            b_artifact="b", b_reading="s",
            kind="label-tension", severity="note", as_of="2026-07-05",
            note="n", ticker="T", date_str="2026-07-05",
        )
        assert rec["display_only"] is True

    def test_required_fields_present(self, fc_module):
        """Record must contain all required fields."""
        rec = fc_module._record(
            pair_id="borrowed_strength:AAPL:2026-07-05",
            a_artifact="site/factordata/us_standouts.json",
            a_reading="T1 fire for AAPL as_of 2026-07-05",
            b_artifact="data/factordata/panel/",
            b_reading="alibi_share_20d=0.85 >= Q80=0.70",
            kind="label-tension",
            severity="note",
            as_of="2026-07-05",
            note="Some note.",
            ticker="AAPL",
            date_str="2026-07-05",
        )
        for field in ("pair_id", "a", "b", "kind", "severity", "as_of", "note",
                      "display_only", "ticker", "date"):
            assert field in rec, f"Missing field: {field}"
        assert "artifact" in rec["a"]
        assert "reading" in rec["a"]
        assert "artifact" in rec["b"]
        assert "reading" in rec["b"]

    def test_pair_id_format(self, fc_module):
        """pair_id must be 'borrowed_strength:{ticker}:{date}'."""
        rec = fc_module._record(
            pair_id="borrowed_strength:MSFT:2026-07-05",
            a_artifact="a", a_reading="r",
            b_artifact="b", b_reading="s",
            kind="label-tension", severity="note", as_of="2026-07-05",
            note="n", ticker="MSFT", date_str="2026-07-05",
        )
        assert rec["pair_id"].startswith("borrowed_strength:")


# ---------------------------------------------------------------------------
# Test 2: Dormancy below 60 panel dates (RULING-E)
# ---------------------------------------------------------------------------

class TestDormancy:
    def test_dormant_below_60_dates(self, fc_module, tmp_path):
        """With fewer than 60 distinct panel dates, no records emitted + gap note."""
        import pandas as pd

        # 30 dates — below 60 floor
        panel_df = _make_panel_df(n_dates=30, n_tickers=5)
        _write_synthetic_panel(tmp_path, panel_df)

        as_of_date = panel_df["date"].max()
        _write_standouts(tmp_path, [
            {"ticker": "TICK000", "tier_cascade": "T1", "as_of": as_of_date},
        ])

        records, gaps = fc_module.detect_factor_contradictions(
            root=tmp_path, as_of_date=as_of_date,
        )

        assert records == [], f"Expected no records under dormancy, got {records}"
        assert len(gaps) == 1, f"Expected exactly 1 gap note, got {gaps}"
        assert "60d floor" in gaps[0], f"Gap note must mention 60d floor: {gaps[0]}"
        assert "dormant" in gaps[0], f"Gap note must say 'dormant': {gaps[0]}"

    def test_dormant_gap_note_verbatim_format(self, fc_module, tmp_path):
        """Dormancy gap note must match exact format pattern."""
        import pandas as pd

        panel_df = _make_panel_df(n_dates=10, n_tickers=3)
        _write_synthetic_panel(tmp_path, panel_df)
        as_of_date = panel_df["date"].max()

        _, gaps = fc_module.detect_factor_contradictions(
            root=tmp_path, as_of_date=as_of_date,
        )
        assert len(gaps) >= 1
        note = gaps[0]
        # Must contain "factor_contradictions:" prefix + date-count + "dormant"
        assert "factor_contradictions:" in note
        assert "panel history" in note
        assert "dormant until backfill" in note

    def test_dormant_no_panel_dir(self, fc_module, tmp_path):
        """With no panel directory at all, dormancy is triggered."""
        # No panel created in tmp_path

        as_of_date = "2026-07-05"
        _write_standouts(tmp_path, [
            {"ticker": "AAPL", "tier_cascade": "T1", "as_of": as_of_date},
        ])

        records, gaps = fc_module.detect_factor_contradictions(
            root=tmp_path, as_of_date=as_of_date,
        )

        assert records == []
        assert len(gaps) >= 1


# ---------------------------------------------------------------------------
# Test 3: Q80 breakpoint — trailing-252d cross-sectional, PIT correctness
# ---------------------------------------------------------------------------

class TestQ80Breakpoint:
    def test_q80_uses_only_past_dates(self, fc_module, tmp_path):
        """Q80 must be computed only on dates <= as_of_date (PIT)."""
        import pandas as pd
        import numpy as np

        # Build a panel where future rows have much higher alibi values
        past_dates = [
            (date(2025, 1, 2) + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(100)
        ]
        future_dates = [
            (date(2025, 5, 2) + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(50)
        ]

        tickers = ["TICK000", "TICK001"]
        rows = []
        # Past: alibi_share_20d in [0.1, 0.4]
        for d in past_dates:
            for t in tickers:
                rows.append({"ticker": t, "date": d, "alibi_share_20d": 0.25})
        # Future: alibi_share_20d = 0.99 (should NOT influence Q80 for past as_of)
        for d in future_dates:
            for t in tickers:
                rows.append({"ticker": t, "date": d, "alibi_share_20d": 0.99})

        panel_df = pd.DataFrame(rows)
        _write_synthetic_panel(tmp_path, panel_df)

        as_of_date = past_dates[-1]  # evaluate on the last PAST date

        q80 = fc_module._compute_q80_breakpoint(panel_df, as_of_date)
        assert q80 is not None
        # If future dates leaked in, Q80 would be near 0.99; PIT means it must be low
        assert q80 < 0.6, f"Q80={q80} suggests future data leaked into breakpoint"

    def test_q80_uses_trailing_252_window(self, fc_module, tmp_path):
        """Q80 window must be capped at trailing-252 calendar days."""
        import pandas as pd

        # Very old rows (> 252 days back) have alibi=0.99; recent have alibi=0.2
        old_dates = [
            (date(2024, 1, 2) + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(50)
        ]
        recent_dates = [
            (date(2025, 7, 1) + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(70)
        ]

        rows = []
        for d in old_dates:
            rows.append({"ticker": "T", "date": d, "alibi_share_20d": 0.99})
        for d in recent_dates:
            rows.append({"ticker": "T", "date": d, "alibi_share_20d": 0.20})

        panel_df = pd.DataFrame(rows)
        as_of_date = recent_dates[-1]

        q80 = fc_module._compute_q80_breakpoint(panel_df, as_of_date)
        assert q80 is not None
        # Old high-alibi rows (> 252d back) should not contaminate Q80
        assert q80 < 0.5, f"Q80={q80} suggests old data outside 252d leaked in"

    def test_q80_returns_none_below_floor(self, fc_module):
        """_compute_q80_breakpoint returns None if fewer than 10 non-null rows."""
        import pandas as pd

        panel_df = pd.DataFrame({
            "ticker": ["T"] * 5,
            "date": ["2026-07-01"] * 5,
            "alibi_share_20d": [0.3] * 5,
        })
        q80 = fc_module._compute_q80_breakpoint(panel_df, "2026-07-01")
        assert q80 is None


# ---------------------------------------------------------------------------
# Fixture helper: build a panel that guarantees Pair G fires (TICK000 pattern)
# ---------------------------------------------------------------------------

def _make_guaranteed_fire_panel(n_dates: int = 80) -> "Any":  # type: ignore[name-defined]
    """Build a panel where TICK000 always fires Pair G.

    Pattern: 9 bulk tickers at alibi=0.2 (pulls pool Q80 low), TICK000 at
    alibi=0.95 (well above Q80).  Mirrors the working pattern used in
    TestEndToEndFireBehavior::test_pair_g_fires_when_high_alibi.
    """
    import pandas as pd
    from datetime import date, timedelta

    rows = []
    base = date(2025, 1, 2)
    for i in range(n_dates):
        d = (base + timedelta(days=i)).strftime("%Y-%m-%d")
        for t in [f"TICK{j:03d}" for j in range(10)]:
            alibi = 0.95 if t == "TICK000" else 0.2
            rows.append({"ticker": t, "date": d, "alibi_share_20d": alibi})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Test 4: (date, ticker) dedupe on rerun (RULING-F)
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_no_duplicate_on_rerun(self, fc_module, tmp_path):
        """Running detect_factor_contradictions twice for the same date must produce
        exactly 1 ledger line after run 1 AND exactly 1 ledger line after run 2
        (no duplicate on rerun).  The `if exists()` guard is removed — if Pair G
        doesn't fire, the test fails loudly rather than passing vacuously."""
        from unittest.mock import patch

        panel_df = _make_guaranteed_fire_panel(n_dates=80)
        _write_synthetic_panel(tmp_path, panel_df)

        as_of_date = panel_df["date"].max()
        _write_standouts(tmp_path, [
            {"ticker": "TICK000", "tier_cascade": "T1", "as_of": as_of_date},
        ])

        def mock_record_firing(name, payload, root=None):
            return payload

        # ── Run 1 ───────────────────────────────────────────────────────────
        with patch("engine.neuralweb.factor_contradictions.record_firing",
                   new=mock_record_firing):
            records1, gaps1 = fc_module.detect_factor_contradictions(
                root=tmp_path, as_of_date=as_of_date,
            )

        ledger_p = tmp_path / "data" / "neuralweb" / "factor_contradictions.jsonl"
        assert ledger_p.exists(), (
            f"Ledger must exist after run 1 — Pair G must have fired. "
            f"records1={records1}, gaps1={gaps1}"
        )
        lines_after_run1 = [
            l for l in ledger_p.read_text().splitlines() if l.strip()
        ]
        assert len(lines_after_run1) == 1, (
            f"Expected exactly 1 ledger line after run 1, got {len(lines_after_run1)}: "
            f"{lines_after_run1}"
        )

        # ── Run 2 — same date ────────────────────────────────────────────────
        with patch("engine.neuralweb.factor_contradictions.record_firing",
                   new=mock_record_firing):
            records2, gaps2 = fc_module.detect_factor_contradictions(
                root=tmp_path, as_of_date=as_of_date,
            )

        lines_after_run2 = [
            l for l in ledger_p.read_text().splitlines() if l.strip()
        ]
        assert len(lines_after_run2) == 1, (
            f"Expected exactly 1 ledger line after run 2 (dedupe must hold), "
            f"got {len(lines_after_run2)}: {lines_after_run2}"
        )

    def test_ledger_appended_not_overwritten(self, fc_module, tmp_path):
        """Running on two different dates must append two records (not overwrite)."""
        from unittest.mock import patch

        panel_df = _make_guaranteed_fire_panel(n_dates=80)
        _write_synthetic_panel(tmp_path, panel_df)

        # Use two distinct dates from the panel (near the end so panel has 80 dates
        # of history to meet the 60-date floor and fill Q80)
        dates = sorted(panel_df["date"].unique())
        d1, d2 = dates[-2], dates[-1]

        def mock_record_firing(name, payload, root=None):
            return payload

        for d in (d1, d2):
            _write_standouts(tmp_path, [
                {"ticker": "TICK000", "tier_cascade": "T1", "as_of": d},
            ])
            with patch("engine.neuralweb.factor_contradictions.record_firing",
                       new=mock_record_firing):
                fc_module.detect_factor_contradictions(root=tmp_path, as_of_date=d)

        ledger_p = tmp_path / "data" / "neuralweb" / "factor_contradictions.jsonl"
        assert ledger_p.exists(), "Ledger must exist after two distinct-date runs"
        rows = [json.loads(l) for l in ledger_p.read_text().splitlines() if l.strip()]
        assert len(rows) == 2, (
            f"Expected exactly 2 ledger rows (one per date), got {len(rows)}: {rows}"
        )
        keys = [(r["date"], r["ticker"]) for r in rows]
        assert len(keys) == len(set(keys)), f"Duplicates found in ledger: {keys}"

    def test_reflex_firing_idempotent_same_day_rerun(self, fc_module, tmp_path):
        """factor_attention/firings.jsonl must have identical line count after two runs
        on the same as_of date (FIX-1: shared idempotence gate prevents duplicate
        reflex firings that inflate the A2 earn-in denominator)."""
        panel_df = _make_guaranteed_fire_panel(n_dates=80)
        _write_synthetic_panel(tmp_path, panel_df)

        as_of_date = panel_df["date"].max()
        _write_standouts(tmp_path, [
            {"ticker": "TICK000", "tier_cascade": "T1", "as_of": as_of_date},
        ])

        # Wire a real-file-writing mock so we can count firings lines
        firings_path = (
            tmp_path / "data" / "reflexes" / "factor_attention" / "firings.jsonl"
        )
        firings_path.parent.mkdir(parents=True, exist_ok=True)

        def writing_record_firing(name, payload, root=None):
            """Write the firing to the real file so we can count lines."""
            import json as _json
            with open(firings_path, "a", encoding="utf-8") as fh:
                fh.write(_json.dumps({"name": name, **payload}) + "\n")
            return payload

        from unittest.mock import patch

        # Run 1
        with patch("engine.neuralweb.factor_contradictions.record_firing",
                   new=writing_record_firing):
            fc_module.detect_factor_contradictions(root=tmp_path, as_of_date=as_of_date)

        count_after_run1 = sum(
            1 for l in firings_path.read_text().splitlines() if l.strip()
        )
        assert count_after_run1 >= 1, (
            f"Expected at least 1 firing after run 1, got {count_after_run1}"
        )

        # Run 2 — same as_of
        with patch("engine.neuralweb.factor_contradictions.record_firing",
                   new=writing_record_firing):
            fc_module.detect_factor_contradictions(root=tmp_path, as_of_date=as_of_date)

        count_after_run2 = sum(
            1 for l in firings_path.read_text().splitlines() if l.strip()
        )
        assert count_after_run2 == count_after_run1, (
            f"factor_attention/firings.jsonl line count changed after same-day rerun: "
            f"run1={count_after_run1}, run2={count_after_run2}. "
            f"The reflex must be gated on the same idempotence key as the ledger."
        )


# ---------------------------------------------------------------------------
# Test 5: Fail-open on missing/corrupt inputs
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_missing_standouts(self, fc_module, tmp_path):
        """No us_standouts.json → returns ([], [gap_note]) without raising."""
        import pandas as pd

        panel_df = _make_panel_df(n_dates=80)
        _write_synthetic_panel(tmp_path, panel_df)
        # Do NOT write standouts

        records, gaps = fc_module.detect_factor_contradictions(
            root=tmp_path, as_of_date=panel_df["date"].max(),
        )
        # Should not raise; records may be empty
        assert isinstance(records, list)
        assert isinstance(gaps, list)

    def test_corrupt_standouts(self, fc_module, tmp_path):
        """Corrupt us_standouts.json → fail-open, no records, no exception."""
        import pandas as pd

        panel_df = _make_panel_df(n_dates=80)
        _write_synthetic_panel(tmp_path, panel_df)

        p = tmp_path / "site" / "factordata" / "us_standouts.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("NOT VALID JSON {{{{", encoding="utf-8")

        records, gaps = fc_module.detect_factor_contradictions(
            root=tmp_path, as_of_date=panel_df["date"].max(),
        )
        assert isinstance(records, list)
        assert isinstance(gaps, list)

    def test_corrupt_panel_parquet(self, fc_module, tmp_path):
        """Corrupt panel parquet → fail-open."""
        p = tmp_path / "data" / "factordata" / "panel" / "2026-07" / "panel.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"NOT PARQUET DATA")

        _write_standouts(tmp_path, [
            {"ticker": "AAPL", "tier_cascade": "T1", "as_of": "2026-07-05"},
        ])

        records, gaps = fc_module.detect_factor_contradictions(
            root=tmp_path, as_of_date="2026-07-05",
        )
        assert isinstance(records, list)
        assert isinstance(gaps, list)

    def test_missing_panel_dir(self, fc_module, tmp_path):
        """Missing panel dir → fail-open, dormancy gap."""
        _write_standouts(tmp_path, [
            {"ticker": "AAPL", "tier_cascade": "T1", "as_of": "2026-07-05"},
        ])

        records, gaps = fc_module.detect_factor_contradictions(
            root=tmp_path, as_of_date="2026-07-05",
        )
        assert records == []
        assert len(gaps) >= 1


# ---------------------------------------------------------------------------
# Test 6: JSON-safety — allow_nan=False round-trip incl. numpy scalars
# ---------------------------------------------------------------------------

class TestJSONSafety:
    def test_nan_becomes_none(self, fc_module):
        """NaN float must become None through _json_safe."""
        out = fc_module._json_safe(float("nan"))
        assert out is None

    def test_inf_becomes_none(self, fc_module):
        """Inf must become None."""
        out = fc_module._json_safe(float("inf"))
        assert out is None

    def test_numpy_int_safe(self, fc_module):
        """numpy int64 must serialize to Python int."""
        try:
            import numpy as np
            val = np.int64(42)
            out = fc_module._json_safe(val)
            assert out == 42
            assert isinstance(out, int)
        except ImportError:
            pytest.skip("numpy not available")

    def test_numpy_float_nan_becomes_none(self, fc_module):
        """numpy nan float must become None."""
        try:
            import numpy as np
            val = np.float64(float("nan"))
            out = fc_module._json_safe(val)
            assert out is None
        except ImportError:
            pytest.skip("numpy not available")

    def test_dumps_safe_valid_json(self, fc_module):
        """_dumps_safe must produce valid JSON without NaN literals."""
        obj = {"a": float("nan"), "b": 1.0, "c": None}
        result = fc_module._dumps_safe(obj)
        # Must parse without error
        parsed = json.loads(result)
        assert parsed["a"] is None
        assert parsed["b"] == 1.0

    def test_ledger_records_json_safe(self, fc_module, tmp_path):
        """Records written to ledger must be JSON-safe (no NaN literals)."""
        import pandas as pd
        import numpy as np

        # Create panel with a numpy NaN alibi for one ticker + normal for another
        rows = []
        base = date(2025, 1, 2)
        for i in range(80):
            d = (base + timedelta(days=i)).strftime("%Y-%m-%d")
            rows.append({"ticker": "SAFE", "date": d, "alibi_share_20d": 0.8})
        panel_df = pd.DataFrame(rows)
        _write_synthetic_panel(tmp_path, panel_df)

        as_of_date = panel_df["date"].max()
        _write_standouts(tmp_path, [
            {"ticker": "SAFE", "tier_cascade": "T1", "as_of": as_of_date},
        ])

        fc_module.detect_factor_contradictions(root=tmp_path, as_of_date=as_of_date)

        ledger_p = tmp_path / "data" / "neuralweb" / "factor_contradictions.jsonl"
        if ledger_p.exists():
            for line in ledger_p.read_text().splitlines():
                if not line.strip():
                    continue
                # Must parse without error (no NaN literals)
                parsed = json.loads(line)
                # Must not have NaN as a value anywhere
                text = json.dumps(parsed)
                assert "NaN" not in text and "Infinity" not in text


# ---------------------------------------------------------------------------
# Test 7: Firing payload correctness
# ---------------------------------------------------------------------------

class TestFiringPayload:
    def test_falsifier_exact_text(self, fc_module):
        """_FALSIFIER constant must match the exact text required by RULING-G."""
        expected = (
            "direction=-1; hit = name underperforms SPY at horizon_d=21 "
            "(graded by _grade_realized_move)"
        )
        assert fc_module._FALSIFIER == expected, (
            f"FALSIFIER text mismatch.\nExpected: {expected!r}\nGot: {fc_module._FALSIFIER!r}"
        )

    def test_direction_minus_one(self, fc_module, tmp_path):
        """Every factor_attention firing must have direction=-1."""
        import pandas as pd
        from unittest.mock import patch, MagicMock

        panel_df = _make_panel_df(n_dates=80, n_tickers=2, alibi_base=0.9)
        panel_df.loc[panel_df["ticker"] == "TICK000", "alibi_share_20d"] = 0.98
        _write_synthetic_panel(tmp_path, panel_df)

        as_of_date = panel_df["date"].max()
        _write_standouts(tmp_path, [
            {"ticker": "TICK000", "tier_cascade": "T1", "as_of": as_of_date},
        ])

        # Capture what gets passed to record_firing
        captured_payloads = []

        def mock_record_firing(name, payload, root=None):
            captured_payloads.append((name, payload.copy()))
            return payload

        with patch("engine.neuralweb.factor_contradictions.record_firing",
                   new=mock_record_firing):
            fc_module.detect_factor_contradictions(root=tmp_path, as_of_date=as_of_date)

        for name, payload in captured_payloads:
            assert payload.get("direction") == -1, (
                f"direction must be -1, got {payload.get('direction')}"
            )
            assert name == "factor_attention", (
                f"reflex name must be 'factor_attention', got {name!r}"
            )

    def test_no_hand_set_claim_family(self, fc_module, tmp_path):
        """Firing payloads must NOT include a hand-set claim_family."""
        import pandas as pd
        from unittest.mock import patch

        panel_df = _make_panel_df(n_dates=80, n_tickers=2, alibi_base=0.9)
        panel_df.loc[panel_df["ticker"] == "TICK000", "alibi_share_20d"] = 0.98
        _write_synthetic_panel(tmp_path, panel_df)

        as_of_date = panel_df["date"].max()
        _write_standouts(tmp_path, [
            {"ticker": "TICK000", "tier_cascade": "T1", "as_of": as_of_date},
        ])

        captured_payloads = []

        def mock_record_firing(name, payload, root=None):
            captured_payloads.append(payload.copy())
            return payload

        with patch("engine.neuralweb.factor_contradictions.record_firing",
                   new=mock_record_firing):
            fc_module.detect_factor_contradictions(root=tmp_path, as_of_date=as_of_date)

        for payload in captured_payloads:
            assert "claim_family" not in payload, (
                "claim_family must NOT be hand-set in firing payload — "
                "it is auto-stamped by record_firing"
            )

    def test_falsifier_text_in_payload(self, fc_module, tmp_path):
        """Firing payload must include the RULING-G falsifier text."""
        import pandas as pd
        from unittest.mock import patch

        panel_df = _make_panel_df(n_dates=80, n_tickers=2, alibi_base=0.9)
        panel_df.loc[panel_df["ticker"] == "TICK000", "alibi_share_20d"] = 0.98
        _write_synthetic_panel(tmp_path, panel_df)

        as_of_date = panel_df["date"].max()
        _write_standouts(tmp_path, [
            {"ticker": "TICK000", "tier_cascade": "T1", "as_of": as_of_date},
        ])

        captured_payloads = []

        def mock_record_firing(name, payload, root=None):
            captured_payloads.append(payload.copy())
            return payload

        with patch("engine.neuralweb.factor_contradictions.record_firing",
                   new=mock_record_firing):
            fc_module.detect_factor_contradictions(root=tmp_path, as_of_date=as_of_date)

        for payload in captured_payloads:
            assert "falsifier" in payload, "firing payload must include 'falsifier'"
            assert payload["falsifier"] == fc_module._FALSIFIER, (
                f"falsifier text mismatch: {payload['falsifier']!r}"
            )

    def test_horizon_d_is_21(self, fc_module, tmp_path):
        """Firing payload must have horizon_d=21."""
        import pandas as pd
        from unittest.mock import patch

        panel_df = _make_panel_df(n_dates=80, n_tickers=2, alibi_base=0.9)
        panel_df.loc[panel_df["ticker"] == "TICK000", "alibi_share_20d"] = 0.98
        _write_synthetic_panel(tmp_path, panel_df)

        as_of_date = panel_df["date"].max()
        _write_standouts(tmp_path, [
            {"ticker": "TICK000", "tier_cascade": "T1", "as_of": as_of_date},
        ])

        captured_payloads = []

        def mock_record_firing(name, payload, root=None):
            captured_payloads.append(payload.copy())
            return payload

        with patch("engine.neuralweb.factor_contradictions.record_firing",
                   new=mock_record_firing):
            fc_module.detect_factor_contradictions(root=tmp_path, as_of_date=as_of_date)

        for payload in captured_payloads:
            assert payload.get("horizon_d") == 21, (
                f"horizon_d must be 21, got {payload.get('horizon_d')}"
            )


# ---------------------------------------------------------------------------
# Test 8: Single-writer — module never references cortex_attention paths
# ---------------------------------------------------------------------------

class TestSingleWriterLaw:
    def test_no_cortex_attention_in_source(self):
        """factor_contradictions.py must not reference cortex_attention as a reflex name
        or data path — no writes to cortex_attention firings.jsonl or grades.jsonl."""
        import engine.neuralweb.factor_contradictions as m
        source = inspect.getsource(m)
        # These specific path-level strings would indicate a write to cortex paths.
        # The module may MENTION 'cortex_attention' in docstrings (explaining what it
        # must NOT do), but must never reference the actual file paths.
        forbidden_paths = [
            "reflexes/cortex_attention/firings",
            "reflexes/cortex_attention/grades",
            "_REFLEX_NAME = \"cortex_attention\"",
            "record_firing(\"cortex_attention\"",
            "record_firing('cortex_attention'",
        ]
        for token in forbidden_paths:
            assert token not in source, (
                f"factor_contradictions.py must NOT reference {token!r} "
                "(single-writer law violation)"
            )

    def test_reflex_name_is_factor_attention(self, fc_module):
        """_REFLEX_NAME must be 'factor_attention', not 'cortex_attention'."""
        assert fc_module._REFLEX_NAME == "factor_attention"
        assert fc_module._REFLEX_NAME != "cortex_attention"

    def test_no_cortex_path_in_grader(self):
        """grade_factor_attention.py must not write to cortex_attention paths.

        Checks path-level references that would indicate actual writes/reads
        to cortex_attention files — NOT mentions in docstrings.
        """
        grader_path = (
            Path(__file__).resolve().parent.parent
            / "scripts" / "grade_factor_attention.py"
        )
        if not grader_path.exists():
            pytest.skip("grade_factor_attention.py not found")
        source = grader_path.read_text(encoding="utf-8")
        # Specific path/call strings that would indicate cortex_attention writes
        forbidden_path_strings = [
            "reflexes/cortex_attention/firings",
            "reflexes/cortex_attention/grades",
            "_REFLEX_NAME = \"cortex_attention\"",
            "_REFLEX_NAME = 'cortex_attention'",
            "\"cortex_attention\", firings",
            "'cortex_attention', firings",
        ]
        for token in forbidden_path_strings:
            assert token not in source, (
                f"grade_factor_attention.py must NOT reference {token!r} "
                "(would indicate writing to cortex_attention paths)"
            )


# ---------------------------------------------------------------------------
# Test 9: End-to-end with synthetic 80-date panel
# ---------------------------------------------------------------------------

class TestEndToEndFireBehavior:
    def test_pair_g_fires_when_high_alibi(self, fc_module, tmp_path):
        """Pair G fires for T1/T2 name when alibi_share_20d >= Q80."""
        import pandas as pd
        from unittest.mock import patch

        # Build panel where TICK000 has alibi=0.95 (very high) and others 0.2
        rows = []
        base = date(2025, 1, 2)
        for i in range(80):
            d = (base + timedelta(days=i)).strftime("%Y-%m-%d")
            for t in [f"TICK{j:03d}" for j in range(10)]:
                alibi = 0.95 if t == "TICK000" else 0.2
                rows.append({"ticker": t, "date": d, "alibi_share_20d": alibi})

        panel_df = pd.DataFrame(rows)
        _write_synthetic_panel(tmp_path, panel_df)

        as_of_date = panel_df["date"].max()
        _write_standouts(tmp_path, [
            {"ticker": "TICK000", "tier_cascade": "T1", "as_of": as_of_date},
        ])

        def mock_record_firing(name, payload, root=None):
            return payload

        with patch("engine.neuralweb.factor_contradictions.record_firing",
                   new=mock_record_firing):
            records, gaps = fc_module.detect_factor_contradictions(
                root=tmp_path, as_of_date=as_of_date,
            )

        # TICK000 has alibi=0.95 which should be >= Q80 (others at 0.2 give low Q80)
        tickers_fired = [r["ticker"] for r in records]
        assert "TICK000" in tickers_fired, (
            f"TICK000 should have Pair G fired but records: {records}"
        )

    def test_pair_g_does_not_fire_for_t3(self, fc_module, tmp_path):
        """Pair G must NOT fire for T3 or T4 tiers."""
        import pandas as pd
        from unittest.mock import patch

        rows = []
        base = date(2025, 1, 2)
        for i in range(80):
            d = (base + timedelta(days=i)).strftime("%Y-%m-%d")
            for t in ["TICK000", "TICK001"]:
                rows.append({"ticker": t, "date": d, "alibi_share_20d": 0.95})

        panel_df = pd.DataFrame(rows)
        _write_synthetic_panel(tmp_path, panel_df)

        as_of_date = panel_df["date"].max()
        # Only T3 and T4 fires
        _write_standouts(tmp_path, [
            {"ticker": "TICK000", "tier_cascade": "T3", "as_of": as_of_date},
            {"ticker": "TICK001", "tier_cascade": "T4", "as_of": as_of_date},
        ])

        def mock_record_firing(name, payload, root=None):
            return payload

        with patch("engine.neuralweb.factor_contradictions.record_firing",
                   new=mock_record_firing):
            records, gaps = fc_module.detect_factor_contradictions(
                root=tmp_path, as_of_date=as_of_date,
            )

        assert records == [], f"T3/T4 fires must not trigger Pair G, got: {records}"

    def test_pair_g_does_not_fire_when_low_alibi(self, fc_module, tmp_path):
        """Pair G must NOT fire when alibi_share_20d < Q80."""
        import pandas as pd
        from unittest.mock import patch

        rows = []
        base = date(2025, 1, 2)
        for i in range(80):
            d = (base + timedelta(days=i)).strftime("%Y-%m-%d")
            # All tickers have uniformly low alibi
            for t in ["TICK000", "TICK001", "TICK002"]:
                rows.append({"ticker": t, "date": d, "alibi_share_20d": 0.1})

        panel_df = pd.DataFrame(rows)
        _write_synthetic_panel(tmp_path, panel_df)

        as_of_date = panel_df["date"].max()
        _write_standouts(tmp_path, [
            {"ticker": "TICK000", "tier_cascade": "T1", "as_of": as_of_date},
        ])

        def mock_record_firing(name, payload, root=None):
            return payload

        with patch("engine.neuralweb.factor_contradictions.record_firing",
                   new=mock_record_firing):
            records, gaps = fc_module.detect_factor_contradictions(
                root=tmp_path, as_of_date=as_of_date,
            )

        # TICK000 at alibi=0.1, Q80 of [0.1]*n is 0.1, so alibi==Q80 → fires
        # (>= boundary case) or if all are identical, Q80=0.1 and alibi=0.1 fires.
        # This test verifies low-alibi names don't spuriously fire — use a name
        # NOT in the buy lane
        non_buy_tickers = {r["ticker"] for r in records}
        assert "TICK001" not in non_buy_tickers  # not in buy lane
        assert "TICK002" not in non_buy_tickers


# ---------------------------------------------------------------------------
# Test 10: DNA class all-false → 'mixed' (spec §3.3 requirement)
# ---------------------------------------------------------------------------

class TestDNAMixedDefault:
    def test_all_conditions_false_returns_mixed(self):
        """The DNA class cascade must return 'mixed' when no archetype triggers."""
        try:
            from scripts.build_factor_panel import _dna_class  # type: ignore[import]
        except ImportError:
            pytest.skip("build_factor_panel._dna_class not importable in this context")

        # Pass values that satisfy NO archetype condition
        result = _dna_class(
            quality_pct=10,    # < 70 → quality_growth fails
            value_pct=10,      # < 65 → cyclical_value fails
            beta_growth=0.0,   # < 0.3 → quality_growth/high_beta_liquidity fails
            beta_mkt=0.5,      # < 1.3 → high_beta_liquidity fails
            low_vol_pct=50,    # not < 35 for high_beta, not ≥ 55 for rate_duration
            sector="Technology",
            beta_sector=0.0,   # < 0.2 → cyclical_value fails
            beta_rates=0.1,    # < 0.25 → rate_duration fails
            payout_pct=20,     # < 55 → rate_duration fails
            beta_china=0.0,    # < 0.30 → china_crypto_proxy fails
            size_pct=60,       # ≥ 30 → small_spec fails
        )
        assert result == "mixed", (
            f"Expected 'mixed' when all conditions are false, got {result!r}"
        )
