"""Stock Identity W1-A1 — append-only wrong-issuer correction guards.

The suite is committed before the registered artifact run and skips as a unit until
the governing receipt exists.  On the result commit it becomes mandatory: exact W1
hashes, reversible GOLD disclosure, B-only outputs, effective roster, source plane,
rank context, prerequisite merges, and all-false authority are all closed here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from engine.stock_identity import hygiene
from engine.stock_identity import partition as partition_mod
from engine.stock_identity import pilot
from engine.stock_identity.authority import AUTHORITY_KEYS, is_zero_authority
from engine.stock_identity.plane import PLANE_BASKETS, primary_planes
from scripts import stock_identity_build_atlas as sealed_builder
from scripts import stock_identity_build_w1a1 as amendment_builder

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "stock_identity"
REGISTRATION = ROOT / "research/stock_identity/W1_IDENTITY_ATLAS_V0_REGISTRATION.md"
RECEIPT = ROOT / amendment_builder.RECEIPT_RELATIVE_PATH
RESULT_READY = RECEIPT.exists()
PREREQUISITE_READY = (ROOT / amendment_builder.B_SOURCE_RELATIVE_PATH).exists()

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
ORIGINAL_GOLD_MD_SHA256 = "2675b5be60cc09a37324e697bb62c20679b8f21cfe4d268f5082ce0730861558"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _receipt() -> dict:
    if not RESULT_READY:
        pytest.skip("registered W1-A1 result has not been produced yet")
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def _manifest() -> dict:
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
    assert partition_mod.partition_procedure_sha256(REGISTRATION)[0] == _manifest()[
        "partition_procedure_sha256"
    ]
    assert text.index("## Amendment A1") > text.index("## §14. Hashes")
    assert amendment_builder.AMENDMENT_ID in text


def test_result_records_the_registration_commits():
    receipt = _receipt()
    assert receipt["registration_commit"] == amendment_builder.REGISTRATION_COMMIT
    assert receipt["initial_registration_commit"] == amendment_builder.INITIAL_REGISTRATION_COMMIT


def test_b_remains_outside_every_sealed_w1_membership():
    manifest = _manifest()
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
        assert _sha256(ROOT / relative) == expected, relative


def test_result_declares_that_no_sealed_measurement_was_mutated():
    assert _receipt()["measured_rows_mutated"] is False


@pytest.mark.skipif(not RESULT_READY, reason="registered W1-A1 result not produced")
def test_gold_disclosure_is_reversible_and_names_the_actual_instruments():
    path = ROOT / amendment_builder.DISCLOSURE_ONLY_PATH
    text = path.read_text(encoding="utf-8")
    begin = amendment_builder.GOLD_ANNOTATION_BEGIN
    end = amendment_builder.GOLD_ANNOTATION_END
    assert text.count(begin) == text.count(end) == 1
    assert text.index(begin) < text.index("## Identity")
    block = text[text.index(begin): text.index(end) + len(end)]
    for token in (
        "Gold.com", "A-Mark", "bullion dealer", "1591588", "756894",
        "2025-12-02", "2025-05-09", "not miner-neighborhood evidence",
    ):
        assert token in block
    restored = text.replace(f"\n\n{block}\n\n", "\n\n", 1)
    assert hashlib.sha256(restored.encode("utf-8")).hexdigest() == ORIGINAL_GOLD_MD_SHA256
    disclosure = _receipt()["disclosure_only"]
    assert _sha256(path) == disclosure["after_sha256"]
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
    for token in ("Gold.com", "1591588", "756894", "2025-12-02", "2025-05-09"):
        assert token in note


@pytest.mark.skipif(not PREREQUISITE_READY, reason="PR #5632 prerequisite not present")
def test_ack_status_tail_records_the_curated_repair():
    config = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8"))
    ack = config["quality"]["reused_ticker_acks"]["GOLD"]
    for token in ("1591588", "756894", "PR #5632"):
        assert token in ack
    assert "KNOWN CONSUMER DEFECT" not in ack
    assert "NO store file under 'B'" not in ack


@pytest.mark.skipif(not PREREQUISITE_READY, reason="PR #5632 prerequisite not present")
def test_b_source_is_exactly_the_registered_curated_plane():
    path = ROOT / amendment_builder.B_SOURCE_RELATIVE_PATH
    assert _sha256(path) == amendment_builder.B_SOURCE_SHA256
    frame = pd.read_parquet(path)
    assert len(frame) == 3172
    assert frame.index.min() == pd.Timestamp("2014-01-02")
    assert frame.index.max() == pd.Timestamp("2026-08-13")
    assert primary_planes(ROOT)["B"] == PLANE_BASKETS
    assert not (DATA / "ohlcv/B.parquet").exists()


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
    assert _receipt()["prerequisite_merges"] == {
        "pr_5613": amendment_builder.PR_5613_MERGE_SHA,
        "pr_5632": amendment_builder.PR_5632_MERGE_SHA,
    }


@pytest.mark.skipif(not RESULT_READY, reason="registered W1-A1 result not produced")
def test_b_dossier_and_svg_disclose_the_2014_floor():
    markdown = (ROOT / "research/stock_identity/dossiers/B.md").read_text(encoding="utf-8")
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
    assert deviation["status"] == "DISCLOSED_PRE_REGISTRATION_IMPLEMENTATION_EXPOSURE"
    assert "no repository artifacts written" in deviation["write_scope"]
    assert "cannot choose outputs" in deviation["consequence"]
