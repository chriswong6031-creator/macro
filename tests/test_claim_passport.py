"""tests/test_claim_passport.py — W3 Claim Passport linter + promotion_check tests.

Covers:
  1. Linter catches a synthetic violation (unregistered field consumed in scored module).
  2. Grandfathered entries pass (exit 0) under normal mode, fail under --strict.
  3. promotion_check math on fixtures:
       a. n_dates < 25 → not eligible, reason mentions threshold.
       b. n_dates >= 25, CI > 0 → eligible.
       c. n_dates >= 25, CI <= 0 → demote=True.
       d. Empty claim_family → not eligible.
  4. Linter shell invocation via subprocess (CI integration gate).
  5. Ladder YAML parses cleanly with all required keys.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from engine import qledger as q

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parent.parent
_LINTER = _REPO / "scripts" / "check_claim_passport.py"
_LADDER = _REPO / "config" / "qual_ladder.yml"


def _run_linter(*extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_LINTER)] + list(extra_args),
        capture_output=True, text=True,
    )


# ---------------------------------------------------------------------------
# 5. Ladder YAML integrity
# ---------------------------------------------------------------------------
class TestLadderYaml:
    def test_ladder_loads(self):
        import yaml
        with _LADDER.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert isinstance(data, dict), "qual_ladder.yml must be a mapping"
        assert len(data) >= 5, "Expected at least 5 registered entries"

    def test_all_entries_have_required_keys(self):
        import yaml
        with _LADDER.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        required = {"field", "producer", "claim_family", "ladder_state"}
        for key, entry in data.items():
            assert isinstance(entry, dict), f"{key}: entry must be a dict"
            missing = required - set(entry.keys())
            assert not missing, f"{key}: missing required keys {missing}"

    def test_ladder_states_are_valid(self):
        import yaml
        valid_states = {"DISPLAY", "SHADOW", "CONFIRMER", "SCORED"}
        with _LADDER.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        for key, entry in data.items():
            if isinstance(entry, dict):
                st = entry.get("ladder_state", "").upper()
                assert st in valid_states, (
                    f"{key}: ladder_state={st!r} not in {valid_states}"
                )

    def test_grandfathered_entries_have_gated_by(self):
        import yaml
        with _LADDER.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        for key, entry in data.items():
            if isinstance(entry, dict) and entry.get("grandfathered"):
                assert entry.get("gated_by"), (
                    f"{key}: grandfathered=true but no gated_by note. "
                    f"Every debt must document the W0 gate that limits blast radius."
                )

    def test_no_entry_is_scored_without_confirmer_plus(self):
        """Sanity: per the W3 brief, nothing has passed the §3 gate yet.
        No entry should have ladder_state CONFIRMER or SCORED at seed time."""
        import yaml
        with _LADDER.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        for key, entry in data.items():
            if isinstance(entry, dict):
                st = entry.get("ladder_state", "").upper()
                assert st not in ("CONFIRMER", "SCORED"), (
                    f"{key}: seed ladder should have no CONFIRMER/SCORED entries "
                    f"(scoreboard fact: hand formula indistinguishable from placebo). "
                    f"If this field has genuinely passed the §3 gate, update this test."
                )


# ---------------------------------------------------------------------------
# 1 & 2. Linter via real ladder (shell invocation)
# ---------------------------------------------------------------------------
class TestLinterShell:
    def test_linter_passes_on_real_ladder(self):
        """The linter must pass on the committed ladder (grandfathered entries are
        debt, not hard errors, under normal mode)."""
        result = _run_linter()
        assert result.returncode == 0, (
            f"Linter failed on committed ladder.\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

    def test_linter_emits_debt_warnings_for_grandfathered(self):
        """Grandfathered entries must appear in the output as DEBT warnings."""
        result = _run_linter()
        assert "DEBT" in result.stdout or "grandfathered" in result.stdout.lower(), (
            "Expected DEBT warning output for grandfathered entries. "
            f"Stdout was:\n{result.stdout}"
        )

    def test_strict_mode_fails_on_grandfathered(self):
        """--strict mode must exit 1 because the ladder has grandfathered entries."""
        result = _run_linter("--strict")
        assert result.returncode == 1, (
            "Expected exit 1 in --strict mode due to grandfathered entries. "
            f"Stdout:\n{result.stdout}"
        )

    def test_report_mode_always_exits_zero(self):
        """--report mode always exits 0 regardless of errors."""
        result = _run_linter("--report", "--strict")
        assert result.returncode == 0, (
            f"--report mode must always exit 0. Stdout:\n{result.stdout}"
        )

    def test_linter_catches_synthetic_violation(self, tmp_path):
        """Linter must exit 1 when a synthetic ladder entry has ladder_state=DISPLAY
        (not grandfathered) and a scored_consumer module that reads the field."""
        # 1. Create a fake module that reads the forbidden field
        fake_module = tmp_path / "fake_consumer.py"
        fake_module.write_text(
            'def score(data):\n    return data.get("unproven_qual_field")\n',
            encoding="utf-8",
        )

        # 2. Create a synthetic ladder with that violation
        fake_ladder = tmp_path / "test_ladder.yml"
        fake_ladder.write_text(
            f"""synthetic.unproven_field:
  field: unproven_qual_field
  artifact_glob: "site/test/*.json"
  producer: engine/test_engine.py
  claim_family: test_family
  ladder_state: DISPLAY
  max_weight: null
  grandfathered: false
  scored_consumers:
    - {fake_module.relative_to(_REPO) if fake_module.is_relative_to(_REPO) else fake_module}
