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
import copy
import hashlib
import json
from pathlib import Path
import re
import tempfile

import pandas as pd
import pytest
import yaml

from engine.stock_identity import fingerprint as fp
from engine.stock_identity import hygiene
from engine.stock_identity import partition as partition_mod
from engine.stock_identity import pilot
from engine.stock_identity.authority import (
    AUTHORITY_KEYS,
    authority_block,
    is_zero_authority,
)
from engine.stock_identity.hygiene import COMPUTE_BLOCKLIST, check_symbol
from engine.stock_identity.plane import PLANE_BASKETS, primary_planes
from scripts import audit_reused_tickers as reused_audit
from scripts import stock_identity_build_atlas as sealed_builder
from scripts import stock_identity_build_w1a1 as amendment_builder

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

#: Modules the IDENTITY LAYER must never import (the G-8 protected set). This ban is
#: TOTAL for the identity layer — the episode catalog stays expert-free (G-3).
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

#: W2 registration §2 — the ONE scoped exemption. ``engine/stock_identity/replay/**`` may
#: import, read-only, exactly these producers, so a family is recomputed by the engine's
#: OWN function instead of being re-implemented (re-implementation is the silent-fork
#: hazard, archaeology §4.2). Anything not on this list stays banned there too.
REPLAY_ALLOWED_PRODUCERS = (
    "engine.signal_quality",
    "engine.confluence_tiers",
    "engine.washout_turn",
    "engine.canon",
    "engine.us_early_turn",
)

#: Never imported ANYWHERE under engine/stock_identity/**, replay included. These are
#: authority modules and Prophet/Radar internals — not event math.
REPLAY_FORBIDDEN = (
    "engine.signal_gate",
    "engine.entry_signal",
    "engine.mtf_upturn",
    "engine.stock_personality",
    "engine.oracle.personality_context",
    "engine.entry_radar",
)
REPLAY_FORBIDDEN_PREFIXES = (
    "engine.prophet_", "engine.prophet.", "engine.entry_radar.", "engine.oracle.",
    "scripts.", "scripts",
)


def _identity_layer_sources() -> list[Path]:
    """The identity layer: the package's own top-level modules (the TOTAL-ban set)."""
    return sorted(PKG.glob("*.py"))


def _replay_sources() -> list[Path]:
    """The replay subpackage: the ONLY scoped-exemption set."""
    return sorted((PKG / "replay").rglob("*.py"))


def _imported_modules(src: Path) -> list[str]:
    tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
    return mods


def _json_files() -> list[Path]:
    return sorted(DATA.rglob("*.json")) if DATA.exists() else []


def _parquet_files() -> list[Path]:
    return sorted(DATA.rglob("*.parquet")) if DATA.exists() else []


#: Stores of RAW PRICE HISTORY. Their authority block rides on a covering manifest
#: rather than on every price row, because these frames are byte-frozen against a
#: registered digest over exactly [open, high, low, close, volume] -- adding
#: authority columns would break the registration the file exists to preserve.
#: The exemption is not a hole: every parquet under these dirs must still be
#: covered by a zero-authority manifest (see the coverage test below).
_RAW_PRICE_DIRS: frozenset[str] = frozenset({"ohlcv", "source"})


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
        # ``source/`` holds raw immutable snapshots of external market data (the
        # W1-A1 registered B prefix), not an Identity Atlas-computed artifact — the
        # same reason the collected ``ohlcv/`` price parquets are excluded from the
        # parquet half of this law below. Its provenance sidecar documents
        # extraction receipts, not a ranking/sizing/gating decision, so it carries
        # no authority block.
        files = [p for p in _json_files() if p.parent.name != "source"]
        if not files:
            pytest.skip("no artifacts in this checkout")
        for p in files:
            payload = json.loads(p.read_text(encoding="utf-8"))
            assert isinstance(payload, dict), p.name
            assert is_zero_authority(payload), f"{p.name} lacks a complete all-false block"

    def test_every_parquet_artifact_carries_authority_columns(self):
        files = [p for p in _parquet_files() if p.parent.name not in _RAW_PRICE_DIRS]
        if not files:
            pytest.skip("no artifacts in this checkout")
        for p in files:
            df = pd.read_parquet(p)
            for key in AUTHORITY_KEYS:
                col = f"authority_{key}"
                assert col in df.columns, f"{p.name} missing {col}"
                assert not df[col].any(), f"{p.name}: {col} is not all-false"

    def test_every_raw_price_parquet_is_covered_by_a_zero_authority_manifest(self):
        # The _RAW_PRICE_DIRS exemption above skips per-row authority columns. It may
        # never become a silent hole: an exempted parquet must still be covered by a
        # zero-authority manifest -- a sibling manifest.json for a multi-name store, or
        # a same-stem .json sidecar for a single frozen frame.
        exempt = [p for p in _parquet_files() if p.parent.name in _RAW_PRICE_DIRS]
        if not exempt:
            pytest.skip("no raw price stores in this checkout")
        for p in exempt:
            manifest = p.parent / "manifest.json"
            sidecar = p.with_suffix(".json")
            covering = manifest if manifest.exists() else sidecar
            assert covering.exists(), (
                f"{p.name} is exempt from per-row authority columns but has no "
                f"covering manifest ({manifest.name} or {sidecar.name})"
            )
            payload = json.loads(covering.read_text(encoding="utf-8"))
            assert is_zero_authority(payload), (
                f"{covering.name} does not carry a complete all-false block for {p.name}"
            )

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
    """The firewall, in two scopes (W2 registration §2).

    The identity layer keeps the TOTAL ban. ``replay/**`` carries the single scoped
    exemption and nothing wider — which is why this class enumerates the allowlist rather
    than merely subtracting the forbidden set: a producer that quietly appears in a replay
    module without being registered here fails, in the direction that matters.
    """

    def test_identity_layer_imports_no_protected_module(self):
        srcs = _identity_layer_sources()
        assert srcs, "the identity layer has no modules — the walk is looking in the wrong place"
        for src in srcs:
            for mod in _imported_modules(src):
                assert mod not in FORBIDDEN_IMPORTS, f"{src.name} imports {mod}"
                for prefix in FORBIDDEN_PREFIXES:
                    assert not mod.startswith(prefix), f"{src.name} imports {mod}"

    def test_replay_layer_imports_only_the_scoped_allowlist(self):
        srcs = _replay_sources()
        if not srcs:
            pytest.skip("replay subpackage not present in this checkout")
        for src in srcs:
            for mod in _imported_modules(src):
                if not mod.startswith("engine."):
                    continue
                if mod.startswith("engine.stock_identity"):
                    continue                      # in-package imports are unrestricted
                assert mod in REPLAY_ALLOWED_PRODUCERS, (
                    f"{src.name} imports {mod}, which is not on the registration §2 "
                    f"scoped allowlist {REPLAY_ALLOWED_PRODUCERS}"
                )

    def test_replay_layer_never_imports_an_authority_module(self):
        srcs = _replay_sources()
        if not srcs:
            pytest.skip("replay subpackage not present in this checkout")
        for src in srcs:
            for mod in _imported_modules(src):
                assert mod not in REPLAY_FORBIDDEN, f"{src.name} imports {mod}"
                for prefix in REPLAY_FORBIDDEN_PREFIXES:
                    assert not mod.startswith(prefix), f"{src.name} imports {mod}"

    def test_the_allowlist_in_code_matches_the_allowlist_in_this_test(self):
        # The package publishes the same tuple it is judged by, so the law cannot drift
        # away from the guard by editing only one of them.
        try:
            from engine.stock_identity.replay import (
                ALLOWED_PRODUCER_IMPORTS,
                FORBIDDEN_PRODUCER_IMPORTS,
            )
        except Exception:  # pragma: no cover - subpackage absent
            pytest.skip("replay subpackage not importable in this checkout")
        assert tuple(sorted(ALLOWED_PRODUCER_IMPORTS)) == tuple(sorted(REPLAY_ALLOWED_PRODUCERS))
        for mod in FORBIDDEN_PRODUCER_IMPORTS:
            assert mod in REPLAY_FORBIDDEN

    def test_package_imports_nothing_from_scripts(self):
        for src in _identity_layer_sources() + _replay_sources():
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


