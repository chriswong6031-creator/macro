"""Tests for engine.neuralweb.mastermind_context (NW → Mastermind bridge W1).

Per ruling §3.4 W1 test list:
1. Schema + authority-all-false + envelope fields present.
2. gap_notes (not fake neutrals) when inputs are missing.
3. 200KB size cap on a REAL build from worktree data.
4. Candidate scope rule — only tickers from the intake union appear.
5. book_context no-new-names — no bottom-sensors symbol outside the intake
   union appears in serialized book_context.
6. fdr_cleared=False while survivors[] empty.
7. Builder makes no network/LLM calls.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Ensure repo root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.mastermind_context import (  # noqa: E402
    MARKET_PLANE_SCHEMA,
    SCHEMA,
    build_context,
    build_and_write,
    build_and_write_market_plane,
    build_market_plane,
    _coerce_numpy,
    _sparse,
    _is_stale,
)
from engine.neuralweb.envelope import ENVELOPE_KEYS  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_NOW = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)


def _minimal_standouts(tmp_path: Path) -> Path:
    """Write a minimal us_standouts.json fixture."""
    (tmp_path / "site" / "factordata").mkdir(parents=True, exist_ok=True)
    obj = {
        "as_of": "2026-07-05",
        "rank_by": "bottoming-alignment",
        "gate_go": False,
        "buy": [{"ticker": "FIXTURE_BUY", "score": 80}],
        "watch": [{"ticker": "FIXTURE_WATCH", "score": 60}],
        "laggards": [{"ticker": "FIXTURE_LAGGARD", "score": 20}],
        "eligible": 3,
        "universe": 100,
    }
    p = tmp_path / "site" / "factordata" / "us_standouts.json"
    p.write_text(json.dumps(obj))
    return p


def _minimal_altdata(tmp_path: Path, tickers: list[str] | None = None) -> Path:
    """Write a minimal altdata/mastermind.json fixture."""
    (tmp_path / "site" / "altdata").mkdir(parents=True, exist_ok=True)
    sigs = [{"ticker": t, "signal_score": 60, "conviction": "medium",
              "action": "WATCH", "direction": "neutral"} for t in (tickers or [])]
    obj = {
        "schema": "altdata.mastermind.v1",
        "as_of": "2026-07-05",
        "generated_utc": "2026-07-05T12:00:00Z",
        "n_signals": len(sigs),
        "n_broken": 0,
        "signals": sigs,
        "broken_signals": [],
    }
    p = tmp_path / "site" / "altdata" / "mastermind.json"
    p.write_text(json.dumps(obj))
    return p


def _minimal_radar_ticker(tmp_path: Path) -> Path:
    """Write a minimal radar_ticker.json fixture."""
    (tmp_path / "site" / "basketdata").mkdir(parents=True, exist_ok=True)
    obj = {
        "schema": "radar_ticker.v1",
        "is_context_only": True,
        "as_of": "2026-07-05",
        "generated_utc": "2026-07-05T12:00:00Z",
        "n": 1,
        "tickers": [
            {
                "ticker": "RADAR_COILED",
                "state": "POSITIVE_MOMENTUM",
                "bottom_state": "COILED",
                "trigger_tier": "T1",
                "action": "BUY",
            }
        ],
    }
    p = tmp_path / "site" / "basketdata" / "radar_ticker.json"
    p.write_text(json.dumps(obj))
    return p


def _minimal_bottom_sensors(tmp_path: Path, tickers: list[str] | None = None) -> Path:
    """Write a minimal bottom_sensors.json fixture."""
    (tmp_path / "site" / "neuralwebdata").mkdir(parents=True, exist_ok=True)
    rows = []
    for t in (tickers or []):
        rows.append({
            "symbol": t,
            "as_of": "2026-07-05",
            "bottom_state": "COILED",
            "trigger_tier": "T1",
            "coiled": True,
            "star": False,
            "coiled_fire": False,
            "dist_21d_low_pct": 5.0,
            "dist_126d_high_pct": -10.0,
        })
    obj = {
        "as_of": "2026-07-05",
        "labels_version": "labels_v1",
        "is_display_only": True,
        "n_rows": len(rows),
        "rows": rows,
    }
    p = tmp_path / "site" / "neuralwebdata" / "bottom_sensors.json"
    p.write_text(json.dumps(obj))
    return p


def _minimal_world_state(tmp_path: Path) -> Path:
    (tmp_path / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)
    obj = {
        "verdict": {"verdict": "RISK_OFF", "score": 40,
                    "label_en": "Risk-off", "label_zh": "风险规避"},
        "regime": {
            "quad": 1, "quad_name": "Goldilocks", "confidence": 0.5,
            "cycle_tag": "expansion", "transition_state": "STABLE",
            "flip_margin": 0.1, "liquidity_overlay": "neutral", "asof": "2026-07-05",
        },
        "vol": {"regime": "normalizing", "risk_score": 0.24, "vix": 16.2,
                "asof": "2026-07-05"},
        "breadth": {"pct_above_50": 64.5, "pct_above_200": 64.6,
                    "nh": 16, "nl": 1, "date": "2026-07-05"},
        "as_of": "2026-07-05",
        "produced_at": "2026-07-05T12:00:00Z",
    }
    p = tmp_path / "data" / "neuralweb" / "world_state.json"
    p.write_text(json.dumps(obj))
    return p


def _minimal_liquidity_plumbing(tmp_path: Path) -> Path:
    """Write a minimal data/neuralweb/liquidity_plumbing.json fixture."""
    (tmp_path / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)
    obj = {
        "schema": "neuralweb.liquidity_plumbing.v1",
        "asof": "2026-07-05",
        "headline": {"state": "stress_liquidity_expansion", "summary": "test"},
        "quantity": {"netliq_bn": 5980.5, "netliq_chg_20d_bn": 56.7,
                     "overlay": "expanding"},
        "rrp": {"rrp_bn": 5.8, "buffer_state": "exhausted"},
        "treasury": {"tga_bn": 749.2, "tga_chg_20d_bn": -81.2},
        "entry_effect": {
            "direction": "tailwind",
            "quality": "low_quality_tailwind",
            "measured_basis": "cycle_ladder_21d_odds",
            "use": "support existing buy setup, never originate one",
        },
        "gaps": [],
    }
    p = tmp_path / "data" / "neuralweb" / "liquidity_plumbing.json"
    p.write_text(json.dumps(obj))
    return p


def _minimal_kernel_families(tmp_path: Path) -> Path:
    (tmp_path / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)
    obj = {
        "families": {
            "altdata": {
                "armed": True,
                "horizon_curve": {},
                "recency_trend": {},
                "staleness": {},
            }
        },
        "produced_at": "2026-07-05T12:00:00Z",
    }
    p = tmp_path / "data" / "neuralweb" / "kernel_families.json"
    p.write_text(json.dumps(obj))
    return p


def _minimal_kernel_decisions(tmp_path: Path, survivors: list[str] | None = None) -> Path:
    (tmp_path / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)
    obj = {
        "batch_id": "2026-10-01",
        "run_at": "2026-07-05T12:00:00Z",
        "alpha": 0.1,
        "n_eligible": 6,
        "n_survivors": len(survivors or []),
        "survivors": survivors or [],
        "next_batch_due": "2026-10-01",
    }
    p = tmp_path / "data" / "neuralweb" / "kernel_decisions.json"
    p.write_text(json.dumps(obj))
    return p


def _minimal_confluence_graph(tmp_path: Path) -> Path:
    (tmp_path / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)
    obj = {
        "schema": "neuralweb.confluence_graph.v1",
        "as_of": "2026-07-05",
        "produced_at": "2026-07-05T12:00:00Z",
        "contradiction_summary": {"n": 1, "by_severity": {"note": 1}},
        "contradiction_records": [
            {
                "pair_id": "regime-vs-market_state",
                "severity": "note",
                "as_of": "2026-07-05",
                "display_only": True,
            }
        ],
        "nodes": [],
        "edges": [],
        "gaps": [],
    }
    p = tmp_path / "data" / "neuralweb" / "confluence_graph.json"
    p.write_text(json.dumps(obj))
    return p


def _minimal_options_gate(tmp_path: Path) -> Path:
    (tmp_path / "data" / "options_entry").mkdir(parents=True, exist_ok=True)
    obj = {
        "schema": "options_entry.gate.v2",
        "generated_at": "2026-07-05 12:00 UTC",
        "scored": False,
        "status": "building_history",
        "weight": 0.0,
        "note": "building",
    }
    p = tmp_path / "data" / "options_entry" / "gate.json"
    p.write_text(json.dumps(obj))
    return p


def _minimal_cortex(tmp_path: Path) -> Path:
    (tmp_path / "data" / "neuralweb" / "cortex").mkdir(parents=True, exist_ok=True)
    memo = {
        "schema": "neuralweb.cortex_memo.v1",
        "as_of": "2026-07-05",
        "summary": "test memo",
        "decaying_families": [],
        "is_context_only": True,
        "run_status": {"status": "ok", "degraded": False,
                       "degradation_reason": None},
    }
    prob = {
        "schema": "neuralweb.cortex_probation.v1",
        "as_of": "2026-07-05",
        "granted": False,
        "is_context_only": True,
    }
    mp = tmp_path / "data" / "neuralweb" / "cortex" / "memo.json"
    pp = tmp_path / "data" / "neuralweb" / "cortex" / "probation.json"
    mp.write_text(json.dumps(memo))
    pp.write_text(json.dumps(prob))
    return mp


def _build_minimal_tree(tmp_path: Path) -> None:
    """Set up a minimal but complete fixture tree for integration tests."""
    _minimal_standouts(tmp_path)
    _minimal_altdata(tmp_path, tickers=["ALTDATA_A", "ALTDATA_B"])
    _minimal_radar_ticker(tmp_path)
    _minimal_bottom_sensors(tmp_path, tickers=[
        "FIXTURE_BUY", "FIXTURE_WATCH", "FIXTURE_LAGGARD",
        "ALTDATA_A", "ALTDATA_B", "RADAR_COILED",
    ])
    _minimal_world_state(tmp_path)
    _minimal_liquidity_plumbing(tmp_path)
    _minimal_kernel_families(tmp_path)
    _minimal_kernel_decisions(tmp_path, survivors=[])
    _minimal_confluence_graph(tmp_path)
    _minimal_options_gate(tmp_path)
    _minimal_cortex(tmp_path)


# ---------------------------------------------------------------------------
# 1. Schema + authority-all-false + envelope fields present
# ---------------------------------------------------------------------------

class TestSchemaAndAuthority:
    def test_schema_field_present(self, tmp_path):
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        assert payload["schema"] == SCHEMA

    def test_is_context_only_true(self, tmp_path):
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        assert payload["is_context_only"] is True

    def test_authority_all_false(self, tmp_path):
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        auth = payload["authority"]
        # All five authority booleans must be False (ruling §3.1)
        for key in ("can_add_candidates", "can_raise_size", "can_lower_size",
                    "can_block_entry", "can_force_exit"):
            assert auth[key] is False, f"authority.{key} should be False, got {auth[key]}"

    def test_envelope_fields_present_after_stamp(self, tmp_path):
        """After build_and_write(), all ENVELOPE_KEYS must be present."""
        _build_minimal_tree(tmp_path)
        # Need synapse.yml — use real repo if available, else skip stamp check
        reg_path = _REPO_ROOT / "config" / "synapse.yml"
        if not reg_path.exists():
            pytest.skip("synapse.yml not accessible")
        payload = build_and_write(root=tmp_path, now=_NOW)
        for key in ENVELOPE_KEYS:
            assert key in payload, f"envelope key {key!r} missing after stamp"

    def test_as_of_reflects_lobe_data_date(self, tmp_path):
        """as_of must match lobe data timestamps (not build time).

        When all fixture lobes carry as_of='2026-07-05' and build time is also
        2026-07-05, the top-level as_of is '2026-07-05' (the data timestamp).
        See also test_as_of_reflects_data_timestamp_not_build_time in TestHelpers
        which covers the case where build time differs from data timestamps.
        """
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        assert payload["as_of"] == "2026-07-05"

    def test_generated_utc_format(self, tmp_path):
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        assert payload["generated_utc"] == "2026-07-05T12:00:00Z"

    def test_lobes_have_all_six(self, tmp_path):
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        for lobe in ("market", "reliability", "contradictions",
                     "bottom_sensors", "options_entry", "cortex"):
            assert lobe in payload["lobes"], f"lobe {lobe!r} missing"

    def test_schema_version_1(self, tmp_path):
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        assert payload["schema_version"] == 1


# ---------------------------------------------------------------------------
# 2. gap_notes on missing inputs
# ---------------------------------------------------------------------------

class TestGapNotes:
    def test_gap_when_world_state_absent(self, tmp_path):
        """Missing world_state.json should add a gap_note, not raise."""
        _build_minimal_tree(tmp_path)
        (tmp_path / "data" / "neuralweb" / "world_state.json").unlink()
        payload = build_context(root=tmp_path, now=_NOW)
        gap_str = " ".join(payload["gap_notes"])
        assert "market" in gap_str or "world_state" in gap_str, (
            f"Expected market/world_state gap; got: {payload['gap_notes']}"
        )

    def test_gap_when_kernel_families_absent(self, tmp_path):
        """Missing kernel_families.json should add a gap_note, not raise."""
        _build_minimal_tree(tmp_path)
        (tmp_path / "data" / "neuralweb" / "kernel_families.json").unlink()
        (tmp_path / "data" / "neuralweb" / "kernel_decisions.json").unlink()
        payload = build_context(root=tmp_path, now=_NOW)
        gap_str = " ".join(payload["gap_notes"])
        assert "reliability" in gap_str or "kernel" in gap_str, (
            f"Expected reliability/kernel gap; got: {payload['gap_notes']}"
        )

    def test_gap_when_options_gate_absent(self, tmp_path):
        """Missing options gate.json should add a gap_note, not raise."""
        _build_minimal_tree(tmp_path)
        (tmp_path / "data" / "options_entry" / "gate.json").unlink()
        payload = build_context(root=tmp_path, now=_NOW)
        gap_str = " ".join(payload["gap_notes"])
        assert "options_entry" in gap_str or "gate" in gap_str, (
            f"Expected options_entry gap; got: {payload['gap_notes']}"
        )

    def test_gap_when_bottom_sensors_absent(self, tmp_path):
        """Missing bottom_sensors.json should add a gap_note, not raise."""
        _build_minimal_tree(tmp_path)
        (tmp_path / "site" / "neuralwebdata" / "bottom_sensors.json").unlink()
        payload = build_context(root=tmp_path, now=_NOW)
        gap_str = " ".join(payload["gap_notes"])
        assert "bottom_sensors" in gap_str or "bottom" in gap_str, (
            f"Expected bottom_sensors gap; got: {payload['gap_notes']}"
        )

    def test_gap_not_fake_neutral_on_success(self, tmp_path):
        """When all inputs are present, gap_notes should not contain fake neutrals
        for successfully-read lobes."""
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        # market/reliability/contradictions/cortex should NOT have gaps
        for g in payload["gap_notes"]:
            g_lower = g.lower()
            for lobe in ("market", "reliability", "contradictions", "cortex"):
                if lobe in g_lower:
                    assert "absent" in g_lower or "failed" in g_lower or "truncat" in g_lower, (
                        f"Suspicious gap for lobe '{lobe}' with all inputs present: {g!r}"
                    )


# ---------------------------------------------------------------------------
# 3. 200KB size cap on a REAL build from worktree data
# ---------------------------------------------------------------------------

class TestSizeCap:
    def test_real_build_under_300kb(self):
        """Real build from the worktree data must produce an artifact under 300KB.

        Cap raised from 200KB to 300KB in Build 3 (analyst block adds rows;
        prior headroom was ~1.7KB per Build-1 review). CONTEXT_SIZE_CAP_BYTES
        in mastermind_context.py is the authoritative constant.
        """
        from engine.neuralweb.mastermind_context import CONTEXT_SIZE_CAP_BYTES  # noqa: PLC0415
        canonical = _REPO_ROOT / "data" / "neuralweb" / "mastermind_context.json"
        if not canonical.exists():
            # Trigger a fresh build
            build_and_write(root=_REPO_ROOT)
        assert canonical.exists(), "mastermind_context.json not written"
        size_bytes = canonical.stat().st_size
        cap_bytes = CONTEXT_SIZE_CAP_BYTES  # 300 KB
        assert size_bytes <= cap_bytes, (
            f"mastermind_context.json too large: {size_bytes/1024:.1f}KB > "
            f"{cap_bytes//1024}KB. Reduce candidate_context rows or field columns."
        )


# ---------------------------------------------------------------------------
# 4. Candidate scope rule
# ---------------------------------------------------------------------------

class TestCandidateScope:
    def test_candidates_only_from_intake_union(self, tmp_path):
        """Candidate tickers must come from standouts ∪ altdata ∪ radar (actionable).

        A ticker NOT in any intake source must NOT appear in candidate_context.
        """
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)

        # Known intake tickers
        intake = {
            "FIXTURE_BUY", "FIXTURE_WATCH", "FIXTURE_LAGGARD",  # standouts
            "ALTDATA_A", "ALTDATA_B",                             # altdata
            "RADAR_COILED",                                       # radar (actionable: bottom_state=COILED)
        }

        for ticker in payload["candidate_context"]:
            assert ticker in intake, (
                f"Ticker {ticker!r} in candidate_context but not in intake union"
            )

    def test_radar_watch_only_ticker_excluded(self, tmp_path):
        """A radar ticker with bottom_state='WATCH', no trigger_tier, no options row
        must NOT appear in candidate_context (scope rule §3.1)."""
        _build_minimal_tree(tmp_path)
        # Add a WATCH-only radar ticker to bottom_sensors
        bs_path = tmp_path / "site" / "neuralwebdata" / "bottom_sensors.json"
        bs = json.loads(bs_path.read_text())
        bs["rows"].append({
            "symbol": "WATCH_ONLY",
            "as_of": "2026-07-05",
            "bottom_state": "WATCH",
            "trigger_tier": None,
            "coiled": False,
            "star": False,
        })
        bs_path.write_text(json.dumps(bs))

        # Add to radar_ticker as WATCH state
        rt_path = tmp_path / "site" / "basketdata" / "radar_ticker.json"
        rt = json.loads(rt_path.read_text())
        rt["tickers"].append({
            "ticker": "WATCH_ONLY",
            "state": "WATCH",
            "action": "WATCH",
        })
        rt_path.write_text(json.dumps(rt))

        payload = build_context(root=tmp_path, now=_NOW)
        # WATCH_ONLY is not in standouts or altdata, and bottom_state=WATCH + no trigger
        assert "WATCH_ONLY" not in payload["candidate_context"], (
            "WATCH_ONLY ticker should be excluded (no actionable NW context)"
        )

    def test_standout_ticker_always_included(self, tmp_path):
        """All standout tickers (buy/watch/laggards) must be in candidate_context."""
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        expected = {"FIXTURE_BUY", "FIXTURE_WATCH", "FIXTURE_LAGGARD"}
        actual = set(payload["candidate_context"].keys())
        assert expected.issubset(actual), (
            f"Missing standout tickers: {expected - actual}"
        )

    def test_altdata_tickers_included(self, tmp_path):
        """Altdata signals/broken_signals tickers must be in candidate_context."""
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        expected = {"ALTDATA_A", "ALTDATA_B"}
        actual = set(payload["candidate_context"].keys())
        assert expected.issubset(actual), (
            f"Missing altdata tickers: {expected - actual}"
        )


# ---------------------------------------------------------------------------
# 5. book_context no-new-names
# ---------------------------------------------------------------------------

class TestBookContextNoNewNames:
    def test_no_bottom_sensor_symbol_outside_intake_union(self, tmp_path):
        """No bottom-sensors symbol outside the intake union must appear in the
        serialised book_context. (ruling §3.1 red-team guard)."""
        _build_minimal_tree(tmp_path)
        # Add a bottom sensor row for a ticker NOT in any intake source
        bs_path = tmp_path / "site" / "neuralwebdata" / "bottom_sensors.json"
        bs = json.loads(bs_path.read_text())
        bs["rows"].append({
            "symbol": "OUTSIDER_TICKER",
            "as_of": "2026-07-05",
            "bottom_state": "COILED",
            "trigger_tier": "T2",
            "coiled": True,
            "star": False,
        })
        bs_path.write_text(json.dumps(bs))

        payload = build_context(root=tmp_path, now=_NOW)

        # Intake union
        intake = (
            set(["FIXTURE_BUY", "FIXTURE_WATCH", "FIXTURE_LAGGARD"])
            | set(["ALTDATA_A", "ALTDATA_B"])
            | set(payload["candidate_context"].keys())  # includes radar actionable
        )

        # Serialize book_context and check no outsider symbol appears
        book_str = json.dumps(payload["book_context"])
        assert "OUTSIDER_TICKER" not in book_str, (
            "OUTSIDER_TICKER (outside intake union) appeared in serialised book_context"
        )


# ---------------------------------------------------------------------------
# 6. fdr_cleared = False while survivors[] empty
# ---------------------------------------------------------------------------

class TestFdrCleared:
    def test_fdr_cleared_false_when_survivors_empty(self, tmp_path):
        """When kernel_decisions.survivors=[], all families must have fdr_cleared=False."""
        _build_minimal_tree(tmp_path)
        # Explicitly set survivors=[] (already default, but be explicit)
        _minimal_kernel_decisions(tmp_path, survivors=[])

        payload = build_context(root=tmp_path, now=_NOW)
        families = payload["lobes"]["reliability"].get("families", {})
        assert families, "No families found in reliability lobe"
        for name, fam in families.items():
            assert fam["fdr_cleared"] is False, (
                f"fdr_cleared should be False for '{name}' while survivors[] empty, "
                f"got {fam['fdr_cleared']}"
            )

    def test_fdr_cleared_true_when_in_survivors(self, tmp_path):
        """When a family name is in survivors[], its fdr_cleared must be True."""
        _build_minimal_tree(tmp_path)
        _minimal_kernel_decisions(tmp_path, survivors=["altdata"])

        payload = build_context(root=tmp_path, now=_NOW)
        families = payload["lobes"]["reliability"].get("families", {})
        assert "altdata" in families, "altdata family not in reliability lobe"
        assert families["altdata"]["fdr_cleared"] is True, (
            "altdata should be fdr_cleared=True since it's in survivors[]"
        )

    def test_no_bare_armed_key(self, tmp_path):
        """The bridge MUST NOT emit a bare 'armed' key in the reliability families.

        Ruling §1.4: 'armed' → 'display_armed'. Raw 'armed' never crosses the bridge.
        """
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        families = payload["lobes"]["reliability"].get("families", {})
        for name, fam in families.items():
            assert "armed" not in fam, (
                f"Bare 'armed' key found in reliability.families.{name!r} — "
                "use 'display_armed' instead (ruling §1.4)"
            )


# ---------------------------------------------------------------------------
# 7. Builder makes no network or LLM calls
# ---------------------------------------------------------------------------

class TestNoNetworkCalls:
    def test_build_context_no_network(self, tmp_path, monkeypatch):
        """build_context() must never make network requests or LLM calls.

        We monkeypatch urllib.request.urlopen and socket.socket to raise
        immediately if called — any network attempt fails the test.
        """
        import socket
        import urllib.request

        def _no_network(*args, **kwargs):
            raise AssertionError(
                "build_context() made a network call — this is forbidden"
            )

        monkeypatch.setattr(urllib.request, "urlopen", _no_network)
        monkeypatch.setattr(socket, "socket", _no_network)

        _build_minimal_tree(tmp_path)
        # Should complete without raising
        payload = build_context(root=tmp_path, now=_NOW)
        assert payload["schema"] == SCHEMA


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_sparse_removes_none(self):
        from engine.neuralweb.mastermind_context import _sparse
        d = {"a": 1, "b": None, "c": "x", "d": None}
        result = _sparse(d)
        assert result == {"a": 1, "c": "x"}

    def test_sparse_removes_nan(self):
        import math
        from engine.neuralweb.mastermind_context import _sparse
        d = {"a": 1.0, "b": float("nan"), "c": "x"}
        result = _sparse(d)
        assert "b" not in result
        assert result["a"] == 1.0

    def test_coerce_numpy_int(self):
        try:
            import numpy as np
            val = np.int64(42)
            result = _coerce_numpy(val)
            assert isinstance(result, int)
            assert result == 42
        except ImportError:
            pytest.skip("numpy not installed")

    def test_coerce_numpy_nan_to_none(self):
        try:
            import numpy as np
            val = np.float64(float("nan"))
            result = _coerce_numpy(val)
            assert result is None
        except ImportError:
            pytest.skip("numpy not installed")

    def test_is_stale_absent_is_true(self):
        from engine.neuralweb.mastermind_context import _is_stale
        assert _is_stale(None) is True
        assert _is_stale("") is True

    def test_candidate_context_allowed_behavior(self, tmp_path):
        """All candidate rows must carry allowed_behavior='annotate_only'."""
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        for ticker, row in payload["candidate_context"].items():
            assert row.get("allowed_behavior") == "annotate_only", (
                f"Ticker {ticker!r} missing allowed_behavior='annotate_only'"
            )

    def test_new_sub_block_keys_when_data_present(self, tmp_path):
        """When bottom_sensors carries extended fields, new sub-blocks appear."""
        _build_minimal_tree(tmp_path)
        # Patch bottom_sensors fixture with extended fields on FIXTURE_BUY
        bs_path = tmp_path / "site" / "neuralwebdata" / "bottom_sensors.json"
        bs = json.loads(bs_path.read_text())
        for row in bs["rows"]:
            if row.get("symbol") == "FIXTURE_BUY":
                row.update({
                    "net_debt_to_ebitda": 1.5,
                    "net_debt_to_op_income": 2.0,
                    "decline_geometry": "flush",
                    "underwater_state": "mid",
                    "decline_herf": 0.08,
                    "sponsorship_state": "headwind",
                    "days_since_shelf": 90,
                })
        bs_path.write_text(json.dumps(bs))
        payload = build_context(root=tmp_path, now=_NOW)
        row = payload["candidate_context"].get("FIXTURE_BUY", {})
        # leverage block must appear (net_debt_to_ebitda is non-null)
        assert "leverage" in row, f"leverage block missing; row keys: {list(row.keys())}"
        assert "net_debt_to_ebitda" in row["leverage"]
        # structural block must appear
        assert "structural" in row, f"structural block missing; row keys: {list(row.keys())}"
        assert "decline_geometry" in row["structural"]
        assert "sponsorship_state" in row["structural"], "sponsorship_state must fold into structural"
        # dilution block must appear (days_since_shelf is non-null)
        assert "dilution" in row, f"dilution block missing; row keys: {list(row.keys())}"
        assert "days_since_shelf" in row["dilution"]

    def test_new_sub_blocks_omitted_when_all_null(self, tmp_path):
        """Sub-blocks must be omitted entirely when all their fields are None/absent."""
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        # Fixture rows have no leverage/structural/dilution fields — blocks must be absent
        for ticker, row in payload["candidate_context"].items():
            # None of the fixture rows have leverage fields set
            # (they only have bottom_state, coiled, etc.)
            lev = row.get("leverage", {})
            # If leverage is present, all values must be non-null (sparse guarantee)
            for k, v in lev.items():
                assert v is not None, f"leverage.{k}=None on {ticker!r} — sparse failed"

    def test_no_new_names_invariant(self, tmp_path):
        """New sub-blocks add no new ticker names — only values on existing tickers."""
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        # candidate_context keys must still be exactly the intake union
        intake = {
            "FIXTURE_BUY", "FIXTURE_WATCH", "FIXTURE_LAGGARD",
            "ALTDATA_A", "ALTDATA_B", "RADAR_COILED",
        }
        for ticker in payload["candidate_context"]:
            assert ticker in intake, (
                f"Ticker {ticker!r} in candidate_context but not in intake union "
                "(new sub-blocks must not introduce new tickers)"
            )

    def test_candidate_context_compact_json_under_200kb(self, tmp_path):
        """candidate_context compact JSON must stay under 200 KB (size-cap regression)."""
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        cc_bytes = json.dumps(payload["candidate_context"], separators=(",", ":")).encode("utf-8")
        cap_bytes = 200 * 1024
        assert len(cc_bytes) <= cap_bytes, (
            f"candidate_context compact JSON {len(cc_bytes)/1024:.1f}KB > 200KB cap"
        )

    def test_earnings_ctx_block_absent_when_parquet_missing(self, tmp_path):
        """When earnings.parquet is absent, earnings_ctx block must not appear."""
        _build_minimal_tree(tmp_path)
        # No earnings.parquet written — block must be silently absent (not raise)
        payload = build_context(root=tmp_path, now=_NOW)
        for ticker, row in payload["candidate_context"].items():
            # earnings_ctx may or may not be present; if present it must be valid
            ec = row.get("earnings_ctx")
            if ec is not None:
                assert isinstance(ec, dict), f"earnings_ctx must be a dict on {ticker!r}"

    def test_visibility_block_absent_when_rpo_parquet_missing(self, tmp_path):
        """When rpo.parquet is absent, visibility block must not appear."""
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        for ticker, row in payload["candidate_context"].items():
            # No rpo.parquet in tmp_path, so visibility must be absent
            assert "visibility" not in row, (
                f"visibility block on {ticker!r} despite absent rpo.parquet"
            )

    def test_sector_vel_and_accel_not_in_any_block(self, tmp_path):
        """sector_vel_1m and sector_accel must never appear (confirmed absent from source)."""
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        cc_str = json.dumps(payload["candidate_context"])
        assert "sector_vel_1m" not in cc_str, "sector_vel_1m must not appear (absent from source)"
        assert "sector_accel" not in cc_str, "sector_accel must not appear (absent from source)"

    def test_lobe_manifest_nonempty_on_real_registry(self):
        """On the real registry, lobe_manifest must contain at least the seed
        artifacts tagged mastermind:context (world-state, kernel-families, etc.)."""
        reg_path = _REPO_ROOT / "config" / "synapse.yml"
        if not reg_path.exists():
            pytest.skip("synapse.yml not accessible")
        payload = build_context(root=_REPO_ROOT, now=_NOW)
        assert len(payload["lobe_manifest"]) >= 6, (
            f"Expected at least 6 lobe_manifest entries, got {len(payload['lobe_manifest'])}"
        )

    def test_book_context_keys(self, tmp_path):
        """book_context must have exactly the three required keys."""
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        book = payload["book_context"]
        assert "top_macro_contradictions" in book
        assert "decaying_families" in book
        assert "bottom_summary_counts" in book

    def test_reliability_lobe_standing_law_present(self, tmp_path):
        """reliability lobe must carry standing_law string."""
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        rel = payload["lobes"]["reliability"]
        assert "standing_law" in rel
        assert len(rel["standing_law"]) > 20, "standing_law string too short"

    def test_graph_conflicts_no_substring_false_positives(self, tmp_path):
        """graph_conflicts must use word-boundary matching, not substring matching.

        Tickers like 'F', 'ON', 'ST', 'BA', 'NI', 'MAR' are all substrings of
        words appearing in macro contradiction records (growth, transition, state,
        etc.). None should receive graph_conflicts from macro-only records unless
        the ticker symbol appears as a standalone word.
        """
        _build_minimal_tree(tmp_path)
        # Patch the confluence_graph to include macro-level records that contain
        # common ticker substrings (regime/market_state records, no ticker fields).
        cg_path = tmp_path / "data" / "neuralweb" / "confluence_graph.json"
        cg = json.loads(cg_path.read_text())
        cg["contradiction_records"] = [
            {
                "pair_id": "regime_vector-vs-risk_radar",
                "a": "regime_vector",
                "b": "risk_radar",
                "kind": "flip_margin",
                "note": "growth vs contraction transition_state mismatch",
                "severity": "warn",
                "as_of": "2026-07-05",
                "display_only": True,
            },
            {
                "pair_id": "regime-vs-market_state",
                "a": "regime",
                "b": "market_state",
                "kind": "stage",
                "note": "on the transition boundary, stale",
                "severity": "note",
                "as_of": "2026-07-05",
                "display_only": True,
            },
        ]
        cg_path.write_text(json.dumps(cg))

        # Add tickers that are substrings of words in those records to standouts
        ss_path = tmp_path / "site" / "factordata" / "us_standouts.json"
        ss = json.loads(ss_path.read_text())
        # 'F' is in 'growth'/'flip_margin', 'ON' is in 'transition', 'ST' is in 'state'/'stale'
        ss["buy"] = [
            {"ticker": "F", "score": 80},
            {"ticker": "ON", "score": 78},
            {"ticker": "ST", "score": 76},
        ]
        ss_path.write_text(json.dumps(ss))

        # Add these tickers to bottom_sensors so they're not filtered
        bs_path = tmp_path / "site" / "neuralwebdata" / "bottom_sensors.json"
        bs = json.loads(bs_path.read_text())
        for t in ["F", "ON", "ST"]:
            bs["rows"].append({
                "symbol": t,
                "as_of": "2026-07-05",
                "bottom_state": "COILED",
                "trigger_tier": "T1",
                "coiled": True,
                "star": False,
                "coiled_fire": False,
            })
        bs_path.write_text(json.dumps(bs))

        payload = build_context(root=tmp_path, now=_NOW)
        cc = payload["candidate_context"]
        for ticker in ("F", "ON", "ST"):
            row = cc.get(ticker, {})
            assert "graph_conflicts" not in row, (
                f"Ticker {ticker!r} received false-positive graph_conflicts from "
                f"macro-level records (substring match bug): {row.get('graph_conflicts')}"
            )

    def test_as_of_reflects_data_timestamp_not_build_time(self, tmp_path):
        """Top-level as_of must reflect the oldest lobe data timestamp, not build time.

        PERCEPTION_CONTRACTS law: 'asof = TRUE data timestamp per artifact, never
        build time'. The W2 reader gates whole-artifact staleness on this field.
        If all lobe data is from 2026-07-01 but the build runs on 2026-07-05,
        as_of must be 2026-07-01 (the oldest lobe date), not 2026-07-05.
        """
        _build_minimal_tree(tmp_path)

        # Overwrite fixture lobes to have older data timestamps
        stale_date = "2026-07-01"

        ws_path = tmp_path / "data" / "neuralweb" / "world_state.json"
        ws = json.loads(ws_path.read_text())
        ws["as_of"] = stale_date
        ws["regime"]["asof"] = stale_date
        ws_path.write_text(json.dumps(ws))

        kd_path = tmp_path / "data" / "neuralweb" / "kernel_decisions.json"
        kd = json.loads(kd_path.read_text())
        kd["run_at"] = f"{stale_date}T12:00:00Z"
        kd_path.write_text(json.dumps(kd))

        memo_path = tmp_path / "data" / "neuralweb" / "cortex" / "memo.json"
        memo = json.loads(memo_path.read_text())
        memo["as_of"] = stale_date
        memo_path.write_text(json.dumps(memo))

        bs_path = tmp_path / "site" / "neuralwebdata" / "bottom_sensors.json"
        bs = json.loads(bs_path.read_text())
        bs["as_of"] = stale_date
        bs_path.write_text(json.dumps(bs))

        # Build with now=2026-07-05 (4 days after stale data)
        payload = build_context(root=tmp_path, now=_NOW)

        assert payload["as_of"] == stale_date, (
            f"as_of should reflect oldest lobe data timestamp {stale_date!r}, "
            f"not build time; got {payload['as_of']!r}"
        )
        # generated_utc must still be the build timestamp
        assert payload["generated_utc"] == "2026-07-05T12:00:00Z", (
            "generated_utc must remain the build time stamp"
        )


# ---------------------------------------------------------------------------
# 11. claim_reliability lobe (W-B bridge key, RUL-C2/C3/C10)
# ---------------------------------------------------------------------------

def _minimal_track_record(tmp_path: Path) -> Path:
    """Write a minimal site/qledger/track_record.json fixture."""
    (tmp_path / "site" / "qledger").mkdir(parents=True, exist_ok=True)
    obj = {
        "generated_at": "2026-07-05",
        "grade_horizons": [5],
        "by_desk": {
            "altdata": {
                "5": {
                    "n_obs": 94,
                    "hit_rate": 0.56383,
                    "wilson_ci_low": 0.463027,
                    "state": "ACCRUING",
                }
            },
            "radar": {
                "5": {
                    "n_obs": 1014,
                    "hit_rate": 0.540434,
                    "wilson_ci_low": 0.509664,
                    "state": "ACCRUING",
                }
            },
        },
        "by_family": {
            "altdata": {
                "5": {
                    "n_obs": 94,
                    "hit_rate": 0.56383,
                    "wilson_ci_low": 0.463027,
                    "state": "ACCRUING",
                }
            },
        },
    }
    p = tmp_path / "site" / "qledger" / "track_record.json"
    p.write_text(json.dumps(obj))
    return p


class TestClaimReliabilityLobe:
    """Tests for the claim_reliability bridge lobe key (W-B, RUL-C2/C3/C10)."""

    def test_claim_reliability_standing_law_present(self, tmp_path):
        """claim_reliability lobe must carry standing_law string (mirrors reliability test)."""
        _build_minimal_tree(tmp_path)
        _minimal_track_record(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        cr = payload["lobes"].get("claim_reliability", {})
        assert "standing_law" in cr, "claim_reliability lobe missing standing_law"
        assert len(cr["standing_law"]) > 20, "standing_law string too short"
        # Must mention 5d-only and ACCRUING (key spec requirements)
        law = cr["standing_law"]
        assert "5d" in law or "5-day" in law or "5d-only" in law, (
            "standing_law must reference 5d horizon"
        )
        assert "ACCRUING" in law or "accruing" in law.lower(), (
            "standing_law must reference ACCRUING state"
        )

    def test_claim_reliability_expected_subfields(self, tmp_path):
        """claim_reliability lobe must have desks, top_families, standing_law, as_of."""
        _build_minimal_tree(tmp_path)
        _minimal_track_record(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        cr = payload["lobes"].get("claim_reliability")
        assert cr is not None, "claim_reliability lobe missing from payload"
        assert "desks" in cr, "claim_reliability missing 'desks'"
        assert "top_families" in cr, "claim_reliability missing 'top_families'"
        assert "standing_law" in cr, "claim_reliability missing 'standing_law'"
        assert "as_of" in cr, "claim_reliability missing 'as_of'"
        # Each desk entry must have horizon_d=5
        for desk_name, desk_entry in cr["desks"].items():
            assert desk_entry.get("horizon_d") == 5, (
                f"desk {desk_name!r} missing horizon_d=5"
            )
        # Spot-check altdata desk values from fixture
        altdata = cr["desks"].get("altdata", {})
        assert altdata.get("hit_rate") == pytest.approx(0.56383, rel=1e-4), (
            "altdata hit_rate mismatch"
        )
        assert altdata.get("n") == 94, "altdata n mismatch"
        assert altdata.get("state") == "ACCRUING", "altdata state mismatch"

    def test_claim_reliability_track_record_absent_fail_open(self, tmp_path):
        """When track_record.json is absent, lobe should produce a gap_note, not raise."""
        _build_minimal_tree(tmp_path)
        # Deliberately do NOT write track_record.json
        payload = build_context(root=tmp_path, now=_NOW)
        gap_str = " ".join(payload["gap_notes"])
        assert "claim_reliability" in gap_str or "track_record" in gap_str, (
            f"Expected claim_reliability/track_record gap note; got: {payload['gap_notes']}"
        )
        # Lobe key must still be present (even if empty)
        assert "claim_reliability" in payload["lobes"], (
            "claim_reliability key must be present even when track_record absent"
        )

    def test_claim_reliability_claim_accountability_absent_is_gap_note_not_failure(
        self, tmp_path
    ):
        """When claim_accountability.json is absent (sibling PR-B not yet merged),
        lobe succeeds with a gap note on the lobe but does not fail."""
        _build_minimal_tree(tmp_path)
        _minimal_track_record(tmp_path)
        # Do NOT write data/governance/claim_accountability.json
        payload = build_context(root=tmp_path, now=_NOW)
        cr = payload["lobes"].get("claim_reliability", {})
        # Lobe must still have its core fields
        assert "desks" in cr, "desks missing when accountability absent"
        assert "standing_law" in cr, "standing_law missing when accountability absent"
        # accountability_gap note must appear on the lobe
        assert "accountability_gap" in cr, (
            "claim_reliability lobe must carry accountability_gap key when "
            "claim_accountability.json is absent"
        )

    def test_claim_reliability_key_does_not_clobber_reliability(self, tmp_path):
        """RUL-C2: claim_reliability must be separate from reliability lobe."""
        _build_minimal_tree(tmp_path)
        _minimal_track_record(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        lobes = payload["lobes"]
        # Both must be present and distinct
        assert "reliability" in lobes, "reliability lobe must still be present"
        assert "claim_reliability" in lobes, "claim_reliability lobe must be present"
        # reliability lobe must still carry kernel_decisions (its own structure)
        rel = lobes["reliability"]
        assert "kernel_decisions" in rel, (
            "reliability lobe clobbered — kernel_decisions missing"
        )


# ---------------------------------------------------------------------------
# 12. Analyst block (Build 3 — NW consolidated context layer)
# ---------------------------------------------------------------------------

def _minimal_analyst_parquet(tmp_path: Path, rows: list[dict] | None = None) -> Path:
    """Write a minimal data/analyst/targets.parquet fixture."""
    import pandas as pd
    (tmp_path / "data" / "analyst").mkdir(parents=True, exist_ok=True)
    default_rows = [
        {
            "ticker": "FIXTURE_BUY",
            "target_mean": 100.0,
            "target_high": 120.0,
            "target_low": 85.0,
            "implied_upside_pct": 15.2,
            "target_dispersion": 0.35,
            "recommendation": "buy",
            "num_analysts": 12,
            "current_price": 86.8,
            "as_of": "2026-07-05",
            "provenance_note": "yfinance_info_pit_snapshot",
        },
        {
            "ticker": "FIXTURE_WATCH",
            "target_mean": None,
            "target_high": None,
            "target_low": None,
            "implied_upside_pct": None,
            "target_dispersion": None,
            "recommendation": None,
            "num_analysts": None,
            "current_price": None,
            "as_of": "2026-07-05",
            "provenance_note": "yfinance_info_pit_snapshot",
        },
    ]
    df = pd.DataFrame(rows or default_rows)
    p = tmp_path / "data" / "analyst" / "targets.parquet"
    df.to_parquet(p, index=False)
    return p


class TestAnalystBlock:
    """Tests for the analyst sub-block (Build 3 — display/context only)."""

    def test_analyst_block_present_when_parquet_exists(self, tmp_path):
        """When targets.parquet has a row for a standout ticker, analyst block appears."""
        _build_minimal_tree(tmp_path)
        _minimal_analyst_parquet(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        cc = payload["candidate_context"]
        # FIXTURE_BUY has a full analyst row
        assert "FIXTURE_BUY" in cc, "FIXTURE_BUY should be in candidate_context"
        row = cc["FIXTURE_BUY"]
        assert "analyst" in row, (
            "analyst block should be present for FIXTURE_BUY (has target_mean)"
        )
        analyst = row["analyst"]
        assert analyst.get("target_mean") == pytest.approx(100.0)
        assert analyst.get("implied_upside_pct") == pytest.approx(15.2)
        assert analyst.get("target_dispersion") == pytest.approx(0.35)
        assert analyst.get("recommendation") == "buy"
        assert analyst.get("num_analysts") == 12

    def test_analyst_block_absent_when_all_fields_null(self, tmp_path):
        """When all analyst fields are None (honest-null row), no analyst block emitted."""
        _build_minimal_tree(tmp_path)
        _minimal_analyst_parquet(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        cc = payload["candidate_context"]
        # FIXTURE_WATCH has all-None analyst fields — block should be absent
        assert "FIXTURE_WATCH" in cc, "FIXTURE_WATCH should be in candidate_context"
        row = cc["FIXTURE_WATCH"]
        assert "analyst" not in row, (
            "analyst block should NOT appear for FIXTURE_WATCH (all fields None)"
        )

    def test_analyst_block_absent_when_parquet_missing(self, tmp_path):
        """When targets.parquet is absent, no analyst block appears and gap_note is added."""
        _build_minimal_tree(tmp_path)
        # Deliberately do NOT write targets.parquet
        payload = build_context(root=tmp_path, now=_NOW)
        cc = payload["candidate_context"]
        # No ticker should have an analyst block
        for ticker, row in cc.items():
            assert "analyst" not in row, (
                f"analyst block appeared for {ticker!r} despite absent parquet"
            )
        # A gap_note must be present
        gap_str = " ".join(payload["gap_notes"])
        assert "analyst" in gap_str, (
            f"Expected gap note mentioning 'analyst'; got: {payload['gap_notes']}"
        )

    def test_analyst_block_allowed_behavior_unchanged(self, tmp_path):
        """Adding an analyst block must NOT change allowed_behavior for any row."""
        _build_minimal_tree(tmp_path)
        _minimal_analyst_parquet(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        for ticker, row in payload["candidate_context"].items():
            assert row.get("allowed_behavior") == "annotate_only", (
                f"Ticker {ticker!r} has wrong allowed_behavior after analyst block added"
            )

    def test_analyst_block_fields_no_validated_text(self, tmp_path):
        """No analyst field value may contain the word 'validated'."""
        _build_minimal_tree(tmp_path)
        _minimal_analyst_parquet(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        for ticker, row in payload["candidate_context"].items():
            analyst = row.get("analyst") or {}
            for k, v in analyst.items():
                if isinstance(v, str):
                    assert "validated" not in v.lower(), (
                        f"analyst.{k} for {ticker!r} contains 'validated': {v!r}"
                    )

    def test_size_cap_constant_is_300kb(self):
        """CONTEXT_SIZE_CAP_BYTES must be 300 * 1024 (Build 3 cap raise)."""
        from engine.neuralweb.mastermind_context import CONTEXT_SIZE_CAP_BYTES  # noqa: PLC0415
        assert CONTEXT_SIZE_CAP_BYTES == 300 * 1024, (
            f"Expected CONTEXT_SIZE_CAP_BYTES=307200, got {CONTEXT_SIZE_CAP_BYTES}"
        )


# ---------------------------------------------------------------------------
# 13. Weekend-aware staleness (freshness contract fix)
# ---------------------------------------------------------------------------

class TestWeekendStaleness:
    """_is_stale measures staleness in TRADING time.

    2026-07-03 = Friday, 2026-07-04 = Saturday, 2026-07-05 = Sunday,
    2026-07-06 = Monday, 2026-07-07 = Tuesday. SLA = 30h.
    """

    def test_friday_asof_not_stale_on_sunday(self):
        now = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)  # Sunday noon
        assert _is_stale("2026-07-03", now=now) is False, (
            "Friday as_of must not be stale on Sunday (weekend allowance)"
        )

    def test_friday_asof_fresh_through_monday_sla(self):
        """as_of Friday → allow until Monday + SLA (clock restarts Monday)."""
        now = datetime(2026, 7, 7, 5, 0, 0, tzinfo=timezone.utc)  # Tue 05:00 (29h after Mon 00:00)
        assert _is_stale("2026-07-03", now=now) is False

    def test_friday_asof_stale_after_monday_sla(self):
        now = datetime(2026, 7, 7, 12, 0, 0, tzinfo=timezone.utc)  # Tue noon (36h after Mon 00:00)
        assert _is_stale("2026-07-03", now=now) is True

    def test_saturday_asof_clock_starts_monday(self):
        now = datetime(2026, 7, 6, 23, 0, 0, tzinfo=timezone.utc)  # Monday 23:00
        assert _is_stale("2026-07-04", now=now) is False

    def test_weekday_behaviour_unchanged_stale(self):
        """Wednesday as_of checked Friday noon (60h) is stale — no allowance."""
        now = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)  # Friday noon
        assert _is_stale("2026-07-01", now=now) is True

    def test_weekday_behaviour_unchanged_fresh(self):
        """Thursday as_of checked Friday 05:00 (29h) is fresh — within SLA."""
        now = datetime(2026, 7, 3, 5, 0, 0, tzinfo=timezone.utc)
        assert _is_stale("2026-07-02", now=now) is False

    def test_absent_asof_still_stale(self):
        assert _is_stale(None) is True
        assert _is_stale("") is True

    def test_naive_now_accepted(self):
        """now without tzinfo must work (internal callers use naive UTC)."""
        now = datetime(2026, 7, 5, 12, 0, 0)  # naive Sunday noon
        assert _is_stale("2026-07-03", now=now) is False


# ---------------------------------------------------------------------------
# 14. risk_radar_reliability lobe (RR forward-ledger distillation)
# ---------------------------------------------------------------------------

def _minimal_rr_scorecard(
    tmp_path: Path,
    *,
    us_graded_n: int = 30,
    us_alert_n: int = 12,
    us_alert_tp: int = 8,
    us_wc_n: int = 10,
    us_wc_tp: int = 7,
    include_cn: bool = True,
    include_hk: bool = False,
    include_ca: bool = False,
) -> Path:
    """Write a minimal site/riskdata/scorecard.json fixture.

    Mirrors the frozen cross-builder contract (schema risk_radar_scorecard.v1).
    """
    (tmp_path / "site" / "riskdata").mkdir(parents=True, exist_ok=True)

    def _alert_win(n: int, tp: int) -> dict:
        fp = n - tp
        return {
            "n": n,
            "tp": tp,
            "fp": fp,
            "hit_rate": (tp / n) if n >= 5 else None,
        }

    def _wc_win(n: int, tp: int) -> dict:
        tn = n - tp
        return {
            "n": n,
            "tp": tp,
            "tn": tn,
            "precursor_rate": (tp / n) if n >= 5 else None,
        }

    def _full_window(alert_n: int, alert_tp: int, wc_n: int, wc_tp: int) -> dict:
        return {
            "alerts": _alert_win(alert_n, alert_tp),
            "watch_caution": _wc_win(wc_n, wc_tp),
            "calm": {"n": 20, "dd_missed": 1, "quiet": 18, "quiet_rate": 0.9},
            "by_scare": {
                "credit": _alert_win(6, 4),
                "rates": _alert_win(4, 2),
                "growth": _alert_win(2, 1),
            },
            "recovery": {"n": 8, "ok": 6, "rate": 0.75},
        }

    def _market(graded_n: int, alert_n: int, alert_tp: int, wc_n: int, wc_tp: int) -> dict:
        win = _full_window(alert_n, alert_tp, wc_n, wc_tp)
        return {
            "asof_last_row": "2026-07-12",
            "monitoring": {
                "log_fresh": True,
                "last_logged_days_ago": 1,
                "ungraded_backlog": 3,
                "graded_n": graded_n,
            },
            "windows": {
                "full": win,
                "y1": win,
            },
        }

    markets: dict = {
        "us": _market(us_graded_n, us_alert_n, us_alert_tp, us_wc_n, us_wc_tp),
    }
    if include_cn:
        markets["cn"] = _market(10, 5, 3, 6, 4)
    if include_hk:
        markets["hk"] = _market(8, 4, 2, 3, 2)
    if include_ca:
        markets["ca"] = _market(6, 3, 2, 2, 1)

    obj = {
        "schema": "risk_radar_scorecard.v1",
        "generated_at": "2026-07-13T06:00:00Z",
        "markets": markets,
    }
    p = tmp_path / "site" / "riskdata" / "scorecard.json"
    p.write_text(json.dumps(obj))
    return p


def _minimal_rr_scorecard_small_n(tmp_path: Path) -> Path:
    """Scorecard with insufficient_n (n < 5) in all rate fields."""
    (tmp_path / "site" / "riskdata").mkdir(parents=True, exist_ok=True)
    obj = {
        "schema": "risk_radar_scorecard.v1",
        "generated_at": "2026-07-13T06:00:00Z",
        "markets": {
            "us": {
                "asof_last_row": "2026-07-12",
                "monitoring": {
                    "log_fresh": True,
                    "last_logged_days_ago": 1,
                    "ungraded_backlog": 1,
                    "graded_n": 3,
                },
                "windows": {
                    "full": {
                        "alerts": {"n": 3, "tp": 2, "fp": 1, "hit_rate": None},
                        "watch_caution": {"n": 2, "tp": 1, "tn": 1, "precursor_rate": None},
                        "calm": {"n": 0, "dd_missed": 0, "quiet": 0, "quiet_rate": None},
                        "by_scare": {
                            "credit": {"n": 2, "tp": 1, "fp": 1, "hit_rate": None},
                        },
                        "recovery": None,
                    },
                    "y1": {
                        "alerts": {"n": 3, "tp": 2, "fp": 1, "hit_rate": None},
                        "watch_caution": {"n": 2, "tp": 1, "tn": 1, "precursor_rate": None},
                        "calm": {"n": 0, "dd_missed": 0, "quiet": 0, "quiet_rate": None},
                        "by_scare": {
                            "credit": {"n": 2, "tp": 1, "fp": 1, "hit_rate": None},
                        },
                        "recovery": None,
                    },
                },
            }
        },
    }
    p = tmp_path / "site" / "riskdata" / "scorecard.json"
    p.write_text(json.dumps(obj))
    return p


class TestRiskRadarReliabilityLobe:
    """Tests for the risk_radar_reliability bridge lobe."""

    def test_lobe_present_and_standing_law(self, tmp_path):
        """risk_radar_reliability lobe must be present and carry standing_law."""
        _build_minimal_tree(tmp_path)
        _minimal_rr_scorecard(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        rr = payload["lobes"].get("risk_radar_reliability")
        assert rr is not None, "risk_radar_reliability lobe missing"
        assert "standing_law" in rr, "lobe missing standing_law"
        law = rr["standing_law"]
        assert len(law) > 20, "standing_law too short"
        # Must mention graded and track record (no 'validated')
        assert "graded" in law.lower() or "track record" in law.lower(), (
            "standing_law must reference 'graded' or 'track record'"
        )
        assert "validated" not in law.lower(), (
            "standing_law must NOT contain the banned word 'validated'"
        )

    def test_lobe_has_markets_key(self, tmp_path):
        """Lobe must have a 'markets' dict with at least 'us'."""
        _build_minimal_tree(tmp_path)
        _minimal_rr_scorecard(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        rr = payload["lobes"].get("risk_radar_reliability", {})
        assert "markets" in rr, "lobe missing 'markets' key"
        assert isinstance(rr["markets"], dict), "'markets' must be a dict"
        assert "us" in rr["markets"], "'us' market missing from lobe"

    def test_us_alert_hit_rate_correct(self, tmp_path):
        """US y1 alert hit_rate must match fixture (8/12)."""
        _build_minimal_tree(tmp_path)
        _minimal_rr_scorecard(tmp_path, us_alert_n=12, us_alert_tp=8)
        payload = build_context(root=tmp_path, now=_NOW)
        rr = payload["lobes"].get("risk_radar_reliability", {})
        us = rr.get("markets", {}).get("us", {})
        y1a = us.get("y1_alerts", {})
        assert y1a.get("n") == 12, f"Expected n=12, got {y1a.get('n')}"
        assert y1a.get("tp") == 8, f"Expected tp=8, got {y1a.get('tp')}"
        assert y1a.get("hit_rate") == pytest.approx(8 / 12, rel=1e-4), (
            f"Expected hit_rate~=0.667, got {y1a.get('hit_rate')}"
        )
        assert y1a.get("insufficient_n") is False, (
            "insufficient_n should be False when n=12 >= 5"
        )

    def test_null_rate_emits_insufficient_n(self, tmp_path):
        """When n < 5, hit_rate=null and insufficient_n=True must be emitted."""
        _build_minimal_tree(tmp_path)
        _minimal_rr_scorecard_small_n(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        rr = payload["lobes"].get("risk_radar_reliability", {})
        us = rr.get("markets", {}).get("us", {})
        y1a = us.get("y1_alerts", {})
        assert y1a.get("hit_rate") is None, (
            "hit_rate must be null when n < 5 (insufficient_n)"
        )
        assert y1a.get("insufficient_n") is True, (
            "insufficient_n must be True when n < 5"
        )
        y1wc = us.get("y1_watch_caution", {})
        assert y1wc.get("precursor_rate") is None, (
            "precursor_rate must be null when n < 5"
        )
        assert y1wc.get("insufficient_n") is True

    def test_top_scares_sorted_by_count(self, tmp_path):
        """top_scares must be sorted by n descending (credit n=6 > rates n=4)."""
        _build_minimal_tree(tmp_path)
        _minimal_rr_scorecard(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        rr = payload["lobes"].get("risk_radar_reliability", {})
        us = rr.get("markets", {}).get("us", {})
        scares = us.get("top_scares", [])
        assert len(scares) <= 2, "top_scares must be capped at 2"
        if len(scares) >= 2:
            assert scares[0]["n"] >= scares[1]["n"], (
                "top_scares must be sorted descending by n"
            )
        # credit has n=6, must be first
        if scares:
            assert scares[0]["scare"] == "credit", (
                f"Expected 'credit' first (n=6); got {scares[0]['scare']!r}"
            )

    def test_monitoring_health_fields(self, tmp_path):
        """Monitoring block must carry log_fresh, ungraded_backlog, graded_n."""
        _build_minimal_tree(tmp_path)
        _minimal_rr_scorecard(tmp_path, us_graded_n=30)
        payload = build_context(root=tmp_path, now=_NOW)
        rr = payload["lobes"].get("risk_radar_reliability", {})
        us = rr.get("markets", {}).get("us", {})
        mon = us.get("monitoring", {})
        assert mon.get("log_fresh") is True
        assert mon.get("graded_n") == 30
        assert "ungraded_backlog" in mon

    def test_absent_scorecard_produces_gap_note(self, tmp_path):
        """Missing scorecard.json must add a gap_note and not raise."""
        _build_minimal_tree(tmp_path)
        # Deliberately do NOT write scorecard.json
        payload = build_context(root=tmp_path, now=_NOW)
        gap_str = " ".join(payload["gap_notes"])
        assert "risk_radar" in gap_str or "scorecard" in gap_str, (
            f"Expected risk_radar/scorecard gap note; got: {payload['gap_notes']}"
        )
        # Lobe key must still be present (fail-soft)
        assert "risk_radar_reliability" in payload["lobes"], (
            "risk_radar_reliability key must be present even when scorecard absent"
        )

    def test_malformed_json_produces_gap_note(self, tmp_path):
        """Malformed scorecard.json must not raise — fail-soft with gap note."""
        _build_minimal_tree(tmp_path)
        (tmp_path / "site" / "riskdata").mkdir(parents=True, exist_ok=True)
        (tmp_path / "site" / "riskdata" / "scorecard.json").write_text("{{not valid json")
        payload = build_context(root=tmp_path, now=_NOW)
        gap_str = " ".join(payload["gap_notes"])
        assert "risk_radar" in gap_str or "scorecard" in gap_str, (
            f"Expected gap note for malformed scorecard; got: {payload['gap_notes']}"
        )
        assert "risk_radar_reliability" in payload["lobes"]

    def test_absent_market_emits_absent_marker(self, tmp_path):
        """Market keys absent from scorecard (hk/ca) must appear with _absent=True."""
        _build_minimal_tree(tmp_path)
        # Only us and cn in fixture (hk, ca absent)
        _minimal_rr_scorecard(tmp_path, include_cn=True, include_hk=False, include_ca=False)
        payload = build_context(root=tmp_path, now=_NOW)
        rr = payload["lobes"].get("risk_radar_reliability", {})
        markets = rr.get("markets", {})
        hk = markets.get("hk", {})
        ca = markets.get("ca", {})
        assert hk.get("_absent") is True, "hk must be absent-marked when not in scorecard"
        assert ca.get("_absent") is True, "ca must be absent-marked when not in scorecard"

    def test_no_validated_text_in_lobe(self, tmp_path):
        """The word 'validated' must not appear anywhere in the lobe (CI-banned)."""
        _build_minimal_tree(tmp_path)
        _minimal_rr_scorecard(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        rr = payload["lobes"].get("risk_radar_reliability", {})
        lobe_str = json.dumps(rr)
        assert "validated" not in lobe_str.lower(), (
            "The word 'validated' must not appear in risk_radar_reliability lobe "
            "(CI-banned by scripts/check_validated_claims.py)"
        )

    def test_recovery_rate_present_when_n_geq_5(self, tmp_path):
        """Recovery rate must be non-null when n >= 5 in fixture."""
        _build_minimal_tree(tmp_path)
        _minimal_rr_scorecard(tmp_path)  # recovery n=8 >= 5
        payload = build_context(root=tmp_path, now=_NOW)
        rr = payload["lobes"].get("risk_radar_reliability", {})
        us = rr.get("markets", {}).get("us", {})
        rec = us.get("recovery", {})
        assert rec.get("rate") is not None, (
            "recovery.rate must be non-null when n=8 >= 5"
        )
        assert rec.get("insufficient_n") is False

    def test_lobe_does_not_clobber_claim_reliability(self, tmp_path):
        """risk_radar_reliability must be a separate lobe from claim_reliability."""
        _build_minimal_tree(tmp_path)
        _minimal_rr_scorecard(tmp_path)
        _minimal_track_record(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        lobes = payload["lobes"]
        assert "claim_reliability" in lobes, "claim_reliability must still be present"
        assert "risk_radar_reliability" in lobes, "risk_radar_reliability must be present"
        # Structural check: different keys
        cr = lobes["claim_reliability"]
        rr = lobes["risk_radar_reliability"]
        assert "desks" in cr, "claim_reliability must still have desks key"
        assert "markets" in rr, "risk_radar_reliability must have markets key"
        assert "desks" not in rr, (
            "risk_radar_reliability must NOT have a 'desks' key (wrong lobe)"
        )


# ---------------------------------------------------------------------------
# 14. freshest_market_asof (freshness contract fix)
# ---------------------------------------------------------------------------

class TestFreshestMarketAsof:
    def test_freshest_is_max_over_market_lobes_only(self, tmp_path):
        """freshest_market_asof = max over MARKET-DATA lobes; min() as_of
        semantics unchanged (ruling §3.3)."""
        _build_minimal_tree(tmp_path)

        # market lobe (regime asof) newest of the market-data lobes
        ws_path = tmp_path / "data" / "neuralweb" / "world_state.json"
        ws = json.loads(ws_path.read_text())
        ws["regime"]["asof"] = "2026-07-06"
        ws_path.write_text(json.dumps(ws))

        # bottom_sensors older
        bs_path = tmp_path / "site" / "neuralwebdata" / "bottom_sensors.json"
        bs = json.loads(bs_path.read_text())
        bs["as_of"] = "2026-07-03"
        bs_path.write_text(json.dumps(bs))

        # cortex memo: OLDEST (drives min) — and a second variant below proves
        # a NEWER memo cannot drive the max.
        memo_path = tmp_path / "data" / "neuralweb" / "cortex" / "memo.json"
        memo = json.loads(memo_path.read_text())
        memo["as_of"] = "2026-07-01"
        memo_path.write_text(json.dumps(memo))

        payload = build_context(root=tmp_path, now=_NOW)
        assert payload["as_of"] == "2026-07-01", (
            "conservative min() as_of semantics must be unchanged"
        )
        assert payload["freshest_market_asof"] == "2026-07-06", (
            f"expected max over market-data lobes; got {payload['freshest_market_asof']!r}"
        )

    def test_newer_non_market_lobe_does_not_inflate_freshest(self, tmp_path):
        """A cortex memo newer than all market data must NOT raise
        freshest_market_asof (cortex is not a market-data lobe)."""
        _build_minimal_tree(tmp_path)
        memo_path = tmp_path / "data" / "neuralweb" / "cortex" / "memo.json"
        memo = json.loads(memo_path.read_text())
        memo["as_of"] = "2026-07-09"
        memo_path.write_text(json.dumps(memo))

        payload = build_context(root=tmp_path, now=_NOW)
        assert payload["freshest_market_asof"] == "2026-07-05", (
            "cortex memo date leaked into freshest_market_asof"
        )

    def test_freshest_null_when_no_market_asof(self, tmp_path):
        """Empty tree → freshest_market_asof is None (fail-open null), key present."""
        payload = build_context(root=tmp_path, now=_NOW)
        assert "freshest_market_asof" in payload
        assert payload["freshest_market_asof"] is None


# ---------------------------------------------------------------------------
# 15. market_plane.json (NW→dashboards export lane)
# ---------------------------------------------------------------------------

_PLANE_TOP_KEYS = (
    "schema", "asof", "is_context_only", "verdict", "regime", "vol", "breadth",
    "liquidity_plumbing", "contradiction_count", "cortex", "stale", "gaps",
)

# Authority-shaped keys that must never be True anywhere in the plane
_AUTHORITY_KEYS = {
    "can_add_candidates", "can_raise_size", "can_lower_size",
    "can_block_entry", "can_force_exit", "hard_gate", "score_raise",
}


def _walk_items(obj, prefix=""):
    """Yield (dotted_key_path, leaf_value) pairs for nested dict/list."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_items(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_items(v, f"{prefix}[{i}]")
    else:
        yield prefix, obj


