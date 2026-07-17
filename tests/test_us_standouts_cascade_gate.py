"""tests/test_us_standouts_cascade_gate.py — Cascade-gate inclusion + lane fallback.

Covers the 2026-07-16 migration of the US standout wide board's inclusion gate from
bottoming-alignment to signal_gate cascade eligibility (parity with CN/HK).

Tests import the REAL helpers from scripts.build_stock_library (_atier,
_cascade_elig, _lane_for) and order through the REAL signal_gate.blend_sorted
with the exact lambda wiring the builder uses — no mirrored logic.

Key invariants:
  A. Names with cascade eligible=True (regardless of alignment tier) are included;
     names without a cascade-eligible verdict are excluded (alignment no longer admits).
  B. Board order = owner's weighted cascade blend (signal_gate.blend_sorted, US
     defaults): at equal conviction T2 > T1 > T3 > T4 (WEIGHTS 1.0/0.9/0.6/0.4);
     a strong-conviction lower tier outranks a weak master; weightless-but-eligible
     names sink to the bottom but STAY on the shelf.
  C. _lane_for(None, "rising") → "continuation"; _lane_for(None, non-rising) →
     "bottoming" (the cascade-gate lane fallback).
  D. build_operator_exposure_log._KNOWN_LANE_SURFACES includes "recovery".
"""
from __future__ import annotations

from engine import signal_gate
from engine.confluence_tiers import WEIGHTS
from scripts.build_stock_library import _atier, _cascade_elig, _lane_for


# ---------------------------------------------------------------------------
# Helpers (fixtures only — all logic under test is imported)
# ---------------------------------------------------------------------------

def _dummy_profile(composite_z: float = 0.5,
                   aligned: bool = False, near: bool = False,
                   weekly: str = "rising") -> dict:
    """Minimal profile dict with alignment and composite_z."""
    return {
        "composite_z": composite_z,
        "alignment": {
            "aligned": aligned,
            "near": near,
            "weekly": weekly,
            "score": 0.8 if aligned else (0.4 if near else 0.0),
        },
        "cycle_blocked": False,
        "axes": {"entry": {"z": 0.3}},
        "ladder": {"state": "FRESH BUY"},
    }


def _cascade_verdict(tier: str | None, eligible: bool = True) -> dict:
    """Minimal signal_gate verdict with the REAL confluence_tiers.WEIGHTS."""
    return {
        "eligible": eligible,
        "tier_cascade": tier,
        "tier": "take" if tier in ("T1", "T2") else "anticipation",
        "sub": None,
        "weight": WEIGHTS.get(tier or "", 0.0),
        "above200": True,
        "ticks": 1,
        "fresh_bars": 1,
    }


def _not_eligible_verdict() -> dict:
    return {
        "eligible": False, "tier_cascade": None, "tier": None,
        "sub": None, "weight": 0.0,
    }


def _make_scored(tickers_profiles: list[tuple[str, dict]]) -> list[tuple]:
    """Pre-sorted scored list as build_stock_library produces it."""
    scored = [(t, p) for t, p in tickers_profiles]
    scored.sort(key=lambda kv: (-(kv[1]["composite_z"]), kv[0]))
    return scored


def _board_order(scored: list[tuple], sig_verdict: dict,
                 coiled_by: dict | None = None) -> list[tuple]:
    """The EXACT wide-board wiring in build_stock_library.main(): inclusion via
    _cascade_elig, ordering via signal_gate.blend_sorted (US defaults) with the
    same base/verdict/bonus lambdas."""
    cb = coiled_by or {}
    elig = _cascade_elig(scored, sig_verdict)
    return signal_gate.blend_sorted(
        elig,
        base_of=lambda x: x[1].get("composite_z") or 0.0,
        verdict_of=lambda x: sig_verdict.get(x[0]),
        bonus_of=lambda x: ((cb.get(x[0]) or {}).get("bonus") or 0.0),
    )


# ---------------------------------------------------------------------------
# A. Cascade-eligible names admitted regardless of alignment tier
# ---------------------------------------------------------------------------

