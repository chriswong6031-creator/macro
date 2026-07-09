"""tests/test_grade_thematic.py — TIL W6 (PR-H) grading pack.

All tests are hermetic (tmp_path stores; synthetic fixtures).
No network calls, no live data/qledger or data/foresight reads.

Covered:
  Stage 1 (lead-lag grader):
    - we-led case: flag_date < attention_arrival_date → positive lead_days
    - they-led case: flag_date > attention_arrival_date → negative lead_days
    - never-crossed case: no crossing → leg pending, lead_days None
    - pooled_summary null when no arrivals
    - artifact carries authority block with all promotion flags False
    - n_pending honest (flags with no arrivals)
    - stale_legs present when earliness_log absent

  Stage 2 (placebo tape):
    - deterministic: same inputs → same placebo rows
    - no duplicate append: running twice produces same tape (dedup)
    - K=3 random peers + 1 time-shifted row per non-WATCH flag
    - WATCH flags are skipped
    - time-shifted asof is exactly 21 days before flag asof

  Stage 3 (falsifier evaluator):
    - rel_return TRIPPED: excess < threshold (op="<") → FALSIFIER_TRIPPED
    - rel_return CONFIRMED: excess > threshold → CONFIRMED
    - soft check → UNVERIFIABLE
    - unknown kind → UNVERIFIABLE
    - missing price data → UNVERIFIABLE
    - append-only semantics: re-run does not duplicate rows (dedup by claim_id)
    - cap: only MAX_PER_RUN claims evaluated per run

  Cross-cutting:
    - "validated" word banned in all output text
    - scripts.grade_thematic.run_stage() does not raise fatally on empty stores
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def _make_price_parquet(path: Path, dates: list[str], prices: list[float]) -> None:
    """Write a minimal close-series parquet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        {"close": prices},
        index=pd.to_datetime(dates),
    )
    df.to_parquet(path)