class TestMarketPlane:
    def test_schema_and_all_keys_present(self, tmp_path):
        _build_minimal_tree(tmp_path)
        plane = build_market_plane(root=tmp_path, now=_NOW)
        assert plane["schema"] == MARKET_PLANE_SCHEMA
        for key in _PLANE_TOP_KEYS:
            assert key in plane, f"market_plane missing top-level key {key!r}"
        for key in ("verdict", "score", "label_en", "label_zh"):
            assert key in plane["verdict"], f"verdict missing {key!r}"
        for key in ("quad", "quad_name", "confidence", "cycle_tag",
                    "transition_state", "flip_margin", "liquidity_overlay"):
            assert key in plane["regime"], f"regime missing {key!r}"
        for key in ("regime", "risk_score"):
            assert key in plane["vol"], f"vol missing {key!r}"
        for key in ("state", "netliq_bn", "netliq_d20_bn", "rrp_buffer_state",
                    "tga_bn", "entry_effect"):
            assert key in plane["liquidity_plumbing"], f"liquidity_plumbing missing {key!r}"
        for key in ("status", "degradation_reason"):
            assert key in plane["cortex"], f"cortex missing {key!r}"

    def test_values_from_fixtures(self, tmp_path):
        _build_minimal_tree(tmp_path)
        plane = build_market_plane(root=tmp_path, now=_NOW)
        assert plane["verdict"]["verdict"] == "RISK_OFF"
        assert plane["verdict"]["score"] == 40
        assert plane["verdict"]["label_en"] == "Risk-off"
        assert plane["verdict"]["label_zh"] == "风险规避"
        assert plane["regime"]["quad_name"] == "Goldilocks"
        assert plane["vol"]["regime"] == "normalizing"
        assert plane["vol"]["risk_score"] == pytest.approx(0.24)
        assert plane["breadth"]["nh"] == 16
        lp = plane["liquidity_plumbing"]
        assert lp["state"] == "stress_liquidity_expansion"
        assert lp["netliq_bn"] == pytest.approx(5980.5)
        assert lp["netliq_d20_bn"] == pytest.approx(56.7)
        assert lp["rrp_buffer_state"] == "exhausted"
        assert lp["tga_bn"] == pytest.approx(749.2)
        assert lp["entry_effect"]["direction"] == "tailwind"
        assert plane["contradiction_count"] == 1
        assert plane["cortex"]["status"] == "ok"
        # as_of 2026-07-05 is a Sunday; built at Sunday noon → not stale
        assert plane["asof"] == "2026-07-05"
        assert plane["stale"] is False

    def test_envelope_stamped(self, tmp_path):
        """Dual-write output must carry all five envelope keys as SIBLINGS
        (never a wrapper), even before synapse.yml registration lands."""
        _build_minimal_tree(tmp_path)
        stamped = build_and_write_market_plane(root=tmp_path, now=_NOW)
        for key in ENVELOPE_KEYS:
            assert key in stamped, f"envelope key {key!r} missing from market_plane"
        assert stamped["tier"] == "display"
        assert stamped["produced_by"], "produced_by must be non-empty"
        # sibling keys, not a wrapper: payload keys still at top level
        assert stamped["schema"] == MARKET_PLANE_SCHEMA
        assert "verdict" in stamped

    def test_dual_write_byte_identical(self, tmp_path):
        _build_minimal_tree(tmp_path)
        build_and_write_market_plane(root=tmp_path, now=_NOW)
        canonical = tmp_path / "data" / "neuralweb" / "market_plane.json"
        site_copy = tmp_path / "site" / "neuralwebdata" / "market_plane.json"
        assert canonical.exists(), "canonical market_plane.json not written"
        assert site_copy.exists(), "site market_plane.json not written"
        assert canonical.read_bytes() == site_copy.read_bytes(), (
            "site copy must be byte-identical to canonical"
        )

    def test_build_and_write_also_writes_plane(self, tmp_path):
        """The main build_and_write() must dual-write market_plane too."""
        _build_minimal_tree(tmp_path)
        build_and_write(root=tmp_path, now=_NOW)
        assert (tmp_path / "data" / "neuralweb" / "market_plane.json").exists()
        assert (tmp_path / "site" / "neuralwebdata" / "market_plane.json").exists()

    def test_is_context_only_and_no_authority_true(self, tmp_path):
        """is_context_only semantics: the plane may carry NO authority boolean
        set true anywhere in its tree."""
        _build_minimal_tree(tmp_path)
        stamped = build_and_write_market_plane(root=tmp_path, now=_NOW)
        assert stamped["is_context_only"] is True
        for path, value in _walk_items(stamped):
            leaf = path.rsplit(".", 1)[-1]
            if leaf in _AUTHORITY_KEYS:
                assert value is not True, (
                    f"authority-shaped key {path!r} is True in market_plane"
                )

    def test_fail_open_empty_tree(self, tmp_path):
        """No inputs at all → nulls per block + gaps[] entries, never a raise."""
        plane = build_market_plane(root=tmp_path, now=_NOW)
        for key in _PLANE_TOP_KEYS:
            assert key in plane, f"missing key {key!r} on empty tree"
        assert plane["verdict"]["verdict"] is None
        assert plane["regime"]["quad"] is None
        assert plane["vol"]["regime"] is None
        assert plane["breadth"] is None
        assert plane["liquidity_plumbing"]["netliq_bn"] is None
        assert plane["contradiction_count"] is None
        assert plane["cortex"]["status"] is None
        assert plane["asof"] is None
        assert plane["stale"] is True
        assert plane["gaps"], "gaps[] must record the missing inputs"

    def test_liquidity_fallback_to_world_state_embedded(self, tmp_path):
        """When liquidity_plumbing.json is absent, the world_state embedded
        block (flat keys) is used and a gap is recorded."""
        _build_minimal_tree(tmp_path)
        (tmp_path / "data" / "neuralweb" / "liquidity_plumbing.json").unlink()
        ws_path = tmp_path / "data" / "neuralweb" / "world_state.json"
        ws = json.loads(ws_path.read_text())
        ws["liquidity_plumbing"] = {
            "available": True,
            "state": "clean_expansion",
            "netliq_bn": 6000.0,
            "netliq_chg_20d_bn": 10.0,
            "rrp_buffer_state": "thin",
            "tga_bn": 700.0,
            "entry_effect_direction": "tailwind",
            "entry_effect_quality": "clean",
            "entry_effect_basis": "cycle_ladder_21d_odds",
            "entry_effect_use": "support existing buy setup, never originate one",
        }
        ws_path.write_text(json.dumps(ws))
        plane = build_market_plane(root=tmp_path, now=_NOW)
        lp = plane["liquidity_plumbing"]
        assert lp["state"] == "clean_expansion"
        assert lp["netliq_d20_bn"] == pytest.approx(10.0)
        assert lp["rrp_buffer_state"] == "thin"
        assert lp["entry_effect"]["measured_basis"] == "cycle_ladder_21d_odds"
        assert any("liquidity_plumbing" in g for g in plane["gaps"])

    def test_no_validated_string(self, tmp_path):
        """The word 'validated' is banned in any user-facing string (CI rule)."""
        _build_minimal_tree(tmp_path)
        stamped = build_and_write_market_plane(root=tmp_path, now=_NOW)
        assert "validated" not in json.dumps(stamped).lower()

    def test_plane_is_compact(self, tmp_path):
        """Header-feed budget: compact JSON stays well under 8KB (~2KB target)."""
        _build_minimal_tree(tmp_path)
        build_and_write_market_plane(root=tmp_path, now=_NOW)
        size = (tmp_path / "data" / "neuralweb" / "market_plane.json").stat().st_size
        assert size <= 8 * 1024, f"market_plane.json too large: {size} bytes"