class TestCascadeInclusion:

    def test_eligible_without_alignment_admitted(self):
        """A name with eligible=True but no alignment (tier=None) must be admitted."""
        scored = _make_scored([
            ("NVDA", _dummy_profile(composite_z=0.9, aligned=False, near=False)),
        ])
        sig_verdict = {"NVDA": _cascade_verdict("T1", eligible=True)}
        tickers = [t for t, _, _ in _cascade_elig(scored, sig_verdict)]
        assert "NVDA" in tickers, "Cascade-eligible name without alignment MUST be admitted"

    def test_eligible_with_alignment_admitted(self):
        """A name with both eligible=True AND aligned=True is also admitted."""
        scored = _make_scored([
            ("AAPL", _dummy_profile(composite_z=0.7, aligned=True, near=False)),
        ])
        sig_verdict = {"AAPL": _cascade_verdict("T2", eligible=True)}
        tickers = [t for t, _, _ in _cascade_elig(scored, sig_verdict)]
        assert "AAPL" in tickers

    def test_aligned_but_not_eligible_excluded(self):
        """A name with aligned=True but cascade eligible=False is EXCLUDED."""
        scored = _make_scored([
            ("GNL", _dummy_profile(composite_z=0.8, aligned=True, near=False)),
        ])
        sig_verdict = {"GNL": _not_eligible_verdict()}
        tickers = [t for t, _, _ in _cascade_elig(scored, sig_verdict)]
        assert "GNL" not in tickers, "Aligned but not cascade-eligible must NOT be admitted"

    def test_near_but_not_eligible_excluded(self):
        """A name with near=True but cascade eligible=False is EXCLUDED."""
        scored = _make_scored([
            ("XOM", _dummy_profile(composite_z=0.6, aligned=False, near=True)),
        ])
        sig_verdict = {"XOM": _not_eligible_verdict()}
        tickers = [t for t, _, _ in _cascade_elig(scored, sig_verdict)]
        assert "XOM" not in tickers

    def test_missing_sig_verdict_excluded(self):
        """A name absent from sig_verdict (no cascade data) is EXCLUDED."""
        scored = _make_scored([
            ("TSLA", _dummy_profile(composite_z=0.5, aligned=True)),
        ])
        assert _cascade_elig(scored, {}) == [], \
            "Name absent from sig_verdict must be excluded"

    def test_mixed_eligible_and_not(self):
        """Only eligible names appear in the result; non-eligible dropped."""
        scored = _make_scored([
            ("A_ELIG", _dummy_profile(composite_z=0.9, aligned=False)),
            ("B_ALIGNED_NOTELIG", _dummy_profile(composite_z=0.8, aligned=True)),
            ("C_ELIG", _dummy_profile(composite_z=0.6, aligned=True)),
        ])
        sig_verdict = {
            "A_ELIG": _cascade_verdict("T1", eligible=True),
            "B_ALIGNED_NOTELIG": _not_eligible_verdict(),
            "C_ELIG": _cascade_verdict("T3", eligible=True),
        }
        tickers = [t for t, _, _ in _cascade_elig(scored, sig_verdict)]
        assert "A_ELIG" in tickers
        assert "C_ELIG" in tickers
        assert "B_ALIGNED_NOTELIG" not in tickers

    def test_empty_sig_verdict_zero_results(self):
        """Empty sig_verdict admits nothing (cascade gate is sole gate)."""
        scored = _make_scored([
            ("MSFT", _dummy_profile(composite_z=1.0, aligned=True)),
            ("AAPL", _dummy_profile(composite_z=0.9, aligned=True)),
        ])
        assert _cascade_elig(scored, {}) == []

    def test_atier_still_in_tuple(self):
        """The third element of each result tuple is _atier(p) for downstream badge use."""
        scored = _make_scored([
            ("ALIGNED_T1", _dummy_profile(composite_z=0.9, aligned=True)),
            ("NONE_T2", _dummy_profile(composite_z=0.7, aligned=False, near=False)),
            ("NEAR_T3", _dummy_profile(composite_z=0.5, aligned=False, near=True)),
        ])
        sig_verdict = {
            "ALIGNED_T1": _cascade_verdict("T1", eligible=True),
            "NONE_T2": _cascade_verdict("T2", eligible=True),
            "NEAR_T3": _cascade_verdict("T3", eligible=True),
        }
        tier_by_t = {t: tier for t, _, tier in _cascade_elig(scored, sig_verdict)}
        assert tier_by_t["ALIGNED_T1"] == "aligned"
        assert tier_by_t["NONE_T2"] is None
        assert tier_by_t["NEAR_T3"] == "near"

    def test_atier_none_profile_safe(self):
        """_atier tolerates a None/empty profile (graceful, no crash)."""
        assert _atier(None) is None
        assert _atier({}) is None


