"""tests/test_sf_seeds.py — harvest_seeds with all sources absent returns [] + notes."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from engine.signal_foundry.seeds import harvest_seeds


def test_all_sources_absent_returns_notes_only(tmp_path):
    """When no source files exist, harvest_seeds returns note entries (not empty list)."""
    seeds = harvest_seeds(repo_root=tmp_path)
    # Should return a list (not raise)
    assert isinstance(seeds, list)
    # All entries should be 'note' kind (skipped sources)
    note_seeds = [s for s in seeds if s.get("kind") == "note"]
    assert len(note_seeds) > 0, (
        f"Expected note entries for absent sources, got: {seeds}"
    )
    # No other kinds should be present when nothing exists
    non_note = [s for s in seeds if s.get("kind") not in {"note"}]
    assert len(non_note) == 0, f"Unexpected non-note seeds: {non_note}"


def test_seed_schema_keys_present(tmp_path):
    """Every seed entry has required keys."""
    seeds = harvest_seeds(repo_root=tmp_path)
    required_keys = {"source", "ref", "summary", "data_hint", "kind"}
    for i, seed in enumerate(seeds):
        missing = required_keys - set(seed.keys())
        assert missing == set(), f"Seed [{i}] missing keys: {missing} — full seed: {seed}"


def test_causal_mechanisms_read(tmp_path):
    """When causal_mechanisms.jsonl exists with screened_candidate entries, they are harvested."""
    import json
    neuro_dir = tmp_path / "data" / "neuralweb"
    neuro_dir.mkdir(parents=True)
    mech_file = neuro_dir / "causal_mechanisms.jsonl"
    entry = {
        "edge_id": "edge_001",
        "cause_id": "BAMLH0A0HYM2",
        "target_id": "SPY",
        "verdict": "screened_candidate",
        "causal_support": {"correlation": "strong"},
    }
    with mech_file.open("w") as fh:
        fh.write(json.dumps(entry) + "\n")

    seeds = harvest_seeds(repo_root=tmp_path)
    causal_seeds = [s for s in seeds if s.get("kind") == "causal_edge"]
    assert len(causal_seeds) >= 1, f"Expected causal_edge seeds, got: {seeds}"
    assert any("edge_001" in s.get("ref", "") for s in causal_seeds)


def test_surprise_queue_read(tmp_path):
    """When surprise queue exists, its entries are harvested."""
    import json
    neuro_dir = tmp_path / "data" / "neuralweb"
    neuro_dir.mkdir(parents=True)
    sq_file = neuro_dir / "causal_surprise_queue.jsonl"
    entry = {"id": "sq_001", "name": "Surprise signal", "thesis": "test thesis"}
    with sq_file.open("w") as fh:
        fh.write(json.dumps(entry) + "\n")

    seeds = harvest_seeds(repo_root=tmp_path)
    sq_seeds = [s for s in seeds if s.get("kind") == "surprise_queue"]
    assert len(sq_seeds) >= 1, f"Expected surprise_queue seeds, got: {seeds}"


def test_research_factory_absent_gives_note(tmp_path):
    """When research_factory candidates.jsonl is absent, a note is returned."""
    seeds = harvest_seeds(repo_root=tmp_path)
    rf_notes = [s for s in seeds
                if "research_factory" in s.get("source", "").lower()
                or "candidates.jsonl" in s.get("source", "").lower()]
    assert any(s.get("kind") == "note" for s in rf_notes), (
        f"Expected research_factory note for absent file, got: {rf_notes}"
    )


def test_harvest_seeds_idempotent(tmp_path):
    """Calling harvest_seeds twice returns the same count."""
    seeds1 = harvest_seeds(repo_root=tmp_path)
    seeds2 = harvest_seeds(repo_root=tmp_path)
    assert len(seeds1) == len(seeds2), "harvest_seeds is not idempotent"
