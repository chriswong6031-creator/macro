"""Tests for MSP-W3 Neural Web market_structure lobe wiring.

Coverage
--------
1.  compose_happy_path        — _compose_market_structure from tmp fixture returns
                                expected compact keys; display_only=True stamped;
                                no history arrays in output.
2.  compose_absent_file       — absent file → honest-null block with absent=True,
                                display_only=True; no raise.
3.  compose_corrupt_json      — corrupt JSON → honest-null block; no raise.
4.  compose_display_only      — _law.display_only contract: display_only=True always.
5.  compose_no_authority      — _law.assert_no_authority returns [] on composed block.
6.  compose_no_fused_keys     — emitted dict keys contain no forbidden fusion patterns
                                (spi, combined_z, composite_z, blended, fused).
7.  compose_state_changes     — state_changes list extracted (capped at 6); None when empty.
8.  world_state_payload_key   — build_world_state() returns payload with "market_structure" key.
9.  world_state_absent_file   — absent file → payload["market_structure"]["absent"] True,
                                no raise, no gaps entry appended for absent artifact.
10. brief_block_happy         — _block_market_structure returns dict with _tape_family
                                and honesty_note when world_state has valid ms block.
11. brief_block_absent_ws     — _block_market_structure(None) → None.
12. brief_block_absent_ms     — world_state missing market_structure → None.
13. brief_block_all_null      — all key fields null → None (budget-safe drop).
14. mastermind_lobe_key       — LOBE_SUMMARIZERS contains "market_structure".
15. mastermind_artifact_ids   — _LOBE_TO_ARTIFACT_IDS["market_structure"] correct.
16. mastermind_standing_law   — _MARKET_STRUCTURE_STANDING_LAW constant embeds key law text.
17. mastermind_summarize_ws   — _summarize_market_structure reads world_state correctly.
18. mastermind_summarize_absent — absent world_state → empty lobe + gap note.
19. confluence_subtype        — "market_structure" in _MACRO_SUBTYPES.
20. confluence_node_built     — _build_macro_nodes builds macro:market_structure node
                                from a world_state with market_structure present.
21. confluence_node_absent    — absent/null market_structure → no macro:market_structure node,
                                no error.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Repo root + helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_NOW = datetime(2026, 7, 17, 12, 0, 0, tzinfo=timezone.utc)


def _write_json(p: Path, obj: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")


def _ms_fixture() -> dict:
    """Minimal valid market_structure/latest.json payload."""
    return {
        "schema": "market_structure_context.v1",
        "asof": "2026-07-17",
        "built_at": "2026-07-17T06:00:00Z",
        "is_context_only": True,
        "display_only": True,
        "gamma": {
            "regime": "short",
            "net_gex_bn": -11.06,
            "net_gex_pctile": 19.2,
            "gamma_flip": 5450.0,
            "spot": 5432.0,
            "dist_to_flip_pct": -0.33,
            "days_in_regime": 1,
            "series_start": "2017-01-01",
            "history": [],  # history array must NOT appear in compose output
        },
        "systematic": {
            "vc": {
                "alloc_bn": 320.5,
                "alloc_frac": 0.91,
                "flow_1d_bn": -2.1,
                "flow_5d_bn": -8.4,
                "state": "reducing",
                "aum_bn": 350.0,
                "target_vol_pct": 10.0,
                "series_start": "1990-01-01",
            },
            "cta": {
                "score": -0.45,
                "z": -1.1,
                "flow_1d": -3.2,
                "flow_5d": -14.6,
                "state": "cutting",
            },
            "agreement": "aligned_cutting",
            "history": [],
        },
        "vol": {
            "rv21": 0.1135,
            "rv63": 0.1284,
            "rv_cross_state": "calm",
            "vix_curve": [],
            "vix_curve_slope": 2.23,
            "series_start_curve": "2004-01-01",
        },
        "dispersion": {
            "cor1m": 6.38,
            "cor1m_regime": "dispersion",
            "cor1m_1y_delta": -2.1,
            "cor1m_pctile_2y": 3.8,
            "cor3m": 8.1,
            "dspx": 11.2,
            "history": [],
        },
        "state_changes": {
            "vs_asof": None,
            "items": [
                {"field": "gamma.regime", "from": "long", "to": "short", "when": "2026-07-17"},
            ],
        },
        "prev_state": {},
    }


# ---------------------------------------------------------------------------
# 1-6: _compose_market_structure unit tests
# ---------------------------------------------------------------------------

class TestComposeMarketStructure:
    def _import(self):
        from engine.neuralweb.world_state import _compose_market_structure
        return _compose_market_structure

    def test_compose_happy_path(self, tmp_path):
        """compose from fixture → expected compact keys; no history arrays."""
        fn = self._import()
        ms_dir = tmp_path / "data" / "market_structure"
        ms_dir.mkdir(parents=True)
        (ms_dir / "latest.json").write_text(json.dumps(_ms_fixture()), encoding="utf-8")

        block = fn(root=tmp_path)

        # Required top-level keys
        assert block.get("asof") == "2026-07-17"
        assert block.get("display_only") is True
        assert block.get("is_context_only") is True

        # gamma compact keys
        g = block.get("gamma") or {}
        assert g.get("regime") == "short"
        assert g.get("net_gex_bn") == pytest.approx(-11.06, rel=1e-3)
        assert g.get("dist_to_flip_pct") == pytest.approx(-0.33, rel=1e-3)
        assert g.get("days_in_regime") == 1
        assert "history" not in g, "history array must be excluded from compose output"

        # systematic compact keys (MSP-R3: no fused composite)
        s = block.get("systematic") or {}
        assert s.get("vc_state") == "reducing"
        assert s.get("cta_state") == "cutting"
        assert s.get("agreement") == "aligned_cutting"
        assert "history" not in s

        # vol compact keys
        v = block.get("vol") or {}
        assert v.get("rv_cross_state") == "calm"
        assert "vix_curve" not in v  # raw VIX curve array not projected

        # dispersion compact keys
        d = block.get("dispersion") or {}
        assert d.get("cor1m_regime") == "dispersion"
        assert d.get("cor1m_pctile_2y") == pytest.approx(3.8, rel=1e-3)

    def test_compose_absent_file(self, tmp_path):
        """Absent file → honest-null block with absent=True; no raise."""
        fn = self._import()
        block = fn(root=tmp_path)
        assert block.get("absent") is True
        assert block.get("display_only") is True
        assert block.get("asof") is None

    def test_compose_corrupt_json(self, tmp_path):
        """Corrupt JSON → honest-null block; no raise."""
        fn = self._import()
        ms_dir = tmp_path / "data" / "market_structure"
        ms_dir.mkdir(parents=True)
        (ms_dir / "latest.json").write_text("{not valid json", encoding="utf-8")
        block = fn(root=tmp_path)
        assert block.get("absent") is True
        assert block.get("display_only") is True

    def test_compose_display_only(self, tmp_path):
        """display_only=True on BOTH happy and absent paths."""
        fn = self._import()
        ms_dir = tmp_path / "data" / "market_structure"
        ms_dir.mkdir(parents=True)
        (ms_dir / "latest.json").write_text(json.dumps(_ms_fixture()), encoding="utf-8")
        assert fn(root=tmp_path).get("display_only") is True
        # Absent case
        tmp2 = tmp_path / "absent_root"
        tmp2.mkdir()
        assert fn(root=tmp2).get("display_only") is True

    def test_compose_no_authority(self, tmp_path):
        """assert_no_authority returns [] on composed block."""
        from engine.neuralweb._law import assert_no_authority
        fn = self._import()
        ms_dir = tmp_path / "data" / "market_structure"
        ms_dir.mkdir(parents=True)
        (ms_dir / "latest.json").write_text(json.dumps(_ms_fixture()), encoding="utf-8")
        block = fn(root=tmp_path)
        violations = assert_no_authority(block)
        assert violations == [], f"Authority violations: {violations}"

    def test_compose_no_fused_keys(self, tmp_path):
        """No forbidden fusion key in emitted dict keys (flat and nested)."""
        fn = self._import()
        ms_dir = tmp_path / "data" / "market_structure"
        ms_dir.mkdir(parents=True)
        (ms_dir / "latest.json").write_text(json.dumps(_ms_fixture()), encoding="utf-8")
        block = fn(root=tmp_path)

        _FORBIDDEN = {"spi", "combined_z", "composite_z", "blended", "fused"}

        def _gather_keys(d: dict, acc: set) -> None:
            for k, v in d.items():
                acc.add(k)
                if isinstance(v, dict):
                    _gather_keys(v, acc)

        all_keys: set[str] = set()
        _gather_keys(block, all_keys)
        violations = all_keys & _FORBIDDEN
        assert not violations, f"Forbidden fused keys present: {violations}"

    def test_compose_state_changes(self, tmp_path):
        """state_changes list extracted (capped at 6); None when items empty."""
        fn = self._import()
        ms_dir = tmp_path / "data" / "market_structure"
        ms_dir.mkdir(parents=True)

        # With items
        fix = _ms_fixture()
        (ms_dir / "latest.json").write_text(json.dumps(fix), encoding="utf-8")
        block = fn(root=tmp_path)
        assert isinstance(block.get("state_changes"), list)
        assert len(block["state_changes"]) == 1
        assert block["state_changes"][0]["field"] == "gamma.regime"

        # Empty items → None
        fix2 = _ms_fixture()
        fix2["state_changes"]["items"] = []
        (ms_dir / "latest.json").write_text(json.dumps(fix2), encoding="utf-8")
        block2 = fn(root=tmp_path)
        assert block2.get("state_changes") is None

        # Over-length items capped at 6
        fix3 = _ms_fixture()
        fix3["state_changes"]["items"] = [{"field": f"f{i}"} for i in range(10)]
        (ms_dir / "latest.json").write_text(json.dumps(fix3), encoding="utf-8")
        block3 = fn(root=tmp_path)
        assert isinstance(block3.get("state_changes"), list)
        assert len(block3["state_changes"]) == 6


# ---------------------------------------------------------------------------
# 8-9: world_state integration
# ---------------------------------------------------------------------------

class TestWorldStateMarketStructure:
    def _make_minimal_root(self, tmp_path: Path) -> Path:
        """Write just enough fixtures for build_world_state to not crash."""
        import shutil
        # Copy synapse.yml (needed for envelope stamp)
        dest_cfg = tmp_path / "config" / "synapse.yml"
        dest_cfg.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_REPO_ROOT / "config" / "synapse.yml", dest_cfg)
        return tmp_path

    def test_world_state_payload_key(self, tmp_path):
        """build_world_state() returns payload with 'market_structure' key."""
        from engine.neuralweb.world_state import build_world_state
        self._make_minimal_root(tmp_path)
        ms_dir = tmp_path / "data" / "market_structure"
        ms_dir.mkdir(parents=True)
        (ms_dir / "latest.json").write_text(json.dumps(_ms_fixture()), encoding="utf-8")

        payload = build_world_state(root=tmp_path, now=_NOW)
        assert "market_structure" in payload, (
            "build_world_state() must include market_structure key"
        )
        ms = payload["market_structure"]
        assert ms.get("display_only") is True
        assert ms.get("asof") == "2026-07-17"

    def test_world_state_absent_file(self, tmp_path):
        """Absent file → market_structure block has absent=True; no raise; no spurious gap."""
        from engine.neuralweb.world_state import build_world_state
        self._make_minimal_root(tmp_path)

        payload = build_world_state(root=tmp_path, now=_NOW)
        assert "market_structure" in payload
        ms = payload["market_structure"]
        assert ms.get("absent") is True
        assert ms.get("display_only") is True
        # The absent case must NOT add a gap entry (matches intl_risk pattern)
        gaps = payload.get("gaps") or []
        ms_gaps = [g for g in gaps if "market_structure" in str(g)]
        assert not ms_gaps, (
            f"Absent market_structure file should not add gap entry; got: {ms_gaps}"
        )


# ---------------------------------------------------------------------------
# 10-13: brief_context block tests
# ---------------------------------------------------------------------------

class TestBriefBlockMarketStructure:
    def _import(self):
        from engine.neuralweb.brief_context import _block_market_structure
        return _block_market_structure

    def _ws_with_ms(self, asof: str = "2026-07-17") -> dict:
        """Minimal world_state dict with market_structure sub-block."""
        return {
            "produced_at": f"{asof}T10:00:00Z",
            "market_structure": {
                "asof": asof,
                "display_only": True,
                "is_context_only": True,
                "gamma": {
                    "regime": "short",
                    "net_gex_bn": -11.06,
                    "dist_to_flip_pct": -0.33,
                    "days_in_regime": 1,
                },
                "systematic": {
                    "vc_state": "reducing",
                    "vc_alloc_bn": 320.5,
                    "vc_flow_5d_bn": -8.4,
                    "cta_state": "cutting",
                    "cta_z": -1.1,
                    "cta_flow_5d": -14.6,
                    "agreement": "aligned_cutting",
                },
                "vol": {"rv21": 0.1135, "rv63": 0.1284, "rv_cross_state": "calm", "vix_curve_slope": 2.23},
                "dispersion": {"cor1m": 6.38, "cor1m_regime": "dispersion", "cor1m_pctile_2y": 3.8},
                "state_changes": [{"field": "gamma.regime", "from": "long", "to": "short"}],
            },
        }

    def test_brief_block_happy(self):
        """Happy path: block has _tape_family, is_context_only, honesty_note."""
        fn = self._import()
        ws = self._ws_with_ms()
        block = fn(ws)
        assert block is not None
        assert block.get("_tape_family") == "market_structure"
        assert block.get("is_context_only") is True
        assert block.get("display_only") is True
        assert block.get("gamma_regime") == "short"
        assert block.get("agreement") == "aligned_cutting"
        assert block.get("cor1m_regime") == "dispersion"
        assert "honesty_note" in block

    def test_brief_block_absent_ws(self):
        """_block_market_structure(None) → None (drops cleanly)."""
        fn = self._import()
        assert fn(None) is None

    def test_brief_block_absent_ms(self):
        """world_state missing market_structure → None."""
        fn = self._import()
        ws = {"produced_at": "2026-07-17T10:00:00Z"}
        assert fn(ws) is None

    def test_brief_block_all_null(self):
        """All key fields null → None (budget-safe drop)."""
        fn = self._import()
        ws = {
            "market_structure": {
                "asof": "2026-07-17",
                "display_only": True,
                "gamma": {"regime": None, "dist_to_flip_pct": None, "days_in_regime": None},
                "systematic": {"vc_state": None, "cta_state": None, "agreement": None},
                "vol": {"rv_cross_state": None},
                "dispersion": {"cor1m_regime": None},
                "state_changes": None,
            }
        }
        assert fn(ws) is None

    def test_brief_block_tape_family_present(self):
        """_tape_family present on every non-None block (ADB-R3)."""
        fn = self._import()
        block = fn(self._ws_with_ms())
        assert block is not None
        assert "_tape_family" in block


# ---------------------------------------------------------------------------
# 14-18: mastermind_context tests
# ---------------------------------------------------------------------------

class TestMastermindMarketStructure:
    def test_lobe_key_registered(self):
        """LOBE_SUMMARIZERS contains 'market_structure'."""
        from engine.neuralweb.mastermind_context import LOBE_SUMMARIZERS
        assert "market_structure" in LOBE_SUMMARIZERS

    def test_artifact_ids(self):
        """_LOBE_TO_ARTIFACT_IDS['market_structure'] points at market-structure-latest."""
        from engine.neuralweb.mastermind_context import _LOBE_TO_ARTIFACT_IDS
        assert "market_structure" in _LOBE_TO_ARTIFACT_IDS
        assert "market-structure-latest" in _LOBE_TO_ARTIFACT_IDS["market_structure"]

    def test_standing_law_content(self):
        """_MARKET_STRUCTURE_STANDING_LAW embeds key law text (MSP-R2/R3 references)."""
        from engine.neuralweb.mastermind_context import _MARKET_STRUCTURE_STANDING_LAW
        law = _MARKET_STRUCTURE_STANDING_LAW
        assert "ILLEGAL" in law, "standing law must state fusion is ILLEGAL"
        assert "model estimates" in law, "standing law must state keys are model estimates"
        assert "context only" in law.lower(), "standing law must say context only"

    def test_summarize_happy(self, tmp_path):
        """_summarize_market_structure reads world_state correctly."""
        from engine.neuralweb.mastermind_context import _summarize_market_structure

        nw_dir = tmp_path / "data" / "neuralweb"
        nw_dir.mkdir(parents=True)
        ws = {
            "market_structure": {
                "asof": "2026-07-17",
                "display_only": True,
                "is_context_only": True,
                "gamma": {"regime": "short", "net_gex_bn": -11.06, "net_gex_pctile": 19.2,
                          "dist_to_flip_pct": -0.33, "days_in_regime": 1},
                "systematic": {"vc_state": "reducing", "vc_alloc_bn": 320.5, "vc_flow_5d_bn": -8.4,
                               "cta_state": "cutting", "cta_z": -1.1, "cta_flow_5d": -14.6,
                               "agreement": "aligned_cutting"},
                "vol": {"rv21": 0.1135, "rv63": 0.1284, "rv_cross_state": "calm",
                        "vix_curve_slope": 2.23},
                "dispersion": {"cor1m": 6.38, "cor1m_regime": "dispersion", "cor1m_pctile_2y": 3.8},
                "state_changes": None,
            }
        }
        (nw_dir / "world_state.json").write_text(json.dumps(ws), encoding="utf-8")

        lobe, gap = _summarize_market_structure(tmp_path)
        assert gap is None, f"Unexpected gap: {gap}"
        assert lobe.get("is_context_only") is True
        assert lobe.get("display_only") is True
        assert lobe.get("gamma_regime") == "short"
        assert lobe.get("agreement") == "aligned_cutting"
        assert lobe.get("cor1m_regime") == "dispersion"
        assert "standing_law" in lobe
        assert "honesty_note" in lobe

    def test_summarize_absent_ws(self, tmp_path):
        """Absent world_state → empty lobe + gap note."""
        from engine.neuralweb.mastermind_context import _summarize_market_structure
        lobe, gap = _summarize_market_structure(tmp_path)
        assert lobe == {}
        assert gap is not None
        assert "absent" in gap.lower() or "unreadable" in gap.lower()

    def test_summarize_absent_ms_block(self, tmp_path):
        """world_state present but market_structure absent → empty lobe + gap."""
        from engine.neuralweb.mastermind_context import _summarize_market_structure
        nw_dir = tmp_path / "data" / "neuralweb"
        nw_dir.mkdir(parents=True)
        (nw_dir / "world_state.json").write_text(json.dumps({"produced_at": "2026-07-17T10:00:00Z"}), encoding="utf-8")
        lobe, gap = _summarize_market_structure(tmp_path)
        assert lobe == {}
        assert gap is not None


# ---------------------------------------------------------------------------
# 19-21: confluence tests
# ---------------------------------------------------------------------------

class TestConfluenceMarketStructure:
    def test_subtype_registered(self):
        """'market_structure' in _MACRO_SUBTYPES."""
        from engine.neuralweb.confluence import _MACRO_SUBTYPES
        assert "market_structure" in _MACRO_SUBTYPES

    def test_node_built(self, tmp_path):
        """_build_macro_nodes builds macro:market_structure node when ms present."""
        from engine.neuralweb.confluence import _build_macro_nodes
        ws = {
            "market_structure": {
                "asof": "2026-07-17",
                "display_only": True,
                "is_context_only": True,
                "gamma": {"regime": "short"},
                "systematic": {"agreement": "aligned_cutting"},
                "vol": {"rv_cross_state": "calm"},
                "dispersion": {"cor1m_regime": "dispersion"},
                "state_changes": None,
            }
        }
        gaps: list[str] = []
        nodes = _build_macro_nodes(ws, gaps)
        node_ids = {n["id"] for n in nodes}
        assert "macro:market_structure" in node_ids, (
            f"Expected macro:market_structure node; got: {node_ids}"
        )
        ms_node = next(n for n in nodes if n["id"] == "macro:market_structure")
        assert ms_node["meta"].get("display_only") is True
        assert ms_node["meta"].get("regime") == "short"
        assert ms_node["meta"].get("agreement") == "aligned_cutting"
        assert ms_node["meta"].get("cor1m_regime") == "dispersion"

    def test_node_absent(self, tmp_path):
        """absent=True market_structure → no macro:market_structure node, no error."""
        from engine.neuralweb.confluence import _build_macro_nodes
        ws = {
            "market_structure": {
                "absent": True,
                "display_only": True,
            }
        }
        gaps: list[str] = []
        nodes = _build_macro_nodes(ws, gaps)
        node_ids = {n["id"] for n in nodes}
        assert "macro:market_structure" not in node_ids

    def test_node_missing_block(self):
        """world_state without market_structure → no macro:market_structure node."""
        from engine.neuralweb.confluence import _build_macro_nodes
        gaps: list[str] = []
        nodes = _build_macro_nodes({}, gaps)
        node_ids = {n["id"] for n in nodes}
        assert "macro:market_structure" not in node_ids