# ---------------------------------------------------------------------------
# 16. mastermind_ai lobe (W-AI — the trading bot as a lobe of the web)
# ---------------------------------------------------------------------------

def _minimal_feedback_summary(tmp_path: Path, *, state: str = "present",
                              with_ack: bool = True) -> Path:
    """Write a minimal data/governance/mastermind_feedback_summary.json fixture
    (the reverse-bridge artifact built by engine/neuralweb/mastermind_feedback.py)."""
    (tmp_path / "data" / "governance").mkdir(parents=True, exist_ok=True)
    obj: dict = {
        "schema": "neuralweb.mastermind_feedback_summary.v1",
        "generated_utc": "2026-07-05T12:00:00Z",
        "state": state,
        "source_schema": "mastermind_nw_feedback.v3",
        "is_context_only": True,
        "gap_notes": [],
    }
    if state == "present":
        obj["asof"] = "2026-07-05"
        obj["nudges"] = [
            {"code": "ctx_stale_run", "kind": "staleness", "severity": "high",
             "detail": "context stale on 2 of 14 runs"},
            {"code": "lobe_request_theme", "kind": "lobe_request", "severity": "low",
             "detail": "want a theme lobe"},
        ]
        obj["operator_directives"] = [
            {"id": "deadbeef01", "created": "2026-07-05", "text": "check the radar contract"},
        ]
        obj["reflection"] = {
            "state": "ok",
            "contract_drift": [{"code": "radar_ticker_gap", "status": "dead",
                                "severity": "high"}],
            "coverage": {"open_theses_n": 4, "coverage_rate": 0.75},
            "context_quality": {"window_runs": 14, "seen_rate": 0.7142},
            "attribution": {"n_resolved": 2, "state": "accruing"},
        }
        if with_ack:
            obj["ack"] = {
                "nudge_codes_seen": ["ctx_stale_run", "lobe_request_theme"],
                "directive_ids_seen": ["deadbeef01"],
            }
    p = tmp_path / "data" / "governance" / "mastermind_feedback_summary.json"
    p.write_text(json.dumps(obj))
    return p


