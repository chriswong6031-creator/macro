"""tests/test_context_risk.py — Unit tests for scripts/build_context_risk.py (W3, R-CI7).

Tests cover:
1. constants_spot_check    — assert key values from field guide match constants module.
2. composition_ratios      — fabricated board+personality yields correct archetype ratios.
3. insufficient_n_path     — fabricated regime state outside adequate-n cells → insufficient_n.
4. missing_inputs          — missing standouts/personality/regime → available:false artifact written.
5. fail_open               — build_context_risk never raises on corrupt inputs.
6. world_state_subblock    — _compose_context_risk returns available:False when artifact absent.
7. world_state_fail_open   — _compose_context_risk never raises on corrupt artifact file.
8. json_round_trip         — payload is JSON-serializable.
9. forbidden_words         — "validated" does not appear in artifact.
10. authority_block        — artifact carries correct authority stanza.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Import targets
# ---------------------------------------------------------------------------

from scripts.build_context_risk import build_context_risk, _atomic_write_json, main
from engine.neuralweb.context_risk_constants import (
    ARCHETYPE_FINGERPRINTS,
    ARCHETYPE_QUAD_P10,
    ARCHETYPE_QUAD_MEDIAN,
    ARCHETYPE_LIQUIDITY_MEDIAN,
    MIN_N_ADEQUATE,
)


# ---------------------------------------------------------------------------
# Helpers to write fabricated inputs to tmp_path
# ---------------------------------------------------------------------------

def _write_standouts(tmp_path: Path, buy_tickers: list[str], watch: list[str] | None = None, laggards: list[str] | None = None) -> Path:
    p = tmp_path / "site" / "factordata"
    p.mkdir(parents=True, exist_ok=True)
    buy = [{"ticker": t, "name": t} for t in buy_tickers]
    watch_list = [{"ticker": t, "name": t} for t in (watch or [])]
    lag_list = [{"ticker": t, "name": t} for t in (laggards or [])]
    payload = {
        "as_of": "2026-07-07",
        "buy": buy,
        "watch": watch_list,
        "laggards": lag_list,
    }
    out = p / "us_standouts.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    return out


def _write_personality(tmp_path: Path, per_ticker: dict) -> Path:
    p = tmp_path / "site" / "factordata"
    p.mkdir(parents=True, exist_ok=True)
    # Build minimal label_distributions from per_ticker
    arch_dist: dict = {}
    chart_dist: dict = {}
    for rec in per_ticker.values():
        arch = rec.get("arch")
        if arch:
            arch_dist[arch] = arch_dist.get(arch, 0) + 1
        for ch in (rec.get("chart") or []):
            chart_dist[ch] = chart_dist.get(ch, 0) + 1
    payload = {
        "schema": "stock_personality.v1",
        "as_of": "2026-07-07",
        "n_tickers": len(per_ticker),
        "coverage": {"archetype": 0.85},
        "label_distributions": {
            "archetype": arch_dist,
            "chart_personality": chart_dist,
        },
        "per_ticker": per_ticker,
    }
    out = p / "stock_personality.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    return out


def _write_regime(tmp_path: Path, quad: str = "Q1", liq: str = "expanding") -> Path:
    p = tmp_path / "site"
    p.mkdir(parents=True, exist_ok=True)
    payload = {
        "dates": ["2026-07-07"],
        "quad": [quad],
        "liq": [liq],
        "g": [1.0],
        "i": [1.0],
        "conf": [1.0],
    }
    out = p / "regime_timeline.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    return out


def _write_context_risk_artifact(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "data" / "neuralweb"
    p.mkdir(parents=True, exist_ok=True)
    out = p / "context_risk.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# 1. Constants spot-check — assert key values from field guide
# ---------------------------------------------------------------------------

class TestConstantsSpotCheck:
    def test_speculative_unprofitable_vol(self):
        """Field guide §1 Table 1: speculative_unprofitable Vol_med = 0.378."""
        assert ARCHETYPE_FINGERPRINTS["speculative_unprofitable"]["vol_med"] == 0.378

    def test_speculative_unprofitable_disp(self):
        """Field guide §1 Table 1: speculative_unprofitable Disp = 0.544."""
        assert ARCHETYPE_FINGERPRINTS["speculative_unprofitable"]["disp"] == 0.544

    def test_high_beta_momentum_pnr(self):
        """Field guide §1 Table 1: high_beta_momentum %NR_in_yr = 61%."""
        assert ARCHETYPE_FINGERPRINTS["high_beta_momentum"]["pct_never_recover_1yr"] == 0.61

    def test_high_beta_momentum_q1_p10(self):
        """Field guide §3 Table 2: high_beta_momentum Q1 worst-decile = -10.4% = -0.104."""
        assert ARCHETYPE_QUAD_P10["high_beta_momentum"]["Q1"] == pytest.approx(-0.104)

    def test_financial_disp(self):
        """Field guide §1 Table 1: financial Disp = 0.162."""
        assert ARCHETYPE_FINGERPRINTS["financial"]["disp"] == 0.162

    def test_dividend_defensive_vol(self):
        """Field guide §1 Table 1: dividend_defensive Vol_med = 0.218."""
        assert ARCHETYPE_FINGERPRINTS["dividend_defensive"]["vol_med"] == 0.218

    def test_secular_growth_q3_median_negative(self):
        """Field guide §3 Table 1: secular_growth Q3 median = -0.011 (negative)."""
        val = ARCHETYPE_QUAD_MEDIAN["secular_growth"]["Q3"]["med"]
        assert val == pytest.approx(-0.011)

    def test_quality_compounder_pnr_lowest(self):
        """Field guide §1: quality_compounder %NR_in_yr = 38% (lowest in universe)."""
        assert ARCHETYPE_FINGERPRINTS["quality_compounder"]["pct_never_recover_1yr"] == 0.38

    def test_commodity_sensitive_absent(self):
        """Field guide: commodity_sensitive absent from deep corpus — should not be in fingerprints."""
        assert "commodity_sensitive" not in ARCHETYPE_FINGERPRINTS

    def test_min_n_adequate(self):
        """MIN_N_ADEQUATE = 887 per field guide §3 (dividend_defensive Q3 minimum)."""
        assert MIN_N_ADEQUATE == 887

    def test_distressed_liquidity_contracting(self):
        """Field guide §3 Table 3: distressed contracting liquidity median = 0.004."""
        val = ARCHETYPE_LIQUIDITY_MEDIAN["distressed"]["contracting"]["med"]
        assert val == pytest.approx(0.004)


# ---------------------------------------------------------------------------
# 2. Composition ratios — fabricated board → correct archetype overweights
# ---------------------------------------------------------------------------

class TestCompositionRatios:
    def test_buy_board_archetype_overweight(self, tmp_path: Path):
        """Board with 3 high_beta_momentum, 1 mixed out of universe of 1:1 → HBM overweighted."""
        # Universe: 10 high_beta_momentum, 10 mixed (50/50)
        univ = {
            f"UHBM{i}": {"arch": "high_beta_momentum", "chart": ["mixed_chart"], "own": [], "modes": ["normal"]}
            for i in range(10)
        }
        univ.update({
            f"UMIX{i}": {"arch": "mixed", "chart": ["mixed_chart"], "own": [], "modes": ["normal"]}
            for i in range(10)
        })
        # Board: 3 HBM, 1 mixed (75% HBM vs 50% universe → ratio ~1.5)
        board_tickers = ["UHBM0", "UHBM1", "UHBM2", "UMIX0"]

        _write_standouts(tmp_path, buy_tickers=board_tickers)
        _write_personality(tmp_path, per_ticker=univ)
        _write_regime(tmp_path, quad="Q1", liq="expanding")

        payload = build_context_risk(root=tmp_path)

        assert payload["available"] is True
        board_comp = payload["board_buy_lane"]["composition"]["archetype"]
        hbm_cell = board_comp.get("high_beta_momentum", {})
        # 3/4 = 0.75 member_share, 10/20 = 0.5 universe_share → ratio ~1.5
        assert hbm_cell["member_share"] == pytest.approx(0.75, abs=0.01)
        assert hbm_cell["universe_share"] == pytest.approx(0.5, abs=0.01)
        assert hbm_cell["ratio"] == pytest.approx(1.5, abs=0.05)

    def test_board_member_count(self, tmp_path: Path):
        """n_members in board_buy_lane matches buy ticker count."""
        per_ticker = {
            "AAA": {"arch": "rate_sensitive", "chart": ["mixed_chart"], "own": [], "modes": ["normal"]},
            "BBB": {"arch": "cyclical", "chart": ["mixed_chart"], "own": [], "modes": ["normal"]},
            "CCC": {"arch": "financial", "chart": ["mixed_chart"], "own": [], "modes": ["normal"]},
        }
        _write_standouts(tmp_path, buy_tickers=["AAA", "BBB"])
        _write_personality(tmp_path, per_ticker=per_ticker)
        _write_regime(tmp_path)

        payload = build_context_risk(root=tmp_path)
        assert payload["board_buy_lane"]["n_members"] == 2

    def test_unlabeled_ticker_counted(self, tmp_path: Path):
        """Ticker with null arch is counted as unlabeled."""
        per_ticker = {
            "AAA": {"arch": None, "chart": ["mixed_chart"], "own": [], "modes": ["normal"]},
            "BBB": {"arch": "cyclical", "chart": ["mixed_chart"], "own": [], "modes": ["normal"]},
        }
        _write_standouts(tmp_path, buy_tickers=["AAA", "BBB"])
        _write_personality(tmp_path, per_ticker=per_ticker)
        _write_regime(tmp_path)

        payload = build_context_risk(root=tmp_path)
        flags = payload["board_buy_lane"]["flags"]
        assert flags["n_unlabeled_arch"] >= 1

    def test_top_overweights_sorted_desc(self, tmp_path: Path):
        """top_overweights are sorted by ratio descending."""
        per_ticker = {
            "A1": {"arch": "speculative_unprofitable", "chart": [], "own": [], "modes": ["normal"]},
            "A2": {"arch": "speculative_unprofitable", "chart": [], "own": [], "modes": ["normal"]},
            "B1": {"arch": "mixed", "chart": [], "own": [], "modes": ["normal"]},
            "C1": {"arch": "high_beta_momentum", "chart": [], "own": [], "modes": ["normal"]},
        }
        _write_standouts(tmp_path, buy_tickers=["A1", "A2", "B1", "C1"])
        _write_personality(tmp_path, per_ticker=per_ticker)
        _write_regime(tmp_path)

        payload = build_context_risk(root=tmp_path)
        ow = payload["board_buy_lane"]["top_overweights"]
        if len(ow) >= 2:
            ratios = [x["ratio"] for x in ow]
            assert ratios == sorted(ratios, reverse=True)


# ---------------------------------------------------------------------------
# 3. insufficient_n path — fabricated regime state with all cells below floor
# ---------------------------------------------------------------------------

class TestInsufficientN:
    def test_insufficient_n_when_no_archetype_matches(self, tmp_path: Path):
        """When board only has archetypes not in field guide, regime read marks insufficient/unavailable."""
        per_ticker = {
            "FAKE1": {"arch": "commodity_sensitive", "chart": [], "own": [], "modes": ["normal"]},
        }
        _write_standouts(tmp_path, buy_tickers=["FAKE1"])
        _write_personality(tmp_path, per_ticker=per_ticker)
        _write_regime(tmp_path, quad="Q1", liq="expanding")

        payload = build_context_risk(root=tmp_path)
        rr = payload["board_buy_lane"]["regime_conditional"]
        # Should mark weighted_p10_21d and weighted_median_21d as None when no valid cells
        # commodity_sensitive not in field guide → falls through to not_in_field_guide
        assert rr.get("weighted_p10_21d") is None or rr.get("available") is False

    def test_sufficient_cells_produce_numbers(self, tmp_path: Path):
        """Board with archetypes that have adequate cells in Q1 → non-None weighted values."""
        per_ticker = {
            "CYCL": {"arch": "cyclical", "chart": ["mixed_chart"], "own": [], "modes": ["normal"]},
            "RATE": {"arch": "rate_sensitive", "chart": ["mixed_chart"], "own": [], "modes": ["normal"]},
        }
        _write_standouts(tmp_path, buy_tickers=["CYCL", "RATE"])
        _write_personality(tmp_path, per_ticker=per_ticker)
        _write_regime(tmp_path, quad="Q1", liq="expanding")

        payload = build_context_risk(root=tmp_path)
        rr = payload["board_buy_lane"]["regime_conditional"]
        assert rr["available"] is True
        assert rr["weighted_median_21d"] is not None
        assert rr["weighted_p10_21d"] is not None
        # Q1 cells for cyclical (n=16404) and rate_sensitive (n=19340) both >> 887
        assert rr["n_insufficient_cells"] == 0


# ---------------------------------------------------------------------------
# 4. Missing inputs → available:false artifact written (fail-open)
# ---------------------------------------------------------------------------

class TestMissingInputs:
    def test_missing_all_inputs_available_false(self, tmp_path: Path):
        """When none of the three inputs exist, artifact is written with available=False."""
        payload = build_context_risk(root=tmp_path)
        assert payload["available"] is False
        assert len(payload["missing_inputs"]) > 0

    def test_missing_personality_available_false(self, tmp_path: Path):
        """Missing stock_personality.json → available=False."""
        _write_standouts(tmp_path, buy_tickers=["TSLA"])
        # No personality file
        _write_regime(tmp_path)

        payload = build_context_risk(root=tmp_path)
        assert payload["available"] is False
        assert any("stock_personality" in m for m in payload["missing_inputs"])

    def test_missing_standouts_available_false(self, tmp_path: Path):
        """Missing us_standouts.json → available=False."""
        per_ticker = {"TSLA": {"arch": "speculative_unprofitable", "chart": [], "own": [], "modes": []}}
        _write_personality(tmp_path, per_ticker=per_ticker)
        _write_regime(tmp_path)
        # No standouts file

        payload = build_context_risk(root=tmp_path)
        assert payload["available"] is False

    def test_missing_inputs_still_writes_files(self, tmp_path: Path):
        """main() writes both artifact files even when inputs are missing."""
        rc = main(["--root", str(tmp_path)])
        assert rc == 0
        data_path = tmp_path / "data" / "neuralweb" / "context_risk.json"
        site_path = tmp_path / "site" / "neuralwebdata" / "context_risk.json"
        assert data_path.exists()
        assert site_path.exists()
        # Content must be parseable JSON
        parsed = json.loads(data_path.read_text())
        assert "available" in parsed


# ---------------------------------------------------------------------------
# 5. Fail-open — build_context_risk never raises on corrupt inputs
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_corrupt_standouts_no_raise(self, tmp_path: Path):
        """Corrupt us_standouts.json does not raise."""
        p = tmp_path / "site" / "factordata"
        p.mkdir(parents=True, exist_ok=True)
        (p / "us_standouts.json").write_text("NOT JSON", encoding="utf-8")
        _write_personality(tmp_path, per_ticker={"X": {"arch": "mixed", "chart": [], "own": [], "modes": []}})
        _write_regime(tmp_path)

        payload = build_context_risk(root=tmp_path)
        assert isinstance(payload, dict)
        assert "available" in payload

    def test_corrupt_personality_no_raise(self, tmp_path: Path):
        """Corrupt stock_personality.json does not raise."""
        _write_standouts(tmp_path, buy_tickers=["TSLA"])
        p = tmp_path / "site" / "factordata"
        (p / "stock_personality.json").write_text("BROKEN{{{", encoding="utf-8")
        _write_regime(tmp_path)

        payload = build_context_risk(root=tmp_path)
        assert isinstance(payload, dict)

    def test_corrupt_regime_no_raise(self, tmp_path: Path):
        """Corrupt regime_timeline.json does not raise."""
        _write_standouts(tmp_path, buy_tickers=["TSLA"])
        _write_personality(tmp_path, per_ticker={"TSLA": {"arch": "speculative_unprofitable", "chart": [], "own": [], "modes": []}})
        (tmp_path / "site" / "regime_timeline.json").write_text("{]", encoding="utf-8")

        payload = build_context_risk(root=tmp_path)
        assert isinstance(payload, dict)


# ---------------------------------------------------------------------------
# 6. world_state sub-block — _compose_context_risk returns available:False when artifact absent
# ---------------------------------------------------------------------------

class TestWorldStateSubBlock:
    def test_absent_artifact_returns_available_false(self, tmp_path: Path):
        from engine.neuralweb.world_state import _compose_context_risk
        result = _compose_context_risk(root=tmp_path)
        assert result["available"] is False
        assert result["display_only"] is True

    def test_present_artifact_returns_available_true(self, tmp_path: Path):
        from engine.neuralweb.world_state import _compose_context_risk

        # Write a valid artifact
        per_ticker = {
            "CYCL": {"arch": "cyclical", "chart": ["mixed_chart"], "own": [], "modes": ["normal"]},
        }
        _write_standouts(tmp_path, buy_tickers=["CYCL"])
        _write_personality(tmp_path, per_ticker=per_ticker)
        _write_regime(tmp_path, quad="Q1", liq="expanding")

        payload = build_context_risk(root=tmp_path)
        _write_context_risk_artifact(tmp_path, payload)

        result = _compose_context_risk(root=tmp_path)
        assert result["available"] is True
        assert result["display_only"] is True
        assert "board_top_overweights" in result

    def test_present_artifact_contains_regime_context(self, tmp_path: Path):
        from engine.neuralweb.world_state import _compose_context_risk

        per_ticker = {
            "RATE": {"arch": "rate_sensitive", "chart": ["mixed_chart"], "own": [], "modes": ["normal"]},
        }
        _write_standouts(tmp_path, buy_tickers=["RATE"])
        _write_personality(tmp_path, per_ticker=per_ticker)
        _write_regime(tmp_path, quad="Q2", liq="contracting")

        payload = build_context_risk(root=tmp_path)
        _write_context_risk_artifact(tmp_path, payload)

        result = _compose_context_risk(root=tmp_path)
        assert result.get("regime_context", {}).get("quad") == "Q2"


# ---------------------------------------------------------------------------
# 7. world_state fail-open — _compose_context_risk never raises on corrupt artifact
# ---------------------------------------------------------------------------

class TestWorldStateFailOpen:
    def test_corrupt_artifact_no_raise(self, tmp_path: Path):
        from engine.neuralweb.world_state import _compose_context_risk

        p = tmp_path / "data" / "neuralweb"
        p.mkdir(parents=True, exist_ok=True)
        (p / "context_risk.json").write_text("NOT JSON {{{", encoding="utf-8")

        result = _compose_context_risk(root=tmp_path)
        assert isinstance(result, dict)
        assert result["available"] is False

    def test_non_dict_artifact_no_raise(self, tmp_path: Path):
        from engine.neuralweb.world_state import _compose_context_risk

        p = tmp_path / "data" / "neuralweb"
        p.mkdir(parents=True, exist_ok=True)
        (p / "context_risk.json").write_text("[1, 2, 3]", encoding="utf-8")

        result = _compose_context_risk(root=tmp_path)
        assert isinstance(result, dict)
        assert result["available"] is False


# ---------------------------------------------------------------------------
# 8. JSON round-trip
# ---------------------------------------------------------------------------

class TestJsonRoundTrip:
    def test_payload_serializable(self, tmp_path: Path):
        """build_context_risk output is JSON-serializable."""
        per_ticker = {
            "TSLA": {"arch": "speculative_unprofitable", "chart": ["mixed_chart"], "own": [], "modes": ["normal"]},
            "KKR": {"arch": "financial", "chart": ["stair_step_leader"], "own": [], "modes": ["normal"]},
        }
        _write_standouts(tmp_path, buy_tickers=["TSLA", "KKR"])
        _write_personality(tmp_path, per_ticker=per_ticker)
        _write_regime(tmp_path, quad="Q1", liq="expanding")

        payload = build_context_risk(root=tmp_path)
        json_str = json.dumps(payload, ensure_ascii=False, default=str)
        reparsed = json.loads(json_str)
        assert reparsed["schema"] == "neuralweb.context_risk.v1"


# ---------------------------------------------------------------------------
# 9. Forbidden words — "validated" must not appear
# ---------------------------------------------------------------------------

class TestForbiddenWords:
    def test_validated_absent(self, tmp_path: Path):
        """The word 'validated' must not appear in the artifact (CI-guarded law)."""
        per_ticker = {
            "TSLA": {"arch": "speculative_unprofitable", "chart": [], "own": [], "modes": ["normal"]},
        }
        _write_standouts(tmp_path, buy_tickers=["TSLA"])
        _write_personality(tmp_path, per_ticker=per_ticker)
        _write_regime(tmp_path)

        payload = build_context_risk(root=tmp_path)
        json_str = json.dumps(payload)
        # Case-insensitive check
        assert "validated" not in json_str.lower(), (
            "Artifact must not contain the word 'validated' — CI-guarded law"
        )


# ---------------------------------------------------------------------------
# 10. Authority block — correct stanza
# ---------------------------------------------------------------------------

class TestAuthorityBlock:
    def test_authority_block_present(self, tmp_path: Path):
        """Artifact must carry authority block with tier=display and article2 note."""
        per_ticker = {
            "CYCL": {"arch": "cyclical", "chart": [], "own": [], "modes": ["normal"]},
        }
        _write_standouts(tmp_path, buy_tickers=["CYCL"])
        _write_personality(tmp_path, per_ticker=per_ticker)
        _write_regime(tmp_path)

        payload = build_context_risk(root=tmp_path)
        auth = payload.get("authority")
        assert auth is not None
        assert auth.get("tier") == "display"
        assert auth.get("weights") == "none"
        assert "Article 2" in auth.get("article2_law", "")

    def test_display_only_true(self, tmp_path: Path):
        """Top-level display_only must be True."""
        per_ticker = {"X": {"arch": "mixed", "chart": [], "own": [], "modes": []}}
        _write_standouts(tmp_path, buy_tickers=["X"])
        _write_personality(tmp_path, per_ticker=per_ticker)
        _write_regime(tmp_path)

        payload = build_context_risk(root=tmp_path)
        assert payload["display_only"] is True
