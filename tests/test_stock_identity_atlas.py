"""Stock Identity W1 — the exclusion laws, mechanically (registration §13).

Four things this program promised that a reader should not have to take on trust:

1. **No expert-fit content anywhere in W1** (masterplan §16.9). No expert identifier,
   fit metric, ordering, or "best" field exists as a key, column, or code identifier.
2. **Zero authority on every artifact.** Every JSON under ``data/stock_identity/``
   carries a complete all-false authority block; every parquet carries the same as
   columns.
3. **No per-name blind-arm row.** Blind names exist in the partition manifest's
   membership list and as anonymous denominators — nowhere else.
4. **No G-8 import.** ``engine/stock_identity/**`` imports no gate-chain, signal, or
   ranking module, and never imports from ``scripts/``.

Plus the hashes: the constants file recomputes its own fingerprint spec hash and
carries every rule it claims to.

Offline; reads committed artifacts and walks source with ``ast``. No plotting stack,
no network, no universe sweep.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from engine.stock_identity import fingerprint as fp
from engine.stock_identity.authority import AUTHORITY_KEYS, is_zero_authority

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "engine" / "stock_identity"
DATA = ROOT / "data" / "stock_identity"
MANIFEST = DATA / "partition" / "partition_manifest_v1.json"
CONSTANTS = DATA / "constants" / "si_constants_v1.json"

#: Field/identifier tokens that would mean W1 had grown an expert-fit result.
#: Matched against KEYS, COLUMN NAMES and CODE IDENTIFIERS only — never against prose,
#: because the census and the dossiers must be free to say "no expert data exists in
#: W1 by law", and a test that punished honest wording would push the docs to lie.
BANNED_TOKENS = ("expert", "fit_score", "expert_rank", "best_")

#: Modules the Identity Atlas must never import (the G-8 protected set).
FORBIDDEN_IMPORTS = (
    "engine.entry_signal",
    "engine.signal_gate",
    "engine.confluence_tiers",
    "engine.signal_quality",
    "engine.washout_turn",
    "engine.mtf_upturn",
    "engine.stock_personality",
    "engine.oracle.personality_context",
    "engine.entry_radar",
)
FORBIDDEN_PREFIXES = ("engine.prophet_", "engine.prophet.", "scripts.", "scripts")


def _json_files() -> list[Path]:
    return sorted(DATA.rglob("*.json")) if DATA.exists() else []


def _parquet_files() -> list[Path]:
    return sorted(DATA.rglob("*.parquet")) if DATA.exists() else []


def _walk_keys(obj, out: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k))
            _walk_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_keys(v, out)


def _manifest() -> dict:
    if not MANIFEST.exists():
        pytest.skip("partition manifest not present in this checkout")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _constants() -> dict:
    if not CONSTANTS.exists():
        pytest.skip("constants file not present in this checkout")
    return json.loads(CONSTANTS.read_text(encoding="utf-8"))


class TestNoExpertFitContent:
    def test_no_banned_token_appears_as_a_json_key(self):
        files = _json_files()
        if not files:
            pytest.skip("no artifacts in this checkout")
        for p in files:
            keys: list[str] = []
            _walk_keys(json.loads(p.read_text(encoding="utf-8")), keys)
            for k in keys:
                low = k.lower()
                for token in BANNED_TOKENS:
                    assert token not in low, f"{p.name}: key {k!r} carries {token!r}"

    def test_no_banned_token_appears_as_a_parquet_column(self):
        files = _parquet_files()
        if not files:
            pytest.skip("no artifacts in this checkout")
        for p in files:
            cols = list(pd.read_parquet(p).columns)
            for c in cols:
                low = str(c).lower()
                for token in BANNED_TOKENS:
                    assert token not in low, f"{p.name}: column {c!r} carries {token!r}"

    def test_no_banned_token_appears_as_a_code_identifier(self):
        for src in sorted(PKG.glob("*.py")):
            tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
            names: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    names.append(node.id)
                elif isinstance(node, ast.Attribute):
                    names.append(node.attr)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.append(node.name)
                elif isinstance(node, ast.arg):
                    names.append(node.arg)
            for n in names:
                low = n.lower()
                for token in BANNED_TOKENS:
                    assert token not in low, f"{src.name}: identifier {n!r} carries {token!r}"

    def test_fingerprint_spec_declares_no_expert_feature(self):
        for f in fp.ALL_FEATURES:
            low = f["name"].lower()
            for token in BANNED_TOKENS:
                assert token not in low


class TestZeroAuthority:
    def test_every_json_artifact_carries_an_all_false_authority_block(self):
        files = _json_files()
        if not files:
            pytest.skip("no artifacts in this checkout")
        for p in files:
            payload = json.loads(p.read_text(encoding="utf-8"))
            assert isinstance(payload, dict), p.name
            assert is_zero_authority(payload), f"{p.name} lacks a complete all-false block"

    def test_every_parquet_artifact_carries_authority_columns(self):
        files = [p for p in _parquet_files() if p.parent.name != "ohlcv"]
        if not files:
            pytest.skip("no artifacts in this checkout")
        for p in files:
            df = pd.read_parquet(p)
            for key in AUTHORITY_KEYS:
                col = f"authority_{key}"
                assert col in df.columns, f"{p.name} missing {col}"
                assert not df[col].any(), f"{p.name}: {col} is not all-false"

    def test_the_ohlcv_store_declares_authority_in_its_manifest(self):
        # The collected price parquets are raw history, so the block rides on the
        # store's manifest rather than on every price row.
        m = DATA / "ohlcv" / "manifest.json"
        if not m.exists():
            pytest.skip("program-owned ohlcv store not present")
        assert is_zero_authority(json.loads(m.read_text(encoding="utf-8")))


class TestBlindArmIsInvisible:
    """Blind names may appear in the membership list and in rank denominators only."""

    def _derived_artifacts(self) -> list[Path]:
        return [
            DATA / "fingerprints" / "pilot_fingerprint_v0.parquet",
            DATA / "episodes" / "pilot_episode_catalog_v0.parquet",
            DATA / "state" / "pilot_state_daily.parquet",
            DATA / "census" / "coverage_census_v0.parquet",
        ]

    def test_no_blind_name_has_a_row_in_any_derived_artifact(self):
        m = _manifest()
        blind = set(m["blind_arm"]["members"])
        assert blind
        checked = 0
        for p in self._derived_artifacts():
            if not p.exists():
                continue
            df = pd.read_parquet(p)
            if "symbol" not in df.columns:
                continue
            leaked = blind & set(df["symbol"].astype(str))
            assert not leaked, f"{p.name} carries blind rows: {sorted(leaked)[:5]}"
            checked += 1
        if checked == 0:
            pytest.skip("no derived artifacts in this checkout")

    def test_no_per_name_blind_episode_json_exists(self):
        m = _manifest()
        blind = set(m["blind_arm"]["members"])
        pilot_dir = DATA / "episodes" / "pilot"
        if not pilot_dir.exists():
            pytest.skip("pilot episode directory not present")
        for p in pilot_dir.glob("*.json"):
            assert p.stem not in blind, f"blind name {p.stem} has a per-name artifact"

    def test_the_census_states_how_many_names_it_excluded_as_blind(self):
        md = DATA / "census" / "coverage_census_v0.md"
        if not md.exists():
            pytest.skip("census markdown not present")
        text = md.read_text(encoding="utf-8")
        m = _manifest()
        assert "Excluded as blind evaluation arm" in text
        assert str(len(m["blind_arm"]["members"])) in text


class TestImportDiscipline:
    def test_package_imports_no_protected_module(self):
        for src in sorted(PKG.glob("*.py")):
            tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
            mods: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods.extend(a.name for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods.append(node.module)
            for mod in mods:
                assert mod not in FORBIDDEN_IMPORTS, f"{src.name} imports {mod}"
                for prefix in FORBIDDEN_PREFIXES:
                    assert not mod.startswith(prefix), f"{src.name} imports {mod}"

    def test_package_imports_nothing_from_scripts(self):
        for src in sorted(PKG.glob("*.py")):
            text = src.read_text(encoding="utf-8")
            assert "from scripts" not in text, src.name
            assert "import scripts" not in text, src.name

    def test_matplotlib_is_not_imported_at_module_level(self):
        # The dossier module must stay importable where no plotting stack exists.
        src = PKG / "dossier.py"
        tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = (
                    node.module if isinstance(node, ast.ImportFrom)
                    else node.names[0].name
                )
                assert not str(mod).startswith("matplotlib"), "matplotlib imported eagerly"


class TestConstantsFile:
    REQUIRED = (
        "X", "Y", "N", "k", "z", "M", "m", "D1", "D2", "theta_dw", "theta_bd",
        "theta_pb", "theta_up", "J", "V", "E", "R", "g", "w", "delta", "theta_fs",
        "P_pre", "S_reclaim",
    )

    def test_every_declared_constant_is_present_with_a_value_and_a_rule(self):
        c = _constants()
        for key in self.REQUIRED:
            assert key in c["values"], f"missing value {key}"
            assert key in c["rules"], f"missing rule text for {key}"
            assert key in c["receipts"], f"missing receipt for {key}"
            assert c["receipts"][key]["value"] == c["values"][key]

    def test_declared_constants_are_marked_as_declared_in_their_receipts(self):
        c = _constants()
        for key, r in c["receipts"].items():
            if r.get("declared"):
                assert "declared, not partition-computed" in r.get("note", ""), key
                assert "declared, not partition-computed" in c["rules"][key], key

    def test_partition_computed_constants_record_their_raw_statistic(self):
        c = _constants()
        for key, r in c["receipts"].items():
            if r.get("declared"):
                continue
            has_raw = ("raw" in r) or ("raw_pct" in r) or ("grid" in r)
            assert has_raw, f"{key} claims to be partition-computed but shows no statistic"

    def test_constants_recompute_the_fingerprint_spec_hash(self):
        c = _constants()
        assert c["fingerprint_spec_hash"] == fp.spec_hash()

    def test_constants_recompute_their_own_spec_hash(self):
        # The constants' spec hash must cover the frozen DECISIONS (version, values, rule
        # text) and nothing that moves on a re-read: a hash that folded in the receipts'
        # sample counts would change without any constant changing, which would make
        # "constants never change after sealing" unverifiable.
        c = _constants()
        payload = {
            "version": c["version"],
            "partition_name": c["partition_name"],
            "values": c["values"],
            "rules": c["rules"],
        }
        recomputed = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        assert recomputed == c["si_constants_spec_hash"]

    def test_constants_pin_the_partition_hashes(self):
        c, m = _constants(), _manifest()
        assert c["partition_procedure_sha256"] == m["partition_procedure_sha256"]
        assert c["calibration_sha256"] == m["calibration_partition"]["calibration_sha256"]
        assert c["blind_sha256"] == m["blind_arm"]["blind_sha256"]
        assert c["universe_sha256"] == m["universe"]["universe_sha256"]

    def test_the_sensitivity_grid_is_registered_and_diagnostic_only(self):
        c = _constants()
        grid = c["sensitivity_grid"]
        assert grid["trial_family"] == "stock_identity_w1_calibration"
        assert "BEFORE running" in grid["status"]
        assert "diagnostic only" in grid["status"]
        assert set(grid["keys"]) == {"X", "N", "k", "z", "theta_dw", "g"}

    def test_calibration_history_stops_short_of_asof(self):
        c = _constants()
        assert pd.Timestamp(c["calibration_history_cutoff"]) < pd.Timestamp(c["asof"])


class TestManifestHashes:
    def test_manifest_pins_the_live_fingerprint_spec_hash(self):
        assert _manifest()["fingerprint_spec_hash"] == fp.spec_hash()

    def test_manifest_records_the_hygiene_exclusions_it_applied(self):
        m = _manifest()
        assert "hygiene_excluded_from_compute" in m

    def test_pilot_receipts_carry_the_rule_that_chose_each_pick(self):
        m = _manifest()
        r = m["pilot"]["receipts"]
        for key in ("recent_ipo", "secular_decliner", "dead_names"):
            assert key in r, key
        assert "rule" in r["recent_ipo"] and r["recent_ipo"]["pick"]
        assert "rule" in r["secular_decliner"] and r["secular_decliner"]["pick"]

    def test_dead_name_shortfall_is_disclosed_rather_than_filled(self):
        # W1's measured position: the allowed planes retain no ceased tapes. If that is
        # ever fixed the status flips to SATISFIED, but it must never be quietly
        # populated from a prohibited plane or by relabeling a live name.
        r = _manifest()["pilot"]["receipts"]["dead_names"]
        if r["members"]:
            assert r["status"] == "SATISFIED"
        else:
            assert r["status"].startswith("BLOCKED")
            assert "sources_checked" in r and "consequence" in r