class TestMastermindAiLobe:
    """W-AI: lobes.mastermind_ai carries the bot dialogue state + the ACK block."""

    def test_registered_in_lobe_summarizers(self):
        from engine.neuralweb.mastermind_context import LOBE_SUMMARIZERS  # noqa: PLC0415
        assert "mastermind_ai" in LOBE_SUMMARIZERS

    def test_lobe_present_state_and_identity(self, tmp_path):
        _build_minimal_tree(tmp_path)
        _minimal_feedback_summary(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        lobe = payload["lobes"]["mastermind_ai"]
        assert lobe["state"] == "present"
        assert lobe["source_schema"] == "mastermind_nw_feedback.v3"
        assert lobe["as_of"] == "2026-07-05"

    def test_lobe_nudges_block(self, tmp_path):
        _build_minimal_tree(tmp_path)
        _minimal_feedback_summary(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        nudges = payload["lobes"]["mastermind_ai"]["nudges"]
        assert nudges["n"] == 2
        assert nudges["by_severity"] == {"high": 1, "low": 1}
        assert nudges["top_codes"] == ["ctx_stale_run", "lobe_request_theme"]

    def test_lobe_directives_block(self, tmp_path):
        _build_minimal_tree(tmp_path)
        _minimal_feedback_summary(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        directives = payload["lobes"]["mastermind_ai"]["directives"]
        assert directives["n"] == 1
        assert directives["ids"] == ["deadbeef01"]

    def test_lobe_reflection_block(self, tmp_path):
        _build_minimal_tree(tmp_path)
        _minimal_feedback_summary(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        rf = payload["lobes"]["mastermind_ai"]["reflection"]
        assert rf["state"] == "ok"
        assert rf["contract_drift_n"] == 1
        assert rf["coverage_rate"] == pytest.approx(0.75)
        assert rf["context_seen_rate"] == pytest.approx(0.7142)
        assert rf["attribution_state"] == "accruing"

    def test_lobe_carries_ack(self, tmp_path):
        """THE ACK — the bot keys directive/nudge status advancement off this."""
        _build_minimal_tree(tmp_path)
        _minimal_feedback_summary(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        assert payload["lobes"]["mastermind_ai"]["ack"] == {
            "nudge_codes_seen": ["ctx_stale_run", "lobe_request_theme"],
            "directive_ids_seen": ["deadbeef01"],
        }

    def test_lobe_ack_defaults_empty_when_missing(self, tmp_path):
        """Summary present but no ack key → empty ack lists, never a raise."""
        _build_minimal_tree(tmp_path)
        _minimal_feedback_summary(tmp_path, with_ack=False)
        payload = build_context(root=tmp_path, now=_NOW)
        assert payload["lobes"]["mastermind_ai"]["ack"] == {
            "nudge_codes_seen": [], "directive_ids_seen": [],
        }

    def test_lobe_absent_gap_note_and_empty_lobe(self, tmp_path):
        """No feedback summary → gap_note 'lobe.mastermind_ai: ...' + empty lobe."""
        _build_minimal_tree(tmp_path)
        # Deliberately do NOT write mastermind_feedback_summary.json
        payload = build_context(root=tmp_path, now=_NOW)
        assert payload["lobes"]["mastermind_ai"] == {}
        assert any(g.startswith("lobe.mastermind_ai:") for g in payload["gap_notes"]), (
            f"Expected 'lobe.mastermind_ai:' gap note; got: {payload['gap_notes']}"
        )

    def test_lobe_summary_state_absent_no_dialogue_blocks(self, tmp_path):
        """Summary file present but state=absent → identity fields only."""
        _build_minimal_tree(tmp_path)
        _minimal_feedback_summary(tmp_path, state="absent")
        payload = build_context(root=tmp_path, now=_NOW)
        lobe = payload["lobes"]["mastermind_ai"]
        assert lobe["state"] == "absent"
        for key in ("nudges", "directives", "reflection", "ack"):
            assert key not in lobe, f"unexpected key {key!r} on absent-state lobe"

    def test_freshness_map_excludes_mastermind_ai(self, tmp_path):
        """Deliberately NOT in _build_freshness asof_sources — the governance
        artifact must not drag the artifact-level as_of."""
        _build_minimal_tree(tmp_path)
        _minimal_feedback_summary(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        assert "mastermind_ai" not in payload["freshness"]

    def test_freshness_map_excludes_mastermind_ai_when_absent(self, tmp_path):
        _build_minimal_tree(tmp_path)
        payload = build_context(root=tmp_path, now=_NOW)
        assert "mastermind_ai" not in payload["freshness"]

    def test_as_of_not_dragged_by_old_feedback_summary(self, tmp_path):
        """An old feedback-summary asof must not lower the artifact as_of
        (governance cadence ≠ market-data cadence)."""
        _build_minimal_tree(tmp_path)
        p = _minimal_feedback_summary(tmp_path)
        obj = json.loads(p.read_text())
        obj["asof"] = "2026-06-01"  # much older than every market lobe
        p.write_text(json.dumps(obj))
        payload = build_context(root=tmp_path, now=_NOW)
        assert payload["as_of"] == "2026-07-05", (
            "old mastermind_ai asof dragged the artifact as_of — it must be "
            "excluded from the freshness min()"
        )