# ---------------------------------------------------------------------------
# B. Board order: owner's weighted cascade blend (signal_gate.blend_sorted)
# ---------------------------------------------------------------------------

class TestBoardOrderBlend:

    def _order(self, tiers_czs: list[tuple[str, str, float]]) -> list[str]:
        """Board ticker order from [(ticker, tier, composite_z), ...] (all eligible)."""
        scored = _make_scored([(t, _dummy_profile(composite_z=cz)) for t, _, cz in tiers_czs])
        sig_verdict = {t: _cascade_verdict(tier, eligible=True) for t, tier, _ in tiers_czs}
        return [t for t, _, _ in _board_order(scored, sig_verdict)]

    def test_tier_order_at_equal_conviction(self):
        """Equal composite_z ⇒ tier weight decides: T2 > T1 > T3 > T4
        (confluence_tiers.WEIGHTS 1.0/0.9/0.6/0.4, operator-ratified)."""
        tickers = self._order([
            ("N_T4", "T4", 0.5), ("N_T1", "T1", 0.5),
            ("N_T3", "T3", 0.5), ("N_T2", "T2", 0.5),
        ])
        assert tickers == ["N_T2", "N_T1", "N_T3", "N_T4"]

    def test_strong_t3_outranks_weak_t1(self):
        """The blend's raison d'être (blend_sorted docstring): a strong-conviction
        T3 must outrank a weak T1 master — strict tier-first would bury it."""
        tickers = self._order([("WEAK_T1", "T1", -1.5), ("STRONG_T3", "T3", 2.5),
                               ("MID_T4", "T4", 0.0)])
        assert tickers.index("STRONG_T3") < tickers.index("WEAK_T1")

    def test_within_tier_sort_by_composite_z_desc(self):
        """Within the same cascade tier, higher composite_z ranks first."""
        tickers = self._order([("AAA", "T1", 0.3), ("BBB", "T1", 0.8), ("CCC", "T1", 0.5)])
        assert tickers == ["BBB", "CCC", "AAA"]

    def test_equal_everything_deterministic_ticker_asc(self):
        """Equal tier + equal composite_z: blend score ties; the stable sort keeps
        the scored order (composite desc, ticker asc) — deterministic board."""
        tickers = self._order([("ZZZ", "T2", 0.5), ("AAA", "T2", 0.5), ("MMM", "T2", 0.5)])
        assert tickers == ["AAA", "MMM", "ZZZ"]

    def test_weightless_eligible_sinks_but_included(self):
        """An eligible verdict with no cascade tier (weight 0) sinks to the shelf
        bottom but is NOT dropped (eligibility is the sole inclusion predicate)."""
        scored = _make_scored([
            ("NOTIER", _dummy_profile(composite_z=3.0)),
            ("T4NAME", _dummy_profile(composite_z=-1.0)),
        ])
        sig_verdict = {"NOTIER": _cascade_verdict(None, eligible=True),
                       "T4NAME": _cascade_verdict("T4", eligible=True)}
        tickers = [t for t, _, _ in _board_order(scored, sig_verdict)]
        assert tickers == ["T4NAME", "NOTIER"]

    def test_coiled_bonus_lifts(self):
        """The COILED cohort-washout bonus lifts a name within its tier
        (wave-2-validated display ranking bonus, framework ledger 2026-07-01)."""
        scored = _make_scored([
            ("PLAIN", _dummy_profile(composite_z=0.6)),
            ("COILED", _dummy_profile(composite_z=0.5)),
        ])
        sig_verdict = {t: _cascade_verdict("T1", eligible=True) for t in ("PLAIN", "COILED")}
        without = [t for t, _, _ in _board_order(scored, sig_verdict)]
        with_bonus = [t for t, _, _ in _board_order(
            scored, sig_verdict, coiled_by={"COILED": {"bonus": 0.3}})]
        assert without == ["PLAIN", "COILED"]
        assert with_bonus == ["COILED", "PLAIN"]


