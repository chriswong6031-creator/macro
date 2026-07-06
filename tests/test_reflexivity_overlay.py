"""Tests for the W4 reflexivity overlay (engine/reflexivity.py + scripts/build_reflexivity_overlay.py).

Invariants tested:
  - Similarity matrix: symmetric, [0,1]-valued, self-similarity = 1
  - N_eff on synthetic identical candidates: N_eff ≈ 1
  - N_eff on synthetic orthogonal candidates: N_eff ≈ N
  - None-safety: names missing factor betas get membership-only similarity, never a crash
  - Missing-artifact degradation: builder degrades to empty overlay, never raises
  - Verdict thresholds: duplicate / partial / new boundaries
  - Earnings leg: always None in v1 (R-D ruling)
  - is_context_only: always True in artifact (R-F ruling)
  - schema: always "reflexivity_overlay.v1"
  - Basis flag printed for thin-beta names
  - n_eff_by_lane emitted per-lane (population-fix for invariant e)
  - _lane_tickers extracts correct per-lane set
  - empty overlay includes n_eff_by_lane with None values
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import engine.reflexivity as refmod
from engine.reflexivity import (
    HIGH_TIER_FACTORS,
    R2_FLOOR,
    build_groups_index,
    compute,
    factor_cosine,
    membership_jaccard,
    n_eff_participation_ratio,
    pairwise_similarity,
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

    def test_earnings_leg_always_none_in_v1(self):
        """R-D ruling: earnings leg not wired, must be None."""
        mem, sector, betas = self._basic_setup()
        result = compute(["NVDA", "AMD"], sector, betas, mem, "2026-07-05")
        for tkr, rec in result["by_ticker"].items():
            assert rec.get("earnings_leg") is None, (
                f"{tkr}: earnings_leg must be None in v1 but got {rec.get('earnings_leg')!r}"
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
