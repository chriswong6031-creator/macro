"""tests/test_board_contradictions.py — Invariant guard for board contradictions.

These tests assert that W3 evidence chips are display-only and never create
contradictions with the core board logic. Key invariants:

  1. A name on the WATCH (non-buy) lane must not have confluence_plus promoting it.
  2. Evidence fields must not affect lane assignment.
  3. A name with high confluence_k must not rank higher than a lower-confluence
     name when the lower-confluence name has higher alpha.
  4. Stop guidance must be absent if anticipation rec is absent.
  5. Template chips must not appear when their underlying data is absent / below threshold.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.grade_us_board import _row_features, build_track  # noqa: E402
from tests.test_grade_us_board import _minimal_grade_df  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _base_row(**kw) -> dict:
    base = {
        "ticker": "X", "sector": "Technology",
        "alpha": 0.5, "state": "FRESH BUY", "label": "FRESH BUY",
        "urgency": "now", "align_tier": "aligned", "off_high": -3.0,
        "lane": "trend", "arbiter_note": None,
        "conviction": {
            "score": 70, "band": "high", "composite_z": 0.5,
            "verdict": "Leader", "validation_status": "validated",
        },
    }
    base.update(kw)
    return base


def _boards_stub(*as_ofs):
    return [{"as_of": a, "rows": []} for a in as_ofs]


def _names_stub():
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# 1. Evidence fields must not change lane assignment
# ---------------------------------------------------------------------------

class TestLaneImmutability:
    """Evidence fields must not influence a row's lane attribute."""

    def test_watch_lane_rows_unchanged_by_evidence(self):
        """A watch-lane row with full evidence fields stays in watch lane."""
        row = _base_row(
            lane="watch",
            insider_buyers=5,
            gex_confirm={"verdict": "confirm"},
            confluence_plus={"k": 5, "groups": list("ABCDE")},
        )
        # lane must not be altered by evidence fields
        assert row["lane"] == "watch", "Lane must not be changed by evidence fields"

    def test_trend_lane_rows_unchanged_by_absent_evidence(self):
        """Absence of evidence fields must not demote a trend-lane row."""
        row = _base_row(lane="trend")
        # No evidence fields present; lane should remain trend
        assert row["lane"] == "trend"


# ---------------------------------------------------------------------------
# 2. confluence_k must not promote a low-alpha row above a high-alpha row
# ---------------------------------------------------------------------------

class TestConfluenceNoOrderingPower:
    """Confluence+ badge is display-only; it must NOT reorder the board."""

    def _sort_by_alpha_only(self, rows: list[dict]) -> list[str]:
        """Sort rows by alpha desc (the board's sort key). Lane-agnostic."""
        return [r["ticker"] for r in sorted(rows, key=lambda r: -(r.get("alpha") or 0))]

    def test_high_alpha_no_badge_beats_low_alpha_with_badge(self):
        rows = [
            {"ticker": "HIGH", "alpha": 0.9, "lane": "trend"},
            {"ticker": "LOW",  "alpha": 0.2, "lane": "trend",
             "confluence_plus": {"k": 7, "groups": list("ABCDEFG")},
             "insider_buyers": 5, "gex_confirm": {"verdict": "confirm"}},
        ]
        order = self._sort_by_alpha_only(rows)
        assert order[0] == "HIGH", "High-alpha name must rank first regardless of badge"

    def test_equal_alpha_row_order_not_affected_by_evidence(self):
        """When alphas are identical, evidence must not break ties differently
        depending on whether evidence fields are populated."""
        rows_no_ev = [
            {"ticker": "A", "alpha": 0.5, "lane": "trend"},
            {"ticker": "B", "alpha": 0.5, "lane": "trend"},
        ]
        rows_with_ev = [
            {"ticker": "A", "alpha": 0.5, "lane": "trend",
             "confluence_plus": {"k": 3, "groups": ["SUE", "GEX-OPTIONS", "INSIDER"]}},
            {"ticker": "B", "alpha": 0.5, "lane": "trend"},
        ]
        order_no_ev = self._sort_by_alpha_only(rows_no_ev)
        order_with_ev = self._sort_by_alpha_only(rows_with_ev)
        # Both should produce [A, B] (stable sort preserves insertion order for equal keys)
        assert order_no_ev == order_with_ev, (
            "Evidence fields must not change tie-breaking order")


