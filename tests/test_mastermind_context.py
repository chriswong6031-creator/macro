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
    SCHEMA,
    build_context,
    build_and_write,
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
        "verdict": {"verdict": "RISK_OFF", "score": 40},
        "regime": {
            "quad": 1, "quad_name": "Goldilocks", "confidence": 0.5,
            "cycle_tag": "expansion", "transition_state": "STABLE",
            "flip_margin": 0.1, "liquidity_overlay": "neutral", "asof": "2026-07-05",
        },
        "as_of": "2026-07-05",
        "produced_at": "2026-07-05T12:00:00Z",
    }
    p = tmp_path / "data" / "neuralweb" / "world_state.json"
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

    def test_as_of_matches_now(self, tmp_path):
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
    def test_real_build_under_200kb(self):
        """Real build from the worktree data must produce an artifact under 200KB."""
        canonical = _REPO_ROOT / "data" / "neuralweb" / "mastermind_context.json"
        if not canonical.exists():
            # Trigger a fresh build
            build_and_write(root=_REPO_ROOT)
        assert canonical.exists(), "mastermind_context.json not written"
        size_bytes = canonical.stat().st_size
        cap_bytes = 200 * 1024  # 200 KB
        assert size_bytes <= cap_bytes, (
            f"mastermind_context.json too large: {size_bytes/1024:.1f}KB > 200KB. "
            "Reduce candidate_context rows or field columns."
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