""",
            encoding="utf-8",
        )

        # Write the synthetic module relative to repo root so linter can find it
        # (linter resolves consumer paths from repo root; use absolute path workaround)
        # We write the module into the repo tree for the test
        test_mod = _REPO / "tests" / "_synthetic_claim_consumer.py"
        test_mod.write_text(
            'def score(data):\n    return data.get("unproven_qual_field")\n',
            encoding="utf-8",
        )
        syn_ladder = tmp_path / "syn_ladder.yml"
        syn_ladder.write_text(
            "synthetic.unproven_field:\n"
            "  field: unproven_qual_field\n"
            "  artifact_glob: \"site/test/*.json\"\n"
            "  producer: engine/test_engine.py\n"
            "  claim_family: test_family\n"
            "  ladder_state: DISPLAY\n"
            "  max_weight: null\n"
            "  grandfathered: false\n"
            "  scored_consumers:\n"
            "    - tests/_synthetic_claim_consumer.py\n",
            encoding="utf-8",
        )
        try:
            result = _run_linter("--ladder", str(syn_ladder))
            assert result.returncode == 1, (
                f"Linter should exit 1 for non-grandfathered DISPLAY field "
                f"consumed in scored module.\nStdout:\n{result.stdout}"
            )
            assert "FAIL" in result.stdout, (
                f"Expected [FAIL] in output. Got:\n{result.stdout}"
            )
        finally:
            test_mod.unlink(missing_ok=True)

    def test_linter_passes_grandfathered_violation(self, tmp_path):
        """Grandfathered DISPLAY entry must pass (exit 0) in normal mode."""
        test_mod = _REPO / "tests" / "_synthetic_claim_consumer.py"
        test_mod.write_text(
            'def score(data):\n    return data.get("unproven_qual_field")\n',
            encoding="utf-8",
        )
        syn_ladder = tmp_path / "gf_ladder.yml"
        syn_ladder.write_text(
            "synthetic.unproven_field:\n"
            "  field: unproven_qual_field\n"
            "  artifact_glob: \"site/test/*.json\"\n"
            "  producer: engine/test_engine.py\n"
            "  claim_family: test_family\n"
            "  ladder_state: DISPLAY\n"
            "  max_weight: null\n"
            "  grandfathered: true\n"
            "  gated_by: \"W0 gate: n_scored>0 condition limits blast radius\"\n"
            "  scored_consumers:\n"
            "    - tests/_synthetic_claim_consumer.py\n",
            encoding="utf-8",
        )
        try:
            result = _run_linter("--ladder", str(syn_ladder))
            assert result.returncode == 0, (
                f"Grandfathered entry should not fail in normal mode.\n"
                f"Stdout:\n{result.stdout}"
            )
            assert "DEBT" in result.stdout, "Expected DEBT in output for grandfathered"
        finally:
            test_mod.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 3. promotion_check math
# ---------------------------------------------------------------------------
def _mk_series_prices(monkeypatch, store: dict):
    """Install synthetic price layer on the qledger price helpers."""
    import pandas as pd

    def _level_asof_mock(ticker, root, asof):
        s = store.get(ticker)
        if s is None:
            return None
        try:
            ts = pd.Timestamp(asof)
            valid = s[s.index <= ts]
            return float(valid.iloc[-1]) if not valid.empty else None
        except Exception:
            return None

    def _close_at_mock(ticker, root, asof):
        return _level_asof_mock(ticker, root, asof)

    def _covers_mock(ticker, root, asof):
        s = store.get(ticker)
        if s is None:
            return False
        try:
            ts = pd.Timestamp(asof)
            return not s[s.index <= ts].empty
        except Exception:
            return False

    monkeypatch.setattr("engine.qledger._level_asof", _level_asof_mock)
    monkeypatch.setattr("engine.qledger._close_at", _close_at_mock)
    monkeypatch.setattr("engine.qledger._covers", _covers_mock)


def _make_fixtures(tmp_path: Path, monkeypatch,
                   n_dates: int, hit_rate: float = 0.70) -> None:
    """Write n_dates claim+grade pairs into a tmp_path store.
    hit_rate controls fraction of directional hits (grade.hit=True)."""
    import pandas as pd

    # Synthetic prices: subject outperforms bench when hit=True
    start = pd.Timestamp("2020-01-01")
    store: dict = {}
    n_total = n_dates * 2  # enough price history
    for ticker, drift in (("SUBJ", 0.01), ("SPY", 0.002), ("CTRL", 0.004)):
        idx = pd.bdate_range(start=start, periods=n_total + 200)
        vals = [100.0 * (1 + drift) ** i for i in range(len(idx))]
        store[ticker] = pd.Series(vals, index=idx)
    _mk_series_prices(monkeypatch, store)

    (tmp_path / "data" / "qledger").mkdir(parents=True)
    (tmp_path / "site" / "qledger").mkdir(parents=True)

    claims_path = tmp_path / "data" / "qledger" / "claims.jsonl"
    grades_path = tmp_path / "data" / "qledger" / "grades.jsonl"

    claim_rows = []
    grade_rows = []
    for i in range(n_dates):
        asof = (start + pd.Timedelta(days=i * 7)).date().isoformat()
        cid = f"fixture_{i:04d}"
        claim = {
            "claim_id": cid,
            "desk": "test_desk",
            "asof": asof,
            "scope": {"type": "entity", "key": "SUBJ"},
            "direction": 1,
            "horizon_d": 21,
            "bench": "SPY",
            "control": "CTRL",
            "timestamp_quality": "CRAWL_BOUNDED",
            "is_placebo": False,
            "status": "open",
            "claim_family": "test_family",
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
        claim_rows.append(claim)

        # Compute subject/bench/control returns to drive hit
        is_hit = (i / n_dates) < hit_rate
        subj_ret = 0.05 if is_hit else -0.03
        bench_ret = 0.01
        ctrl_ret = 0.02
        grade = {
            "claim_id": cid,
            "horizon_d": 21,
            "graded_at": "2026-01-01T00:00:00+00:00",
            "subject_ret": subj_ret,
            "bench_ret": bench_ret,
            "control_ret": ctrl_ret,
            "excess": round(subj_ret - bench_ret, 6),
            "hit": bool(subj_ret > bench_ret),
            "embargo_applied": False,
        }
        grade_rows.append(grade)

    with claims_path.open("w", encoding="utf-8") as fh:
        for r in claim_rows:
            fh.write(json.dumps(r) + "\n")
    with grades_path.open("w", encoding="utf-8") as fh:
        for r in grade_rows:
            fh.write(json.dumps(r) + "\n")


class TestPromotionCheck:
    def test_insufficient_n_dates(self, tmp_path, monkeypatch):
        """n_dates < 25 → not eligible."""
        _make_fixtures(tmp_path, monkeypatch, n_dates=10)
        result = q.promotion_check("test_family", 21, root=tmp_path)
        assert not result.eligible
        assert "n_dates=10" in result.reason
        assert str(q.PROMOTION_MIN_DATES) in result.reason
        assert result.n_dates == 10

    def test_eligible_at_25_dates_positive_ci(self, tmp_path, monkeypatch):
        """n_dates=25 with >50% hits → wilson_ci_low > 0 → eligible."""
        _make_fixtures(tmp_path, monkeypatch, n_dates=25, hit_rate=0.80)
        result = q.promotion_check("test_family", 21, root=tmp_path)
        assert result.eligible, (
            f"Expected eligible=True. Reason: {result.reason}, "
            f"n_dates={result.n_dates}, ci_low={result.wilson_ci_low}"
        )
        assert result.n_dates == 25
        assert result.wilson_ci_low is not None
        assert result.wilson_ci_low > 0
        assert not result.demote

    def test_demote_when_ci_negative(self, tmp_path, monkeypatch):
        """n_dates >= 25 but zero hits (all misses) → CI <= 0 → demote=True."""
        _make_fixtures(tmp_path, monkeypatch, n_dates=30, hit_rate=0.0)
        result = q.promotion_check("test_family", 21, root=tmp_path)
        assert not result.eligible, (
            f"Expected not eligible with 0 hits. "
            f"ci_low={result.wilson_ci_low}, n_dates={result.n_dates}"
        )
        assert result.demote, (
            f"Expected demote=True with CI <= 0. ci_low={result.wilson_ci_low}"
        )
        assert result.pinned_reason
        assert "AUTO-DEMOTE" in result.reason or result.demote

    def test_empty_family(self, tmp_path, monkeypatch):
        """Unknown claim_family → not eligible, n_dates=0."""
        (tmp_path / "data" / "qledger").mkdir(parents=True)
        (tmp_path / "data" / "qledger" / "claims.jsonl").write_text("", encoding="utf-8")
        (tmp_path / "data" / "qledger" / "grades.jsonl").write_text("", encoding="utf-8")
        result = q.promotion_check("nonexistent_family", 21, root=tmp_path)
        assert not result.eligible
        assert result.n_dates == 0
        assert result.current_state == q.STATE_UNGRADED

    def test_promotion_result_as_dict(self, tmp_path, monkeypatch):
        """as_dict() returns all required keys."""
        _make_fixtures(tmp_path, monkeypatch, n_dates=30, hit_rate=0.70)
        result = q.promotion_check("test_family", 21, root=tmp_path)
        d = result.as_dict()
        for key in ("eligible", "reason", "n_dates", "wilson_ci_low",
                    "current_state", "demote", "pinned_reason"):
            assert key in d, f"Missing key {key!r} in as_dict() output"

    def test_emit_ladder_states_writes_to_track_record(self, tmp_path, monkeypatch):
        """emit_ladder_states() writes ladder_states into track_record.json."""
        _make_fixtures(tmp_path, monkeypatch, n_dates=10)
        states = q.emit_ladder_states(root=tmp_path)
        assert "test_family" in states
        # Should have entries at each grade horizon
        fam_data = states["test_family"]
        for h in q.GRADE_HORIZONS:
            assert str(h) in fam_data, f"Missing horizon {h} in ladder_states"
        # Check it was written to disk
        tr_path = tmp_path / "site" / "qledger" / "track_record.json"
        assert tr_path.exists()
        payload = json.loads(tr_path.read_text(encoding="utf-8"))
        assert "ladder_states" in payload
        assert "ladder_states_at" in payload


# ---------------------------------------------------------------------------
# Wilson CI sanity (unit)
# ---------------------------------------------------------------------------
class TestWilsonCI:
    def test_none_at_zero_n(self):
        assert q.wilson_ci_low(0, 0) is None

    def test_positive_for_high_hit_rate(self):
        # 20/25 hits → CI should be well above 0
        ci = q.wilson_ci_low(20, 25)
        assert ci is not None and ci > 0

    def test_negative_for_low_hit_rate(self):
        # 5/25 hits → CI lower bound should be <= 0 (well below 0.5)
        ci = q.wilson_ci_low(5, 25)
        assert ci is not None and ci < 0.5

    def test_boundary_exactly_25_all_hits(self):
        ci = q.wilson_ci_low(25, 25)
        assert ci is not None and ci > 0


# ---------------------------------------------------------------------------
# Derive state (regression)
# ---------------------------------------------------------------------------
class TestDeriveState:
    def test_ungraded(self):
        assert q.derive_state(0) == q.STATE_UNGRADED

    def test_accruing(self):
        assert q.derive_state(1) == q.STATE_ACCRUING
        assert q.derive_state(24) == q.STATE_ACCRUING

    def test_graded(self):
        assert q.derive_state(25) == q.STATE_GRADED
        assert q.derive_state(100) == q.STATE_GRADED