# ---------------------------------------------------------------------------
# C. _lane_for tier=None behavior (the 2026-07-16 cascade-gate lane fallback)
# ---------------------------------------------------------------------------

class TestLaneForNoneTier:
    """_lane_for(None, weekly_phase) reflects cascade-gate semantics:
    rising weekly → 'continuation'; non-rising → 'bottoming'. Tests call the
    REAL module-level _lane_for in scripts.build_stock_library."""

    def test_none_rising_is_continuation(self):
        assert _lane_for(None, "rising") == "continuation", (
            "tier=None + weekly=rising must yield 'continuation' (uptrending leader)")

    def test_none_rolling_is_bottoming(self):
        assert _lane_for(None, "rolling") == "bottoming"

    def test_none_falling_is_bottoming(self):
        assert _lane_for(None, "falling") == "bottoming"

    def test_none_unknown_is_bottoming(self):
        assert _lane_for(None, "unknown") == "bottoming"

    def test_none_none_weekly_is_bottoming(self):
        assert _lane_for(None, None) == "bottoming"

    def test_aligned_still_bottoming_regardless_of_weekly(self):
        """Existing aligned → bottoming behavior must NOT change."""
        assert _lane_for("aligned", "rising") == "bottoming"
        assert _lane_for("aligned", "falling") == "bottoming"

    def test_near_rising_is_continuation(self):
        """Existing near+rising → continuation must still hold."""
        assert _lane_for("near", "rising") == "continuation"

    def test_near_non_rising_is_bottoming(self):
        assert _lane_for("near", "falling") == "bottoming"

    def test_replay_vocab_prime_is_bottoming(self):
        """Replay vocabulary (PRIME/ARMED/APPROACHING) still handled."""
        assert _lane_for("PRIME", "rising") == "bottoming"
        assert _lane_for("ARMED", "rising") == "continuation"
        assert _lane_for("APPROACHING", "falling") == "bottoming"

    def test_unknown_vocab_defaults_bottoming(self):
        assert _lane_for("GIBBERISH", "rising") == "bottoming"


# ---------------------------------------------------------------------------
# D. build_operator_exposure_log._KNOWN_LANE_SURFACES includes "recovery"
# ---------------------------------------------------------------------------

class TestExposureLogRecoveryLane:
    def test_recovery_in_known_lane_surfaces(self):
        import scripts.build_operator_exposure_log as boel
        assert "recovery" in boel._KNOWN_LANE_SURFACES, \
            "'recovery' must be in _KNOWN_LANE_SURFACES (maps to 'board_buy')"

    def test_recovery_maps_to_board_buy(self):
        import scripts.build_operator_exposure_log as boel
        assert boel._KNOWN_LANE_SURFACES["recovery"] == "board_buy"

    def test_recovery_not_counted_as_unknown_lane(self, tmp_path):
        """A board row with lane='recovery' must NOT increment n_unknown_lanes."""
        import json
        import scripts.build_operator_exposure_log as boel

        root = tmp_path
        (root / "site" / "marketdata").mkdir(parents=True)
        (root / "site" / "factordata").mkdir(parents=True)
        (root / "data" / "governance").mkdir(parents=True)
        (root / "data" / "operator").mkdir(parents=True)

        as_of = "2026-07-16"
        # Write minimal experiments.json
        (root / "site" / "marketdata" / "experiments.json").write_text(
            json.dumps({"schema": "experiments_registry.v1", "as_of": as_of,
                        "experiments": []}))
        # Write us_standouts.json with a recovery-lane buy row
        standouts = {
            "as_of": as_of,
            "buy": [{"ticker": "RECOV", "lane": "recovery"}],
            "watch": [],
        }
        (root / "site" / "factordata" / "us_standouts.json").write_text(
            json.dumps(standouts))
        # Write empty alerts
        (root / "site" / "marketdata" / "wh_banner.json").write_text(
            json.dumps({"alerts": []}))
        (root / "site" / "marketdata" / "rr_banner.json").write_text(
            json.dumps({"as_of": as_of, "alert": None}))

        result = boel.run(root=root)
        assert result["n_unknown_lanes"] == 0, (
            f"recovery lane must NOT be counted as unknown; got {result['n_unknown_lanes']}")
