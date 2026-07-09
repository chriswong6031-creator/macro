"""tests/test_theme_pathways.py — TIL W2 theme_pathways graph tests.

Covers:
  (1) Config graph integrity — every edge references declared nodes; no orphan nodes.
  (2) Crosswalk id validity — all theme_ids in config exist in theme_crosswalk.yml.
  (3) No bare ticker lists — basket_refs only (no "tickers:" lists in config).
  (4) Authority block assertions — forbidden_uses present, all promotion flags False.
  (5) Collision math on synthetic fixtures — purity_weight = 1/n_themes, correct grouping.
  (6) Banned directional language scan — no buy/sell/short/rotate now in labels/rationales.
  (7) Banned words from language law — no validated/caused/proved/proof.
  (8) Tolerant reads — missing config → null artifact + stale_legs, no crash.
  (9) run_stage() succeeds and writes both output files.
  (10) test_signal_bus_doc and test_dag_conformance compatibility assertions.

All tests are hermetic — tmp_path only; no live network calls.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PATHWAYS_CONFIG = _REPO_ROOT / "config" / "theme_pathways.yml"
_CROSSWALK_CONFIG = _REPO_ROOT / "config" / "theme_crosswalk.yml"

# ---------------------------------------------------------------------------
# Fixtures — load real config
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def crosswalk() -> dict:
    raw = yaml.safe_load(_CROSSWALK_CONFIG.read_text(encoding="utf-8"))
    assert raw and "themes" in raw, "theme_crosswalk.yml missing or malformed"
    return raw


@pytest.fixture(scope="module")
def pathways_config() -> dict:
    raw = yaml.safe_load(_PATHWAYS_CONFIG.read_text(encoding="utf-8"))
    assert raw and "themes" in raw, "theme_pathways.yml missing or malformed"
    return raw


@pytest.fixture(scope="module")
def valid_theme_ids(crosswalk: dict) -> set[str]:
    return {t["id"] for t in crosswalk["themes"] if "id" in t}


@pytest.fixture(scope="module")
def valid_basket_ids(crosswalk: dict) -> set[str]:
    ids: set[str] = set()
    for t in crosswalk.get("themes", []):
        ids.update(t.get("basket_ids", []))
    for b in crosswalk.get("unmapped_baskets", []):
        if "id" in b:
            ids.add(b["id"])
    return ids


# ---------------------------------------------------------------------------
# 1. Config graph integrity
# ---------------------------------------------------------------------------

class TestConfigGraphIntegrity:
    """Every edge must reference declared nodes; no orphan nodes; no orphan edges."""

    def test_all_edge_src_in_nodes(self, pathways_config: dict) -> None:
        """Every edge.src must refer to a declared node id."""
        errors: list[str] = []
        for theme in pathways_config["themes"]:
            tid = theme.get("theme_id", "?")
            node_ids = {n["id"] for n in theme.get("nodes", []) if "id" in n}
            for e in theme.get("edges", []):
                src = e.get("src", "")
                if src not in node_ids:
                    errors.append(f"theme={tid}: edge.src={src!r} not in nodes {node_ids}")
        assert not errors, "\n".join(errors)

    def test_all_edge_dst_in_nodes(self, pathways_config: dict) -> None:
        """Every edge.dst must refer to a declared node id."""
        errors: list[str] = []
        for theme in pathways_config["themes"]:
            tid = theme.get("theme_id", "?")
            node_ids = {n["id"] for n in theme.get("nodes", []) if "id" in n}
            for e in theme.get("edges", []):
                dst = e.get("dst", "")
                if dst not in node_ids:
                    errors.append(f"theme={tid}: edge.dst={dst!r} not in nodes {node_ids}")
        assert not errors, "\n".join(errors)

    def test_no_orphan_nodes(self, pathways_config: dict) -> None:
        """Every non-driver node should appear in at least one edge (src or dst)."""
        errors: list[str] = []
        for theme in pathways_config["themes"]:
            tid = theme.get("theme_id", "?")
            node_ids = {n["id"] for n in theme.get("nodes", []) if "id" in n}
            # Driver nodes (enabling_infrastructure) may have no incoming edge — allowed
            driver_nodes = {
                n["id"] for n in theme.get("nodes", [])
                if n.get("node_type") == "enabling_infrastructure"
            }
            edge_node_ids: set[str] = set()
            for e in theme.get("edges", []):
                edge_node_ids.add(e.get("src", ""))
                edge_node_ids.add(e.get("dst", ""))
            for nid in node_ids:
                if nid not in edge_node_ids and nid not in driver_nodes:
                    errors.append(f"theme={tid}: orphan node {nid!r} not referenced in any edge")
        assert not errors, "\n".join(errors)

    def test_node_ids_unique_within_theme(self, pathways_config: dict) -> None:
        """Node ids must be unique within each theme."""
        errors: list[str] = []
        for theme in pathways_config["themes"]:
            tid = theme.get("theme_id", "?")
            node_ids = [n["id"] for n in theme.get("nodes", []) if "id" in n]
            seen: set[str] = set()
            for nid in node_ids:
                if nid in seen:
                    errors.append(f"theme={tid}: duplicate node id {nid!r}")
                seen.add(nid)
        assert not errors, "\n".join(errors)

    def test_edge_order_values(self, pathways_config: dict) -> None:
        """Edge order must be 1, 2, or 3."""
        errors: list[str] = []
        for theme in pathways_config["themes"]:
            tid = theme.get("theme_id", "?")
            for e in theme.get("edges", []):
                order = e.get("order")
                if order not in (1, 2, 3):
                    errors.append(f"theme={tid}: edge {e.get('src')}→{e.get('dst')} order={order!r} invalid")
        assert not errors, "\n".join(errors)

    def test_edge_side_values(self, pathways_config: dict) -> None:
        """Edge side must be 'winner' or 'loser'."""
        errors: list[str] = []
        for theme in pathways_config["themes"]:
            tid = theme.get("theme_id", "?")
            for e in theme.get("edges", []):
                side = e.get("side")
                if side not in ("winner", "loser"):
                    errors.append(f"theme={tid}: edge {e.get('src')}→{e.get('dst')} side={side!r} invalid")
        assert not errors, "\n".join(errors)

    def test_edge_confidence_values(self, pathways_config: dict) -> None:
        """Edge confidence must be 'low', 'med', or 'high'."""
        errors: list[str] = []
        for theme in pathways_config["themes"]:
            tid = theme.get("theme_id", "?")
            for e in theme.get("edges", []):
                conf = e.get("confidence")
                if conf not in ("low", "med", "high"):
                    errors.append(f"theme={tid}: edge {e.get('src')}→{e.get('dst')} confidence={conf!r} invalid")
        assert not errors, "\n".join(errors)

    def test_node_type_values(self, pathways_config: dict) -> None:
        """Node types must be from the approved vocabulary."""
        valid_types = {
            "enabling_infrastructure", "bottleneck", "direct_beneficiary",
            "implementer", "downstream_winner", "impaired_incumbent", "second_order_risk",
        }
        errors: list[str] = []
        for theme in pathways_config["themes"]:
            tid = theme.get("theme_id", "?")
            for n in theme.get("nodes", []):
                nt = n.get("node_type", "")
                if nt not in valid_types:
                    errors.append(f"theme={tid}: node {n.get('id')!r} node_type={nt!r} invalid")
        assert not errors, "\n".join(errors)


# ---------------------------------------------------------------------------
# 2. Crosswalk id validity
# ---------------------------------------------------------------------------

class TestCrosswalkValidity:
    """All theme_ids in config must exist in theme_crosswalk.yml."""

    def test_all_theme_ids_in_crosswalk(
        self, pathways_config: dict, valid_theme_ids: set[str]
    ) -> None:
        """theme_ids in config must all be canonical crosswalk ids."""
        errors: list[str] = []
        for theme in pathways_config["themes"]:
            tid = theme.get("theme_id", "")
            if tid not in valid_theme_ids:
                errors.append(f"theme_id={tid!r} not in crosswalk valid ids {sorted(valid_theme_ids)[:5]}...")
        assert not errors, "\n".join(errors)

    def test_covers_all_18_foresight_themes(
        self, pathways_config: dict, valid_theme_ids: set[str]
    ) -> None:
        """Config should cover at least the 18 foresight-mapped themes."""
        config_ids = {t.get("theme_id") for t in pathways_config["themes"]}
        missing = valid_theme_ids - config_ids
        assert not missing, f"Config missing coverage for themes: {sorted(missing)}"

    def test_basket_refs_in_crosswalk(
        self, pathways_config: dict, valid_basket_ids: set[str]
    ) -> None:
        """All basket_refs must reference basket ids known to the crosswalk."""
        errors: list[str] = []
        for theme in pathways_config["themes"]:
            tid = theme.get("theme_id", "?")
            for node in theme.get("nodes", []):
                for bid in node.get("basket_refs", []) or []:
                    if bid not in valid_basket_ids:
                        errors.append(
                            f"theme={tid}: node={node.get('id')!r}: "
                            f"basket_ref={bid!r} not in crosswalk basket ids"
                        )
        assert not errors, "\n".join(errors)


# ---------------------------------------------------------------------------
# 3. No bare ticker lists
# ---------------------------------------------------------------------------

class TestNoBareTickerLists:
    """Config must not contain bare ticker lists; only basket_refs allowed."""

    def test_no_tickers_key_in_nodes(self, pathways_config: dict) -> None:
        """Nodes must not have a 'tickers' key."""
        errors: list[str] = []
        for theme in pathways_config["themes"]:
            tid = theme.get("theme_id", "?")
            for node in theme.get("nodes", []):
                if "tickers" in node:
                    errors.append(f"theme={tid}: node {node.get('id')!r} has bare 'tickers' key")
        assert not errors, "\n".join(errors)

    def test_no_members_key_in_nodes(self, pathways_config: dict) -> None:
        """Nodes must not have a 'members' key."""
        errors: list[str] = []
        for theme in pathways_config["themes"]:
            tid = theme.get("theme_id", "?")
            for node in theme.get("nodes", []):
                if "members" in node:
                    errors.append(f"theme={tid}: node {node.get('id')!r} has bare 'members' key")
        assert not errors, "\n".join(errors)

    def test_basket_refs_are_lists_not_strings(self, pathways_config: dict) -> None:
        """basket_refs must be lists, not bare strings."""
        errors: list[str] = []
        for theme in pathways_config["themes"]:
            tid = theme.get("theme_id", "?")
            for node in theme.get("nodes", []):
                refs = node.get("basket_refs")
                if refs is not None and not isinstance(refs, list):
                    errors.append(
                        f"theme={tid}: node {node.get('id')!r} basket_refs must be list, got {type(refs)}"
                    )
        assert not errors, "\n".join(errors)


# ---------------------------------------------------------------------------
# 4. Authority block
# ---------------------------------------------------------------------------

class TestAuthorityBlock:
    """Authority block must have correct forbidden_uses and all promotion flags False."""

    def test_forbidden_uses_present(self) -> None:
        """authority.forbidden_uses must include TI-R5 runtime shock escalation entry."""
        from engine.neuralweb.theme_pathways import AUTHORITY_BLOCK
        fu = AUTHORITY_BLOCK.get("forbidden_uses", [])
        assert any("TI-R5" in f for f in fu), (
            "forbidden_uses must include 'runtime shock-to-beneficiary escalation (TI-R5)'"
        )

    def test_promotion_flags_false(self) -> None:
        """All promotion flags must be False."""
        from engine.neuralweb.theme_pathways import AUTHORITY_BLOCK
        for flag in ("may_rank", "may_gate", "may_size", "may_escalate"):
            assert AUTHORITY_BLOCK.get(flag) is False, f"AUTHORITY_BLOCK.{flag} must be False"

    def test_is_context_only_true(self) -> None:
        from engine.neuralweb.theme_pathways import AUTHORITY_BLOCK
        assert AUTHORITY_BLOCK.get("is_context_only") is True

    def test_display_only_true(self) -> None:
        from engine.neuralweb.theme_pathways import AUTHORITY_BLOCK
        assert AUTHORITY_BLOCK.get("display_only") is True

    def test_not_a_signal_true(self) -> None:
        from engine.neuralweb.theme_pathways import AUTHORITY_BLOCK
        assert AUTHORITY_BLOCK.get("not_a_signal") is True

    def test_short_side_in_forbidden_uses(self) -> None:
        """Loser-leg / short-side direction must be in forbidden_uses."""
        from engine.neuralweb.theme_pathways import AUTHORITY_BLOCK
        fu = AUTHORITY_BLOCK.get("forbidden_uses", [])
        assert any("short-side" in f or "short side" in f for f in fu), (
            "forbidden_uses must include short-side direction entry"
        )

    def test_board_ordering_in_forbidden_uses(self) -> None:
        from engine.neuralweb.theme_pathways import AUTHORITY_BLOCK
        fu = AUTHORITY_BLOCK.get("forbidden_uses", [])
        assert any("board ordering" in f or "board_ordering" in f for f in fu), (
            "forbidden_uses must include board ordering"
        )


# ---------------------------------------------------------------------------
# 5. Collision math on synthetic fixtures
# ---------------------------------------------------------------------------

class TestCollisionMath:
    """Purity weight must equal 1/n_themes; correct grouping of multi-theme tickers."""

    def _make_membership(self, basket_assignments: dict[str, list[str]]) -> dict:
        """Build a minimal membership.json structure.

        basket_assignments: {basket_id: [ticker, ...]}
        """
        baskets: dict[str, Any] = {}
        for bid, tickers in basket_assignments.items():
            baskets[bid] = {
                "name": bid, "name_zh": bid,
                "members": [{"ticker": t, "added": "2024-01-01", "removed": None} for t in tickers],
            }
        return {"baskets": baskets}

    def test_purity_weight_single_theme(self) -> None:
        """Ticker in 1 theme → not in collision map."""
        from engine.neuralweb.theme_pathways import (
            _build_ticker_basket_index, _build_basket_to_themes, _build_collision_map,
        )
        membership = self._make_membership({"basket_a": ["TICK1", "TICK2"]})
        theme_basket_map = {"theme_x": ["basket_a"]}
        basket_to_themes = _build_basket_to_themes(theme_basket_map)
        idx = _build_ticker_basket_index(membership, {"basket_a"}, theme_basket_map)
        collisions = _build_collision_map(idx, basket_to_themes)
        tickers_in_collision = {c["ticker"] for c in collisions}
        assert "TICK1" not in tickers_in_collision
        assert "TICK2" not in tickers_in_collision

    def test_purity_weight_two_themes(self) -> None:
        """Ticker in 2 theme baskets → purity_weight = 0.5."""
        from engine.neuralweb.theme_pathways import (
            _build_ticker_basket_index, _build_basket_to_themes, _build_collision_map,
        )
        membership = self._make_membership({
            "basket_a": ["SHARED", "ONLY_A"],
            "basket_b": ["SHARED", "ONLY_B"],
        })
        theme_basket_map = {
            "theme_x": ["basket_a"],
            "theme_y": ["basket_b"],
        }
        basket_to_themes = _build_basket_to_themes(theme_basket_map)
        idx = _build_ticker_basket_index(membership, {"basket_a", "basket_b"}, theme_basket_map)
        collisions = _build_collision_map(idx, basket_to_themes)
        shared = next((c for c in collisions if c["ticker"] == "SHARED"), None)
        assert shared is not None, "SHARED ticker should appear in collision map"
        assert shared["n_themes"] == 2
        assert abs(shared["purity_weight"] - 0.5) < 1e-6
        assert set(shared["themes"]) == {"theme_x", "theme_y"}

    def test_purity_weight_three_themes(self) -> None:
        """Ticker in 3 theme baskets → purity_weight = 1/3."""
        from engine.neuralweb.theme_pathways import (
            _build_ticker_basket_index, _build_basket_to_themes, _build_collision_map,
        )
        membership = self._make_membership({
            "ba": ["MULTI"], "bb": ["MULTI"], "bc": ["MULTI"],
        })
        theme_basket_map = {
            "t1": ["ba"], "t2": ["bb"], "t3": ["bc"],
        }
        basket_to_themes = _build_basket_to_themes(theme_basket_map)
        idx = _build_ticker_basket_index(membership, {"ba", "bb", "bc"}, theme_basket_map)
        collisions = _build_collision_map(idx, basket_to_themes)
        multi = next((c for c in collisions if c["ticker"] == "MULTI"), None)
        assert multi is not None
        assert multi["n_themes"] == 3
        assert abs(multi["purity_weight"] - (1.0 / 3)) < 1e-4

    def test_removed_members_excluded(self) -> None:
        """Members with removed != None must not appear in collision map."""
        from engine.neuralweb.theme_pathways import (
            _build_ticker_basket_index, _build_basket_to_themes, _build_collision_map,
        )
        membership: dict[str, Any] = {
            "baskets": {
                "basket_a": {
                    "members": [
                        {"ticker": "REMOVED", "added": "2024-01-01", "removed": "2025-01-01"},
                        {"ticker": "ACTIVE", "added": "2024-01-01", "removed": None},
                    ],
                },
                "basket_b": {
                    "members": [
                        {"ticker": "REMOVED", "added": "2024-01-01", "removed": "2025-01-01"},
                        {"ticker": "ACTIVE", "added": "2024-01-01", "removed": None},
                    ],
                },
            }
        }
        theme_basket_map = {"theme_x": ["basket_a"], "theme_y": ["basket_b"]}
        basket_to_themes = _build_basket_to_themes(theme_basket_map)
        idx = _build_ticker_basket_index(membership, {"basket_a", "basket_b"}, theme_basket_map)
        collisions = _build_collision_map(idx, basket_to_themes)
        tickers = {c["ticker"] for c in collisions}
        assert "REMOVED" not in tickers, "Removed members must not appear in collision map"
        assert "ACTIVE" in tickers, "Active members in 2+ themes should appear in collision map"

    def test_weight_share_sums_to_one(self) -> None:
        """sum(weight_share_by_theme.values()) * n_themes must equal n_themes."""
        from engine.neuralweb.theme_pathways import (
            _build_ticker_basket_index, _build_basket_to_themes, _build_collision_map,
        )
        membership = self._make_membership({
            "ba": ["X"], "bb": ["X"], "bc": ["X"], "bd": ["X"],
        })
        theme_basket_map = {f"t{i}": [f"b{c}"] for i, c in enumerate("abcd")}
        basket_to_themes = _build_basket_to_themes(theme_basket_map)
        idx = _build_ticker_basket_index(membership, set("abcd"), theme_basket_map)
        # Need proper basket ids
        membership2 = self._make_membership({
            "b0": ["X"], "b1": ["X"], "b2": ["X"], "b3": ["X"],
        })
        theme_basket_map2 = {f"t{i}": [f"b{i}"] for i in range(4)}
        basket_to_themes2 = _build_basket_to_themes(theme_basket_map2)
        idx2 = _build_ticker_basket_index(membership2, {f"b{i}" for i in range(4)}, theme_basket_map2)
        collisions = _build_collision_map(idx2, basket_to_themes2)
        c = next((x for x in collisions if x["ticker"] == "X"), None)
        assert c is not None
        total_weight = sum(c["weight_share_by_theme"].values())
        expected = c["purity_weight"] * c["n_themes"]
        assert abs(total_weight - expected) < 1e-6

    def test_collision_map_sorted_by_n_themes_desc(self) -> None:
        """Collision map must be sorted by n_themes descending."""
        from engine.neuralweb.theme_pathways import (
            _build_ticker_basket_index, _build_basket_to_themes, _build_collision_map,
        )
        membership = self._make_membership({
            "ba": ["TWO", "THREE"], "bb": ["TWO", "THREE"], "bc": ["THREE"],
        })
        theme_basket_map = {
            "t1": ["ba"], "t2": ["bb"], "t3": ["bc"],
        }
        basket_to_themes = _build_basket_to_themes(theme_basket_map)
        idx = _build_ticker_basket_index(membership, {"ba", "bb", "bc"}, theme_basket_map)
        collisions = _build_collision_map(idx, basket_to_themes)
        n_themes_seq = [c["n_themes"] for c in collisions]
        assert n_themes_seq == sorted(n_themes_seq, reverse=True), (
            f"Collision map should be sorted by n_themes descending; got {n_themes_seq}"
        )


# ---------------------------------------------------------------------------
# 6 & 7. Banned directional language and language law words
# ---------------------------------------------------------------------------

class TestLanguageLaw:
    """No buy/sell/short/rotate now in labels/rationales; no validated/caused/proved/proof."""

    _DIRECTIONAL_BANNED = ("buy", "sell", "short", "rotate now")
    _LANGUAGE_LAW_BANNED = ("validated", "caused", "proved", "proof")
    _ALL_BANNED = _DIRECTIONAL_BANNED + _LANGUAGE_LAW_BANNED

    def _collect_text_fields(self, pathways_config: dict) -> list[tuple[str, str, str]]:
        """Return [(theme_id, field_path, text_value)] for all text fields."""
        results: list[tuple[str, str, str]] = []
        for theme in pathways_config["themes"]:
            tid = theme.get("theme_id", "?")
            for node in theme.get("nodes", []):
                nid = node.get("id", "?")
                for field in ("label_en", "label_zh", "rationale"):
                    v = node.get(field, "")
                    if v:
                        results.append((tid, f"node.{nid}.{field}", v))
            for i, e in enumerate(theme.get("edges", [])):
                v = e.get("rationale", "")
                if v:
                    results.append((tid, f"edge[{i}].rationale", v))
        return results

    def test_no_directional_banned_words(self, pathways_config: dict) -> None:
        """No buy/sell/short/rotate now in any label or rationale."""
        errors: list[str] = []
        for tid, field, text in self._collect_text_fields(pathways_config):
            tl = text.lower()
            for word in self._DIRECTIONAL_BANNED:
                # Use word-boundary-aware check for short words
                if word in ("buy", "sell") and word in tl.split():
                    errors.append(f"theme={tid} {field}: contains banned word '{word}'")
                elif word not in ("buy", "sell") and word in tl:
                    errors.append(f"theme={tid} {field}: contains banned phrase '{word}'")
        assert not errors, "\n".join(errors)

    def test_no_language_law_words(self, pathways_config: dict) -> None:
        """No validated/caused/proved/proof in any text field."""
        errors: list[str] = []
        for tid, field, text in self._collect_text_fields(pathways_config):
            tl = text.lower()
            for word in self._LANGUAGE_LAW_BANNED:
                if word in tl:
                    errors.append(f"theme={tid} {field}: contains banned word '{word}'")
        assert not errors, "\n".join(errors)

    def test_engine_sanitize_function_exists(self) -> None:
        """_check_banned_words must exist in the engine module."""
        from engine.neuralweb.theme_pathways import _check_banned_words
        assert callable(_check_banned_words)

    def test_engine_sanitize_detects_validated(self) -> None:
        from engine.neuralweb.theme_pathways import _check_banned_words
        found = _check_banned_words("This is a validated signal.")
        assert "validated" in found

    def test_engine_sanitize_detects_short(self) -> None:
        from engine.neuralweb.theme_pathways import _check_banned_words
        found = _check_banned_words("short the sector immediately")
        assert "short" in found

    def test_engine_sanitize_clean_text(self) -> None:
        from engine.neuralweb.theme_pathways import _check_banned_words
        found = _check_banned_words("Basket members benefit from structural supply constraints.")
        assert not found


# ---------------------------------------------------------------------------
# 8. Tolerant reads — missing config
# ---------------------------------------------------------------------------

class TestTolerantReads:
    """Missing or corrupt inputs → honest null artifact + stale_legs, never crash."""

    def _make_minimal_repo(self, tmp_path: Path) -> Path:
        """Copy crosswalk and membership into tmp_path for a hermetic test repo."""
        import shutil
        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir(parents=True)
        # Copy crosswalk
        shutil.copy(_CROSSWALK_CONFIG, cfg_dir / "theme_crosswalk.yml")
        # Copy pathways config
        shutil.copy(_PATHWAYS_CONFIG, cfg_dir / "theme_pathways.yml")
        # Copy membership
        src_mem = _REPO_ROOT / "data" / "baskets" / "membership.json"
        if src_mem.exists():
            data_dir = tmp_path / "data" / "baskets"
            data_dir.mkdir(parents=True)
            shutil.copy(src_mem, data_dir / "membership.json")
        return tmp_path

    def test_missing_pathways_config_returns_null(self, tmp_path: Path) -> None:
        """Missing config/theme_pathways.yml → null artifact, no exception."""
        from engine.neuralweb.theme_pathways import compile as pathway_compile
        root = tmp_path / "empty_repo"
        root.mkdir()
        (root / "config").mkdir()
        # Only crosswalk, no pathways
        shutil.copy(_CROSSWALK_CONFIG, root / "config" / "theme_crosswalk.yml")
        result = pathway_compile(root=root)
        assert result["schema"] == "neuralweb.theme_pathways.v1"
        assert result["theme_count"] == 0
        assert result["theme_pathways"] == []
        assert any("config" in s or "unavailable" in s for s in result["stale_legs"])

    def test_missing_crosswalk_still_compiles(self, tmp_path: Path) -> None:
        """Missing crosswalk → stale_legs but no crash; theme_pathways may be empty."""
        from engine.neuralweb.theme_pathways import compile as pathway_compile
        root = tmp_path / "no_crosswalk"
        root.mkdir()
        cfg_dir = root / "config"
        cfg_dir.mkdir()
        shutil.copy(_PATHWAYS_CONFIG, cfg_dir / "theme_pathways.yml")
        # No crosswalk
        result = pathway_compile(root=root)
        assert result["schema"] == "neuralweb.theme_pathways.v1"
        # May or may not have themes (unknown theme ids → skipped) but no crash
        assert isinstance(result["theme_pathways"], list)
        assert isinstance(result["stale_legs"], list)

    def test_missing_radar_adds_stale_leg(self, tmp_path: Path) -> None:
        """Missing radar.json → stale_legs entry, themes still compile."""
        from engine.neuralweb.theme_pathways import compile as pathway_compile
        root = self._make_minimal_repo(tmp_path)
        # Do not create radar.json
        result = pathway_compile(root=root)
        stale_text = " ".join(result.get("stale_legs", []))
        assert "radar" in stale_text.lower(), (
            f"Expected 'radar' in stale_legs; got: {result.get('stale_legs')}"
        )

    def test_missing_foresight_adds_stale_leg(self, tmp_path: Path) -> None:
        """Missing foresight_cascade.json → stale_legs entry, themes still compile."""
        from engine.neuralweb.theme_pathways import compile as pathway_compile
        root = self._make_minimal_repo(tmp_path)
        result = pathway_compile(root=root)
        stale_text = " ".join(result.get("stale_legs", []))
        assert "foresight" in stale_text.lower(), (
            f"Expected 'foresight' in stale_legs; got: {result.get('stale_legs')}"
        )

    def test_authority_block_in_null_artifact(self, tmp_path: Path) -> None:
        """Even the null artifact must carry the correct authority block."""
        from engine.neuralweb.theme_pathways import compile as pathway_compile
        root = tmp_path / "null_test"
        root.mkdir()
        result = pathway_compile(root=root)
        auth = result.get("authority", {})
        assert auth.get("may_rank") is False
        assert auth.get("may_gate") is False
        assert auth.get("may_size") is False
        assert auth.get("may_escalate") is False
        assert auth.get("display_only") is True

    def test_compile_never_raises(self, tmp_path: Path) -> None:
        """compile() must never raise regardless of file system state."""
        from engine.neuralweb.theme_pathways import compile as pathway_compile
        # Completely empty directory
        result = pathway_compile(root=tmp_path)
        assert isinstance(result, dict)
        assert result["schema"] == "neuralweb.theme_pathways.v1"


# ---------------------------------------------------------------------------
# 9. run_stage writes output files
# ---------------------------------------------------------------------------

class TestRunStage:
    """run_stage() must write both output files without raising."""

    def _make_minimal_repo(self, tmp_path: Path) -> Path:
        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir(parents=True)
        shutil.copy(_CROSSWALK_CONFIG, cfg_dir / "theme_crosswalk.yml")
        shutil.copy(_PATHWAYS_CONFIG, cfg_dir / "theme_pathways.yml")
        src_mem = _REPO_ROOT / "data" / "baskets" / "membership.json"
        if src_mem.exists():
            data_dir = tmp_path / "data" / "baskets"
            data_dir.mkdir(parents=True)
            shutil.copy(src_mem, data_dir / "membership.json")
        return tmp_path

    def test_run_stage_does_not_raise(self, tmp_path: Path) -> None:
        """run_stage() must complete without raising."""
        from engine.neuralweb.theme_pathways import run_stage
        root = self._make_minimal_repo(tmp_path)
        run_stage(root=root)  # must not raise

    def test_run_stage_writes_data_json(self, tmp_path: Path) -> None:
        """run_stage() must write data/neuralweb/theme_pathways.json."""
        from engine.neuralweb.theme_pathways import run_stage
        root = self._make_minimal_repo(tmp_path)
        run_stage(root=root)
        out = root / "data" / "neuralweb" / "theme_pathways.json"
        assert out.exists(), f"Expected {out} to exist after run_stage()"

    def test_run_stage_writes_site_json(self, tmp_path: Path) -> None:
        """run_stage() must write site/neuralwebdata/theme_pathways.json."""
        from engine.neuralweb.theme_pathways import run_stage
        root = self._make_minimal_repo(tmp_path)
        run_stage(root=root)
        out = root / "site" / "neuralwebdata" / "theme_pathways.json"
        assert out.exists(), f"Expected {out} to exist after run_stage()"

    def test_run_stage_output_valid_json(self, tmp_path: Path) -> None:
        """Output files must contain valid JSON."""
        from engine.neuralweb.theme_pathways import run_stage
        root = self._make_minimal_repo(tmp_path)
        run_stage(root=root)
        for rel in (
            "data/neuralweb/theme_pathways.json",
            "site/neuralwebdata/theme_pathways.json",
        ):
            p = root / rel
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                assert data["schema"] == "neuralweb.theme_pathways.v1"
                assert "authority" in data
                assert "theme_pathways" in data

    def test_run_stage_output_has_all_18_themes(self, tmp_path: Path) -> None:
        """With real config, run_stage should output all 18 canonical themes."""
        from engine.neuralweb.theme_pathways import run_stage
        root = self._make_minimal_repo(tmp_path)
        run_stage(root=root)
        out = root / "data" / "neuralweb" / "theme_pathways.json"
        if out.exists():
            data = json.loads(out.read_text(encoding="utf-8"))
            assert data.get("theme_count", 0) == 18, (
                f"Expected 18 themes, got {data.get('theme_count')}; "
                f"stale_legs: {data.get('stale_legs')}"
            )

    def test_run_stage_collision_map_present(self, tmp_path: Path) -> None:
        """Output must include cross_theme_collision_map."""
        from engine.neuralweb.theme_pathways import run_stage
        root = self._make_minimal_repo(tmp_path)
        run_stage(root=root)
        out = root / "data" / "neuralweb" / "theme_pathways.json"
        if out.exists():
            data = json.loads(out.read_text(encoding="utf-8"))
            cmap = data.get("cross_theme_collision_map", {})
            assert "collisions" in cmap
            assert "collision_count" in cmap

    def test_run_stage_stale_legs_is_list(self, tmp_path: Path) -> None:
        """stale_legs must always be a list (never None)."""
        from engine.neuralweb.theme_pathways import run_stage
        root = self._make_minimal_repo(tmp_path)
        run_stage(root=root)
        out = root / "data" / "neuralweb" / "theme_pathways.json"
        if out.exists():
            data = json.loads(out.read_text(encoding="utf-8"))
            assert isinstance(data.get("stale_legs"), list)

    def test_run_stage_from_empty_dir_no_raise(self, tmp_path: Path) -> None:
        """run_stage from a completely empty directory must not raise."""
        from engine.neuralweb.theme_pathways import run_stage
        run_stage(root=tmp_path)  # must not raise


# ---------------------------------------------------------------------------
# 10. Real compile output (live artifacts present)
# ---------------------------------------------------------------------------

class TestLiveCompile:
    """Integration test against real repo artifacts (skipped if artifacts absent)."""

    @pytest.mark.skipif(
        not (_REPO_ROOT / "config" / "theme_pathways.yml").exists(),
        reason="config/theme_pathways.yml not present",
    )
    def test_compile_schema(self) -> None:
        """compile() against real repo must return correct schema."""
        from engine.neuralweb.theme_pathways import compile as pathway_compile
        result = pathway_compile(root=_REPO_ROOT)
        assert result["schema"] == "neuralweb.theme_pathways.v1"

    @pytest.mark.skipif(
        not (_REPO_ROOT / "config" / "theme_pathways.yml").exists(),
        reason="config/theme_pathways.yml not present",
    )
    def test_compile_authority_block(self) -> None:
        """compile() against real repo must have correct authority block."""
        from engine.neuralweb.theme_pathways import compile as pathway_compile
        result = pathway_compile(root=_REPO_ROOT)
        auth = result["authority"]
        assert auth["may_rank"] is False
        assert auth["may_gate"] is False
        assert auth["may_size"] is False
        assert auth["may_escalate"] is False
        assert auth["is_context_only"] is True

    @pytest.mark.skipif(
        not (_REPO_ROOT / "config" / "theme_pathways.yml").exists(),
        reason="config/theme_pathways.yml not present",
    )
    def test_compile_collision_map_structure(self) -> None:
        """Collision map must have the required keys."""
        from engine.neuralweb.theme_pathways import compile as pathway_compile
        result = pathway_compile(root=_REPO_ROOT)
        cmap = result.get("cross_theme_collision_map", {})
        assert "collision_count" in cmap
        assert "collisions" in cmap
        for c in cmap["collisions"]:
            assert "ticker" in c
            assert "themes" in c
            assert "purity_weight" in c
            assert "weight_share_by_theme" in c
            assert "n_themes" in c
            assert c["n_themes"] >= 2

    @pytest.mark.skipif(
        not (_REPO_ROOT / "config" / "theme_pathways.yml").exists(),
        reason="config/theme_pathways.yml not present",
    )
    def test_compile_theme_node_structure(self) -> None:
        """Each compiled theme must have required structural keys."""
        from engine.neuralweb.theme_pathways import compile as pathway_compile
        result = pathway_compile(root=_REPO_ROOT)
        for t in result.get("theme_pathways", []):
            assert "theme_id" in t
            assert "nodes" in t
            assert "edges" in t
            assert isinstance(t["nodes"], list)
            assert isinstance(t["edges"], list)
            for n in t["nodes"]:
                assert "id" in n
                assert "node_type" in n
                assert "label_en" in n
                assert "label_zh" in n
                assert "basket_refs" in n
                assert isinstance(n["basket_refs"], list)