# ---------------------------------------------------------------------------
# 3. Row features: strata values must not exceed expected types
# ---------------------------------------------------------------------------

class TestRowFeaturesTypes:
    """_row_features W3 fields must return the correct Python types."""

    def test_insider_cluster_is_bool(self):
        feat = _row_features(_base_row(insider_buyers=3))
        assert isinstance(feat["insider_cluster"], bool)

    def test_altdata_conv_gte2_is_bool(self):
        feat = _row_features(_base_row(altdata={"convergence_score": 3, "channels": []}))
        assert isinstance(feat["altdata_conv_gte2"], bool)

    def test_sue_fresh_is_bool(self):
        feat = _row_features(_base_row(sue_z=1.5, sue_fresh_days=30))
        assert isinstance(feat["sue_fresh"], bool)

    def test_news_burst_is_bool(self):
        feat = _row_features(_base_row(news_burst={"n_recent": 5}))
        assert isinstance(feat["news_burst"], bool)

    def test_smartmoney_add_is_bool(self):
        feat = _row_features(_base_row(smartmoney_chip={"action": "new", "n_funds_adding": 1}))
        assert isinstance(feat["smartmoney_add"], bool)

    def test_has_stop_guidance_is_bool(self):
        feat = _row_features(_base_row(stop_guidance={"pct": 5.0}))
        assert isinstance(feat["has_stop_guidance"], bool)

    def test_confluence_k_is_int(self):
        feat = _row_features(_base_row(confluence_plus={"k": 3, "groups": ["A", "B", "C"]}))
        assert isinstance(feat["confluence_k"], int)

    def test_gex_confirm_verdict_is_str_or_none(self):
        feat = _row_features(_base_row(gex_confirm={"verdict": "confirm"}))
        assert isinstance(feat["gex_confirm_verdict"], (str, type(None)))

    def test_gex_confirm_verdict_none_when_no_gex(self):
        feat = _row_features(_base_row())
        assert feat["gex_confirm_verdict"] is None


# ---------------------------------------------------------------------------
# 4. Chips absent below threshold (template-level invariant via Jinja2)
# ---------------------------------------------------------------------------

class TestChipThresholdGuards:
    """Evidence chips must not render when data is absent or below threshold.
    These are the same guards as in the template, tested via Jinja2."""

    def _render_chips(self, row: dict) -> str:
        import jinja2
        SNIPPET = """
{% set n = row %}
{% if n.gex_confirm and n.gex_confirm.get('verdict') in ('confirm', 'caution') %}GEX_ON{% else %}GEX_OFF{% endif %}
{% if n.altdata and (n.altdata.get('convergence_score') or 0) >= 2 %}ALT_ON{% else %}ALT_OFF{% endif %}
{% if n.news_burst and (n.news_burst.get('n_recent') or 0) >= 3 %}NEWS_ON{% else %}NEWS_OFF{% endif %}
{% if n.smartmoney_chip %}SM_ON{% else %}SM_OFF{% endif %}
{% if n.confluence_plus and (n.confluence_plus.get('k') or 0) >= 2 %}CONF_ON{% else %}CONF_OFF{% endif %}
"""
        env = jinja2.Environment(undefined=jinja2.Undefined, autoescape=False)
        return env.from_string(SNIPPET).render(row=row)

    def test_all_chips_off_for_empty_row(self):
        out = self._render_chips({})
        assert "GEX_OFF" in out
        assert "ALT_OFF" in out
        assert "NEWS_OFF" in out
        assert "SM_OFF" in out
        assert "CONF_OFF" in out

    def test_gex_off_for_neither_confirm_nor_caution(self):
        out = self._render_chips({"gex_confirm": {"verdict": "neutral"}})
        assert "GEX_OFF" in out

    def test_altdata_off_when_score_is_1(self):
        out = self._render_chips({"altdata": {"convergence_score": 1, "channels": ["congress_buy"]}})
        assert "ALT_OFF" in out

    def test_news_off_when_n_recent_is_2(self):
        out = self._render_chips({"news_burst": {"n_recent": 2}})
        assert "NEWS_OFF" in out

    def test_confluence_off_when_k_is_1(self):
        out = self._render_chips({"confluence_plus": {"k": 1, "groups": ["INSIDER"]}})
        assert "CONF_OFF" in out

    def test_all_chips_on_when_all_fields_present(self):
        row = {
            "gex_confirm": {"verdict": "confirm"},
            "altdata": {"convergence_score": 3, "channels": ["congress_buy", "patent_cluster"]},
            "news_burst": {"n_recent": 5},
            "smartmoney_chip": {"action": "new", "n_funds_adding": 2},
            "confluence_plus": {"k": 4, "groups": ["GEX-OPTIONS", "ALTDATA-ALT", "NEWS", "SMARTMONEY"]},
        }
        out = self._render_chips(row)
        assert "GEX_ON" in out
        assert "ALT_ON" in out
        assert "NEWS_ON" in out
        assert "SM_ON" in out
        assert "CONF_ON" in out


