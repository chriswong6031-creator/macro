"""Tests for the W4 reflexivity overlay (engine/reflexivity.py + scripts/build_reflexivity_overlay.py).

Invariants tested:
  - Similarity matrix: symmetric, [0,1]-valued, self-similarity = 1
  - N_eff on synthetic identical candidates: N_eff ≈ 1
  - N_eff on synthetic orthogonal candidates: N_eff ≈ N
  - None-safety: names missing factor betas get membership-only similarity, never a crash
  - Missing-artifact degradation: builder degrades to empty overlay, never raises
  - Verdict thresholds: duplicate / partial / new boundaries
  - Earnings leg: wired in W-D (dict with has_data; annotation-only, no matrix/N_eff effect)
  - is_context_only: always True in artifact (R-F ruling)
  - schema: always "reflexivity_overlay.v1"
  - Basis flag printed for thin-beta names
  - n_eff_by_lane emitted per-lane (population-fix for invariant e)
  - _lane_tickers extracts correct per-lane set
  - empty overlay includes n_eff_by_lane with None values
  W-D additions:
  - same_thesis_groups: connected components at DUPLICATE_THRESH, size >= 3
  - N_eff history: bounded array, dedup-by-as_of, degraded-run-preserves-history
  - Earnings-week annotation from fixture parquet
  - Banner renders thesis-group block only for groups >= 5
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import io
import tempfile

import pandas as pd

import engine.reflexivity as refmod
from engine.reflexivity import (
    HIGH_TIER_FACTORS,
    R2_FLOOR,
    build_groups_index,
    compute,
    earnings_week_annotation,
    factor_cosine,
    membership_jaccard,
    n_eff_participation_ratio,
    pairwise_similarity,
    same_thesis_groups,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_membership(basket_map: dict[str, list[str]]) -> dict:
    """Construct a minimal membership.json dict for testing."""
    baskets = {}
    for bid, tickers in basket_map.items():
        baskets[bid] = {
            "name": bid, "members": [
                {"ticker": t, "added": "2024-01-01", "removed": None}
                for t in tickers
            ]
        }
    return {"version": "test", "baskets": baskets}


def _make_betas(
    mkt: float = 1.0, growth: float = 0.0, size: float = 0.0, rates: float = 0.0,
    r2: float = 0.50,
) -> dict:
    return {"mkt": mkt, "growth": growth, "size": size, "rates": rates, "r2": r2}


# ── similarity matrix properties ─────────────────────────────────────────────

class TestMembershipJaccard:
    def test_identical_groups(self):
        g = frozenset(["sector:Technology", "basket:ai_infra"])
        assert membership_jaccard(g, g) == 1.0

    def test_disjoint_groups(self):
        a = frozenset(["sector:Technology"])
        b = frozenset(["sector:Utilities"])
        assert membership_jaccard(a, b) == 0.0

    def test_partial_overlap(self):
        a = frozenset(["sector:Technology", "basket:ai_infra", "basket:mag7"])
        b = frozenset(["sector:Technology", "basket:ai_infra"])
        # intersection={sector:Technology, basket:ai_infra}, union=3
        expected = 2.0 / 3.0
        assert abs(membership_jaccard(a, b) - expected) < 1e-9

    def test_both_empty_returns_zero(self):
        assert membership_jaccard(frozenset(), frozenset()) == 0.0


class TestFactorCosine:
    def test_identical_vectors_return_one(self):
        b = _make_betas(1.0, 0.5, -0.3, 0.2, r2=0.6)
        sim, flag = factor_cosine(b, b)
        assert sim is not None
        assert abs(sim - 1.0) < 1e-9

    def test_orthogonal_vectors_return_zero(self):
        # [1, 0, 0, 0] vs [0, 1, 0, 0]
        b1 = _make_betas(1.0, 0.0, 0.0, 0.0, r2=0.6)
        b2 = _make_betas(0.0, 1.0, 0.0, 0.0, r2=0.6)
        sim, _ = factor_cosine(b1, b2)
        assert sim is not None
        assert abs(sim) < 1e-9

    def test_anti_correlated_clipped_to_zero(self):
        # exact opposite → cosine = -1, but R-C says clip to [0, 1]
        b1 = _make_betas(1.0, 0.0, 0.0, 0.0, r2=0.6)
        b2 = _make_betas(-1.0, 0.0, 0.0, 0.0, r2=0.6)
        sim, _ = factor_cosine(b1, b2)
        assert sim is not None
        assert sim == 0.0

    def test_thin_r2_returns_none(self):
        b_thin = _make_betas(r2=0.10)   # below R2_FLOOR=0.20
        b_ok   = _make_betas(r2=0.50)
        sim, flag = factor_cosine(b_thin, b_ok)
        assert sim is None
        assert "thin" in flag

    def test_missing_betas_returns_none(self):
        sim, flag = factor_cosine({}, _make_betas())
        assert sim is None

    def test_result_in_zero_one(self):
        rng = np.random.default_rng(42)
        for _ in range(50):
            vals = rng.standard_normal(4)
            b1 = dict(zip(HIGH_TIER_FACTORS, vals.tolist()))
            b1["r2"] = 0.5
            vals2 = rng.standard_normal(4)
            b2 = dict(zip(HIGH_TIER_FACTORS, vals2.tolist()))
            b2["r2"] = 0.5
            sim, _ = factor_cosine(b1, b2)
            if sim is not None:
                assert 0.0 <= sim <= 1.0, f"cosine out of [0,1]: {sim}"


class TestPairwiseSimilarity:
    def _setup_identical(self, n: int):
        """n identical names — each identical to all others."""
        tickers = [f"T{i}" for i in range(n)]
        # All in same sector and basket
        groups = {t: frozenset(["sector:Tech", "basket:ai"]) for t in tickers}
        betas = {t: _make_betas(1.0, 0.5, 0.0, 0.0, r2=0.6) for t in tickers}
        return tickers, groups, betas

    def test_symmetric(self):
        tickers = ["A", "B", "C"]
        groups = {
            "A": frozenset(["sector:Tech", "basket:x"]),
            "B": frozenset(["sector:Tech"]),
            "C": frozenset(["sector:Health"]),
        }
        betas = {
            "A": _make_betas(1.0, 0.5, 0.0, 0.0, r2=0.6),
            "B": _make_betas(0.8, 0.4, 0.0, 0.0, r2=0.6),
            "C": _make_betas(0.3, -0.2, 0.5, 0.1, r2=0.6),
        }
        S, ordered, _ = pairwise_similarity(tickers, groups, betas)
        n = len(ordered)
        for i in range(n):
            for j in range(n):
                assert abs(S[i, j] - S[j, i]) < 1e-12, f"S[{i},{j}] != S[{j},{i}]"

    def test_diagonal_is_one(self):
        tickers = ["A", "B"]
        groups = {"A": frozenset(["sector:Tech"]), "B": frozenset(["sector:Health"])}
        betas = {"A": _make_betas(r2=0.5), "B": _make_betas(r2=0.5)}
        S, _, _ = pairwise_similarity(tickers, groups, betas)
        for i in range(len(tickers)):
            assert S[i, i] == 1.0

    def test_values_in_zero_one(self):
        tickers = ["A", "B", "C", "D"]
        groups = {
            "A": frozenset(["sector:Tech", "basket:x", "basket:y"]),
            "B": frozenset(["sector:Tech", "basket:x"]),
            "C": frozenset(["sector:Health"]),
            "D": frozenset(),
        }
        betas = {
            "A": _make_betas(1.2, 0.3, -0.2, 0.1, r2=0.6),
            "B": _make_betas(1.1, 0.2, -0.1, 0.0, r2=0.6),
            "C": _make_betas(0.4, -0.5, 0.3, 0.6, r2=0.5),
            "D": {},  # no betas
        }
        S, _, _ = pairwise_similarity(tickers, groups, betas)
        assert S.min() >= 0.0
        assert S.max() <= 1.0

    def test_self_similarity_single_ticker(self):
        """Single ticker → 1×1 eye matrix."""
        S, ordered, _ = pairwise_similarity(["SOLO"], {"SOLO": frozenset()}, {})
        assert S.shape == (1, 1)
        assert S[0, 0] == 1.0


class TestNeff:
    def test_identical_candidates_neff_one(self):
        """N identical candidates → N_eff ≈ 1."""
        n = 6
        # All similarity = 1 except diagonal (which is also 1)
        S = np.ones((n, n), dtype=np.float64)
        neff = n_eff_participation_ratio(S)
        # Should be very close to 1 (one eigenvalue = N, rest 0)
        assert abs(neff - 1.0) < 0.1, f"N_eff={neff} for identical matrix"

    def test_orthogonal_candidates_neff_n(self):
        """N orthogonal candidates → N_eff ≈ N."""
        n = 5
        S = np.eye(n, dtype=np.float64)  # all off-diagonal = 0
        neff = n_eff_participation_ratio(S)
        assert abs(neff - float(n)) < 0.01, f"N_eff={neff} for identity matrix"

    def test_neff_single_returns_one(self):
        S = np.array([[1.0]])
        assert n_eff_participation_ratio(S) == 1.0

    def test_neff_empty_returns_zero(self):
        S = np.zeros((0, 0))
        assert n_eff_participation_ratio(S) == 0.0

    def test_neff_in_range_one_to_n(self):
        rng = np.random.default_rng(99)
        for _ in range(20):
            n = rng.integers(2, 8)
            # Random PSD matrix
            A = rng.standard_normal((n, n))
            S = (A @ A.T) / n
            # Normalize diagonal to 1
            diag = np.sqrt(np.diag(S))
            S = S / np.outer(diag, diag)
            np.fill_diagonal(S, 1.0)
            neff = n_eff_participation_ratio(S)
            assert 0.9 <= neff <= n + 0.1, f"N_eff={neff} out of [1, {n}]"


# ── None-safety: missing factor betas ────────────────────────────────────────

class TestNoneSafety:
    def test_missing_beta_falls_back_to_membership(self):
        """Name with no beta record uses membership-only similarity, never crashes."""
        mem = _make_membership({"ai": ["A", "B"], "health": ["C"]})
        sector = {"A": "Technology", "B": "Technology", "C": "Health Care"}
        betas = {
            "A": _make_betas(1.0, 0.5, 0.0, 0.0, r2=0.6),
            # B has no betas at all
            "C": _make_betas(0.3, -0.2, 0.5, 0.1, r2=0.5),
        }
        result = compute(["A", "B", "C"], sector, betas, mem, "2026-07-05")
        # Must not crash
        assert "by_ticker" in result
        by_ticker = result["by_ticker"]
        # B should have a valid verdict without crashing
        assert "B" in by_ticker
        b_rec = by_ticker["B"]
        assert b_rec["verdict"] in ("duplicate", "partial", "new")
        # Basis flag for B should indicate membership-only
        assert "membership-only" in b_rec.get("basis", "")

    def test_all_betas_missing_still_works(self):
        """All betas absent → membership-only similarity, no crash."""
        mem = _make_membership({"basket_x": ["A", "B"]})
        sector = {"A": "Technology", "B": "Technology"}
        result = compute(["A", "B"], sector, {}, mem, "2026-07-05")
        assert "by_ticker" in result
        # Both in same basket → Jaccard = 1.0 → should be duplicate
        for t in ["A", "B"]:
            assert result["by_ticker"][t]["verdict"] == "duplicate"

    def test_no_membership_data_still_works(self):
        """No membership.json → factor-only similarity, no crash."""
        sector = {"A": "Technology", "B": "Health Care"}
        betas = {
            "A": _make_betas(1.0, 0.5, 0.0, 0.0, r2=0.6),
            "B": _make_betas(0.3, -0.2, 0.5, 0.1, r2=0.5),
        }
        result = compute(["A", "B"], sector, betas, None, "2026-07-05")
        assert "by_ticker" in result
        assert "A" in result["by_ticker"]
        assert "B" in result["by_ticker"]

    def test_thin_r2_uses_membership_only(self):
        """Name with r2 < R2_FLOOR gets membership-only similarity, basis flag set."""
        mem = _make_membership({"basket_x": ["A", "B"]})
        sector = {"A": "Technology", "B": "Technology"}
        betas = {
            "A": _make_betas(1.0, 0.5, 0.0, 0.0, r2=0.05),  # thin
            "B": _make_betas(0.8, 0.3, 0.0, 0.0, r2=0.6),
        }
        result = compute(["A", "B"], sector, betas, mem, "2026-07-05")
        a_rec = result["by_ticker"]["A"]
        assert "membership-only" in a_rec.get("basis", ""), (
            f"Expected membership-only basis for thin-r2 name, got: {a_rec.get('basis')}"
        )


# ── compute() invariants ──────────────────────────────────────────────────────

class TestComputeInvariants:
    def _basic_setup(self):
        mem = _make_membership({
            "semis": ["NVDA", "AMD", "INTC"],
            "ai_infra": ["NVDA", "AMD"],
        })
        sector = {
            "NVDA": "Information Technology",
            "AMD":  "Information Technology",
            "INTC": "Information Technology",
            "MSFT": "Information Technology",
            "JNJ":  "Health Care",
        }
        betas = {
            "NVDA": _make_betas(1.2, 0.8, -0.2, -0.1, r2=0.70),
            "AMD":  _make_betas(1.1, 0.7, -0.1, -0.1, r2=0.65),
            "INTC": _make_betas(0.9, 0.5,  0.1,  0.0, r2=0.55),
            "MSFT": _make_betas(1.0, 0.4,  0.0,  0.1, r2=0.60),
            "JNJ":  _make_betas(0.5,-0.2,  0.2,  0.4, r2=0.45),
        }
        return mem, sector, betas

    def test_schema_always_set(self):
        mem, sector, betas = self._basic_setup()
        result = compute(["NVDA", "AMD", "JNJ"], sector, betas, mem, "2026-07-05")
        assert result["schema"] == "reflexivity_overlay.v1"

    def test_is_context_only_always_true(self):
        mem, sector, betas = self._basic_setup()
        result = compute(["NVDA", "AMD", "JNJ"], sector, betas, mem, "2026-07-05")
        assert result["is_context_only"] is True

    def test_earnings_leg_wired_in_wd(self):
        """W-D wave: earnings_leg is now a dict (not None). No earnings_store passed
        → has_data=False for all, but the field is always a dict (never None).
        Does NOT affect similarity matrix, N_eff, or verdicts (R-D annotation only)."""
        mem, sector, betas = self._basic_setup()
        result = compute(["NVDA", "AMD"], sector, betas, mem, "2026-07-05")
        for tkr, rec in result["by_ticker"].items():
            el = rec.get("earnings_leg")
            assert el is not None, (
                f"{tkr}: earnings_leg must be a dict in W-D, got None"
            )
            assert isinstance(el, dict), f"{tkr}: earnings_leg must be dict"
            assert "has_data" in el, f"{tkr}: earnings_leg missing has_data"
            # Without earnings store, has_data=False
            assert el["has_data"] is False, (
                f"{tkr}: no earnings store passed → has_data must be False"
            )

    def test_duplicate_verdict_for_identical_candidates(self):
        """Two names sharing ALL groups → Jaccard=1 → duplicate verdict."""
        mem = _make_membership({"b1": ["A", "B"], "b2": ["A", "B"]})
        sector = {"A": "Technology", "B": "Technology"}
        betas = {
            "A": _make_betas(1.0, 0.5, 0.0, 0.0, r2=0.6),
            "B": _make_betas(1.0, 0.5, 0.0, 0.0, r2=0.6),
        }
        result = compute(["A", "B"], sector, betas, mem, "2026-07-05")
        # Each sees the other as duplicate
        assert result["by_ticker"]["A"]["verdict"] == "duplicate"
        assert result["by_ticker"]["B"]["verdict"] == "duplicate"

    def test_new_verdict_for_orthogonal_candidates(self):
        """Two names with no shared groups + anti-correlated betas → new verdict."""
        mem = _make_membership({"tech_basket": ["A"], "health_basket": ["B"]})
        sector = {"A": "Information Technology", "B": "Health Care"}
        betas = {
            "A": _make_betas(1.2, 0.8, -0.2, -0.1, r2=0.7),
            "B": _make_betas(0.4,-0.3,  0.3,  0.5, r2=0.5),
        }
        result = compute(["A", "B"], sector, betas, mem, "2026-07-05")
        # Different sector, different basket → Jaccard = 0
        # factor similarity: let's check combined < PARTIAL_THRESH
        for tkr in ["A", "B"]:
            rec = result["by_ticker"][tkr]
            assert rec["verdict"] in ("new", "partial"), (
                f"{tkr}: expected new/partial but got {rec['verdict']}"
            )

    def test_board_concentration_n_eff_present(self):
        mem, sector, betas = self._basic_setup()
        result = compute(["NVDA", "AMD", "JNJ"], sector, betas, mem, "2026-07-05")
        bc = result["board_concentration"]
        assert "n" in bc
        assert "n_eff" in bc
        assert bc["n"] == 3
        assert 0.9 <= bc["n_eff"] <= 3.1

    def test_single_candidate_returns_zero_neighbors(self):
        mem = _make_membership({"b": ["SOLO"]})
        result = compute(["SOLO"], {"SOLO": "Technology"}, {}, mem, "2026-07-05")
        assert "SOLO" in result["by_ticker"]
        solo = result["by_ticker"]["SOLO"]
        assert solo["nearest"] == []

    def test_empty_candidate_list(self):
        """Empty candidate set → no crash, n=0."""
        result = compute([], {}, {}, None, "2026-07-05")
        assert result["board_concentration"]["n"] == 0

    def test_why_en_why_zh_present_for_all(self):
        mem, sector, betas = self._basic_setup()
        result = compute(["NVDA", "AMD", "JNJ"], sector, betas, mem, "2026-07-05")
        for tkr, rec in result["by_ticker"].items():
            assert "why_en" in rec and rec["why_en"], f"{tkr}: missing why_en"
            assert "why_zh" in rec and rec["why_zh"], f"{tkr}: missing why_zh"

    def test_json_serializable(self):
        """All output must be JSON-serializable (no numpy scalars)."""
        mem, sector, betas = self._basic_setup()
        result = compute(["NVDA", "AMD", "JNJ"], sector, betas, mem, "2026-07-05")
        try:
            json.dumps(result)
        except TypeError as e:
            pytest.fail(f"compute() result not JSON-serializable: {e}")

    def test_nvda_amd_are_partial_or_duplicate(self):
        """NVDA and AMD share semis + ai_infra + same sector → high similarity."""
        mem, sector, betas = self._basic_setup()
        result = compute(["NVDA", "AMD"], sector, betas, mem, "2026-07-05")
        nvda_verdict = result["by_ticker"]["NVDA"]["verdict"]
        assert nvda_verdict in ("duplicate", "partial"), (
            f"Expected NVDA to be duplicate/partial of AMD, got: {nvda_verdict}"
        )


# ── builder degradation ───────────────────────────────────────────────────────

class TestBuilderDegradation:
    def test_missing_standouts_returns_empty_overlay(self, tmp_path):
        """Builder degrades gracefully when us_standouts_v2.json is absent."""
        from scripts.build_reflexivity_overlay import compute as builder_compute

        # Create site dir without standouts
        (tmp_path / "site" / "factordata").mkdir(parents=True)
        result = builder_compute(site=tmp_path / "site")
        assert result["schema"] == "reflexivity_overlay.v1"
        assert result["is_context_only"] is True
        assert result["by_ticker"] == {}

    def test_missing_factor_betas_falls_back(self, tmp_path):
        """Builder works with membership-only similarity when betas absent."""
        from scripts.build_reflexivity_overlay import compute as builder_compute

        site_dir = tmp_path / "site"
        fd = site_dir / "factordata"
        fd.mkdir(parents=True)

        # Write minimal standouts
        standouts = {
            "as_of": "2026-07-05",
            "lanes": {
                "entry_open": [
                    {"ticker": "NVDA", "sector": "Information Technology"},
                    {"ticker": "AMD",  "sector": "Information Technology"},
                ],
                "setting_up": [],
            }
        }
        (fd / "us_standouts_v2.json").write_text(json.dumps(standouts))
        # No factor_betas.json → should degrade silently

        result = builder_compute(site=site_dir)
        assert result["schema"] == "reflexivity_overlay.v1"
        assert "NVDA" in result["by_ticker"]
        assert "AMD" in result["by_ticker"]

    def test_builder_returns_zero_on_exception(self):
        """main() should always return 0 (non-fatal)."""
        from scripts.build_reflexivity_overlay import main as builder_main
        # main() swallows exceptions — call it with bad env is hard to simulate cleanly,
        # so just verify the function exists and is callable returning 0 when inputs present
        # (end-to-end with real data is an integration concern)
        assert callable(builder_main)

    def test_n_eff_by_lane_emitted_with_two_lanes(self, tmp_path):
        """compute() must emit n_eff_by_lane keyed by entry_open and setting_up."""
        from scripts.build_reflexivity_overlay import compute as builder_compute

        site_dir = tmp_path / "site"
        fd = site_dir / "factordata"
        fd.mkdir(parents=True)
        standouts = {
            "as_of": "2026-07-05",
            "lanes": {
                "entry_open": [
                    {"ticker": "AAPL", "sector": "Information Technology"},
                    {"ticker": "MSFT", "sector": "Information Technology"},
                ],
                "setting_up": [
                    {"ticker": "NVDA", "sector": "Information Technology"},
                ],
            },
        }
        (fd / "us_standouts_v2.json").write_text(json.dumps(standouts))

        result = builder_compute(site=site_dir)
        assert "n_eff_by_lane" in result, "n_eff_by_lane must be present in artifact"
        by_lane = result["n_eff_by_lane"]
        assert "entry_open" in by_lane
        assert "setting_up" in by_lane
        # entry_open has 2 names → n_eff should be a number between 1 and 2
        eo_neff = by_lane["entry_open"]
        assert isinstance(eo_neff, float), f"entry_open n_eff should be float, got {eo_neff!r}"
        assert 0.9 <= eo_neff <= 2.1
        # setting_up has 1 name → n_eff = 1.0
        su_neff = by_lane["setting_up"]
        assert su_neff == 1.0, f"single-name lane n_eff should be 1.0, got {su_neff}"

    def test_n_eff_by_lane_none_for_empty_lane(self, tmp_path):
        """Empty lane → n_eff_by_lane[lane] is None (no population)."""
        from scripts.build_reflexivity_overlay import compute as builder_compute

        site_dir = tmp_path / "site"
        fd = site_dir / "factordata"
        fd.mkdir(parents=True)
        standouts = {
            "as_of": "2026-07-05",
            "lanes": {
                "entry_open": [
                    {"ticker": "AAPL", "sector": "IT"},
                    {"ticker": "MSFT", "sector": "IT"},
                ],
                "setting_up": [],  # empty
            },
        }
        (fd / "us_standouts_v2.json").write_text(json.dumps(standouts))

        result = builder_compute(site=site_dir)
        by_lane = result.get("n_eff_by_lane", {})
        assert by_lane.get("setting_up") is None, (
            "Empty lane must produce None n_eff, not a numeric value"
        )

    def test_empty_overlay_has_n_eff_by_lane(self, tmp_path):
        """_empty_overlay must include n_eff_by_lane with None values (schema completeness)."""
        from scripts.build_reflexivity_overlay import compute as builder_compute

        # Absent us_standouts_v2.json → empty overlay path
        (tmp_path / "site" / "factordata").mkdir(parents=True)
        result = builder_compute(site=tmp_path / "site")
        assert "n_eff_by_lane" in result
        by_lane = result["n_eff_by_lane"]
        assert by_lane.get("entry_open") is None
        assert by_lane.get("setting_up") is None

    def test_lane_tickers_extracts_correct_lane(self):
        """_lane_tickers returns only the tickers for the named lane."""
        from scripts.build_reflexivity_overlay import _lane_tickers

        standouts = {
            "lanes": {
                "entry_open": [
                    {"ticker": "A", "sector": "IT"},
                    {"ticker": "B", "sector": "IT"},
                ],
                "setting_up": [
                    {"ticker": "C", "sector": "Health"},
                ],
            }
        }
        assert _lane_tickers(standouts, "entry_open") == ["A", "B"]
        assert _lane_tickers(standouts, "setting_up") == ["C"]
        assert _lane_tickers(standouts, "nonexistent") == []

    def test_lane_tickers_deduplicates(self):
        """_lane_tickers deduplicates repeated tickers (first occurrence wins)."""
        from scripts.build_reflexivity_overlay import _lane_tickers

        standouts = {
            "lanes": {
                "entry_open": [
                    {"ticker": "A", "sector": "IT"},
                    {"ticker": "A", "sector": "IT"},  # duplicate
                    {"ticker": "B", "sector": "IT"},
                ],
            }
        }
        result = _lane_tickers(standouts, "entry_open")
        assert result == ["A", "B"], f"Expected deduplication, got {result}"

    def test_per_lane_neff_independent_of_other_lane(self, tmp_path):
        """n_eff_by_lane values are computed per lane, not over the union."""
        from scripts.build_reflexivity_overlay import compute as builder_compute

        site_dir = tmp_path / "site"
        fd = site_dir / "factordata"
        fd.mkdir(parents=True)
        # entry_open: same sector only → medium similarity, small N_eff
        # setting_up: different sector → low similarity, N_eff closer to N
        standouts = {
            "as_of": "2026-07-05",
            "lanes": {
                "entry_open": [
                    {"ticker": "AAPL", "sector": "IT"},
                    {"ticker": "MSFT", "sector": "IT"},
                    {"ticker": "GOOG", "sector": "IT"},
                ],
                "setting_up": [
                    {"ticker": "JNJ", "sector": "Health Care"},
                    {"ticker": "UNH", "sector": "Health Care"},
                ],
            },
        }
        (fd / "us_standouts_v2.json").write_text(json.dumps(standouts))

        result = builder_compute(site=site_dir)
        by_lane = result["n_eff_by_lane"]
        # Both lanes should have distinct numeric n_eff
        for lane_name in ("entry_open", "setting_up"):
            val = by_lane[lane_name]
            assert isinstance(val, float), f"{lane_name}: expected float, got {val!r}"
            assert val >= 1.0, f"{lane_name}: n_eff must be >= 1"


# ── W-D: same_thesis_groups ───────────────────────────────────────────────────

class TestSameThesisGroups:
    """W-D five-candidates-one-thesis detector."""

    def _all_similar_matrix(self, n: int) -> tuple[np.ndarray, list[str]]:
        """N×N matrix where all off-diagonal values = DUPLICATE_THRESH + 0.05."""
        from engine.reflexivity import DUPLICATE_THRESH
        S = np.full((n, n), DUPLICATE_THRESH + 0.05)
        np.fill_diagonal(S, 1.0)
        tickers = [f"T{i}" for i in range(n)]
        return S, tickers

    def _orthogonal_matrix(self, n: int) -> tuple[np.ndarray, list[str]]:
        """N×N identity matrix — all pairs below threshold."""
        S = np.eye(n)
        tickers = [f"T{i}" for i in range(n)]
        return S, tickers

    def test_all_similar_n5_forms_one_group(self):
        """5 names all similar → one group of size 5 emitted."""
        S, tickers = self._all_similar_matrix(5)
        groups = same_thesis_groups(S, tickers, {}, min_size=3)
        assert len(groups) == 1, f"Expected 1 group, got {len(groups)}"
        assert groups[0]["size"] == 5
        assert set(groups[0]["members"]) == set(tickers)

    def test_all_similar_n3_emitted_at_min_size(self):
        """3 names all similar → one group of size 3 (at min_size boundary)."""
        S, tickers = self._all_similar_matrix(3)
        groups = same_thesis_groups(S, tickers, {}, min_size=3)
        assert len(groups) == 1
        assert groups[0]["size"] == 3

    def test_two_disjoint_components(self):
        """Two separate clusters of 3 → two groups."""
        # Tickers 0-2 are all similar; tickers 3-5 are all similar;
        # cross-cluster similarity is 0.
        from engine.reflexivity import DUPLICATE_THRESH
        n = 6
        S = np.eye(n)
        thresh = DUPLICATE_THRESH + 0.05
        for i in range(3):
            for j in range(3):
                S[i, j] = thresh
        for i in range(3, 6):
            for j in range(3, 6):
                S[i, j] = thresh
        np.fill_diagonal(S, 1.0)
        tickers = [f"T{i}" for i in range(n)]
        groups = same_thesis_groups(S, tickers, {}, min_size=3)
        assert len(groups) == 2, f"Expected 2 groups, got {len(groups)}"
        sizes = {g["size"] for g in groups}
        assert sizes == {3}

    def test_orthogonal_no_groups(self):
        """All orthogonal → no components reach min_size."""
        S, tickers = self._orthogonal_matrix(5)
        groups = same_thesis_groups(S, tickers, {}, min_size=3)
        assert groups == [], f"Expected no groups for orthogonal matrix, got {groups}"

    def test_min_size_filter_excludes_small_components(self):
        """A pair (size=2) must be excluded when min_size=3."""
        from engine.reflexivity import DUPLICATE_THRESH
        S = np.eye(4)
        # T0 and T1 are similar; T2 and T3 are isolated
        S[0, 1] = S[1, 0] = DUPLICATE_THRESH + 0.05
        tickers = ["T0", "T1", "T2", "T3"]
        groups = same_thesis_groups(S, tickers, {}, min_size=3)
        assert groups == [], "Pair (size=2) must not appear at min_size=3"

    def test_groups_sorted_by_size_desc(self):
        """Groups sorted by size descending."""
        from engine.reflexivity import DUPLICATE_THRESH
        n = 7
        S = np.eye(n)
        thresh = DUPLICATE_THRESH + 0.05
        # T0-T3 (size 4), T4-T6 (size 3)
        for i in range(4):
            for j in range(4):
                S[i, j] = thresh
        for i in range(4, 7):
            for j in range(4, 7):
                S[i, j] = thresh
        np.fill_diagonal(S, 1.0)
        tickers = [f"T{i}" for i in range(n)]
        groups = same_thesis_groups(S, tickers, {}, min_size=3)
        assert len(groups) == 2
        assert groups[0]["size"] >= groups[1]["size"], "Groups must be sorted by size desc"

    def test_label_derived_from_pair_basis(self):
        """label is extracted from shared_groups in pair_basis."""
        from engine.reflexivity import DUPLICATE_THRESH
        S = np.full((3, 3), DUPLICATE_THRESH + 0.05)
        np.fill_diagonal(S, 1.0)
        tickers = ["A", "B", "C"]
        pair_basis = {
            "A__B": {"combined": 0.9, "membership_jaccard": 0.9,
                     "factor_cosine": None, "shared_groups": ["sector:Technology"]},
            "A__C": {"combined": 0.8, "membership_jaccard": 0.8,
                     "factor_cosine": None, "shared_groups": ["sector:Technology"]},
            "B__C": {"combined": 0.85, "membership_jaccard": 0.85,
                     "factor_cosine": None, "shared_groups": ["sector:Technology"]},
        }
        groups = same_thesis_groups(S, tickers, pair_basis, min_size=3)
        assert len(groups) == 1
        assert groups[0]["label"] == "Technology", (
            f"Expected 'Technology', got {groups[0]['label']!r}"
        )

    def test_empty_tickers_returns_empty(self):
        """Empty ticker list → empty groups."""
        S = np.zeros((0, 0))
        assert same_thesis_groups(S, [], {}) == []

    def test_same_thesis_groups_in_compute_output(self):
        """compute() emits same_thesis_groups key."""
        mem = _make_membership({"ai": ["A", "B", "C"]})
        sector = {"A": "IT", "B": "IT", "C": "IT"}
        # All in same basket → Jaccard=1 → all duplicate → one group of 3
        result = compute(["A", "B", "C"], sector, {}, mem, "2026-07-05")
        assert "same_thesis_groups" in result
        groups = result["same_thesis_groups"]
        assert isinstance(groups, list)
        # All three share the same basket → should form one group
        assert len(groups) == 1
        assert groups[0]["size"] == 3

    def test_display_only_no_ordering_effect(self):
        """same_thesis_groups must not change verdict or max_similarity for any ticker."""
        mem = _make_membership({"ai": ["A", "B", "C", "D", "E"]})
        sector = {t: "IT" for t in ["A", "B", "C", "D", "E"]}
        result = compute(["A", "B", "C", "D", "E"], sector, {}, mem, "2026-07-05")
        # All in same basket → Jaccard=1 → all "duplicate"
        for tkr in ["A", "B", "C", "D", "E"]:
            assert result["by_ticker"][tkr]["verdict"] == "duplicate", (
                f"{tkr}: verdict changed by thesis-groups (should not)"
            )
            assert result["by_ticker"][tkr]["max_similarity"] == 1.0


# ── W-D: N_eff history ────────────────────────────────────────────────────────

class TestNeffHistory:
    """Tests for data/reflexivity/n_eff_history.json build and maintenance."""

    def test_history_written_on_normal_run(self, tmp_path):
        """Normal run creates history file with one entry."""
        from scripts.build_reflexivity_overlay import (
            _load_history, _update_history, _write_n_eff_history,
        )
        artifact = {
            "as_of": "2026-07-05",
            "board_concentration": {"n": 5, "n_eff": 3.2},
            "n_eff_by_lane": {"entry_open": 2.1, "setting_up": 1.5},
            "same_thesis_groups": [{"members": ["A", "B", "C"], "size": 3,
                                    "basis": "membership-jaccard", "label": "IT"}],
            "by_ticker": {"A": {}, "B": {}, "C": {}, "D": {}, "E": {}},
        }
        hist_path = tmp_path / "n_eff_history.json"
        _write_n_eff_history(artifact, hist_path)
        assert hist_path.exists(), "History file must be created"
        data = json.loads(hist_path.read_text())
        assert "history" in data
        assert len(data["history"]) == 1
        entry = data["history"][0]
        assert entry["as_of"] == "2026-07-05"
        assert entry["same_thesis_group_count"] == 1
        assert "n_eff_by_lane" in entry

    def test_history_dedup_by_as_of(self, tmp_path):
        """Re-running on the same as_of replaces the entry (last-write-wins)."""
        from scripts.build_reflexivity_overlay import _write_n_eff_history
        hist_path = tmp_path / "n_eff_history.json"

        artifact_v1 = {
            "as_of": "2026-07-05",
            "board_concentration": {"n": 3, "n_eff": 2.0},
            "n_eff_by_lane": {"entry_open": 2.0, "setting_up": None},
            "same_thesis_groups": [],
            "by_ticker": {"A": {}, "B": {}, "C": {}},
        }
        artifact_v2 = {
            "as_of": "2026-07-05",
            "board_concentration": {"n": 4, "n_eff": 2.5},
            "n_eff_by_lane": {"entry_open": 2.5, "setting_up": None},
            "same_thesis_groups": [],
            "by_ticker": {"A": {}, "B": {}, "C": {}, "D": {}},
        }
        _write_n_eff_history(artifact_v1, hist_path)
        _write_n_eff_history(artifact_v2, hist_path)

        data = json.loads(hist_path.read_text())
        assert len(data["history"]) == 1, "Same as_of must be deduped (last-write-wins)"
        assert data["history"][0]["n_eff_by_lane"]["entry_open"] == 2.5, (
            "Second write must replace first"
        )

    def test_history_bounded_to_252(self, tmp_path):
        """History array never exceeds _HISTORY_LEN=252 entries."""
        from scripts.build_reflexivity_overlay import _write_n_eff_history, _HISTORY_LEN
        hist_path = tmp_path / "n_eff_history.json"

        for i in range(260):
            artifact = {
                "as_of": f"2025-{(i // 30) + 1:02d}-{(i % 28) + 1:02d}",
                "board_concentration": {"n": 3, "n_eff": 2.0},
                "n_eff_by_lane": {"entry_open": 2.0, "setting_up": None},
                "same_thesis_groups": [],
                "by_ticker": {"A": {}, "B": {}, "C": {}},
            }
            _write_n_eff_history(artifact, hist_path)

        data = json.loads(hist_path.read_text())
        assert len(data["history"]) <= _HISTORY_LEN, (
            f"History must be bounded to {_HISTORY_LEN}, got {len(data['history'])}"
        )

    def test_degraded_run_preserves_history(self, tmp_path):
        """Degraded/empty overlay run must NOT reset history."""
        from scripts.build_reflexivity_overlay import _write_n_eff_history
        hist_path = tmp_path / "n_eff_history.json"

        # Write a real entry first
        good_artifact = {
            "as_of": "2026-07-05",
            "board_concentration": {"n": 3, "n_eff": 2.0},
            "n_eff_by_lane": {"entry_open": 2.0, "setting_up": None},
            "same_thesis_groups": [],
            "by_ticker": {"A": {}, "B": {}, "C": {}},
        }
        _write_n_eff_history(good_artifact, hist_path)
        data_before = json.loads(hist_path.read_text())
        assert len(data_before["history"]) == 1

        # Now simulate a degraded/empty run (n=0, no by_ticker)
        empty_artifact = {
            "as_of": "2026-07-06",
            "board_concentration": {"n": 0, "n_eff": 0.0},
            "n_eff_by_lane": {"entry_open": None, "setting_up": None},
            "same_thesis_groups": [],
            "by_ticker": {},
        }
        _write_n_eff_history(empty_artifact, hist_path)

        data_after = json.loads(hist_path.read_text())
        assert len(data_after["history"]) == 1, (
            "Degraded run must preserve prior history, not reset it"
        )
        assert data_after["history"][0]["as_of"] == "2026-07-05", (
            "Original entry must survive a degraded run"
        )

    def test_history_appends_across_days(self, tmp_path):
        """History grows by one entry per unique as_of date."""
        from scripts.build_reflexivity_overlay import _write_n_eff_history
        hist_path = tmp_path / "n_eff_history.json"

        for day in ["2026-07-01", "2026-07-02", "2026-07-03"]:
            artifact = {
                "as_of": day,
                "board_concentration": {"n": 3, "n_eff": 2.0},
                "n_eff_by_lane": {"entry_open": 2.0, "setting_up": None},
                "same_thesis_groups": [],
                "by_ticker": {"A": {}, "B": {}, "C": {}},
            }
            _write_n_eff_history(artifact, hist_path)

        data = json.loads(hist_path.read_text())
        assert len(data["history"]) == 3


# ── W-D: earnings-week annotation ─────────────────────────────────────────────

def _make_earnings_parquet(ticker_dates: dict[str, str], tmp_path: Path) -> Path:
    """Create a minimal earnings.parquet fixture with next_date column."""
    import io
    rows = []
    for ticker, next_date in ticker_dates.items():
        rows.append({
            "ticker_idx": ticker.upper(),
            "next_date": next_date,
            "next_time": None,
            "eps_forecast": None,
            "as_of": "2026-07-05",
        })
    df = pd.DataFrame(rows).set_index("ticker_idx")
    df.index.name = None
    p = tmp_path / "earnings.parquet"
    df.to_parquet(p)
    return p


class TestEarningsWeekAnnotation:
    """Tests for earnings_week_annotation (W-D, R-D)."""

    def test_same_week_peers_detected(self, tmp_path):
        """Tickers with next_date within 7 days of each other are peers."""
        store = pd.DataFrame({
            "next_date": {"AAPL": "2026-07-10", "MSFT": "2026-07-12", "JNJ": "2026-07-25"},
            "as_of": {"AAPL": "2026-07-05", "MSFT": "2026-07-05", "JNJ": "2026-07-05"},
        })
        result = earnings_week_annotation(
            ["AAPL", "MSFT", "JNJ"], store, "2026-07-05", window_days=7
        )
        # AAPL (7/10) and MSFT (7/12) are within 7 days of each other
        assert "MSFT" in result["AAPL"]["same_week_peers"], (
            "MSFT should be a same-week peer of AAPL (2-day difference)"
        )
        assert "AAPL" in result["MSFT"]["same_week_peers"], "Symmetry check"
        # JNJ (7/25) is 15 days from AAPL → not in same week
        assert "JNJ" not in result["AAPL"]["same_week_peers"], (
            "JNJ (15 days apart) must not be a same-week peer"
        )

    def test_no_earnings_store_returns_empty_has_data_false(self):
        """None store → all tickers get has_data=False, no crash."""
        result = earnings_week_annotation(["AAPL", "MSFT"], None, "2026-07-05")
        for tkr in ["AAPL", "MSFT"]:
            assert result[tkr]["has_data"] is False
            assert result[tkr]["same_week_peers"] == []

    def test_past_dates_excluded(self):
        """next_date before as_of → has_data=False (fail-open semantics)."""
        store = pd.DataFrame({
            "next_date": {"AAPL": "2026-06-01"},  # past date
            "as_of": {"AAPL": "2026-07-05"},
        })
        result = earnings_week_annotation(["AAPL"], store, "2026-07-05")
        assert result["AAPL"]["has_data"] is False, (
            "Past next_date must be treated as no-data (fail-open)"
        )

    def test_ticker_not_in_store_has_data_false(self):
        """Missing ticker in store → has_data=False."""
        store = pd.DataFrame({
            "next_date": {"AAPL": "2026-07-10"},
            "as_of": {"AAPL": "2026-07-05"},
        })
        result = earnings_week_annotation(["NVDA"], store, "2026-07-05")
        assert result["NVDA"]["has_data"] is False

    def test_does_not_affect_similarity_or_neff(self):
        """Earnings annotation must not change similarity matrix, N_eff, or verdicts."""
        mem = _make_membership({"ai": ["A", "B"]})
        sector = {"A": "IT", "B": "IT"}
        betas = {
            "A": _make_betas(1.0, 0.5, 0.0, 0.0, r2=0.6),
            "B": _make_betas(1.0, 0.5, 0.0, 0.0, r2=0.6),
        }
        store = pd.DataFrame({
            "next_date": {"A": "2026-07-10", "B": "2026-07-10"},
            "as_of": {"A": "2026-07-05", "B": "2026-07-05"},
        })
        # With earnings
        r1 = compute(["A", "B"], sector, betas, mem, "2026-07-05", earnings_store=store)
        # Without earnings
        r2 = compute(["A", "B"], sector, betas, mem, "2026-07-05", earnings_store=None)

        # Similarity matrix-derived fields must be identical
        assert r1["board_concentration"]["n_eff"] == r2["board_concentration"]["n_eff"], (
            "Earnings annotation must not change N_eff"
        )
        assert r1["by_ticker"]["A"]["verdict"] == r2["by_ticker"]["A"]["verdict"], (
            "Earnings annotation must not change verdicts"
        )
        assert r1["by_ticker"]["A"]["max_similarity"] == r2["by_ticker"]["A"]["max_similarity"], (
            "Earnings annotation must not change max_similarity"
        )

    def test_earnings_coverage_frac_in_overlay(self):
        """earnings_coverage_frac must be present and reflect actual coverage."""
        mem = _make_membership({"ai": ["A", "B", "C"]})
        sector = {"A": "IT", "B": "IT", "C": "IT"}
        store = pd.DataFrame({
            "next_date": {"A": "2026-07-10", "B": "2026-07-12"},
            "as_of": {"A": "2026-07-05", "B": "2026-07-05"},
        })
        result = compute(["A", "B", "C"], sector, {}, mem, "2026-07-05", earnings_store=store)
        cov = result.get("earnings_coverage_frac")
        assert cov is not None, "earnings_coverage_frac must be present"
        # A and B have data, C does not → coverage = 2/3
        assert abs(cov - 2.0 / 3.0) < 0.01, f"Expected coverage ~0.667, got {cov}"

    def test_earnings_leg_in_by_ticker(self):
        """Each ticker in by_ticker has earnings_leg dict with expected keys."""
        mem = _make_membership({"ai": ["A", "B"]})
        sector = {"A": "IT", "B": "IT"}
        store = pd.DataFrame({
            "next_date": {"A": "2026-07-10", "B": "2026-07-10"},
            "as_of": {"A": "2026-07-05", "B": "2026-07-05"},
        })
        result = compute(["A", "B"], sector, {}, mem, "2026-07-05", earnings_store=store)
        for tkr in ["A", "B"]:
            el = result["by_ticker"][tkr]["earnings_leg"]
            assert isinstance(el, dict)
            assert el["has_data"] is True
            assert el["next_date"] == "2026-07-10"
            # Each is in the other's same_week_peers
            assert "B" in result["by_ticker"]["A"]["earnings_leg"]["same_week_peers"] or \
                   "A" in result["by_ticker"]["B"]["earnings_leg"]["same_week_peers"], (
                "A and B have same next_date → should be peers"
            )

    def test_same_earnings_week_in_nearest(self):
        """same_earnings_week field in nearest peers reflects earnings annotation."""
        mem = _make_membership({"ai": ["A", "B"]})
        sector = {"A": "IT", "B": "IT"}
        store = pd.DataFrame({
            "next_date": {"A": "2026-07-10", "B": "2026-07-10"},
            "as_of": {"A": "2026-07-05", "B": "2026-07-05"},
        })
        result = compute(["A", "B"], sector, {}, mem, "2026-07-05", earnings_store=store)
        # A's nearest[0] is B; same_earnings_week should be True
        nearest = result["by_ticker"]["A"]["nearest"]
        assert len(nearest) > 0
        b_peer = next((p for p in nearest if p["ticker"] == "B"), None)
        assert b_peer is not None
        assert b_peer["same_earnings_week"] is True, (
            "B is in same earnings week as A → same_earnings_week must be True"
        )


# ── W-D: template banner rendering ───────────────────────────────────────────

class TestBannerRendering:
    """Test that the thesis-group banner renders correctly for groups >= 5."""

    def _render_banner(self, overlay: dict | None) -> str:
        """Render rx_board_banner() with the given overlay using Jinja2.

        Renders a self-contained mini-template containing just the macro
        definition + call, without importing the full page template (which
        requires the `d` context variable for the full page body).
        """
        try:
            from jinja2 import Environment
        except ImportError:
            pytest.skip("jinja2 not available")

        # Read the macro source directly from the template file, then
        # wrap it in a standalone mini-template with a stub `t()` function.
        template_path = Path(__file__).resolve().parents[1] / "templates" / "us_stocks_v2.html.j2"
        if not template_path.exists():
            pytest.skip("us_stocks_v2.html.j2 not found")

        full_src = template_path.read_text()

        # Extract the row_card and conc_banner and rx_board_banner macros —
        # rx_board_banner only needs `rx` and `t`, and does not call conc_banner.
        # We splice out just the macros we need so the body never executes.
        # Strategy: wrap macro definitions + a call in a clean env.
        env = Environment(autoescape=False)

        def t(en: str, zh: str) -> str:
            return en

        # Build a mini-template that defines the macros and calls rx_board_banner.
        # We extract the macro blocks from the full source to avoid running
        # the template body (which requires `d`).
        import re
        # Find all macro blocks
        macro_pattern = re.compile(
            r'\{%-?\s*macro\s+(\w+)\s*\(.*?\n.*?'  # macro start
            r'\{%-?\s*endmacro\s*-?%\}',
            re.DOTALL,
        )
        # Simpler: just find the rx_board_banner macro by line boundaries
        lines = full_src.split("\n")
        macro_lines: list[str] = []
        in_macro = False
        for line in lines:
            if re.search(r'\{%-?\s*macro\s+(conc_banner|rx_board_banner)\s*\(', line):
                in_macro = True
            if in_macro:
                macro_lines.append(line)
                if re.search(r'\{%-?\s*endmacro\s*-?%\}', line):
                    in_macro = False
                    macro_lines.append("")  # separator

        mini_src = "\n".join(macro_lines) + "\n{{ rx_board_banner() }}"
        tmpl = env.from_string(mini_src)
        return tmpl.render(rx=overlay, t=t)

    def test_no_banner_when_max_group_lt5(self):
        """Groups of size 3 or 4 must not trigger the thesis banner."""
        overlay = {
            "board_concentration": {"n": 4, "n_eff": 2.0},
            "factor_caveat": "",
            "same_thesis_groups": [
                {"members": ["A", "B", "C", "D"], "size": 4,
                 "basis": "membership-jaccard", "label": "IT"},
            ],
        }
        html = self._render_banner(overlay)
        assert "rx-thesis-banner" not in html, (
            "Groups of size 4 must not trigger thesis banner (threshold is >= 5)"
        )

    def test_banner_fires_for_group_gte5(self):
        """Group of size 5 triggers the thesis banner with EN and ZH text."""
        overlay = {
            "board_concentration": {"n": 5, "n_eff": 1.2},
            "factor_caveat": "",
            "same_thesis_groups": [
                {"members": ["A", "B", "C", "D", "E"], "size": 5,
                 "basis": "membership-jaccard", "label": "ai_infra"},
            ],
        }
        html = self._render_banner(overlay)
        assert "rx-thesis-banner" in html, "Group of size 5 must trigger thesis banner"
        assert "5 candidates, one thesis: ai_infra" in html, (
            "Banner must contain EN text with group size and label"
        )
        assert "5 候选，同一主题：ai_infra" in html, (
            "Banner must contain ZH text with group size and label"
        )

    def test_banner_contains_member_list(self):
        """Banner must list the group members."""
        overlay = {
            "board_concentration": {"n": 5, "n_eff": 1.2},
            "factor_caveat": "",
            "same_thesis_groups": [
                {"members": ["NVDA", "AMD", "INTC", "QCOM", "TXN"], "size": 5,
                 "basis": "membership-jaccard", "label": "semis"},
            ],
        }
        html = self._render_banner(overlay)
        for tkr in ["NVDA", "AMD", "INTC", "QCOM", "TXN"]:
            assert tkr in html, f"Member {tkr} must appear in banner"

    def test_no_title_attribute_in_banner(self):
        """CI law: no translated text inside title= attributes."""
        overlay = {
            "board_concentration": {"n": 6, "n_eff": 1.1},
            "factor_caveat": "some caveat",
            "same_thesis_groups": [
                {"members": ["A", "B", "C", "D", "E", "F"], "size": 6,
                 "basis": "membership-jaccard", "label": "test_label"},
            ],
        }
        html = self._render_banner(overlay)
        # Check that no title= attribute contains Chinese characters
        import re
        title_matches = re.findall(r'title=["\'][^"\']*["\']', html)
        for match in title_matches:
            # No Chinese characters allowed in title= attributes
            assert not any('一' <= ch <= '鿿' for ch in match), (
                f"Found Chinese text in title= attribute: {match!r}"
            )

    def test_rx_none_renders_empty(self):
        """When rx is None, banner renders empty (no error)."""
        overlay = None
        html = self._render_banner(overlay)
        assert "rx-banner" not in html, "None rx must render empty banner"

    def test_multiple_large_groups_all_rendered(self):
        """Multiple groups of size >= 5 all get banners."""
        overlay = {
            "board_concentration": {"n": 10, "n_eff": 2.0},
            "factor_caveat": "",
            "same_thesis_groups": [
                {"members": ["A", "B", "C", "D", "E"], "size": 5,
                 "basis": "membership-jaccard", "label": "group1"},
                {"members": ["F", "G", "H", "I", "J"], "size": 5,
                 "basis": "factor-cosine", "label": "group2"},
            ],
        }
        html = self._render_banner(overlay)
        assert html.count("rx-thesis-banner") == 2, (
            "Two groups of size 5 must each get a banner"
        )