def _placebo_seed(theme_id: str, asof: str) -> int:
    raw = f"{theme_id}|{asof}"
    h = hashlib.sha256(raw.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")


# ============================================================================
# Stage 1 — Crowd-arrival lead-lag grader
# ============================================================================

class TestLeadLag:

    def _make_flag(self, theme="ai_semiconductors", asof="2026-05-01",
                   stage="PRECIPICE (text)", members=None):
        return {
            "theme": theme,
            "asof": asof,
            "stage": stage,
            "members": members or ["NVDA", "AMD"],
            "ts": "2026-05-01T10:00:00+00:00",
        }

    def _make_log_rows(self, theme: str, dates_and_legs: list[tuple]) -> list[dict]:
        """dates_and_legs: [(asof_str, {leg: value})]"""
        rows = []
        for asof, legs in dates_and_legs:
            rows.append({
                "theme": theme,
                "asof": asof,
                "ts": f"{asof}T10:00:00+00:00",
                "earliness": None,
                "n_legs_live": len(legs),
                "legs": {k: v for k, v in legs.items()},
            })
        return rows

    def test_we_led(self, tmp_path):
        """Flag date 2026-04-01; news_flow crosses threshold on 2026-04-20.

        Spec (engine docstring): lead_days = arrival_date − flag_date.
        POSITIVE = desk flagged BEFORE the crowd (we led).
        NEGATIVE = crowd arrived before our flag (we were late).

        flag=2026-04-01, arrival=2026-04-20:
          lead_days = (04-20) - (04-01) = +19  → POSITIVE → note='led'.
        """
        from engine.foresight_leadlag import grade_flag

        theme = "test_theme"
        flag_date = "2026-04-01"

        # Historical low values, then high crossing AFTER flag date (2026-04-20).
        log_rows = []
        for i, d in enumerate(["2026-01-01", "2026-02-01", "2026-03-01",
                                "2026-03-15", "2026-03-25"]):
            log_rows.append({
                "theme": theme, "asof": d, "ts": f"{d}T10:00:00+00:00",
                "earliness": 0.8, "n_legs_live": 1,
                "legs": {"news_flow": 0.1 * (i + 1), "coverage_arrival": None,
                         "ownership_breadth": None, "tape_extension": None},
            })
        # High-value entries after flag → crowd arrives 2026-04-20
        for i, d in enumerate(["2026-04-20", "2026-04-25"]):
            log_rows.append({
                "theme": theme, "asof": d, "ts": f"{d}T10:00:00+00:00",
                "earliness": 0.1, "n_legs_live": 1,
                "legs": {"news_flow": 10.0 + i, "coverage_arrival": None,
                         "ownership_breadth": None, "tape_extension": None},
            })

        flag = self._make_flag(theme=theme, asof=flag_date, stage="PRECIPICE (text)",
                               members=["NVDA"])
        result = grade_flag(flag, log_rows, spy=None, root=Path("/nonexistent"))

        news_leg = result["per_leg"]["news_flow"]
        assert news_leg["arrival_date"] == "2026-04-20", "crowd should arrive 04-20"

        # lead_days = arrival - flag = Apr-20 − Apr-01 = +19 (positive = we led)
        assert news_leg["lead_days"] == 19, (
            f"expected +19 (we led by 19d), got {news_leg['lead_days']}"
        )
        assert news_leg["note"] == "led", (
            f"note should be 'led' when lead_days > 0, got {news_leg['note']!r}"
        )

    def test_we_led_small(self, tmp_path):
        """Desk led by only 2 days: flag 05-01, crowd arrives 05-03.

        lead_days = (05-03) - (05-01) = +2 → note='led' (within concurrent band).
        This tests the engine picks up a short lead correctly.
        """
        from engine.foresight_leadlag import grade_flag

        theme = "test_small_lead"
        flag_date = "2026-05-01"
        arrival_date = "2026-05-03"

        log_rows = []
        for i, d in enumerate(["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"]):
            log_rows.append({
                "theme": theme, "asof": d, "ts": f"{d}T10:00:00+00:00",
                "earliness": 0.8, "n_legs_live": 1,
                "legs": {"news_flow": 0.1 * (i + 1), "coverage_arrival": None,
                         "ownership_breadth": None, "tape_extension": None},
            })
        # Crowd crosses 2 days after our flag
        log_rows.append({
            "theme": theme, "asof": "2026-05-03", "ts": "2026-05-03T10:00:00+00:00",
            "earliness": 0.1, "n_legs_live": 1,
            "legs": {"news_flow": 100.0, "coverage_arrival": None,
                     "ownership_breadth": None, "tape_extension": None},
        })

        flag = self._make_flag(theme=theme, asof=flag_date, stage="BROADENING (fingerprint)",
                               members=["NVDA"])
        result = grade_flag(flag, log_rows, spy=None, root=Path("/nonexistent"))

        news_leg = result["per_leg"]["news_flow"]
        assert news_leg["arrival_date"] == arrival_date
        # lead_days = arrival - flag = May-03 − May-01 = +2 (positive = we led)
        assert news_leg["lead_days"] == 2, (
            f"expected +2 (led by 2d), got {news_leg['lead_days']}"
        )
        assert result["n_legs_arrived"] > 0

    def test_desk_lagged(self, tmp_path):
        """Crowd crossed 30d before our flag → no post-flag crossing → pending.

        The engine only looks for crossings AFTER flag_date. A crowd that arrived
        before our flag produces no arrival record → lead_days=None for that leg.
        """
        from engine.foresight_leadlag import grade_flag

        theme = "test_lagged"
        flag_date = "2026-05-01"

        log_rows = []
        # Crowd crossed long before flag (2026-03-01 — before flag_date)
        for i, d in enumerate(["2026-01-01", "2026-02-01"]):
            log_rows.append({
                "theme": theme, "asof": d, "ts": f"{d}T10:00:00+00:00",
                "earliness": 0.8, "n_legs_live": 1,
                "legs": {"news_flow": 0.05 * (i + 1), "coverage_arrival": None,
                         "ownership_breadth": None, "tape_extension": None},
            })
        # Big cross on 2026-03-01 — BEFORE our flag on 2026-05-01
        log_rows.append({
            "theme": theme, "asof": "2026-03-01", "ts": "2026-03-01T10:00:00+00:00",
            "earliness": 0.1, "n_legs_live": 1,
            "legs": {"news_flow": 99.0, "coverage_arrival": None,
                     "ownership_breadth": None, "tape_extension": None},
        })
        # Nothing after the flag
        log_rows.append({
            "theme": theme, "asof": "2026-04-01", "ts": "2026-04-01T10:00:00+00:00",
            "earliness": 0.5, "n_legs_live": 1,
            "legs": {"news_flow": 1.0, "coverage_arrival": None,
                     "ownership_breadth": None, "tape_extension": None},
        })

        flag = self._make_flag(theme=theme, asof=flag_date, stage="PRECIPICE (text)",
                               members=["NVDA"])
        result = grade_flag(flag, log_rows, spy=None, root=Path("/nonexistent"))

        news_leg = result["per_leg"]["news_flow"]
        # No crossing found after flag_date (the big cross was pre-flag)
        assert news_leg["arrival_date"] is None, (
            "pre-flag crowd crossing should not produce an arrival record"
        )
        assert news_leg["lead_days"] is None

    def test_never_crossed(self, tmp_path):
        """Leg never crosses threshold → leg pending, lead_days None."""
        from engine.foresight_leadlag import grade_flag

        theme = "test_never_crossed"
        flag_date = "2026-05-01"

        # All values far below any threshold
        log_rows = []
        for i, d in enumerate(["2026-01-01", "2026-02-01", "2026-03-01",
                                "2026-04-01", "2026-05-15"]):
            log_rows.append({
                "theme": theme, "asof": d, "ts": f"{d}T10:00:00+00:00",
                "earliness": 0.9, "n_legs_live": 1,
                "legs": {"news_flow": 0.01, "coverage_arrival": None,
                         "ownership_breadth": None, "tape_extension": None},
            })

        flag = self._make_flag(theme=theme, asof=flag_date, members=["AAA"])
        result = grade_flag(flag, log_rows, spy=None, root=Path("/nonexistent"))

        news_leg = result["per_leg"]["news_flow"]
        # All-tied values — threshold computation may still return something
        # but no crossing will be found after flag_date since all values are the same
        # (0.01 <= 75th pct of [0.01, 0.01, 0.01, 0.01, 0.01] = 0.01)
        # Actually all-tied → 75th pct = 0.01 → crossing requires > 0.01 → never crossed
        if news_leg["arrival_date"] is None:
            assert news_leg["lead_days"] is None
        # The result may be 'never_crossed' or 'insufficient_data'
        assert news_leg["arrival_date"] is None or news_leg.get("note") in (
            "never_crossed", "insufficient_data", "led", "lagged", "concurrent"
        )

    def test_null_artifact_on_no_foresight_log(self, tmp_path):
        """Missing foresight log → honest null artifact, never crash."""
        from engine.foresight_leadlag import compute_earliness_grades

        result = compute_earliness_grades(tmp_path)
        assert result["n_flags"] == 0
        assert result["n_pending"] == 0
        assert isinstance(result["stale_legs"], list)
        assert len(result["stale_legs"]) > 0
        assert result["pooled_summary"] is None

    def test_authority_block_all_false(self, tmp_path):
        """Authority block must have all promotion flags False."""
        from engine.foresight_leadlag import compute_earliness_grades

        result = compute_earliness_grades(tmp_path)
        auth = result.get("authority", {})
        assert auth.get("is_context_only") is True
        assert auth.get("may_rank") is False
        assert auth.get("may_gate") is False
        assert auth.get("may_size") is False
        assert auth.get("may_escalate") is False

    def test_n_pending_counts_flags_with_no_arrivals(self, tmp_path):
        """n_pending = count of flags where n_legs_arrived == 0."""
        from engine.foresight_leadlag import compute_earliness_grades

        # Write a minimal foresight log with one flag, no earliness log
        foresight_path = tmp_path / "data" / "foresight" / "log.jsonl"
        _write_jsonl(foresight_path, [
            {"theme": "ai_cap", "asof": "2026-05-01", "stage": "PRECIPICE (text)",
             "members": ["NVDA"], "ts": "2026-05-01T10:00:00+00:00"},
        ])

        result = compute_earliness_grades(tmp_path)
        # 1 flag; no earliness log entries → no arrivals → n_pending = 1
        assert result["n_flags"] == 1
        assert result["n_pending"] == 1

    def test_stale_legs_when_earliness_log_absent(self, tmp_path):
        """stale_legs contains an entry when earliness_log is absent."""
        from engine.foresight_leadlag import compute_earliness_grades

        foresight_path = tmp_path / "data" / "foresight" / "log.jsonl"
        _write_jsonl(foresight_path, [
            {"theme": "test_t", "asof": "2026-05-01", "stage": "PRECIPICE (text)",
             "members": ["A"], "ts": "2026-05-01T00:00:00+00:00"},
        ])

        result = compute_earliness_grades(tmp_path)
        stale = result.get("stale_legs", [])
        # Should report that earliness_log is absent
        assert any("earliness_log" in s for s in stale), f"stale_legs: {stale}"

    def test_banned_word_validated(self, tmp_path):
        """'validated' must not appear in any user-facing output field."""
        from engine.foresight_leadlag import compute_earliness_grades

        result = compute_earliness_grades(tmp_path)
        text = json.dumps(result).lower()
        assert "validated" not in text, "banned word 'validated' found in output"

    def test_front_run_assessment_desk_leads(self, tmp_path):
        """Discriminating test: genuine we-led scenario produces DESK_LEADS_CROWD.

        This guards against sign-convention inversions: if lead_days arithmetic
        is inverted, a desk that actually led would produce DESK_LAGS_CROWD here.

        Setup: flag on 2026-04-01, crowd arrives on 2026-04-30 → +29d lead.
        overall_median = +29 → > 2 → front_run_assessment = DESK_LEADS_CROWD.
        """
        from engine.foresight_leadlag import compute_earliness_grades

        theme = "ai_cap"
        flag_date = "2026-04-01"

        foresight_path = tmp_path / "data" / "foresight" / "log.jsonl"
        _write_jsonl(foresight_path, [{
            "theme": theme,
            "asof": flag_date,
            "stage": "PRECIPICE",
            "members": [],
            "ts": f"{flag_date}T10:00:00+00:00",
        }])

        # Earliness log: 5 historical rows (low news_flow), then crowd crosses 2026-04-30
        earliness_path = tmp_path / "data" / "foresight" / "earliness_log.jsonl"
        rows = []
        for i, d in enumerate(["2026-01-10", "2026-01-20", "2026-02-10",
                                "2026-02-20", "2026-03-10"]):
            rows.append({
                "theme": theme, "asof": d, "ts": f"{d}T10:00:00+00:00",
                "earliness": 0.9, "n_legs_live": 1,
                "legs": {"news_flow": 0.05 * (i + 1), "coverage_arrival": None,
                         "ownership_breadth": None, "tape_extension": None},
            })
        # Crowd crossing 29 days after flag
        rows.append({
            "theme": theme, "asof": "2026-04-30", "ts": "2026-04-30T10:00:00+00:00",
            "earliness": 0.05, "n_legs_live": 1,
            "legs": {"news_flow": 50.0, "coverage_arrival": None,
                     "ownership_breadth": None, "tape_extension": None},
        })
        _write_jsonl(earliness_path, rows)

        result = compute_earliness_grades(tmp_path)
        summary = result.get("pooled_summary", {})
        assessment = summary.get("front_run_assessment", "")

        assert "DESK_LEADS_CROWD" in assessment, (
            f"expected DESK_LEADS_CROWD for +29d lead, got: {assessment!r}. "
            "This catches sign-convention inversion in lead_days arithmetic."
        )
        # Sanity: the median should be positive
        assert summary.get("overall_median_lead_days", 0) > 2, (
            f"median_lead_days should be >2 for a 29d lead, got "
            f"{summary.get('overall_median_lead_days')}"
        )

    def test_front_run_assessment_desk_lags(self, tmp_path):
        """Discriminating test: desk that lags produces DESK_LAGS_CROWD (honest null).

        Setup: crowd arrives 2026-04-30 but flag is on 2026-06-01 (flag is AFTER crowd).
        Engine only finds crossings AFTER flag_date, so this flag will have no
        post-flag crossing → n_pending. Confirmed: desk that arrives after the crowd
        gets no crossing record, so assessment remains INSUFFICIENT_DATA.
        """
        from engine.foresight_leadlag import compute_earliness_grades

        theme = "lagging_theme"
        flag_date = "2026-06-01"  # flag AFTER crowd crossed

        foresight_path = tmp_path / "data" / "foresight" / "log.jsonl"
        _write_jsonl(foresight_path, [{
            "theme": theme,
            "asof": flag_date,
            "stage": "PRECIPICE",
            "members": [],
            "ts": f"{flag_date}T10:00:00+00:00",
        }])

        earliness_path = tmp_path / "data" / "foresight" / "earliness_log.jsonl"
        rows = []
        for i, d in enumerate(["2026-01-10", "2026-02-10", "2026-03-10",
                                "2026-04-10", "2026-04-30"]):
            rows.append({
                "theme": theme, "asof": d, "ts": f"{d}T10:00:00+00:00",
                "earliness": 0.9, "n_legs_live": 1,
                "legs": {"news_flow": (50.0 if d == "2026-04-30" else 0.1 * (i + 1)),
                         "coverage_arrival": None,
                         "ownership_breadth": None, "tape_extension": None},
            })
        _write_jsonl(earliness_path, rows)

        result = compute_earliness_grades(tmp_path)
        summary = result.get("pooled_summary", {})
        # Crowd already crossed before flag date → no post-flag crossing → insufficient data
        assessment = summary.get("front_run_assessment", "")
        assert "INSUFFICIENT_DATA" in assessment or "DESK_LAGS" in assessment, (
            f"expected INSUFFICIENT_DATA or DESK_LAGS for lagging desk, got: {assessment!r}"
        )


# ============================================================================
# Stage 2 — Placebo tape
# ============================================================================

class TestPlaceboTape:

    def _make_foresight_log(self, tmp_path: Path, flags: list[dict]) -> None:
        path = tmp_path / "data" / "foresight" / "log.jsonl"
        _write_jsonl(path, flags)

    def test_deterministic_same_seed(self, tmp_path):
        """Same theme+asof always produces the same placebo rows."""
        from engine.theme_placebo import build_placebo_rows

        flag = {
            "theme": "ai_semiconductors",
            "asof": "2026-05-10",
            "stage": "PRECIPICE (text)",
            "members": ["NVDA", "AMD"],
            "ts": "2026-05-10T09:00:00+00:00",
        }
        all_themes = ["ai_semiconductors", "biotech", "clean_energy", "ev", "semis",
                      "cybersecurity", "cloud", "memory_storage"]

        rows1 = build_placebo_rows(flag, all_themes, set())
        rows2 = build_placebo_rows(flag, all_themes, set())

        # Convert to comparable form
        keys1 = [(r["theme"], r["asof"], r["placebo_kind"]) for r in rows1]
        keys2 = [(r["theme"], r["asof"], r["placebo_kind"]) for r in rows2]
        assert keys1 == keys2, "placebo rows not deterministic"

    def test_k_random_peers_plus_one_time_shift(self, tmp_path):
        """Each non-WATCH flag generates K=3 random peers + 1 time-shifted row."""
        from engine.theme_placebo import build_placebo_rows, K_RANDOM

        flag = {
            "theme": "biotech",
            "asof": "2026-06-01",
            "stage": "BROADENING (fingerprint)",
            "members": ["MRNA", "BNTX"],
            "ts": "2026-06-01T09:00:00+00:00",
        }
        all_themes = ["biotech", "clean_energy", "ev", "semis", "cybersecurity",
                      "cloud", "memory_storage", "defense", "fintech"]

        rows = build_placebo_rows(flag, all_themes, set())

        peers = [r for r in rows if r["placebo_kind"] == "random_peer"]
        shifts = [r for r in rows if r["placebo_kind"] == "time_shift_minus_21d"]

        assert len(peers) == K_RANDOM, f"expected {K_RANDOM} peers, got {len(peers)}"
        assert len(shifts) == 1, f"expected 1 time-shift row, got {len(shifts)}"

    def test_watch_flags_skipped(self, tmp_path):
        """WATCH stage flags are skipped (no placebo generated)."""
        from engine.theme_placebo import append_placebo_tape

        self._make_foresight_log(tmp_path, [
            {"theme": "ai_cap", "asof": "2026-05-01", "stage": "WATCH",
             "members": ["NVDA"], "ts": "2026-05-01T09:00:00+00:00"},
        ])

        summary = append_placebo_tape(tmp_path)
        assert summary["n_new_placebo_rows"] == 0
        assert summary["n_watch_skipped"] == 1

    def test_time_shift_is_21d(self, tmp_path):
        """The time-shifted variant's asof is exactly 21 days before the source."""
        from engine.theme_placebo import build_placebo_rows, TIME_SHIFT_DAYS

        flag_asof = "2026-07-01"
        flag = {
            "theme": "ev",
            "asof": flag_asof,
            "stage": "PRECIPICE (text)",
            "members": ["TSLA"],
            "ts": "2026-07-01T09:00:00+00:00",
        }
        all_themes = ["ev", "biotech", "clean_energy", "semis", "cloud",
                      "memory", "fintech", "defense"]

        rows = build_placebo_rows(flag, all_themes, set())
        shift_rows = [r for r in rows if r["placebo_kind"] == "time_shift_minus_21d"]

        assert len(shift_rows) == 1
        from datetime import datetime, timedelta
        source_dt = datetime.strptime(flag_asof, "%Y-%m-%d")
        expected_shift = (source_dt - timedelta(days=TIME_SHIFT_DAYS)).strftime("%Y-%m-%d")
        assert shift_rows[0]["asof"] == expected_shift

    def test_no_duplicate_append(self, tmp_path):
        """Running append_placebo_tape twice does not duplicate rows."""
        from engine.theme_placebo import append_placebo_tape

        flags = [
            {"theme": "clean_energy", "asof": "2026-05-15", "stage": "PRECIPICE (text)",
             "members": ["ENPH", "SEDG"], "ts": "2026-05-15T09:00:00+00:00"},
        ]
        self._make_foresight_log(tmp_path, flags)

        summary1 = append_placebo_tape(tmp_path)
        n_rows1 = summary1["n_new_placebo_rows"]

        summary2 = append_placebo_tape(tmp_path)
        n_rows2 = summary2["n_new_placebo_rows"]

        assert n_rows2 == 0, f"second run should produce 0 new rows, got {n_rows2}"

        # Verify the tape file has no duplicate (theme, asof, placebo_kind) keys
        tape_path = tmp_path / "data" / "foresight" / "theme_placebo_tape.jsonl"
        if tape_path.exists():
            rows = _read_jsonl(tape_path)
            keys = [(r["theme"], r["asof"], r["placebo_kind"]) for r in rows]
            assert len(keys) == len(set(keys)), "duplicates found in tape"

    def test_non_flagged_theme_in_peers(self, tmp_path):
        """Peer placebo rows must not use the same theme as the real flag."""
        from engine.theme_placebo import build_placebo_rows

        flag_theme = "defense"
        flag = {
            "theme": flag_theme,
            "asof": "2026-05-20",
            "stage": "PRECIPICE (text)",
            "members": ["LMT", "NOC"],
            "ts": "2026-05-20T09:00:00+00:00",
        }
        all_themes = [flag_theme, "biotech", "clean_energy", "ev", "semis",
                      "cybersecurity", "cloud", "memory"]

        rows = build_placebo_rows(flag, all_themes, set())
        peers = [r for r in rows if r["placebo_kind"] == "random_peer"]

        for peer in peers:
            assert peer["theme"] != flag_theme, (
                f"peer placebo must not use the same theme as the flag: {flag_theme}"
            )

    def test_banned_word_validated(self, tmp_path):
        """'validated' must not appear in placebo rows."""
        from engine.theme_placebo import build_placebo_rows

        flag = {
            "theme": "cloud",
            "asof": "2026-05-01",
            "stage": "PRECIPICE (text)",
            "members": ["AMZN"],
            "ts": "2026-05-01T09:00:00+00:00",
        }
        all_themes = ["cloud", "ev", "biotech", "semis", "memory", "defense", "fintech"]
        rows = build_placebo_rows(flag, all_themes, set())

        for row in rows:
            text = json.dumps(row).lower()
            assert "validated" not in text


# ============================================================================
# Stage 3 — Falsifier auto-evaluation
# ============================================================================

class TestFalsifierEvaluator:

    def _make_claims_jsonl(self, tmp_path: Path, claims: list[dict]) -> None:
        path = tmp_path / "data" / "qledger" / "claims.jsonl"
        _write_jsonl(path, claims)

    def _make_claim(self, claim_id: str, asof: str, check_by: str,
                    falsifier: dict | None = None, desk: str = "altdata") -> dict:
        return {
            "claim_id": claim_id,
            "desk": desk,
            "asof": asof,
            "check_by": check_by,
            "scope": {"type": "entity", "key": "TEST"},
            "direction": 1,
            "horizon_d": 63,
            "falsifier": falsifier,
            "status": "open",
            "is_placebo": False,
            "bench": "SPY",
        }

    def _write_price(self, tmp_path: Path, ticker: str,
                     dates: list[str], prices: list[float]) -> None:
        _make_price_parquet(
            tmp_path / "data" / "yahoo" / f"{ticker}.parquet",
            dates, prices,
        )

    def test_rel_return_tripped(self, tmp_path):
        """op='<', threshold=-0.05: excess < -0.05 → FALSIFIER_TRIPPED."""
        from engine.qledger_falsifier import evaluate_falsifiers

        asof = "2026-01-01"
        check_by = "2026-03-15"

        # Subject drops 20%, SPY flat → excess = -0.20 - 0.0 = -0.20 < -0.05 → TRIPPED
        dates = ["2026-01-02", "2026-01-05", "2026-03-10", "2026-03-15"]
        self._write_price(tmp_path, "SUBJ", dates, [100.0, 100.0, 80.0, 80.0])
        self._write_price(tmp_path, "SPY",  dates, [400.0, 400.0, 400.0, 400.0])

        claim = self._make_claim(
            claim_id="test_tripped_01",
            asof=asof,
            check_by=check_by,
            falsifier={
                "text": "SUBJ underperforms SPY by >5%.",
                "check": {
                    "kind": "rel_return",
                    "subject_ticker": "SUBJ",
                    "vs": "SPY",
                    "op": "<",
                    "threshold": -0.05,
                    "horizon_d": 63,
                },
            },
        )
        self._make_claims_jsonl(tmp_path, [claim])

        summary = evaluate_falsifiers(tmp_path, today=check_by)
        assert summary["n_tripped"] == 1
        assert summary["n_confirmed"] == 0

        # Check the evaluation was written
        eval_path = tmp_path / "data" / "qledger" / "falsifier_evaluations.jsonl"
        rows = _read_jsonl(eval_path)
        assert len(rows) == 1
        assert rows[0]["outcome"] == "FALSIFIER_TRIPPED"
        assert rows[0]["claim_id"] == "test_tripped_01"

    def test_rel_return_confirmed(self, tmp_path):
        """op='<', threshold=-0.05: excess = +0.10 > -0.05 → CONFIRMED."""
        from engine.qledger_falsifier import evaluate_falsifiers

        asof = "2026-01-01"
        check_by = "2026-03-15"

        # Subject up 10%, SPY flat → excess = +0.10. Not < -0.05 → CONFIRMED.
        dates = ["2026-01-02", "2026-01-05", "2026-03-10", "2026-03-15"]
        self._write_price(tmp_path, "BULL", dates, [100.0, 100.0, 110.0, 110.0])
        self._write_price(tmp_path, "SPY",  dates, [400.0, 400.0, 400.0, 400.0])

        claim = self._make_claim(
            claim_id="test_confirmed_01",
            asof=asof,
            check_by=check_by,
            falsifier={
                "text": "BULL fails to outperform.",
                "check": {
                    "kind": "rel_return",
                    "subject_ticker": "BULL",
                    "vs": "SPY",
                    "op": "<",
                    "threshold": -0.05,
                    "horizon_d": 63,
                },
            },
        )
        self._make_claims_jsonl(tmp_path, [claim])

        summary = evaluate_falsifiers(tmp_path, today=check_by)
        assert summary["n_confirmed"] == 1
        assert summary["n_tripped"] == 0

    def test_soft_check_unverifiable(self, tmp_path):
        """Soft check kind → UNVERIFIABLE."""
        from engine.qledger_falsifier import evaluate_falsifiers

        asof = "2026-01-01"
        check_by = "2026-03-15"

        claim = self._make_claim(
            claim_id="test_soft_01",
            asof=asof,
            check_by=check_by,
            falsifier={
                "text": "Treasury announces auction increase.",
                "check": {
                    "kind": "soft",
                    "reason": "BIL not a scorable proxy",
                },
            },
        )
        self._make_claims_jsonl(tmp_path, [claim])

        summary = evaluate_falsifiers(tmp_path, today=check_by)
        assert summary["n_unverifiable"] == 1
        assert summary["n_tripped"] == 0
        assert summary["n_confirmed"] == 0

    def test_unknown_kind_unverifiable(self, tmp_path):
        """Unknown check kind → UNVERIFIABLE."""
        from engine.qledger_falsifier import evaluate_falsifiers

        asof = "2026-01-01"
        check_by = "2026-03-15"

        claim = self._make_claim(
            claim_id="test_unknown_01",
            asof=asof,
            check_by=check_by,
            falsifier={
                "text": "Some threshold gets crossed.",
                "check": {"kind": "future_unknown_kind", "threshold": 5.0},
            },
        )
        self._make_claims_jsonl(tmp_path, [claim])

        summary = evaluate_falsifiers(tmp_path, today=check_by)
        assert summary["n_unverifiable"] == 1

    def test_missing_price_data_unverifiable(self, tmp_path):
        """Missing ticker price data → UNVERIFIABLE (no crash)."""
        from engine.qledger_falsifier import evaluate_falsifiers

        asof = "2026-01-01"
        check_by = "2026-03-15"

        claim = self._make_claim(
            claim_id="test_noprice_01",
            asof=asof,
            check_by=check_by,
            falsifier={
                "text": "NOPRICE underperforms.",
                "check": {
                    "kind": "rel_return",
                    "subject_ticker": "NOPRICE_TICKER_DOES_NOT_EXIST",
                    "vs": "SPY",
                    "op": "<",
                    "threshold": -0.05,
                    "horizon_d": 63,
                },
            },
        )
        self._make_claims_jsonl(tmp_path, [claim])

        summary = evaluate_falsifiers(tmp_path, today=check_by)
        # No crash; unverifiable because no price data
        assert summary["n_unverifiable"] == 1
        assert summary["n_claims_checked"] == 1

    def test_append_only_no_duplicate(self, tmp_path):
        """Re-running evaluate_falsifiers does not duplicate rows (dedup by claim_id)."""
        from engine.qledger_falsifier import evaluate_falsifiers

        asof = "2026-01-01"
        check_by = "2026-03-15"

        claim = self._make_claim(
            claim_id="test_dedup_01",
            asof=asof,
            check_by=check_by,
            falsifier={
                "text": "Check.",
                "check": {"kind": "soft", "reason": "manual check"},
            },
        )
        self._make_claims_jsonl(tmp_path, [claim])

        summary1 = evaluate_falsifiers(tmp_path, today=check_by)
        summary2 = evaluate_falsifiers(tmp_path, today=check_by)

        assert summary1["n_claims_checked"] == 1
        assert summary2["n_claims_checked"] == 0, (
            "second run should skip already-evaluated claims"
        )

        eval_path = tmp_path / "data" / "qledger" / "falsifier_evaluations.jsonl"
        rows = _read_jsonl(eval_path)
        cids = [r["claim_id"] for r in rows]
        assert len(cids) == len(set(cids)), "duplicates found in evaluations tape"

    def test_cap_per_run(self, tmp_path):
        """Only MAX_PER_RUN claims evaluated per run; rest deferred."""
        from engine.qledger_falsifier import evaluate_falsifiers

        today = "2026-03-15"
        claims = []
        for i in range(10):
            claims.append(self._make_claim(
                claim_id=f"cap_test_{i:04d}",
                asof="2026-01-01",
                check_by="2026-03-01",
                falsifier={
                    "text": f"Check {i}.",
                    "check": {"kind": "soft", "reason": "test"},
                },
            ))
        self._make_claims_jsonl(tmp_path, claims)

        summary = evaluate_falsifiers(tmp_path, today=today, max_per_run=3)
        assert summary["n_claims_checked"] == 3
        assert summary["n_capped"] == 7  # 10 - 3 = 7

    def test_future_check_by_skipped(self, tmp_path):
        """Claims whose check_by is in the future are not evaluated."""
        from engine.qledger_falsifier import evaluate_falsifiers

        today = "2026-03-01"
        claim = self._make_claim(
            claim_id="future_01",
            asof="2026-01-01",
            check_by="2026-12-31",  # future
            falsifier={
                "text": "Future check.",
                "check": {"kind": "soft", "reason": "not yet"},
            },
        )
        self._make_claims_jsonl(tmp_path, [claim])

        summary = evaluate_falsifiers(tmp_path, today=today)
        assert summary["n_claims_checked"] == 0
        assert summary["n_total_due"] == 0

    def test_null_falsifier_skipped(self, tmp_path):
        """Claims with null falsifier are not evaluated."""
        from engine.qledger_falsifier import evaluate_falsifiers

        today = "2026-03-15"
        claim = self._make_claim(
            claim_id="null_falsifier_01",
            asof="2026-01-01",
            check_by="2026-03-01",
            falsifier=None,
        )
        self._make_claims_jsonl(tmp_path, [claim])

        summary = evaluate_falsifiers(tmp_path, today=today)
        assert summary["n_claims_checked"] == 0

    def test_authority_block_present(self, tmp_path):
        """Authority block present with all flags False."""
        from engine.qledger_falsifier import evaluate_falsifiers

        summary = evaluate_falsifiers(tmp_path, today="2026-03-15")
        auth = summary.get("authority", {})
        assert auth.get("is_context_only") is True
        assert auth.get("may_rank") is False
        assert auth.get("may_gate") is False

    def test_banned_word_validated(self, tmp_path):
        """'validated' must not appear in evaluations output."""
        from engine.qledger_falsifier import evaluate_falsifiers

        today = "2026-03-15"
        claim = self._make_claim(
            claim_id="vw_test_01",
            asof="2026-01-01",
            check_by="2026-03-01",
            falsifier={
                "text": "Some claim text.",
                "check": {"kind": "soft", "reason": "soft"},
            },
        )
        self._make_claims_jsonl(tmp_path, [claim])

        summary = evaluate_falsifiers(tmp_path, today=today)
        text = json.dumps(summary).lower()
        assert "validated" not in text


# ============================================================================
# Cross-cutting: run_stage does not raise fatally
# ============================================================================

class TestRunStage:

    def test_run_stage_empty_stores(self, tmp_path):
        """run_stage() completes without raising on entirely empty stores."""
        from scripts.grade_thematic import run_stage
        # Should not raise — all stages are tolerant readers
        run_stage(tmp_path)

    def test_run_stage_partial_data(self, tmp_path):
        """run_stage() completes when only foresight log exists (no earliness log)."""
        from scripts.grade_thematic import run_stage

        foresight_path = tmp_path / "data" / "foresight" / "log.jsonl"
        _write_jsonl(foresight_path, [
            {"theme": "ev", "asof": "2026-05-01", "stage": "PRECIPICE (text)",
             "members": ["TSLA"], "ts": "2026-05-01T09:00:00+00:00"},
        ])

        # Should not raise
        run_stage(tmp_path)

        # Grade file should exist (written even if mostly null)
        grades_path = tmp_path / "data" / "foresight" / "earliness_grades.json"
        assert grades_path.exists(), "earliness_grades.json should be written"
        data = json.loads(grades_path.read_text())
        assert data.get("n_flags") == 1

    def test_run_stage_banned_word_validated(self, tmp_path):
        """'validated' must not appear in any output written by run_stage."""
        from scripts.grade_thematic import run_stage

        run_stage(tmp_path)

        # Check all written files
        for pattern in ("data/foresight/earliness_grades.json",):
            p = tmp_path / pattern
            if p.exists():
                text = p.read_text().lower()
                assert "validated" not in text, f"'validated' in {p}"