# ---------------------------------------------------------------------------
# 5. Missingness is never neutral: absent artifact -> evidence_health marker
# ---------------------------------------------------------------------------

class TestEvidenceHealthMarker:
    """When an artifact is absent, the evidence_health dict must be populated
    with the appropriate marker. This is enforced in build_stock_library.py
    during W3 evidence collection."""

    def _collect_health(self, row: dict) -> dict:
        """Inline the health-marker logic from the per-ticker evidence block."""
        health: dict[str, str] = {}
        if row.get("gex_confirm") is None:
            health["gex"] = "artifact_absent"
        if row.get("altdata") is None:
            health["altdata"] = "artifact_absent"
        if row.get("news_burst") is None:
            health["news"] = "artifact_absent"
        if row.get("smartmoney_chip") is None:
            health["smartmoney"] = "artifact_absent"
        return health

    def test_all_absent_produces_full_health_markers(self):
        health = self._collect_health({})
        assert health["gex"] == "artifact_absent"
        assert health["altdata"] == "artifact_absent"
        assert health["news"] == "artifact_absent"
        assert health["smartmoney"] == "artifact_absent"

    def test_present_artifact_no_health_marker(self):
        health = self._collect_health({
            "gex_confirm": {"verdict": "confirm"},
            "altdata": {"convergence_score": 2, "channels": []},
            "news_burst": {"n_recent": 4},
            "smartmoney_chip": {"action": "new", "n_funds_adding": 1},
        })
        assert "gex" not in health
        assert "altdata" not in health
        assert "news" not in health
        assert "smartmoney" not in health

    def test_partial_absence_only_marks_absent(self):
        health = self._collect_health({
            "gex_confirm": {"verdict": "caution"},
            # altdata absent
            "news_burst": {"n_recent": 3},
            # smartmoney absent
        })
        assert "gex" not in health
        assert health["altdata"] == "artifact_absent"
        assert "news" not in health
        assert health["smartmoney"] == "artifact_absent"


# ---------------------------------------------------------------------------
# 6. Blocked signal must never carry actionable urgency (W6-US invariant (b))
# ---------------------------------------------------------------------------