class TestCurrentTickerHygiene:
    """Post-seal identity repairs must stay coherent with the frozen W1 record."""

    def test_gold_is_acked_readable_dealer_tape_not_a_compute_block(self):
        verdict = check_symbol("GOLD", repo_root=ROOT)
        assert "GOLD" not in COMPUTE_BLOCKLIST
        assert verdict["compute_eligible"] is True
        assert verdict["blind_eligible"] is False
        assert set(verdict["flags"]) == {"reused_ticker_acked", "symbol_history_note"}
        note = verdict["notes"]["symbol_history_note"]
        for needle in (
            "Gold.com", "dealer", "1591588", "Barrick", "756894", "B.parquet", "PR #5632",
        ):
            assert needle.lower() in note.lower()

    def test_abx_block_is_acked_and_only_preserves_the_sealed_w1_population(self):
        verdict = check_symbol("ABX", repo_root=ROOT)
        assert "ABX" in COMPUTE_BLOCKLIST
        assert verdict["compute_eligible"] is False
        assert verdict["blind_eligible"] is False
        assert set(verdict["flags"]) == {"reused_ticker_acked", "compute_blocklisted"}
        reason = verdict["notes"]["compute_blocklisted"]
        for needle in ("acknowledged", "sealed W1", "registered amendment", "Abacus"):
            assert needle in reason
        assert "unacknowledged" not in reason.lower()
        assert "absent from reused_ticker_acks" not in reason

    def test_gold_ack_records_the_repaired_consumer_without_quarantining_store(self):
        cfg = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8"))
        text = cfg["quality"]["reused_ticker_acks"]["GOLD"]
        for needle in (
            "CONSUMER DEFECT REPAIRED", "PR #5632", "B.parquet", "valid Gold.com instrument",
        ):
            assert needle in text
        for stale in ("KNOWN CONSUMER DEFECT", "NO store file under 'B'", "separate curated act"):
            assert stale not in text

    def test_member_identity_detector_catches_the_exact_gold_wrong_issuer(self, tmp_path):
        membership = tmp_path / "baskets" / "membership.json"
        membership.parent.mkdir(parents=True)
        membership.write_text(
            json.dumps(
                {
                    "baskets": {
                        "gold_miners": {
                            "members": [
                                {
                                    "ticker": "GOLD",
                                    "removed": None,
                                    "rationale": "Barrick Mining — global senior producer",
                                }
                            ]
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        rows, unacked = reused_audit._member_identity_rows(
            tmp_path,
            {"GOLD": "Gold.com, Inc. Common Stock"},
            {},
            {"extra_names": {}},
        )
        assert unacked == ["gold_miners/GOLD"]
        assert rows == [
            {
                "ticker": "GOLD",
                "where": "gold_miners",
                "source": "membership_rationale",
                "curated_name": "Barrick Mining",
                "directory_name": "Gold.com, Inc. Common Stock",
                "acked": False,
            }
        ]

    def test_gold_is_absent_and_b_alone_owns_the_current_miner_slot(self):
        membership = json.loads(
            (ROOT / "data/baskets/membership.json").read_text(encoding="utf-8")
        )
        basket = membership["baskets"]["gold_miners"]
        rows = {row["ticker"]: row for row in basket["members"]}
        assert "GOLD" not in rows
        assert rows["B"]["added"] == "2023-05-09"
        assert rows["B"]["curated_added"] == "2026-08-14"
        assert rows["B"]["removed"] is None
        assert len([row for row in basket["members"] if not row.get("removed")]) == 12
        disclosure = " ".join(basket["omitted"]) + " " + " ".join(
            row["note"] for row in basket["changelog"]
        )
        for token in ("Gold.com", "1591588", "756894", "2025-12-02", "2025-05-09"):
            assert token in disclosure

    def test_b_tape_is_barrick_and_gold_stays_zero_in_both_mask_modes(self):
        from engine.basket_index import _live_mask

        membership = json.loads(
            (ROOT / "data/baskets/membership.json").read_text(encoding="utf-8")
        )
        members = membership["baskets"]["gold_miners"]["members"]
        b_row = next(row for row in members if row["ticker"] == "B")
        assert all(row["ticker"] != "GOLD" for row in members)

        curated = pd.read_parquet(ROOT / "data/baskets/ohlcv/B.parquet")
        barrick = pd.read_parquet(ROOT / "data/yahoo/B.parquet")
        dealer = pd.read_parquet(ROOT / "data/baskets/ohlcv/GOLD.parquet")
        assert list(curated.columns) == ["open", "high", "low", "close", "volume"]
        assert len(curated) >= 3_172
        assert curated.index.min() == pd.Timestamp("2014-01-02")
        assert curated.index.max() >= pd.Timestamp("2026-08-13")

        b_pair = pd.concat(
            [curated["close"].pct_change(), barrick["close"].pct_change()],
            axis=1,
            join="inner",
        ).dropna()
        dealer_pair = pd.concat(
            [curated["close"].pct_change(), dealer["close"].pct_change()],
            axis=1,
            join="inner",
        ).dropna()
        assert b_pair.corr().iloc[0, 1] > 0.999
        assert dealer_pair.corr().iloc[0, 1] < 0.35

        idx = curated.index
        close = pd.concat(
            {"GOLD": dealer["close"], "B": curated["close"]}, axis=1, sort=False
        ).reindex(idx)
        strict = _live_mask([b_row], idx, ["GOLD", "B"], pit=True, close=close)
        deep = _live_mask([b_row], idx, ["GOLD", "B"], pit=False, close=close)
        assert not strict["GOLD"].any() and not deep["GOLD"].any()
        assert int(strict["B"].sum()) == int((idx >= pd.Timestamp(b_row["added"])).sum())
        assert int(deep["B"].sum()) == len(curated)


# ── W1-A1 append-only overlay: fail-closed consumer and publisher guards ─────

def _pilot_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_receipt(root: Path, payload: dict) -> None:
    path = root / pilot.RECEIPT_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _closed_fixture(root: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    generated: dict[str, str] = {}
    for relative in pilot.W1A1_GENERATED_OUTPUT_PATHS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"governed:{relative}".encode("utf-8"))
        generated[relative] = _pilot_sha256(path)

    sealed: dict[str, str] = {}
    for relative in pilot.W1A1_SEALED_W1_SHA256:
        if relative == pilot.W1A1_GOLD_DISCLOSURE_PATH:
            continue
        frozen = root / relative
        frozen.parent.mkdir(parents=True, exist_ok=True)
        frozen.write_bytes(f"sealed:{relative}".encode("utf-8"))
        sealed[relative] = _pilot_sha256(frozen)

    original = "# sealed GOLD dossier\n\nstanding authority\n\n## Identity\n"
    before_sha = hashlib.sha256(original.encode("utf-8")).hexdigest()
    monkeypatch.setattr(pilot, "W1A1_GOLD_MD_BEFORE_SHA256", before_sha)
    sealed[pilot.W1A1_GOLD_DISCLOSURE_PATH] = before_sha
    monkeypatch.setattr(pilot, "W1A1_SEALED_W1_SHA256", sealed)
    block = "\n".join(
        (
            pilot.W1A1_GOLD_ANNOTATION_BEGIN,
            "> additive wrong-issuer disclosure",
            pilot.W1A1_GOLD_ANNOTATION_END,
        )
    )
    annotated = original.replace("\n\n## Identity", f"\n\n{block}\n\n## Identity")
    gold = root / pilot.W1A1_GOLD_DISCLOSURE_PATH
    gold.parent.mkdir(parents=True, exist_ok=True)
    gold.write_text(annotated, encoding="utf-8")

    payload = {
        "schema": pilot.W1A1_RECEIPT_SCHEMA,
        "amendment_id": pilot.AMENDMENT_ID,
        "asof": pilot.W1A1_ASOF,
        "pull_request": pilot.W1A1_PULL_REQUEST,
        "pull_request_context": {
            "repository": pilot.W1A1_GITHUB_REPOSITORY,
            "base_ref": pilot.W1A1_PR_BASE_REF,
            "head_ref": pilot.W1A1_PR_HEAD_REF,
            "head_oid_at_run": "3" * 40,
            "url": pilot.W1A1_PR_URL,
            "draft_at_run": True,
        },
        "initial_registration_commit": pilot.W1A1_INITIAL_REGISTRATION_COMMIT,
        "registration_commit": "3" * 40,
        "prerequisite_source_heads": copy.deepcopy(
            pilot.W1A1_PREREQUISITE_SOURCE_HEADS
        ),
        "prerequisite_merges": copy.deepcopy(pilot.W1A1_PREREQUISITE_MERGES),
        "identity_receipt": copy.deepcopy(pilot.W1A1_IDENTITY_RECEIPT),
        "miner_probe_roster": {
            "sealed_w1": list(pilot.W1_SEALED_MINER_PROBE),
            "effective_w1a1": list(pilot.W1A1_EFFECTIVE_MINER_PROBE),
        },
        "partition_treatment": copy.deepcopy(pilot.W1A1_PARTITION_TREATMENT),
        "procedural_deviation": copy.deepcopy(pilot.W1A1_PROCEDURAL_DEVIATION),
        "rank_context": {
            "method": "B-only hypothetical insertion",
            "frozen_reference_rows": 2780,
            "hypothetical_joint_rows": 2781,
            "only_B_persisted": True,
            "w1_percentiles_rewritten": False,
            "univ_ew_recomputed": False,
            "dealer_context_disclosure": "frozen ranks retain GOLD dealer context",
            "reference_sha256": copy.deepcopy(pilot.W1A1_REFERENCE_SHA256),
        },
        "price_input": {
            "path": "data/baskets/ohlcv/B.parquet",
            "price_plane_id": "baskets_ohlcv_v1",
            "prefix_asof": pilot.W1A1_ASOF,
            "prefix_sha256": "6d8988fc8ec3990d3a5c2a6d5f4bb31d94b3ab46ac49978d21fb3770482ae8db",
            "seed_container_sha256": "dc126c36c6fa07b37ca212051d2a194758725330bfed9c5b6112701b12be6b5f",
            "file_sha256_at_run": "4" * 64,
            "file_rows_at_run": 3172,
            "file_last_date_at_run": pilot.W1A1_ASOF,
            "rows_used": 3172,
            "first_date": "2014-01-02",
            "last_date_used": pilot.W1A1_ASOF,
        },
        "sealed_w1_sha256": copy.deepcopy(sealed),
        "registered_output_paths": list(pilot.W1A1_REGISTERED_OUTPUT_PATHS),
        "generated_output_sha256": generated,
        "disclosure_only": {
            "path": pilot.W1A1_GOLD_DISCLOSURE_PATH,
            "before_sha256": before_sha,
            "after_sha256": _pilot_sha256(gold),
            "marker_begin": pilot.W1A1_GOLD_ANNOTATION_BEGIN,
            "marker_end": pilot.W1A1_GOLD_ANNOTATION_END,
            "restores_original_when_removed": True,
            "gold_svg_unchanged": True,
        },
        "measured_rows_mutated": False,
        "trial_budget": pilot.W1A1_TRIAL_BUDGET,
        "authority": authority_block(),
    }
    _write_receipt(root, payload)
    return payload


def test_current_miner_probe_requires_complete_closed_receipt(tmp_path, monkeypatch):
    _closed_fixture(tmp_path, monkeypatch)
    assert pilot.current_miner_probe(tmp_path) == pilot.W1A1_EFFECTIVE_MINER_PROBE


@pytest.mark.parametrize(
    "keys,value,match",
    (
        (("schema",), "wrong", "receipt schema"),
        (("identity_receipt", "B", "edgar_cik"), "1591588", "identity receipt"),
        (("partition_treatment", "B_design_touched"), False, "partition quarantine"),
        (("procedural_deviation", "write_scope"), "erased", "deviation disclosure"),
        (("procedural_deviation", "observed_scope"), "erased", "deviation disclosure"),
        (("trial_budget",), "outcome-selected", "trial-budget"),
        (("pull_request",), 9999, "pull_request receipt"),
        (("pull_request_context", "base_ref"), "master", "pull-request context"),
        (("pull_request_context", "head_ref"), "wrong", "pull-request context"),
        (("pull_request_context", "head_oid_at_run"), "0" * 40, "pull-request head"),
        (("initial_registration_commit",), "0" * 40, "initial registration commit"),
        (("prerequisite_source_heads", "pr_5632"), "0" * 40, "source-head"),
        (("prerequisite_merges", "pr_5632"), "0" * 40, "merge closure"),
        (("rank_context", "w1_percentiles_rewritten"), True, "rank context"),
        (("price_input", "prefix_sha256"), "0" * 64, "price-input"),
        (("sealed_w1_sha256", "data/stock_identity/constants/si_constants_v1.json"),
         "0" * 64, "sealed W1 hash receipt"),
    ),
)
def test_current_miner_probe_rejects_governance_tampering(
    tmp_path, monkeypatch, keys, value, match
):
    payload = copy.deepcopy(_closed_fixture(tmp_path, monkeypatch))
    target = payload
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    _write_receipt(tmp_path, payload)
    with pytest.raises(ValueError, match=match):
        pilot.current_miner_probe(tmp_path)


def test_current_miner_probe_rejects_actual_sealed_artifact_drift(tmp_path, monkeypatch):
    _closed_fixture(tmp_path, monkeypatch)
    frozen = tmp_path / "data/stock_identity/constants/si_constants_v1.json"
    frozen.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="sealed W1 artifact drifted"):
        pilot.current_miner_probe(tmp_path)


@pytest.mark.parametrize(
    "key,match",
    (("procedural_deviation", "deviation disclosure"), ("trial_budget", "trial-budget")),
)
def test_current_miner_probe_rejects_omitted_exposure_governance(
    tmp_path, monkeypatch, key, match
):
    payload = copy.deepcopy(_closed_fixture(tmp_path, monkeypatch))
    payload.pop(key)
    _write_receipt(tmp_path, payload)
    with pytest.raises(ValueError, match=match):
        pilot.current_miner_probe(tmp_path)


@pytest.mark.parametrize("value", ("zzzz", "2026-8-14", "2026-08-13T00:00:00"))
def test_current_miner_probe_rejects_noncanonical_run_last_date(
    tmp_path, monkeypatch, value
):
    payload = copy.deepcopy(_closed_fixture(tmp_path, monkeypatch))
    payload["price_input"]["file_last_date_at_run"] = value
    _write_receipt(tmp_path, payload)
    with pytest.raises(ValueError, match="last date is not canonical ISO"):
        pilot.current_miner_probe(tmp_path)


def test_current_miner_probe_rejects_omitted_governed_output(tmp_path, monkeypatch):
    payload = _closed_fixture(tmp_path, monkeypatch)
    payload = copy.deepcopy(payload)
    payload["generated_output_sha256"].pop(pilot.W1A1_GENERATED_OUTPUT_PATHS[-1])
    _write_receipt(tmp_path, payload)
    with pytest.raises(ValueError, match="hash closure is incomplete"):
        pilot.current_miner_probe(tmp_path)


def test_current_miner_probe_rejects_path_traversal_key(tmp_path, monkeypatch):
    payload = _closed_fixture(tmp_path, monkeypatch)
    payload = copy.deepcopy(payload)
    payload["generated_output_sha256"]["../escape"] = "0" * 64
    _write_receipt(tmp_path, payload)
    with pytest.raises(ValueError, match="hash closure is incomplete"):
        pilot.current_miner_probe(tmp_path)


def test_current_miner_probe_rejects_substituted_disclosure_path(tmp_path, monkeypatch):
    payload = _closed_fixture(tmp_path, monkeypatch)
    payload = copy.deepcopy(payload)
    payload["disclosure_only"]["path"] = "research/stock_identity/dossiers/B.md"
    _write_receipt(tmp_path, payload)
    with pytest.raises(ValueError, match="disclosure path drifted"):
        pilot.current_miner_probe(tmp_path)


def test_current_miner_probe_rejects_nonreversible_disclosure(tmp_path, monkeypatch):
    payload = _closed_fixture(tmp_path, monkeypatch)
    payload = copy.deepcopy(payload)
    gold = tmp_path / pilot.W1A1_GOLD_DISCLOSURE_PATH
    gold.write_text(
        "tampered outside marker\n" + gold.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    payload["disclosure_only"]["after_sha256"] = _pilot_sha256(gold)
    _write_receipt(tmp_path, payload)
    with pytest.raises(ValueError, match="does not restore the sealed dossier"):
        pilot.current_miner_probe(tmp_path)


def test_authority_frame_rejects_nulls_and_integer_zero():
    columns = {
        f"authority_{key}": pd.Series([False], dtype=bool)
        for key in authority_block()
    }
    valid = pd.DataFrame(columns)
    amendment_builder._assert_zero_authority_frame(valid, "valid")

    nullish = valid.astype(object)
    nullish.loc[0, "authority_can_rank"] = None
    with pytest.raises(SystemExit, match="non-null boolean"):
        amendment_builder._assert_zero_authority_frame(nullish, "nullish")

    integer_zero = valid.copy()
    integer_zero["authority_can_rank"] = 0
    with pytest.raises(SystemExit, match="non-null boolean"):
        amendment_builder._assert_zero_authority_frame(integer_zero, "integer")


def test_b_compute_hygiene_fails_before_history_is_consumed(monkeypatch):
    monkeypatch.setattr(amendment_builder.hyg_mod, "COMPUTE_BLOCKLIST", {"B": "verified block"})
    monkeypatch.setattr(
        amendment_builder.hyg_mod,
        "check_symbol",
        lambda *args, **kwargs: {
            "flags": ["compute_blocklisted"],
            "notes": {"compute_blocklisted": "verified block"},
            "compute_eligible": False,
        },
    )
    with pytest.raises(SystemExit, match="pre-read compute hygiene gate"):
        amendment_builder._validate_compute_hygiene("B", pd.Timestamp("2014-01-02"))


def _pr_payload(number: int, key: str) -> dict:
    return {
        "number": number,
        "state": "MERGED",
        "baseRefName": "main",
        "headRefName": f"source-{number}",
        "headRefOid": pilot.W1A1_PREREQUISITE_SOURCE_HEADS[key],
        "mergeCommit": {"oid": pilot.W1A1_PREREQUISITE_MERGES[key]},
        "isCrossRepository": False,
        "isDraft": False,
        "url": f"https://github.com/mastermindx-market-intelligence/macro/pull/{number}",
    }


def test_prerequisite_gate_checks_exact_pr_pairs_and_only_merge_ancestry(monkeypatch):
    payloads = {
        5613: _pr_payload(5613, "pr_5613"),
        5632: _pr_payload(5632, "pr_5632"),
    }
    ancestry: list[tuple[str, str, str]] = []
    monkeypatch.setattr(amendment_builder, "_gh_pr_view", payloads.__getitem__)
    monkeypatch.setattr(amendment_builder, "_git", lambda *args: "f" * 40)
    monkeypatch.setattr(
        amendment_builder,
        "_require_ancestor",
        lambda ancestor, descendant, label: ancestry.append((ancestor, descendant, label)),
    )
    amendment_builder._validate_prerequisites()
    assert [row[0] for row in ancestry] == list(
        pilot.W1A1_PREREQUISITE_MERGES.values()
    )
    assert not set(row[0] for row in ancestry) & set(
        pilot.W1A1_PREREQUISITE_SOURCE_HEADS.values()
    )


def test_prerequisite_gate_rejects_a_valid_but_wrong_source_head(monkeypatch):
    payloads = {
        5613: _pr_payload(5613, "pr_5613"),
        5632: _pr_payload(5632, "pr_5632"),
    }
    payloads[5632]["headRefOid"] = "0" * 40
    monkeypatch.setattr(amendment_builder, "_gh_pr_view", payloads.__getitem__)
    monkeypatch.setattr(amendment_builder, "_git", lambda *args: "f" * 40)
    monkeypatch.setattr(amendment_builder, "_require_ancestor", lambda *args: None)
    with pytest.raises(SystemExit, match="source-head provenance"):
        amendment_builder._validate_prerequisites()


def _current_pr_payload(registration_commit: str) -> dict:
    return {
        "number": pilot.W1A1_PULL_REQUEST,
        "state": "OPEN",
        "baseRefName": pilot.W1A1_PR_BASE_REF,
        "headRefName": pilot.W1A1_PR_HEAD_REF,
        "headRefOid": registration_commit,
        "mergeCommit": None,
        "isCrossRepository": False,
        "isDraft": True,
        "url": pilot.W1A1_PR_URL,
    }


def test_current_pr_gate_binds_the_clean_pushed_registration_head(monkeypatch):
    registration = "a" * 40
    monkeypatch.setattr(
        amendment_builder,
        "_git",
        lambda *args: pilot.W1A1_PR_HEAD_REF if args == ("branch", "--show-current") else "",
    )
    monkeypatch.setattr(
        amendment_builder, "_gh_pr_view", lambda number: _current_pr_payload(registration)
    )
    context = amendment_builder._validate_current_pull_request(registration)
    assert context["head_oid_at_run"] == registration
    assert context["draft_at_run"] is True


@pytest.mark.parametrize(
    "field,value",
    (
        ("number", 9999),
        ("state", "MERGED"),
        ("baseRefName", "master"),
        ("headRefName", "wrong"),
        ("headRefOid", "0" * 40),
        ("isCrossRepository", True),
        ("isDraft", False),
        ("url", "https://example.invalid/pr/5660"),
    ),
)
def test_current_pr_gate_rejects_metadata_drift(monkeypatch, field, value):
    registration = "a" * 40
    payload = _current_pr_payload(registration)
    payload[field] = value
    monkeypatch.setattr(
        amendment_builder,
        "_git",
        lambda *args: pilot.W1A1_PR_HEAD_REF if args == ("branch", "--show-current") else "",
    )
    monkeypatch.setattr(amendment_builder, "_gh_pr_view", lambda number: payload)
    with pytest.raises(SystemExit, match="pull-request provenance"):
        amendment_builder._validate_current_pull_request(registration)


def test_b_logical_prefix_digest_ignores_later_appends_but_detects_revisions():
    columns = ["open", "high", "low", "close", "volume"]
    prefix = pd.DataFrame(
        [[1.0, 2.0, 0.5, 1.5, 100.0], [1.5, 2.5, 1.0, 2.0, 120.0]],
        index=pd.DatetimeIndex(["2026-08-12", "2026-08-13"], name="Date"),
        columns=columns,
    )
    appended = pd.concat(
        [
            prefix,
            pd.DataFrame(
                [[2.0, 3.0, 1.5, 2.5, 140.0]],
                index=pd.DatetimeIndex(["2026-08-14"], name="Date"),
                columns=columns,
            ),
        ]
    )
    assert amendment_builder._ohlcv_prefix_sha256(appended.loc[:"2026-08-13"]) == (
        amendment_builder._ohlcv_prefix_sha256(prefix)
    )
    revised = prefix.copy()
    revised.loc[pd.Timestamp("2026-08-12"), "close"] = 1.5000001
    assert amendment_builder._ohlcv_prefix_sha256(revised) != (
        amendment_builder._ohlcv_prefix_sha256(prefix)
    )


def test_additive_schema_is_normalized_then_reopened_exactly(tmp_path):
    frozen = pd.DataFrame(
        {
            "when": pd.Series([pd.Timestamp("2020-01-01")], dtype="datetime64[us]"),
            "label": pd.Series(["sealed"], dtype="str"),
            "note": pd.Series([None], dtype=object),
            "authority_can_rank": pd.Series([False], dtype=bool),
        }
    )
    frozen_path = tmp_path / "frozen.parquet"
    # Reproduce the sealed episode artifact's accidental physical RangeIndex. The
    # consumer-visible pandas schema excludes it, and an additive index=False file is
    # still logically schema-compatible.
    frozen.to_parquet(frozen_path, index=True)
    candidate = pd.DataFrame(
        {
            "when": pd.Series([pd.Timestamp("2026-08-13")], dtype="datetime64[ms]"),
            "label": ["B"],
            "note": [None],
            "authority_can_rank": [False],
        }
    )
    normalized = amendment_builder._schema_like(candidate, frozen_path, "candidate")
    amendment_builder._validate_schema_like(
        normalized, pd.read_parquet(frozen_path), "candidate"
    )

    written = tmp_path / "candidate.parquet"
    normalized.to_parquet(written, index=False)
    amendment_builder._validate_parquet_schema_like(written, frozen_path, "candidate")

    import pyarrow.parquet as pq

    assert "__index_level_0__" in pq.read_schema(frozen_path).names
    assert "__index_level_0__" not in pq.read_schema(written).names

    wrong = normalized.copy()
    wrong["authority_can_rank"] = 0
    wrong_path = tmp_path / "wrong.parquet"
    wrong.to_parquet(wrong_path, index=False)
    with pytest.raises(SystemExit, match="logical-type drift"):
        amendment_builder._validate_parquet_schema_like(wrong_path, frozen_path, "wrong")


def test_b_only_dossier_overrides_disclose_rank_and_open_gap_semantics():
    generic = "\n".join(
        (
            "# B — Identity Atlas v0 dossier",
            amendment_builder._GENERIC_PERCENTILE_PROSE,
            amendment_builder._GENERIC_B_GAP_PROSE,
        )
    )
    amended = amendment_builder._apply_b_dossier_disclosures(generic)
    assert "W1-A1 addendum" in amended
    assert "only B was ranked and no W1 row was recomputed or rewritten" in amended
    assert "opening print is compared with the previous close" in amended
    assert "close-to-close proxy" not in amended


def test_b_dossier_prologue_uses_the_complete_identity_heading_boundary():
    markdown = "\n".join(
        (
            "# B — Identity Atlas v0 dossier (W1-A1 addendum)",
            "",
            "## Identity",
            "",
            "identity body",
            "",
            "## Identity-episode catalog",
        )
    )
    boundary = "\n## Identity\n"
    assert markdown.count(boundary) == 1
    inserted = markdown.replace(
        boundary,
        f"\n{amendment_builder.B_DOSSIER_PROLOGUE}\n{boundary}",
        1,
    )
    assert inserted.count(amendment_builder.B_DOSSIER_PROLOGUE) == 1
    assert "## Identity-episode catalog" in inserted


def test_gold_annotation_uses_complete_heading_and_restores_exactly(tmp_path, monkeypatch):
    relative = "research/stock_identity/dossiers/GOLD.md"
    original = "\n".join(
        (
            "# GOLD — Identity Atlas v0 dossier",
            "",
            "standing authority",
            "",
            "## Identity",
            "",
            "identity body",
            "",
            "## Identity-episode catalog",
        )
    )
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(original, encoding="utf-8")
    expected = hashlib.sha256(original.encode("utf-8")).hexdigest()
    monkeypatch.setattr(amendment_builder, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(amendment_builder, "DISCLOSURE_ONLY_PATH", relative)
    monkeypatch.setattr(amendment_builder, "FROZEN_SHA256", {relative: expected})

    annotated = amendment_builder._gold_markdown_with_annotation()
    assert annotated.count(amendment_builder.GOLD_ANNOTATION_BEGIN) == 1
    assert "## Identity-episode catalog" in annotated
    restored = annotated.replace(
        f"\n\n{amendment_builder.GOLD_ANNOTATION}\n\n",
        "\n\n",
        1,
    )
    assert hashlib.sha256(restored.encode("utf-8")).hexdigest() == expected


def test_post_publish_validation_failure_rolls_back_the_whole_amendment(
    tmp_path, monkeypatch
):
    outputs = (
        "data/receipt.json",
        "data/B.parquet",
        "research/B.md",
    )
    disclosure = "research/GOLD.md"
    stage = tmp_path / "stage"
    repo = tmp_path / "repo"
    for relative in outputs:
        path = stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"staged:{relative}", encoding="utf-8")
    staged_gold = stage / "GOLD.annotated.md"
    staged_gold.write_text("annotated", encoding="utf-8")
    original_gold = repo / disclosure
    original_gold.parent.mkdir(parents=True, exist_ok=True)
    original_gold.write_text("sealed", encoding="utf-8")

    monkeypatch.setattr(amendment_builder, "REPO_ROOT", repo)
    monkeypatch.setattr(amendment_builder, "OUTPUT_PATHS", outputs)
    monkeypatch.setattr(amendment_builder, "RECEIPT_RELATIVE_PATH", outputs[0])
    monkeypatch.setattr(amendment_builder, "DISCLOSURE_ONLY_PATH", disclosure)
    monkeypatch.setattr(amendment_builder, "_validate_outputs_absent", lambda: None)
    monkeypatch.setattr(
        amendment_builder, "_validate_frozen_hashes", lambda **kwargs: None
    )

    def fail_closure(_receipt):
        raise SystemExit("forced post-publish closure failure")

    monkeypatch.setattr(amendment_builder, "_validate_published", fail_closure)
    with pytest.raises(SystemExit, match="forced post-publish"):
        amendment_builder._publish(stage, staged_gold, {"test": True})

    assert original_gold.read_text(encoding="utf-8") == "sealed"
    assert all(not (repo / relative).exists() for relative in outputs)
    lock_key = hashlib.sha256(str(repo.resolve()).encode("utf-8")).hexdigest()[:16]
    assert (
        Path(tempfile.gettempdir()) / f"stock-identity-w1a1-{lock_key}.lock"
    ).exists()


def test_consumer_rejected_receipt_rolls_back_the_whole_amendment(
    tmp_path, monkeypatch
):
    receipt_relative = "data/receipt.json"
    disclosure_relative = "research/GOLD.md"
    stage = tmp_path / "stage"
    repo = tmp_path / "repo"
    original = "# sealed GOLD dossier\n\n## Identity\n"
    annotated = original.replace(
        "\n\n## Identity", f"\n\n{amendment_builder.GOLD_ANNOTATION}\n\n## Identity", 1
    )
    staged_gold = stage / "GOLD.annotated.md"
    staged_gold.parent.mkdir(parents=True, exist_ok=True)
    staged_gold.write_text(annotated, encoding="utf-8")
    receipt = {
        "generated_output_sha256": {},
        "disclosure_only": {
            "after_sha256": hashlib.sha256(annotated.encode("utf-8")).hexdigest(),
            "before_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
        },
        # This is the governing field the real consumer validates exactly.
        "trial_budget": "erased after staging",
    }
    staged_receipt = stage / receipt_relative
    staged_receipt.parent.mkdir(parents=True, exist_ok=True)
    staged_receipt.write_text(json.dumps(receipt), encoding="utf-8")
    original_gold = repo / disclosure_relative
    original_gold.parent.mkdir(parents=True, exist_ok=True)
    original_gold.write_text(original, encoding="utf-8")

    monkeypatch.setattr(amendment_builder, "REPO_ROOT", repo)
    monkeypatch.setattr(amendment_builder, "OUTPUT_PATHS", (receipt_relative,))
    monkeypatch.setattr(amendment_builder, "RECEIPT_RELATIVE_PATH", receipt_relative)
    monkeypatch.setattr(amendment_builder, "DISCLOSURE_ONLY_PATH", disclosure_relative)
    monkeypatch.setattr(amendment_builder, "_validate_outputs_absent", lambda: None)
    monkeypatch.setattr(
        amendment_builder, "_validate_frozen_hashes", lambda **kwargs: None
    )

    def reject_tampered_trial_budget(root):
        published = json.loads((root / receipt_relative).read_text(encoding="utf-8"))
        if published.get("trial_budget") != pilot.W1A1_TRIAL_BUDGET:
            raise ValueError("no-sweep trial-budget receipt drifted")
        return pilot.W1A1_EFFECTIVE_MINER_PROBE

    monkeypatch.setattr(
        amendment_builder, "current_miner_probe", reject_tampered_trial_budget
    )
    with pytest.raises(SystemExit, match="consumer closure failed.*trial-budget"):
        amendment_builder._publish(stage, staged_gold, receipt)

    assert original_gold.read_text(encoding="utf-8") == original
    assert not (repo / receipt_relative).exists()


# ── W1-A1 append-only overlay: committed result and freeze guards ────────────

REGISTRATION = ROOT / "research/stock_identity/W1_IDENTITY_ATLAS_V0_REGISTRATION.md"
RECEIPT = ROOT / amendment_builder.RECEIPT_RELATIVE_PATH
RESULT_READY = RECEIPT.exists()
PREREQUISITE_READY = (ROOT / amendment_builder.B_SOURCE_RELATIVE_PATH).exists()
SNAPSHOT_READY = (ROOT / amendment_builder.B_SNAPSHOT_RELATIVE_PATH).exists()

SEALED_SHA256 = {
    "data/stock_identity/partition/partition_manifest_v1.json":
        "b1f82f842350e39ac7a73214fd8ebd58b175b52fdf42b3a0fb5a2d03143a5d48",
    "data/stock_identity/partition/universe_snapshot_v1.parquet":
        "9f22807e7cb6ba570f1963de945b7be77461a1788608754e25db6235f4fe3730",
    "data/stock_identity/constants/si_constants_v1.json":
        "276d4ad267ab8711942943e306e844bfdff1f17a051bd17a9d460c1e428fc648",
    "data/stock_identity/fingerprints/fingerprint_spec.json":
        "bbefcd5b72915435acb8714d7892b79e010cb49d394b3222d89575c7b022dee0",
    "data/stock_identity/fingerprints/pilot_fingerprint_v0.parquet":
        "2bdef8763b0c73a6df3f27e8307246887b7b9dc982f66331ba4d96ff09d72ba3",
    "data/stock_identity/state/pilot_state_daily.parquet":
        "e2c43f8761431c62506311e61fa387c70433f82bde8143b564fdf87da7ee485e",
    "data/stock_identity/episodes/pilot_episode_catalog_v0.parquet":
        "3216f6cbbf539584dba31caf30e09b6e76e0297ca34698fcb0235cf6e0d6bc0f",
    "data/stock_identity/episodes/pilot/GOLD.json":
        "be8a1d053c6fc9f639017abb4cf7f3063e7bde8229d9a1622dedd38a02ff16d1",
    "data/stock_identity/census/coverage_census_v0.parquet":
        "d64d37c0ab8e0729aa732f2a68a183dd08e0ca3336e9a4a71975772f28c0b4cd",
    "data/stock_identity/census/coverage_census_v0.md":
        "cf1a818749802bf6143656cfc06efa8ad95d3e87570a011726766c461bf371bb",
    "research/stock_identity/dossiers/GOLD.svg":
        "e4e6466f2b4535b97d2fae4eb3eb7e39c1a40600343d955f0e0fe843d7df49db",
}
ORIGINAL_GOLD_MD_SHA256 = (
    "2675b5be60cc09a37324e697bb62c20679b8f21cfe4d268f5082ce0730861558"
)


def _w1a1_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _receipt() -> dict:
    if not RESULT_READY:
        pytest.skip("registered W1-A1 result has not been produced yet")
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def _w1a1_manifest() -> dict:
    return json.loads(
        (DATA / "partition/partition_manifest_v1.json").read_text(encoding="utf-8")
    )


def test_historical_recipe_and_registered_effective_tuple_are_both_explicit():
    assert sealed_builder.MINER_PROBE == ("NEM", "GOLD", "AEM", "PAAS", "WPM", "AG")
    assert sealed_builder.PILOT_ROLES["GOLD"] == "miner neighborhood probe"
    assert pilot.W1_SEALED_MINER_PROBE == sealed_builder.MINER_PROBE
    assert pilot.W1A1_EFFECTIVE_MINER_PROBE == ("NEM", "AEM", "PAAS", "WPM", "AG", "B")


@pytest.mark.skipif(not RESULT_READY, reason="registered W1-A1 result not produced")
def test_current_miner_probe_activates_only_after_closed_receipt():
    assert pilot.current_miner_probe(ROOT) == pilot.W1A1_EFFECTIVE_MINER_PROBE


def test_registration_append_did_not_move_the_sealed_partition_hash():
    text = REGISTRATION.read_text(encoding="utf-8")
    assert partition_mod.partition_procedure_sha256(REGISTRATION)[0] == (
        _w1a1_manifest()["partition_procedure_sha256"]
    )
    assert text.index("## Amendment A1") > text.index("## §14. Hashes")
    assert amendment_builder.AMENDMENT_ID in text
    for sha in (
        *pilot.W1A1_PREREQUISITE_SOURCE_HEADS.values(),
        *pilot.W1A1_PREREQUISITE_MERGES.values(),
        pilot.W1A1_INITIAL_REGISTRATION_COMMIT,
    ):
        assert sha in text
    assert f"PR #{pilot.W1A1_PULL_REQUEST}" in text
    assert pilot.W1A1_PR_HEAD_REF in text


def test_result_records_the_registration_commits():
    receipt = _receipt()
    assert re.fullmatch(r"[0-9a-f]{40}", receipt["registration_commit"])
    assert receipt["initial_registration_commit"] == (
        pilot.W1A1_INITIAL_REGISTRATION_COMMIT
    )
    assert receipt["pull_request"] == pilot.W1A1_PULL_REQUEST
    assert receipt["pull_request_context"]["head_oid_at_run"] == (
        receipt["registration_commit"]
    )


def test_b_remains_outside_every_sealed_w1_membership():
    manifest = _w1a1_manifest()
    snapshot = pd.read_parquet(DATA / "partition/universe_snapshot_v1.parquet")
    symbols = set(snapshot["symbol"].astype(str))
    assert "GOLD" in symbols and "B" not in symbols
    assert "GOLD" in manifest["pilot"]["members"] and "B" not in manifest["pilot"]["members"]
    assert "B" not in manifest["blind_arm"]["members"]
    assert "B" not in manifest["calibration_partition"]["members"]


def test_result_keeps_b_design_touched_and_nonconfirmatory():
    treatment = _receipt()["partition_treatment"]
    assert treatment["B_design_touched"] is True
    assert treatment["B_excluded_from_future_blind_extension"] is True
    assert treatment["B_excluded_from_confirmatory_grading"] is True


def test_combined_w1_artifacts_still_contain_gold_and_never_b():
    for relative in (
        "fingerprints/pilot_fingerprint_v0.parquet",
        "state/pilot_state_daily.parquet",
        "episodes/pilot_episode_catalog_v0.parquet",
    ):
        frame = pd.read_parquet(DATA / relative)
        symbols = set(frame["symbol"].astype(str))
        assert "GOLD" in symbols, relative
        assert "B" not in symbols, relative


def test_every_sealed_w1_artifact_is_byte_frozen():
    for relative, expected in SEALED_SHA256.items():
        assert _w1a1_sha256(ROOT / relative) == expected, relative


def test_result_declares_that_no_sealed_measurement_was_mutated():
    assert _receipt()["measured_rows_mutated"] is False


@pytest.mark.skipif(not RESULT_READY, reason="registered W1-A1 result not produced")
def test_gold_disclosure_is_reversible_and_names_the_actual_instruments():
    path = ROOT / amendment_builder.DISCLOSURE_ONLY_PATH
    dossier_text = path.read_text(encoding="utf-8")
    begin = amendment_builder.GOLD_ANNOTATION_BEGIN
    end = amendment_builder.GOLD_ANNOTATION_END
    assert dossier_text.count(begin) == dossier_text.count(end) == 1
    assert dossier_text.index(begin) < dossier_text.index("## Identity")
    block = dossier_text[
        dossier_text.index(begin): dossier_text.index(end) + len(end)
    ]
    for token in (
        "Gold.com", "A-Mark", "bullion dealer", "1591588", "756894",
        "2025-12-02", "2025-05-09", "not miner-neighborhood evidence",
    ):
        assert token in block
    restored = dossier_text.replace(f"\n\n{block}\n\n", "\n\n", 1)
    assert hashlib.sha256(restored.encode("utf-8")).hexdigest() == (
        ORIGINAL_GOLD_MD_SHA256
    )
    disclosure = _receipt()["disclosure_only"]
    assert _w1a1_sha256(path) == disclosure["after_sha256"]
    assert disclosure["gold_svg_unchanged"] is True


@pytest.mark.skipif(not PREREQUISITE_READY, reason="PR #5632 prerequisite not present")
def test_gold_is_acked_readable_blind_ineligible_and_not_blocklisted():
    hygiene._load_config.cache_clear()
    assert "GOLD" not in hygiene.COMPUTE_BLOCKLIST
    verdict = hygiene.check_symbol(
        "GOLD", repo_root=ROOT, first_date=pd.Timestamp("2014-03-17")
    )
    assert verdict["compute_eligible"] is True
    assert verdict["blind_eligible"] is False
    assert "reused_ticker_acked" in verdict["flags"]
    assert "symbol_history_note" in verdict["flags"]
    assert "reused_ticker_unacked" not in verdict["flags"]
    note = hygiene.HYGIENE_NOTES["GOLD"]
    for token in ("Gold.com", "1591588", "756894", "2025-12-02", "2025-05-08"):
        assert token in note


@pytest.mark.skipif(not PREREQUISITE_READY, reason="PR #5632 prerequisite not present")
def test_ack_status_tail_records_the_curated_repair():
    config = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8"))
    ack = config["quality"]["reused_ticker_acks"]["GOLD"]
    for token in ("1591588", "756894", "2025-05-09", "PR #5632"):
        assert token in ack
    assert "KNOWN CONSUMER DEFECT" not in ack
    assert "NO store file under 'B'" not in ack


@pytest.mark.skipif(
    not (PREREQUISITE_READY and SNAPSHOT_READY),
    reason="PR #5632 prerequisite or registered B snapshot not present",
)
def test_b_source_is_exactly_the_registered_curated_plane():
    frame = amendment_builder._validate_b_source()
    assert amendment_builder._ohlcv_prefix_sha256(frame) == (
        amendment_builder.B_SOURCE_PREFIX_SHA256
    )
    assert len(frame) == 3172
    assert frame.index.min() == pd.Timestamp("2014-01-02")
    assert frame.index.max() == pd.Timestamp("2026-08-13")
    assert primary_planes(ROOT)["B"] == PLANE_BASKETS
    assert not (DATA / "ohlcv/B.parquet").exists()


@pytest.mark.skipif(not SNAPSHOT_READY, reason="registered B snapshot not present")
def test_registered_b_prefix_snapshot_is_immutable_and_matches_registration():
    snapshot_path = ROOT / amendment_builder.B_SNAPSHOT_RELATIVE_PATH
    assert _w1a1_sha256(snapshot_path) == amendment_builder.B_SNAPSHOT_FILE_SHA256
    frame = amendment_builder._load_registered_b_prefix()
    assert amendment_builder._ohlcv_prefix_sha256(frame) == (
        amendment_builder.B_SOURCE_PREFIX_SHA256
    )


@pytest.mark.skipif(not SNAPSHOT_READY, reason="registered B snapshot not present")
def test_live_b_plane_tripwire_tolerates_vendor_readjustment_and_fires_on_revision(
    monkeypatch,
):
    registered = amendment_builder._load_registered_b_prefix()

    noise = registered.copy()
    noise[["open", "high", "low", "close"]] = (
        noise[["open", "high", "low", "close"]] * (1 + 5e-7)
    )
    monkeypatch.setattr(
        amendment_builder, "load_symbol", lambda symbol, plane_id, repo_root: noise
    )
    amendment_builder._validate_live_b_plane_tracks_registration(registered)

    revised = registered.copy()
    revised.loc[revised.index[-1], "close"] = revised["close"].iloc[-1] * 1.01
    monkeypatch.setattr(
        amendment_builder, "load_symbol", lambda symbol, plane_id, repo_root: revised
    )
    with pytest.raises(SystemExit, match="restated an individual price"):
        amendment_builder._validate_live_b_plane_tracks_registration(registered)


_B_PRICES = ["open", "high", "low", "close"]


def _b_live(monkeypatch, registered, mutate):
    live = mutate(registered.copy())
    monkeypatch.setattr(
        amendment_builder, "load_symbol", lambda symbol, plane_id, repo_root: live
    )


def _b_rescale(frame, factor):
    return frame.assign(**{c: frame[c] * factor for c in _B_PRICES})


@pytest.mark.skipif(not SNAPSHOT_READY, reason="registered B snapshot not present")
@pytest.mark.parametrize(
    ("label", "factor"),
    (
        # auto_adjust rescales the whole elapsed window on every FUTURE ex-dividend. That
        # is return-preserving, so it must NOT fire — banding the price LEVEL instead of
        # the uniformity would red the fleet on Barrick's next ordinary dividend.
        ("routine ~$0.10 quarterly dividend", 0.9976),
        ("small $0.02 dividend", 0.99951),
        ("tiny $0.005 dividend", 0.999878),
        ("deep re-adjustment", 0.85),
    ),
)
def test_b_tripwire_passes_return_preserving_rescales(
    monkeypatch, label, factor
):
    registered = amendment_builder._load_registered_b_prefix()
    _b_live(monkeypatch, registered, lambda f: _b_rescale(f, factor))
    amendment_builder._validate_live_b_plane_tracks_registration(registered)


@pytest.mark.skipif(not SNAPSHOT_READY, reason="registered B snapshot not present")
@pytest.mark.parametrize(
    ("label", "mutate", "expected"),
    (
        (
            # A real split rescales share counts as well as prices, so it is caught on the
            # volume channel rather than by the price level.
            "2:1 split",
            lambda f: _b_rescale(f, 0.5).assign(volume=f["volume"] * 2.0),
            "restated settled volume",
        ),
        (
            # Below the old blanket 1e-2 volume tolerance, so this used to pass silently.
            "settled volume restated +0.5%",
            lambda f: f.assign(
                volume=f["volume"].mask(f.index == f.index[10], f["volume"] * 1.005)
            ),
            "restated settled volume",
        ),
        (
            "one-column restatement above the float32 grid",
            lambda f: f.assign(
                open=f["open"].mask(f.index == f.index[500], f["open"] * (1 + 2e-6))
            ),
            "restated an individual price",
        ),
        (
            "segment restatement changes relative prices",
            lambda f: pd.concat([_b_rescale(f.iloc[:800], 1.001), f.iloc[800:]]),
            "NON-UNIFORMLY",
        ),
        (
            "asof volume blowout",
            lambda f: f.assign(
                volume=f["volume"].mask(f.index == f.index[-1], f["volume"] * 1.5)
            ),
            "ASOF-session volume",
        ),
        (
            "broken vendor frame",
            lambda f: _b_rescale(f, 100.0),
            "broken vendor frame",
        ),
    ),
)
def test_b_tripwire_fires_on_real_revisions(monkeypatch, label, mutate, expected):
    registered = amendment_builder._load_registered_b_prefix()
    _b_live(monkeypatch, registered, mutate)
    with pytest.raises(SystemExit) as excinfo:
        amendment_builder._validate_live_b_plane_tracks_registration(registered)
    assert expected in str(excinfo.value), label


@pytest.mark.skipif(not RESULT_READY, reason="registered W1-A1 result not produced")
def test_b_addendum_parquets_are_b_only_on_baskets_with_zero_authority():
    paths = (
        DATA / "fingerprints/amendments/w1a1_b_fingerprint_v0.parquet",
        DATA / "state/amendments/w1a1_b_state_daily.parquet",
        DATA / "episodes/amendments/w1a1_b_episode_catalog_v0.parquet",
    )
    for path in paths:
        frame = pd.read_parquet(path)
        assert set(frame["symbol"].astype(str)) == {"B"}
        assert set(frame["price_plane_id"].astype(str)) == {PLANE_BASKETS}
        for key in AUTHORITY_KEYS:
            assert f"authority_{key}" in frame.columns
            assert not frame[f"authority_{key}"].any()
    states = pd.read_parquet(paths[1])
    episodes = pd.read_parquet(paths[2])
    assert pd.to_datetime(states["date"]).max() <= pd.Timestamp("2026-08-13")
    for column in ("start_date", "anchor_date", "end_date", "resolution_known_date"):
        assert pd.to_datetime(episodes[column]).max() <= pd.Timestamp("2026-08-13")

    fingerprint = pd.read_parquet(paths[0])
    assert len(fingerprint) == 1
    pct_columns = [c for c in fingerprint.columns if c.endswith("__pct")]
    for column in pct_columns:
        values = fingerprint[column].dropna()
        assert values.between(0.0, 100.0).all()


@pytest.mark.skipif(not RESULT_READY, reason="registered W1-A1 result not produced")
def test_b_episode_json_and_governing_receipt_are_zero_authority():
    episode_json = json.loads(
        (DATA / "episodes/amendments/B.json").read_text(encoding="utf-8")
    )
    assert is_zero_authority(episode_json)
    assert episode_json["symbol"] == "B"
    assert all(row["symbol"] == "B" for row in episode_json["episodes"])
    assert is_zero_authority(_receipt())


def test_rank_context_is_frozen_hypothetical_insertion_only():
    context = _receipt()["rank_context"]
    assert context["frozen_reference_rows"] == 2780
    assert context["hypothetical_joint_rows"] == 2781
    assert context["only_B_persisted"] is True
    assert context["w1_percentiles_rewritten"] is False
    assert context["univ_ew_recomputed"] is False
    assert "GOLD dealer context" in context["dealer_context_disclosure"]
    assert context["reference_sha256"] == amendment_builder.REFERENCE_SHA256
    assert "no sweep" in _receipt()["trial_budget"]


def test_output_allowlist_is_exact_and_disjoint_from_sealed_artifacts():
    expected = (
        "data/stock_identity/amendments/w1a1_gold_wrong_issuer.json",
        "data/stock_identity/fingerprints/amendments/w1a1_b_fingerprint_v0.parquet",
        "data/stock_identity/state/amendments/w1a1_b_state_daily.parquet",
        "data/stock_identity/episodes/amendments/w1a1_b_episode_catalog_v0.parquet",
        "data/stock_identity/episodes/amendments/B.json",
        "research/stock_identity/dossiers/B.md",
        "research/stock_identity/dossiers/B.svg",
    )
    assert amendment_builder.OUTPUT_PATHS == expected
    assert set(expected).isdisjoint(SEALED_SHA256)


def test_result_records_exact_allowlist_and_prerequisite_merges():
    assert tuple(_receipt()["registered_output_paths"]) == amendment_builder.OUTPUT_PATHS
    assert _receipt()["prerequisite_source_heads"] == (
        pilot.W1A1_PREREQUISITE_SOURCE_HEADS
    )
    assert _receipt()["prerequisite_merges"] == pilot.W1A1_PREREQUISITE_MERGES


@pytest.mark.skipif(not RESULT_READY, reason="registered W1-A1 result not produced")
def test_b_dossier_and_svg_disclose_the_2014_floor():
    markdown = (
        ROOT / "research/stock_identity/dossiers/B.md"
    ).read_text(encoding="utf-8")
    for token in (
        "Barrick Mining Corporation", "756894", "W1-A1 addendum", "Zero authority",
        "baskets_ohlcv_v1", "2014-01-02", "no existing rank changed",
        "only B was ranked and no W1 row was recomputed or rewritten",
    ):
        assert token in markdown
    assert "pre-2014 portion" in markdown
    gap_line = next(line for line in markdown.splitlines() if "Gap basis" in line)
    assert "`open_vs_prev_close`" in gap_line
    assert "opening print is compared with the previous close" in gap_line
    assert "close-to-close proxy" not in gap_line
    svg = (ROOT / "research/stock_identity/dossiers/B.svg").read_text(encoding="utf-8")
    assert "2014-01-02" in svg
    assert svg.count("<dc:date>2026-08-14T00:00:00+00:00</dc:date>") == 1


def test_pre_registration_exposure_is_disclosed_and_quarantined():
    deviation = _receipt()["procedural_deviation"]
    assert deviation == pilot.W1A1_PROCEDURAL_DEVIATION
    assert _receipt()["trial_budget"] == pilot.W1A1_TRIAL_BUDGET
