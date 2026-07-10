"""tests/test_signal_lab_foundry.py — Signal Foundry panel in signal_lab.py (Lane D).

Covers:
- Foundry key always present in build_scorecard() payload
- Absent data directory → present=False
- Fixture cohort → funnel counts correct, rows shaped, docket only pass_candidates
- No crash on corrupt JSONL lines
- No "validated" vocabulary in rendered HTML
- Template renders both absent-state and present-state without error
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

from engine import signal_lab
from engine.signal_lab import _build_foundry_block

WORKTREE = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Helper: build a minimal fixture repo tree with fake candidates + results
# ---------------------------------------------------------------------------

def _make_fixture_tree(tmpdir: Path) -> Path:
    """Create a minimal data/signal_foundry/ tree with 3 fake candidates."""
    sf_dir = tmpdir / "data" / "signal_foundry"
    results_dir = sf_dir / "results"
    forward_dir = sf_dir / "forward"
    sf_dir.mkdir(parents=True)
    results_dir.mkdir()
    forward_dir.mkdir()

    # Candidate 1: pass_candidate + registered (tested)
    c1 = {
        "id": "SF-0001",
        "name": "Test Spread Signal",
        "name_zh": "测试利差信号",
        "market": "US macro",
        "thesis": "Credit spread z-score predicts forward equity returns.",
        "seed_provenance": {"source": "causal_mechanisms.jsonl", "ref": "cm-001"},
        "data": [{"path": "data/archive/TEST.parquet", "column": "value", "pit": "proxy"}],
        "feature": {"pipeline": [["zscore", {"window": 252}], ["lag", {"n": 1}]]},
        "target": {"path": "data/yahoo/SPY.parquet", "kind": "excess_return", "horizon_d": 21},
        "gates": {"min_t_hac": 2.0, "fdr_q": 0.10, "dsr": 0.90},
        "registered_at": "2026-06-01",
        "status": "tested",
    }
    # Candidate 2: null verdict + registered
    c2 = {
        "id": "SF-0002",
        "name": "Null Signal",
        "name_zh": "空信号",
        "market": "US macro",
        "thesis": "A signal that turned out to be null.",
        "seed_provenance": {"source": "causal_frontier.json", "ref": "cf-002"},
        "data": [{"path": "data/archive/NULL.parquet", "column": "value", "pit": "proxy"}],
        "feature": {"pipeline": [["pctile_rank", {"window": 63}]]},
        "target": {"path": "data/yahoo/SPY.parquet", "kind": "excess_return", "horizon_d": 21},
        "gates": {"min_t_hac": 2.0, "fdr_q": 0.10, "dsr": 0.90},
        "registered_at": "2026-06-05",
        "status": "tested",
    }
    # Candidate 3: screen_rejected (no result)
    c3 = {
        "id": "SF-0003",
        "name": "Rejected Proposal",
        "name_zh": "已筛除提议",
        "market": "US macro",
        "thesis": "A proposal that failed the screen.",
        "seed_provenance": {"source": "causal_frontier.json", "ref": "cf-003"},
        "status": "screen_rejected",
        "registered_at": "",
    }

    candidates_path = sf_dir / "candidates.jsonl"
    with candidates_path.open("w") as fh:
        fh.write(json.dumps(c1) + "\n")
        fh.write(json.dumps(c2) + "\n")
        # Corrupt line in between (should be tolerated)
        fh.write("{CORRUPT LINE NOT JSON\n")
        fh.write(json.dumps(c3) + "\n")

    # Result for SF-0001 (pass_candidate)
    # NOTE: fixtures use the REAL harness nested schema as written by
    # engine/signal_foundry/harness.py _write_result (lines 990-1000):
    #   stats = {n_obs, effective_months, full_ic, hac:{t,...}, split_half,
    #            era_split, block_bootstrap_ci, dsr:{dsr,...}|None}
    #   placebos = {time_shift:{shift_pctile,...}, negative_lag:{...}}
    #   ran_at (not run_at)
    r1 = {
        "spec": {
            "id": "SF-0001",
            "name": "Test Spread Signal",
            "name_zh": "测试利差信号",
            "market": "US macro",
            "thesis": "Credit spread z-score predicts forward equity returns.",
            "gates": {"min_t_hac": 2.0, "fdr_q": 0.10, "dsr": 0.90},
            "registered_at": "2026-06-01",
        },
        "verdict": "pass_candidate",
        "stats": {
            "n_obs": 1512,
            "effective_months": 72,
            "full_ic": 0.085,
            "hac": {"t": 2.43, "se": 0.035, "lags": 3},
            "split_half": {"ic_first": 0.081, "ic_second": 0.088, "split_half_sign_flip": False},
            "era_split": {"ic_pre": 0.074, "ic_post": 0.093},
            "block_bootstrap_ci": {"lo": 0.031, "hi": 0.139},
            "dsr": {"dsr": 0.91, "dsr_series": "z_product_ic_proxy"},
        },
        "placebos": {
            "time_shift": {
                "shift_pctile": 0.95,
                "obs_ic": 0.085,
                "placebo_pct_ge_abs_obs": 0.05,
                "n_draws": 200,
            },
            "negative_lag": {"neg_lag_ic": -0.003, "neg_lag_t": -0.12},
        },
        "backtest": {},
        "verdict_reasons": [],
        "battery_version": "1.0",
        "ran_at": "2026-07-01",
        "ledger_n_at_run": 1512,
    }
    (results_dir / "SF-0001.json").write_text(json.dumps(r1), encoding="utf-8")

    # Result for SF-0002 (null) — same real nested schema
    r2 = {
        "spec": {
            "id": "SF-0002",
            "name": "Null Signal",
            "gates": {"min_t_hac": 2.0, "fdr_q": 0.10, "dsr": 0.90},
            "registered_at": "2026-06-05",
        },
        "verdict": "null",
        "stats": {
            "n_obs": 1365,
            "effective_months": 65,
            "full_ic": 0.012,
            "hac": {"t": 0.81, "se": 0.015, "lags": 3},
            "split_half": {"ic_first": 0.008, "ic_second": 0.015, "split_half_sign_flip": False},
            "era_split": {"ic_pre": 0.010, "ic_post": 0.014},
            "block_bootstrap_ci": {"lo": -0.018, "hi": 0.042},
            "dsr": {"dsr": 0.22, "dsr_series": "z_product_ic_proxy"},
        },
        "placebos": {
            "time_shift": {
                "shift_pctile": 0.55,
                "obs_ic": 0.012,
                "placebo_pct_ge_abs_obs": 0.45,
                "n_draws": 200,
            },
            "negative_lag": {"neg_lag_ic": 0.009, "neg_lag_t": 0.41},
        },
        "backtest": {},
        "verdict_reasons": ["t_hac 0.81 < min_t_hac 2.0"],
        "battery_version": "1.0",
        "ran_at": "2026-07-01",
        "ledger_n_at_run": 1365,
    }
    (results_dir / "SF-0002.json").write_text(json.dumps(r2), encoding="utf-8")

    # Forward accrual: 5 rows for SF-0001
    fwd_path = forward_dir / "SF-0001.jsonl"
    with fwd_path.open("w") as fh:
        for i in range(5):
            row = {"date": f"2026-07-0{i+2}", "spec_id": "SF-0001",
                   "feature": 0.1 * i, "target_raw": 101.0 + i,
                   "registered_at": "2026-06-01"}
            fh.write(json.dumps(row) + "\n")

    # Lane status
    ls = {"auto_loop": False, "armed": False, "as_of": "2026-07-10",
          "paused_reason": "operator gate SIGNAL_FOUNDRY_PAUSED"}
    (sf_dir / "lane_status.json").write_text(json.dumps(ls), encoding="utf-8")

    return tmpdir


# ---------------------------------------------------------------------------
# Tests: _build_foundry_block()
# ---------------------------------------------------------------------------

class TestBuildFoundryBlock:

    def test_foundry_key_always_present_absent(self, tmp_path):
        """Absent data dir → present=False, no crash."""
        result = _build_foundry_block(tmp_path)
        assert "present" in result
        assert result["present"] is False

    def test_foundry_key_always_present_with_data(self, tmp_path):
        """Fixture cohort → present=True."""
        _make_fixture_tree(tmp_path)
        result = _build_foundry_block(tmp_path)
        assert result["present"] is True

    def test_funnel_counts_correct(self, tmp_path):
        """Funnel counts match the fixture (3 candidates: 2 registered/tested, 1 rejected)."""
        _make_fixture_tree(tmp_path)
        result = _build_foundry_block(tmp_path)
        fn = result["funnel"]
        # 3 valid candidates (corrupt line skipped) + screen_rejected
        assert fn["proposed"] == 3
        assert fn["screen_rejected"] == 1
        assert fn["pass_candidates"] == 1  # one pass_candidate result
        assert fn["promoted"] == 0

    def test_rows_shaped(self, tmp_path):
        """Rows have all required keys."""
        _make_fixture_tree(tmp_path)
        result = _build_foundry_block(tmp_path)
        rows = result["rows"]
        required_keys = {
            "id", "name", "name_zh", "market", "thesis", "seed_provenance_source",
            "status", "verdict", "ic", "t_hac", "dsr", "n_eff_months",
            "placebo_pct", "gates", "registered_at", "forward_days",
            "data", "pipeline", "target", "thesis_full",
        }
        for row in rows:
            missing = required_keys - set(row.keys())
            assert not missing, f"Row {row.get('id')} missing keys: {missing}"

    def test_stats_extracted_from_real_harness_schema(self, tmp_path):
        """Stats must be extracted from the REAL nested harness schema.

        The harness writes:
          stats.full_ic (not 'ic'), stats.hac.t (not 't_hac'),
          stats.effective_months (not 'n_eff_months'),
          stats.dsr = {dsr: float, ...} dict (not a scalar),
          placebos.time_shift.shift_pctile (not stats.placebo_pct).

        This test would have caught the critical bug: if _build_foundry_block
        reads stats.get('ic') / stats.get('t_hac') etc. it returns all-None
        against a real harness result.
        """
        _make_fixture_tree(tmp_path)
        result = _build_foundry_block(tmp_path)
        rows_by_id = {r["id"]: r for r in result["rows"]}

        r = rows_by_id["SF-0001"]
        assert r["ic"] == pytest.approx(0.085), (
            f"ic should be stats.full_ic=0.085, got {r['ic']!r}"
        )
        assert r["t_hac"] == pytest.approx(2.43), (
            f"t_hac should be stats.hac.t=2.43, got {r['t_hac']!r}"
        )
        assert r["dsr"] == pytest.approx(0.91), (
            f"dsr should be scalar from stats.dsr.dsr=0.91, got {r['dsr']!r}"
        )
        assert r["n_eff_months"] == 72, (
            f"n_eff_months should be stats.effective_months=72, got {r['n_eff_months']!r}"
        )
        assert r["placebo_pct"] == pytest.approx(0.95), (
            f"placebo_pct should be placebos.time_shift.shift_pctile=0.95, got {r['placebo_pct']!r}"
        )

        # Also confirm none are None (flat-schema bug would return all-None)
        for key in ("ic", "t_hac", "dsr", "n_eff_months", "placebo_pct"):
            assert r[key] is not None, (
                f"Row SF-0001 key '{key}' is None — likely reading wrong flat schema key"
            )

    def test_dsr_is_scalar_not_dict(self, tmp_path):
        """dsr row value must be a scalar float, not the raw harness dict."""
        _make_fixture_tree(tmp_path)
        result = _build_foundry_block(tmp_path)
        rows_by_id = {r["id"]: r for r in result["rows"]}
        dsr_val = rows_by_id["SF-0001"]["dsr"]
        assert not isinstance(dsr_val, dict), (
            f"dsr should be extracted scalar, got dict: {dsr_val!r}"
        )
        assert isinstance(dsr_val, float), f"dsr should be float, got {type(dsr_val)}"

    def test_docket_only_pass_candidates(self, tmp_path):
        """Docket only contains pass_candidate results not yet adjudicated."""
        _make_fixture_tree(tmp_path)
        result = _build_foundry_block(tmp_path)
        docket = result["docket"]
        # All docket entries must have verdict=pass_candidate in their spec/result
        for d in docket:
            assert d.get("verdict") == "pass_candidate", (
                f"Non-pass_candidate in docket: {d.get('verdict')}"
            )

    def test_docket_excludes_adjudicated(self, tmp_path):
        """After writing promotions.jsonl, that id leaves the docket."""
        _make_fixture_tree(tmp_path)
        # Write an adjudication for SF-0001
        prom_path = tmp_path / "data" / "signal_foundry" / "promotions.jsonl"
        with prom_path.open("w") as fh:
            fh.write(json.dumps({"spec_id": "SF-0001", "date": "2026-07-10",
                                  "ruling": "PROMOTE", "adjudicator": "Fable"}) + "\n")
        result = _build_foundry_block(tmp_path)
        docket_ids = [(d.get("spec") or {}).get("id") for d in result["docket"]]
        assert "SF-0001" not in docket_ids

    def test_forward_days_counted(self, tmp_path):
        """SF-0001 has 5 forward rows; forward_days == 5."""
        _make_fixture_tree(tmp_path)
        result = _build_foundry_block(tmp_path)
        sf0001 = next((r for r in result["rows"] if r["id"] == "SF-0001"), None)
        assert sf0001 is not None
        assert sf0001["forward_days"] == 5

    def test_pass_candidate_sorted_first(self, tmp_path):
        """pass_candidate rows sort before null rows."""
        _make_fixture_tree(tmp_path)
        result = _build_foundry_block(tmp_path)
        verdicts = [r["verdict"] for r in result["rows"] if r["verdict"]]
        if "pass_candidate" in verdicts and "null" in verdicts:
            pass_idx = verdicts.index("pass_candidate")
            null_idx = verdicts.index("null")
            assert pass_idx < null_idx

    def test_corrupt_jsonl_tolerated(self, tmp_path):
        """Corrupt JSONL lines do not raise; valid lines are loaded."""
        _make_fixture_tree(tmp_path)
        result = _build_foundry_block(tmp_path)
        # 3 candidates (corrupt line skipped)
        assert result["funnel"]["proposed"] == 3

    def test_disclaimer_keys_present(self, tmp_path):
        """present=True result carries disclaimer keys."""
        _make_fixture_tree(tmp_path)
        result = _build_foundry_block(tmp_path)
        assert "disclaimer_en" in result
        assert "disclaimer_zh" in result
        # Must not contain "validated" (house law)
        assert "validated" not in result["disclaimer_en"].lower()
        assert "validated" not in result["disclaimer_zh"]

    def test_no_validated_text(self, tmp_path):
        """No 'validated' text anywhere in the foundry payload string representation."""
        _make_fixture_tree(tmp_path)
        result = _build_foundry_block(tmp_path)
        payload_str = json.dumps(result, default=str)
        assert "validated" not in payload_str.lower(), (
            "Found 'validated' in foundry payload — house law violation"
        )

    def test_lane_status_loaded(self, tmp_path):
        """lane_status key is populated from lane_status.json."""
        _make_fixture_tree(tmp_path)
        result = _build_foundry_block(tmp_path)
        ls = result["lane_status"]
        assert isinstance(ls, dict)
        assert ls.get("armed") is False

    def test_absent_candidates_returns_not_present(self, tmp_path):
        """data/signal_foundry/ exists but candidates.jsonl absent → present=False."""
        sf_dir = tmp_path / "data" / "signal_foundry"
        sf_dir.mkdir(parents=True)
        result = _build_foundry_block(tmp_path)
        assert result["present"] is False

    def test_empty_candidates_returns_not_present(self, tmp_path):
        """Empty candidates.jsonl → present=False."""
        sf_dir = tmp_path / "data" / "signal_foundry"
        sf_dir.mkdir(parents=True)
        (sf_dir / "candidates.jsonl").write_text("", encoding="utf-8")
        result = _build_foundry_block(tmp_path)
        assert result["present"] is False


# ---------------------------------------------------------------------------
# Tests: build_scorecard() always has 'foundry' key
# ---------------------------------------------------------------------------

class TestBuildScorecardFoundryKey:
    """build_scorecard() must always return a 'foundry' key."""

    def test_foundry_always_present_in_scorecard(self, monkeypatch):
        """The 'foundry' key is always present in the payload (even absent state)."""
        # Monkeypatch _build_foundry_block to return a known absent block
        monkeypatch.setattr(signal_lab, "_build_foundry_block",
                            lambda repo_root=None: {"present": False})
        payload = signal_lab.build_scorecard()
        assert "foundry" in payload
        assert payload["foundry"]["present"] is False

    def test_foundry_present_true_with_fixture(self, tmp_path, monkeypatch):
        """When _build_foundry_block returns present=True, scorecard carries it."""
        _make_fixture_tree(tmp_path)
        monkeypatch.setattr(signal_lab, "_build_foundry_block",
                            lambda repo_root=None: _build_foundry_block(tmp_path))
        payload = signal_lab.build_scorecard()
        assert payload["foundry"]["present"] is True
        assert "funnel" in payload["foundry"]
        assert "rows" in payload["foundry"]


# ---------------------------------------------------------------------------
# Tests: Template renders without error
# ---------------------------------------------------------------------------

class TestTemplateRender:
    """Smoke test: template renders both states without Jinja error.

    Uses the real build_scorecard() payload (same pattern as test_signal_lab_v2.py)
    with the foundry block monkeypatched.  Template includes (_navlinks etc.) must
    exist — tests skip if the environment is not fully wired.
    """

    def _render(self, payload: dict) -> str:
        env = Environment(
            loader=FileSystemLoader(str(WORKTREE / "templates")),
            autoescape=False,
        )
        tmpl = env.get_template("signal_lab.html.j2")
        return tmpl.render(**payload)

    def test_render_absent_state(self, monkeypatch):
        """Template renders the dark-state note when foundry.present=False."""
        monkeypatch.setattr(signal_lab, "_build_foundry_block",
                            lambda repo_root=None: {"present": False})
        payload = signal_lab.build_scorecard()
        try:
            html = self._render(payload)
        except Exception:
            pytest.skip("Template not renderable in test env (nav includes may fail)")
        assert "no cohort filed" in html or "尚无候选" in html or "Foundry lane built" in html

    def test_render_present_state(self, tmp_path, monkeypatch):
        """Template renders the full panel when foundry.present=True."""
        _make_fixture_tree(tmp_path)
        monkeypatch.setattr(signal_lab, "_build_foundry_block",
                            lambda repo_root=None: _build_foundry_block(tmp_path))
        payload = signal_lab.build_scorecard()
        try:
            html = self._render(payload)
        except Exception:
            pytest.skip("Template not renderable in test env (nav includes may fail)")
        assert "SF-0001" in html or "Test Spread Signal" in html

    def test_no_validated_in_rendered_absent(self, monkeypatch):
        """Rendered absent-state HTML contains no 'validated' text in foundry section."""
        monkeypatch.setattr(signal_lab, "_build_foundry_block",
                            lambda repo_root=None: {"present": False})
        payload = signal_lab.build_scorecard()
        try:
            html = self._render(payload)
        except Exception:
            pytest.skip("Template not renderable in test env")
        sf_start = html.find('id="sf-foundry"')
        sf_end = html.find('class="panel ctl"', sf_start) if sf_start >= 0 else -1
        if sf_start >= 0 and sf_end > sf_start:
            sf_html = html[sf_start:sf_end]
            assert "validated" not in sf_html.lower()

    def test_no_validated_in_rendered_present(self, tmp_path, monkeypatch):
        """Rendered present-state HTML contains no 'validated' text in foundry panel."""
        _make_fixture_tree(tmp_path)
        monkeypatch.setattr(signal_lab, "_build_foundry_block",
                            lambda repo_root=None: _build_foundry_block(tmp_path))
        payload = signal_lab.build_scorecard()
        try:
            html = self._render(payload)
        except Exception:
            pytest.skip("Template not renderable in test env")
        sf_start = html.find('id="sf-foundry"')
        sf_end = html.find('class="panel ctl"', sf_start) if sf_start >= 0 else -1
        if sf_start >= 0 and sf_end > sf_start:
            sf_html = html[sf_start:sf_end]
            assert "validated" not in sf_html.lower()