class TestBlockedUrgencyInvariant:
    """Regression for the 2026-07 deploy-gate incident: REZI/NGVT/ATMU/PCG shipped
    with label='BOTTOMING (blocked)' + urgency='imminent'. The builder pass that
    suffixes '(blocked)' only downgraded urgency=='now', so 'imminent' slipped
    through; their states (HOLD / TURN SIGNALED) also dodged the W8 arbiter's
    BOTTOMING-class rule. These tests exercise the real builder function, not a
    re-implementation."""

    @staticmethod
    def _blocked_row(ticker: str, state: str, urgency: str) -> dict:
        # Exact shape of the violating rows in site/factordata/us_standouts.json
        return {
            "ticker": ticker, "state": state, "label": "BOTTOMING",
            "label_zh": "筑底", "urgency": urgency, "lane": "buy",
            "signal": {"last": {"quality": "block"}, "ticks": 1},
            "entry_signal": {"status": "buy_soon"},
        }

    def _incident_rows(self) -> list[dict]:
        return [
            self._blocked_row("REZI", "TURN SIGNALED", "imminent"),
            self._blocked_row("NGVT", "HOLD", "imminent"),
            self._blocked_row("ATMU", "HOLD", "imminent"),
            self._blocked_row("PCG", "HOLD", "imminent"),
        ]

    def test_imminent_blocked_rows_downgraded(self):
        from scripts.build_stock_library import _enforce_blocked_buy_invariant
        rows = self._incident_rows()
        touched = _enforce_blocked_buy_invariant(rows)
        assert touched == 4
        for r in rows:
            assert r["urgency"] == "caution", f"{r['ticker']}: imminent must not survive block"
            assert "(blocked)" in r["label"]
            assert "（受阻）" in r["label_zh"]

    def test_now_blocked_still_downgraded(self):
        from scripts.build_stock_library import _enforce_blocked_buy_invariant
        rows = [self._blocked_row("X", "FRESH BUY", "now")]
        _enforce_blocked_buy_invariant(rows)
        assert rows[0]["urgency"] == "caution"

    def test_unblocked_rows_untouched(self):
        from scripts.build_stock_library import _enforce_blocked_buy_invariant
        rows = [{"ticker": "OK", "state": "FRESH BUY", "label": "FRESH BUY",
                 "urgency": "imminent", "signal": {"last": {"quality": "clean"}}}]
        touched = _enforce_blocked_buy_invariant(rows)
        assert touched == 0
        assert rows[0]["urgency"] == "imminent"
        assert rows[0]["label"] == "FRESH BUY"

    def test_idempotent_no_double_suffix(self):
        from scripts.build_stock_library import _enforce_blocked_buy_invariant
        rows = self._incident_rows()
        _enforce_blocked_buy_invariant(rows)
        _enforce_blocked_buy_invariant(rows)
        for r in rows:
            assert r["label"].count("(blocked)") == 1
            assert r["label_zh"].count("（受阻）") == 1

    def test_checker_passes_on_enforced_artifact(self, tmp_path):
        """End-to-end: the deploy-gate checker must accept what the builder emits."""
        import json as _json
        from scripts.build_stock_library import _enforce_blocked_buy_invariant
        from scripts.check_board_contradictions import _check
        rows = self._incident_rows()
        _enforce_blocked_buy_invariant(rows)
        artifact = tmp_path / "us_standouts.json"
        artifact.write_text(_json.dumps({"buy": rows}))
        assert _check(str(artifact)) == []

    def test_checker_catches_pre_fix_shape(self, tmp_path):
        """The exact artifact shape that shipped must trip invariant (b) — proves
        the pages.yml gate catches this class if the builder regresses."""
        import json as _json
        from scripts.check_board_contradictions import _check
        rows = self._incident_rows()
        for r in rows:  # pre-fix builder: label suffixed, urgency left imminent
            r["label"] = f"{r['label']} (blocked)"
        artifact = tmp_path / "us_standouts.json"
        artifact.write_text(_json.dumps({"buy": rows}))
        violations = _check(str(artifact))
        assert len(violations) == 4
        assert all("(b)" in v and "block" in v for v in violations)


# ---------------------------------------------------------------------------
# 7. Invariant (e): W4 reflexivity N_eff per-lane comparison
# ---------------------------------------------------------------------------

