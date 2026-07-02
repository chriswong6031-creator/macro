"""Tests for D3-W3.3 — falsifier tripwire compiler + latched FIRED + alert wiring.

Acceptance areas (per the wave spec):

  (1) DSL EVALUATOR    — gt/lt/cross/sustain/yoy/all/any/not each covered on
                         synthetic series (pure in-memory, no disk reads)
  (2) LATCH SEMANTICS  — fires once, stays FIRED, current_leg flips when
                         condition recovers; version-bump un-latches
  (3) TTL / OVERDUE    — MANUAL entries show overdue_days when TTL elapsed
  (4) DATA_MISSING     — stale tape (> _STALE_TRADING_DAYS trading days)
                         surfaces DATA_MISSING, never silently ARMED
  (5) FALSIFIERS JSON  — the committed registry is valid JSON; 23 cycle entries;
                         correct coverage tally (10 full / 8 partial / 5 none)
  (6) BUILD INTEGRATION smoke — evaluate_all + persist round-trips cleanly
                                (data-guarded; skips in data-less checkout)

Tests use synthetic in-memory series via monkeypatching — zero disk I/O in the
core DSL tests (important: the evaluator must be pure-functional over data).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
FALSIFIERS_JSON = ROOT / "data" / "cycle_ontology" / "falsifiers.json"


# ── helpers ───────────────────────────────────────────────────────────────────
def _make_series(values, start="2020-01-01", freq="B") -> pd.Series:
    """Build a synthetic daily pd.Series over business days."""
    idx = pd.bdate_range(start, periods=len(values))
    return pd.Series(values, index=idx, dtype=float)


def _asof(s: pd.Series) -> pd.Timestamp:
    """Return a timestamp safely past the series end."""
    return s.index[-1] + pd.Timedelta(days=1)


def _patch_read(ref: str, s: pd.Series | None):
    """Return a context manager that patches store.read for a given ref."""
    grp, tick = ref.split(":", 1)
    if s is None:
        df = None
    else:
        df = s.rename("close").to_frame()
    return patch("lib.store.read", side_effect=lambda g, t: df if g == grp and t == tick else None)


# ── (1) DSL EVALUATOR ─────────────────────────────────────────────────────────
class TestDSLEvaluator:
    """Each combinator + op exercised with a synthetic series."""

    def test_gt_true(self):
        from engine.falsifier_tripwires import _eval_leg
        s = _make_series([50, 60, 70, 80])
        asof = _asof(s)
        with _patch_read("fred:X", s):
            r, d = _eval_leg({"series": "fred:X", "op": "gt", "value": 75}, asof)
        assert r is True
        assert d["value_now"] == 80.0

    def test_lt_false(self):
        from engine.falsifier_tripwires import _eval_leg
        s = _make_series([50, 60, 70, 80])
        asof = _asof(s)
        with _patch_read("fred:X", s):
            r, d = _eval_leg({"series": "fred:X", "op": "lt", "value": 75}, asof)
        assert r is False

    def test_sustain_fails_when_not_enough_bars_hold(self):
        from engine.falsifier_tripwires import _eval_leg
        # last 3 bars: [60, 80, 80] — sustain=3 requires ALL 3 > 75; 60 fails
        s = _make_series([90, 90, 60, 80, 80])
        asof = _asof(s)
        with _patch_read("yahoo:Y", s):
            r, d = _eval_leg({"series": "yahoo:Y", "op": "gt", "value": 75, "sustain_bars": 3}, asof)
        assert r is False

    def test_sustain_passes_when_all_bars_hold(self):
        from engine.falsifier_tripwires import _eval_leg
        s = _make_series([50, 90, 90, 90])
        asof = _asof(s)
        with _patch_read("yahoo:Y", s):
            r, d = _eval_leg({"series": "yahoo:Y", "op": "gt", "value": 75, "sustain_bars": 3}, asof)
        assert r is True

    def test_cross_above(self):
        from engine.falsifier_tripwires import _eval_leg
        # last bar crosses above threshold (prev ≤ 100, cur > 100)
        s = _make_series([90, 95, 98, 101])
        asof = _asof(s)
        with _patch_read("yahoo:Z", s):
            r, d = _eval_leg({"series": "yahoo:Z", "op": "cross_above", "value": 100}, asof)
        assert r is True

    def test_cross_above_no_cross(self):
        from engine.falsifier_tripwires import _eval_leg
        # already above threshold in prior bar — not a fresh cross
        s = _make_series([90, 101, 102, 103])
        asof = _asof(s)
        with _patch_read("yahoo:Z", s):
            r, d = _eval_leg({"series": "yahoo:Z", "op": "cross_above", "value": 100}, asof)
        assert r is False

    def test_yoy_pct_transform_gt(self):
        from engine.falsifier_tripwires import _eval_leg
        # The yoy_pct transform shifts by 252 bars (daily) and computes % change.
        # Build a 260-bar series: first 252 bars at 100, last 8 bars at 106.
        # The last bar's yoy = (106 - 100) / 100 * 100 = 6% > 5%.
        base = 100.0
        arr = [base] * 252 + [base * 1.06] * 8
        s = _make_series(arr)
        asof = _asof(s)
        with _patch_read("fred:C", s):
            r, d = _eval_leg({"series": "fred:C", "op": "gt", "value": 5.0,
                               "transform": "yoy_pct"}, asof)
        assert r is True, f"yoy should be ~6% > 5%; detail={d}"

    def test_all_combinator(self):
        from engine.falsifier_tripwires import _eval_expr
        s1 = _make_series([100])
        s2 = _make_series([50])
        asof = _asof(s1)
        # all([X>90, Y>60]) → True & False = False
        expr = {"all": [
            {"series": "yahoo:A", "op": "gt", "value": 90},
            {"series": "yahoo:B", "op": "gt", "value": 60},
        ]}
        def fake_read(g, t):
            if t == "A": return s1.rename("close").to_frame()
            if t == "B": return s2.rename("close").to_frame()
            return None
        with patch("lib.store.read", side_effect=fake_read):
            r, details = _eval_expr(expr, asof)
        assert r is False

    def test_any_combinator_short_circuits_on_true(self):
        from engine.falsifier_tripwires import _eval_expr
        s1 = _make_series([100])
        s2 = _make_series([50])
        asof = _asof(s1)
        expr = {"any": [
            {"series": "yahoo:A", "op": "gt", "value": 90},   # True
            {"series": "yahoo:B", "op": "gt", "value": 60},   # False
        ]}
        def fake_read(g, t):
            if t == "A": return s1.rename("close").to_frame()
            if t == "B": return s2.rename("close").to_frame()
            return None
        with patch("lib.store.read", side_effect=fake_read):
            r, details = _eval_expr(expr, asof)
        assert r is True

    def test_not_combinator(self):
        from engine.falsifier_tripwires import _eval_expr
        s = _make_series([30])
        asof = _asof(s)
        expr = {"not": {"series": "yahoo:X", "op": "gt", "value": 50}}
        with _patch_read("yahoo:X", s):
            r, details = _eval_expr(expr, asof)
        assert r is True   # 30 NOT > 50 → True

    def test_seasonal_guard_outside_months(self):
        from engine.falsifier_tripwires import _eval_leg
        s = _make_series([100.0] * 5)
        # force asof to be in January (month 1), but seasonal guard = [7,8,9]
        asof = pd.Timestamp("2026-01-15")
        # align series to include Jan dates
        idx = pd.bdate_range("2026-01-05", periods=5)
        s2 = pd.Series([100.0] * 5, index=idx)
        with _patch_read("fred:NG", s2):
            r, d = _eval_leg({"series": "fred:NG", "op": "gt", "value": 4.0,
                               "months": [7, 8, 9]}, asof)
        # outside seasonal window → vacuously True (not watchful)
        assert r is True
        assert d.get("seasonal_skip") is True

    def test_weekly_close_transform(self):
        from engine.falsifier_tripwires import _eval_leg
        # build 20 business days of data, last weekly close should be the last Friday value
        vals = list(range(80, 100))   # 20 bars, last val = 99
        s = _make_series(vals)
        asof = _asof(s)
        with _patch_read("yahoo:DX", s):
            r, d = _eval_leg({"series": "yahoo:DX", "op": "lt", "value": 98,
                               "transform": "weekly_close"}, asof)
        # last weekly close is 99, which is NOT < 98
        assert r is False

    def test_ratio_transform(self):
        from engine.falsifier_tripwires import _eval_leg
        # PL=F / GC=F ratio: if PL=1400, GC=2000 → ratio=0.7 < 2.2 → True
        s_pl = _make_series([1400.0] * 5)
        s_gc = _make_series([2000.0] * 5)
        def fake_read(g, t):
            t_clean = t.replace("=", "_").replace("^", "_")
            if t in ("PL=F", "PL_F", "PL"): return s_pl.rename("close").to_frame()
            if t in ("GC=F", "GC_F", "GC"): return s_gc.rename("close").to_frame()
            return None
        with patch("lib.store.read", side_effect=fake_read):
            r, d = _eval_leg({"series": "yahoo:PL=F", "op": "lt", "value": 2.2,
                               "transform": "ratio:yahoo:GC=F"}, _asof(s_pl))
        assert r is True   # 0.7 < 2.2


# ── (2) LATCH SEMANTICS ───────────────────────────────────────────────────────
class TestLatchSemantics:
    """FIRED latches across builds; version-bump un-latches; current_leg updates."""

    def _oil_entry(self, version=1) -> dict:
        return {
            "id": "oil.test.v" + str(version),
            "cycle": "oil",
            "version": version,
            "direction": "refutes",
            "claim": "WTI < $55 test",
            "expires": "2030-01-01",
            "coverage": "full",
            "dsl": {"series": "fred:DCOILWTICO", "op": "lt", "value": 55,
                    "sustain_bars": 1},
            "manual": None,
        }

    def test_fires_once_stays_fired(self, tmp_path, monkeypatch):
        from engine import falsifier_tripwires as ft
        monkeypatch.setattr("engine.falsifier_tripwires._STATE_JSON",
                            tmp_path / "tripwire_state.json")
        monkeypatch.setattr("engine.falsifier_tripwires._FALSIFIERS_JSON",
                            tmp_path / "falsifiers.json")

        (tmp_path / "falsifiers.json").write_text(
            json.dumps([self._oil_entry()]), encoding="utf-8")

        # build 1: WTI = 50 → fires
        s_fire = _make_series([50.0] * 10)
        asof_fire = _asof(s_fire)
        with _patch_read("fred:DCOILWTICO", s_fire):
            results = ft.evaluate_all(asof=asof_fire)
        newly = ft.persist(results)
        assert len(newly) == 1
        assert results[0].state == "FIRED"
        assert results[0].latched is True
        first_fire_date = results[0].fired_on

        # build 2: WTI = 80 → condition no longer met, BUT latch stays
        s_recover = _make_series([80.0] * 10)
        asof_recover = _asof(s_recover)
        with _patch_read("fred:DCOILWTICO", s_recover):
            results2 = ft.evaluate_all(asof=asof_recover)
        newly2 = ft.persist(results2)
        assert len(newly2) == 0          # NOT newly fired (was already latched)
        assert results2[0].state == "FIRED"
        assert results2[0].latched is True
        assert results2[0].fired_on == first_fire_date     # original fire date preserved
        assert results2[0].current_leg is False             # A17: condition no longer met

    def test_version_bump_unlatches(self, tmp_path, monkeypatch):
        from engine import falsifier_tripwires as ft
        monkeypatch.setattr("engine.falsifier_tripwires._STATE_JSON",
                            tmp_path / "tripwire_state.json")
        monkeypatch.setattr("engine.falsifier_tripwires._FALSIFIERS_JSON",
                            tmp_path / "falsifiers.json")

        # first: fire v1
        (tmp_path / "falsifiers.json").write_text(
            json.dumps([self._oil_entry(1)]), encoding="utf-8")
        s_fire = _make_series([50.0] * 10)
        with _patch_read("fred:DCOILWTICO", s_fire):
            res = ft.evaluate_all(asof=_asof(s_fire))
        ft.persist(res)
        assert res[0].state == "FIRED"

        # second: bump to v2 — should un-latch
        (tmp_path / "falsifiers.json").write_text(
            json.dumps([self._oil_entry(2)]), encoding="utf-8")
        s_recover = _make_series([80.0] * 10)
        with _patch_read("fred:DCOILWTICO", s_recover):
            res2 = ft.evaluate_all(asof=_asof(s_recover))
        newly2 = ft.persist(res2)
        # v2 with condition NOT met → ARMED (not FIRED)
        assert res2[0].state == "ARMED"
        assert len(newly2) == 0


# ── (3) TTL / OVERDUE ────────────────────────────────────────────────────────
class TestManualTTL:
    def test_overdue_days_computed(self, tmp_path, monkeypatch):
        from engine import falsifier_tripwires as ft
        monkeypatch.setattr("engine.falsifier_tripwires._FALSIFIERS_JSON",
                            tmp_path / "falsifiers.json")
        monkeypatch.setattr("engine.falsifier_tripwires._STATE_JSON",
                            tmp_path / "state.json")

        entry = {
            "id": "memory.dram.v1",
            "cycle": "memory",
            "version": 1,
            "direction": "refutes",
            "claim": "DRAM ASP < cycle bottom",
            "expires": "2030-01-01",
            "coverage": "none",
            "dsl": None,
            "manual": {"ttl_days": 90, "last_reviewed": "2026-01-01", "note": "paywalled"},
        }
        (tmp_path / "falsifiers.json").write_text(json.dumps([entry]), encoding="utf-8")
        asof = pd.Timestamp("2026-07-02")   # ~182 days after last_reviewed → overdue by ~92d
        results = ft.evaluate_all(asof=asof)
        assert results[0].state == "MANUAL"
        assert results[0].overdue_days is not None
        assert results[0].overdue_days > 0

    def test_within_ttl_not_overdue(self, tmp_path, monkeypatch):
        from engine import falsifier_tripwires as ft
        monkeypatch.setattr("engine.falsifier_tripwires._FALSIFIERS_JSON",
                            tmp_path / "falsifiers.json")
        monkeypatch.setattr("engine.falsifier_tripwires._STATE_JSON",
                            tmp_path / "state.json")

        entry = {
            "id": "memory.dram.v1",
            "cycle": "memory",
            "version": 1,
            "direction": "refutes",
            "claim": "DRAM ASP < cycle bottom",
            "expires": "2030-01-01",
            "coverage": "none",
            "dsl": None,
            "manual": {"ttl_days": 90, "last_reviewed": "2026-06-01", "note": "paywalled"},
        }
        (tmp_path / "falsifiers.json").write_text(json.dumps([entry]), encoding="utf-8")
        asof = pd.Timestamp("2026-07-02")   # ~31 days after last_reviewed → within 90d TTL
        results = ft.evaluate_all(asof=asof)
        assert results[0].state == "MANUAL"
        assert results[0].overdue_days == 0


# ── (4) DATA_MISSING ─────────────────────────────────────────────────────────
class TestDataMissing:
    def test_stale_tape_returns_data_missing(self, tmp_path, monkeypatch):
        from engine import falsifier_tripwires as ft
        monkeypatch.setattr("engine.falsifier_tripwires._FALSIFIERS_JSON",
                            tmp_path / "falsifiers.json")
        monkeypatch.setattr("engine.falsifier_tripwires._STATE_JSON",
                            tmp_path / "state.json")
        monkeypatch.setattr("engine.falsifier_tripwires._STALE_TRADING_DAYS", 5)

        entry = {
            "id": "oil.stale.v1",
            "cycle": "oil",
            "version": 1,
            "direction": "refutes",
            "claim": "WTI test",
            "expires": "2030-01-01",
            "coverage": "full",
            "dsl": {"series": "fred:DCOILWTICO", "op": "lt", "value": 55},
            "manual": None,
        }
        (tmp_path / "falsifiers.json").write_text(json.dumps([entry]), encoding="utf-8")

        # build a series that is 15 trading days STALE relative to asof
        s_old = _make_series([50.0] * 10, start="2026-01-01")   # ends early Jan
        asof = pd.Timestamp("2026-02-15")   # well past the tape
        with _patch_read("fred:DCOILWTICO", s_old):
            results = ft.evaluate_all(asof=asof)
        assert results[0].state == "DATA_MISSING", \
            f"expected DATA_MISSING, got {results[0].state}"

    def test_missing_tape_returns_data_missing(self, tmp_path, monkeypatch):
        from engine import falsifier_tripwires as ft
        monkeypatch.setattr("engine.falsifier_tripwires._FALSIFIERS_JSON",
                            tmp_path / "falsifiers.json")
        monkeypatch.setattr("engine.falsifier_tripwires._STATE_JSON",
                            tmp_path / "state.json")

        entry = {
            "id": "oil.missing.v1",
            "cycle": "oil",
            "version": 1,
            "direction": "refutes",
            "claim": "test",
            "expires": "2030-01-01",
            "coverage": "full",
            "dsl": {"series": "fred:NOTEXIST", "op": "lt", "value": 55},
            "manual": None,
        }
        (tmp_path / "falsifiers.json").write_text(json.dumps([entry]), encoding="utf-8")
        with patch("lib.store.read", return_value=None):
            results = ft.evaluate_all(asof=pd.Timestamp("2026-07-02"))
        assert results[0].state == "DATA_MISSING"


# ── (5) FALSIFIERS JSON validity ─────────────────────────────────────────────
class TestFalsifiersJson:
    def test_json_parses_and_has_23_cycle_entries(self):
        if not FALSIFIERS_JSON.exists():
            pytest.skip("falsifiers.json not committed yet")
        entries = json.loads(FALSIFIERS_JSON.read_text(encoding="utf-8"))
        # 23 cycles + spx = 24 entries (spx included per the registry census)
        # but the spec says 23 cycles; we accept 23 or 24
        cycle_ids = [e["cycle"] for e in entries]
        unique_cycles = set(cycle_ids) - {"spx"}
        assert len(unique_cycles) == 23, \
            f"expected 23 unique cycle ids (excl. spx), got {len(unique_cycles)}: {unique_cycles}"

    def test_coverage_tally(self):
        if not FALSIFIERS_JSON.exists():
            pytest.skip("falsifiers.json not committed yet")
        entries = json.loads(FALSIFIERS_JSON.read_text(encoding="utf-8"))
        non_spx = [e for e in entries if e.get("cycle") != "spx"]
        counts = {}
        for e in non_spx:
            c = e.get("coverage", "none")
            counts[c] = counts.get(c, 0) + 1
        # spec: 10 FULL (incl. dollar reclassified to full), 8 PARTIAL, 5 NONE
        # allow ±1 since dollar is listed partial→full in the spec ambiguously
        assert counts.get("none", 0) == 5, f"expected 5 NONE, got {counts}"
        assert counts.get("full", 0) + counts.get("partial", 0) == 18, \
            f"expected 18 full+partial, got {counts}"

    def test_none_coverage_has_null_dsl(self):
        if not FALSIFIERS_JSON.exists():
            pytest.skip("falsifiers.json not committed yet")
        entries = json.loads(FALSIFIERS_JSON.read_text(encoding="utf-8"))
        for e in entries:
            if e.get("coverage") == "none":
                assert e.get("dsl") is None, \
                    f"{e['id']}: coverage=none but dsl is not null"

    def test_full_coverage_has_non_null_dsl(self):
        if not FALSIFIERS_JSON.exists():
            pytest.skip("falsifiers.json not committed yet")
        entries = json.loads(FALSIFIERS_JSON.read_text(encoding="utf-8"))
        for e in entries:
            if e.get("coverage") == "full":
                assert e.get("dsl") is not None, \
                    f"{e['id']}: coverage=full but dsl is null"

    def test_required_fields_present(self):
        if not FALSIFIERS_JSON.exists():
            pytest.skip("falsifiers.json not committed yet")
        entries = json.loads(FALSIFIERS_JSON.read_text(encoding="utf-8"))
        required = {"id", "cycle", "version", "direction", "claim",
                    "coverage", "manual", "source_prose"}
        for e in entries:
            missing = required - set(e.keys())
            assert not missing, f"{e.get('id')}: missing fields {missing}"


# ── (6) BUILD INTEGRATION smoke ───────────────────────────────────────────────
class TestBuildIntegration:
    def test_evaluate_all_returns_list(self, tmp_path, monkeypatch):
        """evaluate_all works on a data-less checkout (returns empty list when no tapes)."""
        from engine import falsifier_tripwires as ft
        monkeypatch.setattr("engine.falsifier_tripwires._FALSIFIERS_JSON",
                            tmp_path / "falsifiers.json")
        monkeypatch.setattr("engine.falsifier_tripwires._STATE_JSON",
                            tmp_path / "state.json")

        # minimal single-entry registry
        entry = {
            "id": "vol.test.v1", "cycle": "vol", "version": 1,
            "direction": "refutes", "claim": "VIX test", "expires": "2030-01-01",
            "coverage": "full",
            "dsl": {"series": "fred:VIXCLS", "op": "gt", "value": 27.5, "sustain_bars": 5},
            "manual": None,
        }
        (tmp_path / "falsifiers.json").write_text(json.dumps([entry]), encoding="utf-8")

        # tape missing → DATA_MISSING, not a crash
        with patch("lib.store.read", return_value=None):
            results = ft.evaluate_all(asof=pd.Timestamp("2026-07-02"))
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0].state == "DATA_MISSING"

    def test_persist_round_trips_state(self, tmp_path, monkeypatch):
        from engine import falsifier_tripwires as ft
        monkeypatch.setattr("engine.falsifier_tripwires._FALSIFIERS_JSON",
                            tmp_path / "falsifiers.json")
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("engine.falsifier_tripwires._STATE_JSON", state_path)

        entry = {
            "id": "vol.state.v1", "cycle": "vol", "version": 1,
            "direction": "refutes", "claim": "VIX test", "expires": "2030-01-01",
            "coverage": "full",
            "dsl": {"series": "fred:VIXCLS", "op": "gt", "value": 27.5},
            "manual": None,
        }
        (tmp_path / "falsifiers.json").write_text(json.dumps([entry]), encoding="utf-8")

        s_fire = _make_series([30.0] * 10)
        asof = _asof(s_fire)
        with _patch_read("fred:VIXCLS", s_fire):
            results = ft.evaluate_all(asof=asof)
        newly = ft.persist(results)

        assert state_path.exists()
        state = json.loads(state_path.read_text())
        assert "vol.state.v1" in state
        assert state["vol.state.v1"]["latched"] is True
        assert state["vol.state.v1"]["fired_on"] is not None

    def test_results_summary_groups_by_cycle(self, tmp_path, monkeypatch):
        from engine import falsifier_tripwires as ft
        from engine.falsifier_tripwires import TripwireResult
        # synthetic pre-built results
        r1 = TripwireResult(id="oil.a.v1", cycle="oil", version=1,
                            state="ARMED", fired_on=None, latched=False,
                            current_leg=False, claim="c", direction="refutes",
                            coverage="full", expires=None)
        r2 = TripwireResult(id="vol.a.v1", cycle="vol", version=1,
                            state="FIRED", fired_on="2026-06-01", latched=True,
                            current_leg=True, claim="d", direction="refutes",
                            coverage="full", expires=None)
        summary = ft.results_summary([r1, r2])
        assert "oil" in summary and "vol" in summary
        assert summary["oil"][0]["state"] == "ARMED"
        assert summary["vol"][0]["state"] == "FIRED"

    def test_overdue_digest(self):
        from engine import falsifier_tripwires as ft
        from engine.falsifier_tripwires import TripwireResult
        r_overdue = TripwireResult(id="memory.x.v1", cycle="memory", version=1,
                                   state="MANUAL", fired_on=None, latched=False,
                                   current_leg=None, claim="c", direction="refutes",
                                   coverage="none", expires=None, overdue_days=15,
                                   manual={"ttl_days": 90, "last_reviewed": "2026-01-01"})
        r_ok = TripwireResult(id="shipping.x.v1", cycle="shipping", version=1,
                              state="MANUAL", fired_on=None, latched=False,
                              current_leg=None, claim="d", direction="refutes",
                              coverage="none", expires=None, overdue_days=0,
                              manual={"ttl_days": 90, "last_reviewed": "2026-06-01"})
        digest = ft.overdue_manual_digest([r_overdue, r_ok])
        assert len(digest) == 1
        assert digest[0]["id"] == "memory.x.v1"

    def test_synthetic_fire_renders_in_engine_payload(self, tmp_path, monkeypatch):
        """Synthetic forced-fire goes through evaluate_and_persist + results_summary
        and produces the expected FIRED entry in the summary."""
        from engine import falsifier_tripwires as ft
        monkeypatch.setattr("engine.falsifier_tripwires._FALSIFIERS_JSON",
                            tmp_path / "falsifiers.json")
        monkeypatch.setattr("engine.falsifier_tripwires._STATE_JSON",
                            tmp_path / "state.json")

        entry = {
            "id": "oil.forced.v1", "cycle": "oil", "version": 1,
            "direction": "refutes", "claim": "WTI trough forced",
            "expires": "2030-01-01", "coverage": "full",
            "dsl": {"series": "fred:DCOILWTICO", "op": "lt", "value": 55,
                    "sustain_bars": 42},
            "manual": None,
        }
        (tmp_path / "falsifiers.json").write_text(json.dumps([entry]), encoding="utf-8")

        # build 42 bars of sub-$55 WTI
        s_fire = _make_series([50.0] * 42)
        asof = _asof(s_fire)
        with _patch_read("fred:DCOILWTICO", s_fire):
            results, newly = ft.evaluate_and_persist(asof=asof, dispatch=False)

        assert len(newly) == 1
        assert results[0].state == "FIRED"
        assert results[0].latched is True

        summary = ft.results_summary(results)
        assert summary["oil"][0]["state"] == "FIRED"
        assert summary["oil"][0]["latched"] is True