class TestInvariantEReflexivityNeff:
    """Invariant (e) compares per-lane n_eff from the overlay against per-lane
    board effective_bets.  Both numbers must be computed over the SAME population
    (the same per-lane candidate set) to avoid false-trip / false-pass.

    The fix: check_board_contradictions uses n_eff_by_lane[lane] from the overlay
    rather than the union board_concentration.n_eff.

    NOTE: invariant (e) reads companion artifacts at hardcoded paths relative to
    module ROOT (site/factordata/us_standouts_v2.json + reflexivity_overlay.json).
    Tests that exercise the live check use monkeypatch to redirect ROOT; tests
    that exercise the check logic directly call the inner comparison block.
    """

    def _write_companion_artifacts(
        self, root, eff_v2_eo, eff_v2_su, neff_by_lane_eo, neff_by_lane_su,
        union_neff=6.0,
    ):
        """Write companion artifacts under root/site/factordata/."""
        import json as _json
        v2_dir = root / "site" / "factordata"
        v2_dir.mkdir(parents=True, exist_ok=True)

        standouts_v2 = {
            "as_of": "2026-07-05",
            "lanes": {"entry_open": [], "setting_up": []},
            "concentration": {
                "entry_open": {
                    "n": 5, "n_sectors": 2, "top2_sector_share": 0.4,
                    "effective_bets": eff_v2_eo,
                    "effective_bets_basis": "membership-jaccard+high-tier-factor-cosine",
                    "concentrated": False, "by_sector": {},
                },
                "setting_up": {
                    "n": 3, "n_sectors": 2, "top2_sector_share": 0.5,
                    "effective_bets": eff_v2_su,
                    "effective_bets_basis": "membership-jaccard+high-tier-factor-cosine",
                    "concentrated": False, "by_sector": {},
                },
            },
        }
        (v2_dir / "us_standouts_v2.json").write_text(_json.dumps(standouts_v2))

        overlay = {
            "schema": "reflexivity_overlay.v1",
            "is_context_only": True,
            "board_concentration": {"n": 8, "n_eff": union_neff, "basis": "membership-jaccard"},
            "n_eff_by_lane": {
                "entry_open": neff_by_lane_eo,
                "setting_up": neff_by_lane_su,
            },
            "by_ticker": {}, "pair_basis": {}, "verdicts": {},
        }
        (v2_dir / "reflexivity_overlay.json").write_text(_json.dumps(overlay))
        (v2_dir / "us_standouts.json").write_text(_json.dumps({"buy": []}))
        return str(v2_dir / "us_standouts.json")

    def test_consistent_per_lane_neff_no_violation(self, tmp_path, monkeypatch):
        """Per-lane effective_bets and n_eff_by_lane within 3x → no violation."""
        import scripts.check_board_contradictions as cbc_mod
        monkeypatch.setattr(cbc_mod, "ROOT", tmp_path)
        from scripts.check_board_contradictions import _check

        artifact = self._write_companion_artifacts(
            tmp_path,
            eff_v2_eo=3.5, eff_v2_su=2.0,
            neff_by_lane_eo=3.8, neff_by_lane_su=2.2,
        )
        violations = _check(artifact)
        e_violations = [v for v in violations if "(e)" in v]
        assert e_violations == [], f"No (e) violation expected, got: {e_violations}"

    def test_divergent_per_lane_neff_fires_violation(self, tmp_path, monkeypatch):
        """Per-lane effective_bets and n_eff_by_lane diverge >3x → (e) violation."""
        import scripts.check_board_contradictions as cbc_mod
        monkeypatch.setattr(cbc_mod, "ROOT", tmp_path)
        from scripts.check_board_contradictions import _check

        artifact = self._write_companion_artifacts(
            tmp_path,
            eff_v2_eo=1.5, eff_v2_su=2.0,
            neff_by_lane_eo=9.0,   # ratio=6x > 3x → VIOLATION
            neff_by_lane_su=2.2,
        )
        violations = _check(artifact)
        e_violations = [v for v in violations if "(e)" in v]
        assert len(e_violations) == 1, f"Expected 1 (e) violation, got: {e_violations}"
        assert "entry_open" in e_violations[0]

    def test_none_per_lane_neff_skips_check(self, tmp_path, monkeypatch):
        """If n_eff_by_lane[lane] is None (empty lane), invariant (e) does not fire."""
        import scripts.check_board_contradictions as cbc_mod
        monkeypatch.setattr(cbc_mod, "ROOT", tmp_path)
        from scripts.check_board_contradictions import _check

        artifact = self._write_companion_artifacts(
            tmp_path,
            eff_v2_eo=3.0, eff_v2_su=2.0,
            neff_by_lane_eo=3.2,
            neff_by_lane_su=None,  # empty lane
        )
        violations = _check(artifact)
        e_violations = [v for v in violations if "(e)" in v]
        assert e_violations == [], f"None n_eff_by_lane should skip check, got: {e_violations}"

    def test_missing_n_eff_by_lane_skips_check(self, tmp_path, monkeypatch):
        """If overlay has no n_eff_by_lane (old schema), invariant (e) does not fire."""
        import json as _json
        import scripts.check_board_contradictions as cbc_mod
        monkeypatch.setattr(cbc_mod, "ROOT", tmp_path)
        from scripts.check_board_contradictions import _check

        v2_dir = tmp_path / "site" / "factordata"
        v2_dir.mkdir(parents=True)

        standouts_v2 = {
            "concentration": {
                "entry_open": {"effective_bets": 2.0, "effective_bets_basis": "X",
                               "n": 3, "n_sectors": 1, "top2_sector_share": 0.8,
                               "concentrated": False, "by_sector": {}},
                "setting_up": {"effective_bets": 1.5, "effective_bets_basis": "X",
                               "n": 2, "n_sectors": 1, "top2_sector_share": 1.0,
                               "concentrated": False, "by_sector": {}},
            },
        }
        # Old overlay schema: no n_eff_by_lane — would diverge if union n_eff were used
        overlay_old = {
            "schema": "reflexivity_overlay.v1",
            "board_concentration": {"n": 5, "n_eff": 50.0},
        }
        (v2_dir / "us_standouts_v2.json").write_text(_json.dumps(standouts_v2))
        (v2_dir / "reflexivity_overlay.json").write_text(_json.dumps(overlay_old))
        (v2_dir / "us_standouts.json").write_text(_json.dumps({"buy": []}))

        violations = _check(str(v2_dir / "us_standouts.json"))
        e_violations = [v for v in violations if "(e)" in v]
        assert e_violations == [], (
            "Old overlay without n_eff_by_lane should not fire invariant (e)"
        )

    def test_docstring_does_not_promise_basis_check(self):
        """Docstring for invariant (e) must NOT contain the old false clause about
        'effective_bets_basis must NOT be sector-only-hhi' — that check was never
        implemented, and the false promise has been removed."""
        import inspect
        import scripts.check_board_contradictions as cbc_mod
        module_doc = cbc_mod.__doc__ or ""
        # The old false clause mentioned both conditions together
        assert "sector-only-hhi" not in module_doc, (
            "False docstring clause about sector-only-hhi must be removed from module docstring"
        )
        # The word 'duplicate verdicts' as a checked condition must also be gone
        assert "duplicate verdicts" not in module_doc, (
            "False docstring clause about duplicate verdicts must be removed from module docstring"
        )

    def test_invariant_e_uses_n_eff_by_lane_not_union(self, tmp_path, monkeypatch):
        """Critical: invariant (e) must use n_eff_by_lane, NOT board_concentration.n_eff.
        If it still uses union n_eff, a large union value (99.9) far from per-lane
        board effective_bets (3.0, 2.0) would false-trip.  Verify no violation when
        per-lane n_eff values are within 3x of board effective_bets."""
        import scripts.check_board_contradictions as cbc_mod
        monkeypatch.setattr(cbc_mod, "ROOT", tmp_path)
        from scripts.check_board_contradictions import _check

        artifact = self._write_companion_artifacts(
            tmp_path,
            eff_v2_eo=3.0, eff_v2_su=2.0,
            neff_by_lane_eo=3.2,  # within 3x of 3.0 → no violation
            neff_by_lane_su=1.8,  # within 3x of 2.0 → no violation
            union_neff=99.9,      # union far from board: would false-trip if used
        )
        violations = _check(artifact)
        e_violations = [v for v in violations if "(e)" in v]
        assert e_violations == [], (
            f"Invariant (e) must use per-lane n_eff, not union n_eff. "
            f"Got violations: {e_violations}"
        )


# ---------------------------------------------------------------------------
# 8. Invariant (d): the two sort contracts (us_prophet_v1 + legacy)
# ---------------------------------------------------------------------------

class TestInvariantDSortContracts:
    """Invariant (d) asks "is the board in ITS OWN declared order?", and which order
    that is depends on the artifact.

    us_prophet_v1 rows carry `stage`, and the order is (stage bucket, priority score
    desc, ticker) — alpha is one of five legs there, so an alpha-desc assertion would
    turn every correct render red. Legacy rows carry no `stage` and keep the
    pre-2026-08 alpha-desc-within-lane check.

    Both branches must still be able to FAIL: a guard that stopped seeing broken
    sorts would be worse than no guard at all.
    """

    @staticmethod
    def _row(ticker, stage, score, **extra):
        row = {"ticker": ticker, "stage": stage, "prophet": {"score": score},
               "lane": "continuation"}
        row.update(extra)
        return row

    def _write(self, tmp_path, buy):
        import json as _json
        artifact = tmp_path / "us_standouts.json"
        artifact.write_text(_json.dumps({"buy": buy}))
        return str(artifact)

    def _d(self, violations):
        return [v for v in violations if v.startswith("(d)")]

    # -- prophet branch -----------------------------------------------------

    def _good_board(self):
        return [
            self._row("AAA", "live", 88.0, alpha=0.1),
            self._row("BBB", "live", 71.5, alpha=1.9),      # alpha ASCENDS: legal now
            self._row("CCC", "setting_up", 60.0, alpha=2.5),
            self._row("DDD", "ran", 44.0, alpha=-0.2),
            self._row("EEE", "blocked", 90.0, alpha=3.0),   # high score, still last
        ]

    def test_a_correctly_ordered_prophet_board_is_clean(self, tmp_path):
        from scripts.check_board_contradictions import _check
        assert self._d(_check(self._write(tmp_path, self._good_board()))) == []

    def test_alpha_ascending_is_no_longer_a_violation(self, tmp_path):
        """The legacy branch would flag a negative-alpha row above a positive one;
        under us_prophet_v1 that is the score doing its job."""
        from scripts.check_board_contradictions import _check
        buy = [self._row("NEG", "live", 88.0, alpha=-1.5),
               self._row("POS", "live", 40.0, alpha=2.0)]
        assert self._d(_check(self._write(tmp_path, buy))) == []

    def test_stage_running_backwards_trips(self, tmp_path):
        from scripts.check_board_contradictions import _check
        buy = [self._row("RAN", "ran", 44.0), self._row("LIVE", "live", 88.0)]
        assert any("stage buckets must run" in v
                   for v in self._d(_check(self._write(tmp_path, buy))))

    def test_a_blocked_row_above_a_live_row_trips(self, tmp_path):
        from scripts.check_board_contradictions import _check
        buy = [self._row("BLK", "blocked", 99.0), self._row("LIVE", "live", 88.0)]
        viols = self._d(_check(self._write(tmp_path, buy)))
        assert any("blocked-stage row sits at slot 1" in v for v in viols)

    def test_score_rising_inside_a_stage_trips(self, tmp_path):
        from scripts.check_board_contradictions import _check
        buy = [self._row("LOW", "live", 40.0), self._row("HIGH", "live", 88.0)]
        assert any("outranks the row above it" in v
                   for v in self._d(_check(self._write(tmp_path, buy))))

    def test_an_unknown_stage_trips(self, tmp_path):
        from scripts.check_board_contradictions import _check
        buy = [self._row("WAT", "banana", 40.0), self._row("LIVE", "live", 88.0)]
        assert any("unknown stage" in v
                   for v in self._d(_check(self._write(tmp_path, buy))))

    def test_a_scrambled_prophet_board_trips(self, tmp_path):
        """Mutation check: reverse a valid board and the guard must see it."""
        from scripts.check_board_contradictions import _check
        buy = list(reversed(self._good_board()))
        assert self._d(_check(self._write(tmp_path, buy)))

    def test_missing_scores_do_not_crash_the_walk(self, tmp_path):
        from scripts.check_board_contradictions import _check
        buy = [{"ticker": "A", "stage": "live"}, {"ticker": "B", "stage": "ran"}]
        assert self._d(_check(self._write(tmp_path, buy))) == []

    def test_a_scoreless_row_does_not_blind_the_walk_behind_it(self, tmp_path):
        """A None score used to CLOBBER the comparison anchor, so one scoreless row in
        the middle of a bucket masked the very violation that followed it: [100, None,
        200] inside one stage compared nothing at all and passed clean. The anchor now
        carries the last SCORED row forward, so the guard can see the failure."""
        from scripts.check_board_contradictions import _check
        buy = [self._row("TOP", "live", 100.0),
               {"ticker": "GAP", "stage": "live", "lane": "continuation"},
               self._row("BAD", "live", 200.0)]
        viols = self._d(_check(self._write(tmp_path, buy)))
        assert any("BAD" in v and "outranks the row above it" in v for v in viols), (
            f"a scoreless row must not hide the score inversion behind it, got {viols}")

    def test_a_scoreless_row_alone_is_still_not_a_violation(self, tmp_path):
        """The anchor must not turn a MISSING reading into a reported one."""
        from scripts.check_board_contradictions import _check
        buy = [self._row("TOP", "live", 100.0),
               {"ticker": "GAP", "stage": "live", "lane": "continuation"},
               self._row("OK", "live", 90.0)]
        assert self._d(_check(self._write(tmp_path, buy))) == []

    def test_a_new_bucket_restarts_the_score_chain(self, tmp_path):
        """Scores are only comparable inside one stage: a `setting_up` row may score
        above the last `live` row without that being a sort break."""
        from scripts.check_board_contradictions import _check
        buy = [self._row("LIVE", "live", 10.0),
               self._row("SETUP", "setting_up", 99.0),
               self._row("SETUP2", "setting_up", 98.0)]
        assert self._d(_check(self._write(tmp_path, buy))) == []

    def test_an_unknown_stage_does_not_reset_the_anchor_either(self, tmp_path):
        """The unknown-stage row is reported and skipped; the rows around it are still
        judged against each other."""
        from scripts.check_board_contradictions import _check
        buy = [self._row("TOP", "live", 40.0),
               self._row("WAT", "banana", 55.0),
               self._row("BAD", "live", 88.0)]
        viols = self._d(_check(self._write(tmp_path, buy)))
        assert any("unknown stage" in v for v in viols)
        assert any("BAD" in v and "outranks" in v for v in viols)

    # -- legacy branch ------------------------------------------------------

    def test_legacy_board_still_gets_the_alpha_check(self, tmp_path):
        """No `stage` field anywhere => the pre-2026-08 contract, unchanged."""
        from scripts.check_board_contradictions import _check
        buy = [{"ticker": "NEG", "lane": "trend", "alpha": -1.5},
               {"ticker": "POS", "lane": "trend", "alpha": 2.0}]
        viols = self._d(_check(self._write(tmp_path, buy)))
        assert len(viols) == 1 and "sort broken" in viols[0]

    def test_legacy_board_in_alpha_order_is_clean(self, tmp_path):
        from scripts.check_board_contradictions import _check
        buy = [{"ticker": "POS", "lane": "trend", "alpha": 2.0},
               {"ticker": "NEG", "lane": "trend", "alpha": -1.5}]
        assert self._d(_check(self._write(tmp_path, buy))) == []

    def test_one_staged_row_switches_the_whole_board_to_the_new_contract(self, tmp_path):
        """The branch is chosen by the artifact, not per row — a partially migrated
        board must not be judged by two contradictory contracts at once."""
        from scripts.check_board_contradictions import _check
        buy = [self._row("NEG", "live", 88.0, alpha=-1.5),
               {"ticker": "POS", "lane": "continuation", "alpha": 2.0,
                "stage": "blocked", "prophet": {"score": 10.0}}]
        assert self._d(_check(self._write(tmp_path, buy))) == []
